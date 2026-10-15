---
phase: 01-adapter-control-path-run-state
verified: 2026-10-15T13:08:03Z
status: passed
score: 5/5 must-haves verified
covered_files: [".planning/phases/01-adapter-control-path-run-state/01-01-PLAN.md", ".planning/phases/01-adapter-control-path-run-state/01-01-SUMMARY.md", ".planning/phases/01-adapter-control-path-run-state/01-02-PLAN.md", ".planning/phases/01-adapter-control-path-run-state/01-02-SUMMARY.md", ".planning/phases/01-adapter-control-path-run-state/01-03-PLAN.md", ".planning/phases/01-adapter-control-path-run-state/01-03-SUMMARY.md", ".planning/phases/01-adapter-control-path-run-state/01-04-PLAN.md", ".planning/phases/01-adapter-control-path-run-state/01-04-SUMMARY.md", ".planning/phases/01-adapter-control-path-run-state/01-05-PLAN.md", ".planning/phases/01-adapter-control-path-run-state/01-05-SUMMARY.md", "interfaces/tools/grpc_interfaces/fast.proto", "interfaces/tools/grpc_interfaces/tool_base.proto", "tools/fast/server.py", "tools/tests/fast_test.py"]
covered_digest: "v3:sha256:e8aa50d67fea268f79bad770ffbd6d7e696afdc0a211cb45418161e781dcbf10"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: passed
  previous_score: 5/5
  gaps_closed: []
  gaps_remaining: []
  regressions: []
advisory:
  - finding: "Resume()'s crash-recovery acceptance gate (tools/fast/server.py:937) checks `accepted.get(\"errorCode\") != 0` directly instead of the module's own fail-closed `_accepted()` helper, so a non-int, zero-equivalent errorCode (e.g. `False`) is misclassified as accepted and the call proceeds to `service.wait(...)` (holding `_motion_lock`) instead of returning immediately through `_recovery_reply`. Reproduced live: mocking `service.resume.return_value = {\"errorCode\": False}` with the motion lock free causes `service.wait` to be invoked."
    category: architectural
    reason: "Flagged as WR-01 in the fresh 01-REVIEW.md (2026-10-15, disposition: open in 01-REVIEW-DISPOSITION.md). Not a regression introduced during Phases 2-3: this exact inline check was the pre-existing crash-recovery body that Plan 01-01 Task 3 explicitly instructed to 'keep today's body exactly' (the module's _accepted() fail-closed helper was added later by Phase 2's own WR-01 fix, d9acdcf, which patched _recovery_reply's SUCCESS mapping and Abort() but never retrofitted this duplicate inline check). No ROADMAP success criterion or PLAN must_haves truth for Phase 1 specifies errorCode type-strictness on the crash-recovery path specifically (01-02-PLAN's D-07 truths scope that guarantee to 'the in-flight path' only) — so no stated phase-1 must-have is violated. Per explicit instruction for this re-verification pass, a code-review finding does not by itself fail the phase; recorded here for visibility and already tracked in 01-REVIEW-DISPOSITION.md."
    evidence_status: "reproduced (see Behavioral Spot-Checks) — not a Phase-1 must-have, so not counted as a gap"
---

# Phase 1: Adapter Control Path & Run State Verification Report

**Phase Goal:** An operator's Pause, Resume or Abort reaches the instrument while the step's
Transfer is still running, the tool reports live run state for galago-core to poll, and tests
prove no code path acts without the operator.

