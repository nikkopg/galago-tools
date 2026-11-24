# Phase 4: STACK Tool Registration, Reads & Estimate - Context

**Gathered:** 2026-10-28
**Status:** Ready for planning
**Mode:** `--auto` (every gray area resolved with the recommended option; see `04-DISCUSSION-LOG.md`)

<domain>
## Phase Boundary

Register a `stack` tool type in galago-tools and ship `tools/stack/` so an operator can Configure it
(host/port, `galago` owner lock, env credentials), read instrument state (manager state, robot
states, devices, labware profiles, transfer profiles, labware presence) and get a transfer estimate,
all 1:1 onto the frozen stack-automation-layer core (contract v1, `ed8ce47`). Reads answer while
another command holds the tool BUSY. Simulated mode validates adapter arguments and sleeps constant
estimates.

`stack.proto` is **frozen for v2 in this phase**: it declares the whole v2 command surface, including
`Transfer`, `AcknowledgeFailure` and the latch-status read. In real mode those three are refused
until Phase 5. No real-mode code path in this phase can move the arm.

Not in this phase: the step-key ledger, any motion, acknowledge, the latch read implementation
(Phase 5, gated on DEP-01); galago-core codegen and forms (DEP-02); the GAL-02 workflow (Phase 6).

</domain>

<decisions>
## Implementation Decisions

