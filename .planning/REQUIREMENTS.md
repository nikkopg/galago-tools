# Requirements: galago-tools — v1 F.A.S.T. Live Run Control (adapter & rollout)

**Defined:** 2026-10-12
**Core Value:** An operator running a F.A.S.T. step from Galago can always see what the instrument
is doing and recover it themselves; no adapter code path pauses, resumes or aborts on its own.
**Governing design:** `docs/specs/2026-10-12-galago-live-run-control-design.md`
**Companion:** galago-core `.planning/REQUIREMENTS.md` (QUE-*, UI-*). Together the two sets carry
the 25 requirements approved on 2026-10-12 (originally RCTL/PAUSE/RSTATE/RSAFE/SIM/ROLL); each
requirement below names the original ID(s) it carries.

## Milestone Requirements

### Adapter control path (ADP)

- [x] **ADP-01**: Operator's Pause reaches the instrument as a soft pause (`FastService.pause(hard=False)`); the `Pause` command carries no hard/soft choice (D5) — *RCTL-01*
- [x] **ADP-02**: `Pause`/`Resume`/`Abort` sent through `ExecuteCommand` reach `FastService` while a `Transfer`/`RunProtocol` is in flight — not refused by `base_server`'s readiness gate, not blocked by the adapter's motion lock — through a `FastServer.ExecuteCommand` override; `tools/base_server.py` is unchanged — *RCTL-05*
- [x] **ADP-03**: A control command never changes the tool's status: a tool that is BUSY with a run stays BUSY after a control command completes — *RCTL-05*
- [x] **ADP-04**: With a run in flight, `Resume` returns once the instrument accepts it (the step's own wait reports the outcome); with no run in flight (crash recovery), `Resume` waits for the resumed run and reports its outcome — *RCTL-02, RCTL-07*
- [x] **ADP-05**: `GetStatus` returns `StatusReply.run_state` (an additive optional `google.protobuf.Struct` on `tool_base.proto`) with state, percent and the current pause (`PauseInfo`) for the F.A.S.T.; other tool types leave it unset — *RSTATE-01*
- [ ] **ADP-06**: Blank or unclear `is_tip_broken`/`return_liquid` are `INVALID_ARGUMENTS` on every path (real and simulated, `ExecuteCommand` override included); no decision is ever defaulted — *RSAFE-02*
- [ ] **ADP-07**: The no-auto-abort invariant is extended: `.pause`/`.resume`/`.abort` appear only in the `Pause`/`Resume`/`Abort` methods, `.wait` only in the long-running commands and the crash-recovery `Resume`, `on_pause` only records state; a planted violation fails the check — *RSAFE-01*
- [x] **ADP-08**: A real-mode (not simulated) test shows `Pause`/`Resume`/`Abort` reaching the service through `ExecuteCommand` while a `Transfer` is blocked, with the tool still BUSY afterwards — *RSAFE-04*
- [ ] **ADP-09**: The adapter adds no instrument-state check of its own; every state gate stays in the fast-mcp core — *RSAFE-03*
- [ ] **ADP-10**: In simulated mode, control commands check their arguments and return SUCCESS, and a test hook drives `run_state` to paused (with a `PauseInfo`) so galago-core's prompt and controls can be exercised without hardware — *SIM-01*

### Live wiring and rollout (LIVE)

- [ ] **LIVE-01**: `tools/fast/requirements.txt` pins fast-mcp `b30b38d` or later; before go-live the installed core is checked to have the state-gated `pause`/`resume`/`abort` and `through_pauses` — *ROLL-01*
- [ ] **LIVE-02**: `Transfer`/`RunProtocol` keep their step open through instrument and operator pauses (`through_pauses` + `on_pause` feeding `run_state`), end SUCCESS on completion and "run aborted by operator at <p>%" on an operator abort — *PAUSE-01, RCTL-02, RCTL-03*
- [ ] **LIVE-03**: Time spent paused doesn't count toward the run timeout — *PAUSE-04*
- [ ] **LIVE-04**: Deployed in the safe order: core into the service `.venv`, restart `galago-tools`, rebuild `galago-web` (galago-core milestone done) — *ROLL-02*
- [ ] **LIVE-05**: Supervised live: deck 3 empty → pause prompt shows "Deck 3: expected plate 1, found none" → fix the deck → Resume (tip intact) → the same step ends SUCCESS — *ROLL-03*
- [ ] **LIVE-06**: Supervised live: Pause → Resume → SUCCESS; Pause → Abort (return liquid yes/no) → "aborted by operator", queue FAILED — *ROLL-04*
- [ ] **LIVE-07**: Supervised live: restart `galago-web` while a step runs, then recover through the tool page's Resume or Abort — *ROLL-05*

## Future Requirements

- **Hard pause** — explicit, non-defaulted choice once `hardPause` is documented (D5)
- **Second `runControl` tool type** — prove the generic path with another tool server

## Out of Scope

| Feature | Reason |
|---------|--------|
| Software-initiated pause/resume/abort | Operator-only invariant (design §7) |
| Hard pause | Undocumented instrument behaviour (D5) |
| Editing `tools/base_server.py` | Shared by every tool type; override in `FastServer` instead |
| galago-core queue/UI work | Planned in galago-core's own `.planning/` |
| F5 / F3 | Tracked debt, out by user decision |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| ADP-01 | Phase 1 | Complete |
| ADP-02 | Phase 1 | Complete |
| ADP-03 | Phase 1 | Complete |
| ADP-04 | Phase 1 | Complete |
| ADP-05 | Phase 1 | Complete |
| ADP-06 | Phase 1 | Pending |
| ADP-07 | Phase 1 | Pending |
| ADP-08 | Phase 1 | Complete |
| ADP-09 | Phase 1 | Pending |
| ADP-10 | Phase 1 | Pending |
| LIVE-01 | Phase 2 | Pending |
| LIVE-02 | Phase 2 | Pending |
| LIVE-03 | Phase 2 | Pending |
| LIVE-04 | Phase 3 | Pending |
| LIVE-05 | Phase 3 | Pending |
| LIVE-06 | Phase 3 | Pending |
| LIVE-07 | Phase 3 | Pending |

**Coverage:**
- Milestone requirements: 17 total
- Mapped to phases: 17
- Unmapped: 0 ✓

---
*Requirements defined: 2026-10-12*
*Last updated: 2026-10-12 after moving the Galago planning out of fast-mcp*
