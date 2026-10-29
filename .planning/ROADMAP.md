# Roadmap: galago-tools (nikkopg fork) — F.A.S.T. & STACK adapters

## Milestones

- ✅ **v1 Live Run Control** — Phases 1-3 (shipped 2026-10-16) — [archive](milestones/v1-ROADMAP.md)
- 🚧 **v2 STACK Tool & STACK↔F.A.S.T. Handoff** — Phases 4-7 (in progress)

## Phases

<details>
<summary>✅ v1 Live Run Control (Phases 1-3) — SHIPPED 2026-10-16</summary>

- [x] Phase 1: Adapter Control Path & Run State (5/5 plans) — completed 2026-10-13
- [x] Phase 2: Wait Through Pauses on the Pinned Core (5/5 plans) — completed 2026-10-15
- [x] Phase 3: Deploy & Supervised Live Acceptance (8/8 plans) — completed 2026-10-15

</details>

### 🚧 v2 STACK Tool & STACK↔F.A.S.T. Handoff (In Progress)

**Milestone Goal:** Galago drives the Formulatrix STACK plate mover through the frozen
stack-automation-layer core (contract v1), and one Galago workflow hands a plate between the STACK
and the F.A.S.T. Research: `.planning/research/SUMMARY.md`.
Companion: galago-core's own parallel milestone (codegen, command forms, operator UI).

**Hard constraints (every v2 phase):**
- No STACK motion in the default test suite; tests run on fakes, `MagicMock(spec=StackService)`, a
  closed port, or temp lock dirs.
- Live STACK motion happens only in Phase 7, in a supervised, runbook-gated session with the user
  present and the operator's explicit go-ahead.
- Nothing targets `10.150.1.125` / `stack-server` before Phase 7. Phases 4-6 use mocks, a closed port,
  or the loopback PAC simulator only.
- No adapter code path retries motion, cancels, goes to the safe position, or acknowledges a failure
  on its own; a STACK motion is submitted at most once per step key.
- Claude sends `Configure` only on the user's explicit request with no run in flight.

- [x] **Phase 4: STACK Tool Registration, Reads & Estimate** - Register the STACK tool type and let an (completed 2026-10-29)
  operator Configure it, read instrument state and get a transfer estimate, with no path that can move
  the arm.
- [ ] **Phase 5: F5-safe Transfer & Operator Acknowledge** - The only motion path: a `Transfer` that
  can never send a second transfer for the same step, plus an operator-only failure acknowledge.
- [ ] **Phase 6: GAL-02 Workflow, Simulated Workcell & PAC-Simulator Run** - Prove the STACK ->
  F.A.S.T. -> STACK handoff end to end, and that a re-dispatch sends nothing, before any hardware.
- [ ] **Phase 7: Deploy & Supervised Live STACK + Handoff** - Deploy in the safe order, then prove a
  live STACK Transfer and the live handoff on the instrument with the user present.

## Phase Details

### Phase 4: STACK Tool Registration, Reads & Estimate

**Goal**: An operator can register, Configure and read from a STACK tool in Galago (manager state,
robots, devices, profiles, labware presence and a transfer estimate), and no real-mode code path can
move the arm.
**Depends on**: Nothing in this milestone (builds on v1's `tools/fast/` as the template; the core is
pinned by SHA, no cross-repo gate). Its `stack.proto` is the input to DEP-02.
**Requirements**: STK-01, STK-02, STK-03, STK-04, STK-05, STK-06, STK-07
**Success Criteria** (what must be TRUE):
  1. `stack.proto` is registered (`tool_base` Command `stack = 24`, Config `stack = 43`;
     `controller.proto` `stack = 24`), `bin/make proto test` is green, and `python -m tools.stack.server
     --port=N` starts a tool server that reports as the `stack` tool type.
  2. An operator can Configure the STACK tool with host/port: the tool opens the core only through
     `composition.open_service(..., owner="galago")` with credentials from `STACK_USER`/`STACK_PASSWORD`
     and no `lock_dir` field; a lock held by stack-mcp fails Configure with a message naming the
     holder; a test proves nothing from `stack_automation_layer.mcp` is imported and the core is
     pinned by SHA.
  3. An operator can read manager state, robot states, devices, labware profiles, transfer profiles
     and labware presence: each is SUCCESS with an empty message and the core's contract v1
     `to_dict()` in the reply meta; a core `readFailed` (or any non-read kind) is `ERROR_FROM_TOOL`
     with a one-line reason and guid, never SUCCESS, and adapter argument errors are
     `INVALID_ARGUMENTS`.
  4. An operator can get a transfer estimate (`GetTransferEstimate`) and nothing moves; in
     simulated mode, commands validate their arguments (including `step_key`), sleep the constant
     `Estimate<Cmd>` value, never contact the core and never write the ledger.
  5. A read issued while another command holds the tool BUSY returns its result instead of NOT_READY
     (exercised with an injected slow command, since `Transfer` lands in Phase 5) while motion
     commands stay serialised; in real mode `Transfer` and `AcknowledgeFailure` are refused with a
     clear not-yet-available error, and a test proves nothing in `tools/stack/` calls the core's motion
     methods.
  6. `stack.proto` is frozen for v2 in this phase: it declares the full v2 command surface, including
     `Transfer`, `AcknowledgeFailure` and the latch-status read (real-mode handlers refused until
     Phase 5), so galago-core's DEP-02 codegen runs once; a later proto change in v2 is a deviation
     that re-opens DEP-02 and needs the user's sign-off.
