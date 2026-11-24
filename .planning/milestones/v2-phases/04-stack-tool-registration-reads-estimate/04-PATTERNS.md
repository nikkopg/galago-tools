# Phase 4: STACK Tool Registration, Reads & Estimate - Pattern Map

**Mapped:** 2026-10-28
**Files analyzed:** 8 (6 new, 3 modified registration points)
**Analogs found:** 8 / 8 (all tracked via `git ls-files`)

All analogs below are git-tracked: `tools/fast/server.py`, `tools/fast/requirements.txt`, `tools/fast/__init__.py`, `tools/tests/fast_test.py`, `interfaces/tools/grpc_interfaces/fast.proto`, `interfaces/tools/grpc_interfaces/tool_base.proto`, `interfaces/controller.proto`, `pyproject.toml`.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `interfaces/tools/grpc_interfaces/stack.proto` | proto/contract | request-response | `interfaces/tools/grpc_interfaces/fast.proto` | exact |
| `interfaces/tools/grpc_interfaces/tool_base.proto` (modify) | config/registration | - | same file, fast lines 28, 54, 84 | exact |
| `interfaces/controller.proto` (modify) | config/registration | - | same file, `fast = 23;` line 30 | exact |
| `tools/stack/__init__.py` | package marker | - | `tools/fast/__init__.py` | exact |
| `tools/stack/server.py` | service/adapter | request-response (+ bypass reads) | `tools/fast/server.py` | exact (role), narrower surface |
| `tools/stack/requirements.txt` | config | - | `tools/fast/requirements.txt` | exact |
| `pyproject.toml` (modify) | config | - | fast_mcp mypy override (lines 31-33) | exact |
| `tools/tests/stack_test.py` | test | request-response, AST | `tools/tests/fast_test.py` | exact (with closed-port difference) |

## Pattern Assignments

### `interfaces/tools/grpc_interfaces/stack.proto` (proto, request-response)

**Analog:** `interfaces/tools/grpc_interfaces/fast.proto` (lines 1-30)

```proto
syntax = 'proto3';

package com.science.foundry.tools.grpc_interfaces.fast;

message Command {
  oneof command {
    Transfer transfer = 1;
    ...
  }
  message Transfer {
    optional int32 source_deck = 1;
    ...
    optional double volume = 11;
```
Copy: `syntax`, package line (`...stack`), `message Command { oneof command {...} nested messages }`, every string/double/bool field `optional`, top-level `message Config`. Use the D-01 ten-entry order and field shapes from RESEARCH "The draft proto" (reformat one field per line). Carry the CONTEXT `<specifics>` comment block (step_key unique per run; arm_inspected "yes" only after inspection and recovery in the STACK Manager; no lock_dir). `Config` scalars are NOT optional (0/"" mean unset). Avoid message names `GetStatus`, `EstimateDuration`, `Configure`, `ExecuteCommand`, `Estimate*` (D-05).

### `tool_base.proto` / `controller.proto` / `pyproject.toml` (registration)

**Analog:** the fast lines in the same files.
- `tool_base.proto:28` `import "tools/grpc_interfaces/fast.proto";` -> add `import "tools/grpc_interfaces/stack.proto";` after it.
- `tool_base.proto:54` `tools.grpc_interfaces.fast.Command fast = 23;` -> add `tools.grpc_interfaces.stack.Command stack = 24;` (oneof `tool_command`).
- `tool_base.proto:84` `tools.grpc_interfaces.fast.Config fast = 42;` -> add `tools.grpc_interfaces.stack.Config stack = 43;` (oneof `config`).
- `controller.proto:30` `fast = 23;` (last ToolType) -> add `stack = 24;`.
- `pyproject.toml` (end of file, comment + override):
```toml
# fast_mcp ships no py.typed marker (core-only package, Phase 5 D-01/D-03).
[[tool.mypy.overrides]]
module = ["fast_mcp", "fast_mcp.*"]
ignore_missing_imports = true
```
Add an identical block with `module = ["stack_automation_layer", "stack_automation_layer.*"]`. After proto edits run `bin/make proto` (generated `*_pb2*.py[i]` are gitignored).

### `tools/stack/requirements.txt` (config)

