---
status: complete
phase: 06-gal-02-workflow-simulated-workcell-pac-simulator-run
source: [06-VERIFICATION.md]
started: 2026-11-02T07:20:00Z
updated: 2026-11-02T07:52:32.080Z
---

## Current Test

[testing complete]

## Tests

### 1. Tool-page re-send of a completed in-leg with blank optional fields replays
expected: SUCCESS, replayed true, same task guid, submit counter +0 (needs a fresh GAL-02 run on STACK-PACSIM; the 156f9e5c3701e7000 window has passed). Fill step_key (byte-exact) and the required fields from the run's stored row; leave only the optionals blank.
result: pass
note: "2026-11-02, driven by the orchestrator at the user's request in the user's Chrome on the real dev-galago tool page (http://10.150.1.138:3020/tools/STACK-PACSIM, Select Command = Transfer, Send Command). Run 156ffd71ed81e7000 (protocol id 3, post-review script, batch GAL02-UAT-20261102, started by the user): in-leg GAL02-UAT-20261102-2026-11-02T07:46:27.930Z-89ad781f-in completed 07:46:59Z with one submit (POST /api/v2/transfer at 07:46:38Z). Form filled with step_key byte-exact plus robot/labware_profile/source/destination device-deck-nest; source_transfer_profile, destination_transfer_profile, timeout_s left blank. galago-core sent the params WITHOUT the three blank optionals (they were omitted, not '' or 0). Sent 07:51:05Z (4 min 06 s after the in-leg completed): reply SUCCESS in the same second, page meta {replayed: true, stepKey: <in key>, ledgerState: ...}; ledger record for the key is done with guid 23b8ad43-4d4f-4e0f-9f82-5c6bea692128 (the in-leg's own task guid, present in the in-leg's polling in gal02-stack-pacsim-uat.log); submit counter 1 -> 1 (+0); robot sim-arm-1 idle. Side observation (not part of this test): the run's out-leg (queueId 19) FAILED at 07:48:22Z in galago-core with 'Tool STACK-PACSIM not found in store. Must be configured first.' before reaching the tool (no second submit, no tool log entry), right after STACK-SIM had been reconfigured in real mode against the stopped :40010 at 07:44:34Z - a dev-galago tool-store state issue, recorded as a Phase 7 watch item.

### 2. Re-imported protocol previews in galago-core's real executor after the WR-01/WR-02 script change
expected: Import the current docs/runbooks/gal-02-handoff.protocol.json via POST /api/protocols into a dev Galago; Preview with defaults (stack_tool and fast_tool set to distinct workcell tools) shows 4 rows with no error; Preview with one bad F.A.S.T. value (e.g. fast_step_num_rows=0) and with stack_tool equal to fast_tool up to case shows the script error and 0 rows.
result: pass
note: "2026-11-02, run by the orchestrator at the user's request through the same tRPC protocol.preview the UI's Preview calls, on the script text galago-core stored. Imported via POST /api/protocols as id 3 'GAL-02 STACK to F.A.S.T. handoff (post-review)' (mode script, 27 params, 4774-char script, byte-equal to the repo JSON). Defaults (stack_tool STACK-PACSIM, fast_tool FAST-SIM) -> success, 4 rows: Tool Box/note, STACK-PACSIM/transfer, FAST-SIM/transfer, STACK-PACSIM/transfer. fast_step_num_rows=0 -> error 'GAL-02: parameter fast_step_num_rows must be a whole number from 1 to 2147483647', 0 rows. stack_tool FAST-SIM vs fast_tool fast-sim -> error 'GAL-02: parameter fast_tool must differ from stack_tool', 0 rows."

## Summary

total: 2
passed: 2
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps
