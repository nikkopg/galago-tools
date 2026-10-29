"""The Galago adapter for the Formulatrix STACK plate-transfer manager.

It maps each command 1:1 onto a StackService method and holds no instrument
policy of its own -- every decision (identity probe, session, validation,
failure latch, transfer sequencing) lives in the stack-automation-layer core.
The core is obtained only through composition.open_service with owner
"galago", so galago and the core's own MCP front end contend on the same owner
lock. This module never imports the core's MCP adapter subpackage.

Transfer is the one motion path and the one multi-call command (D-12): a fresh
step key runs plan_transfer, a write-ahead ledger record, execute_transfer,
one wait and the terminal ledger record in a single command (_run_fresh, the
only place either core call is made). The step ledger (tools/stack/ledger.py)
is what guarantees a step key is never submitted twice: a repeated step key is
replayed (a recent ran), re-attached read-only (a started record, through
wait_transfer only) or refused with its next action, and never re-sent. The
reads, including GetFailureLatch, answer while a Transfer runs; a second
Transfer is refused (NOT_READY while BUSY, the motion lock on a direct call).
No adapter path acknowledges, cancels, retries or goes to the safe position:
AcknowledgeFailure is a separate, operator-confirmed command and never touches
the ledger.

A result is turned into a reply by its ``kind``: only the explicit allowlist
in _SUCCESS_KINDS yields SUCCESS; every other result (a refusal, a failed
read, an unknown shape) is an ERROR_FROM_TOOL carrying a one-line message.
"""
import argparse
import contextlib
import logging
import math
import os
import re
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Iterator, Optional, cast

import grpc
from google.protobuf import message
from google.protobuf.struct_pb2 import Struct
from stack_automation_layer.composition import OwnedService, open_service
from stack_automation_layer.model import Location, TransferRequest
from stack_automation_layer.owner_lock import endpoint_key
from stack_automation_layer.results import (
    LatchStatus,
    Lost,
    NeedsInput,
    ReadFailed,
    Refused,
    Rejected,
    TaskHandle,
    TimedOut,
    TransferPlan,
)
from stack_automation_layer.service import StackService

from tools.base_server import ToolServer, serve
from tools.grpc_interfaces.stack_pb2 import Command, Config
from tools.grpc_interfaces.tool_base_pb2 import (
    DRIVER_ERROR,
    ERROR_FROM_TOOL,
    FAILED,
    INVALID_ARGUMENTS,
    NOT_READY,
    READY,
    SUCCESS,
    ExecuteCommandReply,
    ResponseCode,
    ToolStatus,
)
from tools.grpc_interfaces.tool_base_pb2 import Command as ToolCommand
from tools.stack.ledger import (
    FRESH,
    MISMATCH,
    REATTACH,
    REFUSE_COMPLETED,
    REFUSE_FAILED,
    REFUSE_OUTCOME_UNKNOWN,
    REFUSE_SUBMITTING,
    REPLAY,
    Decision,
    Ledger,
    LedgerError,
    decide,
    fingerprint,
    is_terminal,
    resolve_ledger_dir,
)

DEFAULT_PORT = 5005

# D-11: the wait budget of one Transfer, in seconds. Transfer.timeout_s wins
# when > 0, then Config.transfer_timeout_s when > 0, then the default; the
# result is clamped (never rejected) to the maximum.
DEFAULT_TRANSFER_TIMEOUT_S = 300.0
MAX_TRANSFER_TIMEOUT_S = 3600.0

# D-11: one read-only wait_transfer slice of the re-attach loop. The core clamps
# each call to its own WAIT_TRANSFER_MAX_S (300 s) anyway.
WAIT_SLICE_S = 300.0

# D-12: one Transfer at a time per tool server. Module level, taken
# non-blocking, so a second Transfer is refused at once rather than queued.
_MOTION_LOCK = threading.Lock()

# WR-01: the longest a Configure waits for in-flight commands to finish before
# it refuses with "busy". A read ends within the core's transport timeouts; a
# Phase 5 Transfer can run for minutes, and a Configure must not park a gRPC
# worker (serve() has 10) behind it, so it is refused instead of queued.
CONFIGURE_DRAIN_TIMEOUT_S = 5.0

# D-01: every handler maps 1:1 onto one StackService method, except Transfer:
# it is the one motion path and the one multi-call command (D-12), so it has no
# single mapped method.
COMMAND_TO_SERVICE_METHOD = {
    "GetManagerState": "manager_state",
    "GetRobotStates": "robot_states",
    "ListDevices": "devices",
    "ListLabwareProfiles": "labware_profiles",
    "ListTransferProfiles": "transfer_profiles",
    "GetLabwarePresence": "labware_presence",
    "GetTransferEstimate": "estimate_transfer",
    "GetFailureLatch": "latch_status",
    "AcknowledgeFailure": "acknowledge_failure",
}

# D-19: every Estimate<Cmd> hook returns one of these local constants (seconds);
# none does I/O, so neither a simulated run nor the EstimateDuration RPC can
# touch the instrument or raise.
EST_TRANSFER_S = 35
EST_TRANSFER_ESTIMATE_S = 3
EST_READ_S = 2
EST_ACK_S = 2

# D-13: the eight read-only commands (oneof field names) that bypass the BUSY
# gate so an operator can read STACK state while a motion command holds the
# tool. get_transfer_estimate is included (D-15): it sends one estimation POST
# and never moves anything. transfer and acknowledge_failure are never in it.
READ_COMMANDS = frozenset({
    "get_manager_state",
    "get_robot_states",
    "list_devices",
    "list_labware_profiles",
    "list_transfer_profiles",
    "get_labware_presence",
    "get_transfer_estimate",
    "get_failure_latch",
})

# WR-05: the core builds "http://{host}:{port}" and sends the STACK credentials
# to it, so a host must be a bare name or address: hostname / IPv4 characters,
# or a bracketed IPv6 literal. Anything that could rewrite the URL (@ / ? # \
# whitespace, a scheme prefix, a stray colon) fails the match.
_HOST_RE = re.compile(r"[A-Za-z0-9._\-]+|\[[0-9A-Fa-f:.]+\]")

# D-14: real mode with no service yet.
_NOT_CONFIGURED_MESSAGE = "stack: not configured"

# D-14 (ACK-01): clearing a latch needs the operator to have inspected the arm
# and to say so with exactly "yes".
_ACK_NOT_YES_MESSAGE = (
    "arm_inspected must be exactly 'yes': inspect the arm and recover STACK in "
    "the STACK Manager, then send yes")

