---
phase: 01-adapter-control-path-run-state
fixed_at: 2026-10-13T02:40:20Z
review_path: .planning/phases/01-adapter-control-path-run-state/01-REVIEW.md
iteration: 1
findings_in_scope: 2
fixed: 2
skipped: 0
status: all_fixed
---

# Phase 01: Code Review Fix Report

**Fixed at:** 2026-10-13T02:40:20Z
**Source review:** .planning/phases/01-adapter-control-path-run-state/01-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 2 (critical_warning scope: CR-01, WR-01; IN-01/IN-02/IN-03 out of scope)
- Fixed: 2
- Skipped: 0

**Verification environment:** All fixes were applied and verified inside an isolated git
worktree (`git worktree add -b gsd-reviewfix/01-2098844 ...`), then fast-forwarded onto
`feat/fast-tool` and torn down. The gate command (`PATH=.../galago-py310/bin:$PATH bash
bin/make proto test`) was run from that worktree after each commit; results are reproducible
by re-running the same command against the resulting commits on `feat/fast-tool` in the main
checkout -- the worktree itself no longer exists.

## Fixed Issues

### CR-01: `_run_in_flight()` resets the run record on every entry, not just the first, silently clobbering an in-flight pause

**Files modified:** `tools/fast/server.py`, `tools/tests/fast_test.py`
**Commit:** 581dec7
**Applied fix:** Matched the reviewer's suggested fix exactly -- `_run_in_flight()`'s entry
path now only (re)initializes `self._run_record` on the `0 -> 1` transition of
`self._active_runs`, mirroring the existing `if self._active_runs == 0:` guard already used
on the exit path. Also updated the method's docstring to describe the guarded entry
behavior. Added a regression test,
`TestSimulatedTransferOverGrpc::test_pause_recorded_during_one_run_survives_a_second_overlapping_runs_entry`,
which records a pause (via `simulate_pause`) for one simulated run while it is still in
flight, then starts a second overlapping simulated run and asserts the first run's pause
is still reported (`state: "paused"` with its detail) through the second run's entry, through
the first run's exit (since one run is still in flight), and only clears to idle once both
runs have ended.

### WR-01: `_log_progress` writes `percent` into `run_state` without the `_run_percent()` sanitization every other path uses

**Files modified:** `tools/fast/server.py`, `tools/tests/fast_test.py`
**Commit:** cb7886d
**Applied fix:** Matched the reviewer's suggested fix exactly -- `_log_progress` now routes
`percent` through `_run_percent()` before storing it, using the same "only overwrite when
valid" pattern already used in `_record_pause` (an invalid value leaves the previously
recorded percent untouched rather than being stored verbatim). Added a regression test,
`TestRunState::test_log_progress_sanitizes_the_percent_like_every_other_path`, which calls
`_log_progress` directly with NaN, +/-infinity, `True`/`False`, and a string value and
asserts each reads back as `None` in `run_state`, plus a case confirming a later invalid
value does not clobber an earlier valid one. The deliberately-invalid test inputs required
`# type: ignore[arg-type]` on the two calls that violate `_log_progress`'s `percent: int`
annotation (consistent with existing precedent elsewhere in this test file, e.g.
`fast_test.py:197`, `:1793`, `:1799`).

## Skipped Issues

None -- both in-scope findings were fixed.

## Out of Scope (not attempted, per `fix_scope: critical_warning`)

- IN-01: `_run_record`'s initial state seeded as `"running"` instead of `"idle"`
- IN-02: `tool_base.proto` missing trailing newline
- IN-03: `_run_percent`'s return type annotation doesn't cover its `int` branch

## Verification

After each commit, the full gate was run and confirmed green:
`PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto test`
(ruff check, mypy --config-file=pyproject.toml tools, unittest, pytest).

- After CR-01 commit: 119 tests passed (118 baseline + 1 new).
- After WR-01 commit: 120 tests passed (119 + 1 new).
- Ruff: all checks passed in both runs.
- Mypy: no issues in both runs (after adding `# type: ignore[arg-type]` to the two
  deliberately-invalid-type test calls in the WR-01 regression test).
- `tools/base_server.py` was not modified by either fix.
- `TestAdapterInvariant::test_adapter_obtains_service_only_through_open_service` (the AST
  invariant checker, `_adapter_invariant_violations`) still returns `[]` for `server.py` after
  both fixes -- `_log_progress` and `_run_in_flight` remain record-only with no service calls.

---

_Fixed: 2026-10-13T02:40:20Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
