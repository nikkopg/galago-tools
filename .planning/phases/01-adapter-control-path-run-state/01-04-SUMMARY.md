---
phase: 01-adapter-control-path-run-state
plan: 04
subsystem: adapter
tags: [ast, static-analysis, fast-adapter, invariant-testing, safety]

# Dependency graph
requires:
  - phase: 01-adapter-control-path-run-state (plan 01)
    provides: "Pause/Resume/Abort, CONTROL_COMMANDS, the original TestAdapterInvariant scoped-attribute check with .pause already moved to scoped (not banned)"
  - phase: 01-adapter-control-path-run-state (plan 03)
    provides: "_record_pause, _log_progress (extended), _build_run_state, _get_status -- the functions this plan's new rules scope"
provides:
  - "_SCOPED_ATTRS: dict[str, frozenset[str]] replacing the one-owner scoped-attribute map; .wait now owns Resume plus Transfer/RunProtocol"
  - "_adapter_invariant_violations(tree): a pure, assertion-free checker returning violation strings, reused by the real-file check and by every planted-violation test"
  - "_plant(tree, function, statement): deep-copies an AST and inserts a parsed statement into a named function (after its docstring) or at module level"
  - "_RECORD_ONLY_FUNCTIONS, _STATUS_READERS, _CONTROL_PATH_FUNCTIONS, _COMMANDING_NAMES, _INSTRUMENT_STATES: the new scoping constants for D-16/D-14/D-08"
  - "Five planted-violation/allowed-call test methods in TestAdapterInvariant proving every rule (old and new) actually depends on the code it checks"
affects: [01-05-simulated-pause-hook]

# Actuals (#2632)
actuals:
  tokens: 5289
  tasks: 2
  commits: 2
  plan_head_before: 9890f6b230880fe80f7696ab52483274d354b980
  plan_head_after: edcf241d9ce4f1c627cf22b26954b2d216972591

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "A test-time AST checker factored into a pure function (_adapter_invariant_violations) that returns violation strings instead of asserting, so the same function checks both the real source file and deliberately-broken copies without the planting test failing on its own plant"
    - "_plant(tree, function, statement): a reusable AST-mutation helper (copy.deepcopy + ast.parse(...).body + list splice + ast.fix_missing_locations) that inserts a statement into a named function after its docstring, used to prove a static check actually fires (D-17 planted-violation pattern) without ever executing the planted code"
    - "Attribute-to-owner scoping generalized from a single owner name to a frozenset of owner names (_SCOPED_ATTRS), so one attribute (.wait) can be legitimately called from more than one method"
    - "A 'required functions exist' pre-check (reported as a violation, not an exception) so a rename or deletion of any scoped/owning method can never silently disable the rule that depends on it"

key-files:
  created: []
  modified:
    - tools/tests/fast_test.py

key-decisions:
  - "D-15: _SCOPED_ATTRS[\"wait\"] = frozenset({\"Resume\", \"Transfer\", \"RunProtocol\"}) -- Transfer/RunProtocol don't call .wait today (they call run_transfer/run_protocol), but the scoping allows it per the plan's exact spec rather than narrowing to only the methods that currently use it"
  - "D-17: _adapter_invariant_violations never raises; it is the single source of truth for both test_adapter_obtains_service_only_through_open_service (must return []) and every planted-violation test (must report the planted mistake), proving the checker depends on content in both directions (T-01-20)"
  - "D-16/D-14/D-08: no changes were needed to tools/fast/server.py -- _record_pause, _log_progress, _build_run_state, and the control-path functions (Pause/Resume/Abort/ExecuteCommand/_dispatchCommand) already satisfied every new rule; this plan is purely additive test coverage, confirmed by running the new checker against the real file before writing any planted-violation test"
  - "The control-path state-comparison rule deliberately excludes _log_progress (per the plan): its `state == \"running\"` check is bookkeeping about an observation, not a gate on a command, so it is not in _CONTROL_PATH_FUNCTIONS"
  - "Record-only and status-only-reader violation messages all name the offending function (e.g. \"_record_pause() touches .service at line N\"), so a single subTest assertion (fragment-in-message) can validate each planted case without re-deriving exact wording"

requirements-completed: [ADP-07, ADP-09]

