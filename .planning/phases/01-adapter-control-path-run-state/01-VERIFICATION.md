---
phase: 01-adapter-control-path-run-state
verified: 2026-10-13T10:00:00Z
status: passed
score: 5/5 must-haves verified
covered_files: [".planning/phases/01-adapter-control-path-run-state/01-01-PLAN.md", ".planning/phases/01-adapter-control-path-run-state/01-01-SUMMARY.md", ".planning/phases/01-adapter-control-path-run-state/01-02-PLAN.md", ".planning/phases/01-adapter-control-path-run-state/01-02-SUMMARY.md", ".planning/phases/01-adapter-control-path-run-state/01-03-PLAN.md", ".planning/phases/01-adapter-control-path-run-state/01-03-SUMMARY.md", ".planning/phases/01-adapter-control-path-run-state/01-04-PLAN.md", ".planning/phases/01-adapter-control-path-run-state/01-04-SUMMARY.md", ".planning/phases/01-adapter-control-path-run-state/01-05-PLAN.md", ".planning/phases/01-adapter-control-path-run-state/01-05-SUMMARY.md", "interfaces/tools/grpc_interfaces/fast.proto", "interfaces/tools/grpc_interfaces/tool_base.proto", "tools/fast/server.py", "tools/tests/fast_test.py"]
covered_digest: "v3:sha256:95eabe7a99097b5b80d982414d8177130641f03525f1a228e15646cac1c6c8a8"
behavior_unverified: 0
overrides_applied: 0
---

# Phase 1: Adapter Control Path & Run State Verification Report

**Phase Goal:** An operator's Pause, Resume or Abort reaches the instrument while the step's
Transfer is still running, the tool reports live run state for galago-core to poll, and tests
prove no code path acts without the operator.

