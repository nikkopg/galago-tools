---
phase: 04-stack-tool-registration-reads-estimate
verified: 2026-10-29T08:20:00Z
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
covered_digest: "v3:sha256:a0caae631da3ce85082c3e13f2dcdfc7cce775443c671dbc4e369c2f9c63dca5"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: passed
  previous_score: 6/6
  gaps_closed:
    - "Review WR-01 (iteration 2): Configure drain wait is now bounded and a busy refusal keeps the healthy owner (advisory from previous report closed)"
    - "Review WR-02 (iteration 2): commands during a Configure are refused immediately, handlers use the admitted service, stale READY held at FAILED (advisory from previous report closed)"
  gaps_remaining: []
  regressions: []
advisory:
  - finding: "The setStatus override holds READY at FAILED whenever _configure_failed is set and service is None, and it applies in simulated mode too. After a failed real-mode Configure followed by a switch to simulated, all ten simulated commands still run and return SUCCESS, but GetStatus keeps reporting FAILED (it is no longer flipped to READY by the first command, as it was before 6d46926)."
    category: other
    reason: "Cosmetic status display only: simulated commands are admitted by isReady() == True and never read status. Consider scoping the hold to real mode (or clearing _configure_failed on a successful simulated Configure) when Phase 6 builds the simulated workcell."
    evidence_status: "reproduced by verifier script (scratchpad sim_after_fail.py); no behavioral impact on command results"
  - finding: "A Configure refused as busy (drain timeout) makes base Configure set status FAILED while the healthy owner is kept and reads still answer. A motion command's own finally restores READY, but if the blocker was a long bypassed read nothing restores READY until the next successful Configure."
    category: other
    reason: "Status shown FAILED while the tool is in fact serving reads. Not reachable as a stuck state in Phase 4 (non-read commands are all instant refusals); revisit when Phase 5 adds a long-running Transfer."
    evidence_status: "reproduced by verifier script (scratchpad busy.py): FAILED while owner kept and reads SUCCESS, READY again after the Transfer ended"
---

# Phase 4: STACK Tool Registration, Reads & Estimate Verification Report

**Phase Goal:** An operator can register, Configure and read from a STACK tool in Galago (manager state, robots, devices, profiles, labware presence and a transfer estimate), and no real-mode code path can move the arm.
**Verified:** 2026-10-29
**Status:** passed
**Re-verification:** Yes. The previous report (cade0b5, 261 tests) went stale after `d46fd4a` (bounded Configure drain, busy refusal keeps the owner, `open_service` outside `_state`) and `6d46926` (commands during a Configure refused with "stack: reconfiguring", handlers use the service captured at admission, `StackServer.setStatus` override). Every criterion was re-checked against the current code, with extra scrutiny on STK-05, STK-06, STK-02 and the no-motion invariant.

## Gate Command

`source ~/data/nikko/.venvs/galago-py310/bin/activate && cd /home/formulatrix/data/nikko/galago-tools && bin/make proto test` was run by the verifier: proto regeneration OK, `ruff check .` "All checks passed!", `mypy ... tools` "Success: no issues found in 92 source files", **267 passed in 3.31s**. No STACK motion was performed and nothing contacted 10.150.1.125 / stack-server (loopback ports and fake transports only; the `_StackTestCase` loopback guard forbids anything else; verifier scripts used a fake transport). The STACK core in the venv is stack-automation-layer at `ed8ce478d8881a517eb93ed233707f81aea01238` (`direct_url.json`), identical to the pin in `tools/stack/requirements.txt`. `git status` shows only the untracked `.planning/state.json`; no source was edited.

## Goal Achievement

