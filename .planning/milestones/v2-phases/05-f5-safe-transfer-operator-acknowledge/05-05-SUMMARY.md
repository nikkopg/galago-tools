---
phase: 05-f5-safe-transfer-operator-acknowledge
plan: 05
subsystem: stack-transfer-outcome-handling
tags: [step-key-release, outcome-unknown, fail-closed, whitelist, ledger-dir, wait-budget, motion-lock, tdd, stack-core-934a621, safety]

requires:
  - phase: 05-f5-safe-transfer-operator-acknowledge
    provides: "05-02 fresh-path Transfer (_run_fresh/_finish, wait budget, motion lock); 05-03 Ledger.release / mark_outcome_unknown / find_by_guid; 05-04 _latch_clause and _transfer_error_reply; 05-SPIKE.md section 3 and 6c"
provides:
  - "_RELEASE_TYPES = (Refused, Rejected, NeedsInput, ReadFailed): an execute_transfer result of one of these classes (by isinstance) deletes the step key's record, replies ERROR_FROM_TOOL, and a re-run calls plan_transfer and execute_transfer again (XFR-04)"
  - "Lost(submitOutcomeUnknown), any other Lost, and any object outside the core's result classes mark the record outcomeUnknown (latchGuid from latch_status() for the first, None otherwise) and are never deleted; the reply says 'this step key will not be re-sent'"
  - "_in_flight_owner_clause: a Refused(inFlight) whose detail guid is another record's handle guid names that step key (A-3)"
  - "_apply_config refuses a non-blank relative Config.ledger_dir before any owner swap (D-03); the raw value is still recorded and nothing is created"
  - "Proof by test of the fail-closed ledger (D-04), the wait budget (D-11) and the motion-lock backstop (D-12)"
affects: [05-06, 05-07, phase-07-runbook]

actuals:
  tokens: 8000
  tasks: 2
  commits: 4
plan_head_before: ed9c3982be00e1f9bf7e08126efd256fd7f40d88
plan_head_after: 848b2041c859bb3625991bbc72853510ce615d4f

tech-stack:
  added: []
  patterns:
    - "Release is by isinstance on the core's real classes, never by kind string; the default for an unknown answer is keep (fail closed)"
    - "_with_suffix cuts the front of a reply line, never the appended clause, so 'will not be re-sent' and the A-3 owner clause survive the 300-character cap"
    - "A failed ledger write never deletes or rewrites a record, so a re-run of the key can only refuse, never re-send"

key-files:
  created: []
  modified:
    - tools/stack/server.py
    - tools/tests/stack_test.py

key-decisions:
  - "mark_done is skipped once mark_started has failed: the ledger is not trusted, and the record stays submitting (the plan's stated end state) rather than jumping submitting -> done with no handle"
  - "The outcomeUnknown path reads latch_status() twice (once for the ledger's latchGuid, once inside _latch_clause for the message), as the plan describes; the tests assert at least one call"
  - "A failed ledger write on the outcomeUnknown path leaves the record submitting and the reply still says 'will not be re-sent'; a failed release keeps the record and says the same"

patterns-established:
  - "TestKeyRelease builds the A-3 fixture through the real Ledger API (claim + mark_started) rather than hand-written JSON"

requirements-completed: [XFR-04, XFR-02, ACK-02, XFR-01]