**Plans:** 5/5 plans complete (waves 1-5, sequential: every plan touches `tools/stack/server.py` and `tools/tests/stack_test.py`)

Plans:
**Wave 1**
- [x] 04-01-PLAN.md — Core install gate, proto-freeze decision, register `stack` and read manager state end to end (STK-01)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 04-02-PLAN.md — Configure ownership lifecycle, failure surfaces, restart warning, SHA pin and AST no-motion/no-MCP invariant (STK-02, SC 5)

**Wave 3** *(blocked on Wave 2 completion)*
- [x] 04-03-PLAN.md — Transfer estimate, the remaining reads, 1:1 surface and exhaustive result mapping (STK-03, STK-04, STK-07)

**Wave 4** *(blocked on Wave 3 completion)*
- [x] 04-04-PLAN.md — Simulated mode, adapter-argument checks, real-mode refusals and constant estimate hooks (STK-06, STK-04, SC 5)

**Wave 5** *(blocked on Wave 4 completion)*
- [x] 04-05-PLAN.md — Reads answer while BUSY via the ExecuteCommand override, test-first (STK-05)

**Notes**: Proto freeze made binding by the user at roadmap approval (2026-10-28). Message names must avoid `GetStatus`,
`EstimateDuration`, `Configure`, `ExecuteCommand` and any `Estimate*` prefix. Research flag: none
(fast precedent). DEP-02 can start as soon as this phase's proto is on the branch.

### Phase 5: F5-safe Transfer & Operator Acknowledge

