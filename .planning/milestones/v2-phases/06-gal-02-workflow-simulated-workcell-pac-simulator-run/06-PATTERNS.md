# Phase 6: GAL-02 Workflow, Simulated Workcell & PAC-Simulator Run - Pattern Map

**Mapped:** 2026-11-02
**Files analyzed:** 5 (4 new in galago-tools, 1 optional)
**Analogs found:** 4 / 5 (JSON protocol has no in-repo analog; format comes from galago-core docs)

All analog paths below are git-tracked (verified with `git ls-files` in their own repos). No gitignored mirror paths are used.
Sibling repos: `/home/formulatrix/data/nikko/stack-automation-layer` (SAL), `/home/formulatrix/data/nikko/fast/fast-mcp`, `/home/formulatrix/data/nikko/galago-core`.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `docs/runbooks/gal-02-handoff.protocol.json` | config (importable protocol) | transform (params -> queued commands) | `RESEARCH.md` Code Examples script + `../galago-core/docs/script-protocols.md` export format | format-match, no in-repo analog |
| `docs/runbooks/gal-02-handoff.md` | runbook/doc | operator procedure + findings log | `fast-mcp/docs/runbooks/phase5-galago-live-run.md` (shape), `stack-automation-layer/docs/runbooks/stack-validation.md` Part A (sim safety/ports) | role-match (two analogs) |
| `tools/tests/gal02_handoff_test.py` | test (harness + offline replay proof) | request-response via in-process gRPC + subprocess node | `tools/tests/stack_test.py` (`_TransferTestCase`, `_FakeCore`, `TestTransferFreshPath`) | exact (fixtures), partial (node subprocess is new) |
| inline node harness (string inside the test; no separate `.js`) | utility | transform | RESEARCH.md "Node harness" | no analog (new) |
| DEP-02 precondition script (a fenced bash block inside the runbook, not a repo file) | utility | read-only check | RESEARCH.md "DEP-02 precondition check" | no analog (new) |

`docs/runbooks/` does not exist yet (verified); creating it also creates the first non-`specs/` doc dir. `tools/tests/` uses `*_test.py` naming picked up by `bin/make test` (unittest discover `-p "*_test.py"` then pytest).

## Pattern Assignments

### `tools/tests/gal02_handoff_test.py` (test, gRPC request-response + node subprocess)

**Analog:** `/home/formulatrix/data/nikko/galago-tools/tools/tests/stack_test.py`

