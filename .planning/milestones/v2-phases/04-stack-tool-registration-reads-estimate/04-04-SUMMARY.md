---
phase: 04-stack-tool-registration-reads-estimate
plan: 04
subsystem: stack-tool
tags: [simulated-mode, argument-check, real-mode-refusal, estimate-hooks, no-motion]
status: complete
requires: ["04-03"]
provides:
  - "_check_args: Transfer step_key / timeout_s and AcknowledgeFailure guid / exact 'yes'|'no' arm_inspected, identical in both modes"
  - "StackServer._dispatchCommand override: argument check, then not-configured NOT_READY (refusals exempt), then base dispatch"
  - "Transfer, AcknowledgeFailure, GetFailureLatch real-mode handlers: ERROR_FROM_TOOL 'stack: <Command> is not available in this build', no service access"
  - "Ten constant Estimate<Cmd> hooks (EST_TRANSFER_S 35, EST_TRANSFER_ESTIMATE_S 3, EST_READ_S 2, EST_ACK_S 2)"
  - "_SimulatedGrpcTestCase, TestSimulatedTransferOverGrpc, TestCheckArgs, TestRealModeRefusals, TestRealModeRefusalsOrdering, TestEstimates, TestSimulatedCommands"
affects: [04-05]
tech-stack:
  added: []
  patterns: ["adapter-owned argument check before dispatch in both modes", "pure constant estimate hooks with no attribute access", "faked tools.base_server.time to record simulated sleeps"]
key-files:
  created: []
  modified:
    - tools/stack/server.py
    - tools/tests/stack_test.py
key-decisions:
  - "The three Phase 5 commands are refused before the not-configured check (research Open Question 1): they need no service and their text is operator-visible, so a missing service must not hide it"
  - "arm_inspected is matched byte-for-byte against 'yes'/'no' with no strip, lower or default; fast's _decision helper was deliberately not copied"
  - "Refusal and argument-failure replies use ERROR_FROM_TOOL only for the refusal; INVALID_ARGUMENTS / NOT_READY stay for argument and not-configured cases"
requirements-completed: [STK-04, STK-05, STK-06]
duration: 20 min
completed: 2026-10-29
plan_head_before: d94e9460fe6c67e9aba101a4f01218cefe24b7b6
plan_head_after: 4599009f670aca493b3ed76c52b62fca6f3689a1
commits: 3
actuals:
  tokens: 5300
  tasks: 3
  commits: 3
coverage:
  - deliverable: "Simulated mode rehearses all ten commands with valid adapter arguments: SUCCESS after sleeping the constant estimate, never calling open_service, leaving service None, creating no lock file and no ledger path"
    verification:
      - {kind: test, ref: "tools/tests/stack_test.py#TestSimulatedTransferOverGrpc", status: pass}
      - {kind: test, ref: "tools/tests/stack_test.py#TestSimulatedCommands", status: pass}
    human_judgment: false
  - deliverable: "Adapter-owned arguments checked identically in both modes (step_key, timeout_s, guid, exact yes/no arm_inspected); instrument fields never checked"
    verification:
      - {kind: test, ref: "tools/tests/stack_test.py#TestCheckArgs", status: pass}
    human_judgment: false
  - deliverable: "Real mode refuses Transfer, AcknowledgeFailure and GetFailureLatch with a one-line not-available error and no service call, ahead of not-configured; other commands are NOT_READY without a service"
    verification:
      - {kind: test, ref: "tools/tests/stack_test.py#TestRealModeRefusals", status: pass}
      - {kind: test, ref: "tools/tests/stack_test.py#TestRealModeRefusalsOrdering", status: pass}
      - {kind: test, ref: "tools/tests/stack_test.py#TestAdapterInvariant", status: pass}
    human_judgment: false
  - deliverable: "Ten Estimate hooks return local integer constants, never raise, including through the EstimateDuration RPC"
    verification:
      - {kind: test, ref: "tools/tests/stack_test.py#TestEstimates", status: pass}
    human_judgment: false
