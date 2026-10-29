# Phase 5: F5-safe Transfer & Operator Acknowledge - Pattern Map

**Mapped:** 2026-10-29
**Files analyzed:** 5 (2 new code/test, 2 modified, 1 spike doc)
**Analogs found:** 5 / 5 (05-SPIKE.md has only a loose analog)

All analog paths below are git-tracked in this repo, except the core excerpt, which is read from `git -C ~/data/nikko/stack-automation-layer show 934a621:stack_automation_layer/state_store.py`.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `tools/stack/ledger.py` (new) | service/store (persisted state machine) | file-I/O, CRUD | core `state_store.py` @934a621 (atomic write, fail closed) | exact for storage; state machine has no analog |
| `tools/stack/server.py` (mod) | tool-server handlers | request-response (Transfer is multi-call) | `tools/fast/server.py` `Transfer` (:715-740) plus this file's own read handlers | exact |
| `tools/tests/stack_ledger_test.py` (new) | test | file-I/O | `tools/tests/stack_test.py` `_StackTestCase` (:114-141) | role-match |
| `tools/tests/stack_test.py` (mod) | test | request-response, AST | itself: `_stack_adapter_violations` (:1107), `_plant` (:1166), `TestBusyReads` (:2130) | exact |
| `05-SPIKE.md` (new) | doc | n/a | Phase 4 `04-REVIEW-DISPOSITION.md` (format only) | loose |

## Pattern Assignments

### `tools/stack/ledger.py` (store, file-I/O)

**Analog:** core `state_store.py` @934a621.

**Atomic save** (core, mirror exactly, per D-02):
```python
def _fsync_dir(directory):
    if os.name == "nt":
        return
    with contextlib.suppress(OSError):
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)

def save(self, payload):
    data = dict(payload); data["version"] = STATE_VERSION
    text = json.dumps(data, sort_keys=True, indent=2)
    directory = self.path.parent
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=self.path.name + ".", suffix=".tmp")  # mkstemp gives 0600
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text); handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, self.path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    _fsync_dir(directory)
```

**Fail-closed load** (core, D-04):
```python
class StateUnreadable(Exception):
    def __init__(self, reason): super().__init__(reason); self.reason = reason

def load(self):
    try:
        raw = self.path.read_bytes()
    except FileNotFoundError:
        return None                       # clean start
    except OSError:
        raise StateUnreadable("unreadable") from None
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise StateUnreadable("corrupt") from None
    if not isinstance(payload, dict):
        raise StateUnreadable("corrupt")
    version = payload.get("version")
    if type(version) is not int or version != STATE_VERSION:
        raise StateUnreadable("unknownVersion")
```

**Directory resolution** (core `_posix_state_dir`, adapt per D-03 with `galago-tools/stack` and no `STACK_STATE_DIR`):
```python
xdg = environ.get("XDG_STATE_HOME")
if xdg and os.path.isabs(xdg):
    return pathlib.Path(xdg) / _APP_DIR
return pathlib.Path.home() / ".local" / "state" / _APP_DIR
```
Read the environment at call time, never at import. Load never creates anything.

**Gaps (no analog, use RESEARCH.md and CONTEXT D-02, D-05..D-08):**
- `fcntl.flock` on a sibling lock file. The core takes no file lock, so write this fresh.
- The record state machine, the sha256 fingerprint and the retention prune.
- Keep it pure and free of `stack_automation_layer.mcp` imports (D-21 invariant). The new module is in `tools/stack/*.py`, so `_STACK_SOURCES` globs it automatically.

---

### `tools/stack/server.py` (handlers, request-response)

**Motion lock analog:** `tools/fast/server.py` :464 (`self._motion_lock = threading.Lock()`), :715-740.
```python
if not self._motion_lock.acquire(blocking=False):
    return _reply(NOT_READY, message=_BUSY_MESSAGE)
try:
    ...
finally:
    self._motion_lock.release()
```
Adapt for stack: CONTEXT D-12 says refuse with `ERROR_FROM_TOOL` "busy" (the operator-visible code), not `NOT_READY`. D-12 also calls the lock module-level, so decide at plan time between module-level and instance. Take the lock after the arg check and before the ledger load, and release it in `finally`.

**Service access:** use `service = self._require_service()` once at the top of `Transfer` and make every core call through it (WR-02). Pattern from `server.py` :555-562 and :570-577.

