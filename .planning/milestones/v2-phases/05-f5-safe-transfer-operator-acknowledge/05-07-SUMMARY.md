---
phase: 05-f5-safe-transfer-operator-acknowledge
plan: 07
subsystem: stack-transfer-never-resend-proof
tags: [never-resend, behavioural-matrix, stk-05, busy-reads, restart, d-09, d-12, d-15, d-16, d-17, safety, stack-core-934a621]

requires:
  - phase: 05-f5-safe-transfer-operator-acknowledge
    provides: "05-06 repeat-key state machine (decide dispatch, read-only re-attach, D-09 restart rule); 05-05 release whitelist; 05-02/05-04 AST invariant; _FakeCore, _TransferTestCase, _LedgerCase helpers"
provides:
  - "TestNeverResends: 12-scenario behavioural matrix proving execute_transfer stays at 1 per step key across repeats, retries, timeouts and restarts, with no acknowledge_failure and only plan/execute/wait/wait_transfer/latch_status reached (XFR-05, D-15, D-16)"
  - "The one documented exception pinned: a released outcome re-runs exactly one more execute_transfer (total 2), a third run replays"
  - "TestBusyReads (and the TestFailureLatch busy test) re-proven on the real Transfer blocked inside the core wait: reads incl. GetFailureLatch answer while BUSY, second Transfer NOT_READY over gRPC and 'busy' on a direct call, ledger record done after release (STK-05, D-12, D-17)"
  - "Simulated Transfer leaves no stack-ledger.json under the configured ledger dir or XDG_STATE_HOME (STK-06 regression)"
  - "Final module and Transfer docstrings (no behaviour change)"
affects: [phase-06, phase-07-runbook]

actuals:
  tokens: 5500
  tasks: 2
  commits: 2
plan_head_before: 68484d1b1862572d7cc6ce0f623aa2a467020a53
plan_head_after: e292f76c88fc57f059149f441fa38985994a031c

tech-stack:
  added: []
  patterns:
    - "_run_scenario(name, steps, expected_executes): each step is (callable(key) -> reply, expected response code); afterwards it asserts the execute total across every fake core, no acknowledge_failure, and every call name inside the allowed set"
    - "A patched _monotonic that jumps 1000 s per read bounds every re-attach scenario, so no test can spin on the real clock"
    - "A restart is a new StackServer plus a new _FakeCore on the same ledger dir (_restarted), the fake cores are tallied together"
    - "The busy tests drive the real Transfer through a MagicMock service whose wait blocks on a threading.Event; cleanups run release before join, and the motion-lock-free check runs last"

key-files:
  created: []
  modified:
    - tools/tests/stack_test.py
    - tools/stack/server.py

key-decisions:
  - "No behaviour change was needed: all 12 matrix scenarios passed on the 05-06 implementation (D-09 stays as the user confirmed: a re-attach observing ran after a restart is SUCCESS with reattachedAfterRestart true)"
  - "The injected-handler patch in TestFailureLatch (a plan 05-05 test) was also converted to the real Transfer so the acceptance criterion (zero injected Transfer patches) holds everywhere"

patterns-established:
  - "Mutation check for a safety matrix: with the claim guard and the decide() dispatch temporarily disabled all 12 scenarios fail; the source was restored with git checkout -- <file> before any commit"

requirements-completed: [XFR-05, XFR-03, XFR-01, ACK-01]

