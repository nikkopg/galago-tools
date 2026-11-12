---
phase: quick-261112-gh0
plan: 01
subsystem: tools/fast
tags: [fast, grpc, read-only, get_plates]
requires: []
provides: [fast get_plates command]
affects: [interfaces/tools/grpc_interfaces/fast.proto, tools/fast/server.py, tools/tests/fast_test.py]
tech-stack:
  added: []
  patterns: [READ_COMMANDS bypass mirrored from tools/stack/server.py, thread-local last_error suppression (STACK WR-04)]
key-files:
  created: []
  modified:
    - interfaces/tools/grpc_interfaces/fast.proto
    - tools/fast/server.py
    - tools/tests/fast_test.py
decisions:
  - "get_plates goes in a new READ_COMMANDS set; CONTROL_COMMANDS and MOTION_LOCK_COMMANDS unchanged"
  - "Bypassed reads never write last_error (orchestrator amendment, mirrors STACK WR-04); control commands unchanged"
metrics:
  tasks: 2
  completed: 2026-11-12
status: complete
actuals:
  tasks: 2
  commits: 2
plan_head_before: 4ccd3da656c0e981332018b3d33e16148a8bc513
plan_head_after: 7e75882b7c81372292044d7c0ad420797fcbf461
---

# Quick 261112-gh0: read-only get_plates for F.A.S.T. Summary

Read-only `get_plates` command: lists plate definitions registered on the instrument via
`FastService.plate_definitions(refresh=...)`, answers while a Transfer holds the tool BUSY, and never
touches the motion lock, instrument status, or `last_error`.

## Commits

- 1e26433e6a1491a8d91b30641ba8380bd89cf04e feat: proto, adapter bypass, handler, last_error suppression, tracer + invariant tests
- 7e75882b7c81372292044d7c0ad420797fcbf461 test: shape/order/empty, refresh, unreachable, sets, estimates

## Contract

- meta_data: `{"plates": [{"id", "description", "rowCount", "colCount", "workingCapacity"}]}` sorted ascending by id; empty list is SUCCESS.
- Unreachable / HTTP error: ERROR_FROM_TOOL, `instrument unreachable: ConnectError: refused` or `instrument HTTP 503: ...`, no plates key. Other exceptions: DRIVER_ERROR, no plates key. No service: NOT_READY.
- BUSY bypass: `READ_COMMANDS` branch in `FastServer.ExecuteCommand` (tools/fast/server.py).
- last_error suppression: `last_error` property/setter backed by `__dict__["_last_error"]`, dropping writes while thread-local `_read_bypass.active` is set; the READ_COMMANDS branch sets it, clears it in `finally`, and on exception clears it then records `last_error = str(e)` and returns DRIVER_ERROR.

## Deviations from Plan

- [Orchestrator amendment] Added the last_error suppression described above (plan open item 6), with tests: failing and successful get_plates mid-Transfer leave last_error and GetStatus error_message unchanged; exception path records the error; control commands still write last_error.
- Test class placement: TestGetPlatesMapping and TestGetPlatesRealCore sit after their base classes (defined later in the file) rather than next to TestGetPlatesOverGrpc.

## Notes

- One `bin/make proto test` run hit a pre-existing order/port-dependent flake in `TestReconfigure.test_reconfigure_different_endpoint_releases_old_lock_first` (owner lock on a reused ephemeral port held by the same test process). Three reruns of the unittest run and a full `bin/make proto test` rerun were green (600 passed). Not caused by this change; not fixed (out of scope).

## Known Stubs

None.

## Self-Check: PASSED

Both commits exist; `git diff 4ccd3da -- interfaces/` is additions only in fast.proto; base_server.py and tools/stack/ unchanged; no `_pb2` files committed.
