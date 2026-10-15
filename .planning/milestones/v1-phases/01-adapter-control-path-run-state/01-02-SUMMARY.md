---
phase: 01-adapter-control-path-run-state
plan: 02
subsystem: adapter
tags: [grpc, fast-mcp, control-path, concurrency, unittest]

# Dependency graph
requires:
  - phase: 01-adapter-control-path-run-state (plan 01)
    provides: "FastServer.ExecuteCommand override, CONTROL_COMMANDS, MOTION_LOCK_COMMANDS, COMMAND_TO_SERVICE_METHOD, TestControlCommandsOverGrpc tracer tests"
provides:
  - "Resume's two paths proven: in-flight returns on acceptance without waiting (lock stays held by its owner); crash-recovery (lock free) waits under the lock, blocking a concurrent Transfer"
  - "Pause and Abort proven never to touch _motion_lock, and to succeed while another command holds it"
  - "Pause's result mapping through the real fast-mcp core gate: soft pause while running, refused (no transport call) otherwise, nonzero/missing errorCode as ERROR_FROM_TOOL"
  - "ExecuteCommand control path proven fail-closed on blank/unclear decisions, both idle and mid-run, with a deterministic single-entry needsInput meta"
  - "Tool-type check (WRONG_TOOL/UNRECOGNIZED_COMMAND) and the non-control base_server gate (NOT_READY mid-run) proven unaffected by the override"
  - "Control-command exceptions proven to map to DRIVER_ERROR and set last_error; no control command ever calls setStatus"
  - "No control command reads instrument state under any status/{}/exception; back-to-back commands reach the service in send order"
affects: [01-03-run-state, 01-04-static-invariant, 01-05-simulated-pause-hook]

# Actuals (#2632)
actuals:
  tokens: 5507
  tasks: 2
  commits: 2
  plan_head_before: 309a55efa89b60994173c335aaae4975cbd31112
  plan_head_after: e42dd45ab374b5fe580ca8848bd52d8c84528830

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "MagicMock(wraps=threading.Lock()) as a spy that proves a code path never calls acquire/release, while still behaving as a real lock for any code that does"
    - "Resetting a MagicMock(spec=...) between subTest iterations so a class-wide tearDown invariant (call_count <= 1 per control method) still holds at test end, even though the body sent many more calls across the matrix"

key-files:
  created: []
  modified:
    - tools/fast/server.py
    - tools/tests/fast_test.py

key-decisions:
  - "EST_RESUME_S stays a flat 15s placeholder; the comment above it now records that Resume only waits on the crash-recovery path and that a single flat value over/under-states the two now-different-latency cases (research Pitfall 8), per CONTEXT.md Claude's Discretion -- no behavior change, no new estimate logic"
  - "No bugs found in Pause/Abort/Resume: all must_haves were already satisfied by Plan 01-01's implementation, so this plan is purely additive test coverage plus the one debt comment"

patterns-established:
  - "Pattern: TestControlCommandsOverGrpc's tearDown (pause/resume/abort call_count <= 1) is honored across multi-case matrix tests by calling self.service.reset_mock() at the top of each subTest -- only the last iteration's counts are live when tearDown runs"

requirements-completed: [ADP-04, ADP-06, ADP-09, ADP-01, ADP-03]

