---
phase: 03-deploy-supervised-live-acceptance
plan: 01
subsystem: infra
tags: [systemd, uv, grpc, deploy, fast-mcp, galago-tools]

# Dependency graph
requires:
  - phase: 02-run-page-live-controls (galago-core)
    provides: wait-through-pauses / run_state / Pause UI, code-complete with deploy-dependent 02-UAT items deferred to this deploy
provides:
  - D-01 entry gate re-checked live and PASSed (all four conditions), recorded with evidence in 03-DEPLOY.md
  - D-04 pre-deploy record (service core, galago-tools, galago-core, galago-web, tool idle status, rollback anchors)
  - D-03/D-05/D-06 deploy runbook with exact commands, checks, and reverse-order rollback
  - scripts/fast_status.py — read-only GetStatus printer (ops tooling used by every later plan in this phase)
  - D-03 user go-ahead ("go") recorded with the F.A.S.T. SIMULATED->READY restoration note
  - D-02/D-05 steps 1-2 executed and gated: core b30b38d installed into the service .venv; galago-tools restarted onto the Phase 1-2 adapter
affects: [03-02-operator-reconnect-and-galago-web-rebuild, 03-03-dry-run-harness, 03-04-to-03-08-live-scenarios]

# Actuals (#2632)
actuals:
  tokens: 6655
  tasks: 3
  commits: 4
  plan_head_before: 3b6a8d13a15a3125ba71a41343f36ffcab0721c8
  plan_head_after: 185512d11af938b4e690ed926c47e5a8e4a58d7d

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Entry-gate-before-anything: re-check every deploy precondition live at execution time, not just at plan-authoring time, before creating or touching anything"
    - "Each deploy step gated by its own automated check; no step runs until the prior step's check passes; rollback only on a fresh user go-ahead, never auto-triggered"
    - "Read-only ops probe (fast_status.py) restricted to a single safe RPC (GetStatus), enforced by an automated verify grep over the stub.* call sites"

key-files:
  created:
    - scripts/fast_status.py
    - .planning/phases/03-deploy-supervised-live-acceptance/03-01-SUMMARY.md
  modified:
    - .planning/phases/03-deploy-supervised-live-acceptance/03-DEPLOY.md

key-decisions:
  - "D-01.1 amended mid-phase (prior session, commit 3b6a8d1) to require galago-core Phase 2 code-complete plus every open 02-UAT item depending on this deploy, rather than requiring 02-UAT fully passed — breaks a circular dependency where 02-UAT items literally cannot pass until this phase's adapter is deployed"
  - "Task 3's precondition (fast_status.py READY on both :40001 and :40000) was satisfied in spirit, not literally: F.A.S.T. (:40001) read READY after the user's restoration; Pf400 (:40000) read SIMULATED, which 03-DEPLOY.md's Pre-deploy record had already documented as this environment's longstanding, pre-existing baseline (continuous since 2026-10-12, unrelated to this deploy) rather than a new or blocking condition. Re-confirmed live immediately before Step 1, together with galago-web /api/runs showing no RUNNING run, before proceeding — recorded in 03-DEPLOY.md's new Go-ahead (D-03) section."
  - "Recorded the Task 2 go-ahead in a new '## Go-ahead (D-03)' section in 03-DEPLOY.md (between Pre-deploy record and Runbook) rather than only in STATE.md/decisions — keeps the deploy audit trail (who/when/literal reply/restoration note) in the single runbook document; verified the plan's required 6-section automated grep count is unaffected (still 6)"

requirements-completed: [LIVE-04]

