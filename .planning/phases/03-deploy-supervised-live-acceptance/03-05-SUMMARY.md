---
phase: 03-deploy-supervised-live-acceptance
plan: 05
subsystem: testing
tags: [fast-tool, grpc, live-acceptance, galago-web, galago-core, pause-prompt, d-14]

# Dependency graph
requires:
  - phase: 03-04
    provides: LIVE-06a PASS in 03-ACCEPTANCE.md; F.A.S.T. READY/idle on the post-deploy MainPID, unblocking scenario 2
provides:
  - "LIVE-05 evidence in 03-ACCEPTANCE.md: Result PASS after the D-14 fix and redeploy, with the first attempt's FAIL kept as history in the same section"
  - "D-14 redeploy (LIVE-05 fix) subsection in 03-DEPLOY.md: galago-core ad87ea5 none-plate fix, galago-web b0e183e rebuild, bundle verification, no galago-tools restart"
  - "REQUIREMENTS.md LIVE-05 marked Complete"
affects: [03-06, 03-07, 03-08]

actuals:
  tokens: 5123
  tasks: 3
  commits: 2
plan_head_before: ea18f1604cb1d5dd31570980d77795a7298b67a5
plan_head_after: 0090a3cb6bd337f7fcb78ac11d1d3dab2bf1693c

tech-stack:
  added: []
  patterns:
    - "First-attempt-as-history pattern for a D-14 FAIL-then-fix-then-rerun record: the scored scenario's evidence stays in the eleven top-level D-13 bullets, the earlier FAIL attempt is preserved as indented sub-bullets under each bullet (not duplicate top-level bullets), keeping the plan's automated verify regexes (exactly 11 labels, exactly one Result line) satisfied while the audit trail is not lost"
    - "Honest caveat recording when live evidence is thinner on a rerun than on the first attempt (no fresh fast_status.py snapshot during the second pause, queue entries cleared) — state the gap plainly rather than imply the same depth of evidence, per A-EDGE-LIVE-05"

key-files:
  created: []
  modified:
    - .planning/phases/03-deploy-supervised-live-acceptance/03-ACCEPTANCE.md
    - .planning/phases/03-deploy-supervised-live-acceptance/03-DEPLOY.md
    - .planning/REQUIREMENTS.md
    - .planning/STATE.md
    - .planning/ROADMAP.md

key-decisions:
  - "Scored LIVE-05 PASS on the rerun's operator-reported evidence plus the deployed-bundle fix verification, explicitly noting two caveats rather than silently upgrading confidence to first-attempt levels: no fast_status.py snapshot was taken during the rerun's pause (the -645/eventPayload attribution rests on the operator's report plus consistency with the first attempt's directly-captured payload on identical parameters), and the operator did not explicitly state deck 3 was empty at the rerun's start beyond the instrument self-pausing on -645"
  - "Kept the first attempt (run 154132ef8081e7000, FAIL, commit eb8ca7f) as indented history sub-bullets under each of the eleven D-13 bullets, rather than a separate top-level entry, so the plan's automated verify checks (exactly 11 '^- Label:' bullets, exactly one '^- Result: (PASS|FAIL)$' line) still pass against the merged record"
  - "Recorded the superseded run 15413f0fc681e7000 (no Transfer sent) as excluded/superseded per the operator's own 'use the latest LIVE-05' instruction, without speculating on its cause"
  - "Marked only LIVE-05 complete in REQUIREMENTS.md; LIVE-06 and LIVE-07 remain Pending (LIVE-06b and LIVE-07 are later plans' scenarios)"

requirements-completed: [LIVE-05]

coverage:
  - id: D1
    description: "Rerun of the deck-3-empty scenario after galago-core's none-plate rendering fix (ad87ea5) and the galago-web rebuild (b0e183e): the instrument pauses itself with WrongPlateType (-645), the tool_paused prompt now reads 'Deck 3: expected plate 1, found none' (previously 'found -1'), nothing is preselected, and after the operator's deck fix and Resume (tip intact) the same step ends SUCCESS with one Transfer, one Resume, no retry and no second step"
    requirement: "LIVE-05"
    verification:
      - kind: manual_procedural
        ref: "03-ACCEPTANCE.md ## LIVE-05 section: rerun F.A.S.T.log excerpt (Transfer/pause/Resume/SUCCESS), operator's direct replies confirming the reason, the fixed detail line and nothing preselected, deployed-bundle grep confirming the isNoPlateDetected fix is live, D-11 criteria sub-bullets, Result: PASS"
        status: pass
    human_judgment: true
    rationale: "Supervised live hardware scenario: every motion step (start, deck fix, Resume) was the operator's own physical action at the instrument, and the rendered prompt text and the deck-3-empty starting condition can only be attested by the human present at the instrument, not purely by log inspection — compounded here by the rerun lacking a live fast_status.py payload snapshot, which the record states plainly rather than treating as independently machine-verified"

