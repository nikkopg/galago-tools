# Phase 6: GAL-02 Workflow, Simulated Workcell & PAC-Simulator Run - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-11-02
**Phase:** 6-GAL-02 Workflow, Simulated Workcell & PAC-Simulator Run
**Areas discussed:** DEP-02 gate and plan split, Protocol artifact, Step-key minting, FLOW-03 simulated-half meaning, Protocol harness, PAC-sim run setup, Forced re-dispatch method
**Mode:** `--auto`. Every area was auto-selected and resolved with the recommended option. No questions were asked.

---

## DEP-02 gate and plan split

| Option | Description | Selected |
|--------|-------------|----------|
| Two parts: autonomous Part 1 now, DEP-02-gated operator Part 2 | Precondition check stops as blocking-human | ✓ |
| Wait for DEP-02 before planning anything | Idle until galago-core Phase 5 lands | |
| Drive the tool servers without galago-core | Bypass the queue for FLOW-02..04 | |

**Choice:** [auto] Two parts (recommended). The scout found galago-core Phase 5 not started, and the
roadmap allows FLOW-01 + offline FLOW-03 before DEP-02.

## Protocol artifact

| Option | Description | Selected |
|--------|-------------|----------|
| `docs/runbooks/gal-02-handoff.{md,protocol.json}`, exact galago-core export format | Importable without edits | ✓ |
| Protocol under `tools/stack/` | Next to the adapter code | |

**Choice:** [auto] docs/runbooks (recommended; "beside its runbook" per FLOW-01).

## Step-key minting

| Option | Description | Selected |
|--------|-------------|----------|
| `batch_label + ISO timestamp + random hex`, `-in`/`-out` suffixes | Run-unique, stable once queued | ✓ |
| Operator-entered key parameter | Reuse risk (Pitfall 1) | |
| Timestamp only | Collision if two runs are queued in the same ms | |

**Choice:** [auto] Label + timestamp + random (recommended).

## Parameter defaults

| Option | Description | Selected |
|--------|-------------|----------|
| PAC-sim lab names as defaults | Safe by default; hardware names typed in Phase 7 | ✓ |
| No defaults | Operator must fill every triple | |
| Hardware names as defaults | Unsafe default | |

**Choice:** [auto] Sim names (recommended).

## FLOW-03 simulated-half meaning

| Option | Description | Selected |
|--------|-------------|----------|
| Sim re-dispatch returns SUCCESS and writes no ledger; no-second-transfer claim rests on the fake-core test + FLOW-04 | Honest about what sim mode can prove | ✓ |
| Claim the sim run proves no second transfer | Not provable: sim mode never writes the ledger | |

**Choice:** [auto] First option (recommended; resolves the roadmap note).

## Protocol harness

| Option | Description | Selected |
|--------|-------------|----------|
| Python test runs the script in `node` with a stub `galago`; skip with a reason if no node | Exercises the real script text | ✓ |
| Re-implement the script in Python | Drifts from the shipped JSON | |

**Choice:** [auto] node stub harness (recommended).

## PAC-sim run setup

| Option | Description | Selected |
|--------|-------------|----------|
| galago-tools host, loopback 127.0.0.1:5005, sim creds in env, sim-only ledger_dir, runbook hardware-refusal preflight | Matches SAL A.0 rules | ✓ |
| Separate sim host | Sim is loopback-only, so the tool server can't reach it | |

**Choice:** [auto] First option (recommended). Docker access was confirmed on the host; the PAC sim
images are not yet built.

## Forced re-dispatch method (FLOW-04)

| Option | Description | Selected |
|--------|-------------|----------|
| Re-send the stored in-leg params from the tool page within 600 s; sim task count = 1; one more re-send after the window | Shows both replay and refusal | ✓ |
| Try to reproduce F5 in dev mode | Not reproducible on demand | |

**Choice:** [auto] Tool-page re-send (recommended).

## Claude's Discretion

- Runbook layout and wording; F.A.S.T. parameter defaults from the v1 runbook.
- The node invocation style; whether the D-06 and D-08 tests share a module.

## Deferred Ideas

- A PAC-sim compose wrapper in this repo.
- Hardware presets for stack2-6 (Phase 7).
- Ledger backup rule (Phase 7).
