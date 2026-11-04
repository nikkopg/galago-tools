# API Coverage — stack-automation-layer core (StackService @ 934a621) via the Galago `stack` tool

> Full coverage by default. Opt-outs are explicit, reasoned decisions.
> The surface is `composition.open_service` plus every public `StackService` method at core
> `934a621ece116a8b263897c1e9b62b57374f4ef3` (DEP-01), which this repo pins by SHA. The core is an
> in-house dependency with a surface frozen by Phase 4's `stack.proto`. This file follows the
> Phase 4 precedent (`04-stack-tool-registration-reads-estimate/COVERAGE.md`) and records what
> Phase 5 changes: the motion, wait, latch and acknowledge rows move from "not needed yet" to
> INTEGRATE.

| capability | decision | reason |
|---|---|---|
| open_service | INTEGRATE | Phase 4 (owner="galago", unchanged) |
| manager_state | INTEGRATE | Phase 4 (GetManagerState, unchanged) |
| robot_states | INTEGRATE | Phase 4 (GetRobotStates, unchanged) |
| devices | INTEGRATE | Phase 4 (ListDevices, unchanged) |
| labware_profiles | INTEGRATE | Phase 4 (ListLabwareProfiles, unchanged) |
| transfer_profiles | INTEGRATE | Phase 4 (ListTransferProfiles, unchanged) |
| labware_presence | INTEGRATE | Phase 4 (GetLabwarePresence, unchanged) |
| estimate_transfer | INTEGRATE | Phase 4 (GetTransferEstimate, unchanged) |
| plan_transfer | INTEGRATE | XFR-01: the first call of `Transfer`. It has exactly one call site, in `_run_fresh` (D-16, plan 05-02) |
| execute_transfer | INTEGRATE | XFR-01/XFR-02: exactly one call site, in `_run_fresh`, after the write-ahead `claim`, never in a loop (D-16, plans 05-02/05-07) |
| wait | INTEGRATE | XFR-01/D-11: one `wait(handle, timeout_s=T)` per fresh path (plan 05-02) |
| wait_transfer | INTEGRATE | XFR-03/XFR-06: the read-only re-attach loop for a `started` record (D-11, plan 05-06) |
| latch_status | INTEGRATE | ACK-02: `GetFailureLatch` 1:1, and the zero-I/O guid source for operator messages (D-13, amendment A-2, plans 05-04/05-05/05-06) |
| acknowledge_failure | INTEGRATE | ACK-01: `AcknowledgeFailure` only, exactly one call site, only after the exact `"yes"` check, `confirm=True` (D-14/D-15, plan 05-04) |
| refresh | OPT-OUT | out of scope: Phase 4 Deferred Ideas, where the refresh flag on the list reads covers v2 |
| refresh_devices | OPT-OUT | out of scope: Phase 4 Deferred Ideas, where `devices(refresh=True)` covers v2 |
| validate_transfer | OPT-OUT | out of scope: not in the frozen v2 proto. D-16 forbids any call from `tools/stack/` |
| start_transfer | OPT-OUT | out of scope: XFR-05 forbids it. `execute_transfer` is the only submit path |
| cancel_transfer | OPT-OUT | out of scope for v2 (REQUIREMENTS Out of Scope). XFR-05/D-16 forbid it |
| go_to_safe_position | OPT-OUT | out of scope for v2 (REQUIREMENTS Out of Scope). XFR-05/D-16 forbid it |
| wait_safe_position | OPT-OUT | out of scope for v2: it follows `go_to_safe_position`. D-16 forbids it |

No proto or `Config` field is added (Phase 4 D-01..D-05 freeze), and no `ListTransferProfiles`-style
extra command is needed (ROADMAP Phase 5 settle-at-plan-time item, answered in `05-SPIKE.md` § 6).
