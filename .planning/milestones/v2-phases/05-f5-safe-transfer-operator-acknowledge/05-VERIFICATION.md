---
phase: 05-f5-safe-transfer-operator-acknowledge
verified: 2026-10-30T06:00:00Z
status: passed
score: 6/6 must-haves verified
covered_files:
  - ".planning/phases/05-f5-safe-transfer-operator-acknowledge/05-01-PLAN.md"
  - ".planning/phases/05-f5-safe-transfer-operator-acknowledge/05-01-SUMMARY.md"
  - ".planning/phases/05-f5-safe-transfer-operator-acknowledge/05-02-PLAN.md"
  - ".planning/phases/05-f5-safe-transfer-operator-acknowledge/05-02-SUMMARY.md"
  - ".planning/phases/05-f5-safe-transfer-operator-acknowledge/05-03-PLAN.md"
  - ".planning/phases/05-f5-safe-transfer-operator-acknowledge/05-03-SUMMARY.md"
  - ".planning/phases/05-f5-safe-transfer-operator-acknowledge/05-04-PLAN.md"
  - ".planning/phases/05-f5-safe-transfer-operator-acknowledge/05-04-SUMMARY.md"
  - ".planning/phases/05-f5-safe-transfer-operator-acknowledge/05-05-PLAN.md"
  - ".planning/phases/05-f5-safe-transfer-operator-acknowledge/05-05-SUMMARY.md"
  - ".planning/phases/05-f5-safe-transfer-operator-acknowledge/05-06-PLAN.md"
  - ".planning/phases/05-f5-safe-transfer-operator-acknowledge/05-06-SUMMARY.md"
  - ".planning/phases/05-f5-safe-transfer-operator-acknowledge/05-07-PLAN.md"
  - ".planning/phases/05-f5-safe-transfer-operator-acknowledge/05-07-SUMMARY.md"
  - "tools/stack/ledger.py"
  - "tools/stack/server.py"
  - "tools/tests/stack_ledger_test.py"
  - "tools/tests/stack_test.py"
covered_digest: "v3:sha256:ba14915e4bf88ece322df69ea53b32c749bb6560bd5a39b04ceab12db47d0e0a"
behavior_unverified: 0
overrides_applied: 1
overrides:
  - must_have: "A restart during a transfer is reported as needing arm inspection, never replayed as SUCCESS"
    reason: "D-09 / 05-SPIKE.md OQ1: a live `ran` that STACK itself reports through wait_transfer after a restart is SUCCESS flagged reattachedAfterRestart (an observation, not a ledger replay). Every other outcome after a restart carries the arm-inspection clause. The strict reading would be a one-line change in _finish."
    accepted_by: "user (D-09 confirmed, recorded in commit 6d365f6 and relayed in the verification request of 2026-10-30)"
    accepted_at: "2026-10-30T00:00:00Z"
coincidental_reliance_items: []
---

# Phase 5: F5-safe Transfer & Operator Acknowledge Verification Report

**Phase Goal:** A workflow step moves a plate through the STACK exactly once per step key, an operator can see and clear a core failure latch from Galago, and re-running, re-dispatching or restarting the tool can never send a second transfer.
**Verified:** 2026-10-30
**Status:** passed
**Re-verification:** No, initial verification

