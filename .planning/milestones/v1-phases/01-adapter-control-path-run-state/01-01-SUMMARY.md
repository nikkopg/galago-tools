---
phase: 01-adapter-control-path-run-state
plan: 01
subsystem: api
tags: [grpc, protobuf, fast-adapter, concurrency, threading]

# Dependency graph
requires: []
provides:
  - "fast.Command.Pause message and oneof field pause = 10 (soft-only, D5)"
  - "FastServer.Pause() / EstimatePause(), mapped through _recovery_reply"
  - "MOTION_LOCK_COMMANDS and CONTROL_COMMANDS frozensets (replaces dead MOTION_COMMANDS)"
  - "FastServer.ExecuteCommand override: pause/resume/abort bypass base_server's
    isReady/setStatus gate and reach a run in flight"
  - "Lock-free Abort; two-path Resume (crash-recovery wait vs in-flight no-wait)"
  - "TestControlCommandsOverGrpc: real in-process gRPC test class for the control path"
affects: [01-02, 01-03, 01-04, 01-05]

# Actuals (#2632)
actuals:
  tokens: 7180
  tasks: 3
  commits: 3

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "ExecuteCommand override discriminates by WhichOneof(tool_command)/WhichOneof(command)
      instead of arity, following the existing GetStatus dual-dispatch idiom"
    - "Non-blocking threading.Lock.acquire(blocking=False) as an in-flight signal for Resume's
      two-path split (bookkeeping about adapter threads, never an instrument-state check)"
    - "Real in-process gRPC server + MagicMock(spec=FastService) injected directly onto the
      server instance, composed with a threading.Event-blocked side_effect to drive
      base_server's actual ExecuteCommand gate from a test"

key-files:
  created: []
  modified:
    - interfaces/tools/grpc_interfaces/fast.proto
    - tools/fast/server.py
    - tools/tests/fast_test.py

key-decisions:
  - "D-05: Pause {} has no fields (soft-only); FastServer.Pause() calls
    service.pause(hard=False) with hard as an explicit keyword"
  - "D-01/D-02/D-03: ExecuteCommand override checks tool_command==self.toolType and the inner
    oneof in CONTROL_COMMANDS before parseCommand; dispatches through
    self._dispatchCommand(command) so _check_args still runs; everything else falls through to
    super().ExecuteCommand unchanged"
  - "D-06: Pause and Abort never touch _motion_lock; MOTION_LOCK_COMMANDS and CONTROL_COMMANDS
    replace the dead, misleadingly-named MOTION_COMMANDS"
  - "D-07: Resume branches on a non-blocking _motion_lock.acquire() -- acquired is crash
    recovery (unchanged wait-under-lock behavior), not acquired is in-flight (resume, return on
    acceptance, no wait, no lock release)"
  - "D-04/ADP-08: the real-mode concurrency test was written and committed first as an expected
    failure (observed 6 != 1, NOT_READY from base_server's isReady() gate), then the override
    made it an ordinary passing test -- never a throwaway, same class extended in place"
  - "Deviation: deferred adding the BUSY import to tool_base_pb2's import list until Task 2 (its
    first user) instead of Task 1 as literally sequenced in the plan, to keep Task 1's commit
    ruff-clean (F401 unused import) -- scope and test content are unchanged, only which commit
    introduces the import line"

requirements-completed: [ADP-01, ADP-02, ADP-03, ADP-08]

