# Requirements: galago-tools (nikkopg fork) — F.A.S.T. & STACK adapters

**Defined:** 2026-10-28
**Milestone:** v2 STACK Tool & STACK↔F.A.S.T. Handoff
**Core Value:** An operator running an instrument step from Galago can always see what the instrument is
doing and recover it themselves; no adapter code path pauses, resumes, aborts, cancels, retries or
acknowledges on its own; for the STACK, a step never sends a second transfer.

Split (fast-aligned, user decision 2026-10-28): this repo owns the adapter, the GAL-02 runbook protocol
and live acceptance; galago-core owns codegen, command forms and operator UI in its own parallel
milestone; stack-automation-layer core gaps are fixed there via `/gsd-quick`. Research:
`.planning/research/SUMMARY.md`.

## v2 Requirements

### Tool registration & reads (GAL-01, no motion)

- [x] **STK-01**: `stack.proto` exists and is registered (`tool_base` Command `stack = 24`, Config
  `stack = 43`; `controller.proto` `stack = 24`); `bin/make proto test` is green
- [x] **STK-02**: Operator can Configure the STACK tool with host/port; the tool opens the core only via
  `composition.open_service(..., owner="galago")` with credentials from `STACK_USER`/`STACK_PASSWORD`,
  imports nothing from `stack_automation_layer.mcp`, pins the core by SHA, has no `lock_dir` field, and a
  lock held by stack-mcp fails Configure naming the holder
- [x] **STK-03**: Operator can read manager state, robot states, devices, labware profiles, transfer
  profiles and labware presence — each 1:1 onto a core method, contract v1 `to_dict()` in the reply meta
- [ ] **STK-04**: Operator can get a transfer estimate (`GetTransferEstimate` → `estimate_transfer`,
  nothing moves); `Estimate<Cmd>` hooks are local constants with no I/O
- [ ] **STK-05**: Reads work from the tool page while a Transfer is in flight (fast-style `ExecuteCommand`
  override); motion commands stay serialised
- [ ] **STK-06**: Simulated mode validates arguments (including `step_key`), sleeps the constant
  estimate, never contacts the core and never writes the ledger
- [x] **STK-07**: Result mapping — `ran`, read kinds, `estimated`, `failureAcknowledged` → SUCCESS with
  an empty message; every other core kind → `ERROR_FROM_TOOL` with a one-line message carrying reason
  and guid; adapter argument errors → `INVALID_ARGUMENTS`; a core rejection never becomes SUCCESS

### F5-safe Transfer (GAL-01, gated on the DEP-01 core SHA)

- [ ] **XFR-01**: A workflow step can move a plate with `Transfer`: `plan_transfer` → `execute_transfer`
  → wait to a terminal result in one command; starting the Galago run is the approval
- [ ] **XFR-02**: `Transfer` requires a non-blank `step_key`; a persisted, atomically written ledger
  records key + request fingerprint, a write-ahead `submitting` record before `execute_transfer`, then
  the guid, then the terminal outcome
- [ ] **XFR-03**: A repeated `step_key` (F5 re-dispatch, retry after failure, tool restart) never
  submits: it re-attaches to the recorded guid, replays a recorded `ran`, or refuses (`submitting`
  without a guid, `outcomeUnknown`); the same key with a different request → `INVALID_ARGUMENTS`
- [ ] **XFR-04**: An outcome that proves nothing was sent (`refused`/`rejected`/`needsInput`/
  `readFailed`) releases the key so the operator can fix the cause and re-run the step
- [ ] **XFR-05**: The adapter never retries motion — an AST invariant with planted violations proves it
  never calls `start_transfer`, `cancel_transfer` or `go_to_safe_position`, and calls
  `execute_transfer` at most once per key
- [ ] **XFR-06**: A Transfer `TimedOut` leaves the arm running and is reported as an error; re-running
  the same step re-attaches and finishes it

### Operator acknowledge (GAL-01)

- [ ] **ACK-01**: Operator can clear a core failure latch with `AcknowledgeFailure(guid, arm_inspected)`;
  only the exact string `"yes"` reaches `acknowledge_failure(guid, confirm=True)`, anything else →
  `INVALID_ARGUMENTS` with no core call; no adapter path sends it on its own
