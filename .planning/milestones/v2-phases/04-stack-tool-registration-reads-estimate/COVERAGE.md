# API Coverage — stack-automation-layer core (StackService @ ed8ce47) via the Galago `stack` tool

> Full coverage by default. Opt-outs are explicit, reasoned decisions.
> Surface = composition.open_service plus every public StackService method at ed8ce47, plus the
> DEP-01 latch-status read that the frozen proto already names.

| capability | decision | reason |
|---|---|---|
| open_service | INTEGRATE | |
| manager_state | INTEGRATE | |
| robot_states | INTEGRATE | |
| devices | INTEGRATE | |
| labware_profiles | INTEGRATE | |
| transfer_profiles | INTEGRATE | |
| labware_presence | INTEGRATE | |
| estimate_transfer | INTEGRATE | |
| refresh | OPT-OUT | explicitly out of scope — CONTEXT Deferred Ideas: the refresh flag on devices/labware_profiles/transfer_profiles covers v2 |
| refresh_devices | OPT-OUT | explicitly out of scope — CONTEXT Deferred Ideas: devices(refresh=True) covers v2 |
| validate_transfer | OPT-OUT | explicitly out of scope — not in the frozen v2 proto surface; D-20 forbids calling it from tools/stack/ in Phase 4 |
| plan_transfer | OPT-OUT | not needed yet — Phase 5 XFR-01 Transfer (plan -> execute -> wait), gated on DEP-01; D-20 forbids it in Phase 4 |
| execute_transfer | OPT-OUT | not needed yet — Phase 5 XFR-01/XFR-02 behind the step-key ledger, gated on DEP-01; D-20 forbids it in Phase 4 |
| wait_transfer | OPT-OUT | not needed yet — Phase 5 XFR-01/XFR-06 re-attach path; D-20 forbids it in Phase 4 |
| wait | OPT-OUT | not needed — the Transfer path waits through wait_transfer (Phase 5); D-20 forbids it in Phase 4 |
| start_transfer | OPT-OUT | explicitly out of scope — XFR-05 forbids the adapter from ever calling it |
| cancel_transfer | OPT-OUT | explicitly out of scope for v2 — REQUIREMENTS Out of Scope (cancel stays an operator action outside Galago); XFR-05 forbids it |
| go_to_safe_position | OPT-OUT | explicitly out of scope for v2 — REQUIREMENTS Out of Scope (safe position stays an operator action outside Galago); XFR-05 forbids it |
| wait_safe_position | OPT-OUT | explicitly out of scope for v2 — follows go_to_safe_position, which is out of scope |
| acknowledge_failure | OPT-OUT | not needed yet — Phase 5 ACK-01; the AcknowledgeFailure proto entry is frozen now and refused in real mode (D-18) |
| failure_latch_status | OPT-OUT | not needed yet — the read does not exist in the core at ed8ce47; DEP-01 G2 adds it and Phase 5 ACK-02 binds GetFailureLatch to it (refused in real mode now, D-18) |
