# galago-tools (nikkopg fork) — F.A.S.T. adapter

## What This Is

The `nikkopg/galago-tools` fork of `sciencecorp/galago-tools`: Galago's gRPC tool servers, plus a
Formulatrix F.A.S.T. liquid-handler adapter (`tools/fast/`). The adapter maps Galago commands 1:1
onto the shared `fast-mcp` core (`FastService`), so Galago drives the instrument through the same
safety policy as the fast-mcp LLM agent. This GSD project covers the F.A.S.T. adapter and its
rollout; galago-core (the web app, queue and run page) has its own GSD project.

## Core Value

An operator running a F.A.S.T. step from Galago can always see what the instrument is doing and
recover it themselves. No code path in the adapter pauses, resumes or aborts the instrument on its
own, and the adapter never holds a copy of an instrument safety rule (the fast-mcp core owns them).

## Current Milestone: v1 F.A.S.T. Live Run Control (adapter & rollout)

**Goal:** Pause, Resume and Abort reach a F.A.S.T. run while its Galago step is still in flight, the
adapter reports live run state to galago-core, a running step stays open through an instrument
pause, and the whole stack is proven live on the instrument.

**Governing design:** `docs/specs/2026-10-12-galago-live-run-control-design.md` (decisions D1-D6 in
§11; §5.1 carries the research correction about `base_server`'s BUSY gate).

**Companion milestone:** galago-core `.planning/` — "Live Run Control: queue & run page". It
consumes this repo's `run_state` proto (via its `vendor/galago-tools` submodule) and the control
commands. This repo's final phase (live acceptance) needs both milestones done.

**Target features:**
- Soft-only `Pause`; `Pause`/`Resume`/`Abort` that bypass the motion lock and `base_server`'s
  readiness gate through a `FastServer.ExecuteCommand` override, without touching `base_server.py`
- `StatusReply.run_state` (additive `google.protobuf.Struct`) with state, percent and pause info
- `Transfer`/`RunProtocol` waiting through pauses on the re-pinned core (paused time excluded from
  the timeout)
- Simulated-mode pause hook; extended no-auto-abort invariant; real-mode concurrency test
- Safe-order deploy and supervised live acceptance

## Requirements

### Validated

<!-- Shipped on feat/fast-tool before this milestone. -->

- ✓ F.A.S.T. tool type registered (`fast.proto`, `controller.proto`, `tool_base.proto`); adapter
  obtains `FastService` only through `fast_mcp.composition.open_service` under the single-owner lock
  (fast-mcp v1 Phase 5)
- ✓ Intent commands mapped 1:1 to `FastService`: Transfer, RunProtocol, ValidateProtocol,
  GetStatus, GetTipStatus, ScanTips, EjectTray; simulated mode validates arguments and sleeps a
  named estimate; supervised live transfer passed (GAL-05, 2026-10-09)
- ✓ Operator Abort/Resume as commands with required `"yes"`/`"no"` decisions (`return_liquid`,
  `is_tip_broken`); state gates in the core (`76f8c3f`); scoped no-auto-abort AST invariant with a
  planted-violation check; actionable Paused message (`ebc5bab`..`7c0ff7b`, 2026-10-09/12)
- ✓ Deployed on forb01: core in `.venv`, `galago-tools` systemd user service (manager on `:8081`,
  Tool Box on `:11010`, F.A.S.T. driver on `:40001` against `10.150.1.170:5003`)

### Active

See `.planning/REQUIREMENTS.md` (ADP-*, LIVE-*).

### Out of Scope

- Software-initiated pause/resume/abort (on error, timeout, cancel, restart or reconnect) — every
  recovery action is an operator decision (design §7)
- Hard pause — the instrument API's `hardPause` is undocumented; deferred until the F.A.S.T. team
  confirms its behaviour (D5)
- Editing `tools/base_server.py` — shared by every tool type; the F.A.S.T. adapter overrides instead
- Upstream PRs to `sciencecorp/galago-tools` — fork-only; upstream cannot reach the private GitLab
  core dependency
- galago-core F5 (queue re-ran one transfer 3 times) and F3 (run UI hides tool errors) — tracked
  debt, out by user decision (2026-10-12)

## Context

- **Repos:** this fork (branch `feat/fast-tool`), galago-core (branch `feat/fast-tool`, its
  `vendor/galago-tools` submodule points at this fork), and fast-mcp (GitLab `nikkopg/fast-mcp`,
  the core; branch `fix/run-recovery-gate` holds `76f8c3f` and the quick task `b30b38d`, not yet
  pushed — a clean install of a new pin needs that branch on GitLab).
- **Core API available now** (fast-mcp `b30b38d`): `RunOptions.through_pauses`,
  `on_pause(PauseInfo)`, `Paused.detail`, `ResumeMarker`, thread-safe `FastService`
  (`pause`/`resume`/`abort`/`status` callable from another thread while `wait` polls).
- **Key research finding:** `ToolServer.parseCommand` refuses every command while `status != READY`
  (`base_server.py:200`), `ExecuteCommand` sets BUSY for the whole command (`:236`) and resets READY
  in its `finally` (`:254`). Control commands need a `FastServer.ExecuteCommand` override; the
  existing concurrency test only runs simulated, where `isReady()` is always true.
- **Gate:** `bin/make proto test` on Python 3.10 (`~/data/nikko/.venvs/galago-py310`): ruff, mypy,
  unittest, pytest. Last green: 70 tests (2026-10-09).
- **Deployment rule:** install the core into `.venv` first, restart `galago-tools`, then rebuild
  `galago-web` — an older core has no state gate on abort/resume and the adapter adds none.
- **Research:** `.planning/research/` (copied from the fast-mcp planning, 2026-10-12; cross-repo).
- **Planning history:** this milestone was first drafted in fast-mcp's `.planning/` and moved here
  on 2026-10-12 so each repo plans its own changes.

## Constraints

- **Python 3.10** — the fork runtime (D-01); the gate runs on 3.10.12
- **Core-only dependency** — `fast-mcp` pinned by SHA in `tools/fast/requirements.txt`, no `[mcp]`
  extra; the adapter imports nothing from `fast_mcp.mcp`
- **No motion in default tests** — live checks are supervised, operator at the instrument, e-stop
  within reach, and never run without the operator's explicit go-ahead
- **Physical decisions explicit** — `"yes"`/`"no"` strings, never bools with defaults
- **ts-proto 1.151.1** for galago-core codegen of any proto change here (the local 1.153.2 breaks
  `tool_base.ts`)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Plan the Galago side per repo (this repo: adapter + rollout; galago-core: queue + UI) | Clearer separation; each repo plans the code it changes | — Pending |
| D1 run state via additive `StatusReply.run_state` Struct | Reuses the existing GetStatus heartbeat; other tools unaffected | — Pending |
| D5 soft pause only | `hardPause` undocumented | — Pending |
| Override `ExecuteCommand` in `FastServer` instead of editing `base_server.py` | `base_server.py` is shared by every tool type | — Pending |
| Live acceptance owned here | This repo is the integration owner for the F.A.S.T. | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-10-12 after project initialization (moved from fast-mcp planning)*
