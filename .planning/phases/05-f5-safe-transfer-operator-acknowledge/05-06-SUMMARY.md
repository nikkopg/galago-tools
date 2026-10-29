---
phase: 05-f5-safe-transfer-operator-acknowledge
plan: 06
subsystem: stack-transfer-repeat-key-state-machine
tags: [repeat-key, decide, replay, reattach, wait-transfer, timed-out, restart, d-09, tdd, stack-core-934a621, safety]

requires:
  - phase: 05-f5-safe-transfer-operator-acknowledge
    provides: "05-03 decide()/Decision/Ledger; 05-04 _latch_clause and _transfer_error_reply; 05-05 release whitelist, _finish, _with_suffix; 05-SPIKE.md sections 4 (A-1, A-6), 5 (OQ1), 6b, 6f"
provides:
  - "Transfer dispatches on ledger.decide(): FRESH -> _run_fresh, REPLAY -> SUCCESS, REATTACH -> _reattach, every other action -> _ledger_reply (XFR-03, D-07)"
  - "_ledger_reply: fingerprint mismatch is INVALID_ARGUMENTS; submitting, outcomeUnknown, completed (age >= 600 s, future-dated) and done-non-ran records are ERROR_FROM_TOOL with the guid and next action ahead of the step key, capped at 300 characters, zero plan/execute/wait/wait_transfer calls"
  - "_reattach_loop: read-only wait_transfer slices of min(remaining, WAIT_SLICE_S = 300.0), bounded by the budget, never called with remaining <= 0 (D-11); _monotonic() wrapper for tests"
  - "_non_terminal_reply: timedOut, lost(pollFailed) and any other non-terminal result leave the record started and say 're-run this step to re-attach' (XFR-06, A-1)"
  - "D-09 restart rule (kept by the user): a re-attach across a restart that observes ran is SUCCESS with meta reattachedAfterRestart true; any other outcome adds the arm-inspection clause plus the current latch clause; a submitting record from another instance is refused with the same clause; a done record is never re-observed"
affects: [05-07, phase-07-runbook]

actuals:
  tokens: 10800
  tasks: 3
  commits: 6
plan_head_before: 6d365f6daad3f56dc371337a8b6f062e5ba8bad0
plan_head_after: 71c3a44c49ef92c959d829abd4973965ece4e3d9

tech-stack:
  added: []
  patterns:
    - "Every repeat-key reply puts the guid and the next action before the step key, so the 300-character cut only ever removes key text"
    - "_with_suffix cuts the front of a line, so the restart clause and the latch clause appended after a restart always survive the cap"
    - "The re-attach loop reads the clock only after a timedOut slice; the first slice is exactly min(budget, 300) with no clock read in front of it"

key-files:
  created: []
  modified:
    - tools/stack/server.py
    - tools/tests/stack_test.py

key-decisions:
  - "D-09 stays as confirmed by the user: after a restart a re-attach that observes ran is SUCCESS flagged reattachedAfterRestart; any non-ran outcome adds the arm-inspection clause (05-SPIKE.md OQ1, a one-line change if the stricter reading is wanted later)"
  - "refuseOutcomeUnknown names the recorded latchGuid and makes no latch_status call; only refuseFailed reads latch_status() (once), because only its template names the live latch"
  - "A non-terminal result with a restart adds the latch clause itself (a latching result's reply already carries it), so the operator always sees the current latched guid next to the arm-inspection clause"

patterns-established:
  - "_LedgerCase test base: _seed(key, **fields) plants a record with the real request fingerprint and this server's instance, _write_record writes any record by hand, _at(now, age_s) builds an updatedAt"
  - "A patched _monotonic plus a wait_transfer that advances the fake clock by the requested slice is how every budget test avoids real waiting"

requirements-completed: [XFR-03, XFR-06]