**Verified:** 2026-10-15T13:08:03Z
**Status:** passed
**Re-verification:** Yes — covered source files (`tools/fast/server.py`, `tools/tests/fast_test.py`,
both protos) changed during Phases 2-3 after the 2026-10-13 verification; this pass re-checks all
five ROADMAP success criteria and all 10 ADP requirements against the current code, not the
previous report.

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A real-mode test sends Pause, Resume and Abort through `ExecuteCommand` while a `Transfer` is blocked: each reaches the (mocked) service, the tool's status is still BUSY afterwards, and `tools/base_server.py` is unchanged | ✓ VERIFIED | Re-ran directly: `python -m unittest tools.tests.fast_test.TestControlCommandsOverGrpc.test_pause_resume_abort_reach_service_while_transfer_in_flight -v` → `OK`. `git diff --exit-code 9c27896 -- tools/base_server.py` exits 0 (still byte-identical). |
| 2 | `GetStatus` returns `run_state` with state, percent and pause info for the F.A.S.T., other tool types return it unset, and the proto change regenerates cleanly for Python | ✓ VERIFIED | `interfaces/tools/grpc_interfaces/tool_base.proto:135` still has `optional google.protobuf.Struct run_state = 4;`; `tools/fast/server.py::_build_run_state`/`GetStatus` (lines 638-804) fill it via `reply.run_state.update(...)`; full gate (`bash bin/make proto test`, which regenerates protos) re-ran green with `TestRunStateOverGrpc`, `TestRunState.test_other_tool_types_leave_run_state_unset` passing. |
| 3 | Blank or unclear decisions are `INVALID_ARGUMENTS` on every path, Pause is always soft, and Resume returns on acceptance with a run in flight but waits when there is none | ✓ VERIFIED | Re-ran `TestRecoveryCommands`, `TestControlCommandsBypassMotionLock` (10 tests) directly: `OK`. `Pause()` still calls `service.pause(hard=False)` (line 868). Resume's two branches (lock acquired = crash-recovery wait, lock not acquired = in-flight no-wait) are both present and green, including `test_resume_with_a_run_in_flight_returns_on_acceptance_without_waiting` and `test_crash_recovery_resume_waits_and_holds_the_lock`. |
| 4 | The extended no-auto-abort invariant fails on a planted violation, and no instrument-state check exists in the adapter | ✓ VERIFIED | `_adapter_invariant_violations` run directly against the current `tools/fast/server.py` returns `[]`; `TestAdapterInvariant` (6 tests, including two new ones added in Phase 2 for `operator_abort`/`through_pauses` bookkeeping) re-ran green. |
| 5 | In simulated mode, control commands return SUCCESS after argument checks and a test hook drives `run_state` to paused | ✓ VERIFIED | `TestSimulatedTransferOverGrpc`, `TestSimulatePauseHook` re-ran directly: `OK`. `simulate_pause` still absent from `fast.proto`'s oneof (not a gRPC command). |

**Score:** 5/5 ROADMAP success criteria verified (0 present-but-behavior-unverified)

### Changes Since the 2026-10-13 Verification (Phases 2-3 impact on Phase-1 scope)

`tools/fast/server.py` and `tools/tests/fast_test.py` grew substantially during Phases 2-3:
operator-abort wording (`operator_abort`, `_accepted()`), `through_pauses` wait wiring, a
`WR-01` fail-closed errorCode helper, and `NoError (0)` wording fixes. None of these changes
touched the Phase-1 symbols (`ExecuteCommand` override, `CONTROL_COMMANDS`,
`MOTION_LOCK_COMMANDS`, `_build_run_state`, `_adapter_invariant_violations`'s scoped-attrs
tables) in a way that breaks any Phase-1 must-have — confirmed by re-running every Phase-1 test
class directly against the current file (70 tests across `TestControlCommandsOverGrpc`,
`TestControlCommandsBypassMotionLock`, `TestRecoveryCommands`, `TestRunState`,
`TestRunStateOverGrpc`, `TestAdapterInvariant`, `TestSimulatePauseHook`,
`TestSimulatedTransferOverGrpc` — all `OK`), not merely re-reading the old report.

