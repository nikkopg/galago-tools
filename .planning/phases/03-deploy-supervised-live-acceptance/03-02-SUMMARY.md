---
phase: 03-deploy-supervised-live-acceptance
plan: 02
subsystem: infra
tags: [docker, docker-compose, galago-web, rollback, deploy, fast-mcp]

# Dependency graph
requires:
  - phase: 03-01 (deploy entry gate, pre-deploy record, go-ahead, Steps 1-2)
    provides: core b30b38d installed and galago-tools restarted onto the Phase 1-2 adapter, F.A.S.T. tool server listening on :40001 NOT_CONFIGURED, all rollback anchors recorded
provides:
  - D-05 step 2 closed with evidence (operator reconnect; fast_status.py READY/idle read from the instrument through the b30b38d core)
  - D-05 step 3 closed with evidence (galago-web rebuilt from the verified galago-core HEAD, running on a genuinely new image ID after a user-directed no-cache rebuild)
  - D-06 rollback anchor (galago-core-galago-web:rollback-pre-live04) preserved, with a documented caveat that it shares content with the new deploy
  - LIVE-04 safe-order timeline (four strictly increasing UTC times)
  - 03-ACCEPTANCE.md (D-13) created with the LIVE-04 block filled and eight remaining sections scaffolded for plans 03-03 through 03-08
affects: [03-03-dry-run-harness, 03-04-to-03-08-live-scenarios]

# Actuals (#2632)
actuals:
  tokens: 4871
  tasks: 2
  commits: 2
  plan_head_before: 568d334aeb3bc1131b358175a09ee84e33a7a49c
  plan_head_after: 5217bd7c9f4d1258ab78a0bdd148fc10c0eff54d

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Cached-rebuild detection: a docker compose up -d --build that CACHEs every layer can produce a byte-identical image ID when the build context hasn't changed since an out-of-runbook rebuild; this is a finding to surface and let the user decide on (no-cache vs. accept), not a silent pass or an auto-fix"
    - "Rollback-anchor content caveat: a pre-deploy image tag is only a true rollback anchor if its content differs from the post-deploy image; when both were built from the same source HEAD, the tag restores identical content and the runbook must say so explicitly rather than implying it undoes the whole deploy"

key-files:
  created:
    - .planning/phases/03-deploy-supervised-live-acceptance/03-ACCEPTANCE.md
  modified:
    - .planning/phases/03-deploy-supervised-live-acceptance/03-DEPLOY.md

key-decisions:
  - "User decision: 'No cache rebuild' — after the first docker compose up -d --build reused Docker's cache for every layer and produced an image ID byte-identical to the rollback tag (galago-core's controller/ had not changed since an out-of-runbook rebuild already recorded in the Pre-deploy record), execution stopped per plan instruction and the user was asked to decide; the user chose to force docker compose build --no-cache galago-web + docker compose up -d so the must-have 'running on a new image ID' is genuinely met rather than accepted as unmeetable by construction"
  - "rollback-pre-live04 was left untouched (not re-tagged) per the user's explicit instruction, and a caveat was recorded in 03-DEPLOY.md's Rollback (D-06) section: that tag was built from the same galago-core HEAD as the new deploy, so rolling galago-web back to it restores identical content, not the pre-milestone UI; a true pre-milestone rollback needs a fresh no-cache rebuild from the pre-milestone galago-core commit"
  - "Only one service (galago-web) is defined in galago-core's docker-compose.yml, confirmed with docker compose config --services before running build/up, so the no-cache rebuild and recreate could not have touched any other container"

requirements-completed: [LIVE-04]

coverage:
  - id: D5
    description: "D-05 step 2 check: after the operator reconnects F.A.S.T. (Simulate off, config unchanged), fast_status.py --port 40001 reports READY/idle through the b30b38d core, and the post-deploy F.A.S.T.log shows a real-mode Received configuration line with the pre-deploy host/port/expected_tray_id"
    requirement: "LIVE-04"
    verification:
      - kind: other
        ref: "fast_status.py --port 40001 -> status READY, run_state.state idle"
        status: pass
      - kind: other
        ref: "F.A.S.T.log Received configuration line: pre-deploy host/port/expected_tray_id, no simulated flag, 0 tracebacks over 444 lines"
        status: pass
    human_judgment: false
  - id: D6
    description: "D-05 step 3 + D-06: galago-web rebuilt only after step 2's check passed, from the verified galago-core HEAD with a clean controller/ tree, rollback tag created first, running on a new image ID after resolving the cached-rebuild finding"
    requirement: "LIVE-04"
    verification:
      - kind: other
        ref: "docker inspect galago-web --format State.Status/.Image -> running, sha256:26917ca7... (differs from rollback-pre-live04 sha256:9ad9c64...)"
        status: pass
      - kind: other
        ref: "curl /api/health -> 200; curl /runs -> 200"
        status: pass
      - kind: other
        ref: "docker exec galago-web grep -rl is_tip_broken /app/.next/server -> found; grep -rl run_state /app/gen-interfaces -> found"
        status: pass
      - kind: other
        ref: "container TCP probe to host.docker.internal:40001 -> open; fast_status.py --port 40001 -> READY/idle; galago-tools MainPID 4044033 unchanged"
        status: pass
    human_judgment: false
  - id: D13
    description: "03-ACCEPTANCE.md created with the nine required level-2 sections, LIVE-04 Deploy block filled from 03-DEPLOY.md evidence, Flagged assumptions section lists A-EDGE-LIVE-04 to 07 plus RESEARCH A1-A3"
    requirement: "LIVE-04"
    verification:
      - kind: other
        ref: "grep -cE over the nine required section headers -> 9"
        status: pass
    human_judgment: true
    rationale: "Whether the LIVE-04 block's evidence is a faithful, complete transcription of 03-DEPLOY.md's rows is a human-reviewable completeness judgment, not something a grep can confirm beyond section presence"