coverage:
  - id: D1
    description: "Resume's two paths: in-flight returns on acceptance without waiting and leaves the owner's lock held; in-flight failures (Refused, nonzero errorCode, transport error) never wait or release the lock; crash-recovery (lock free) waits under the lock and blocks a concurrent Transfer until done"
    requirement: ADP-04
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py::TestControlCommandsBypassMotionLock#test_resume_with_a_run_in_flight_returns_on_acceptance_without_waiting"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py::TestControlCommandsBypassMotionLock#test_resume_in_flight_failures_never_wait_or_release_the_owners_lock"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py::TestControlCommandsBypassMotionLock#test_crash_recovery_resume_waits_and_holds_the_lock"
        status: pass
    human_judgment: false
  - id: D2
    description: "Pause and Abort never touch _motion_lock (spy-verified acquire/release never called) and both succeed while another command holds it"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py::TestControlCommandsBypassMotionLock#test_pause_and_abort_never_touch_the_motion_lock"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py::TestControlCommandsBypassMotionLock#test_pause_and_abort_succeed_while_another_command_holds_the_lock"
        status: pass
    human_judgment: false
  - id: D3
    description: "Pause's result mapping through the real fast-mcp core gate: soft pause (transport.pause(hard=False)) while running; refused with no transport call while idle/paused; nonzero or missing errorCode as ERROR_FROM_TOOL"
    requirement: ADP-01
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py::TestRecoveryCommands#test_pause_while_running_is_a_soft_pause_and_success"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py::TestRecoveryCommands#test_pause_while_not_running_is_refused_without_a_pause_call"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py::TestRecoveryCommands#test_pause_nonzero_or_missing_error_code_is_error_from_tool"
        status: pass
    human_judgment: false
  - id: D4
    description: "The ExecuteCommand control path is fail-closed on blank/unclear is_tip_broken/return_liquid, idle and mid-run, with a deterministic single-entry needsInput meta and nothing reaching the service; only trimmed/case-insensitive yes/no pass"
    requirement: ADP-06
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py::TestControlCommandsOverGrpc#test_blank_or_unclear_decisions_are_invalid_arguments_through_the_control_path"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py::TestControlCommandsOverGrpc#test_blank_decisions_mid_run_are_invalid_arguments_and_leave_the_tool_busy"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py::TestControlCommandsOverGrpc#test_trimmed_case_insensitive_yes_no_is_accepted"
        status: pass
    human_judgment: false
  - id: D5
    description: "The tool-type check and the non-control base_server gate are unaffected by the override: a toolbox command is WRONG_TOOL, an empty fast command is UNRECOGNIZED_COMMAND, and GetTipStatus mid-run is still NOT_READY"
    requirement: ADP-03
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py::TestControlCommandsOverGrpc#test_wrong_tool_type_never_takes_the_control_path"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py::TestControlCommandsOverGrpc#test_non_control_commands_still_take_the_base_server_gate_mid_run"
        status: pass
    human_judgment: false
  - id: D6
    description: "A control command's service exception maps to DRIVER_ERROR carrying the exception text and sets last_error; no control command ever calls setStatus (a non-control command still brackets BUSY/READY normally)"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py::TestControlCommandsOverGrpc#test_control_command_exception_is_driver_error_and_sets_last_error"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py::TestControlCommandsOverGrpc#test_control_commands_never_call_set_status"
        status: pass
    human_judgment: false
  - id: D7
    description: "No control command ever reads instrument state (service.status call_count stays 0) under any reported state, {}, or a transport ConnectError, through both the gRPC override and direct method calls; back-to-back Pause/Abort/Resume reach the service in send order"
    requirement: ADP-09
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py::TestControlCommandsOverGrpc#test_control_commands_never_check_instrument_state"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py::TestControlCommandsOverGrpc#test_control_commands_reach_the_service_in_send_order"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-10-12
status: complete
---

# Phase 1 Plan 2: Resume's Two Paths and the Fail-Closed Control Path Summary

**Resume's in-flight/crash-recovery split, lock-free Pause/Abort, Pause's core-gate mapping, and the ExecuteCommand override's fail-closed/state-check-free guarantees are now each pinned by a named test.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-10-12T21:42:00Z
- **Completed:** 2026-10-12T21:57:11Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- `TestControlCommandsBypassMotionLock` (new class) proves Resume's two paths: in-flight returns on acceptance and leaves the owner's lock held (and never waits or releases it on a Refused/nonzero-errorCode/transport-error failure); crash-recovery (lock free) waits under the lock, blocking a concurrent Transfer, and releases the lock once the wait returns.
- `TestControlCommandsBypassMotionLock` also proves Pause and Abort never touch `_motion_lock` (spy-verified `acquire`/`release`) and both succeed while another command holds it.
- `TestRecoveryCommands` gains Pause's mapping through the real fast-mcp core gate: soft pause while running, refused with no transport call while idle/paused, and nonzero/missing `errorCode` as `ERROR_FROM_TOOL`.
- `TestControlCommandsOverGrpc` is extended with nine override-path guarantee tests: fail-closed blank/unclear decisions (idle and mid-run, with a deterministic single-entry `needsInput` meta), trimmed/case-insensitive yes/no acceptance, the tool-type check (`WRONG_TOOL`/`UNRECOGNIZED_COMMAND`), the non-control base_server gate still applying mid-run, `DRIVER_ERROR` exception mapping, `setStatus` never being called by a control command, an exhaustive matrix proving zero `status()` calls under any instrument state (including `{}` and a transport `ConnectError`), and send-order preservation.
- `EST_RESUME_S`'s comment now records the accepted estimate debt: a single flat value is wrong in both directions now that Resume only waits on the crash-recovery path.

