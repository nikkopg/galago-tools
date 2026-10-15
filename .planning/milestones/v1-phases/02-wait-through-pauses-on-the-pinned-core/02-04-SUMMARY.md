---
phase: 02-wait-through-pauses-on-the-pinned-core
plan: 04
subsystem: adapter
tags: [fast-mcp, unittest, pause-resume, timeout, run-control]

# Dependency graph
requires:
  - phase: 02-wait-through-pauses-on-the-pinned-core
    plan: 01
    provides: "fast-mcp re-pinned to b30b38d; Transfer/RunProtocol wired with
      on_pause=self._record_pause, through_pauses=True; real-core gRPC test
      fixture (_real_core, _stub_transport)"
  - phase: 02-wait-through-pauses-on-the-pinned-core
    plan: 03
    provides: "operator-abort wording and _aborted test helper; real-core
      gRPC proof pattern used by TestOperatorAbortRealCore"
provides:
  - "_no_sleep/_fake_clock test helpers for pacing the real core's poll loop
     on an injected clock with no wall-clock cost"
  - "TestPausedTimeExcludedFromTimeout (6 tests) proving on the real core:
     a Transfer paused far past its timeout still ends SUCCESS, the same
     time spent running times out with no control call, the timeout
     threshold is inclusive at poll granularity, paused time is excluded
     at poll granularity, RunProtocol's per-command timeout behaves the
     same way, and two pause episodes record exactly two pauses"
  - "D-12 AST acceptance proves the adapter still owns no clock of its own"
affects: ["Phase 3 (deploy and live acceptance; this closes ROADMAP Phase 2
  success criteria 3 and 4)"]

# Actuals (#2632)
actuals:
  tokens: 2228
  tasks: 2
  commits: 2
  plan_head_before: d24b31dc0da5f95a61b8d9e74e8a6b6d21426685
  plan_head_after: 248fed89565a6ab9d1ea8c412dfca1d2cd53c2cd

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Fake clock closure (_fake_clock) injected into the real FastService
       alongside a no-op sleep (_no_sleep), so a timeout proof on the real
       core takes no wall-clock time and every clock call is deterministic"

key-files:
  created: []
  modified:
    - tools/tests/fast_test.py

key-decisions:
  - "Split the plan's single test class across two commits by editing then
     reverting the Task-2-only members (_run_protocol and its two tests)
     before Task 1's commit, then re-adding them for Task 2 -- the plan
     specifies one commit per task even though both tasks touch the same
     class in the same file"
  - "Each _transfer/_run_protocol call builds a fresh FastService with its
     own _fake_clock(1.0), so every poll sequence in every test (and every
     subTest) starts its clock at 0, matching the interface note's traces
     exactly"

requirements-completed: [LIVE-03, LIVE-02]

coverage:
  - id: D1
    description: "A Transfer paused far longer than its 6.0s timeout still
      ends SUCCESS (kind ran), with the pause recorded once and no control
      call; the same clock units spent running instead end TimedOut with
      the unaborted-instrument message and no control call either way"
    requirement: "LIVE-03"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestPausedTimeExcludedFromTimeout.test_a_pause_far_longer_than_the_timeout_still_ends_success"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestPausedTimeExcludedFromTimeout.test_the_same_time_running_times_out_and_never_commands_the_instrument"
        status: pass
    human_judgment: false
  - id: D2
    description: "The timeout threshold is inclusive at poll granularity (5
      running polls then idle/done end SUCCESS, 6 end TimedOut) and paused
      time is excluded at the same granularity (20 paused + 4 running end
      SUCCESS, 20 paused + 5 running end TimedOut)"
    requirement: "LIVE-03"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestPausedTimeExcludedFromTimeout.test_the_timeout_threshold_is_inclusive_one_poll_either_side"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestPausedTimeExcludedFromTimeout.test_paused_time_is_excluded_at_poll_granularity"
        status: pass
    human_judgment: false
  - id: D3
    description: "RunProtocol's per-command timeout_s (Config.run_timeout_s
      0) excludes paused time exactly like Transfer's Config-sourced
      timeout, with no control call either way"
    requirement: "LIVE-03"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestPausedTimeExcludedFromTimeout.test_run_protocol_per_command_timeout_excludes_paused_time"
        status: pass
    human_judgment: false
  - id: D4
    description: "Two pauses separated by a running reading record two
      distinct pause episodes (one per episode, core S4), and the step
      still ends SUCCESS"
    requirement: "LIVE-02"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestPausedTimeExcludedFromTimeout.test_each_pause_episode_records_once"
        status: pass
    human_judgment: false
  - id: D5
    description: "The adapter adds no timer, clock or deadline logic of its
      own (D-12): server.py imports no time module, uses no
      monotonic/perf_counter/sleep attribute access and no deadline name"
    requirement: "LIVE-03"
    verification:
      - kind: other
        ref: "AST acceptance criterion over tools/fast/server.py (Task 1)"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-10-13
