"""The Galago adapter for the Formulatrix F.A.S.T. liquid handler.

It maps the ten intent-level commands 1:1 onto FastService methods and
holds no instrument policy of its own -- every decision (idle gate,
validate -> run sequencing (the instrument detects plates and the tip
caddy in-run, Phase 5 D-29), tray confirmation, timeouts, and which
instrument states allow Abort and Resume) lives in
fast_mcp.service.FastService.

Pause, Resume and Abort are the operator's control commands (dual-frontend
section 11 #1, amended). They reach a run in flight through the
ExecuteCommand override: a paused, timed-out or cancelled run is reported,
never paused, resumed or aborted on the adapter's own initiative -- the
adapter only ever calls pause/resume/abort from those three methods. This
module never imports the MCP adapter subpackage (fast_mcp.mcp) -- it
obtains its FastService only through fast_mcp.composition.open_service
(D-04).
"""
import argparse
import logging
import math
import re
import threading
import typing as t
from contextlib import contextmanager
from dataclasses import fields
from datetime import datetime, timezone
from typing import Any, Iterator, Optional, cast

import grpc
import httpx
from google.protobuf import message
from google.protobuf.struct_pb2 import Struct

from fast_mcp.authoring import _TIP_REUSE_MODES
from fast_mcp.composition import OwnedService, endpoint_key, open_service
from fast_mcp.model import Protocol
from fast_mcp.results import (
    Aborted,
    Cancelled,
    DeckSuggestion,
    NeedsConfirmation,
    NeedsInput,
    Paused,
    Refused,
    Rejected,
    RunResult,
    TimedOut,
)
from fast_mcp.run_control import RunHandle, RunOptions
from fast_mcp.service import FastService, TransferRequest
from fast_mcp.transport import InstrumentHTTPError

from tools.base_server import ToolServer, serve
from tools.grpc_interfaces.fast_pb2 import Command, Config
from tools.grpc_interfaces.tool_base_pb2 import (
    DRIVER_ERROR,
    ERROR_FROM_TOOL,
    INVALID_ARGUMENTS,
    NOT_READY,
    SUCCESS,
    Command as ToolCommand,
    ExecuteCommandReply,
    ResponseCode,
)

DEFAULT_PORT = 5003

_NOT_CONNECTED_MESSAGE = (
    "fast tool is not connected to an instrument: restart the tool server and "
    "Configure it with simulated off")
_BUSY_MESSAGE = "another motion command is in progress on this tool"

# The commands that take _motion_lock and are serialised against each
# other; the control commands (pause/resume/abort) are deliberately absent
# -- they must reach a run that one of these commands holds in flight (D-06).
MOTION_LOCK_COMMANDS = frozenset({"Transfer", "RunProtocol", "ScanTips", "EjectTray"})

# The fast.Command oneof field names (lowercase, as WhichOneof returns them)
# that FastServer.ExecuteCommand routes past base_server's readiness gate and
# status bracket (D-01, D-02).
CONTROL_COMMANDS = frozenset({"pause", "resume", "abort"})

# The commands that own an instrument run, so their run is "in flight" for
# run_state (D-12, D-19; design section 5.2 names exactly these two). Named
# separately from CONTROL_COMMANDS (D-06): ScanTips and EjectTray also take
# MOTION_LOCK_COMMANDS but read as idle (a fresh status()) while they run.
LONG_RUNNING_COMMANDS = frozenset({"Transfer", "RunProtocol"})

COMMAND_TO_SERVICE_METHOD = {
    "Transfer": "run_transfer",
    "RunProtocol": "run_protocol",
    "ValidateProtocol": "validate",
    "GetStatus": "status",
    "GetTipStatus": "tip_status",
    "ScanTips": "scan_tips",
    "EjectTray": "eject_tray",
    "Abort": "abort",
    "Resume": "resume",
    "Pause": "pause",
}

# The physical decision each recovery command must carry explicitly. A
# "yes"/"no" string, never a bool: galago-core fills an untouched boolean
# form field with false, so only a string can fail closed when blank.
_RECOVERY_DECISION_FIELD = {"Abort": "return_liquid", "Resume": "is_tip_broken"}
_YES_NO = {"yes": True, "no": False}

_RESPONSE_FOR_KIND = {
    "ran": SUCCESS,
    "rejected": INVALID_ARGUMENTS,
    "needsInput": INVALID_ARGUMENTS,
    "needsConfirmation": ERROR_FROM_TOOL,
    "deckSuggestion": ERROR_FROM_TOOL,
    "paused": ERROR_FROM_TOOL,
    "aborted": ERROR_FROM_TOOL,
    "timedOut": ERROR_FROM_TOOL,
    "cancelled": ERROR_FROM_TOOL,
    "refused": NOT_READY,
    "trayEjected": SUCCESS,
    "tipScan": SUCCESS,
    "tipRescan": SUCCESS,
}

# D-16 ASSUMED PLACEHOLDERS: no live timing evidence exists yet (RESEARCH.md
# Pitfall 7). The GAL-05 live run records the observed duration against
# EstimateTransfer and compares it with this formula; per-plate-format
# calibration is deferred unless that comparison is off by more than x2.
_DECK_SLOTS = 6  # fast_mcp.authoring._plate_list_for builds a 6-slot PlateList
_ROW_RE = re.compile(r"[A-Za-z]{1,2}")

