---
phase: "06"
slug: "gal-02-workflow-simulated-workcell-pac-simulator-run"
status: verified
# threats_open = count of OPEN threats at or above workflow.security_block_on severity (the blocking gate)
threats_open: 0
asvs_level: 1
register_authored_at_plan_time: true
created: "2026-11-02"
---

# Phase 06 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Register built from the `<threat_model>` blocks of this phase's four PLAN files; mitigations
> verified at HEAD on 2026-11-02 (ASVS L1 grep-depth, block_on: high). Every SUMMARY reported
> `## Threat Flags: None`; `threats_open: 0` with a plan-time register at ASVS L1 short-circuits
> the auditor subagent per the workflow rule.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| operator run-form input -> protocol script | parameter strings typed or saved by the operator become STACK and F.A.S.T. command params | see 06-01-PLAN threat model |
| protocol script output -> STACK adapter | stored queue params reach the frozen ledger and Transfer path on every dispatch and re-dispatch | see 06-01-PLAN threat model |
| test suite -> network and real state | tests must never reach the real STACK, the real ledger or the real latch | see 06-01-PLAN threat model |
| runbook -> operator actions | the operator follows written steps against Docker, galago-core and tool servers | see 06-02-PLAN threat model |
| galago-core source tree -> DEP-02 gate | the gate decides whether Part 2 may start from files in another repo | see 06-02-PLAN threat model |
| sim environment files -> tool-server process | sim account credentials enter only through sourced env files | see 06-02-PLAN threat model |
| operator -> dev galago-core and tool servers | operator-started infrastructure on the galago-tools host | see 06-03-PLAN threat model |
| Claude -> local services | read-only GETs and file reads only | see 06-03-PLAN threat model |
| STACK real tool server -> PAC sim manager (127.0.0.1) | a real STACK API with motion on simulated hardware | see 06-04-PLAN threat model |
| sim-account.env -> tool-server process environment | sim credentials cross into the process only | see 06-04-PLAN threat model |
| operator re-send form -> adapter ledger | an operator-typed key and params decide replay, refusal or a fresh submit | see 06-04-PLAN threat model |

---

## Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation / Evidence | Status |
|-----------|----------|-----------|----------|-------------|-----------------------|--------|
| T-06-01 | Tampering / Elevation (safety) | protocol defaults | high | mitigate | `test_no_hardware_names_in_the_protocol`, `test_safe_defaults_are_the_pac_sim_lab_names` (`tools/tests/gal02_handoff_test.py`) pin PAC-sim-only defaults; hardware names entered only by the operator in Phase 7 | closed |
| T-06-02 | Tampering | step_key reuse across runs (a false replayed SUCCESS while the plate is elsewhere) | high | mitigate | key base is label + ISO timestamp + 8-hex random, minted once per run; `test_step_key_is_non_blank_distinct_and_run_unique` (`gal02_handoff_test.py`), `test_redispatch_second_run_mints_new_keys_and_is_fresh` (`gal02_replay_test.py`) | closed |
| T-06-03 | Elevation of privilege | operator-only commands in a protocol | medium | mitigate | script emits only note/transfer; `test_safe_defaults_emit_no_operator_only_command`, `test_script_style_uses_only_the_documented_sandbox_api`; galago-core also refuses them at enqueue | closed |
| T-06-04 | Tampering (input validation, ASVS V5) | script inputs | medium | mitigate | need/whole/positive validators throw before any galago call; ParseDict rejects unknown proto fields; `_check_args` asserted on both legs (`gal02_replay_test.py:168`, `gal02_handoff_test.py:354`) | closed |
| T-06-05 | Information disclosure / Tampering | tests touching the real ledger, latch or network | high | mitigate | `_StackTestCase` temp HOME/XDG_STATE_HOME/STACK_STATE_DIR isolation (`stack_test.py:139`), loopback socket guard, hardware deny-set; vm sandbox has no `require`, so the script cannot open a socket | closed |
| T-06-06 | Tampering | galago-core replaces a param value that starts with `{`{ and ends with `}`} | low | accept | accepted — see AR-06-01 | closed |
| T-06-07 | Elevation of privilege | DEP-02 gate false pass | high | mitigate | five independent checks; `TestDep02Gate` (`gal02_runbook_test.py:147`) covers empty tree, each missing piece, exposed acknowledge, one-byte proto difference, complete tree | closed |
| T-06-08 | Tampering | gate side effects on the galago-core checkout | medium | mitigate | script reads only (plus `git rev-parse`); `test_dep02_gate_is_read_only` compares sha256, mtime_ns and file list before/after | closed |
| T-06-09 | Tampering / Elevation (safety) | runbook directing a run at the real STACK, port 5006 or the port-5005 service | high | mitigate | hardware-refusal preflight (host deny-set, 127.0.0.1-only bind, productName/version, sim- robots); STACK_SIM_PORT checked free and never 5005/5006; `test_runbook_carries_the_required_procedure_phrases` | closed |
| T-06-10 | Information disclosure (ASVS V2, V7) | credentials or bearer tokens in the runbook or Findings log | high | mitigate | credentials only via sourced sim.env / sim-account.env; presence checked with `grep -c`, never printed; `test_runbook_holds_no_credential_values` | closed |
| T-06-11 | Tampering | production galago-web (:3010) or its DB used for sim tools | high | mitigate | separate compose project galago-gal06 on :3020 with its own DB; phrase pinned by the content test; Findings G0 records production :3010 untouched (health 200) | closed |
| T-06-12 | Repudiation | over-claiming what the simulated re-dispatch proves | medium | mitigate | D-07 sentence pinned verbatim (`test_runbook_states_d07_exactly`); Findings row 2a-3 repeats the key phrase and states what the simulated re-dispatch does not prove | closed |
| T-06-13 | Elevation of privilege | Claude starting infrastructure or sending commands | high | mitigate | every start/motion step gated `checkpoint:human-action` (06-03-PLAN ×4, 06-04-PLAN ×3); Claude's checks read-only (ss, file tests, grep on tee'd logs, GET /api/protocols); the two user-delegated sends are logged as Deviations in Findings 2a-3/2b-3 | closed |
| T-06-14 | Tampering | a STACK process configured simulated being reused in real mode | medium | mitigate | STACK-SIM (40010) stopped after Part 2a; Part 2b uses a separate process (40012) and tool instance | closed |
| T-06-15 | Repudiation | numberOfRuns above 1, or an over-claimed row 2a-3 | low | mitigate | instructions pin numberOfRuns 1; Task 3 requires the D-07 phrase in row 2a-3 | closed |
| T-06-16 | Tampering | the production galago-web or its DB used for the sim run | high | mitigate | verification reads the protocol on :3020 (galago-gal06); instructions forbid :3010; Findings record production untouched | closed |
| T-06-17 | Tampering / Elevation (safety) | the run reaching the real STACK | high | mitigate | preflight host deny-set (`HARDWARE_DENY`, `gal02_harness.py:23`), 127.0.0.1-only bind, productName and pinned productVersion, sim- robot sentinel; read-only re-checks of bind, application identity and Configure host before any transfer (host-refusal cases `stack_test.py:532`) | closed |
| T-06-18 | Tampering | the wrong port (5005 scoringservice, 5006 Device master) | high | mitigate | STACK_SIM_PORT read from sim.env and asserted not 5005/5006; the application identity check proves it is the Stack manager | closed |
| T-06-19 | Tampering | sim keys mixed into a hardware ledger, or a shared lock and latch | high | mitigate | absolute sim-only ledger_dir; sim-only STACK_MCP_LOCK_DIR and STACK_STATE_DIR; separate process from both STACK-SIM and the future Phase 7 deployment | closed |
| T-06-20 | Information disclosure (ASVS V2, V7) | sim credentials in logs or the Findings log | high | mitigate | credentials only via the sourced env files; presence via `grep -c`; the runbook credential regex re-run after the edits; nothing from ps or env enters evidence | closed |
| T-06-21 | Tampering | a re-send with a byte-altered key submits a second transfer to the sim | medium | mitigate | instructions require a byte-for-byte copy (`gal-02-handoff.md` re-send steps); the +1 counter and Transfer-line counts would expose a second submit; byte-exact equality pinned by the 06-01 tests; the sim has no real plate | closed |
| T-06-22 | Repudiation | an unfalsifiable "no second POST" (an uncalibrated counter) | medium | mitigate | the +1 calibration comes first (Findings 2b-3: counter before 2, after 2 — no second POST); an uncalibrated result is labelled "fallback evidence, user to judge", never a plain PASS | closed |
| T-06-SC (06-01) | Tampering | npm/pip/cargo installs | high | mitigate | no package installed; node is a pre-installed runtime; git diff on requirements.txt and tools/*/ pins stays clean | closed |
| T-06-SC (06-02) | Tampering | npm/pip/cargo installs | high | mitigate | no package installed (bash, awk, grep, cmp, jq and curl present); pins stay clean | closed |
| T-06-SC (06-03) | Tampering | npm/pip/cargo installs | high | mitigate | no package installed in this plan | closed |
| T-06-SC (06-04) | Tampering | npm/pip/cargo installs | high | mitigate | no package installed by Claude; PAC sim images built by the operator from the pinned commit per SAL A.1 | closed |

*Status: open · closed · open — below high threshold (non-blocking)*
*Severity: critical > high > medium > low — only open threats at or above workflow.security_block_on count toward threats_open*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-06-01 | T-06-06 | galago-core replaces a param value of the form `{`{...`}`}; step keys always end in `-in`/`-out` so a key cannot be altered this way, other values are operator-typed, and the behaviour is noted in the runbook (plan 06-02). | user (via plan threat model) | 2026-11-02 |

*Accepted risks do not resurface in future audit runs.*

---

## Audit Notes

- Register authored at plan time: all four PLAN files carry parseable `<threat_model>` blocks; all four SUMMARY files report `## Threat Flags: None`.
- L1 grep-depth verification at HEAD found every cited test and procedural control present (10/10 named tests, `TestDep02Gate`, `_StackTestCase` env isolation, hardware deny-set, runbook phrases, `checkpoint:human-action` gates, `byte for byte` copy instructions, counter calibration in Findings 2b-3).
- `threats_open: 0` with a plan-time register at ASVS L1 — workflow short-circuit applied; the `gsd-security-auditor` subagent was not required.
- Findings rows 2a-3 and 2b-3 record that the two re-dispatch sends were made by the orchestrator via tRPC `tool.runCommand` at the user's delegation instead of by the operator — logged as Deviations, consistent with T-06-13's checkpoint rule.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-11-02 | 26 | 26 | 0 | orchestrator L1 verification (ASVS L1, block_on: high; short-circuit, auditor not required) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-11-02
