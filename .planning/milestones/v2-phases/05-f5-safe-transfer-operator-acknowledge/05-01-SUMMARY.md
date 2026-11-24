---
phase: 05-f5-safe-transfer-operator-acknowledge
plan: 01
subsystem: transfer-ledger-design
tags: [design-spike, step-key-ledger, idempotency, stack-core-934a621, safety]

requires:
  - phase: 04-stack-tool-registration-reads-estimate
    provides: frozen stack.proto, reply mapping (D-10..D-12), Config.ledger_dir / transfer_timeout_s recorded but unused
provides:
  - "05-SPIKE.md: the D-01 answers (restart, latch guid, nothing-sent classification) re-verified against core 934a621"
  - "Amendments A-1..A-6 that supersede CONTEXT D-05/D-07/D-11/D-13 where they differ"
  - "Binding ledger contract (section 6): record schema, 8-row repeat-key table, release whitelist, constants, path order, message templates"
  - "Verdict: no core gap blocks the phase, so no /gsd-quick in stack-automation-layer"
affects: [05-02, 05-03, 05-04, 05-05, 05-06, 05-07, phase-07-runbook]

actuals:
  tokens: 8286
  tasks: 2
  commits: 2
plan_head_before: d0dca833f7f496a322f427b90b75a93b372a5f8c
plan_head_after: 30d996ee6d6aef644ce643a4dd1ced3346227fff

tech-stack:
  added: []
  patterns:
    - "Ledger done-set mirrors the core's _task_ended (A-1)"
    - "Operator guid comes from latch_status() first, task guid is a label only (A-2)"
    - "Release by isinstance whitelist, fail closed: unknown result types are kept as outcomeUnknown"

key-files:
  created:
    - .planning/phases/05-f5-safe-transfer-operator-acknowledge/05-SPIKE.md
  modified: []

key-decisions:
  - "A-1: a record is done only for ran, failed, aborted or lost(taskNotFound); timedOut, lost(pollFailed) and the rest stay started (avoids a permanent core Refused(inFlight) trap)"
  - "A-2: the guid to acknowledge is latch_status().guid first; the result's guid is only 'task guid'"
  - "OQ1 (orchestrator): keep D-09; a live ran observed after a restart is SUCCESS flagged reattachedAfterRestart; a recorded ran replays only within REPLAY_WINDOW_S; any non-ran after a restart adds the arm-inspection clause"
  - "OQ2 (orchestrator): follow XFR-04 as written; release after Rejected(stage=instrument) and Refused(stackBusy); documented as residual risk"
  - "Orphaned core in-flight guard is documented for the Phase 7 runbook; no adapter drain"
  - "Replay is fail-closed: age exactly 600 s or negative is refuseCompleted"

patterns-established:
  - "Spike section 6 is the single source of truth for plans 05-02..05-07 (constants, table, templates)"

requirements-completed: [XFR-03, XFR-04, ACK-02]

coverage:
  - id: D1
    description: "05-SPIKE.md answers the three D-01 questions with core 934a621 line citations and the executed probe evidence"
    requirement: "XFR-03"
    verification:
      - kind: other
        ref: "Task 1 verify: heading, SHA, submitOutcomeUnknown and stackBusy greps, plus sed/grep re-check of service.py 1701-1702, 2010-2011, 1917, 1348-1350 at 934a621"
        status: pass
    human_judgment: true
    rationale: "A grep proves the sections and citations exist, not that the reading of the core is sound; the verifier must read sections 1-3 against the cited lines"
  - id: D2
    description: "Amendments A-1..A-6, the orchestrator's resolved open questions, and the binding ledger contract (schema, repeat-key table, whitelist, constants, templates) in sections 4-6"
    requirement: "XFR-04"
    verification:
      - kind: other
        ref: "Task 2 verify: section headings and 16 required terms present; section 6b has 8 action rows; all 9 constants listed with values"
        status: pass
    human_judgment: true
    rationale: "The contract is a design decision document; its completeness for plans 05-02..05-07 is a judgment the verifier makes by tracing each later plan's read_first references into it"
  - id: D3
    description: "Section 7 verdict: no core gap blocks the phase, with residual risks for the Phase 7 runbook"
    requirement: "ACK-02"
    verification:
      - kind: other
        ref: "grep -F 'no core gap blocks the phase' 05-SPIKE.md"
        status: pass
    human_judgment: true
    rationale: "The verdict rests on the reading of the core in sections 1-3; the edge flagged in 'Flagged Assumptions' (XFR-04 classification of a typed 5xx) stays unresolved for the verifier"

duration: 6min
completed: 2026-10-29
status: complete
---

# Phase 5 Plan 01: Design Spike Summary

**Written design spike for the F5-safe step-key ledger: three D-01 questions answered against core 934a621 with executed probe evidence, six amendments (done-set mirrors `_task_ended`, acknowledge guid from `latch_status()` first), and one binding contract for plans 05-02..05-07.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-10-29T08:35:00Z (approximate; the start time was not captured at plan start)
- **Completed:** 2026-10-29T08:42:00Z
- **Tasks:** 2
- **Files modified:** 1 created (`05-SPIKE.md`), no code