EST_READ_S = 1
EST_SCAN_TIPS_S = 30
EST_EJECT_TRAY_S = 15
EST_ABORT_S = 15
# Pause returns once the instrument accepts the soft pause and never waits
# for the head, so it takes the read-sized flat value, not EST_ABORT_S's --
# this also keeps a simulated Pause quick for galago-core's UI tests.
EST_PAUSE_S = 1
# D-16 ASSUMED PLACEHOLDER, now stale for the common case (RESEARCH.md
# Pitfall 8): Resume only waits on the crash-recovery path (no run in
# flight) -- mid-run it returns as soon as the instrument accepts. A single
# flat value therefore over-states the common in-flight case and
# under-states the rarer crash-recovery wait, which can run as long as the
# remainder of the run. Kept flat anyway, like the other D-16 placeholders
# (CONTEXT.md "Claude's Discretion"); splitting it into an in-flight vs.
# crash-recovery pair is a deferred idea, not built here.
EST_RESUME_S = 15
EST_TRANSFER_OVERHEAD_S = 60
EST_TRANSFER_PER_CYCLE_S = 20
EST_TIP_MAX_VOLUME_UL = 13.0
EST_RUN_PROTOCOL_OVERHEAD_S = 60
EST_RUN_PROTOCOL_PER_TASK_S = 15


def _run_percent(value: object) -> Optional[float]:
    """run_state's percent (D-11, ADP-05 precision): the adapter never
    rounds, clamps or converts. An int that is not a bool, or a finite
    float, passes through unchanged; a bool, a string, NaN/infinity, or a
    missing value becomes None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    return None


def _one_line(text: str, limit: int) -> str:
    """Collapse all whitespace runs to single spaces, then truncate to
    `limit` characters, adding "..." when cut."""
    collapsed = " ".join(text.split())
    if len(collapsed) > limit:
        return collapsed[: max(limit - 3, 0)] + "..."
    return collapsed


def _check_args(command: "message.Message") -> list[str]:
    """Pure, instrument-free structural argument checks (D-15, RESEARCH
    Pattern 1). Returns a list of problem strings; an empty list means the
    command is well-formed. Called from FastServer._dispatchCommand before
    delegating to super(), so it runs identically in simulated and real mode
    -- bad arguments never reach the instrument and never come back as
    DRIVER_ERROR in simulated mode (base_server._estimateDuration's error
    slot is structurally always None, see RESEARCH.md).

    `command` is one of the ten generated oneof message types, which have
    no shared base beyond google.protobuf.message.Message -- cast to Any
    once here (not Message itself) so the per-field checks below can access
    each concrete message's own fields."""
    cmd = cast(Any, command)
    name = type(command).__name__
    if name == "Transfer":
        missing = [f.name for f in fields(TransferRequest) if not cmd.HasField(f.name)]
        if missing:
            return missing
        problems: list[str] = []
        if not (1 <= cmd.source_deck <= _DECK_SLOTS):
            problems.append(f"source_deck must be 1-{_DECK_SLOTS} (got {cmd.source_deck})")
        if not (1 <= cmd.dest_deck <= _DECK_SLOTS):
            problems.append(f"dest_deck must be 1-{_DECK_SLOTS} (got {cmd.dest_deck})")
        if cmd.source_plate_id < 1:
            problems.append(f"source_plate_id must be >= 1 (got {cmd.source_plate_id})")
        if cmd.dest_plate_id < 1:
            problems.append(f"dest_plate_id must be >= 1 (got {cmd.dest_plate_id})")
        if cmd.source_start_col < 1:
            problems.append(f"source_start_col must be >= 1 (got {cmd.source_start_col})")
        if cmd.dest_start_col < 1:
            problems.append(f"dest_start_col must be >= 1 (got {cmd.dest_start_col})")
        if cmd.num_rows < 1:
            problems.append(f"num_rows must be >= 1 (got {cmd.num_rows})")
        if cmd.num_cols < 1:
            problems.append(f"num_cols must be >= 1 (got {cmd.num_cols})")
        if not _ROW_RE.fullmatch(cmd.source_start_row):
            problems.append(
                f"source_start_row must be 1-2 letters (got {cmd.source_start_row!r})")
        if not _ROW_RE.fullmatch(cmd.dest_start_row):
            problems.append(
                f"dest_start_row must be 1-2 letters (got {cmd.dest_start_row!r})")
        if not (math.isfinite(cmd.volume) and cmd.volume > 0):
            problems.append(f"volume must be a positive number of uL (got {cmd.volume})")
        if cmd.tip_reuse not in _TIP_REUSE_MODES:
            problems.append(
                f"tip_reuse must be one of {', '.join(_TIP_REUSE_MODES)} "
                f"(got {cmd.tip_reuse!r})")
        return problems
    if name in ("RunProtocol", "ValidateProtocol"):
        problems = []
        csv = cmd.csv
        if not csv.strip():
            problems.append("csv is required")
        else:
            try:
                Protocol.from_csv(csv)
            except Exception as exc:
                # Structural parse only -- plate knowledge needs the live instrument.
                problems.append(
                    f"csv does not parse: {type(exc).__name__}: {_one_line(str(exc), 200)}")
        if name == "RunProtocol" and cmd.HasField("timeout_s"):
            if not (math.isfinite(cmd.timeout_s) and cmd.timeout_s > 0):
                problems.append("timeout_s must be a positive number of seconds")
        return problems
    if name in _RECOVERY_DECISION_FIELD:
        field_name = _RECOVERY_DECISION_FIELD[name]
        if _decision(cmd, field_name) is None:
            got = getattr(cmd, field_name) if cmd.HasField(field_name) else "unset"
            return [f"{field_name} must be 'yes' or 'no' (got {got!r})"]
        return []
    return []


