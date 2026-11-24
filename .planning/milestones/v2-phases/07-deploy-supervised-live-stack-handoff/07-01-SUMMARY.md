---
phase: 07-deploy-supervised-live-stack-handoff
plan: 01
subsystem: infra
tags: [stack, runbook, preflight, bash, fail-closed, systemd, docker, live-safety]

# Dependency graph
requires:
  - phase: 06-gal-02-workflow-simulated-workcell-pac-simulator-run
    provides: the DEP-02 gate script (gal-02-dep02-check.sh), the gal-02 runbook+test triple pattern, and the adapter proven through the loopback PAC simulator
provides:
  - docs/runbooks/gal-07-live-check.sh — executable fail-closed live pre-flight gate (8 env-overridable checks; verdict lines PREFLIGHT OK / BLOCKED:)
  - docs/runbooks/gal-07-live-handoff.md — the supervised live runbook for LIVE-08/09/10 with per-event typed GO gates, the safe-order deploy procedure, the D-11 recovery drill and the 13-row findings log
  - tools/tests/gal07_live_runbook_test.py — falsification matrix, degenerate-input fail-closed proof, held-lock fixture with a real flock, read-only snapshot proof, and the runbook text pins
affects: [07-02 deploy, 07-03 LIVE-09, 07-04 LIVE-10, gsd-verify-work phase 7, /gsd-ship]

# Actuals (#2632) — pairs with the plan's `estimate` to calibrate future estimates.
actuals:
  tokens: 79000
  tasks: 3
  commits: 3
plan_head_before: 7d158fb8e00921ac9c680e491cc8bccca98f190b
plan_head_after: 4ca4112e8405b23ad2eefe2114a26923791c50ea

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Fail-closed exit-code gate: set -u (never set -e), a failed accumulator, per-check missing:/forbidden:/warn: lines, verdict as the last line (mirrors gal-02-dep02-check.sh)"
    - "Lock probing through the pinned core's own endpoint_key/lock_path/default_lock_dir helpers plus a non-blocking flock — never a re-implemented lock name"
    - "Presence-only credential checks (assignment-line count, 0600 mode); advisory warn: by default, blocking under GAL07_REQUIRE_STACK_ENV=1"
    - "Fixture falsification: one-removed-piece matrix, degenerate-input fail-closed cases, twice-run read-only snapshot"

key-files:
  created:
    - docs/runbooks/gal-07-live-check.sh
    - docs/runbooks/gal-07-live-handoff.md
    - tools/tests/gal07_live_runbook_test.py
  modified: []

key-decisions:
  - "The gate reads the PRODUCTION API shapes, discovered at verification time: the tool store nests the STACK config under .config.stack, and /api/runs is a {count, data} envelope — both allow-listed with fail-closed fallbacks (pattern from RESEARCH interfaces assumed flat arrays)"
  - "GAL07_REQUIRE_ALL is this test module's REQUIRE_ALL_ENV variant (gal02_harness pattern, own variable name, no shared-constant mutation so GAL02_REQUIRE_ALL promote semantics stay intact)"
  - "Credential-env handling: missing file, missing assignment line and mode != 0600 are warn:-only by default and blocking (missing: + failed=1) under GAL07_REQUIRE_STACK_ENV=1, which the runbook's Parts 2-3 set"
  - "Findings rows G0/1a-1..6/2a-1..3/3a-1..3 are authored empty by design; plans 07-02..04 fill them during the supervised live session"

patterns-established:
  - "Per-plan head ledger at .planning: measured commits for the SUMMARY frontmatter"
  - "Fixture HTTP server + stub-bin helpers (dep02 stub, docker stub) for gate falsification, reuse-able by later gate tests"

requirements-completed: [LIVE-08]

