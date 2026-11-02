# galago-tools (nikkopg fork) — F.A.S.T. & STACK adapters

## What This Is

The `nikkopg/galago-tools` fork of `sciencecorp/galago-tools`: Galago's gRPC tool servers, plus a
Formulatrix F.A.S.T. liquid-handler adapter (`tools/fast/`) and, from v2, a Formulatrix STACK
plate-mover adapter (`tools/stack/`). Each adapter maps Galago commands 1:1 onto its instrument's
shared core (`fast-mcp`'s `FastService`, stack-automation-layer's `StackService`), so Galago drives
each instrument through the same safety policy as that instrument's MCP agent. This GSD project
covers the adapters, the two-instrument workflow and their rollout; galago-core (the web app, queue
and run page) has its own GSD project.

## Core Value

An operator running an instrument step from Galago can always see what the instrument is doing and
recover it themselves. No adapter code path pauses, resumes, aborts, cancels, retries or
acknowledges on its own, and no adapter holds a copy of an instrument safety rule (each core owns
them). For the STACK: a step never sends a second transfer.

## Current State

**v1 Live Run Control shipped 2026-10-16** (3 phases, 18 plans; archive in
`.planning/milestones/`). Operator Pause/Resume/Abort reach an in-flight F.A.S.T. step, the adapter
reports live `run_state`, steps wait through pauses on the pinned core (`b30b38d`), and the stack
is proven live on the instrument. forb01 runs `galago-tools` at HEAD (incl. the CR-01 fix), core
`b30b38d` in the service `.venv`, and `galago-web` from galago-core's queue-fix build. Nothing is
pushed yet.

**Governing design:** `docs/specs/2026-10-12-galago-live-run-control-design.md`.
**Companion:** galago-core `.planning/` — "Live Run Control: queue & run page".

## Current Milestone: v2 STACK Tool & STACK↔F.A.S.T. Handoff

**Goal:** Galago drives the Formulatrix STACK plate mover through the frozen stack-automation-layer
core, and one Galago workflow hands a plate between the STACK and the F.A.S.T.

**Target features:**
- GAL-01: `tools/stack/` gRPC tool, 1:1 with the core's allowlisted intents — Transfer
  (`plan_transfer` → `execute_transfer` → wait to a terminal result; starting the run is the
  approval), reads (manager state, robot states, devices, labware profiles, labware presence),
  EstimateDuration, and an operator-only AcknowledgeFailure (`"yes"` arm-inspected decision)
- F5 guard: Transfer carries a required `step_key`; a persisted key→guid ledger means a re-executed
  step re-attaches (`wait_transfer`) to its original guid and never submits again
- Every non-`ran` core result (rejected/needsInput/refused/readFailed/lost/failed/aborted/
  cancelled/timedOut) maps to a Galago error response, never SUCCESS
- Simulation mode, a simulated workcell run, and a supervised, runbook-gated live run
- GAL-02: a Galago workflow — STACK moves a plate from a nest/hotel onto the F.A.S.T. deck, the
  F.A.S.T. runs its transfer, STACK moves the plate back

