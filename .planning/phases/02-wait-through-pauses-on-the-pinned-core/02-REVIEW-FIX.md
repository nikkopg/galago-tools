---
phase: 02-wait-through-pauses-on-the-pinned-core
fixed_at: 2026-10-13T20:04:00Z
review_path: .planning/phases/02-wait-through-pauses-on-the-pinned-core/02-REVIEW.md
iteration: 1
findings_in_scope: 1
fixed: 1
skipped: 0
status: all_fixed
---

# Phase 2: Code Review Fix Report

**Fixed at:** 2026-10-13T20:04:00Z
**Source review:** .planning/phases/02-wait-through-pauses-on-the-pinned-core/02-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 1 (fix_scope: critical_warning -- WR-01 only; IN-01 is Info-tier and out of scope)
- Fixed: 1
- Skipped: 0

## Fixed Issues

### WR-01: `errorCode == 0` boolean/int ambiguity now gates operator-abort attribution, not just the reply code

**Files modified:** `tools/fast/server.py`, `tools/tests/fast_test.py`
**Commit:** d9acdcf
**Applied fix:** Added a single shared helper, `_accepted(result) -> bool`, defined just above
`_recovery_reply` in `tools/fast/server.py`. It returns `True` only when `result` is a `dict` whose
`errorCode` is the literal `int` `0` (`type(code) is int and code == 0`), mirroring the rule
`fast_mcp.orchestration._pause_info` already uses for the same distinction. Both safety-sensitive call
sites now go through this one helper instead of the bare `errorCode == 0` comparison:
- `Abort()`'s operator-abort bookkeeping (`tools/fast/server.py`, inside the `Abort` method) now calls
  `if _accepted(result):` before setting `self._run_record["operator_abort"] = True` under
  `_run_state_lock`.
- `_recovery_reply`'s SUCCESS mapping (shared by `Pause`, `Abort`, and the crash-recovery `Resume`
  path) now calls `if _accepted(result):` before returning `SUCCESS`; anything else (including a
  bool/str/missing `errorCode`) falls through to the existing `ERROR_FROM_TOOL` branch with the actual
  `errorCode` value in the message.
- `_accepted()` takes a plain `dict | Refused` value and never touches `self.service` or any other
  adapter/instrument state, so `TestAdapterInvariant` stays green and no new adapter-invariant rule was
  needed (confirmed by rerunning that test class after the fix).

TDD was followed: the regression tests were added and run first to observe the `False`-errorCode case
fail (`True is not False` / `1 != 7` under the old `== 0` check), then the fix was applied and the same
tests were rerun to confirm they pass.

Regression tests added:
- `TestOperatorAbortWording.test_only_an_accepted_abort_sets_the_flag` (`tools/tests/fast_test.py`):
  extended the existing case table with `bool_false_error_code` (`{"errorCode": False}`),
  `bool_true_error_code` (`{"errorCode": True}`), and `str_zero_error_code` (`{"errorCode": "0"}`), all
  asserting the operator-abort flag stays `False` and the reply is `ERROR_FROM_TOOL` (only the
  `accepted` case -- real int `0` -- sets the flag and returns `SUCCESS`).
- `TestRecoveryCommands.test_abort_bool_false_error_code_is_not_success`,
  `test_abort_bool_true_error_code_is_not_success`, and `test_abort_str_zero_error_code_is_not_success`
  (`tools/tests/fast_test.py`): exercise `_recovery_reply` via `Abort()` against a real `FastService`
  wrapping a stubbed transport, asserting `ERROR_FROM_TOOL` for each non-int `errorCode` shape.

**Verification:**
- Tier 1: re-read both modified regions (`_accepted`/`_recovery_reply` in `tools/fast/server.py`, the
  `Abort()` call site, and the new/extended tests in `tools/tests/fast_test.py`) -- fix text present,
  surrounding code intact.
- Tier 2/3: ran the full project gate, `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash
  bin/make proto test`, inside the isolated worktree. Ruff check: all checks passed. Mypy
  (`tools` package): no issues found in 89 source files. `python -m unittest discover`: 143 tests, OK.
  `pytest tools/tests/`: 143 passed (up from the 140-test baseline noted in the brief, reflecting the 3
  new regression tests added by this fix). `tools/base_server.py` was not touched.
- This is a pure boolean/type-check correctness fix (not an ambiguous logic judgment call), and the
  committed behavior was directly validated by the regression tests above (red before the fix, green
  after) plus the full project gate, so it is recorded as `fixed`, not `fixed: requires human
  verification`.

## Skipped Issues

None -- the only in-scope finding (WR-01) was fixed. (IN-01 is Info-tier and excluded by
`fix_scope: critical_warning`; it was left untouched as instructed, with no action required per the
reviewer's own note.)

---

_Fixed: 2026-10-13T20:04:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