- [ ] **ACK-02**: Operator can see the latched guid — in the error message and via a latch-status read
  (DEP-01's new core read), including the `submit-<hex>` case after an ambiguous submit

### Simulated workcell & handoff workflow (GAL-02)

- [ ] **FLOW-01**: A script-mode GAL-02 protocol, kept as importable JSON beside its runbook, mints
  per-run `step_key`s and runs STACK nest/hotel → F.A.S.T. deck, F.A.S.T. transfer, STACK back; nest
  triples are parameters
- [ ] **FLOW-02**: A fully Galago-simulated workcell run of GAL-02 completes all three steps
- [ ] **FLOW-03**: A forced re-dispatch of a completed STACK step sends no second transfer — proven
  offline on a fake core and in a simulated run
- [ ] **FLOW-04**: A GAL-02 run with the STACK tool in real mode against the loopback PAC simulator
  (runbook Part A preconditions, sim account credentials, sim lab names) and the F.A.S.T. simulated
  completes, including a forced re-dispatch check that sends no second POST; operator-run, never against
  `10.150.1.125`/`stack-server`

### Deploy & supervised live

- [ ] **LIVE-08**: Deployed in the safe order (core → service `.venv` → restart `galago-tools` → rebuild
  `galago-web`); stack-mcp closed during Galago runs; both front ends use the identical host string and
  lock dir
- [ ] **LIVE-09**: A supervised, runbook-gated live STACK Transfer reaches `ran` on `stack2-6` with the
  user present
- [ ] **LIVE-10**: A supervised live GAL-02 handoff runs STACK → F.A.S.T. → STACK to SUCCESS on hardware

### Cross-repo dependencies (tracked here, built elsewhere)

- **DEP-01** (stack-automation-layer, one bundled `/gsd-quick`): G1 latch/ownership/in-flight guard
  survive a restart and a re-attached guid is adopted; G2 latch-status read; G3 latch set before the
  explanation build; new SHA and a contract-version decision. Gates XFR-*/ACK-*.
- **DEP-02** (galago-core milestone): submodule bump, ts-proto 1.151.1 regen, `commandFields.stack`
  without acknowledge. Gates FLOW-02..04 and LIVE-*.
- **DEP-03** (galago-core milestone): operator AcknowledgeFailure control (D-20 pattern), F3 tool-error
  display, F5 root cause. Needed for the full operator experience at LIVE-*; not a hard adapter gate.

## Future Requirements

- WR-02 strict `_is_no_error` (F.A.S.T. adapter, v1 debt)
- Adapter refusal of `Configure` while a run is in flight (T-03-05/T-03-08)
- F.A.S.T. hard pause once `hardPause` is documented (D5)
- STACK safe-position and cancel as operator controls from Galago

## Out of Scope

| Feature | Reason |
|---------|--------|
| STACK safe-position / cancel from Galago | Operator actions outside Galago for v2, as fast-mcp kept cancel out |
| Runtime sim/hardware guard in the adapter (G7) | The core's guards are test-only; the adapter holds no instrument policy — enforced by test fixtures and the runbook |
| Fixing core gaps in this repo | Core fixes happen in stack-automation-layer via `/gsd-quick` |
| galago-core code (codegen, forms, run UI, queue) | Owned by galago-core's own milestone |
| Automatic retry of any motion | Hard constraint |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| STK-01 | Phase 4 | Complete |
| STK-02 | Phase 4 | Complete |
| STK-03 | Phase 4 | Complete |
| STK-04 | Phase 4 | Pending |
| STK-05 | Phase 4 | Pending |
| STK-06 | Phase 4 | Pending |
| STK-07 | Phase 4 | Complete |
| XFR-01 | Phase 5 | Pending |
| XFR-02 | Phase 5 | Pending |
| XFR-03 | Phase 5 | Pending |
| XFR-04 | Phase 5 | Pending |
| XFR-05 | Phase 5 | Pending |
| XFR-06 | Phase 5 | Pending |
| ACK-01 | Phase 5 | Pending |
| ACK-02 | Phase 5 | Pending |
| FLOW-01 | Phase 6 | Pending |
| FLOW-02 | Phase 6 | Pending |
| FLOW-03 | Phase 6 | Pending |
| FLOW-04 | Phase 6 | Pending |
| LIVE-08 | Phase 7 | Pending |
| LIVE-09 | Phase 7 | Pending |
| LIVE-10 | Phase 7 | Pending |

**External gates (not requirements, not mapped to a phase):**

| Gate | Gates phase(s) | Strength |
|------|----------------|----------|
| DEP-01 | Phase 5 (XFR-*, ACK-*) | Hard; Phase 5 also re-pins the core to DEP-01's SHA |
| DEP-02 | Phase 6 (FLOW-02..04), Phase 7 (LIVE-*) | Hard; consumes Phase 4's `stack.proto` |
| DEP-03 | Phase 7 | Recommended, not a hard adapter gate |

**Coverage:**
- v2 requirements: 22 total (STK 7, XFR 6, ACK 2, FLOW 4, LIVE 3)
- Mapped to phases: 22/22
- Unmapped: 0
- Mapped to more than one phase: 0

Note: STK-05 (reads answer while another command holds the tool BUSY) is mapped to Phase 4, where the
`ExecuteCommand` override lands and is proven with an injected slow command. Phase 5 re-proves it on the
real `Transfer` path as a carry-over check, not a second mapping.

---
*Requirements defined: 2026-10-28*
*Last updated: 2026-10-28 after roadmap creation (traceability filled)*
