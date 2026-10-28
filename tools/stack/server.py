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
import logging
import math
from typing import Any, Optional

from google.protobuf.struct_pb2 import Struct
from stack_automation_layer.composition import OwnedService, open_service
from stack_automation_layer.model import Location, TransferRequest
from stack_automation_layer.owner_lock import endpoint_key
from stack_automation_layer.service import StackService

from tools.base_server import ToolServer, serve
from tools.grpc_interfaces.stack_pb2 import Command, Config
from tools.grpc_interfaces.tool_base_pb2 import (
    ERROR_FROM_TOOL,
    SUCCESS,
    ExecuteCommandReply,
    ResponseCode,
)

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

    def _configure(self, config: Config) -> None:
        host = config.host.strip()
        if not host:
            raise ValueError("stack: Config.host is required")
        port = config.port or DEFAULT_PORT
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
        if self._owned is not None:
            self._owned.close()
            self._owned = None
            self.service = None
        self._owned = open_service(host, port, owner="galago")
        self.service = self._owned.service
        logging.warning(_RESTART_WARNING)

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


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
    args = parser.parse_args()
    if not args.port:
        raise RuntimeWarning("Port must be provided...")
    serve(StackServer(), str(args.port))
