---
phase: 02-wait-through-pauses-on-the-pinned-core
plan: 01
subsystem: adapter
tags: [fast-mcp, grpc, run-control, pause-resume, unittest]

# Dependency graph
requires:
  - phase: 01-adapter-control-path-run-state
    provides: "_record_pause/_log_progress/_run_in_flight/_build_run_state, the ExecuteCommand
      control-command override, run_state over GetStatus"
provides:
  - "fast-mcp re-pinned to b30b38d (wait-through-pauses core) in tools/fast/requirements.txt"
  - "Transfer and RunProtocol wait through instrument and operator pauses (through_pauses=True,
     on_pause=self._record_pause), proven end to end over the real core with a stub transport"
  - "D-08: the re-pinned core's stale-leading-paused masking pinned by a rewritten Resume test"
  - "Real-core gRPC test fixture (_Stepper, _stub_transport, _real_core, _RealCoreGrpcTestCase)
     reusable by later plans in this phase"
affects: ["02-02 (capability/state-gate pin tests, docstring updates)",
  "02-03 (operator-abort wording)", "02-04 (paused-time-excluded-from-timeout tests)"]

# Actuals (#2632)
actuals:
  tokens: 5365
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Real FastService over a MagicMock transport (InstrumentSession + default_openapi_path),
       never a mocked FastService, for tests that must exercise the core's own state machine"
    - "Sleep-gated _Stepper (threading.Event + threading.Semaphore) paces a real core's poll
       loop from the test thread without blocking get_status, which would deadlock
       ResumeMarker's lock against a concurrent Resume/Pause/Abort"

key-files:
  created: []
  modified:
    - tools/fast/requirements.txt
    - tools/fast/server.py
    - tools/tests/fast_test.py