# WR-02: a command that arrives while a Configure is swapping the owner is
# refused at once, never parked. ERROR_FROM_TOOL rather than NOT_READY because
# galago-core hides the text of NOT_READY / INVALID_ARGUMENTS replies from the
# operator, and this one is worth seeing: it is transient and the controller
# should retry.
_RECONFIGURING_MESSAGE = "stack: reconfiguring"

# D-12: a second Transfer while one is running is refused, not queued.
_BUSY_MESSAGE = (
    "stack: busy; another Transfer is running in this tool; "
    "wait for it to finish, then re-run this step")

# D-04: operator-visible ledger messages (05-SPIKE.md section 6f).
_LEDGER_UNREADABLE = (
    "stack: step ledger unreadable ({reason}) at {path}; do not delete it; "
    "no transfer was sent")
_WRITE_AHEAD_FAILED = (
    "stack: no transfer was sent; the step ledger could not record the step "
    "({reason}); fix the ledger directory, then re-run this step")
_CLAIMED_ELSEWHERE = (
    "stack: this step key is claimed by another tool server sharing the ledger; "
    "no transfer was sent; re-run this step to see its state")
_EXECUTE_RAISED = (
    "stack: execute failed ({name}); outcome unknown; check the STACK Manager "
    "and GetFailureLatch; this step key will not be re-sent")
_LATER_WRITE_FAILED = (
    "stack: transfer {kind}, but the ledger could not record it; {latch}"
    "re-running this step key will not send a second transfer")

# A-2 (05-SPIKE.md 6f): the latch clause names the guid AcknowledgeFailure must
# be given. Fixed strings, built from latch_status() fields only.
_LATCH_LATCHED = "latched guid {guid}{kind}; inspect the arm, then AcknowledgeFailure"
_LATCH_NOT_LATCHED = "the core did not latch this; inspect the arm"
_LATCH_UNAVAILABLE = "latch status unavailable; read GetFailureLatch"

# XFR-04 (05-SPIKE.md 3): the only execute_transfer results that prove nothing
# was sent, so the step key is released. Matched by isinstance against the
# core's real classes, never by the kind string; anything else is kept.
_RELEASE_TYPES = (Refused, Rejected, NeedsInput, ReadFailed)
_NOT_RE_SENT = "this step key will not be re-sent"
_IN_FLIGHT_OWNER = "step key {key} is still running; re-run that step to re-attach"

# D-07 (05-SPIKE.md 6b, 6f): the repeat-key replies. In every line the guid and
# the next action come before the step key, so a long key is what gets cut.
_MISMATCH = (
    "stack: this step key was used for a different request or STACK; "
    "mint a new step key; step key {key}")
# XFR-06 / A-1 (05-SPIKE.md 6f): a wait that ended without ending the task. The
# record stays started and a re-run of the same step re-attaches.
_STILL_RUNNING = "stack: still running (timedOut); re-run this step to re-attach"
_NOT_ENDED = (
    "stack: lost ({reason}); {latch}; the transfer may still be running; "
    "re-run this step to re-attach")
_RE_ATTACH = "re-run this step to re-attach"

# D-09 as kept by 05-SPIKE.md OQ1: after a restart the core may not own the
# guid, so a non-ran outcome may never have latched.
_RESTART_CLAUSE = (
    "tool restarted mid-transfer; inspect the arm; the core may not have latched "
    "this failure")
_REFUSE_SUBMITTING = (
    "stack: {restart}outcome unknown for this step key; check the STACK Manager "
    "and GetFailureLatch; this step key will not be re-sent; step key {key}")
_REFUSE_OUTCOME_UNKNOWN = (
    "stack: outcome unknown; latched guid {guid}; inspect the arm, then "
    "AcknowledgeFailure; this step key will not be re-sent; step key {key}")
_REFUSE_OUTCOME_UNKNOWN_NO_GUID = (
    "stack: outcome unknown; no latch guid was recorded; read GetFailureLatch; "
    "this step key will not be re-sent; step key {key}")
_REFUSE_COMPLETED = (
    "stack: step key already completed at {at}; the protocol must mint a new "
    "step key per run; nothing was sent; step key {key}")
_REFUSE_FAILED = (
    "stack: {kind}{reason} is recorded for this step key; {latch}; then run the "
    "step under a new step key{task}; step key {key}")

# Result kinds whose cause can latch in the core (failed, aborted and lost
# results, and a refusal because a latch is already held).
_LATCHING_KINDS = frozenset({"failed", "aborted", "lost"})


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _monotonic() -> float:
    """The clock of the re-attach budget. A wrapper so a test can patch it."""
    return time.monotonic()


# D-09: logged once per fresh open. A restart of this tool server silently
# drops the core's in-process failure latch and in-flight guard.
_RESTART_WARNING = (
    "stack: the STACK core keeps its failure latch across a restart, but a "
    "restart during a transfer can lose that task's ownership so its failure "
    "never latches; inspect the arm after any mid-transfer restart, never "
    "delete the core's state file, and acknowledge a failure, never restart "
    "it away"
)

# D-10: the explicit, case-sensitive allowlist of result kinds that are SUCCESS.
# knowledgeRefreshed, validationReport, transferPlan, cancelRequested and a
# TaskHandle's "transfer" are deliberately absent.
_SUCCESS_KINDS = frozenset({
    "managerState",
    "deviceTree",
    "robotStates",
    "labwareProfiles",
    "transferProfiles",
    "labwarePresence",
    "estimated",
    "failureAcknowledged",
    "latchStatus",
    "ran",
})


class _ConfigureRefused(RuntimeError):
    """A Configure that was refused with nothing changed: no setting applied and
    the current owner kept. Unlike every other Configure failure it neither
    drops the owner nor leaves the tool FAILED (WR-02)."""


class _ConfigureBusy(_ConfigureRefused):
    """A Configure that could not drain the in-flight commands in time."""


def _text_or_none(cmd: Any, field: str) -> Optional[str]:
    """An instrument field, or None when it is unset or blank. proto3 presence
    is True for an explicit "" (Pitfall 8), so a blank is treated as unset; a
    non-blank value passes unchanged -- the adapter applies no instrument rule."""
    if not cmd.HasField(field):
        return None
    value = getattr(cmd, field)
    return value if value.strip() else None


def _flag(cmd: Any, field: str) -> bool:
    """An optional bool field: unset is False."""
    return bool(cmd.HasField(field) and getattr(cmd, field))