def _decision(cmd: Any, field_name: str) -> Optional[bool]:
    """The operator's explicit yes/no for a recovery command, or None when
    the field is unset, blank or anything other than yes/no. None is never
    turned into a default."""
    if not cmd.HasField(field_name):
        return None
    return _YES_NO.get(getattr(cmd, field_name).strip().lower())


def _transfer_cycles(params: "Command.Transfer") -> int:
    """A 96/384 head moves the whole block in one pass, so the block size
    does not multiply the cycles -- only the per-tip volume does."""
    if not params.HasField("volume"):
        return 1
    volume = params.volume
    if not (math.isfinite(volume) and volume > 0):
        return 1
    return max(1, math.ceil(volume / EST_TIP_MAX_VOLUME_UL))


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


_NO_ERROR_TEXT = "no error reported"


def _outcome_text(outcome: object) -> str:
    """"<error_name> (<error_code>): <message>" with None parts dropped, or
    _NO_ERROR_TEXT when all are None."""
    name_code: Optional[str] = None
    error_name = getattr(outcome, "error_name", None)
    error_code = getattr(outcome, "error_code", None)
    message = getattr(outcome, "message", None)
    if error_name is not None and error_code is not None:
        name_code = f"{error_name} ({error_code})"
    elif error_name is not None:
        name_code = error_name
    elif error_code is not None:
        name_code = f"({error_code})"
    if name_code and message:
        return f"{name_code}: {message}"
    if name_code:
        return name_code
    if message:
        return str(message)
    return _NO_ERROR_TEXT


def _message_for(
        result: RunResult, expected_tray_id: Optional[int],
        operator_abort: bool = False) -> str:
    """D-12: every message passes through _one_line with limit 500.

    `operator_abort` (D-10) is the caller's record of whether THIS adapter's
    own Abort was accepted for the run that produced `result` -- it is
    always a parameter, never a read of adapter state, so this function
    stays pure. It only changes the Aborted branch's wording (D-09): True
    names the operator ("run aborted by operator at <p>%"), appending the
    instrument's own outcome text only when there is a real error; False (or
    omitted) keeps the plain instrument wording, exactly as before."""
    text = ""
    if isinstance(result, Rejected):
        parts = "; ".join(f"{f.code} {f.name}: {f.message}" for f in result.findings)
        text = f"rejected at {result.stage}: {parts}"
        if result.tray_ejected:
            text += "; tray ejected for the operator"
    elif isinstance(result, NeedsInput):
        text = "missing or invalid: " + ", ".join(result.missing)
    elif isinstance(result, NeedsConfirmation):
        if expected_tray_id is None:
            text = f"tray {result.tray_id} installed, no expected tray configured"
        else:
            text = f"tray {result.tray_id} installed, expected {expected_tray_id}"
    elif isinstance(result, DeckSuggestion):
        parts = "; ".join(
            f"plate {m.plate_id} ({m.description}) deck {m.from_deck} -> {m.to_deck}"
            for m in result.moves)
        text = f"deck layout differs from the instrument's suggestion; move {parts}"
        if result.tray_ejected:
            text += "; tray ejected for the operator"
    elif isinstance(result, Refused):
        text = f"instrument not ready: {result.reason} (state {result.state})"
    elif isinstance(result, Paused):
        text = (f"run paused at {result.percent}%: {_outcome_text(result.outcome)}; "
                "fix the deck, then send Resume (is_tip_broken) or Abort (return_liquid)")
    elif isinstance(result, Aborted):
        outcome_text = _outcome_text(result.outcome)
        if operator_abort:
            text = f"run aborted by operator at {result.percent}%"
            if outcome_text != _NO_ERROR_TEXT:
                text += f": {outcome_text}"
        else:
            text = f"run aborted at {result.percent}%: {outcome_text}"
    elif isinstance(result, TimedOut):
        text = (f"run timed out at {result.percent}%; the instrument run was NOT aborted, "
                "check the instrument and stop it physically if needed")
    elif isinstance(result, Cancelled):
        text = "cancelled by operator"
    return _one_line(text, 500)


def _result_reply(
        result: RunResult, expected_tray_id: Optional[int] = None,
        operator_abort: bool = False) -> ExecuteCommandReply:
    code = _RESPONSE_FOR_KIND[result.kind]
    message = _message_for(result, expected_tray_id, operator_abort=operator_abort)
    return _reply(code, message=message, meta=result.to_dict())


def _transport_error_reply(exc: Exception) -> ExecuteCommandReply:
    """ERROR_FROM_TOOL, no meta."""
    if isinstance(exc, InstrumentHTTPError):
        message = f"instrument HTTP {exc.status_code}: " + _one_line(str(exc.body), 200)
    else:
        message = f"instrument unreachable: {type(exc).__name__}: " + _one_line(str(exc), 200)
    return _reply(ERROR_FROM_TOOL, message=message)


