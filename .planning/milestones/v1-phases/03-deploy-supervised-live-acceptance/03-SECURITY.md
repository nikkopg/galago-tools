---
phase: "03"
slug: "deploy-supervised-live-acceptance"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
register_authored_at_plan_time: true
created: "2026-10-16"
---

# Phase 03 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register built from the `<threat_model>` blocks of this phase's PLAN files; mitigations
> verified at HEAD by gsd-security-auditor on 2026-10-16 (ASVS L1, block_on: high).

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Claude shell -> host services | Claude restarts a shared systemd user service and installs into the service venv; only after the user's go | see 03-01-PLAN threat model |
| uv -> package sources | the core comes from a local git clone at a pinned SHA; uv may resolve dependencies from an index | see 03-01-PLAN threat model |
| galago-web (old UI) -> adapter (new) | between steps 2 and 3 the old UI talks to the new adapter | see 03-01-PLAN threat model |
| adapter -> fast-mcp core -> instrument | the core owns every state gate; it must be gated before any new UI exists | see 03-01-PLAN threat model |
| operator browser -> galago-web | the operator's Connect click is the only Configure source for the production tool | see 03-02-PLAN threat model |
| galago-core working tree -> docker build context | the image is built from the working tree, not a git archive | see 03-02-PLAN threat model |
| galago-web container -> host tool ports | host.docker.internal through ufw | see 03-02-PLAN threat model |
| galago-web container -> harness on host port 40003 | a second, simulated F.A.S.T. tool server is reachable from the container and the LAN | see 03-03-PLAN threat model |
| local user -> control FIFO | anyone who can write the FIFO can change the simulated run state | see 03-03-PLAN threat model |
| harness process -> instrument | must not exist | see 03-03-PLAN threat model |
| operator -> galago-web -> adapter -> core -> instrument | the only path a motion or control command may take | see 03-04-PLAN threat model |
| Claude shell -> host | read-only during the scenario: GetStatus, log files, journal | see 03-04-PLAN threat model |
| instrument -> core -> adapter -> galago-web | the instrument's pause reaches the operator as read-only run_state | see 03-05-PLAN threat model |
| galago-core queue -> next step | must stop after the step fails | see 03-06-PLAN threat model |
| Claude shell -> galago-web container | Claude restarts it, only on the operator's go-restart | see 03-07-PLAN threat model |
| galago-web (restarted) -> adapter | the queue has lost the step; the tool page reaches the adapter directly | see 03-07-PLAN threat model |
| operator -> tool page -> adapter -> core -> instrument | the only recovery path after the restart | see 03-07-PLAN threat model |
| evidence record -> requirement status | REQUIREMENTS.md completion is driven by this plan finishing | see 03-08-PLAN threat model |
| gate run -> running service | the gate shares the working tree the service imports from | see 03-08-PLAN threat model |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation / Evidence | Status |
|-----------|----------|-----------|----------|-------------|-----------------------|--------|
| T-03-01 | Tampering | deploy order (core / galago-tools / galago-web) | high | mitigate | `03-DEPLOY.md` Runbook D-05 + Deploy evidence: core → galago-tools → galago-web, strictly increasing UTC timestamps | closed |
| T-03-02 | Tampering | uv install resolving extra dependencies | medium | mitigate | `03-DEPLOY.md` Step-1 dry-run preview and post-install freeze diff: only fast-mcp changed | closed |
| T-03-03 | Denial of Service | galago-tools restart during a run | high | mitigate | `03-DEPLOY.md` tools-idle precondition re-checked before each restart (`GetStatus` READY, no run RUNNING); repeated for the 2026-10-16 CR-01 redeploy | closed |
| T-03-04 | Repudiation | what was deployed and when | medium | mitigate | `03-DEPLOY.md` Deploy evidence, Post-deploy record, every redeploy entry: SHAs, MainPIDs, UTC times, check output | closed |
| T-03-05 | Elevation of Privilege | Claude acting without the user | high | mitigate | Held for every scenario in 03-01..03-08 (`03-DEPLOY.md`, `03-ACCEPTANCE.md`: operator did every reconnect). One user-authorized exception 2026-10-16 (Configure after the CR-01 redeploy) — closed as a logged exception, see AR log and Audit Notes | closed |
| T-03-SC (03-01) | Tampering | uv install of fast-mcp | high | mitigate | `direct_url.json` commit-pin check + `TestRequirementsPin`; install from the local clone at the pinned SHA | closed |
| T-03-06 | Tampering | galago-web image built from unverified code | high | mitigate | `03-ACCEPTANCE.md` HEAD-equals-entry-gate and clean `controller/` checked before each galago-web build | closed |
| T-03-07 | Denial of Service | a failed or broken rebuild | medium | mitigate | `rollback-pre-live04` tag created before the build; anchors and caveat recorded | closed |
| T-03-08 | Elevation of Privilege | reconnect of a tool mid-run flipping BUSY to READY in base_server | high | mitigate | Operator reconnected each tool from its own page for every scenario. One user-authorized exception 2026-10-16 (no run in flight, tool NOT_CONFIGURED, queue empty) — closed as a logged exception, see AR log | closed |
| T-03-SC (03-02) | Tampering | package installs | low | accept | Accepted — no package installed | closed |
| T-03-09 | Spoofing | DryRunFastServer reaching the instrument | critical | mitigate | `scripts/fast_dryrun.py:84-93` refuses non-simulated Configure, `_configure` raises; `self_test()` asserts refusal and `sim-no-contact.invalid` host | closed |
| T-03-10 | Tampering | control FIFO | low | mitigate | `os.mkfifo(control, 0o600)` (`fast_dryrun.py:223,263`); dryrun dir mode 700; FIFO removed at teardown | closed |
| T-03-11 | Information Disclosure | harness listening on 0.0.0.0:40003 | low | accept | Accepted — see AR log; harness torn down (PID exited, port closed) | closed |
| T-03-12 | Tampering | the dry run touching the production F.A.S.T tool | high | mitigate | Production `F.A.S.T.log`: zero `Running command` lines in the dry-run window | closed |
| T-03-13 | Elevation of Privilege | a ufw rule left open, or FAST-DRYRUN left in the workcell | medium | mitigate | Teardown: FIFO/port gone, FAST-DRYRUN removed from workcell, no ufw rule ever added | closed |
| T-03-SC (03-03) | Tampering | package installs | low | accept | Accepted — no package installed | closed |
| T-03-14 | Elevation of Privilege | software-initiated control (Claude or any code path) | critical | mitigate | `scripts/fast_status.py` sends only `GetStatus`; Safety invariant audit: 0 unmapped control-command lines | closed |
| T-03-15 | Tampering | a Configure (Connect, Simulate, Connect all tools) during the run flipping BUSY to READY | high | mitigate | Control-command counts in each run window match the operator's actions; no restart inside a run window | closed |
| T-03-16 | Repudiation | what the operator chose and saw | medium | mitigate | D-13 fields, verbatim operator replies and log excerpts in `03-ACCEPTANCE.md` | closed |
| T-03-SC (03-04) | Tampering | package installs | low | accept | Accepted — no package installed | closed |
| T-03-17 | Elevation of Privilege | software resuming or retrying after an instrument pause | critical | mitigate | Exactly one operator-sent Resume in the LIVE-05 window; Claude sent no command | closed |
| T-03-18 | Tampering | a misleading prompt (wrong deck or plate shown) leading to a wrong physical fix | high | mitigate | D-14 none-plate fix verified in the deployed bundle; operator confirmed the prompt named deck and plate | closed |
| T-03-SC (03-05) | Tampering | package installs | low | accept | Accepted — no package installed | closed |
| T-03-19 | Elevation of Privilege | the queue running the next step after an operator abort | high | mitigate | No step dispatched after the LIVE-06b abort; FINDING (a) resolved by `261015-o44` live verification | closed |
| T-03-20 | Repudiation | which Return-liquid choice was made | medium | mitigate | Operator reply and Decisions-chosen field recorded for LIVE-06b | closed |
| T-03-SC (03-06) | Tampering | package installs | low | accept | Accepted — no package installed | closed |
| T-03-21 | Elevation of Privilege | Claude restarting a service without authorization | high | mitigate | `docker restart galago-web` only after the operator's literal "go-restart"; 2026-10-16 galago-tools restart only after the user's "go 1" | closed |
| T-03-22 | Tampering | a Configure after the restart flipping BUSY to READY and admitting a new Transfer mid-run | high | mitigate | Tool stayed BUSY/paused across the galago-web restart; F.A.S.T. listener PID unchanged | closed |
| T-03-23 | Elevation of Privilege | the queue re-dispatching the step after the restart | high | mitigate | Exactly one Transfer line in the LIVE-07 window; queue re-run defect fixed (D-14) and re-verified; FINDING (b) resolved | closed |
| T-03-SC (03-07) | Tampering | package installs | low | accept | Accepted — no package installed | closed |
| T-03-24 | Repudiation | requirements marked complete without evidence | high | mitigate | Summary table PASS rows, Safety invariant audit PASS, 03-08 Task 2 gate | closed |
| T-03-25 | Denial of Service | a gate step deleting pb2 files under the running service | medium | mitigate | Post-acceptance gate ran `bin/make test` only, never `proto`/`clean_proto` | closed |
| T-03-SC (03-08) | Tampering | package installs | low | accept | Accepted — no package installed | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-03-01 | T-03-05 / T-03-08 (logged exception) | On 2026-10-16, at the user's explicit request after the CR-01 redeploy, Claude sent `Configure` over gRPC to F.A.S.T. (real) and Pf400 (simulated). Compensating facts: tools were NOT_CONFIGURED after the restart, no run in flight, galago-web queue empty, configs identical to pre-restart, no motion command sent. The rule now reads: Claude sends `Configure` only on the user's explicit request and only while no run is in flight; the operator otherwise reconnects. A code-level backstop (adapter refuses `Configure` mid-run) is a candidate for v2. | user (via plan threat model; confirmed at milestone close) | 2026-10-16 |
| AR-03-02 | T-03-11 | Dry-run harness on 0.0.0.0:40003 served only simulated state, like the other LAN tool servers, and was torn down at plan end. | user (via plan threat model; confirmed at milestone close) | 2026-10-16 |
| AR-03-03 | T-03-SC (03-02..03-08) | No package installed by these plans; the galago-web image uses galago-core's locked dependencies. | user (via plan threat model; confirmed at milestone close) | 2026-10-16 |

*Accepted risks do not resurface in future audit runs.*

---

## Audit Notes

- Auditor verdict was OPEN_THREATS (31/33): T-03-05 and T-03-08 declare an unconditional, procedural-only prohibition, broken once on 2026-10-16 by a user-authorized `Configure` (recorded in `03-DEPLOY.md` CR-01 redeploy and `03-VERIFICATION.md` Resolution). No code-level backstop exists (`server.py`, `base_server.py`, `fast_status.py`, `fast_dryrun.py` checked). The user chose to close both as a logged, bounded exception (2026-10-16); see AR log.
- No `## Threat Flags` in any 03 SUMMARY. 03-REVIEW WR-01 (dev-only dry-run harness) and WR-02 (`_is_no_error`, carried as v2 debt) are code-review items, not registered threats.
- Local suite re-run read-only: 147 tests OK.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-10-16 | 33 | 33 | 0 | gsd-security-auditor (sonnet); T-03-05/T-03-08 closed by logged exception (user decision) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-10-16
