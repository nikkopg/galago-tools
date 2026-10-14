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
| 3-01-T1 (entry gate) | 03-01 | 1 | LIVE-04 | T-03-05 | Nothing changes until D-01 holds and the user says go | automated | `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto test`; galago-core `npm test` / `npm run test:unit`; 03-DEPLOY.md gate rows | ✅ | ⬜ pending |
| 3-01-T3 (deploy steps 1-2, tracer) | 03-01 | 1 | LIVE-04 | T-03-01, T-03-02, T-03-03 | Core is gated before the adapter restarts | automated | `.venv/bin/python -m unittest tools.tests.fast_test.TestRequirementsPin -v`; `systemctl --user is-active galago-tools`; `.venv/bin/python scripts/fast_status.py --port 40001` | ✅ | ⬜ pending |
| 3-02-T1/T2 (reconnect, galago-web rebuild) | 03-02 | 2 | LIVE-04 | T-03-06, T-03-07, T-03-08 | New UI only after the tool reports run_state from the gated core | automated + human-action | `scripts/fast_status.py`; `docker inspect galago-web`; `curl http://localhost:3010/runs`; build contains `is_tip_broken` | ✅ | ⬜ pending |
| 3-03-T1/T2/T3 (dry run, D-07) | 03-03 | 3 | LIVE-05/06/07 | T-03-09, T-03-12 | Simulated-only harness can never reach the instrument | automated + manual walkthrough | `PYTHONPATH=. $HOME/data/nikko/.venvs/galago-py310/bin/python scripts/fast_dryrun.py --self-test` | ❌ W0: created by 03-03-T1 | ⬜ pending |
| 3-04 (pause/resume) | 03-04 | 4 | LIVE-06 | T-03-14, T-03-15 | Every control command operator-sent; step stays open | manual (operator) + log record | record check: `awk` field count on 03-ACCEPTANCE.md LIVE-06a | n/a | ⬜ pending |
| 3-05 (deck-3) | 03-05 | 5 | LIVE-05 | T-03-17, T-03-18 | Prompt names deck and plate; operator decides | manual (operator) + log record | record check on 03-ACCEPTANCE.md LIVE-05 | n/a | ⬜ pending |
| 3-06 (pause/abort) | 03-06 | 6 | LIVE-06 | T-03-19, T-03-20 | Abort wording exact; queue FAILED; no later step | manual + static pre-check | `grep -c "run aborted by operator at" tools/fast/server.py` (precondition) | ✅ | ⬜ pending |
| 3-07 (web restart) | 03-07 | 7 | LIVE-07 | T-03-21, T-03-22, T-03-23 | Recovery only through the tool page; restart only on go-restart | manual + automated restart checks | `docker inspect galago-web`; `scripts/fast_status.py` BUSY/paused after restart | n/a | ⬜ pending |
| 3-08 (closeout) | 03-08 | 8 | LIVE-04..07 | T-03-24, T-03-25 | No unmapped control command; requirements complete only from evidence | automated | `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make test`; Summary PASS count | ✅ | ⬜ pending |

*Task IDs are filled in by the planner. Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Existing infrastructure covers all phase requirements. The `simulate_pause` dry-run harness (RESEARCH Open Question 1) is an ops/QA tool, not a gated test file: `scripts/fast_dryrun.py`, created by plan 03-03 Task 1 with its own `--self-test` (and ruff-checked by the gate's `ruff check .`).

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
