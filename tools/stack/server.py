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


def _error_line(d: dict) -> str:
    """One-line operator message from a non-success result dict (D-11): the
    kind, the reason when present, the guid when present. Never the
    explanation, message, detail text or error.detail."""
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
    args = parser.parse_args()
    if not args.port:
        raise RuntimeWarning("Port must be provided...")
    serve(StackServer(), str(args.port))
