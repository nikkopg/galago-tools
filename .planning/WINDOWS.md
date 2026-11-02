---
schema_version: 1
open_count: 2
waived_count: 0
fixed_count: 0
total_count: 2
last_updated: 2026-11-02T10:49:33.026Z
---

# Broken Windows Ledger

> Cross-phase defect register. With `workflow.windows_enforce` enabled, `/gsd-ship` blocks while `open_count > 0`.
> Waive with `gsd-tools windows waive <id> "<reason>"` (reason required).
> Mark fixed with `gsd-tools windows fixed <id>`.

| id | phase | kind | file | line | description | status | reason | recorded_at | resolved_at |
|----|-------|------|------|------|-------------|--------|--------|-------------|-------------|
| 1 | 07 | stub | docs/runbooks/gal-07-live-handoff.md |  | Rollback-anchor placeholders (image ID, adapter SHA) and the Part 1 evidence-table cells are intentionally filled at execution time by plan 07-02; the 13 findings rows stay empty until plans 07-02..04 execute the live events | open |  | 2026-11-02T10:49:32.920Z |  |
| 2 | 07 | unrun-verify | docs/runbooks/gal-07-live-handoff.md |  | The live procedures Parts 1-3 and the recovery drill are authored and test-pinned but not executed: the supervised live session runs them under plans 07-02 (deploy), 07-03 (LIVE-09) and 07-04 (LIVE-10) | open |  | 2026-11-02T10:49:33.026Z |  |

````json
[
  {
    "id": 1,
    "kind": "stub",
    "phase": "07",
    "file": "docs/runbooks/gal-07-live-handoff.md",
    "line": null,
    "description": "Rollback-anchor placeholders (image ID, adapter SHA) and the Part 1 evidence-table cells are intentionally filled at execution time by plan 07-02; the 13 findings rows stay empty until plans 07-02..04 execute the live events",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-11-02T10:49:32.920Z",
    "resolved_at": null,
    "milestone": null
  },
  {
    "id": 2,
    "kind": "unrun-verify",
    "phase": "07",
    "file": "docs/runbooks/gal-07-live-handoff.md",
    "line": null,
    "description": "The live procedures Parts 1-3 and the recovery drill are authored and test-pinned but not executed: the supervised live session runs them under plans 07-02 (deploy), 07-03 (LIVE-09) and 07-04 (LIVE-10)",
    "status": "open",
    "reason": "",
    "recorded_at": "2026-11-02T10:49:33.026Z",
    "resolved_at": null,
    "milestone": null
  }
]
````
