# Project Research Summary

**Project:** galago-tools (nikkopg fork) — milestone v2: STACK Tool & STACK↔F.A.S.T. Handoff
**Domain:** Galago gRPC tool adapter for a plate-mover arm, plus a two-instrument handoff workflow
**Researched:** 2026-10-28
**Confidence:** HIGH on integration points and core behaviour (read from code); MEDIUM on the galago-core workflow/step-key design (code-read inference, not run)
**Mode:** Targeted (v2 deltas only; `tools/fast/` is the template and is not re-researched)

Pinned sources read: galago-tools `feat/stack-tool`; stack-automation-layer `origin/feat/initial-layer` =
`ed8ce478d8881a517eb93ed233707f81aea01238` (on GitLab: `git branch -r --contains ed8ce47` →
`origin/feat/initial-layer`); galago-core `main` (= `feat/fast-tool`, `e0a4f2b`). Citations:
`SAL:path:line` = `git show origin/feat/initial-layer:path` in stack-automation-layer; `GC:path:line` =
galago-core; bare paths = this repo. **[V]** verified by reading the code, **[I]** inferred.

> Saved by the orchestrator from the researcher's returned content (the subagent's own Write was
> blocked by the harness).

---

## Executive Summary

**1. A STACK tool type is mechanical but spans two repos.** The F.A.S.T. precedent gives the exact
checklist. In this repo (`2001231` + `3df5ed9`): new `<tool>.proto`, two oneof entries in
`tool_base.proto`, one enum value in `controller.proto`, `tools/<tool>/{__init__,server,requirements}.*`,
a mypy override and a test module. In galago-core (`GC` commit `128bbd7`): submodule bump, ts-proto
1.151.1 regen of `gen-interfaces`, and a `commandFields` entry. The galago-core half is not optional:
galago-core builds the gRPC payload as `{[toolType]: {[command]: params}}` (GC:controller/server/tools.ts:359-365)
with the generated ts-proto types, so it cannot send a `stack` command until they are regenerated.
**[V]** for the payload, **[I]** for ts-proto dropping an unknown key.

**2. The core fits the decided single-command Transfer, but the adapter must own the step-key ledger
carefully.** `plan_transfer` (one estimation POST, fresh device read; SAL:stack_automation_layer/service.py:610-641)
→ `execute_transfer` (pops the single-use plan, re-runs full `start_transfer` gates; :643-675, :966-1046)
→ `wait(handle, timeout_s=…)`. `wait` has **no** 300 s clamp; only `wait_transfer(guid)` clamps to
`WAIT_TRANSFER_MAX_S = 300` (:191-192, :705-706). The latch, the `_started` ownership map and the
`_inflight` guard all live in memory (:300-318). After a tool-server restart a re-attached guid is
**foreign**: its failure never latches (:1682-1688) and it never re-enters `_inflight`. This is the most
important core gap (G1).

**3. galago-core sends no per-run or per-step identifier to tools [V].** It does offer a clean place to
mint one: **script-mode protocols run once at queue time in a sandbox with `Date` and `Math`**
(GC:docs/script-protocols.md:12-20, 253-265; GC:controller/server/scripting/protocol-script-executor.ts:71,78,91),
and their output is stored as the queued commands. A script can mint a per-run key
(`"<batch>-" + new Date().toISOString() + "-in"`) that stays stable across F5 re-dispatch and
retry-after-failure (failed rows stay queued and `startNext` re-picks them:
GC:controller/server/utils/SqliteQueue.ts:112-150, 500-508) yet is unique per run. GAL-02 is therefore
**pure workflow config plus tool configs**, with no galago-core code change beyond GAL-01's codegen and
`commandFields`. The main hazard is a **step key reused across runs**: the adapter would replay SUCCESS
while the plate sits elsewhere. Mitigate with run-unique keys from the script plus adapter rules
(Pitfall 1).

**4. Simulation has two distinct levels.** Galago "simulated" mode: `Configure(simulated=true)` never
calls `_configure`, sleeps `Estimate<Cmd>` and returns SUCCESS (base_server.py:104-107, 138-145). No
core, no ledger, no STACK contact; enough for a simulated GAL-02 workcell run. The PAC simulator
(runbook Part A) *can* back a non-hardware, real-mode STACK run from Galago, but only with the tool
server on the same host (the sim publishes on loopback only) and the sim account's
`STACK_USER`/`STACK_PASSWORD` in the galago-tools process environment, using the sim lab names. The
core's sim/hardware guards are in `tests/`, not the shipped package, so inside Galago the configured host
is the **only** thing that selects sim or hardware.

---

## Key Findings

### Q1. What a new tool type needs (galago-tools), following F.A.S.T.

| # | File | New/Mod | What | Evidence |
|---|------|---------|------|----------|
| 1 | `interfaces/tools/grpc_interfaces/stack.proto` | NEW | `package com.science.foundry.tools.grpc_interfaces.stack;` with `Command` (oneof `command`) and `Config` | fast.proto:1-104 pattern; `2001231` |
| 2 | `interfaces/tools/grpc_interfaces/tool_base.proto` | MOD | `import "tools/grpc_interfaces/stack.proto";` + `tools.grpc_interfaces.stack.Command stack = 24;` in `Command.tool_command` + `tools.grpc_interfaces.stack.Config stack = 43;` in `Config.config` | tool_base.proto:28 (import), :54 (`fast = 23`), :84 (`fast = 42`) **[V]** |
| 3 | `interfaces/controller.proto` | MOD | `stack = 24;` in `enum ToolType` | controller.proto:30 (`fast = 23`) **[V]** |
| 4 | `tools/stack/__init__.py` | NEW | empty; `find_tool_packages()` ships any dir with `__init__.py` | setup.py:104-117 **[V]** |
| 5 | `tools/stack/server.py` | NEW | `StackServer(ToolServer)`, `toolType = "stack"`, `__main__` with `--port`; launched as `python -m tools.stack.server --port=N` | utils.py:30-31; fast server.py:1008-1015 **[V]** |
| 6 | `tools/stack/requirements.txt` | NEW | `stack-automation-layer @ git+https://gitlab.formulatrix.com/nikkopg/stack-automation-layer.git@ed8ce478d8881a517eb93ed233707f81aea01238`, no `[mcp]` extra; `bin/make deps` installs every `tools/*/requirements.txt` | tools/fast/requirements.txt:5; bin/make `deps()` **[V]** |
| 7 | `pyproject.toml` | MOD | mypy override `module = ["stack_automation_layer", "stack_automation_layer.*"]` (core ships no `py.typed`) | pyproject.toml:31-34 **[V]** |
| 8 | `tools/tests/stack_test.py` | NEW | mirror fast_test.py: skip if core missing, oneof registration tests, requirements pin test, `MagicMock(spec=StackService)` mapping table, gRPC in-process Configure round trip against a closed port | fast_test.py:20-80, 2660-2664, 3509 **[V]** |
| 9 | `tools/tool_images/stack.png` | NEW (optional) | web manager serves `f"{tool.type}.png"`; fast has none either | tools/web_server.py:303, 852 **[V]** |