## Task Commits

Each task was committed atomically:

1. **Task 1: Resume's two paths, lock-free Pause and Abort, and Pause's result mapping, proven** - `5bcb812` (test)
2. **Task 2: The ExecuteCommand control path is fail-closed, keeps the tool-type check, maps errors and never checks instrument state** - `e42dd45` (test)

**Plan metadata:** commit created after this SUMMARY.

## Files Created/Modified
- `tools/fast/server.py` - Updated the `EST_RESUME_S` comment to record the accepted estimate debt (Pitfall 8); no behavior change
- `tools/tests/fast_test.py` - New `TestControlCommandsBypassMotionLock` class (5 tests); 3 new Pause tests in `TestRecoveryCommands`; 9 new override-path guarantee tests in `TestControlCommandsOverGrpc`; `toolbox_pb2` and `DRIVER_ERROR`/`UNRECOGNIZED_COMMAND`/`WRONG_TOOL` added to imports

## Decisions Made
- `EST_RESUME_S` stays a flat 15s placeholder (no new branching estimate logic); the comment above it documents why that is now wrong in both directions, per CONTEXT.md's explicit "Claude's Discretion" guidance.
- No implementation bugs were found in `Pause`, `Abort` or `Resume` -- every `must_haves` truth was already satisfied by Plan 01-01's implementation. This plan is purely additive test coverage (all three new/extended commits are `test(...)`) plus the one accepted-debt comment.

## Deviations from Plan

None - plan executed exactly as written. No bugs were exposed in `server.py` by any of the new tests, so step 1's conditional fix clause in both tasks' `<action>` was not triggered.

## Issues Encountered

None. `TestControlCommandsOverGrpc`'s class-wide `tearDown` invariant (`pause`/`resume`/`abort` call_count `<= 1`) required calling `self.service.reset_mock()` at the top of every `subTest` iteration in the two multi-case tests (`test_blank_or_unclear_decisions_are_invalid_arguments_through_the_control_path` and `test_control_commands_never_check_instrument_state`) so only the final iteration's call counts are live when `tearDown` runs -- this is noted as an established pattern above, not a deviation, since it was anticipated by the plan's own "reset the mock between cases" instruction.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 1's control-path error states and edge cases (Resume's two paths, lock-free Pause/Abort, fail-closed decisions, no instrument-state reads) are now fully pinned by tests, ready for Plan 01-03 (`StatusReply.run_state`) to build on this base without re-litigating these guarantees.
- No blockers. `tools/base_server.py` remains untouched (verified via `git diff --exit-code 9c27896 -- tools/base_server.py`).

---
*Phase: 01-adapter-control-path-run-state*
*Completed: 2026-10-12*

## Self-Check: PASSED

- `tools/fast/server.py` exists on disk
- `tools/tests/fast_test.py` exists on disk
- `5bcb812` (Task 1 commit) is an ancestor of HEAD
- `e42dd45` (Task 2 commit) is an ancestor of HEAD
- All task `<acceptance_criteria>` re-verified passing (grep checks for both tasks all exited 0)
- Full gate (`bin/make proto test`: ruff, mypy, 90 unittest cases) green at HEAD `e42dd45`
- `git diff --exit-code 9c27896 -- tools/base_server.py` exits 0 (never edited)