def _transfer_request(cmd: Any) -> TransferRequest:
    """Build the core's TransferRequest from a GetTransferEstimate or Transfer
    command (they share the ten instrument field names), blank or unset fields
    as None (the core's missing_fields, not this adapter, decides what is
    incomplete)."""
    return TransferRequest(
        robot=_text_or_none(cmd, "robot"),
        labware_profile=_text_or_none(cmd, "labware_profile"),
        source=Location(
            device=_text_or_none(cmd, "source_device"),
            deck=_text_or_none(cmd, "source_deck"),
            nest=_text_or_none(cmd, "source_nest"),
            transfer_profile=_text_or_none(cmd, "source_transfer_profile"),
        ),
        destination=Location(
            device=_text_or_none(cmd, "destination_device"),
            deck=_text_or_none(cmd, "destination_deck"),
            nest=_text_or_none(cmd, "destination_nest"),
            transfer_profile=_text_or_none(cmd, "destination_transfer_profile"),
        ),
    )


def _one_line(text: str, limit: int) -> str:
    """Collapse all whitespace runs to single spaces, then truncate to
    `limit` characters, adding "..." when cut."""
    collapsed = " ".join(text.split())
    if len(collapsed) > limit:
        return collapsed[: max(limit - 3, 0)] + "..."
    return collapsed


def _reply(code: ResponseCode, *, message: str = "",
           meta: Optional[dict] = None) -> ExecuteCommandReply:
    """Always sets return_reply=True. When meta is given, builds a Struct,
    calls update(meta) and copies it into meta_data."""
    reply = ExecuteCommandReply(response=code, error_message=message, return_reply=True)
    if meta is not None:
        s = Struct()
        s.update(meta)
        reply.meta_data.CopyFrom(s)
    return reply


def _check_args(command: message.Message) -> list[str]:
    """D-17: the adapter's own argument rules, identical in both modes. Only
    arguments this adapter owns are checked; instrument fields (robot, nests,
    profiles) are the core's business. Returns a list of problems, [] when ok."""
    problems: list[str] = []
    cmd = cast(Any, command)
    if type(command).__name__ == "Transfer":
        if not (cmd.HasField("step_key") and cmd.step_key.strip()):
            problems.append("step_key is required")
        if cmd.HasField("timeout_s"):
            value = cmd.timeout_s
            if not math.isfinite(value) or value < 0:
                problems.append(f"timeout_s must be a finite number >= 0 (got {value!r})")
    elif type(command).__name__ == "AcknowledgeFailure":
        if not (cmd.HasField("guid") and cmd.guid.strip()):
            problems.append("guid is required")
        # Exact match only: no strip, no case folding, no default (T-04-16).
        if not (cmd.HasField("arm_inspected") and cmd.arm_inspected in ("yes", "no")):
            got = repr(cmd.arm_inspected) if cmd.HasField("arm_inspected") else "unset"
            problems.append(f"arm_inspected must be exactly 'yes' or 'no' (got {got})")
    return problems


def _find_guid(d: dict) -> Optional[str]:
    """First non-empty guid string among d["guid"], d["task"]["guid"],
    d["handle"]["guid"], d["detail"]["guid"]."""
    candidates: list[Any] = [d.get("guid")]
    for key in ("task", "handle", "detail"):
        inner = d.get(key)
        candidates.append(inner.get("guid") if isinstance(inner, dict) else None)
    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def _hint(d: dict[str, Any]) -> Optional[str]:
    """One bounded structured hint for the operator line (D-11, Open Question
    2): needsInput's missing fields, the first rejected finding's name, or the
    readFailed error name (with its HTTP status when an int). Never any
    free-text explanation, message or detail from the core."""
    kind = d.get("kind")
    if kind == "needsInput":
        missing = d.get("missing")
        if isinstance(missing, list):
            names = [m for m in missing if isinstance(m, str) and m]
            if names:
                return "missing: " + ", ".join(names)
    elif kind == "rejected":
        findings = d.get("findings")
        if isinstance(findings, list) and findings and isinstance(findings[0], dict):
            name = findings[0].get("name")
            if isinstance(name, str) and name:
                return f"finding: {name}"
    elif kind == "readFailed":
        error = d.get("error")
        if isinstance(error, dict):
            name = error.get("name")
            if isinstance(name, str) and name:
                status = error.get("status")
                if isinstance(status, int) and not isinstance(status, bool):
                    return f"error: {name} (HTTP {status})"
                return f"error: {name}"
    return None


def _error_line(d: dict) -> str:
    """One-line operator message from a non-success result dict (D-11): the
    kind, the reason when present, the guid when present, then at most one
    bounded structured hint. Never the explanation, message, detail text or
    error.detail."""
    kind = d.get("kind")
    if not isinstance(kind, str) or not kind:
        return "stack: unrecognised result"
    line = f"stack: {kind}"
    reason = d.get("reason")
    if isinstance(reason, str) and reason:
        line += f" ({reason})"
    guid = _find_guid(d)
    if guid:
        line += f", guid {guid}"
    hint = _hint(d)
    if hint:
        line += f"; {hint}"
    return _one_line(line, 300)


def _ledger_error_reply(exc: Exception, path: str) -> ExecuteCommandReply:
    """D-04: the ledger cannot be trusted, so nothing was sent. A ValueError
    (a relative Config.ledger_dir) is reported as "invalid". Built from the
    structured reason only, never str(exc)."""
    reason = exc.reason if isinstance(exc, LedgerError) else "invalid"
    shown = exc.path if isinstance(exc, LedgerError) else path
    return _reply(ERROR_FROM_TOOL, message=_one_line(
        _LEDGER_UNREADABLE.format(reason=reason, path=shown), 300))


def _can_latch(d: Any) -> bool:
    """True for a result dict whose cause can leave a failure latch held."""
    if not isinstance(d, dict):
        return False
    kind = d.get("kind")
    return kind in _LATCHING_KINDS or (
        kind == "refused" and d.get("reason") == "failureLatched")


def _latch_clause(service: Any) -> str:
    """A-2: what the operator must acknowledge, read from latch_status() (one
    zero-I/O call) and never from the core's explanation text. Never raises:
    an exception or an unexpected answer reads as "unavailable"."""
    try:
        status = service.latch_status()
    except Exception:
        return _LATCH_UNAVAILABLE
    if not isinstance(status, LatchStatus):
        return _LATCH_UNAVAILABLE
    if status.latched is False:
        return _LATCH_NOT_LATCHED
    if status.latched is True and isinstance(status.guid, str) and status.guid.strip():
        kind = status.result_kind
        shown = f" ({kind})" if isinstance(kind, str) and kind else ""
        return _one_line(_LATCH_LATCHED.format(guid=status.guid.strip(), kind=shown), 300)
    return _LATCH_UNAVAILABLE