status: complete
---

# Phase 2 Plan 4: Paused time excluded from the run timeout on the real core Summary

**`TestPausedTimeExcludedFromTimeout` (6 tests) proves on the real fast-mcp core with an injected fake clock: a Transfer paused far longer than its 6.0s timeout still ends SUCCESS, the same time spent running ends TimedOut without ever commanding the instrument, the timeout threshold and the paused-time exclusion are both pinned at poll granularity, RunProtocol's per-command timeout behaves identically, and two separate pause episodes record exactly two pauses — all while the adapter (`tools/fast/server.py`) is proven by AST to own no clock of its own.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-10-13T12:32:00Z
- **Completed:** 2026-10-13T12:47:00Z
- **Tasks:** 2 completed
- **Files modified:** 1

## Accomplishments
- `_no_sleep(_seconds)` and `_fake_clock(step)` test helpers next to `_real_core`:
  a no-op sleep and a clock closure (ported from fast-mcp's
  `tests/test_pause_control.py`, not importable from this fork) that adds
  `step` on each call and returns the running total, so a real-core timeout
  proof takes no wall-clock time and every call is deterministic.
- `TestPausedTimeExcludedFromTimeout(unittest.TestCase)`, after
  `TestOperatorAbortRealCore`, with `_transfer`/`_run_protocol` helpers that
  each build a fresh real `FastService` (stub transport, `_no_sleep`,
  `_fake_clock(1.0)`) per call, and `_assert_no_control_calls`:
  - `test_a_pause_far_longer_than_the_timeout_still_ends_success` (D-13): 20
    live-paused polls (20 clock units, over three times the 6.0 timeout) end
    SUCCESS kind `ran`, `_record_pause` called exactly once, no control call.
  - `test_the_same_time_running_times_out_and_never_commands_the_instrument`
    (D-13 control, D-16, D-11): the same 20 clock units spent running end
    `ERROR_FROM_TOOL` kind `timedOut` with "the instrument run was NOT
    aborted" in the message, no control call.
  - `test_the_timeout_threshold_is_inclusive_one_poll_either_side` (LIVE-03
    boundary): 5 running polls then idle/done is SUCCESS; 6 running polls is
    kind `timedOut`; no control calls in either subTest.
  - `test_paused_time_is_excluded_at_poll_granularity` (LIVE-03 precision):
    20 paused + 4 running polls then idle/done is SUCCESS; the same with 5
    running polls is kind `timedOut`; no control calls in either subTest.
  - `test_run_protocol_per_command_timeout_excludes_paused_time` (LIVE-03):
    `RunProtocol(csv=EXAMPLE1_CSV, timeout_s=6.0)` with `Config.run_timeout_s`
    0 behaves identically — 20 paused polls end SUCCESS kind `ran`, 20
    running polls end kind `timedOut`, no control call either way.
  - `test_each_pause_episode_records_once` (LIVE-02/D-06): a Transfer with
    two separate 3-poll paused episodes (separated by a running reading)
    ends SUCCESS kind `ran`, `_record_pause` called exactly twice, first at
    10% then at 20% (one record per episode, core S4), no control call.
- D-12 AST acceptance (Task 1): `tools/fast/server.py` imports no `time`
  module, uses no `monotonic`/`perf_counter`/`sleep` attribute access, and no
  `deadline`/`monotonic`/`perf_counter` name — the adapter's whole part in
  the timeout remains `through_pauses=True` plus the `timeout_s` it already
  forwarded (confirmed by `git diff --exit-code` against the plan's recorded
  baseline SHA after each commit).
- No production code changed: `tools/fast/server.py` and
  `tools/base_server.py` are both untouched by this plan (test-only, as the
  plan required).

## Task Commits

Each task was committed atomically:

1. **Task 1: A Transfer paused far longer than its timeout ends SUCCESS; the same time running times out without commanding the instrument; threshold and granularity pinned** - `fd53a22` (test)
2. **Task 2: RunProtocol's per-command timeout excludes paused time too; each pause episode records once** - `248fed8` (test)

**Plan metadata:** pending (this SUMMARY's own commit)

## Files Created/Modified
- `tools/tests/fast_test.py` - `_no_sleep`/`_fake_clock` helpers;
  `TestPausedTimeExcludedFromTimeout` (6 tests) proving LIVE-03 (paused time
  excluded from the timeout, both Transfer's Config-sourced timeout and
  RunProtocol's per-command timeout, at poll granularity) and LIVE-02 (two
  pause episodes record two pauses)

## Decisions Made
See `key-decisions` in frontmatter: the two-task class split (edit, revert,
re-add) to keep one commit per task despite both tasks touching the same
class in the same file; and the fresh-core-per-call pattern that gives every
test (and subTest) its own clock starting at 0.

## Observed Pre-Wiring RED Failures

**Task 1, before removing `through_pauses=True` from `Transfer`'s
`RunOptions` (temporary, never committed):**
```
test_a_pause_far_longer_than_the_timeout_still_ends_success ...
2026-10-13 19:44:58 | INFO | fast run progress 10% (running)
2026-10-13 19:44:58 | INFO | fast run progress 10% (paused)
FAIL
...
AssertionError: 7 != 1 : run paused at 10%: WrongPlateType (-645); fix the
deck, then send Resume (is_tip_broken) or Abort (return_liquid)
```
The first paused reading ended the Transfer as `Paused` (kind `paused`,
response code 7) instead of waiting through it — exactly the failure the
plan predicted. `through_pauses=True` was restored and
`git diff --exit-code -- tools/fast/server.py` confirmed a clean tree
(exit 0) before the Task 1 commit.

**Task 2, before removing `through_pauses=True` from `RunProtocol`'s
`RunOptions` (temporary, never committed):**
```
test_run_protocol_per_command_timeout_excludes_paused_time [paused] ...
2026-10-13 19:46:25 | INFO | fast run progress 10% (running)
2026-10-13 19:46:25 | INFO | fast run progress 10% (paused)
2026-10-13 19:46:25 | INFO | fast run progress 10% (running)
FAIL
...
AssertionError: 7 != 1 : run paused at 10%: WrongPlateType (-645); fix the
deck, then send Resume (is_tip_broken) or Abort (return_liquid)
```
Same root cause as Task 1 (the paused subTest's first paused reading ended
the RunProtocol as `Paused`). `through_pauses=True` was restored and
`git diff --exit-code -- tools/fast/server.py` confirmed a clean tree
(exit 0) before the Task 2 commit.

## Deviations from Plan

None - plan executed exactly as written. Every acceptance criterion in both
tasks was verified to pass before committing, and both temporary RED runs
reproduced exactly the failure the plan predicted.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto
  test` exits 0 with 140 unittest tests (up from 138 after Task 1, 134
  after 02-03).
- `git diff --exit-code c9a89cf -- tools/base_server.py` exits 0
  (unchanged).
- `git diff --exit-code HEAD -- tools/fast/server.py` exits 0;
  `git log -1 --format=%H -- tools/fast/server.py` still prints
  `8a4a6faa0a98fe586cef24b5daf2f2341693f934` (the last 02-03 commit) — this
  plan changed no production code.
- `git log --oneline -2` shows `248fed8` (RunProtocol/episodes commit) then
  `fd53a22` (Transfer timeout commit), in that order.
- ROADMAP Phase 2 success criteria 3 (second half, "a timeout still never
  aborts") and 4 ("paused time doesn't count toward the run timeout") are
  both done. This is the last plan in Phase 2 — Phase 3 (safe-order deploy
  and supervised live acceptance) is next.
- No blockers.

---
*Phase: 02-wait-through-pauses-on-the-pinned-core*
*Completed: 2026-10-13*

## Self-Check: PASSED

- FOUND: tools/tests/fast_test.py
- FOUND: fd53a22 (Task 1)
- FOUND: 248fed8 (Task 2)
- `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto test` re-run: exit 0,
  140 unittest tests passed
- `git diff --exit-code c9a89cf -- tools/base_server.py` exits 0
- Every acceptance criterion from both tasks verified to pass (see commit history and the
  acceptance-criteria commands run before each commit)