**Edits at known locations** (line numbers from the current file):
- Remove `UNAVAILABLE_COMMANDS` (:77) and its test at `_dispatchCommand` (~:539, `type(command).__name__ not in UNAVAILABLE_COMMANDS`). Drop `_unavailable_reply` (~:243) once unused. Then `service is None` always gives `NOT_READY` `_NOT_CONFIGURED_MESSAGE`.
- Add `"latchStatus"` to `_SUCCESS_KINDS` (:123 block).
- Add `GetFailureLatch` -> `latch_status` and `AcknowledgeFailure` -> `acknowledge_failure` to `COMMAND_TO_SERVICE_METHOD` (the dict ending at :64 `"GetTransferEstimate": "estimate_transfer"`).
- `_apply_config` (:447-475): replace the "Recorded only" comment. Resolve and validate `ledger_dir` there (absolute, otherwise `ValueError`, creating nothing).
- `_transfer_request` (:156): reuse for `Transfer` and the fingerprint. Its docstring names only GetTransferEstimate, so update it. It reads the same field names, so `Command.Transfer` works.

**Read handler pattern** (:582 region), for `GetFailureLatch`:
```python
def GetManagerState(self, params):
    return _result_reply(self._require_service().manager_state())
```
`GetFailureLatch` is the same shape with `latch_status()`.

**Reply helpers to reuse:** `_reply(code, *, message, meta)` (:200 region), `_one_line(text, limit)`, `_error_line(d)` (:271, caps at 300 chars, never uses `explanation`), `_result_reply` (:292). Ledger-generated replies are built with `_reply(ERROR_FROM_TOOL, message=..., meta={"stepKey":..., "ledgerState":...})`.

**`AcknowledgeFailure`:** `_check_args` already covers a non-blank guid and yes/no. Add the `arm_inspected != "yes"` -> `_reply(INVALID_ARGUMENTS, ...)` check in the handler before the core call (the INVALID_ARGUMENTS shape is at `_dispatchCommand` :525-528). In simulated mode the handler is never reached.

**Error-handling pattern:** exceptions propagate to base_server, which sets `DRIVER_ERROR`/`last_error`. Inside `Transfer`, wrap `execute_transfer` in `try/except Exception` so the record stays `submitting` (D-08), then return `ERROR_FROM_TOOL`.

---

### `tools/tests/stack_test.py` (mod; AST + busy tests)

**AST helpers to modify:** `_FORBIDDEN_SERVICE_CALLS` (:1081-1085) shrinks to `start_transfer`, `cancel_transfer`, `go_to_safe_position`, `wait_safe_position`, `validate_transfer`. `test_every_forbidden_service_call_is_reported` asserts `len == 10` (:1224) and needs updating to 5.

Existing violation form to extend, in `_stack_adapter_violations`:
```python
if isinstance(func, ast.Attribute) and func.attr in _FORBIDDEN_SERVICE_CALLS:
    violations.append(f"{at}: forbidden core call .{func.attr}()")
```

Add new checks in the same "return strings, never raise" style:
- `plan_transfer` count == 1.
- `acknowledge_failure` count == 1, inside the `AcknowledgeFailure` FunctionDef.
- `execute_transfer` count == 1, with no `For`/`While`/`ListComp`/`SetComp`/`DictComp`/`GeneratorExp` ancestor. Build a parent map, or walk each FunctionDef and its loops. Also require it to sit in the fresh-path function after the write-ahead call. Compare statement order (`lineno`) against the ledger write-ahead call.
- `wait_transfer` is allowed in loops.

**Planting:** `_plant(tree, function, statement)` (:1166-1189) inserts a statement at module top or at the start of a function after its docstring. Reuse it for each planted violation:
- `self.service.execute_transfer(p)` inserted a second time.
- `execute_transfer` inside a `for` (`"for _ in range(2):\n    self.service.execute_transfer(p)"`).
- `acknowledge_failure` inside `GetManagerState`.
- A second `plan_transfer`.

**Required functions:** `_REQUIRED_FUNCTIONS = ("_configure", "_result_reply", "GetManagerState")` (:1096). Add the fresh-path function name and `AcknowledgeFailure`.

**`test_allowed_read_calls_are_not_reported`** (:1280-1286) plants allowed calls and asserts `[]`. Add `latch_status()` and `wait_transfer(...)`.

**Test classes to change:**
- `TestBusyReads` (:2130). The injected Transfer handler via `patch.object(self.server, "Transfer", handler)` (:2160 region) is replaced by a real `Transfer`. Fake `service.wait` blocks on a `threading.Event`. Keep the `entered`/`release` pattern and the cleanup order (`addCleanup(thread.join, 10)` first, then `addCleanup(release.set)`, so release runs before join):
```python
release = threading.Event(); entered = threading.Event()
def _blocking(*a, **k):
    entered.set(); release.wait(timeout=10); return Ran(...)
```
  The `get_failure_latch` subtest (:2193-2197) currently expects `_REFUSALS["GetFailureLatch"]` ERROR_FROM_TOOL. Change it to SUCCESS with `latch_status().to_dict()` meta.
- `TestRealModeRefusals`, `TestRealModeRefusalsOrdering` (:1942, :1975), `_REFUSALS` and `TestOneToOneSurface`: rework, since the placeholders are gone.
- `TestResultMapping` (:1606): add a `latchStatus` SUCCESS case.
- `TestConfigureLedgerDir` (:1018): extend for absolute/relative/XDG resolution.
- `_PINNED_CORE_SHA` pin test (:1050): unchanged.