duration: ~25min (Task 3 only — read-only re-verification of the D-14 fix and the rerun evidence, section rewrite, record, commit; Tasks 1-2 were operator-paced live checkpoints across two sessions: the first attempt in this session's predecessor, the fix-and-rerun checkpoint replies in this session)
completed: 2026-10-15
status: complete
---

# Phase 3 Plan 5: LIVE-05 Deck-3 Scenario Summary

**Recorded LIVE-05 as PASS in 03-ACCEPTANCE.md after galago-core's D-14 none-plate rendering fix (`ad87ea5`) and a galago-web redeploy (`b0e183e`), rerunning the identical deck-3-empty scenario and keeping the first attempt's FAIL as history in the same section.**

## Performance

- **Duration:** ~25 min of active Claude work for this continuation (Tasks 1-2 were operator-driven live checkpoints at the instrument across two sessions; the first attempt and its FAIL record were completed in the predecessor session, commit `eb8ca7f`)
- **Started:** 2026-10-15 (continuation agent spawned after the D-14 fix and redeploy)
- **Completed:** 2026-10-15
- **Tasks:** 3 (Task 1 checkpoint:human-action, Task 2 checkpoint:human-action, Task 3 auto)
- **Files modified:** 2 in this continuation's commit (`03-ACCEPTANCE.md`, `03-DEPLOY.md`); `REQUIREMENTS.md`/`STATE.md`/`ROADMAP.md` updated in the plan-metadata commit

## Accomplishments
- Re-verified, read-only, the D-14 fix and redeploy before trusting the rerun: galago-core HEAD `ad87ea5` (quick task 261015-f48, commits `07fb7fa`/`e6b0e97`/`ad87ea5`) adds `isNoPlateDetected` mapping `null`/`undefined`/`""`/`-1`/`"-1"` to "none"; the deployed `galago-web` bundle (image `b0e183e...`, built 11:02:27 WIB) was grepped directly and confirmed to carry `-1===r||"-1"===r?"none"`; `galago-tools` MainPID (`4044033`) and the F.A.S.T. listener PID (`727894`) were confirmed unchanged, so no tool-server restart occurred during the redeploy.
- Rewrote the `## LIVE-05` section of `03-ACCEPTANCE.md` so the scored evidence is the rerun (run `15413f379a81e7000`, created 11:05:50 WIB): the prompt now reads "Deck 3: expected plate 1, found none" (operator-confirmed), the same step ended SUCCESS after the operator's deck fix and Resume (tip intact), and the control-command window matches the operator's actions exactly (Transfer=1, Pause=0, Resume=1, Abort=0). All eleven D-13 bullets and all five D-11 criteria sub-bullets are present; the section still contains exactly one `Result:` line (`PASS`).
- Preserved the first attempt (run `154132ef8081e7000`, FAIL, commit `eb8ca7f`) as clearly labelled "First attempt (FAIL, D-14)" history sub-bullets under each of the eleven top-level bullets, rather than discarding it or duplicating top-level labels — the automated verify regexes (11 labels, 1 Result line) still pass against the combined record.
- Recorded two honest caveats rather than inflating the rerun's evidentiary weight to match the first attempt's: no `fast_status.py` poll was taken while the rerun was paused (the -645/eventPayload attribution rests on the operator's direct report plus consistency with the first attempt's directly-captured payload on identical parameters), and the operator did not explicitly confirm deck 3 was empty at the rerun's start beyond the instrument self-pausing on -645.
- Recorded the superseded run `15413f0fc681e7000` (created 11:05:30 WIB, sent no Transfer) as excluded per the operator's own "use the latest LIVE-05" instruction.
- Added a "D-14 redeploy (LIVE-05 fix)" subsection to `03-DEPLOY.md` covering the galago-core fix, the galago-web rebuild and bundle check, the no-restart confirmation for `galago-tools`, the 11:05:44 WIB F.A.S.T. reconnect, and the rollback-anchor caveat (rolling back to `rollback-pre-live04` would undo this fix along with all of Phase 2's fixes).
- Updated the Summary table row for LIVE-05 to PASS.
- Marked requirement `LIVE-05` complete (checkbox + traceability row) in `.planning/REQUIREMENTS.md`; confirmed `LIVE-06` and `LIVE-07` remain Pending.

## Task Commits

Each task was committed atomically:

1. **Task 1: LIVE-05 part 1 (checkpoint:human-action)** - no commit (operator-performed physical/UI actions; Claude sent nothing); first attempt from the predecessor session
2. **Task 2: LIVE-05 part 2 (checkpoint:human-action)** - no commit (operator-performed physical/UI actions; Claude sent nothing); covers both the first attempt and, after the D-14 fix, the rerun's deck fix and Resume
3. **Task 3: Record LIVE-05 against D-11 (D-13)** - first scored FAIL in `eb8ca7f` (predecessor session); rescored PASS in `0090a3c` (this session) after the D-14 fix and rerun

**Plan metadata:** recorded separately via the final docs commit (SUMMARY.md, STATE.md, ROADMAP.md, REQUIREMENTS.md)

## Files Created/Modified
- `.planning/phases/03-deploy-supervised-live-acceptance/03-ACCEPTANCE.md` - `## LIVE-05` section rewritten: rerun scored PASS, first attempt kept as history; Summary table row updated
- `.planning/phases/03-deploy-supervised-live-acceptance/03-DEPLOY.md` - new "D-14 redeploy (LIVE-05 fix)" subsection
- `.planning/REQUIREMENTS.md` - LIVE-05 checkbox and traceability row marked Complete
- `.planning/STATE.md` - position, decisions, session updated
- `.planning/ROADMAP.md` - Phase 3 plan-progress row updated

## Decisions Made
- Scored PASS on the rerun's evidence even though it is thinner than the first attempt's (no live `fast_status.py` pause snapshot, no usable queue entry) — the orchestrator's synthesis across the operator's three verbatim replies, the verified-present code fix in the deployed bundle, and physical consistency with the first attempt's directly-captured payload on identical parameters was judged sufficient, with both gaps stated plainly in the record rather than hidden.
- Kept the first attempt as indented history under each bullet (not a separate top-level entry) so the plan's automated verify checks keep passing against the merged record.
- Did not attribute a cause to the superseded run `15413f0fc681e7000` sending no Transfer — recorded as observed and excluded, not speculated on.

## Deviations from Plan

None - plan executed exactly as written, across the D-14 detour: Task 3's FAIL branch (predecessor session) and the plan's prescribed re-record-on-fix path (this session) are both explicit paths the plan's own instructions and D-14 anticipate, not unplanned work.

## Issues Encountered
- None in this continuation. The predecessor session's FAIL record and this session's D-14 fix-and-rerun record were both anticipated by the plan's own D-14 instruction ("If FAIL: commit, then STOP with a blocking-human checkpoint... Root cause and fix route are in the plan 03-05 checkpoint").

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- LIVE-05 Result: PASS unblocks scenario 3 (LIVE-06b, plan 03-06) per D-09's least-to-most-disruptive ordering.
- `LIVE-06` and `LIVE-07` remain Pending in `REQUIREMENTS.md` — plan 03-06 (LIVE-06b: Pause -> Abort) and plan 03-07 (LIVE-07: galago-web restart mid-run) still need to PASS.
- `03-DEPLOY.md`'s rollback anchor (`rollback-pre-live04`) now also predates the D-14 none-plate fix; a rollback to it would undo this fix along with Phase 2's WR-01..WR-07 and UI-review fixes — noted in the new subsection for future reference.

## Self-Check: PASSED
- FOUND: .planning/phases/03-deploy-supervised-live-acceptance/03-ACCEPTANCE.md (`## LIVE-05` section, `Result: PASS`, "Deck 3" rendered line present)
- FOUND: .planning/phases/03-deploy-supervised-live-acceptance/03-DEPLOY.md (`### D-14 redeploy (LIVE-05 fix)` subsection present)
- FOUND commit 0090a3c (HEAD at SUMMARY time)
- FOUND commit eb8ca7f (ancestor, first-attempt FAIL record)

---
*Phase: 03-deploy-supervised-live-acceptance*
*Completed: 2026-10-15*
