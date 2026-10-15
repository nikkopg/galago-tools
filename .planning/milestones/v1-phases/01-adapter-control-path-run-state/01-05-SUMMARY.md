---
phase: 01-adapter-control-path-run-state
plan: 05
subsystem: adapter
tags: [fast-adapter, simulated-mode, run-state, pause-hook, grpc]

# Dependency graph
requires:
  - phase: 01-adapter-control-path-run-state (plan 01)
    provides: "CONTROL_COMMANDS, LONG_RUNNING_COMMANDS, the ExecuteCommand/_dispatchCommand overrides, Pause/Resume/Abort, EST_PAUSE_S/EST_RESUME_S/EST_ABORT_S"
  - phase: 01-adapter-control-path-run-state (plan 03)
    provides: "_run_state_lock, _active_runs, _run_record, _run_in_flight(), _record_pause(info), _build_run_state(), _PauseInfoLike, _run_percent"
  - phase: 01-adapter-control-path-run-state (plan 04)
    provides: "_adapter_invariant_violations(tree), _plant(tree, function, statement), _RECORD_ONLY_FUNCTIONS and the rest of the scoping constants, TestAdapterInvariant"
provides:
  - "FastServer._dispatchCommand brackets a simulated LONG_RUNNING_COMMANDS sleep in _run_in_flight() so simulated run_state reads running for its duration (counted, not boolean) and idle once it ends"
  - "FastServer._build_run_state gains a simulated-first branch: paused (with detail) whenever a pause is recorded regardless of an in-flight run, else running/idle from _active_runs, never touching the service"
  - "_DictPauseInfo: wraps a plain dict as a _PauseInfoLike so the simulated hook feeds the same _record_pause Phase 2 wires as RunOptions(on_pause=...)"
  - "FastServer.simulate_pause(pause) and FastServer._clear_pause(): the in-process, simulated-mode-only test hook (D-20) that drives run_state to paused/idle with no instrument and no new gRPC command"
  - "_PAUSE_CLEARING_COMMANDS and _dispatchCommand's new clearing step: a successful simulated Resume/Abort clears a hooked pause"
  - "simulate_pause/_clear_pause added to _RECORD_ONLY_FUNCTIONS with planted-violation coverage"
affects: ["02-core-repin-and-wait-through-pauses"]

# Actuals (#2632)
actuals:
  tokens: 5758
  tasks: 2
  commits: 2
  plan_head_before: cb93bedd5e8c39a452a27a4fb4d585535b3334f8
  plan_head_after: 246cdece53f709a2bc6125817c607f48946b3f17

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "A control-flow override (_dispatchCommand) that brackets the base class's own simulated sleep with a context manager, rather than replicating the sleep itself -- base_server still owns the timing, the adapter only observes its duration for run_state"
    - "A thin duck-typed wrapper (_DictPauseInfo) lets a test/dev-only entry point feed the same production recorder a future real caller (Phase 2's RunOptions(on_pause=...)) will use, so there is exactly one path that turns a pause into a recorded run_state, not two"
    - "State for run_state is always derived from the current record (pause / _active_runs), never read back from a cached state string, so a cleared pause can never leave a stale derived value behind"

key-files:
  created: []
  modified:
    - tools/fast/server.py
    - tools/tests/fast_test.py

key-decisions:
  - "D-18: no new production code was needed for simulated Pause/Resume/Abort to check arguments then succeed -- the existing _dispatchCommand -> _check_args -> super()._dispatchCommand path already routes through base_server's simulated branch, which sleeps the named estimate and returns SUCCESS without ever building a service. Task 1 only added test coverage plus the run_state bracketing for LONG_RUNNING_COMMANDS."
  - "D-19: _build_run_state's simulated branch derives state from pause/_active_runs directly (paused > running > idle), not from _run_record['state'], so a hook-cleared pause can never surface as a stale 'paused' even though _run_in_flight's own bookkeeping also writes a 'state' key into the record."
  - "D-20: simulate_pause's real-mode guard is the first statement after its docstring (enforced by the plan's own AST acceptance check) so no state is ever touched before the RuntimeError fires; it is a bare instance method with no gRPC surface, proto, or COMMAND_TO_SERVICE_METHOD entry."
  - "D-20: _PAUSE_CLEARING_COMMANDS = {Resume, Abort} is deliberately checked after super()._dispatchCommand returns (and only on response == SUCCESS), so an INVALID_ARGUMENTS reply from _check_args -- which returns before this point -- never clears a hooked pause, and a simulated Pause is not in the set at all."
  - "Two-overlapping-Transfer test tracks completion via a queue.Queue of replies rather than per-thread result slots, avoiding any assumption about which thread claims which of the two interchangeable sleep gates -- a lesson carried over from RESEARCH Pitfall 3's counter-not-boolean guidance applied to the test itself."

