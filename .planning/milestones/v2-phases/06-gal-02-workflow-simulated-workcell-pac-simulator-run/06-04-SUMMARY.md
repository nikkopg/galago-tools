---
phase: 06-gal-02-workflow-simulated-workcell-pac-simulator-run
plan: 04
subsystem: testing
tags: [runbook, pac-simulator, stack-real-mode, redispatch, ledger, findings-log]

requires:
  - phase: 06-gal-02-workflow-simulated-workcell-pac-simulator-run
    provides: "06-01 offline re-dispatch proof; 06-02 runbook and DEP-02 gate; 06-03 Part 2a rows"
provides:
  - Findings rows 2b-0..2b-5 in docs/runbooks/gal-02-handoff.md, all PASS
  - Evidence that the real STACK adapter, real ledger and a real STACK API (PAC simulator on loopback) replay a re-dispatched completed step with no second POST
  - A calibrated sim-side submit counter (+1 on the in leg) backing the +0 readings
affects: [07 hardware deploy]

status: complete
commits: 1
plan_head_before: 43374dd6721f54efdf51d08c1027a95f3b7ef259
plan_head_after: 3f0d3a471f451eac5983c449bec2fdf7046d4a0d

actuals:
  tokens: 6500
  tasks: 3
  commits: 1

tech-stack:
  added: []
  patterns:
    - "Calibrate the sim-side counter on the first leg before trusting a +0 on the re-send"

key-files:
  created: []
  modified:
    - docs/runbooks/gal-02-handoff.md

key-decisions:
  - "FLOW-04 no-second-POST is a plain PASS: the manager submit counter was calibrated (+1 on the in leg), so the +0 on the in-window re-send is falsifiable evidence, not fallback"

requirements-completed: [FLOW-04]

coverage:
  - id: D1
    description: "Hardware-refusal preflight: sim port 15005 bound to 127.0.0.1 only, Stack manager 0.12.0-beta.1+1157, Configure host 127.0.0.1, only sim-arm-1 idle, manager automated"
    requirement: "FLOW-04"
    verification:
      - kind: manual
        ref: "Findings row 2b-0; read-only re-check of sim.env, ss, GET /api/general/application, Received configuration"
        status: pass
    human_judgment: true
  - id: D2
    description: "GAL-02 run with STACK-PACSIM (real mode, PAC simulator) and FAST-SIM completes note, in leg, FAST transfer, out leg; counter +1 after the in leg, +2 after the run"
    requirement: "FLOW-04"
    verification:
      - kind: manual
        ref: "Findings rows 2b-1, 2b-2 (run_id 156f9e5c3701e7000, queueId 12-15)"
        status: pass
    human_judgment: true
  - id: D3
    description: "In-window re-send replays (replayed true, same stepKey, ledgerState done, same guid, 11 ms, robot idle, counter +0); late re-send refused with 'step key already completed' and 'nothing was sent', counter +0"
    requirement: "FLOW-04"
    verification:
      - kind: manual
        ref: "Findings rows 2b-3, 2b-4"
        status: pass
    human_judgment: true
  - id: D4
    description: "Sim-only ledger holds exactly two done records for the run's keys; pacsim log has 4 Transfer lines and 1 Configure; no ledger file deleted"
    requirement: "FLOW-04"
    verification:
      - kind: manual
        ref: "Findings row 2b-5; python read-only ledger check"
        status: pass
      - kind: automated
        ref: "bin/make proto test (555 passed); tools/tests/gal02_runbook_test.py (15 passed)"
        status: pass
---

# Phase 6 Plan 04: Part 2b PAC Simulator Run Summary

**A GAL-02 run with the real-mode STACK tool against the loopback PAC simulator completed, and a re-send of the completed in leg replayed with the same task guid and no second POST, proven by a manager submit counter that was calibrated first (+1 on the in leg, +0 on the re-send). Findings rows 2b-0..2b-5 are recorded as PASS.**

## What was done

- **Task 1 (operator checkpoint, carried out):** DEP-02 gate printed `DEP-02 OK`. The PAC simulator (manager on `127.0.0.1:15005` only) was built, started and seeded; a real STACK tool server runs on :40012 with sim-only lock and state dirs; tool STACK-PACSIM (id 4) was configured with host 127.0.0.1, port 15005 and the sim-only absolute `ledger_dir`. STACK-SIM on :40010 was stopped first. Re-checked read-only here: gate, sim.env port (not 5005 or 5006), `ss` (127.0.0.1:15005, no wildcard), `GET /api/general/application` (Stack manager, 0.12.0-beta.1+1157), the `Received configuration` block (host "127.0.0.1", port 15005, sim-only ledger_dir), :40010 not listening.
- **Task 2 (operator checkpoint, carried out):** run `156f9e5c3701e7000` completed queueId 12-15. The submit counter read 0 at baseline, +1 after the in leg (calibrated) and 2 after the run. The in-leg re-send inside the 600 s window (04:21:33Z) replied SUCCESS in 11 ms with `replayed` true, the in key, `ledgerState` done and the in-leg guid; counter stayed 2. The late re-send (04:29:40Z) answered ERROR_FROM_TOOL "step key already completed ... nothing was sent"; counter stayed 2. Re-checked read-only: ledger version 1 with exactly two done records matching the reported guids; pacsim log has 4 `Running command Transfer` lines and 1 `Received configuration`.
- **Task 3:** filled Findings rows 2b-0..2b-5 (commit 3f0d3a4). Row verify prints `rows ok`; `bin/make proto test` gives 555 passed; the 15 runbook content tests pass, including the credential check.

