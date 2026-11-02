---
status: testing
phase: 06-gal-02-workflow-simulated-workcell-pac-simulator-run
source: [06-VERIFICATION.md]
started: 2026-11-02T07:20:00Z
updated: 2026-11-02T09:00:00Z
---

## Current Test

number: 1
name: Tool-page re-send of a completed in-leg with blank optional fields replays
expected: |
  The STACK-PACSIM tool-page transfer form delivers the blank optionals (source_transfer_profile,
  destination_transfer_profile, timeout_s) as unset (absent, empty string, or timeout_s 0). Re-sending the
  in-leg with the stored step_key inside the 600 s replay window replies SUCCESS with replayed true and the
  same task guid, not a fingerprint-mismatch refusal. The manager submit counter
  (~/data/nikko/.venvs/gal06/count-submits.sh) stays unchanged.
awaiting: user response

## Tests

### 1. Tool-page re-send of a completed in-leg with blank optional fields replays
expected: SUCCESS, replayed true, same task guid, submit counter +0 (needs a fresh GAL-02 run on STACK-PACSIM; the 156f9e5c3701e7000 window has passed). Fill step_key (byte-exact) and the required fields from the run's stored row; leave only the optionals blank.
result: [pending]

### 2. Re-imported protocol previews in galago-core's real executor after the WR-01/WR-02 script change
expected: Import the current docs/runbooks/gal-02-handoff.protocol.json via POST /api/protocols into a dev Galago; Preview with defaults (stack_tool and fast_tool set to distinct workcell tools) shows 4 rows with no error; Preview with one bad F.A.S.T. value (e.g. fast_step_num_rows=0) and with stack_tool equal to fast_tool up to case shows the script error and 0 rows.
result: [pending]

## Summary

total: 2
passed: 0
issues: 0
pending: 2
skipped: 0
blocked: 0

## Gaps