coverage:
  - id: D1
    description: "A repeated step key whose fingerprint differs (a different request field, or the same request against another STACK endpoint) is INVALID_ARGUMENTS with zero core calls, for submitting, started, outcomeUnknown, done+ran and done+failed records"
    requirement: "XFR-03"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestRepeatKey.test_a_different_request_is_invalid_arguments_for_every_state"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestRepeatKey.test_the_same_request_against_another_stack_endpoint_is_a_mismatch"
        status: pass
    human_judgment: false
  - id: D2
    description: "A done+ran record is replayed (SUCCESS, empty message, meta {stepKey, ledgerState, result, replayed}) at 1 s and 599.9 s; at exactly 600 s, 601 s and future-dated it is ERROR_FROM_TOOL 'already completed at ... mint a new step key'; zero core calls throughout"
    requirement: "XFR-03"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestRepeatKey.test_a_done_ran_record_inside_the_window_is_replayed"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestRepeatKey.test_a_done_ran_record_at_the_window_edges"
        status: pass
    human_judgment: false
  - id: D3
    description: "submitting, outcomeUnknown (with and without a latchGuid) and done+failed/aborted/lost records are refused with the template wording and next action; no plan, execute, wait or wait_transfer call, at most one latch_status"
    requirement: "XFR-03"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestRepeatKey"
        status: pass
    human_judgment: false
  - id: D4
    description: "The step key is byte-exact ('run-1:stack-1 ' with a trailing space takes the fresh path); a 280-character key keeps every refusal within 300 characters with the guid it names still present"
    requirement: "XFR-03"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestRepeatKey.test_a_key_that_differs_by_a_trailing_space_takes_the_fresh_path"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestRepeatKey.test_a_280_character_step_key_keeps_every_refusal_within_300_characters"
        status: pass
    human_judgment: false
  - id: D5
    description: "A timedOut fresh wait leaves the record started and replies 'still running ... re-run this step to re-attach'; re-running calls wait_transfer(guid, timeout_s=300.0) and on ran records done and returns SUCCESS, with execute_transfer and plan_transfer called once in total"
    requirement: "XFR-06"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestTimedOutReattach.test_re_running_a_timed_out_step_re_attaches_and_finishes_it"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestTimedOutReattach.test_a_timed_out_step_is_sent_exactly_once_in_total"
        status: pass
    human_judgment: false
  - id: D6
    description: "Budget 650 with always-timedOut slices calls wait_transfer with [300.0, 300.0, 50.0] and never with a non-positive timeout; a zero budget makes no call and reads as timedOut; the re-attach calls only wait_transfer"
    requirement: "XFR-06"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestTimedOutReattach.test_the_budget_is_spent_in_slices_and_never_called_with_nothing_left"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestTimedOutReattach.test_a_loop_with_no_budget_makes_no_call_and_reads_as_timed_out"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestTimedOutReattach.test_the_re_attach_never_plans_executes_or_waits_on_a_handle"
        status: pass
    human_judgment: false
  - id: D7
    description: "lost(pollFailed) on the fresh path or a re-attach leaves the record started (A-1), names the latch guid, exits the loop after one call, and a re-run re-attaches to ran and returns SUCCESS while the latch is still held; lost(taskNotFound) records done; a failed mark_done after a re-attach ends 'but the ledger could not record it' with the record still started"
    requirement: "XFR-06"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestTimedOutReattach.test_a_poll_failure_leaves_the_record_started_and_a_re_run_re_attaches"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestTimedOutReattach.test_the_fresh_path_keeps_pollfailed_started_and_ends_tasknotfound"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestTimedOutReattach.test_a_failed_mark_done_after_a_re_attach_keeps_the_record_started"
        status: pass
    human_judgment: false
  - id: D8
    description: "Restart: a second StackServer on the same ledger dir re-attaches a started record to ran as SUCCESS with reattachedAfterRestart true and the Ran keys, zero execute calls; a non-ran outcome (failed, aborted, lost, cancelled, still running) carries 'tool restarted mid-transfer; inspect the arm; the core may not have latched this failure' plus the current latch guid within 300 characters; a submitting record from the old instance is refused with the same wording; a done+ran record from the old instance is replayed without re-observation; a same-instance re-attach has no flag"
    requirement: "XFR-03"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestRestart"
        status: pass
    human_judgment: false
  - id: D9
    description: "Prohibitions (descriptor-less, flagged unverified in the plan): no SUCCESS replay except done+ran inside the window, no restarted non-ran without the arm-inspection clause, no re-send, cancel or safe-position move on any repeat-key, re-attach or timeout path"
    requirement: "XFR-03"
    verification:
      - kind: unit
        ref: "tools/tests/stack_test.py#TestRepeatKey.test_a_done_ran_record_at_the_window_edges"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestRestart.test_every_non_ran_outcome_after_a_restart_carries_the_clause"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestTimedOutReattach.test_the_re_attach_never_plans_executes_or_waits_on_a_handle"
        status: pass
      - kind: unit
        ref: "tools/tests/stack_test.py#TestAdapterInvariant"
        status: pass
    human_judgment: false

duration: 40min
completed: 2026-10-29
status: complete
---

# Phase 5 Plan 06: Repeat-Key State Machine, Read-Only Re-attach and Restart Rule Summary

