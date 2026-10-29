---
phase: 04
review: 04-REVIEW.md
titles: json
findings:
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "Configure drains in-flight commands with no bound, and blocks every command including the BUSY-bypass reads while it does"
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "A command parked behind a Configure can leave status READY with no service, and could run against the wrong owner in Phase 5"
  - id: IN-01
    severity: info
    disposition: open
    title: "Simulated to real Configure toggle silently ignores a changed host (carried forward)"
  - id: IN-02
    severity: info
    disposition: open
    title: "Truncation limits are bare literals, and `last_error` is not bounded like the reply (carried forward)"
  - id: IN-03
    severity: info
    disposition: open
    title: "`logging.basicConfig` in `__main__` has no effect (carried forward)"
  - id: IN-04
    severity: info
    disposition: open
    title: "`_teardown` reaches into the core's private `_lock` and silently skips the release if it is renamed"
  - id: IN-05
    severity: info
    disposition: open
    title: "`_in_flight` is not reentrant, so a nested dispatch would deadlock against a waiting Configure"
open: 5
total: 7
recorded: 2026-10-29T00:00:00.000Z
---

# Phase 04: Code Review Disposition

The frontmatter tracks the **current** `04-REVIEW.md`: the second, incremental review of
`tools/stack/server.py` and `tools/tests/stack_test.py` after the first fix run. Its IDs restart at
WR-01, so they are not the same findings as the first review's WR-01..WR-05 below.

## Review pass 1 (69e102a) — fixed by 04-REVIEW-FIX.md, iteration 1

| ID | Title | Disposition | Commit | Note |
|----|-------|-------------|--------|------|
| WR-01 | A failing `OwnedService.close()` leaks the owner lock | fixed | 3567aa0 | |
| WR-02 | A Configure that fails validation keeps the previous service | fixed | 7f77504 | |
| WR-03 | No synchronisation between Configure and in-flight commands | fixed | b67fbd0 | Its unbounded wait is what pass 2's WR-01/WR-02 are about |
| WR-04 | The bypass read path mutates `last_error` | fixed (partial) | 28b0812 | A read that raises still sets `last_error` (locked by D-13) |
| WR-05 | `host` is interpolated into a URL unvalidated | fixed | 6e1c585 | |
| IN-01..IN-03 | | carried into pass 2 | | |

## Review pass 2 (incremental, after the fixes)

All seven findings above start `open`. Pass 2's WR-01 and WR-02 both come from the WR-03 fix's
design (Configure waits, unbounded, for in-flight commands); the reviewer suggests refusing commands
quickly while a Configure runs instead of parking them.

### Pass 2 fix run (04-REVIEW-FIX.md, iteration 2)

| ID | Disposition | Commit | Note |
|----|-------------|--------|------|
| WR-01 | fixed | d46fd4a | Drain bounded by `CONFIGURE_DRAIN_TIMEOUT_S = 5.0`; a busy refusal keeps the healthy owner, but base `Configure` still reports FAILED |
| WR-02 | fixed | 6d46926 | Commands during a Configure get an immediate ERROR_FROM_TOOL "stack: reconfiguring"; handlers use the service captured at admission; `setStatus` holds READY at FAILED after a failed Configure (cosmetic: can keep FAILED showing in simulated mode until the next successful real Configure) |
| IN-01..IN-05 | open | | Out of the default fix scope |
