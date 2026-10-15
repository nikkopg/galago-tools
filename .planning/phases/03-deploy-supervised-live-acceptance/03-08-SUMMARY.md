---
phase: 03-deploy-supervised-live-acceptance
plan: 08
subsystem: infra
tags: [deploy, acceptance-evidence, galago-tools, galago-core, galago-web, F.A.S.T, safety-audit]

# Dependency graph
requires:
  - phase: 03-deploy-supervised-live-acceptance
    provides: LIVE-07 scored PASS (plan 03-07), LIVE-06b follow-up check PASS, D-14 queue-fix redeploy evidence
provides:
  - "LIVE-07 record confirmed complete (twelve bullets, unchanged from plan 03-07)"
  - "Safety invariant audit (design section 7 invariant 1, D-11): 20 control-command lines since the LIVE-04 deploy, all mapped to a recorded operator action, 0 unmapped; 3 explained tool-process restarts; 2 precisely-named gaps with no surviving log"
  - "Live verification of galago-core 261015-o44 (findings (a) and (b) resolved): an accepted abort now removes a run's remaining steps, and a startup-orphaned STARTED step is failed and dequeued, never re-dispatched"
  - "Code-unchanged-since-last-redeploy confirmation, post-acceptance gate (144 tests, ruff, mypy), dry-run harness self-test"
  - "03-ACCEPTANCE.md closed out: Summary six PASS rows plus four closeout lines; D-13 completeness confirmed for LIVE-04..07"
affects: [milestone-close, galago-core-queue-debt]

# Actuals (#2632)
actuals:
  tokens: 5919
  tasks: 2
  commits: 2
  plan_head_before: ee7547b2d437e1009d09725640b661064a04c312
  plan_head_after: 698961a6a749fc38b5f8221d941fa069446c2b90

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Control-command audit: compile every Running command Pause/Resume/Abort line from the live log plus every backup taken before an in-place overwrite, map each to a recorded operator action, and name any gap precisely rather than claim coverage the surviving files don't support"

key-files:
  created: []
  modified:
    - .planning/phases/03-deploy-supervised-live-acceptance/03-ACCEPTANCE.md

key-decisions:
  - "LIVE-07's twelve-bullet record (written by plan 03-07) needed no changes; Task 1 verified completeness rather than rewriting it"
  - "Compared code-unchanged-since-deploy against the LAST deployed SHA (201d987, the D-14 LIVE-06b adapter fix), not the original LIVE-04 deploy SHA (d9acdcf0) — git diff 201d987..HEAD over code paths is empty, while d9acdcf0..HEAD correctly lists the two evidenced D-14 fix commits"
  - "FINDING (a) and FINDING (b) (galago-core queue defects flagged by plans 03-06/03-07 as blocking items for this close-out) are marked RESOLVED in Flagged assumptions, backed by a new, independently re-verified '## 261015-o44 live verification' section with its own log excerpts and a read-only queue.db re-query"
  - "Named two gaps in the Safety invariant audit precisely (2026-10-14 ~17:47 -> 2026-10-15 10:16:36 WIB, and 2026-10-15 ~11:47 -> 12:02:49 WIB) rather than overstate coverage; both rest on records written at the time in other documents (the dry run's own zero-command check, galago-core's 02-UAT.md), not a fresh audit of files that no longer exist"

requirements-completed: [LIVE-04, LIVE-05, LIVE-06, LIVE-07]

