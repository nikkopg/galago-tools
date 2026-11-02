---
phase: 06-gal-02-workflow-simulated-workcell-pac-simulator-run
plan: 01
subsystem: testing
tags: [galago-script-protocol, node-vm, stack-adapter, step-ledger, grpc, protobuf]

requires:
  - phase: 05-f5-safe-transfer-operator-acknowledge
    provides: frozen StackServer Transfer, step ledger, REPLAY_WINDOW_S replay semantics
provides:
  - docs/runbooks/gal-02-handoff.protocol.json, the GAL-02 script-mode protocol in galago-core export format (27 parameters, PAC sim defaults)
  - tools/tests/gal02_harness.py, a node vm sandbox stub runner with PATH/NODE/nvm lookup
  - FLOW-01 protocol matrix (gal02_handoff_test.py) and FLOW-03 offline re-dispatch proof (gal02_replay_test.py)
affects: [06-02 runbook, 06-03 simulated run, 06-04 PAC-sim run, 07 hardware deploy]

plan_head_before: e2560a8da88364ae61cfc5296c91dda718a6476b
plan_head_after: 88f70af91c299f3ec343e13330ad9386fda30382

actuals:
  tokens: 10289
  tasks: 3
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Script text lives only in the committed JSON; tests load scriptContent and defaults from it"
    - "Node vm sandbox stub (galago.command/note/timer plus listed globals) driven from Python via subprocess"
    - "Offline replay proof subclasses stack_test._TransferTestCase and ParseDicts script params into the real proto"

key-files:
  created:
    - docs/runbooks/gal-02-handoff.protocol.json
    - tools/tests/gal02_harness.py
    - tools/tests/gal02_handoff_test.py
    - tools/tests/gal02_replay_test.py
  modified: []

key-decisions:
  - "Parameter vocabulary locked at 27 names (D-04, D-13 fast_step_ prefix, D-14 decks); renaming later breaks stored runs"
  - "The script has no fallback values: blank required input throws before the first galago call, defaults live only in parameters[].defaultValue (D-03 Number()||default idiom has no applicable field)"
  - "Key base is label (first 20 code points) + ISO timestamp + 8 hex; keys end -in / -out, at most 58 characters"
  - "REPLAY_WINDOW_S is imported from tools.stack.ledger (it is not exported by tools.stack.server)"

patterns-established:
  - "Accepted submits are counted apart from fake-core execute_calls, which includes a Refused attempt"
  - "A throw inside the node vm is read via e.message, never instanceof Error"

requirements-completed: [FLOW-01, FLOW-03]

coverage:
  - id: D1
    description: "GAL-02 script-mode protocol exists as importable JSON in galago-core export shape with sim defaults, ordered note, STACK in, F.A.S.T., STACK out, and per-run step keys"
    requirement: "FLOW-01"
    verification:
      - kind: unit
        ref: "tools/tests/gal02_handoff_test.py (TestGal02Protocol, 18 tests)"
        status: pass
    human_judgment: true
    rationale: "The stub mirrors only the documented sandbox; galago-core's real import and Preview (plan 06-03) are the authority on row count, order and keys"
  - id: D2
    description: "A re-dispatch of the protocol's own stored STACK in-leg params through a real-mode StackServer on the fake core returns replayed SUCCESS with no second accepted submit; Refused releases the key; late re-send is refused; a new run mints new keys"
    requirement: "FLOW-03"
    verification:
      - kind: unit
        ref: "tools/tests/gal02_replay_test.py (TestGal02Redispatch, 7 tests)"
        status: pass
    human_judgment: false
  - id: D3
    description: "Node lookup (PATH, NODE, newest nvm by number) with a stated skip reason; both gal02 modules run with 0 skipped"
    requirement: "FLOW-01"
    verification:
      - kind: unit
        ref: "tools/tests/gal02_handoff_test.py (TestNodeLookup, 5 tests)"
        status: pass
    human_judgment: false

duration: 16min
completed: 2026-11-02
status: complete
---

# Phase 6 Plan 01: GAL-02 Protocol JSON and Offline Re-dispatch Proof Summary

**GAL-02 script-mode protocol as galago-core export JSON (27 sim-default parameters, per-run `-in`/`-out` STACK step keys) with a node vm harness and fake-core tests proving a re-dispatched STACK step never causes a second accepted submit.**

## Performance

- **Duration:** about 16 min
- **Completed:** 2026-11-02T03:25Z
- **Tasks:** 3
- **Files modified:** 4 (all new)

## Accomplishments

- `docs/runbooks/gal-02-handoff.protocol.json` is generated with `json.dumps` from a scratch script (never hand-escaped). It is galago-core's export shape exactly, emits four calls in fixed order (Tool Box note, STACK transfer in, F.A.S.T. transfer, STACK transfer out), validates all inputs before the first call, and carries no operator-only command.
- The two STACK legs never merge: keys end `-in` and `-out` on one base, change every evaluation, are at most 58 characters, and cut the batch label by code point (no lone surrogate). The out leg is the in leg's location triples swapped.
- Offline FLOW-03 proof on the frozen Phase 5 adapter: replay returns `SUCCESS` with meta keys exactly `stepKey, ledgerState, result, replayed`; execute count stays 1; past `REPLAY_WINDOW_S` the key is refused with "step key already completed ... nothing was sent"; Refused releases the key then one accepted submit; a tool-page re-send with blank optionals still replays; one-character key differences are fresh steps (why the runbook must demand an exact copy); a second run mints new keys.
- Full gate: `bin/make proto test` green with node on PATH: 540 passed under pytest (baseline 510 + 30 new) and 540 under unittest, ruff clean, mypy clean. Both gal02 modules ran 30 tests with 0 skipped under pytest `-rs` and `unittest discover`. `git diff --quiet 477b0ed -- tools/stack/ tools/fast/ tools/base_server.py interfaces/ requirements.txt` exits 0.

