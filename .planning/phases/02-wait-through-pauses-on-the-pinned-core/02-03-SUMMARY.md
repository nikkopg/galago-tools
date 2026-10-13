---
phase: 02-wait-through-pauses-on-the-pinned-core
plan: 03
subsystem: adapter
tags: [fast-mcp, unittest, grpc, abort, run-control]

# Dependency graph
requires:
  - phase: 02-wait-through-pauses-on-the-pinned-core
    plan: 01
    provides: "fast-mcp re-pinned to b30b38d; Transfer/RunProtocol wired with
      on_pause=self._record_pause, through_pauses=True; real-core gRPC test
      fixture (_real_core, _stub_transport, _Stepper, _RealCoreGrpcTestCase)"
  - phase: 02-wait-through-pauses-on-the-pinned-core
    plan: 02
    provides: "TestRequirementsPin gate tests proving the installed core
      exposes the wait-through-pauses capability and state gates"
provides:
  - "_run_record['operator_abort'] flag: False in __init__ and the
     _run_in_flight 0->1 reset, set True inline by Abort only on an
     accepted abort (errorCode 0), under _run_state_lock"
  - "_message_for(result, expected_tray_id, operator_abort=False) stays
     pure; the Aborted branch reads 'run aborted by operator at <p>%' only
     when the flag is True, appending the instrument error only when there
     is one; every other branch (Paused/TimedOut/Cancelled) is unchanged"
  - "Transfer/RunProtocol read the flag once under _run_state_lock inside
     their _run_in_flight block and pass it through _result_reply; the
     crash-recovery Resume wait passes none (stale-flag protection)"
  - "TestOperatorAbortWording (5 unit tests) and TestOperatorAbortRealCore
     (3 real-core gRPC tests) proving the wording and the real-core
     behaviour end to end"
affects: ["02-04 (paused-time-excluded-from-timeout tests)",
  "galago-core (the queue shows this text verbatim and moves to FAILED on
   it, design 6.6)"]

# Actuals (#2632)
actuals:
  tokens: 5796
  tasks: 2
  commits: 2
  plan_head_before: d89d62cdc1ad0d6ef9a579b65962f06df70e714b
  plan_head_after: 880cd16a2f90b459a597290eeaad95849bdfafe6

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "A record-only flag set inline inside an existing control method
       (Abort), read once by the methods that need it (Transfer/
       RunProtocol), rather than a new helper function -- keeps the D-17
       no-new-FunctionDef invariant satisfied with no new record-only rule
       needed"

key-files:
  created: []
  modified:
    - tools/fast/server.py
    - tools/tests/fast_test.py

key-decisions:
  - "D-09 scope (planner choice, recorded in the plan's must_haves): the
     crash-recovery Resume's wait passes no operator_abort flag, because
     that wait is not bracketed by _run_in_flight -- a flag left by an
     earlier Abort could be stale there, and blaming the operator on stale
     state would misattribute the error (Core Value: the operator sees
     what the instrument did)"
  - "The real-core proof's call-count shape was derived directly from
     fast_mcp.orchestration.poll_run and fast_mcp.service's _require_state:
     exactly one get_status() per poll iteration (no debounce on pause
     detection -- the core's own in_episode tracking de-duplicates on_pause
     across repeated identical paused reads) and one more per pause/resume/
     abort state-gate check, confirmed by reading the installed core's
     source before writing the three real-core tests' status side-effect
     lists, so they are a first-try match for the plan's specified traces"

requirements-completed: [LIVE-02]

