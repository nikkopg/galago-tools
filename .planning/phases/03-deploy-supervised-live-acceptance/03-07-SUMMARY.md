---
phase: 03-deploy-supervised-live-acceptance
plan: 07
subsystem: testing
tags: [fast-tool, grpc, live-acceptance, galago-web, galago-core, run-recovery, queue-defect, d-12, d-14]

# Dependency graph
requires:
  - phase: 03-06
    provides: LIVE-06 complete (both halves PASS) in 03-ACCEPTANCE.md and REQUIREMENTS.md, unblocking D-09 scenario 4 (LIVE-07)
provides:
  - "LIVE-07 evidence in 03-ACCEPTANCE.md: Result PASS on the scored rerun (galago-web restart mid-run, docker restart at 14:23:40 WIB, tool-page Resume, the original Transfer's own wait ending and the motion lock clearing for LIVE-07's own step this time) with attempt 1 (FAIL, D-14, queue re-run defect) kept as history in the same section"
  - "LIVE-06b follow-up check PASS in 03-ACCEPTANCE.md, confirming the galago-core queue fix dequeues an aborted step so it cannot re-run"
  - "D-14 redeploy (queue re-run fix) subsection in 03-DEPLOY.md: galago-core quick task 261015-h0q (4b575ed/5598347/e18a177/a0afd61), galago-web image 94bdfa7e built 14:05:18 WIB, bundle check, galago-tools untouched (MainPID 836290, listener 867162), rollback caveat"
  - "FINDING (a) and FINDING (b) — two residual galago-core queue defects (an aborted run's later steps stay queued; a galago-web-restart-orphaned STARTED row survives recovery) recorded in 03-ACCEPTANCE.md's Flagged assumptions as blocking items for plan 03-08's phase close-out decision, each with its operator workaround"
  - "REQUIREMENTS.md LIVE-07 marked complete"
affects: [03-08]

actuals:
  tokens: 10642
  tasks: 3
  commits: 2
plan_head_before: 98eaff0c1c448df5cd8140d02b47c567241c6e3e
plan_head_after: 7250bf473e361a252558c29f4288d5c13f797b0f

tech-stack:
  added: []
  patterns:
    - "Non-scored-attempt-as-history pattern, extended across a cross-repo D-14 fix-then-rerun cycle: LIVE-07's scored rerun stays in the plan's eleven top-level D-13 bullets plus the Restart (D-12) bullet (twelve total), attempt 1's full record (including its own Restart (D-12) checks, which themselves passed) is preserved as indented sub-bullets under each top-level bullet, and the automated verify regexes (exactly one 'Restart (D-12):' line, exactly one Result line, twelve labels) stay satisfied against the merged record."
    - "Findings surfaced during a scenario rerun but not scored against that scenario's own criteria (because they never materialized as unintended motion in that run's window) are recorded as a named FINDING with an explicit operator workaround and routed to the next plan's close-out decision, rather than either silently dropped or incorrectly failing a scenario whose own D-11/D-12 criteria held."

key-files:
  created: []
  modified:
    - .planning/phases/03-deploy-supervised-live-acceptance/03-ACCEPTANCE.md
    - .planning/phases/03-deploy-supervised-live-acceptance/03-DEPLOY.md
    - .planning/REQUIREMENTS.md
    - .planning/STATE.md
    - .planning/ROADMAP.md