def _accepted(result: "dict | Refused") -> bool:
    """WR-01: the single definition of "the instrument accepted the
    command" -- True only when `result` is a dict whose `errorCode` is the
    literal int 0. Mirrors fast_mcp.orchestration._pause_info's own rule
    (`type(code) is int`): a bool, str or other non-int errorCode never
    counts as accepted, even though e.g. `False == 0` in Python. Used by
    both _recovery_reply's SUCCESS mapping and Abort()'s operator-abort
    bookkeeping so the stricter definition can never diverge between the
    two safety-sensitive call sites."""
    if not isinstance(result, dict):
        return False
    code = result.get("errorCode")
    return type(code) is int and code == 0


def _recovery_reply(action: str, result: "dict | Refused") -> ExecuteCommandReply:
    """Map FastService.pause/abort/resume's `dict | Refused`. Refused means the
    core sent nothing to the instrument (wrong state); the dict is the
    instrument's reply, which only counts as success with errorCode 0. A
    missing errorCode is treated as a failure."""
    if isinstance(result, Refused):
        return _reply(ERROR_FROM_TOOL, message=_message_for(result, None),
                      meta=result.to_dict())
    if _accepted(result):
        return _reply(SUCCESS, meta=result)
    code = result.get("errorCode")
    return _reply(ERROR_FROM_TOOL,
                  message=_one_line(f"instrument rejected {action}: errorCode {code}", 500),
                  meta=result)


class _PauseInfoLike(t.Protocol):
    """A duck-typed stand-in for fast-mcp's PauseInfo (D-13): the re-pinned
    core exports PauseInfo from fast_mcp.orchestration, but the adapter
    invariant's allowed fast_mcp modules do not include that module, so
    this file still never imports it (nor ResumeMarker). The real PauseInfo
    satisfies this Protocol, and Transfer/RunProtocol pass
    RunOptions(on_pause=self._record_pause) (D-04, D-05).
    `typing.Protocol` is used as `t.Protocol` because `fast_mcp.model.Protocol`
    is already imported under the bare name `Protocol`."""

    def to_dict(self) -> dict[str, Any]: ...