One new-scope finding surfaced by the fresh code review and independently reproduced during this
pass (`WR-01`, Resume's crash-recovery acceptance gate) is recorded in the `advisory:`
frontmatter above — it does not fail any stated Phase-1 must-have (see reasoning there) and is
already tracked as an open code-review item in `01-REVIEW-DISPOSITION.md`.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `interfaces/tools/grpc_interfaces/fast.proto` | `Pause {}` message, oneof field `pause = 10` | ✓ VERIFIED | `grep` confirms both lines present |
| `interfaces/tools/grpc_interfaces/tool_base.proto` | `StatusReply.run_state = 4` (optional Struct) | ✓ VERIFIED | Present at line 135, regenerates cleanly via `bin/make proto` |
| `tools/fast/server.py` | `ExecuteCommand` override, `Pause`/`Abort`/`Resume`, `_build_run_state`, `_record_pause`, `simulate_pause`, `_clear_pause`, `_adapter_invariant`-compliant | ✓ VERIFIED | All symbols present at current line numbers; invariant checker returns `[]` against the live file (re-run, not assumed) |
| `tools/tests/fast_test.py` | `TestControlCommandsOverGrpc`, `TestControlCommandsBypassMotionLock`, `TestRunStateOverGrpc`, `TestRunState`, `TestAdapterInvariant` (extended), `TestSimulatePauseHook` | ✓ VERIFIED | All classes present; all re-run directly and pass; full gate now reports 144 tests (up from 120 at the prior verification, reflecting Phases 2-3 additions) |
| `tools/base_server.py` | Unchanged vs commit `9c27896` | ✓ VERIFIED | `git diff --exit-code 9c27896 -- tools/base_server.py` exits 0 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `tools/fast/server.py` (`ExecuteCommand`) | `tools/fast/server.py` (`_dispatchCommand`) | control branch dispatches through `self._dispatchCommand(command)` | ✓ WIRED | `grep -n "self._dispatchCommand(command)" tools/fast/server.py` confirms, line 538 |
| `tools/fast/server.py` (`Pause`) | `fast_mcp.service.FastService.pause` | `service.pause(hard=False)` with `hard` as explicit keyword | ✓ WIRED | Line 868; `test_pause_over_grpc_reaches_service_as_soft_pause` still asserts `assert_called_once_with(hard=False)` |
| `tools/fast/server.py` (`GetStatus`) | `interfaces/tools/grpc_interfaces/tool_base.proto` (`StatusReply.run_state`) | `reply.run_state.update(run_state)` | ✓ WIRED | Confirmed at lines 801/804; `TestRunStateOverGrpc` passes over the real gRPC stub |
| `tools/tests/fast_test.py` (`TestControlCommandsOverGrpc`) | `tools/base_server.py` (`ExecuteCommand`) | real in-process gRPC stub exercises `isReady`/BUSY/READY bracket | ✓ WIRED | Re-ran: `self._health().status == BUSY` asserted mid-run, `READY` after release |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `GetStatus` reply | `run_state` (in-flight) | `FastServer._run_record` under `_run_state_lock`, populated by `_log_progress`/`_record_pause` | Yes — live, sanitized record | ✓ FLOWING |
| `GetStatus` reply | `run_state` (idle) | `service.status()` mapped via `_run_percent` | Yes — calls the mocked/real service each time | ✓ FLOWING |
| `GetStatus` reply | `run_state` (other tool types) | unset (`HasField` False) | N/A, correctly absent | ✓ FLOWING (absence is correct) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full gate (ruff, mypy, unittest, pytest) | `bash bin/make proto test` | `144 passed` | ✓ PASS |
| Real-mode concurrency test (D-04/ADP-08) | `python -m unittest ...test_pause_resume_abort_reach_service_while_transfer_in_flight` | `OK` | ✓ PASS |
| All 8 Phase-1 test classes re-run directly | `python -m unittest TestControlCommandsOverGrpc TestControlCommandsBypassMotionLock TestRecoveryCommands TestRunState TestRunStateOverGrpc TestAdapterInvariant TestSimulatePauseHook TestSimulatedTransferOverGrpc -v` | `Ran 70 tests ... OK` | ✓ PASS |
| Invariant checker non-vacuous and clean on real file | inline Python invoking `_adapter_invariant_violations` against current `tools/fast/server.py` | `[]`, exit 0 | ✓ PASS |
| `base_server.py` byte-identical to `9c27896` | `git diff --exit-code 9c27896 -- tools/base_server.py` | exit 0 | ✓ PASS |
| WR-01 reproduction (advisory, not a Phase-1 must-have) | mocked `service.resume.return_value={"errorCode": False}` with motion lock free, call `server.Resume(...)` | `service.wait` was invoked (confirmed via traceback reaching `_result_reply`) instead of an immediate `_recovery_reply` rejection | ⚠️ REPRODUCED (see advisory) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ADP-01 | 01-01/01-02 | Pause reaches the instrument as a soft pause | ✓ SATISFIED | `Pause()` calls `service.pause(hard=False)`; tracer test re-run OK |
| ADP-02 | 01-01 | Pause/Resume/Abort reach FastService while a run is in flight, through `ExecuteCommand` override | ✓ SATISFIED | `TestControlCommandsOverGrpc` concurrency test re-run OK |
| ADP-03 | 01-01/01-02 | Control command never changes tool status | ✓ SATISFIED | Health BUSY asserted mid-run, READY only after Transfer's own finally |
| ADP-04 | 01-02 | Resume's two paths (in-flight no-wait vs crash-recovery wait) | ✓ SATISFIED | `TestControlCommandsBypassMotionLock` tests re-run OK |
| ADP-05 | 01-03 | `GetStatus` returns `run_state` with state/percent/pause | ✓ SATISFIED | `TestRunStateOverGrpc`/`TestRunState` re-run OK |
| ADP-06 | 01-02/01-05 | Blank/unclear decisions are `INVALID_ARGUMENTS` on every path | ✓ SATISFIED | Real-mode and simulated-mode blank-decision tests re-run OK |
| ADP-07 | 01-04 | No-auto-abort invariant extended, fails on planted violation | ✓ SATISFIED | `TestAdapterInvariant` planted-violation tests re-run OK; checker still non-vacuous |
| ADP-08 | 01-01 | Real-mode test proves control commands reach service while Transfer blocked | ✓ SATISFIED | Re-run directly, `OK` |
| ADP-09 | 01-02/01-04 | No adapter-side instrument-state check | ✓ SATISFIED | `ExecuteCommand`/`_build_run_state` AST-checked: no `isReady`/`setStatus`/`parseCommand` calls, no state-string comparisons |
| ADP-10 | 01-05 | Simulated mode: control commands SUCCESS after arg checks; test hook for `run_state` | ✓ SATISFIED | `TestSimulatedTransferOverGrpc`/`TestSimulatePauseHook` re-run OK |

No orphaned requirements: all 10 IDs mapped to this phase in REQUIREMENTS.md (ADP-01 through
ADP-10) are claimed by one of the five plans' `requirements` frontmatter
(ADP-01: 01-01,01-02; ADP-02: 01-01; ADP-03: 01-01,01-02; ADP-04: 01-02; ADP-05: 01-03;
ADP-06: 01-02,01-05; ADP-07: 01-04; ADP-08: 01-01; ADP-09: 01-02,01-04; ADP-10: 01-05), and all
are marked `[x]` / "Complete" in REQUIREMENTS.md's own tracking table.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tools/fast/server.py` | 125, 140, 145 | `PLACEHOLDER` in comments on `EST_ABORT_S`/`EST_RESUME_S` estimate values | ℹ️ Info | Pre-existing documented debt (D-16 estimate values), not a new stub. Not a `TBD`/`FIXME`/`XXX` marker. |
| `tools/fast/server.py` | 937 | `Resume()`'s crash-recovery gate uses `accepted.get("errorCode") != 0` instead of the module's own `_accepted()` fail-closed helper (WR-01, 01-REVIEW.md 2026-10-15) | ⚠️ Warning | Reproduced live (see Behavioral Spot-Checks): a non-int zero-equivalent `errorCode` is misclassified as accepted. Does not violate any stated Phase-1 must-have (01-02-PLAN's D-07 strictness guarantee is explicitly scoped to the in-flight path only); recorded as advisory per this pass's instructions, already tracked `open` in `01-REVIEW-DISPOSITION.md`. |

No `TBD`, `FIXME`, or `XXX` markers found in any covered file. No empty implementations,
hardcoded-empty stubs, or console-log-only handlers found.

Two other fresh-review warnings (WR-02, WR-03) concern `scripts/fast_dryrun.py`, a file outside
Phase 1's scope (not in `covered_files`, not touched by any Phase-1 plan) — not evaluated here;
see `01-REVIEW.md` directly. Three info-level findings (IN-01, IN-02, IN-03) are cosmetic/
documented trade-offs per `01-REVIEW-DISPOSITION.md` and do not affect goal achievement.

## Human Verification

N/A — Infrastructure/foundation phase (internal adapter control path and gRPC wire protocol, no
user-facing elements). All five ROADMAP success criteria and all 10 ADP requirements were
verified programmatically by re-running the actual test suite against the current code, not by
re-reading the prior VERIFICATION.md or SUMMARY claims.

## Gaps Summary

No gaps. All five ROADMAP success criteria still hold against the current code (re-run directly,
not assumed from the stale 2026-10-13 report) despite substantial Phases 2-3 changes to the same
files. All 10 phase requirement IDs (ADP-01 through ADP-10) remain satisfied and traced in
REQUIREMENTS.md with no orphans. `tools/base_server.py` remains byte-identical to `9c27896`. The
full gate (`bash bin/make proto test`) was re-run and passed with 144 tests (up from 120, as
Phases 2-3 added coverage).

One finding from the fresh code review (WR-01, Resume's crash-recovery acceptance check bypassing
`_accepted()`) was independently reproduced during this pass and is recorded as an advisory — it
does not fail any stated Phase-1 must-have and is already tracked as an open code-review item, not
a new gap against this phase's goal.

---

*Verified: 2026-10-15T13:08:03Z*
*Verifier: Claude (gsd-verifier)*
