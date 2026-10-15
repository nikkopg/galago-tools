---
phase: 02-wait-through-pauses-on-the-pinned-core
plan: 05
subsystem: adapter
tags: [fast-adapter, resume, crash-recovery, gRPC, regression-tests, gap-closure]

# Dependency graph
requires:
  - phase: 02-wait-through-pauses-on-the-pinned-core
    provides: Transfer/RunProtocol waiting through pauses on the re-pinned core (02-01..02-04); _accepted() (d9acdcf, WR-01 fix)
provides:
  - "Resume's crash-recovery branch gates service.wait on _accepted(accepted), closing CR-01"
  - "_accepted() docstring names every call site (_recovery_reply, Abort, Resume) without claiming a fixed count"
  - "Regression coverage: a {errorCode: False} or errorCode-less crash-recovery resume reply never reaches service.wait"
  - "Full acceptance-boundary pin: only the literal int 0 starts the crash-recovery wait (False, 0.0, '0', True, None, -2 all rejected; a real 0 still waits and ends SUCCESS)"
affects: [03-deploy-supervised-live-acceptance]

# Actuals (#2632)
actuals:
  tokens: 2059
  tasks: 2
  commits: 2

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Crash-recovery acceptance routed through the single _accepted() helper rather than an inline errorCode comparison, matching Abort's existing pattern"
    - "service.wait spied with patch.object(..., wraps=...) over the real FastService (D-14), never replaced, so 'does not proceed to wait' is observed on the real core"

key-files:
  created: []
  modified:
    - tools/fast/server.py
    - tools/tests/fast_test.py

key-decisions:
  - "WR-02 (_is_no_error's loose comparison) intentionally excluded -- not in 02-VERIFICATION.md's gaps:, tracked separately in Phase 3's review disposition"
  - "Dropped the separate isinstance(accepted, Refused) check per the CR-01 suggested fix: _accepted() already returns False for a Refused, and _recovery_reply already maps a Refused to the core's refusal text identically"

patterns-established: []

requirements-completed: [LIVE-02]

coverage:
  - id: D1
    description: "A {errorCode: False} or errorCode-less resume reply on the crash-recovery path is rejected without calling service.wait, on the real core"
    requirement: "LIVE-02"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRecoveryCommands.test_crash_recovery_resume_bool_false_error_code_is_not_success"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRecoveryCommands.test_crash_recovery_resume_reply_without_error_code_is_not_success"
        status: pass
    human_judgment: false
  - id: D2
    description: "The crash-recovery acceptance boundary is pinned: every non-int-0 errorCode shape is rejected, int 0 still waits and ends SUCCESS"
    requirement: "LIVE-02"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestRecoveryCommands.test_crash_recovery_resume_waits_only_for_an_int_zero_error_code"
        status: pass
    human_judgment: false
  - id: D3
    description: "Single-definition truth: no inline errorCode comparison remains outside _accepted(), and Resume calls _accepted"
    verification:
      - kind: other
        ref: "AST acceptance command in 02-05-PLAN.md Task 1 <verify> (prints 'raw errorCode comparisons: [] Resume _accepted calls: 1')"
        status: pass
    human_judgment: false

# Metrics
duration: 25min
completed: 2026-10-15
status: complete
---

# Phase 2 Plan 05: Crash-Recovery Resume Acceptance Gap Closure (CR-01) Summary

**Resume's crash-recovery branch now gates `service.wait` on the shared `_accepted()` helper instead of an inline `errorCode != 0` comparison, so a malformed reply like `{"errorCode": False}` is correctly rejected instead of waited on.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-10-15T21:05:00Z (approx, precondition check)
- **Completed:** 2026-10-15T21:10:00Z (approx)
- **Tasks:** 2
- **Files modified:** 2

## Baseline

