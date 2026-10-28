---
phase: 04
review: 04-REVIEW.md
titles: json
findings:
  - id: WR-01
    severity: warning
    disposition: open
    title: "A failing `OwnedService.close()` leaks the owner lock and leaves a dead service marked usable"
  - id: WR-02
    severity: warning
    disposition: open
    title: "A Configure that fails validation keeps the previous service, and reads are still served under status FAILED"
  - id: WR-03
    severity: warning
    disposition: open
    title: "No synchronisation between Configure and in-flight commands, or between concurrent Configures"
  - id: WR-04
    severity: warning
    disposition: open
    title: "The bypass read path mutates `last_error`, so a read can clear or overwrite a motion command's error"
  - id: WR-05
    severity: warning
    disposition: open
    title: "`host` is interpolated into a URL unvalidated, while STACK credentials are sent to it"
  - id: IN-01
    severity: info
    disposition: open
    title: "Simulated to real Configure toggle silently ignores a changed host"
  - id: IN-02
    severity: info
    disposition: open
    title: "Truncation limits are bare literals, and `last_error` is not bounded like the reply"
  - id: IN-03
    severity: info
    disposition: open
    title: "`logging.basicConfig` in `__main__` has no effect"
open: 8
total: 8
recorded: 2026-10-29T00:00:00.000Z
---

# Phase 04: Code Review Disposition

Every finding in `04-REVIEW.md` starts as `open`. Critical: 0, Warning: 5, Info: 3.
Update a row to `fixed` (with the commit) or `accepted` (with a reason) when it is triaged;
`/gsd-code-review 4 --fix` applies Critical + Warning fixes.
