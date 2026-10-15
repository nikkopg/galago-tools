---
phase: "2"
slug: "wait-through-pauses-on-the-pinned-core"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-13"
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `unittest` + `pytest` over the same files, both run by `bin/make test` |
| **Config file** | `pyproject.toml` (mypy); pytest defaults |
| **Quick run command** | `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH python -m pytest tools/tests/fast_test.py -k <affected class> -vv` |
| **Full suite command** | `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto test` |
| **Estimated runtime** | ~60 seconds (full gate); seconds for a class (all sleeps injected) |

---

## Sampling Rate

- **After every task commit:** Run the quick command for the affected test class
- **After every plan wave:** Run the full suite command
- **Before `/gsd-verify-work`:** Full suite must be green against the gate venv re-pinned to `b30b38d`
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

Filled in by the planner from the PLAN.md tasks. Requirement → test map from research:

| Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|-----------|-------------------|-------------|--------|
| LIVE-01 | Pin is `b30b38d`; installed core has `through_pauses`/`on_pause`/`PauseInfo` and state-gated pause/resume/abort | unit | `pytest tools/tests/fast_test.py -k "TestRequirementsPin or TestRecoveryCommands" -vv` | ✅ pin + idle-refusal tests; ❌ W0 capability assertion | ⬜ pending |
| LIVE-02 | Pause keeps the step open; SUCCESS after resume; "run aborted by operator at <p>%" on operator abort | integration (real core, stub transport, threaded) | `pytest tools/tests/fast_test.py -k "PauseThrough or OperatorAbort or TestResultMapping" -vv` | ❌ W0 | ⬜ pending |
| LIVE-03 | Paused time excluded from the timeout; timeout never aborts | unit (injected clock/sleep) | `pytest tools/tests/fast_test.py -k "Timeout" -vv` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Re-install the gate venv's fast_mcp from the local clone at `b30b38df48e8480f325228145ccae7915a56e437`
- [ ] LIVE-01 capability assertion (RunOptions fields + PauseInfo import)
- [ ] Rewrite `test_resume_known_limitation_leading_paused_poll_reads_as_paused` (D-08)
- [ ] Local `_Stepper` helper (sleep-gated pacing, research Pattern 3)
- [ ] End-to-end pause/resume and operator-abort tests (D-15/D-16)
- [ ] Deterministic timeout-exclusion test (D-13)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Clean install from GitLab at the new pin | LIVE-01 | `fix/run-recovery-gate` not yet pushed; outward-facing action owned by the user | After the push, `pip install -r tools/fast/requirements.txt` in a scratch venv succeeds (Phase 3 prerequisite) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
