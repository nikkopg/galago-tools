---
phase: 01-adapter-control-path-run-state
plan: 03
subsystem: adapter
tags: [grpc, protobuf, struct, fast-adapter, run-state, concurrency]

# Dependency graph
requires:
  - phase: 01-adapter-control-path-run-state (plan 01)
    provides: "LONG_RUNNING_COMMANDS' sibling MOTION_LOCK_COMMANDS, FastServer.Transfer/RunProtocol, _log_progress stub, GetStatus dual-dispatch"
  - phase: 01-adapter-control-path-run-state (plan 02)
    provides: "Resume's two paths, lock-free Pause/Abort, fail-closed control path, all proven by tests this plan builds on without re-litigating"
provides:
  - "StatusReply.run_state = 4 (optional google.protobuf.Struct) on tool_base.proto, regenerated cleanly"
  - "LONG_RUNNING_COMMANDS frozenset naming Transfer/RunProtocol as the runs that are 'in flight' for run_state"
  - "FastServer._run_state_lock/_active_runs/_run_record, _run_in_flight() context manager wrapping Transfer/RunProtocol's core call"
  - "_log_progress extended to update the run record; an observation of running clears any recorded pause"
  - "_build_run_state(): the adapter's own record while a run is in flight, a mapped service.status() otherwise, unset with no service, {state: unknown} on any read-path failure"
  - "GetStatus's 2-arg health branch fills reply.run_state via Struct.update, falling back to {state: unknown} on an unencodable payload"
  - "_PauseInfoLike (t.Protocol, duck-typed to_dict()) and FastServer._record_pause(info), recording a pause plus a UTC since timestamp without importing fast-mcp's PauseInfo/ResumeMarker"
  - "_run_percent(value): the adapter's single percent-coercion rule (int/finite-float pass through, bool/str/NaN/missing become None)"
affects: [01-04-static-invariant, 01-05-simulated-pause-hook]

# Actuals (#2632)
actuals:
  tokens: 7226
  tasks: 2
  commits: 2
  plan_head_before: 8dab38c4099e6166aeccb6ac5fb810270a6114db
  plan_head_after: 2c7edf398d2c1cd6109ee4e2b2a25ccc412fc6a7

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "A dedicated threading.Lock (_run_state_lock) guards a small in-memory run record, read and written under the lock, copied out before returning -- the same idiom as _motion_lock but for observation state rather than serialization"
    - "A contextmanager (_run_in_flight) brackets a long-running command's core call to mark/clear run_state's in-flight record, decoupled from the pre-existing _motion_lock try/finally"
    - "typing.Protocol via `import typing as t` / `t.Protocol`, to declare a duck-typed interface (_PauseInfoLike) without colliding with an already-imported same-named class (fast_mcp.model.Protocol)"
    - "A heartbeat read path (_build_run_state) that converts every failure mode -- transport exception, non-dict status, non-str state, unencodable Struct payload -- into a single {state: unknown} sentinel, so GetStatus itself never raises"

key-files:
  created: []
  modified:
    - interfaces/tools/grpc_interfaces/tool_base.proto
    - tools/fast/server.py
    - tools/tests/fast_test.py

key-decisions:
  - "D-09: StatusReply.run_state = 4 is an additive optional google.protobuf.Struct; struct.proto was already imported for ExecuteCommandReply.meta_data, so no new proto import was needed"
  - "D-12: run_state's source is adapter-record-while-in-flight vs. mapped-status()-otherwise, chosen entirely by _active_runs > 0 under _run_state_lock -- never _motion_lock -- so a run-state read can never contend with or depend on a motion command's lock"
  - "D-12/T-01-13: every failure on the read path (a service.status() exception of any type, a non-dict status, a non-string state, or a Struct-unencodable payload) collapses to {state: unknown} rather than distinguishing failure kinds, because the single safety requirement is that the heartbeat never fails"
  - "D-13: _PauseInfoLike is declared as t.Protocol (import typing as t) specifically to avoid colliding with the already-imported fast_mcp.model.Protocol bound to the bare name Protocol; _record_pause accepts any to_dict()-able object and is tested with a module-level _StubPauseInfo stub, never the core's real PauseInfo"
  - "ADP-05 precision: _run_percent is the adapter's one and only percent-coercion rule -- an int (not bool) or finite float passes through unrounded; a bool, string, NaN or missing value becomes None -- applied uniformly to both the idle service.status() mapping and _record_pause's own percent"