coverage:
  - id: D1
    description: "_SCOPED_ATTRS and _adapter_invariant_violations/_plant form a reusable, non-vacuous checker: the real server.py returns [], and a planted .pause/.abort/.resume/.wait violation (including one in a brand-new module-level function) is reported by name"
    requirement: "ADP-07"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestAdapterInvariant.test_adapter_obtains_service_only_through_open_service"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestAdapterInvariant.test_planted_scoped_call_violations_are_caught"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestAdapterInvariant.test_planted_allowed_calls_add_no_violation"
        status: pass
    human_judgment: false
  - id: D2
    description: "The pre-existing invariants (fast_mcp.mcp import ban, no raw :5003/REST path literals, no direct FastService/InstrumentSession construction, open_service required, banned attributes, httpx limited to HTTPError) are preserved as pure checks and proven non-vacuous by planting one violation per rule"
    requirement: "ADP-07"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestAdapterInvariant.test_planted_existing_invariant_violations_are_caught"
        status: pass
    human_judgment: false
  - id: D3
    description: "_record_pause and _log_progress are provably record-only: no access to .service and no call naming a control or motion method anywhere in their bodies, each planted mistake reported, a planted logging call adds nothing"
    requirement: "ADP-07"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestAdapterInvariant.test_planted_record_and_state_violations_are_caught"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestAdapterInvariant.test_planted_allowed_record_and_reader_calls_add_no_violation"
        status: pass
    human_judgment: false
  - id: D4
    description: "service.status() calls are confined to _get_status/_build_run_state (D-14), _build_run_state calls nothing else on the service, and no control-path function (Pause/Resume/Abort/ExecuteCommand/_dispatchCommand) compares against an instrument-state string (D-08, ADP-09); each mistake is planted and reported, a planted allowed status() call in _build_run_state adds nothing"
    requirement: "ADP-09"
    verification:
      - kind: unit
        ref: "tools/tests/fast_test.py#TestAdapterInvariant.test_planted_record_and_state_violations_are_caught"
        status: pass
      - kind: unit
        ref: "tools/tests/fast_test.py#TestAdapterInvariant.test_planted_allowed_record_and_reader_calls_add_no_violation"
        status: pass
      - kind: other
        ref: "PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto test (full gate: ruff, mypy, 109 unittest + pytest tests)"
        status: pass
    human_judgment: false

duration: 10min
completed: 2026-10-12
status: complete
---

# Phase 1 Plan 4: Mechanical No-Auto-Abort Invariant Summary

**`_adapter_invariant_violations` is now a reusable, assertion-free AST checker covering every existing and newly-scoped rule -- `.pause`/`.resume`/`.abort`/`.wait` confined to their owning methods, the pause recorder and progress callback record-only, the run-state reader status-only, and no control-path function comparing against an instrument-state string -- with a planted violation proving each rule actually fires.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-10-12T22:11:00Z
- **Completed:** 2026-10-12T22:21:28Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- `_SCOPED_ATTRS: dict[str, frozenset[str]]` replaces the old one-owner scoped-attribute map; `.wait` is now legitimately owned by `Resume`, `Transfer`, and `RunProtocol` (D-15)
- `_adapter_invariant_violations(tree)` is a pure, never-raising function reproducing every rule `test_adapter_obtains_service_only_through_open_service` used to assert inline (import allowlist, no plain `import fast_mcp`, banned constructors, `open_service` required, banned attributes, `httpx` limited to `HTTPError`, banned substrings) plus a "required function exists" pre-check so a rename can't silently disable a rule
- `_plant(tree, function, statement)` deep-copies an AST and inserts a parsed statement into a named function (after its docstring) or at module level, used by every planted-violation test without ever executing the planted code
- `TestAdapterInvariant` gained three new tests (`test_planted_scoped_call_violations_are_caught`, `test_planted_existing_invariant_violations_are_caught`, `test_planted_allowed_calls_add_no_violation`) proving the checker is non-vacuous in both directions (D-17, T-01-20)
- `_RECORD_ONLY_FUNCTIONS`, `_STATUS_READERS`, `_CONTROL_PATH_FUNCTIONS`, `_COMMANDING_NAMES`, `_INSTRUMENT_STATES` extend the checker with four more rules: `_record_pause`/`_log_progress` never touch `.service` or call a control/motion method (D-16); `_build_run_state` calls only `.status()` on the service (D-14); `service.status()` is confined to `_get_status`/`_build_run_state` (D-08, ADP-09); no control-path function (`Pause`/`Resume`/`Abort`/`ExecuteCommand`/`_dispatchCommand`) compares against an instrument-state string, deliberately excluding `_log_progress`'s own observational `state == "running"` check
- Two more planted-violation tests (`test_planted_record_and_state_violations_are_caught`, `test_planted_allowed_record_and_reader_calls_add_no_violation`) cover all four new rules; `tools/fast/server.py` needed no changes -- it already satisfied every new rule

