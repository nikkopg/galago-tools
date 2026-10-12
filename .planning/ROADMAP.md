# Roadmap: galago-tools (nikkopg fork) — F.A.S.T. adapter

## Milestones

- 🚧 **v1 F.A.S.T. Live Run Control (adapter & rollout)** — Phases 1-3 (in progress)

## Phases

### 🚧 v1 F.A.S.T. Live Run Control (In Progress)

**Milestone Goal:** Pause, Resume and Abort reach a F.A.S.T. run while its Galago step is still in
flight, the adapter reports live run state, a running step stays open through an instrument pause,
and the stack is proven live. Governing design: `docs/specs/2026-10-12-galago-live-run-control-design.md`.
Companion milestone: galago-core "Live Run Control: queue & run page".

- [ ] **Phase 1: Adapter Control Path & Run State** - Control commands reach an in-flight run
  without touching the tool's status, `run_state` is reported, and the safety invariants and tests
  are extended, all proven against a mocked `FastService`.
- [ ] **Phase 2: Wait Through Pauses on the Pinned Core** - Re-pin to the wait-through-pauses core
  and keep `Transfer`/`RunProtocol` steps open through pauses, with paused time excluded from the
  timeout.
- [ ] **Phase 3: Deploy & Supervised Live Acceptance** - Deploy in the safe order once galago-core's
  milestone is done, then prove the deck-3, pause/resume, pause/abort and restart-mid-run scenarios
  on the instrument.

## Phase Details

### Phase 1: Adapter Control Path & Run State

**Goal**: An operator's Pause, Resume or Abort reaches the instrument while the step's Transfer is
still running, the tool reports live run state for galago-core to poll, and tests prove no code path
acts without the operator.
**Depends on**: Nothing in this milestone (builds on the shipped adapter; uses a mocked `FastService`)
**Requirements**: ADP-01, ADP-02, ADP-03, ADP-04, ADP-05, ADP-06, ADP-07, ADP-08, ADP-09, ADP-10
**Success Criteria** (what must be TRUE):
  1. A real-mode test sends Pause, Resume and Abort through `ExecuteCommand` while a `Transfer` is
     blocked: each reaches the (mocked) service, and the tool's status is still BUSY afterwards;
     `tools/base_server.py` is unchanged.
  2. `GetStatus` returns `run_state` with state, percent and pause info for the F.A.S.T., and
     other tool types return it unset; the proto change regenerates cleanly for Python.
  3. Blank or unclear decisions are `INVALID_ARGUMENTS` on every path, Pause is always soft, and
     Resume returns on acceptance with a run in flight but waits when there is none.
  4. The extended no-auto-abort invariant fails on a planted violation, and no instrument-state
     check exists in the adapter.
  5. In simulated mode, control commands return SUCCESS after argument checks and a test hook drives
     `run_state` to paused.
**Plans**: 2/5 plans executed (sequential waves 1-5; every plan edits `tools/fast/server.py` or `tools/tests/fast_test.py`)

Plans:
**Wave 1**
- [x] 01-01-PLAN.md — Pause tracer over gRPC, failing real-mode concurrency test (expected failure first), `ExecuteCommand` override, lock-free Pause/Abort, two-path Resume (ADP-01/02/03/08)

**Wave 2** *(blocked on Wave 1 completion)*
- [x] 01-02-PLAN.md — Resume's two paths, Pause mapping, fail-closed decisions, tool-type check, DRIVER_ERROR, no state checks on the control path (ADP-04/06/09)

**Wave 3** *(blocked on Wave 2 completion)*
- [ ] 01-03-PLAN.md — `StatusReply.run_state = 4`, run record, pause recorder, fail-safe health `GetStatus` (ADP-05)

**Wave 4** *(blocked on Wave 3 completion)*
- [ ] 01-04-PLAN.md — reusable AST invariant: scoped pause/resume/abort/wait, record-only callbacks, status-only reader, planted violations (ADP-07/09)

**Wave 5** *(blocked on Wave 4 completion)*
- [ ] 01-05-PLAN.md — simulated control commands, simulated run_state, `simulate_pause` hook (ADP-10, ADP-06 simulated)

**Research flags**: build the failing real-mode test before the `ExecuteCommand` override
(research/SUMMARY.md, ARCHITECTURE.md); the override must keep the tool-type check and
`_check_args` for control commands and leave every other command on the `base_server` path.

### Phase 2: Wait Through Pauses on the Pinned Core

**Goal**: A F.A.S.T. step stays open through any pause on the real core and ends with the run's real
outcome.
**Depends on**: Phase 1
**Requirements**: LIVE-01, LIVE-02, LIVE-03
**Success Criteria** (what must be TRUE):
  1. `tools/fast/requirements.txt` pins fast-mcp `b30b38d` or later, and the gate's pin test passes
     against that install.
  2. With the real core (stub transport), a paused run keeps the `Transfer` step open, `run_state`
     shows the pause, and the step ends SUCCESS after a resume.
  3. An operator abort ends the step "run aborted by operator at <p>%"; a timeout still never aborts.
  4. Paused time doesn't count toward the run timeout.

**Plans**: TBD
**Note**: a clean install of the new pin needs fast-mcp's `fix/run-recovery-gate` pushed to GitLab;
until then install from the local clone at the pinned SHA.

### Phase 3: Deploy & Supervised Live Acceptance

**Goal**: The live-control stack runs on forb01 and is proven on the instrument with an operator
present.
**Depends on**: Phase 2, and galago-core's "Live Run Control: queue & run page" milestone
**Requirements**: LIVE-04, LIVE-05, LIVE-06, LIVE-07
**Success Criteria** (what must be TRUE):
  1. Deployment followed the safe order (core into `.venv` → restart `galago-tools` → rebuild
     `galago-web`), with no window where the new UI ran against an ungated core.
  2. Deck-3 scenario: the prompt names the deck and plate, the operator fixes the deck and resumes,
     and the same step ends SUCCESS.
  3. Pause → Resume ends SUCCESS; Pause → Abort ends "aborted by operator" with the queue FAILED.
  4. After restarting `galago-web` mid-run, the operator recovers through the tool page.

**Plans**: TBD
**Safety**: every motion step needs the operator's explicit go-ahead, e-stop within reach.

## Backlog

(none)