coverage:
  - id: D1
    description: "Refused (planNotFound, planExpired, failureLatched, inFlight, stackBusy, managerNotAutomated, recoveryPending, robotNotIdle), Rejected (instrument and local), NeedsInput and ReadFailed from execute_transfer delete the record, reply ERROR_FROM_TOOL, and the same key re-runs through plan and execute to SUCCESS"
    requirement: "XFR-04"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestKeyRelease.test_every_nothing_was_sent_result_releases_the_key"
        status: pass
    human_judgment: false
  - id: D2
    description: "Lost(submitOutcomeUnknown) becomes outcomeUnknown with latchGuid (submit-<hex> or None), the reply names the guid / 'did not latch' and 'will not be re-sent', a re-run makes no plan or execute call; other Lost reasons, a MagicMock and a string are kept as outcomeUnknown; an exception leaves the record submitting and the reply carries the type name only"
    requirement: "XFR-04"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestKeyRelease"
        status: pass
    human_judgment: false
  - id: D3
    description: "A plan_transfer result that is not a TransferPlan (Rejected, NeedsInput, ReadFailed, Refused failureLatched) leaves no stack-ledger.json"
    requirement: "XFR-02"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestKeyRelease.test_a_plan_that_is_not_a_plan_leaves_no_ledger_file"
        status: pass
    human_judgment: false
  - id: D4
    description: "A Refused(inFlight) whose detail guid is another step key's handle guid names that step key after the guid; an unknown guid names none"
    requirement: "ACK-02"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestKeyRelease.test_an_in_flight_refusal_names_the_step_key_that_owns_the_guid"
        status: pass
    human_judgment: false
  - id: D5
    description: "Configure with a relative ledger_dir (relative/ledger, ledger, ./ledger, padded) is NOT_READY naming ledger_dir, status FAILED, open_service never called; absolute, empty and blank are accepted, recorded raw, and nothing is created"
    requirement: "XFR-01"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestConfigureLedgerDir"
        status: pass
    human_judgment: false
  - id: D6
    description: "Seven malformed ledgers (bad bytes, bad JSON, version 2, version true, records list, unknown state, ledger path a directory) refuse with the path and 'do not delete it', zero core calls, file bytes unchanged; a failed claim sends nothing; a failed mark_started or mark_done still waits once and ends ERROR_FROM_TOOL 'but the ledger could not record it' even for ran, and a re-run never re-sends"
    requirement: "XFR-02"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestLedgerFailClosed"
        status: pass
    human_judgment: false
  - id: D7
    description: "Wait budget: timeout_s 42 -> 42.0; Config 120 -> 120.0; neither -> 300.0; timeout_s 0 falls through; 1e9 and Config 1e6 clamp to 3600.0"
    requirement: "XFR-01"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestWaitBudget"
        status: pass
    human_judgment: false
  - id: D8
    description: "With _MOTION_LOCK held a direct Transfer returns 'busy' with zero core calls; the lock is free after success, a refusal and an exception raised by plan_transfer (DRIVER_ERROR over gRPC)"
    requirement: "XFR-01"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestMotionLock"
        status: pass
    human_judgment: false
  - id: D9
    description: "The prohibition 'MUST NOT release a step key's record after Lost(submitOutcomeUnknown), an unknown result shape or an exception from execute_transfer' (descriptor-less, flagged unverified in the plan)"
    requirement: "XFR-04"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestKeyRelease.test_a_submit_outcome_unknown_keeps_the_key_with_the_latch_guid"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestKeyRelease.test_an_unexpected_lost_or_unknown_shape_is_kept_as_outcome_unknown"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestKeyRelease.test_an_exception_from_execute_names_only_its_type"
        status: pass
    human_judgment: false

duration: 25min
completed: 2026-10-29
status: complete
---

# Phase 5 Plan 05: Release Whitelist, outcomeUnknown and Transfer Hardening Summary

**A step key is deleted only when execute_transfer returns one of the core's real Refused, Rejected, NeedsInput or ReadFailed classes (by isinstance); Lost(submitOutcomeUnknown), any other Lost and any unknown shape become a permanent outcomeUnknown record carrying the latch guid, and a relative `Config.ledger_dir` now fails Configure before the owner is swapped.**

## Performance

- **Duration:** about 25 min (start time was not captured; estimated from commit times)
- **Completed:** 2026-10-29
- **Tasks:** 2, each RED then GREEN (4 commits)
- **Files:** 2 modified (`tools/stack/server.py`, `tools/tests/stack_test.py`), none created
- **Gate:** `bin/make proto test` exits 0 with ruff clean, mypy clean (94 files), 434 tests passed (413 before the plan; `stack_test.py` 176 to 197)

## Accomplishments

- **Task 1: classification in `_run_fresh`.** The interim keep-submitting branch is replaced. `isinstance(outcome, _RELEASE_TYPES)` goes to `_release`: the reply comes from `_transfer_error_reply`, an `inFlight` refusal gets the A-3 owner clause, and `ledger.release` runs; if it raises `LedgerError` the record stays and "this step key will not be re-sent" is appended. Anything that is not a `TaskHandle` goes to `_keep_unknown`: for `Lost(submitOutcomeUnknown)` the guid comes from `latch_status()` (`_latched_guid`, never raises), then `mark_outcome_unknown`, then the reply with the "will not be re-sent" clause. `_with_suffix` trims the front of the line so the clause survives the 300-character cap (tested with a 400-character reason). The exception branch is unchanged.
- **Task 2: hardening.** `_apply_config` raises `ValueError("stack: Config.ledger_dir must be an absolute path")` for a non-blank relative value, ahead of the owner swap and ahead of recording `_transfer_timeout_s`, so NOT_READY / FAILED and no `open_service` call. TestLedgerFailClosed, TestWaitBudget and TestMotionLock confirmed that the 05-02 behaviour already met D-04, D-11 and D-12, apart from the one gap below.

## Task Commits