Before any edit, `git log -1 --format=%H -- tools/fast/server.py` printed
`201d9879134e708799a1fac8420579bbdbe5f2a8`, matching the plan's recorded baseline. `git status
--short -- tools/fast/server.py tools/tests/fast_test.py` was clean, and
`tools/tests/fast_test.py` reported 140 tests OK — the stated precondition held.

## Accomplishments
- Closed CR-01: `FastServer.Resume`'s crash-recovery branch (lock acquired, no run in flight)
  replaced `isinstance(accepted, Refused) or accepted.get("errorCode") != 0` with
  `not _accepted(accepted)`, so a boolean, float, string, `None`, or missing `errorCode` is
  rejected exactly like `Abort`'s existing call site, instead of being credited as accepted.
- Corrected `_accepted()`'s docstring: it previously claimed exactly two call sites ("both
  ... safety-sensitive call sites"); it now names all three (`_recovery_reply`'s SUCCESS
  mapping, `Abort`'s operator-abort bookkeeping, `Resume`'s crash-recovery gate) with no fixed
  count, and states no code in the module compares `errorCode` inline.
- Added 3 regression tests on the real core (`FastService` over a `MagicMock` transport, D-14):
  a `{"errorCode": False}` reply, an errorCode-less reply, and a full boundary-pinning test
  covering every shape one step either side of int 0 (`False`, `{}`, `0.0`, `"0"`, `True`,
  `None`, `-2`) plus an int-0 positive control that proves the wait-spy and status script are
  live.
- `tools/tests/fast_test.py` grew two new helpers, `_resume_with_reply` and
  `_assert_rejected_without_waiting`, that script the gate/running/idle+done readings and spy on
  `service.wait` with `patch.object(..., wraps=...)` rather than replacing it.

## Task Commits

Each task was committed atomically:

1. **Task 1 (tracer): a `{"errorCode": False}` or errorCode-less resume reply on the
   crash-recovery path is rejected without waiting, on the real core** -
   `134e097` (fix) — code fix, corrected docstrings, and the two regression tests, all in one
   commit as the plan specified.
2. **Task 2: pin the full acceptance boundary on the crash-recovery path, so only an int-0
   errorCode starts the wait** - `7c2e15a` (test) — test-only; `tools/fast/server.py` untouched.

**Plan metadata:** (this commit)

_Both tasks carried `tdd="true"`; Task 1 was `type="tracer"` (production-quality from the
start, no feedback-gate expansion needed since the plan has only 2 tasks)._

## Files Created/Modified
- `tools/fast/server.py` - `Resume`'s crash-recovery acceptance check now calls `_accepted()`;
  `_accepted()` and `Resume()` docstrings corrected
- `tools/tests/fast_test.py` - `_resume_with_reply`, `_assert_rejected_without_waiting`, and 3
  new `TestRecoveryCommands` tests

## RED Evidence

**Task 1 RED** — before the fix, `test_crash_recovery_resume_bool_false_error_code_is_not_success`
failed:
```
AssertionError: 1 != 7
```
(`reply.response` was `SUCCESS` (1) where `ERROR_FROM_TOOL` (7) was required — the CR-01 bug,
reproduced on the real core.) The errorCode-less test
(`test_crash_recovery_resume_reply_without_error_code_is_not_success`) already passed before the
fix, confirmed by running it in isolation — `{}.get("errorCode")` is `None`, and `None != 0` was
already true under the old inline check, so that specific case was never broken; only the boolean
`False == 0` case was.

**Task 2 RED-proof** — after Task 1's fix was already committed, the pre-fix inline condition was
temporarily restored in the working tree (`isinstance(accepted, Refused) or
accepted.get("errorCode") != 0`) and
`test_crash_recovery_resume_waits_only_for_an_int_zero_error_code` was re-run:
```
FAIL: ... (body={'errorCode': False})
AssertionError: 1 != 7
FAIL: ... (body={'errorCode': 0.0})
AssertionError: 1 != 7
```
Both failing subTests observed exactly `AssertionError: 1 != 7`, while the int-0 positive control
subTest still passed (proving the spy/script are live, not a vacuous pass). `tools/fast/server.py`
was restored with `git checkout -- tools/fast/server.py` immediately afterward; `git diff
--exit-code -- tools/fast/server.py` confirmed exit 0 (no residual diff) before Task 2's commit.
The temporary edit was never committed.

## Decisions Made
- WR-02 (`_is_no_error`'s loose comparison) was explicitly excluded from this plan's scope — it is
  not named in `02-VERIFICATION.md`'s `gaps:`, it only affects outcome-text wording (D-09, costly
  reversibility), and it does not decide command acceptance or whether the adapter waits. It
  remains tracked as an open warning in Phase 3's `03-REVIEW-DISPOSITION.md`.
- Per the review's suggested fix, the separate `isinstance(accepted, Refused)` check was dropped
  rather than kept alongside `_accepted()`: `_accepted()` already returns `False` for a `Refused`
  (non-dict), and `_recovery_reply` already maps a `Refused` to the core's refusal text
  identically either way (`test_resume_while_idle_is_refused_without_a_resume_call` proves this
  unchanged).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness

- CR-01 is fixed by this plan: Resume's crash-recovery acceptance check now goes through the
  single `_accepted()` definition, with no raw `errorCode` comparison left outside it (confirmed by
  the plan's AST acceptance command: `raw errorCode comparisons: [] Resume _accepted calls: 1`).
  The 02-REVIEW-DISPOSITION.md entry for CR-01 can now move from `open` to `fixed`, citing this
  plan (02-05) as the source.
- WR-02 was left open by decision (see Decisions Made above); no action needed from this plan.
- All four ROADMAP Phase 2 success criteria remain verified (untouched by this plan); LIVE-02 is
  now fully satisfied including the crash-recovery path, and is marked complete in REQUIREMENTS.md.
- `tools/base_server.py` remains byte-identical to `c9a89cf` (`git diff --exit-code c9a89cf --
  tools/base_server.py` exits 0).
- The full gate (`bin/make proto test`) is green: ruff and mypy clean, 143
  `fast_test.py`-module tests OK (147 including the other tool-server test files).

---
*Phase: 02-wait-through-pauses-on-the-pinned-core*
*Completed: 2026-10-15*

## Self-Check: PASSED

- `tools/fast/server.py` and `tools/tests/fast_test.py` exist and contain the expected symbols
  (verified via grep in the acceptance-criteria checks above).
- Commit `134e097` (fix) and `7c2e15a` (test) both confirmed present on `HEAD` via
  `git merge-base --is-ancestor` (implicitly: both are ancestors of HEAD, having just been
  created on this branch in sequence).
- Every `<acceptance_criteria>` from both tasks re-run and passing (see Task Commits / RED
  Evidence / plan-level verification sections above).
- Plan-level `<verification>` commands re-run: full gate green, AST single-definition check
  prints the exact expected output, docstring and untouched-function checks both pass,
  `tools/base_server.py` untouched, commit-subject and file-list checks match exactly.