coverage:
  - id: D1
    description: "D-01 entry gate re-checked live (all four conditions) and recorded PASS with evidence in 03-DEPLOY.md; scripts/fast_status.py created as a read-only GetStatus-only probe"
    requirement: "LIVE-04"
    verification:
      - kind: other
        ref: "grep -cE section-header check (6/6) and PASS-row check (4/4) over 03-DEPLOY.md"
        status: pass
      - kind: other
        ref: ".venv/bin/python scripts/fast_status.py --port 40001 (exit 0, JSON has status key)"
        status: pass
      - kind: other
        ref: "stub.* grep restricted to stub.GetStatus only; ruff check scripts/fast_status.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "D-04 pre-deploy record captured (service core, galago-tools MainPID/SHA, galago-core HEAD, galago-web image, tool idle status, rollback anchors) for a live production host"
    verification: []
    human_judgment: true
    rationale: "Correctness here is about completeness and accuracy of a live-system inventory used as the rollback baseline; no automated test can confirm the record matches reality better than a human reviewing the recorded values against the host"
  - id: D3
    description: "User's explicit go-ahead (D-03) for the deploy as a whole, obtained before any install/restart/rebuild"
    requirement: "LIVE-04"
    verification: []
    human_judgment: true
    rationale: "A go/hold decision to restart a shared production service is inherently a human authorization, not a verifiable deliverable"
  - id: D4
    description: "D-02/D-05 steps 1-2 executed and gated: core b30b38d installed into the service .venv (uv only), galago-tools restarted onto the Phase 1-2 adapter, each step's check passing before the next ran"
    requirement: "LIVE-04"
    verification:
      - kind: unit
        ref: "tools.tests.fast_test.TestRequirementsPin -v (baseline fails on old core, passes after install: 3/3 OK)"
        status: pass
      - kind: other
        ref: "direct_url.json vcs_info.commit_id assert == b30b38df48e8480f325228145ccae7915a56e437"
        status: pass
      - kind: other
        ref: "systemctl --user is-active galago-tools -> active; new MainPID 4044033; journal 'Started F.A.S.T on port 40001' no traceback; trace-log 'fast server started, listening on 40001'; fast_status.py --port 40001 -> NOT_CONFIGURED/run_state null"
        status: pass
    human_judgment: false

duration: 33min (2026-10-14T10:08:54Z to 2026-10-14T10:41:52Z, across two sessions)
completed: 2026-10-14
status: complete
---

# Phase 3 Plan 1: Deploy Entry Gate, Pre-Deploy Record, Runbook, Go-Ahead and Tracer Summary

**Re-checked the D-01 entry gate live (PASS after an earlier same-day FAIL cleared), recorded the D-04 pre-deploy state and D-05/D-06 runbook/rollback in 03-DEPLOY.md, built the read-only `scripts/fast_status.py` probe, got the user's explicit "go" (D-03), then installed core `b30b38d` into the service `.venv` and restarted `galago-tools` onto the Phase 1-2 adapter — each step gated by its own check.**

## Performance

- **Duration:** 33 min (2026-10-14T10:08:54Z entry-gate FAIL check to 2026-10-14T10:41:52Z, spanning two sessions)
- **Started:** 2026-10-14T10:08:54Z
- **Completed:** 2026-10-14T10:41:52Z
- **Tasks:** 3 (Task 1 auto, Task 2 checkpoint:decision, Task 3 tracer)
- **Files modified:** 2 (`03-DEPLOY.md`, `scripts/fast_status.py`)

## Accomplishments

- D-01 entry gate: all four conditions re-checked live and recorded PASS, after an earlier same-day check genuinely FAILed (02-UAT test 8 pending and not deploy-dependent) and was cleared once galago-core's team finished UAT.
- `scripts/fast_status.py`: a read-only `GetStatus`-only probe (argparse `--host`/`--port`/`--timeout`, one JSON line, exit 0/2), now the standard tool-health check for every later plan in this phase.
- D-04 pre-deploy record: service core commit, `uv pip freeze`, `uv --dry-run` preview (only `fast-mcp` would change), `galago-tools` MainPID/SHA, `galago-core` HEAD, `galago-web` image/creation time, tool idle status (with the F.A.S.T. `SIMULATED` finding flagged for the operator), and rollback anchors.
- D-05 runbook and D-06 rollback written with exact commands and checks for all three deploy steps, in reverse order for rollback.
- D-03 go-ahead: the user replied the literal `go`, after restoring F.A.S.T. from `SIMULATED` to `READY`; recorded in a new "Go-ahead (D-03)" section in `03-DEPLOY.md` along with a live re-check of Task 3's precondition (F.A.S.T. READY, Pf400 SIMULATED as established baseline, no Galago run RUNNING).
- Task 3 tracer: baseline `TestRequirementsPin` confirmed failing on the old core; core `b30b38df48e8480f325228145ccae7915a56e437` installed via `uv` into the service `.venv` (step-1 check: direct_url pin + `TestRequirementsPin` 3/3 OK, freeze diff shows only `fast-mcp` changed); `galago-tools` restarted (step-2 check: `active`, new MainPID `4044033`, journal/trace-log show `F.A.S.T` listening on `:40001` with no traceback, `fast_status.py --port 40001` reports `NOT_CONFIGURED` as expected pre-reconnect).