### Frozen proto surface (STK-01, roadmap SC 6)
- **D-01:** `interfaces/tools/grpc_interfaces/stack.proto`, package
  `com.science.foundry.tools.grpc_interfaces.stack`, `Command` oneof `command` with exactly these ten
  entries, in this order:
  1. `Transfer transfer = 1`
  2. `GetManagerState get_manager_state = 2` → `service.manager_state()`
  3. `GetRobotStates get_robot_states = 3` → `service.robot_states()`
  4. `ListDevices list_devices = 4` → `service.devices(refresh=)`
  5. `ListLabwareProfiles list_labware_profiles = 5` → `service.labware_profiles(refresh=)`
  6. `ListTransferProfiles list_transfer_profiles = 6` → `service.transfer_profiles(refresh=)`
  7. `GetLabwarePresence get_labware_presence = 7` → `service.labware_presence(robot)`
  8. `GetTransferEstimate get_transfer_estimate = 8` → `service.estimate_transfer(request)`
  9. `AcknowledgeFailure acknowledge_failure = 9` (real mode refused until Phase 5)
  10. `GetFailureLatch get_failure_latch = 10` (latch-status read for ACK-02; real mode refused until
      Phase 5, where it binds to DEP-01's G2 core read)

  — **Reversibility:** one-way — galago-core's DEP-02 regenerates ts-proto types and builds
  `commandFields.stack` from this file once; any later v2 change re-opens DEP-02 and needs the
  user's sign-off (roadmap Phase 4 note, binding since 2026-10-28).
- **D-02:** `ListTransferProfiles` is added (STK-03 names transfer profiles as a read), so `Transfer`
  and `GetTransferEstimate` keep their per-location `*_transfer_profile` fields. Research left this
  open; STK-03 settles it.
- **D-03:** Message shapes follow `.planning/research/SUMMARY.md` § "Proposed stack.proto", with
  these fixes:
  - Every string field is proto3 `optional`, so an untouched galago-core field arrives unset. The
    adapter passes unset/blank instrument fields to the core as `None`, and the core's
    `missing_fields` produces `NeedsInput`. The adapter does not copy the core's completeness rules.
  - `Transfer`: `step_key` (1), `robot`, `labware_profile`, `source_{device,deck,nest,transfer_profile}`,
    `destination_{device,deck,nest,transfer_profile}`, `optional double timeout_s` (12).
  - `GetTransferEstimate`: the same request fields without `step_key`/`timeout_s`.
  - `ListDevices` / `ListLabwareProfiles` / `ListTransferProfiles`: `optional bool refresh = 1`.
  - `GetLabwarePresence`: `optional string robot = 1`.
  - `AcknowledgeFailure`: `optional string guid = 1`, `optional string arm_inspected = 2` (a
    `"yes"`/`"no"` string, never a bool).
  - `GetFailureLatch {}`: no fields. Its reply meta is whatever DEP-01's read returns, so a
    contract-version bump in DEP-01 changes meta, not the proto.
- **D-04:** `Config`: `string host = 1`, `int32 port = 2` (0 → 5005), `double transfer_timeout_s = 3`
  (0 → adapter default, used in Phase 5), `string ledger_dir = 4` (blank → per-user state dir,
  used in Phase 5). There is **no `lock_dir` field**. Phase 4 validates `transfer_timeout_s` (finite,
  >= 0) and stores `ledger_dir` but creates nothing on disk.
  — **Reversibility:** one-way — same DEP-02 freeze as D-01.
- **D-05:** No message is named `GetStatus`, `EstimateDuration`, `Configure`, `ExecuteCommand`, or
  starts with `Estimate`. `base_server` resolves handlers by class name and estimate hooks as
  `Estimate<ClassName>`.
- **D-06:** Registration: `tool_base.proto` imports `tools/grpc_interfaces/stack.proto`, adds
  Command `stack = 24` and Config `stack = 43`; `controller.proto` `ToolType` adds `stack = 24`.
  `bin/make proto test` must be green on the Python 3.10 venv.

### Configure and ownership (STK-02)
- **D-07:** `_configure` mirrors `FastServer._configure`:
  - `host` stripped and non-blank;
  - `port or 5005`;
  - validate `transfer_timeout_s`;
  - if the same `endpoint_key(host, port)` is already owned, return without reopening;
  - otherwise close the old `OwnedService` first, then
    `open_service(host, port, owner="galago")`, with no `lock_dir` argument.

  Credentials come only from `STACK_USER`/`STACK_PASSWORD` (the core reads them). Use the core's
  `endpoint_key` and `OwnedService.endpoint` for the comparison. The adapter applies no other host
  normalisation, so its owner-lock key matches stack-mcp's.
- **D-08:** Any failure in `open_service` propagates: `StackOwnedError` (its `str()` already names
  the holder), missing credentials, the identity probe, or a closed port. `base_server.Configure`
  then returns `NOT_READY` with `error_message=str(e)` and status FAILED. The adapter does not reword
  the holder text. A test proves a lock held by an `owner="mcp"` holder in a temp `STACK_MCP_LOCK_DIR`
  fails Configure, and that the reply names it.
- **D-09:** On a successful real-mode Configure, log one WARNING. It says that restarting this tool
  server clears the core's failure latch and in-flight guard (core gap G1), and that a failure must
  be acknowledged, not cleared by a restart. This is a log line, not a policy check.

### Reply mapping (STK-07)
- **D-10:** One `_reply(code, message="", meta=None)` helper, copied from fast. It always sets
  `return_reply=True` and fills `meta_data` from a Struct.
  - **Read kinds, `estimated`, `failureAcknowledged`, `ran`:** SUCCESS with an **empty** message
    (galago-core throws on SUCCESS plus a message). Meta is `result.to_dict()` unchanged, not
    wrapped.
  - **Any other core kind** (`readFailed`, `refused`, `rejected`, `needsInput`, `lost`, `failed`,
    `aborted`, `cancelled`, `timedOut`, and any kind the adapter does not recognise): returns
    `ERROR_FROM_TOOL` with meta = `to_dict()`.
  - **Adapter argument errors:** `INVALID_ARGUMENTS`.
  - **Not SUCCESS:** an unrecognised kind never becomes SUCCESS. The SUCCESS kinds are an explicit
    allowlist.
- **D-11:** The `ERROR_FROM_TOOL` message is a single line with no newline. It is built from
  structured fields, not from the core's agent-worded `explanation` (G5):
  - the kind;
  - the reason, when present;
  - the guid, when present, e.g. `"stack: refused (failureLatched), guid 3f2a…"`.

  The full `explanation` stays in meta. Exact wording is the planner's choice, within these rules.
- **D-12:** Map by the result's `kind` from `to_dict()` (or the result class) using one table. Map
  every kind, regardless of a method's narrower return annotation (G4). Struct turns numbers into
  doubles; accept this and don't convert back.

### Concurrency: reads while BUSY (STK-05)
- **D-13:** Use a fast-style `StackServer.ExecuteCommand` override with one module-level
  `READ_COMMANDS` frozenset. It contains `get_manager_state`, `get_robot_states`, `list_devices`,
  `list_labware_profiles`, `list_transfer_profiles`, `get_labware_presence`,
  `get_transfer_estimate` and `get_failure_latch`.

  A request with `WhichOneof("tool_command") == "stack"` whose inner command is in `READ_COMMANDS`:
  - skips `isReady`/`parseCommand`/`setStatus`;
  - goes through `self._dispatchCommand(command)`, so simulated mode and argument checks still
    apply;
  - turns an `Exception` into `DRIVER_ERROR` and sets `last_error`.

  Everything else returns `super().ExecuteCommand(...)` unchanged. Motion commands therefore stay
  serialised by base_server's BUSY gate. `tools/base_server.py` is not edited.
- **D-14:** In real mode, a bypass read with no configured service returns `NOT_READY` with
  "stack: not configured". It never reaches a `None` service.
- **D-15:** `GetTransferEstimate` is in the bypass set. It sends one estimation POST, never moves
  anything, and the core is thread-safe (three internal locks).
- **D-16:** Prove STK-05 with an injected slow command. Use real mode and a
  `MagicMock(spec=StackService)`. Block a non-read command inside its handler on a
  `threading.Event` (patch the `Transfer` handler, since real Transfer lands in Phase 5), so
  base_server holds BUSY. Then:
  - each read returns its result, not NOT_READY;
  - status stays BUSY;
  - a second non-read command gets NOT_READY;
  - after release, status returns to READY.

  Write the failing test first, as fast did (v1 D-04).

### Simulated mode and estimates (STK-06, STK-04)
- **D-17:** Simulated mode validates **adapter-owned arguments only**:
  - `Transfer.step_key` must be set and non-blank;
  - `Transfer.timeout_s`, if set, must be finite and >= 0;
  - `AcknowledgeFailure.guid` must be non-blank;
  - `AcknowledgeFailure.arm_inspected` must be exactly `"yes"` or `"no"`.

  Each failure is `INVALID_ARGUMENTS`. Instrument fields (robot, nests, profiles) are not checked,
  because that is the core's job and the adapter holds no instrument rule. Simulated mode sleeps
  the `Estimate<Cmd>` constant, returns SUCCESS, never contacts the core and never writes a ledger.
- **D-18:** The same adapter-argument checks run first in real mode too (one shared `_check_args`
  path, fast pattern). Only after they pass does real mode refuse `Transfer` / `AcknowledgeFailure`
  / `GetFailureLatch` with `ERROR_FROM_TOOL` and a one-line "not available in this build" message.
  `ERROR_FROM_TOOL` is used because galago-core hides the text of `INVALID_ARGUMENTS`/`NOT_READY`.
- **D-19:** `Estimate<Cmd>` hooks return local integer constants: no I/O, never raise. Values:
  - `EST_TRANSFER_S = 35` (hardware actual 30-32 s, runbook B3/B7, plus margin);
  - `EST_TRANSFER_ESTIMATE_S = 3`;
  - `EST_READ_S = 2` for every read, `GetFailureLatch` included;
  - `EST_ACK_S = 2`.

  The planner may tune these values but must keep them constant.

### Safety invariant and dependency pin (roadmap SC 2, SC 5)
- **D-20:** Add an AST test over `tools/stack/`, with a planted-violation check, as in v1's
  no-auto-abort invariant. It fails if any adapter code calls `plan_transfer`, `execute_transfer`,
  `start_transfer`, `wait`, `wait_transfer`, `cancel_transfer`, `go_to_safe_position`,
  `wait_safe_position`, `acknowledge_failure` or `validate_transfer` on the service. Phase 5
  replaces it with the narrower XFR-05 invariant.
- **D-21:** A second test asserts that no module under `tools/stack/` imports
  `stack_automation_layer.mcp`.
- **D-22:** `tools/stack/requirements.txt` pins
  `stack-automation-layer @ git+https://gitlab.formulatrix.com/nikkopg/stack-automation-layer.git@ed8ce478d8881a517eb93ed233707f81aea01238`,
  with no `[mcp]` extra. A test asserts the SHA pin, mirroring fast's pin test. `pyproject.toml` gets
  a mypy override for `stack_automation_layer` and `stack_automation_layer.*`. If the GitLab install
  fails on forb01, install from the local clone `~/data/nikko/stack-automation-layer` at `ed8ce47`
  (the fast-mcp precedent). `stack_test.py` skips cleanly when the core is missing.
  — **Reversibility:** reversible — Phase 5 re-pins to the DEP-01 SHA anyway.

### Claude's Discretion
- File layout inside `tools/stack/server.py`: whether the mapping table and the message builder live
  in the module or a small helper module.
- Exact one-line message wording (D-11) and the exact estimate values (D-19), within the stated
  rules.
- Whether to add `tools/tool_images/stack.png` (optional; fast has none).
- How tests build fake results: real core result classes are preferred over hand-built dicts, so
  `to_dict()` shapes are the contract's.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope and research
- `.planning/ROADMAP.md` § "Phase 4" — goal, six success criteria, proto-freeze note, name-collision note
- `.planning/REQUIREMENTS.md` § "Tool registration & reads" — STK-01..STK-07; DEP-02 consumes this phase's proto
- `.planning/PROJECT.md` § Constraints, Context ("STACK core (v2)", "STACK core semantics") — single owner, core-only, credentials, host-string rule
- `.planning/research/SUMMARY.md` — Q1 (file checklist), Q2 (result kinds per call, field mapping, thread safety, ownership), "Proposed stack.proto", reply-mapping table, Core Gaps G1-G7

### Template adapter (this repo)
- `tools/fast/server.py` — `_reply` (:273), `FastServer.ExecuteCommand` override (:515), `_configure` (:546), `Estimate*` hooks (:968-1005), `GetStatus` arity hack (:777, the reason D-05 exists)
- `tools/base_server.py` — `Configure` (:89-120), `_dispatchCommand`/simulated branch (:122-145), `parseCommand`/`ExecuteCommand` BUSY gate (:195-294); **do not edit**
- `tools/tests/fast_test.py` — skip-if-missing, oneof registration, pin test, `MagicMock(spec=...)` mapping table, closed-port Configure, AST invariant with planted violation
- `interfaces/tools/grpc_interfaces/fast.proto`, `tool_base.proto`, `interfaces/controller.proto` — registration points
- `.planning/milestones/v1-phases/01-adapter-control-path-run-state/01-CONTEXT.md` — v1 D-01..D-04 (override pattern and test-first concurrency test)

### STACK core (stack-automation-layer `origin/feat/initial-layer` @ `ed8ce47`; read with `git show ed8ce47:<path>` in `~/data/nikko/stack-automation-layer`)
- `stack_automation_layer/service.py` — read methods (:376-463), `estimate_transfer` (:561), motion methods the invariant forbids (:527-1719)
- `stack_automation_layer/results.py` — `CONTRACT_VERSION = 1` (:64), result kinds and `to_dict()` shapes
- `stack_automation_layer/composition.py` — `open_service` (:137), `OwnedService.endpoint`
- `stack_automation_layer/owner_lock.py` — `endpoint_key` (:50), `StackOwnedError` (:79, names the holder), `default_lock_dir` / `STACK_MCP_LOCK_DIR` (:42)
- `stack_automation_layer/model.py` — `TransferRequest`, `Location`, `missing_fields`
- `stack_automation_layer/mcp/server.py` — `_transfer_request` (:67-97), the reference field mapping (read, never import)
- `docs/runbooks/stack-validation.md` — Part A (sim), Part B (hardware facts, actual transfer times for D-19)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tools/fast/server.py` `_reply`, `ExecuteCommand` override, `_configure` endpoint-reuse logic: copy
  the shapes and adapt them. Do not import across tool packages.
- `tools/tests/fast_test.py` test scaffolding: skip guard, registration tests, pin test, gRPC
  in-process Configure against a closed port, AST invariant helper with planted violation.

### Established Patterns
- Handler = method named after the command's message class; estimate = `Estimate<ClassName>`.
- `_check_args` runs inside `_dispatchCommand` before the simulated-mode branch, so validation applies
  in both modes.
- Generated `*_pb2*.py[i]` are gitignored; `bin/make proto` regenerates them. The gate is
  `bin/make proto test` on `~/data/nikko/.venvs/galago-py310` (ruff, mypy, unittest, pytest). It was
  last green at 147 tests.
- `find_tool_packages()` ships any `tools/<x>/` that has an `__init__.py`. The server is launched as
  `python -m tools.stack.server --port=N`.

### Integration Points
- `tool_base.proto` Command/Config oneofs and `controller.proto` `ToolType`: three one-line additions
  plus an import.
- galago-core (DEP-02, out of this repo) consumes `stack.proto` via its `vendor/galago-tools` submodule
  and ts-proto 1.151.1. It is the reason for the proto freeze.
- To check during research: whether galago-core shows `ConfigureReply.error_message` for a
  `NOT_READY` Configure. Research found that the text is hidden only on the ExecuteCommand path. If
  Configure hides it too, D-08's holder name would only reach the log and `last_error`.

</code_context>

<specifics>
## Specific Ideas

- The proto comment block should state the operator rules inline:
  - `step_key` must be unique per run;
  - `arm_inspected` is `"yes"` only after the arm was inspected and STACK recovered in the STACK
    Manager;
  - there is no `lock_dir`, because both front ends must contend on the same lock.
- Tests never contact `10.150.1.125` / `stack-server`. Use mocks, a closed loopback port, or temp
  lock dirs only.

</specifics>

<deferred>
## Deferred Ideas

- A `run_state`-style STACK heartbeat on the health `GetStatus` (like fast's ADP-05). Not in
  STK-01..07; consider it once Transfer exists (Phase 5 or later).
- Exposing `refresh()` / `refresh_devices()` as commands: `devices(refresh=True)` covers them for v2.
- A tool-page-only command list so `AcknowledgeFailure` stays out of the protocol builder. This is a
  galago-core decision (DEP-02/DEP-03, research Pitfall 5).
- Adapter refusal of `Configure` while a run is in flight. This is a v2 Future Requirement, shared
  with the F.A.S.T. adapter.

</deferred>

---

*Phase: 04-stack-tool-registration-reads-estimate*
*Context gathered: 2026-10-28*
