---
phase: 05-f5-safe-transfer-operator-acknowledge
reviewed: 2026-10-29T00:00:00Z
depth: standard
files_reviewed: 4
files_reviewed_list:
  - tools/stack/ledger.py
  - tools/stack/server.py
  - tools/tests/stack_ledger_test.py
  - tools/tests/stack_test.py
findings:
  critical: 1
  warning: 6
  info: 4
  total: 11
status: issues_found
---

# Phase 5: Code Review Report

**Reviewed:** 2026-10-29
**Depth:** standard
**Files Reviewed:** 4
**Status:** issues_found

## Summary

Reviewed the step-key ledger (`ledger.py`), the Transfer / AcknowledgeFailure / Configure machinery in `server.py`, and both test files, against the pinned core `934a621` (extracted to a scratch dir to run the suite; 240 of 241 `stack_test` tests pass, the one error is `test_installed_core_is_the_pinned_commit`, which only fails because the core is not pip-installed in this sandbox).

The fresh path itself is sound. `execute_transfer` has one call site, after the write-ahead claim. A claim, `mark_*` or release failure never leads to a send. Strict loading never treats a bad ledger as empty. No adapter path acknowledges, cancels or goes to the safe position on its own. The ledger module is carefully written.

The holes are at the seams around it. A `Configure` can silently swap the ledger directory, so the next repeat of a step key sees an empty ledger and sends a second `execute_transfer`. I reproduced that. The same `Configure` flips BUSY to READY mid-Transfer, and I reproduced `AcknowledgeFailure` reaching the core while a Transfer was running. Several message-cap paths can still drop a guid. One test-coverage hole means a mutation deleting the only multi-process claim guard survives all 240 tests.

Reproductions were run against throwaway copies under the scratchpad. No source file was modified.

## Critical Issues

### CR-01: A Configure that changes `ledger_dir` makes the ledger "empty" and lets a repeated step key send a second `execute_transfer`

**File:** `tools/stack/server.py:747-757` (also `server.py:911`, `server.py:1013-1028`)
**Issue:** `_apply_config` assigns `self._ledger_dir = config.ledger_dir` (line 752) and `self._transfer_timeout_s` (line 750) *before* the same-endpoint early return (757) and *before* `_exclusive()` drains in-flight commands. Three consequences:

1. A same-endpoint `Configure` with a different `ledger_dir` takes effect immediately, with no drain, even while a Transfer is running. `Transfer` resolves `Ledger(resolve_ledger_dir(self._ledger_dir))` on every call (line 911). The next call for a step key that already ran therefore reads a brand-new, empty directory, and `decide()` returns FRESH. Reproduced with a fake core: Transfer `busy-1` completes (SUCCESS). A same-endpoint Configure pointing at another directory returns SUCCESS. Re-running `busy-1` returned SUCCESS and the fake core counted 1 `execute_transfer` after `calls.clear()`, i.e. a second physical send for the same step key.
2. A `Configure` that is refused as `_ConfigureBusy` (endpoint change while a command runs, `server.py:759-763`) has already swapped `_ledger_dir`, although its docstring (lines 655-659) says "nothing was changed". The owner stays on the old STACK while the ledger moves.
3. The same applies with no Configure at all. A blank `ledger_dir` resolves from `XDG_STATE_HOME` / `HOME` at call time (`ledger.py:90-106`). A tool server restarted by a different launcher, user or environment silently gets a different, empty ledger. There is no marker that says "this ledger should already have records".

This breaks the one invariant the phase exists for (never send a second `execute_transfer` for a step key, even across a restart) with no error and no operator-visible signal.
**Fix:** Make the ledger location immutable once it has been used, and never mutate settings before the swap is committed.
```python
# in _apply_config, after validation, before any assignment
new_dir = config.ledger_dir
if self._ledger_pinned is not None and new_dir.strip() != self._ledger_pinned_raw:
    raise ValueError("stack: Config.ledger_dir cannot change while this tool server runs; "
                     "restart the tool server")
# assign _ledger_dir / _transfer_timeout_s only inside the committed branch
# (after _exclusive() succeeds), and for the same-endpoint path only when no
# command is in flight.
```
Pin the resolved directory on the first successful `Transfer` or `Configure`. For the environment-dependent default, also write a small `ledger-dir` marker next to the state, or log and refuse when a resolved default differs from the one used by the previous instance. Add a regression test that reuses a step key across a ledger_dir change.

## Warnings

### WR-01: The BUSY gate can be falsified mid-Transfer, and `AcknowledgeFailure` is not covered by the motion lock

**File:** `tools/stack/server.py:678-686, 752-758, 1112-1118`
**Issue:** The only thing that stops `AcknowledgeFailure` running during a Transfer is the base class's `isReady()` check (status BUSY). That status is easy to reset:
- A same-endpoint `Configure` returns early from `_apply_config` (no drain). Base `Configure` then calls `setStatus(READY)` and clears `last_error`. Reproduced: status was BUSY (4) during a blocked Transfer, and READY (3) after the Configure. A `yes` `AcknowledgeFailure` was then admitted and `acknowledge_failure` was called on the core while the Transfer was still running.
- Base `ExecuteCommand`'s `finally: self.setStatus(READY)` runs for any non-read command that passed `isReady` in the check-then-set window. A second Transfer that loses to `_MOTION_LOCK` still ends by setting READY while the first one runs.