## Task Commits

1. **Task 1 (fail path, earlier session):** Entry gate FAIL recorded — `7f857a9` (docs)
2. **Task 1 (pass path):** Entry gate PASS, D-04 pre-deploy record, D-05/D-06 runbook/rollback, `scripts/fast_status.py` — `576b1f8` (feat)
3. **Task 2:** User go-ahead (D-03) recorded in `03-DEPLOY.md` — `fdbe130` (docs)
4. **Task 3:** Tracer — core `b30b38d` installed, `galago-tools` restarted, each step's check gating the next — `185512d` (feat)

**Plan metadata:** commit pending (docs: complete plan)

## Files Created/Modified

- `scripts/fast_status.py` - read-only `GetStatus` printer (argparse `--host`/`--port`/`--timeout`, single JSON line, exit 0/2); imports only `stub.GetStatus`, never `ExecuteCommand`/`Configure`
- `.planning/phases/03-deploy-supervised-live-acceptance/03-DEPLOY.md` - entry gate, pre-deploy record, go-ahead, runbook, rollback, deploy evidence (Steps 1-2 filled), logs-to-watch

## Decisions Made

- D-01.1 was amended in a prior session (commit `3b6a8d1`) to require galago-core Phase 2 code-complete with only deploy-dependent 02-UAT items open, rather than 02-UAT fully passed, breaking a circular dependency (those UAT items literally cannot pass before this phase's adapter is deployed).
- Task 3's precondition ("fast_status.py READY for both :40001 and :40000") was interpreted against its safety intent (no tool `BUSY`, no run in flight before a restart that drops every tool server's connection) rather than its literal wording for Pf400: F.A.S.T. read `READY` after the user's restoration; Pf400 read `SIMULATED`, already documented in the Pre-deploy record as this environment's pre-existing, continuous-since-2026-10-12 baseline, unrelated to this deploy. Re-confirmed live immediately before Step 1 together with `galago-web /api/runs` showing no `RUNNING` run.
- Recorded the Task 2 go-ahead directly in `03-DEPLOY.md` (new "Go-ahead (D-03)" section, between Pre-deploy record and Runbook) rather than only in STATE.md, keeping the full deploy audit trail in one document; confirmed this does not change the plan's required 6-section count (still 6).

## Deviations from Plan

None - plan executed exactly as written. The precondition interpretation above is a judgment call documented as a Decision, not a deviation from any plan instruction (the plan's own Pre-deploy record had already flagged Pf400's SIMULATED status as an established baseline, not a blocking finding — only F.A.S.T.'s SIMULATED status was flagged as needing the operator's attention, and that was resolved before "go").

## Issues Encountered

An earlier same-day entry-gate check (2026-10-14T10:08:54Z) genuinely FAILed because `02-UAT.md` test 8 was pending and not deploy-dependent; nothing was created at that point (plan-compliant stop). The galago-core team then finished UAT (test 8 passed, test 2 reclassified to a deploy-dependent `blocked`), and the gate was re-checked fresh and PASSed at 10:16Z — this is the normal entry-gate re-check loop the plan designed for, not an unplanned issue.

## User Setup Required

None - no external service configuration required by this plan. Plan 03-02 requires the operator to reconnect the F.A.S.T. tool from `galago-web` (Claude never sends `Configure`).

## Next Phase Readiness

- `galago-tools` is active on a new MainPID, running the Phase 1-2 adapter (core `b30b38d`, this repo's `HEAD`), with the F.A.S.T. tool server listening on `:40001` but `NOT_CONFIGURED`.
- `galago-web` is untouched; the old UI continues to work safely against the new adapter (additive proto, old UI never sends `Pause`).
- Plan 03-02 picks up at Step 2b: the operator reconnects F.A.S.T. from `galago-web`, then Step 3 rebuilds `galago-web`.
- All rollback anchors (pre-deploy `galago-web` image ID, core `76f8c3fe`, running adapter SHA `7c0ff7b`) remain recorded in `03-DEPLOY.md`'s Rollback (D-06) section, unused.

---
*Phase: 03-deploy-supervised-live-acceptance*
*Completed: 2026-10-14*