## Task Commits

1. **Task 1: tracer, protocol JSON to node stub to ParseDict to real-mode StackServer** - `c432b63` (feat)
2. **Task 2: FLOW-01 protocol matrix and node lookup (23 tests)** - `4dd4cae` (test)
3. **Task 3: FLOW-03 offline re-dispatch matrix (7 tests total in class)** - `88f70af` (test)

**Plan metadata:** committed separately (docs).

## Files Created/Modified

- `docs/runbooks/gal-02-handoff.protocol.json` - the protocol (single source of truth for script text and defaults)
- `tools/tests/gal02_harness.py` - find_node/require_node, load_export, default_params, run_script, stack_legs, constants (not collected as tests)
- `tools/tests/gal02_handoff_test.py` - TestNodeLookup (5) and TestGal02Protocol (18)
- `tools/tests/gal02_replay_test.py` - TestGal02Redispatch (7), subclass of `stack_test._TransferTestCase`

## Decisions Made

- D-03 note: the `Number(params.x) || default` idiom has no applicable field. Every required numeric has its default in `parameters[].defaultValue` (shown in the run form) and a blank throws; every optional numeric falls back to the adapter default by being omitted. No script-side fallback exists, so a blank can never silently become a sim value.
- Part 2 harness findings: strict mode (`"use strict";` prepended) yields the same tool/command sequence and param key sets as plain mode; no difference to record.

## TDD Gate Compliance

Tasks 2 and 3 are `tdd="true"` but test only artifacts that Task 1 (the tracer) had already created, as the plan specifies. There was therefore no failing-first RED for the tests as written (unexpected green by design, not a wrong test). To prove the tests can fail, a mutation check was run against the committed JSON for Task 2 and the file was then restored (`git diff` clean):

| Mutation of scriptContent | Result |
|---|---|
| out leg built with source/fast not swapped | 2 failed |
| out leg suffix `-in` instead of `-out` | 1 failed |
| `need()` no longer throws on blank | 1 failed |
| out leg removed (null) | 8 failed |
| label cut at 60 instead of 20 (first pass) | 1 failed |
| extra non-note Tool Box command emitted | 1 failed |

RED/GREEN commit pair per task was not produced: Task 2 and Task 3 each have one `test(06-01)` commit; the `feat(06-01)` commit is the Task 1 tracer. The plan frontmatter is `type: execute`, not `type: tdd`, so the plan-level gate sequence does not apply.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] REPLAY_WINDOW_S import path**
- **Found during:** Task 3
- **Issue:** The plan's interface note imports `REPLAY_WINDOW_S` from `tools.stack.server`; it is defined in `tools.stack.ledger` (collection error, then mypy attr-defined).
- **Fix:** `from tools.stack.ledger import REPLAY_WINDOW_S`. Adapter untouched.
- **Files modified:** tools/tests/gal02_replay_test.py
- **Commit:** 88f70af

**2. [Rule 1 - Bug] Harness decoded node output with the locale encoding**
- **Found during:** Task 2 (non-BMP label test design)
- **Issue:** `subprocess.run(..., text=True)` uses the locale codec, which can mangle a non-BMP character from node's UTF-8 stdout on a non-UTF-8 locale.
- **Fix:** `encoding="utf-8"` in `run_script`.
- **Files modified:** tools/tests/gal02_harness.py
- **Commit:** 4dd4cae

**Total deviations:** 2 auto-fixed (1 blocking, 1 bug). **Impact:** none on scope; the adapter, protos, requirements and `tools/stack/`, `tools/fast/`, `tools/base_server.py` are unchanged since 477b0ed.

## Authentication Gates

None.

## Flagged Assumptions (carried from the plan)

- **A-EDGE-FLOW-01:** the node stub mirrors only the documented sandbox API; galago-core's real executor is the authority. If Preview of the imported protocol disagrees with the harness (row count, order, keys, params), the runbook Findings log records it and the harness or script is corrected, never the import path.
- **A-EDGE-FLOW-03:** `execute_calls` counts every attempt, a Refused one included, so accepted submits are counted separately. This proves the adapter never re-submits a stored key, not anything about the instrument's own task list (FLOW-04 owns that evidence).

## Known Stubs

None.

## Threat Flags

None. No new network endpoint, auth path or schema; tests ran only on loopback fakes and the fixture host is asserted not in `{10.150.1.125, stack-server}`.

## Issues Encountered

None.

## Next Phase Readiness

Ready for 06-02 (runbook). Parts of Phase 6 that need DEP-02 (FLOW-02, simulated half of FLOW-03, FLOW-04) remain gated on galago-core Phase 5.

## Self-Check: PASSED

- FOUND: docs/runbooks/gal-02-handoff.protocol.json, tools/tests/gal02_harness.py, tools/tests/gal02_handoff_test.py, tools/tests/gal02_replay_test.py
- FOUND commits: c432b63, 4dd4cae, 88f70af