coverage:
  - id: D1
    description: "Executable live pre-flight gate with 8 env-overridable checks (manager identity, owner-lock probe through the pinned core, DEP-02 commit assert, DEP-02 gate re-run, web bundle, D-12 pre-store with byte-exact host, no RUNNING run, credential presence-only), fail-closed on empty/malformed input"
    requirement: LIVE-08
    verification:
      - kind: unit
        ref: "tools/tests/gal07_live_runbook_test.py::TestLiveGate (13 tests: complete-fixture pass, 15-removal/blocking matrix incl nested-config and runs-envelope shapes, degenerate inputs, credential advisory/required, held-lock)"
        status: pass
      - kind: integration
        ref: "bash docs/runbooks/gal-07-live-check.sh on the real host → exit 1, last line BLOCKED:, with missing: stack_automation_layer pinned + missing: a type fast tool + advisory warn: (the two known pre-deploy reasons)"
        status: pass
    human_judgment: false
  - id: D2
    description: "The gate provably writes nothing: two consecutive runs leave a sha256+mtime_ns snapshot of the complete fixture set byte-identical"
    verification:
      - kind: unit
        ref: "tools/tests/gal07_live_runbook_test.py::TestLiveGate::test_gate_is_read_only"
        status: pass
    human_judgment: false
  - id: D3
    description: "Live runbook gal-07-live-handoff.md with, in order: Safety rules, Pre-flight, Part 1 deploy (LIVE-08), Part 2 LIVE-09, Part 3 LIVE-10, Recovery drill (D-11), Findings log; typed-go gates with UTC lines (exactly one 'Reply: literal go' per part), never-delete clauses, manager-UI primary recovery route with AcknowledgeFailure fallback, verbatim restart-warning and 600 s replay-window rules; 13 empty findings rows G0/1a-x/2a-x/3a-x"
    requirement: LIVE-08
    verification:
      - kind: unit
        ref: "tools/tests/gal07_live_runbook_test.py::TestRunbookContent (8 headings in order, 31 required phrases, one gate block per part with UTC, every findings row, credential-value regex)"
        status: pass
      - kind: other
        ref: "inline assert: 13 rows match '^| <row-id> |' and 'Reply: literal go' count == 3; gal-02-handoff.md pristine"
        status: pass
    human_judgment: false
  - id: D4
    description: "The runbook's live procedures themselves (deploy order, LIVE-09 rehearsal, LIVE-10 handoff, recovery drill) are authored and test-pinned but NOT executed — they run supervised, with the operator present, under plans 07-02..04"
    verification: []
    human_judgment: true
    rationale: "Live hardware motion is the requirement of the executing plans (07-02/03/04) and is operator-run by design (D-10); no automated run can prove these procedures. Text pins prove only the authored claims, explicitly not the execution."

# Metrics
duration: 29 min
completed: 2026-11-02
status: complete
---

# Phase 7 Plan 1: Live pre-flight gate + runbook + falsification tests Summary

**Executable fail-closed live pre-flight gate (8 checks incl. core-pin assert and owner-lock probe through the pinned STACK core), the supervised-live runbook with per-event GO gates and recovery drill, and a falsification-test module that proves the gate cannot pass falsely — the real-host pre-deploy run BLOCKs on exactly the two known gaps (service-venv core pin, missing F.A.S.T. store entry).**

## Performance

- **Duration:** 29 min
- **Started:** 2026-11-02T10:20:34Z
- **Completed:** 2026-11-02T10:49:52Z
- **Tasks:** 3
- **Files modified:** 3 (all new)