### Observable Truths (ROADMAP Phase 4 success criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | `stack.proto` registered (tool_base Command `stack = 24`, Config `stack = 43`; controller `stack = 24`), gate green, `python -m tools.stack.server --port=N` starts and reports as `stack` | VERIFIED | `TestRegistration` passes (tool type 24, Command oneof 24, Config oneof 43). `StackServer.toolType = "stack"`. Live run `python -m tools.stack.server --port=50997` logged "stack server started, listening on 50997". `git diff 69e102a..HEAD` shows no change under `interfaces/`. Gate green. |
| 2 | Configure with host/port; core opened only via `open_service(..., owner="galago")`, credentials from `STACK_USER`/`STACK_PASSWORD`, no `lock_dir` field; an mcp-held lock fails Configure naming the holder; no `stack_automation_layer.mcp` import; core pinned by SHA | VERIFIED | Sole call site `server.py:474` `open_service(host, port, owner="galago")`; grep of `tools/stack/` finds no `stack_automation_layer.mcp`, no `lock_dir`, no `10.150`. Config has no credential or lock field (`TestProtoFreeze.test_config_fields`). `requirements.txt` pins `@ed8ce478...` without `[mcp]`. Owner-lock lifecycle re-read in the new code: `_teardown` (`:340`) clears `_owned`/`service` under `_state` then closes outside it and releases the lock in a `finally` (idempotent); `_apply_config` tears down first (close-first) then `open_service` (so a failed open leaves no lock and no service); `_configure` drops the owner on any non-busy failure; on `_ConfigureBusy` nothing was changed and the owner is kept. `open_service` now runs outside `_state` but inside `_exclusive()` and under `_configure_lock`, so no command can touch the owner mid-swap and Configures stay serialised. Same-endpoint reconfigure returns before any drain. Passing tests: `TestStackOwned` (mcp holder fails Configure naming the holder), `TestConfigureFails`, `TestConfigureFailureDropsService`, `TestConfigureCloseFails`, `TestConfigureBusy` (busy refusal keeps the owner, same endpoint does not drain), `TestRequirementsPin`, `TestAdapterInvariant`. Verifier script (busy.py): busy-refused Configure returned "stack: busy, a command is still running; retry Configure when it ends", owner `127.0.0.1:19301` kept, and a later Configure to the new endpoint succeeded; stress script ended with a successful Configure to a fresh port (no leaked lock). |
| 3 | Six reads each SUCCESS with empty message and core `to_dict()` in meta; `readFailed` and any non-read kind are `ERROR_FROM_TOOL` with one-line reason and guid, never SUCCESS; argument errors `INVALID_ARGUMENTS` | VERIFIED | Handlers `server.py:538-566` each make one service call on the admitted service and return `_result_reply`: SUCCESS only for `kind` in `_SUCCESS_KINDS` with `meta=d` unchanged; anything else or a non-dict is `ERROR_FROM_TOOL` via `_error_line` (kind, reason, guid, one bounded hint, 300-char cap). `_check_args` yields `INVALID_ARGUMENTS` first in both modes. `TestReadCommands`, `TestResultMapping`, `TestCheckArgs`, `TestOneToOneSurface` pass. Verifier script: real-mode `GetManagerState` over the fake transport returned SUCCESS, empty message, meta `kind=managerState`. |
| 4 | `GetTransferEstimate` works and nothing moves; simulated mode validates args (incl. `step_key`), sleeps constant `Estimate<Cmd>`, never contacts the core, never writes the ledger | VERIFIED | `GetTransferEstimate` calls only `service.estimate_transfer(...)`. `_dispatchCommand` runs `_check_args` first and, in simulated mode, returns `super()._dispatchCommand` before `_admit`, so simulated commands never read or wait on any real-mode state. Estimate hooks return module constants, no I/O. `TestEstimates`, `TestSimulatedCommands`, `TestSimulatedTransferOverGrpc`, `TestSimulatedBypassRead` pass. |
| 5 | A read issued while another command holds the tool BUSY returns its result (injected slow command) while motion stays serialised; real-mode `Transfer`/`AcknowledgeFailure` refused with a not-yet-available error; a test proves nothing in `tools/stack/` calls core motion methods | VERIFIED | See STK-05 re-check below. `TestBusyReads` (injected slow Transfer over gRPC) and the new `TestReconfiguringAdmission` pass. Verifier script busy.py: with a slow injected Transfer holding status BUSY, `GetManagerState` returned SUCCESS with `kind=managerState` and status stayed BUSY; a second Transfer got NOT_READY (serialised). Independent AST scan of `tools/stack/*.py` for the ten forbidden names (`plan_transfer`, `execute_transfer`, `start_transfer`, `wait`, `wait_transfer`, `cancel_transfer`, `go_to_safe_position`, `wait_safe_position`, `acknowledge_failure`, `validate_transfer`) as Attribute or Name nodes returned `[]`; `TestAdapterInvariant` passes. `Transfer`/`AcknowledgeFailure`/`GetFailureLatch` return `"stack: <Cmd> is not available in this build"` as `ERROR_FROM_TOOL` without touching the service. |
| 6 | `stack.proto` frozen for v2: full surface incl. `Transfer`, `AcknowledgeFailure` and the latch-status read | VERIFIED | Ten-command oneof pinned by `TestProtoFreeze` (passing); no diff to `interfaces/`, `requirements.txt` or `tools/base_server.py` since the previous verification. |

