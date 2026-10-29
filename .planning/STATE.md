---
gsd_state_version: "1.0"
milestone: v2
milestone_name: STACK Tool & STACK↔F.A.S.T. Handoff
current_phase: 5
current_phase_name: F5-safe Transfer & Operator Acknowledge
status: executing
stopped_at: Completed 05-02-PLAN.md
last_updated: "2026-10-29T08:50:03.426Z"
last_activity: 2026-10-29
last_activity_desc: Phase 5 execution started
state_head: a2d653f5072107ea2f7aaa7693ed41e18a2ddc42
progress:
  total_phases: 4
  completed_phases: 1
  total_plans: 12
  completed_plans: 7
  percent: 25
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-10-28)

**Core value:** An operator running an instrument step from Galago can always see what the instrument
is doing and recover it themselves; no adapter code path pauses, resumes, aborts, cancels, retries or
acknowledges on its own. For the STACK: a step never sends a second transfer.
**Current focus:** Phase 5 — F5-safe Transfer & Operator Acknowledge

## Current Position

Phase: 5 (F5-safe Transfer & Operator Acknowledge) — EXECUTING
Plan: 3 of 7
Status: Ready to execute
Last activity: 2026-10-29 — Phase 5 execution started

Progress: [███░░░░░░░] 25%

## Performance Metrics

**Velocity:**
- Total plans completed: 23 (v1, archived); v2: 0 of TBD
- Average duration: -
- Total execution time: 0 hours

**By Phase (v1, archived in `.planning/milestones/v1-phases/`):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 5 | - | - |
| 02 | 5 | - | - |
| 03 | 8 | - | - |
| 4 | 5 | - | - |

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
| Phase 04 P01 | 2 min | 3 tasks | 8 files |
| Phase 04 P02 | 8 min | 3 tasks | 2 files |
| Phase 04 P03 | 15 min | 3 tasks | 2 files |
| Phase 04 P04 | 20 min | 3 tasks | 2 files |
| Phase 4 P05 | 15 min | 2 tasks | 2 files |
| Phase 05 P01 | 6 min | 2 tasks | 1 files |
| Phase 5 P02 | 25min | 3 tasks | 3 files |

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
- [Phase 04]: stack.proto v2 frozen exactly as D-01..D-05 (user: Freeze); Command 24, Config 43, ToolType 24
- [Phase 04]: StackServer._configure is the thinnest D-07 path (open_service owner galago); Plan 02 adds validation and close-first lifecycle
- [Phase 04]: Same-endpoint Configure reuse keyed on core endpoint_key vs OwnedService.endpoint; close-first on endpoint change so a failed open leaves no lock or service
- [Phase 04]: transfer_timeout_s and ledger_dir are record-only in Configure; ledger path untouched until Phase 5
- [Phase 04]: 04-03: blank/whitespace instrument fields reach the core as None; the adapter applies no instrument rule
- [Phase 04]: 04-03: operator error line = kind, reason, guid, then one bounded structured hint; core explanation/detail text never read
- [Phase 04]: 04-04: Phase 5 commands (Transfer, AcknowledgeFailure, GetFailureLatch) are refused in real mode before the not-configured check; arm_inspected matched byte-for-byte against yes/no
- [Phase 4]: 04-05: READ_COMMANDS (eight reads incl. get_transfer_estimate, get_failure_latch) bypass BUSY via StackServer.ExecuteCommand; reads never call isReady/parseCommand/setStatus; transfer/acknowledge_failure never in set
- [Phase 05]: 05-01 A-1: ledger done set mirrors core _task_ended (ran, failed, aborted, lost(taskNotFound)); timedOut and lost(pollFailed) stay started — Recording lost(pollFailed) as done would leave the core persisted in-flight guard set forever (acknowledge does not clear it), so every later Transfer would be Refused(inFlight)
- [Phase 05]: 05-01 A-2: the guid to acknowledge comes from latch_status() first; the result guid is labelled task guid only — Latch is first-failure-wins and acknowledge_failure answers guidMismatch for any other guid
- [Phase 05]: 05-01 OQ1/OQ2: keep D-09 (live ran after restart is SUCCESS flagged reattachedAfterRestart); release after Rejected(instrument)/Refused(stackBusy) per XFR-04 as documented residual risk; orphaned core in-flight guard goes to the Phase 7 runbook — Orchestrator resolutions in --auto mode; adapter holds no instrument policy
- [Phase 5]: 05-02: an existing step key sends nothing (interim ERROR_FROM_TOOL, replaced by decide() in 05-06); non-TaskHandle execute results keep the record submitting (interim, 05-05 adds the release whitelist)
- [Phase 5]: 05-02: XFR-05 call-site AST rules replace the blanket no-motion rule: single sites for execute_transfer/plan_transfer in _run_fresh, no loop ancestor, after claim, no getattr/alias, acknowledge_failure confined to AcknowledgeFailure

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
- DEP-01 is met (2026-10-29): core `934a621` closes G1-G3, contract still v1; pinned in the fork
  (`237268c`), D-09 restart warning corrected (`fe8aee8`). Phase 5 can start; its design spike must
  cover a re-attach after a mid-transfer restart (core limit 1). Phase 6 and Phase 7 are gated on DEP-02 (galago-core codegen +
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

Last session: 2026-10-29T08:50:03.390Z
Stopped at: Completed 05-02-PLAN.md
Resume file: None

## Operator Next Steps

- Plan Phase 4 with /gsd-plan-phase 4 (or /gsd-discuss-phase 4 first); Phase 4 has no cross-repo gate
- DEP-01 done (core `934a621` pinned); next: /gsd-discuss-phase 5
- On forb01, run galago-tools and stack-mcp as the same OS user (or share `STACK_STATE_DIR`) so the
  persisted failure latch is shared across a hand-over (LIVE-08)
