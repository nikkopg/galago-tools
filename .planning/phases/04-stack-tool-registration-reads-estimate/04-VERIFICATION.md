---
phase: 04-stack-tool-registration-reads-estimate
verified: 2026-10-29T08:05:00Z
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
covered_digest: "v3:sha256:d576c77137b8b217805ab3ec050dd93e5c2ecf8ebcac25844d46a5601f043d57"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: passed
  previous_score: 6/6
  gaps_closed: []
  gaps_remaining: []
  regressions: []
advisory:
  - finding: "Configure drains in-flight commands with no timeout while holding the state condition, so a long-running command (Phase 5 Transfer) would stall Configure and park every command, including BUSY-bypass reads, behind it (04-REVIEW WR-01)"
    category: architectural
    reason: "No long-running real-mode command exists in Phase 4 (Transfer, AcknowledgeFailure and GetFailureLatch are refused instantly; reads are bounded by core transport timeouts). Becomes real only when Phase 5 adds a motion command. Bound the wait or refuse-fast while reconfiguring before Phase 5."
    evidence_status: "code-read plus 6-second multi-thread stress run (no hang); latent hazard not reproducible in Phase 4"
  - finding: "A non-read command parked behind a failing Configure can reset status to READY with no service and overwrite last_error (04-REVIEW WR-02)"
    category: architectural
    reason: "Reachable in Phase 4 only through the instant refusals; resulting state is READY with service None, in which every read returns NOT_READY and no motion path exists. Cosmetic status inconsistency now; matters when Transfer exists. Snapshot the service and admission under one lock before Phase 5."
    evidence_status: "code-read; not reproduced"
---

# Phase 4: STACK Tool Registration, Reads & Estimate Verification Report

**Phase Goal:** An operator can register, Configure and read from a STACK tool in Galago (manager state, robots, devices, profiles, labware presence and a transfer estimate), and no real-mode code path can move the arm.
**Verified:** 2026-10-29
**Status:** passed
**Re-verification:** Yes. The previous report (250 tests) went stale after the review-fix commits `3567aa0..6e1c585` (WR-01..WR-05) changed `tools/stack/server.py` and `tools/tests/stack_test.py`. Every criterion was re-checked against the current code, with extra scrutiny on STK-02, STK-05 and the no-motion invariant.

## Gate Command

`source ~/data/nikko/.venvs/galago-py310/bin/activate && cd /home/formulatrix/data/nikko/galago-tools && bin/make proto test` was run by the verifier: proto regeneration OK, `ruff check .` "All checks passed!", `mypy ... tools` "Success: no issues found in 92 source files", **261 passed in 3.09s** (250 baseline plus 11 regression tests). No STACK motion was performed and nothing contacted 10.150.1.125 / stack-server (loopback ports, fake transports; the `_StackTestCase` loopback guard forbids anything else). The STACK core in the venv is stack-automation-layer 0.1.0 at `ed8ce478d8881a517eb93ed233707f81aea01238` (`direct_url.json`).

## Goal Achievement

