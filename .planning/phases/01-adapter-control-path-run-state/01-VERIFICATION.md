---
phase: 01-adapter-control-path-run-state
verified: 2026-10-16T05:35:00Z
status: passed
score: 5/5 must-haves verified
covered_files: [".planning/phases/01-adapter-control-path-run-state/01-01-PLAN.md", ".planning/phases/01-adapter-control-path-run-state/01-01-SUMMARY.md", ".planning/phases/01-adapter-control-path-run-state/01-02-PLAN.md", ".planning/phases/01-adapter-control-path-run-state/01-02-SUMMARY.md", ".planning/phases/01-adapter-control-path-run-state/01-03-PLAN.md", ".planning/phases/01-adapter-control-path-run-state/01-03-SUMMARY.md", ".planning/phases/01-adapter-control-path-run-state/01-04-PLAN.md", ".planning/phases/01-adapter-control-path-run-state/01-04-SUMMARY.md", ".planning/phases/01-adapter-control-path-run-state/01-05-PLAN.md", ".planning/phases/01-adapter-control-path-run-state/01-05-SUMMARY.md", "interfaces/tools/grpc_interfaces/fast.proto", "interfaces/tools/grpc_interfaces/tool_base.proto", "tools/fast/server.py", "tools/tests/fast_test.py"]
covered_digest: "v3:sha256:c55beed08e33b10457fbeab02e652e4c78c7b966691a28cd8805f4a8cf2f6e38"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: passed
  previous_score: 5/5
  gaps_closed:
    - "WR-01 advisory from the 2026-10-15T13:08Z pass (Resume's crash-recovery acceptance gate bypassing _accepted()) is now fixed in code: commit 134e097 (fix(02-05)) routes the gate through _accepted(accepted), and commit 7c2e15a (test(02-05)) pins the full boundary with 7 rejection shapes plus an int-0 positive control. No longer an open finding against the current HEAD."
  gaps_remaining: []
  regressions: []
---

# Phase 1: Adapter Control Path & Run State Verification Report

**Phase Goal:** An operator's Pause, Resume or Abort reaches the instrument while the step's
Transfer is still running, the tool reports live run state for galago-core to poll, and tests
prove no code path acts without the operator.