coverage:
  - id: D1
    description: "LIVE-07 record verified complete (twelve bullets: Date/time, Operator, Transfer parameters, Restart (D-12), Decisions chosen, Log excerpt, Final step result, Queue state, Control commands in window, Screenshots, D-11 criteria, Result)"
    requirement: "LIVE-07"
    verification:
      - kind: other
        ref: "awk/grep bullet-count check over ## LIVE-07 in 03-ACCEPTANCE.md (plan 03-08 Task 1 <verify>)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Safety invariant audit (design section 7 invariant 1, D-11): every Pause/Resume/Abort line since the LIVE-04 deploy restart mapped to an operator action, 0 unmapped, restarts explained"
    verification:
      - kind: other
        ref: "awk/grep bullet-count and exact Result-line check over ## Safety invariant audit in 03-ACCEPTANCE.md (plan 03-08 Task 1 <verify>)"
        status: pass
    human_judgment: false
  - id: D3
    description: "261015-o44 live verification: an accepted abort removes a run's remaining steps (check a, run 15420f33a301e7000); a galago-web-restart-orphaned STARTED step is failed and dequeued, never re-dispatched (check b, run 154210ef5381e7000)"
    verification:
      - kind: manual_procedural
        ref: "F.A.S.T.log excerpts (fast-log-20261015-o44-checks.log) plus a read-only docker cp copy of /app/data/queue.db, re-queried independently for this record"
        status: pass
    human_judgment: true
    rationale: "Live hardware run with an operator at the instrument; the pass/fail call rests on the operator's real-time actions and replies, not a reproducible automated test."
  - id: D4
    description: "Code unchanged since the last actual redeploy (201d987); post-acceptance gate (bin/make test: 144 tests, ruff, mypy) green; dry-run harness self-test OK; D-13 completeness (six Summary PASS rows, all scenario-section fields present) confirmed"
    requirement: "LIVE-04"
    verification:
      - kind: other
        ref: "git diff --stat 201d987 HEAD -- tools/ interfaces/ setup.py requirements.txt (plan 03-08 Task 2 action 1)"
        status: pass
      - kind: unit
        ref: "bin/make test (plan 03-08 Task 2 <verify>, 144 passed)"
        status: pass
      - kind: other
        ref: "scripts/fast_dryrun.py --self-test (plan 03-08 Task 2 <verify>, SELF-TEST OK)"
        status: pass
    human_judgment: false

duration: ~25min
completed: 2026-10-15
status: complete
---

# Phase 3 Plan 8: Close Phase 3 from Evidence Summary

**Safety invariant audit (20 control-command lines since the LIVE-04 deploy, all mapped, 0 unmapped, 3 explained restarts, 2 precisely-named log gaps) plus live verification of galago-core 261015-o44 resolving FINDING (a) and FINDING (b); code unchanged since the last redeploy, gate green (144 tests), D-13 complete for LIVE-04..07**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-10-15 (session start, after plan 03-07)
- **Completed:** 2026-10-15T11:57:31Z
- **Tasks:** 2
- **Files modified:** 1 (`.planning/phases/03-deploy-supervised-live-acceptance/03-ACCEPTANCE.md`)

## Accomplishments

- Confirmed plan 03-07's LIVE-07 record (twelve bullets, Result: PASS) is complete against this
  plan's own regex checks — no rewrite needed.
- Added `## 261015-o44 live verification`: independently re-verified, read-only, galago-core
  quick task `261015-o44` (commits `662bb12`, `38b5d17`, `7627bf6`; `galago-web` image
  `ab544595abe2`) against the live F.A.S.T.log and a read-only `docker cp` copy of
  `/app/data/queue.db`. Check (a) PASS: an accepted abort now dequeues the aborted run's
  remaining steps (run `15420f33a301e7000`, queue rows 132 FAILED / 133 SKIPPED, queue table
  empty). Check (b) PASS: a STARTED step orphaned by a `galago-web` restart is failed and
  dequeued at startup, never re-dispatched (run `154210ef5381e7000`, queue rows 134 FAILED /
  135 SKIPPED, zero Transfer commands after the restart, before and after the operator's
  tool-page Resume completed the still-open original step exactly once).
- Filled `## Safety invariant audit` (design section 7 invariant 1, D-11): compiled 20
  `Running command Pause/Resume/Abort` lines across the live log and every surviving backup
  since the LIVE-04 deploy restart, mapped all 20 to a recorded operator action (0 unmapped),
  explained all 3 tool-process restarts (2 tool-server-only via the `:8081` manager page, 1
  `galago-tools` service restart that is the recorded D-14 LIVE-06b adapter redeploy), and
  named two windows with no surviving production log precisely instead of claiming coverage.
  Result: PASS.
- Marked FINDING (a) and FINDING (b) in `## Flagged assumptions` RESOLVED, citing the
  `261015-o44` live verification.
- Confirmed code unchanged since the last actual redeploy: `git diff --stat 201d987 HEAD --
  tools/ interfaces/ setup.py requirements.txt` is empty; the only commits since the original
  LIVE-04 deploy SHA (`d9acdcf0`) are the two already-evidenced D-14 LIVE-06b adapter fix
  commits (`7d77e23`, `201d987`).
