---
phase: 02-wait-through-pauses-on-the-pinned-core
reviewed: 2026-10-13T00:00:00Z
depth: standard
files_reviewed: 3
files_reviewed_list:
  - tools/fast/requirements.txt
  - tools/fast/server.py
  - tools/tests/fast_test.py
findings:
  critical: 0
  warning: 1
  info: 1
  total: 2
status: issues_found
---

# Phase 2: Code Review Report

**Reviewed:** 2026-10-13T00:00:00Z
**Depth:** standard
**Files Reviewed:** 3
**Status:** issues_found

## Summary

Reviewed the Phase 2 diff against `e385c86` for `tools/fast/requirements.txt`, `tools/fast/server.py`
and `tools/tests/fast_test.py`: the fast-mcp re-pin to `b30b38d`, the `through_pauses=True` /
`on_pause=self._record_pause` wiring in `Transfer`/`RunProtocol`, the new `operator_abort` bookkeeping
in `Abort()`/`_message_for`/`_run_in_flight`, and the ~840 new lines of real-core tests (`_Stepper`,
`_RealCoreGrpcTestCase`, `TestPauseThroughRealCore`, `TestOperatorAbortRealCore`,
`TestPausedTimeExcludedFromTimeout`, the installed-core gate tests).

The implementation matches the locked decisions in `02-CONTEXT.md` (D-01 through D-17) closely: the
operator-abort flag is adapter-only bookkeeping set under `_run_state_lock` (never an instrument-state
check), is reset on the `_run_in_flight` 0→1 transition so it never carries into a new run, and never
leaks into the public `run_state` keys (`state`/`percent`/`pause`). The crash-recovery `Resume` path's
known gap (an operator abort landing during the lock-held, non-`_run_in_flight`-bracketed wait is not
attributed to the operator) is explicitly called out in the code's own docstring as an accepted,
documented scope boundary (D-09) and is not re-flagged here as a defect. `through_pauses`/`on_pause`
are wired identically in `Transfer` and `RunProtocol`, with the crash-recovery `Resume` wait correctly
omitting both (D-07), matched by `test_resume_wait_uses_a_fresh_handle_and_transfer_options`.

One genuine robustness gap was found in the new operator-abort bookkeeping (see WR-01 below): the
success check reused from the pre-existing `_recovery_reply` pattern (`errorCode == 0`) is now also
used to decide whether to *attribute an abort to the operator*, which is exactly the safety-sensitive
distinction this module's header docstring says must never be gotten wrong ("never attribute a
non-operator abort to the operator"). Python's `False == 0` means a malformed/boolean `errorCode`
would silently satisfy this check.

No critical/blocker issues were found. No hardcoded secrets, no dangerous functions, no SQL/command
injection surfaces, and no empty catch blocks were introduced by this diff.

## Warnings

### WR-01: `errorCode == 0` boolean/int ambiguity now gates operator-abort attribution, not just the reply code

**File:** `tools/fast/server.py:872-874`
**Issue:** The new operator-abort bookkeeping is:
```python
if isinstance(result, dict) and result.get("errorCode") == 0:
    with self._run_state_lock:
        self._run_record["operator_abort"] = True
```
In Python, `False == 0` evaluates to `True`. If `result["errorCode"]` is ever a JSON boolean (`false`)
rather than the integer `0` — a malformed/non-conforming instrument or stub-transport response, or a
future response-shape change elsewhere in the stack — this check passes and the adapter will record
`operator_abort=True` for a command that was not actually confirmed accepted with `errorCode: 0`.
Because `_message_for`'s `Aborted` branch uses this very flag to decide between "run aborted by
operator at &lt;p&gt;%" and the plain instrument wording, a false positive here directly violates the
module's own stated safety invariant ("never attribute a non-operator abort to the operator",
reiterated in `02-CONTEXT.md` D-09 as reversibility-costly because galago-core shows this text
verbatim). The identical `errorCode == 0` pattern already exists in `_recovery_reply`
(`tools/fast/server.py:389`), but there it only selects the ExecuteCommandReply's response code
(SUCCESS vs ERROR_FROM_TOOL) — a much lower-stakes use than operator attribution. No test in this
diff exercises `errorCode: False`/`errorCode: True` for either path (`TestOperatorAbortWording.
test_only_an_accepted_abort_sets_the_flag` only covers `0`, `-1`, `{}` and `Refused`), so this gap is
currently unverified in either direction.
**Fix:** Guard against bool explicitly before comparing, e.g.:
```python
error_code = result.get("errorCode")
if isinstance(result, dict) and error_code == 0 and not isinstance(error_code, bool):
    with self._run_state_lock:
        self._run_record["operator_abort"] = True
```
or centralize the "accepted" check (e.g. a small `_accepted(result) -> bool` helper used by both
`Abort()` and `_recovery_reply`) so the stricter definition is enforced in exactly one place, and add
a regression test with `errorCode: False`.

## Info

### IN-01: `_message_for`'s `Aborted` branch complexity grew with the new operator-abort wording

**File:** `tools/fast/server.py:347-354`
**Issue:** The `Aborted` branch now nests an `if operator_abort` / inner `if outcome_text != _NO_ERROR_TEXT`
inside the already-large `_message_for` if/elif chain (ten result kinds). Not a defect — the new tests
(`TestOperatorAbortWording`) cover all four combinations of `operator_abort` × error-present — but the
function is becoming a reasonable candidate for a small per-kind dispatch table if more wording
variants are added in a future phase, to keep this function's cyclomatic complexity from climbing
further.
**Fix:** No action required now; consider extracting an `_aborted_text(result, operator_abort)` helper
if a future phase adds another conditional to this branch.

---

_Reviewed: 2026-10-13T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