**Analog:** `tools/fast/requirements.txt` (comment lines + one pinned line):
```
fast-mcp @ git+https://gitlab.formulatrix.com/nikkopg/fast-mcp.git@b30b38df48e8480f325228145ccae7915a56e437
```
Use `stack-automation-layer @ git+https://gitlab.formulatrix.com/nikkopg/stack-automation-layer.git@ed8ce478d8881a517eb93ed233707f81aea01238`, no `[mcp]` extra. Local install via `git+file://` (see RESEARCH Installation); make it a human-action checkpoint.

### `tools/stack/server.py` (adapter, request-response + BUSY-bypass reads)

**Analog:** `tools/fast/server.py`

**Imports pattern** (lines 15-72; swap fast_mcp -> stack_automation_layer, grpc_interfaces.stack_pb2):
```python
import argparse, logging, math, threading
from typing import Any, Optional, cast
import grpc
from google.protobuf import message
from google.protobuf.struct_pb2 import Struct

from fast_mcp.composition import OwnedService, endpoint_key, open_service   # fast re-exports endpoint_key
...
from tools.base_server import ToolServer, serve
from tools.grpc_interfaces.fast_pb2 import Command, Config
from tools.grpc_interfaces.tool_base_pb2 import (
    DRIVER_ERROR, ERROR_FROM_TOOL, INVALID_ARGUMENTS, NOT_READY, SUCCESS,
    Command as ToolCommand, ExecuteCommandReply, ResponseCode,
)
```
STACK differences: `from stack_automation_layer.composition import OwnedService, open_service` and `from stack_automation_layer.owner_lock import endpoint_key` (composition does not re-export it). Never import `stack_automation_layer.mcp`. `DEFAULT_PORT = 5005`.

**Module constants pattern** (lines 68-95): `DEFAULT_PORT`, `CONTROL_COMMANDS = frozenset({"pause","resume","abort"})` (lowercase oneof field names) -> `READ_COMMANDS` (eight lowercase names, D-13); `COMMAND_TO_SERVICE_METHOD` dict class-name -> service method (use for the 1:1 surface test). `EST_*` int constants (D-19).

**`_one_line`** (lines 169-176) copy as-is:
```python
def _one_line(text: str, limit: int) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) > limit:
        return collapsed[: max(limit - 3, 0)] + "..."
    return collapsed
```

**`_reply`** (lines 273-282) copy as-is:
```python
def _reply(code: ResponseCode, *, message: str = "",
          meta: Optional[dict] = None) -> ExecuteCommandReply:
    reply = ExecuteCommandReply(response=code, error_message=message, return_reply=True)
    if meta is not None:
        s = Struct()
        s.update(meta)
        reply.meta_data.CopyFrom(s)
    return reply
```
Then add the explicit `_SUCCESS_KINDS` allowlist + `_result_reply` + `_error_line` (RESEARCH Pattern 1). SUCCESS replies must have an empty message.

