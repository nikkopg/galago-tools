---
phase: "1"
slug: "adapter-control-path-run-state"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-12"
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | Python `unittest` discovery + `pytest` (same files), ruff, mypy |
| **Config file** | `pyproject.toml` (`[tool.ruff]`, `[tool.mypy]`); no pytest config |
| **Quick run command** | `~/data/nikko/.venvs/galago-py310/bin/python -m unittest discover -s tools/tests/ -p "fast_test.py"` |
| **Full suite command** | `PATH=~/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto test` |
| **Estimated runtime** | ~5 seconds quick, ~60 seconds full |

---

## Sampling Rate

- **After every task commit:** Run the quick command
- **After every plan wave:** Run the full suite command
- **Before `/gsd-verify-work`:** Full suite must be green (baseline 70 tests; count must only grow)
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

Filled in by the planner/executor per task. Requirement → test mapping (from 01-RESEARCH.md):

| Requirement | Behavior | Test Type | Test location | File Exists | Status |
|-------------|----------|-----------|---------------|-------------|--------|
| ADP-01 | `Pause` → `service.pause(hard=False)` exactly once; 1:1 surface includes Pause | unit | `TestOneToOneSurface`, new Pause tests | ✅ extend | ⬜ pending |
| ADP-02 | Pause/Resume/Abort through real gRPC `ExecuteCommand` reach the mock while Transfer blocked | integration | new real-mode concurrency class | ❌ W0 | ⬜ pending |
| ADP-03 | Health `GetStatus` reports BUSY after each control command mid-run | integration | same new class | ❌ W0 | ⬜ pending |
| ADP-04 | Resume: in-flight → no wait; idle → waits (crash recovery) | unit | `TestRecoveryCommands` extension | ✅ extend | ⬜ pending |
| ADP-05 | `run_state` shape for fast; unset for other tool types; `{state: unknown}` on transport error | unit | GetStatus health-RPC tests | ✅ extend | ⬜ pending |
| ADP-06 | Blank/unclear decisions INVALID_ARGUMENTS on override path, real + simulated | unit/integration | `_check_args` + override tests | ✅ extend | ⬜ pending |
| ADP-07 | Scoped `.pause/.resume/.abort/.wait`; record-only recorder/progress; planted violations fail | static (AST) | `TestAdapterInvariant` | ✅ extend | ⬜ pending |
| ADP-08 | Real-mode concurrency test (not simulated) | integration | new class (same as ADP-02) | ❌ W0 | ⬜ pending |
| ADP-09 | Control commands call `service.status` zero times | unit | mocked-service assertions | ❌ W0 | ⬜ pending |
| ADP-10 | Simulated control commands SUCCESS; `simulate_pause` drives `run_state` paused | unit | new simulated tests | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Real-mode `ExecuteCommand` concurrency test class in `tools/tests/fast_test.py`, written failing first (ADP-02/03/08)
- [ ] `TestAdapterInvariant` extension: move `pause` from banned to scoped, add record-only and planted-violation cases (ADP-07)
- [ ] Recorder / run_state unit tests fed a duck-typed `to_dict()` stub (D-13)
- [ ] Simulated hook tests (ADP-10)

---

## Manual-Only Verifications

All phase behaviors have automated verification. (Live instrument behaviour is Phase 3.)

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
