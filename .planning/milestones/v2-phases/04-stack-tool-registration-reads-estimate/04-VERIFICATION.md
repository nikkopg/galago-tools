---
phase: 04-stack-tool-registration-reads-estimate
verified: 2026-11-02T00:00:00Z
status: passed
score: 6/6 must-haves verified
covered_files:
  - ".planning/phases/04-stack-tool-registration-reads-estimate/04-01-PLAN.md"
  - ".planning/phases/04-stack-tool-registration-reads-estimate/04-01-SUMMARY.md"
  - ".planning/phases/04-stack-tool-registration-reads-estimate/04-02-PLAN.md"
  - ".planning/phases/04-stack-tool-registration-reads-estimate/04-02-SUMMARY.md"
  - ".planning/phases/04-stack-tool-registration-reads-estimate/04-03-PLAN.md"
  - ".planning/phases/04-stack-tool-registration-reads-estimate/04-03-SUMMARY.md"
  - ".planning/phases/04-stack-tool-registration-reads-estimate/04-04-PLAN.md"
  - ".planning/phases/04-stack-tool-registration-reads-estimate/04-04-SUMMARY.md"
  - ".planning/phases/04-stack-tool-registration-reads-estimate/04-05-PLAN.md"
  - ".planning/phases/04-stack-tool-registration-reads-estimate/04-05-SUMMARY.md"
  - "interfaces/controller.proto"
  - "interfaces/tools/grpc_interfaces/stack.proto"
  - "interfaces/tools/grpc_interfaces/tool_base.proto"
  - "pyproject.toml"
  - "tools/stack/__init__.py"
  - "tools/stack/ledger.py"
  - "tools/stack/requirements.txt"
  - "tools/stack/server.py"
  - "tools/tests/stack_ledger_test.py"
  - "tools/tests/stack_test.py"
covered_digest: "v3:sha256:8bd4c96ac2548498495df12d36a547ab4d1fb0fcc05887c78c0278026596b969"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: passed
  previous_score: 6/6
  gaps_closed: []
  gaps_remaining: []
  regressions: []
superseded:
  - must_have: "Real-mode Transfer, AcknowledgeFailure and GetFailureLatch are refused with 'stack: <Cmd> is not available in this build' (04 SC5, 04-04 truth, UNAVAILABLE_COMMANDS)"
    superseded_by: "Phase 5 (XFR-01, ACK-01, ACK-02); 05-CONTEXT.md line 180 'UNAVAILABLE_COMMANDS is removed, along with its real-mode refusal'"
    evidence: "stack_test.py:4433 test_the_refusal_machinery_is_gone asserts UNAVAILABLE_COMMANDS and _unavailable_reply no longer exist; server.py Transfer (~1062), AcknowledgeFailure (~1310), GetFailureLatch are real handlers"
  - must_have: "No real-mode code path can move the arm; nothing in tools/stack/ calls plan_transfer, execute_transfer, wait, wait_transfer, acknowledge_failure (04 goal clause, 04-02 AST invariant, Phase 4 D-20)"
    superseded_by: "Phase 5 D-16 (XFR-05): 'The XFR-05 AST test over tools/stack/ replaces Phase 4 D-20'"
    evidence: "Narrower invariant now enforced by TestAdapterInvariant: start_transfer, cancel_transfer, go_to_safe_position, wait_safe_position, validate_transfer never called (independent AST scan: 0 hits); plan_transfer and execute_transfer have exactly one call site each, in _run_fresh (server.py:1179, 1193), execute_transfer after the write-ahead claim and outside any loop; acknowledge_failure has exactly one call site, in AcknowledgeFailure (server.py:1324) after the exact 'yes' check"
  - must_have: "Core pinned at ed8ce478d8881a517eb93ed233707f81aea01238 (04-01/04-02 truth)"
    superseded_by: "Phase 5 DEP-01 (core 934a621, hard dependency of XFR/ACK)"
    evidence: "tools/stack/requirements.txt pins 934a621ece116a8b263897c1e9b62b57374f4ef3 without [mcp]; installed direct_url.json commit_id is the same; TestRequirementsPin passes. The 'pinned by SHA' intent of STK-02 still holds; only the SHA moved, deliberately (Phase 4 D-22 'bump deliberately')"
