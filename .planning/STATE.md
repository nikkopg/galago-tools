---
gsd_state_version: "1.0"
milestone: v2
milestone_name: STACK Tool & STACK↔F.A.S.T. Handoff
current_phase: 7
current_phase_name: Deploy & Supervised Live STACK + Handoff
status: executing
stopped_at: Phase 7 context gathered
last_updated: "2026-11-02T10:11:56.560Z"
last_activity: 2026-11-02
last_activity_desc: Phase 06 complete, transitioned to Phase 7
state_head: 72294d38f07ad2d62f62ed92f98c7b4f7d080dbc
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 20
  completed_plans: 16
  percent: 75
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-11-02)

**Core value:** An operator running an instrument step from Galago can always see what the instrument
is doing and recover it themselves; no adapter code path pauses, resumes, aborts, cancels, retries or
acknowledges on its own. For the STACK: a step never sends a second transfer.
**Current focus:** Phase 7 — Deploy & Supervised Live STACK + Handoff

## Current Position

Phase: 7 (Deploy & Supervised Live STACK + Handoff) — READY TO EXECUTE
Plan: Not started
Status: Ready to execute
Last activity: 2026-11-02 — Phase 06 complete, transitioned to Phase 7

Progress: [████████░░] 75%

## Performance Metrics

**Velocity:**
- Total plans completed: 34 (v1, archived); v2: 0 of TBD
- Average duration: -
- Total execution time: 0 hours

**By Phase (v1, archived in `.planning/milestones/v1-phases/`):**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 | 5 | - | - |
| 02 | 5 | - | - |
| 03 | 8 | - | - |
| 4 | 5 | - | - |
| 5 | 7 | - | - |
| 06 | 4 | - | - |

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
| Phase 5 P03 | 3 min | 3 tasks | 2 files |
| Phase 5 P04 | 14min | 3 tasks | 2 files |
| Phase 05 P05 | 25min | 2 tasks | 2 files |
| Phase 05 P06 | 40min | 3 tasks | 2 files |
| Phase 5 P07 | 25 min | 2 tasks | 2 files |
| Phase 06 P01 | 16 min | 3 tasks | 4 files |
| Phase 6 P02 | 20min | 2 tasks | 3 files |
| Phase 06 P03 | 20min | 3 tasks | 1 files |
| Phase 06 P04 | operator-delegated | 3 tasks | 1 files |

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
- [Phase 5]: 05-03: decide() treats an unknown record state as refuseOutcomeUnknown; replay only for done+ran with 0 <= age < 600 s
- [Phase 5]: 05-03: ledger retention prunes done records older than 7 days only inside a mutation that wrote; load never prunes
- [Phase 5]: GetFailureLatch is latch_status() 1:1; the yes gate sits in _dispatchCommand before admission and again in the AcknowledgeFailure handler
- [Phase 5]: Later ledger-write-failure message carries the latch clause for latching results only (ran makes no latch_status call)
- [Phase 05]: 05-05: mark_done skipped after a failed mark_started so the record stays submitting
- [Phase 05]: 05-05: step key released only by isinstance whitelist (Refused/Rejected/NeedsInput/ReadFailed); unknown shapes become outcomeUnknown
- [Phase 05]: 05-06: D-09 kept (user-confirmed): a ran re-attached after a restart is SUCCESS flagged reattachedAfterRestart; any non-ran outcome adds the arm-inspection clause plus the current latch clause
- [Phase 05]: 05-06: re-attach loop is read-only (wait_transfer only), first slice exactly min(budget,300), clock read only after a timedOut slice
- [Phase 5]: 05-07: never-resend proven behaviourally (12-scenario matrix, execute_transfer total 1 per key incl. restarts; released-outcome exception pinned at 2) with no adapter behaviour change; STK-05 re-proven on the real Transfer
- [Phase 06]: Phase 6 plan 01: GAL-02 parameter vocabulary locked at 27 names (fast_step_ prefix, deck fields); script has no fallback values and throws on blank required input — Names become operator saved-run inputs and Phase 7 runbook vocabulary; defaults live only in parameters[].defaultValue so sim names cannot reach hardware silently
- [Phase 06]: REPLAY_WINDOW_S is imported from tools.stack.ledger, not tools.stack.server — Constant is defined in ledger.py; adapter unchanged
- [Phase 6]: 06-02: DEP-02 gate is a read-only script with an exit code (testable on fixture trees); it printed DEP-02 OK on 2026-11-02 (galago-core a5fa75f), so Part 2 is unblocked at the gate
- [Phase 06]: Row 2a-3 credits the simulated re-dispatch per D-07 only; no-second-transfer is carried by the offline fake-core test and Part 2b
- [Phase 06]: 06-04: FLOW-04 no-second-POST is a plain PASS; manager submit counter calibrated (+1 on in leg) before the +0 re-send readings

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
  (`237268c`), D-09 restart warning corrected (`fe8aee8`). DEP-02 is met (2026-11-02, galago-core
  `a5fa75f`): Phase 6 ran unblocked. Phase 7 is DEP-02-met with DEP-03 recommended.
- ⚠ [Phase 6 UAT watch item] dev-galago tool-store state: after STACK-SIM was reconfigured in real
  mode, the GAL-02 out-leg (STACK-PACSIM) failed in galago-core with 'Tool STACK-PACSIM not found in
  store. Must be configured first.' — carries into the Phase 7 supervised checklist.
- v2 hard constraint: no STACK motion in default tests; live motion only in Phase 7, supervised and
  runbook-gated; never `10.150.1.125` / `stack-server` before Phase 7.

## Deferred Items

Items acknowledged and deferred at milestone close, most recent first:

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-11-02T09:15:29.964Z
Stopped at: Phase 7 context gathered
Resume file: .planning/phases/07-deploy-supervised-live-stack-handoff/07-CONTEXT.md

## Operator Next Steps

- Plan Phase 7 with /gsd-plan-phase 7 (or /gsd-discuss-phase 7 first); no CONTEXT.md exists yet
- Supervised live run gating: DEP-02 met; DEP-03 (PAC-simulator supervised preview) recommended before hardware
- Carry the Phase 6 tool-store watch item (STACK-PACSIM "not found in store" after STACK-SIM reconfigured) into the Phase 7 runbook/checklist