**Import + skip-guard pattern** (stack_test.py:1-12, 26-83). All core-dependent imports sit in ONE try block, converted to `unittest.SkipTest` with a stated reason. Copy this shape. `fast_test.py:72` does the same for `fast_mcp`.
```python
try:
    import httpx  # noqa: F401
    import stack_automation_layer.composition as core_composition
    ...
    from tools.stack import server as stack_server
    from tools.stack.server import READ_COMMANDS, StackServer, _result_reply
except ModuleNotFoundError as exc:
    if exc.name and exc.name.split(".")[0] in ("stack_automation_layer", "httpx"):
        raise unittest.SkipTest(
            "stack_automation_layer core is not installed (private GitLab dependency, ...)") from exc
    raise

from tools.grpc_interfaces import controller_pb2, fast_pb2, stack_pb2, tool_base_pb2
from tools.grpc_interfaces.tool_base_pb2 import (DRIVER_ERROR, ERROR_FROM_TOOL, FAILED, NOT_READY, READY, SUCCESS)
```
In the new module import ONLY the fixtures, never test classes (unittest would re-collect them): `from tools.tests.stack_test import _TransferTestCase, _FakeCore, _ESTIMATE_FIELDS, _GUID` plus `Refused, TaskHandle` re-exported from the core results (they are imported inside stack_test's try block; re-import them from `stack_automation_layer.results` in your own try block rather than depending on re-export). Also `REPLAY_WINDOW_S` from `tools.stack.server`, `ParseDict` from `google.protobuf.json_format`, `datetime/timedelta`, `patch`.

**Fixture to subclass** (stack_test.py:1682-1700 base, 1787-1818 `_TransferTestCase`):
```python
class _TransferTestCase(_RealModeGrpcTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.ledger_dir = os.path.join(self._tmpdir.name, "ledger")
        self.server._ledger_dir = self.ledger_dir
        self.core = _FakeCore()
        self.server.service = self.core  # type: ignore[assignment]
        self.addCleanup(self._assert_motion_lock_free)
    def _transfer(self, step_key=_STEP_KEY, **fields): ...
```
`_RealModeGrpcTestCase.setUp` builds `StackServer()`, `config = stack_pb2.Config(host="127.0.0.1")`, `status = READY`, and `self.stub = _serve_in_process(self, self.server)`. `_StackTestCase.setUp` (stack_test.py:121-156) already isolates HOME/XDG_STATE_HOME/STACK_STATE_DIR in a tmpdir and installs the loopback-only socket guard. Nothing extra needed for isolation.

**Fake core counters** (stack_test.py:1726-1785): `self.core.execute_calls` (count of `execute_transfer` attempts), `self.core.call_names`, `self.core.execute_result` (set to an Exception instance to raise, a callable to call, or a value), `Refused(reason=...)`, `TaskHandle(guid=_GUID, robot="sim-arm-1", estimated_s=30.0)`.
Caveat (RESEARCH anti-pattern): `execute_calls` counts attempts including a `Refused` one. For the retry test assert `== 2` after Refused then TaskHandle, then still `== 2` after the replay.

**Core dispatch pattern for D-06** (prototyped in RESEARCH, replay assertions mirror `TestTransferFreshPath` stack_test.py:1821+):
```python
def dispatch(self, p):
    return self.stub.ExecuteCommand(self._stack(transfer=ParseDict(p, stack_pb2.Command.Transfer())))

reply = self.dispatch(in_leg); assert reply.response == SUCCESS; assert self.core.execute_calls == 1
again = self.dispatch(in_leg)
assert again.response == SUCCESS and again.meta_data["replayed"] is True   # meta keys: stepKey, ledgerState, result, replayed
assert self.core.execute_calls == 1
future = stack_server._utcnow() + timedelta(seconds=REPLAY_WINDOW_S + 5)
with patch.object(stack_server, "_utcnow", return_value=future):
    late = self.dispatch(in_leg)
# late.response == ERROR_FROM_TOOL, "step key already completed" in late.error_message
```
`ParseDict` rejects unknown proto field names, which serves as the contract test between the script output and `stack.proto` (script must emit `destination_*`, not `fast_*`).

**Hardware deny-set assertion (D-10):** module-level `_HARDWARE = frozenset({"10.150.1.125", "stack-server"})` and `assertNotIn(self.server.config.host, _HARDWARE)` in setUp. Existing literals are at stack_test.py:532 and :1193 (`_FORBIDDEN_LITERALS`); the AST literal scan only globs `tools/stack/*.py` (stack_test.py:1175), so `tools/tests/` may contain these literals.

**Node lookup (D-16c):** `shutil.which("node")` -> `os.environ["NODE"]` -> newest of `glob(~/.nvm/versions/node/*/bin/node)` -> else `raise unittest.SkipTest("node not found: tried PATH, $NODE, ~/.nvm/versions/node/*/bin/node")`. No in-repo analog; use RESEARCH "Node harness" snippet (stdin JSON `{"script","params"}`, `vm.createContext` with stub `galago.command/note`, 5 s timeout, read `e.message` never `instanceof Error`). Run each script both as is and with `"use strict";` prepended. Params for the test = `{p["name"]: p.get("defaultValue","")}` from the JSON.

**Test list to cover** (from RESEARCH validation table): `export_shape`, `command_order` (note, STACK, FAST, STACK), key distinct/run-unique and <= 60 chars, return leg = swap, no operator-only command (`acknowledge_failure`), sim lab defaults, `throws` on blank/non-integer with zero commands emitted, FAST step passes `tools.fast.server._check_args` (skip if `fast_mcp` missing, `fast_test.py:72` style), then the D-06 replay class.

**Verification gate:** run with `PATH=$HOME/.nvm/versions/node/v24.14.1/bin:$PATH` and `pytest -rs tools/tests/gal02_handoff_test.py`, requiring 0 skipped; full suite baseline 510 passed.

---

### `docs/runbooks/gal-02-handoff.protocol.json` (config, transform)

**No in-repo analog.** Format authority: `/home/formulatrix/data/nikko/galago-core/docs/script-protocols.md` § Import / Export. Shape:
```json
{"protocol": {"name": "...", "category": "...", "description": "...", "mode": "script",
  "scriptContent": "<JS string>", "parameters": [ {"name","label","type","defaultValue":"<string>","required":true,"options":[...],"description":"..."} ],
  "commands": []},
 "exportedAt": "<ISO>", "version": "1.0"}
```
Content source: RESEARCH.md "Protocol script" block (lines 251-317) and the parameter table (lines 320-339). Rules to apply:
- `defaultValue` must be a string. `type` in string|number|boolean|select (`fast_step_tip_reuse` is select with `["fresh","reuse"]`).
- F.A.S.T. params use the `fast_step_` prefix (D-13). STACK names stay as D-04 plus `*_deck` (D-14).
- Generate the file with `json.dumps(..., indent=2)` from the script text (single source of truth); the test loads `scriptContent` from the file. Do not hand-escape.
- Optional keys omitted when blank; numbers emitted via `Number()`; `label.slice(0, 20)` keeps keys <= 58 chars.
- Script throws on blank required input before the first `galago.command` (build all three param objects first).
- Defaults only in `parameters[].defaultValue`, not in script fallbacks.

---

### `docs/runbooks/gal-02-handoff.md` (runbook, operator procedure)

**Analog 1 (shape):** `/home/formulatrix/data/nikko/fast/fast-mcp/docs/runbooks/phase5-galago-live-run.md`
- Heading skeleton (line numbers from that file): intro safety statement (:1-13), `## Deployment rules` (:15), `## Part A — Simulated workcell run` (:29) with numbered steps and fenced bash, `## Part B ...` with `### Pre-run checklist`, `### Step N`, `### Evidence and teardown`, `## If something goes wrong` (:243), `## Known limitations` (:271), `## Evidence` table (:288), `## Findings` (:307), Finding F5 (:495-530; relevant to forced re-dispatch).
- Step-1 style command block to copy:
```bash
cd /home/formulatrix/data/nikko/galago-tools
FAST_MCP_LOCK_DIR=<an empty directory> \
  /home/formulatrix/data/nikko/.venvs/galago-py310/bin/python -m tools.fast.server --port=4010
```
  For STACK use `python -m tools.stack.server --port=<p>` with `STACK_USER`/`STACK_PASSWORD` (sim account) in the env.
- Evidence table columns: `| Row | UTC timestamp | Observation | Result |` (:288-306). Use rows for run id, keys, replies, sim counters. Mirror this for the D-12 Findings log.
- Known galago-core dev conventions in that runbook: separate compose project (`-p galago-gal06`), alt UI port (3020), `extra_hosts: host.docker.internal:host-gateway`, firewall blocks container->host on some ports (use 40000/11010-range ports that are reachable). Never touch production `galago-web` (:3010).

**Analog 2 (sim safety):** `/home/formulatrix/data/nikko/stack-automation-layer/docs/runbooks/stack-validation.md` Part A: A.0 safety rules (:18), A.1 build/start (:66), A.3 mode and recovery (:166), A.4 sim lab names (:228), A.7 what the sim does not prove (:413), A.10 operator teardown (:490). Reference by section; do not copy. The runbook must say the executor never starts Docker/sim/run.

**Required content beyond the analogs (from CONTEXT/RESEARCH):**
- Import via `jq .protocol docs/runbooks/gal-02-handoff.protocol.json | curl -sS -X POST http://localhost:<UI port>/api/protocols -H 'content-type: application/json' --data @-`, not the Import button (D-16a); post-import check: Mode Script, Preview shows 4 rows.
- DEP-02 precondition block (RESEARCH lines 403-416, a read-only bash block, fails today by design). Part 2 stops `blocking-human` when it prints BLOCKED.
- Separate STACK tool-server processes/instances for sim and real (`base_server.py:98-101`, D-16b).
- Absolute `ledger_dir` (no `~`), pinned after first Transfer; sim port via `STACK_SIM_PORT`, never 5005 (taken by `scoringservice`) and never 5006; refuse `10.150.1.125` / `stack-server`; confirm `sim-` robots via `GetRobotStates`.
- Expected durations: STACK sim 35 s per step, F.A.S.T. sim 80 s, whole run ~150 s.
- What the simulated re-dispatch does and does NOT prove (D-07); no-second-POST evidence calibration and fallbacks (D-16d); re-send must be from the tool page with the same stored params (Pitfall 12); second re-send after 600 s expects the refusal line.

---

## Shared Patterns

### Fixture isolation (never touch real ledger/state)
**Source:** `tools/tests/stack_test.py:121-156` (`_StackTestCase.setUp`)
**Apply to:** `gal02_handoff_test.py` (inherited automatically via `_TransferTestCase`). It patches `HOME`, `XDG_STATE_HOME`, `STACK_STATE_DIR`, `STACK_MCP_LOCK_DIR`, sets fake `STACK_USER`/`STACK_PASSWORD`, strips proxy env, and guards `socket.connect` to loopback only (`_loopback_guard`, :110-118). Do not add a second isolation scheme.

### Skip with a stated reason, never silently green
**Source:** `tools/tests/stack_test.py:61-83` and `tools/tests/fast_test.py:72`
**Apply to:** missing core import (module level `raise unittest.SkipTest(...)`) and missing node (same call, reason names all three lookup places).

### Real-mode StackServer replay semantics (frozen, only proven here)
**Source:** `tools/stack/server.py` `_check_args` (:454-457: `step_key` non-blank), replay meta (:671-674, :1112-1113), `REPLAY_WINDOW_S = 600`, simulated mode returns no meta and writes no ledger (`base_server.py:138-145`).
**Apply to:** D-06 assertions. No adapter edits (Phase 6 is read-only against `tools/stack/*.py`).

### Hardware deny-set
**Source:** values at `tools/tests/stack_test.py:532,1193`; upstream guards `stack-automation-layer/tests/netguard.py:24-26`, `tests/sim_support.py:46-48`
**Apply to:** the test fixture and the runbook preflight step.

### Verification gate
`bin/make proto test` on `~/data/nikko/.venvs/galago-py310`; baseline 510 passed (about 11 s). Re-run after adding the module and confirm the new module reports 0 skipped with node on PATH.

## No Analog Found

| File | Role | Data Flow | Reason |
|---|---|---|---|
| `docs/runbooks/gal-02-handoff.protocol.json` | config | transform | No protocol JSON in this repo; use galago-core's export format doc plus the RESEARCH-prototyped script |
| node harness (inline in the test) | utility | subprocess transform | No test in the repo shells out to node; use the RESEARCH snippet |
| DEP-02 precondition script | utility | read-only check | No existing check script; use the RESEARCH block, embedded in the runbook as a fenced code block |

## Metadata

**Analog search scope:** `tools/tests/`, `docs/`, sibling runbooks (fast-mcp, stack-automation-layer), RESEARCH.md prototypes
**Files scanned:** about 8 (stack_test.py and fast_test.py by targeted ranges)
**Pattern extraction date:** 2026-11-02