requirements-completed: [ADP-05]

coverage:
  - id: D1
    description: "StatusReply.run_state = 4 (optional google.protobuf.Struct) regenerates cleanly with bin/make proto, additive and unset by default for every tool type (ADP-05)"
    requirement: "ADP-05"
    verification:
      - kind: other
        ref: "bin/make proto test (full gate, regenerates tool_base_pb2 and runs the suite against it)"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRunState.test_other_tool_types_leave_run_state_unset"
        status: pass
    human_judgment: false
  - id: D2
    description: "While a Transfer/RunProtocol is in flight, the health GetStatus reports run_state from the adapter's own record: running at entry with percent null, then the latest (percent, state) from _log_progress, never calling service.status()"
    requirement: "ADP-05"
    verification:
      - kind: integration
        ref: "tools/tests/fast_test.py#TestRunStateOverGrpc.test_run_state_is_running_with_the_latest_progress_while_a_transfer_runs"
        status: pass
      - kind: integration
        ref: "tools/tests/fast_test.py#TestRunStateOverGrpc.test_run_state_at_transfer_entry_has_no_percent_yet"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRunState.test_run_protocol_marks_its_run_in_flight"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRunState.test_a_run_that_raises_leaves_no_run_in_flight"
        status: pass
    human_judgment: false
  - id: D3
    description: "With no run in flight, run_state maps a fresh service.status() to state/percent (percentProgress renamed to percent, the raw key never appears), pause: null; percent is never rounded, clamped or coerced (0 and 100 pass through exactly; a bool, string, NaN or missing value becomes None)"
    requirement: "ADP-05"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRunState.test_no_run_in_flight_maps_status_and_renames_percent"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRunState.test_percent_is_passed_through_without_rounding_or_coercion"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestReadAndRecoveryCommands.test_get_status_dual_dispatch_delegates_health_rpc_to_super"
        status: pass
    human_judgment: false
  - id: D4
    description: "run_state is unset when no service is configured, and every read-path failure (a service.status() exception of any kind, a non-dict status, a non-string state, or an unencodable recorded payload) yields {state: unknown} without ever failing the heartbeat (status and uptime still return normally)"
    requirement: "ADP-05"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRunState.test_unconfigured_tool_leaves_run_state_unset"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRunState.test_status_failure_reports_unknown_and_the_heartbeat_still_answers"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRunState.test_unencodable_run_state_falls_back_to_unknown"
        status: pass
    human_judgment: false
  - id: D5
    description: "A recorded pause (_record_pause, fed a duck-typed to_dict()-able object) is reported with its full detail (errorCode, errorName, percent, eventPayload) plus a UTC since timestamp; a later running observation clears it, a paused observation keeps it"
    requirement: "ADP-05"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRunState.test_recorded_pause_is_reported_with_its_detail_and_a_utc_since"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRunState.test_running_observation_clears_the_pause_and_paused_keeps_it"
        status: pass
    human_judgment: false
  - id: D6
    description: "Reading run_state never commands the instrument: zero service calls while a run is in flight, exactly one service.status() call when idle; the dedicated _run_state_lock is never the _motion_lock; the 1-arg intent GetStatus command is unaffected and still returns the raw status dict"
    requirement: "ADP-05"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRunState.test_run_state_lock_is_not_the_motion_lock"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRunState.test_intent_get_status_is_unchanged"
        status: pass
      - kind: other
        ref: "AST acceptance check: _build_run_state's only service.* call is status() (plan Task 1 acceptance criteria)"
        status: pass
    human_judgment: false

duration: 26min
completed: 2026-10-12
status: complete
---

# Phase 1 Plan 3: run_state on the Health GetStatus Summary

**`StatusReply.run_state` reports live state/percent/pause for the F.A.S.T., sourced from the adapter's own record while a Transfer/RunProtocol is in flight and from a mapped `service.status()` otherwise, with every read-path failure collapsing to `{state: unknown}` so the heartbeat never fails.**

