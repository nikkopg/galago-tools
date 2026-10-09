"""The Galago adapter for the Formulatrix F.A.S.T. liquid handler.

It maps the nine intent-level commands 1:1 onto FastService methods and
holds no instrument policy of its own -- every decision (idle gate,
validate -> run sequencing (the instrument detects plates and the tip
caddy in-run, Phase 5 D-29), tray confirmation, timeouts, and which
instrument states allow Abort and Resume) lives in
fast_mcp.service.FastService.

Abort and Resume are operator-issued recovery commands for a run the
instrument has paused (dual-frontend section 11 #1, amended). The adapter
only ever calls abort/resume from those two commands: a paused, timed-out
or cancelled run is reported, never aborted on the adapter's own initiative. This module never imports the MCP adapter
subpackage (fast_mcp.mcp) -- it obtains its FastService only through
fast_mcp.composition.open_service (D-04).
"""
import argparse
import logging
import math
import re
import threading
from dataclasses import fields
from typing import Any, Optional, cast

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
    ERROR_FROM_TOOL,
    INVALID_ARGUMENTS,
    NOT_READY,
    SUCCESS,
    ExecuteCommandReply,
    ResponseCode,
)

DEFAULT_PORT = 5003

_NOT_CONNECTED_MESSAGE = (
    "fast tool is not connected to an instrument: restart the tool server and "
    "Configure it with simulated off")
_BUSY_MESSAGE = "another motion command is in progress on this tool"

MOTION_COMMANDS = frozenset(
    {"Transfer", "RunProtocol", "ScanTips", "EjectTray", "Abort", "Resume"})

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
# Resume waits for the resumed run to finish, but how much of the run is
# left is unknown from the command alone, so this is the same flat
# placeholder as Abort.
EST_RESUME_S = 15
EST_TRANSFER_OVERHEAD_S = 60
EST_TRANSFER_PER_CYCLE_S = 20
EST_TIP_MAX_VOLUME_UL = 13.0
EST_RUN_PROTOCOL_OVERHEAD_S = 60
EST_RUN_PROTOCOL_PER_TASK_S = 15


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

    `command` is one of the nine generated oneof message types, which have
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


def _outcome_text(outcome: object) -> str:
    """"<error_name> (<error_code>): <message>" with None parts dropped, or
    "no error reported" when all are None."""
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
    return "no error reported"


def _message_for(result: RunResult, expected_tray_id: Optional[int]) -> str:
    """D-12: every message passes through _one_line with limit 500."""
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
        text = f"run aborted at {result.percent}%: {_outcome_text(result.outcome)}"
    elif isinstance(result, TimedOut):
        text = (f"run timed out at {result.percent}%; the instrument run was NOT aborted, "
                "check the instrument and stop it physically if needed")
    elif isinstance(result, Cancelled):
        text = "cancelled by operator"
    return _one_line(text, 500)


def _result_reply(result: RunResult, expected_tray_id: Optional[int] = None) -> ExecuteCommandReply:
    code = _RESPONSE_FOR_KIND[result.kind]
    message = _message_for(result, expected_tray_id)
    return _reply(code, message=message, meta=result.to_dict())


def _transport_error_reply(exc: Exception) -> ExecuteCommandReply:
    """ERROR_FROM_TOOL, no meta."""
    if isinstance(exc, InstrumentHTTPError):
        message = f"instrument HTTP {exc.status_code}: " + _one_line(str(exc.body), 200)
    else:
        message = f"instrument unreachable: {type(exc).__name__}: " + _one_line(str(exc), 200)
    return _reply(ERROR_FROM_TOOL, message=message)


def _recovery_reply(action: str, result: "dict | Refused") -> ExecuteCommandReply:
    """Map FastService.abort/resume's `dict | Refused`. Refused means the
    core sent nothing to the instrument (wrong state); the dict is the
    instrument's reply, which only counts as success with errorCode 0. A
    missing errorCode is treated as a failure."""
    if isinstance(result, Refused):
        return _reply(ERROR_FROM_TOOL, message=_message_for(result, None),
                      meta=result.to_dict())
    code = result.get("errorCode")
    if code == 0:
        return _reply(SUCCESS, meta=result)
    return _reply(ERROR_FROM_TOOL,
                  message=_one_line(f"instrument rejected {action}: errorCode {code}", 500),
                  meta=result)