coverage:
  - id: D1
    description: "An Aborted result reads 'run aborted by operator at <p>%'
      only when this adapter's own Abort was accepted for the run in
      flight; any other abort (rejected, refused, transport error, no run
      in flight, instrument-side) keeps the instrument's plain wording;
      TimedOut/Cancelled/Paused are unaffected by the flag"
    requirement: "LIVE-02"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestOperatorAbortWording.test_message_for_names_the_operator_only_when_the_flag_is_set"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestOperatorAbortWording.test_timed_out_cancelled_and_paused_text_ignores_the_flag"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestOperatorAbortWording.test_only_an_accepted_abort_sets_the_flag"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestOperatorAbortWording.test_a_new_run_starts_with_the_flag_cleared"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestOperatorAbortWording.test_an_abort_accepted_mid_run_reaches_the_steps_message"
        status: pass
    human_judgment: false
  - id: D2
    description: "Over the real core and a stub transport, reached through
      the real gRPC stub: an operator Abort of a paused Transfer ends 'run
      aborted by operator at 40%' with the transport's abort called once
      and pause/resume never; an instrument-side abort with no Abort sent
      keeps 'run aborted at 40%: WrongPlateType (-645)'; an operator abort
      on one run never carries into the next Transfer's result"
    requirement: "LIVE-02"
    verification:
      - kind: integration
        ref: "tools/tests/fast_test.py#TestOperatorAbortRealCore.test_operator_abort_while_paused_ends_the_step_aborted_by_operator"
        status: pass
      - kind: integration
        ref: "tools/tests/fast_test.py#TestOperatorAbortRealCore.test_instrument_side_abort_keeps_the_instruments_wording"
        status: pass
      - kind: integration
        ref: "tools/tests/fast_test.py#TestOperatorAbortRealCore.test_operator_abort_on_one_run_is_not_carried_into_the_next"
        status: pass
    human_judgment: false
  - id: D3
    description: "D-17: no new FunctionDef added to server.py since the
      phase started, and the invariant rule sets (_SCOPED_ATTRS,
      _RECORD_ONLY_FUNCTIONS, _STATUS_READERS, _CONTROL_PATH_FUNCTIONS,
      _COMMANDING_NAMES) are unchanged -- Abort still calls only .abort on
      the service"
    requirement: "LIVE-02"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestAdapterInvariant.test_adapter_obtains_service_only_through_open_service"
        status: pass
      - kind: other
        ref: "AST diff of server.py FunctionDef names against c9a89cf (acceptance criterion, both tasks)"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-10-13
status: complete
---

# Phase 2 Plan 3: Operator-abort wording and real-core proof Summary

**`_run_record["operator_abort"]`, set inline by `Abort` only on an accepted abort and cleared by every new run, makes an `Aborted` step read "run aborted by operator at `<p>`%" exactly when this adapter's own `Abort` caused it — proven both at the unit level (`_message_for`) and end to end over the real fast-mcp core through the real gRPC stub.**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-10-13T15:00:00Z
- **Completed:** 2026-10-13T15:25:00Z
- **Tasks:** 2 completed
- **Files modified:** 2

## Accomplishments
- `tools/fast/server.py`: `_NO_ERROR_TEXT = "no error reported"` backs
  `_outcome_text`'s fallback and the Aborted branch's "is there a real
  error" comparison as one shared string.
- `_run_record` gains `"operator_abort": False` in `FastServer.__init__`
  and in `_run_in_flight`'s 0->1 reset literal (the only two places that
  set it `False`, confirmed by AST).
- `Abort` sets `self._run_record["operator_abort"] = True` inline, under
  `_run_state_lock`, only when the instrument accepts (`errorCode == 0`) —
  the only function that sets the flag `True` (confirmed by AST). No new
  helper method was added (D-17).
- `_message_for(result, expected_tray_id, operator_abort=False)` stays a
  pure function (no `self` access, confirmed by AST): the `Aborted` branch
  reads `"run aborted by operator at {percent}%"` when the flag is `True`,
  appending `": {outcome}"` only when the outcome text is not
  `_NO_ERROR_TEXT`; `False` (or the argument omitted) keeps the unchanged
  plain wording. Every other branch (`Paused`, `TimedOut`, `Cancelled`) is
  untouched and the flag has no effect on them.
- `_result_reply` forwards `operator_abort` to `_message_for`.
  `Transfer`/`RunProtocol` read the flag once, under `_run_state_lock`,
  inside their `_run_in_flight` block (after the transport-error catch but
  before returning), so a mid-run operator abort reaches that same step's
  own result. The crash-recovery `Resume`'s wait passes no flag — that wait
  is not bracketed by `_run_in_flight`, so a flag left over from an earlier
  `Abort` could be stale (planner choice, recorded in the plan's
  `must_haves`).