## Performance

- **Duration:** 26 min
- **Started:** 2026-10-12T21:45:00Z
- **Completed:** 2026-10-12T22:11:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- `StatusReply.run_state = 4` (`optional google.protobuf.Struct`) added to `tool_base.proto` and regenerated cleanly, additive and unset by default for every tool type other than the F.A.S.T.
- `FastServer` gained a dedicated `_run_state_lock`, `_active_runs`/`_run_record` state, and a `_run_in_flight()` context manager wrapping `Transfer`'s and `RunProtocol`'s core service call, so the record is set on entry and cleared on every exit (success, failure or exception) without ever touching `_motion_lock`
- `_log_progress` now also updates the run record on every poll; a `running` observation clears any recorded pause
- `_build_run_state()` is the single read-path builder: the adapter's own record while in flight, a `percentProgress`-to-`percent` mapped `service.status()` otherwise, `None` (unset) with no service configured, and `{state: unknown}` on any failure -- a `service.status()` exception, a non-dict status, a non-string state, or (via `GetStatus`'s `Struct.update` fallback) an unencodable payload
- `GetStatus`'s 2-arg health branch fills `reply.run_state`; the 1-arg intent command is unchanged
- `_PauseInfoLike` (`t.Protocol`, avoiding the existing `fast_mcp.model.Protocol` name collision) and `FastServer._record_pause` record a pause with a UTC `since` timestamp, duck-typed so the module never imports the pinned core's missing `PauseInfo`/`ResumeMarker` (D-13)
- `_run_percent` is the one percent-coercion rule used everywhere: an int (not bool) or finite float passes through unrounded; a bool, string, NaN or missing value becomes `None`
- `_RealModeGrpcTestCase` extracted as the shared real-mode gRPC fixture (setUp, `_fast`, `_health`, `_start_blocked_transfer` with an optional `progress` hook); `TestControlCommandsOverGrpc` now inherits it unchanged, and the new `TestRunStateOverGrpc`/`TestRunState` classes build on it and on a fresh `_StubPauseInfo`/`_WRONG_PLATE_PAUSE` fixture

## Task Commits

Each task was committed atomically:

1. **Task 1: Live run_state on the health GetStatus while a Transfer runs, and from status() when idle** - `2809200` (feat)
2. **Task 2: Pause recorder and a run_state that never fails the heartbeat** - `2c7edf3` (feat)

## Files Created/Modified
- `interfaces/tools/grpc_interfaces/tool_base.proto` - adds `optional google.protobuf.Struct run_state = 4` to `StatusReply`
- `tools/fast/server.py` - `LONG_RUNNING_COMMANDS`, `_run_percent`, `_PauseInfoLike`, `FastServer._run_state_lock`/`_active_runs`/`_run_record`, `_run_in_flight()`, `_record_pause()`, `_build_run_state()`, extended `_log_progress`/`Transfer`/`RunProtocol`/`GetStatus`
- `tools/tests/fast_test.py` - `_RealModeGrpcTestCase` (extracted shared fixture), `TestRunStateOverGrpc`, `TestRunState`, `_StubPauseInfo`, `_WRONG_PLATE_PAUSE`, extended `TestReadAndRecoveryCommands.test_get_status_dual_dispatch_delegates_health_rpc_to_super`

