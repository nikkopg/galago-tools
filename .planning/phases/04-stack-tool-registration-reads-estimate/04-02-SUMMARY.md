---
phase: 04-stack-tool-registration-reads-estimate
plan: 02
subsystem: stack-tool
tags: [configure, owner-lock, supply-chain-pin, ast-invariant, no-motion]
status: complete
requires: ["04-01"]
provides:
  - "StackServer._configure full D-07 lifecycle: endpoint_key reuse, close-first, transfer_timeout_s validation, ledger_dir record-only, port 0 -> 5005"
  - "_RESTART_WARNING logged once per fresh open (D-09)"
  - "TestAdapterInvariant: mechanical proof that tools/stack/ cannot call any core motion/cancel/safe-position/validate/acknowledge method, never imports the core MCP subpackage, and calls open_service only as owner galago"
  - "TestRequirementsPin: single 40-hex SHA pin, installed commit_id equals it"
affects: [04-03, 04-04, 04-05]
tech-stack:
  added: []
  patterns: ["close-first endpoint change", "assertion-free AST checker with planted violations (fast tool precedent)"]
key-files:
  created: []
  modified:
    - tools/stack/server.py
    - tools/tests/stack_test.py
key-decisions:
  - "Same-endpoint reuse is keyed on the core's endpoint_key against OwnedService.endpoint; the adapter only strips the host and never rewords a core exception"
  - "transfer_timeout_s and ledger_dir are recorded only; nothing touches the ledger path (Phase 5 owns it)"
requirements-completed: [STK-02, STK-05]
duration: 8 min
completed: 2026-10-29
plan_head_before: 6926261e7a1c8c8697e1bbf6f17dcc2b67873681
plan_head_after: 887e234fbd6d2127a324eda6919c521bcf5c9a33
commits: 4
actuals:
  tokens: 7000
  tasks: 3
  commits: 4
coverage:
  - deliverable: "Configure ownership lifecycle: foreign (stack-mcp) holder named in NOT_READY, same-endpoint reuse, close-first on endpoint change"
    verification:
      - {kind: test, ref: "tools/tests/stack_test.py#TestStackOwned", status: pass}
      - {kind: test, ref: "tools/tests/stack_test.py#TestConfigureOwnership", status: pass}
    human_judgment: false
  - deliverable: "Configure validation and failure surfaces (timeout, blank host, closed port, missing credentials, no credential leakage), ledger_dir record-only, port 0 -> 5005, one restart WARNING per fresh open"
    verification:
      - {kind: test, ref: "tools/tests/stack_test.py#TestConfigureFails", status: pass}
      - {kind: test, ref: "tools/tests/stack_test.py#TestConfigureWarning", status: pass}
      - {kind: test, ref: "tools/tests/stack_test.py#TestConfigureLedgerDir", status: pass}
    human_judgment: false
  - deliverable: "SHA pin and AST no-motion / no-MCP / open_service-shape invariant with planted violations"
    verification:
      - {kind: test, ref: "tools/tests/stack_test.py#TestRequirementsPin", status: pass}
      - {kind: test, ref: "tools/tests/stack_test.py#TestAdapterInvariant", status: pass}
    human_judgment: false
---

# Phase 4 Plan 2: Configure lifecycle and no-motion invariant Summary

Completed the operator's Configure lifecycle (owner lock via the core's `open_service(owner="galago")`, same-endpoint session reuse by `endpoint_key`, close-first endpoint changes, finite/non-negative `transfer_timeout_s`, record-only `ledger_dir`, one restart-clears-latch WARNING per fresh open) and locked in the supply-chain pin plus an AST test proving nothing under `tools/stack/` can reach a core motion or acknowledge method or the core MCP subpackage.

## Accomplishments

- `_configure` in `tools/stack/server.py`: validates host and `transfer_timeout_s` before any open; computes `endpoint_key(host, port)`; returns early when the owned session is already on that endpoint; otherwise closes the old `OwnedService` (releasing its owner lock) and clears `service` before `open_service(host, port, owner="galago")`, so a failed new open leaves no lock and no service. Logs `_RESTART_WARNING` once after a fresh open.
- Ownership tests: a `stack-mcp` holder fails Configure with "already owned by mcp", FAILED status, no REST client built, holder's lock untouched; whitespace and case variants reuse one session (`open_service` called once, `service` identical); moving A to B proves A is free inside B's open; opening a port owned by mcp afterwards leaves B free and the tool with no service.
- Failure tests: NaN/inf/-inf/-1.0 timeouts and blank host fail before open; a closed loopback port yields "transport error" and releases the lock; missing credentials yield the core's "STACK credentials missing"; a sentinel password never appears in any reply or DEBUG log record.
- `TestRequirementsPin` and `TestAdapterInvariant` (ten forbidden call names each planted, three MCP import forms, five open_service shape violations, constructors incl. `Credentials.from_env`, forbidden literals incl. the hardware manager address and stack-server host, renamed required functions, allowed read calls not reported).

## Task Commits

| Task | Name | Commit |
| ---- | ---- | ------ |
| 1 | Tracer: Configure ownership lifecycle | 52a98b9 |
| 2 | Validation, failure surfaces, restart warning (RED) | 76587b3 |
| 2 | Validation, failure surfaces, restart warning (GREEN) | 97ad5a0 |
| 3 | SHA pin and AST invariant | 887e234 |

## Verification

- `bin/make proto test`: 186 passed (160 baseline + 26 new), ruff and mypy clean.
- Tracer re-verified end to end (full gate, 165 passed) before expansion.
- All acceptance greps pass. No network beyond loopback; no STACK hardware contacted; `tools/base_server.py` untouched.

## Deviations from Plan

None - plan executed exactly as written. (Task 2 followed TDD with a separate RED test commit, 76587b3, before the GREEN feat commit, per the TDD reference.)

## Authentication Gates

None.

## Known Stubs

None.

## Flagged assumption (STK-02 edge probe, unresolved by the probe)

Treated host-string equality as the relevant edge: the adapter only strips the host and relies on the core's `endpoint_key` for case/brackets/trailing-dot folding, so its lock key matches stack-mcp's. Covered by `TestConfigureOwnership` (whitespace and case variants reuse one session). Left for the verifier.

## Threat Flags

None - no new network endpoints, auth paths or schema changes beyond the plan's threat model.

## Next

Ready for 04-03.

## Self-Check: PASSED

- FOUND: tools/stack/server.py, tools/tests/stack_test.py
- FOUND: commits 52a98b9, 76587b3, 97ad5a0, 887e234 (ancestors of HEAD)
- Full gate green (186 passed, ruff and mypy clean).