All evidence below was read from the code at HEAD `a4365d6`, not taken from the SUMMARY files. No source file was modified and nothing contacted `10.150.1.125` / `stack-server`.

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria 1-5, plus the proto-freeze carry-over)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC1: `Transfer` runs plan -> execute -> wait in one command, SUCCESS only on `ran`, every other terminal kind is `ERROR_FROM_TOOL` with reason and guid, blank `step_key` is `INVALID_ARGUMENTS` before any core call | VERIFIED | `server.py` `Transfer` -> `_run_fresh` (lines 1060-1209): `plan_transfer`, `ledger.claim`, `execute_transfer`, `mark_started`, one `service.wait`. `_finish` maps via `_transfer_error_reply` (reason, latch clause, `task guid`). `_check_args` (lines 454-460) runs first in `_dispatchCommand` for both modes. Independent probe: fresh = SUCCESS with calls `[plan_transfer, execute_transfer, wait]`; `step_key="  "` = `INVALID_ARGUMENTS "step_key is required"` with zero core calls (probe A1/A4). |
| 2 | SC2: a repeated key never submits (recorded guid re-attaches, recorded `ran` replays, ambiguous submit refuses), different request is `INVALID_ARGUMENTS`, holds after a tool restart (atomic ledger: key + fingerprint, write-ahead `submitting`, guid, outcome) | VERIFIED | `ledger.decide()` (ledger.py 161-193) matches the 05-SPIKE 6b table: mismatch first for every state, `submitting`/`outcomeUnknown` refuse, `started` re-attaches, `done`+`ran` replays only for `0 <= age < 600`. Write path is `fcntl.flock` + strict reload + temp file + `fsync` + `os.replace` + dir fsync (ledger.py 444-513); load is fail closed. Probe: A2 rerun replays (execute count stays 1), A3 mismatch `INVALID_ARGUMENTS` with no core call, A5 new `StackServer` on the same dir replays with zero calls, B2/B3 timedOut -> `wait_transfer` -> ran -> replay (execute count 1), D1-D3 raise after write-ahead is refused on rerun and after a restart (zero calls), E1/E2 `submitOutcomeUnknown` records `latchGuid` and refuses. `TestNeverResends` (12 scenarios incl. restart while started/submitting/done) passes. |
| 2b | SC2 last sentence: a restart during a transfer is reported as needing arm inspection, never replayed as SUCCESS | PASSED (override) | Restart on `submitting` is refused with the restart clause (probe D3). Restart on `started`: a non-`ran` outcome gets the restart clause (probe C2: `...the core did not latch this; inspect the arm...`), but a live `ran` observed through `wait_transfer` is SUCCESS flagged `reattachedAfterRestart` (probe C1; `_finish` line 1274-1275). That is the user-confirmed D-09 decision (commit 6d365f6), recorded in 05-SPIKE OQ1. Override carried in frontmatter. |
| 3 | SC3: `refused`/`rejected`/`needsInput`/`readFailed` release the key; `TimedOut` leaves the arm running as an error and a re-run re-attaches and finishes it | VERIFIED | `_RELEASE_TYPES = (Refused, Rejected, NeedsInput, ReadFailed)` matched by `isinstance` (line 228, `_run_fresh` 1199-1200); `Ledger.release` deletes only a `submitting` record (WR-04 fix). Unknown objects and non-whitelisted `Lost` go to `_keep_unknown` (outcomeUnknown, never deleted). Probe F1/F2: Rejected(instrument, 500) releases, re-run executes again (accepted WR-06 residual, XFR-04 as written). Probe B1/B2: timedOut is `ERROR_FROM_TOOL ... re-run this step to re-attach`, re-run calls only `wait_transfer` (read-only loop, `_reattach_loop`, never `remaining <= 0`) and finishes to ran. `TestKeyRelease`, `TestTimedOutReattach` pass. |
| 4 | SC4: AST invariant with planted violations fails if the adapter calls `start_transfer`/`cancel_transfer`/`go_to_safe_position` or calls `execute_transfer` more than once per key | VERIFIED | `stack_test.py` `_stack_adapter_violations` (1259-1379): forbidden calls, exactly one `execute_transfer` and one `plan_transfer` site inside `_run_fresh`, no loop/comprehension/lambda ancestor, after a claim that is assigned and gated by `if not <name>: return` (`_claim_gates`), `getattr` and uncalled-attribute escapes reported. `TestAdapterInvariant` plants violations for each rule and they pass. grep of `tools/stack/server.py` shows a single call site each for `plan_transfer` (1179), `execute_transfer` (1193), `acknowledge_failure` (1324), and no `start_transfer`/`cancel_transfer`/`go_to_safe_position` anywhere. |
| 5 | SC5: operator sees the latched guid (error message and `GetFailureLatch` 1:1 with `latch_status()`, `latchStatus` in `_SUCCESS_KINDS`, `submit-` and `state-` cases) and clears it with `AcknowledgeFailure(guid, arm_inspected)`; only exact `"yes"` reaches `acknowledge_failure(guid, confirm=True)`, no adapter path acknowledges on its own | VERIFIED | `GetFailureLatch` (1328-1330) returns `_result_reply(latch_status())`; `latchStatus` is in `_SUCCESS_KINDS` (line 302); it is in `READ_COMMANDS`, so it answers while BUSY. `_latch_clause` / `_transfer_error_reply` name `latch_status().guid` first and label the result guid "task guid" (A-2); probe E1 shows `latched guid submit-abcdef0123456789 (lost); inspect the arm, then AcknowledgeFailure`. `AcknowledgeFailure` (1310-1326): exact `!= "yes"` -> `INVALID_ARGUMENTS`, then one call `acknowledge_failure(guid.strip(), confirm=True)` under `_MOTION_LOCK`. Probe: `yes` reaches the core once; `Yes`, `yes `, `y`, empty, `no`, `YES` are `INVALID_ARGUMENTS` with zero core calls. It never touches the ledger (`TestAcknowledgeLeavesTheLedgerAlone`); `TestNeverResends` asserts no acknowledge in any scenario. |
| 6 | Carry-over: STK-05 re-proven on the real `Transfer` (reads, including `GetFailureLatch`, answer while a Transfer is in flight; second Transfer refused); `stack.proto` frozen | VERIFIED | `TestBusyReads` (real Transfer parked mid-wait), `TestMotionLock`, `TestProtoFreeze` pass. `git diff 9134f74~1 HEAD` outside `.planning` touches only `tools/stack/ledger.py`, `server.py`, and the two test files, so no proto or `Config` field changed. |

