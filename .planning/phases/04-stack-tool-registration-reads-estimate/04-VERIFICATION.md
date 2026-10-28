---
phase: 04-stack-tool-registration-reads-estimate
verified: 2026-10-29T05:45:00Z
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
  - "tools/stack/requirements.txt"
  - "tools/stack/server.py"
  - "tools/tests/stack_test.py"
covered_digest: "v3:sha256:141fd2c231fd49b2928c1444c13298488fd3aae0e17f9e31dd616ca4dc75ab2f"
behavior_unverified: 0
overrides_applied: 0
---

# Phase 4: STACK Tool Registration, Reads & Estimate Verification Report

**Phase Goal:** An operator can register, Configure and read from a STACK tool in Galago (manager state, robots, devices, profiles, labware presence and a transfer estimate), and no real-mode code path can move the arm.
**Verified:** 2026-10-29
**Status:** passed
**Re-verification:** No, initial verification

## Gate Command

`source ~/data/nikko/.venvs/galago-py310/bin/activate && bin/make proto test` was run by the verifier:
proto regeneration OK, `ruff check .` "All checks passed!", `mypy ... tools` "Success: no issues found in 92 source files", **250 passed in 2.16s**. No STACK motion was performed and no connection was made to 10.150.1.125 / stack-server (the tests use loopback ports and fake transports; the `_StackTestCase` loopback guard and AST literal rule forbid those addresses).

## Goal Achievement

### Observable Truths (ROADMAP Phase 4 success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `stack.proto` registered (tool_base Command `stack = 24`, Config `stack = 43`; controller `stack = 24`), gate green, `python -m tools.stack.server --port=N` starts and reports as `stack` | VERIFIED | `tool_base.proto:56` Command stack=24, `:87` Config stack=43, `controller.proto:31` stack=24. Runtime check of the generated descriptors printed `24`, then `24 43`. `TestRegistration` pins all three plus `StackServer.toolType == "stack"`. `timeout 6 python -m tools.stack.server --port=50999` logged "stack server started, listening on 50999". Gate green (250 passed, ruff and mypy clean). |
| 2 | Configure with host/port; core opened only via `open_service(..., owner="galago")`, credentials from `STACK_USER`/`STACK_PASSWORD`, no `lock_dir` field; mcp-held lock fails Configure naming the holder; no `stack_automation_layer.mcp` import; core pinned by SHA | VERIFIED | `server.py:305` `open_service(host, port, owner="galago")` is the only open site. `stack.proto` Config is host/port/transfer_timeout_s/ledger_dir (no lock_dir, no credential field), pinned by `TestProtoFreeze`. `TestStackOwned.test_mcp_holder_fails_configure_naming_the_holder` asserts NOT_READY, "already owned by mcp", FAILED status, service None, no REST client constructed, other holder's lock untouched. Credentials-missing and password non-leak covered in `TestConfigureFails` (stack_test.py:477-488). `TestAdapterInvariant` AST checks forbid mcp imports (3 forms), `lock_dir`/`transport` kwargs, core constructors, and the forbidden host literals; `grep` of `tools/stack/` finds no mcp import or hardware literal. `requirements.txt` pins `@ed8ce478d8881a517eb93ed233707f81aea01238` with no `[mcp]` extra; installed `direct_url.json` commit_id equals it (`TestRequirementsPin`). |
| 3 | Six reads each SUCCESS with empty message and core `to_dict()` in meta; `readFailed`/non-read kinds are `ERROR_FROM_TOOL` with one-line reason and guid, never SUCCESS; argument errors `INVALID_ARGUMENTS` | VERIFIED | `server.py:359-379` six handlers, each one service call. `_result_reply` (`:260`) returns SUCCESS only for kinds in the explicit `_SUCCESS_KINDS` allowlist, with `meta=d` unchanged; any other kind or non-dict goes to `ERROR_FROM_TOOL` with `_error_line` (kind, reason, guid, one bounded hint, no explanation text, whitespace collapsed, 300-char cap). `_check_args` returns `INVALID_ARGUMENTS`. Covered by `TestReadCommands`, `TestResultMapping`, `TestCheckArgs` (all passing). |
| 4 | `GetTransferEstimate` works and nothing moves; simulated mode validates args (incl. `step_key`), sleeps constant `Estimate<Cmd>`, never contacts the core, never writes the ledger | VERIFIED | `GetTransferEstimate` (`:381`) calls only `service.estimate_transfer(_transfer_request(params))`. `_dispatchCommand` (`:339`) runs `_check_args` first in both modes, then defers to base simulated branch which sleeps `Estimate<Cmd>`; ten constant hooks at `:397-427` do no I/O. `TestSimulatedCommands`, `TestSimulatedTransferOverGrpc`, `TestEstimates` (incl. EstimateDuration RPC with malformed args) pass; no `open_service` in simulated mode, no lock/ledger file created. |
| 5 | A read issued while another command holds the tool BUSY returns its result (injected slow command) while motion stays serialised; real-mode `Transfer`/`AcknowledgeFailure` refused with a not-yet-available error; a test proves nothing in `tools/stack/` calls core motion methods | VERIFIED | `ExecuteCommand` override (`:309-337`) bypasses isReady/parseCommand/setStatus for `READ_COMMANDS` only (transfer and acknowledge_failure excluded; `TestReadCommandSet`). `TestBusyReads` blocks a real gRPC Transfer inside its handler, confirms status BUSY, all seven reads return their own SUCCESS meta, the latch returns its refusal line, status stays BUSY, a second Transfer gets NOT_READY, then status returns to READY. Git order confirms test-first: `fe97a7d test(04-05)` precedes `9efb8fa feat(04-05)`. `Transfer`/`AcknowledgeFailure`/`GetFailureLatch` (`:385-395`) return `"stack: <Cmd> is not available in this build"` as `ERROR_FROM_TOOL` without touching the service (`TestRealModeRefusals*`). `TestAdapterInvariant` walks every `tools/stack/*.py` AST and reports the ten forbidden core calls (plan_transfer, execute_transfer, start_transfer, wait, wait_transfer, cancel_transfer, go_to_safe_position, wait_safe_position, acknowledge_failure, validate_transfer), with planted-violation tests proving the detector fires. Manual read of `server.py` confirms no such call. `tools/base_server.py` is unchanged since phase start. |
| 6 | `stack.proto` frozen for v2: full surface incl. Transfer, AcknowledgeFailure and latch-status read | VERIFIED | `stack.proto` Command oneof has exactly the ten commands numbered 1-10 with `optional` presence on every nested field; `TestProtoFreeze` pins the oneof list, every nested field name and type, and Config. The user sign-off on the freeze is recorded as an Plan 01 checkpoint (autonomous: false) in 04-01-SUMMARY. |