def _transfer_error_reply(service: Any, result: Any) -> ExecuteCommandReply:
    """A Transfer error reply. When the cause can latch, the line names the
    guid from latch_status() first (ACK-02, A-2: the first latch wins in the
    core, so the result's own guid may not be the one to acknowledge) and labels
    the result's guid only as "task guid". The reason is capped inside the line
    so the latched guid always sits within the 300-character cap. Meta is the
    result's to_dict() unchanged. Every other result keeps _result_reply."""
    to_dict = getattr(result, "to_dict", None)
    d = to_dict() if callable(to_dict) else result
    if not _can_latch(d):
        return _result_reply(result)
    line = f"stack: {d['kind']}"
    reason = d.get("reason")
    if isinstance(reason, str) and reason:
        line += f" ({_one_line(reason, 60)})"
    line += f"; {_latch_clause(service)}"
    guid = _find_guid(d)
    if guid:
        line += f"; task guid {guid}"
    hint = _hint(d)
    if hint:
        line += f"; {hint}"
    return _reply(ERROR_FROM_TOOL, message=_one_line(line, 300), meta=d)


def _latched_guid(service: Any) -> Optional[str]:
    """The guid latch_status() names right now, or None when the core is not
    latched or cannot say. One zero-I/O call; never raises."""
    try:
        status = service.latch_status()
    except Exception:
        return None
    if isinstance(status, LatchStatus) and status.latched is True and isinstance(
            status.guid, str) and status.guid.strip():
        return status.guid.strip()
    return None


def _with_suffix(reply: ExecuteCommandReply, suffix: str) -> ExecuteCommandReply:
    """Append a fixed clause to a reply's message, cutting the front part (never
    the clause) so the line stays within 300 characters."""
    if suffix:
        reply.error_message = _one_line(
            reply.error_message, 300 - len(suffix)) + suffix
    return reply


def _in_flight_owner_clause(ledger: Ledger, d: dict[str, Any], own_key: str) -> str:
    """A-3: an inFlight refusal whose guid is the handle guid of another step
    key's record names that key. Empty when there is no such record or the
    ledger cannot be read."""
    detail = d.get("detail")
    guid = detail.get("guid") if isinstance(detail, dict) else None
    if not isinstance(guid, str) or not guid:
        return ""
    try:
        owner = ledger.find_by_guid(guid)
    except LedgerError:
        return ""
    if owner is None or owner == own_key:
        return ""
    return "; " + _IN_FLIGHT_OWNER.format(key=owner)


def _non_terminal_reply(service: Any, result: Any, d: Any) -> ExecuteCommandReply:
    """XFR-06 / A-1: a wait result that did not end the task (timedOut,
    lost(pollFailed), cancelled, anything else). The record stays started, so
    every such reply tells the operator to re-run the step to re-attach. The
    task guid comes last; a lost result names the latch first (A-2)."""
    meta = d if isinstance(d, dict) else None
    kind = d.get("kind") if isinstance(d, dict) else None
    guid = _find_guid(d) if isinstance(d, dict) else None
    task = f"; task guid {guid}" if guid else ""
    if kind == "timedOut":
        return _reply(ERROR_FROM_TOOL, message=_one_line(_STILL_RUNNING + task, 300), meta=meta)
    if kind == "lost" and isinstance(d, dict):
        reason = d.get("reason")
        shown = _one_line(reason, 60) if isinstance(reason, str) and reason else "unknown"
        line = _NOT_ENDED.format(reason=shown, latch=_latch_clause(service)) + task
        return _reply(ERROR_FROM_TOOL, message=_one_line(line, 300), meta=meta)
    return _with_suffix(_transfer_error_reply(service, result), f"; {_RE_ATTACH}")


def _with_restart_clause(service: Any, reply: ExecuteCommandReply, d: Any) -> ExecuteCommandReply:
    """D-09: after a restart the core may not own the guid, so a non-ran outcome
    may never have latched. Append the arm-inspection clause, preceded by the
    current latch clause unless the reply already carries it (a latching result).
    The front of the line is cut, never these clauses, so the latched guid stays
    inside the 300-character cap."""
    latch = "" if _can_latch(d) else f"{_latch_clause(service)}; "
    return _with_suffix(reply, f"; {latch}{_RESTART_CLAUSE}")


def _ledger_meta(key: str, record: dict[str, Any], **extra: Any) -> dict[str, Any]:
    """D-10: the meta of every ledger-generated reply, {stepKey, ledgerState}
    plus whatever the reply adds (a replay adds result and replayed)."""
    return {"stepKey": key, "ledgerState": record.get("state"), **extra}


def _result_reply(result: Any) -> ExecuteCommandReply:
    """Map a core result onto a reply (D-10, D-12): meta is to_dict()
    unchanged; SUCCESS only for a kind in the allowlist."""
    to_dict = getattr(result, "to_dict", None)
    d = to_dict() if callable(to_dict) else result
    if not isinstance(d, dict):
        return _reply(ERROR_FROM_TOOL, message="stack: unrecognised result")
    if d.get("kind") in _SUCCESS_KINDS:
        return _reply(SUCCESS, meta=d)
    return _reply(ERROR_FROM_TOOL, message=_error_line(d), meta=d)


