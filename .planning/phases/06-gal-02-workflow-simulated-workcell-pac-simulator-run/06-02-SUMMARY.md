---
phase: 06-gal-02-workflow-simulated-workcell-pac-simulator-run
plan: 02
subsystem: testing
tags: [runbook, dep-02-gate, bash, pac-simulator, galago-script-protocol]

requires:
  - phase: 06-gal-02-workflow-simulated-workcell-pac-simulator-run
    provides: "06-01 protocol JSON, node harness (load_export), offline re-dispatch proof"
provides:
  - docs/runbooks/gal-02-dep02-check.sh, the read-only DEP-02 gate (DEP-02 OK / BLOCKED:)
  - docs/runbooks/gal-02-handoff.md, the GAL-02 operator runbook with a ready Findings log
  - tools/tests/gal02_runbook_test.py, gate fixture-tree tests and runbook content pins
affects: [06-03 simulated run, 06-04 PAC-sim run, 07 hardware deploy]

plan_head_before: da489fc784928d9c7763fe5538338383f9d6c7fd
plan_head_after: 5f2d2c76842d264f088c512b042b5ae1d10d71b4

actuals:
  tokens: 9200
  tasks: 2
  commits: 3

tech-stack:
  added: []
  patterns:
    - "Gate script tested on fixture trees built in a temp dir, with a snapshot (sha256, mtime_ns, file list) read-only proof"
    - "Runbook content pinned by tests: ordered headings, every protocol parameter in backticks, procedure phrases, findings rows"

key-files:
  created:
    - docs/runbooks/gal-02-dep02-check.sh
    - docs/runbooks/gal-02-handoff.md
    - tools/tests/gal02_runbook_test.py
  modified: []

key-decisions:
  - "Gate is a script with an exit code, not a fenced block, so plans 06-03 and 06-04 get one command to stop on and the gate is testable on fixture trees"
  - "Runbook references SAL A.0..A.10 by section and never copies the sim build steps"

patterns-established:
  - "Gate prints one missing:/forbidden: line per failed check and a single final verdict line"

requirements-completed: [FLOW-01]

coverage:
  - id: D1
    description: "Read-only DEP-02 gate: six checks, never passes falsely on an empty tree, any single missing piece, an exposed acknowledge, or a one-byte proto difference"
    requirement: "FLOW-04"
    verification:
      - kind: unit
        ref: "tools/tests/gal02_runbook_test.py (TestDep02Gate, 7 tests)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Runbook with protocol reference, Part 1, gate, shared setup, Part 2a, Part 2b with hardware-refusal preflight and evidence calibration, teardown, follow-ups and a Findings log with the 10 rows"
    requirement: "FLOW-01"
    verification:
      - kind: unit
        ref: "tools/tests/gal02_runbook_test.py (TestRunbookContent, 8 tests)"
        status: pass
    human_judgment: true
    rationale: "Tests pin structure and required phrases only. Whether the operator procedure runs as written is established by the Part 2 plans (06-03, 06-04)."

duration: 20min
completed: 2026-11-02
status: complete
---

# Phase 6 Plan 02: GAL-02 Runbook and DEP-02 Gate Summary

**Read-only `gal-02-dep02-check.sh` gate (six checks, tested on fixture trees) plus the full GAL-02 operator runbook for Part 2a/2b, with the D-07 limit stated verbatim, a hardware-refusal preflight and a ready Findings log.**

## Performance

- **Duration:** about 20 min
- **Completed:** 2026-11-02
- **Tasks:** 2
- **Files:** 3 (all new)

## Accomplishments

