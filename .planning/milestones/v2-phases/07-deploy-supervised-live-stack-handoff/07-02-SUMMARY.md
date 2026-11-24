---
phase: 07-deploy-supervised-live-stack-handoff
plan: 02
subsystem: deployment-live-infrastructure
tags: [gal07, stack, live-deploy, systemd, docker-compose, runbook, safe-order, rollback-anchor]

requires:
  - phase: 07-deploy-supervised-live-stack-handoff plan 01
    provides: the live runbook + executable pre-flight gate (PREFLIGHT OK / BLOCKED verdicts), findings log shape
  - phase: 06-gal02-workflow-simulated-runs (DEP-02 core build)
    provides: stack_automation_layer 934a621 pin, the DEP-02 gate
provides:
  - stack_automation_layer 934a621 installed into the service .venv (uv-only install, D-04 waiver recorded)
  - stack credentials wired through the operator's 0600 env file + unit drop-in (values never read)
  - restarted galago-tools service with listener-PID baseline; D-06 backups recorded
  - store holds both a stack and a fast tool (D-12 gap closed); both READY; reads answer 200
  - galago-web rebuilt on a new image (rollback anchor galago-core-galago-web:rollback-pre-gal07 tagged), Command_Transfer in the container bundle
  - findings row G0 + rows 1a-1..1a-6 all PASS, including the four strictly-increasing UTC timestamps (LIVE-08 safe-order proof)
affects: [07-03 (live rehearsal Transfer LIVE-09), 07-04 (supervised GAL-02 handoff LIVE-10), verify-work / UAT, Phase-7 close-out]

actuals:
  tokens: 3290        # chars/4 over the cumulative plan diff (13,160 chars — findings rows are long single lines)
  tasks: 3
  commits: 4          # MEASURED from ledger b7c6ab7..HEAD at SUMMARY write time
plan_head_before: b7c6ab7d5c8aa87183fc4a39477d9465ce85fab5
plan_head_after: d9488c0fb7f194ad4857ea5fddcdc42cf23b1b2a

tech-stack:
  added: [stack-automation-layer @ 934a621 (service .venv, git+file local install per waiver)]
  patterns: [typed-go + UTC timestamp per live event (D-10), presence-only credential checks, rollback docker tag before image rebuild, listener-PID not-MainPID no-restart baseline]

key-files:
  created:
    - .planning/phases/07-deploy-supervised-live-stack-handoff/deferred-items.md
    - .planning/phases/07-deploy-supervised-live-stack-handoff/07-USER-SETUP.md
  modified:
    - docs/runbooks/gal-07-live-handoff.md (findings G0, 1a-1..1a-6, Part-1 evidence table Step 3 row, pre-deploy rollback anchors)

key-decisions:
  - "OQ-1 resolved by user decision: local-clone-waiver of D-04 — install ran from /home/formulatrix/data/nikko/stack-automation-layer @ 934a621… (HEAD verified == pin) after the git+https probe stalled in an OAuth device flow"
  - "Reconnect order held (OQ-3): FAST Configure first, STACK real-mode Configure LAST, both through the operator's prod-page clicks after a tool-server/repair cycle (row 1a-5)"
  - "F.A.S.T. hardware moved off the v1 host: 10.150.1.170 dead, instrument at 192.168.0.26:5003 bridged to forb01 via the operator's ssh tunnel (tool FA100056 stores host 127.0.0.1, port 5003)"
  - "galago-web vault executed by Claude after the operator's literal typed go (01:31:09Z): anchor tag → TOOLBOX_PORT=11010 docker compose up -d --build from galago-core a799627 (vendor bcbbf8e)"

patterns-established:
  - "Pattern: presence-only evidence rows for secret-adjacent steps (assignment-line count + file mode, values never echoed)"
  - "Pattern: PITFALL-3 guard executed live — anchor image tagged (sha256:93821723…), rebuilt sha256:2f609032… compared, cache-hit STOP unused because IDs differ"

requirements-completed: [LIVE-08]

