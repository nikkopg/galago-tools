---
phase: 02-wait-through-pauses-on-the-pinned-core
verified: 2026-10-15T13:45:00Z
status: gaps_found
score: 4/4 must-haves verified
covered_files: [".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-01-PLAN.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-01-SUMMARY.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-02-PLAN.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-02-SUMMARY.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-03-PLAN.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-03-SUMMARY.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-04-PLAN.md", ".planning/phases/02-wait-through-pauses-on-the-pinned-core/02-04-SUMMARY.md", "tools/fast/requirements.txt", "tools/fast/server.py", "tools/tests/fast_test.py"]
covered_digest: "v3:sha256:bb75eee1e7f2b6ddf6ad3582d22005ff42f936a39d54b3c8997a18a54b59a8c4"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: passed
  previous_score: 4/4
  gaps_closed: []
  gaps_remaining: []
  regressions: []
gaps:
  - truth: "Every safety-sensitive acceptance check this phase relies on (whether the instrument's resume/abort/pause reply really counts as accepted) goes through the single strict _accepted() definition, with no call site still using a raw errorCode comparison"
    status: failed
    reason: >
      CR-01 (fresh code review 02-REVIEW.md, 2026-10-15, severity critical, disposition OPEN in
      02-REVIEW-DISPOSITION.md). Resume()'s crash-recovery branch in tools/fast/server.py (the
      "lock acquired, no run in flight" path this phase's own D-07/D-08 truths describe) still
      gates entry into service.wait(...) with `isinstance(accepted, Refused) or
      accepted.get("errorCode") != 0` instead of `not _accepted(accepted)`. `_accepted()` was
      added inside this same phase's review-fix cycle (commit d9acdcf, "WR-01 fail closed on
      non-int errorCode") specifically because `False == 0` in Python lets a malformed/falsy
      instrument reply (e.g. `{"errorCode": False}`) be misread as "accepted". `_accepted()`'s own
      docstring claims it is used by "both ... safety-sensitive call sites so the stricter
      definition can never diverge" -- but there is a third call site (this one), and it still has
      exactly the bug WR-01 was written to eliminate. Confirmed by direct read of the current tree
      (tools/fast/server.py, Resume's crash-recovery branch): the raw `!= 0` comparison is still
      there, and no test drives `{"errorCode": False}` (or a missing errorCode) through this
      specific branch the way `test_abort_bool_false_error_code_is_not_success` does for Abort.
      Practical effect: a malformed resume acceptance reply on the crash-recovery path is credited
      as accepted, so the adapter proceeds to wait on a run that was never actually resumed instead
      of returning the rejection -- directly undermining "ends with the run's real outcome" for
      this one path. This does not break any of the four ROADMAP success criteria as currently
      tested (the gRPC real-core Resume test takes the *other* branch -- lock not acquired, which
      does call `_accepted()` correctly, confirmed by reading `_recovery_reply`) but it is an
      unresolved, critical, in-scope finding this phase's own fix claimed to have closed everywhere.
    artifacts:
      - path: "tools/fast/server.py"
        issue: "Resume()'s crash-recovery branch (~line 939, `if isinstance(accepted, Refused) or accepted.get(\"errorCode\") != 0:`) bypasses the _accepted() helper added by this phase's own WR-01 fix"
    missing:
      - "Replace the raw check with `if not _accepted(accepted): return _recovery_reply(\"resume\", accepted)` in Resume's crash-recovery branch (tools/fast/server.py)"
      - "A regression test mirroring test_abort_bool_false_error_code_is_not_success for this exact crash-recovery Resume branch (e.g. a stubbed `{\"errorCode\": False}` resume reply must not proceed to service.wait)"
---

# Phase 2: Wait Through Pauses on the Pinned Core Verification Report

**Phase Goal:** A F.A.S.T. step stays open through any pause on the real core and ends with the
run's real outcome.
**Verified:** 2026-10-15T13:45:00Z
**Status:** gaps_found
**Re-verification:** Yes — after Phase 3 commits touched phase-2-covered files (7d77e23, 201d987
dropping the "NoError (0)" suffix from operator-abort wording; d9acdcf's WR-01 fix, already
reflected in the prior report, is also in this diff range)

## Goal Achievement

### Observable Truths

These map 1:1 to the four ROADMAP Phase 2 success criteria. All four were independently re-checked
against the current tree (not just re-read from the prior report).

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `tools/fast/requirements.txt` pins fast-mcp `b30b38d` or later, and the gate's pin test passes against that install | ✓ VERIFIED | Current file still has exactly one non-comment line, `fast-mcp @ git+...@b30b38df48e8480f325228145ccae7915a56e437`; live check: gate venv's `fast_mcp` `direct_url.json` `vcs_info.commit_id == b30b38df...`, url `file:///home/formulatrix/data/nikko/fast/fast-mcp`; `TestRequirementsPin` (3 tests) re-run and pass |
| 2 | With the real core (stub transport), a paused run keeps the `Transfer` step open, `run_state` shows the pause, and the step ends SUCCESS after a resume | ✓ VERIFIED | `tools/fast/server.py` Transfer/RunProtocol (current lines ~725-759) both still pass `RunOptions(timeout_s=..., on_progress=self._log_progress, on_pause=self._record_pause, through_pauses=True)` (confirmed by direct read and AST check); `TestPauseThroughRealCore` (3 tests: operator/instrument pause and resume) re-run and pass against the real core over a stub transport through the real in-process gRPC stub |
| 3 | An operator abort ends the step "run aborted by operator at `<p>`%"; a timeout still never aborts | ✓ VERIFIED | `_message_for`'s Aborted branch (current, ~line 353-362) now routes the "is this really an error" check through the new `_is_no_error()` helper (added by Phase 3 commit `201d987`, which also masks the live instrument's literal "NoError (0)" report, not just the adapter's own `_NO_ERROR_TEXT` fallback) instead of a direct string comparison — the operator-facing wording is unchanged and still exactly matches D-09/D-11: `TestOperatorAbortWording` (7 tests, including the new `test_message_for_treats_the_instruments_noerror_outcome_as_no_error`) and `TestOperatorAbortRealCore` (3 real-core gRPC tests) re-run and pass; `TestPausedTimeExcludedFromTimeout.test_the_same_time_running_times_out_and_never_commands_the_instrument` re-run and passes, asserting no pause/resume/abort call on a timeout |
| 4 | Paused time doesn't count toward the run timeout | ✓ VERIFIED | `TestPausedTimeExcludedFromTimeout` (6 tests) re-run and pass against the real core with an injected fake clock; AST re-check confirms `tools/fast/server.py` still imports no `time` module and touches no `monotonic`/`perf_counter`/`deadline` |

**Score:** 4/4 truths verified (0 present, behavior-unverified)

**However**, a fifth, cross-cutting concern surfaced by the phase's own fresh code review (CR-01,
below) is not covered by any of the four truths above and is tracked as a gap, not folded into the
score, because it is not one of the plan's stated must-haves — but it directly concerns the same
mechanism ("ends with the run's real outcome") this phase introduced.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tools/fast/requirements.txt` | fast-mcp pin at b30b38d + reason comment | ✓ VERIFIED | Unchanged since prior verification; one pin line at the exact SHA, reason comment intact |
| `tools/fast/server.py` | Transfer/RunProtocol wait through pauses; operator-abort wording; no adapter-owned clock | ✓ VERIFIED (with an open finding — see Gaps) | `through_pauses=True`/`on_pause=self._record_pause` intact in both RunOptions calls (AST-checked); `_run_record["operator_abort"]`, `Abort`, `_message_for`, `_accepted`, the new `_is_no_error` all present and consistent with plan intent; `tools/base_server.py` still byte-identical to `c9a89cf`; **but** `_accepted()` is not used at every call site its own docstring claims (CR-01) |
| `tools/tests/fast_test.py` | Real-core gRPC fixture + pause/abort/timeout proof suites | ✓ VERIFIED | `_Stepper`, `_stub_transport`, `_real_core`, `_RealCoreGrpcTestCase`, `TestPauseThroughRealCore`, `TestOperatorAbortRealCore`, `TestPausedTimeExcludedFromTimeout`, `TestRequirementsPin`'s two gate tests, `TestOperatorAbortWording` all present and passing; no test exercises the CR-01 branch with a malformed errorCode |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `tools/fast/server.py` Transfer/RunProtocol | `fast_mcp.run_control.RunOptions` | `on_pause=self._record_pause, through_pauses=True` | WIRED | Re-confirmed by direct read and AST check at the current line numbers |
| `tools/fast/server.py` Abort | `tools/fast/server.py` `_run_record` | `_run_record["operator_abort"] = True` under `_accepted(result)` | WIRED | Re-confirmed; `Abort` is the only setter (AST) |
| `tools/fast/server.py` Transfer/RunProtocol | `tools/fast/server.py` `_message_for` | flag read once under `_run_state_lock`, passed via `_result_reply` | WIRED | Re-confirmed |
| `tools/fast/requirements.txt` | gate venv `fast_mcp` dist-info | `TestRequirementsPin` compares pinned SHA to `direct_url.json` | WIRED | Live check re-run: `direct_url.json` commit_id matches; test passes |
| `tools/tests/fast_test.py` real-core tests | `fast_mcp.service.FastService` | real core over a `MagicMock` transport, paced by `_Stepper`/fake clock | WIRED | All real-core test classes re-run and pass |
| `tools/fast/server.py` Resume (crash-recovery branch) | `tools/fast/server.py` `_accepted` | **expected:** acceptance gated by the shared helper | **NOT WIRED** | CR-01: this call site still uses a raw `errorCode != 0` comparison, bypassing `_accepted()` entirely |

### Behavioral Spot-Checks

Independently re-run (not a filtered grep of one full run — each invocation below is a separate
process):

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Pin installed and gate passes | `python -c "importlib.metadata...direct_url.json"` | `commit_id == b30b38df...`, url is the local clone | ✓ PASS |
| Paused Transfer/RunProtocol stays open, ends SUCCESS | `unittest ... TestPauseThroughRealCore -v` | 3/3 ok | ✓ PASS |
| Operator/instrument abort wording and real-core proof | `unittest ... TestOperatorAbortWording TestOperatorAbortRealCore -v` | 10/10 ok | ✓ PASS |
| Paused time excluded from timeout; timeout never aborts | `unittest ... TestPausedTimeExcludedFromTimeout -v` | 6/6 ok | ✓ PASS |
| Gate rejects a core without the capability | `unittest ... TestRequirementsPin -v` | 3/3 ok | ✓ PASS |
| Crash-recovery / recovery-command regressions | `unittest ... TestRecoveryCommands -v` | 21/21 ok | ✓ PASS |
| Full project test module | `.venv/bin/python -m unittest discover -s tools/tests -p 'fast_test.py'` | 140 tests, OK | ✓ PASS |
| D-12: adapter owns no clock | AST scan for `time` import / `monotonic`/`perf_counter`/`deadline` in `server.py` | no matches | ✓ PASS |
| `tools/base_server.py` untouched | `git diff --exit-code c9a89cf -- tools/base_server.py` | exit 0 | ✓ PASS |
| CR-01 reproduction (code read, not a new test) | Direct read of `Resume`'s crash-recovery branch | `accepted.get("errorCode") != 0` still present, `_accepted()` not called | ✗ CONFIRMED BUG |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|--------------|--------|----------|
| LIVE-01 | 02-01, 02-02 | pin to b30b38d or later + installed-core gate check | ✓ SATISFIED | requirements.txt pin + `TestRequirementsPin` (3 tests, all passing) |
| LIVE-02 | 02-01, 02-03, 02-04 | Transfer/RunProtocol wait through pauses, end SUCCESS/operator-abort wording | ✓ SATISFIED (see CR-01 caveat) | `TestPauseThroughRealCore`, `TestOperatorAbortWording`, `TestOperatorAbortRealCore`, `TestPausedTimeExcludedFromTimeout.test_each_pause_episode_records_once` all pass; the CR-01 gap is in the crash-recovery Resume path (ADP-04's "with no run in flight" half), which LIVE-02's own text does not explicitly call out but is adjacent code this phase's review-fix cycle touched |
| LIVE-03 | 02-04 | paused time excluded from run timeout | ✓ SATISFIED | `TestPausedTimeExcludedFromTimeout` (6 tests) |

No orphaned requirements: REQUIREMENTS.md's Traceability table maps exactly LIVE-01/02/03 to Phase
2, and all three appear in at least one plan's `requirements:` frontmatter field.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tools/fast/server.py` | ~939 | Raw `accepted.get("errorCode") != 0` comparison in Resume's crash-recovery branch, bypassing `_accepted()` | 🛑 Blocker (code review CR-01, open) | A malformed/falsy instrument resume reply can be misread as accepted, so the adapter waits on a run that was never actually resumed instead of returning the rejection |
| `tools/fast/server.py` | ~310-318 | `_is_no_error()` uses `error_code in (None, 0)`, the same loose-comparison pattern `_accepted()` was written to retire (WR-02, open, warning) | ⚠️ Warning | Lower practical exposure (`error_code` comes from a `RunOutcome` dataclass, not a raw instrument dict) but the same anti-pattern; carried forward from 02-REVIEW.md, not blocking this phase's tested truths |
| `scripts/fast_status.py` | 34-51 | gRPC channel never closed (WR-03, open, warning) | ⚠️ Warning | Out of this phase's `files_modified` scope (no plan in this phase lists `scripts/fast_status.py`); noted for completeness, not counted against Phase 2 |
| `scripts/fast_dryrun.py` | 174-181 | Free function reaches into private harness state (IN-01, open, info) | ℹ️ Info | Harness-only, out of this phase's `files_modified` scope |
| `tools/fast/server.py` | 125, 140, 145 | "PLACEHOLDER" in comments (`EST_*` timing constants) | ℹ️ Info | Pre-existing Phase 1 content, unrelated to this phase's changes |

