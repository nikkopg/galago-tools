---
gsd_state_version: "1.0"
milestone: v2
milestone_name: STACK Tool & STACK↔F.A.S.T. Handoff
status: Awaiting next milestone
stopped_at: Phase 07 complete — all phases complete
last_updated: "2026-11-04T08:17:39.172Z"
last_activity: 2026-11-04
last_activity_desc: Milestone v2 completed and archived
state_head: 2004162c8c5eee80345a95bca14ddceb583e9466
progress:
  total_phases: 4
  completed_phases: 4
  total_plans: 20
  completed_plans: 20
  percent: 100
current_phase: 07
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-11-02)

**Core value:** An operator running an instrument step from Galago can always see what the instrument
is doing and recover it themselves; no adapter code path pauses, resumes, aborts, cancels, retries or
acknowledges on its own. For the STACK: a step never sends a second transfer.
**Current focus:** Planning next milestone (v2 archived 2026-11-04; candidates in PROJECT.md)

## Current Position

Phase: Milestone v2 complete
Plan: —
Status: Awaiting next milestone
Last activity: 2026-11-04 — Milestone v2 completed and archived

## Performance Metrics

**Velocity:**
- Total plans completed: 38 (v1, archived); v2: 0 of TBD
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
| 07 | 4 | - | - |

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
| Phase 07 P01 | 29 min | 3 tasks | 3 files |
| Phase 07 P02 | ~14h 21m elapsed (two sessions; active ~75min + supervised rebuild cycle) | 3 tasks | 3 files |
| Phase 07 P03 | split sessions (go-gate hand-off + live event + main-session recording) | 2 tasks | 4 files |
| Phase 07 P04 | ~3.5h two-plate live handoff (D-14 fix chain + one clean run) | 2 tasks | 2 files |

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
- [Phase 07]: [Phase 07]: 07-01 credential handling is presence-only (assignment-line count + 0600 mode), advisory warn: by default and blocking under GAL07_REQUIRE_STACK_ENV=1, which the runbook's Parts 2-3 set — D-05's detection signal is reused through the pinned core's own owner-lock helpers, not a re-implemented lock name
- [Phase 07]: gate tests use GAL07_REQUIRE_ALL as the REQUIRE_ALL_ENV variant; gal02_harness's shared constant is not mutated, so GAL02_REQUIRE_ALL promote semantics stay intact — a skip survives as a skip otherwise; GAL07_REQUIRE_ALL=1 in verification runs turns it into a failure
- [Phase 07]: [Phase 07]: 07-01 the live pre-flight gate reads the production API shapes (STACK store config nested at .config.stack, run list as a {count,data} envelope) so the real-host pre-deploy run BLOCKs on exactly the two known gaps: the service-venv core pin and the missing F.A.S.T. store entry — the plan's interfaces section assumed a flat config.host and a bare-array runs list; both were probed live against production :3010 during Task 2 verification
- [Phase 07]: 07-02 OQ-1: install source is a user-recorded local-clone-waiver of D-04 (git+https pin stalls in GitLab OAuth device flow); bundle installed from the verified local clone HEAD 934a621…, evidence in runbook row 1a-1/1a-2 — the only acceptable core build is the pinned 934a621…; the waiver is session-scoped and recorded verbatim so future installs do not silently fall back
- [Phase 07]: 07-02 deliver order held on real hardware: install → restart → reconnect → rebuild, proven by four strictly-increasing UTC timestamps in findings row 1a-6 (2026-11-02T11:20:00Z / 11:24:34Z / 12:18:28Z / 2026-11-03T01:31:16Z) — LIVE-08 safe-order guarantee: a newer UI must never run against an ungated core (D-03)
- [Phase 07]: 07-02: galago-web rollback anchor galago-core-galago-web:rollback-pre-gal07 = sha256:938217230697… (tagged before the rebuild); rebuilt image sha256:2f609032c0e3… — an image-ID rollback path with a real tag beats a summary note; Pitfall 3's cache-hit STOP was compared live and did not fire
- [Phase 07]: LIVE-09 delivered: one supervised live STACK Transfer on stack2-6 reached ran (GAL07-LIVE9-20261103T035107Z, SUCCESS, 27 s); owner-lock probe now accepts the galago single-owner state; no restart, one submission
- [Phase 07]: LIVE-10 delivered: the supervised two-plate live GAL-02 handoff ran STACK -> F.A.S.T. -> STACK to SUCCESS on hardware (4 STACK legs + the F.A.S.T. liquid deck 5->6 leg, 4 per-run minted keys all done); D-14 amendments recorded (protocol id 15 prefetch, plan shape note); no latch, no restart in the whole phase

### Pending Todos

None yet.

### Blockers/Concerns

- fast-mcp `fix/run-recovery-gate` (holding `76f8c3f` and `b30b38d`) is not on GitLab; a clean
  install from the pin fails until it is pushed. Install from the local clone meanwhile.
- WR-02 (`_is_no_error`'s loose `in (, 0)` check) — v2 debt, medium, reporting only.
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
- GAL-07 pre-flight owner-lock probe (gal-07-live-check.sh check 2, 07-01 artifact) blocks PREFLIGHT OK while the session's own galago tool server holds the STACK owner lock (expected single-owner state after real-mode Configure); fixes needed before plan 07-03 Part 2's entry gate — see .planning/phases/07-.../deferred-items.md (logged by 07-02 per the scope boundary)

## Deferred Items

Items acknowledged and deferred at milestone close, most recent first:

| Category | Item | Status | Deferred At | Milestone |
|----------|------|--------|-------------|-----------|
| *(none)* | | | | |

## Session Continuity

Last session: 2026-11-03T01:41:26.293Z
Stopped at: Phase 07 complete — all phases complete
Resume file: None

## Operator Next Steps


- Start the next milestone with /gsd-new-milestone
