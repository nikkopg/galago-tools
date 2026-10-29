---
phase: 05
review: 05-REVIEW.md
titles: json
findings:
  - id: CR-01
    severity: critical
    disposition: open
    title: "Configure swaps ledger_dir/transfer_timeout_s before the same-endpoint return and drain, so a repeated step key can be sent again"
  - id: WR-01
    severity: warning
    disposition: open
    title: "BUSY gate can be reset mid-Transfer; AcknowledgeFailure is not under _MOTION_LOCK"
  - id: WR-02
    severity: warning
    disposition: open
    title: "A busy-refused Configure leaves status FAILED with the owner kept"
  - id: WR-03
    severity: warning
    disposition: open
    title: "_with_suffix is unbounded and cumulative, so the guid can be truncated away"
  - id: WR-04
    severity: warning
    disposition: open
    title: "Ledger.release deletes a record in any state (spike 6c: submitting only)"
  - id: WR-05
    severity: warning
    disposition: open
    title: "The not-claimed guard in _run_fresh is untested"
  - id: WR-06
    severity: warning
    disposition: open
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

All findings open as of the code-review gate (2026-10-29).