**`_check_args`** (starts line 180, `def _check_args(command: "message.Message") -> list[str]`): pure, returns list of error strings, dispatched by `type(command).__name__`. STACK checks (D-17): Transfer step_key set and `.strip()`, timeout_s finite >= 0 if `HasField`; AcknowledgeFailure guid non-blank, arm_inspected exactly "yes"/"no" (no strip/lower; do NOT copy fast's `_decision`). Normaliser for instrument fields: `value if command.HasField(n) and value.strip() else None` (HasField is true for "").

**Class + `__init__`** (lines 456-470):
```python
class FastServer(ToolServer):
    toolType = "fast"
    config: Config
    def __init__(self) -> None:
        super().__init__()
        self._owned: Optional[OwnedService] = None
        self.service: Optional[FastService] = None
```
Use `toolType = "stack"`, `_owned`, `service: Optional[StackService]`.

**`_dispatchCommand` override** (lines 472-~495): `_check_args` runs before the simulated branch so validation applies in both modes; returns `INVALID_ARGUMENTS` on error, then `super()._dispatchCommand(command)`. STACK adds the real-mode refusal of Transfer/AcknowledgeFailure/GetFailureLatch (`ERROR_FROM_TOOL`, one line "not available in this build") after `_check_args`, and D-14 `NOT_READY` "stack: not configured" when `self.service is None`.

**`ExecuteCommand` override** (lines 515-544) — copy shape, rename:
```python
if request.WhichOneof("tool_command") == self.toolType:
    stack_command = request.stack
    field_name = stack_command.WhichOneof("command")
    if field_name in READ_COMMANDS:
        command = getattr(stack_command, field_name)
        try:
            return self._dispatchCommand(command)
        except Exception as e:
            logging.error(f"Error on Tool ={self.toolId}")
            self.last_error = str(e)
            return ExecuteCommandReply(response=DRIVER_ERROR, error_message=str(e))
return super().ExecuteCommand(request, context)
```

**`_configure`** (lines 546-562) — copy shape (RESEARCH Pattern 3 has the STACK version):
```python
host = config.host.strip()
if not host: raise ValueError("fast: Config.host is required")
port = config.port or DEFAULT_PORT
... finite/>=0 check on timeout ...
key = endpoint_key(host, port)
if self._owned is not None and self._owned.endpoint == key:
    return
if self._owned is not None:
    self._owned.close(); self._owned = None; self.service = None
self._owned = open_service(host, port, owner="galago")
self.service = self._owned.service
```
Add the D-09 `logging.warning(...)` after a successful open. Exceptions propagate (base_server.Configure -> NOT_READY with `str(e)`). Note STACK `open_service` probes eagerly, so closed port => Configure fails (unlike fast).

**Estimate hooks** (lines 968-1005): `def EstimateX(self, params: "Command.X") -> int: return EST_...` with no I/O and never raising; one per message class (10 hooks: Transfer, GetManagerState, GetRobotStates, ListDevices, ListLabwareProfiles, ListTransferProfiles, GetLabwarePresence, GetTransferEstimate, AcknowledgeFailure, GetFailureLatch).

**Handlers:** method named after the command message class, e.g. `def GetManagerState(self, params) -> ExecuteCommandReply: return _result_reply(self.service.manager_state())`. `ListDevices(refresh=params.HasField("refresh") and params.refresh)` keyword-only. Build `TransferRequest(robot=, labware_profile=, source=Location(device=, deck=, nest=, transfer_profile=), destination=Location(...))` with blank -> None. `GetLabwarePresence`: robot None if blank (blank `""` would issue a request).

**`__main__`** (lines 1008-1015) copy, with `serve(StackServer(), str(args.port))`:
```python
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    parser = argparse.ArgumentParser()
    parser.add_argument("--port")
    args = parser.parse_args()
    if not args.port:
        raise RuntimeWarning("Port must be provided...")
```

### `tools/stack/__init__.py`
Empty, as `tools/fast/__init__.py`.

### `tools/tests/stack_test.py` (test)

**Analog:** `tools/tests/fast_test.py`

**Skip guard** (lines 31-79): one `try` around all core-dependent imports; on `ModuleNotFoundError` with `exc.name.split(".")[0] in ("stack_automation_layer","httpx")` raise `unittest.SkipTest("... see tools/stack/requirements.txt ...") from exc`, else re-raise. Import `tools.stack.server` inside the try; generated pb2 imports after (`from tools.grpc_interfaces import controller_pb2, stack_pb2, tool_base_pb2`).

**Registration tests** (lines 2656-2667):
```python
def test_command_oneof_registration(self) -> None:
    field = tool_base_pb2.Command.DESCRIPTOR.fields_by_name["fast"]
    self.assertEqual(field.containing_oneof.name, "tool_command")
```
Use `"stack"`, `ToolType.Value("stack") == 24`, field numbers 24/43; plus a proto-freeze test pinning every `(name, number)` pair of the Command oneof (D-01) and Config.

**Real-mode gRPC fixture** (lines 804-838): `MagicMock(spec=StackService)` assigned to `server.service`, `server.config = stack_pb2.Config(host="h")`, `server.status = READY`, `grpc.server(futures.ThreadPoolExecutor(max_workers=4))`, `add_ToolDriverServicer_to_server`, `insecure_channel` on `_free_tcp_port()` (copy helper from fast_test.py:271), cleanups via `addCleanup`.

**Blocked-command helper** (lines 841-~875): `release`/`entered` `threading.Event`, blocking side effect, run command over the stub in a thread; cleanups LIFO (`addCleanup(thread.join, 10)` then `addCleanup(release.set)`). STACK variant (D-16, Pitfall 5): patch `server.Transfer` via `patch.object(server, "Transfer", side_effect=blocking)` with a non-blank `step_key`; assert each read returns its result (get_failure_latch -> ERROR_FROM_TOOL, not NOT_READY), status BUSY, second non-read NOT_READY, status READY after release. Write red first.

**Simulated tests:** `patch("tools.base_server.time", types.SimpleNamespace(time=time.time, sleep=self.fake_sleep))` (fast_test.py:357) and assert sleep called with the EST constant.

**Configure tests:** `patch("tools.stack.server.open_service")` with a two-method fake transport (`get_application` -> `{"productName": "Stack manager"}`, `get_versions` -> `{"2":..., "3":...}`) for success paths; set `STACK_USER`/`STACK_PASSWORD`/`STACK_MCP_LOCK_DIR` via `patch.dict(os.environ, ...)` with a `tempfile.TemporaryDirectory()`; closed loopback port asserts NOT_READY + "transport error" (opposite of fast); `owner="mcp"` lock via `acquire_owner_lock` fails Configure naming the holder; `addCleanup` closes `server._owned`.

**Pin test** (lines 3508-3522): copy, replacing `fast-mcp`/`fast_mcp` with `stack-automation-layer`/`stack_automation_layer`, regex `^stack-automation-layer @ git\+https://gitlab\.formulatrix\.com/nikkopg/stack-automation-layer\.git@[0-9a-f]{40}$`, and compare `direct_url.json` `vcs_info.commit_id` with the pinned SHA (needs `git+file://` install, not archive). Also assert SHA == `ed8ce478d8881a517eb93ed233707f81aea01238`.

**AST invariant** (lines 3212-3235, 3391-3400): assertion-free `_..._violations(tree) -> list[str]`, `_plant(tree, function, statement)` deep-copies and inserts a statement; one test asserts the real tree is `[]`, others assert each planted forbidden call (`plan_transfer`, `execute_transfer`, `start_transfer`, `wait`, `wait_transfer`, `cancel_transfer`, `go_to_safe_position`, `wait_safe_position`, `acknowledge_failure`, `validate_transfer`) is reported and a planted allowed call (e.g. `manager_state`) is not. Glob `tools/stack/*.py`. Second test (D-21): no import of `stack_automation_layer.mcp` (allow `.owner_lock`, `.composition`, etc.).

**Other fast test anchors to mirror:** 1:1 surface (`TestOneToOneSurface` :2591-2654, with `MagicMock(spec=StackService)` per command), estimates (`TestEstimates` :2768: each hook returns int >= 1 for an empty message), not-configured (`TestNotConfigured` :2517), reconfigure (`TestReconfigure` :2548). Mypy applies to tests: annotate everything, `-> None`.

## Shared Patterns

### Reply code discipline
**Source:** `tools/fast/server.py:273-282` (`_reply`), RESEARCH Pattern 1.
**Apply to:** every handler. Allowlisted kinds -> SUCCESS with empty message; everything else -> `ERROR_FROM_TOOL` with a single-line message from kind/reason/guid (never `explanation`); arg errors -> `INVALID_ARGUMENTS`; unrecognised result -> ERROR_FROM_TOOL, never SUCCESS.

### Validation before simulation
**Source:** `tools/fast/server.py:472-` (`_dispatchCommand` calling `_check_args`).
**Apply to:** all commands in both modes.

### Error propagation from Configure
**Source:** `tools/base_server.py` `Configure` (:89-120, do not edit) with `_configure` raising.

### Gate
`source ~/data/nikko/.venvs/galago-py310/bin/activate && bin/make proto test` (ruff, mypy, unittest, pytest). Baseline 147 tests.

## No Analog Found

| File / behaviour | Reason |
|------------------|--------|
| Kind -> reply table (`_SUCCESS_KINDS`, `_error_line`, guid extraction) | fast uses isinstance mapping on result classes (`_message_for`); STACK maps by `kind` string from `to_dict()`. Use RESEARCH Pattern 1 |
| Successful-Configure test seam (patched `open_service` with fake transport) | fast's open_service is lazy; STACK probes eagerly. Use RESEARCH Code Examples |
| Real-mode refusal of Transfer/Ack/Latch | New to STACK (Phase 5 removes) |

## Metadata

**Analog search scope:** `tools/fast/`, `tools/tests/fast_test.py`, `interfaces/`, `pyproject.toml`
**Pattern extraction date:** 2026-10-28