## Task Commits

Each task was committed atomically:

1. **Task 1: A reusable invariant checker with the full scoped map, proven by planted violations** - `3dd24e7` (test)
2. **Task 2: Record-only callbacks, a status-only run-state reader, and no instrument-state checks on the control path** - `edcf241` (test)

## Files Created/Modified
- `tools/tests/fast_test.py` - `_SCOPED_ATTRS`, `_RECORD_ONLY_FUNCTIONS`, `_STATUS_READERS`, `_CONTROL_PATH_FUNCTIONS`, `_COMMANDING_NAMES`, `_INSTRUMENT_STATES`, `_adapter_invariant_violations(tree)`, `_plant(tree, function, statement)`, and `TestAdapterInvariant` rewritten/extended with five planted-violation test methods

## Decisions Made
- **D-15**: `.wait` scoped to `{"Resume", "Transfer", "RunProtocol"}` per the plan's exact spec, even though only `Resume` calls it today -- the allowance is forward-looking, not a tightened allowlist derived from current usage.
- **D-17**: the checker function never raises; every rule, old and new, is proven non-vacuous by a planted violation that must be caught and a planted allowed call that must not add anything.
- **D-16/D-14/D-08**: no production code changes were needed. The real `tools/fast/server.py` was checked against every new rule before any planted-violation test was written, and it passed cleanly on the first run -- confirming Plan 01-03's implementation already respected these boundaries.
- The control-path state-comparison rule explicitly does not cover `_log_progress`: its `state == "running"` check clears a recorded pause on an observation, it does not gate a command, matching the plan's explicit carve-out.

## Deviations from Plan

None - plan executed exactly as written. No production code (`tools/fast/server.py`) needed fixing; `tools/base_server.py` was never touched (confirmed via `git diff --exit-code 9c27896 -- tools/base_server.py` after each task).

## Issues Encountered

None.

## Known Stubs

None - no stub patterns introduced. This plan is test-only (AST-checker and planted-violation tests), with no UI or data-flow surface that could stub.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `_adapter_invariant_violations`, `_plant`, `_SCOPED_ATTRS`, `_RECORD_ONLY_FUNCTIONS`, `_STATUS_READERS`, `_CONTROL_PATH_FUNCTIONS`, `_COMMANDING_NAMES`, and `_INSTRUMENT_STATES` are all in place under the exact names the phase's artifact inventory specifies, ready for Plan 01-05 to extend `_RECORD_ONLY_FUNCTIONS` with the simulated hook's two new functions.
- The checker returns `[]` against the real `tools/fast/server.py` and is proven non-vacuous (five planted-violation/allowed-call test methods, ten `subTest` cases total) against every rule it enforces, old and new.
- Full gate green: `ruff` clean, `mypy` 0 errors, 109 unittest + pytest tests passing (up from 104 at the end of Plan 01-03) at HEAD `edcf241`.
- No blockers.

## Self-Check: PASSED

- FOUND: tools/tests/fast_test.py
- FOUND: 3dd24e7 (ancestor of HEAD)
- FOUND: edcf241 (ancestor of HEAD)
- Full gate (`bin/make proto test`: ruff, mypy, 109 unittest + pytest tests) green at HEAD `edcf241`
- `git diff --exit-code 9c27896 -- tools/base_server.py` exits 0 (never edited)
- `_adapter_invariant_violations` on the real `tools/fast/server.py` returns `[]`

---
*Phase: 01-adapter-control-path-run-state*
*Completed: 2026-10-12*