## FLOW-04 outcome

PASS. Because the counter moved +1 on the in leg, row 2b-3 is a plain PASS and not "fallback evidence, user to judge". No judgment call is being handed to the user on calibration. The fallback evidence (same guid, immediate reply, robot idle, one ledger record per key) agrees with the counter anyway.

## D-07 split

The no-second-transfer property rests on the 06-01 offline fake-core test plus rows 2b-1 and 2b-3 of this plan. It does not rest on Part 2a (which uses a simulated tool that writes no ledger).

## Deviations from Plan

### Auto-fixed Issues

**1. [Note] PAC checkout not at 26e00251e**
- `~/data/nikko/pac` is on main (0.12.2, d6d9ac5), so the Task 1 precondition `git describe --tags` ending `-g26e00251e` does not hold literally. Commit 26e00251e is present and `scripts/sim_up.sh` builds from `git archive 26e00251e` plus a read-only shared clone (never writes the checkout). Equivalent check used: sim.env `STACK_SIM_PAC_DESCRIBE=0.11.0-1157-g26e00251e`, re-read here.

**2. [Rule 3 - Blocking] Simulator bring-up friction**
- `scripts/sim_up.sh` lacks +x (run with `bash`); the first attempt failed because `STACK_SIM_DIR` did not exist (its df check needs it), so the dir was created. The first account seed answered 400 (wrong admin pair; the right one was read at 26e00251e, `AuthenticationV2ApiController.cs:64`).

**3. [Rule 1 - Bug, sim lab] Transit nests missing after lab seed**
- `check` round 1 answered `reach: unreachable` ("There is no transit nest definition in the all instrument"). The SAL runbook A8 fix was applied in Manual mode (nest 1 sim-A1 and nest 2 sim-B1, approachId 1 DEFAULT PORTRAIT, direction Front, nestMasterId 19), then back to Automated; round 2 `reach: reachable`. No motion was sent. Recorded in row 2b-0. Worth folding into the runbook for the next operator.

**4. [Note] batch_label and fast_tool**
- batch_label stayed at the previous run's GAL02-SIM-20261102 rather than GAL02-PACSIM-yyyymmdd (keys still unique by timestamp and random part), and fast_tool is FAST-SIM, not FAST (same reason as 06-03). The plan's Task 2 automated check filters on the `GAL02-PACSIM-` prefix, so the same assertions were run on the keys ending `-in` and `-out`. Recorded in rows 2b-2 and 2b-5.

**5. [Process] Steps performed by the orchestrator, not the operator**
- At the user's explicit delegation the orchestrator set up Task 1 (simulator, tool server, tool config, seeding; account creation by the user) and sent both re-sends via tRPC `tool.runCommand` (the mutation the tool page uses), with params copied byte-exact from stored queueId 13. The run itself was started by the user in the UI. This executor started, stopped, configured and sent nothing, deleted no ledger file and recorded no credentials or tokens.

## Operator teardown (not run by Claude)

1. Ctrl-C the tool servers (:40011, :40012).
2. `STACK_SIM_DIR=$HOME/.cache/stack-automation-layer/sim bash scripts/sim_up.sh down` (SAL A.10) from the stack-automation-layer checkout.
3. `docker compose -p galago-gal06 -f docker-compose.dev.yml -f "$GAL06_DIR/ports.override.yml" down` from the galago-core checkout.
4. The sim-only ledger `/home/formulatrix/.local/state/galago-tools/stack-sim/stack-ledger.json` stays. Never delete a ledger file.

## Auth gates

None beyond the sim account seeding by the user (documented in row 2b-0).

## Known Stubs

None.

## Threat Flags

None.

## Phase status

With 06-01, 06-02, 06-03 and this plan, all four plans of Phase 6 are done: ROADMAP success criterion 4 holds (operator-run GAL-02 with the STACK tool in real mode against the loopback PAC simulator, on the sim account and sim lab names, with FAST-SIM, completes; a forced re-dispatch sends no second POST with a calibrated counter; nothing targeted 10.150.1.125 or stack-server). Production galago-web :3010 was untouched throughout.

## Self-Check: PASSED

- docs/runbooks/gal-02-handoff.md: FOUND, rows 2b-0..2b-5 end in PASS, 2b-1 states "calibrated"
- commit 3f0d3a4: FOUND