- `TestOperatorAbortWording` (5 tests, `tools/tests/fast_test.py`): the five
  exact wording strings for both flag states with and without an
  instrument error; `TimedOut`/`Cancelled`/`Paused` text is byte-identical
  with the flag `True` or `False`; only an accepted `Abort` sets the flag
  (rejected, missing `errorCode`, `Refused`, a transport error, a blank
  decision, an accepted `Pause`, and an accepted in-flight `Resume` all
  leave it `False`); a new run always starts with the flag cleared even
  after a prior no-run-in-flight `Abort`; and a mid-run operator `Abort`
  (for both `Transfer` and `RunProtocol`) reaches that step's own `Aborted`
  result with the exact wording, while a mid-run *rejected* abort keeps the
  instrument wording.
- `_aborted(percent, error_code=None)` test helper next to `_running`, and
  `TestOperatorAbortRealCore` (3 tests) over the real core and a stub
  transport, reached through the real in-process gRPC stub:
  - an operator `Abort` (`return_liquid="no"`) sent while a `Transfer` is
    paused returns `SUCCESS`, calls the transport's `abort` once with
    `return_liquid=False`, never touches `pause`/`resume`, and the step
    ends `ERROR_FROM_TOOL` with exactly `"run aborted by operator at 40%"`
    (meta kind `"aborted"`);
  - an instrument-side abort with no `Abort` sent ends exactly
    `"run aborted at 40%: WrongPlateType (-645)"`, with `pause`/`resume`/
    `abort` never called;
  - an operator abort on one `Transfer` (`"run aborted by operator at
    30%"`) never carries into the next `Transfer`'s result (`"run aborted
    at 50%: no error reported"`), with `abort.call_count == 1` across both
    runs.
- `TestAdapterInvariant` re-run unchanged, and both tasks' AST acceptance
  criteria confirm the invariant rule sets (`_SCOPED_ATTRS`,
  `_RECORD_ONLY_FUNCTIONS`, `_STATUS_READERS`, `_CONTROL_PATH_FUNCTIONS`,
  `_COMMANDING_NAMES`) and the set of `FunctionDef` names in `server.py`
  are byte-identical to `c9a89cf` — no new function, no new rule needed
  (D-17, Pitfall 6).

## Task Commits

Each task was committed atomically:

1. **Task 1: Operator-abort flag and wording** - `8a4a6fa` (feat)
2. **Task 2: Real-core proof over gRPC** - `880cd16` (test)

**Plan metadata:** pending (this SUMMARY's own commit)

## Files Created/Modified
- `tools/fast/server.py` - `_NO_ERROR_TEXT`; `_run_record["operator_abort"]`;
  `Abort` sets it inline on an accepted abort; `_message_for`/`_result_reply`
  take `operator_abort`; `Transfer`/`RunProtocol` read and pass it;
  `Resume` docstring notes the crash-recovery wait passes none
- `tools/tests/fast_test.py` - `_message_for` added to the guarded import;
  `TestOperatorAbortWording` (5 tests); `_aborted` helper;
  `TestOperatorAbortRealCore` (3 real-core gRPC tests)

## Decisions Made
See `key-decisions` in frontmatter: the crash-recovery Resume's scope
exclusion (planner choice, D-09), and the call-count derivation method for
the real-core tests (read `fast_mcp.orchestration.poll_run` and
`fast_mcp.service`'s `_require_state`/`ResumeMarker.read` before writing
the status side-effect lists — one `get_status()` per poll iteration, one
more per pause/resume/abort state-gate check, confirmed by all three new
real-core tests passing on the first run).

## Observed RED Failures (Task 1, before implementation)

Per the plan's TDD requirement, the full `TestOperatorAbortWording` class
was run against `tools/fast/server.py` and `tools/tests/fast_test.py`
exactly as committed in Task 2's prerequisite state (before any Task 1
production-code change — `_message_for` already existed without the new
parameter and `_run_record` had no `operator_abort` key):

