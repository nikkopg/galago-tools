---
phase: 06
review: 06-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: fixed
    title: "DEP-02 gate can report OK without `commandFields.stack.transfer`"
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "F.A.S.T. inputs are only partly validated, so a bad value fails after the STACK in-leg has moved the plate"
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "No guard against a degenerate handoff (same tool, or same location on both sides)"
  - id: WR-03
    severity: warning
    disposition: fixed
    title: "Gate checks 2 and 3 are weaker than the runbook claims"
  - id: WR-04
    severity: warning
    disposition: fixed
    title: "Test coverage does not pin the validation or the gate decoy cases"
  - id: WR-05
    severity: warning
    disposition: fixed
    title: "Replay and F.A.S.T. contract tests can skip silently, so the \"0 skipped\" requirement is only enforced for node"
  - id: IN-01
    severity: info
    disposition: open
    title: "`find_node` lets PATH win over the `$NODE` \"override\""
  - id: IN-02
    severity: info
    disposition: open
    title: "The harness `galago.timer` stub does not match galago-core's signature"
  - id: IN-03
    severity: info
    disposition: open
    title: "The hardware deny assertion is a tautology"
  - id: IN-04
    severity: info
    disposition: open
    title: "`stack_legs` uses bare `assert` in a helper module"
  - id: IN-05
    severity: info
    disposition: open
    title: "Magic numbers and a non-strict zero rule in the script and tests"
---

# Phase 6: Code Review Disposition

CR-01 and WR-01..WR-05 were fixed by `/gsd-code-review 6 --fix` (see 06-REVIEW-FIX.md, commits a56927d..d22fd4c). IN-01..IN-05 stay open (Info, outside the critical_warning fix scope).
CR-01 did not produce a false pass on this run: on 2026-11-02 the orchestrator confirmed by hand that galago-core `controller/components/tools/constants.ts` `commandFields.stack` contains `transfer` and no acknowledge, and `controller/test/commandFields.test.ts` passed 5/5 (vitest).
WR-01 matters before Phase 7 hardware runs (a bad F.A.S.T. value fails after the STACK in-leg has moved the plate). Fixed in 817587f.