advisory:
  - finding: "The setStatus override holds READY at FAILED whenever _configure_failed is set and service is None, and it applies in simulated mode too. After a failed real-mode Configure followed by a switch to simulated, commands still return SUCCESS but GetStatus reports FAILED."
    category: other
    reason: "Cosmetic status display only (carried forward unchanged from the previous report; the override at server.py:800 is unchanged in this respect). Consider scoping the hold to real mode when Phase 6 builds the simulated workcell."
    evidence_status: "reproduced in the previous verification; code path unchanged, not re-run"
---

# Phase 4: STACK Tool Registration, Reads & Estimate Verification Report

**Phase Goal:** An operator can register, Configure and read from a STACK tool in Galago (manager state, robots, devices, profiles, labware presence and a transfer estimate), and no real-mode code path can move the arm.
**Verified:** 2026-11-02
**Status:** passed
**Re-verification:** Yes. The prior report (2026-10-29, passed 6/6) went stale because Phase 5 (F5-safe Transfer and Operator Acknowledge, completed 2026-10-30) changed `tools/stack/server.py`, `tools/tests/stack_test.py`, `tools/stack/requirements.txt` and added `tools/stack/ledger.py` and `tools/tests/stack_ledger_test.py`. Every Phase 4 must-have was re-judged against the current code. Three must-haves were intentionally superseded by Phase 5 and are recorded as such (see "Superseded by Phase 5"), not as gaps. No genuine regression was found.

## Gate Command

`source ~/data/nikko/.venvs/galago-py310/bin/activate && bin/make proto test`: proto regeneration OK, full gate **510 passed in 10.68s** (includes `stack_test.py` and `stack_ledger_test.py`; `pytest tools/tests/stack_test.py tools/tests/stack_ledger_test.py` alone: 363 passed). The orchestrator's separate run (92 passed, 1 skipped, 166 subtests) is consistent. The installed core is stack-automation-layer `934a621ece116a8b263897c1e9b62b57374f4ef3` (`direct_url.json`), identical to the pin in `tools/stack/requirements.txt`. No source was edited; `git status` shows only the untracked `.planning/state.json`. No hardware was contacted (tests use loopback and fake transports; the `_StackTestCase` guard forbids anything else).

## Goal Achievement

