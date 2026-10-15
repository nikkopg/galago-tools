---
phase: 02-wait-through-pauses-on-the-pinned-core
verified: 2026-10-15T21:20:00Z
status: passed
score: 5/5 must-haves verified
covered_files: [".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-01-PLAN.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-01-SUMMARY.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-02-PLAN.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-02-SUMMARY.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-03-PLAN.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-03-SUMMARY.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-04-PLAN.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-04-SUMMARY.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-05-PLAN.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-05-SUMMARY.md", "tools/fast/requirements.txt", "tools/fast/server.py", "tools/tests/fast_test.py"]
covered_digest: "v3:sha256:d387108b133681514a4b81536702664b0eeca5b55808b9c67d93b77b3e7877c7"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 4/4
  gaps_closed:
    - "Every safety-sensitive acceptance check this phase relies on goes through the single strict _accepted() definition, with no call site still using a raw errorCode comparison (CR-01)"
  gaps_remaining: []
  regressions: []
---

# Phase 2: Wait Through Pauses on the Pinned Core Verification Report

**Phase Goal:** A F.A.S.T. step stays open through any pause on the real core and ends with the
run's real outcome.
**Verified:** 2026-10-15T21:20:00Z
**Status:** passed
**Re-verification:** Yes — after gap-closure plan 02-05, which targeted the single gap (CR-01) in
the prior 02-VERIFICATION.md

## Goal Achievement

### Observable Truths