**Verified:** 2026-10-16T05:35:00Z
**Status:** passed
**Re-verification:** Yes — the 2026-10-15T13:08Z VERIFICATION.md is stale because covered source
changed afterwards: Phase 2 gap-closure plan 02-05 (commits 134e097 fix, 7c2e15a test) changed
`tools/fast/server.py`'s crash-recovery Resume to wait only after `_accepted()` (CR-01) and added
regression tests in `tools/tests/fast_test.py`. This pass re-checks all five ROADMAP success
criteria and all 10 ADP requirements against the current HEAD, with particular attention to ADP-04
(Resume's two paths) and ADP-07 (no-auto-abort invariant).

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A real-mode test sends Pause, Resume and Abort through `ExecuteCommand` while a `Transfer` is blocked: each reaches the (mocked) service, the tool's status is still BUSY afterwards, and `tools/base_server.py` is unchanged | ✓ VERIFIED | Ran directly: `python -m unittest tools.tests.fast_test.TestControlCommandsOverGrpc -v` → all pass (part of the 73-test run below). `git diff --exit-code 9c27896 -- tools/base_server.py` exits 0 (still byte-identical). |
| 2 | `GetStatus` returns `run_state` with state, percent and pause info for the F.A.S.T., other tool types return it unset, and the proto change regenerates cleanly for Python | ✓ VERIFIED | `interfaces/tools/grpc_interfaces/tool_base.proto:135` still has `optional google.protobuf.Struct run_state = 4;`. `TestRunStateOverGrpc` and `TestRunState` re-run directly: `OK`. |
| 3 | Blank or unclear decisions are `INVALID_ARGUMENTS` on every path, Pause is always soft, and Resume returns on acceptance with a run in flight but waits when there is none | ✓ VERIFIED | `TestRecoveryCommands`, `TestControlCommandsBypassMotionLock` re-run directly: `OK`. `Pause()` still calls `service.pause(hard=False)` (line 868). Resume's crash-recovery branch (line 944) now gates `service.wait` on `_accepted(accepted)` (CR-01 fix, 134e097) instead of the looser inline check the prior pass flagged as advisory WR-01; `test_crash_recovery_resume_waits_only_for_an_int_zero_error_code` (7c2e15a) exercises 7 non-accepting shapes (`False`, `{}`, `0.0`, `"0"`, `True`, `None`, `-2`) that all reject without calling `service.wait`, plus a real int-0 positive control that does wait exactly once — ran individually, `OK`. |
| 4 | The extended no-auto-abort invariant fails on a planted violation, and no instrument-state check exists in the adapter | ✓ VERIFIED | `_adapter_invariant_violations(ast.parse(Path("tools/fast/server.py").read_text()))` run directly against the current file returns `[]`. `TestAdapterInvariant` (6 tests, including planted-violation tests in both directions) re-ran directly: `OK`. |
| 5 | In simulated mode, control commands return SUCCESS after argument checks and a test hook drives `run_state` to paused | ✓ VERIFIED | `TestSimulatedTransferOverGrpc`, `TestSimulatePauseHook` re-ran directly: `OK`. `simulate_pause` still absent from `fast.proto`'s oneof (not a gRPC command). |

**Score:** 5/5 ROADMAP success criteria verified (0 present-but-behavior-unverified)

### Changes Since the 2026-10-15T13:08Z Verification

`tools/fast/server.py` and `tools/tests/fast_test.py` changed again after the prior verification,
via Phase 2 gap-closure plan 02-05:

- `134e097` (`fix(02-05)`): `Resume()`'s crash-recovery branch now gates `service.wait` on
  `_accepted(accepted)` — the module's single fail-closed definition of "accepted" (`type(code) is
  int and code == 0`) — instead of the inline `isinstance(accepted, Refused) or
  accepted.get("errorCode") != 0` check that the prior verification's `advisory:` finding (WR-01)
  flagged and reproduced live (a mocked `{"errorCode": False}` previously fell through to
  `service.wait`).
- `7c2e15a` (`test(02-05)`): adds `_resume_with_reply`/`_assert_rejected_without_waiting` helpers
  and `test_crash_recovery_resume_bool_false_error_code_is_not_success`,
  `test_crash_recovery_resume_reply_without_error_code_is_not_success`, and
  `test_crash_recovery_resume_waits_only_for_an_int_zero_error_code` — the last of which pins the
  full acceptance boundary (7 rejection shapes + 1 real int-0 acceptance control) on the real core,
  confirming `service.wait` is never called on rejection and is called exactly once on genuine
  acceptance.

Both commits were independently confirmed present at HEAD (`git log`), and the resulting code was
re-read directly (not inferred from commit messages): `tools/fast/server.py:944` reads
`if not _accepted(accepted): return _recovery_reply("resume", accepted)` before the
`service.wait(...)` call. This closes the gap the prior verification carried as an advisory — see
`gaps_closed` in frontmatter.

No other Phase-1 symbols (`ExecuteCommand` override, `CONTROL_COMMANDS`, `MOTION_LOCK_COMMANDS`,
`_build_run_state`, `_adapter_invariant_violations`'s scoped-attrs tables) were touched by 02-05.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `interfaces/tools/grpc_interfaces/fast.proto` | `Pause {}` message, oneof field `pause = 10` | ✓ VERIFIED | `grep` confirms both lines present (lines 72, 16) |
| `interfaces/tools/grpc_interfaces/tool_base.proto` | `StatusReply.run_state = 4` (optional Struct) | ✓ VERIFIED | Present at line 135 |
| `tools/fast/server.py` | `ExecuteCommand` override, `Pause`/`Abort`/`Resume`, `_build_run_state`, `_record_pause`, `simulate_pause`, `_clear_pause`, `_adapter_invariant`-compliant, CR-01 `_accepted()` gate on Resume's crash-recovery path | ✓ VERIFIED | All symbols present at current line numbers; invariant checker returns `[]` against the live file (re-run, not assumed); `_accepted(accepted)` gate confirmed at line 944 |
| `tools/tests/fast_test.py` | `TestControlCommandsOverGrpc`, `TestControlCommandsBypassMotionLock`, `TestRunStateOverGrpc`, `TestRunState`, `TestAdapterInvariant` (extended), `TestSimulatePauseHook`, CR-01 regression tests in `TestRecoveryCommands` | ✓ VERIFIED | All classes/tests present; `node ...verify.artifacts` confirms `passed: true` for all 5 plans; full gate reports 147 tests (up from 144 at the prior verification, reflecting 02-05's 3 new tests) |
| `tools/base_server.py` | Unchanged vs commit `9c27896` | ✓ VERIFIED | `git diff --exit-code 9c27896 -- tools/base_server.py` exits 0 |

Machine-verified via `gsd-tools query verify.artifacts` for all 5 plans (01-01 through 01-05):
`all_passed: true` for every plan, 11/11 declared artifacts passed, 0 issues.

### Key Link Verification

Machine-verified via `gsd-tools query verify.key-links` for all 5 plans: `all_verified: true` for
every plan, 12/12 declared key links verified (4 in 01-01, 2 in 01-02, 3 in 01-03, 1 in 01-04, 2 in
01-05).

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `tools/fast/server.py` (`ExecuteCommand`) | `tools/fast/server.py` (`_dispatchCommand`) | control branch dispatches through `self._dispatchCommand(command)` | ✓ WIRED | Pattern found in source |
| `tools/fast/server.py` (`Pause`) | `fast_mcp.service.FastService.pause` | `service.pause(hard=False)` with `hard` as explicit keyword | ✓ WIRED | Pattern found in source |
| `tools/fast/server.py` (`Resume`, crash-recovery branch) | `tools/fast/server.py` (`_accepted`) | `if not _accepted(accepted): return _recovery_reply(...)` gates `service.wait` | ✓ WIRED | Confirmed at line 944; `test_crash_recovery_resume_waits_only_for_an_int_zero_error_code` exercises both branches |
| `tools/fast/server.py` (`GetStatus`) | `interfaces/tools/grpc_interfaces/tool_base.proto` (`StatusReply.run_state`) | `reply.run_state.update(run_state)` | ✓ WIRED | `TestRunStateOverGrpc` passes over the real gRPC stub |
| `tools/tests/fast_test.py` (`TestControlCommandsOverGrpc`) | `tools/base_server.py` (`ExecuteCommand`) | real in-process gRPC stub exercises `isReady`/BUSY/READY bracket | ✓ WIRED | Re-ran: health BUSY mid-run, READY after release |
| `tools/tests/fast_test.py` (`TestAdapterInvariant`) | `tools/fast/server.py` | parses `server.py`'s AST and asserts the checker reports nothing, then plants violations into deep copies | ✓ WIRED | `_adapter_invariant_violations` returns `[]` on the live file; planted-violation tests catch injected violations |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|---------------------|--------|
| `GetStatus` reply | `run_state` (in-flight) | `FastServer._run_record` under `_run_state_lock`, populated by `_log_progress`/`_record_pause` | Yes — live, sanitized record | ✓ FLOWING |
| `GetStatus` reply | `run_state` (idle) | `service.status()` mapped via `_run_percent` | Yes — calls the mocked/real service each time | ✓ FLOWING |
| `GetStatus` reply | `run_state` (other tool types) | unset (`HasField` False) | N/A, correctly absent | ✓ FLOWING (absence is correct) |
| `Resume` crash-recovery reply | `accepted` acceptance decision | `_accepted(accepted)` — single fail-closed predicate, not an inline comparison | Yes — gates whether `service.wait` is ever called | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full test suite (discover) | `python -m unittest discover -s tools/tests/ -p "*_test.py"` (run once from repo root) | `Ran 147 tests ... OK` | ✓ PASS |
| 8 Phase-1 test classes re-run directly | `python -m unittest TestControlCommandsOverGrpc TestControlCommandsBypassMotionLock TestRecoveryCommands TestRunState TestRunStateOverGrpc TestAdapterInvariant TestSimulatePauseHook TestSimulatedTransferOverGrpc -v` | `Ran 73 tests ... OK` | ✓ PASS |
| CR-01 regression tests (the specific tests added by 02-05) | `python -m unittest TestRecoveryCommands.test_crash_recovery_resume_bool_false_error_code_is_not_success TestRecoveryCommands.test_crash_recovery_resume_reply_without_error_code_is_not_success TestRecoveryCommands.test_crash_recovery_resume_waits_only_for_an_int_zero_error_code -v` | `Ran 3 tests ... OK` | ✓ PASS |
| Invariant checker non-vacuous and clean on real file | inline Python invoking `_adapter_invariant_violations(ast.parse(...))` against current `tools/fast/server.py` | `[]`, exit 0 | ✓ PASS |
| `base_server.py` byte-identical to `9c27896` | `git diff --exit-code 9c27896 -- tools/base_server.py` | exit 0 | ✓ PASS |
| Resume's `_accepted()` gate present at the crash-recovery call site | `grep -n "_accepted" tools/fast/server.py` + direct code read | line 944: `if not _accepted(accepted): return _recovery_reply("resume", accepted)` before `service.wait(...)` | ✓ PASS — closes prior pass's WR-01 advisory |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ADP-01 | 01-01/01-02 | Pause reaches the instrument as a soft pause | ✓ SATISFIED | `Pause()` calls `service.pause(hard=False)`; tests re-run OK |
| ADP-02 | 01-01 | Pause/Resume/Abort reach FastService while a run is in flight, through `ExecuteCommand` override | ✓ SATISFIED | `TestControlCommandsOverGrpc` concurrency test re-run OK |
| ADP-03 | 01-01/01-02 | Control command never changes tool status | ✓ SATISFIED | Health BUSY asserted mid-run, READY only after Transfer's own finally |
| ADP-04 | 01-02 | Resume's two paths (in-flight no-wait vs crash-recovery wait) | ✓ SATISFIED | `TestControlCommandsBypassMotionLock` + CR-01 tests in `TestRecoveryCommands` re-run OK; crash-recovery wait now gated by `_accepted()` |
| ADP-05 | 01-03 | `GetStatus` returns `run_state` with state/percent/pause | ✓ SATISFIED | `TestRunStateOverGrpc`/`TestRunState` re-run OK |
| ADP-06 | 01-02/01-05 | Blank/unclear decisions are `INVALID_ARGUMENTS` on every path | ✓ SATISFIED | Real-mode and simulated-mode blank-decision tests re-run OK |
| ADP-07 | 01-04 | No-auto-abort invariant extended, fails on planted violation | ✓ SATISFIED | `TestAdapterInvariant` planted-violation tests re-run OK; checker still non-vacuous, returns `[]` on real file |
| ADP-08 | 01-01 | Real-mode test proves control commands reach service while Transfer blocked | ✓ SATISFIED | Re-run directly, `OK` |
| ADP-09 | 01-02/01-04 | No adapter-side instrument-state check | ✓ SATISFIED | `ExecuteCommand`/`_build_run_state` invariant-checked: no `isReady`/`setStatus`/`parseCommand` calls, no state-string comparisons |
| ADP-10 | 01-05 | Simulated mode: control commands SUCCESS after arg checks; test hook for `run_state` | ✓ SATISFIED | `TestSimulatedTransferOverGrpc`/`TestSimulatePauseHook` re-run OK |

No orphaned requirements: all 10 IDs mapped to this phase in REQUIREMENTS.md (ADP-01 through
ADP-10) are claimed by one of the five plans' `requirements` frontmatter and are marked `[x]` /
"Complete" in REQUIREMENTS.md's traceability table (cross-checked directly against
`.planning/REQUIREMENTS.md`).

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `tools/fast/server.py` | 125, 140, 145 | `PLACEHOLDER` in comments on `EST_ABORT_S`/`EST_RESUME_S` estimate values | ℹ️ Info | Pre-existing documented debt (D-16 estimate values), not a new stub. Not a `TBD`/`FIXME`/`XXX` marker. |

No `TBD`, `FIXME`, or `XXX` markers found in `tools/fast/server.py` or `tools/tests/fast_test.py`
(grep confirmed empty). No empty implementations, hardcoded-empty stubs, or console-log-only
handlers found.

The WR-01 finding carried as an `advisory:` item in the prior (2026-10-15T13:08Z) VERIFICATION.md
is now fixed in code (commit 134e097) and test-pinned (commit 7c2e15a) — confirmed by direct code
read and by running the specific regression tests. It is removed from this report's findings;
tracked as closed in `gaps_closed` above. Note: `.planning/phases/01-adapter-control-path-run-state/01-REVIEW-DISPOSITION.md`
and `01-REVIEW.md` still show WR-01 as `disposition: open` — those docs are dated 2026-10-15
20:03-20:04 (commit `7b556c9`), which predates the 02-05 fix (`134e097`, 21:07:53) and test
(`7c2e15a`, 21:09:38) by about an hour. Those review artifacts were not updated after the fix
landed; this is a documentation staleness issue in the code-review trail, not a gap against this
phase's goal (the phase goal and all ADP-04/ADP-07 must-haves are independently verified above
against the current code and tests, not against the review disposition doc).

Two other review warnings (WR-02, WR-03) concern `scripts/fast_dryrun.py`, a file outside Phase 1's
scope (not in `covered_files`, not touched by any Phase-1 plan) — not evaluated here.

## Human Verification

N/A — Infrastructure/foundation phase (internal adapter control path and gRPC wire protocol, no
user-facing elements). All five ROADMAP success criteria and all 10 ADP requirements were verified
programmatically by running the actual test suite against the current code, not by re-reading the
prior VERIFICATION.md or SUMMARY claims.

## Gaps Summary

No gaps. All five ROADMAP success criteria still hold against the current HEAD. The one advisory
item carried forward from the prior verification (WR-01 / CR-01: Resume's crash-recovery acceptance
gate bypassing the module's own fail-closed `_accepted()` helper) is now fixed by Phase 2's
gap-closure plan 02-05 (commits 134e097, 7c2e15a) and independently confirmed here: the gate at
`tools/fast/server.py:944` now reads `if not _accepted(accepted): return _recovery_reply(...)`
before `service.wait(...)`, and the new regression test
`test_crash_recovery_resume_waits_only_for_an_int_zero_error_code` proves the full rejection
boundary (7 non-accepting shapes) plus a real int-0 acceptance control, run directly with `OK`.

All 10 phase requirement IDs (ADP-01 through ADP-10) remain satisfied and traced in
REQUIREMENTS.md with no orphans. `tools/base_server.py` remains byte-identical to `9c27896`. The
full suite (`python -m unittest discover -s tools/tests/ -p "*_test.py"`) was run once from the
repo root and passed 147/147 (up from 144 at the 2026-10-15T13:08Z pass, reflecting 02-05's 3 new
tests). All must_haves artifacts (11) and key_links (12) declared across the five Phase-1 plans
were machine-verified via `gsd-tools query verify.artifacts`/`verify.key-links` with no failures.

---

*Verified: 2026-10-16T05:35:00Z*
*Verifier: Claude (gsd-verifier)*