key-decisions:
  - "Scored LIVE-07 PASS on the rerun after the galago-core queue-fix redeploy (quick task 261015-h0q), keeping attempt 1 (FAIL, the queue re-ran a previously operator-aborted LIVE-06b step) as indented history under each of the twelve D-13/D-12 bullets rather than discarding it or giving it separate top-level entries, so the plan's automated verify checks (exactly one Restart (D-12) line, exactly one Result line, twelve labels) still pass against the merged record."
  - "Recorded the LIVE-06b follow-up check (after an abort, starting a new run must not re-run the aborted step) as a new paragraph nested under LIVE-06b's existing Result: PASS bullet, not as a second top-level Result line, preserving the section's single-Result-line structure while adding the confirming evidence the attempt-1 note called for."
  - "Treated FINDING (a) (an aborted run's remaining queued steps are not dequeued, only the aborted step itself is) and FINDING (b) (a galago-web-restart-orphaned STARTED row survives tool-page recovery and would re-run on the next queue start) as NOT LIVE-06b or LIVE-07 failures, since neither scenario's own scored D-11/D-12 criteria were violated by them — both findings were observed in queue-table snapshots but never actually exercised as unintended motion, because an operator Clear All intervened first in both cases. Flagged them instead as blocking items for plan 03-08's phase close-out decision, each with an explicit operator workaround (Clear All after any abort or any galago-web restart recovery, before starting another run)."
  - "Independently re-verified every restart-mechanics claim read-only before writing the record, rather than relying solely on the evidence files handed off from the prior session: docker inspect galago-web's State.StartedAt (2026-10-15T07:23:41.137995454Z) cross-confirms the 14:23:40 WIB restart time; systemctl MainPID (836290), the F.A.S.T. listener PID (867162, confirmed via ps as a child of 836290), and a fresh journalctl query over the rerun window (no entries) cross-confirm no tool-service or tool-server restart occurred; a live fast_status.py poll confirms the tool is now READY/idle."
  - "Corrected the plan commit ledger's plan_head_before from the continuation session's actual HEAD (2eec866, attempt 1's own FAIL commit) to the true pre-plan base (98eaff0, 03-06's plan-metadata commit), so the measured commits: 2 actual honestly includes attempt 1's FAIL commit made in the prior session, not just this session's rerun-PASS commit — the same correction pattern applied in 03-06's SUMMARY."
  - "Marked only LIVE-07 complete in REQUIREMENTS.md; this plan does not touch the Safety invariant audit or the phase-wide closeout lines in 03-ACCEPTANCE.md's Summary section — those are plan 03-08's scope."

requirements-completed: [LIVE-07]

coverage:
  - id: D1
    description: "Scored rerun of the galago-web-restart-mid-run scenario after the galago-core queue-fix redeploy: the operator starts and pauses a Transfer, Claude restarts galago-web on go-restart, the orphaned Transfer survives the restart and still holds the motion lock, the operator recovers from the F.A.S.T tool page's Run Recovery card, the instrument finishes LIVE-07's own transfer (not a substituted step, unlike attempt 1), and a following get_status runs SUCCESS; attempt 1 (FAIL, queue re-run defect) is kept as history under each bullet"
    requirement: "LIVE-07"
    verification:
      - kind: manual_procedural
        ref: "03-ACCEPTANCE.md ## LIVE-07 section: scored-rerun F.A.S.T.log excerpt (Transfer/Pause/Resume/GetStatus spanning the restart), docker inspect galago-web State.StartedAt cross-check, queue.db snapshot confirming queueId 124 ran with LIVE-07's own parameters, operator's direct replies, D-11 criteria sub-bullets, Result: PASS"
        status: pass
    human_judgment: false
  - id: D2
    description: "LIVE-06b follow-up check confirming the galago-core queue fix: after an operator abort, the aborted step is dequeued and does not re-run on the next queue start"
    verification:
      - kind: manual_procedural
        ref: "03-ACCEPTANCE.md ## LIVE-06b follow-up-check paragraph: queue.db snapshot showing the aborted transfer row (120) dequeued, only the get_status row (121) remaining"
        status: pass
    human_judgment: false
  - id: D3
    description: "FINDING (a) and FINDING (b) — two residual galago-core queue defects recorded as blocking items for the phase close-out decision, each with an operator workaround, not resolved or fixed in this plan"
    verification: []
    human_judgment: true
    rationale: "Whether these findings block the phase close-out, and what galago-core follow-up (if any) they require, is a judgment call reserved for plan 03-08's Safety invariant audit and the user's close-out decision — this plan only surfaces and routes them."

duration: ~40min (this continuation session; attempt 1 ran in a prior session)
completed: 2026-10-15
status: complete
---

# Phase 3 Plan 7: LIVE-07 Restart-Recovery Scenario Summary

**LIVE-07 (galago-web restart mid-run, tool-page recovery) scored PASS on rerun after a galago-core queue-fix redeploy fixed the defect that failed attempt 1.**

## Performance