coverage:
  - id: D1
    description: "Public service .venv runs stack_automation_layer pinned at 934a621… installed uv-only from the operator-approved local clone (verifiable build lineage via direct_url.json)"
    requirement: LIVE-08
    verification:
      - kind: integration
        ref: "command: pre-flight gal-07-live-check.sh check 3 (direct_url.json vcs_info.commit_id == 934a621…) passed 2026-11-03T01:18Z + unittest tools.tests.stack_test 271 OK (row 1a-2)"
        status: pass
    human_judgment: false
  - id: D2
    description: "STACK credentials reach the tool server only through the operator's 0600 env file wired as a unit drop-in, with a D-06 backup taken before the restart; service restarted with a new MainPID"
    requirement: LIVE-08
    verification:
      - kind: manual_procedural
        ref: "docs/runbooks/gal-07-live-handoff.md rows 1a-3/1a-4 (presence-only grep -c ×1, stat mode 600, backup pre-gal07-20261102T112327Z, MainPID 1940146→3973399, no traceback, fast_status :40012 NOT_CONFIGURED)"
        status: pass
    human_judgment: true
    rationale: "credential entry, the env-file edit and the restart are operator-only privileged actions (D-06/D-10) — automation can only place the evidence, the operator must vouch the values went into the file and that the restart did what is recorded"
  - id: D3
    description: "Store reconnect: fast tool (FA100056) and stack tool (STACK2-6, config byte-for-byte 10.150.1.125:5005) both configured with FAST first / STACK real-mode Configure last, both READY, reads 200"
    requirement: LIVE-08
    verification:
      - kind: integration
        ref: "command: curl http://localhost:3010/api/tools → [fast FA100056, stack STACK2-6] (Task 3 verify block 1, passed this session; rows 1a-5)"
        status: pass
    human_judgment: true
    rationale: "the Configures were operator clicks from the prod page and the single-owner owner-lock state is an operator-visible session condition; the automated suite can re-check the store but not the act of a supervised reconnect"
  - id: D4
    description: "galago-web rebuilt on a new image (differs from the tagged rollback anchor), /api/health 200, Command_Transfer in the container bundle, the container reaches host.docker.internal:40012, store intact after the rebuild"
    requirement: LIVE-08
    verification:
      - kind: e2e
        ref: "command: docker inspect diff + curl /api/health + docker exec grep Command_Transfer + node TCP connect 40012 (Task 3 verify block 1, all pass 2026-11-03T01:33Z)"
        status: pass
    human_judgment: false
  - id: D5
    description: "LIVE-08 safe-order proof: findings row 1a-6 holds the four strictly-increasing UTC timestamps (install/restart/reconnect/rebuild), plus the recordings row G0 and rollback anchors"
    requirement: LIVE-08
    verification:
      - kind: other
        ref: "command: python assert — 6 finding rows end PASS and row 1a-6 carries 4 distinct sorted ISO timestamps (passed this session)"
        status: pass
    human_judgment: false

duration: ~14h 21m elapsed (two sessions — original executor cancelled mid-plan; this continuation session ran ~19 min active + one supervised rebuild)
completed: 2026-11-03
status: complete
---

# Phase 7 Plan 2: Deploy & Supervised Live STACK (Part 1 of the runbook) Summary

**STACK production stack deployed in the LIVE-04 safe order — DEP-02 core (`934a621`) into the service `.venv` via an operator-approved local-clone waiver, credentials + backup + restart, FAST-first/STACK-Last reconnect closing the D-12 store gap, and `galago-web` rebuilt on a new image (anchor `93821723…` → `2f609032…`) with all five findings rows PASS and the four-timestamp safe-order proof.**

## Performance

- **Duration:** ~14h 21m elapsed across two sessions (the original executor was cancelled after Task 2 Step 2b; this continuation session resumed at Task 3 Step 3 and ran the rebuild + recording, ~19 min)
- **Started:** 2026-11-02T11:16:48Z (first finding/commit); **Completed:** 2026-11-03T01:37:29Z
- **Tasks:** 3 (Task 3 completed by the continuation session at Step 3 — Step 2b was executed by the prior session)
- **Files modified:** 3 (runbook evidence; deferred-items register; USER-SETUP)

## Accomplishments
- Core install proven end-to-end: the pinned `stack_automation_layer 934a621…` resolved by `direct_url.json` commit assert, `tools.tests.stack_test` 271 OK, installed uv-only into the service `.venv` (findings rows G0, 1a-1, 1a-2)
- Credentials wiring + D-06 backup + restart evidenced presence-only: 0600 env file, unit drop-in, backup `pre-gal07-20261102T112327Z`, MainPID 1940146→3973399, no traceback, listeners re-baselined (rows 1a-3, 1a-4)
- Operator reconnect completed the D-12 store gap: FA100056 + STACK2-6 in the store with the byte-for-byte `10.150.1.125` host, both READY, `GetRobotStates`/`GetManagerState` 200 (row 1a-5)
- `galago-web` rebuilt from galago-core `a799627` (vendor `bcbbf8e`): new image `sha256:2f609032…` ≠ anchor `93821723…` (no Pitfall-3 STOP), `/api/health` 200, `Command_Transfer` in the container bundle, container↔`host.docker.internal:40012` TCP verified, store intact (row 1a-6 + evidence table Step 3)
- Row 1a-6 carries the four strictly-increasing UTC timestamps (2026-11-02T11:20:00Z < 11:24:34Z < 12:18:28Z < 2026-11-03T01:31:16Z) — the LIVE-08 order proof; pre-deploy rollback anchors filled with real recorded values

## Task Commits

Each task was committed atomically (Tasks 1-2 by the interrupted session, verified before resuming):

