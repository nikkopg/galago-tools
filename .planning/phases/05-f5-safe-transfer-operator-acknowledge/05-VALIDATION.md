---
phase: "5"
slug: "f5-safe-transfer-operator-acknowledge"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-29"
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `unittest` classes run by pytest 7.4.3; the gate also runs ruff and mypy |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `~/data/nikko/.venvs/galago-py310/bin/python -m pytest tools/tests/stack_test.py tools/tests/stack_ledger_test.py -q -k "<pattern>"` |
| **Full suite command** | `bin/make proto test` (venv `~/data/nikko/.venvs/galago-py310`) |
| **Estimated runtime** | ~5 s quick; full gate ~60 s |

---

## Sampling Rate

- **After every task commit:** run the `-k` quick command for the area touched, plus `ruff check tools/stack tools/tests`.
- **After every plan wave:** run `pytest tools/tests/stack_test.py tools/tests/stack_ledger_test.py -q` and `mypy --config-file=pyproject.toml tools`.
- **Before `/gsd-verify-work`:** `bin/make proto test` must be fully green.
- **Max feedback latency:** 60 seconds.

---

## Per-Task Verification Map

The planner fills in task IDs. Each requirement is mapped to its test target below.

| Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|-----------|-------------------|-------------|--------|
| XFR-01 | Plan, execute and wait run as one command. `ran` → SUCCESS. Any other kind → `ERROR_FROM_TOOL`. A blank `step_key` is INVALID before any I/O. | integration | `pytest tools/tests/stack_test.py -k TestTransfer` | ❌ W0 | ⬜ pending |
| XFR-02 | Atomic write-ahead ledger. Fails closed. Modes 0700/0600. | unit + integration | `pytest tools/tests/stack_ledger_test.py` | ❌ W0 | ⬜ pending |
| XFR-03 | Each D-07 row, fingerprint mismatch, restart, and `lost(pollFailed)` stays `started` (A-1). | unit + integration | `pytest tools/tests/stack_test.py -k "TestRepeatKey or TestRestart"` | ❌ W0 | ⬜ pending |
| XFR-04 | Whitelisted release. An exception leaves `submitting`. | integration | `pytest tools/tests/stack_test.py -k TestKeyRelease` | ❌ W0 | ⬜ pending |
| XFR-05 | AST invariant with planted violations, plus a behavioural submit count of 1. | AST + integration | `pytest tools/tests/stack_test.py -k "TestAdapterInvariant or TestNeverResends"` | partial | ⬜ pending |
| XFR-06 | `timedOut`, then re-attach, then `ran`. 300 s slices. Budget precedence. | integration | `pytest tools/tests/stack_test.py -k "TestTimedOutReattach or TestWaitBudget"` | ❌ W0 | ⬜ pending |
| ACK-01 | Only `"yes"` reaches the core. Exactly one call site. | integration + AST | `pytest tools/tests/stack_test.py -k TestAcknowledge` | partial | ⬜ pending |
| ACK-02 | `GetFailureLatch` → `latch_status()`. Messages name the latch guid first (A-2). | integration | `pytest tools/tests/stack_test.py -k "TestFailureLatch or TestLatchGuidInMessage"` | ❌ W0 | ⬜ pending |
| STK-05 | Reads answer during a real Transfer. | integration | `pytest tools/tests/stack_test.py -k TestBusyReads` | rewrite | ⬜ pending |
| STK-06/07 | Simulated mode never writes the ledger. `latchStatus` is SUCCESS. | integration/unit | `pytest tools/tests/stack_test.py -k "TestSimulated or TestResultMapping"` | ✅ extend | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tools/tests/stack_ledger_test.py`: pure ledger tests. They need no core, so they never skip.
- [ ] A `_FakeCore` helper in `tools/tests/stack_test.py`. It counts `execute_transfer` calls and models foreign guids and `_inflight`.
- [ ] `_StackTestCase.setUp` patches `XDG_STATE_HOME`/`HOME` to a temp dir, so tests never touch the real ledger.
- [ ] A Transfer test base class with a guard against motion-lock poisoning.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live STACK motion | — | No motion in this phase. Live motion is Phase 7. | n/a |

*All Phase 5 behaviors have automated verification against a fake core.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