The first four map 1:1 to the four ROADMAP Phase 2 success criteria (regression-checked, not just
re-read from the prior report). The fifth is the CR-01 gap this round closes.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `tools/fast/requirements.txt` pins fast-mcp `b30b38d` or later, and the gate's pin test passes | ✓ VERIFIED | Pin line unchanged (`b30b38df48e8480f325228145ccae7915a56e437`); `TestRequirementsPin` (3 tests) independently re-run, pass |
| 2 | With the real core (stub transport), a paused run keeps the `Transfer` step open, `run_state` shows the pause, and the step ends SUCCESS after a resume | ✓ VERIFIED | `TestPauseThroughRealCore` (3 tests) independently re-run, pass; `RunOptions(..., on_pause=self._record_pause, through_pauses=True)` confirmed present (direct read) in both `Transfer` and `RunProtocol` |
| 3 | An operator abort ends the step "run aborted by operator at `<p>`%"; a timeout still never aborts | ✓ VERIFIED | `TestOperatorAbortWording` (6 tests — corrects the prior report's miscount of 7) and `TestOperatorAbortRealCore` (3 tests) independently re-run, pass; `TestPausedTimeExcludedFromTimeout.test_the_same_time_running_times_out_and_never_commands_the_instrument` re-run, passes |
| 4 | Paused time doesn't count toward the run timeout | ✓ VERIFIED | `TestPausedTimeExcludedFromTimeout` (6 tests) independently re-run, pass |
| 5 | CR-01 closed: Resume's crash-recovery branch gates `service.wait` on `_accepted(accepted)`, not a raw `errorCode` comparison; no call site outside `_accepted()`'s own body compares `errorCode` inline | ✓ VERIFIED | Direct read of `tools/fast/server.py` lock-acquired branch: `if not _accepted(accepted): return _recovery_reply("resume", accepted)`; AST single-definition check independently re-run, prints `raw errorCode comparisons: [] Resume _accepted calls: 1`; 3 new regression tests (`test_crash_recovery_resume_bool_false_error_code_is_not_success`, `test_crash_recovery_resume_reply_without_error_code_is_not_success`, `test_crash_recovery_resume_waits_only_for_an_int_zero_error_code`) independently re-run, all pass |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tools/fast/requirements.txt` | fast-mcp pin at b30b38d + reason comment | ✓ VERIFIED | Unchanged since prior verification |
| `tools/fast/server.py` | Transfer/RunProtocol wait through pauses; operator-abort wording; no adapter-owned clock; Resume's crash-recovery gate routed through `_accepted()` | ✓ VERIFIED | `gsd_run query verify.artifacts` passed (2/2); direct read confirms the fix and corrected docstrings (`_accepted`, `Resume`) |
| `tools/tests/fast_test.py` | Real-core gRPC fixture + pause/abort/timeout proof suites + CR-01 regression tests | ✓ VERIFIED | `gsd_run query verify.artifacts` passed (2/2); `_resume_with_reply`/`_assert_rejected_without_waiting` helpers and the 3 CR-01 tests present and passing |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `tools/fast/server.py` Resume (crash-recovery branch) | `tools/fast/server.py` `_accepted` | `if not _accepted(accepted): return _recovery_reply('resume', accepted)` | WIRED | `gsd_run query verify.key-links` passed (2/2); directly confirmed by code read |
| `tools/tests/fast_test.py` `TestRecoveryCommands` | `fast_mcp.service.FastService` | real core over `MagicMock` transport, `service.wait` spied with `wraps=` | WIRED | `gsd_run query verify.key-links` passed (2/2); test run confirms the spy records calls |
| `tools/fast/server.py` Transfer/RunProtocol | `fast_mcp.run_control.RunOptions` | `on_pause=self._record_pause, through_pauses=True` | WIRED | Re-confirmed by direct read; unchanged by 02-05 |
| `tools/fast/server.py` Abort | `tools/fast/server.py` `_run_record` | `_run_record["operator_abort"] = True` under `_accepted(result)` | WIRED | Re-confirmed; unchanged by 02-05 |

### Behavioral Spot-Checks

Each independently re-run as a separate process (not a filtered grep of one full run):

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| CR-01 regression: `{errorCode: False}` resume reply rejected without waiting | `unittest ...TestRecoveryCommands.test_crash_recovery_resume_bool_false_error_code_is_not_success -v` | ok | ✓ PASS |
| CR-01 regression: errorCode-less resume reply rejected without waiting | `unittest ...TestRecoveryCommands.test_crash_recovery_resume_reply_without_error_code_is_not_success -v` | ok | ✓ PASS |
| Full acceptance boundary (False, {}, 0.0, "0", True, None, -2 rejected; int 0 waits and succeeds) | `unittest ...TestRecoveryCommands.test_crash_recovery_resume_waits_only_for_an_int_zero_error_code -v` | ok (all subTests) | ✓ PASS |
| Single-definition AST check (no raw errorCode comparison outside `_accepted`, Resume calls `_accepted` once) | `python -c "import ast..."` (Task 1 verify command) | `raw errorCode comparisons: [] Resume _accepted calls: 1`, exit 0 | ✓ PASS |
| `_accepted` docstring names every call site, no fixed count | `python -c "import ast,re..."` (acceptance-criteria command) | `count words: []`, exit 0 | ✓ PASS |
| Untouched-function check (`_is_no_error`, `_message_for`, `_outcome_text`, `_recovery_reply`, `Abort`, `Transfer`, `RunProtocol` AST-identical to `201d987`) | `python -c "import ast,subprocess..."` | `changed: []`, exit 0 | ✓ PASS |
| Pin + gate, paused-Transfer, operator-abort wording, timeout-excludes-pause regressions | `unittest ...TestRequirementsPin TestPauseThroughRealCore TestOperatorAbortWording TestOperatorAbortRealCore TestPausedTimeExcludedFromTimeout -v` | 21/21 ok | ✓ PASS |
| Full project test suite (regression check) | `.../python -m unittest discover -s tools/tests/ -p "*_test.py"` | 147 tests, OK | ✓ PASS |
| Lint/type clean | `uvx ruff@0.9.4 check tools/fast/server.py tools/tests/fast_test.py` / `mypy --config-file=pyproject.toml tools/fast/server.py tools/tests/fast_test.py` | ruff "All checks passed!"; mypy "Success: no issues found in 2 source files" | ✓ PASS |
| `tools/base_server.py` untouched | `git diff --exit-code c9a89cf -- tools/base_server.py` | exit 0 | ✓ PASS |
| No uncommitted changes to covered files | `git status --short .planning tools/fast tools/tests` | only unrelated untracked `.planning/milestone.lock`/`state.json` | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| LIVE-01 | 02-01, 02-02 | pin to b30b38d or later + installed-core gate check | ✓ SATISFIED | `TestRequirementsPin` (3 tests, passing); pin line unchanged |
| LIVE-02 | 02-01, 02-03, 02-04, 02-05 | Transfer/RunProtocol wait through pauses, end SUCCESS/operator-abort wording, crash-recovery Resume ends with the run's real outcome | ✓ SATISFIED (CR-01 gap now closed) | `TestPauseThroughRealCore`, `TestOperatorAbortWording`, `TestOperatorAbortRealCore` all pass; CR-01 regression suite (`TestRecoveryCommands`, 3 new tests + boundary test) passes; AST single-definition check confirms no bypass remains |
| LIVE-03 | 02-04 | paused time excluded from run timeout | ✓ SATISFIED | `TestPausedTimeExcludedFromTimeout` (6 tests) passing |

No orphaned requirements: REQUIREMENTS.md's Traceability table maps exactly LIVE-01/02/03 to Phase
2, and all three appear in at least one plan's `requirements:` frontmatter field (02-01, 02-02,
02-03, 02-04, 02-05).

Note: REQUIREMENTS.md's Traceability table currently shows LIVE-01 and LIVE-03 as "Gaps Found" —
this reflects the prior round's overall phase status (`gaps_found`, driven by CR-01 against
LIVE-02), not a finding against LIVE-01 or LIVE-03 specifically; both were independently
re-confirmed passing in both the prior and this round. The orchestrator should update this table to
`Complete` for all three given this round's `passed` status.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tools/fast/server.py` | 125, 140, 145 | "PLACEHOLDER" in comments (`EST_*` timing constants) | ℹ️ Info | Pre-existing Phase 1 content, unrelated to this phase's or 02-05's changes; carried forward from prior report |

No `TBD`/`FIXME`/`XXX` markers found in any phase-2-covered file. No empty implementations, no
hardcoded-empty stub patterns, no console.log-only handlers. CR-01, the sole blocker from the prior
round, is confirmed fixed (see Observable Truth 5).

### Code Review Findings

`02-REVIEW-DISPOSITION.md` (re-recorded 2026-10-15, after 02-05) shows CR-01 moved from `open` to
`fixed`, sourced to plan 02-05 (commits `134e097`, `7c2e15a`), "confirmed fixed by 02-REVIEW.md
re-review." WR-01 remains `fixed`. The remaining open items — WR-02 (`_is_no_error`'s loose
comparison pattern), WR-03 (gRPC channel never closed in `fast_status.py`), IN-01 (private-state
access in `fast_dryrun.py`) — are warnings/info, explicitly out of this phase's `files_modified`
scope (not touched by any Phase 2 plan), and were already carried forward as non-blocking in the
prior round. They are not re-litigated here since gap-closure plan 02-05 explicitly and
deliberately excluded WR-02 (stated in its objective and CONTEXT) and WR-03/IN-01 were never in
scope.

### Human Verification Required

None. Every observable truth for this phase, including the CR-01 fix, is proven against the real
fast-mcp core (not mocked) over a stub transport, reached through the real in-process gRPC stub,
and independently re-run in this verification pass (not merely re-read from the SUMMARY or prior
report).

### Gaps Summary

All four ROADMAP Phase 2 success criteria remain independently verified against the current tree,
and the single gap from the prior round (CR-01: Resume's crash-recovery branch bypassing
`_accepted()`) is now closed, confirmed by direct code read, an independently re-run AST
single-definition check, and 3 independently re-run regression tests (including a full boundary
pin: every non-int-0 errorCode shape one step either side of 0 is rejected without waiting; int 0
still waits and ends SUCCESS). The full project test suite (147 tests) passes, ruff and mypy are
clean on the two touched files, `tools/base_server.py` remains byte-identical to `c9a89cf`, and all
three phase requirements (LIVE-01/02/03) are satisfied with no orphans. No regressions were found
in any of the four previously-verified truths. Phase goal achieved.

---

_Verified: 2026-10-15T21:20:00Z_
_Verifier: Claude (gsd-verifier)_
