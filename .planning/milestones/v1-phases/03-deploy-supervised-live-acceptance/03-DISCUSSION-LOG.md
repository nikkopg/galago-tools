# Phase 3: Deploy & Supervised Live Acceptance - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-14
**Phase:** 03-deploy-supervised-live-acceptance
**Mode:** `--auto` (recommended option auto-selected for every question)
**Areas discussed:** Entry gate, Core install source, Deploy procedure, Rollback, Dry run, Operator control, Scenario order, Restart scenario, Evidence, Failure handling

---

## Entry gate
[auto] Entry gate — Q: "What must hold before Phase 3 executes?" → Selected: "galago-core milestone verified, gate green, submodule has run_state/Pause, local clone has b30b38d; first plan task checks and stops" (recommended default)

| Option | Description | Selected |
|--------|-------------|----------|
| Hard entry check in the first plan task | Stop on any unmet prerequisite | ✓ |
| Deploy the adapter now, UI later | Splits the safe order | |

## Core install source
[auto] Core install — Q: "Install from GitLab pin URL or local clone?" → Selected: "Local clone at the pinned SHA, commit_id checked" (recommended default)

| Option | Description | Selected |
|--------|-------------|----------|
| Local clone at b30b38d | Same as every forb01 deploy; no push needed | ✓ |
| GitLab pin URL | Needs the user to push fix/run-recovery-gate first | |

## Deploy procedure
[auto] Deploy — Q: "Who runs the deploy and how is it checked?" → Selected: "Runbook; Claude runs non-motion steps after the user's go-ahead; check after each step" (recommended default)

| Option | Description | Selected |
|--------|-------------|----------|
| Runbook + per-step checks, Claude executes after go-ahead | Auditable, no unattended restarts | ✓ |
| Operator runs everything by hand | Slower, same safety | |
| Deploy script | Extra code for a one-off | |

## Rollback
[auto] Rollback — Q: "Rollback order?" → Selected: "Reverse order: web, tools, core; SHAs recorded before deploy" (recommended default)

## Dry run
[auto] Dry run — Q: "Simulated dry run before the instrument?" → Selected: "Yes, simulated F.A.S.T. with simulate_pause, no motion" (recommended default)

## Operator control
[auto] Control — Q: "Who sends motion/control commands during acceptance?" → Selected: "Operator only, through the Galago UI; Claude prepares, watches the journal, and waits for go-ahead before every motion step" (recommended default)

## Scenario order
[auto] Order — Q: "Scenario order?" → Selected: "Pause→Resume, deck-3, Pause→Abort, restart web" (least to most disruptive) (recommended default)

| Option | Description | Selected |
|--------|-------------|----------|
| Least to most disruptive | A failure early costs least | ✓ |
| Requirement order (LIVE-05 first) | Deck-3 first needs the deck manipulated before basics are proven | |

## Restart scenario
[auto] Restart — Q: "How to run LIVE-07?" → Selected: "Pause, restart galago-web, Resume (tip intact) from the tool page; Abort as fallback; check the lock clears" (recommended default)

| Option | Description | Selected |
|--------|-------------|----------|
| Pause first, then restart, tool-page Resume | Run held in a known state during the restart | ✓ |
| Restart while running, tool-page Abort | Less control over timing | |

## Evidence
[auto] Evidence — Q: "Where is acceptance recorded?" → Selected: "03-ACCEPTANCE.md per scenario: time, operator, parameters, decisions, journal excerpt, result, screenshots" (recommended default)

## Failure handling
[auto] Failure — Q: "What happens when a scenario fails?" → Selected: "Stop; operator makes it safe; /gsd-debug; gap fix through the gate; redeploy in order; rerun from the failed scenario" (recommended default)

---

## Claude's Discretion

- Runbook file vs plan section; how the `.venv` capability check runs.
- Plan split (entry gate + deploy → dry run → live scenarios); checklist wording.

## Deferred Ideas

- Pushing fast-mcp `fix/run-recovery-gate` to GitLab and the Galago forks' branches to GitHub (user's action).
- Crash-recovery Resume run_state from the adapter's record; EstimateResume split; hard pause; second runControl tool.
- galago-tools restart mid-run scenario (not a LIVE requirement).