### Observable Truths (ROADMAP Phase 4 success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `stack.proto` registered (tool_base Command `stack = 24`, Config `stack = 43`; controller `stack = 24`), gate green, `python -m tools.stack.server --port=N` starts and reports as `stack` | VERIFIED | `tool_base.proto:56` (`Command stack = 24`), `:87` (`Config stack = 43`), `controller.proto:31` (`stack = 24`). `StackServer.toolType = "stack"` (`server.py:282`). Live run: `python -m tools.stack.server --port=50998` logged "stack server started, listening on 50998". Gate green (261 passed, ruff, mypy clean). `TestRegistration` still passes. |
| 2 | Configure with host/port; core opened only via `open_service(..., owner="galago")`, credentials from `STACK_USER`/`STACK_PASSWORD`, no `lock_dir` field; an mcp-held lock fails Configure naming the holder; no `stack_automation_layer.mcp` import; core pinned by SHA | VERIFIED | Sole open site `server.py:409` `open_service(host, port, owner="galago")`; no credential or `lock_dir` field in Config (`TestProtoFreeze`). `grep` of `tools/stack/` finds no `stack_automation_layer.mcp`, no `lock_dir`, and no hardware literal. `requirements.txt` pins `@ed8ce478...` with no `[mcp]` extra, matching the installed `direct_url.json` commit. Passing tests: `TestStackOwned.test_mcp_holder_fails_configure_naming_the_holder`, `TestConfigureFails` (missing credentials, password non-leak), `TestRequirementsPin`, `TestAdapterInvariant` (mcp imports, `lock_dir`/`transport` kwargs, constructors, literals). The fixes did not regress this: WR-01 `_teardown` releases the old owner's lock idempotently and clears `_owned`/`service` first, and WR-02 drops the owner on any Configure failure, so a failed Configure always means no service and no held lock. WR-05 adds `_HOST_RE` fullmatch and a 1..65535 port check before any open; tests accept `127.0.0.1`, `localhost`, hostnames, bracketed IPv6 and reject `@ / ? # \`, whitespace and scheme forms. |
| 3 | Six reads each SUCCESS with empty message and core `to_dict()` in meta; `readFailed` and any non-read kind are `ERROR_FROM_TOOL` with one-line reason and guid, never SUCCESS; argument errors `INVALID_ARGUMENTS` | VERIFIED | Handlers `server.py:474-498` each make one service call and return `_result_reply` (`:269`): SUCCESS only for `kind` in the explicit `_SUCCESS_KINDS` allowlist with `meta=d` unchanged; anything else (or a non-dict) is `ERROR_FROM_TOOL` via `_error_line` (kind, reason, guid, one bounded hint, whitespace collapsed, 300-char cap). `_check_args` yields `INVALID_ARGUMENTS`. `TestReadCommands`, `TestResultMapping`, `TestCheckArgs`, `TestOneToOneSurface` pass. |
| 4 | `GetTransferEstimate` works and nothing moves; simulated mode validates args (incl. `step_key`), sleeps constant `Estimate<Cmd>`, never contacts the core, never writes the ledger | VERIFIED | `GetTransferEstimate` (`:496`) calls only `service.estimate_transfer(...)`. `_dispatchCommand` (`:451`) runs `_check_args` first in both modes; in simulated mode it returns `super()._dispatchCommand` before the `_in_flight` tracker and before any service access. The ten `Estimate*` hooks (`:512-542`) return module constants and do no I/O. `TestEstimates`, `TestSimulatedCommands`, `TestSimulatedTransferOverGrpc`, `TestSimulatedBypassRead` pass. |
| 5 | A read issued while another command holds the tool BUSY returns its result (injected slow command) while motion stays serialised; real-mode `Transfer`/`AcknowledgeFailure` refused with a not-yet-available error; a test proves nothing in `tools/stack/` calls core motion methods | VERIFIED | `ExecuteCommand` override (`:413-449`) bypasses `isReady`/`parseCommand`/`setStatus` for `READ_COMMANDS` only (the eight reads; `transfer` and `acknowledge_failure` excluded, `TestReadCommandSet`). `TestBusyReads` (passing) blocks a real gRPC Transfer inside its handler, confirms status BUSY, gets seven reads answered with their own SUCCESS meta and the latch refusal, status stays BUSY, a second Transfer gets NOT_READY, then READY. After WR-03, `_in_flight` only waits while `_reconfiguring` is true, so reads do not block on a running command, only on a Configure (see Advisory). After WR-04, `last_error` writes on a bypassed-read thread are dropped (thread-local), and the new tests `test_reads_do_not_clear_or_overwrite_the_last_error`, `test_last_error_survives_reads_while_a_transfer_is_in_flight` and `test_a_non_read_command_still_records_its_error` pass, so bypass reads leave status and `last_error` untouched. `Transfer`/`AcknowledgeFailure`/`GetFailureLatch` (`:500-510`) return `"stack: <Cmd> is not available in this build"` as `ERROR_FROM_TOOL` without touching the service. No-motion invariant: `TestAdapterInvariant` is unchanged by the fixes (the test diff adds no change to it and `Condition.wait_for` is a different attribute from the banned `.wait`); it passes against the current `server.py`. An independent AST scan by the verifier of all ten forbidden core calls (`plan_transfer`, `execute_transfer`, `start_transfer`, `wait`, `wait_transfer`, `cancel_transfer`, `go_to_safe_position`, `wait_safe_position`, `acknowledge_failure`, `validate_transfer`) over `tools/stack/server.py` returned `[]`. `tools/base_server.py` has no diff since before the phase. |
| 6 | `stack.proto` frozen for v2: full surface incl. `Transfer`, `AcknowledgeFailure` and the latch-status read | VERIFIED | Ten-command oneof with `optional` field presence, pinned by `TestProtoFreeze` (passing). `git diff 69e102a..HEAD` shows no change to `interfaces/` or `requirements.txt`; the review fixes touched only `server.py` and `stack_test.py`. |

