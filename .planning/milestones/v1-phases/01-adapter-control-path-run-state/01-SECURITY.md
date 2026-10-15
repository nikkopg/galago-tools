---
phase: "01"
slug: "adapter-control-path-run-state"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
register_authored_at_plan_time: true
created: "2026-10-16"
---

# Phase 01 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register built from the `<threat_model>` blocks of this phase's PLAN files; mitigations
> verified at HEAD by gsd-security-auditor on 2026-10-16 (ASVS L1, block_on: high).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| galago-core gRPC client → FastServer.ExecuteCommand | Command protobufs from the Galago queue/run page cross into the adapter; the control path now skips base_server's readiness gate for three commands | see 01-01-PLAN threat model |
| FastServer → FastService core (instrument) | Calls that move the instrument head; the core owns the state gate | see 01-01-PLAN threat model |
| FastServer → FastService core | Control calls move the head; the core's `_require_state` is the only state gate | see 01-02-PLAN threat model |
| galago-core heartbeat → FastServer.GetStatus | Polled every 2 s during a controllable step; must be read-only and must not fail | see 01-03-PLAN threat model |
| FastServer → FastService.status | The only instrument call on the read path | see 01-03-PLAN threat model |
| instrument → run_state.pause.eventPayload | Instrument-originated diagnostic detail forwarded to the operator UI | see 01-03-PLAN threat model |
| developer change → tools/fast/server.py | Future edits are the threat source: a well-meant auto-recovery line would let software command the instrument | see 01-04-PLAN threat model |
| adapter → instrument | Every pause/resume/abort moves the head with sensors briefly disabled (core comment at `_require_state`) | see 01-04-PLAN threat model |
| in-process dev/test code → FastServer.simulate_pause | Only code inside the tool-server process can call the hook; it has no gRPC surface | see 01-05-PLAN threat model |
| galago-core gRPC client → simulated FastServer | The same commands as real mode, answered without an instrument | see 01-05-PLAN threat model |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation / Evidence | Status |
|-----------|----------|-----------|----------|-------------|-----------------------|--------|
| T-01-01 | Elevation of Privilege | FastServer.ExecuteCommand control branch | high | mitigate | `server.py:532-544` single `CONTROL_COMMANDS` gate (l.82), one `super().ExecuteCommand`; `test_wrong_tool_type_never_takes_the_control_path`, `test_non_control_commands_still_take_the_base_server_gate_mid_run` | closed |
| T-01-02 | Tampering | tool status (`self.status`) during a run | high | mitigate | No `setStatus` call in `server.py`; `test_control_commands_never_call_set_status` | closed |
| T-01-03 | Tampering | Pause hard/soft choice | high | mitigate | `Pause {}` has no fields (`fast.proto`); `server.py:869` `pause(hard=False)`; `assert_called_once_with(hard=False)` | closed |
| T-01-04 | Tampering | input validation on the new path | high | mitigate | `server.py:539` dispatches via `_dispatchCommand` → `_check_args`; blank/unclear-decision tests (idle and mid-run) | closed |
| T-01-05 | Denial of Service | Resume vs `_motion_lock` | medium | mitigate | `server.py:940-958` non-blocking acquire, recovery releases in `finally`; lock-spy tests; CR-01 `_accepted()` gate at `server.py:944` | closed |
| T-01-06 | Spoofing | gRPC caller identity | low | accept | Accepted — see AR log (PLAN 01-01) | closed |
| T-01-SC (01-01) | Tampering | npm/pip/cargo installs | low | accept | Accepted — no package installed; `test_requirements_txt_pins_exactly_one_credential_free_sha` | closed |
| T-01-07 | Tampering | physical decision strings on the control path | high | mitigate | `_check_args` (`server.py:244-249`) in `_dispatchCommand`; unset/blank/unclear → INVALID_ARGUMENTS, service never called | closed |
| T-01-08 | Tampering | adapter second-guessing the core's state gate | high | mitigate | `test_control_commands_never_check_instrument_state` — `service.status` never called for any control command in any state | closed |
| T-01-09 | Elevation of Privilege | non-control commands slipping past base_server's readiness gate | high | mitigate | GetTipStatus mid-run → NOT_READY; toolbox → WRONG_TOOL tests | closed |
| T-01-10 | Information Disclosure | DRIVER_ERROR carries the exception text | low | accept | Accepted — see AR log (PLAN 01-02) | closed |
| T-01-11 | Denial of Service | crash-recovery Resume holds the motion lock for its whole wait | low | accept | Accepted — see AR log (PLAN 01-02); `test_crash_recovery_resume_waits_and_holds_the_lock` | closed |
| T-01-SC (01-02) | Tampering | npm/pip/cargo installs | low | accept | Accepted — no package installed | closed |
| T-01-12 | Elevation of Privilege | run_state read path commanding the instrument | high | mitigate | `_build_run_state` (`server.py:639-696`) calls only `service.status()`; AST rule clean on real file | closed |
| T-01-13 | Denial of Service | heartbeat failing on a bad status or payload | medium | mitigate | `server.py:685-696`, `GetStatus` try/except collapse to `{state: unknown}`; status-failure and unencodable-run_state tests | closed |
| T-01-14 | Tampering | run record race between the poll thread and the progress callback | medium | mitigate | `_run_state_lock` guards `_run_record`; `test_run_state_lock_is_not_the_motion_lock`; overlapping-run pause regression test | closed |
| T-01-15 | Information Disclosure | instrument eventPayload exposed to galago-core | low | accept | Accepted — see AR log (PLAN 01-03) | closed |
| T-01-16 | Tampering | shared wire contract `StatusReply` | medium | mitigate | `tool_base.proto` `run_state = 4` optional Struct (additive); `test_other_tool_types_leave_run_state_unset` | closed |
| T-01-SC (01-03) | Tampering | npm/pip/cargo installs | low | accept | Accepted — stdlib only | closed |
| T-01-17 | Elevation of Privilege | software-initiated pause/resume/abort | high | mitigate | `_SCOPED_ATTRS` AST invariant; planted `.pause/.resume/.abort/.wait` violations caught; real file clean | closed |
| T-01-18 | Elevation of Privilege | the pause recorder or progress callback growing into a command site | high | mitigate | `_RECORD_ONLY_FUNCTIONS` rule; planted command calls in recorder/callbacks caught | closed |
| T-01-19 | Tampering | an adapter-side instrument-state gate | high | mitigate | `_STATUS_READERS` + control-path state-string ban; planted state checks in Abort/Resume caught | closed |
| T-01-20 | Repudiation | a vacuous checker that always passes or always fails | medium | mitigate | Real file → `[]`; planted-allowed calls add no violation (checker non-vacuous both ways) | closed |
| T-01-SC (01-04) | Tampering | npm/pip/cargo installs | low | accept | Accepted — `ast`, `copy` stdlib | closed |
| T-01-21 | Elevation of Privilege | simulate_pause usable against a real instrument | high | mitigate | `simulate_pause` (`server.py:622-637`) raises unless simulated; not in proto/command map; real-mode and not-a-gRPC-command tests | closed |
| T-01-22 | Tampering | a simulated command reaching an instrument | high | mitigate | Simulated `Configure` never calls `open_service`; `test_pause_prompt_round_trip_without_hardware` asserts `open_service` not called | closed |
| T-01-23 | Tampering | simulated decisions defaulted or a hooked pause cleared by an invalid command | medium | mitigate | `_check_args` before simulated branch (`server.py:498-513`); invalid Resume leaves hooked pause in place | closed |
| T-01-24 | Elevation of Privilege | the hook or its clear helper growing into a command site | high | mitigate | `simulate_pause`, `_clear_pause` in `_RECORD_ONLY_FUNCTIONS`; planted violations caught | closed |
| T-01-SC (01-05) | Tampering | npm/pip/cargo installs | low | accept | Accepted — `queue` stdlib | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01-01 | T-01-06 | Unauthenticated internal gRPC on the lab's trusted segment, unchanged by this phase; who may press Pause is galago-core's concern (ASVS V2/V4 out of scope). | user (via plan threat model; confirmed at milestone close) | 2026-10-16 |
| AR-01-02 | T-01-10 | DRIVER_ERROR carries `str(e)`, mirroring base_server; internal operator-only channel, no secrets. | user (via plan threat model; confirmed at milestone close) | 2026-10-16 |
| AR-01-03 | T-01-11 | Crash-recovery Resume holds the motion lock for the whole wait by design (D-07), so no new Transfer starts under an untracked resumed run. | user (via plan threat model; confirmed at milestone close) | 2026-10-16 |
| AR-01-04 | T-01-15 | Instrument eventPayload (plate IDs, deck position) reaches galago-core; no credentials or personal data — it is what the operator prompt must show. | user (via plan threat model; confirmed at milestone close) | 2026-10-16 |
| AR-01-05 | T-01-SC (all 5 plans) | No new package installed by any plan; only stdlib and the already-pinned grpc/protobuf/fast-mcp. | user (via plan threat model; confirmed at milestone close) | 2026-10-16 |

*Accepted risks do not resurface in future audit runs.*

---

## Audit Notes

- Code at HEAD includes the Phase 2 CR-01 fix (`134e097`/`7c2e15a`): crash-recovery `Resume` enters `service.wait` only after `_accepted()` (`server.py:944`), closing 01-REVIEW WR-01; strengthens T-01-05.
- Phase 1's own CR-01 (`_run_in_flight` reset only on 0→1, commit `581dec7`) is live at `server.py:577-581` and regression-tested; strengthens T-01-14.
- `tools/base_server.py` unchanged since `9c27896`.
- No `## Threat Flags` in any 01 SUMMARY. Open 01-REVIEW items (WR-02, WR-03, IN-01..03) concern the dev-only `scripts/fast_dryrun.py` harness and map to no registered threat; tracked in `01-REVIEW-DISPOSITION.md`.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-16 | 29 | 29 | 0 | gsd-security-auditor (sonnet) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-16