**Score:** 6/6 truths verified (0 present, behavior-unverified). Behavior-dependent truths (BUSY bypass, reconfiguring refusal scope, status and `last_error` invariants, Configure serialisation) each have passing behavioral tests plus the verifier's own runs.

### STK-05 re-check (the riskiest part of the new code)

- **The "reconfiguring" refusal applies only DURING a Configure.** `_admit` (`:432`) refuses only when `self._reconfiguring` is true. `_reconfiguring` is set only inside `_exclusive()` (the drain and the swap) and cleared in its `finally` and on the busy-timeout branch. An ordinary BUSY (a command in flight) does not set it. Verifier run: with a slow Transfer holding BUSY and no Configure in progress, a read returned SUCCESS (not "reconfiguring"). Only when a Configure to a different endpoint was concurrently draining did the read get `7 / "stack: reconfiguring"`; after the drain timed out (busy refusal) reads answered SUCCESS again. A same-endpoint Configure never sets the flag.
- **The bypass path never calls `setStatus`/`isReady`/`parseCommand`.** The `StackServer.ExecuteCommand` bypass (`:480-520`) calls only `_dispatchCommand`; grep of `tools/stack/server.py` shows `setStatus` appears only at its definition (`:394`), the base `_dispatchCommand` (`tools/base_server.py:122-190`) contains no `setStatus`, `isReady` or `parseCommand` call, and the base `setStatus` callers are `Configure` (lines 100/109/114) and base `ExecuteCommand` (240/254) only, which the bypass does not enter. `base_server.py` is unmodified. The test `test_reads_never_call_set_status_but_a_transfer_brackets_busy_ready` passes. Verifier run: status was BUSY before and after the bypassed read.
- **Serialisation of motion commands** is unchanged (base `isReady`/BUSY): a second Transfer during the first got NOT_READY.
- **Counter integrity under the new admission:** `_admit` increments `_readers` under `_state` and returns the service snapshot atomically; `_leave` decrements in the `finally` of `_dispatchCommand` and notifies at zero; `_exclusive` waits `wait_for(not _readers, timeout)` (lock released while waiting). Handlers use `_require_service()` which returns the admitted service from a thread-local, never a fresh `self.service`.

### STK-06 re-check (simulated mode)

`_dispatchCommand` returns `super()._dispatchCommand(command)` for `self.simulated` before `_admit`, the thread-local and any service access, so the admission logic cannot affect it. The `setStatus` override only rewrites READY to FAILED when `_configure_failed and service is None`. Verifier script sim_after_fail.py: a failed real Configure (blank host), then a simulated Configure, then all ten commands over the base `ExecuteCommand` (estimates patched to 0 s): every command returned SUCCESS with empty message and `service` stayed `None` (core never contacted). Side effect recorded as an advisory: status reads FAILED throughout (cosmetic; it was FAILED already after the failed Configure, the first command used to flip it to READY). On a fresh server (`_configure_failed` False) simulated behavior is unchanged, and `TestSimulatedCommands`, `TestSimulatedBypassRead`, `TestSimulatedTransferOverGrpc`, `TestNotConfigured.test_simulated_to_real_switch_leaves_reads_not_configured` pass.

### Concurrency Stress Re-run (new code)