requirements-completed: [ADP-10, ADP-06]

coverage:
  - id: D1
    description: "Simulated Pause/Resume/Abort check arguments through _check_args, then sleep their own EST_*_S estimate and return SUCCESS without ever calling open_service or building a FastService; a blank/unclear Resume or Abort decision is INVALID_ARGUMENTS with no sleep"
    requirement: "ADP-06"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestSimulatedTransferOverGrpc.test_simulated_control_commands_check_arguments_then_succeed"
        status: pass
    human_judgment: false
  - id: D2
    description: "Simulated run_state reads running (a counted, not boolean, in-flight marker) while a simulated Transfer sleeps and idle once it ends, including two overlapping Transfers staying running until both end; a simulated Pause sent mid-sleep never shortens the Transfer's own sleep"
    requirement: "ADP-10"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestSimulatedTransferOverGrpc.test_simulated_run_state_is_running_during_a_transfer_sleep_then_idle"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestSimulatedTransferOverGrpc.test_two_overlapping_simulated_transfers_read_running_until_both_end"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestSimulatedTransferOverGrpc.test_simulated_pause_does_not_shorten_the_transfer_sleep"
        status: pass
    human_judgment: false
  - id: D3
    description: "FastServer.simulate_pause(pause) is an in-process, simulated-mode-only hook: it raises RuntimeError and records nothing in real mode, drives run_state to paused with the hooked PauseInfo-shaped detail (or clears it back to idle with None) in simulated mode, and is not a gRPC command (no fast.proto field, no COMMAND_TO_SERVICE_METHOD entry)"
    requirement: "ADP-10"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestSimulatePauseHook.test_hook_raises_in_real_mode_and_records_nothing"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestSimulatePauseHook.test_hook_is_not_a_grpc_command"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestSimulatedTransferOverGrpc.test_hooked_pause_reads_paused_with_its_detail"
        status: pass
    human_judgment: false
  - id: D4
    description: "A simulated Resume or Abort that returns SUCCESS clears a hooked pause; a Resume rejected as INVALID_ARGUMENTS and a simulated Pause both leave it in place; the full pause-prompt round trip (sleeping Transfer -> hook -> Resume -> release) works end to end with no instrument contact"
    requirement: "ADP-10"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestSimulatedTransferOverGrpc.test_simulated_resume_or_abort_clears_a_hooked_pause_and_invalid_args_do_not"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestSimulatedTransferOverGrpc.test_pause_prompt_round_trip_without_hardware"
        status: pass
    human_judgment: false
  - id: D5
    description: "simulate_pause and _clear_pause are record-only (no .service access, no control/motion method call), confirmed by the existing AST invariant checker extended with planted violations in both functions, and the full phase gate (ruff, mypy, unittest+pytest) stays green with tools/base_server.py untouched"
    requirement: "ADP-07"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestAdapterInvariant.test_planted_record_and_state_violations_are_caught"
        status: pass
      - kind: other
        ref: "PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto test (full gate: ruff, mypy, 118 unittest + pytest tests)"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-10-12
status: complete
---

# Phase 1 Plan 5: Simulated Control Path & Pause Hook Summary