1. **Task 1 RED:** `2b2db68` `test(05-05): failing release / outcomeUnknown classification tests (XFR-04)`
2. **Task 1 GREEN:** `43440bd` `feat(05-05): release a step key only when nothing was sent (XFR-04)`
3. **Task 2 RED:** `3c3e812` `test(05-05): Transfer hardening tests (D-03, D-04, D-11, D-12)`
4. **Task 2 GREEN:** `848b204` `feat(05-05): Configure validates ledger_dir; Transfer hardening proven (D-03, D-04)`

Each `test(05-05)` commit precedes its `feat(05-05)` commit.

## RED Evidence

- Task 1 RED (`-k TestKeyRelease`): `8 failed, 3 passed`, e.g. `AssertionError: 'run-planNotFound:k' unexpectedly found in {... 'state': 'submitting' ...}` (the record was not released) and the 400-character reason leaking through the uncapped interim `_result_reply`. After GREEN: full `stack_test.py` 187 passed.
- Task 2 RED (`-k "TestConfigureLedgerDir or TestLedgerFailClosed or TestWaitBudget or TestMotionLock or TestConfigureFails"`): `2 failed, 16 passed`: the relative `ledger_dir` Configure returned SUCCESS (`1 != 6`, expected per the plan), and the `mark_started` failure case ended `'done' != 'submitting'`. After GREEN: 18 passed, then the full gate 434 passed.

## Decisions Made

See `key-decisions` in the frontmatter.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] A failed `mark_started` still let `mark_done` move the record submitting -> done**
- **Found during:** Task 2 RED (`TestLedgerFailClosed.test_a_failed_mark_started_still_waits_once_and_reports_it`)
- **Issue:** When `mark_started` raised, `_finish` still called `mark_done`, which succeeded on the `submitting` record, leaving a `done` record with no handle. The plan requires the record to be `submitting` (or `started`) after either write fails. A re-run would not have re-sent, but the record contradicted the stated end state and the operator would see "completed" for a step whose ledger could not be trusted.
- **Fix:** `_finish` skips `mark_done` when `write_failed` is already set.
- **Files modified:** `tools/stack/server.py`
- **Commit:** `848b204` (test in `3c3e812`)

**2. [Rule 3 - Blocking] mypy rejected `**_ESTIMATE_FIELDS` into `Command.Transfer(...)` in the new TestMotionLock test**
- **Found during:** Task 2 RED commit check
- **Fix:** typed the fields as `dict[str, Any]` first. Test-only change.
- **Commit:** `848b204`

### Plan-scope notes (not defects)

- The plan says the `submitOutcomeUnknown` path "calls `latch_status()` once". The ledger's `latchGuid` read and the message's latch clause are two separate zero-I/O calls, so the core sees two. The test asserts at least one rather than exactly one.
- The interim "step key already has a ledger record, nothing was sent" rule in `Transfer` is untouched; 05-06 replaces it with the `decide()` table. The re-run assertions for kept keys rely on it and check only that `plan_transfer` and `execute_transfer` are not called again.

## Issues Encountered

None. `~/.local/state/galago-tools` does not exist after the full gate (no test wrote the real ledger).

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or schema. T-05-17 (no release after an ambiguous submit) is covered by the keep cases, whose re-runs make zero plan or execute calls. T-05-19 (relative `ledger_dir`) by the Configure subtests. T-05-20 (huge timeouts) by TestWaitBudget clamps. T-05-21 (exception text) by the `SECRET-TEXT` sentinel test. T-05-18 (release after a typed 5xx or `stackBusy`) is accepted per XFR-04 and stays in the Phase 7 runbook notes. `tools/base_server.py` and `interfaces/` are unchanged since `e1bf845`.

## Next Phase Readiness

Ready for 05-06 (wire `decide()` for repeat keys, re-attach via `wait_transfer`). `_run_fresh` now ends every path in a defined ledger state: absent (released or never written), `submitting` (exception or failed write), `outcomeUnknown`, `started` or `done`. The refuseOutcomeUnknown reply can read `latchGuid` from the record.

## Self-Check: PASSED

- `.planning/phases/05-f5-safe-transfer-operator-acknowledge/05-05-SUMMARY.md`, `tools/stack/server.py`, `tools/tests/stack_test.py`: present.
- Commits `2b2db68`, `43440bd`, `3c3e812`, `848b204` are ancestors of HEAD; `git rev-list --count ed9c398..HEAD` = 4 (matches `commits: 4`).
- Acceptance: `_RELEASE_TYPES`, `class TestKeyRelease`, `ledger_dir must be an absolute path`, `class TestLedgerFailClosed`, `class TestWaitBudget` all present; TestKeyRelease holds 12 release subTests and 5 keep cases; `git diff --quiet e1bf845 -- tools/base_server.py interfaces/` exits 0.
- Verification: `bin/make proto test` exit 0 (434 passed).
