"""The Galago adapter for the Formulatrix F.A.S.T. liquid handler.

It maps the seven intent-level commands 1:1 onto FastService methods and
holds no instrument policy of its own -- every decision (idle gate,
validate -> vision -> run sequencing, tray confirmation, timeouts) lives in
fast_mcp.service.FastService. This module never imports the MCP adapter
subpackage (fast_mcp.mcp) -- it obtains its FastService only through
fast_mcp.composition.open_service (D-04).
"""
import argparse
import logging
import math
import threading
from dataclasses import fields
from typing import Optional

import httpx
from google.protobuf.struct_pb2 import Struct

from fast_mcp.composition import OwnedService, endpoint_key, open_service
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
from fast_mcp.run_control import RunOptions
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

MOTION_COMMANDS = frozenset({"Transfer", "RunProtocol", "ScanTips", "EjectTray"})

COMMAND_TO_SERVICE_METHOD = {
    "Transfer": "run_transfer",
    "RunProtocol": "run_protocol",
    "ValidateProtocol": "validate",
    "GetStatus": "status",
    "GetTipStatus": "tip_status",
    "ScanTips": "scan_tips",
    "EjectTray": "eject_tray",
}

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
        text = f"run paused at {result.percent}%: {_outcome_text(result.outcome)}"
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


class FastServer(ToolServer):
    toolType = "fast"
    config: Config

    def __init__(self) -> None:
        super().__init__()
        self._owned: Optional[OwnedService] = None
        self.service: Optional[FastService] = None
        self._motion_lock = threading.Lock()

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
        if params.HasField("expected_tray_id"):
            return params.expected_tray_id
        return self.config.expected_tray_id or None

    def Transfer(self, params: "Command.Transfer") -> ExecuteCommandReply:
        if self.service is None:
            return _reply(
                NOT_READY,
                message=("fast tool is not connected to an instrument: restart the tool "
                         "server and Configure it with simulated off"))
        if not self._motion_lock.acquire(blocking=False):
            return _reply(NOT_READY, message="another motion command is in progress on this tool")
        try:
            request = TransferRequest(**{
                f.name: getattr(params, f.name) if params.HasField(f.name) else None
                for f in fields(TransferRequest)
            })
            expected = self._expected_tray_id(params)
            try:
                result = self.service.run_transfer(
                    request, expected_tray_id=expected,
                    options=RunOptions(timeout_s=self._timeout(None), on_progress=self._log_progress))
            except (InstrumentHTTPError, httpx.HTTPError) as exc:
                return _transport_error_reply(exc)
            return _result_reply(result, expected)
        finally:
            self._motion_lock.release()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
    args = parser.parse_args()
    if not args.port:
        raise RuntimeWarning("Port must be provided...")
    serve(FastServer(), str(args.port))