class FastServer(ToolServer):
    toolType = "fast"
    config: Config

    def __init__(self) -> None:
        super().__init__()
        self._owned: Optional[OwnedService] = None
        self.service: Optional[FastService] = None
        self._motion_lock = threading.Lock()

    def _dispatchCommand(self, command: "message.Message") -> ExecuteCommandReply:
        """Override of ToolServer._dispatchCommand (RESEARCH Pattern 1, D-15).

        Runs in both simulated and real mode, before any instrument contact.
        base_server's simulated-mode dispatch never validates arguments and
        its _estimateDuration error slot is structurally always None, so bad
        arguments must be rejected here or they either sleep through
        unchecked (simulated) or surface as the wrong error code entirely.
        Never edits tools/base_server.py."""
        problems = _check_args(command)
        if problems:
            return _reply(
                INVALID_ARGUMENTS,
                message=_one_line("invalid arguments: " + "; ".join(problems), 500),
                meta=NeedsInput(missing=problems).to_dict(),
            )
        return super()._dispatchCommand(command)

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

    def _log_progress(self, percent: int, state: str) -> None:
        logging.info("fast run progress %s%% (%s)", percent, state)

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
            try:
                result = service.run_transfer(
                    request, expected_tray_id=expected,
                    options=RunOptions(timeout_s=self._timeout(None), on_progress=self._log_progress))
            except (InstrumentHTTPError, httpx.HTTPError) as exc:
                return _transport_error_reply(exc)
            return _result_reply(result, expected)
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
            try:
                result = service.run_protocol(
                    params.csv,
                    options=RunOptions(timeout_s=self._timeout(per_command),
                                       on_progress=self._log_progress))
            except (InstrumentHTTPError, httpx.HTTPError) as exc:
                return _transport_error_reply(exc)
            return _result_reply(result)
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
        (the command). Arity is therefore a safe, stable discriminator."""
        if len(args) == 2:
            return super().GetStatus(*args)  # type: ignore[arg-type]
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

    def Abort(self, params: "Command.Abort") -> ExecuteCommandReply:
        """Operator-issued abort of a running or paused run. The core
        refuses in any other state without contacting the instrument. Moves
        the head, so it takes the motion lock. Returns once the instrument
        has accepted the abort; it does not wait for the head to park."""
        return_liquid = _decision(params, "return_liquid")
        if return_liquid is None:
            return _reply(INVALID_ARGUMENTS,
                          message="return_liquid must be 'yes' or 'no'")
        service = self.service
        if service is None:
            return _reply(NOT_READY, message=_NOT_CONNECTED_MESSAGE)
        if not self._motion_lock.acquire(blocking=False):
            return _reply(NOT_READY, message=_BUSY_MESSAGE)
        try:
            try:
                result = service.abort(return_liquid=return_liquid)
            except (InstrumentHTTPError, httpx.HTTPError) as exc:
                return _transport_error_reply(exc)
            return _recovery_reply("abort", result)
        finally:
            self._motion_lock.release()

    def Resume(self, params: "Command.Resume") -> ExecuteCommandReply:
        """Operator-issued resume of a paused run. The core refuses unless
        the instrument is paused, without contacting it. On an accepted
        resume this WAITS for the resumed run to reach a terminal state,
        with the same timeout and progress logging as Transfer, so the
        protocol step reports the run's real outcome (Ran, Paused again,
        Aborted, TimedOut). Holds the motion lock for the whole wait.

        Known limitation: the wait treats `paused` as terminal on any poll.
        If the instrument still reports `paused` on the first status poll
        after accepting the resume, this returns Paused although the run is
        resuming. Not observed live yet; a supervised check should confirm
        the state flips before the first poll (or the core's wait should
        ignore a leading `paused`)."""
        is_tip_broken = _decision(params, "is_tip_broken")
        if is_tip_broken is None:
            return _reply(INVALID_ARGUMENTS,
                          message="is_tip_broken must be 'yes' or 'no'")
        service = self.service
        if service is None:
            return _reply(NOT_READY, message=_NOT_CONNECTED_MESSAGE)
        if not self._motion_lock.acquire(blocking=False):
            return _reply(NOT_READY, message=_BUSY_MESSAGE)
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