## Accomplishments
- `docs/runbooks/gal-07-live-check.sh`: a read-only, env-overridable, fail-closed 8-check gate. Check 2 probes the owner lock through the pinned core's own `endpoint_key`/`lock_path`/`default_lock_dir` with a non-blocking flock and the verbatim `StackOwnedError` wording; every check runs even after a failure, and the verdict is the last line (`PREFLIGHT OK` exit 0 / `BLOCKED:` exit 1).
- Full fixture falsification in `tools/tests/gal07_live_runbook_test.py`: complete-set pass, a 12-piece blocking matrix + nested-config and runs-envelope shapes, degenerate-input fail-closed cases, held-lock fixture where the test process really holds the flock, credential advisory/required variants, and a twice-run read-only snapshot proof.
- `docs/runbooks/gal-07-live-handoff.md`: the single supervised-live procedure — Safety rules, Pre-flight, Part 1 deploy (rollback anchors, GO gate, uv-only core install with the OQ-1 checkpoint, 0600 credentials env + `systemctl --user edit` wiring, D-06 log backup, restart checks with the listener-PID re-baseline, decided reconnect order FAST-first/STACK-last, galago-web rebuild with the cache-hit STOP rule, interrupted-deploy posture, four-timestamp evidence table), Part 2 LIVE-09 rehearsal Transfer (reads-first parameter selection), Part 3 LIVE-10 handoff (pre-store-first GO gate, live parameter mapping), the D-11 recovery drill, and the 13-row findings log. gal-02-handoff.md untouched (D-07).
- Phase 6 regression holds: `tools/tests/gal02_runbook_test.py` and the full repo gate stay green (579 pytest tests).

## Task Commits

Each task was committed atomically:

1. **Task 1: End-to-end "the live gate refuses a wrong manager identity" (tracer)** - `97bf310` (feat)
2. **Task 2: Remaining five pre-flight checks with the full falsification matrix and read-only proof** - `f13a5ea` (feat)
3. **Task 3: Full live runbook with GO gates, deploy procedure, recovery drill and findings log** - `4ca4112` (feat)

## Files Created/Modified
- `docs/runbooks/gal-07-live-check.sh` - the executable pre-flight gate (chmod +x)
- `docs/runbooks/gal-07-live-handoff.md` - the live supervised runbook (D-07's new file)
- `tools/tests/gal07_live_runbook_test.py` - gate falsification + runbook text pins

## Decisions Made
- The gate reads the production API shapes rather than the plan-interface's assumed flat ones: the production store nests the STACK config under `.config.stack` (verified live against :3010) and `/api/runs` is a `{"count": n, "data": []}` envelope. Both are accepted, and anything else fails closed with a named `missing:` line.
- Credential-env handling is presence-only and advisory by default; `GAL07_REQUIRE_STACK_ENV=1` (set by runbook Parts 2-3) makes a missing file/assignment/mode blocking.
- The test module defines its own `GAL07_REQUIRE_ALL` REQUIRE_ALL_ENV variant instead of mutating gal02_harness's shared constant, so Phase 6's `GAL02_REQUIRE_ALL=1` promote semantics cannot regress.
- The probe python resolution order: `${GALAGO_SERVICES_VENV}/bin/python` first, then the gate venv, overridable by `GAL07_LOCK_PROBE_PYTHON` (used by the tests to pin `sys.executable`).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Production API shape mismatches in checks 6-7**
- **Found during:** Task 2 (the real-host verify run)
- **Issue:** The plan's interfaces section described `GET /api/tools` entries with a flat `config.host`; the production store nests it under `config.stack.host`, and `/api/runs` returns a `{"count": n, "data": []}` envelope rather than a bare array. The first real-host run therefore reported `[null]` hosts and an unparseable run list.
- **Fix:** Check 6 now accepts `.config.host // .config.stack.host` (anything else: `missing:` with the stored strings printed); check 7 accepts a bare array or the `{count, data}` envelope and fails closed otherwise. Covered by two new tests (`test_gate_accepts_the_production_store_and_runs_shapes`, `running_run_envelope` matrix case, `runs_unexpected_envelope` degenerate case).
- **Files modified:** docs/runbooks/gal-07-live-check.sh, tools/tests/gal07_live_runbook_test.py
- **Verification:** real-host run now BLOCKs with exactly the two intended pre-deploy `missing:` lines + one advisory `warn:`; fixture tests green
- **Committed in:** f13a5ea

**2. [Rule 1 - Bug] Held-lock fixture did not actually hold the lock; dead `stored_stack_host` fixture param**
- **Found during:** Task 2 (matrix run)
- **Issue:** The first draft wrote the holder record but released the flock before the gate ran (the probe would have seen a free lock), and a leftover `stored_stack_host` parameter made the stored-host matrix case silently pass.
- **Fix:** The fixture now holds the non-blocking flock for the whole subprocess run and releases it in `finally`; the dead parameter was removed and the case passes `tools_json=_tools_json("stack-server")`. The `dep02_missing` fixture now points `GAL07_DEP02_GATE` at an absent path instead of letting the default real (passing) gate satisfy check 4.
- **Files modified:** tools/tests/gal07_live_runbook_test.py
- **Verification:** the full matrix goes red exactly where its piece is removed
- **Committed in:** f13a5ea

---

**Total deviations:** 2 auto-fixed (2 × Rule 1 bug)
**Impact on plan:** Both fixes were required for the gate's real-host verdict to be truthful; no scope creep.

## Issues Encountered
- The repo's `gsd_run` shim is not on PATH in this runtime; resolved per gsd-run-resolver (node `$GSD_TOOLS` against the opencode config's gsd-core copy).
- `bin/make test` runs `unittest discover` then `pytest` over the full suite; both are green together with ruff and mypy.

