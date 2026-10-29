---
phase: 05
review: 05-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: fixed
    title: "Configure swaps ledger_dir/transfer_timeout_s before the same-endpoint return and drain, so a repeated step key can be sent again"
  - id: WR-01
    severity: warning
    disposition: fixed
    title: "BUSY gate can be reset mid-Transfer; AcknowledgeFailure is not under _MOTION_LOCK"
  - id: WR-02
    severity: warning
    disposition: fixed
    title: "A busy-refused Configure leaves status FAILED with the owner kept"
  - id: WR-03
    severity: warning
    disposition: fixed
    title: "_with_suffix is unbounded and cumulative, so the guid can be truncated away"
  - id: WR-04
    severity: warning
    disposition: fixed
    title: "Ledger.release deletes a record in any state (spike 6c: submitting only)"
  - id: WR-05
    severity: warning
    disposition: fixed
    title: "The not-claimed guard in _run_fresh is untested"
  - id: WR-06
    severity: warning
    disposition: accepted
    title: "Rejected with httpStatus >= 500 releases the key (accepted residual risk OQ2)"
  - id: IN-01
    severity: info
    disposition: open
    title: "AST never-in-a-loop check is intra-function only"
  - id: IN-02
    severity: info
    disposition: open
    title: "Exceptions after a handle reach the operator as DRIVER_ERROR without guid"
  - id: IN-03
    severity: info
    disposition: open
    title: "Path.home() RuntimeError is not caught"
  - id: IN-04
    severity: info
    disposition: open
    title: "_fsync_dir swallows errors; one lock test narrower than its name"
---

# Phase 05 — Review Disposition

Fix iteration 1 (2026-10-30): CR-01, WR-01..WR-05 fixed (9d6bc4d..ff56c2d, see 05-REVIEW-FIX.md). WR-06 accepted by the user (XFR-04 kept as written; residual risk for the Phase 7 runbook). Info findings open.

Iteration 2 (2026-10-30): the new iteration-2 WR-01 (pin only when a record can exist) and WR-02 (keep the re-attach clause whole) were fixed in 093e681 and 8f86382. The user decided to keep the pin on an untrusted ledger file (ba9fe65). Iteration-2 IN-01 (busy wording) was skipped because the wording is a binding 05-SPIKE.md template.

Residual from CR-01 for the Phase 7 runbook: the ledger-dir pin lasts one process; production Config must set an explicit absolute ledger_dir.