**Score:** 6/6 truths verified (0 present, behavior-unverified). The only behavior-dependent truth (SC5 BUSY bypass and status invariants) has a passing behavioral test, not just symbol presence.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `interfaces/tools/grpc_interfaces/stack.proto` | Frozen 10-command surface and Config | VERIFIED | Present, substantive, imported by `tool_base.proto:29`, compiled by `bin/make proto`. |
| `interfaces/tools/grpc_interfaces/tool_base.proto` | Command 24 / Config 43 registration | VERIFIED | Lines 29, 56, 87. |
| `interfaces/controller.proto` | `stack = 24` ToolType | VERIFIED | Line 31. |
| `tools/stack/server.py` | StackServer, mapping, reads, refusals, bypass | VERIFIED | 437 lines, no stubs, wired through `serve(StackServer(), ...)`. |
| `tools/stack/requirements.txt` | SHA-pinned core, no `[mcp]` | VERIFIED | Single pinned line. |
| `tools/stack/__init__.py`, `pyproject.toml` | Package and mypy override | VERIFIED | Present; mypy clean. |
| `tools/tests/stack_test.py` | Registration, freeze, tracer, ownership, mapping, simulation, bypass tests | VERIFIED | 103 tests, all passing. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| tool_base.proto | stack.proto | import + `stack = 24` / `= 43` | WIRED | Confirmed by grep and descriptor check. |
| server.py `_configure` | `open_service` | `open_service(host, port, owner="galago")` | WIRED | `server.py:305`. |
| read handlers | `_result_reply` | `return _result_reply(<one service call>)` | WIRED | `:359-383`. |
| `_dispatchCommand` | `_check_args` | argument check before simulated branch and handlers | WIRED | `:342`. |
| `ExecuteCommand` | `_dispatchCommand` | `field_name in READ_COMMANDS` | WIRED | `:327-331`. |
| TestAdapterInvariant | `tools/stack/*.py` | `ast.parse` of every module | WIRED | `_STACK_SOURCES`. |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
|----------|------|--------|-----------|--------|
| read handlers | reply meta | `service.<method>().to_dict()` from the core, passed through unchanged | Yes (core result; the real hardware path is exercised in later phases) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full gate | `bin/make proto test` | 250 passed, ruff and mypy clean | PASS |
| Server starts as stack tool | `timeout 6 python -m tools.stack.server --port=50999` | "stack server started, listening on 50999" | PASS |
| Registration numbers | descriptor probe | ToolType stack=24, Command stack=24, Config stack=43 | PASS |
| Core pin | `direct_url.json` | commit_id `ed8ce478d8881a517eb93ed233707f81aea01238` | PASS |

