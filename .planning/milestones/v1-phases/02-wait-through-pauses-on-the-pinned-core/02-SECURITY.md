---
phase: "02"
slug: "wait-through-pauses-on-the-pinned-core"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
register_authored_at_plan_time: true
created: "2026-10-16"
---

# Phase 02 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register built from the `<threat_model>` blocks of this phase's PLAN files; mitigations
> verified at HEAD by gsd-security-auditor on 2026-10-16 (ASVS L1, block_on: high).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| local fast-mcp clone → gate venv | The core is installed from a local git clone at a SHA that is not on GitLab yet | see 02-01-PLAN threat model |
| galago-core gRPC client → FastServer.ExecuteCommand | Transfer, RunProtocol and the operator's Pause/Resume cross into the adapter; a paused step now stays open | see 02-01-PLAN threat model |
| instrument status (lastEvent payload) → run_state → operator UI | Untyped instrument data reaches the health RPC through PauseInfo | see 02-01-PLAN threat model |
| test process → instrument | Tests must never reach a real F.A.S.T. | see 02-01-PLAN threat model |
| gate venv core → Phase 3 deploy | The core proven here is the one Phase 3 installs into the forb01 service `.venv` | see 02-02-PLAN threat model |
| galago-core gRPC client → FastServer.Abort | The operator's Abort crosses into the adapter; its acceptance now changes how the step's result is worded | see 02-03-PLAN threat model |
| FastServer → galago-core (ExecuteCommandReply.error_message) | The abort text is shown verbatim and moves the queue to FAILED | see 02-03-PLAN threat model |
| FastServer → FastService core | The adapter forwards the configured timeout; the core owns every clock and deadline | see 02-04-PLAN threat model |
| instrument reply -> FastServer.Resume | The resume reply dict comes from the instrument (via the core) and may be malformed; the adapter decides from it whether to wait | see 02-05-PLAN threat model |
| FastServer -> instrument (control commands) | Only operator-issued Pause/Resume/Abort may reach the instrument; the adapter must never add one of its own | see 02-05-PLAN threat model |
| test process -> instrument | Tests must never reach a real F.A.S.T. | see 02-05-PLAN threat model |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation / Evidence | Status |
|-----------|----------|-----------|----------|-------------|-----------------------|--------|
| T-02-01 | Tampering | gate venv fast_mcp install | medium | mitigate | `tools/fast/requirements.txt:5` full SHA; gate venv `direct_url.json` commit `b30b38d…` from local clone; `test_requirements_txt_pins_exactly_one_credential_free_sha` | closed |
| T-02-02 | Elevation of Privilege | Transfer/RunProtocol waiting through pauses | high | mitigate | `server.py:731-733,754-756` RunOptions adds only `on_pause=_record_pause, through_pauses=True`; `_record_pause` record-only (AST); real-core tests assert no control call on an instrument pause | closed |
| T-02-03 | Denial of Service | a paused step holding the motion lock (tool stays BUSY) | medium | accept | Accepted — see AR log; Pause/Abort never take `_motion_lock`, Resume non-blocking acquire (`server.py:940`) | closed |
| T-02-04 | Information Disclosure | lastEvent payload in run_state | low | mitigate | core `_json_safe` caps depth/items/length; `_record_pause` stores only `to_dict()`+`since`; `test_unencodable_run_state_falls_back_to_unknown` | closed |
| T-02-05 | Denial of Service | test design: Event-gated get_status vs ResumeMarker's lock | low | mitigate | `_Stepper` (`fast_test.py:236-268`) with timeouts and cleanup; no Event-gated `get_status` | closed |
| T-02-06 | Tampering | tests reaching a real instrument | high | mitigate | `_stub_transport()` MagicMock, `_real_core()`, `host="h"`; no `Configure`/`open_service` in real-core test classes | closed |
| T-02-SC (02-01) | Tampering | pip install | medium | mitigate | Same as T-02-01: local-file install at the pinned SHA, no registry contact | closed |
| T-02-13 | Tampering | a core without the state gates or wait-through-pauses reaching Phase 3 | high | mitigate | `test_installed_core_has_wait_through_pauses_and_pause_info`, `test_installed_core_refuses_pause_resume_abort_while_idle` | closed |
| T-02-14 | Elevation of Privilege | adapter's fast_mcp surface | low | mitigate | `server.py` imports exclude `fast_mcp.orchestration`; AST `allowed_modules`; `test_adapter_obtains_service_only_through_open_service` | closed |
| T-02-SC (02-02) | Tampering | npm/pip/cargo installs | low | accept | Accepted — no package installed | closed |
| T-02-07 | Repudiation | attribution of an aborted run | high | mitigate | `operator_abort` set only in `Abort()` on `_accepted(result)` under `_run_state_lock` (`server.py:899-901`); cleared on 0→1; flag tests + `TestOperatorAbortRealCore` | closed |
| T-02-08 | Tampering | safety invariant 1 (no recovery on a result) | high | mitigate | `_SCOPED_ATTRS["abort"]={"Abort"}` AST-enforced; invariant re-run `[]`; tearDown caps control calls | closed |
| T-02-09 | Information Disclosure | instrument error text in the message | low | mitigate | Every `_message_for` branch returns via `_one_line(text, 500)` (`server.py:371`) | closed |
| T-02-SC (02-03) | Tampering | npm/pip/cargo installs | low | accept | Accepted — no package installed | closed |
| T-02-10 | Tampering | safety invariant 1 on the timeout path | high | mitigate | TimedOut message states "NOT aborted" (`server.py:366-368`); timeout tests assert pause/resume/abort never called | closed |
| T-02-11 | Denial of Service | a masked re-pause after a resume holding a step open forever | medium | accept | Accepted — see AR log; adapter adds no clock; `test_resume_masks_a_stale_leading_paused_and_reports_ran` | closed |
| T-02-12 | Tampering | tests reaching a real instrument | high | mitigate | Stub transport/real core, `host="h"` | closed |
| T-02-SC (02-04) | Tampering | npm/pip/cargo installs | low | accept | Accepted — no package installed | closed |
| T-02-15 | Tampering | Resume crash-recovery acceptance (a malformed reply such as errorCode False or 0.0 credited as accepted, so the step waits on and reports a run that was never resumed) | high | mitigate | `_accepted()` int-0 only (`server.py:391-404`); Resume gates `service.wait` on it (`server.py:944`); AST check `raw errorCode comparisons: []`, `_accepted calls: 1`; boundary tests | closed |
| T-02-16 | Elevation of Privilege | operator-only control invariant on a rejected resume (adapter retrying resume, or pausing or aborting on its own) | high | mitigate | `_assert_rejected_without_waiting`: resume once, pause/abort never | closed |
| T-02-17 | Denial of Service | motion lock left held after a rejected crash-recovery resume, blocking every later Transfer | medium | mitigate | Resume `try/finally` releases `_motion_lock` on rejection; `assertFalse(_motion_lock.locked())` | closed |
| T-02-18 | Tampering | new tests reaching a real instrument | high | mitigate | `TestRecoveryCommands` uses a MagicMock transport, `host="h"` | closed |
| T-02-SC (02-05) | Tampering | npm/pip/cargo installs | low | accept | Accepted — no package installed | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-02-01 | T-02-03 | A paused step holds the motion lock by design; operator control bypasses it via the Phase 1 override, so it never blocks Pause/Resume/Abort. | user (via plan threat model; confirmed at milestone close) | 2026-10-16 |
| AR-02-02 | T-02-11 | Stale-paused masking after a re-pause is owned by the pinned fast-mcp core; the adapter adds no clock, so it cannot weaken the core's bound. | user (via plan threat model; confirmed at milestone close) | 2026-10-16 |
| AR-02-03 | T-02-SC (02-02..02-05) | These four plans install no package; the one re-install (02-01) is mitigated as T-02-01. | user (via plan threat model; confirmed at milestone close) | 2026-10-16 |

*Accepted risks do not resurface in future audit runs.*

---

## Audit Notes

- **Unregistered flag (non-blocking, medium): WR-02** — `_is_no_error()` (`tools/fast/server.py:310-318`) uses `error_code in (None, 0)`, true for `False`: the same bool/int ambiguity T-02-15 retired in `Resume`. Impact is reporting integrity only (an aborted run's real error could read as "no error"), not a safety-invariant break; `error_code` comes from a typed fast-mcp dataclass, so likelihood is low. Not in any plan's threat model; tracked `open` in `02-REVIEW-DISPOSITION.md`. Below block_on: high, so it does not count toward threats_open.
- WR-03 (`scripts/fast_status.py` channel never closed) and IN-01 (`scripts/fast_dryrun.py` private-state access) are outside this phase's boundaries; carried forward per the review disposition.
- LIVE-01 note: a clean install from GitLab still fails until fast-mcp `fix/run-recovery-gate` is pushed (tracked in STATE.md); the pin is proven against the local-clone install.
- No `## Threat Flags` in any 02 SUMMARY; no transfer dispositions.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-16 | 23 | 23 | 0 | gsd-security-auditor (sonnet) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-16