- Ran the post-acceptance gate: `bash bin/make test` exit 0, 144 tests passed, `ruff check .`
  clean, `mypy tools` clean (never `bin/make proto`, which would delete the pb2 files the
  running service imports from this checkout).
- Ran the dry-run harness self-test: `SELF-TEST OK`.
- Confirmed D-13 completeness: six Summary PASS rows, eleven fields present in LIVE-06a/LIVE-05/
  LIVE-06b and twelve in LIVE-07, and added the four required closeout lines (Code unchanged
  since deploy, Post-acceptance gate, Dry-run self-test, Edge-probe fallback) under the Summary.
- Confirmed REQUIREMENTS.md's LIVE-04 to LIVE-07 Complete marks are backed by this evidence (no
  reversion needed).

## Task Commits

1. **Task 1: Complete the LIVE-07 record and audit every control command since the deploy
   (D-11, D-12, D-13)** - `2ae1372` (docs)
2. **Task 2: Post-acceptance gate, code-unchanged check and D-13 completeness** - `698961a`
   (docs)

_No separate plan-metadata commit beyond these two task commits plus the final docs commit made
by this executor after SUMMARY/STATE/ROADMAP updates (see below)._

## Files Created/Modified

- `.planning/phases/03-deploy-supervised-live-acceptance/03-ACCEPTANCE.md` - added
  `## 261015-o44 live verification`, filled `## Safety invariant audit`, updated FINDING
  (a)/(b) to RESOLVED, added the four Summary closeout lines.

## Decisions Made

- LIVE-07's existing twelve-bullet record needed no edits; Task 1 verified it rather than
  rewriting it, since plan 03-07 had already written it in full (D-12 restart record included).
- Compared code-unchanged-since-deploy against the LAST deployed SHA (`201d987`), not the
  original LIVE-04 deploy SHA (`d9acdcf0`), per the actual redeploy history recorded in
  `03-DEPLOY.md` — the two commits between `d9acdcf0` and HEAD are the already-evidenced D-14
  fix, consistent with the plan's "or every change is a D-14 gap fix" allowance.
- FINDING (a) and FINDING (b) are marked RESOLVED rather than left open: the user explicitly
  requested a live verification of the `261015-o44` fixes after LIVE-07 passed, and both checks
  independently confirmed PASS (log evidence plus a fresh, read-only `queue.db` re-query), so
  carrying them forward as unresolved blocking items would misstate the evidence.
- Named two log-coverage gaps precisely (`2026-10-14 ~17:47 WIB -> 2026-10-15 10:16:36 WIB` and
  `2026-10-15 ~11:47 WIB -> 12:02:49 WIB`) in the Safety invariant audit instead of claiming full
  coverage — both rest on records written at the time elsewhere (the dry run's own zero-command
  check; galago-core's `02-UAT.md`), not a fresh audit of files that no longer exist.

## Deviations from Plan

None — plan executed exactly as written. Both tasks' `<verify>` checks passed; no FAIL was
found in the LIVE-07 record, the Safety invariant audit, the code-unchanged check, the gate, the
dry-run self-test, or the D-13 completeness check, so no blocking-human checkpoint was needed.

## Issues Encountered

None. One self-correction during drafting: an early edit referenced the fix commit as
`661bb12` (typo) before the SHA was corrected to `662bb12` and independently re-verified via
`git merge-base --is-ancestor` against galago-core HEAD.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 3's D-13 evidence record is complete: LIVE-04 to LIVE-07 all PASS with full D-11/D-12
  criteria, a clean Safety invariant audit, and a live-verified resolution of the two residual
  galago-core queue findings. REQUIREMENTS.md already shows LIVE-04 to LIVE-07 as Complete,
  confirmed backed by this evidence.
- Open galago-core debt, explicitly out of this phase's scope (recorded in 03-ACCEPTANCE.md,
  not fixed here): the Gantt bar drawing past an abort; "Connect all tools" sending empty
  configs; the "Item N not found" queue-clear-during-abort todo; and F.A.S.T. tool-page UI
  staleness after a reconnect.
- No blockers for milestone close from this plan's evidence.

---
*Phase: 03-deploy-supervised-live-acceptance*
*Completed: 2026-10-15*

## Self-Check: PASSED