coverage:
  - id: D1
    description: "A Pause sent over the real gRPC stub to a READY real-mode tool reaches
      FastService.pause(hard=False) exactly once and returns SUCCESS (ADP-01)"
    requirement: "ADP-01"
    verification:
      - kind: integration
        ref: "tools/tests/fast_test.py#TestControlCommandsOverGrpc.test_pause_over_grpc_reaches_service_as_soft_pause"
        status: pass
    human_judgment: false
  - id: D2
    description: "Pause, Resume and Abort sent through the stub while a Transfer is blocked each
      reach the mocked service exactly once; health stays BUSY after each; status returns to
      READY only via the Transfer's own base_server finally (ADP-02, ADP-03, ADP-08)"
    requirement: "ADP-02"
    verification:
      - kind: integration
        ref: "tools/tests/fast_test.py#TestControlCommandsOverGrpc.test_pause_resume_abort_reach_service_while_transfer_in_flight"
        status: pass
    human_judgment: false
  - id: D3
    description: "Transfer, RunProtocol, ScanTips and EjectTray are still refused NOT_READY while
      another motion command holds the lock; the motion-lock and control-command name sets stay
      disjoint"
    requirement: "ADP-03"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestMotionSerialization.test_second_motion_command_refused_while_first_in_flight"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestMotionSerialization.test_motion_lock_and_control_command_sets_are_disjoint"
        status: pass
    human_judgment: false
  - id: D4
    description: "The real-mode concurrency test was observed failing for the right reason
      (NOT_READY from base_server's readiness gate) before the override existed, proving the
      test exercises the actual gate rather than passing trivially"
    requirement: "ADP-08"
    verification:
      - kind: unit
        ref: "manual pre-commit run, quoted verbatim below in Task Commits"
        status: pass
    human_judgment: false

duration: 45min
completed: 2026-10-13
status: complete
---

# Phase 1 Plan 1: Adapter Control Path Tracer Summary

**Pause/Resume/Abort reach a F.A.S.T. run in flight through a new `FastServer.ExecuteCommand`
override that bypasses `base_server`'s readiness gate for exactly those three commands, proven by
a real-mode gRPC concurrency test that was first seen failing against the unmodified gate.**

## Performance

- **Duration:** 45 min
- **Started:** 2026-10-13T04:38:00Z
- **Completed:** 2026-10-13T04:46:00Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- Soft-only `Pause` command wired end to end from the gRPC wire (`fast.proto`'s new `Pause {}`
  oneof field 10) through `FastServer.Pause()` to `FastService.pause(hard=False)`
- `FastServer.ExecuteCommand` override routes `pause`/`resume`/`abort` past `base_server`'s
  `isReady`/`setStatus` bracket while still running `_check_args` via `_dispatchCommand`, and
  falls through to `super().ExecuteCommand` for everything else -- `tools/base_server.py` is
  byte-identical to commit `9c27896`
- `Abort` dropped the motion-lock acquire/release entirely; `Resume` now branches on a
  non-blocking `_motion_lock.acquire()` into a crash-recovery wait-under-lock path (lock
  acquired) and an in-flight no-wait path (lock not acquired, never releases a lock it didn't
  take)
- `TestControlCommandsOverGrpc`, a new real in-process gRPC test class, proves the whole path: a
  blocked `Transfer` holds the tool BUSY while Pause/Resume/Abort each reach the mocked
  `FastService` exactly once and the health RPC still reports BUSY; releasing the Transfer
  returns the tool to READY through its own `base_server` `finally`

## Task Commits

Each task was committed atomically:

1. **Task 1: Pause end to end, from the gRPC wire to FastService.pause(hard=False)** - `46aff8b` (feat)
2. **Task 2: Failing real-mode concurrency test through the gRPC stub, committed as an expected failure (D-04)** - `3c59c7c` (test)
3. **Task 3: FastServer.ExecuteCommand control path, lock-free Pause/Abort, two-path Resume** - `bd41ae0` (feat)

_No separate plan-metadata commit required by this plan's task structure; all three commits above
are task-level production commits per the plan's own numbering._

### Task 2's observed pre-override failure (quoted verbatim, per the plan's `<output>` requirement)

Run without the `@unittest.expectedFailure` decorator, before any `ExecuteCommand` override
existed:

```
FAIL: test_pause_resume_abort_reach_service_while_transfer_in_flight (tools.tests.fast_test.TestControlCommandsOverGrpc)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "tools/tests/fast_test.py", line 379, in test_pause_resume_abort_reach_service_while_transfer_in_flight
    self.assertEqual(reply.response, SUCCESS, reply.error_message)
AssertionError: 6 != 1 :

----------------------------------------------------------------------
Ran 1 test in 0.009s

FAILED (failures=1)
```

`6` is `tool_base_pb2.NOT_READY`, `1` is `tool_base_pb2.SUCCESS` -- exactly the NOT_READY reply
`base_server.parseCommand`'s `isReady()` gate returns while the blocked Transfer holds the tool
BUSY (`base_server.py:203-204`), as predicted by D-04 and RESEARCH.md Pitfall 6. The decorator was
then restored and the suite confirmed `OK (expected failures=1)` before committing.

## Files Created/Modified
- `interfaces/tools/grpc_interfaces/fast.proto` - adds `message Pause {}` and oneof field `pause = 10`
- `tools/fast/server.py` - `EST_PAUSE_S`, `COMMAND_TO_SERVICE_METHOD["Pause"]`, `FastServer.Pause()`/`EstimatePause()`, `MOTION_LOCK_COMMANDS`/`CONTROL_COMMANDS` (replacing dead `MOTION_COMMANDS`), the `ExecuteCommand` override, lock-free `Abort`, two-path `Resume`
- `tools/tests/fast_test.py` - `TestControlCommandsOverGrpc` (tracer + concurrency test), `TestAdapterInvariant`'s `.pause` scoping, extended `TestOneToOneSurface`/`TestEstimates`/`TestNotConfigured`/`TestCheckArgs`, `TestMotionSerialization` updates

## Decisions Made

- **D-05** (Pause is soft-only, no fields): implemented exactly as specified; `hard=False` passed
  as an explicit keyword, asserted with `assert_called_once_with(hard=False)`.
- **D-01/D-02/D-03** (ExecuteCommand override): implemented exactly as specified, including the
  `getattr(fast_command, field_name)` indirection (never a literal attribute access) so the
  AST invariant's scoped-attribute check still holds.
- **D-06/D-07** (lock changes): implemented exactly as specified; the Resume anti-pattern flagged
  in RESEARCH.md (reusing the acquire-or-NOT_READY idiom) was avoided.
- **EST_PAUSE_S = 1** (read-sized, per CONTEXT.md "Claude's Discretion" note; RESEARCH.md's Open
  Question 2 leaned toward `EST_ABORT_S`, but CONTEXT.md's own text explicitly reads
  `EST_READ_S`-sized first and the plan's `<action>` names `EST_PAUSE_S = 1` directly, so the plan's
  explicit value took precedence over the research's softer recommendation).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Deferred the `BUSY` import to Task 2 instead of Task 1**
- **Found during:** Task 1 (verification gate)
- **Issue:** The plan's Task 1 action step 4 says to add `BUSY` to the `tool_base_pb2` constant
  import "at module top" in the same bullet as `empty_pb2`. `BUSY` has no consumer until Task 2's
  concurrency test; adding it in Task 1's commit left it unused, and `ruff check` fails the gate
  with `F401 BUSY imported but unused` (the project runs `ruff check .` with no ignore for
  unused imports).
- **Fix:** Added `empty_pb2` in Task 1 as planned (it is used immediately by `_health()`), and
  moved the `BUSY` import to Task 2's commit, where `test_pause_resume_abort_reach_service_while_transfer_in_flight`
  first references it. No behavior or test content changed, only which commit introduces the
  import line.
- **Files modified:** tools/tests/fast_test.py
- **Verification:** `bash bin/make proto test` green at every commit (71 tests after Task 1, 71
  tests + 1 expected failure after Task 2, 73 tests after Task 3); `ruff check .` clean throughout.
- **Committed in:** 46aff8b (import omitted), 3c59c7c (import added, first used)

---

**Total deviations:** 1 auto-fixed (1 blocking/lint).
**Impact on plan:** Purely a commit-sequencing adjustment to keep every commit gate-green per the
plan's own "every commit in the plan leaves the gate green" success criterion; no change to the
shipped behavior, test coverage, or public surface described anywhere else in this plan.

## Issues Encountered

None beyond the deviation above.

## Known Stubs

None - no stub patterns introduced. `EstimateResume` remains the pre-existing flat 15s
placeholder (accepted debt, unchanged by this plan per CONTEXT.md "Claude's Discretion").

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The control path (`ExecuteCommand` override, `CONTROL_COMMANDS`, `MOTION_LOCK_COMMANDS`) and
  `Pause`/lock-free `Abort`/two-path `Resume` are in place and gate-green, ready for Plan 01-02
  (motion-lock bypass tests and `INVALID_ARGUMENTS` coverage through the override path) and Plan
  01-03 (`run_state` reporting, which reads `_log_progress` and the long-running-command
  boundary this plan established).
- `tools/base_server.py` confirmed byte-identical to commit `9c27896` throughout (no edits made,
  verified via `git diff --exit-code` at every task).
- No blockers. The phase-wide symbol inventory's 01-01 rows (`fast.Command.Pause`,
  `EST_PAUSE_S`, `COMMAND_TO_SERVICE_METHOD["Pause"]`, `MOTION_LOCK_COMMANDS`,
  `CONTROL_COMMANDS`, `FastServer.Pause`/`EstimatePause`/`ExecuteCommand`, modified
  `Abort`/`Resume`, `TestControlCommandsOverGrpc`) are all present under the exact names the
  plan's artifact table specifies, for 01-02 through 01-05 to build on.

## Self-Check: PASSED

- FOUND: interfaces/tools/grpc_interfaces/fast.proto
- FOUND: tools/fast/server.py
- FOUND: tools/tests/fast_test.py
- FOUND: 46aff8b (ancestor of HEAD)
- FOUND: 3c59c7c (ancestor of HEAD)
- FOUND: bd41ae0 (ancestor of HEAD)

---
*Phase: 01-adapter-control-path-run-state*
*Completed: 2026-10-13*