Verifier script stress.py (scratchpad, not committed): 5 `GetManagerState` threads, 2 `GetTransferEstimate` threads, 2 `Transfer` threads and 3 Configure threads (75% valid configures cycling three loopback ports through a fake transport, 25% blank-host failures) calling `StackServer.Configure`/`ExecuteCommand` directly for 8 seconds. Expected codes: SUCCESS, NOT_READY, and ERROR_FROM_TOOL with "stack: reconfiguring" or "stack: Transfer is not available in this build".

- 0 threads left alive (no deadlock).
- Final state: `service is None` iff `_owned is None`, `_readers == 0`, `_reconfiguring == False`; a final Configure to a new port succeeded and a read after it succeeded (no leaked owner lock).
- Observed outcomes: reads SUCCESS 100, "reconfiguring" refusals 312 (reads) + 126 (estimates) + 72 (transfers), "not configured" NOT_READY, Transfer refusals, 25 Configures succeeded and 7 failed with the one-line "Config.host is required". The only entries outside the expected set were 41 `GetTransferEstimate` replies `stack: needsInput; missing: robot, labwareProfile, source, destination`, which are the correct `ERROR_FROM_TOOL` mapping for the verifier's deliberately empty estimate request (a script input artifact, not a defect). No unexpected response code, no exception.
- Configure throughput was low (32 attempts) because Configure only gets in when `_readers` momentarily reaches zero under 9 hammering threads; that is the bounded-drain design, not a hang.

### Deferred Items

None.

### Advisory (New Scope, Unevidenced)

| # | Finding | Category | Why Advisory |
|---|---------|----------|--------------|
| 1 | `setStatus` hold at FAILED also applies in simulated mode after a failed real Configure (status display only) | other | Reproduced, but commands unaffected; cosmetic |
| 2 | A busy-refused Configure leaves GetStatus FAILED while the owner is kept and reads still work | other | Reproduced, but not a stuck state reachable in Phase 4; revisit with Phase 5 Transfer |

Both earlier advisories (unbounded drain, stale READY after a failed Configure) are closed by `d46fd4a`/`6d46926`.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `interfaces/tools/grpc_interfaces/stack.proto` | Frozen 10-command surface and Config | VERIFIED | Unchanged, compiled by `bin/make proto`. |
| `interfaces/tools/grpc_interfaces/tool_base.proto` | Command 24 / Config 43 | VERIFIED | Unchanged. |
| `interfaces/controller.proto` | `stack = 24` ToolType | VERIFIED | Unchanged. |
| `tools/stack/server.py` | StackServer, mapping, reads, refusals, bypass, Configure hardening | VERIFIED | 632 lines, no stubs or debt markers, wired via `serve(StackServer(), ...)`. |
| `tools/stack/requirements.txt` | SHA-pinned core, no `[mcp]` | VERIFIED | Single pinned line matching the installed commit. |
| `tools/stack/__init__.py`, `pyproject.toml` | Package and mypy override | VERIFIED | Present; mypy clean. |
| `tools/tests/stack_test.py` | Registration, freeze, ownership, mapping, simulation, bypass, concurrency tests | VERIFIED | 267-test gate passes (6 new: `TestConfigureBusy`, `TestReconfiguringAdmission`). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| tool_base.proto | stack.proto | import + `stack = 24` / `= 43` | WIRED | `TestRegistration`. |
| `_apply_config` | `open_service` | `open_service(host, port, owner="galago")` inside `_exclusive()` | WIRED | `server.py:474`, only call site. |
| `_configure` | `_exclusive` / `_teardown` | failure drop with bounded drain; busy re-raised without teardown | WIRED | `:360-380`. |
| `_dispatchCommand` | `_admit` / `_leave` / `_admitted` | real-mode bracket, args and simulated first | WIRED | `:522-545`. |
| read handlers | `_require_service` -> `_result_reply` | admitted service, one call each | WIRED | `:538-566`. |
| `ExecuteCommand` | `_dispatchCommand` | `field_name in READ_COMMANDS`, no status calls | WIRED | `:480-520`. |
| `setStatus` override | base `Configure` / `ExecuteCommand` finally | READY held at FAILED after failed Configure | WIRED | `:394`; not on the bypass path. |
| `last_error` setter | `_read_bypass` thread-local | drops bypass-thread writes | WIRED | unchanged. |
| TestAdapterInvariant | `tools/stack/*.py` | `ast.parse` of every module | WIRED | passes; verifier scan agrees. |