`_MOTION_LOCK` only protects Transfer. The module docstring promises "a second Transfer is refused" but says nothing about the latch being cleared during motion.
**Fix:** Take the motion lock in the acknowledge handler as well, non-blocking, so ack is refused whenever a Transfer holds it. Optionally make `setStatus` refuse READY while `_MOTION_LOCK.locked()`.
```python
def AcknowledgeFailure(self, params):
    if params.arm_inspected != "yes":
        return _reply(INVALID_ARGUMENTS, message=_ACK_NOT_YES_MESSAGE)
    service = self._require_service()
    if not _MOTION_LOCK.acquire(blocking=False):
        return _reply(ERROR_FROM_TOOL, message=_BUSY_MESSAGE)
    try:
        return _result_reply(service.acknowledge_failure(params.guid.strip(), confirm=True))
    finally:
        _MOTION_LOCK.release()
```

### WR-02: A Configure refused as "busy" leaves the tool FAILED although the owner is kept

**File:** `tools/stack/server.py:663-664, 702-704` (base `tools/base_server.py` `Configure`)
**Issue:** `_ConfigureBusy` is a `RuntimeError`. Base `Configure` catches every `Exception` and sets status FAILED, sets `is_connected = False`, and sets `last_error`. `_configure` deliberately keeps the healthy owner and does not set `_configure_failed`, so the `setStatus` guard (line 684) does not apply. If the in-flight command is a read (the case `test_busy_configure_refuses_and_keeps_the_healthy_owner` parks), nothing later resets status to READY. Every non-read command, including Transfer and `AcknowledgeFailure`, then returns NOT_READY until another Configure succeeds, while the owner and service are healthy. The test asserts the reply and the owner but never the resulting status. When a Transfer is the in-flight command, its `finally` resets READY, which masks this.
**Fix:** Have `setStatus` (or `_configure`) restore the previous status when the Configure was refused as busy, for example record `_configure_busy = True` and map `FAILED` to the prior status. Assert `GetStatus` after the busy refusal in the test.

### WR-03: Message cap can still drop the guid or the operator action

**File:** `tools/stack/server.py:510-516, 519-533, 555-562, 1013-1028, 434-441`
**Issue:** `_with_suffix` cuts the front to `300 - len(suffix)` but never bounds the suffix, and it is applied cumulatively. Two reproduced cases:
- `_in_flight_owner_clause` puts the owner's step key, which is unbounded client input, in the suffix. With a 250 character owner key the suffix is over 300 characters, so the limit goes negative. The reply was 312 characters, over the cap, and began with "...", so the kind and the guid were gone.
- After a restart, a `timedOut` re-attach goes through `_non_terminal_reply` (adds "; re-run this step to re-attach") and then `_with_restart_clause` (adds the latch clause plus the restart clause, about 200 characters). The front is cut to about 100 characters. Actual line: `...re-run this step to re-attach; task guid aaaaaaaa-1111-2222-3333-bbbbbbb...; latched guid ...`, so the task guid is truncated.

Also `_LEDGER_UNREADABLE` (line 179) puts the path in the middle. A long ledger path cuts "do not delete it; no transfer was sent", the most important part of that reply. The existing tests cover a 280 character key on the repeat-key refusals and a 400 character reason, but not these paths.
**Fix:** Bound variable parts before composing, for example `_one_line(owner, 60)` for the key in the suffix. Make `_with_suffix` guarantee `len(result) <= 300` by capping the suffix, and build the restart reply from one template rather than stacking two suffixes. Add tests for a long owner key and for restart plus `timedOut` asserting the full task guid is present.

### WR-04: `Ledger.release` (and the other mutators) enforce no state transition; the spec says only a `submitting` record is deleted