1. **Task 1: OQ-1 install-source decision + pre-flight verdict G0** — `f13ec3d` (docs)
2. **Task 2: Deploy Steps 1-2** — `f4c9f02` (docs)
3. **Task 3 (Step 2b recovery): reconnect evidence row 1a-5** — `b9011f6` (docs, recovered from the interrupted session)
4. **Task 3 (this session): Step 3 rebuild + row 1a-6 + anchors + deferred-items** — `d9488c0` (docs)

## Files Created/Modified
- `docs/runbooks/gal-07-live-handoff.md` - findings rows G0..1a-6, Part-1 evidence table Step 3 row, pre-deploy rollback anchors (real values)
- `.planning/phases/07-deploy-supervised-live-stack-handoff/deferred-items.md` - the owner-lock probe finding (scope-bounded, left open)
- `.planning/phases/07-deploy-supervised-live-stack-handoff/07-USER-SETUP.md` - user_setup item resolved via the recorded waiver

## Decisions Made
- **local-clone-waiver (OQ-1):** the pinned `git+https` install requires GitLab browser OAuth which stalled; the operator explicitly waived D-04 for this session after the local clone's HEAD was verified equal to the pin (recorded in row 1a-1)
- **D-14 repair cycle accepted on hardware:** the first tool pair had swapped ports and the F.A.S.T. moved hosts; fixes went through the operator's own repair (sd tunnel + manager relaunch), never through restart-to-reset (row 1a-5)
- **Push of running adapter SHA into the rollback anchors** (`b7c6ab7`) so the eventual rollback path names a real commit

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] findings row 1a-3 prose tripped the pinned credential-value regex**
- **Found during:** Task 3 (the plan's test gate)
- **Issue:** the interrupted session's committed row 1a-3 quoted the assignment line as `` `STACK_USER=` ``, and `test_runbook_holds_no_credential_values` excludes only whitespace/`$`/`<`/quotes after `=`, so the trailing backtick matched; 1 test failed
- **Fix:** reworded the row to "exactly 1 STACK_USER assignment line / 1 STACK_PASSWORD assignment line" (presence-only phrasing intact, meaning unchanged)
- **Files modified:** docs/runbooks/gal-07-live-handoff.md (row 1a-3 only)
- **Verification:** `bin/make proto && pytest gal07+gal02` → 35 passed
- **Committed in:** `d9488c0` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug). **Impact on plan:** no deploy step was re-run; the fix is evidence-text only.

## Issues Encountered
- **The pre-flight's owner-lock probe (docs/runbooks/gal-07-live-check.sh check 2) refuses `PREFLIGHT OK` on the session's own galago tool server once the STACK tool is configured** — the holder record says `galago (pid 4004972)`, i.e. the intended single owner, but the probe fails on any held lock. Live at `PREFLIGHT` re-run 2026-11-03T01:18Z, this is the only remaining BLOCKED line. Out of this plan's scope (07-01 artifact): logged open in `deferred-items.md` with a fix direction (treat owner `galago` as the expected case; keep blocking owner `mcp`/unknown). Plan 07-03's entry gate depends on it — the next executor mustresolve this piece through the 07-01 test module's wording pins, not hand-edit around it.
- GitLab auth blocked the pin (original OQ-1): resolved by the operator's waiver, no credentials created.

## User Setup Required

Resolved — see [07-USER-SETUP.md](./07-USER-SETUP.md). No external accounts, env vars or dashboard steps remain; the operator's 0600 env file already carries the credentials (values never read).

## Next Phase Readiness
- The stack is deployed, healthy and store-complete: `LIVE-08` satisfied; the Phase 6 watch item (a reconfigure dropping the peer tool) did not recur across the whole session
- Part 2 (07-03, LIVE-09 rehearsal Transfer) can begin once the owner-lock probe defect above is resolved in the 07-01 gate script — plan 07-03's executor should treat that as its entry-gate concern
- **Note for 07-03/07-04:** the F.A.S.T. now answers at `192.168.0.26:5003` (bridged to forb01 through the operator's ssh tunnel, tool FA100056 stores host `127.0.0.1`, port `5003`, expected_tray_id 90) — `Part 3`'s note that "the F.A.S.T. step fields keep the v1 config values" should read against the new tunnel path, not v1's `10.150.1.170:5003`
- The pre-flight's remaining BLOCKED line (owner-lock probe) is the only gate residue; the D-12 store check and core-pin check pass on the real host

---
*Phase: 07-deploy-supervised-live-stack-handoff*
*Completed: 2026-11-03*

## Self-Check: PASSED

All key files exist on disk; all five plan commits (f13ec3d, f4c9f02, b9011f6, d9488c0, 1b26186)
are ancestors of HEAD. Measured 4 task commits from the plan ledger (b7c6ab7..d9488c0) plus this
metadata commit.