**Simulated Pause/Resume/Abort check arguments then succeed with no instrument contact, simulated run_state tracks a counted in-flight run, and a new in-process `simulate_pause` hook lets galago-core exercise its pause prompt and Resume/Abort round trip with no hardware.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-10-12T22:08:00Z
- **Completed:** 2026-10-12T22:33:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `FastServer._dispatchCommand` brackets a simulated `LONG_RUNNING_COMMANDS` run in `_run_in_flight()`, so `run_state` reads `running` for the whole of base_server's simulated sleep and `idle` once it returns -- a counter, so two overlapping simulated Transfers stay `running` until the last one ends (D-19)
- `_build_run_state` gained a simulated-first branch that never touches `self.service` (which stays `None` throughout simulated mode): a recorded pause always reads `paused` with its detail regardless of whether a run is in flight, otherwise `running`/`idle` derived straight from `_active_runs`
- Simulated Pause/Resume/Abort needed no new production code to check arguments then succeed (D-18) -- `_check_args` already runs before base_server's simulated branch sleeps the named estimate and returns `SUCCESS`; covered with gRPC-level tests proving `open_service` is never called and `self.fs.service` stays `None`
- `FastServer.simulate_pause(pause)` is a new in-process, simulated-mode-only hook (D-20): it raises `RuntimeError` in real mode before touching any state, and in simulated mode either clears a hooked pause (`pause=None`) or wraps a dict in `_DictPauseInfo` and feeds it to the same `_record_pause` Phase 2 will wire as `RunOptions(on_pause=...)`. It has no gRPC surface -- `fast.proto`'s 1:1 command list is unchanged
- A successful simulated Resume or Abort clears a hooked pause via a new `_PAUSE_CLEARING_COMMANDS` check in `_dispatchCommand`; an `INVALID_ARGUMENTS` Resume and a simulated Pause both leave it in place, and the full round trip (sleeping Transfer -> hook -> Resume -> release -> idle) is proven end to end with no instrument contact
- `simulate_pause`/`_clear_pause` were added to `_RECORD_ONLY_FUNCTIONS`, with planted-violation `subTest`s proving a service call inside either is caught by the existing AST invariant checker

## Task Commits

Each task was committed atomically:

1. **Task 1: Simulated control commands succeed after argument checks, and simulated run_state follows the simulated run** - `8ff03dc` (feat)
2. **Task 2: The simulate_pause hook drives run_state to paused, and a simulated Resume or Abort clears it** - `246cdec` (feat)

## Files Created/Modified
- `tools/fast/server.py` - `_dispatchCommand` wraps a simulated long-running sleep in `_run_in_flight()` and clears a hooked pause on a successful simulated Resume/Abort; `_build_run_state` gained its simulated branch; new `_DictPauseInfo`, `_PAUSE_CLEARING_COMMANDS`, `FastServer._clear_pause`, `FastServer.simulate_pause`
- `tools/tests/fast_test.py` - nine new tests across `TestSimulatedTransferOverGrpc` (control commands, run_state during/after a simulated Transfer, two overlapping Transfers, pause-not-shortened, hooked pause detail, Resume/Abort clearing, full round trip) and a new `TestSimulatePauseHook` class (real-mode refusal, no gRPC command); `_RECORD_ONLY_FUNCTIONS` extended and two new planted-violation `subTest`s added to `TestAdapterInvariant`