### Data-Flow Trace (Level 4)

| Artifact | Data | Source | Real data | Status |
|----------|------|--------|-----------|--------|
| read handlers | reply meta | `service.<method>().to_dict()` passed through unchanged | Yes (core result; live hardware is Phase 7) | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full gate | `bin/make proto test` | 267 passed, ruff and mypy clean | PASS |
| Server starts as stack tool | `python -m tools.stack.server --port=50997` | "stack server started, listening on 50997" | PASS |
| Reads answer while BUSY, "reconfiguring" only during a Configure, busy refusal keeps owner | scratchpad `busy.py` | as described under STK-05 | PASS |
| Simulated mode: ten commands, no core, after a failed real Configure | scratchpad `sim_after_fail.py` | 10/10 SUCCESS, `service None` | PASS |
| Concurrency stress, 8 s, 11 threads | scratchpad `stress.py` | no deadlock, consistent state, no lock leak, no unexpected code | PASS |
| No motion call in adapter | independent AST scan, ten forbidden names | `[]` | PASS |
| No mcp import, hardware literal or `lock_dir`; no debt markers | grep `tools/stack/` | no matches | PASS |
| Core pin | installed `direct_url.json` vs `requirements.txt` | both `ed8ce478d8881a517eb93ed233707f81aea01238` | PASS |

### Probe Execution

SKIPPED: the phase declares no `probe-*.sh` scripts.

### Requirements Coverage

All seven IDs appear in PLAN frontmatter (04-01: STK-01, 02, 03, 07; 04-02: STK-02, 05; 04-03: STK-03, 04, 07; 04-04: STK-04, 05, 06; 04-05: STK-05) and in REQUIREMENTS.md (all marked Complete, mapped to Phase 4). None is orphaned.

| Requirement | Source Plan | Status | Evidence |
|-------------|-------------|--------|----------|
| STK-01 | 04-01 | SATISFIED | SC1, SC6. |
| STK-02 | 04-01, 04-02 | SATISFIED | SC2, re-checked after `d46fd4a`/`6d46926` (owner-lock lifecycle, busy keeps owner). |
| STK-03 | 04-01, 04-03 | SATISFIED | SC3. |
| STK-04 | 04-03, 04-04 | SATISFIED | SC4. |
| STK-05 | 04-02, 04-04, 04-05 | SATISFIED | SC5, "reconfiguring" scoped to Configure only; bypass never touches status. |
| STK-06 | 04-04 | SATISFIED | SC4; simulated path independent of admission, including after a failed real Configure. |
| STK-07 | 04-01, 04-03 | SATISFIED | SC3. |

### Anti-Patterns Found

No `TBD`, `FIXME`, `XXX`, `TODO` or `HACK` in `tools/stack/`; no stub returns (debt-marker gate clear). The two iteration-2 review warnings (WR-01, WR-02) are resolved in code and tests. Remaining items are the two advisories above and the earlier Info findings (IN-01..IN-05), none touching the goal.

### Human Verification Required

None. Hardware behavior (a live STACK read) is outside Phase 4's no-motion, loopback-tested scope and belongs to Phase 7 (LIVE-*).

### Gaps Summary

No gaps. All six ROADMAP success criteria and all seven requirement IDs (STK-01..STK-07) hold against the current code after `d46fd4a` and `6d46926`. Reads still answer while a motion command holds BUSY; the new "reconfiguring" refusal fires only during a Configure; the bypass path never reaches `setStatus`; simulated mode still runs all ten commands with no core even after a failed real Configure; the owner-lock lifecycle is intact and the AST no-motion invariant is clean. Two cosmetic status-display advisories are carried for Phase 5/6.

---

_Verified: 2026-10-29_
_Verifier: Claude (gsd-verifier)_