**File:** `tools/stack/ledger.py:352-410`
**Issue:** 05-SPIKE.md section 6c says "`release`: delete the record (only a `submitting` record is deleted)". `release()` deletes a record in any state, including `started`, `done` and `outcomeUnknown`. `mark_started` and `mark_done` can likewise regress or overwrite any state (`done` back to `started`, `outcomeUnknown` to `done`). The server only calls them in the right order today, but two tool servers sharing one ledger (the case `claim`'s create-if-absent exists for) or one future caller bug can delete an `outcomeUnknown` record. Module docs state it "is never deleted after this". The ledger is the single guard against a second send, so it should not rely on callers.
**Fix:** Check state inside each `change()`:
```python
def change(records):
    record = records.get(key)
    if record is None or record["state"] != "submitting":
        return None, False      # release: only ever delete a submitting record
    del records[key]
    return None, True
```
Do the same for `mark_started` (requires `submitting`), `mark_done` (requires `started`, or `submitting` on the failed-started path) and `mark_outcome_unknown` (requires `submitting`). Add negative tests.

### WR-05: The `claim() == False` guard is untested; deleting it passes every test

**File:** `tools/stack/server.py:988-993` (tests: `tools/tests/stack_test.py`)
**Issue:** `if not claimed: return _reply(ERROR_FROM_TOOL, message=_CLAIMED_ELSEWHERE)` is the only thing that stops two tool servers sharing a ledger from both reaching `execute_transfer` for the same key. I copied the tree, removed those two lines, and ran `stack_test`: still 240 pass, with only the unrelated pin-metadata error. `_CLAIMED_ELSEWHERE` is not referenced by any test. The AST invariant only checks that some `.claim(` call appears earlier by line number (`stack_test.py:1286-1292`); it does not check that the result gates the send.
**Fix:** Add a test where `ledger.claim` returns False, for example by patching `Ledger.claim`, or by planting a record after `ledger.get` through a patched `get`. Assert no `execute_transfer` call and the `_CLAIMED_ELSEWHERE` message. Strengthen the AST check to require that `claim()`'s value is tested (an `if not <name>` return) before the send.

### WR-06: A typed 5xx (or timeout-class typed error) on the submit POST releases the key, so a re-run can double-send

**File:** `tools/stack/server.py:204, 1001-1002, 1013-1028`
**Issue:** `_RELEASE_TYPES` matches `Rejected` by class only. The pinned core's `_classify_submit_error` maps every non-busy 4xx and every 5xx to `Rejected(stage="instrument", http_status=...)` after the POST was sent. A 500, 502 or 504 does not prove that STACK did not start the task, yet the key is deleted and a re-run sends `execute_transfer` again. 05-SPIKE.md OQ2 records this as an accepted risk, and I am not claiming it contradicts the decision. In a plate-handling robot a double send is the worst failure, and the spike itself names the cheap mitigation (`httpStatus >= 500` becomes `outcomeUnknown`, no latch). The adapter has the information: `outcome.to_dict()["httpStatus"]`.
**Fix:** In `_run_fresh`, route `Rejected` with an int `http_status >= 500` to `_keep_unknown`. Keep 4xx and `Refused` released. Pin the behaviour with a test.

## Info

### IN-01: The AST "never in a loop" invariant is intra-function only

**File:** `tools/tests/stack_test.py:1278-1292`
**Issue:** The loop check walks the ancestors of the single `execute_transfer` call, which lives in `_run_fresh`. A `for` or `while` in `Transfer` around `self._run_fresh(...)`, or `_run_fresh` re-calling itself or `self.Transfer`, would send repeatedly and pass the invariant. `claim` is checked by line number only, as in WR-05.
**Fix:** Also assert that `_run_fresh` is called exactly once, from `Transfer`, with no loop ancestor, and that `_run_fresh` and `Transfer` contain no self-calls.

### IN-02: Exceptions after `execute_transfer` returned a TaskHandle escape with no guid or step key

**File:** `tools/stack/server.py:1005-1011, 1085-1093`
**Issue:** `service.wait`, `outcome.to_dict()` and `service.wait_transfer` are called unguarded. The pinned core says `wait` never raises, and the record is already `started` or `submitting`, so a re-run cannot re-send. If one did raise, base `ExecuteCommand` returns `DRIVER_ERROR` with raw `str(e)` (or `INVALID_ARGUMENTS` for a `KeyError`, which galago-core hides). The operator gets no task guid, no step key and no "re-run to re-attach" instruction for a transfer that is physically running.
**Fix:** Wrap the post-submit section in `except Exception`. Return the `_EXECUTE_RAISED`-style message with the guid from `outcome` and "re-run this step to re-attach".

### IN-03: `Path.home()` failure is not caught and gives no ledger guidance

**File:** `tools/stack/ledger.py:106`, `tools/stack/server.py:910-914`
**Issue:** `resolve_ledger_dir` can raise `RuntimeError` ("Could not determine home directory") when HOME is unset and there is no passwd entry. `Transfer` catches only `(LedgerError, ValueError)`. The outcome is fail closed (nothing sent), but the operator sees a raw `DRIVER_ERROR` with no "no transfer was sent" text.
**Fix:** Catch `RuntimeError` in `resolve_ledger_dir` and re-raise `ValueError`, or add it to the `except` tuple.

### IN-04: Directory fsync failure is silently ignored, and one lock test is narrower than its name

**File:** `tools/stack/ledger.py:210-219`, `tools/tests/stack_ledger_test.py:421-425`
**Issue:** `_fsync_dir` swallows every `OSError`, so a durable-rename failure is invisible before `execute_transfer` is sent. SPIKE 6a specifies "best-effort", so this is by spec, but a single logged warning would make a recurring EIO diagnosable. `test_the_lock_is_released_after_every_mutation` only exercises `claim`, not the other four mutators, despite its name.
**Fix:** Log a warning on failure, and loop the lock-release test over each mutator.

---

_Reviewed: 2026-10-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