## Decisions Made
- **D-18**: confirmed before writing any test that the existing `_dispatchCommand`/`_check_args`/base_server-simulated-branch path already satisfies "check arguments, then sleep the estimate and succeed" for Pause/Resume/Abort -- Task 1 added only the `_run_in_flight` bracketing for `LONG_RUNNING_COMMANDS` plus test coverage, not new control-command code.
- **D-19**: `_build_run_state`'s simulated branch derives `state` from `pause`/`_active_runs` each time it is read, rather than trusting `_run_record["state"]`, so a cleared pause (by the hook or by Resume/Abort) can never leave a stale `"paused"` behind even though `_run_in_flight`/`_log_progress` also write a `state` key into the same record for the real-mode path.
- **D-20**: `simulate_pause`'s simulated-mode guard is the first statement after its docstring (matching the plan's own AST acceptance check), so no state is ever touched before the `RuntimeError` fires in real mode; it is a bare instance method with no proto field, no `COMMAND_TO_SERVICE_METHOD` entry, and no effect on the 1:1 command surface.
- **D-20**: `_PAUSE_CLEARING_COMMANDS = {"Resume", "Abort"}` is checked only after `super()._dispatchCommand(command)` returns and only when its `response == SUCCESS` -- an `INVALID_ARGUMENTS` reply returns earlier from `_check_args` and so never reaches this point, and a simulated Pause is not in the set at all, matching the plan's "argument failures never clear; Pause never clears" requirement exactly.
- Test-only: the two-overlapping-Transfer test tracks completion through a `queue.Queue` of replies instead of per-thread result slots, so the test makes no assumption about which of the two threads claims which of the two interchangeable sleep-gate `Event`s (RESEARCH Pitfall 3's counter-not-boolean guidance, applied to the test harness itself to avoid a flaky index-matching bug).

## Deviations from Plan

None - plan executed exactly as written. `tools/base_server.py` was never touched (confirmed via `git diff --exit-code 9c27896 -- tools/base_server.py` after each task). One mechanical fix surfaced during the full-gate run and was corrected before the Task 2 commit:

### Auto-fixed Issues

**1. [Rule 3 - Blocking] mypy flagged a list-comprehension cleanup as a return-value misuse**
- **Found during:** Task 2 full-gate run (`bin/make proto test`)
- **Issue:** `self.addCleanup(lambda: [t.join(10) for t in threads])` in the two-overlapping-Transfers test built a list from `Thread.join()`'s `None` return, which mypy flags as `func-returns-value` since the list comprehension consumes the return.
- **Fix:** Replaced the lambda/list-comprehension with a small named `_join_all()` helper that loops and calls `.join(10)` as a statement, with no return value collected.
- **Files modified:** tools/tests/fast_test.py
- **Verification:** `bin/make proto test` reruns clean (`mypy`: 0 errors, 118 tests pass)
- **Commit:** `246cdec` (part of Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking/mypy)
**Impact on plan:** Test-only mechanical fix with no behavior change. No scope creep.

## Issues Encountered

None.

## Known Stubs

None - no stub patterns introduced. This plan is adapter logic plus test coverage, with no UI or data-flow surface that could stub.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 1 (Adapter Control Path & Run State) is now complete: all 5 plans executed. The F.A.S.T. adapter has soft-only Pause, control commands that bypass the motion lock and base_server's readiness gate, `StatusReply.run_state`, simulated-mode control commands and run_state, a simulated pause hook for galago-core's dev tests, and an extended mechanical no-auto-abort invariant -- all proven against a mocked `FastService` on the pinned core `76f8c3f`.
- `simulate_pause`'s `_DictPauseInfo` wrapper and its use of the existing `_record_pause` mean Phase 2's re-pin can wire `RunOptions(on_pause=self._record_pause)` directly with no further change to the recorder itself.
- Full gate green: `ruff` clean, `mypy` 0 errors, 118 unittest + pytest tests passing (up from 109 at the end of Plan 01-04) at HEAD `246cdec`.
- `tools/base_server.py` was never edited across any plan in this phase (`git diff --exit-code 9c27896 -- tools/base_server.py` exits 0).
- No blockers. Phase 2 (core re-pin, `through_pauses`/`on_pause` wiring, paused-time-excluded timeout) can proceed once fast-mcp's `fix/run-recovery-gate` branch (`76f8c3f`/`b30b38d`) is pushed to GitLab (tracked in STATE.md Blockers/Concerns).

## Self-Check: PASSED

- FOUND: tools/fast/server.py
- FOUND: tools/tests/fast_test.py
- FOUND: 8ff03dc (ancestor of HEAD)
- FOUND: 246cdec (ancestor of HEAD)
- Full gate (`bin/make proto test`: ruff, mypy, 118 unittest + pytest tests) green at HEAD `246cdec`
- `git diff --exit-code 9c27896 -- tools/base_server.py` exits 0 (never edited)
- `_adapter_invariant_violations` on the real `tools/fast/server.py` returns `[]`

---
*Phase: 01-adapter-control-path-run-state*
*Completed: 2026-10-12*