coverage:
  - id: D1
    description: "For one step key the total execute_transfer count across every Transfer sent stays exactly 1 for: F5 repeat after ran, repeat past the replay window, retry after failed, timedOut then re-run to ran, lost(pollFailed) then re-run, submitOutcomeUnknown then re-run, an exception after the write-ahead then re-run, a fingerprint-mismatch attempt then the original, and a restart with the record started, submitting or done"
    requirement: "XFR-05"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestNeverResends"
        status: pass
    human_judgment: false
  - id: D2
    description: "In every matrix scenario acknowledge_failure is never called and no core method outside plan_transfer, execute_transfer, wait, wait_transfer and latch_status is reached; the AST invariant still passes on the final sources"
    requirement: "XFR-05"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestNeverResends"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestAdapterInvariant"
        status: pass
    human_judgment: false
  - id: D3
    description: "The documented exception is pinned: after a released Refused(stackBusy) a re-run sends exactly one more execute_transfer (total 2) and a third run replays"
    requirement: "XFR-05"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestNeverResends.test_the_one_exception_a_released_outcome_re_runs_exactly_once_more"
        status: pass
    human_judgment: false
  - id: D4
    description: "While a real Transfer is blocked in the core wait, GetStatus is BUSY, the seven reads and GetFailureLatch answer SUCCESS with their own results, a second Transfer over gRPC is NOT_READY, a direct second Transfer is ERROR_FROM_TOOL busy, plan_transfer and execute_transfer are called once each, and after release the first Transfer is SUCCESS, the record is done, GetStatus is READY and the motion lock is free"
    requirement: "ACK-01"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestBusyReads.test_reads_answer_while_busy_and_a_second_transfer_is_refused"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestBusyReads.test_last_error_survives_reads_while_a_transfer_is_in_flight"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestFailureLatch.test_the_latch_answers_while_a_transfer_holds_the_tool_busy"
        status: pass
    human_judgment: false
  - id: D5
    description: "A simulated Transfer leaves no stack-ledger.json in the configured ledger dir nor under XDG_STATE_HOME and creates no ~/.local under the fake home"
    requirement: "XFR-01"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestSimulatedTransferOverGrpc.test_a_simulated_transfer_never_writes_a_ledger_anywhere"
        status: pass
    human_judgment: false
  - id: D6
    description: "Module and Transfer docstrings describe Transfer as the one motion path and the one multi-call command; AST invariant, no-MCP import rule and forbidden-literals rule pass; bin/make proto test exits 0"
    requirement: "XFR-05"
    verification:
      - kind: command
        ref: "bin/make proto test (478 passed, ruff and mypy clean)"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-10-29
status: complete
---

# Phase 5 Plan 07: Never-Resend Matrix and STK-05 on the Real Transfer Summary

**A 12-scenario fake-core matrix proves that no repeat, retry, timeout or restart sends a second `execute_transfer` or acknowledges on its own, and the BUSY-read tests now run against the real Transfer blocked inside the core wait; the full gate is green at 478 tests with no adapter behaviour change.**

## Performance

- **Duration:** about 25 min (start time not captured; estimated from commit times)
- **Completed:** 2026-10-29
- **Tasks:** 2 (2 commits)
- **Files:** 2 modified (`tools/tests/stack_test.py`, `tools/stack/server.py` docstrings only), none created
- **Gate:** `bin/make proto test` exit 0, ruff clean, mypy clean (94 files), 478 passed (Phase 4 baseline 267, 465 before this plan)

## Accomplishments

- **Task 1: `TestNeverResends`.** `_run_scenario(name, steps, expected_executes)` runs a list of `(step, expected response)` pairs under one step key, then asserts the `execute_transfer` total across every fake core, that `acknowledge_failure` is absent from every call log, and that every call name is within `{plan_transfer, execute_transfer, wait, wait_transfer, latch_status}`. The 12 scenarios, each its own test method:
  1. ran then F5 (x3: SUCCESS, replay, replay)
  2. ran then past the window (+5 s replays, +601 s refused, twice)
  3. failed then retry (two refusals)
  4. timedOut then re-run to ran, then replay
  5. lost(pollFailed) then re-run to ran
  6. submitOutcomeUnknown then two re-runs refused
  7. exception after the write-ahead then two re-runs refused
  8. fingerprint mismatch (INVALID_ARGUMENTS) then the original replays
  9. restart while started (new server and core re-attach to ran, flagged `reattachedAfterRestart`, one `wait_transfer`, zero execute)
  10. restart while submitting (refused with "tool restarted mid-transfer", zero core calls)
  11. restart after done (replayed, zero core calls)
  12. the released-outcome exception: Refused(stackBusy), then an accepted re-run, then a replay; total execute 2, plan 2
- **Task 2: STK-05 on the real Transfer.** `TestBusyReads._start_blocked_transfer` replaces the injected-handler helper: `plan_transfer` answers a plan, `execute_transfer` a handle, and `wait` blocks on a `threading.Event` (timeout 10) then answers Ran. Reads (seven plus `GetFailureLatch`) answer SUCCESS while GetStatus is BUSY; a second Transfer over gRPC is NOT_READY; a direct `server.Transfer` call is ERROR_FROM_TOOL "busy" (motion lock); plan and execute are called once each; after release the first Transfer is SUCCESS, record `busy-1` is done (and `busy-2`/`busy-3` have none), GetStatus is READY and `_MOTION_LOCK` is free. The last-error test also drives the real Transfer. `TestSimulatedTransferOverGrpc` gains a ledger-absence check under the configured dir and `XDG_STATE_HOME`. The module and `Transfer` docstrings now state the one-motion-path / one-multi-call contract (no behaviour change).

