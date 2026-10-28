---
phase: 04-stack-tool-registration-reads-estimate
plan: 01
subsystem: stack-tool
tags: [grpc, proto, stack, tracer, registration]
status: complete
requires: []
provides:
  - "stack.proto frozen v2 surface (10 commands + Config), registered as Command 24 / Config 43 / ToolType 24"
  - "tools/stack StackServer with Configure (open_service owner galago) and GetManagerState"
  - "_result_reply kind-allowlist mapping (STK-07 first slice)"
  - "tools/tests/stack_test.py hermetic scaffold"
affects: [04-02, 04-03, 04-04, 04-05]
tech-stack:
  added: ["stack-automation-layer @ ed8ce478 (core only, no [mcp] extra)"]
  patterns: ["fast-tool adapter shape", "SUCCESS only for allowlisted result kinds", "loopback-guarded hermetic tests"]
key-files:
  created:
    - interfaces/tools/grpc_interfaces/stack.proto
    - tools/stack/__init__.py
    - tools/stack/requirements.txt
    - tools/stack/server.py
    - tools/tests/stack_test.py
  modified:
    - interfaces/tools/grpc_interfaces/tool_base.proto
    - interfaces/controller.proto
    - pyproject.toml
key-decisions:
  - "stack.proto frozen exactly as D-01..D-05 (user reply: Freeze)"
  - "_configure is the thinnest D-07 path; endpoint reuse, validation and close-first lifecycle are left to Plan 02"
requirements-completed: [STK-01, STK-02, STK-03, STK-07]
duration: 2 min
completed: 2026-10-28
plan_head_before: e9fcb9ae386711fbda4768a5944f922743f87fef
plan_head_after: bcbbf8e245877dc77dbdaaa1e5d18a768dffa8f8
commits: 1
actuals:
  tokens: 5100
  tasks: 3
  commits: 1
coverage:
  - deliverable: "stack tool registered (ToolType 24, Command 24, Config 43) and frozen proto pinned"
    verification:
      - {kind: test, ref: "tools/tests/stack_test.py#TestRegistration", status: pass}
      - {kind: test, ref: "tools/tests/stack_test.py#TestProtoFreeze", status: pass}
    human_judgment: false
  - deliverable: "Configure then GetManagerState over gRPC returns SUCCESS with core to_dict() meta; owner lock names galago and this pid"
    verification:
      - {kind: test, ref: "tools/tests/stack_test.py#TestTracerManagerStateOverGrpc", status: pass}
    human_judgment: false
  - deliverable: "Non-allowlisted result kind never yields SUCCESS (readFailed -> ERROR_FROM_TOOL)"
    verification:
      - {kind: test, ref: "tools/tests/stack_test.py#TestTracerManagerStateOverGrpc::test_read_failed_is_never_success", status: pass}
    human_judgment: false
---

# Phase 4 Plan 1: Stack tool registration and manager-state tracer Summary

Registered the `stack` tool type (ToolType 24, Command 24, Config 43), froze the v2 `stack.proto` surface, and proved one operator path end to end: gRPC Configure (real mode, real owner lock, core identity probe on a fake transport) then `GetManagerState` returning SUCCESS with the core's `to_dict()` in meta, with SUCCESS gated by an explicit result-kind allowlist.

## Resolved checkpoints

| Task | Name | Outcome | Commit |
| ---- | ---- | ------- | ------ |
| 1 | Install pinned STACK core (checkpoint:human-action, blocking-human) | Resolved. User reply (verbatim): "Install it for me". Orchestrator ran the git+file install at SHA ed8ce478; verify printed `core ok`; core repo `git status --porcelain` identical before and after (`cmp`). | none (no tracked files) |
| 2 | Confirm frozen stack.proto (checkpoint:decision, blocking-human) | Resolved. User reply (verbatim): "Freeze". Field list frozen exactly as D-01..D-05; no amendments. | none (no tracked files) |
| 3 | Tracer: register stack tool, read manager state over gRPC | Complete | bcbbf8e |

## Accomplishments

- `stack.proto` with the ten-command oneof, nested messages with proto3 presence on every field, and a four-field Config with no lock_dir or credential field; registered in tool_base.proto and controller.proto.
- `tools/stack/server.py`: `StackServer` (`toolType = "stack"`), `_configure` via `open_service(host, port, owner="galago")`, `GetManagerState`, `_result_reply` with `_SUCCESS_KINDS`, `_error_line`/`_find_guid` one-line error mapping; `python -m tools.stack.server --port=N` logs "stack server started, listening on N".
- `tools/tests/stack_test.py` (13 tests): skip guard, hermetic base (temp lock dir, fake creds, no proxies, loopback-only connect guard), registration, proto-freeze, and tracer tests (owner lock contention shows holder galago and this pid; readFailed returns ERROR_FROM_TOOL with a one-line "stack: readFailed" message).
- Pinned core in `tools/stack/requirements.txt` and mypy override in `pyproject.toml`.

## Verification

- `bin/make proto test`: 160 passed (147 pre-existing + 13 new), ruff and mypy clean.
- `python -m tools.stack.server --port=N`: startup line logged.
- All task acceptance greps pass; generated `stack_pb2*` files are gitignored and untracked.
- Tracer re-verified end to end (full gate above) before finishing; no expansion tasks in this plan.

## Deviations from Plan

None - plan executed exactly as written.

## Authentication Gates

None (the Task 1 install was a package-legitimacy checkpoint, not an auth gate).

## Known Stubs

None.

## Flagged assumption (STK-01 edge probe, unresolved by the probe)

Treated the proto3 presence boundary as the relevant edge; pinned by `TestProtoFreeze` (`has_presence` on every Command field, Config scalars without presence, `HasField` True for `""`). Left for the verifier.

## Next

Ready for 04-02.

## Self-Check: PASSED

- FOUND: stack.proto, tools/stack/__init__.py, requirements.txt, server.py, tools/tests/stack_test.py
- FOUND: commit bcbbf8e (ancestor of HEAD)