class StackServer(ToolServer):
    toolType = "stack"
    config: Config
    # WR-02: True from a failed Configure until the next successful one.
    _configure_failed = False

    def __init__(self) -> None:
        super().__init__()
        self._owned: Optional[OwnedService] = None
        self.service: Optional[StackService] = None
        self._transfer_timeout_s: float = 0.0
        self._ledger_dir: str = ""
        # WR-02: the status a refused Configure must leave standing, per thread
        # (base Configure sets FAILED on the same thread right after _configure).
        self._refused = threading.local()
        # D-05: minted once per server; a ledger record carries it so a later
        # plan can tell a record of this process from one left by a restart.
        self._instance: str = uuid.uuid4().hex
        # WR-03: serve() runs commands on a thread pool. _configure_lock
        # serialises Configures; _state guards _readers/_reconfiguring so a
        # Configure waits (bounded) for in-flight commands to finish before it
        # closes the owner, and a command that arrives meanwhile is refused.
        self._read_bypass = threading.local()
        # WR-02: the service a command was admitted against, per thread.
        self._admitted = threading.local()
        self._configure_lock = threading.Lock()
        self._state = threading.Condition()
        self._readers = 0
        self._reconfiguring = False

    @property
    def last_error(self) -> Optional[str]:
        value: Optional[str] = self.__dict__.get("_last_error", "")
        return value

    @last_error.setter
    def last_error(self, value: Optional[str]) -> None:
        """WR-04: GetStatus.error_message is the operator's view of the tool's
        last failure. A bypassed read must not clear or overwrite it (base
        _dispatchCommand writes it on every reply), or a concurrent read could
        erase a motion command's failure text with no change in status. Writes
        made on a thread that is inside a bypassed read are dropped; the read's
        own outcome is in its reply. Thread-local, so a motion command's write
        on another thread is never suppressed and never overwritten by a stale
        restore. The one deliberate exception is the bypass's own exception
        handler, which still records the error (D-13)."""
        bypass = self.__dict__.get("_read_bypass")  # absent while base __init__ runs
        if bypass is not None and getattr(bypass, "active", False):
            return
        self.__dict__["_last_error"] = value

    def _teardown(self) -> None:
        """Drop the current owner, if any, so "no service" always holds after
        this returns or raises (WR-01). The references are cleared first, under
        _state so a command admitted later sees them change together, and the
        close runs after, outside _state: the core's OwnedService.close() marks
        itself closed before it closes the transport, so a transport close that
        raises would otherwise skip the lock release and leave a dead service
        looking usable. The owner lock is therefore released in a finally
        (OwnerLock.release() is idempotent), which is a no-op after a clean
        close. Callers hold _exclusive(), so no command is using the owner."""
        with self._state:
            owned, self._owned, self.service = self._owned, None, None
        if owned is None:
            return
        try:
            owned.close()
        finally:
            lock = getattr(owned, "_lock", None)
            if lock is not None:
                lock.release()

    def _configure(self, config: Config) -> None:
        """Apply a real-mode Config. Any failure -- a validation error as much
        as a failed open -- drops the current owner (WR-02), so the FAILED
        status base Configure then reports always means "no service": a read
        can never keep answering from a previously configured STACK while
        GetStatus says the tool is not configured. The one exception is a busy
        refusal (_ConfigureBusy): nothing was changed, so a healthy owner is
        kept rather than dropped for the sake of a retry."""
        with self._configure_lock:
            self._refused.status = None
            try:
                self._apply_config(config)
            except _ConfigureRefused:
                self._refused.status = self.status
                raise
            except BaseException as exc:
                if self._owned is not None:
                    # Validation failed before the swap: the owner is still
                    # there. Dropping it needs the same drain as a swap.
                    try:
                        with self._exclusive():
                            self._teardown()
                    except _ConfigureBusy as busy:
                        self._refused.status = self.status
                        raise busy from exc
                self._configure_failed = True
                raise
            self._configure_failed = False

    def setStatus(self, status: ToolStatus) -> None:
        """WR-02: base ExecuteCommand ends every non-read command with
        setStatus(READY), and a command admitted before a failing Configure can
        run that after Configure reported FAILED. READY with no service after a
        failed Configure would then be left standing, so it is held at FAILED
        until the next Configure succeeds.

        WR-02: a Configure refused with nothing changed (_ConfigureRefused)
        leaves the tool as it was, not FAILED: base Configure reports FAILED
        for every exception, but the owner and service are healthy, so the
        status the refusal recorded is restored instead."""
        refused = self.__dict__.get("_refused")  # absent while base __init__ runs
        if status == FAILED and refused is not None:
            prior = getattr(refused, "status", None)
            if prior is not None:
                refused.status = None
                status = prior
        if status == READY and self._configure_failed and self.service is None:
            status = FAILED
        super().setStatus(status)

    @contextlib.contextmanager
    def _exclusive(self) -> Iterator[None]:
        """WR-01/WR-03: hold off new real-mode commands and wait, for at most
        CONFIGURE_DRAIN_TIMEOUT_S, for the in-flight ones to finish. On timeout
        raise _ConfigureBusy having changed nothing. Otherwise run the body
        with no command touching the owner, so a read never meets a transport
        Configure just closed. _state is held only for the wait and the flag
        flips, never across the body's I/O (open_service)."""
        with self._state:
            self._reconfiguring = True
            if not self._state.wait_for(
                    lambda: not self._readers, timeout=CONFIGURE_DRAIN_TIMEOUT_S):
                self._reconfiguring = False
                self._state.notify_all()
                raise _ConfigureBusy(
                    "stack: busy, a command is still running; "
                    "retry Configure when it ends")
        try:
            yield
        finally:
            with self._state:
                self._reconfiguring = False
                self._state.notify_all()

    def _admit(self) -> tuple[bool, Optional[StackService]]:
        """WR-02: admission and the service snapshot, taken together under
        _state. While a Configure is swapping the owner a command is refused at
        once rather than parked, so it can never wake up against a different
        (or no) owner, and it never ties up a gRPC worker waiting for one."""
        with self._state:
            if self._reconfiguring:
                return False, None
            self._readers += 1
            return True, self.service

    def _leave(self) -> None:
        with self._state:
            self._readers -= 1
            if not self._readers:
                self._state.notify_all()

    def _apply_config(self, config: Config) -> None:
        host = config.host.strip()
        if not host:
            raise ValueError("stack: Config.host is required")
        if not _HOST_RE.fullmatch(host):
            raise ValueError(
                "stack: Config.host must be a bare hostname or IP address "
                "(no scheme, path, credentials, port or whitespace)")
        port = config.port or DEFAULT_PORT
        if not 1 <= port <= 65535:
            raise ValueError(f"stack: Config.port must be in 1..65535, got {port}")
        timeout = config.transfer_timeout_s
        if not math.isfinite(timeout) or timeout < 0:
            raise ValueError(
                f"stack: Config.transfer_timeout_s must be finite and >= 0, got {timeout!r}")
        # D-03: a relative path would resolve against whatever the working
        # directory happens to be, so it is refused here, before any owner swap.
        # The raw value is still what is recorded; nothing is created.
        ledger_dir = config.ledger_dir
        if ledger_dir.strip() and not os.path.isabs(ledger_dir.strip()):
            raise ValueError("stack: Config.ledger_dir must be an absolute path")
        self._transfer_timeout_s = timeout
        # Recorded only: resolved lazily at Transfer time, nothing is created here.
        self._ledger_dir = config.ledger_dir
        key = endpoint_key(host, port)
        # Only Configures change _owned, and they are serialised, so this read
        # needs no lock. An unchanged endpoint changes nothing, so it must not
        # drain (or refuse as busy) while commands are running.
        if self._owned is not None and self._owned.endpoint == key:
            return
        with self._exclusive():
            # Close-first: release the old owner lock before opening the new
            # endpoint, so a failed open leaves this tool holding no lock and
            # no service.
            self._teardown()
            owned = open_service(host, port, owner="galago")
            with self._state:
                self._owned = owned
                self.service = owned.service
        logging.warning(_RESTART_WARNING)

    def ExecuteCommand(
        self, request: ToolCommand, context: grpc.ServicerContext
    ) -> ExecuteCommandReply:
        """Override of ToolServer.ExecuteCommand (D-13..D-15, STK-05).

        base_server refuses every command unless READY, sets BUSY for the whole
        command and resets READY in its finally. A read must answer while a
        motion command holds the tool BUSY and must not flip its status, so
        this override bypasses those three for READ_COMMANDS only. It still
        runs the argument check, simulated mode and the real-mode
        not-configured guard because it goes through _dispatchCommand. Never
        calls isReady, parseCommand or setStatus on this path. Every other
        request (a non-stack tool_command, a stack request with no command, any
        non-read command) returns super().ExecuteCommand(request, context)
        unchanged. tools/base_server.py is never edited."""
        if request.WhichOneof("tool_command") == self.toolType:
            stack_command = request.stack
            field_name = stack_command.WhichOneof("command")
            if field_name in READ_COMMANDS:
                command = getattr(stack_command, field_name)
                # WR-04: last_error writes are dropped on this thread for the
                # whole read (see the last_error setter).
                self._read_bypass.active = True
                try:
                    logging.info(f"Running command {command.__class__.__name__}")
                    return self._dispatchCommand(command)
                except Exception as e:
                    logging.error(f"Error on Tool ={self.toolId}")
                    # D-13 locks "an Exception sets last_error": the one write
                    # a bypassed read still makes.
                    self._read_bypass.active = False
                    self.last_error = str(e)
                    return ExecuteCommandReply(
                        response=DRIVER_ERROR, error_message=_one_line(str(e), 500))
                finally:
                    self._read_bypass.active = False
        return super().ExecuteCommand(request, context)

    def _dispatchCommand(self, command: message.Message) -> ExecuteCommandReply:
        # D-17: adapter arguments are checked first, in both modes; the base
        # class then runs the simulated sleep or the handler.
        problems = _check_args(command)
        if problems:
            return _reply(
                INVALID_ARGUMENTS,
                message=_one_line("invalid arguments: " + "; ".join(problems), 500))
        if self.simulated:
            return super()._dispatchCommand(command)
        # D-14: the exact "yes" is checked before admission, so it wins over
        # not-configured and reaches no core. The handler checks it again.
        if (type(command).__name__ == "AcknowledgeFailure"
                and cast(Any, command).arm_inspected != "yes"):
            return _reply(INVALID_ARGUMENTS, message=_ACK_NOT_YES_MESSAGE)
        admitted, service = self._admit()
        if not admitted:
            return _reply(ERROR_FROM_TOOL, message=_RECONFIGURING_MESSAGE)
        local = self._admitted
        previous = (getattr(local, "active", False), getattr(local, "service", None))
        local.active, local.service = True, service
        try:
            if service is None:
                return _reply(NOT_READY, message=_NOT_CONFIGURED_MESSAGE)
            return super()._dispatchCommand(command)
        finally:
            local.active, local.service = previous
            self._leave()

    def _require_service(self) -> StackService:
        """The service this command was admitted against (WR-02), never a
        fresh read of self.service. Outside a dispatch (a handler called
        directly) it falls back to the current service."""
        local = self._admitted
        service = local.service if getattr(local, "active", False) else self.service
        if service is None:
            raise RuntimeError("stack: not configured")
        return cast(StackService, service)

    def GetManagerState(self, params: "Command.GetManagerState") -> ExecuteCommandReply:
        return _result_reply(self._require_service().manager_state())

    def GetRobotStates(self, params: "Command.GetRobotStates") -> ExecuteCommandReply:
        return _result_reply(self._require_service().robot_states())

    def ListDevices(self, params: "Command.ListDevices") -> ExecuteCommandReply:
        service = self._require_service()
        return _result_reply(service.devices(refresh=_flag(params, "refresh")))

    def ListLabwareProfiles(self, params: "Command.ListLabwareProfiles") -> ExecuteCommandReply:
        service = self._require_service()
        return _result_reply(service.labware_profiles(refresh=_flag(params, "refresh")))

    def ListTransferProfiles(self, params: "Command.ListTransferProfiles") -> ExecuteCommandReply:
        service = self._require_service()
        return _result_reply(service.transfer_profiles(refresh=_flag(params, "refresh")))

    def GetLabwarePresence(self, params: "Command.GetLabwarePresence") -> ExecuteCommandReply:
        service = self._require_service()
        return _result_reply(service.labware_presence(_text_or_none(params, "robot")))

    def GetTransferEstimate(self, params: "Command.GetTransferEstimate") -> ExecuteCommandReply:
        service = self._require_service()
        return _result_reply(service.estimate_transfer(_transfer_request(params)))

    def _endpoint(self) -> str:
        """The normalised STACK endpoint this tool serves (part of the request
        fingerprint)."""
        if self._owned is not None:
            return str(self._owned.endpoint)
        return str(endpoint_key(self.config.host.strip(), self.config.port or DEFAULT_PORT))

    def _wait_budget(self, params: Any) -> float:
        """D-11: Transfer.timeout_s when set and > 0, else Config.transfer_timeout_s
        when > 0, else the default, clamped to MAX_TRANSFER_TIMEOUT_S."""
        if params.HasField("timeout_s") and params.timeout_s > 0:
            budget = float(params.timeout_s)
        elif self._transfer_timeout_s > 0:
            budget = self._transfer_timeout_s
        else:
            budget = DEFAULT_TRANSFER_TIMEOUT_S
        return min(budget, MAX_TRANSFER_TIMEOUT_S)

    def Transfer(self, params: "Command.Transfer") -> ExecuteCommandReply:
        """The one motion path and the one multi-call command (D-12): plan,
        write-ahead ledger record, execute, wait, terminal record, guarded by
        the step-key ledger (XFR-03, XFR-05). A repeated step key is decided by
        decide(): replayed (done+ran inside the window), re-attached read-only
        (started), or refused with the guid and the next action; execute_transfer
        is called at most once per step key, except after a released "nothing
        was sent" outcome (D-08). Reads, including GetFailureLatch, answer while
        this runs; a second Transfer meets the motion lock. No path here
        acknowledges, cancels, retries or goes to the safe position."""
        service = self._require_service()
        if not _MOTION_LOCK.acquire(blocking=False):
            return _reply(ERROR_FROM_TOOL, message=_BUSY_MESSAGE)
        try:
            # The key is used byte-exact: no strip, no case folding (D-06).
            key = params.step_key
            request = _transfer_request(params)
            fp = fingerprint(self._endpoint(), request)
            budget = self._wait_budget(params)
            try:
                ledger = Ledger(resolve_ledger_dir(self._ledger_dir))
                existing = ledger.get(key)
            except (LedgerError, ValueError) as exc:
                return _ledger_error_reply(exc, self._ledger_dir)
            decision = decide(existing, fingerprint=fp, instance=self._instance, now=_utcnow())
            if decision.action == FRESH:
                return self._run_fresh(service, ledger, key, fp, request, budget)
            if decision.action == REPLAY and decision.record is not None:
                return _reply(SUCCESS, meta=_ledger_meta(
                    key, decision.record, result=decision.record.get("result"), replayed=True))
            if decision.action == REATTACH and decision.record is not None:
                return self._reattach(
                    service, ledger, key, decision.record, budget, decision.restarted)
            return self._ledger_reply(decision, key, service)
        finally:
            _MOTION_LOCK.release()

    def _ledger_reply(self, decision: Decision, key: str,
                      service: StackService) -> ExecuteCommandReply:
        """The reply for a repeated step key that is not replayed or re-attached:
        a fingerprint mismatch (INVALID_ARGUMENTS) or a refusal (ERROR_FROM_TOOL).
        No branch calls plan_transfer, execute_transfer, wait or wait_transfer
        (A-6); only the refuseFailed row reads latch_status() (zero I/O, once).
        Each line puts the guid and the next action before the step key and is
        cut at 300 characters. Meta is {stepKey, ledgerState} (D-10)."""
        record = decision.record if decision.record is not None else {}
        meta = _ledger_meta(key, record)
        action = decision.action
        if action == MISMATCH:
            return _reply(INVALID_ARGUMENTS, message=_one_line(
                _MISMATCH.format(key=key), 300), meta=meta)
        if action == REFUSE_SUBMITTING:
            restart = f"{_RESTART_CLAUSE}; " if decision.restarted else ""
            line = _REFUSE_SUBMITTING.format(restart=restart, key=key)
        elif action == REFUSE_OUTCOME_UNKNOWN:
            guid = record.get("latchGuid")
            if isinstance(guid, str) and guid.strip():
                line = _REFUSE_OUTCOME_UNKNOWN.format(guid=guid.strip(), key=key)
            else:
                line = _REFUSE_OUTCOME_UNKNOWN_NO_GUID.format(key=key)
        elif action == REFUSE_COMPLETED:
            line = _REFUSE_COMPLETED.format(at=record.get("updatedAt"), key=key)
        elif action == REFUSE_FAILED:
            line = self._refuse_failed_line(service, key, record)
        else:
            line = f"stack: unrecognised ledger decision; nothing was sent; step key {key}"
        return _reply(ERROR_FROM_TOOL, message=_one_line(line, 300), meta=meta)

    @staticmethod
    def _refuse_failed_line(service: StackService, key: str, record: dict[str, Any]) -> str:
        """A done record that is not a ran: repeat the recorded kind, reason and
        task guid, name the latch from latch_status() first (A-2), and say to
        run the step under a new step key."""
        result = record.get("result")
        d = result if isinstance(result, dict) else {}
        kind = d.get("kind")
        reason = d.get("reason")
        guid = _find_guid(d)
        return _REFUSE_FAILED.format(
            kind=kind if isinstance(kind, str) and kind else "unrecognised result",
            reason=f" ({_one_line(reason, 60)})" if isinstance(reason, str) and reason else "",
            latch=_latch_clause(service),
            task=f"; task guid {guid}" if guid else "",
            key=key)

    def _run_fresh(self, service: StackService, ledger: Ledger, key: str, fp: str,
                   request: TransferRequest, budget: float) -> ExecuteCommandReply:
        """The fresh path: plan, write-ahead, execute, started, wait, done. The
        only place plan_transfer and execute_transfer are called, and
        execute_transfer is called exactly once, after the write-ahead claim
        and never in a loop (XFR-05, enforced by the AST invariant tests). Once
        the claim returned, any failure leaves the record at submitting or later
        (never absent), so a repeat of the key cannot reach execute_transfer."""
        plan = service.plan_transfer(request)
        if not isinstance(plan, TransferPlan):
            return _transfer_error_reply(service, plan)
        try:
            claimed = ledger.claim(key, fingerprint=fp, instance=self._instance, now=_utcnow())
        except LedgerError as exc:
            return _reply(ERROR_FROM_TOOL, message=_one_line(
                _WRITE_AHEAD_FAILED.format(reason=exc.reason), 300))
        if not claimed:
            return _reply(ERROR_FROM_TOOL, message=_CLAIMED_ELSEWHERE)
        try:
            outcome = service.execute_transfer(plan.plan_id)
        except Exception as exc:
            # The record stays submitting: the submit may have reached STACK.
            # Only the exception's type is reported, never str(exc).
            return _reply(ERROR_FROM_TOOL, message=_one_line(
                _EXECUTE_RAISED.format(name=type(exc).__name__), 300))
        if isinstance(outcome, _RELEASE_TYPES):
            return self._release(service, ledger, key, outcome)
        if not isinstance(outcome, TaskHandle):
            return self._keep_unknown(service, ledger, key, outcome)
        write_failed = False
        try:
            ledger.mark_started(key, handle=outcome.to_dict(), now=_utcnow())
        except LedgerError:
            write_failed = True
        result = service.wait(outcome, timeout_s=budget)
        return self._finish(service, ledger, key, result, write_failed)

    def _release(self, service: StackService, ledger: Ledger, key: str,
                 outcome: Any) -> ExecuteCommandReply:
        """XFR-04: the core refused or rejected before anything was sent, so the
        write-ahead record is deleted and the operator can fix the cause and
        re-run the step. A failed delete keeps the record (the key then refuses
        a re-run) and says so."""
        reply = _transfer_error_reply(service, outcome)
        suffix = ""
        d = outcome.to_dict()
        if isinstance(outcome, Refused) and d.get("reason") == "inFlight":
            suffix = _in_flight_owner_clause(ledger, d, key)
        try:
            ledger.release(key, now=_utcnow())
        except LedgerError:
            suffix += f"; {_NOT_RE_SENT}"
        return _with_suffix(reply, suffix)

    def _keep_unknown(self, service: StackService, ledger: Ledger, key: str,
                      outcome: Any) -> ExecuteCommandReply:
        """The submit may have reached STACK (Lost(submitOutcomeUnknown)) or the
        answer is not a result class the adapter knows: fail closed. The record
        becomes outcomeUnknown with the guid latch_status() names right now
        (None when the core did not latch), and is never deleted. A failed
        ledger write leaves the record submitting, which also refuses a re-run."""
        latch_guid: Optional[str] = None
        if isinstance(outcome, Lost) and outcome.reason == "submitOutcomeUnknown":
            latch_guid = _latched_guid(service)
        try:
            ledger.mark_outcome_unknown(key, latch_guid=latch_guid, now=_utcnow())
        except LedgerError:
            pass
        return _with_suffix(_transfer_error_reply(service, outcome), f"; {_NOT_RE_SENT}")

    def _finish(self, service: StackService, ledger: Ledger, key: str, result: Any,
                write_failed: bool, restarted: bool = False) -> ExecuteCommandReply:
        """Record a terminal wait result and map it to the reply. A ledger write
        failure never stops the wait (the transfer already ran), but it turns
        the reply into an error (D-04). ``restarted`` is set only on a re-attach
        of a record written by another tool-server instance (D-09): a live ran
        is then SUCCESS flagged reattachedAfterRestart, and every other outcome
        gets the arm-inspection clause."""
        to_dict = getattr(result, "to_dict", None)
        d = to_dict() if callable(to_dict) else None
        ran = isinstance(d, dict) and d.get("kind") == "ran"
        # No terminal write after a failed started write: the ledger is not
        # trusted, and the record stays submitting so a re-run never re-sends.
        if isinstance(d, dict) and is_terminal(d) and not write_failed:
            try:
                ledger.mark_done(key, result=d, now=_utcnow())
            except LedgerError:
                write_failed = True
        if write_failed:
            kind = d.get("kind") if isinstance(d, dict) else None
            # The latch clause comes first: it is the guid the operator needs.
            # A ran result has no latch to name, so it makes no latch_status call.
            latch = f"{_latch_clause(service)}; " if d is None or _can_latch(d) else ""
            reply = _reply(
                ERROR_FROM_TOOL,
                message=_one_line(_LATER_WRITE_FAILED.format(
                    kind=kind if isinstance(kind, str) and kind else "outcome unknown",
                    latch=latch), 300),
                meta=d if isinstance(d, dict) else None)
        elif isinstance(d, dict) and is_terminal(d):
            if ran and restarted:
                return _reply(SUCCESS, meta={**d, "reattachedAfterRestart": True})
            reply = _transfer_error_reply(service, result)
        else:
            reply = _non_terminal_reply(service, result, d)
        if restarted and not ran:
            reply = _with_restart_clause(service, reply, d)
        return reply

    def _reattach(self, service: StackService, ledger: Ledger, key: str,
                  record: dict[str, Any], budget: float, restarted: bool) -> ExecuteCommandReply:
        """D-07 row 5 / XFR-06: a started record is finished by waiting on its
        recorded guid, read-only. The record becomes done only for a result
        that ends the task (A-1), exactly as on the fresh path."""
        handle = record.get("handle")
        guid = handle.get("guid") if isinstance(handle, dict) else None
        result = self._reattach_loop(service, guid if isinstance(guid, str) else "", budget)
        return self._finish(service, ledger, key, result, False, restarted)

    def _reattach_loop(self, service: Any, guid: str, budget: float) -> Any:
        """Wait on ``guid`` in slices of min(remaining, WAIT_SLICE_S) until a
        result that is not timedOut arrives or ``budget`` seconds are spent.
        Read-only (D-11): only wait_transfer is called, never plan, execute or
        cancel, and never with a non-positive timeout. When the budget runs out
        the last timedOut is returned, or a synthesised one when no call fit."""
        started = _monotonic()
        remaining = budget
        last: Any = None
        while remaining > 0:
            result = service.wait_transfer(guid, timeout_s=min(remaining, WAIT_SLICE_S))
            if not isinstance(result, TimedOut):
                return result
            last = result
            remaining = budget - (_monotonic() - started)
        return last if last is not None else TimedOut(handle=TaskHandle(guid=guid))

    def AcknowledgeFailure(self, params: "Command.AcknowledgeFailure") -> ExecuteCommandReply:
        # ACK-01: the one place the core's latch is cleared, and only for the
        # operator's exact "yes". Never reads or writes the step ledger (D-15).
        if params.arm_inspected != "yes":
            return _reply(INVALID_ARGUMENTS, message=_ACK_NOT_YES_MESSAGE)
        service = self._require_service()
        return _result_reply(service.acknowledge_failure(params.guid.strip(), confirm=True))

    def GetFailureLatch(self, params: "Command.GetFailureLatch") -> ExecuteCommandReply:
        # D-13: latch_status() 1:1, zero I/O; the guid AcknowledgeFailure must name.
        return _result_reply(self._require_service().latch_status())

    def EstimateTransfer(self, params: "Command.Transfer") -> int:
        return EST_TRANSFER_S

    # D-19: constant estimates. No attribute access on params or self.service
    # and no I/O, so EstimateDuration (which bypasses _check_args) cannot raise.
    def EstimateGetManagerState(self, params: "Command.GetManagerState") -> int:
        return EST_READ_S

    def EstimateGetRobotStates(self, params: "Command.GetRobotStates") -> int:
        return EST_READ_S

    def EstimateListDevices(self, params: "Command.ListDevices") -> int:
        return EST_READ_S

    def EstimateListLabwareProfiles(self, params: "Command.ListLabwareProfiles") -> int:
        return EST_READ_S

    def EstimateListTransferProfiles(self, params: "Command.ListTransferProfiles") -> int:
        return EST_READ_S

    def EstimateGetLabwarePresence(self, params: "Command.GetLabwarePresence") -> int:
        return EST_READ_S

    def EstimateGetTransferEstimate(self, params: "Command.GetTransferEstimate") -> int:
        return EST_TRANSFER_ESTIMATE_S

    def EstimateAcknowledgeFailure(self, params: "Command.AcknowledgeFailure") -> int:
        return EST_ACK_S

    def EstimateGetFailureLatch(self, params: "Command.GetFailureLatch") -> int:
        return EST_READ_S


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
    args = parser.parse_args()
    if not args.port:
        raise RuntimeWarning("Port must be provided...")
    serve(StackServer(), str(args.port))