## Task Commits

1. **Task 1:** `f966d44` `test(05-07): never-resend matrix across repeats, timeouts and restarts (XFR-05)`
2. **Task 2:** `e292f76` `test(05-07): STK-05 re-proven on the real Transfer; final docs (D-12, D-17)`

## Evidence the matrix has teeth

All 12 scenarios passed on the 05-06 implementation (as the plan expected: characterisation tests, no RED phase, no `fix(05-07)` commit). To prove they can fail, `tools/stack/server.py` was temporarily mutated (the `decide()` dispatch forced to the fresh path and the `claimed` guard disabled); `-k TestNeverResends` then reported `12 failed`. The file was restored with `git checkout -- tools/stack/server.py` before any commit; `git diff` shows only the docstring change.

## Decisions Made

See `key-decisions` in the frontmatter. D-09 (user-confirmed this session) is exercised by scenario 9 as written: a re-attach that observes ran after a restart is SUCCESS with `reattachedAfterRestart: true`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug, test-only] `Struct.get` does not exist**
- **Found during:** Task 1 first run
- **Issue:** my `ran-f5` scenario read `reply.meta_data.get("replayed")`; a protobuf Struct has no `.get`.
- **Fix:** index with `reply.meta_data["replayed"]`.
- **Files modified:** `tools/tests/stack_test.py`
- **Commit:** `f966d44` (fixed before the commit)

**2. [Rule 3 - Blocking acceptance criterion] A second injected Transfer handler lived in `TestFailureLatch`**
- **Found during:** Task 2 acceptance check (`grep -c 'patch.object(self.server, "Transfer"'` printed 1, not 0)
- **Issue:** `TestFailureLatch.test_the_latch_answers_while_a_transfer_holds_the_tool_busy` (from plan 05-05) still used the injected-handler pattern.
- **Fix:** it now blocks the real Transfer in the core wait with a temp ledger dir and the motion-lock-free cleanup; the assertions are unchanged. The criterion now prints 0.
- **Files modified:** `tools/tests/stack_test.py`
- **Commit:** `e292f76`

**Total deviations:** 2 auto-fixed (1 test typo, 1 criterion-driven test conversion). **Impact:** none on adapter behaviour; the only `tools/stack/server.py` change is docstrings.

## Issues Encountered

None. `~/.local/state/galago-tools` does not exist after the full gate (no test wrote the real ledger); `git diff --quiet e1bf845 -- tools/base_server.py interfaces/ tools/stack/requirements.txt` exits 0; no STACK motion, no `10.150.1.125`/`stack-server` contact (fake cores and the loopback socket guard only), no import of `stack_automation_layer.mcp`.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or schema. T-05-26 (never-resend regression) is covered by `TestNeverResends` plus `TestAdapterInvariant`; T-05-27 (reads during a Transfer) by `TestBusyReads` on the real path and `TestReadCommandSet`; T-05-28 (tests contacting hardware) by the `_StackTestCase` loopback guard and the forbidden-literals rule; T-05-SC by the unchanged `tools/stack/requirements.txt`.

## Next Phase Readiness

Phase 5 plans are all executed. Behavioural and AST proof of XFR-05 and the STK-05 carry-over are in the default gate. Phase 7 runbook notes carried from 05-SPIKE.md section 7 are unchanged.

## Self-Check: PASSED

- `tools/tests/stack_test.py` (`class TestNeverResends`, `_start_blocked_transfer`, `test_a_simulated_transfer_never_writes_a_ledger_anywhere`) and `tools/stack/server.py` are present; `grep -c 'patch.object(self.server, "Transfer"'` = 0.
- Commits `f966d44` and `e292f76` are ancestors of HEAD; `git rev-list --count 68484d1..HEAD` = 2 (matches `commits: 2`).
- `bin/make proto test` exit 0 (478 passed, ruff and mypy clean); `git diff --quiet e1bf845 -- tools/base_server.py interfaces/ tools/stack/requirements.txt` exits 0.