key-decisions:
  - "Re-installed the gate venv from the local fast-mcp clone at b30b38d with --no-deps
     --force-reinstall (D-02); fix/run-recovery-gate is not yet on GitLab, so a clean install
     from the pinned URL remains a Phase 3 prerequisite (the user's action)"
  - "D-08: test_resume_known_limitation_leading_paused_poll_reads_as_paused replaced with
     test_resume_masks_a_stale_leading_paused_and_reports_ran, pinning the fixed behaviour
     (ResumeMarker masks the stale leading paused reading) instead of the old limitation"
  - "Both tasks wrote and ran the new/extended tests before touching server.py and recorded the
     observed pre-wiring failures, then wired Transfer (Task 1) and RunProtocol (Task 2) with a
     single commit per task, matching the plan's explicit action steps rather than splitting
     into separate RED/GREEN commits (the plan's own task 2 action text specifies one commit)"

requirements-completed: [LIVE-01, LIVE-02]

coverage:
  - id: D1
    description: "requirements.txt pins fast-mcp b30b38d; the gate venv installs from the local
      clone at that SHA and the pin test passes"
    requirement: "LIVE-01"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRequirementsPin.test_requirements_txt_pins_exactly_one_credential_free_sha"
        status: pass
      - kind: other
        ref: "python -c direct_url.json vcs_info.commit_id check (acceptance criteria)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Transfer and RunProtocol wait through instrument and operator pauses:
      run_state reports the pause with its detail, and the step ends SUCCESS after a Resume,
      proven over the real core (stub transport) through the real gRPC stub"
    requirement: "LIVE-02"
    verification:
      - kind: integration
        ref: "tools/tests/fast_test.py#TestPauseThroughRealCore.test_paused_transfer_stays_open_and_ends_success_after_resume"
        status: pass
      - kind: integration
        ref: "tools/tests/fast_test.py#TestPauseThroughRealCore.test_operator_pause_then_resume_keeps_the_transfer_open_and_ends_success"
        status: pass
      - kind: integration
        ref: "tools/tests/fast_test.py#TestPauseThroughRealCore.test_instrument_pause_keeps_a_run_protocol_open_with_no_command_sent"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRecoveryCommands.test_resume_wait_uses_a_fresh_handle_and_transfer_options"
        status: pass
    human_judgment: false

duration: 15min
completed: 2026-10-13
status: complete
---

# Phase 2 Plan 1: Re-pin to b30b38d and wait through pauses Summary

**Re-pinned fast-mcp to b30b38d and wired Transfer/RunProtocol with `on_pause=self._record_pause, through_pauses=True`, proven end to end over the real core (stub transport): a paused step stays open, `run_state` reports the pause detail, and the step ends SUCCESS after an operator Resume.**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-10-13T07:36:05Z
- **Completed:** 2026-10-13T07:48:50Z
- **Tasks:** 2 completed
- **Files modified:** 3

## Accomplishments
- `tools/fast/requirements.txt` pins `fast-mcp @ ...@b30b38df48e8480f325228145ccae7915a56e437`,
  with a comment naming the wait-through-pauses core as the reason and the GitLab push as a
  Phase 3 prerequisite; the gate venv was re-installed from the local clone at that SHA
  (`--no-deps --force-reinstall`) and `direct_url.json` records the matching commit.
- `Transfer` and `RunProtocol` both pass `on_pause=self._record_pause, through_pauses=True` in
  their `RunOptions`, with nothing else in either method changed.
- D-08: the old `test_resume_known_limitation_leading_paused_poll_reads_as_paused` is replaced
  by `test_resume_masks_a_stale_leading_paused_and_reports_ran`, pinning the re-pinned core's
  fixed behaviour (`ResumeMarker` masks the stale leading `paused` reading after an accepted
  resume); `Resume`'s docstring drops the "Known limitation" paragraph.
- New real-core gRPC test fixture in `tools/tests/fast_test.py`: `_Stepper` (sleep-gated single
  stepping of the real core's poll loop), `_stub_transport`, `_real_core`,
  `_RealCoreGrpcTestCase`, and `TestPauseThroughRealCore` with three tests proving, over the
  real `FastService` and a stub transport reached through the real in-process gRPC stub:
  - an instrument pause on a `Transfer` keeps the step open, reports the full `PauseInfo`
    detail (errorCode/errorName/eventPayload/since) in `run_state`, and ends SUCCESS after an
    operator Resume;
  - an operator `Pause` on a `Transfer` keeps the step open with a detail-less pause record and
    ends SUCCESS after Resume;
  - an instrument pause on a `RunProtocol` records exactly one pause episode (two consecutive
    paused readings fire `_record_pause` once) with no pause/resume/abort command sent, and
    ends SUCCESS when the instrument starts running again.
- Extended `TestTransferMapping`, `TestResultMapping` and `TestRecoveryCommands` to assert the
  new `RunOptions` kwargs on Transfer/RunProtocol and their absence on the crash-recovery
  Resume's wait (D-07).

## Task Commits

Each task was committed atomically:

1. **Task 1: Re-pin to b30b38d and keep a paused Transfer open end to end** - `9b74cd3` (feat)
2. **Task 2: RunProtocol waits through pauses too** - `d60c829` (feat)

**Plan metadata:** pending (this SUMMARY's own commit)

## Files Created/Modified
- `tools/fast/requirements.txt` - re-pinned to b30b38d with a reason comment
- `tools/fast/server.py` - `Transfer`/`RunProtocol` wire `on_pause`/`through_pauses`; `Resume`
  docstring updated for D-08
- `tools/tests/fast_test.py` - D-08 test rewrite; new real-core test fixture and
  `TestPauseThroughRealCore`; extended options assertions on three existing tests

## Decisions Made
- Installed the gate venv from the local clone with `--no-deps --force-reinstall` rather than a
  bare `pip install` (D-02's recorded discretion): identical `direct_url.json` result, no
  registry contact, and guarantees the same 0.1.0 version is replaced.
- Kept each task to a single commit (tests + implementation together), per the plan's own
  action text, rather than splitting into separate TDD RED/GREEN commits — this plan's
  frontmatter is `type: execute`, not `type: tdd`, and `workflow.tdd_mode` is not enabled in
  this project's config.

## Deviations from Plan

None - plan executed exactly as written. Both tasks' pre-wiring test runs reproduced exactly
the failure the plan predicted (see "Observed Pre-Wiring Failures" below), and every
acceptance criterion in the plan was verified to pass before committing.

## Observed Pre-Wiring Failures

**Task 1 (tracer), before wiring `Transfer`'s `RunOptions`:**
```
test_paused_transfer_stays_open_and_ends_success_after_resume (tools.tests.fast_test.TestPauseThroughRealCore) ...
2026-10-13 14:43:19 | INFO | fast run progress 10% (running)
2026-10-13 14:43:19 | INFO | fast run progress 40% (paused)
2026-10-13 14:43:19 | DEBUG | ExecuteCommand Response: response: ERROR_FROM_TOOL
error_message: "run paused at 40%: WrongPlateType (-645); fix the deck, th...
FAIL
...
AssertionError: timed out waiting for the wait thread to sleep
```
The paused reading was terminal in default mode: the Transfer ended at once (`ERROR_FROM_TOOL`,
"run paused at 40%: ..."), so the test's second `wait_sleeping()` never saw the core sleep
again and timed out — exactly the failure the plan predicted.

**Task 2, before wiring `RunProtocol`'s `RunOptions`:**
```
test_instrument_pause_keeps_a_run_protocol_open_with_no_command_sent ...
AssertionError: timed out waiting for the wait thread to sleep
```
(the first instrument-pause reading ended the `RunProtocol` as Paused, same root cause as
Task 1's pre-wiring failure)
```
test_run_protocol_passes_no_verify_layout_and_no_cancel ...
AssertionError: False is not True
```
(`call.kwargs["options"].through_pauses` was still the default `False`)

Both failures disappeared after wiring `RunProtocol`'s `RunOptions` with
`on_pause=self._record_pause, through_pauses=True`.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. The fast-mcp `fix/run-recovery-gate` branch
(holding b30b38d) still needs to be pushed to GitLab before a clean install works outside this
local-clone install; that push is the user's action and a documented Phase 3 prerequisite
(already tracked in STATE.md Blockers/Concerns and PROJECT.md Context).

## Next Phase Readiness
- The real-core gRPC test fixture (`_Stepper`, `_stub_transport`, `_real_core`,
  `_RealCoreGrpcTestCase`) is in place and reusable by 02-02 (capability/state-gate tests),
  02-03 (abort wording tests) and 02-04 (paused-time-excluded-from-timeout tests).
- `tools/base_server.py` is untouched (`git diff --exit-code c9a89cf -- tools/base_server.py`
  exits 0).
- No blockers for 02-02.

---
*Phase: 02-wait-through-pauses-on-the-pinned-core*
*Completed: 2026-10-13*

## Self-Check: PASSED

- FOUND: tools/fast/requirements.txt
- FOUND: tools/fast/server.py
- FOUND: tools/tests/fast_test.py
- FOUND: 9b74cd3227c30862e6febc66ce26e5055a2c5f39 (Task 1)
- FOUND: d60c829d3df9e70a4291aa2992ee36e29a8aabd2 (Task 2)
- `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto test` re-run: exit 0,
  123 unittest tests passed
- `git diff --exit-code c9a89cf -- tools/base_server.py` exits 0
- Every acceptance criterion from both tasks verified to pass (see commit history and the
  acceptance-criteria commands run before each commit)
