# GAL-02 handoff runbook: STACK -> F.A.S.T. -> STACK (simulation only)

This runbook sits beside the protocol `docs/runbooks/gal-02-handoff.protocol.json`. The protocol is
checked by `tools/tests/gal02_handoff_test.py` and `tools/tests/gal02_replay_test.py` (offline), and
this runbook by `tools/tests/gal02_runbook_test.py`. It covers Phase 6 requirements FLOW-01 (the
protocol and this runbook), FLOW-02 (Galago-simulated workcell run), FLOW-03 (a re-dispatched STACK
step sends no second transfer) and FLOW-04 (STACK real mode against the PAC simulator).

## Safety rules

- Simulation only. Nothing in this runbook moves hardware.
- Nothing targets 10.150.1.125 or stack-server before Phase 7.
- The executor (an automated session) never starts Docker, the PAC simulator, galago-core, a tool server or a run.
- The executor never clicks a real-mode Configure and never sends a STACK command (SAL runbook A.0, A.10).
- Production galago-web (:3010) and its DB are never used (D-16e).
- Credentials come only through the sourced sim env files. They are never typed into this runbook, the Findings log or shell history.
- Galago-simulated STACK and real-mode STACK use separate tool-server processes and separate Galago tool instances (D-16b).
- A ledger file is never deleted (Phase 5).

## What each part proves

| Part | Environment | Proves | Does not prove |
|------|-------------|--------|----------------|
| Part 1 | Offline: node script stub and the fake core, no Docker | The protocol emits the right four rows and keys; a re-dispatched stored STACK step is answered from the ledger (replayed SUCCESS) and the fake core's accepted-submit count stays at 1 | That galago-core imports and queues the protocol the same way; anything about the PAC simulator |
| Part 2a | Dev galago-core, STACK and F.A.S.T. both Galago-simulated | The protocol imports (Mode Script, four rows), runs to completion through the real queue, and its stored STACK step survives a re-dispatch | That no second transfer is sent (simulated mode never writes the ledger and never reaches an instrument) |
| Part 2b | Dev galago-core, STACK in real mode against the loopback PAC simulator, F.A.S.T. Galago-simulated | A real-mode run completes against the simulator, and a re-sent in leg is answered `replayed true` with no second manager task | Anything about hardware: the simulator models no plate presence or grip (SAL A.7) |

The Galago-simulated re-dispatch in Part 2a proves only that the protocol's stored STACK step survives a re-dispatch through the real queue: it returns SUCCESS and no ledger file appears in the configured ledger_dir. It does not prove that no second transfer is sent; only the offline fake-core test (tools/tests/gal02_replay_test.py) and the Part 2b run against the PAC simulator prove that.

## Part 2 gate: DEP-02

Part 2 needs galago-core Phase 5 (DEP-02, STACK Codegen & Command Forms). It has not landed unless
this gate says so.

1. From the galago-tools root run:

   ```bash
   bash docs/runbooks/gal-02-dep02-check.sh
   ```

   The script is read-only. Set `GALAGO_CORE_DIR` if galago-core is not at `../galago-core`.
2. `DEP-02 OK` on the last line means continue.
3. Any `BLOCKED:` line means stop. Part 2 does not start. The `missing:` and `forbidden:` lines above it say which piece is absent; see galago-core `.planning/ROADMAP.md` Phase 5.
4. Never hand-write stack types into galago-core and never drive the queue another way to get around the gate (D-01).
5. Record the verdict line and the printed galago-core HEAD in Findings row G0.
6. Once the gate is OK, also confirm two things (the operator runs both):
   - the dev galago-core in use was started from that source (its dev compose bind-mounts `./controller`);
   - galago-core's own `controller/test/commandFields.test.ts` passes there.
