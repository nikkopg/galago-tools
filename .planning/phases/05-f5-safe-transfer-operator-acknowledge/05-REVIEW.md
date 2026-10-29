---
phase: 05-f5-safe-transfer-operator-acknowledge
reviewed: 2026-10-30T00:00:00Z
depth: standard
iteration: 2
files_reviewed: 4
files_reviewed_list:
  - tools/stack/ledger.py
  - tools/stack/server.py
  - tools/tests/stack_ledger_test.py
  - tools/tests/stack_test.py
findings:
  critical: 0
  warning: 2
  info: 1
  total: 3
status: issues_found
---

# Phase 5: Code Review Report (iteration 2)

**Reviewed:** 2026-10-30
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Re-review of the fix commits `5571cc9..ff56c2d` against the iteration-1 findings. The core `934a621` was exported with `git archive` from the local `stack-automation-layer` checkout into the scratchpad and put on `PYTHONPATH` (the machine has no pip-installed core). With the repo's `.venv` python, `unittest tools.tests.stack_test tools.tests.stack_ledger_test` ran 353 tests. The only error is `test_installed_core_is_the_pinned_commit`, which needs pip metadata (same as iteration 1). No source file was modified; mutations were run on a copy under the scratchpad.

Disposition of iteration-1 findings:

| ID | Result |
|----|--------|
| CR-01 | Resolved. The pin, the deferred commit, and the refusal all hold. Regression tests are not vacuous (mutations below). One side effect is raised as WR-01. |
| WR-01 (ack vs motion lock) | Resolved. The lock in the handler and the `setStatus` BUSY mapping are each covered by a test that fails when only that half is removed. |
| WR-02 (busy refusal leaves FAILED) | Resolved. Mutation test fails when the restore is removed. |
| WR-03 (message cap) | Mostly resolved: guids are no longer dropped and the cap holds. The re-attach action is still cut in one combination, raised as WR-02. |
| WR-04 (ledger state transitions) | Resolved. All server call orders still satisfy the new checks. |
| WR-05 (`claim() == False`) | Resolved. Behavioural tests and the `_claim_gates` AST rule both fail when the guard is deleted. |
| WR-06 (typed 5xx releases the key) | Accepted by the user (XFR-04 kept as written; Phase 7 runbook). Not a finding. |
| CR-01 residual (a different default `ledger_dir` after a restart or a different launcher) | Accepted and documented for the Phase 7 runbook (an explicit absolute `ledger_dir`). Not a new finding. |

Mutation checks I ran on a scratch copy (each mutation shown with the tests that caught it):
- Remove the pin refusal (`if not same: raise`): 3 `TestLedgerDirPinned` tests fail.
- Remove the `_ledger_pinned` assignment: the same 3 tests fail.
- Remove the ack motion lock: `test_the_handler_is_refused_busy_while_a_transfer_holds_the_motion_lock` fails.
- Remove the `setStatus` READY-to-BUSY mapping: `test_a_same_endpoint_configure_neither_resets_busy_nor_admits_an_acknowledge` fails.
- Remove the WR-02 status restore: `test_a_busy_refusal_leaves_the_tool_ready_and_able_to_transfer` and the CR-01 re-send test fail.
- Remove the `release` state check: the transition-matrix test fails for `started`, `done` and `outcomeUnknown`.
- Remove the `if not claimed` guard: `TestClaimedElsewhere`, `test_a_send_that_does_not_test_the_claim_result_is_reported` and `test_real_sources_are_clean` fail.

Traced and found sound: `_commit_settings` (the check runs under `_state`, the same lock Transfer pins under; for an endpoint swap the check runs after the drain and before the owner is touched, and the final commit cannot see a new pin because commands are held off). The refusal path through `_configure` and base `Configure` restores BUSY or READY correctly, including when a Transfer holds the lock. `Ledger._existing` raises before any mutation or save, so a refused transition writes nothing. The legal write order (`claim`, `mark_started`, `mark_done` or `release` or `mark_outcome_unknown`) is never refused, and a failed `mark_started` skips `mark_done` as before.

## Warnings

### WR-01: The ledger directory is pinned by any Transfer, including one that never touched the ledger, and a failed Transfer then makes the operator's fix impossible without a restart

**File:** `tools/stack/server.py:1026-1031` (pin), `tools/stack/server.py:866-880` (refusal), message at `tools/stack/server.py:175-179`
**Issue:** `Transfer` sets `self._ledger_pinned = directory` before `Ledger(directory)` and `ledger.get(key)` run, so the pin is set on every Transfer call, including these cases where no record was ever written to that directory:
- `ledger.get` fails (unreadable, corrupt, unknownVersion).
- The write-ahead `claim` fails (`unwritable`, `busy`).
- The plan is `NeedsInput`, `Refused` or `Rejected` (these `get` before `plan_transfer`, and no claim happens for `NeedsInput`).