## Known Stubs

| Stub | File | Line(s) | Reason |
|------|------|---------|--------|
| Rollback-anchor placeholders (`<docker inspect ...>`, adapter SHA) and the empty Part 1 evidence-table cells | docs/runbooks/gal-07-live-handoff.md | Pre-deploy record + Part 1 evidence table | Intentional: filled at execution time by plan 07-02 (Task: deploy), per the plan's own "filled at execution time" design |
| The 13 empty findings rows (G0, 1a-1..6, 2a-1..3, 3a-1..3) | docs/runbooks/gal-07-live-handoff.md | ## Findings log | Intentional: the LIVE-08/09/10 evidence rows stay empty until plans 07-02..04 execute the supervised live session |
| Parts 1-3 and the recovery drill are authored, not executed | docs/runbooks/gal-07-live-handoff.md | whole file | The procedures run live, operator-supervised, under plans 07-02 (deploy), 07-03 (LIVE-09), 07-04 (LIVE-10); recorded in the broken-windows ledger |

## User Setup Required

None - no external service configuration required beyond what plan 07-02's checkpoints already own (GitLab credentials for the core pin install, the operator's 0600 credentials env file).

## Next Phase Readiness
- Plans 07-02..04 can execute the runbook section by section; every part's entry gate is the script's `PREFLIGHT OK`, re-run immediately before each typed GO gate.
- The pre-deploy real-host verdict is today: `BLOCKED:` with `missing: stack_automation_layer pinned` (service `.venv`), `missing: a type fast tool` (D-12 watch item) and an advisory `warn:` for the absent credentials env file — exactly the gaps 07-02's steps close.
- LIVE-08 is declared by 07-01 and 07-02 alike, so it stays unchecked in REQUIREMENTS.md until 07-02's SUMMARY exists (shared-ID gate).
- Known carried blocker: the git+https core pin install fails on forb01 without GitLab credentials; 07-02 Task 1 owns the resolution checkpoint (OQ-1).

---
*Phase: 07-deploy-supervised-live-stack-handoff*
*Completed: 2026-11-02*

## Self-Check: PASSED

- Files exist: docs/runbooks/gal-07-live-check.sh (executable), docs/runbooks/gal-07-live-handoff.md, tools/tests/gal07_live_runbook_test.py, 07-01-SUMMARY.md
- Commits exist in HEAD: 97bf310, f13a5ea, 4ca4112 (measured plan range 7d158fb8..HEAD, 3 commits)