### Observable Truths (ROADMAP Phase 4 success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `stack.proto` registered (tool_base Command `stack = 24`, Config `stack = 43`; controller `stack = 24`), gate green, server starts as `stack` | VERIFIED | `TestRegistration` and `TestProtoFreeze` pass. `git log` shows `stack.proto` last touched by `bcbbf8e` (04-01) and `git diff 69e102a..HEAD --stat -- interfaces` is empty, so the surface is unchanged since Phase 4. Gate green (510). |
| 2 | Configure with host/port; core opened only via `open_service(..., owner="galago")`, credentials from env, no `lock_dir` field; mcp-held lock fails Configure naming the holder; no `stack_automation_layer.mcp` import; core pinned by SHA | VERIFIED | Sole `open_service` call site `server.py:907` (`owner="galago"`, no `lock_dir`/`transport`). grep of `tools/stack/` finds no `stack_automation_layer.mcp`, `lock_dir` or `10.150`. `TestStackOwned`, `TestConfigureBusy`, `TestAdapterInvariant` (open_service shape, constructor and literal rules), `TestRequirementsPin` pass. Config now has `ledger_dir = 4` (Phase 5, in the frozen Phase 4 field list, validated absolute and recorded only); still no credential or lock field. Pin moved to `934a621` by Phase 5 DEP-01 (superseded must-have, intent "pinned by SHA, no `[mcp]`" intact). |
| 3 | Six reads each SUCCESS with empty message and the core's `to_dict()` in meta; `readFailed` / non-read kinds are `ERROR_FROM_TOOL` with one-line reason and guid, never SUCCESS; argument errors `INVALID_ARGUMENTS` | VERIFIED | Handlers `server.py` ~1020-1060 make one service call each on the admitted service via `_require_service()` and return `_result_reply`. `TestReadCommands`, `TestResultMapping`, `TestCheckArgs` pass. The 1:1 method map is unchanged (`COMMAND_TO_SERVICE_METHOD`, `GetFailureLatch` -> `latch_status`). |
| 4 | `GetTransferEstimate` works and nothing moves; simulated mode validates args (incl. `step_key`), sleeps constant `Estimate<Cmd>`, never contacts the core, never writes the ledger | VERIFIED | `GetTransferEstimate` calls only `service.estimate_transfer(...)`. `_dispatchCommand` runs `_check_args` first and in simulated mode returns `super()._dispatchCommand` before `_admit`, so no service, owner lock or ledger is touched. Estimate hooks are module constants (`EST_*`, `server.py:133-136`), no I/O. `TestEstimates`, `TestSimulatedCommands`, `TestSimulatedTransferOverGrpc` (incl. `test_a_simulated_transfer_never_writes_a_ledger_anywhere`, line 4082), `TestSimulatedBypassRead` pass. |
| 5 | Read while another command holds BUSY returns its result while motion stays serialised; a test proves nothing in `tools/stack/` calls core motion methods; real-mode `Transfer`/`AcknowledgeFailure` refused not-yet-available | VERIFIED for reads, serialisation and the no-forbidden-call test; the "refused not-yet-available" clause is SUPERSEDED by Phase 5 | Reads: `ExecuteCommand` bypass (`server.py:939-975`) routes `READ_COMMANDS` (8 names, `server.py:142`) through `_dispatchCommand` without `isReady`/`parseCommand`/`setStatus`; `TestBusyReads`, `TestReadCommandSet`, `TestReadBypassEdges` pass, and Phase 5 re-proved it on the real `Transfer` (`e292f76 test(05-07): STK-05 re-proven on the real Transfer`). Serialisation: `_MOTION_LOCK.acquire(blocking=False)` in `Transfer` plus base `isReady`; a second Transfer is refused at once with `_BUSY_MESSAGE`. No-motion test: `TestAdapterInvariant` still proves `start_transfer`, `cancel_transfer`, `go_to_safe_position`, `wait_safe_position`, `validate_transfer` are never called, and confines `plan_transfer`/`execute_transfer`/`acknowledge_failure` to single named sites (see Superseded). |
| 6 | `stack.proto` frozen for v2: full surface incl. `Transfer`, `AcknowledgeFailure`, latch-status read | VERIFIED | Ten-command oneof pinned by `TestProtoFreeze` (passing); no change under `interfaces/` since Phase 4. Phase 5 filled in the handlers behind the frozen surface without a proto change, so DEP-02 codegen is not re-opened. |

**Score:** 6/6 truths verified (0 present, behavior-unverified). Superseded clauses are not counted as failures.

### Superseded by Phase 5 (not gaps)

Phase 5 is the planned owner of the only motion path. These Phase 4 clauses were retired on purpose by Phase 5 requirements, and the replacement guards are verified.