**Score:** 6/6 truths verified (SC2b carried as PASSED (override)); 0 present-but-behavior-unverified. Every behavior-dependent truth (restart, re-attach, cleanup/release, never-resend) has a passing behavioral test that I re-ran and an independent probe of my own.

### Review-fix commits (9d6bc4d..1de1590) re-checked in code

| Fix | Status | Evidence |
|-----|--------|----------|
| CR-01 `ledger_dir` pinned once a Transfer used it; settings applied only in `_commit_settings` | VERIFIED | `_commit_settings` (914-937) refuses a differing resolved dir with `_ConfigureRefused` under `_state`; `Transfer` pins under the same lock (1091-1095). `TestLedgerDirPinned` passes. |
| WR-01 pin kept whenever a ledger file exists or a claim returned; untrusted file keeps the pin | VERIFIED | `Transfer` 1097-1106 and `_run_fresh` 1189; finally restores the previous pin only when no record can exist. |
| WR-01 (iter 1) `AcknowledgeFailure` under `_MOTION_LOCK`, `setStatus` never READY while locked | VERIFIED | lines 823-824 and 1321-1326; `TestAcknowledgeDuringTransfer`. |
| WR-04 ledger enforces its own transitions | VERIFIED | `_existing(..., *allowed)` in ledger.py 431-442; release only from `submitting`. |
| WR-05 claim-False guard tested and covered by the AST rule | VERIFIED | `TestClaimedElsewhere`, `_claim_gates`. |
| WR-06 typed 5xx releases the key | ACCEPTED residual | Not a gap: XFR-04 as written, user-accepted, recorded in 05-SPIKE OQ2 and 05-REVIEW-DISPOSITION. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tools/stack/ledger.py` (513 lines) | Atomic strict ledger, `decide()`, release/outcomeUnknown/retention | VERIFIED | Substantive and wired (imported by `server.py`: `Ledger`, `decide`, `fingerprint`, `is_terminal`, `resolve_ledger_dir`); stdlib only. |
| `tools/stack/server.py` (1372 lines) | `Transfer`, `AcknowledgeFailure`, `GetFailureLatch`, reply mapping | VERIFIED | All handlers real, no stubs, `COMMAND_TO_SERVICE_METHOD` wired. |
| `tools/tests/stack_ledger_test.py` | Pure ledger contract tests | VERIFIED | Runs without the core. |
| `tools/tests/stack_test.py` | Fake-core behavioral matrix, AST invariant | VERIFIED | 363 passed together with the ledger tests in the pinned venv. |
| `05-SPIKE.md` | Binding contract, A-1..A-6 | VERIFIED | Implementation matches 6a-6f (constants `REPLAY_WINDOW_S=600`, `RETENTION_DONE_S`, `LOCK_TIMEOUT_S=5`, 300 s slices, templates). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `Transfer` | `decide()` | `decide(existing, fingerprint=fp, instance=self._instance, now=...)` | WIRED | line 1107; each action routed to `_run_fresh` / replay / `_reattach` / `_ledger_reply`. |
| `_run_fresh` | `Ledger.claim` -> `execute_transfer` | `claimed` gated by `if not claimed: return` | WIRED | lines 1183-1193; enforced by the AST invariant. |
| `_finish` | `Ledger.mark_done` | only when `is_terminal(d)` (A-1) | WIRED | timedOut / lost(pollFailed) stay `started`. |
| `AcknowledgeFailure` | `service.acknowledge_failure(..., confirm=True)` | after exact `"yes"` and the motion lock | WIRED | single call site. |
| `GetFailureLatch` | `latch_status()` | `_result_reply` (1:1) | WIRED | kind `latchStatus` is SUCCESS. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| Transfer reply | `result` / `outcome` | the core's `wait` / `execute_transfer` results (real result classes) | Yes | FLOWING |
| Repeat-key decision | `existing` | `Ledger.get(key)` strict file read | Yes | FLOWING |
| Latch guid in messages | `latch_status()` | the core, zero I/O | Yes | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Phase test files | `~/data/nikko/.venvs/galago-py310/bin/python -m pytest tools/tests/stack_test.py tools/tests/stack_ledger_test.py -q` | 363 passed | PASS |
| Full gate (orchestrator-reported) | `bin/make proto test` | 510 passed | PASS (not re-run by me) |
| Never-resend scenarios against the real `StackServer` handlers with a fake core (own script, not the repo tests) | scratchpad `probe.py` | rerun/replay/mismatch/restart/raise/outcomeUnknown/ack matrix as in the truth table | PASS |

### Probe Execution

Step 7c: SKIPPED. The phase declares no `probe-*.sh`; all verification is pytest against a fake core and no motion.

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|----------------|-------------|--------|----------|
| XFR-01 | 05-02, 05-05, 05-07 | plan -> execute -> wait in one command | SATISFIED | SC1 |
| XFR-02 | 05-02, 05-03, 05-05 | non-blank key, atomic write-ahead ledger | SATISFIED | SC1/SC2; ledger.py atomic write, `claim` before `execute_transfer` |
| XFR-03 | 05-01, 05-03, 05-06, 05-07 | repeated key never submits; restart reported | SATISFIED | SC2 (restart wording: override, D-09) |
| XFR-04 | 05-01, 05-03, 05-05 | nothing-sent outcomes release the key | SATISFIED | SC3; WR-06 residual accepted |
| XFR-05 | 05-02, 05-04, 05-07 | AST invariant, no motion retry | SATISFIED | SC4 |
| XFR-06 | 05-06 | timedOut is an error, re-run re-attaches | SATISFIED | SC3 |
| ACK-01 | 05-04, 05-07 | exact "yes" only, operator-only | SATISFIED | SC5 |
| ACK-02 | 05-01, 05-04, 05-05 | latched guid visible in message and `GetFailureLatch` | SATISFIED | SC5 |

All eight IDs appear in at least one PLAN `requirements:` field and in REQUIREMENTS.md; REQUIREMENTS.md maps no other ID to Phase 5, so there are no orphans.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (all `tools/stack/*.py`) | - | `TODO|FIXME|XXX|TBD|HACK` grep | none | No debt markers. |
| `tools/stack/server.py` | 1199-1202, 1257-1281 | A non-core object from `execute_transfer` whose `to_dict()` kind is `ran` replies SUCCESS (with a "will not be re-sent" message) while the record is `outcomeUnknown` (my probe2) | Info | Unreachable with the real core (it never returns a `Ran` from `execute_transfer`) and it can never cause a second send. A reply-mapping hardening, not a safety gap. |
| `tools/stack/server.py` | various | Review items IN-01 (AST never-in-a-loop check is intra-function), IN-02 (exception after a handle becomes `DRIVER_ERROR` without guid), IN-03 (`Path.home()` RuntimeError), IN-04 (`_fsync_dir` swallows errors) | Info | Left open by the review; none lets a second transfer be sent (the claim gate and write-ahead record still hold). |

### Human Verification Required

None for the phase goal. The phase is entirely fake-core by design; live motion is Phase 7.

### Carry-forward for Phase 7 (not gaps in this phase)

1. Production `Config.ledger_dir` must be an explicit absolute path. The pin lasts one process, and a restart under a different `HOME`/`XDG_STATE_HOME` resolves a different default directory and so an empty ledger.
2. A typed 5xx or `stackBusy` on the submit POST releases the key (WR-06 / OQ2, accepted); a re-run is stopped only by the core's gates.
3. The orphaned core in-flight guard (A-3) and "never delete or fail to back up the ledger directory" go in the runbook.
4. galago-core's command deadline versus the 300 s default budget (OQ4) is unconfirmed until the live acceptance.
5. `05-VALIDATION.md` is still `status: draft` (`nyquist_compliant: false`); run validation if that sign-off is wanted.

### Gaps Summary

No gaps. Every ROADMAP success criterion is backed by code I read, tests I re-ran, and an independent probe of the real `StackServer` handlers. The one literal deviation (SC2's last sentence versus D-09) is a user-confirmed decision recorded in the repository and carried as an override.

---

_Verified: 2026-10-30_
_Verifier: Claude (gsd-verifier)_