## Accomplishments

- Re-read every cited core line with `git show 934a621:...` and confirmed the quoted code (`owned = handle.guid in self._started` at 2010-2011, the `submit-` latch mint at 1701-1702, `_task_ended` at 1917-1930, first-failure-wins at 1348-1350, `guidMismatch` at 1476-1477, the single POST at 1271). Both Task 1 verify commands pass.
- Answered the three D-01 questions. (a) A foreign guid's `wait_transfer` still observes `ran`/`failed`, a foreign `failed` does not latch and an owned-after-restart one does, so D-09 holds. (b) `latch_status().guid` is `submit-` plus 16 hex the instant `execute_transfer` returns `Lost(submitOutcomeUnknown)`, and no structured field of the result carries it. (c) The release whitelist is by `isinstance` (Refused, Rejected, NeedsInput, ReadFailed); `Rejected(instrument)` and `Refused(stackBusy)` were sent once and typed-refused.
- Fixed the contract plans 05-02..05-07 implement: record schema with `latchGuid`, an 8-action `decide()` table with reply codes, the keep/release rules, all nine constants with values, the default ledger path order, and the operator message templates (guid and next action before the step key, 300-character cap).
- Recorded the orchestrator's resolutions (OQ1 keep D-09, OQ2 follow XFR-04, orphaned in-flight guard documented, OQ4 carried to Phase 7) and the verdict that no core gap blocks the phase.

## Task Commits

1. **Task 1: Spike sections 1-3, the three D-01 answers** - `e62ff3f` (docs)
2. **Task 2: Spike sections 4-7, amendments, resolved questions, binding ledger contract, verdict** - `30d996e` (docs)

**Plan metadata:** recorded in the final `docs(05-01)` metadata commit (SUMMARY committed first, then STATE/ROADMAP/REQUIREMENTS).

## Files Created/Modified

- `.planning/phases/05-f5-safe-transfer-operator-acknowledge/05-SPIKE.md` - the D-01 design spike and the binding ledger contract. Nothing under `tools/` changed.

## Decisions Made

- **A-1:** the ledger's `done` set is `ran`, `failed`, `aborted`, `lost(taskNotFound)`, mirroring the core's `_task_ended`. `lost(pollFailed)` leaves the core latched and its persisted in-flight guard set, and `acknowledge_failure` does not clear it, so recording it as `done` would make every later Transfer `Refused(inFlight)` forever.
- **A-2:** the guid named to the operator is `latch_status().guid`, because the latch is first-failure-wins and the core answers `guidMismatch` for any other guid.
- **A-3/A-4/A-5/A-6:** orphaned core in-flight guard documented for the Phase 7 runbook, no held-latch field on SUCCESS, an optional `latchGuid` record field, and ledger refusal rows may make one zero-I/O `latch_status()` call.
- **OQ1/OQ2:** resolved by the orchestrator as listed in the frontmatter.
- **Fail-closed replay:** an age of exactly 600 s, a negative age or an unparseable `updatedAt` is `refuseCompleted`.

## Deviations from Plan

None - plan executed exactly as written.

The plan's `<action>` for Task 2 said Section 5 should mark each item "resolved by the orchestrator in --auto mode"; the document does so in its intro line rather than repeating the label on every bullet. The plan's `<action>` for section 6f lists the template names; two helper clauses (latch clause with three variants, in-flight owner clause) are listed as `clause` rows alongside the reply templates so plans 05-04 and 05-05 have exact text.

## Issues Encountered

None. The spike's file was created with the continuation sentinel from the large-file protocol, which was removed before the Task 1 commit, so no sentinel is committed.

## Authentication Gates

None.

## Known Stubs

None. This plan wrote no code.

## Threat Flags

None. No file under `tools/` changed and no new network, auth or file-access surface was introduced.

## Flagged Assumption Carried Forward

The plan's flagged unresolved edge for XFR-04 (`unclassified`) stays unresolved: whether a typed 5xx can leave STACK having acted is not provable from the core source. The spike records it as residual risk (section 5 OQ2, section 7) and keeps the release as XFR-04 requires.

## Next Phase Readiness

Ready for 05-02 (tracer: fresh-path Transfer through a write-ahead ledger). Every later plan lists `05-SPIKE.md` in `read_first`, so 05-02 should read section 6 (schema, constants, templates) and section 4 A-1 before writing `tools/stack/ledger.py`.

## Self-Check: PASSED

- FOUND: `.planning/phases/05-f5-safe-transfer-operator-acknowledge/05-SPIKE.md`
- FOUND commit `e62ff3f` and `30d996e` (both ancestors of HEAD; `git rev-list --count d0dca83..HEAD` was 2 before this SUMMARY)
- Task 1 and Task 2 verify commands exit 0; all nine constants listed with values in section 6d; section 6b holds eight action rows, each with a reply code; section 7 contains "no core gap blocks the phase"
- `git diff --stat d0dca83 HEAD -- tools` is empty (no file under `tools/` changed)