**Transfer now runs every repeated step key through `decide()`: a different request is INVALID_ARGUMENTS, a recent done+ran is replayed, a started record is re-attached with a read-only bounded `wait_transfer` loop, everything else is refused with the guid and the next action, and across a tool-server restart a live ran is SUCCESS flagged `reattachedAfterRestart` while every other outcome tells the operator to inspect the arm.**

## Performance

- **Duration:** about 40 min (start time was not captured; estimated from commit times)
- **Completed:** 2026-10-29
- **Tasks:** 3, each RED then GREEN (6 commits)
- **Files:** 2 modified (`tools/stack/server.py`, `tools/tests/stack_test.py`), none created
- **Gate:** `bin/make proto test` exits 0 after every GREEN commit; ruff clean, mypy clean (94 files), 465 tests passed at the end (434 before the plan; `stack_test.py` 197 to 228)

## Accomplishments

- **Task 1: `decide()` drives Transfer.** The interim "any existing record is refused" rule is gone. `Transfer` calls `decide(existing, fingerprint=fp, instance=self._instance, now=_utcnow())` and dispatches: FRESH to `_run_fresh`, REPLAY to SUCCESS with `_ledger_meta(key, record, result=..., replayed=True)`, REATTACH to `_reattach` (refused with no core call for this one commit), and everything else to `_ledger_reply`, which builds the 05-SPIKE.md 6f lines with the guid and next action before the step key. Only the refuseFailed row reads `latch_status()` (once).
- **Task 2: read-only re-attach.** `_reattach_loop(service, guid, budget)` calls `wait_transfer(guid, timeout_s=min(remaining, WAIT_SLICE_S))` until a non-timedOut result or the budget is spent; it returns the last TimedOut (or a synthesised one when no call fit) and never plans, executes or cancels. `_reattach` finishes through the same `_finish` terminal logic as the fresh path, so A-1 decides done versus still started. `_non_terminal_reply` gives timedOut ("still running (timedOut); re-run this step to re-attach"), lost (latch clause first, then the re-attach advice) and any other non-terminal result the "re-run this step to re-attach" tail, on both paths.
- **Task 3: restart rule (D-09 as kept by the user).** `_finish` takes `restarted`: a terminal ran with `restarted` returns SUCCESS with `{**ran, "reattachedAfterRestart": True}`; every other outcome, including a failed ledger write, goes through `_with_restart_clause`, which appends the current latch clause (unless the reply already has it) and `_RESTART_CLAUSE`, cutting the front of the line so both survive the 300-character cap. A submitting record from another instance is refused with the clause first (`_ledger_reply`); a done record is never re-observed.

## Task Commits

1. **Task 1 RED:** `327378f` `test(05-06): failing repeat-key state-machine tests (XFR-03)`
2. **Task 1 GREEN:** `8acd258` `feat(05-06): repeat step keys replay, refuse or re-attach, never re-send (XFR-03)`
3. **Task 2 RED:** `8f93d1c` `test(05-06): failing re-attach and timeout tests (XFR-06)`
4. **Task 2 GREEN:** `0d1410a` `feat(05-06): read-only re-attach finishes timed-out transfers (XFR-06)`
5. **Task 3 RED:** `79cd0c6` `test(05-06): failing restart re-attach tests (D-09)`
6. **Task 3 GREEN:** `71c3a44` `feat(05-06): restart re-attach reports arm inspection unless STACK reports ran (D-09)`

Each `test(05-06)` commit precedes its `feat(05-06)` commit.

## RED Evidence

- Task 1 RED (`-k "TestRepeatKey or TestTransferFreshPath"`): `11 failed, 12 passed`, e.g. `AssertionError: 7 != 4` (the interim rule answered ERROR_FROM_TOOL, not INVALID_ARGUMENTS, for a changed STACK endpoint). After GREEN: 34 passed in `-k "TestRepeatKey or TestTransferFreshPath or TestKeyRelease"`.
- Task 2 RED (`-k TestTimedOutReattach`): `8 failed, 3 passed`, e.g. `AttributeError: module 'tools.stack.server' does not have the attribute '_monotonic'` and the interim refusal where a re-attach was expected. After GREEN: 219 passed in the whole file.
- Task 3 RED (`-k TestRestart`): `6 failed, 3 passed` (the replay, refuse-submitting and same-instance cases already held; the flag and the arm-inspection clause were missing). After GREEN: 31 passed in `-k "TestRestart or TestTimedOutReattach or TestRepeatKey"`, then the full gate 465 passed.

## Decisions Made

