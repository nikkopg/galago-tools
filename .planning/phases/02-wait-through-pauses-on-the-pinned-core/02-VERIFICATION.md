---
phase: 02-wait-through-pauses-on-the-pinned-core
verified: 2026-10-13T20:10:00Z
status: passed
score: 4/4 must-haves verified
covered_files: [".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-01-PLAN.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-01-SUMMARY.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-02-PLAN.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-02-SUMMARY.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-03-PLAN.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-03-SUMMARY.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-04-PLAN.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-04-SUMMARY.md", "tools/fast/requirements.txt", "tools/fast/server.py", "tools/tests/fast_test.py"]
covered_digest: "v3:sha256:1f3f287e5108b900e1984a41cfae94757ac28478e4d97c879ce52410eb1579c9"
behavior_unverified: 0
overrides_applied: 0
---

# Phase 2: Wait Through Pauses on the Pinned Core Verification Report

**Phase Goal:** A F.A.S.T. step stays open through any pause on the real core and ends with the
run's real outcome.
**Verified:** 2026-10-13T20:10:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

These map 1:1 to the four ROADMAP Phase 2 success criteria.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `tools/fast/requirements.txt` pins fast-mcp `b30b38d` or later, and the gate's pin test passes against that install | ✓ VERIFIED | `tools/fast/requirements.txt` line 5 pins `fast-mcp @ git+...@b30b38df48e8480f325228145ccae7915a56e437`; gate venv's `fast_mcp` `direct_url.json` records `vcs_info.commit_id == b30b38df...` installed from the local clone (`file:///home/formulatrix/data/nikko/fast/fast-mcp`), confirmed live by `python -c "importlib.metadata..."`; `TestRequirementsPin.test_requirements_txt_pins_exactly_one_credential_free_sha` passes (re-run) |
| 2 | With the real core (stub transport), a paused run keeps the `Transfer` step open, `run_state` shows the pause, and the step ends SUCCESS after a resume | ✓ VERIFIED | `tools/fast/server.py` Transfer/RunProtocol both pass `RunOptions(on_pause=self._record_pause, through_pauses=True)` (confirmed by direct read, lines 719/742); `TestPauseThroughRealCore.test_paused_transfer_stays_open_and_ends_success_after_resume` (and the operator-pause and RunProtocol-instrument-pause siblings) re-run and pass against the real core over a stub transport through the real in-process gRPC stub |
| 3 | An operator abort ends the step "run aborted by operator at `<p>`%"; a timeout still never aborts | ✓ VERIFIED | `_message_for`'s Aborted branch (lines 347-354) and the `operator_abort` flag wiring (`Abort` sets it only via `_accepted(result)`, `Transfer`/`RunProtocol` read it once under `_run_state_lock`) read exactly as documented; `TestOperatorAbortWording` (5 tests) and `TestOperatorAbortRealCore` (3 real-core gRPC tests) re-run and pass; `TestPausedTimeExcludedFromTimeout.test_the_same_time_running_times_out_and_never_commands_the_instrument` re-run and passes, asserting no pause/resume/abort call on a timeout |
| 4 | Paused time doesn't count toward the run timeout | ✓ VERIFIED | `TestPausedTimeExcludedFromTimeout` (6 tests: far-longer-than-timeout pause ends SUCCESS, threshold inclusive at poll granularity, paused time excluded at poll granularity, RunProtocol's per-command timeout behaves identically, two pause episodes record twice) re-run and pass against the real core with an injected fake clock; D-12 AST check confirms `tools/fast/server.py` imports no `time` module and touches no `monotonic`/`perf_counter`/`deadline` — the adapter owns no clock of its own |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tools/fast/requirements.txt` | fast-mcp pin at b30b38d + reason comment | ✓ VERIFIED | One non-comment pin line at the exact SHA; comment names the wait-through-pauses core and the GitLab-push Phase 3 prerequisite |
| `tools/fast/server.py` | Transfer/RunProtocol wait through pauses; operator-abort wording; no adapter-owned clock | ✓ VERIFIED | `through_pauses=True`/`on_pause=self._record_pause` in both RunOptions calls; `_run_record["operator_abort"]`, `Abort`, `_message_for`, `_accepted` all present and match plan intent; `tools/base_server.py` byte-identical to `c9a89cf` |
| `tools/tests/fast_test.py` | Real-core gRPC fixture + pause/abort/timeout proof suites | ✓ VERIFIED | `_Stepper`, `_stub_transport`, `_real_core`, `_RealCoreGrpcTestCase`, `TestPauseThroughRealCore`, `TestOperatorAbortRealCore`, `TestPausedTimeExcludedFromTimeout`, `TestRequirementsPin`'s two gate tests, `TestOperatorAbortWording` all present and passing |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `tools/fast/server.py` Transfer/RunProtocol | `fast_mcp.run_control.RunOptions` | `on_pause=self._record_pause, through_pauses=True` | WIRED | Confirmed by direct read at lines 719-721 and 742-744 |
| `tools/fast/server.py` Abort | `tools/fast/server.py` `_run_record` | `_run_record["operator_abort"] = True` under `_accepted(result)` | WIRED | Confirmed lines 887-889 |
| `tools/fast/server.py` Transfer/RunProtocol | `tools/fast/server.py` `_message_for` | flag read once under `_run_state_lock`, passed via `_result_reply` | WIRED | Confirmed lines 724-726, 747-749 |
| `tools/fast/requirements.txt` | gate venv `fast_mcp` dist-info | `TestRequirementsPin` compares pinned SHA to `direct_url.json` | WIRED | Live check: `direct_url.json` commit_id matches; test passes |
| `tools/tests/fast_test.py` real-core tests | `fast_mcp.service.FastService` | real core over a `MagicMock` transport, paced by `_Stepper`/fake clock | WIRED | All real-core test classes re-run and pass |

### Behavioral Spot-Checks

Full gate re-run plus targeted named-test re-runs (not a filtered grep of one full run — each invocation below is independent):

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Pin installed and gate passes | `python -c "importlib.metadata...direct_url.json"` | `commit_id == b30b38df...`, url is the local clone | ✓ PASS |
| Paused Transfer/RunProtocol stays open, ends SUCCESS | `unittest ... TestPauseThroughRealCore -v` | 3/3 ok | ✓ PASS |
| Operator/instrument abort wording and real-core proof | `unittest ... TestOperatorAbortWording TestOperatorAbortRealCore -v` | 8/8 ok | ✓ PASS |
| Paused time excluded from timeout; timeout never aborts | `unittest ... TestPausedTimeExcludedFromTimeout -v` | 6/6 ok | ✓ PASS |
| Gate rejects a core without the capability | `unittest ... TestRequirementsPin -v` | 3/3 ok | ✓ PASS |
| Full project gate | `PATH=.../galago-py310/bin:$PATH bash bin/make proto test` | exit 0, ruff clean, mypy clean, 143 unittest + 143 pytest passed | ✓ PASS |
| D-12: adapter owns no clock | AST scan for `time` import / `monotonic`/`perf_counter`/`deadline` in `server.py` | no matches | ✓ PASS |
| D-07: crash-recovery Resume passes neither `on_pause` nor `through_pauses` | AST scan of `Resume`'s `.wait(...)` call kwargs | `{'on_progress', 'timeout_s'}` only, no `RunOptions` call in `Resume` | ✓ PASS |
| `tools/base_server.py` untouched | `git diff --exit-code c9a89cf -- tools/base_server.py` | exit 0 | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| LIVE-01 | 02-01, 02-02 | pin to b30b38d or later + installed-core gate check | ✓ SATISFIED | requirements.txt pin + `TestRequirementsPin` (3 tests, all passing, including the two gate tests added by 02-02) |
| LIVE-02 | 02-01, 02-03, 02-04 | Transfer/RunProtocol wait through pauses, end SUCCESS/operator-abort wording | ✓ SATISFIED | `TestPauseThroughRealCore`, `TestOperatorAbortWording`, `TestOperatorAbortRealCore`, `TestPausedTimeExcludedFromTimeout.test_each_pause_episode_records_once` |
| LIVE-03 | 02-04 | paused time excluded from run timeout | ✓ SATISFIED | `TestPausedTimeExcludedFromTimeout` (6 tests) |

No orphaned requirements: REQUIREMENTS.md's Traceability table maps exactly LIVE-01/02/03 to Phase 2, and all three appear in at least one plan's `requirements:` frontmatter field.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tools/fast/server.py` | 125, 140, 145 | "PLACEHOLDER" in comments (`EST_*` timing constants) | ℹ️ Info | Pre-existing Phase 1 content, byte-identical to the `c9a89cf` baseline (confirmed by diff); not introduced or touched by this phase; already tracked as a deliberate, documented deferral (D-16, RESEARCH.md Pitfalls 7/8), not an unresolved debt marker on phase-2-modified code |