**Verified:** 2026-10-13T10:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A real-mode test sends Pause, Resume and Abort through `ExecuteCommand` while a `Transfer` is blocked: each reaches the (mocked) service, the tool's status is still BUSY afterwards, and `tools/base_server.py` is unchanged | ✓ VERIFIED | `tools/tests/fast_test.py::TestControlCommandsOverGrpc.test_pause_resume_abort_reach_service_while_transfer_in_flight` passes (ran directly, `OK`); `git diff --exit-code 9c27896 -- tools/base_server.py` exits 0. Plan 01-01's SUMMARY quotes the pre-override failure (`6 != 1`, NOT_READY) observed before the override existed, proving the test exercises the real gate. |
| 2 | `GetStatus` returns `run_state` with state, percent and pause info for the F.A.S.T., other tool types return it unset, and the proto change regenerates cleanly for Python | ✓ VERIFIED | `interfaces/tools/grpc_interfaces/tool_base.proto:135` has `optional google.protobuf.Struct run_state = 4;`; `tools/fast/server.py::_build_run_state`/`GetStatus` fill it via `reply.run_state.update(...)`; `TestRunStateOverGrpc`, `TestRunState.test_other_tool_types_leave_run_state_unset` pass; full gate (`bin/make proto test`, which regenerates protos) is green. |
| 3 | Blank or unclear decisions are `INVALID_ARGUMENTS` on every path, Pause is always soft, and Resume returns on acceptance with a run in flight but waits when there is none | ✓ VERIFIED | `TestControlCommandsOverGrpc.test_blank_or_unclear_decisions_are_invalid_arguments_through_the_control_path`, `TestSimulatedTransferOverGrpc.test_simulated_control_commands_check_arguments_then_succeed` (simulated blank decisions), `TestRecoveryCommands.test_pause_while_running_is_a_soft_pause_and_success` (`hard=False`), `TestControlCommandsBypassMotionLock.test_resume_with_a_run_in_flight_returns_on_acceptance_without_waiting` and `test_crash_recovery_resume_waits_and_holds_the_lock` all pass. |
| 4 | The extended no-auto-abort invariant fails on a planted violation, and no instrument-state check exists in the adapter | ✓ VERIFIED | `_adapter_invariant_violations` run directly against `tools/fast/server.py` returns `[]`; `TestAdapterInvariant.test_planted_scoped_call_violations_are_caught`, `test_planted_record_and_state_violations_are_caught`, `test_planted_allowed_calls_add_no_violation`, `test_planted_allowed_record_and_reader_calls_add_no_violation` pass (each plants a violation and confirms it's caught, and plants an allowed call and confirms it's quiet — a non-vacuous checker). |
| 5 | In simulated mode, control commands return SUCCESS after argument checks and a test hook drives `run_state` to paused | ✓ VERIFIED | `TestSimulatedTransferOverGrpc.test_simulated_control_commands_check_arguments_then_succeed`, `test_hooked_pause_reads_paused_with_its_detail`, `test_pause_prompt_round_trip_without_hardware`, `TestSimulatePauseHook.test_hook_raises_in_real_mode_and_records_nothing` all pass; `fast.proto` has no `simulate_pause` field (grep exits 1, confirming it's not a gRPC command). |

**Score:** 5/5 ROADMAP success criteria verified (0 present-but-behavior-unverified)

### Plan-Level Must-Haves (supporting detail)

All five plans' `must_haves.truths`, `artifacts`, `key_links` and `prohibitions` were cross-checked
against the live codebase, not just the SUMMARY claims:

- **D-05/D-06/D-07 (lock discipline):** `Pause`/`Abort` have no `_motion_lock` access (confirmed by
  AST acceptance checks baked into the test suite and independently re-run); `Resume` branches on a
  non-blocking `_motion_lock.acquire()`. `TestControlCommandsBypassMotionLock` (5 tests) proves this
  with a `MagicMock(wraps=threading.Lock())` spy.
- **D-01/D-02/D-03 (ExecuteCommand override):** routes only `pause`/`resume`/`abort` past
  `isReady`/`setStatus`/`parseCommand`; every other command (including a non-control fast command
  mid-run, and a non-fast `toolbox` command) still takes `super().ExecuteCommand(...)`. Proven by
  `test_wrong_tool_type_never_takes_the_control_path` and
  `test_non_control_commands_still_take_the_base_server_gate_mid_run`.
- **D-09 through D-14 (run_state):** `_build_run_state` reads only the adapter's own record while a
  run is in flight and calls `service.status()` exactly once otherwise (AST-verified: its only
  `service.*` call is `status`); every read-path failure (exception, non-dict, non-str state,
  unencodable Struct payload) collapses to `{state: unknown}` without failing the heartbeat
  (`TestRunState.test_status_failure_reports_unknown_and_the_heartbeat_still_answers`, re-run live
  and observed passing with `RuntimeError` injected).
- **D-15 through D-17 (mechanical invariant):** `_SCOPED_ATTRS`, `_RECORD_ONLY_FUNCTIONS`,
  `_STATUS_READERS`, `_CONTROL_PATH_FUNCTIONS` scope every control/record/status call to its owning
  function; the checker is proven non-vacuous (fires on a planted mistake, stays quiet on a planted
  legitimate call) — this was independently re-run, not just read from the SUMMARY.
- **D-18 through D-20 (simulated mode):** simulated control commands sleep their estimate and never
  call `open_service` or build a `FastService`; `simulate_pause` raises `RuntimeError` outside
  simulated mode as its first statement, before touching any state (AST-verified); it has no proto
  field and is absent from `COMMAND_TO_SERVICE_METHOD`.
- **Code-review fixes (CR-01, WR-01) verified in the live file, not just claimed in
  01-REVIEW-FIX.md:** `_run_in_flight()`'s entry path now only resets `_run_record` on the `0->1`
  transition (`tools/fast/server.py:515-530`, matching the reviewer's exact suggested fix); and
  `_log_progress` now routes `percent` through `_run_percent()` before storing it
  (`tools/fast/server.py:536-543`). Both regression tests
  (`test_pause_recorded_during_one_run_survives_a_second_overlapping_runs_entry` and
  `test_log_progress_sanitizes_the_percent_like_every_other_path`) were re-run directly and pass.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `interfaces/tools/grpc_interfaces/fast.proto` | `Pause {}` message, oneof field `pause = 10` | ✓ VERIFIED | `grep` confirms both lines present at 16, 72 |
| `interfaces/tools/grpc_interfaces/tool_base.proto` | `StatusReply.run_state = 4` (optional Struct) | ✓ VERIFIED | Present at line 135, regenerates cleanly via `bin/make proto` |
| `tools/fast/server.py` | `ExecuteCommand` override, `Pause`/`Abort`/`Resume`, `_build_run_state`, `_record_pause`, `simulate_pause`, `_clear_pause`, `_adapter_invariant`-compliant | ✓ VERIFIED | All symbols present at expected line numbers; invariant checker returns `[]` against the live file |
| `tools/tests/fast_test.py` | `TestControlCommandsOverGrpc`, `TestControlCommandsBypassMotionLock`, `TestRunStateOverGrpc`, `TestRunState`, `TestAdapterInvariant` (extended), `TestSimulatePauseHook` | ✓ VERIFIED | All classes present; all re-run directly and pass (39 tests across these 6 classes, 120 total in the full gate) |
| `tools/base_server.py` | Unchanged vs commit `9c27896` | ✓ VERIFIED | `git diff --exit-code 9c27896 -- tools/base_server.py` exits 0 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `tools/fast/server.py` (`ExecuteCommand`) | `tools/fast/server.py` (`_dispatchCommand`) | control branch dispatches through `self._dispatchCommand(command)` | ✓ WIRED | Confirmed present and exercised (`_check_args` runs on the control path — fail-closed decision tests pass) |
| `tools/fast/server.py` (`Pause`) | `fast_mcp.service.FastService.pause` | `service.pause(hard=False)` with `hard` as explicit keyword | ✓ WIRED | `test_pause_over_grpc_reaches_service_as_soft_pause` asserts `assert_called_once_with(hard=False)` |
| `tools/fast/server.py` (`GetStatus`) | `interfaces/tools/grpc_interfaces/tool_base.proto` (`StatusReply.run_state`) | `reply.run_state.update(run_state)` | ✓ WIRED | Grep confirms the call site; `TestRunStateOverGrpc` confirms the field is populated end to end over the real gRPC stub |
| `tools/tests/fast_test.py` (`TestControlCommandsOverGrpc`) | `tools/base_server.py` (`ExecuteCommand`) | real in-process gRPC stub exercises `isReady`/BUSY/READY bracket | ✓ WIRED | Confirmed via the pre-override expected-failure, now a passing ordinary test |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `GetStatus` reply | `run_state` (in-flight) | `FastServer._run_record` under `_run_state_lock`, populated by `_log_progress`/`_record_pause` | Yes — a live, sanitized record, not a static literal | ✓ FLOWING |
| `GetStatus` reply | `run_state` (idle) | `service.status()` mapped via `_run_percent` | Yes — calls the mocked/real service each time | ✓ FLOWING |
| `GetStatus` reply | `run_state` (other tool types) | unset (`HasField` False) | N/A, correctly absent | ✓ FLOWING (absence is the correct behavior) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full gate (ruff, mypy, unittest, pytest) | `bash bin/make proto test` | `120 passed` | ✓ PASS |
| Real-mode concurrency test (D-04/ADP-08) | `python -m unittest ...test_pause_resume_abort_reach_service_while_transfer_in_flight` | `OK` | ✓ PASS |
| Crash-recovery Resume holds lock through wait | `python -m unittest ...test_crash_recovery_resume_waits_and_holds_the_lock` | `OK` | ✓ PASS |
| CR-01 regression (overlapping-run pause survival) | `python -m unittest ...test_pause_recorded_during_one_run_survives_a_second_overlapping_runs_entry` | `OK` | ✓ PASS |
| Invariant checker non-vacuous and clean on real file | inline Python invoking `_adapter_invariant_violations` | `[]`, exit 0 | ✓ PASS |
| `base_server.py` byte-identical to `9c27896` | `git diff --exit-code 9c27896 -- tools/base_server.py` | exit 0 | ✓ PASS |
| `simulate_pause` not a gRPC command | `grep -n "simulate_pause" interfaces/tools/grpc_interfaces/fast.proto` | exit 1 (not found) | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ADP-01 | 01-01 | Pause reaches the instrument as a soft pause | ✓ SATISFIED | `Pause()` calls `service.pause(hard=False)`; tracer test passes |
| ADP-02 | 01-01 | Pause/Resume/Abort reach FastService while a run is in flight, through `ExecuteCommand` override | ✓ SATISFIED | `TestControlCommandsOverGrpc` concurrency test passes |
| ADP-03 | 01-01/01-02 | Control command never changes tool status | ✓ SATISFIED | `test_control_commands_never_call_set_status` passes |
| ADP-04 | 01-02 | Resume's two paths (in-flight no-wait vs crash-recovery wait) | ✓ SATISFIED | `TestControlCommandsBypassMotionLock` tests pass |
| ADP-05 | 01-03 | `GetStatus` returns `run_state` with state/percent/pause | ✓ SATISFIED | `TestRunStateOverGrpc`/`TestRunState` pass |
| ADP-06 | 01-02/01-05 | Blank/unclear decisions are `INVALID_ARGUMENTS` on every path | ✓ SATISFIED | Real-mode and simulated-mode blank-decision tests pass |
| ADP-07 | 01-04 | No-auto-abort invariant extended, fails on planted violation | ✓ SATISFIED | `TestAdapterInvariant` planted-violation tests pass |
| ADP-08 | 01-01 | Real-mode test proves control commands reach service while Transfer blocked | ✓ SATISFIED | Pre-override failure quoted and reproduced; override makes it pass |
| ADP-09 | 01-02/01-04 | No adapter-side instrument-state check | ✓ SATISFIED | `test_control_commands_never_check_instrument_state` + AST rule pass |
| ADP-10 | 01-05 | Simulated mode: control commands SUCCESS after arg checks; test hook for `run_state` | ✓ SATISFIED | `TestSimulatedTransferOverGrpc`/`TestSimulatePauseHook` pass |

No orphaned requirements: all 10 IDs mapped to this phase in REQUIREMENTS.md (ADP-01 through ADP-10)
are claimed by one of the five plans' `requirements` frontmatter, and all are marked `[x]` /
"Complete" in REQUIREMENTS.md's own tracking table.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tools/fast/server.py` | 125, 140, 145 | `PLACEHOLDER` in comments on `EST_ABORT_S`/`EST_RESUME_S` estimate values | ℹ️ Info | Pre-existing (present at commit `9c27896`, before this phase); explicitly documented accepted debt (D-16 estimate values), not a new stub introduced by this phase. Not a `TBD`/`FIXME`/`XXX` marker, so the debt-marker gate does not apply. |

No `TBD`, `FIXME`, or `XXX` markers found in any file touched by this phase. No empty
implementations, hardcoded-empty stubs, or console-log-only handlers found in the diff
(`git diff 9c27896 HEAD -- tools/fast/server.py tools/tests/fast_test.py interfaces/...`).

Three code-review findings remain open by deliberate scope decision, not oversight — recorded in
`01-REVIEW-DISPOSITION.md` and out of `fix_scope: critical_warning`:
- **IN-01** (info): `_run_record`'s initial seed state is `"running"` though no run is in flight —
  has no observable effect (confirmed: `_build_run_state` never reads this value before the first
  `_run_in_flight()` call overwrites it).
- **IN-02** (info): `tool_base.proto` missing trailing newline — cosmetic.
- **IN-03** (info): `_run_percent`'s return type annotation doesn't exactly match its `int` branch —
  cosmetic/typing nit, confirmed harmless at runtime.

None of these three affect goal achievement; they are informational only.

## Gaps Summary

No gaps. All five ROADMAP success criteria are verified with passing, independently re-run tests
(not just SUMMARY claims). All 10 phase requirement IDs (ADP-01 through ADP-10) are satisfied and
traced in REQUIREMENTS.md with no orphans. The two code-review findings that could have undermined
the goal (CR-01: a pause could be silently clobbered by an overlapping run; WR-01: unsanitized
percent could leak into `run_state`) were fixed in commits `581dec7`/`cb7886d`, and both fixes were
independently confirmed in the live file and by re-running their regression tests — not merely
trusted from `01-REVIEW-FIX.md`. `tools/base_server.py` is confirmed byte-identical to `9c27896`.
The full gate (`bash bin/make proto test`) was independently re-run and passed with 120 tests.

---

*Verified: 2026-10-13T10:00:00Z*
*Verifier: Claude (gsd-verifier)*