**Goal**: A workflow step moves a plate through the STACK exactly once per step key, an operator can
see and clear a core failure latch from Galago, and re-running, re-dispatching or restarting the tool
can never send a second transfer.
**Depends on**: Phase 4 **and** cross-repo **DEP-01** (stack-automation-layer G1-G3, one bundled
`/gsd-quick`: restart-surviving latch/ownership/in-flight guard with a re-attached guid adopted,
latch-status read, latch set before the explanation build; new core SHA and contract-version
decision). **DEP-01 landed 2026-10-29 as core `934a621`** (contract still v1, `latchStatus` additive);
the fork already pins it (`237268c`), so this phase starts on that pin. Remaining core limits and the
re-checked research: `.planning/research/SUMMARY.md` § Addendum (2026-10-29).
**Requirements**: XFR-01, XFR-02, XFR-03, XFR-04, XFR-05, XFR-06, ACK-01, ACK-02
**Success Criteria** (what must be TRUE):
  1. A workflow step `Transfer` runs `plan_transfer` -> `execute_transfer` -> wait to a terminal
     result in one command (starting the run is the approval) and ends SUCCESS only when the core
     reports `ran`; every other terminal kind is `ERROR_FROM_TOOL` with reason and guid; a blank
     `step_key` is `INVALID_ARGUMENTS` before any core call.
  2. Re-running a step with the same `step_key` never submits: with a recorded guid it re-attaches
     (`wait_transfer`), with a recorded `ran` it replays SUCCESS, after an ambiguous submit it
     refuses; the same key with a different request is `INVALID_ARGUMENTS`; this holds after a
     tool-server restart because the ledger (key + request fingerprint, write-ahead `submitting`
     record, then guid, then terminal outcome) is persisted atomically. A restart during a transfer
     is reported as needing arm inspection, never replayed as SUCCESS (core `934a621` can lose that
     task's ownership if it died between the POST and its state save).
  3. An outcome that proves nothing was sent (`refused`/`rejected`/`needsInput`/`readFailed`)
     releases the key so the operator can fix the cause and re-run the step; a `TimedOut` leaves the
     arm running and is reported as an error, and re-running the same step re-attaches and finishes it.
  4. An AST invariant with planted violations fails if the adapter calls `start_transfer`,
     `cancel_transfer` or `go_to_safe_position`, or calls `execute_transfer` more than once per key,
     so no adapter path retries motion.
  5. An operator can see the latched guid (in the error message and via `GetFailureLatch`, bound
     1:1 to the core's `latch_status()`, including the `submit-<hex>` case after an ambiguous submit
     and the `state-<hex>` case after an unreadable or unsaved core state file) and clear the latch with
     `AcknowledgeFailure(guid, arm_inspected)`: only the exact string `"yes"` reaches
     `acknowledge_failure(guid, confirm=True)`, anything else is `INVALID_ARGUMENTS` with no core
     call, and no adapter path acknowledges on its own.
**Plans:** 2/7 plans executed (waves 1-6; 05-03 and 05-04 run in parallel in wave 3, every other plan is sequential on `tools/stack/server.py` / `tools/tests/stack_test.py`)

Plans:
**Wave 1**
- [x] 05-01-PLAN.md — D-01 design spike `05-SPIKE.md` against core 934a621: answers, amendments A-1/A-2, resolved open questions, binding ledger contract (XFR-03, XFR-04, ACK-02)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 05-02-PLAN.md — Tracer: fresh-path Transfer through a write-ahead step ledger (`tools/stack/ledger.py`), Phase 4 test migration, then the XFR-05 call-site AST rules (XFR-01, XFR-02, XFR-05)

**Wave 3** *(blocked on Wave 2 completion; the two plans share no files)*
- [ ] 05-03-PLAN.md — Pure ledger: storage contract tests, `decide()` state machine and transitions, test first (XFR-02, XFR-03, XFR-04)
- [ ] 05-04-PLAN.md — `GetFailureLatch` 1:1 `latch_status()`, operator-only `AcknowledgeFailure` behind an exact "yes", latch guid in Transfer errors (ACK-01, ACK-02, XFR-05)

**Wave 4** *(blocked on Wave 3 completion)*
- [ ] 05-05-PLAN.md — Release a key only when nothing was sent, outcomeUnknown with the latch guid, Transfer hardening (D-03/D-04/D-11/D-12) (XFR-04, XFR-02, ACK-02)

**Wave 5** *(blocked on Wave 4 completion)*
- [ ] 05-06-PLAN.md — `decide()` wired into Transfer: replay, refusals, mismatch, read-only re-attach, timedOut, restart (XFR-03, XFR-06)

**Wave 6** *(blocked on Wave 5 completion)*
- [ ] 05-07-PLAN.md — Never-resend behavioural matrix, STK-05 re-proven on the real Transfer, final gate (XFR-05, XFR-03, ACK-01)

**Notes**: Highest-risk phase; open with a short design spike on ledger semantics against core
`934a621` before planning — in particular how a re-attach after a mid-transfer restart (core limit 1:
the task may have become foreign, so its failure would not latch) is reported. `GetFailureLatch`
binds to `latch_status()` and `latchStatus` joins `_SUCCESS_KINDS`. Settle at plan time: replay-window value, default ledger path
(per-user state dir, not tmp), retention, and whether `ListTransferProfiles`-style extras are needed.
Carry-over check: re-prove STK-05 (reads answer while a real `Transfer` is in flight) on the real
motion path. All tests use a fake or mocked core; no motion.

### Phase 6: GAL-02 Workflow, Simulated Workcell & PAC-Simulator Run

**Goal**: The STACK -> F.A.S.T. -> STACK plate handoff runs end to end in simulation, and a forced
re-dispatch of a completed STACK step is shown to send no second transfer, with no real instrument
involved.
**Depends on**: Phase 5 **and** cross-repo **DEP-02** (galago-core milestone: submodule bump, ts-proto
1.151.1 regeneration, `commandFields.stack` without acknowledge). FLOW-01 (authoring the protocol and
the offline half of FLOW-03) can start before DEP-02 lands; FLOW-02..04 need it.
**Requirements**: FLOW-01, FLOW-02, FLOW-03, FLOW-04
**Success Criteria** (what must be TRUE):
  1. A script-mode GAL-02 protocol exists as importable JSON beside its runbook: it mints a per-run
     `step_key` for each STACK step, takes the nest/hotel triples as parameters, and runs STACK
     nest/hotel -> F.A.S.T. deck, the F.A.S.T. transfer, then STACK back.
  2. A fully Galago-simulated workcell run of GAL-02 (both tools in simulated mode) completes all
     three steps.
  3. A forced re-dispatch of an already-completed STACK step sends no second transfer: proven offline
     against a fake core (the recorded submit count stays at one) and re-exercised in a simulated run.
  4. An operator-run GAL-02 with the STACK tool in real mode against the loopback PAC simulator
     (runbook Part A preconditions, sim account credentials, sim lab names) and the F.A.S.T. simulated
     completes, including a forced re-dispatch that sends no second POST; it never targets
     `10.150.1.125` / `stack-server`.
**Plans**: TBD
**Notes**: Research flag: confirm Docker and the PAC simulator build can run on the galago-tools host
(the sim publishes on loopback only, so the tool server must run on that host with the sim account in
its environment). The F.A.S.T. has no simulator in scope, so "simulated" there means Galago-simulated.
Galago-simulated mode never writes the ledger, so the substantive no-second-transfer proof for FLOW-03
is the fake-core test plus FLOW-04's real-mode PAC run; clarify at plan time what the "simulated run"
half of FLOW-03 asserts.

### Phase 7: Deploy & Supervised Live STACK + Handoff

**Goal**: The STACK tool is deployed in the safe order and proven on the real STACK: a supervised live
Transfer, then a supervised live STACK -> F.A.S.T. -> STACK handoff, with the user present.
**Depends on**: Phase 6 (DEP-02's galago-core build is deployed as part of this phase). **DEP-03**
(galago-core operator AcknowledgeFailure control, F3 tool-error display, F5 root cause) is
recommended before live runs for the full operator experience but is not a hard gate.
**Requirements**: LIVE-08, LIVE-09, LIVE-10
**Success Criteria** (what must be TRUE):
  1. The stack is deployed in the safe order (core into the service `.venv` -> restart `galago-tools`
     -> rebuild `galago-web`), with stack-mcp closed during Galago runs and both front ends using the
     identical host string and lock dir.
  2. A supervised, runbook-gated live STACK `Transfer` reaches `ran` on `stack2-6` (manager
     `10.150.1.125:5005`) with the user present and the operator's explicit go-ahead.
  3. A supervised live GAL-02 handoff runs STACK -> F.A.S.T. -> STACK to SUCCESS on the hardware.

**Plans**: TBD
**Notes**: Runbook authoring, not research. This is the only phase that may send live STACK motion or
target `10.150.1.125` / `stack-server`. Back up logs before any restart; the manager page can restart a
single tool server without a service restart, so track the tool-server listener PID, not only the
service MainPID.

## External Gates (cross-repo, not requirements)

DEP-01..03 are built elsewhere and tracked here as gates on the phases above. They are not mapped to a
phase as requirements.

| Gate | Built in | What it delivers | Gates | Status |
|------|----------|------------------|-------|--------|
| DEP-01 | stack-automation-layer (one bundled `/gsd-quick`) | G1 latch/ownership/in-flight guard survive a restart and a re-attached guid is adopted; G2 latch-status read; G3 latch set before the explanation build; new SHA and a contract-version decision | Phase 5 (XFR-*, ACK-*) — hard gate | **Done** 2026-10-29: `934a621ece116a8b263897c1e9b62b57374f4ef3`, contract v1 kept; pinned in the fork (`237268c`) |
| DEP-02 | galago-core milestone | Submodule bump, ts-proto 1.151.1 regen, `commandFields.stack` without acknowledge; consumes Phase 4's `stack.proto` | Phase 6 (FLOW-02..04) and Phase 7 (LIVE-*) — hard gate | Not started |
| DEP-03 | galago-core milestone | Operator AcknowledgeFailure control (D-20 pattern), F3 tool-error display, F5 root cause | Phase 7 — recommended, not a hard gate | Not started |

A core gap found while building here stops the work and is fixed in stack-automation-layer via
`/gsd-quick`; it is never patched in this repo.

## Progress

**Execution Order:**
Phases execute in numeric order: 4 → 5 → 6 → 7 (DEP-01 is met, so Phase 5 can start; Phases 6-7 wait on DEP-02)

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 4. STACK Tool Registration, Reads & Estimate | v2 | 5/5 | Complete    | 2026-10-29 |
| 5. F5-safe Transfer & Operator Acknowledge | v2 | 2/7 | In Progress | - |
| 6. GAL-02 Workflow, Simulated Workcell & PAC-Simulator Run | v2 | 0/TBD | Not started | - |
| 7. Deploy & Supervised Live STACK + Handoff | v2 | 0/TBD | Not started | - |

## Backlog

(none)