duration: ~2h24min (2026-10-14T10:50:24Z Step 2b check to 2026-10-14T13:14Z, across two sessions — the first was cut off by a usage limit mid-Task 2 and recorded the cached-rebuild BLOCKED finding; this session resumed with the user's no-cache decision)
completed: 2026-10-14
status: complete
---

# Phase 3 Plan 2: Operator Reconnect and galago-web Rebuild Summary

**Operator reconnected the production F.A.S.T. tool (D-05 step 2 closed), then galago-web was rebuilt from the verified galago-core HEAD — a first cached rebuild produced a byte-identical image ID and was correctly stopped as BLOCKED, and a user-directed no-cache rebuild then produced a genuinely new image ID that passed every Step 3 check — closing LIVE-04 and opening 03-ACCEPTANCE.md (D-13) with its block filled.**

## Performance

- **Duration:** ~2h24min (2026-10-14T10:50:24Z Step 2b check to 2026-10-14T13:14Z), across two sessions
- **Started:** 2026-10-14T10:50:24Z (Step 2b run_state check)
- **Completed:** 2026-10-14T13:14Z
- **Tasks:** 2 (Task 1 checkpoint:human-action — operator reconnect; Task 2 auto — galago-web rebuild + 03-ACCEPTANCE.md)
- **Files modified:** 2 (`03-DEPLOY.md`, `03-ACCEPTANCE.md`)

## Accomplishments

- D-05 step 2 closed: the operator reconnected the production F.A.S.T. tool from `galago-web` (Simulate off, configuration unchanged); `fast_status.py --port 40001` confirmed `READY`/`run_state.state: idle` read from the instrument through the `b30b38d` core, and the F.A.S.T. log showed a real-mode `Received configuration` line matching the pre-deploy host/port/`expected_tray_id` with no traceback. Non-blocking UI observation recorded: the operator needed to navigate away and back to the tools page to see the `READY` status render.
- D-05 step 3 attempt 1 (cached): `docker compose up -d --build` from `/home/formulatrix/data/nikko/galago-core` recreated the container but reused Docker's cache for every layer — `galago-core`'s `controller/` had not changed since an earlier out-of-runbook rebuild — producing a running image ID byte-identical to the `rollback-pre-live04` tag. Every content/connectivity/safety check still PASSed. Per the plan's explicit "STOP and report" instruction, this was recorded `BLOCKED` (not scored PASS/FAIL) rather than silently accepted or self-resolved.
- User decision "No cache rebuild": re-confirmed read-only (no run `RUNNING`, `fast_status.py` READY/idle, `galago-tools` MainPID and `galago-core` HEAD unchanged), left `rollback-pre-live04` untouched, confirmed `docker-compose.yml` defines only the `galago-web` service, then ran `docker compose build --no-cache galago-web` followed by `docker compose up -d`. Produced image `sha256:26917ca79a781bb3b3563b481d1845ce1defeb92c33a0dc97e9368baf39029a2`, genuinely different from the rollback tag, and every Step 3 check PASSed (health/runs 200, `is_tip_broken`/`run_state` present in the built app, host port `40001` reachable, `fast_status.py` still READY/idle, `galago-tools` MainPID unchanged).
- `03-DEPLOY.md` updated: Step 3 row rewritten to two rows (cached attempt BLOCKED, no-cache rebuild PASS), the Safe-order line's build-start time updated to the no-cache rebuild's start, and a Rollback (D-06) caveat added explaining `rollback-pre-live04` shares content with the new deploy.
- `03-ACCEPTANCE.md` (D-13) created with all nine required level-2 sections; the `## LIVE-04 Deploy` block is fully filled (date/time, operator, SHAs/images, per-step check results, safe order, rollback anchors with caveat, Result: PASS); the Flagged assumptions section lists `A-EDGE-LIVE-04` through `A-EDGE-LIVE-07` with how each plan in the phase handles them, plus `RESEARCH A1`-`A3`; the remaining five scenario sections are left "not run" for plans 03-03 through 03-08.

## Task Commits

1. **Task 1 (checkpoint:human-action, operator reconnect) + Task 2 (Step 3 rewrite to PASS):** `5e324d0` (docs) — Step 2b reconnect evidence row and the rewritten Step 3 (cached BLOCKED + no-cache PASS) rows, safe-order update, rollback caveat
2. **Task 2 (03-ACCEPTANCE.md creation):** `5217bd7` (docs) — nine-section evidence record with the LIVE-04 block filled

**Plan metadata:** commit pending (docs: complete plan)

## Files Created/Modified

- `.planning/phases/03-deploy-supervised-live-acceptance/03-ACCEPTANCE.md` - phase evidence record (D-13): Summary table, `## LIVE-04 Deploy` filled, five live-scenario sections plus Safety invariant audit and Flagged assumptions scaffolded for later plans
- `.planning/phases/03-deploy-supervised-live-acceptance/03-DEPLOY.md` - Step 2b reconnect row, Step 3 rewritten (cached attempt + no-cache rebuild), Safe-order line updated, Rollback (D-06) caveat added

## Decisions Made

- The first `docker compose up -d --build` run was correctly treated as a finding requiring a user decision, not an auto-fixable deviation: the functional/content/connectivity checks all PASSed, but the literal must-have ("running image ID differs from the rollback tag") could not be met by that exact, documented command because there was no new build content. This is an environment-state fact (an earlier out-of-runbook rebuild had already produced that content), not a bug in the plan or the command — Rule 4 (architectural/significant decision) applied, and execution stopped for the user's go-ahead rather than silently retrying or substituting a different command.
- `rollback-pre-live04` was deliberately left un-retagged per explicit user instruction, even though it now "lags" the deploy's actual rollback intent; the gap was made visible instead via a caveat note in `03-DEPLOY.md`'s Rollback (D-06) section, so a future rollback decision is made with full information rather than assuming the tag means what its name implies.
- `docker compose up -d` (without `--build`) was used after the separate `docker compose build --no-cache galago-web`, rather than repeating `--build`, since the image had already been freshly built; this avoided a second redundant build pass while still recreating the container on the new image.

## Deviations from Plan

None — plan executed exactly as written, including its "STOP and report" instruction for the cached-rebuild finding. The no-cache rebuild path was carried out on the user's explicit decision (continuation-state instruction), consistent with the plan's own provision that "If any check fails: STOP and report; the galago-web rollback in 03-DEPLOY.md runs only on the user's go-ahead" — here the resolution was a forward fix (no-cache rebuild), not a rollback, and still required the same explicit go-ahead gate before proceeding.

## Issues Encountered

The first `docker compose up -d --build` (documented runbook command) produced a byte-identical image ID because galago-core's `controller/` had not changed since an earlier out-of-runbook rebuild recorded in the Pre-deploy record (`2026-10-14T08:10:47Z`, same HEAD). This is an environment pre-condition, not a bug introduced by this plan; it was surfaced as a BLOCKED finding and resolved by the user's "No cache rebuild" decision rather than worked around automatically.

## User Setup Required

None further for this plan. The operator's two actions (Task 1 reconnect, and the Step 3 "No cache rebuild" decision) are already recorded above and in `03-DEPLOY.md`.

## Next Phase Readiness

- `galago-web` is running image `sha256:26917ca79a781bb3b3563b481d1845ce1defeb92c33a0dc97e9368baf39029a2`, built from `galago-core` HEAD `d95c2e143ca13d8837bd9c248d6579777b2ebdc9` with a genuinely fresh, no-cache build; the F.A.S.T. tool reports `READY`/`idle`; `galago-tools` is unchanged on MainPID `4044033`.
- LIVE-04 is fully evidenced end to end (core -> galago-tools -> operator reconnect -> galago-web), with the safe-order timeline and rollback anchors for every layer (with the rollback-pre-live04 content caveat recorded).
- `03-ACCEPTANCE.md` is open with the LIVE-04 block complete; plan 03-03 (dry run, D-07) fills the next section, followed by the live scenarios in 03-04 through 03-08.
- No motion was performed and no `Configure`/`ExecuteCommand`/other command was sent to any tool by Claude in this plan.

---
*Phase: 03-deploy-supervised-live-acceptance*
*Completed: 2026-10-14*

## Self-Check: PASSED

- FOUND: .planning/phases/03-deploy-supervised-live-acceptance/03-ACCEPTANCE.md
- FOUND: .planning/phases/03-deploy-supervised-live-acceptance/03-DEPLOY.md
- FOUND commit: 5e324d0, 5217bd7