```
======================================================================
ERROR: test_a_new_run_starts_with_the_flag_cleared (tools.tests.fast_test.TestOperatorAbortWording)
----------------------------------------------------------------------
KeyError: 'operator_abort'

======================================================================
ERROR: test_message_for_names_the_operator_only_when_the_flag_is_set (tools.tests.fast_test.TestOperatorAbortWording)
----------------------------------------------------------------------
TypeError: _message_for() got an unexpected keyword argument 'operator_abort'

======================================================================
ERROR: test_only_an_accepted_abort_sets_the_flag (tools.tests.fast_test.TestOperatorAbortWording)
----------------------------------------------------------------------
KeyError: 'operator_abort'

======================================================================
ERROR: test_timed_out_cancelled_and_paused_text_ignores_the_flag (tools.tests.fast_test.TestOperatorAbortWording) (kind='TimedOut'|'Cancelled'|'Paused')
----------------------------------------------------------------------
TypeError: _message_for() got an unexpected keyword argument 'operator_abort'

======================================================================
FAIL: test_an_abort_accepted_mid_run_reaches_the_steps_message (tools.tests.fast_test.TestOperatorAbortWording) (command='Transfer'|'RunProtocol')
----------------------------------------------------------------------
AssertionError: 'run aborted at 40%: no error reported' != 'run aborted by operator at 40%'

----------------------------------------------------------------------
Ran 31 tests in 0.787s

FAILED (failures=2, errors=6)
```

**Semantic assessment:** every failure traces to the planned behavior
change, not a fixture/import/setup defect — `TypeError` on the unknown
`operator_abort` keyword (the parameter did not exist yet), `KeyError` on
the missing `_run_record` key (the flag did not exist yet), and an
`AssertionError` where the old plain wording appeared instead of the new
operator wording. This is valid RED evidence for the behavior under test.
After the GREEN implementation (described above), the same 31 tests all
pass (see Task Commits).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] mypy type error on `set(Optional[dict])`**
- **Found during:** Task 1, running the full gate after the first GREEN pass
- **Issue:** `set(self.server._build_run_state())` failed mypy because
  `_build_run_state()` returns `Optional[dict[str, Any]]`, and `set()`
  requires a non-`None` `Iterable`.
- **Fix:** Bound the result to a local, asserted it is not `None`, then
  called `set()` on the local — the test's own precondition (a run is in
  flight) already guarantees a non-`None` return; the `assert` documents
  that guarantee for the type checker.
- **Files modified:** `tools/tests/fast_test.py`
- **Verification:** `mypy --config-file=pyproject.toml tools` reports 0
  errors; the full gate passes.
- **Committed in:** `8a4a6fa` (part of Task 1's commit)

---

**Total deviations:** 1 auto-fixed (1 bug).
**Impact on plan:** Necessary for the mypy gate; no scope creep — the fix
is local to one test helper closure and changes no assertion.

## Issues Encountered
None. Both tasks' real-core status-sequence designs (derived from reading
the installed `fast_mcp.orchestration.poll_run` and `fast_mcp.service`
source before writing the tests) matched the actual `get_status` call
counts on the first run — no trial-and-error adjustment was needed.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto
  test` exits 0 with 134 unittest tests (up from 126 after 02-02; 5 from
  Task 1's `TestOperatorAbortWording`, 3 from Task 2's
  `TestOperatorAbortRealCore`).
- `git diff --exit-code c9a89cf -- tools/base_server.py` exits 0
  (unchanged).
- `git log --oneline -2` shows `880cd16` (real-core abort test commit) then
  `8a4a6fa` (wording commit) — most-recent-first, matching the plan's
  required order (wording commit, then real-core abort test commit).
- ROADMAP Phase 2 success criterion 3's first half ("an operator abort ends
  the step 'run aborted by operator at `<p>`%'") is done. The second half
  ("a timeout still never aborts") is 02-04's job, with the injected clock.
- No blockers for 02-04 (paused-time-excluded-from-timeout tests).

---
*Phase: 02-wait-through-pauses-on-the-pinned-core*
*Completed: 2026-10-13*

## Self-Check: PASSED

- FOUND: tools/fast/server.py
- FOUND: tools/tests/fast_test.py
- FOUND: 8a4a6fa (Task 1)
- FOUND: 880cd16 (Task 2)
- `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto test` re-run: exit 0,
  134 unittest tests passed
- `git diff --exit-code c9a89cf -- tools/base_server.py` exits 0
- Every acceptance criterion from both tasks verified to pass (see commit history and the
  acceptance-criteria commands run before each commit)