| Phase 4 must-have | Superseded by | Evidence the replacement holds |
|-------------------|---------------|--------------------------------|
| Real-mode `Transfer`/`AcknowledgeFailure`/`GetFailureLatch` refused with "not available in this build" (SC5, 04-04, `UNAVAILABLE_COMMANDS`) | Phase 5 XFR-01, ACK-01, ACK-02; 05-CONTEXT line 180 ("`UNAVAILABLE_COMMANDS` is removed, along with its real-mode refusal") | `test_the_refusal_machinery_is_gone` (stack_test.py:4433) passes; `UNAVAILABLE_COMMANDS` is absent from `server.py`. `AcknowledgeFailure` still requires the exact string `"yes"` and a non-blank guid before any admission (`server.py` `_dispatchCommand`: `_ACK_NOT_YES_MESSAGE`, `INVALID_ARGUMENTS`). |
| "No real-mode code path can move the arm"; blanket AST ban on `plan_transfer`/`execute_transfer`/`wait`/`wait_transfer`/`acknowledge_failure` (goal clause, 04-02, D-20) | Phase 5 D-16 / XFR-05 ("The XFR-05 AST test over `tools/stack/` replaces Phase 4 D-20"); ROADMAP Phase 5 is "the only motion path" | Independent AST scan of `tools/stack/*.py`: `start_transfer`, `cancel_transfer`, `go_to_safe_position`, `wait_safe_position`, `validate_transfer` have 0 hits. `plan_transfer` appears once (`server.py:1179`) and `execute_transfer` once (`server.py:1193`), both in `_run_fresh`, after the write-ahead claim, no loop; `acknowledge_failure` once (`server.py:1324`) in `AcknowledgeFailure`. `tools/stack/ledger.py` imports only stdlib and does not touch the core. The motion path is gated by the step-key ledger (decide(), write-ahead, `_MOTION_LOCK`), never reachable from simulated mode, never from any of the eight reads. Phase 5 itself was verified (05-VERIFICATION.md, passed 6/6). The Phase 4 intent ("reads and estimate never move the arm; any motion is a deliberate, guarded, single-site path") holds. |
| Core pin `ed8ce478...` | Phase 5 DEP-01 (core `934a621`, latch/ownership/in-flight guard + `latchStatus`) | `requirements.txt` pins `934a621ece116a8b263897c1e9b62b57374f4ef3`, no `[mcp]`; installed commit matches; `TestRequirementsPin` passes. |

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `interfaces/tools/grpc_interfaces/stack.proto` | Frozen 10-command surface and Config | VERIFIED | Unchanged since `bcbbf8e`. |
| `interfaces/tools/grpc_interfaces/tool_base.proto`, `interfaces/controller.proto` | Command 24 / Config 43 / ToolType 24 | VERIFIED | Unchanged. |
| `tools/stack/server.py` | StackServer, mapping, reads, bypass, Configure hardening | VERIFIED | 1372 lines (Phase 5 added Transfer/Acknowledge/latch); no debt markers; all Phase 4 reads and Configure hardening intact. |
| `tools/stack/requirements.txt` | SHA-pinned core, no `[mcp]` | VERIFIED | Pin is now `934a621` (DEP-01). |
| `tools/stack/ledger.py` | Phase 5 step ledger (not a Phase 4 artifact) | VERIFIED (relied on only for the supersession evidence) | 513 lines, stdlib only. |
| `tools/tests/stack_test.py`, `tools/tests/stack_ledger_test.py` | Phase 4 test classes retained | VERIFIED | `TestRegistration`, `TestProtoFreeze`, `TestStackOwned`, `TestConfigureBusy`, `TestReconfiguringAdmission`, `TestRequirementsPin`, `TestReadCommands`, `TestResultMapping`, `TestCheckArgs`, `TestEstimates`, `TestSimulated*`, `TestBusyReads`, `TestReadCommandSet`, `TestReadBypassEdges` all present and passing. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| tool_base.proto | stack.proto | import + `stack = 24` / `= 43` | WIRED | `TestRegistration`. |
| `_apply_config` | `open_service` | `open_service(host, port, owner="galago")` inside `_exclusive()` | WIRED | `server.py:907`, only call site. |
| `_dispatchCommand` | `_admit` / `_leave` | real-mode bracket, args and simulated first | WIRED | `server.py:977-1005`. |
| read handlers | `_require_service` -> `_result_reply` | admitted service, one call each | WIRED | ~1020-1060. |
| `ExecuteCommand` | `_dispatchCommand` | `field_name in READ_COMMANDS`, no status calls | WIRED | `server.py:957`. |
| `TestAdapterInvariant` | `tools/stack/*.py` | `ast.parse` of every module, Phase 5 narrower rules | WIRED | passes. |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
|----------|------|--------|-----------|--------|
| read handlers | reply meta | `service.<method>().to_dict()` unchanged | Yes (core result; live hardware is Phase 7) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full gate | `bin/make proto test` | 510 passed | PASS |
| STACK suites | `pytest tools/tests/stack_test.py tools/tests/stack_ledger_test.py -q` | 363 passed | PASS |
| Forbidden core calls absent | independent AST scan of `tools/stack/*.py` | 0 hits for the five forbidden names; one site each for plan/execute/acknowledge | PASS |
| No mcp import, hardware literal, `lock_dir`, debt markers | grep `tools/stack/` | no matches | PASS |
| Core pin | installed `direct_url.json` vs `requirements.txt` | both `934a621ece116a8b263897c1e9b62b57374f4ef3` | PASS |
| Single `open_service` call site | grep | `server.py:907` only | PASS |

