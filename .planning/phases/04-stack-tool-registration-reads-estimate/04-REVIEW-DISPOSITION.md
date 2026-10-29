---
phase: 04
review: 04-REVIEW.md
titles: json
findings:
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "A failing `OwnedService.close()` leaks the owner lock and leaves a dead service marked usable"
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "A Configure that fails validation keeps the previous service, and reads are still served under status FAILED"
  - id: WR-03
    severity: warning
    disposition: fixed
    title: "No synchronisation between Configure and in-flight commands, or between concurrent Configures"
  - id: WR-04
    severity: warning
    disposition: fixed
    title: "The bypass read path mutates `last_error`, so a read can clear or overwrite a motion command's error"
  - id: WR-05
    severity: warning
    disposition: fixed
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
open: 3
total: 8
recorded: 2026-10-29T00:00:00.000Z
fix_report: 04-REVIEW-FIX.md
---

# Phase 04: Code Review Disposition

Every finding in `04-REVIEW.md` starts as `open`. Critical: 0, Warning: 5, Info: 3.
Update a row to `fixed` (with the commit) or `accepted` (with a reason) when it is triaged;
`/gsd-code-review 4 --fix` applies Critical + Warning fixes.

## Fix run (04-REVIEW-FIX.md, iteration 1)

| ID | Disposition | Commit | Note |
|----|-------------|--------|------|
| WR-01 | fixed | 3567aa0 | |
| WR-02 | fixed | 7f77504 | |
| WR-03 | fixed | b67fbd0 | Configure now waits, with no timeout, for in-flight real-mode commands |
| WR-04 | fixed (partial) | 28b0812 | A bypassed read that raises still sets `last_error` (locked by D-13) |
| WR-05 | fixed | 6e1c585 | Bare `::1` is now rejected; `[::1]` is accepted |
| IN-01..IN-03 | open | | Out of the default fix scope (`--all` not passed) |
