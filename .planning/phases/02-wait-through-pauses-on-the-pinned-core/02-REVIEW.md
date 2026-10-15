---
phase: 02-wait-through-pauses-on-the-pinned-core
reviewed: 2026-10-15T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - tools/fast/server.py
  - tools/tests/fast_test.py
findings:
  critical: 0
  warning: 1
  info: 0
  total: 1
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-10-15T00:00:00Z
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

Incremental re-review after gap-closure plan 02-05 (commits `134e097`,
`7c2e15a`), scoped to `tools/fast/server.py` and `tools/tests/fast_test.py`.
Diffed against `95cbee47f42fe7d714d7e7ff80dad6d754ae8a46` (the commit the
prior `02-REVIEW.md` was written against) and read both files in full for
context.

**CR-01 is fixed.** `Resume()`'s crash-recovery branch (`tools/fast/server.py:944`)
now reads:
```python
accepted = service.resume(is_tip_broken=is_tip_broken)
if not _accepted(accepted):
    return _recovery_reply("resume", accepted)
```
replacing the old `isinstance(accepted, Refused) or accepted.get("errorCode") != 0`
inline comparison. `_accepted()` returns `False` for anything that is not a
`dict`, so the `Refused` case is still handled correctly (the
`isinstance(..., Refused)` special-case was folded in, as the prior review's
fix suggestion allowed), and only a literal `int` `0` now starts the
`service.wait(...)` call — a `{"errorCode": False}` or `{"errorCode": True}`
reply from `fast_mcp.resume()` is now correctly treated as a rejection, not a
credited acceptance. `_accepted()`'s docstring was updated to list this as a
third call site, and the `Resume()` docstring was updated to describe the new
gate explicitly, including "no code in this module compares errorCode inline"
— verified true: the crash-recovery branch was the last inline comparison of
`errorCode` in this file.

The gap-closure plan's new regression tests
(`test_crash_recovery_resume_bool_false_error_code_is_not_success`,
`test_crash_recovery_resume_reply_without_error_code_is_not_success`,
`test_crash_recovery_resume_waits_only_for_an_int_zero_error_code`) exercise
exactly the adversarial shapes the original finding named (`False`, `{}`,
`0.0`, `"0"`, `True`, `None`, `-2`, all asserted rejected-without-waiting) and
pin the one true-acceptance case (`{"errorCode": 0}`) with a positive control
asserting `wait()` was actually called and the instrument was polled the
expected number of times — so the rejection assertions can't pass vacuously.
The harness correctly drives the real `FastService` (not a mock), confirms
the motion lock starts free (so the crash-recovery branch is actually taken),
and asserts no stray `abort`/`pause` calls and the lock is released
afterwards. This closes CR-01 both in the production code and in test
coverage; I found no new defect in the fix or its tests.

One previously-reported, still-open finding remains in the file scope of this
review and was carried forward unchanged (not touched by the gap-closure
diff):

- **WR-02** (`_is_no_error()`, `tools/fast/server.py:310-318`) still uses the
  same loose `error_code in (None, 0)` comparison that `_accepted()` was
  introduced to retire elsewhere in this file. This was out of scope for the
  02-05 gap-closure plan (which targeted CR-01 specifically) and is carried
  forward here as still open.

Two further previously-reported findings (**WR-03**, gRPC channel never
closed in `scripts/fast_status.py`; **IN-01**, `fast_dryrun.py` reaching into
private `FastServer`/`DryRunFastServer` state) concern files outside this
review's `files` scope (`scripts/fast_status.py`, `scripts/fast_dryrun.py` are
not in the config's file list, and `git diff` confirms `scripts/` is
untouched since the diff base). They are not re-verified here and are noted
only for completeness; see the phase's disposition record for their current
status.

## Warnings

### WR-02: `_is_no_error()` repeats the same loose-comparison pattern `_accepted()` was meant to retire (carried forward, still open)

**File:** `tools/fast/server.py:310-318`
**Issue:**
```python
def _is_no_error(outcome: object) -> bool:
    error_name = getattr(outcome, "error_name", None)
    error_code = getattr(outcome, "error_code", None)
    message = getattr(outcome, "message", None)
    return (error_code in (None, 0) and error_name in (None, "NoError")
            and not message)
```
`error_code in (None, 0)` is true for `error_code = False` as well
(`False == 0` in Python), the same class of bug `_accepted()` exists to
close elsewhere in this file (and that CR-01's fix just extended to
`Resume()`). `error_code` here comes from `RunOutcome` (a `fast_mcp`
dataclass) rather than a raw instrument dict, so the practical exposure is
smaller than CR-01 was, but it remains the same anti-pattern this phase
otherwise eliminates: if `fast_mcp` ever surfaces a non-int, falsy
`error_code` (e.g. from imprecise JSON deserialization upstream), an
operator-abort with a real error could be reported via `_message_for`'s
`Aborted` branch as "no error" via `_is_no_error`, silently dropping the
error detail from the operator-facing message.
**Fix:** Use the same strict check as `_accepted()`:
```python
return (type(error_code) in (type(None), int) and error_code in (None, 0)
        and error_name in (None, "NoError") and not message)
```
or factor a shared helper (e.g. `_is_real_int_zero_or_none(value)`) used by
both `_accepted()` and `_is_no_error()`, so the two can never diverge again.

---

_Reviewed: 2026-10-15T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