Generated `*_pb2*.py[i]` are gitignored (.gitignore:1-2); `bin/make proto` regenerates them. Gate:
`bin/make proto test` (ruff, mypy, `unittest discover`, pytest) on the 3.10 venv. **[V]** The core
requires Python `>=3.10` and depends only on `httpx>=0.27,<1` (SAL:pyproject.toml). **[V]**

**galago-core side, needed for GAL-01 to be usable (precedent `GC` commit `128bbd7`, 8 files):** bump
`vendor/galago-tools`; `bin/make proto_ts` with **ts-proto 1.151.1**, `snakeToCamel=false`
(GC:bin/make:58-69), regenerating `gen-interfaces/controller.ts`, `tools/grpc_interfaces/tool_base.ts`
and new `stack.ts`; add `commandFields.stack` in GC:controller/components/tools/constants.ts (fast at
:314-343). Command keys are the snake_case oneof field names; use `text` fields with no `defaultValue`
for every required string (F.A.S.T. precedent: an untouched boolean is saved as `false`, a `select`
pre-fills a value). `commandFields` feeds both the tool page (GC:controller/pages/tools/[id].tsx) and the
protocol builder (GC:controller/components/protocols/AddToolCommandModal.tsx). **[V]**

**Method-name collisions (must avoid) [V]:** `base_server._dispatchCommand` resolves the handler as
`getattr(self, command.__class__.__name__)` (base_server.py:129-131); the estimate hook is
`Estimate<ClassName>` (:258-266); the servicer RPCs are `GetStatus`, `ExecuteCommand`,
`EstimateDuration`, `Configure` (tool_driver.proto). A command message must **not** be named `GetStatus`
(fast needed an arity hack, fast server.py:777), `EstimateDuration`, `Configure`, `ExecuteCommand`, or
anything starting with `Estimate` (`EstimateTransfer` would hijack `Transfer`'s estimate hook). The
decided "EstimateDuration" command therefore needs another name; this document uses
`GetTransferEstimate`.

**How results travel back [V]:** fast's `_reply(code, message=…, meta=dict)` builds a
`google.protobuf.Struct` via `Struct.update(meta)` into `ExecuteCommandReply.meta_data` and always sets
`return_reply=True` (fast server.py:273-282; tool_base.proto:111-116). Carry `result.to_dict()` unchanged
(contract v1, SAL:stack_automation_layer/results.py:64). Caveat: Struct stores every number as a double
(`errorCode`, `estimatedS`, `httpStatus`). **A SUCCESS reply must have an empty `error_message`**:
galago-core throws on SUCCESS plus a message (GC:controller/server/tools.ts:635-645). **galago-core
discards `error_message` for `INVALID_ARGUMENTS` and `NOT_READY`** and substitutes a generic sentence;
only `ERROR_FROM_TOOL` and the default branch show the tool's text (GC:tools.ts:604-623). fast maps
`refused → NOT_READY` and `rejected/needsInput → INVALID_ARGUMENTS` (fast server.py:109-123); for the
STACK that would hide the latched guid and explanation the operator needs. **Recommendation:** every
non-`ran` core kind → `ERROR_FROM_TOOL`; `INVALID_ARGUMENTS` only for adapter-side argument errors
(missing `step_key`, bad decision string).

**EstimateDuration semantics, two different things [V]:**
- **Galago's `EstimateDuration` RPC** calls the `Estimate<Cmd>` hooks. galago-core calls it **for every
  step at run creation**, with **unsubstituted** params (`{{var}}` resolves only at execute time)
  (GC:controller/server/runs.ts:183-207; GC:tools.ts:408-436, 650-659). It goes through `parseCommand`,
  so it returns NOT_READY while the tool is BUSY (base_server.py:203, 271-275), and it is the
  simulated-mode sleep (:138-145). The hooks must be local constants: no I/O, never raising (fast's D-16,
  fast server.py:960-1005).
- **The `GetTransferEstimate` command** calls `service.estimate_transfer(request)`: a fresh device-tree
  read plus one estimation POST, nothing moves (SAL:service.py:561-608). Returns
  `Estimated{estimatedTime, guid, advisories, seconds?}` (results.py:463-519). Estimates are conservative
  (~2.3x on the simulator, runbook A.8; ~1.7x on hardware, PROJECT.md Context). Simulator real elapsed
  17-21 s (runbook A9) is a reasonable basis for the `EstimateTransfer` constant.

### Q2. Core behaviours the adapter must handle

**Result kinds per call [V]:**

| Call | Can return | Notes |
|------|------------|-------|
| `plan_transfer(req)` | `TransferPlan` · `Rejected` · `NeedsInput` · `ReadFailed` · `Refused(failureLatched)` | Latch checked first with zero reads (service.py:629-632). Nothing moves. A non-plan result stores nothing. |
| `execute_transfer(plan_id)` | `TaskHandle` · `Refused(planNotFound/planExpired/failureLatched/inFlight/managerNotAutomated/recoveryPending/robotNotIdle/stackBusy)` · `Rejected(validate/instrument)` · `NeedsInput` · `ReadFailed` · `Lost(submitOutcomeUnknown)` | Plan TTL 600 s, single-use (:185, :666-675). Gates under `_submit_lock`; exactly one POST, never retried (:1008-1044). |
| `wait(handle, timeout_s, on_progress=, cancel=)` | `Ran` · `Failed` · `Aborted` · `TimedOut` · `Lost(pollFailed/taskNotFound)` · `Cancelled` · `NeedsInput` | No clamp; default 600 s (:162, :1719-1767). Never sends anything to STACK; `cancel` only stops the wait (results.py:917-951). |
| `wait_transfer(guid, timeout_s)` | as `_reattach`, **including `Failed`/`Aborted`** despite the narrower annotation (:716-718 vs :677-679) | Clamped to 300 s (:705-706). A non-guid string such as `submit-…` → `NeedsInput(["guid"])` (:1629-1630). |
| `acknowledge_failure(guid, confirm=True)` | `FailureAcknowledged` · `Refused(nothingLatched/guidMismatch/recoveryPending)` · `NeedsInput(["guid","confirm"])` · `ReadFailed` | Clears only on exact guid match, `confirm is True`, and a fresh manager-state read showing automated/manual with no recovery options (:1140-1221). |
| reads | `ManagerState` / `DeviceTree` / `RobotStates` / `LabwareProfiles` / `LabwarePresence`, or `ReadFailed` | `devices`/`labware_profiles` take `refresh=` (:389-436); presence failures always say "labware presence unavailable" (:96, :438-463). |

**Field mapping [V]:** `Transfer.robot` → `TransferRequest.robot`; `labware_profile` →
`.labware_profile`; `source_{device,deck,nest}` + `source_transfer_profile` →
`.source = Location(device, deck, nest, transfer_profile)`; `destination_*` likewise. `transfer_profile`
is optional; `to_wire_v2` emits `transferProfileName` only when non-blank
(SAL:stack_automation_layer/model.py:21-42, 70-90). This is exactly what the MCP adapter's
`_transfer_request` builds (SAL:stack_automation_layer/mcp/server.py:67-97). Pass blank proto fields as
`None` and let the core's `missing_fields` produce `NeedsInput` (model.py:50-67); the adapter must not
duplicate completeness rules. `AcknowledgeFailure.guid` → `acknowledge_failure(guid, confirm=True)` only
when `arm_inspected == "yes"` exactly; any other or blank value → adapter `INVALID_ARGUMENTS`, no core
call (fast's fail-closed `"yes"`/`"no"`). `GetLabwarePresence.robot` → `labware_presence(robot)`.
`ListDevices.refresh` / `ListLabwareProfiles.refresh` → `refresh=`. `TransferRequest` has **no** timeout
or step key; both are adapter-only.

**Waits and timeouts [V]:** in the original process, `service.wait(handle, timeout_s=T)` with the
`TaskHandle` from `execute_transfer` (no 300 s ceiling). To re-attach after a restart, either
`service.wait(TaskHandle.from_dict(saved_handle_dict), timeout_s=T)` (round-trip by design,
results.py:647-690) or a read-only loop of `wait_transfer(guid)` in ≤300 s slices. Neither stops or
re-sends motion.

**`TimedOut` [V]:** leaves the guid in `_inflight` (`_task_ended` false: service.py:1590-1603,
1714-1716), so every other Transfer is `Refused(inFlight)` until somebody waits that guid to terminal
(:1269-1270). That makes "operator re-runs the same step" the natural recovery: same `step_key` → ledger
→ re-attach → `Ran` → SUCCESS.

**`Lost(submitOutcomeUnknown)` [V]:** `handle = None`, so the ledger has **no guid** for that key. The
core mints a latch id `submit-<16 hex>` and latches on it, non-terminal (service.py:1353-1421; id at
:1404). That id is in no structured field of the `Lost` dict (golden
SAL:tests/golden/lost-submitOutcomeUnknown.json: `handle: null`, `detail` = robot/mode/recovery/robotState).
It appears only in the free-text `explanation` ("…acknowledge_failure with guid {id} and confirm=True",
results.py:1131-1140) and later in any `Refused(failureLatched).detail.guid` (service.py:1120-1124). The
ledger must record the key as `outcomeUnknown` permanently: never resubmit, never re-attach.

**Latch [V]:** first failure wins. `failed`, `aborted`, `lost` (any reason) and `cancelRequested` latch
(service.py:1048-1093). The latch blocks `plan_transfer` and `start_transfer` with zero reads and is
re-checked under the submit lock (:1126-1138, :1264-1268). Only an **owned** guid (in `_started`)
latches (:1682-1688).

**Thread safety [V]:** `StackService` uses `_lock` (knowledge), `_submit_lock` (gates + POST) and
`_state_lock` (registries + latch) (service.py:285-318), so it is safe from several gRPC worker threads;
`serve()` uses a 10-worker pool (base_server.py:296-297). Galago-side catch: base `ExecuteCommand` sets
BUSY for the whole command and `parseCommand` refuses everything unless READY (base_server.py:203, 240,
254). Reads from the tool page during a multi-minute Transfer get NOT_READY unless the adapter adds a
fast-style `ExecuteCommand` override for reads (fast server.py:515-544). A requirements decision, not a
must.

**Tool-server restart [V]:**

| What | Where | Effect of restart |
|------|-------|-------------------|
| Ledger | adapter file | survives, by design |
| `_plans` | core memory | lost; fine, plans never span commands |
| `_started`, `_inflight` | core memory | lost; a re-attached guid is neither owned nor in-flight-guarded |
| `_latch`, `_acknowledged` | core memory | **lost; a failure is silently cleared by the restart.** The runbook forbids clearing a failure this way (SAL:docs/runbooks/stack-validation.md:536-538); `FailureAcknowledged`'s docstring documents it as a limitation (results.py:760-786) |
| Owner lock | OS advisory lock | released when the process dies (SAL:stack_automation_layer/owner_lock.py:1-24) |

The galago-tools manager page can restart a single tool server without a service restart (PROJECT.md
Context), so this path is far more likely under Galago than under stack-mcp.

**Ownership [V]:** `open_service(host, port=5005, *, owner, lock_dir=None, transport=None)`
(SAL:stack_automation_layer/composition.py:137-180) reads credentials only from
`STACK_USER`/`STACK_PASSWORD` (SAL:stack_automation_layer/transport.py:83-89) and runs an anonymous
identity probe requiring `productName == "Stack manager"` (composition.py:37, 115-119). stack-mcp calls
`open_service(host, port, owner="mcp")` with **no `lock_dir`** (SAL:stack_automation_layer/mcp/__main__.py:44-60),
so the lock dir comes from `STACK_MCP_LOCK_DIR` or the per-user temp default (owner_lock.py:42-47).
**Do not add a `lock_dir` Config field**: an explicit dir that differs from stack-mcp's environment would
let both front ends own the arm at once. `endpoint_key` lives in `owner_lock` (owner_lock.py:50-59);
`composition` does not re-export it (`__all__`, composition.py:29); compare against
`OwnedService.endpoint` instead.

### Q3. galago-core: two-tool sequencing, step params, IDs, F5

- **Protocol formats [V]:** visual (`protocols.commands` JSON array of
  `{toolId, toolType, command, params, label, advancedParameters}`; GC:controller/db/schema/index.ts:204-216;
  GC:runs.ts:96-113) or script (JS run at queue time; `galago.command(toolId, command, params)` resolves
  the tool type by tool name; GC:docs/script-protocols.md:104-126; GC:runs.ts:69-89). Import/export JSON:
  GC:docs/script-protocols.md:276-306. No protocol examples in the repo (`GC:examples/` holds only
  Python helpers).
- **Sequencing [V]:** one busy loop, strictly in order: `startNext` → `executeCommand` (awaited gRPC, no
  deadline) → `complete` (GC:controller/server/command_queue.ts:943-1309, 486-489). STACK → F.A.S.T. →
  STACK is three consecutive commands for different `toolId`s. `advancedParameters.runAsynchronously`
  exists in UI/types but the queue never reads it.
- **Params to the tool [V]:** payload `{[toolType]: {[command]: params}}` (GC:tools.ts:359-365);
  whole-value `{{var}}` substitution at execute time (:408-436); protocol parameters are upserted as
  workcell variables at run start (GC:runs.ts:120-150); `variable_assignment` supports `${var}`
  concatenation but the target variable must already exist (GC:command_queue.ts:305-400, 1231-1280).
- **Identifiers [V]:** `queueId`/`runId` exist only inside the queue (`attempt` snapshot,
  GC:command_queue.ts:1297-1300). **Nothing reaches the tool.** Script mode can mint per-run keys
  (`Date`/`Math` in the sandbox: GC:protocol-script-executor.ts:71,78); they become stored params, stable
  across re-dispatch.
- **F5 evidence [V]:** fast-mcp runbook "Finding F5"
  (/home/formulatrix/data/nikko/fast/fast-mcp/docs/runbooks/phase5-galago-live-run.md:495-530; row R4 at
  :489): one queued `transfer` executed three times **back to back, each after a successful
  completion** (08:13:04, 08:13:54, 08:14:52Z), in Run 1 under Next.js dev mode. Hypothesis
  (unconfirmed): dev-mode re-instantiation of the busy loop re-picked a retired row
  (`SqliteQueue.complete` deletes the queue row: GC:SqliteQueue.ts:450-461). galago-core's `.planning`
  lists F5 as out-of-scope debt (GC:.planning/PROJECT.md:68; GC:.planning/research/PITFALLS.md:391). A
  second, **by-design** re-dispatch path also exists: a failed step stays queued (`fail` only sets status:
  GC:SqliteQueue.ts:500-508), so the next queue start re-executes it ("any other failure keeps upstream
  retry", GC:command_queue.ts:1323-1326). The ledger must cover both: F5 (repeat after success) and
  retry-after-failure (repeat after an error).
- **GAL-02 verdict:** no galago-core code change beyond GAL-01's codegen + `commandFields`. Author GAL-02
  as a **script-mode protocol**: parameters (plate/batch label, STACK nest triples so sim and hardware
  names both work); mint per-run `step_key`s; emit STACK `transfer` (in), F.A.S.T. `transfer`, STACK
  `transfer` (out). Tool configs: STACK `{host, port}`, F.A.S.T. `{host, port, …}`. Tool **instances**
  are workcell records in galago-core's DB (ip/port + Config): a config action, not code.

### Q4. Simulated runs

- **Galago-simulated (both tools) [V]:** `simulated=true` → base returns SUCCESS without `_configure`
  (base_server.py:104-107); every command sleeps `Estimate<Cmd>` and returns SUCCESS with no meta
  (:138-145); fast adds argument checks and a run-state record (fast server.py:472-514). The STACK
  adapter should validate arguments (including `step_key`) and use constant estimates. **No ledger writes
  in simulated mode**, so a sim run cannot poison real keys. Base quirk: switching simulated → real
  returns SUCCESS **without** calling `_configure` (base_server.py:98-101), leaving the tool not ready;
  reconfigure or restart after leaving sim.
- **PAC-simulator-backed STACK (real mode against the sim)** [V facts, I end-to-end]: the sim manager
  publishes only on `127.0.0.1:5005`, operator-built and started with Docker (runbook A.0, A.1). The
  galago-tools tool server must run on that host with `STACK_USER`/`STACK_PASSWORD` = the **sim account**
  in its process environment. Credentials are process-global (transport.py:83-89), so switching sim ↔
  hardware means restarting the galago-tools service with different env values. The identity probe
  passes (same product name, composition.py:37); the `galago` owner is allowed (owner_lock.py:35). Sim
  lab: robot `sim-arm-1`, nests `sim-A1`/`sim-B1` on `sim-nest-a/b`, profile `greiner 96 white` (runbook
  A4). Mode/recovery are operator REST calls (A.3). The sim models no plate presence, e-stop or real
  grip (A.7). The **sim/hardware guards** (`resolve_sim_target`, netguard deny-sets for
  `10.150.1.125`/`stack-server`) live in SAL:tests/sim_support.py:48-51,101 and SAL:tests/netguard.py:24-25,
  not in the shipped package (pyproject `packages.find include = ["stack_automation_layer*"]`). A Galago
  sim run is hardware-safe only because of the configured host: put a hardware-host refusal in the
  galago-tools **test** fixtures and the runbook step, not in adapter runtime policy. The F.A.S.T. has no
  simulator in scope, so a "simulated workcell run" is either fully Galago-simulated, or STACK-on-PAC-sim
  with the F.A.S.T. Galago-simulated.

### Critical Pitfalls

1. **A step key reused across runs replays SUCCESS without moving** (no run id reaches tools; a visual
   protocol with a literal key repeats it every run). Prevention: mint keys per run in a script-mode
   protocol; the ledger stores a request fingerprint, and a repeat key with a different request →
   `INVALID_ARGUMENTS`, no I/O; consider a replay window (a key whose `ran` record is older than N minutes
   is refused rather than replayed: an adapter idempotency policy, not an instrument rule). F5's real
   repeats arrived within ~1 s of completion (fast-mcp runbook :503-507).
2. **Crash window between the POST and the ledger write.** Write a **write-ahead** `submitting` record
   (fsync + atomic `os.replace`) *after* `plan_transfer` succeeds and *before* `execute_transfer`. On a
   repeat, `submitting` with no guid = outcome unknown: refuse, never submit, send the operator to the
   STACK Manager. `execute_transfer` results that prove nothing was sent (`Refused`, `Rejected`,
   `NeedsInput`, `ReadFailed`) may release the key so a fixed step can re-run: the POST is reached only
   past every gate, and post-POST exceptions become `Lost` (service.py:1013-1022, 1045-1046).
3. **A restart clears the latch and ownership (G1).** Under Galago, a manager-page restart of the tool
   server silently un-latches a failed arm and orphans its in-flight task. In-scope mitigation: an
   operator rule in the runbook (as stack-mcp has) and a warning surfaced on Configure (log/STATUS). The
   real fix is in the core (G1); per PROJECT.md, a gap stops the work → `/gsd-quick` in
   stack-automation-layer.
4. **The operator can't see the guid to acknowledge.** galago-core hides `INVALID_ARGUMENTS`/`NOT_READY`
   text (GC:tools.ts:604-612), and F3 (run UI hides tool errors) is open. Map non-`ran` kinds to
   `ERROR_FROM_TOOL`, put the latch guid in the one-line message, and expose it on the tool page via a
   read (no clean core read exists: G2).
5. **"Operator-only" AcknowledgeFailure cannot be enforced in galago-core today.** `commandFields` also
   feeds the protocol builder, and script protocols can emit any command. The core's exact-guid +
   `confirm` requirement is the real guard (a protocol cannot know a future latched guid). Use `text`
   fields with no default (a `select` defaults to its first option). Decide whether to accept this or ask
   galago-core for a tool-page-only command list.

---

## Proposed stack.proto

```proto
syntax = 'proto3';

package com.science.foundry.tools.grpc_interfaces.stack;

// Every string is proto3 `optional` so an untouched galago-core field reaches
// the adapter as "unset" and the core's own completeness check names it
// (NeedsInput). Physical decisions are "yes"/"no" strings, never bools.
// Message names avoid the servicer RPC names (GetStatus, EstimateDuration,
// Configure, ExecuteCommand) and the Estimate<Cmd> hook prefix.
message Command {
  oneof command {
    Transfer transfer = 1;                         // plan -> execute -> wait, one step
    GetManagerState get_manager_state = 2;         // service.manager_state()
    GetRobotStates get_robot_states = 3;           // service.robot_states()
    ListDevices list_devices = 4;                  // service.devices(refresh=)
    ListLabwareProfiles list_labware_profiles = 5; // service.labware_profiles(refresh=)
    GetLabwarePresence get_labware_presence = 6;   // service.labware_presence(robot)
    GetTransferEstimate get_transfer_estimate = 7; // service.estimate_transfer(req); nothing moves
    AcknowledgeFailure acknowledge_failure = 8;    // operator only
  }

  message Transfer {
    // Adapter-only idempotency key: required, non-blank. A repeat key never
    // submits; it re-attaches to the recorded guid or replays the recorded
    // outcome. Must be unique per run (mint it in a script-mode protocol).
    optional string step_key = 1;
    optional string robot = 2;                         // TransferRequest.robot
    optional string labware_profile = 3;               // TransferRequest.labware_profile
    optional string source_device = 4;                 // source = Location(device,
    optional string source_deck = 5;                   //                   deck,
    optional string source_nest = 6;                   //                   nest,
    optional string source_transfer_profile = 7;       //                   transfer_profile)
    optional string destination_device = 8;           // destination = Location(...)
    optional string destination_deck = 9;
    optional string destination_nest = 10;
    optional string destination_transfer_profile = 11;
    // Adapter wait budget for service.wait(); unset/0 -> Config.transfer_timeout_s.
    // A timeout never stops the arm (core TimedOut); a re-run of the same step re-attaches.
    optional double timeout_s = 12;
  }

  message GetManagerState {}
  message GetRobotStates {}
  message ListDevices { optional bool refresh = 1; }
  message ListLabwareProfiles { optional bool refresh = 1; }
  message GetLabwarePresence { optional string robot = 1; }

  // Same request fields as Transfer, no step_key/timeout. Returns `estimated`
  // in meta_data. Distinct from Galago's EstimateDuration RPC, whose
  // Estimate<Cmd> hooks stay local constants (no I/O).
  message GetTransferEstimate {
    optional string robot = 1;
    optional string labware_profile = 2;
    optional string source_device = 3;
    optional string source_deck = 4;
    optional string source_nest = 5;
    optional string source_transfer_profile = 6;
    optional string destination_device = 7;
    optional string destination_deck = 8;
    optional string destination_nest = 9;
    optional string destination_transfer_profile = 10;
  }

  // acknowledge_failure(guid, confirm=True) only for arm_inspected == "yes"
  // (the operator inspected the arm and recovered STACK in the STACK Manager).
  // Unset or any other value -> INVALID_ARGUMENTS, no core call. guid is the
  // latched guid (a task guid, or "submit-<hex>" after an ambiguous submit).
  message AcknowledgeFailure {
    optional string guid = 1;
    optional string arm_inspected = 2;
  }
}

message Config {
  string host = 1;                // STACK manager host; must be the identical
                                  // string stack-mcp uses (owner-lock key)
  int32 port = 2;                 // 0 -> 5005
  double transfer_timeout_s = 3;  // default wait budget; 0 -> adapter default (e.g. 600)
  string ledger_dir = 4;          // step-key ledger dir; blank -> per-user state dir
  // Deliberately NO lock_dir: the lock dir comes from STACK_MCP_LOCK_DIR /
  // default, exactly as stack-mcp opens it, so both front ends always contend
  // on the same lock. Credentials only from STACK_USER/STACK_PASSWORD.
}
```

Registration: `tool_base.proto` gets `stack = 24` (Command) and `stack = 43` (Config);
`controller.proto` gets `stack = 24`.

Scope notes against the decided list: transfer profiles are a Transfer input, but `transfer_profiles()`
is not among the decided reads. Either add `ListTransferProfiles` (1:1 read, service.py:428-436) or drop
both `*_transfer_profile` fields from v2. `refresh()`/`refresh_devices()` are not exposed;
`devices(refresh=True)` covers them.

**Reply mapping (recommended):**

| Outcome | Reply |
|---------|-------|
| `ran` | `SUCCESS`, meta `ran` |
| read kinds, `estimated`, `failureAcknowledged` | `SUCCESS` |
| every other core kind (`rejected`, `needsInput`, `refused`, `readFailed`, `lost`, `failed`, `aborted`, `cancelled`, `timedOut`) | `ERROR_FROM_TOOL`, one-line message carrying the guid and reason, meta = `to_dict()` |
| adapter-side argument errors (missing `step_key`, bad `arm_inspected`, step key reused for a different request) | `INVALID_ARGUMENTS` |
| ledger repeat whose recorded outcome is `ran` | `SUCCESS`; meta is adapter-owned, so wrap it as `{result: <to_dict>, stepKey, replayed: true}` (outside the contract shape) |

---

## Core Gaps

Listed only; none fixed here. Per PROJECT.md a blocking gap stops the work and gets a `/gsd-quick` in
stack-automation-layer.

| ID | Gap | Evidence | Impact on adapter | Blocking? |
|----|-----|----------|-------------------|-----------|
| G1 | **Latch, ownership and in-flight guard do not survive a process restart**, and a guid re-attached after restart cannot be "adopted": `wait`/`wait_transfer` on a guid not in `_started` never latches, and nothing adds it to `_inflight` | service.py:300-318, 1026-1027, 1675-1688; results.py:760-786 (documented limitation); runbook :536-538 | After a Galago tool-server restart mid- or post-failure, the STACK accepts new motion with no acknowledge, and a re-attached failing transfer does not latch. The adapter cannot compensate without holding a safety rule (Core Value) | **Likely yes for live use**; at minimum an explicit decision |
| G2 | **No read of the current latch** (guid, kind, explanation). For `lost(submitOutcomeUnknown)` the minted `submit-<hex>` id is in no structured field, only in `explanation` | service.py:1404-1414, 1120-1138; golden `lost-submitOutcomeUnknown.json` (`handle: null`) | The operator needs the guid for AcknowledgeFailure. Workaround: `plan_transfer(TransferRequest())` returns `Refused(failureLatched, detail.guid)` with zero I/O when latched, else `NeedsInput` with zero I/O (service.py:629-632, 507-509); works but uses an allowlisted method for a side purpose | Soft (workaround) |
| G3 | **Ambiguous submit may leave the service unlatched**: `_set_latch` is inside the same `try` as the explanation build; if `explain_failure`/`failure_context` raises, `Lost` is returned with no latch | service.py:1397-1421 | Rare path where motion may be running but the next Transfer isn't latch-refused; only the robot-idle gate remains (and STACK queues a second submit) | Low likelihood; flag |
| G4 | `wait_transfer`'s return annotation omits `Failed`/`Aborted`, which `_reattach` returns | service.py:716-718 vs 677-679 | Adapter must map every kind regardless; mypy won't help | No (types/docs) |
| G5 | `explanation` text is written for an agent ("call acknowledge_failure with guid … and confirm=True") | results.py:1066-1140 | Galago operators see MCP wording; contract frozen, so the adapter composes its own one-line message from structured fields and relays the explanation in meta | No |
| G6 | Docstring conflict: `FailureAcknowledged` says acknowledging "never checks STACK state"; `acknowledge_failure` now reads manager-state and refuses `recoveryPending` | results.py:760-776 vs service.py:1165-1174 | Tests should pin behaviour (it reads), not the docstring | No |
| G7 | **No runtime sim/hardware guard in the shipped core**; guards are test-only | SAL:tests/sim_support.py:48-51, 101; SAL:tests/netguard.py:24-25; SAL:pyproject.toml packages | A PAC-sim Galago run is protected only by configured host + env credentials | No (process/runbook) |

---

## Addendum (2026-10-29): conclusions re-checked against core `934a621`

DEP-01 landed as `934a621ece116a8b263897c1e9b62b57374f4ef3` (`origin/feat/initial-layer`, pushed;
local clone `~/data/nikko/stack-automation-layer` on that commit). The claims below were checked against
`service.py`, `results.py`, `composition.py` and the new `state_store.py` at that SHA; the offline
870-test result is the core author's report, not re-run here. The fork pins it (`tools/stack/requirements.txt`,
`_PINNED_CORE_SHA` in `tools/tests/stack_test.py`, commit `237268c`) and the 3.10 venv runs it (gate: 267 passed).

| Gap | Status at `934a621` | What changed for the adapter |
|-----|--------------------|------------------------------|
| G1 | **Resolved, with two limits** | The latch, acknowledged guids, owned tasks (`_started`), the in-flight guard and cancel reservations are saved per manager endpoint (`StateStore(lock.key)`, the same key as `owner_lock.endpoint_key`, not per owner), so they survive a tool-server restart and a galago <-> mcp hand-over. `open_service` wires it with no new argument; the adapter's call is unchanged. A started guid still running after a restart stays in-flight-guarded and its failure latches when waited on. **Limit 1:** a process death after STACK accepts the POST but before the save loses that task's ownership: after restart it is foreign and its failure does not latch. **Limit 2:** a task that finished without a latch is foreign after a restart. |
| G2 | **Resolved** | `StackService.latch_status() -> LatchStatus`: zero STACK I/O, no disk access. `to_dict()` = `{"kind": "latchStatus", "latched", "guid", "resultKind", "reason", "explanation"}`. `guid` is what `acknowledge_failure` must name: a task guid, `submit-<hex>` (ambiguous submit), or `state-<hex>` (state file). The `plan_transfer(TransferRequest())` workaround is no longer needed. |
| G3 | **Resolved** | An ambiguous submit latches before it builds its explanation, so it can never be left unlatched. |
| G4 | **Resolved** | `wait_transfer` is annotated `Ran \| Failed \| Aborted \| TimedOut \| Lost \| NeedsInput`. |
| G5 | Unchanged | Explanations are still agent-worded; the adapter keeps composing its own one-line message (D-11). |
| G6 | **Resolved** | The `FailureAcknowledged` docstring now says `acknowledge_failure` reads manager state and can refuse `recoveryPending`. |
| G7 | Unchanged | Still no runtime sim/hardware guard in the shipped core. |

**New core behaviour the adapter and runbooks must respect:**
- **Fail closed on state.** An unreadable, corrupt or unknown-version state file starts the service
  latched (`resultKind` `stateUnreadable`, guid `state-<hex>`); a failed save leaves it latched
  (`stateUnsaved`). Only `acknowledge_failure(state-<hex>, confirm=True)` clears it. Loading never creates a
  file; saving is atomic (temp file, fsync, `os.replace`; dir 0700, file 0600).
- **Never delete the state file**: a missing file reads as a clean start, which would silently clear a latch.
- **Shared state needs a shared directory.** `$STACK_STATE_DIR`, else `$XDG_STATE_HOME/stack-automation-layer`
  (absolute only), else `~/.local/state/stack-automation-layer`. On forb01 the `galago-tools` service user
  and the stack-mcp user must be the same OS user, or both set the same `STACK_STATE_DIR`, or a hand-over
  does not share the latch. A hostname and an IP for the same manager are different keys (as with the lock).
- **Contract stays v1.** `latchStatus` is an additive kind with its own golden; `FROZEN_SHAPE_DIGEST` was
  re-pinned and every original shape still hashes to the frozen digest. No existing `to_dict()` changed.

**Conclusions that change:**
- Q2 "Tool-server restart" table: `_started`, `_inflight`, `_latch` and `_acknowledged` now **survive** a
  restart (persisted per endpoint). `_plans` are still lost (fine), and the owner lock is still released
  when the process dies.
- Pitfall 3 ("a restart clears the latch and ownership") is closed in the core. What remains is narrower: a
  restart **during** a transfer can lose that one task's ownership. Galago must treat a tool-server restart
  mid-transfer as "inspect the arm", never as a clean slate.
- Pitfall 4 (operator can't see the guid) is closed by `latch_status()`; `GetFailureLatch` binds 1:1 to it.
- `Lost(submitOutcomeUnknown)`: its `submit-<hex>` latch id is now readable via `latch_status().guid`.
- The adapter's Configure restart warning (D-09) said a restart clears the latch; it was corrected in
  `fe8aee8` to name the remaining limits.

**Phase 5 design inputs (to settle at plan time):**
- Add `latchStatus` to `_SUCCESS_KINDS` (it is a read) when `GetFailureLatch` is bound; extend the
  result-mapping test with it.
- Ledger re-attach after a restart: with persisted ownership, re-attaching to a recorded guid latches on
  failure as before — except under limit 1 (crash between POST acceptance and the core's save). The ledger's
  write-ahead `submitting` record covers the same window from the adapter side; whether a re-attach can tell
  a "foreign" guid apart (and should refuse SUCCESS-replay or force an arm-inspection message) is the open
  question for the Phase 5 design spike.
- `stateUnreadable` / `stateUnsaved` latches surface through the same `Refused(failureLatched)` path and
  `latch_status()`; the operator acknowledges them with the `state-<hex>` guid like any other.

## Implications for Roadmap

Phases continue at 4; GAL-01 first, GAL-02 after.

### Phase 4: STACK tool registration, reads and estimate (no motion path)
**Rationale:** proto + registration gate everything (including galago-core codegen). Reads plus
`GetTransferEstimate` exercise `open_service`, the owner lock, credentials and the reply/Struct mapping
with zero motion risk.
**Delivers:** `stack.proto` + registrations; `tools/stack/{__init__,server,requirements}`; `StackServer`
with `_configure` via `open_service(host, port, owner="galago")`; the six non-motion commands; constant
`Estimate<Cmd>` hooks; simulated mode with argument validation; mypy override; `stack_test.py`
(registration, pin, mapping table on `MagicMock(spec=StackService)`, closed-port Configure, owner-lock
contention); gate `bin/make proto test`.
**Cross-repo:** galago-core quick task (submodule bump, ts-proto 1.151.1 regen, `commandFields.stack`).
**Avoids:** method-name collisions, Struct/SUCCESS-with-message traps, `lock_dir` divergence.

### Phase 5: F5-safe Transfer + AcknowledgeFailure
**Rationale:** the only motion path and all the idempotency risk; build it after the plumbing is proven.
**Delivers:** `Transfer` = `plan_transfer` → write-ahead ledger → `execute_transfer` → record guid →
`wait(handle, T)` → record terminal outcome; repeat-key re-attach/replay/refuse; request fingerprint
check; persistent atomic ledger in `ledger_dir`; kind→reply mapping (non-`ran` → `ERROR_FROM_TOOL`);
non-blocking motion lock (fast D-13); `AcknowledgeFailure` with fail-closed `"yes"`; an invariant test
(no adapter path calls `cancel_transfer`, `go_to_safe_position` or `start_transfer`, and
`execute_transfer` at most once per key — mirrors the v1 no-auto-abort AST invariant); tests for F5
(repeat after `ran`), retry-after-failure, `TimedOut` re-attach, `submitOutcomeUnknown`, restart (new
`StackServer`, same ledger).
**Decide before planning:** G1 (stop and fix in core, or accept with a runbook rule), G2 (workaround or
core read), replay window + fingerprint rules, whether reads bypass the BUSY gate.

### Phase 6: Simulated workcell run + GAL-02 workflow
**Rationale:** prove the three-step sequence before any motion.
**Delivers:** GAL-02 script-mode protocol (per-run `step_key`s, nest-triple parameters); a fully
Galago-simulated STACK → F.A.S.T. → STACK run; optionally a STACK-on-PAC-simulator run on the sim host
(runbook Part A preconditions; F.A.S.T. simulated), including a forced F5-style re-dispatch check (re-run
the completed step: no second POST).
**Uses:** galago-core script protocols (no galago-core code), workcell tool records.

### Phase 7: Deploy, supervised live STACK run, live handoff
**Rationale:** same safe deploy order as v1 (core into service `.venv` → restart `galago-tools` →
rebuild `galago-web` with the new `stack` types); live motion only in a runbook-gated, supervised session
with stack-mcp closed (single owner).
**Delivers:** a supervised live Transfer to `ran`, then a live GAL-02 handoff, using the hardware facts
in PROJECT.md (`10.150.1.125:5005`, `stack2-6`, the listed nests).

### Phase Ordering Rationale
Registration and codegen gate every Galago-visible test; reads come before motion to prove ownership,
credentials and reply mapping; the ledger must exist before any workflow can be safely re-run; sim before
live.

### Research Flags
- Phase 5: short design spike on ledger semantics and the G1 decision (highest risk).
- Phase 6: check Docker + PAC sim build can run on the galago-tools host (loopback only).
- Phase 4: standard patterns (fast precedent); no further research.
- Phase 7: runbook authoring, not research.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Registration and file list | HIGH | fast commits, protos, setup.py, bin/make, galago-core `128bbd7` |
| Core behaviours and contract | HIGH | service.py, results.py, composition.py, owner_lock.py, model.py, mcp/server.py at the pinned SHA |
| galago-core sequencing, IDs, F5 | MEDIUM-HIGH | code paths read; F5 root cause an unconfirmed hypothesis (dev-mode re-instantiation); script-mode key stability inferred from store-then-replay code, not run |
| Simulation | MEDIUM | sim facts from the runbook; a Galago→PAC-sim run has never been done; depends on host Docker |

### Gaps to Address
- G1 and G2 decisions before Phase 5 planning.
- Whether ts-proto's generated `tool_base.Command.encode` silently drops an unregistered `stack` key
  **[I]**: confirm during the galago-core codegen task.
- Whether reads bypass the BUSY gate during a Transfer (needs a fast-style `ExecuteCommand` override).
- Whether `commandFields.stack.acknowledge_failure` is acceptable in the protocol builder, or galago-core
  needs a tool-page-only list.
- Expose `ListTransferProfiles`, or drop the per-location transfer-profile fields.
- Ledger retention, replay window value, default ledger path (per-user state dir, not tmp).
- The `Estimate<Cmd>` constant for Transfer (sim 17-21 s actual; hardware actual 30-32 s per runbook B3/B7).

## Sources

galago-tools (`feat/stack-tool`): interfaces/tools/grpc_interfaces/{fast,tool_base,tool_driver}.proto;
interfaces/controller.proto; tools/base_server.py:98-145, 195-294; tools/fast/server.py:109-123, 273-282,
472-563, 777, 960-1015; tools/fast/requirements.txt; tools/tests/fast_test.py:20-80, 2660, 3509;
setup.py:104-117; tools/utils.py:30-31; pyproject.toml:31-34; bin/make; .gitignore; commits `2001231`,
`3df5ed9`; .planning/PROJECT.md.

stack-automation-layer (`origin/feat/initial-layer` @ `ed8ce47`): stack_automation_layer/service.py
(lines inline); results.py:1-64, 101-182, 341-404, 463-1140; model.py:21-118; composition.py:1-180;
owner_lock.py:1-181; mcp/server.py:67-400; mcp/__main__.py:44-60; transport.py:83-89; pyproject.toml;
tests/golden/lost-submitOutcomeUnknown.json; tests/sim_support.py; tests/netguard.py;
docs/runbooks/stack-validation.md (A.0-A.9, B.0).

galago-core (`main` = `feat/fast-tool` @ `e0a4f2b`): controller/server/tools.ts:359-436, 598-659;
controller/server/command_queue.ts:305-400, 486-489, 943-1400; controller/server/utils/SqliteQueue.ts:112-150,
450-508; controller/server/runs.ts:65-225; controller/server/scripting/protocol-script-executor.ts;
controller/db/schema/index.ts:204-216; controller/components/tools/constants.ts:314-343;
controller/server/runControl.ts:35-60; docs/script-protocols.md; bin/make:58-69; commits `128bbd7`,
`d4c3c23`; .planning/PROJECT.md; .planning/research/{SUMMARY,PITFALLS}.md.

fast-mcp: docs/runbooks/phase5-galago-live-run.md:489, 495-530 (Finding F5);
.planning/milestones/v1-MILESTONE-AUDIT.md:30, 141.
