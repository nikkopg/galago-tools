---
gsd_state_version: "1.0"
milestone: v1
milestone_name: F.A.S.T. Live Run Control (adapter & rollout)
current_phase: 02
current_plan: Not started
status: completed
stopped_at: Phase 02 complete — all phases complete
last_updated: "2026-10-15T14:21:24.666Z"
last_activity: 2026-10-15
last_activity_desc: Phase 02 complete
state_head: 5858f8996209c3e36bfd0a98b08b53e6a81e7a50
progress:
  total_phases: 3
  completed_phases: 3
  total_plans: 18
  completed_plans: 18
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-15)

**Core value:** An operator running a F.A.S.T. step from Galago can always see what the instrument
is doing and recover it themselves; no adapter code path pauses, resumes or aborts on its own.
**Current focus:** Phase 02 — Wait Through Pauses on the Pinned Core
(`/gsd-complete-milestone`)

## Current Position

Phase: 02
Current Plan: Not started
Total Plans in Phase: 5
Status: All phases complete
Last activity: 2026-10-15 — Phase 02 complete

Progress: [████████████████████] 17/17 plans ([██████████] 100%)

## Performance Metrics

**Velocity:**
- Total plans completed: 18
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 5 | - | - |
| 02 | 5 | - | - |
| 03 | 8 | - | - |

**Recent Trend:**
- Last 5 plans: none yet
- Trend: -

*Updated after each plan completion*
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 01 P01 | 45min | 3 tasks | 3 files |
| Phase 01 P02 | 15min | 2 tasks | 2 files |
| Phase 01 P03 | 26min | 2 tasks | 3 files |
| Phase 01 P04 | 10 min | 2 tasks | 1 files |
| Phase 01 P05 | 25min | 2 tasks | 2 files |
| Phase 02 P01 | 15 min | 2 tasks | 3 files |
| Phase 02 P02 | 20min | 2 tasks | 2 files |
| Phase 02 P03 | 25min | 2 tasks | 2 files |
| Phase 02-wait-through-pauses-on-the-pinned-core P04 | 15min | 2 tasks | 1 files |
| Phase 03 P01 | 33min | 3 tasks | 2 files |
| Phase 03 P02 | ~2h24min | 2 tasks | 2 files |
| Phase 03 P03-03 | ~13h elapsed (active ~40min) | 3 tasks | 2 files |
| Phase 03 P04 | 15min | 3 tasks | 2 files |
| Phase 03 P05 | ~25min | 3 tasks | 2 files |
| Phase 03 P06 | ~35min (Task 3) | 3 tasks | 7 files |
| Phase 03 P07 | ~40min | 3 tasks | 2 files |
| Phase 03 P08 | ~25min | 2 tasks | 1 files |
| Phase 02 P05 | 25min | 2 tasks | 2 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Init]: Galago-side planning split per repo on 2026-10-12: this repo owns the adapter, re-pin,
  deploy and live acceptance; galago-core owns the queue, tRPC and run page. The 25 requirements
  approved in fast-mcp were re-split into ADP/LIVE (here) and QUE/UI (galago-core).
- [Init]: The fast-mcp core prerequisites already exist (`b30b38d`), so the re-pin and
  wait-through-pauses wiring is its own phase here (Phase 2) rather than waiting on another repo.
