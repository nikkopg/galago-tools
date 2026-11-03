# Code Review Disposition

- phase: 07-deploy-supervised-live-stack-handoff
- review: 07-REVIEW.md (status: reviewed, 2026-11-03)
- recorded: 2026-11-03 at the execute-phase code_review_gate
- found: 11 findings (counts {critical: 0, high: 2, medium: 1, low: 8})
- default: open — advisory ledger; `/gsd-code-review 07 --fix` writes fixed rows through code-review-fix.md's record_disposition

ID | Severity | Title | Disposition | Reason
|---|---|---|---|---|
| H-01 | warning | Runbook Pre-flight text contradicts the gate's galago-holder exemption | fixed | runbook lines 20-24 + 51-56 rewritten to name the foreign owner classes (mcp/stack-mcp/unknown), the galago-holder exemption and the corroboration clause (main-session fix, 2026-11-03, gate re-run PREFLIGHT OK) |
| H-02 | warning | Silent lock-probe fallback to an unpinned core can probe a different lock namespace (check 2 fail-open) | fixed | gate now corroborates the fallback interpreter's default_lock_dir against the service venv core; un-corroborated refuses forbidden: fail-closed (live: fake-venv run exits 1 with the forbidden line; real host PREFLIGHT OK through the primary) |
| M-01 | warning | Check 6 accepts the wanted host among several config tools; a divergent-host stack tool in the store passes silently (D-12 split risk) | open | (not yet triaged; triaged by) |
| L-01 | info | Degenerate multi-document runs body silently skips the RUNNING refusal | open | (not yet triaged; triaged by) |
| L-02 | info | "Exactly an assignment line" overpromise: duplicated `STACK_USER=` lines pass | open | (not yet triaged; triaged by) |
| L-03 | info | Runbook and BLOCKED footer promise a `forbidden:` line class the gate never emits | fixed | the H-02 corroboration now actually emits `forbidden:` lines — the promised class exists (main-session fix, 2026-11-03) |
| L-04 | info | Check 3 inspects an arbitrarily-ordered dist-info when the venv holds several | open | (not yet triaged; triaged by) |
| L-05 | info | Test matrix omits the third blocked owner class named by the gate (`stack-mcp`) | open | (not yet triaged; triaged by) |
| L-06 | info | Test matrix omits the stale-record trial (record present, no live flock → LOCK-FREE) | open | (not yet triaged; triaged by) |
| L-07 | info | Credential-leak regex misses quoted and whitespace-padded values | open | (not yet triaged; triaged by) |
| L-08 | info | The galago-holder exemption trusts the record's owner string uncorroborated | open | (not yet triaged; triaged by) |
