---
phase: "3"
slug: "deploy-supervised-live-acceptance"
# status lifecycle: draft (seeded by plan-phase) → validated (set by validate-phase §6)
# audit-milestone §5.5 distinguishes NOT-VALIDATED (draft) from PARTIAL (validated + nyquist_compliant: false) (#2117)
status: draft
nyquist_compliant: false
wave_0_complete: false
created: "2026-10-14"
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `unittest` + `pytest` (Python 3.10, via `bin/make proto test`: ruff, mypy, unittest discover, pytest) |
| **Config file** | `pyproject.toml` (mypy); test discovery via `tools/tests/*_test.py` |
| **Quick run command** | `$HOME/data/nikko/.venvs/galago-py310/bin/python -m unittest tools.tests.fast_test.TestRequirementsPin -v` |
| **Full suite command** | `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto test` |
| **Estimated runtime** | ~5 seconds quick, ~120 seconds full |

---

## Sampling Rate

- **After every deploy step:** Run the D-05 check that follows that step (capability test against the service `.venv`, `systemctl --user is-active galago-tools`, or the `galago-web` container status). Do not move on until it passes.
- **After every acceptance scenario:** Record the D-11 pass criteria live in `03-ACCEPTANCE.md`.
- **Before `/gsd-verify-work`:** Full suite must be green (re-run before any redeploy if a D-14 gap fix lands)
- **Max feedback latency:** 120 seconds for automated checks

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 3-xx (deploy) | TBD | TBD | LIVE-04 | ungated-core window | Core is gated before the new UI goes live | automated | `.venv/bin/python -m unittest tools.tests.fast_test.TestRequirementsPin -v`; `systemctl --user is-active galago-tools`; `docker ps --filter name=galago-web` | ✅ | ⬜ pending |
| 3-xx (deck-3) | TBD | TBD | LIVE-05 | software acting as operator | Prompt names deck and plate; operator decides | manual | — | n/a | ⬜ pending |
| 3-xx (pause/abort) | TBD | TBD | LIVE-06 | stale command | Abort wording exact; queue FAILED | manual + static pre-check | `grep -n "run aborted by operator at" tools/fast/server.py` | ✅ | ⬜ pending |
| 3-xx (web restart) | TBD | TBD | LIVE-07 | — | Recovery only through the tool page | manual | — | n/a | ⬜ pending |

*Task IDs are filled in by the planner. Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. The `simulate_pause` dry-run harness (RESEARCH Open Question 1) is an ops/QA tool, not a gated test file.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Deck-3 pause prompt, fix, Resume, same step SUCCESS | LIVE-05 | Moves the instrument; operator must be present | Per CONTEXT D-08/D-11; operator go-ahead before each motion step, e-stop within reach |
| Pause → Resume SUCCESS; Pause → Abort "aborted by operator", queue FAILED | LIVE-06 | Live instrument | Per CONTEXT D-11 pass criteria |
| Restart `galago-web` mid-run, recover through the tool page | LIVE-07 | Live instrument + container restart; the recovery click is the operator's | Per CONTEXT D-08/D-11 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