- [Phase 01]: D-05: Pause {} has no fields (soft-only); FastServer.Pause() calls service.pause(hard=False) explicitly.
- [Phase 01]: D-01/D-02/D-03: FastServer.ExecuteCommand override bypasses base_server's isReady/setStatus for pause/resume/abort only, dispatching through _dispatchCommand so _check_args still runs.
- [Phase 01]: D-06/D-07: Pause and Abort never take _motion_lock; Resume branches on a non-blocking acquire into crash-recovery (wait under lock) vs in-flight (no wait, no lock) paths.
- [Phase 01]: EST_RESUME_S stays a flat 15s placeholder; comment records the accepted debt now that Resume only waits on the crash-recovery path (research Pitfall 8)
- [Phase 01]: No implementation bugs found in Pause/Abort/Resume for Plan 01-02; all must_haves were already satisfied by Plan 01-01, so this plan is purely additive test coverage
- [Phase 01]: D-09/D-12: StatusReply.run_state = 4 sources from the adapter's own record (under a dedicated _run_state_lock, never _motion_lock) while a Transfer/RunProtocol is in flight, and from a mapped service.status() otherwise; any read-path failure collapses to {state: unknown} so the heartbeat never fails
- [Phase 01]: D-13: _PauseInfoLike declared as t.Protocol (import typing as t) to avoid colliding with the already-imported fast_mcp.model.Protocol; _record_pause accepts any to_dict()-able object, tested with a stub, no PauseInfo/ResumeMarker import
- [Phase 01]: D-15: .wait scoped to Resume/Transfer/RunProtocol per spec, even though only Resume calls it today
- [Phase 01]: D-16/D-14/D-08: no production code changes needed; server.py already satisfied every new rule, confirmed before any planted-violation test was written
- [Phase 01]: D-18: no new production code needed for simulated Pause/Resume/Abort to check arguments then succeed; existing _dispatchCommand/_check_args/base_server simulated branch already satisfied it
- [Phase 01]: D-19/D-20: _build_run_state's simulated branch derives state from pause/_active_runs directly (never _run_record["state"]), so a cleared pause can never surface as stale paused
- [Phase 01]: D-20: simulate_pause is an in-process, simulated-mode-only hook with no gRPC surface; _PAUSE_CLEARING_COMMANDS={Resume,Abort} clears a hooked pause only on a SUCCESS reply
- [Phase 02]: D-02: gate venv re-installed from local fast-mcp clone at b30b38d (--no-deps --force-reinstall); GitLab push of fix/run-recovery-gate remains a Phase 3 prerequisite
- [Phase 02]: D-08: rewrote the leading-paused Resume test to pin the re-pinned core's fixed behaviour (ResumeMarker masks a stale leading paused reading) instead of the old known-limitation assertion
- [Phase 02]: D-03: LIVE-01 gate tests join TestRequirementsPin and check state gates by calling the real core directly, leaving FastServer-level idle tests unchanged
- [Phase 02]: D-05: test_real_pause_info_records_like_the_stub passes at once (pins compatibility, does not drive a change); PauseInfo/recorder docstrings in server.py rewritten present-tense, no logic change
- [Phase 02]: D-09/D-10: operator_abort flag set inline in Abort (no new helper, D-17), read once by Transfer/RunProtocol inside _run_in_flight, passed as a parameter into a still-pure _message_for; crash-recovery Resume passes no flag to avoid blaming the operator on a stale flag
- [Phase 02-wait-through-pauses-on-the-pinned-core]: D-13: 20 live-paused polls (1.0 clock step) against a 6.0 timeout, with a no-op sleep and a fresh fake clock per _transfer/_run_protocol call, proves LIVE-03 on the real core: paused time excluded from the timeout at poll granularity, for both Transfer's Config-sourced timeout and RunProtocol's per-command timeout_s
- [Phase 03]: D-01.1 amended (prior session, 3b6a8d1) to require galago-core Phase 2 code-complete with only deploy-dependent 02-UAT items open, breaking a circular dependency with 02-UAT
- [Phase 03]: Task 3 precondition interpreted against its safety intent: F.A.S.T. READY after user restoration, Pf400 SIMULATED accepted as this environment's pre-existing established baseline (unrelated to this deploy), confirmed with no Galago run RUNNING before Step 1
- [Phase 03]: Recorded the Task 2 user go-ahead (D-03) directly in 03-DEPLOY.md's new Go-ahead section, keeping the full deploy audit trail in one runbook document
- [Phase 03]: User decision: 'No cache rebuild' after the cached docker compose up -d --build produced a byte-identical galago-web image ID; forced docker compose build --no-cache galago-web + up -d to genuinely satisfy the new-image-ID must-have
- [Phase 03]: rollback-pre-live04 left un-retagged per user instruction; caveat recorded in 03-DEPLOY.md that it shares content with the new deploy (same galago-core HEAD) and is not a true pre-milestone rollback anchor
- [Phase 03]: Dry run (D-07) harness lives under scripts/ (not tools/), is committed and kept (not deleted) so the dry run can be repeated after a future fix
- [Phase 03]: Two unexplained operator-initiated commands at 09:11 (extra pause + abort) recorded honestly as a note in 03-ACCEPTANCE.md rather than attributed to any scripted step
- [Phase 03]: Dry run (D-07) Result: PASS recorded only after independently re-deriving the command sequence from the harness log and the production F.A.S.T.log window, not solely from the operator's summary
- [Phase 03]: LIVE-06a recorded PASS despite operator running protocol "test" (num_rows 1, two simulated Pf400 moves) instead of the planned single-transfer protocol (num_rows 8) — D-11's pass criteria held regardless; deviation flagged in 03-ACCEPTANCE.md for user review
- [Phase 03]: Did NOT mark LIVE-06 complete in REQUIREMENTS.md after LIVE-06a — it is only half of LIVE-06; LIVE-06b (Pause -> Abort, plan 03-06) must also PASS first
- [Phase 03]: LIVE-05 scored PASS on rerun after D-14 none-plate fix (galago-core ad87ea5) and galago-web redeploy (b0e183e); first attempt (FAIL, found -1) kept as history in the same 03-ACCEPTANCE.md section
- [Phase 03]: Recorded two honest caveats on the LIVE-05 rerun rather than treating it as fully re-verified: no live fast_status.py pause snapshot was taken, and deck-3-empty at start was only indirectly confirmed by the operator
- [Phase 03]: LIVE-06b scored PASS on the third attempt after fixing a NoError(0)-suffix abort-wording bug found live on real hardware (7d77e23, 201d987); two non-scored attempts kept as history in the same 03-ACCEPTANCE.md section
- [Phase 03]: Corrected the plan-06 commit ledger base from 201d987 to cc721c7 so actuals.commits honestly includes the D-14 fix commits made earlier in this plan's execution
- [Phase 03]: Did not mark LIVE-07 complete; only LIVE-06 (both halves now PASS) was marked complete in REQUIREMENTS.md
- [Phase 03]: LIVE-07 scored PASS on rerun after galago-core queue-fix redeploy (261015-h0q); attempt 1 (FAIL, queue re-run defect) kept as history in 03-ACCEPTANCE.md
- [Phase 03]: LIVE-06b follow-up check PASS confirms the galago-core fix dequeues an aborted step; FINDING (a) and FINDING (b) (two residual galago-core queue defects) routed to plan 03-08's phase close-out decision, not treated as LIVE-06b/LIVE-07 failures
- [Phase 03]: Did not touch Safety invariant audit or phase-wide Summary closeout lines in 03-ACCEPTANCE.md -- that is plan 03-08's scope
- [Phase 03]: LIVE-07's twelve-bullet record needed no changes; Task 1 verified completeness against plan 03-08's own regexes rather than rewriting it
- [Phase 03]: Compared code-unchanged-since-deploy against the LAST deployed SHA (201d987, the D-14 LIVE-06b adapter fix), not the original LIVE-04 deploy SHA (d9acdcf0)
- [Phase 03]: FINDING (a) and FINDING (b) (galago-core queue defects flagged by plans 03-06/03-07) marked RESOLVED after live-verifying galago-core 261015-o44 (662bb12, 38b5d17, 7627bf6) read-only against the F.A.S.T.log and a copy of queue.db
- [Phase 03]: Named two Safety invariant audit gaps precisely (2026-10-14 ~17:47->10:16:36 WIB; 2026-10-15 ~11:47->12:02:49 WIB) rather than overstate log coverage; all 20 surviving control-command lines mapped to a recorded operator action, 0 unmapped
- [Phase 03 - Transition]: Milestone v1 complete — all 17 requirements (ADP-01..10, LIVE-01..07) moved to PROJECT.md's Validated section; "Active" requirements now empty.
- [Phase 03 - Transition]: Logged the deploy-order, D-14 FAIL->fix->rerun defect cycle, and the `galago-tools` manager (`:8081`)-restart-overwrites-F.A.S.T.log caveat as new rows in PROJECT.md's Key Decisions table for future milestones/repos to reference.
- [Phase 03 - Transition]: Open code-review disposition (WR-01, WR-02, 3 info items) and galago-core's queue/UI observations (Gantt bar past abort, "Connect all tools" empty configs, "Item N not found", tool-page staleness) carried forward as open debt in PROJECT.md's Context — not milestone-blocking.
- [Phase 02]: CR-01 fixed: Resume's crash-recovery acceptance check routed through _accepted(); separate Refused check dropped per review's suggested fix
- [Phase 02]: WR-02 (_is_no_error loose comparison) intentionally excluded from this gap-closure plan; remains tracked open in Phase 3's review disposition

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 2]: fast-mcp `fix/run-recovery-gate` (holding `76f8c3f` and `b30b38d`) is not on GitLab;
  a clean install from the pin fails until it is pushed. Install from the local clone meanwhile.
- [Phase 3]: Code review disposition left `open`: WR-01 (dry-run harness phantom-paused race,
  dev-only, harness already torn down) and WR-02 (`_is_no_error`'s `==` vs. the module's
  `type(code) is int` convention) plus 3 info items — not milestone-blocking, tracked in
  `.planning/phases/03-deploy-supervised-live-acceptance/03-REVIEW-DISPOSITION.md`.
- [Phase 3]: galago-core debt out of this repo's scope: run-page Gantt bar draws past an abort;
  "Connect all tools" sends empty configs; "Item N not found" when the queue clears mid-abort;
  F.A.S.T. tool-page status can render stale after a reconnect.
- [Phase 3]: Branches on both repos are not pushed (deferred D-02) — pushing is the user's own
  action; push only to the `nikkopg` fork remote.

## Deferred Items

Items acknowledged and deferred at milestone close, most recent first:

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-10-15T14:11:38.439Z
Stopped at: Phase 02 complete — all phases complete
`/gsd-complete-milestone`
Resume file: None
