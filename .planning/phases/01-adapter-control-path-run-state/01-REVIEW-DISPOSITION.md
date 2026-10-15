---
phase: 01
review: 01-REVIEW.md
titles: json
findings:
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "`Resume()`'s crash-recovery gate bypasses the module's own `_accepted()` fail-closed rule"
  - id: WR-02
    severity: warning
    disposition: open
    title: "`DryRunFastServer`'s auto-pause timer state is shared across overlapping simulated Transfers"
  - id: WR-03
    severity: warning
    disposition: open
    title: "`_read_control` dies silently on any exception other than `OSError`"
  - id: IN-01
    severity: info
    disposition: open
    title: "Crash-recovery `Resume()` never attributes a concurrent, non-stale operator Abort"
  - id: IN-02
    severity: info
    disposition: open
    title: "Redundant `.gitignore` entry"
  - id: IN-03
    severity: info
    disposition: open
    title: "`COMMAND_TO_SERVICE_METHOD` is production-module state with no production consumer"
  - id: CR-01
    severity: critical
    disposition: fixed
    title: "`_run_in_flight()` resets the run record on every entry, not just the first, silently clobbering an in-flight pause"
open: 5
total: 7
recorded: 2026-10-15T13:04:03.957Z
---

# Phase 01: Code Review Disposition

| Finding | Severity | Disposition | Source |
|---------|----------|-------------|--------|
| WR-01 | warning | fixed | Phase 2 plan 02-05 (134e097, 7c2e15a) — same defect as 02-REVIEW CR-01; deployed 2026-10-16 |
| WR-02 | warning | open | - |
| WR-03 | warning | open | - |
| IN-01 | info | open | - |
| IN-02 | info | open | - |
| IN-03 | info | open | - |
| CR-01 | critical | fixed | 01-REVIEW-FIX.md (not in the current review) |

Dispositions: `open` (recorded, not yet triaged), `fixed`, `skipped`, `deferred`.
Set `deferred` by hand and put the reason in the Source cell; both are preserved. A `|` in the reason is kept as prose and escaped on the next run.
Re-running the gate keeps every row it can. A row the current review no longer reports is kept and its Source cell flagged, so a finding does not leave this record silently. ONE exception: when a finding id is REUSED by a different finding, the earlier decision cannot keep a row — the id is taken — and it is dropped. A RECORDED decision (anything but `open`) is named on the console when that happens; a row still at `open` is replaced silently, because `open` records no decision to lose.