**Score:** 6/6 truths verified (0 present, behavior-unverified). The behavior-dependent truths (SC5 BUSY bypass, status and `last_error` invariants, Configure serialisation) each have a passing behavioral test.

### Concurrency Re-check (WR-03 code, the riskiest change)

Read `server.py:291-299, 340-382, 461-467` in full.
- **Lock order:** `_configure_lock`, then `_state` (`_configure`: `with self._configure_lock, self._exclusive()`). `_in_flight` takes only `_state`. No inversion and no nested `_in_flight` in Phase 4.
- **Counter integrity:** `_readers += 1` and the `try` are adjacent; the decrement and `notify_all` are in a `finally`; `_exclusive` clears `_reconfiguring` and notifies in a `finally`, so an exception in the body cannot wedge commands. `Condition.wait_for` releases the lock while waiting, so a finishing command can decrement.
- **Simulated mode** returns before the tracker, so simulated reads never wait on Configure.
- **Stress run (verifier, not committed):** 6 reader threads, 2 Transfer-refusal threads and 3 Configure threads (75% valid configures to three loopback ports, 25% blank-host failures) calling `StackServer.Configure`/`ExecuteCommand` directly with a fake transport for 6 seconds: 104,674 reads, 7,850 transfer refusals and 419 Configures; no deadlock (0 threads alive), no unexpected response code, `service is None` iff `_owned is None`, `_readers == 0`, `_reconfiguring == False`, and a final Configure to a new port succeeded (so no owner lock leaked).
- **Regression tests:** `TestConfigureConcurrency` (Configure parks behind an in-flight read and the read completes on an open transport; two concurrent Configures leave one consistent owner), `TestConfigureCloseFails`, `TestConfigureFailureDropsService`, `TestConfigureHostValidation` all pass.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `interfaces/tools/grpc_interfaces/stack.proto` | Frozen 10-command surface and Config | VERIFIED | Unchanged, imported by `tool_base.proto`, compiled by `bin/make proto`. |
| `interfaces/tools/grpc_interfaces/tool_base.proto` | Command 24 / Config 43 | VERIFIED | Lines 56 and 87. |
| `interfaces/controller.proto` | `stack = 24` ToolType | VERIFIED | Line 31. |
| `tools/stack/server.py` | StackServer, mapping, reads, refusals, bypass, Configure hardening | VERIFIED | 552 lines, no stubs or debt markers, wired via `serve(StackServer(), ...)`. |
| `tools/stack/requirements.txt` | SHA-pinned core, no `[mcp]` | VERIFIED | Single pinned line. |
| `tools/stack/__init__.py`, `pyproject.toml` | Package and mypy override | VERIFIED | Present; mypy clean. |
| `tools/tests/stack_test.py` | Registration, freeze, ownership, mapping, simulation, bypass, concurrency tests | VERIFIED | 261-test gate passes. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| tool_base.proto | stack.proto | import + `stack = 24` / `= 43` | WIRED | grep and gate. |
| `_apply_config` | `open_service` | `open_service(host, port, owner="galago")` | WIRED | `server.py:409`, only call site. |
| `_configure` | `_exclusive` / `_teardown` | context manager and failure teardown | WIRED | `:346-351`. |
| `_dispatchCommand` | `_in_flight` / `_check_args` | real-mode bracket, args first | WIRED | `:454-467`. |
| read handlers | `_result_reply` | one service call each | WIRED | `:474-498`. |
| `ExecuteCommand` | `_dispatchCommand` | `field_name in READ_COMMANDS` | WIRED | `:431-438`. |
| `last_error` setter | `_read_bypass` thread-local | drops bypass-thread writes | WIRED | `:301-320`, `:435`. |
| TestAdapterInvariant | `tools/stack/*.py` | `ast.parse` of every module | WIRED | passes on current source. |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
|----------|------|--------|-----------|--------|
| read handlers | reply meta | `service.<method>().to_dict()` passed through unchanged | Yes (core result; live hardware is Phase 7) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full gate | `bin/make proto test` | 261 passed, ruff and mypy clean | PASS |
| Server starts as stack tool | `python -m tools.stack.server --port=50998` | "stack server started, listening on 50998" | PASS |
| Core pin | installed `direct_url.json` | commit_id `ed8ce478d8881a517eb93ed233707f81aea01238` | PASS |
| No motion call in adapter | independent AST scan for the ten forbidden core calls | `[]` | PASS |
| No mcp import, hardware literal or `lock_dir` | grep `tools/stack/` | no matches | PASS |
| Configure/read concurrency | 11-thread stress, 6 s | no deadlock, consistent state, no lock leak | PASS |

