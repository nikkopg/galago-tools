# Phase 07 deferred items

Discovered during execution, out of the acting plan's scope. A pending item surfaces in
audit-open / audit-uat / complete-milestone until it carries a `status:` field.

## Deferred Items

- GAL-07 pre-flight owner-lock probe (docs/runbooks/gal-07-live-check.sh, check 2) blocks on the
  session's own galago tool server after Configure
  **status:** done — fixed by 07-03 commit 9344957 (the probe treats a holder record with owner `galago` as the expected single-owner state; verified live at row 3a-1 and by the re-verification)
  **What:** the probe refuses `PREFLIGHT OK` whenever the lock at 10.150.1.125:5005 is held at
  all. Once the STACK tool is configured in real mode, its own tool server (galago owner,
  pid 4004972) holds that lock persistently — seen live 2026-11-03T01:18Z: `missing: an owner
  lock free at 10.150.1.125:5005 — STACK manager 10.150.1.125:5005 is already owned by galago
  (pid 4004972)`. The runbook's intent (Safety rules; check 2 header comment) is to refuse only
  when ANOTHER front end (owner `mcp`, stack-mcp) holds the lock; the galago holder is the
  desired single-owner state the PARTS 2-3 sessions run through. Unfixed, plan 07-03 Part 2's
  entry gate (`PREFLIGHT OK` re-run both forms) can never pass while the tool server is up, and
  a restart-to-reset is forbidden (D-11). Fix direction: the probe should treat a holder record
  with owner `galago` as the OK/expected case ( LOCK-FREE-equivalent verdict or an explicit
  `ok: owned by galago` line) and keep blocking owner `mcp`/unknown. Written by 07-01; fixing it
  is 07-03's gate concern (its test module pins the script's wording), logged here by 07-02 per
  the scope boundary.
