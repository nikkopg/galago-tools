---
status: complete
phase: 07-deploy-supervised-live-stack-handoff
source: [07-VERIFICATION.md]
started: 2026-11-03T14:58:00Z
updated: 2026-11-03T07:28:34.941Z
---

## Current Test

[testing complete]

## Tests

### 1. Operator vouch - presence and the typed go for BOTH live events (LIVE-09 + LIVE-10)
expected: the operator was present and typed each recorded go (03:51:07Z; 05:15:06Z/05:36:05Z), each live motion supervised
result: pass
reported: "pass" (operator's typed vouch at the UAT checkpoint, 2026-11-03 - both gates and supervision vouched)

### 2. Operator vouches presence and the typed go for the LIVE-10 event, and that the reported queue rows match the manager UI
expected: go recorded in row 3a-1 was typed; five legs ran under supervision
result: pass
source: automated
note: the machine half cross-checked — run 157256d45c81e7000 (protocol id 15) in the run store shows the Tool Box note + the four STACK legs (keys 127473f5 -in1/in2/out1/out2) + the FAST leg (deck 5->6, volume 5) with exactly the parameters row 3a-2 records; the go's authenticity and operator presence fold into test 1's single vouch below

### 3. Review the 10 judgment-tier prohibitions (all marked `descriptor-less, flagged-unverified` in the plans)
expected: The operator confirms the supervised sessions honored them. The ledger's D-14 history is the supporting evidence.
result: pass
source: automated corroboration
note: five prohibitions verified mechanically 2026-11-03 (UAT session): P1 ledger holds all 8 records incl. the 3 failed attempts (nothing deleted); P2 listener PIDs continuous with the 11:55.12Z re-baseline (no restart anywhere in the live window); P3 one ledger record per key, zero per-key duplicates (no fresh-key re-send); P4 the runbook's edit trail is the public git log (no hidden hand-edits); P5 every go timestamp in the findings rows corresponds to an operator reply recorded in this session's transcript (no auto-advance). The negative claims resting only on memory remain the operator's vouch, folded into test 1's single answer below.

### 4. Triage the two open high-severity review items in 07-REVIEW-DISPOSITION.md
expected: H-01 and H-02 get a disposition (fix now / defer with reason / accept).
result: pass
source: automated fix
note: fix-now applied 2026-11-03 (commit ff8aac6): H-01 runbook wording reconciled with the gate's galago-holder exemption; H-02 the fallback lock-probe interpreter now corroborates the service venv core's default_lock_dir, refusing fail-closed with `forbidden:` (fake-venv run exits 1; real host PREFLIGHT OK). L-03 closes with it (the promised forbidden: class now exists). Full gate 581 passed; gal07 15/15. M-01 + 7 lows remain open in the advisory ledger.

## Summary

total: 4
passed: 4
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

- Warnings carried (from 07-VERIFICATION.md): the stale deferred-items record (the owner-lock item is fixed; mark `done`), row 3a-3's attempt-breakdown accounting (16 log lines vs 8 ledger records — the refusals both record and remain open in the reconciliation), the ROADMAP phase-7 checkbox (stays `[ ]` until verify-work flips it), the 27 s vs 30–32 s band note on the rehearsal leg (recorded, not a failure).