I reproduced this on a scratch copy. A Configure points `ledger_dir` at an unwritable path. The Transfer returns `no transfer was sent; the step ledger could not record the step (unwritable); fix the ledger directory, then re-run this step`. The follow-up Configure to a good directory returns `NOT_READY: stack: Config.ledger_dir cannot change after a Transfer has used the step ledger; restart the tool server to move it`.

The pin exists to stop a step key that already has a record from reading as new in another directory. A directory in which nothing was ever recorded has no such key. The consequence is operational, not a double-send, and it fails closed. But the tool's own message tells the operator to "fix the ledger directory" and the Configure that does so is refused, with a message ("after a Transfer has used the step ledger") that is untrue for these cases. An operator with a typo in `ledger_dir` gets a tool server restart as the only way out.
**Fix:** Pin only once a record can exist in that directory: after a successful `claim` (True) and also when `ledger.get` returned a record. `get` returning `None` on an empty or absent ledger should not pin. For example:
```python
directory = resolve_ledger_dir(self._ledger_dir)       # under _state, no pin yet
ledger = Ledger(directory)
existing = ledger.get(key)
if existing is not None:
    with self._state:
        self._ledger_pinned = directory
```
and set the pin in `_run_fresh` immediately after `claimed` is True (it is the first moment a record exists). The check and assignment must remain under `_state`, and a pin race with a concurrent same-endpoint Configure must be re-checked (commit the pin only if `self._ledger_dir` still resolves to `directory`). Add a test that a Transfer failing with `unwritable` leaves a Configure to another directory accepted.

### WR-02: The WR-03 truncation fix still cuts the re-attach instruction when a restart clause is stacked on a timedOut or lost line

**File:** `tools/stack/server.py:359-383` (`_fit`), `tools/stack/server.py:595-607` and `tools/stack/server.py:620-628` (callers)
**Issue:** `_fit` keeps the suffix and the front's `; task guid <g>` segment whole and cuts the front's head. After a restart, `_non_terminal_reply` builds the front (kind, latch clause, "re-run this step to re-attach") and `_with_restart_clause` then appends about 190 characters. The head is what gets cut, and the head is exactly where the operator action sits. Actual output on a scratch run (latch held, `cancelRequested`):
- timedOut after a restart: `stack: still running (timedOut); re-run this ste...; task guid aaaaaaaa-...; latched guid cccccccc-... (cancelRequested); inspect the arm, then AcknowledgeFailure; tool restarted mid-transfer; ...`
- lost(pollFailed) after a restart: `stack: lost (pollFailed); latched guid cccccccc-... (cancelRequested); inspect the arm, then AcknowledgeFailure; the transfer may still...; task guid aaaaaaaa-...; tool restarted mid-transfer; ...`

Both guids and the cap now hold, which is what the review asked for. But for the lost case "re-run this step to re-attach" is gone, replaced by "...", and in the timedOut case it ends "re-run this ste...". This is the one instruction that says the transfer is still running and the key will re-attach. `TestMessageCap` asserts the guids and `tool restarted mid-transfer`, never the re-attach text, so this regression of the action is not pinned.
**Fix:** Keep both fixed clauses whole and let only variable text (the reason, the latch `kind`, the step key) be cut. For example make `_fit` take the front as `(variable_head, fixed_clause)` for the re-attach lines, or shorten the fixed wording after a restart (drop the duplicate "inspect the arm" that appears in both the latch clause and the restart clause). Add an assertion in `test_a_timed_out_re_attach_after_a_restart_keeps_both_guids` and the lost test that `re-run this step to re-attach` is in the message.

## Info

### IN-01: A Transfer refused because an AcknowledgeFailure holds the motion lock says "another Transfer is running"

**File:** `tools/stack/server.py:179-181`, `tools/stack/server.py:1011-1013`, `tools/stack/server.py:1241-1248`
**Issue:** The ack handler now takes `_MOTION_LOCK` for the duration of the core call. A Transfer that loses the lock to a concurrent acknowledge (both pass the status check in the check-then-set window) gets `_BUSY_MESSAGE`, "another Transfer is running in this tool", which is wrong for that case. The refusal is correct and safe; only the wording misleads. The window is short, so it is low impact.
**Fix:** Word the Transfer busy message neutrally ("a Transfer or an AcknowledgeFailure is running in this tool"), or leave as is and document it.

---

_Reviewed: 2026-10-30_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard (iteration 2)_
