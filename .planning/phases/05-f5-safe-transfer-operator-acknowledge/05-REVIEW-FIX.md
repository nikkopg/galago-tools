---
phase: 05-f5-safe-transfer-operator-acknowledge
fixed_at: 2026-10-30T00:00:00Z
review_path: .planning/phases/05-f5-safe-transfer-operator-acknowledge/05-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 6
skipped: 1
status: partial
---

# Phase 5: Code Review Fix Report

**Fixed at:** 2026-10-30
**Source review:** `.planning/phases/05-f5-safe-transfer-operator-acknowledge/05-REVIEW.md`
**Iteration:** 1

**Summary:**
- Findings in scope: 7 (CR-01, WR-01..WR-06; Info findings are out of scope)
- Fixed: 6
- Skipped: 1 (WR-06, by the user's decision)

**Verification:** `bin/make proto test` exited 0 in the main checkout after the fixes were fast-forwarded onto
`feat/stack-tool` (ruff, mypy, `unittest discover`, pytest: 500 passed). The per-fix runs happened in an isolated
worktree (`.claude/worktrees/rf-05-...`, generated protos only, no `node_modules`), which was removed afterwards; the
final gate above is the reproducible one. Each new test was shown to fail against the pre-fix code (the fix was
reverted or mutated, the test run, the fix restored). No test contacted 10.150.1.125; every test uses the fake core,
a temp ledger directory and patched clocks.

## Fixed Issues

### CR-01: A Configure that changes `ledger_dir` makes the ledger "empty" and lets a repeated step key send a second `execute_transfer`

**Files modified:** `tools/stack/server.py`, `tools/tests/stack_test.py`
**Commit:** 4b62fcd
**Status:** fixed: requires human verification (logic change)
**Applied fix:**
- A Transfer now resolves the configured ledger directory and pins it (`_ledger_pinned`) in one step under `_state`.
- A Configure whose `ledger_dir` resolves somewhere else than the pinned directory is refused with
  `_ConfigureRefused` ("restart the tool server to move it"), with nothing applied. The same directory (even spelled
  differently, or blank resolving to the same XDG path) is accepted. Before any Transfer, the directory can still change.
- `ledger_dir` and `transfer_timeout_s` are no longer assigned at the top of `_apply_config`. They are applied only in
  `_commit_settings` when the Configure commits: immediately for an unchanged endpoint, after the drain and a successful
  `open_service` for a swap. A busy refusal, a pin refusal or a failed open therefore changes no setting, which also
  fixes review point 2 (a refused Configure that had already swapped `_ledger_dir`).
- Phase 4 Configure semantics (WR-01..WR-05 there) are unchanged: an unchanged endpoint still does not drain, a
  validation failure still drops the owner, `_exclusive()` is still bounded.
- Regression tests: `TestLedgerDirPinned` (the reviewer's scenario: completed step key, same-endpoint Configure with a
  different `ledger_dir`, re-run sends no second `execute_transfer`; also endpoint change, same dir accepted, blank
  default accepted, change allowed before the first Transfer, no other setting applied) and
  `TestConfigureBusy.test_a_busy_refusal_changes_no_setting`.
- Not addressed (review point 3, residual): a tool server restarted by a different launcher or environment, whose blank
  `ledger_dir` resolves from `XDG_STATE_HOME` / `HOME` to a different default directory, still starts with an empty
  ledger. A pin only lives for one process. The reviewer's optional "ledger-dir marker" was not built; it is a design
  change beyond a targeted fix. Phase 7 runbook should require an explicit absolute `ledger_dir` in the production Config.

### WR-01: The BUSY gate can be falsified mid-Transfer, and `AcknowledgeFailure` is not covered by the motion lock

**Files modified:** `tools/stack/server.py`, `tools/tests/stack_test.py`
**Commit:** d42e45a
**Status:** fixed: requires human verification (logic change)
**Applied fix:**
- `AcknowledgeFailure` takes `_MOTION_LOCK` non-blocking after the exact-"yes" check and is refused
  `ERROR_FROM_TOOL` ("stack: busy; a Transfer is running in this tool; ... then acknowledge again") while a Transfer
  holds it. It still never touches the ledger and still has the one `acknowledge_failure` call site.
- `setStatus` never reports READY while `_MOTION_LOCK` is held (it maps to BUSY), so a same-endpoint Configure or a
  losing second Transfer cannot reopen the gate. The Transfer's own finally releases the lock before it asks for READY.
- Regression tests: `TestAcknowledgeDuringTransfer` (handler refused busy with the lock held; a same-endpoint Configure
  during a parked Transfer leaves GetStatus BUSY and no `acknowledge_failure` reaches the core; status returns to READY
  and an acknowledge works afterwards).

### WR-02: A Configure refused as "busy" leaves the tool FAILED although the owner is kept

**Files modified:** `tools/stack/server.py`, `tools/tests/stack_test.py`
**Commit:** 9d6bc4d
**Status:** fixed
**Applied fix:** `_ConfigureBusy` now derives from a new `_ConfigureRefused` ("nothing changed, owner kept"). `_configure`
records the current status (thread-local) when it raises one, and `setStatus` restores that status in place of the
FAILED that base `Configure` sets for every exception (so BUSY stays BUSY during a Transfer, READY stays READY). Test:
`TestConfigureBusy.test_a_busy_refusal_leaves_the_tool_ready_and_able_to_transfer` asserts GetStatus and that a motion
command is admitted afterwards. (`is_connected`, which base sets False and nothing reads, is not restored.) This commit
was made before CR-01 because CR-01's refusal reuses the same mechanism.

### WR-03: Message cap can still drop the guid or the operator action

**Files modified:** `tools/stack/server.py`, `tools/tests/stack_test.py`
**Commit:** 3182899
**Status:** fixed
**Applied fix:** New `_fit(front, suffix)` keeps the fixed clause and the front's `; task guid <g>` segment whole and cuts
the text after that segment first, then the front's head; `_with_suffix`, the timedOut/lost re-attach lines, the
latching Transfer error line and every ledger refusal go through it. The owner step key in the in-flight clause is
bounded to 60 characters. A long ledger path in the unreadable-ledger line is cut from its left, so
"do not delete it; no transfer was sent" always survives. Tests: `TestMessageCap` (250-character owner key, restart plus
timedOut with a latched `cancelRequested` guid, lost with an 80-character reason, recorded failure before a long step
key, a 360-character ledger path), each asserting at most 300 characters and the full guids.

### WR-04: `Ledger.release` (and the other mutators) enforce no state transition

**Files modified:** `tools/stack/ledger.py`, `tools/tests/stack_ledger_test.py`
**Commit:** 96d5bed
**Status:** fixed: requires human verification (logic change)
**Applied fix:** `release` deletes only a `submitting` record (an absent key is still a silent no-op); `mark_started` and
`mark_outcome_unknown` require `submitting`; `mark_done` requires `started` or `submitting`. Any other state raises
`LedgerError("state")` and writes nothing. The existing test `test_mark_outcome_unknown_keeps_a_started_handle` asserted
the removed `started -> outcomeUnknown` transition (which the server never makes) and was replaced by a
transition-matrix test that covers every refused (operation, state) pair, plus positive tests.

### WR-05: The `claim() == False` guard is untested; deleting it passes every test

**Files modified:** `tools/tests/stack_test.py`
**Commit:** ff56c2d
**Status:** fixed (test-only; no source change was needed)
**Applied fix:** `TestClaimedElsewhere` covers a patched `Ledger.claim` returning False and the real claim meeting a record
written after our read (record bytes unchanged, no `execute_transfer`, `_CLAIMED_ELSEWHERE` reply). The AST invariant
now also requires that the `claim()` value is assigned and tested by an `if not <name>` that returns, between the claim
and `execute_transfer` (`_claim_gates`), with a planted-mutation test. Mutation check: deleting the two guard lines in
`_run_fresh` now fails the behavioural tests and the invariant.

## Skipped Issues

### WR-06: A typed 5xx (or timeout-class typed error) on the submit POST releases the key, so a re-run can double-send

**File:** `tools/stack/server.py:204, 1001-1002, 1013-1028`
**Reason:** user kept XFR-04 as written; residual risk documented for Phase 7 runbook
**Original issue:** `_RELEASE_TYPES` matches `Rejected` by class only, so a typed HTTP 5xx on the submit POST (which does
not prove STACK did not start the task) releases the step key and a re-run can send `execute_transfer` again. 05-SPIKE.md
OQ2 and section 7 already record this as an accepted risk; the cheap mitigation (`httpStatus >= 500` becomes
`outcomeUnknown`, no latch) is a one-branch change if the decision is revisited.

---

_Fixed: 2026-10-30_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