- The gate checks: galago-core checkout, `ToolType.stack`, generated `stack.ts`, `commandFields.stack.transfer`, no `acknowledge` in the stack block, and vendored `stack.proto` byte-equal to the frozen one. It only reads (plus `git rev-parse --short HEAD`) and prints one `missing:`/`forbidden:` line per failed check, then `DEP-02 OK` (exit 0) or `BLOCKED:` (exit 1).
- **The gate prints `DEP-02 OK` on the real sibling tree today** (galago-core `feat/stack-tool` HEAD `a5fa75f`). The plan expected BLOCKED, but galago-core Phase 5 (05-01..05-03) has landed since the plan was written. I confirmed independently: `stack = "stack"` at `controller/gen-interfaces/controller.ts:31`, `stack.ts` generated, `commandFields.stack` holds `transfer` and no `acknowledge`, and the vendored proto is byte-equal (`cmp` clean). So Part 2 is no longer blocked at the gate. The two follow-on checks (dev galago-core started from that source, `commandFields.test.ts` passing) are still the operator's.
- The runbook has the 16 ordered required headings, all 27 parameters in backticks, the step-key rules, import through `jq .protocol ... | curl POST /api/protocols` (never the Import button), the separate STACK-SIM (40010) and STACK-PACSIM (40012) tool processes, the hardware-refusal preflight, the calibrated no-second-POST procedure with its fallback evidence, teardown, upstream follow-ups and a Findings log with rows G0, 2a-1..2a-3, 2b-0..2b-5 all "pending".
- Tests: 15 in `gal02_runbook_test.py` (7 gate, 8 content), 15 passed, 0 skipped. Full gate `bin/make proto test` green with node on PATH: 555 passed under pytest (baseline 540 + 15) and 555 under unittest, ruff clean, mypy clean. `git diff --quiet 477b0ed -- tools/stack/ tools/fast/ tools/base_server.py interfaces/ requirements.txt` exits 0.

## Task Commits

1. **Task 1 (tracer): gate script, runbook gate section, gate tests** - `ec11721` (feat)
2. **Task 2 RED: runbook content tests** - `7e5ec4b` (test; 4 of 5 new tests failed against the Task 1 runbook, as intended)
3. **Task 2 GREEN: complete runbook** - `5f2d2c7` (docs)

**Plan metadata:** committed separately (docs).

## Deviations from Plan

None to code or scope. One expectation differed from the plan text: the gate says `DEP-02 OK`, not `BLOCKED`, on 2026-11-02 (see Accomplishments). The plan's second verify command and acceptance accept either verdict, and `test_dep02_gate_on_the_real_sibling_tree_prints_one_verdict` pairs the exit code with the last line either way. Part 2 plans must run the gate themselves rather than assume its result.

Operator-facing assumptions I could not check offline (to be confirmed in Part 2): the shape of `$GAL06_DIR/ports.override.yml` (modelled on the gal05 override), the `logs-mgr` and `db/pac-manager.db` paths under `$STACK_SIM_DIR` for the calibration counter, and that `python -m tools.stack.server --port=<n>` is the launch form (it matches `tools/stack/server.py`'s `--port` argument and the fast server's launch form).

## Flagged Assumptions

- **A-EDGE-FLOW-02-RB:** after DEP-02, galago-core's tool-page form is assumed to send blank numbers as 0 and blank strings as empty, as the v1 F.A.S.T. form did. The runbook records the observed behaviour in row 2b-3, and a fingerprint-mismatch reply on the re-send is recorded as a Finding, not retried with edits.

## TDD Gate Compliance

Task 2 is `tdd="true"`. RED commit `7e5ec4b` (4 failed, 11 passed) then GREEN commit `5f2d2c7` (15 passed). The plan frontmatter is `type: execute`, so the plan-level gate does not apply.

## Known Stubs

None. The Findings log rows read "not run yet / pending" by design; plans 06-03 and 06-04 fill them.

## Threat Flags

None. The gate reads files only; the runbook holds no credential (regex test) and no token.

## Self-Check: PASSED

- FOUND: docs/runbooks/gal-02-dep02-check.sh, docs/runbooks/gal-02-handoff.md, tools/tests/gal02_runbook_test.py
- FOUND commits: ec11721, 7e5ec4b, 5f2d2c7