---

# Phase 4 Plan 4: Simulated mode, argument checks, real-mode refusals and estimates Summary

A simulated STACK tool now rehearses the whole frozen ten-command surface without touching the core: each command with valid adapter arguments sleeps its constant estimate and returns SUCCESS, while real mode refuses Transfer, AcknowledgeFailure and GetFailureLatch with a clear one-line error and no service call.

## Accomplishments

- `_check_args` runs first in `StackServer._dispatchCommand` in both modes. `Transfer.step_key` must be set and non-blank; `Transfer.timeout_s`, when set, must be finite and >= 0; `AcknowledgeFailure.guid` must be non-blank; `AcknowledgeFailure.arm_inspected` must be exactly `"yes"` or `"no"` (rejects "Yes", " yes", "yes ", "y", "true", empty and unset). Failures are INVALID_ARGUMENTS with one bounded line. Instrument fields are never checked.
- Real mode after the argument check: the three Phase 5 commands return ERROR_FROM_TOOL `stack: <Command> is not available in this build` without touching the service (`mock_calls == []`); every other command returns NOT_READY `stack: not configured` when no service exists. The refusals precede not-configured.
- Simulated mode (base `_dispatchCommand` simulated branch, `tools/base_server.py` untouched): each of the ten commands sleeps `Estimate<Cmd>` and succeeds; `open_service` never called, `service` stays None, no `*.lock` file, configured ledger path never created.
- Ten Estimate hooks are one-line constant returns (Transfer 35, GetTransferEstimate 3, AcknowledgeFailure 2, the six reads and GetFailureLatch 2). The hook set is pinned to the proto oneof names, and the EstimateDuration RPC returns each constant even for a NaN-timeout Transfer.
- The 04-02 AST invariant stays green: nothing under `tools/stack/` calls a forbidden service method.

## Task Commits

1. Task 1 (tracer): `476607b` - simulated Transfer end to end (argument check, constant sleep, no core)
2. Task 2: `3442ff4` - real-mode refusals, ack/latch handlers, exact argument matrix
3. Task 3: `4599009` - constant Estimate hooks and simulated runs of all ten commands

The tracer `<verify>` is automated-only and passed (14 passed with the AST invariant) before expansion.

## Verification

`bin/make proto test` in `~/data/nikko/.venvs/galago-py310`: ruff and mypy clean, 239 passed (213 before this plan). `git diff main -- tools/base_server.py` is empty.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] mypy rejected `self.subTest("no-service", name)`**
- **Found during:** Task 3 gate run
- **Issue:** `unittest.TestCase.subTest` takes `(msg, **params)`; two positional args fail mypy `call-arg`.
- **Fix:** Folded into one message string `f"no-service {name}"`.
- **Files modified:** tools/tests/stack_test.py
- **Commit:** 4599009 (fixed before the commit)

**Total deviations:** 1 auto-fixed (trivial test-typing). **Impact:** none.

## Known Stubs

None. The three refusal handlers are intentional, spec-mandated Phase 5 placeholders (real mode), not unwired UI data.

## Threat Flags

None. No new network endpoint, auth path or file access; simulated mode creates no lock or ledger file (T-04-17 asserted).

## Notes

- `_require_service` keeps its guard but is now unreachable through dispatch for a missing service, since `_dispatchCommand` returns NOT_READY first.
- The STK-06 `unclassified` edge assumption (timeout_s 0.0 accepted; -0.5/NaN/inf rejected; exact yes/no; whitespace-only step_key/guid blank) is covered in `TestCheckArgs`.

## Next

Ready for 04-05.

## Self-Check: PASSED

- tools/stack/server.py and tools/tests/stack_test.py exist and contain the plan's symbols (UNAVAILABLE_COMMANDS, _check_args, ten Estimate hooks, TestSimulatedCommands).
- Commits 476607b, 3442ff4 and 4599009 are ancestors of HEAD.
