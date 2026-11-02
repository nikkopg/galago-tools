---
phase: 06-gal-02-workflow-simulated-workcell-pac-simulator-run
plan: 03
subsystem: testing
tags: [runbook, galago-core-dev, simulated-run, stack-redispatch, findings-log]

requires:
  - phase: 06-gal-02-workflow-simulated-workcell-pac-simulator-run
    provides: "06-01 protocol JSON and offline re-dispatch proof; 06-02 runbook, DEP-02 gate, Findings log"
provides:
  - Findings rows G0, 2a-1, 2a-2, 2a-3 in docs/runbooks/gal-02-handoff.md, all PASS
  - Evidence that the imported script protocol runs end to end through galago-core's real queue with STACK-SIM and a simulated F.A.S.T.
  - Evidence that a simulated re-dispatch of the completed in-leg STACK step returns SUCCESS and writes no ledger
affects: [06-04 PAC-sim run, 07 hardware deploy]

status: complete
plan_head_before: eee72108e186ec23d4ee4329fd761fa19ca6f9f2
plan_head_after: 5d8fe74

actuals:
  tokens: 5200
  tasks: 3
  commits: 1

tech-stack:
  added: []
  patterns:
    - "Findings rows carry deviations inline (tool name, who sent the re-dispatch) so the log is honest about what was actually done"

key-files:
  created: []
  modified:
    - docs/runbooks/gal-02-handoff.md

key-decisions:
  - "Row 2a-3 credits the simulated re-dispatch with only the D-07 claim: the stored step survives a re-dispatch through the real queue path and simulated mode writes no ledger; the no-second-transfer property is carried by the offline fake-core test (06-01) and the Part 2b run (FLOW-04)"

requirements-completed: [FLOW-02, FLOW-03]

coverage:
  - id: D1
    description: "DEP-02 gate OK, dev galago-core on :3020, two simulated tool servers, protocol imported as mode script with a non-empty script and 4-row preview"
    requirement: "FLOW-02"
    verification:
      - kind: manual
        ref: "Findings rows G0 and 2a-1 (gate output, GET /api/protocols, ss, tee'd logs, vitest 5/5)"
        status: pass
    human_judgment: true
  - id: D2
    description: "One Galago-simulated GAL-02 run completes note, STACK in, FAST-SIM transfer, STACK out in order, with -in/-out keys on one base"
    requirement: "FLOW-02"
    verification:
      - kind: manual
        ref: "Findings row 2a-2 (run_id 156f910fe281e7000, queueId 8-11 COMPLETED)"
        status: pass
    human_judgment: true
  - id: D3
    description: "Simulated re-dispatch of the completed in-leg step returns SUCCESS with no meta, no stack-ledger.json anywhere, 3 Transfer log lines in the STACK-SIM log"
    requirement: "FLOW-03"
    verification:
      - kind: manual
        ref: "Findings row 2a-3; python read-only check 'sim ok 3 1'"
        status: pass
    human_judgment: true
---

# Phase 6 Plan 03: Part 2a Simulated Run Summary

**A Galago-simulated GAL-02 run completed all four rows through galago-core's real queue, and a simulated re-dispatch of the in-leg STACK step returned SUCCESS without writing a ledger. Findings rows G0, 2a-1, 2a-2 and 2a-3 are recorded as PASS.**

## What was done

- **Task 1 (operator checkpoint, carried out):** DEP-02 gate printed `DEP-02 OK`; galago-core `commandFields.test.ts` passes 5/5 under vitest; dev galago-core (compose project galago-gal06, UI :3020) up, production :3010 untouched; STACK-SIM on :40010 and F.A.S.T. on :40011 both configured simulated; protocol imported via `POST /api/protocols` as id 2, mode script, 3028-char script, 4-row preview. Re-checked read-only here: gate, `ss`, `GET /api/protocols`, logs.
- **Task 2 (operator checkpoint, carried out):** run `156f910fe281e7000` (batch GAL02-SIM-20261102, numberOfRuns 1) completed queueId 8-11 in order; in-leg key `...-0cb7fd09-in`, out-leg key `...-0cb7fd09-out`. A forced re-dispatch of the in-leg returned `SUCCESS`, no meta. The STACK-SIM log has exactly 3 `Running command Transfer` lines, the F.A.S.T. log 1, and `/home/formulatrix/.local/state/galago-tools` does not exist, so no `stack-ledger.json` was written (STK-06).
- **Task 3:** filled the four Findings rows (commit 5d8fe74). `bin/make proto test` gives 555 passed; the 15 runbook content tests still pass.

## D-07 statement

The simulated re-dispatch does not prove that no second transfer is sent; that is proven by the offline fake-core test (06-01) and the Part 2b run (FLOW-04). What this run shows is that the stored in-leg step survives a re-dispatch through the real queue path, and that simulated mode writes no ledger.

FLOW-02: PASS. FLOW-03 simulated half: PASS (credited per D-07 only).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Simulated F.A.S.T. tool named FAST-SIM, not FAST**
- **Found during:** Task 1
- **Issue:** the dev DB already holds a real tool `Fast` (id 1, fa100056.local); galago-core matches tool names case-insensitively (`server/toolKey.ts` normalizeToolKey), so `FAST` would resolve to the old record.
- **Fix:** created `FAST-SIM` (id 3, port 40011) and ran with `fast_tool=FAST-SIM`. Recorded in row 2a-1.

**2. [Rule 3 - Blocking] F.A.S.T. log name**
- **Issue:** the plan's Task 2 verify names `gal02-fast-sim.log`; the runbook (and the operator) use `gal02-fast.log`.
- **Fix:** counted in `gal02-fast.log` (1 Transfer line). Recorded in row 2a-2.

**3. [Process] Re-dispatch not sent by the operator from the tool page**
- **Issue:** the plan expects the operator to re-send from the STACK-SIM tool page. At the user's explicit delegation the orchestrator re-sent it via tRPC `tool.runCommand` (the same mutation the tool page uses), params copied byte-exact from stored queueId 9. Operator-delegated setup and run steps (Tasks 1 and 2) were likewise performed by the orchestrator, not by this executor. Recorded in row 2a-3.

**4. [Note] Config keys are snake_case**
- A camelCase `ledgerDir` first attempt silently dropped `ledger_dir`; re-sent as `ledger_dir` and confirmed in the STACK log. Recorded in row 2a-1.

**5. [Note] galago-core HEAD moved**
- The gate printed galago-core HEAD a5fa75f during setup and 0a7ee5a on the re-check; the intervening commits are docs-only (`git diff a5fa75f HEAD -- controller` is empty). Recorded in row G0.

## Auth gates

None.

## Known Stubs

None.

## Upstream follow-up (unchanged)

The Protocols-page Import button was not tried, so the galago-core defect (`ProtocolPageComponent.tsx:137-146` drops `mode` and `scriptContent`) was not re-observed in this plan.

## Next step

STACK-SIM (:40010) was configured simulated and must be stopped (Ctrl-C) before Part 2b; Part 2b uses a separate process on :40012 (D-16b, T-06-14).

## Self-Check: PASSED

- docs/runbooks/gal-02-handoff.md: FOUND, rows G0/2a-1/2a-2/2a-3 end in PASS, 2a-3 holds the D-07 phrase
- commit 5d8fe74: FOUND
