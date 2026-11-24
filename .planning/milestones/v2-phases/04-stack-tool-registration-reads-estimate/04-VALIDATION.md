---
phase: "4"
slug: "stack-tool-registration-reads-estimate"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-28"
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `unittest` (stdlib), run by both `unittest discover` and pytest 7.4.3 |
| **Config file** | `pyproject.toml` (`[tool.ruff]`, `[tool.mypy]`); `bin/make` `test()` |
| **Quick run command** | `source ~/data/nikko/.venvs/galago-py310/bin/activate && python -m pytest tools/tests/stack_test.py -x -q -p no:cacheprovider` |
| **Full suite command** | `source ~/data/nikko/.venvs/galago-py310/bin/activate && bin/make proto test` |
| **Estimated runtime** | quick ~3 s; full gate ~60 s (baseline 147 tests) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command
- **After every plan wave:** Run the full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

Task IDs are filled in by the planner/executor. The requirement → test map from `04-RESEARCH.md` § Validation Architecture:

| Requirement | Plan / Task | Secure Behavior | Test Type | Automated Command (`-k` on the quick command) | File Exists | Status |
|-------------|-------------|-----------------|-----------|-----------------------------------------------|-------------|--------|
| STK-01 | 04-01 T1-T3 | Core installed at pinned SHA; registration numbers 24/43/24; frozen proto field list; no `lock_dir`; server starts as `stack` | unit + smoke | `-k "Registration or ProtoFreeze or Tracer"` + server smoke + `bin/make proto test` | ❌ W0 | ⬜ pending |
| STK-02 | 04-01 T3, 04-02 T1-T3 | `galago` owner lock; same-endpoint reuse; close-first; `mcp` holder → NOT_READY naming holder, no network; closed port / missing creds fail; no credential leak; no `.mcp` import; SHA pin | integration + AST | `-k "StackOwned or ConfigureOwnership or ConfigureFails or ConfigureWarning or ConfigureLedgerDir or AdapterInvariant or RequirementsPin"` | ❌ W0 | ⬜ pending |
| STK-03 | 04-01 T3, 04-03 T2 | Each read calls exactly one core method; SUCCESS, empty message, meta == `to_dict()`; order and duplicates preserved | unit | `-k "Tracer or ReadCommands or OneToOne"` | ❌ W0 | ⬜ pending |
| STK-04 | 04-03 T1, 04-04 T3 | `GetTransferEstimate` → `estimate_transfer` once; `Estimate<Cmd>` constants, no I/O | unit | `-k "TransferEstimate or Estimates"` | ❌ W0 | ⬜ pending |
| STK-05 | 04-02 T3, 04-04 T2, 04-05 T1-T2 | Reads answer while BUSY (red first); motion serialised; not-configured → NOT_READY; real mode refuses Transfer/Ack | integration + AST | `-k "BusyReads or ReadCommandSet or NotConfigured or ReadBypassEdges or RealModeRefusals or AdapterInvariant"` | ❌ W0 | ⬜ pending |
| STK-06 | 04-04 T1-T3 | Simulated: no core, no lock, no ledger, adapter-arg checks in both modes | unit + integration | `-k "Simulated or CheckArgs"` | ❌ W0 | ⬜ pending |
| STK-07 | 04-01 T3, 04-03 T1, T3 | SUCCESS allowlist; every other kind → ERROR_FROM_TOOL one-line with kind/reason/guid (+ bounded hint) | unit | `-k "ResultMapping or TransferEstimate"` | ❌ W0 | ⬜ pending |
| SC 5 (safety) | 04-02 T3 | No forbidden core motion/ack call in `tools/stack/`; planted violations caught | AST | `-k AdapterInvariant` | ❌ W0 | ⬜ pending |
| D-09 | 04-02 T2 | One WARNING on a fresh real Configure about restart/latch | unit | `-k ConfigureWarning` | ❌ W0 | ⬜ pending |
| D-16 order | 04-05 T1 | `test(04-05)` commit precedes `feat(04-05)` | git | the git-log ordering command in 04-05 Task 1 | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `stack-automation-layer` installed at `ed8ce47` in the 3.10 venv via `git+file://` (human-action checkpoint)
- [ ] `interfaces/tools/grpc_interfaces/stack.proto` + three registration edits, then `bin/make proto`
- [ ] `tools/stack/__init__.py`, `tools/stack/requirements.txt`, `pyproject.toml` mypy override
- [ ] `tools/tests/stack_test.py` — skip guard, `_free_tcp_port`, in-process gRPC fixture, blocked-command helper, loopback net-guard
- [ ] Failing STK-05 test committed before the `ExecuteCommand` override (CONTEXT D-16)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Lock-holder text reaches the operator's Configure toast in galago-web | STK-02 | Needs galago-core with DEP-02 codegen (not in this repo) | After DEP-02: configure the STACK tool while stack-mcp holds the lock; the toast shows "already owned by mcp" |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