- **Duration:** ~40 min (this continuation session, which recorded the rerun and closed out the plan; attempt 1's live scenario and its FAIL record were executed in a prior session, commit `2eec866`)
- **Tasks:** 3 of 3 (Task 1 operator checkpoint, Task 2 restart + record, Task 3 operator recovery checkpoint — all originally executed across the two sessions; this session's work was re-recording the merged evidence, not re-running the live scenario)
- **Files modified:** 2 content files (`03-ACCEPTANCE.md`, `03-DEPLOY.md`) + 3 tracking files (`REQUIREMENTS.md`, `STATE.md`, `ROADMAP.md`)

## Accomplishments

- Rewrote `## LIVE-07` in `03-ACCEPTANCE.md` so the rerun (galago-web run `1541991a8101e7000`, queue row 124, Transfer A6→A6) is the scored Result: PASS, with attempt 1 (FAIL, D-14, queue re-run defect, commit `2eec866`) preserved as indented history under all twelve bullets (Date/time, Operator, Transfer parameters, Restart (D-12), Decisions chosen, Log excerpt, Final step result, Queue state, Control commands in window, Screenshots, D-11 criteria, Result).
- Recorded the LIVE-06b follow-up check as PASS under `## LIVE-06b`'s existing Result bullet: the galago-core fix dequeues an aborted step (row 120) so it cannot re-run, confirmed from a `docker cp` queue.db snapshot.
- Documented the D-14 redeploy in `03-DEPLOY.md`: galago-core quick task `261015-h0q` (commits `4b575ed`/`5598347`/`e18a177`/`a0afd61`), `galago-web` image `94bdfa7e...` built 14:05:18 WIB, bundle verification, and that `galago-tools` was untouched (MainPID `836290`, F.A.S.T. listener `867162` unchanged).
- Surfaced two new, residual galago-core queue defects (FINDING (a): an aborted run's remaining queued steps are not dequeued; FINDING (b): a galago-web-restart-orphaned STARTED row survives tool-page recovery) and routed both to plan 03-08's phase close-out decision as blocking items, each with an explicit operator workaround — neither counted against LIVE-06b's or LIVE-07's own Result, since both scenarios' scored criteria held.
- Independently re-verified the restart mechanics read-only before writing the record: `docker inspect galago-web` (`State.StartedAt 2026-10-15T07:23:41.137995454Z`), `systemctl --user show galago-tools -p MainPID` (`836290`), a live `ps` check of the F.A.S.T. listener (`867162`, child of `836290`), a fresh `journalctl` query over the rerun window (no entries), and a live `fast_status.py` poll (READY/idle).
- Marked LIVE-07 complete in `REQUIREMENTS.md`.

## Task Commits

This plan's live-scenario work spans two sessions. The prior session executed Tasks 1-3 against attempt 1 and committed the FAIL record:

1. **Tasks 1-3 (attempt 1, prior session)** - `2eec866` (docs) — LIVE-07 attempt 1 recorded FAIL (queue re-run defect found live)

This continuation session re-ran the live scenario (operator-driven, outside this record's own task boundaries, following the galago-core fix and redeploy) and recorded the merged result:

2. **Record LIVE-07 rerun PASS, LIVE-06b follow-up PASS, D-14 redeploy, findings (a)/(b)** - `7250bf4` (docs)

**Plan metadata:** (this commit, following this SUMMARY)

## Files Created/Modified

- `.planning/phases/03-deploy-supervised-live-acceptance/03-ACCEPTANCE.md` - `## LIVE-07` rewritten with the scored rerun as Result: PASS (attempt 1 kept as history); `## LIVE-06b`'s Result bullet extended with the follow-up-check PASS paragraph and FINDING (a); `## Flagged assumptions` updated to mark the queue re-run defect fixed and add FINDING (a)/(b) as blocking items for 03-08; Summary table's LIVE-07 row updated to PASS
- `.planning/phases/03-deploy-supervised-live-acceptance/03-DEPLOY.md` - new "D-14 redeploy (queue re-run fix)" subsection
- `.planning/REQUIREMENTS.md` - LIVE-07 checkbox and traceability row marked complete
- `.planning/STATE.md` - position, decision, session fields updated
- `.planning/ROADMAP.md` - phase 3 plan-progress row updated for plan 03-07

## Decisions Made

See `key-decisions` in the frontmatter above for the full rationale on each. In brief: scored the rerun PASS with attempt 1 kept as nested history (not discarded, not a separate top-level entry); nested the LIVE-06b follow-up check under the existing Result bullet rather than adding a second Result line; treated findings (a) and (b) as blocking items for 03-08's close-out rather than LIVE-06b/LIVE-07 failures, since neither scenario's own scored criteria were violated; independently re-verified every restart-mechanics claim read-only; corrected the plan commit ledger's base to the true pre-plan commit so `commits: 2` honestly includes attempt 1's FAIL commit.

## Deviations from Plan

### Auto-fixed Issues

None — this plan is itself a continuation that incorporates the artifacts of a D-14 cross-repo fix cycle (galago-core fix, redeploy, operator rerun) that the plan's own structure anticipated (A-EDGE-LIVE-07, the "D-14 route" note in `03-DEPLOY.md`). No code in this repo changed during this session; only evidence-record files were edited.

**Noted for the record, not an auto-fix:**
1. **[D-14 cross-repo fix]** LIVE-07 attempt 1 FAILed because of a galago-core queue defect (`SqliteQueue.ts` `fail()`/`startNext()`). galago-core fixed it (quick task `261015-h0q`), `galago-web` was rebuilt, and the operator reran both the LIVE-06b follow-up check and LIVE-07 — both now PASS. This repo (`fast-mcp`/`galago-tools`) was never implicated and was not redeployed for this fix.
2. **[Pre-existing, re-noted]** The 12:04:42 WIB tool-server restart (F.A.S.T. listener PID `836333` → `867162`, no `galago-tools` service restart) predates LIVE-07 attempt 1 and was already recorded as a baseline note under attempt 1; carried forward unchanged as the still-current baseline for the rerun.
3. **[New findings, routed not fixed]** FINDING (a) — an aborted run's remaining queued steps stay in `_queue` and are not dequeued by the fix (only the aborted step itself is). FINDING (b) — a `galago-web`-restart-orphaned queue row stays `STARTED` after tool-page recovery and would re-run on the next queue start. Both are galago-core defects of the same class as the one just fixed; both are documented with their root cause and an operator workaround (Clear All before starting another run), and both are flagged in `## Flagged assumptions` as blocking items for plan 03-08's phase close-out decision. Neither was fixed in this repo or in galago-core during this plan — fixing them is explicitly out of this plan's scope and left for the close-out decision.

---

**Total deviations:** 0 auto-fixed; 3 noted-for-the-record items (one cross-repo D-14 fix cycle, one pre-existing restart baseline carried forward, two new findings routed to 03-08).
**Impact on plan:** No scope creep — all noted items are either already-anticipated D-14 cycle artifacts or explicitly routed to the next plan rather than fixed here.

## Issues Encountered

None beyond the findings documented above. The operator's reported Resume time for the rerun ("14.23") differs by about 43 seconds from the F.A.S.T.log's actual `Running command Resume` line (14:24:06 WIB); flagged plainly in the record as a minor timing discrepancy, consistent with how attempt 1's 2%-vs-5% paused discrepancy was handled, and does not affect the Result.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- LIVE-04, LIVE-05, LIVE-06 and LIVE-07 are all now PASS in `03-ACCEPTANCE.md`; `REQUIREMENTS.md` has LIVE-07 marked complete.
- Plan 03-08 can now run its Safety invariant audit (design section 7 invariant 1) over the full post-deploy `F.A.S.T.log`, confirm no code changed since the deploy (or that every change is an evidenced D-14 fix — this plan's `03-DEPLOY.md` entries qualify), run the post-acceptance gate, and check D-13 completeness.
- **Blocking items carried into 03-08's close-out decision:** FINDING (a) and FINDING (b) (both galago-core queue defects, documented in `03-ACCEPTANCE.md`'s `## Flagged assumptions` with root cause and operator workaround) are not failures of any scored scenario but are explicitly flagged as needing a close-out decision — whether the phase can close with these as known, workaround-mitigated debt, or whether a further galago-core fix is required first, is for 03-08 and the user to decide.

---
*Phase: 03-deploy-supervised-live-acceptance*
*Completed: 2026-10-15*
