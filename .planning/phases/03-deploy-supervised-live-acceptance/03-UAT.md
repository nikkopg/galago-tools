---
status: testing
phase: 03-deploy-supervised-live-acceptance
source: [03-VERIFICATION.md]
started: 2026-10-16T05:45:00Z
updated: 2026-10-16T05:45:00Z
---

## Current Test

number: 1
name: Decide redeploy/rerun of LIVE-07 for the undeployed CR-01 fix
expected: |
  A recorded decision: either (a) redeploy forb01 with 134e097/7c2e15a in the safe order and rerun
  LIVE-07 live, recording the rerun in 03-ACCEPTANCE.md as a D-14-style entry, or (b) accept that the
  deployed, already-accepted adapter (201d987) stays the production baseline and the CR-01 fix ships
  with a later deploy, with that acceptance recorded durably.
awaiting: user response

## Tests

### 1. Decide redeploy/rerun of LIVE-07 for the undeployed CR-01 fix
expected: forb01 runs adapter 201d987; CR-01 (134e097/7c2e15a) changed the crash-recovery Resume path that LIVE-07 exercises and was never deployed or run on the instrument. Either redeploy and rerun LIVE-07 live, or record explicit acceptance of the 201d987 baseline.
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
