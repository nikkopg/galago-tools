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

Task IDs from plans 05-01..05-07. Verify blocks that run stack_test.py first run `bin/make proto` (see the plans). The ledger tests and the spike checks do not need it. The per-wave gate is `bin/make proto test`.

| Task ID | Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|---------|-------------|----------|-----------|-------------------|-------------|--------|
| 05-01-T1/T2 | XFR-03, XFR-04, ACK-02 | 05-SPIKE.md answers the D-01 questions and core citations hold at 934a621 | doc + git grep | the grep / `git show 934a621` checks in 05-01 verify | ❌ W0 (spike) | ⬜ pending |
| 05-02-T1 | XFR-01, XFR-02 | Fresh path plan → write-ahead → execute → started → wait → done. `ran` → SUCCESS. Corrupt ledger refuses | integration | `pytest tools/tests/stack_test.py -k TestTransferFreshPath` | ❌ W0 | ⬜ pending |
| 05-02-T2 | XFR-05 | Call-site AST rules with planted violations | AST | `pytest tools/tests/stack_test.py -k TestAdapterInvariant` | partial (rewrite) | ⬜ pending |
| 05-03-T1 | XFR-02 | Atomic write-ahead ledger. Fails closed. Modes 0700/0600. flock. Path resolution. Fingerprint | unit | `pytest tools/tests/stack_ledger_test.py -k "TestLedgerStorage or TestResolveLedgerDir or TestFingerprint"` | ❌ W0 | ⬜ pending |
| 05-03-T2 | XFR-03 | `decide()` per D-07 row, incl. the replay-window edges | unit | `pytest tools/tests/stack_ledger_test.py -k TestDecide` | ❌ W0 | ⬜ pending |
| 05-03-T3 | XFR-03, XFR-04 | release / outcomeUnknown / `is_terminal` (A-1) / retention | unit | `pytest tools/tests/stack_ledger_test.py` | ❌ W0 | ⬜ pending |
| 05-04-T1 | ACK-02 | `GetFailureLatch` → `latch_status()` 1:1. `latchStatus` is SUCCESS | integration | `pytest tools/tests/stack_test.py -k "TestFailureLatch or TestResultMapping"` | ❌ W0 | ⬜ pending |
| 05-04-T2 | ACK-01, XFR-05 | Only `"yes"` reaches the core. Exactly one call site | integration + AST | `pytest tools/tests/stack_test.py -k "TestAcknowledge or TestAdapterInvariant"` | partial | ⬜ pending |
| 05-04-T3 | ACK-02 | Messages name the latch guid first (A-2) and keep it under truncation | integration | `pytest tools/tests/stack_test.py -k TestLatchGuidInMessage` | ❌ W0 | ⬜ pending |
| 05-05-T1 | XFR-04 | Whitelisted release. Unknown / exception / submitOutcomeUnknown keep the key | integration | `pytest tools/tests/stack_test.py -k TestKeyRelease` | ❌ W0 | ⬜ pending |
| 05-05-T2 | XFR-02, XFR-06 | Configure ledger_dir, fail-closed Transfer, budget precedence, motion lock | integration | `pytest tools/tests/stack_test.py -k "TestLedgerFailClosed or TestWaitBudget or TestMotionLock or TestConfigureLedgerDir"` | ❌ W0 | ⬜ pending |
| 05-06-T1 | XFR-03 | Each D-07 row wired into Transfer. Fingerprint mismatch | integration | `pytest tools/tests/stack_test.py -k TestRepeatKey` | ❌ W0 | ⬜ pending |
| 05-06-T2 | XFR-06, XFR-03 | `timedOut` → re-attach → `ran`. 300 s slices. `lost(pollFailed)` stays `started`. Restart | integration | `pytest tools/tests/stack_test.py -k "TestTimedOutReattach or TestRestart"` | ❌ W0 | ⬜ pending |
| 05-07-T1 | XFR-05 | Behavioural submit count of 1 across the D-16 matrix. No auto-ack | integration | `pytest tools/tests/stack_test.py -k TestNeverResends` | ❌ W0 | ⬜ pending |
| 05-07-T2 | STK-05, STK-06 | Reads answer during a real Transfer. Simulated mode never writes the ledger | integration | `pytest tools/tests/stack_test.py -k "TestBusyReads or TestSimulated"` | rewrite | ⬜ pending |

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
