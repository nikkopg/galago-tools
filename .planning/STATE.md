---
gsd_state_version: "1.0"
milestone: v2
milestone_name: STACK Tool & STACK↔F.A.S.T. Handoff
status: planning
last_updated: "2026-10-28T12:30:00.000Z"
last_activity: 2026-10-28
progress:
  total_phases: 4
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-28)

**Core value:** An operator running an instrument step from Galago can always see what the instrument
is doing and recover it themselves; no adapter code path pauses, resumes, aborts, cancels, retries or
acknowledges on its own. For the STACK: a step never sends a second transfer.
**Current focus:** Phase 4 — STACK Tool Registration, Reads & Estimate

## Current Position

Phase: 4 of 7 (STACK Tool Registration, Reads & Estimate) — v2 covers Phases 4-7
Plan: — (not yet planned)
Status: Ready to plan
Last activity: 2026-10-28 — v2 roadmap created (4 phases, 22/22 requirements mapped)

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**
- Total plans completed: 18 (v1, archived); v2: 0 of TBD
- Average duration: -
- Total execution time: 0 hours

**By Phase (v1, archived in `.planning/milestones/v1-phases/`):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 5 | - | - |
| 02 | 5 | - | - |
| 03 | 8 | - | - |

**Recent Trend:**
- Last 5 plans: none yet in v2
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

Full log in PROJECT.md Key Decisions; v1 per-plan decisions archived with the phases in
`.planning/milestones/v1-phases/`. Carried into the next milestone:

- Claude sends `Configure` only on the user's explicit request and only with no run in flight
  (logged exception T-03-05/T-03-08, 2026-10-16).
- Deploy order stays core → `galago-tools` → `galago-web`; back up `F.A.S.T.log` before any restart.

v2 roadmap-level decisions (2026-10-28, detail in PROJECT.md Key Decisions):

- Starting the Galago run is the approval for a STACK `Transfer` (plan → execute → wait in one
  command); `AcknowledgeFailure` is operator-only with a `"yes"` arm-inspected decision.
- F5 defence is a persisted `step_key` → guid ledger in the STACK adapter (re-attach, never re-submit).
- Three-way split: this repo = adapter + GAL-02 runbook protocol + live acceptance; galago-core = codegen,
  forms, operator Ack control, F3/F5; stack-automation-layer = G1-G3 via one `/gsd-quick` (DEP-01).
- v2 phase shape: 4 reads/estimate (no motion) → 5 F5-safe Transfer + Ack (gated on DEP-01) → 6 GAL-02
  workflow + simulated runs (gated on DEP-02) → 7 deploy + supervised live (DEP-03 recommended).

### Pending Todos

None yet.

### Blockers/Concerns

- fast-mcp `fix/run-recovery-gate` (holding `76f8c3f` and `b30b38d`) is not on GitLab; a clean
  install from the pin fails until it is pushed. Install from the local clone meanwhile.
- WR-02 (`_is_no_error`'s loose `in (None, 0)` check) — v2 debt, medium, reporting only.
- galago-core debt out of this repo's scope: run-page Gantt bar draws past an abort; "Connect all
  tools" sends empty configs; "Item N not found" when the queue clears mid-abort; F.A.S.T. tool-page
  status can render stale after a reconnect.
- Branches on both repos are not pushed (deferred D-02) — pushing is the user's own action; push
  only to the `nikkopg` fork remote.
- v2 Phase 5 is gated on DEP-01 (stack-automation-layer G1-G3 `/gsd-quick`); a G1/G2 decision is needed
  before planning it. Phase 6 and Phase 7 are gated on DEP-02 (galago-core codegen +
  `commandFields.stack`); DEP-02 consumes Phase 4's `stack.proto`, so keep that proto complete.
- v2 Phase 6: confirm Docker + the PAC simulator can run on the galago-tools host (loopback only).
- v2 hard constraint: no STACK motion in default tests; live motion only in Phase 7, supervised and
  runbook-gated; never `10.150.1.125` / `stack-server` before Phase 7.

## Deferred Items

Items acknowledged and deferred at milestone close, most recent first:

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-10-28
Stopped at: v2 roadmap created (Phases 4-7), REQUIREMENTS traceability filled; ready to plan Phase 4
Resume file: None

## Operator Next Steps

- Plan Phase 4 with /gsd-plan-phase 4 (or /gsd-discuss-phase 4 first); Phase 4 has no cross-repo gate
- Start DEP-01 (stack-automation-layer `/gsd-quick`) in parallel so Phase 5 is not blocked