## Decisions Made
- **D-09** (proto field): implemented exactly as specified, reusing the already-imported `struct.proto` -- no new proto import.
- **D-12** (run_state source split): the in-flight/idle branch decision and the universal `{state: unknown}` failure fallback were implemented exactly as specified; a `service.status()` failure of any exception type (not just transport errors) maps to `unknown`, per the plan's explicit "a heartbeat must never fail because of run state" framing.
- **D-13** (duck-typed recorder): `_PauseInfoLike` declared via `import typing as t` / `t.Protocol`, avoiding the pre-existing `fast_mcp.model.Protocol` name collision flagged in 01-PATTERNS.md; `_record_pause` has no caller in production code this phase (Phase 2 wires it as `RunOptions(on_pause=...)`), matching D-13's scope.
- **ADP-05 precision**: `_run_percent` never rounds, clamps or converts -- an int or finite float passes through exactly, everything else becomes `None`. Applied identically whether the value comes from `service.status()["percentProgress"]` or a recorded pause's `percent`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Two mypy `arg-type` fixes needed to keep the gate green**
- **Found during:** Task 2 (full-gate verification)
- **Issue:** (a) The existing `test_get_status_dual_dispatch_delegates_health_rpc_to_super` accessed `.run_state` on the raw return value of `FastServer.GetStatus(...)`, whose declared return type is `object` (the existing `# type: ignore[override]` dual-dispatch signature) -- mypy correctly flagged `"object" has no attribute "run_state"` once the test started reading that field. (b) The new `test_other_tool_types_leave_run_state_unset` calls `Lcus1RelayServer().GetStatus(empty_pb2.Empty(), None)`; `Lcus1RelayServer` does not override `GetStatus`, so mypy resolves the call against `ToolServer.GetStatus(self, request: tool_base_pb2.Config, context: grpc.ServicerContext)`, and `empty_pb2.Empty()`/`None` don't match that signature.
- **Fix:** (a) Wrapped the call in `cast(tool_base_pb2.StatusReply, ...)` before reading `.run_state`, matching every other call site in this file. (b) Added a `# type: ignore[arg-type]` comment on the `Lcus1RelayServer` call, matching the established idiom already used elsewhere in this file for the identical `Config`/`Empty` signature mismatch (e.g. `TestReconfigure`'s `Configure(config_a, None)` calls).
- **Files modified:** tools/tests/fast_test.py
- **Verification:** `bash bin/make proto test` green (ruff clean, mypy 0 errors, 104 unittest + 104 pytest tests passing).
- **Committed in:** 2c7edf3 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking/type-check, two call sites).
**Impact on plan:** Purely a type-annotation fix to keep every commit gate-green; no change to runtime behavior, test coverage, or public surface described anywhere else in this plan.

## Issues Encountered

None beyond the deviation above.

## Known Stubs

None - no stub patterns introduced. `simulate_pause` and the simulated-mode `run_state` marker remain Plan 01-05's scope, unbuilt here per the phase's artifact inventory.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `StatusReply.run_state`, the run record (`_run_in_flight`, `_log_progress`, `_record_pause`), the builder (`_build_run_state`) and the `GetStatus` fill-in are in place and gate-green, ready for Plan 01-04 (the reusable AST invariant extending `TestAdapterInvariant` to scope `.pause`/`on_pause`/the run_state builder) and Plan 01-05 (the simulated-mode `run_state` marker and `simulate_pause` hook, which will call this plan's `_record_pause` through a trivial `to_dict()`-able wrapper per 01-RESEARCH.md's Open Question 1 recommendation).
- `tools/base_server.py` confirmed byte-identical to commit `9c27896` throughout (no edits made, verified via `git diff --exit-code` at every task).
- No blockers. The phase-wide symbol inventory's 01-03 rows (`StatusReply.run_state = 4`, `LONG_RUNNING_COMMANDS`, `_run_percent`, `_PauseInfoLike`, `FastServer._run_state_lock`/`_active_runs`/`_run_record`, `_run_in_flight()`/`_record_pause(info)`/`_build_run_state()`, extended `_log_progress`/`GetStatus`, `_RealModeGrpcTestCase`, `TestRunStateOverGrpc`/`TestRunState`/`_StubPauseInfo`/`_WRONG_PLATE_PAUSE`) are all present under the exact names the plan's artifact table specifies.

## Self-Check: PASSED

- FOUND: interfaces/tools/grpc_interfaces/tool_base.proto
- FOUND: tools/fast/server.py
- FOUND: tools/tests/fast_test.py
- FOUND: 2809200 (ancestor of HEAD)
- FOUND: 2c7edf3 (ancestor of HEAD)
- Full gate (`bin/make proto test`: ruff, mypy, 104 unittest + 104 pytest tests) green at HEAD `2c7edf3`
- `git diff --exit-code 9c27896 -- tools/base_server.py` exits 0 (never edited)

---
*Phase: 01-adapter-control-path-run-state*
*Completed: 2026-10-12*
