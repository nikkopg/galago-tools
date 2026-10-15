---
phase: 03-deploy-supervised-live-acceptance
plan: 03
subsystem: testing
tags: [grpc, fast-tool, dry-run, simulated, galago-web]

# Dependency graph
requires:
  - phase: 03-02
    provides: deployed galago-web (no-cache rebuild, LIVE-04 PASS), production F.A.S.T. reconnected
provides:
  - "scripts/fast_dryrun.py: simulated-only DryRunFastServer harness with auto-pause timer, control FIFO, and a self-test, committed under scripts/ (not tools/)"
  - "Dry run (D-07) evidence in 03-ACCEPTANCE.md: all nine UI walkthrough items PASS, ordered command sequence, production-tool-untouched proof, teardown proof, Result PASS"
affects: [03-04, 03-05, 03-06, 03-07]

actuals:
  tokens: 6537
  tasks: 3
  commits: 3
plan_head_before: 223c4cf0ae81f06d9b0a5e457ff36a03969b0f08
plan_head_after: abfefe7515dc986f050897af873a627e0d41fe80

tech-stack:
  added: []
  patterns:
    - "Simulated-only ops harness pattern: a FastServer subclass that refuses real Configure (NOT_READY + raises from _configure) and drives pauses only through simulate_pause (ADP-10), so a dry run can exercise the deployed UI with zero instrument risk"
    - "Auto-pause timer instead of a stdin loop so a human-paced operator checkpoint doesn't need Claude present mid-walkthrough"

key-files:
  created:
    - scripts/fast_dryrun.py
  modified:
    - .planning/phases/03-deploy-supervised-live-acceptance/03-ACCEPTANCE.md

key-decisions:
  - "Design choice per RESEARCH Open Question 1: the harness lives under scripts/ (not tools/), is linted by the gate's ruff check, and is kept (not deleted) so the dry run can be repeated after a future fix"
  - "The two unexplained operator-initiated commands at 09:11 (an extra pause and an extra abort with return_liquid no) are recorded honestly as a note, not attributed to the scripted Stop->Cancel step (which independently sent nothing) or to any other walkthrough item, since the operator did not state their source when asked"
  - "Result: PASS recorded only after independently re-deriving the harness command sequence and the production F.A.S.T.log window from the raw logs, not solely from the operator's blanket 'all visual checks passed' reply"

requirements-completed: [LIVE-05, LIVE-06, LIVE-07]

coverage:
  - id: D1
    description: "Simulated-only dry-run harness (scripts/fast_dryrun.py) refuses a real Configure, drives pauses only via simulate_pause, and passes its self-test"
    requirement: "LIVE-05"
    verification:
      - kind: unit
        ref: "PYTHONPATH=. python scripts/fast_dryrun.py --self-test -> SELF-TEST OK"
        status: pass
      - kind: other
        ref: "ruff check scripts/fast_dryrun.py; mypy --config-file=pyproject.toml scripts/fast_dryrun.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Operator walkthrough of the galago-web run page and tool page against FAST-DRYRUN: control bar, Pause, Stop/Cancel, tool-page Run Recovery disabled state, tool_paused prompt, Resume, Abort, post-run Resume, and tool removal"
    requirement: "LIVE-06"
    verification:
      - kind: manual_procedural
        ref: "operator walkthrough replies + harness log command sequence (03-ACCEPTANCE.md Dry run (D-07) Checklist results, items 1-9)"
        status: pass
    human_judgment: true
    rationale: "UI rendering and dialog behavior (control bar fields, confirmation dialogs, disabled-state text) can only be confirmed by a human looking at the rendered page; the harness log corroborates the command side but not the visual rendering"
  - id: D3
    description: "Production F.A.S.T. tool (:40001) untouched during the entire dry run window, and the FAST-DRYRUN tool/harness were fully torn down afterward"
    requirement: "LIVE-07"
    verification:
      - kind: other
        ref: "grep -c 'Running command' on trace_logs/1791974367/F.A.S.T.log over its full 694,871 lines -> 0; window 09:06:06-09:14:15 WIB contains only GET /status 200 OK lines; ss -ltn and control-FIFO existence check after teardown"
        status: pass
    human_judgment: false

duration: ~13h elapsed (overnight gap awaiting operator; active execution ~25min for Task 1, ~15min for Task 3 verification/record/teardown)
completed: 2026-10-15
status: complete
---

# Phase 3 Plan 3: Simulated FAST-DRYRUN Harness and D-07 Dry Run Summary

**Built and tore down a simulated-only F.A.S.T. tool server (scripts/fast_dryrun.py) that let the operator exercise every run-page and tool-page control in the deployed galago-web UI with zero hardware risk, recording a PASS on all nine walkthrough items in 03-ACCEPTANCE.md's Dry run (D-07) block.**

## Performance

