---
gsd_state_version: "1.0"
milestone: v1
milestone_name: F.A.S.T. Live Run Control (adapter & rollout)
current_phase: 02
current_phase_name: Wait Through Pauses on the Pinned Core
status: executing
stopped_at: Completed 02-02-PLAN.md
last_updated: "2026-10-13T07:58:54.591Z"
last_activity: 2026-10-13
last_activity_desc: Phase 02 execution started
state_head: f7d62f8ce9c901cdedf9b82db786f273e44f3fe0
progress:
  total_phases: 3
  completed_phases: 1
  total_plans: 9
  completed_plans: 7
  percent: 33
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-12)

**Core value:** An operator running a F.A.S.T. step from Galago can always see what the instrument
is doing and recover it themselves; no adapter code path pauses, resumes or aborts on its own.
**Current focus:** Phase 02 — Wait Through Pauses on the Pinned Core

## Current Position

Phase: 02 (Wait Through Pauses on the Pinned Core) — EXECUTING
Plan: 3 of 4
Status: Ready to execute
Last activity: 2026-10-13 — Phase 02 execution started

Progress: [███░░░░░░░] 33%

## Performance Metrics

**Velocity:**
- Total plans completed: 5
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 5 | - | - |

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

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 1]: The `FastServer.ExecuteCommand` override is a research recommendation, not yet built
  (MEDIUM confidence) — write the failing real-mode concurrency test first.
- [Phase 2]: fast-mcp `fix/run-recovery-gate` (holding `76f8c3f` and `b30b38d`) is not on GitLab;
  a clean install from the pin fails until it is pushed. Install from the local clone meanwhile.
- [Phase 3]: Depends on galago-core's companion milestone; the proto change from Phase 1 must
  reach galago-core through its `vendor/galago-tools` submodule, regenerated with ts-proto 1.151.1.

## Deferred Items

Items acknowledged and deferred at milestone close, most recent first:

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-10-13T07:58:54.555Z
Stopped at: Completed 02-02-PLAN.md
Resume file: None
