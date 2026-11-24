---
phase: 04-stack-tool-registration-reads-estimate
plan: 03
subsystem: stack-tool
tags: [reads, estimate, result-mapping, error-line, no-motion]
status: complete
requires: ["04-02"]
provides:
  - "StackServer.GetTransferEstimate -> estimate_transfer(TransferRequest) with unset/blank fields as None"
  - "Five reads 1:1 onto the core: robot_states, devices(refresh=), labware_profiles(refresh=), transfer_profiles(refresh=), labware_presence(robot|None)"
  - "COMMAND_TO_SERVICE_METHOD (7 entries) pinned against the proto oneof"
  - "_hint: one bounded structured hint (missing fields, first finding name, readFailed error name + HTTP status) on every ERROR_FROM_TOOL line"
  - "_RealModeGrpcTestCase, TestTransferEstimate, TestReadCommands, TestOneToOneSurface, TestResultMapping"
affects: [04-04, 04-05]
tech-stack:
  added: []
  patterns: ["single-call handlers returning _result_reply(<one service call>)", "real core result classes as test fixtures", "exact case-sensitive kind allowlist"]
key-files:
  created: []
  modified:
    - tools/stack/server.py
    - tools/tests/stack_test.py
key-decisions:
  - "Blank/whitespace instrument fields (proto3 presence is True for an explicit empty string) reach the core as None; non-blank values pass byte-for-byte, the adapter applies no instrument rule"
  - "Operator error line is kind, then reason, then guid, then at most one bounded structured hint; core explanation/message/detail text is never read (galago-core drops meta on non-SUCCESS replies, so the line is all the operator sees)"
requirements-completed: [STK-03, STK-04, STK-07]
duration: 15 min
completed: 2026-10-29
plan_head_before: 1a820d541125893461b8ad6724f97781f121e214
plan_head_after: a7bdb64c8ebff939053f9080ca0f2441993d98f3
commits: 5
actuals:
  tokens: 8250
  tasks: 3
  commits: 5
coverage:
  - deliverable: "GetTransferEstimate calls estimate_transfer exactly once with a None-normalised TransferRequest; Estimated is SUCCESS with empty message, needsInput/rejected/readFailed are ERROR_FROM_TOOL"
    verification:
      - {kind: test, ref: "tools/tests/stack_test.py#TestTransferEstimate", status: pass}
    human_judgment: false
  - deliverable: "Six reads answer 1:1 with untouched to_dict() meta, preserved order and duplicates, hasLabware False kept, blank robot to None, refresh default False"
    verification:
      - {kind: test, ref: "tools/tests/stack_test.py#TestReadCommands", status: pass}
      - {kind: test, ref: "tools/tests/stack_test.py#TestOneToOneSurface", status: pass}
    human_judgment: false
  - deliverable: "Exhaustive result mapping: nine allowlisted kinds SUCCESS with empty message; every other core kind, unknown/case-variant kinds and non-result objects ERROR_FROM_TOOL as one bounded line with kind, reason, guid and hint, never agent-worded text"
    verification:
      - {kind: test, ref: "tools/tests/stack_test.py#TestResultMapping", status: pass}
    human_judgment: false
---

# Phase 4 Plan 3: Reads, transfer estimate and exhaustive result mapping Summary

The operator can now read robot states, devices, labware profiles, transfer profiles and labware presence, and ask for a transfer estimate, all 1:1 onto the STACK core with the core's `to_dict()` as untouched meta. Every result is mapped by one explicit table: nine allowlisted kinds are SUCCESS with an empty message, everything else is a single bounded ERROR_FROM_TOOL line (`stack: <kind> (<reason>), guid <guid>; <hint>`).

## Accomplishments

- `GetTransferEstimate` builds `TransferRequest`/`Location` through `_text_or_none` (unset, "" and whitespace become None; non-blank passes unchanged), calls `estimate_transfer` once and nothing else (`mock_calls` length 1 asserted), and an all-blank request is judged by the core's `missing_fields`, not the adapter.
- `GetRobotStates`, `ListDevices`, `ListLabwareProfiles`, `ListTransferProfiles`, `GetLabwarePresence`: single `_result_reply(<one call>)` handlers. `refresh` is keyword-only and defaults to False; a blank robot reaches `labware_presence(None)` so the core does zero I/O. No sorting, filtering, merging or caching (duplicate and order tests; `hasLabware: false` is kept; a presence `ReadFailed` carries no `hasLabware` key).
- `COMMAND_TO_SERVICE_METHOD` (7 keys) is proven equal to the proto oneof names plus the three Phase 5 commands; every key is a `StackServer` method, every value a `StackService` attribute outside the forbidden set, and each command over a fresh `MagicMock(spec=StackService)` records exactly one mapped call.
- `_hint` adds at most one structured hint (needsInput missing fields, first rejected finding name, readFailed error name with `(HTTP n)` for an int status, bool excluded). Newlines collapse and the line is capped at 300 characters. A sentinel placed in every explanation/message/detail field never appears in any message.
- `TestResultMapping` covers all nine allowlisted kinds and fourteen non-success core results from real classes, case variants (`ManagerState`, `managerstate`, ` managerState`), non-str kinds, list/`object()`/`MagicMock()` results, and the empty success message surviving gRPC.

## Task Commits

| Task | Name | Commit |
| ---- | ---- | ------ |
| 1 | Tracer: transfer estimate end to end | e1ec6a2 |
| 2 | Five reads and surface map (RED) | 4578887 |
| 2 | Five reads and surface map (GREEN) | a216e0c |
| 3 | Result mapping and error-line hints (RED) | 1d553dc |
| 3 | Result mapping and error-line hints (GREEN) | a7bdb64 |

## Verification

- `bin/make proto test`: 213 passed (186 baseline + 27 new), ruff and mypy clean.
- Tracer re-verified end to end with the full gate (192 passed) before expansion.
- All acceptance greps pass. The 04-02 `TestAdapterInvariant` stays green with the new handlers. Hermetic only: mocks, in-process loopback gRPC, temp lock dirs; no STACK hardware or stack-server contacted; `tools/base_server.py` untouched.

## Deviations from Plan

None - plan executed exactly as written. (Tasks 2 and 3 followed TDD with separate RED test commits.)

## Authentication Gates

None.

## Known Stubs

None.

## Flagged assumption (STK-04 edge probe, unresolved by the probe)

Treated the all-blank request as the relevant edge: every instrument field reaches `estimate_transfer` as None and the core's `missing_fields` produces `needsInput`, mapped to ERROR_FROM_TOOL (`TestTransferEstimate`). The `Estimate<Cmd>` hooks are pinned in Plan 04. Left for the verifier.

## Threat Flags

None - no new network endpoints, auth paths or schema changes beyond the plan's threat model.

## Next

Ready for 04-04.

## Self-Check: PASSED

- FOUND: tools/stack/server.py, tools/tests/stack_test.py
- FOUND: commits e1ec6a2, 4578887, a216e0c, 1d553dc, a7bdb64 (ancestors of HEAD)
- Full gate green (213 passed, ruff and mypy clean).