**Carried v1 candidates (not in v2 scope unless pulled in):** WR-02 strict `_is_no_error`; adapter
refusal of `Configure` mid-run; hard pause (D5); pushing branches (user's action).

## Requirements

### Validated

<!-- Pre-v1 items shipped on feat/fast-tool; v1 items tagged. -->

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

- ✓ ADP-01..ADP-10: adapter control path (soft-only Pause, lock-free/gate-bypassing `ExecuteCommand`
  override, two-path Resume, `StatusReply.run_state`, fail-closed decisions, extended no-auto-abort
  invariant, real-mode concurrency test, simulated-mode control commands and pause hook) — v1
- ✓ LIVE-01..LIVE-03: `Transfer`/`RunProtocol` wait through pauses on the re-pinned fast-mcp core
  (`b30b38d`), paused time excluded from the timeout — Phase 2 (re-verified after gap-closure
  plan 02-05 fixed CR-01: crash-recovery `Resume` now gates its wait on `_accepted()`) — v1
- ✓ LIVE-04: Deployed in the safe order (core → service `.venv` → `galago-tools` restart →
  `galago-web` rebuild), no window with a new UI against an ungated core — v1
- ✓ LIVE-05: Supervised live deck-3-empty scenario — pause prompt names the deck/plate, operator
  fixes the deck and resumes, the same step ends SUCCESS — v1
- ✓ LIVE-06: Supervised live Pause → Resume → SUCCESS, and Pause → Abort → "aborted by operator at
  `<p>`%" with the queue FAILED — v1
- ✓ LIVE-07: Supervised live `galago-web` restart mid-run, operator recovers through the tool page — v1

- ✓ STK-01..STK-07: STACK gRPC tool registered with `Transfer`-in-flight reads, estimate, simulated
  mode, and success/failure result mapping — Phases 4–5 (v2)
- ✓ XFR-01..XFR-06: F5-safe Transfer — step-key ledger on the DEP-01 core (`934a621`), re-attach
  instead of re-submit, no adapter-initiated retries — Phase 5 (v2)
- ✓ ACK-01..ACK-02: Operator acknowledge of a latched core failure with visible guid — Phase 5 (v2)
- ✓ FLOW-01..FLOW-04: GAL-02 STACK → F.A.S.T. → STACK handoff in full simulation plus real-mode
  STACK against the loopback PAC simulator; forced re-dispatch of a completed step sends no second
  transfer — Phase 6 (v2)

### Active

v2 requirements in `.planning/REQUIREMENTS.md` (v1 traceability:
`.planning/milestones/v1-REQUIREMENTS.md`).

- [ ] Supervised live STACK deployment & run (LIVE-08..LIVE-10) — safe-order deploy on `stack2-6`,
  runbook-gated live STACK Transfer, supervised live GAL-02 handoff on hardware

### Out of Scope

- Software-initiated pause/resume/abort (on error, timeout, cancel, restart or reconnect) — every
  recovery action is an operator decision (design §7)
- Hard pause — the instrument API's `hardPause` is undocumented; deferred until the F.A.S.T. team
  confirms its behaviour (D5)
- Editing `tools/base_server.py` — shared by every tool type; the F.A.S.T. adapter overrides instead
- Upstream PRs to `sciencecorp/galago-tools` — fork-only; upstream cannot reach the private GitLab
  core dependency
- galago-core F5 (queue re-ran one transfer 3 times) and F3 (run UI hides tool errors) — tracked
  debt, out by user decision (2026-10-12); v2 defends against F5 inside the STACK adapter instead
- STACK safe-position and cancel from Galago — operator actions outside Galago for v2, the same way
  fast-mcp kept cancel out of Galago
- Fixing stack-automation-layer core gaps in this repo — a gap found here stops the work and is
  fixed in stack-automation-layer via `/gsd-quick`

## Context

- **Shipped v1** (2026-10-16): adapter + tests ~5,000 LOC Python across `tools/fast/server.py`,
  `tools/tests/fast_test.py`, `scripts/fast_status.py`, `scripts/fast_dryrun.py`.
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
  unittest, pytest. Last green: 147 tests (2026-10-16).
- **Deployment rule:** install the core into `.venv` first, restart `galago-tools`, then rebuild
  `galago-web` — an older core has no state gate on abort/resume and the adapter adds none.
- **Research:** `.planning/research/` (copied from the fast-mcp planning, 2026-10-12; cross-repo).
- **Planning history:** this milestone was first drafted in fast-mcp's `.planning/` and moved here
  on 2026-10-12 so each repo plans its own changes.
- **Deploy order (Phase 3):** core into the service `.venv` → restart `galago-tools` → rebuild
  `galago-web`; never rebuild `galago-web` before the core/adapter restart (an older core has no
  state gate on abort/resume and the adapter adds none).
- **galago-tools manager caveat:** the manager page on `:8081` can restart an individual tool server
  (e.g. F.A.S.T. on `:40001`) without restarting the `galago-tools` service itself. That overwrites
  `F.A.S.T.log` in place, so any no-restart / log-coverage check must track the tool-server listener
  PID, not just the `galago-tools` service MainPID.
- **Open debt carried forward (not milestone-blocking):**
  - WR-02 (`_is_no_error`'s loose `in (None, 0)` check, medium, reporting only) — v2 debt; Phase 3
    review WR-01 (dry-run harness race, dev-only) and info items stay open —
    `.planning/milestones/v1-phases/03-deploy-supervised-live-acceptance/03-REVIEW-DISPOSITION.md`.
  - Phase 1 review WR-02/WR-03 and info items (dev-only `scripts/fast_dryrun.py`) remain open.
  - galago-core observations (out of this repo's scope, not fixed here): run-page Gantt bar keeps
    drawing past an abort; "Connect all tools" sends empty configs to tools; "Item N not found" when
    the queue is cleared mid-abort; F.A.S.T. tool-page status can render stale after a reconnect.
  - Branches are not pushed (deferred D-02): pushing is the user's own action. Per local setup notes,
    push only to the `nikkopg` fork remote.

- **STACK core (v2):** stack-automation-layer (GitLab `nikkopg/stack-automation-layer`, branch
  `feat/initial-layer`, local clone `~/data/nikko/stack-automation-layer`). **Pinned at
  `934a621ece116a8b263897c1e9b62b57374f4ef3`** (DEP-01, 2026-10-29; `tools/stack/requirements.txt` and
  the pin test's `_PINNED_CORE_SHA`); Phase 4 was built on `ed8ce47`. Result contract v1 is
  frozen (`CONTRACT_VERSION = 1`, 2026-10-28, after the supervised hardware run); any key/type change
  is a version bump plus an adapter migration. Its `.planning/PROJECT.md` is gitignored and was not
  available on forb01 when v2 was scoped — CLAUDE.md, `docs/runbooks/stack-validation.md` and the
  code were read instead.
- **STACK hardware facts (runbook Part B):** manager `10.150.1.125:5005` (hostname `stack-server`),
  robot `stack2-6`, nests `nest-1/deck1/A1`, `orange-nest/deck1/A1`, `rack/l1/A1`; build
  `0.12.0-beta.1+1157`. Estimates run ~1.7x conservative on hardware. A second valid submit is
  **accepted and queued**, not refused — only the core's in-flight and robot-idle gates stop a
  double-queued motion, and those cover only a task still in flight (hence the step-key ledger).
- **STACK core semantics the adapter depends on:** plan ids are in-memory, single-use, TTL-bound;
  the owner lock is per host string + per-user lock dir (`STACK_MCP_LOCK_DIR`), owners `mcp` |
  `galago`. Since `934a621` the failure latch, acknowledged guids, owned tasks and in-flight guard are
  persisted per manager endpoint (not per owner) in `$STACK_STATE_DIR` or
  `~/.local/state/stack-automation-layer`, so they survive a restart and a galago <-> mcp hand-over;
  a bad state file or failed save fails closed on a `state-<hex>` latch; `latch_status()` is a
  zero-I/O read of the latch. Two limits remain: a process death between STACK accepting a POST and
  the state save loses that task's ownership (its failure will not latch), and a task that finished
  without a latch is foreign after a restart — so a restart mid-transfer means "inspect the arm".
  Never delete the state file (missing reads as a clean start).

## Constraints

- **Python 3.10** — the fork runtime (D-01); the gate runs on 3.10.12
- **Core-only dependency** — `fast-mcp` pinned by SHA in `tools/fast/requirements.txt`, no `[mcp]`
  extra; the adapter imports nothing from `fast_mcp.mcp`
- **No motion in default tests** — live checks are supervised, operator at the instrument, e-stop
  within reach, and never run without the operator's explicit go-ahead
- **Physical decisions explicit** — `"yes"`/`"no"` strings, never bools with defaults
- **ts-proto 1.151.1** for galago-core codegen of any proto change here (the local 1.153.2 breaks
  `tool_base.ts`)
- **STACK core-only** — stack-automation-layer pinned by SHA, no `[mcp]` extra, nothing imported
  from `stack_automation_layer.mcp`; the service opened only via `composition.open_service(...,
  owner="galago")`; credentials only from `STACK_USER`/`STACK_PASSWORD`; bind only to contract v1
  `to_dict()` shapes
- **STACK single owner** — the tool holds the `galago` lock; stack-mcp (Claude Desktop) must be
  closed during Galago runs; both front ends use the identical host string and lock dir
- **No automatic motion retry** — a STACK motion is submitted at most once per step key; a core
  rejection never reaches the arm
- **STACK live motion** — only in a supervised, runbook-gated session with the user present; real
  hardware is the default target, so the default test suite sends no STACK motion

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Plan the Galago side per repo (this repo: adapter + rollout; galago-core: queue + UI) | Clearer separation; each repo plans the code it changes | Shipped — adapter + rollout here (Phases 1-3), galago-core's queue + run page in its own `.planning/` |
| D1 run state via additive `StatusReply.run_state` Struct | Reuses the existing GetStatus heartbeat; other tools unaffected | Shipped — ADP-05, Phase 1 |
| D5 soft pause only | `hardPause` undocumented | Shipped — ADP-01, Phase 1; hard pause remains a Future Requirement |
| Override `ExecuteCommand` in `FastServer` instead of editing `base_server.py` | `base_server.py` is shared by every tool type | Shipped — ADP-02, Phase 1; `tools/base_server.py` confirmed unchanged through Phase 3 close-out |
| Live acceptance owned here | This repo is the integration owner for the F.A.S.T. | Shipped — Phase 3: LIVE-04..07 all PASS on the instrument, D-13 evidence in `03-ACCEPTANCE.md` |
| Deploy order: core → `galago-tools` → `galago-web` | An older core has no state gate on abort/resume and the adapter adds none; rebuilding the UI first risks a window where the new UI runs against an ungated core | Shipped — LIVE-04, Phase 3; four strictly increasing UTC timestamps recorded in `03-DEPLOY.md` |
| D-14 FAIL→fix→rerun cycles handled by stop/fix/gate/redeploy/rerun, never silent pass | Live defects found on real hardware must be fixed and re-verified, not worked around in the evidence record | Found and fixed three real defects live: galago-core's `pausePrompt` rendered the no-plate sentinel as literal `"-1"`; this repo's adapter appended a spurious `": NoError (0)"` suffix to the operator-abort wording (fixed `201d987`); galago-core's queue re-ran operator-aborted or `galago-web`-restart-orphaned steps (fixed by galago-core quick tasks `261015-h0q` and `261015-o44`, each live-verified) |
| galago-tools manager (`:8081`) can restart a tool server without a service restart | Operators may use the manager page directly, outside the deploy runbook | Overwrites `F.A.S.T.log` in place; any no-restart or log-coverage check must track the tool-server listener PID, not the `galago-tools` service MainPID (confirmed during Phase 3's Safety invariant audit) |
| Re-verify stale phases before closing; redeploy CR-01 without a live rerun | Verification went stale after the 02-05 fix; logs showed LIVE-07 used the in-flight Resume path, which CR-01 did not touch | ✓ Good — forb01 at HEAD 2026-10-16, Phase 3 re-verified `passed` |
| v2: starting the Galago run is the approval for a STACK Transfer (plan → execute → wait in one command) | The core's plan id is in-memory, single-use and TTL-bound — unusable across workflow steps; operator-initiated runs already approve F.A.S.T. transfers | — Pending |
| v2: AcknowledgeFailure is an operator-only Galago command with a `"yes"` arm-inspected decision | The failure latch lives in the Galago tool process; stack-mcp can't take the lock to acknowledge, and a restart clears the latch, which the runbook forbids | — Pending |
| v2: F5 defence is a persisted `step_key` → guid ledger in the STACK adapter | STACK queues a second submit; the core's in-flight guard misses a re-execution after the first task finished; works regardless of galago-core | — Pending |
| v2: three-way split aligned with F.A.S.T. — this repo: adapter, GAL-02 runbook protocol, live acceptance; galago-core (own parallel milestone): codegen + forms, operator Ack control (D-20 pattern), F3, F5 root cause; stack-automation-layer: G1-G3 via one `/gsd-quick` | Mirrors how F.A.S.T. shipped (galago-core `128bbd7`, `d4c3c23`); G1 (latch lost on restart) is a core gap | — Pending |
| v2: research only what is new (STACK proto, galago-core two-tool workflow); skip the 4-researcher pass | `tools/fast/` is the template | — Pending |
| Claude may send `Configure` only on the user's explicit request with no run in flight | User asked Claude to reconnect after the 2026-10-16 redeploy; the operator-only rule had no code backstop | ⚠️ Revisit — logged exception (T-03-05/T-03-08); add an adapter-side mid-run `Configure` refusal |

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
*Last updated: 2026-11-02 after Phase 6*