### Probe Execution

SKIPPED: the phase declares no `probe-*.sh` scripts.

### Requirements Coverage

All seven IDs appear in PLAN frontmatter (04-01: STK-01, 02, 03, 07; 04-02: STK-02, 05; 04-03: STK-03, 04, 07; 04-04: STK-04, 05, 06; 04-05: STK-05) and in REQUIREMENTS.md. None are orphaned.

| Requirement | Source Plan | Status | Evidence |
|-------------|-------------|--------|----------|
| STK-01 | 04-01 | SATISFIED | SC1, SC6; proto registered and frozen, gate green. |
| STK-02 | 04-01, 04-02 | SATISFIED | SC2; `open_service` owner galago, holder-named failure, SHA pin, no MCP import. |
| STK-03 | 04-01, 04-03 | SATISFIED | SC3; six reads 1:1 with `to_dict()` meta (`COMMAND_TO_SERVICE_METHOD`, `TestOneToOneSurface`). |
| STK-04 | 04-03, 04-04 | SATISFIED | SC4; estimate read plus constant `Estimate<Cmd>` hooks. |
| STK-05 | 04-02, 04-04, 04-05 | SATISFIED | SC5; BUSY bypass proven, motion serialised, no motion call possible. |
| STK-06 | 04-04 | SATISFIED | SC4; simulated mode validates args, sleeps constants, core-free. |
| STK-07 | 04-01, 04-03 | SATISFIED | SC3; kind allowlist, one-line error, `INVALID_ARGUMENTS`. |

### Anti-Patterns Found

No `TBD`, `FIXME`, `XXX`, `TODO` or stub returns in `tools/stack/` (debt-marker gate clear). The code review (0 critical, 5 warnings, 3 info; all dispositions still `open` in `04-REVIEW-DISPOSITION.md`) was weighed against the goal:

| File | Line | Pattern | Severity | Impact on goal |
|------|------|---------|----------|----------------|
| `tools/stack/server.py` | 296-306 | WR-01: `OwnedService.close()` raising leaves `_owned`/`service` set and the lock leaked | Warning | Lifecycle robustness on a Configure retry after a transport-close exception. Does not enable motion; goal not undermined. |
| `tools/stack/server.py` | 284-292, 324-337 | WR-02: validation-failed re-Configure keeps the previous service; reads still answered under status FAILED | Warning | Inconsistent state on an unusual operator sequence (reads, not motion). Goal not undermined, but should be fixed before the live phases. |
| `tools/stack/server.py` | 283-307 | WR-03: no lock between Configure and bypassed reads or between concurrent Configures | Warning | Race window yields DRIVER_ERROR or `readFailed`, never SUCCESS from a closed client. Goal not undermined. |
| `tools/stack/server.py` | 329-336 | WR-04: bypassed read overwrites `last_error` | Warning | Matters once Transfer exists (Phase 5). No effect in Phase 4. |
| `tools/stack/server.py` | 284-305 | WR-05: `host` not validated for URL-reserved characters | Warning | Hardening gap on a trusted-controller input; credentials go to the Config host. Not exploitable by an untrusted party in the current design. |
| `tools/stack/server.py` | various | IN-01..IN-03 | Info | Documentation and cosmetic. |

None of the five warnings touches the "no real-mode path can move the arm" half of the goal: the only service methods the adapter can call are the seven read/estimate methods, enforced by the AST invariant test, and the three Phase 5 commands never reach the service.

### Human Verification Required

None. Hardware behavior (a live STACK read) is explicitly outside Phase 4's no-motion, loopback-tested scope and is covered by Phase 7 (LIVE-*).

### Gaps Summary

No gaps. All six ROADMAP success criteria and all seven requirement IDs (STK-01..STK-07) are verified in the codebase and by the gate (250 passed, ruff and mypy clean). Recommendation (non-blocking): triage `WR-01..WR-05` (all still `open` in the disposition file) before Phase 5 adds a real Transfer, since WR-02, WR-03 and WR-04 become more consequential once a long-running motion command exists.

---

_Verified: 2026-10-29_
_Verifier: Claude (gsd-verifier)_