See `key-decisions` in the frontmatter. D-09 was confirmed by the user this session; the implementation follows 05-SPIKE.md OQ1 as written.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] The re-attach loop's first slice was 299.9999995 s, not 300.0 s**
- **Found during:** Task 2 GREEN (`test_re_running_a_timed_out_step_re_attaches_and_finishes_it`, which asserts `timeout_s=300.0`)
- **Issue:** The plan describes a deadline from `_monotonic()` with `remaining = deadline - _monotonic()`. With a real clock, a second clock read before the first call makes the first slice a few nanoseconds under the 300 s the spike specifies.
- **Fix:** the loop tracks `remaining = budget` and reads the clock only after a timedOut slice (`remaining = budget - (_monotonic() - started)`). The first slice is exactly `min(budget, 300)`; the later slices and the "never call with remaining <= 0" rule behave as the plan states (the patched-clock test yields `[300.0, 300.0, 50.0]`).
- **Files modified:** `tools/stack/server.py`
- **Commit:** `0d1410a`

**2. [Rule 1 - Bug, test-only] Two of my own RED tests spun on the real clock**
- **Found during:** Task 2 GREEN, the first full run hung past the 120 s timeout
- **Issue:** a fake `wait_transfer` that answers TimedOut forever loops until the 300 s budget runs out on a real clock. The first "sent exactly once" test also wrongly expected a queued TimedOut to end the loop (the loop continues until a non-timedOut result).
- **Fix:** a `_time_out_every_slice(clock)` helper advances a patched `_monotonic` by each requested slice; the two tests use it. The hung process was killed.
- **Files modified:** `tools/tests/stack_test.py`
- **Commit:** `0d1410a` (test changes made after the RED commit `8f93d1c`, before the GREEN commit)

**3. [Rule 3 - Blocking] mypy rejected `**_ESTIMATE_FIELDS` into `Command.Transfer(...)` in the new `_fp` helper**
- **Found during:** Task 1 gate run
- **Fix:** typed the fields as `dict[str, Any]` first. Test-only change.
- **Commit:** `8acd258`

### Plan-scope notes (not defects)

- Message wording: the mismatch line puts the step key last (`stack: this step key was used for a different request or STACK; mint a new step key; step key <k>`) rather than in the middle, and the completed line is `step key already completed at <updatedAt>; the protocol must mint a new step key per run; nothing was sent; step key <k>`, which satisfies both the plan's must-have wording and the 6f template substrings. Both keep the action ahead of the key.
- `REPLAY` is handled directly in `Transfer` and the other actions in `_ledger_reply`, as the plan lists.
- A restarted refuseOutcomeUnknown is not given the restart clause: D-09 and the plan name only the submitting record and the re-attach outcomes.
- The `_with_suffix` cut means that on a restarted failure the task guid (last in the front part) can be the part that is trimmed when the line is long. The latch guid and the restart clause are never trimmed; the longest observed line in the tests is 253 characters.

## Issues Encountered

None beyond the deviations above. `~/.local/state/galago-tools` does not exist after the full gate (no test wrote the real ledger); `tools/base_server.py` and all protos are unchanged; no STACK, no `10.150.1.125` contact (fake core only), no import of `stack_automation_layer.mcp`.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Flags

None. No new endpoint, auth path or schema. T-05-22 (replay only for done+ran inside 600 s with a matching fingerprint) is covered by the window-edge and endpoint-mismatch tests. T-05-23 (restart mid-transfer) by TestRestart. T-05-24 (re-attach loop DoS) by the slice test and the zero-budget test. T-05-25 (byte-exact keys) by the trailing-space test. The plan's `<assumption>` about the XFR-06 budget edges is exercised by the patched-clock tests and is left for the verifier as flagged.

## Next Phase Readiness

Ready for 05-07. The repeat-key table, the re-attach loop and the restart rule are complete; every ledger state now has a defined reply. Phase 7 runbook notes carried from 05-SPIKE.md section 7 are unchanged.

## Self-Check: PASSED

- `tools/stack/server.py`, `tools/tests/stack_test.py` and this SUMMARY are present; `def _reattach_loop`, `reattachedAfterRestart`, `decide(`, `class TestRepeatKey`, `class TestTimedOutReattach`, `class TestRestart` all grep-present.
- Commits `327378f`, `8acd258`, `8f93d1c`, `0d1410a`, `79cd0c6`, `71c3a44` are ancestors of HEAD; `git rev-list --count 6d365f6..HEAD` = 6 (matches `commits: 6`).
- Verification: `bin/make proto test` exit 0 (465 passed, ruff and mypy clean).
