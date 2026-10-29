---
phase: 05-f5-safe-transfer-operator-acknowledge
reviewed: 2026-10-30T00:00:00Z
depth: standard
iteration: 3
files_reviewed: 4
files_reviewed_list:
  - tools/stack/ledger.py
  - tools/stack/server.py
  - tools/tests/stack_ledger_test.py
  - tools/tests/stack_test.py
findings:
  critical: 0
  warning: 2
  info: 2
  total: 4
status: issues_found
---

# Phase 5: Code Review Report (iteration 3)

**Reviewed:** 2026-10-30
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Scope: `git diff f25e340..ba9fe65 -- tools/` (server.py and stack_test.py; ledger.py and stack_ledger_test.py are
unchanged since iteration 2). Accepted items (WR-06, the CR-01 default-dir-after-restart residual, iteration-2 IN-01)
are not re-raised.

Verified resolved:

- **Iteration-2 WR-02 (`_fit` keeps the re-attach clause whole):** resolved. The clause that ends the free text is moved
  into the protected suffix, and only variable text (latch kind label, reason, a duplicated "inspect the arm") is shed
  before the head is cut. I traced the shed arithmetic (`over` is decremented by what leaves the suffix as well, and
  `room - len(rest)` cannot go negative because `rest` was cut against the older, smaller room). The new tests assert
  the re-attach text, the latch action and the whole restart clause, and `assertNotIn("...")`. They are non-vacuous.
- **Pin/restore races with Configure:** none found. The pin is taken together with the `_ledger_dir` read under
  `_state`; every Configure path that can change `_ledger_dir` re-checks the pin under the same lock
  (`_commit_settings`), and the swap path runs it again after the drain with `_reconfiguring` set, which keeps a new
  Transfer out (a Transfer is a "reader"). Pin writers are serialised by `_MOTION_LOCK`, so the `finally` restore cannot
  overwrite another Transfer's pin, and `previous` always equals the directory being pinned when it is not None (a
  Configure to a different directory is refused once a pin exists).
- **Untrusted-ledger-file pin (`ba9fe65`):** works for the three reasons raised by `ledger.get`; the test fails without
  the fix.

Two problems remain. The first (WR-01) is a narrowing of the iteration-2 pin condition that lets a second
`execute_transfer` through for a step key in a reachable sequence. I reproduced it with a probe test (see below). The
second (WR-02) is a test gap on the line that protects the pin.

## Warnings

### WR-01: A Transfer that read a populated ledger but wrote nothing releases the pin, so the operator is invited to move `ledger_dir` and a recorded step key reads as new

**File:** `tools/stack/server.py:1097-1105, 1116-1120` (with `tools/stack/server.py:1182-1188`)
**Issue:** `_ledger_used` ("a record can exist here") is set only when `ledger.get(key)` returned a record for *this* key,
when the claim returned, or when the file was untrusted. A ledger file that exists and holds other steps' records
(`done`, `started`, `outcomeUnknown`) but not this key does not count. If that Transfer then ends without a claim
(a `claim` that raises `unwritable`/`busy` or a race-corrupted file, a `NeedsInput`/`Refused`/`Rejected` plan), the
`finally` puts the pin back to `None`, and a Configure to another `ledger_dir` is accepted. Every record in the old
directory is then invisible, and a repeat of any of those step keys is FRESH and calls `execute_transfer` a second time.
The write-ahead-failure reply says "fix the ledger directory", which is exactly the prompt to do it. Before the
iteration-2 fix this Transfer pinned the directory, so this is a regression of the CR-01 guard, not the accepted
"different default after restart" residual. The only way in is a pin that is `None` (first Transfer since the tool
server started) with an already populated ledger, which is the normal state after any restart, and a disk-full or
read-only ledger is the very case the reply tells the operator to repair.

Reproduced in a copy of the tree with a probe test (`TestLedgerDirPinned` subclass; fake core): configure, seed a `done`
record for `other-step`, patch `Ledger.claim` to raise `LedgerError("unwritable")`, Transfer a different key, then
Configure with another directory. Result: `_ledger_pinned` is `None` and the Configure returns SUCCESS.

**Fix:** the pin condition should be "the ledger file exists", not "this key exists":

```python
ledger = Ledger(directory)
existing = ledger.get(key)
if existing is not None or ledger.path.exists():
    self._ledger_used = True
```

(`get` has already proved the file readable, so `exists()` is the cheap, race-free-enough check; a claim failure then
no longer matters because the file is already there. A missing file in an unwritable directory still leaves the pin
unset, which is what iteration-2 WR-01 wanted.) Add a test: seed another key, make the claim raise `unwritable`, assert
a Configure to another directory is refused.

### WR-02: Nothing tests that the restore puts back the previous pin; restoring `None` passes the whole suite

**File:** `tools/tests/stack_test.py:3190-3277` (the iteration-2 WR-01 tests), source `tools/stack/server.py:1116-1119`
**Issue:** All three "does not pin" tests and the "held while running" test start from `_ledger_pinned is None`. The
`finally` restores `previous`, and the case where `previous` is a real directory (an earlier Transfer used the ledger,
a later one writes nothing) is the one that guards CR-01 within a process. I mutated the line to
`self._ledger_pinned = None` in a copy and ran `unittest tools.tests.stack_test` (269 tests): every ledger test
still passed (the only error is `TestRequirementsPin`, caused by the core not being pip-installed in that copy). With
that mutation, `Transfer(K1)` completes, `Transfer(K2)` fails at the plan or the claim, a Configure to another
directory is accepted, and `Transfer(K1)` sends a second `execute_transfer`.
**Fix:** add a test: Transfer succeeds (pin A), then a Transfer that returns `NeedsInput` (and one whose claim raises
`unwritable`), assert `server._ledger_pinned == Path(ledger_dir)` and a Configure to another directory is
refused (NOT_READY) and a repeat of the first key sends no `execute_transfer`.

## Info

### IN-01: A Configure during a Transfer that has not written yet is refused with "after a Transfer has used the step ledger; restart the tool server"

**File:** `tools/stack/server.py:179-181, 1091-1095`
**Issue:** The pin is deliberately taken before the ledger is read (this closes the Configure race), so a Configure that
lands while a Transfer is planning or waiting on the core is refused with the restart-the-server message, even when that
Transfer later ends without writing and the pin is released. Restarting the tool server is wrong advice there (retrying
after the Transfer ends works). The refusal is safe; the wording is misleading.
**Fix:** none required; optionally a distinct message when `_MOTION_LOCK.locked()` ("a Transfer is running; retry
Configure when it ends").

### IN-02: `_fit` pathological branch duplicates the re-attach clause

**File:** `tools/stack/server.py:419-426`
**Issue:** The clause is moved from `rest` into `suffix` before the `room < 0` branch, which then returns
`_one_line(front + suffix, limit)` with the original `front` (still ending in the clause) and the modified `suffix`
(starting with it). The clause would appear twice in the (cut) line. Only reachable when suffix plus the task guid
segment alone exceed the limit, which no caller produces; noted only because the iteration-2 change introduced it.
**Fix:** in that branch, build the line from the stripped `head`/`rest` (`head + keep + rest + suffix`) instead of
`front + suffix`.

---

_Reviewed: 2026-10-30_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
_Iteration: 3_