No `TBD`/`FIXME`/`XXX` markers found in any phase-2-modified file. No empty implementations, no hardcoded-empty stub patterns, no console.log-only handlers.

### Code Review Findings (carried forward)

The phase's own code-review cycle (`02-REVIEW.md` → `02-REVIEW-FIX.md` → `02-REVIEW-DISPOSITION.md`) is part of this phase's record and was checked against the current tree, not just trusted:

- **WR-01** (warning, `errorCode == 0` boolean/int ambiguity gating operator-abort attribution): disposition `fixed` in commit `d9acdcf`. Verified live: `_accepted(result)` (lines 380-392) requires `type(code) is int and code == 0`, used at both `Abort`'s operator-abort bookkeeping (line 887) and `_recovery_reply`'s SUCCESS mapping (line 403). Regression tests (`test_abort_bool_false_error_code_is_not_success`, `test_abort_bool_true_error_code_is_not_success`, `test_abort_str_zero_error_code_is_not_success`, and the extended `test_only_an_accepted_abort_sets_the_flag`) re-run and pass.
- **IN-01** (info, `_message_for`'s Aborted branch complexity): disposition `open`, no action required per the reviewer's own note — not a blocker.

Note: the `_accepted` helper added by the WR-01 fix is a new `FunctionDef` in `tools/fast/server.py` added after plan 02-03 completed (which itself had a D-17 "no new function" constraint scoped to that plan's own tasks). This is an intentional, reviewed, and tested post-plan safety fix, not an unaccounted deviation — `TestAdapterInvariant` was re-confirmed green with `_accepted` present (it introduces no new control-method call, so no invariant rule update was needed), and the full gate (143 tests) passes.

### Human Verification Required

None. Every observable truth for this phase is proven against the real fast-mcp core (not mocked) over a stub transport, reached through the real in-process gRPC stub, with deterministic pacing (`_Stepper`, fake clock) — no visual, UX, or external-service behavior requiring human judgment falls within this phase's scope. The two explicitly flagged open items are documented Phase 3 prerequisites, not phase 2 gaps:
- A clean install from the GitLab URL (rather than the local clone) is untested until `fix/run-recovery-gate` is pushed to GitLab — this is the user's own action and explicitly named a Phase 3 prerequisite in both `02-CONTEXT.md` (D-02) and the plans' "Flagged assumptions" sections.
- A few race-condition edges (a control command landing in the exact same poll as an instrument state change) are explicitly flagged as unprobed in the plans' "Flagged assumptions" sections; these are deferred, not silently missed, and do not contradict any of the four roadmap success criteria.

### Gaps Summary

None. All four ROADMAP Phase 2 success criteria are independently verified against the live codebase (not merely SUMMARY claims): the pin and its gate test, the paused-Transfer-stays-open-and-resumes-to-SUCCESS behavior, the operator-abort wording plus timeout-never-aborts behavior, and the paused-time-excluded-from-timeout behavior. The full project gate passes (143 unittest + 143 pytest, ruff clean, mypy clean), `tools/base_server.py` is untouched, all three phase requirements (LIVE-01/02/03) are satisfied with no orphans, and the phase's own code-review warning (WR-01) was fixed and its fix independently re-verified.

---

_Verified: 2026-10-13T20:10:00Z_
_Verifier: Claude (gsd-verifier)_