**Fixture:** `_RealModeGrpcTestCase` (:1295-1311) injects `MagicMock(spec=StackService)`, sets `server.status = READY` and serves over gRPC. For `Transfer` tests, also set `self.server._ledger_dir = <tmp>` (or Configure with `ledger_dir`). Build results from the core's result classes (`Ran`, `Failed`, `Lost`, `Refused`, `TaskHandle`, `TransferPlan`).

**Restart scenario:** a new `StackServer()` over the same ledger dir, mock service injected the same way.

---

### `tools/tests/stack_ledger_test.py` (new; unit tests of the ledger)

**Analog:** `_StackTestCase.setUp` (stack_test.py :114-141): `tempfile.TemporaryDirectory()` plus `addCleanup`, and `patch.dict(os.environ, {...})` with `addCleanup(env_patcher.stop)`.
```python
self._tmpdir = tempfile.TemporaryDirectory()
self.addCleanup(self._tmpdir.cleanup)
env_patcher = patch.dict(os.environ, {"XDG_STATE_HOME": ..., })
env_patcher.start(); self.addCleanup(env_patcher.stop)
```
Import `_StackTestCase` from `tools.tests.stack_test` only if the loopback socket guard is wanted. Otherwise a plain `unittest.TestCase` with a temp dir is enough, since the ledger makes no network calls.

Cases to write first, one per D-07 row, plus:
- corrupt, unknown-version and unreadable files (fail closed, file untouched)
- mode 0700/0600 (`os.stat`)
- atomic replace (tmp file removed on failure)
- flock serialisation between two threads
- fingerprint stability and exclusions (`step_key`, `timeout_s`)

---

### `05-SPIKE.md`

No code analog. Structure it as one section per D-01 question: question, evidence (`git show 934a621:stack_automation_layer/service.py` with line refs), answer, and a verdict that confirms or amends D-05..D-12. The decision log in `04-REVIEW-DISPOSITION.md` is the format reference.

## Shared Patterns

### One-line operator messages
**Source:** `tools/stack/server.py` `_one_line` (:~215) and `_error_line` (:271). **Apply to:** every new reply message. Build from structured fields, cap at 300 or 500 characters, never use the core `explanation`.

### Reply codes
**Source:** `tools/stack/server.py` `_reply`. **Apply to:** all handlers. Operator-visible refusals use `ERROR_FROM_TOOL`. `INVALID_ARGUMENTS` and `NOT_READY` text is hidden by galago-core (see `_unavailable_reply` docstring).

### Admitted service per thread (WR-02)
**Source:** `_require_service()` (:546). **Apply to:** `Transfer`, `GetFailureLatch`, `AcknowledgeFailure`. Never read `self.service` directly inside a handler.

### Non-blocking motion lock
**Source:** `tools/fast/server.py` :719-740. **Apply to:** `Transfer` only.

### Test isolation
**Source:** `_StackTestCase` (stack_test.py :114-141). Never touch `~/.local/state/...`. Set the env and use temp dirs. Loopback-only socket guard.

## No Analog Found

| File / piece | Role | Data Flow | Reason |
|---|---|---|---|
| flock-serialised read-modify-write in `ledger.py` | store | file-I/O | The core takes no file lock; use stdlib `fcntl.flock` per CONTEXT D-02 |
| Repeat-key state machine (D-07) | state machine | CRUD | Novel; follow the table in CONTEXT D-07 |
| Re-attach `wait_transfer` loop (D-11) | service call | polling | No existing loop; read the core's `wait_transfer` (`service.py` :930-972) and clamp at `WAIT_TRANSFER_MAX_S=300` |
| AST "single call site, not in a loop, after the write-ahead" check | test | transform | Existing checks are name-only; the parent-map and ordering logic is new, built on `ast.walk` and `_plant` |

## Notes for the planner

- `tools/base_server.py` must not be edited. `ExecuteCommand` is overridden only for `READ_COMMANDS`, which already contains `get_failure_latch`, so no change is needed there.
- Because `execute_transfer` appears in `ledger.py` nowhere, keep its single call site in `server.py` so the AST count stays at 1 across `tools/stack/*.py`. Do not move the call into the ledger module.
- The `fast_test.py` AST helper (`_adapter_invariant_violations`, :3212) is a second reference. It is larger and fast-specific, so prefer the stack helper in `stack_test.py` as the base.

## Metadata

**Analog search scope:** `tools/stack/`, `tools/fast/server.py`, `tools/tests/`, core `state_store.py` @934a621
**Files read:** `server.py` (stack, partial), `fast/server.py` (partial), `stack_test.py` (partial), core `state_store.py`
**Pattern extraction date:** 2026-10-29