### Probe Execution

SKIPPED: the phase declares no `probe-*.sh` scripts.

### Requirements Coverage

All seven IDs appear in PLAN frontmatter (04-01: STK-01, 02, 03, 07; 04-02: STK-02, 05; 04-03: STK-03, 04, 07; 04-04: STK-04, 05, 06; 04-05: STK-05) and in REQUIREMENTS.md (all marked Complete, mapped to Phase 4). None is orphaned.

| Requirement | Source Plan | Status | Evidence |
|-------------|-------------|--------|----------|
| STK-01 | 04-01 | SATISFIED | SC1, SC6. |
| STK-02 | 04-01, 04-02 | SATISFIED | SC2, re-checked after WR-01/02/03/05. |
| STK-03 | 04-01, 04-03 | SATISFIED | SC3. |
| STK-04 | 04-03, 04-04 | SATISFIED | SC4. |
| STK-05 | 04-02, 04-04, 04-05 | SATISFIED | SC5, re-checked after WR-03/04. |
| STK-06 | 04-04 | SATISFIED | SC4. |
| STK-07 | 04-01, 04-03 | SATISFIED | SC3. |

### Anti-Patterns Found

No `TBD`, `FIXME`, `XXX`, `TODO` or `HACK` in `tools/stack/`; no stub returns (debt-marker gate clear). The incremental review (0 critical, 2 warnings, 5 info) was weighed against the goal:

| File | Line | Pattern | Severity | Impact on goal |
|------|------|---------|----------|----------------|
| `tools/stack/server.py` | 353-367, 369-382 | Review WR-01: Configure waits with no timeout for in-flight commands while holding `_state`, which parks all commands (including bypass reads) for the duration | Warning (advisory) | In Phase 4 every real-mode command is bounded (reads by core transport timeouts, the three Phase 5 commands refused instantly), so the stall is short and the stress run showed no hang. It does not enable motion and does not undermine the Phase 4 goal. It would undercut STK-05 once a minutes-long Transfer exists, so it must be fixed before Phase 5 (bound the wait or refuse fast while reconfiguring; do the open outside `_state`). |
| `tools/stack/server.py` | 451-467 | Review WR-02: a non-read command parked behind a failing Configure can set READY with no service and overwrite `last_error` | Warning (advisory) | Resulting state is READY with `service None`: reads return NOT_READY, nothing can move. Operator-visible status inconsistency only, on an unusual sequence. Take admission and the service snapshot together in `_in_flight` before Phase 5. |
| `tools/stack/server.py` | various | IN-01..IN-05 | Info | Documentation, cosmetic, or latent hardening (for example `_teardown` reading the core's private `_lock`; bypass exception handler still writes `last_error` by D-13). |

Neither warning touches the "no real-mode path can move the arm" half of the goal (the adapter can only call the seven read/estimate service methods, enforced by the AST invariant), and neither breaks a Phase 4 success criterion, so both are carried as non-blocking advisories.

### Human Verification Required

None. Hardware behavior (a live STACK read) is outside Phase 4's no-motion, loopback-tested scope and belongs to Phase 7 (LIVE-*).

### Gaps Summary

No gaps. All six ROADMAP success criteria and all seven requirement IDs (STK-01..STK-07) hold against the current code after the five review-fix commits. The fixes did not regress STK-02 (Configure, owner lock, holder-naming failure), STK-05 (reads answer while BUSY, status and `last_error` untouched by the bypass) or the no-motion AST invariant. Recommendation for Phase 5 planning: close review WR-01 and WR-02 (bounded or refuse-fast Configure, atomic admission plus service snapshot) before the first real motion command lands.

---

_Verified: 2026-10-29_
_Verifier: Claude (gsd-verifier)_
