---
phase: 04-stack-tool-registration-reads-estimate
plan: 05
subsystem: stack-tool
tags: [busy-bypass, execute-command-override, read-commands, test-first, no-motion]
status: complete
requires: ["04-04"]
provides:
  - "READ_COMMANDS: frozenset of the eight read oneof names that bypass the BUSY gate"
  - "StackServer.ExecuteCommand override: reads dispatch directly, every other request falls through to base_server"
  - "TestBusyReads (with _start_blocked_command), TestReadCommandSet, TestNotConfigured, TestReadBypassEdges, TestSimulatedBypassRead"
affects: []
tech-stack:
  added: []
  patterns: ["fast-style ExecuteCommand override gated on a pinned command frozenset", "injected slow handler on the server instance to hold BUSY over real gRPC"]
key-files:
  created: []
  modified:
    - tools/stack/server.py
    - tools/tests/stack_test.py
key-decisions:
  - "get_transfer_estimate and get_failure_latch are in READ_COMMANDS (D-15): they move nothing; transfer and acknowledge_failure are never in the set, pinned by TestReadCommandSet"
  - "A bypassed read goes through _dispatchCommand, so the argument check, simulated mode and the real-mode not-configured NOT_READY still apply; it never calls isReady, parseCommand or setStatus, so a BUSY tool stays BUSY and a READY tool stays READY"
  - "tools/base_server.py is not edited; non-read, non-stack and empty requests return super().ExecuteCommand unchanged"
requirements-completed: [STK-05]
duration: 15 min
completed: 2026-10-29
plan_head_before: f0f8da19508659b184b76eba9a04a606a598cdbc
plan_head_after: e5c3c3749821bb862abb143c3b100263230ed385
commits: 3
actuals:
  tokens: 3800
  tasks: 2
  commits: 3
coverage:
  - deliverable: "While a non-read command holds the tool BUSY, each of the eight reads returns its own result (get_failure_latch its not-available ERROR_FROM_TOOL), health stays BUSY, a second Transfer gets NOT_READY, and health returns to READY after release"
    verification:
      - {kind: test, ref: "tools/tests/stack_test.py#TestBusyReads", status: pass}
    human_judgment: false
  - deliverable: "READ_COMMANDS is exactly the eight read names; transfer and acknowledge_failure are excluded"
    verification:
      - {kind: test, ref: "tools/tests/stack_test.py#TestReadCommandSet", status: pass}
    human_judgment: false
  - deliverable: "Bypass edges: not-configured and simulated-to-real switch return NOT_READY without reaching a None service; exceptions become DRIVER_ERROR with last_error; reads never call setStatus; empty and other-tool requests fall through; simulated bypass read sleeps EST_READ_S core-free"
    verification:
      - {kind: test, ref: "tools/tests/stack_test.py#TestNotConfigured", status: pass}
      - {kind: test, ref: "tools/tests/stack_test.py#TestReadBypassEdges", status: pass}
      - {kind: test, ref: "tools/tests/stack_test.py#TestSimulatedBypassRead", status: pass}
    human_judgment: false
---

# Phase 4 Plan 5: BUSY-bypass reads via ExecuteCommand override Summary

The STACK tool now answers all eight read commands while a motion command holds it BUSY, through a fast-style `StackServer.ExecuteCommand` override gated on a pinned `READ_COMMANDS` frozenset, while a second motion command still gets NOT_READY and `tools/base_server.py` stays untouched.

## Accomplishments

- `READ_COMMANDS` holds exactly get_manager_state, get_robot_states, list_devices, list_labware_profiles, list_transfer_profiles, get_labware_presence, get_transfer_estimate and get_failure_latch.
- `StackServer.ExecuteCommand`: for a stack request whose inner command is in `READ_COMMANDS` it calls `_dispatchCommand` directly inside `try`, mapping any exception to `DRIVER_ERROR` (one-line message, `last_error` set). It never calls `isReady`, `parseCommand` or `setStatus`. All other requests go to `super().ExecuteCommand`.
- Test-first (D-16): the BusyReads test was committed failing before the override. The injected slow command is a `Transfer` handler patched on the server instance (an instance attribute wins because base `_dispatchCommand` resolves the handler with `getattr(self, name)`), sent over real in-process gRPC with `step_key="busy-1"` so the BUSY/READY bracket is really exercised.
- Edge coverage: a fresh real-mode server and a simulated-to-real switched server both return NOT_READY "stack: not configured" for reads and never call `open_service`; `setStatus` is never called by any of the eight reads while a real Transfer records exactly `[BUSY, READY]`.

## RED run (quoted)

Before the override (`pytest -k BusyReads`), a read sent while the injected Transfer held the tool BUSY failed with the response code for NOT_READY:

```
>               self.assertEqual(reply.response, SUCCESS, reply.error_message)
E               AssertionError: 6 != 1 :
tools/tests/stack_test.py:1697: AssertionError
ERROR    root:base_server.py:231 Failed o execute commad for Tool undefined, Error=None
FAILED tools/tests/stack_test.py::TestBusyReads::test_reads_answer_while_busy_and_a_second_transfer_is_refused
1 failed, 92 deselected in 0.15s
```

(`6` is `NOT_READY`, `1` is `SUCCESS`.)

## Task Commits

1. Task 1 RED: `fe97a7d` - `test(04-05)` failing BusyReads test
2. Task 1 GREEN: `9efb8fa` - `feat(04-05)` READ_COMMANDS and ExecuteCommand override, plus TestReadCommandSet
3. Task 2: `e5c3c37` - `test(04-05)` bypass-edge tests (all passed on the Task 1 override; no code change needed)

The git-log ordering check passes (earliest test/feat 04-05 commit is `test`). The tracer `<verify>` is automated-only and passed (14 passed with the AST invariant) before Task 2.

## Verification

`bin/make proto test` in `~/data/nikko/.venvs/galago-py310`: ruff and mypy clean, 250 passed (239 before this plan). `git diff --quiet main -- tools/base_server.py` exits 0. The 04-02 `TestAdapterInvariant` stays green (the new `import grpc` and `ToolCommand` import are allowed).

## Deviations from Plan

None - plan executed exactly as written. Task 2's tests passed against the Task 1 override with no further source change. The WRONG_TOOL case uses a `fast_pb2` pause command; `fast_pb2` was added to the test imports.

## Known Stubs

None.

## Threat Flags

None. No new network endpoint, auth path or file access. T-04-19 (set pinned by TestReadCommandSet; non-reads still NOT_READY while BUSY), T-04-20 (setStatus never called on bypass; not-configured guard) and T-04-21 (exception becomes DRIVER_ERROR, status unchanged) are covered by tests.

## Notes

- Flagged assumption (STK-05 `unclassified` edge): treated the BUSY window boundaries as the edges (read while BUSY, read while READY must not set BUSY, BUSY to READY after release); covered in TestBusyReads and TestReadBypassEdges. Left unverified by a probe-authored criterion.
- `_require_service`'s RuntimeError guard remains unreachable through dispatch (04-04 note); kept as defence in depth.

## Next

Phase 4 plans complete; ready for phase verification.

## Self-Check: PASSED