### Probe Execution

SKIPPED: the phase declares no `probe-*.sh` scripts.

### Requirements Coverage

All seven IDs appear in PLAN frontmatter (04-01: STK-01, 02, 03, 07; 04-02: STK-02, 05; 04-03: STK-03, 04, 07; 04-04: STK-04, 05, 06; 04-05: STK-05) and in REQUIREMENTS.md (all `[x]`, mapped to Phase 4 / Complete). REQUIREMENTS.md maps no other ID to Phase 4; none orphaned.

| Requirement | Source Plan | Status | Evidence |
|-------------|-------------|--------|----------|
| STK-01 | 04-01 | SATISFIED | SC1, SC6. |
| STK-02 | 04-01, 04-02 | SATISFIED | SC2 (SHA pin moved by DEP-01, still pinned). |
| STK-03 | 04-01, 04-03 | SATISFIED | SC3. |
| STK-04 | 04-03, 04-04 | SATISFIED | SC4. |
| STK-05 | 04-02, 04-04, 04-05 | SATISFIED | SC5; reads answer while BUSY, motion serialised, re-proven by Phase 5 on the real Transfer. |
| STK-06 | 04-04 | SATISFIED | SC4; simulated path core-free and ledger-free. |
| STK-07 | 04-01, 04-03 | SATISFIED | SC3; result mapping unchanged and now also covers `failureAcknowledged`. |

### Anti-Patterns Found

No `TBD`, `FIXME`, `XXX`, `TODO` or `HACK` in `tools/stack/`; no stub returns. Debt-marker gate clear.

### Deferred Items

None.

### Advisory (New Scope, Unevidenced)

| # | Finding | Category | Why Advisory |
|---|---------|----------|--------------|
| 1 | `setStatus` holds READY at FAILED in simulated mode after a failed real Configure (status display only) | other | Carried forward; cosmetic, commands unaffected |

The earlier second advisory (busy-refused Configure leaving status FAILED) was closed by Phase 5 `9d6bc4d fix(05): WR-02 keep the tool READY when a Configure is refused as busy` (`_ConfigureRefused` plus the `setStatus` restore of the prior status, `server.py:800-825`).

### Human Verification Required

None. Live STACK behavior is outside Phase 4's loopback-tested scope and belongs to Phase 7 (LIVE-*).

### Gaps Summary

No gaps. All six ROADMAP success criteria and all seven requirement IDs (STK-01..STK-07) hold against the current code. Three Phase 4 clauses (real-mode refusal of Transfer/AcknowledgeFailure/GetFailureLatch, the blanket "no motion" AST ban, and the old core SHA) were deliberately superseded by Phase 5 (XFR-01/05, ACK-01/02, D-16, DEP-01); the replacement invariants are in place and tested, so these are recorded as superseded, not regressions.

---

_Verified: 2026-11-02_
_Verifier: Claude (gsd-verifier)_
