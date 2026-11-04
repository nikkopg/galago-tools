---
phase: "6"
slug: "gal-02-workflow-simulated-workcell-pac-simulator-run"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-11-02"
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `unittest` class style run by both `python -m unittest discover` and `pytest`, plus `ruff` and `mypy` (all in `bin/make test`) |
| **Config file** | `pyproject.toml` (mypy `disallow_untyped_defs`, tests included) |
| **Quick run command** | `PATH=$HOME/.nvm/versions/node/v24.14.1/bin:$PATH ~/data/nikko/.venvs/galago-py310/bin/python -m pytest tools/tests/gal02_handoff_test.py -q -rs -p no:cacheprovider` |
| **Full suite command** | `source ~/data/nikko/.venvs/galago-py310/bin/activate && export PATH=$HOME/.nvm/versions/node/v24.14.1/bin:$PATH && bin/make proto test` |
| **Estimated runtime** | ~15 seconds (baseline 510 passed in 10.8 s) |

---

## Sampling Rate

- **After every task commit:** Run the quick command.
- **After every plan wave:** Run the full suite with node on PATH. Expect 0 skipped in `gal02_handoff_test.py`.
- **Before `/gsd-verify-work`:** The full suite must be green, and the new module must have run in both runners (not skipped).
- **Max feedback latency:** 20 seconds.

---

## Per-Task Verification Map

Filled in by the planner and executor per plan. The requirement → test map comes from `06-RESEARCH.md` § Validation Architecture:

| Requirement | Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|----------|-----------|-------------------|-------------|--------|
| FLOW-01 | Export JSON shape, parameters schema, unique names | unit | `pytest tools/tests/gal02_handoff_test.py -k "export_shape or parameters"` | ❌ W0 | ⬜ pending |
| FLOW-01 | Command order, step keys, swap, safe defaults, throws, no hardware names | unit (node) | `-k "command_order or step_key or swap or safe_defaults or throws or no_hardware_names"` | ❌ W0 | ⬜ pending |
| FLOW-01 | Generated dicts parse into both protos; F.A.S.T. `_check_args == []` | unit | `-k proto_contract` | ❌ W0 | ⬜ pending |
| FLOW-03 (offline) | Re-dispatch replays with submit count 1; late re-dispatch refused; Refused-then-success; out leg uses a fresh key | integration (fake core) | `-k redispatch` | ❌ W0 | ⬜ pending |
| FLOW-02..04 gate | DEP-02 precondition script exits 0 | scripted read-only check | runbook preflight | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `docs/runbooks/` directory (does not exist yet)
- [ ] `docs/runbooks/gal-02-handoff.protocol.json`: the artifact under test
- [ ] `tools/tests/gal02_handoff_test.py`: FLOW-01 + offline FLOW-03

No framework install is needed. Node v24.14.1 is present under nvm only.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Both tools simulated, the run completes 3 tool steps plus the note | FLOW-02 | Needs DEP-02, a dev galago-core and an operator (~150 s) | Runbook Part 2a; Findings log row |
| Simulated re-dispatch returns SUCCESS and no ledger file appears | FLOW-03 (sim half) | Needs a real queue | Runbook Part 2a |
| Real STACK on the PAC sim plus F.A.S.T. sim completes; the re-send replays with sim-side evidence calibrated; the late re-send is refused | FLOW-04 | Operator-built sim and Docker; SAL A.0/A.10 forbid agents starting them | Runbook Part 2b with hardware-refusal preflight |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 20s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