- **Duration:** ~13h elapsed (mostly an overnight gap waiting on the operator's checkpoint walkthrough); active Claude work was roughly 25 min for Task 1 (harness + self-test + stand-up) and 15 min for Task 3 (log re-verification, record, teardown)
- **Started:** 2026-10-14T13:23:41Z (first commit, Task 1 RED)
- **Completed:** 2026-10-15T02:21:13Z (last commit, Task 3)
- **Tasks:** 3 (Task 1 auto/tdd, Task 2 checkpoint:human-action, Task 3 auto)
- **Files modified:** 2 (`scripts/fast_dryrun.py` created, `03-ACCEPTANCE.md` modified)

## Accomplishments
- `scripts/fast_dryrun.py`: a `DryRunFastServer(FastServer)` subclass that refuses a real `Configure` (`NOT_READY` + "simulated-only" message, `_configure` raises), drives pauses only through `FastServer.simulate_pause` (ADP-10) via an auto-pause timer or a control FIFO, and ships with a `--self-test` that exercises the real-Configure refusal, FIFO pause/clear, a blank-decision Resume rejection, and the auto-pause arm/re-arm/stop cycle around a simulated run.
- Stood the harness up on port 40003, confirmed `galago-web`'s container reached it, and let the operator register FAST-DRYRUN, run the DRYRUN protocol, and walk all nine run-page/tool-page checks (control bar rendering, Pause confirmation, Stop/Cancel sending nothing, tool-page Run Recovery disabled while a run step tracks the tool, the `WrongPlateType (-645)` / "Deck 3: expected plate 1, found none" prompt, Resume, a second Abort with Return-liquid = yes, post-run Resume, and tool deletion) — all PASS.
- Independently re-derived the evidence from raw logs rather than trusting the operator's summary alone: the harness log's command sequence (transfer, pause, resume, abort, resume, each SUCCESS) and the production `F.A.S.T.log`'s complete absence of any `Running command` line (0 across 694,871 lines; the dry-run window shows only `/status` polling).
- Recorded two unexplained extra operator-initiated commands (a pause and an abort with `return_liquid no` at 09:11) honestly as a note, without attributing them to any scripted step, since they don't affect any walkthrough item's pass/fail.
- Filled the Dry run (D-07) block in `03-ACCEPTANCE.md` with Result: PASS, and updated the Summary table row; the live scenarios (03-04 to 03-07) may now proceed.
- Tore the harness down: stopped PID 17097 via the control FIFO's `quit` command (exited within 2s, no SIGTERM needed), confirmed port 40003 is free and the FIFO is gone; the operator independently confirmed (and `tool.getAll` corroborates) FAST-DRYRUN is no longer in the workcell.

## Task Commits

Each task was committed atomically:

1. **Task 1 (RED): failing self-test for the dry-run harness** - `2c9637a` (test)
2. **Task 1 (GREEN): simulated-only dry-run harness (scripts/fast_dryrun.py)** - `5cd20eb` (feat)
3. **Task 2: operator walkthrough (checkpoint:human-action)** - no commit (operator-performed UI actions only; nothing for Claude to commit)
4. **Task 3: tear down the harness, record Dry run (D-07)** - `abfefe7` (docs)

_No separate plan-metadata commit beyond Task 3's — the Dry run record and the task itself are the same deliverable._

## Files Created/Modified
- `scripts/fast_dryrun.py` - simulated-only `DryRunFastServer` harness, control FIFO, auto-pause timer, self-test, CLI entrypoint
- `.planning/phases/03-deploy-supervised-live-acceptance/03-ACCEPTANCE.md` - Dry run (D-07) section filled with full evidence; Summary row updated to PASS

## Decisions Made
- The harness is a committed, typed, ruff/mypy-clean ops script under `scripts/` (RESEARCH Open Question 1), kept rather than deleted so the dry run can be repeated after a future fix.
- Treated the operator's blanket "all visual checks passed" + per-item confirmations as sufficient only after independently cross-checking the harness log's command sequence and the production log's clean window — the written record cites the log evidence per item rather than relying on the operator's summary alone.
- The two unattributed extra commands at 09:11 were recorded as a note rather than silently omitted or guessed at; they do not change the Result.

## Deviations from Plan

None - plan executed as written. The two extra operator-initiated commands at 09:11 are not a deviation from the plan's execution (Claude sent no commands and made no code changes beyond what the plan specified) — they are an operator UI action outside the scripted walkthrough, recorded transparently in the acceptance evidence per the plan's own "record pass or fail and what you saw" instruction.

## Issues Encountered
- The automated verify regex for the Dry run (D-07) block (`^- (Date/time|Operator|...):`) expects plain bullet labels without bold markdown and a `Result: PASS` line ending immediately after `PASS`/`FAIL`. The first draft used `- **Label:**` styling (matching the existing `LIVE-04 Deploy` section's prose style) and a trailing explanation on the same line as `Result: PASS`, which failed both automated checks. Reformatted the eight top-level bullets to plain `- Label:` and split the Result explanation onto a sub-bullet; re-ran the automated checks until all four passed.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Dry run (D-07) Result: PASS unblocks the live scenarios (plans 03-04 through 03-07), which may now run against the production F.A.S.T. tool.
- The harness is fully torn down (process gone, port free, FIFO removed, FAST-DRYRUN removed from the workcell); no cleanup carries forward.
- `scripts/fast_dryrun.py` remains in the repo (not deleted) so the dry run can be repeated if a later plan changes `tools/fast/server.py` or `tools/base_server.py`.

## Self-Check: PASSED
- FOUND: scripts/fast_dryrun.py
- FOUND: .planning/phases/03-deploy-supervised-live-acceptance/03-ACCEPTANCE.md (Dry run (D-07) section, Result: PASS)
- FOUND commit 2c9637a (ancestor of HEAD)
- FOUND commit 5cd20eb (ancestor of HEAD)
- FOUND commit abfefe7 (HEAD)
- Confirmed: nothing listens on port 40003; `$HOME/.local/share/galago/dryrun/control` does not exist; PID 17097 is not running.

---
*Phase: 03-deploy-supervised-live-acceptance*
*Completed: 2026-10-15*