class _DictPauseInfo:
    """Wraps a plain dict so FastServer.simulate_pause (D-20) can feed the
    same _record_pause that Transfer and RunProtocol wire as
    RunOptions(on_pause=self._record_pause): _PauseInfoLike only requires
    to_dict(). Stores and returns a copy, so the caller's dict and the
    recorded one never alias."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = dict(data)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


# Simulated-only (D-20): a SUCCESS reply from one of these clears a pause
# recorded by the simulate_pause test hook, mirroring a real Resume/Abort
# accepting the recovery. A simulated Pause is deliberately absent.
_PAUSE_CLEARING_COMMANDS = frozenset({"Resume", "Abort"})


class FastServer(ToolServer):
    toolType = "fast"
    config: Config

    def __init__(self) -> None:
        super().__init__()
        self._owned: Optional[OwnedService] = None
        self.service: Optional[FastService] = None
        self._motion_lock = threading.Lock()
        # Dedicated to run_state (D-12): never the same lock as _motion_lock,
        # so reading run_state never contends with a motion command.
        self._run_state_lock = threading.Lock()
        self._active_runs = 0
        self._run_record: dict[str, Any] = {
            "state": "running", "percent": None, "pause": None, "operator_abort": False}

    def _dispatchCommand(self, command: "message.Message") -> ExecuteCommandReply:
        """Override of ToolServer._dispatchCommand (RESEARCH Pattern 1, D-15).

        Runs in both simulated and real mode, before any instrument contact.
        base_server's simulated-mode dispatch never validates arguments and
        its _estimateDuration error slot is structurally always None, so bad
        arguments must be rejected here or they either sleep through
        unchecked (simulated) or surface as the wrong error code entirely.

        Two simulated-only behaviors layer on top of the plain dispatch
        (D-18, D-19, D-20), both only once _check_args has already passed:
        - A LONG_RUNNING_COMMANDS run is marked in flight for the whole of
          base_server's simulated sleep -- base_server does the sleeping,
          this override only brackets it with _run_in_flight() so run_state
          reads running for its duration and idle once it returns.
          _run_in_flight is a counter, so two overlapping simulated runs
          stay running until the last one ends.
        - A successful simulated Resume or Abort clears a pause recorded by
          the simulate_pause test hook (D-20); an INVALID_ARGUMENTS reply
          never reaches this because _check_args already returned above, and
          a simulated Pause is never in _PAUSE_CLEARING_COMMANDS so it never
          clears.

        Real mode is unchanged: Transfer and RunProtocol enter
        _run_in_flight themselves, and a real pause is never cleared from
        here. Never edits tools/base_server.py."""
        problems = _check_args(command)
        if problems:
            return _reply(
                INVALID_ARGUMENTS,
                message=_one_line("invalid arguments: " + "; ".join(problems), 500),
                meta=NeedsInput(missing=problems).to_dict(),
            )
        name = type(command).__name__
        if self.simulated and name in LONG_RUNNING_COMMANDS:
            with self._run_in_flight():
                return super()._dispatchCommand(command)
        reply = super()._dispatchCommand(command)
        if (self.simulated and name in _PAUSE_CLEARING_COMMANDS
                and reply.response == SUCCESS):
            self._clear_pause()
        return reply

    def ExecuteCommand(
        self, request: ToolCommand, context: grpc.ServicerContext
    ) -> ExecuteCommandReply:
        """Override of ToolServer.ExecuteCommand (D-01, D-02, D-03).

        base_server refuses every command unless READY (base_server.py:203),
        sets BUSY for the whole command (:240) and resets READY in its
        finally (:254). A control command (pause/resume/abort) must reach
        the run that an in-flight Transfer/RunProtocol owns and must not
        flip its status, so this override bypasses those three for
        CONTROL_COMMANDS only -- it still checks the tool type and still
        runs _check_args through _dispatchCommand. Never calls isReady,
        parseCommand or setStatus on this path: a BUSY tool stays BUSY and a
        READY tool stays READY. Every other request (a non-fast
        tool_command, a fast request with no command set, any non-control
        fast command) returns super().ExecuteCommand(request, context)
        unchanged. tools/base_server.py is never edited."""
        if request.WhichOneof("tool_command") == self.toolType:
            fast_command = request.fast
            field_name = fast_command.WhichOneof("command")
            if field_name in CONTROL_COMMANDS:
                command = getattr(fast_command, field_name)
                try:
                    logging.info(f"Running command {command.__class__.__name__}")
                    return self._dispatchCommand(command)
                except Exception as e:
                    logging.error(f"Error on Tool ={self.toolId}")
                    self.last_error = str(e)
                    return ExecuteCommandReply(response=DRIVER_ERROR, error_message=str(e))
        return super().ExecuteCommand(request, context)

    def _configure(self, config: Config) -> None:
        host = config.host.strip()
        if not host:
            raise ValueError("fast: Config.host is required")
        port = config.port or DEFAULT_PORT
        run_timeout_s = config.run_timeout_s
        if not math.isfinite(run_timeout_s) or run_timeout_s < 0:
            raise ValueError(
                f"fast: Config.run_timeout_s must be finite and >= 0, got {run_timeout_s!r}")
        key = endpoint_key(host, port)
        if self._owned is not None and self._owned.endpoint == key:
            return
        if self._owned is not None:
            self._owned.close()
            self._owned = None
            self.service = None
        self._owned = open_service(host, port, owner="galago")
        self.service = self._owned.service

    @contextmanager
    def _run_in_flight(self) -> Iterator[None]:
        """Marks a LONG_RUNNING_COMMANDS run as in flight for run_state
        (D-12). Entry increments the nesting counter under _run_state_lock
        (never _motion_lock) and, only on the 0->1 transition, resets the
        record to running/no-percent/no-pause/no-operator-abort -- mirroring
        the exit guard below so an overlapping second run never clobbers a
        pause recorded for a run that is still in flight. The reset also
        clears the operator-abort flag (D-09): a new run never inherits an
        abort recorded for a previous one. Exit decrements the counter and,
        only once no run remains in flight, clears any recorded pause.
        Records only -- calls nothing on the service (D-16)."""
        with self._run_state_lock:
            if self._active_runs == 0:
                self._run_record = {
                    "state": "running", "percent": None, "pause": None,
                    "operator_abort": False}
            self._active_runs += 1
        try:
            yield
        finally:
            with self._run_state_lock:
                self._active_runs -= 1
                if self._active_runs == 0:
                    self._run_record["pause"] = None

    def _log_progress(self, percent: int, state: str) -> None:
        logging.info("fast run progress %s%% (%s)", percent, state)
        with self._run_state_lock:
            sanitized = _run_percent(percent)
            if sanitized is not None:
                self._run_record["percent"] = sanitized
            self._run_record["state"] = state
            if state == "running":
                self._run_record["pause"] = None

    def _record_pause(self, info: "_PauseInfoLike") -> None:
        """Records the current pause for run_state (D-11, D-12). Transfer and
        RunProtocol wire it as RunOptions(on_pause=self._record_pause); the
        simulated hook (Plan 01-05) and the tests are its other callers.
        Records only: no service call, no control method (D-16)."""
        pause = dict(info.to_dict())
        pause["since"] = datetime.now(timezone.utc).isoformat()
        with self._run_state_lock:
            self._run_record["pause"] = pause
            self._run_record["state"] = "paused"
            percent = _run_percent(pause.get("percent"))
            if percent is not None:
                self._run_record["percent"] = percent

    def _clear_pause(self) -> None:
        """Clears any recorded pause (D-20): used by _dispatchCommand when a
        simulated Resume/Abort succeeds, and by simulate_pause(None).
        Records only -- no service call, no control method (D-16)."""
        with self._run_state_lock:
            self._run_record["pause"] = None

    def simulate_pause(self, pause: Optional[dict[str, Any]]) -> None:
        """In-process test hook (D-20, ADP-10), simulated mode only. Lets
        galago-core exercise its pause prompt and controls against this tool
        server running under a dev script or test, with no instrument
        contact and no new gRPC command -- fast.proto's 1:1 command surface
        is unchanged. `pause=None` clears a hooked pause, as a successful
        Resume/Abort would; a dict is wrapped as _DictPauseInfo and fed to
        the same _record_pause that Transfer and RunProtocol wire as
        RunOptions(on_pause=self._record_pause). An out-of-process trigger
        (a gRPC command or an env var) is a deferred idea, not built here."""
        if not self.simulated:
            raise RuntimeError("simulate_pause is only available in simulated mode")
        if pause is None:
            self._clear_pause()
        else:
            self._record_pause(_DictPauseInfo(pause))

    def _build_run_state(self) -> Optional[dict[str, Any]]:
        """The health GetStatus's run_state source (D-12, D-14, D-19, D-20).

        While simulated, reads only the adapter's own record under
        _run_state_lock and never touches the service (service stays None
        throughout simulated mode, D-18): a recorded pause always reads
        paused with its detail regardless of whether a run is in flight
        (D-20, the simulate_pause hook); otherwise running while a
        LONG_RUNNING_COMMANDS run is in flight (a counted run, not a
        boolean, D-19) and idle otherwise. State is derived here from
        pause/_active_runs directly, not from _run_record["state"], so a
        cleared pause can never leave a stale "paused" behind.

        In real mode, while a LONG_RUNNING_COMMANDS run is in flight,
        returns a copy of the adapter's own record taken under
        _run_state_lock -- never _motion_lock -- and calls nothing on the
        service. Otherwise maps a fresh service.status() to state/percent/
        pause (percentProgress -> percent, RESEARCH Pitfall 2); unset (None)
        when no service is configured; any failure on this path -- a
        service.status() exception, a non-dict status, or a non-string
        state -- yields {"state": "unknown"} so a heartbeat never fails
        because of run state (T-01-13). The only service call on this path
        is status()."""
        if self.simulated:
            with self._run_state_lock:
                pause = self._run_record["pause"]
                if pause is not None:
                    return {
                        "state": "paused",
                        "percent": _run_percent(pause.get("percent")),
                        "pause": dict(pause),
                    }
                if self._active_runs > 0:
                    return {"state": "running", "percent": None, "pause": None}
                return {"state": "idle", "percent": None, "pause": None}
        with self._run_state_lock:
            if self._active_runs > 0:
                pause = self._run_record["pause"]
                return {
                    "state": self._run_record["state"],
                    "percent": self._run_record["percent"],
                    "pause": dict(pause) if pause is not None else None,
                }
        service = self.service
        if service is None:
            return None
        try:
            status = service.status()
        except Exception:
            logging.warning("fast run_state: service.status() failed", exc_info=True)
            return {"state": "unknown"}
        if not isinstance(status, dict) or not isinstance(status.get("state"), str):
            return {"state": "unknown"}
        return {
            "state": status["state"],
            "percent": _run_percent(status.get("percentProgress")),
            "pause": None,
        }

    def _timeout(self, per_command: Optional[float]) -> Optional[float]:
        if per_command is not None:
            return per_command
        if self.config.run_timeout_s > 0:
            return self.config.run_timeout_s
        return None

    def _expected_tray_id(self, params: "Command.Transfer") -> Optional[int]:
        """D-26, GAL-05 F2: 0 means unset for both the per-command field and
        Config, because galago-core's command form sends 0 for a blank field
        (runbook B5 -- the live attempts 1-2 failure). A non-zero
        per-command value overrides Config (D-14). Negative values pass
        through unchanged and fail the tray-id gate closed."""
        if params.HasField("expected_tray_id") and params.expected_tray_id != 0:
            return params.expected_tray_id
        return self.config.expected_tray_id or None

    def Transfer(self, params: "Command.Transfer") -> ExecuteCommandReply:
        service = self.service
        if service is None:
            return _reply(NOT_READY, message=_NOT_CONNECTED_MESSAGE)
        if not self._motion_lock.acquire(blocking=False):
            return _reply(NOT_READY, message=_BUSY_MESSAGE)
        try:
            request = TransferRequest(**{
                f.name: getattr(params, f.name) if params.HasField(f.name) else None
                for f in fields(TransferRequest)
            })
            expected = self._expected_tray_id(params)
            with self._run_in_flight():
                try:
                    result = service.run_transfer(
                        request, expected_tray_id=expected,
                        options=RunOptions(
                            timeout_s=self._timeout(None), on_progress=self._log_progress,
                            on_pause=self._record_pause, through_pauses=True))
                except (InstrumentHTTPError, httpx.HTTPError) as exc:
                    return _transport_error_reply(exc)
                with self._run_state_lock:
                    operator_abort = self._run_record.get("operator_abort") is True
                return _result_reply(result, expected, operator_abort=operator_abort)
        finally:
            self._motion_lock.release()

    def RunProtocol(self, params: "Command.RunProtocol") -> ExecuteCommandReply:
        service = self.service
        if service is None:
            return _reply(NOT_READY, message=_NOT_CONNECTED_MESSAGE)
        if not self._motion_lock.acquire(blocking=False):
            return _reply(NOT_READY, message=_BUSY_MESSAGE)
        try:
            per_command = params.timeout_s if params.HasField("timeout_s") else None
            with self._run_in_flight():
                try:
                    result = service.run_protocol(
                        params.csv,
                        options=RunOptions(
                            timeout_s=self._timeout(per_command), on_progress=self._log_progress,
                            on_pause=self._record_pause, through_pauses=True))
                except (InstrumentHTTPError, httpx.HTTPError) as exc:
                    return _transport_error_reply(exc)
                with self._run_state_lock:
                    operator_abort = self._run_record.get("operator_abort") is True
                return _result_reply(result, operator_abort=operator_abort)
        finally:
            self._motion_lock.release()

    def ValidateProtocol(self, params: "Command.ValidateProtocol") -> ExecuteCommandReply:
        service = self.service
        if service is None:
            return _reply(NOT_READY, message=_NOT_CONNECTED_MESSAGE)
        report = service.validate(params.csv)
        if report.valid:
            return _reply(SUCCESS, meta=report.to_dict())
        parts = "; ".join(f"{f.code} {f.name}: {f.message}" for f in report.findings)
        return _reply(INVALID_ARGUMENTS,
                     message=_one_line(f"validation findings: {parts}", 500),
                     meta=report.to_dict())

    def GetStatus(self, *args: object) -> object:  # type: ignore[override]
        """Dual-purpose, by necessity: `ToolDriverServicer.GetStatus(request,
        context) -> StatusReply` is the generic tool-health RPC that every
        registered tool exposes (galago-core polls it on a heartbeat,
        `controller/server/tools.ts:fetchStatus`) -- it is bound by
        `add_ToolDriverServicer_to_server` directly to `self.GetStatus`, by
        attribute name, in generated code we cannot edit (base_server.py and
        tool_driver_pb2_grpc.py). `Command.GetStatus {}` is this adapter's
        own read-status intent command, dispatched by
        `ToolServer._dispatchCommand`'s `getattr(self,
        command.__class__.__name__)` -- which is ALSO literally "GetStatus".
        Both bind to the same attribute. The gRPC-generated stub always calls
        the health RPC with exactly two positional args (request, context);
        `_dispatchCommand` always calls the intent command with exactly one
        (the command). Arity is therefore a safe, stable discriminator.

        The 2-arg health-RPC branch also fills `reply.run_state` (D-10): the
        adapter's own record while a run is in flight, a mapped
        `service.status()` otherwise, unset when no service is configured.
        The 1-arg intent-command branch is unchanged."""
        if len(args) == 2:
            reply = super().GetStatus(*args)  # type: ignore[arg-type]
            run_state = self._build_run_state()
            if run_state is not None:
                try:
                    reply.run_state.update(run_state)
                except (ValueError, TypeError):
                    reply.ClearField("run_state")
                    reply.run_state.update({"state": "unknown"})
            return reply
        (params,) = args
        return self._get_status(params)  # type: ignore[arg-type]

    def _get_status(self, params: "Command.GetStatus") -> ExecuteCommandReply:
        service = self.service
        if service is None:
            return _reply(NOT_READY, message=_NOT_CONNECTED_MESSAGE)
        try:
            status = service.status()
        except (InstrumentHTTPError, httpx.HTTPError) as exc:
            return _transport_error_reply(exc)
        return _reply(SUCCESS, meta=status)

    def GetTipStatus(self, params: "Command.GetTipStatus") -> ExecuteCommandReply:
        service = self.service
        if service is None:
            return _reply(NOT_READY, message=_NOT_CONNECTED_MESSAGE)
        try:
            result = service.tip_status()
        except (InstrumentHTTPError, httpx.HTTPError) as exc:
            return _transport_error_reply(exc)
        return _result_reply(result)

    def ScanTips(self, params: "Command.ScanTips") -> ExecuteCommandReply:
        service = self.service
        if service is None:
            return _reply(NOT_READY, message=_NOT_CONNECTED_MESSAGE)
        if not self._motion_lock.acquire(blocking=False):
            return _reply(NOT_READY, message=_BUSY_MESSAGE)
        try:
            try:
                result = service.scan_tips(is_tip_broken=params.is_tip_broken)
            except (InstrumentHTTPError, httpx.HTTPError) as exc:
                return _transport_error_reply(exc)
            return _result_reply(result)
        finally:
            self._motion_lock.release()

    def EjectTray(self, params: "Command.EjectTray") -> ExecuteCommandReply:
        service = self.service
        if service is None:
            return _reply(NOT_READY, message=_NOT_CONNECTED_MESSAGE)
        if not self._motion_lock.acquire(blocking=False):
            return _reply(NOT_READY, message=_BUSY_MESSAGE)
        try:
            try:
                result = service.eject_tray()
            except (InstrumentHTTPError, httpx.HTTPError) as exc:
                return _transport_error_reply(exc)
            return _result_reply(result)
        finally:
            self._motion_lock.release()

    def Pause(self, params: "Command.Pause") -> ExecuteCommandReply:
        """Operator-issued soft pause of a running run. The core refuses
        without contacting the instrument unless the instrument is running.
        It never takes the motion lock, so it reaches a run that
        Transfer/RunProtocol own; it returns once the instrument accepts."""
        service = self.service
        if service is None:
            return _reply(NOT_READY, message=_NOT_CONNECTED_MESSAGE)
        try:
            result = service.pause(hard=False)
        except (InstrumentHTTPError, httpx.HTTPError) as exc:
            return _transport_error_reply(exc)
        return _recovery_reply("pause", result)

    def Abort(self, params: "Command.Abort") -> ExecuteCommandReply:
        """Operator-issued abort of a running or paused run. The core
        refuses in any other state without contacting the instrument. Never
        takes the motion lock (D-06), so it reaches a run in flight. Returns
        once the instrument has accepted the abort; it does not wait for the
        head to park.

        D-09: when the instrument accepts (errorCode 0), records
        operator_abort=True under _run_state_lock -- bookkeeping about this
        adapter's own accepted command, never an instrument-state check
        (ADP-09). Transfer/RunProtocol read it afterwards to word an Aborted
        result as the operator's doing ("run aborted by operator at <p>%")
        rather than the instrument's. Set inline, never in a new helper
        method (D-17)."""
        return_liquid = _decision(params, "return_liquid")
        if return_liquid is None:
            return _reply(INVALID_ARGUMENTS,
                          message="return_liquid must be 'yes' or 'no'")
        service = self.service
        if service is None:
            return _reply(NOT_READY, message=_NOT_CONNECTED_MESSAGE)
        try:
            result = service.abort(return_liquid=return_liquid)
        except (InstrumentHTTPError, httpx.HTTPError) as exc:
            return _transport_error_reply(exc)
        if _accepted(result):
            with self._run_state_lock:
                self._run_record["operator_abort"] = True
        return _recovery_reply("abort", result)

    def Resume(self, params: "Command.Resume") -> ExecuteCommandReply:
        """Operator-issued resume of a paused run. The core refuses unless
        the instrument is paused, without contacting it.

        Two paths (D-07), decided by a non-blocking acquire of the motion
        lock -- adapter bookkeeping about its own threads, never an
        instrument-state check (D-08):
        - Lock acquired: no motion command is in flight (crash recovery).
          Resumes, then WAITS for the resumed run to reach a terminal state,
          with the same timeout and progress logging as Transfer, holding
          the lock for the whole wait so no new Transfer can start under it.
          The re-pinned core masks a stale leading `paused` reading after an
          accepted resume, so this wait reports the resumed run's real
          outcome; it keeps the default (non-through) wait, so a fresh pause
          still ends it as Paused with the actionable message (D-07, D-08).
        - Lock not acquired: a run is in flight. Resumes and returns as soon
          as the instrument accepts; no wait, and never releases a lock this
          call did not acquire -- the in-flight step's own wait reports the
          outcome.

        The crash-recovery wait's _result_reply call below passes no
        operator_abort flag: that wait is not bracketed by _run_in_flight,
        so a flag left by an earlier Abort could be stale, and an Aborted
        result here keeps the plain instrument wording (planner choice,
        D-09 scope)."""
        is_tip_broken = _decision(params, "is_tip_broken")
        if is_tip_broken is None:
            return _reply(INVALID_ARGUMENTS,
                          message="is_tip_broken must be 'yes' or 'no'")
        service = self.service
        if service is None:
            return _reply(NOT_READY, message=_NOT_CONNECTED_MESSAGE)
        if self._motion_lock.acquire(blocking=False):
            try:
                try:
                    accepted = service.resume(is_tip_broken=is_tip_broken)
                    if isinstance(accepted, Refused) or accepted.get("errorCode") != 0:
                        return _recovery_reply("resume", accepted)
                    result = service.wait(
                        RunHandle(plates=None, stale_done=False),
                        on_progress=self._log_progress, timeout_s=self._timeout(None))
                except (InstrumentHTTPError, httpx.HTTPError) as exc:
                    return _transport_error_reply(exc)
                return _result_reply(result)
            finally:
                self._motion_lock.release()
        try:
            accepted = service.resume(is_tip_broken=is_tip_broken)
        except (InstrumentHTTPError, httpx.HTTPError) as exc:
            return _transport_error_reply(exc)
        return _recovery_reply("resume", accepted)

    # -- D-16 estimate methods -------------------------------------------
    # Every Estimate<Cmd> method is called from two places: base_server's
    # simulated-mode _dispatchCommand (after _check_args has already
    # passed), and the EstimateDuration RPC, which bypasses _check_args
    # entirely (RESEARCH.md: "parseCommand -> _estimateDuration ... does
    # NOT go through _dispatchCommand"). Every method below must therefore
    # never raise, even given malformed input, and always return an int >= 1.

    def EstimateTransfer(self, params: "Command.Transfer") -> int:
        try:
            cycles = _transfer_cycles(params)
            return EST_TRANSFER_OVERHEAD_S + EST_TRANSFER_PER_CYCLE_S * cycles
        except Exception:
            return EST_TRANSFER_OVERHEAD_S + EST_TRANSFER_PER_CYCLE_S

    def EstimateRunProtocol(self, params: "Command.RunProtocol") -> int:
        try:
            n = len(Protocol.from_csv(params.csv).tasks)
        except Exception:
            lines = [ln for ln in params.csv.splitlines() if ln.strip()]
            n = max(0, len(lines) - 1)
        return EST_RUN_PROTOCOL_OVERHEAD_S + EST_RUN_PROTOCOL_PER_TASK_S * max(1, n)

    def EstimateValidateProtocol(self, params: "Command.ValidateProtocol") -> int:
        return EST_READ_S

    def EstimateGetStatus(self, params: "Command.GetStatus") -> int:
        return EST_READ_S

    def EstimateGetTipStatus(self, params: "Command.GetTipStatus") -> int:
        return EST_READ_S

    def EstimateScanTips(self, params: "Command.ScanTips") -> int:
        return EST_SCAN_TIPS_S

    def EstimateEjectTray(self, params: "Command.EjectTray") -> int:
        return EST_EJECT_TRAY_S

    def EstimatePause(self, params: "Command.Pause") -> int:
        return EST_PAUSE_S

    def EstimateAbort(self, params: "Command.Abort") -> int:
        return EST_ABORT_S

    def EstimateResume(self, params: "Command.Resume") -> int:
        return EST_RESUME_S


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
    args = parser.parse_args()
    if not args.port:
        raise RuntimeWarning("Port must be provided...")
    serve(FastServer(), str(args.port))