No `TBD`/`FIXME`/`XXX` markers found in any phase-2-covered file. No empty implementations, no
hardcoded-empty stub patterns, no console.log-only handlers.

**Re-verification evidence-gate note (CR-01):** `tools/fast/server.py` was git-modified after the
prior `verified:` timestamp (2026-10-13T20:10:00Z) by commits `d9acdcf` (same-day, pre-dates the
prior verification and is already reflected there), then `7d77e23`/`201d987` (2026-10-15,
post-dates it). Because the flagged file was modified since the prior verification, CR-01 blocks
unconditionally per the evidence-gate rule — it is not demoted to advisory. It is also independently
confirmed by direct reading of the current tree (not merely cited from the review), so it carries
its own deterministic evidence regardless.

### Code Review Findings (carried forward and fresh)

The phase's own code-review cycle now spans two rounds: the original (`02-REVIEW.md` v1 →
`02-REVIEW-FIX.md` → fixed WR-01) already reflected in the prior VERIFICATION.md, and a fresh,
independent review dated 2026-10-15 (current `02-REVIEW.md`, disposition recorded in
`02-REVIEW-DISPOSITION.md`) that covers everything changed since the prior review commit,
including the phase-3 wording fix that touches this phase's files.

- **CR-01** (critical, disposition `open`): Resume()'s crash-recovery acceptance check still
  bypasses `_accepted()`. Confirmed live by direct code read. **Treated as a phase-2 gap** (see
  frontmatter `gaps:`), because it undermines the general safety claim `_accepted()`'s own
  docstring makes ("the stricter definition can never diverge between the two safety-sensitive call
  sites" — there is a third, unguarded one) and sits squarely inside this phase's own `Resume`
  method (D-07/D-08 scope).
- **WR-01** (warning, originally; fixed in `d9acdcf`, already verified in the prior report):
  `_accepted()` correctly guards `Abort`'s operator-abort bookkeeping and `_recovery_reply`'s
  SUCCESS mapping. Re-confirmed live; regression tests still pass.
- **WR-02** (warning, disposition `open`): `_is_no_error()` repeats the loose-comparison pattern.
  Not blocking (lower exposure, `RunOutcome`-typed input), carried forward as an open warning.
- **WR-03**, **IN-01** (disposition `open`): outside this phase's `files_modified` scope
  (`scripts/fast_status.py`, `scripts/fast_dryrun.py`); noted, not scored against Phase 2.

### Human Verification Required

None. Every observable truth for this phase is proven against the real fast-mcp core (not mocked)
over a stub transport, reached through the real in-process gRPC stub. CR-01 is a deterministically
confirmed code defect (read directly, not a matter of judgment), so it is reported as a gap rather
than routed to human verification.

### Gaps Summary

All four ROADMAP Phase 2 success criteria remain independently verified against the live codebase
after the Phase 3 changes that touched these files (the "NoError (0)" wording fix): the pin and its
gate test, the paused-Transfer-stays-open-and-resumes-to-SUCCESS behavior, the operator-abort
wording plus timeout-never-aborts behavior (now routed through `_is_no_error` rather than a bare
string compare, with identical operator-facing results), and the paused-time-excluded-from-timeout
behavior. The full project test module passes (140 tests), `tools/base_server.py` is untouched, and
all three phase requirements (LIVE-01/02/03) are satisfied with no orphans.

However, this re-verification is not a clean pass: a fresh code review found CR-01, a critical,
unresolved (disposition `open`) defect in `Resume()`'s crash-recovery acceptance check — the exact
class of bug this phase's own WR-01 fix (`d9acdcf`) was supposed to eliminate everywhere, but
missed one call site. It does not break any of the four tested ROADMAP truths (the gRPC real-core
Resume test exercises the *other* branch, which is correctly guarded), but it is in-scope,
reproducible, and still open, so it is reported honestly as a gap rather than silently carried
forward as "fixed" the way the stale prior report implied. Recommended next step: apply the review's
own suggested fix (`if not _accepted(accepted): return _recovery_reply("resume", accepted)`) plus a
regression test mirroring `test_abort_bool_false_error_code_is_not_success` for this branch, in a
small follow-up plan or as part of this phase's gap-closure round.

---

_Verified: 2026-10-15T13:45:00Z_
_Verifier: Claude (gsd-verifier)_
