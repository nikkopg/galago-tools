"""The Galago adapter for the Formulatrix STACK plate-transfer manager.

It maps each command 1:1 onto a StackService method and holds no instrument
policy of its own -- every decision (identity probe, session, validation,
failure latch, transfer sequencing) lives in the stack-automation-layer core.
The core is obtained only through composition.open_service with owner
"galago", so galago and the core's own MCP front end contend on the same owner
lock. This module never imports the core's MCP adapter subpackage, and it has
no real-mode motion path in this phase: only reads are wired.

A result is turned into a reply by its ``kind``: only the explicit allowlist
in _SUCCESS_KINDS yields SUCCESS; every other result (a refusal, a failed
read, an unknown shape) is an ERROR_FROM_TOOL carrying a one-line message.
"""
import argparse
import contextlib
import logging
import math
import re
import threading
from typing import Any, Iterator, Optional, cast

import grpc
from google.protobuf import message
from google.protobuf.struct_pb2 import Struct
from stack_automation_layer.composition import OwnedService, open_service
from stack_automation_layer.model import Location, TransferRequest
from stack_automation_layer.owner_lock import endpoint_key
from stack_automation_layer.service import StackService

from tools.base_server import ToolServer, serve
from tools.grpc_interfaces.stack_pb2 import Command, Config
from tools.grpc_interfaces.tool_base_pb2 import (
    DRIVER_ERROR,
    ERROR_FROM_TOOL,
    INVALID_ARGUMENTS,
    NOT_READY,
    SUCCESS,
    ExecuteCommandReply,
    ResponseCode,
)
from tools.grpc_interfaces.tool_base_pb2 import Command as ToolCommand

DEFAULT_PORT = 5005

# D-01: every handler maps 1:1 onto one StackService method. The Phase 5
# commands (Transfer, AcknowledgeFailure, GetFailureLatch) are not wired here.
COMMAND_TO_SERVICE_METHOD = {
    "GetManagerState": "manager_state",
    "GetRobotStates": "robot_states",
    "ListDevices": "devices",
    "ListLabwareProfiles": "labware_profiles",
    "ListTransferProfiles": "transfer_profiles",
    "GetLabwarePresence": "labware_presence",
    "GetTransferEstimate": "estimate_transfer",
}

# D-19: every Estimate<Cmd> hook returns one of these local constants (seconds);
# none does I/O, so neither a simulated run nor the EstimateDuration RPC can
# touch the instrument or raise.
EST_TRANSFER_S = 35
EST_TRANSFER_ESTIMATE_S = 3
EST_READ_S = 2
EST_ACK_S = 2

# D-18: commands the real-mode adapter refuses without touching the service
# (Phase 5 wires them). They win over the not-configured check (D-14).
UNAVAILABLE_COMMANDS = frozenset({"Transfer", "AcknowledgeFailure", "GetFailureLatch"})

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

# D-09: logged once per fresh open. A restart of this tool server silently
# drops the core's in-process failure latch and in-flight guard.
_RESTART_WARNING = (
    "stack: restarting this tool server clears the STACK core's failure latch "
    "and in-flight guard (core gap G1); a STACK failure must be acknowledged "
    "by the operator, not cleared by a restart"
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
    "ran",
})


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
    """Build the core's TransferRequest from a GetTransferEstimate command,
    blank or unset fields as None (the core's missing_fields, not this
    adapter, decides what is incomplete)."""
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


def _unavailable_reply(name: str) -> ExecuteCommandReply:
    """D-18: ERROR_FROM_TOOL, because galago-core hides the text of
    INVALID_ARGUMENTS / NOT_READY replies from the operator."""
    return _reply(ERROR_FROM_TOOL, message=f"stack: {name} is not available in this build")


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

    def __init__(self) -> None:
        super().__init__()
        self._owned: Optional[OwnedService] = None
        self.service: Optional[StackService] = None
        self._transfer_timeout_s: float = 0.0
        self._ledger_dir: str = ""
        # WR-03: serve() runs commands on a thread pool. _configure_lock
        # serialises Configures; _state guards _readers/_reconfiguring so a
        # Configure waits for in-flight commands to finish before it closes
        # the owner, and commands wait while it swaps the owner and service.
        self._read_bypass = threading.local()
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
        this returns or raises (WR-01). The references are cleared before the
        close: the core's OwnedService.close() marks itself closed before it
        closes the transport, so a transport close that raises would otherwise
        skip the lock release and leave a dead service looking usable. The
        owner lock is therefore released in a finally (OwnerLock.release() is
        idempotent), which is a no-op after a clean close."""
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
        GetStatus says the tool is not configured."""
        with self._configure_lock, self._exclusive():
            try:
                self._apply_config(config)
            except BaseException:
                self._teardown()
                raise

    @contextlib.contextmanager
    def _exclusive(self) -> Iterator[None]:
        """WR-03: hold off new real-mode commands, wait for the in-flight ones
        to finish, then run the body with no command touching the owner, so a
        bypassed read never talks to a transport Configure just closed and
        _owned/service change together. Waits for the in-flight commands
        indefinitely: each is bounded by the core's transport timeouts."""
        with self._state:
            self._reconfiguring = True
            try:
                self._state.wait_for(lambda: not self._readers)
                yield
            finally:
                self._reconfiguring = False
                self._state.notify_all()

    @contextlib.contextmanager
    def _in_flight(self) -> Iterator[None]:
        """WR-03: bracket one real-mode command. Waits while a Configure is
        swapping the owner; the service cannot change until the command ends."""
        with self._state:
            self._state.wait_for(lambda: not self._reconfiguring)
            self._readers += 1
        try:
            yield
        finally:
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
        self._transfer_timeout_s = timeout
        # Recorded only: nothing touches this path here (Phase 5 owns the ledger).
        self._ledger_dir = config.ledger_dir
        key = endpoint_key(host, port)
        if self._owned is not None and self._owned.endpoint == key:
            return
        # Close-first: release the old owner lock before opening the new
        # endpoint, so a failed open leaves this tool holding no lock and no
        # service.
        self._teardown()
        self._owned = open_service(host, port, owner="galago")
        self.service = self._owned.service
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
        with self._in_flight():
            # D-14: the three refusals need no service and their text is
            # operator-visible, so they win over not-configured.
            if (self.service is None
                    and type(command).__name__ not in UNAVAILABLE_COMMANDS):
                return _reply(NOT_READY, message=_NOT_CONFIGURED_MESSAGE)
            return super()._dispatchCommand(command)

    def _require_service(self) -> StackService:
        if self.service is None:
            raise RuntimeError("stack: not configured")
        return self.service

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

    def Transfer(self, params: "Command.Transfer") -> ExecuteCommandReply:
        # D-18: no real-mode motion path in this phase; never touches the service.
        return _unavailable_reply("Transfer")

    def AcknowledgeFailure(self, params: "Command.AcknowledgeFailure") -> ExecuteCommandReply:
        # D-18: refused in real mode; never touches the service.
        return _unavailable_reply("AcknowledgeFailure")

    def GetFailureLatch(self, params: "Command.GetFailureLatch") -> ExecuteCommandReply:
        # D-18: refused in real mode; never touches the service.
        return _unavailable_reply("GetFailureLatch")

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
