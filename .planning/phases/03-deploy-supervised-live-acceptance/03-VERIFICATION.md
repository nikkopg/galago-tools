---
phase: 03-deploy-supervised-live-acceptance
verified: 2026-10-16T05:40:00Z
status: human_needed
score: 15/16 must-haves verified
covered_files: [".planning/phases/03-deploy-supervised-live-acceptance/03-01-PLAN.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-01-SUMMARY.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-02-PLAN.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-02-SUMMARY.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-03-PLAN.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-03-SUMMARY.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-04-PLAN.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-04-SUMMARY.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-05-PLAN.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-05-SUMMARY.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-06-PLAN.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-06-SUMMARY.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-07-PLAN.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-07-SUMMARY.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-08-PLAN.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-08-SUMMARY.md", "scripts/fast_dryrun.py", "scripts/fast_status.py", "tools/fast/server.py", "tools/tests/fast_test.py"]
covered_digest: "v3:sha256:5275c4f6f24bea14f4bac85f8b68a9cfbdb8dab65b6188b6aac239550376d27b"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: passed
  previous_score: 16/16
  gaps_closed: []
  gaps_remaining: []
  regressions:
    - "Truth 14 (\"Code unchanged since the last actual redeploy\") no longer holds literally: Phase 2 gap-closure plan 02-05 (commits 134e097, 7c2e15a, 2026-10-15T21:07-21:10 WIB) modified tools/fast/server.py and tools/tests/fast_test.py after the 201d987 SHA this phase's live acceptance ran against, and after this phase's own 03-VERIFICATION.md was written. This is not a FAIL of this phase's own work (the live-acceptance record is historically accurate and unaffected); it is new information requiring a human decision on redeploy/rerun. Routed to human_verification below, not gaps_found."
behavior_unverified_items: []
human_verification:
  - test: "Decide whether forb01's deployed galago-tools (still running adapter SHA 201d987, per 03-DEPLOY.md) needs to be redeployed with the CR-01 fix (134e097/7c2e15a) before this phase's live-acceptance evidence is treated as current, and whether LIVE-07 (the only one of the four live scenarios that exercises the crash-recovery Resume branch CR-01 touches) needs to be rerun on the instrument against the redeployed adapter."
    expected: "A team decision: either (a) redeploy forb01 with 134e097/7c2e15a in the safe order and rerun LIVE-07 live, recording the rerun in 03-ACCEPTANCE.md as a new D-14-style entry, or (b) explicitly accept that the currently-deployed, already-accepted adapter (201d987) remains the production baseline and the CR-01 fix ships with a later phase/deploy, with that acceptance recorded somewhere durable (e.g. REQUIREMENTS.md note, a new deploy plan, or this VERIFICATION's override)."
    why_human: "This is a production redeploy/rerun decision on a live instrument with an operator required — not something a read-only code/log inspection can resolve, and the instructions for this re-verification explicitly prohibit sending anything to the live services or instrument."
---

# Phase 3: Deploy & Supervised Live Acceptance Verification Report

**Phase Goal:** The live-control stack runs on forb01 and is proven on the instrument with an
operator present.
**Verified:** 2026-10-16T05:40:00Z
**Status:** human_needed
**Re-verification:** Yes — the prior `passed` 16/16 verification (2026-10-15T19:30Z) is stale:
covered source changed afterward (Phase 2 gap-closure plan 02-05, commits `134e097`/`7c2e15a`,
landed ~21:07-21:10 WIB on 2026-10-15, after this phase's verification was written at 19:30Z).

## Method

This is a read-only re-verification. No command was sent to any tool, nothing was restarted, and
no live service was touched (per explicit instruction). Work consisted of: (1) re-reading every
PLAN/SUMMARY must_haves block in this phase, `03-ACCEPTANCE.md`, `03-DEPLOY.md`, `03-REVIEW.md`/
`03-REVIEW-DISPOSITION.md`, and the prior `03-VERIFICATION.md`; (2) identifying exactly what
changed in the covered source since the prior verification (`git log`/`git show` on `134e097`,
`7c2e15a`); (3) determining which of this phase's must-haves that change affects; (4) re-running
the full local test suite and the single named CR-01 regression tests (read-only, no live
services); (5) regenerating the covered-files fingerprint.

```
$HOME/data/nikko/.venvs/galago-py310/bin/python -m unittest discover -s tools/tests/ -p "*_test.py"
Ran 147 tests ... OK
```

## What changed since the prior verification

Phase 2 gap-closure plan `02-05` (commits `134e097` fix, `7c2e15a` test; baseline SHA
`201d9879134e708799a1fac8420579bbdbe5f2a8` per `02-05-SUMMARY.md`'s own baseline check — the exact
SHA this phase's `03-DEPLOY.md`/`03-ACCEPTANCE.md` record as the deployed adapter) changed
`tools/fast/server.py`'s `Resume` crash-recovery branch: it now gates `service.wait` on the shared
`_accepted()` helper instead of an inline `errorCode != 0` comparison, so a malformed reply (e.g.
`{"errorCode": False}`) is rejected instead of waited on (CR-01). Two new regression tests were
added to `tools/tests/fast_test.py` and independently re-run here on the real core:
`test_crash_recovery_resume_bool_false_error_code_is_not_success` and
`test_crash_recovery_resume_reply_without_error_code_is_not_success`, both pass.

This fix has **not** been deployed to forb01** and has **not** been exercised against the
instrument. `03-DEPLOY.md`/`03-ACCEPTANCE.md` both still correctly describe the adapter running on
forb01 as `201d987` — a redeploy to pick up `134e097`/`7c2e15a` has not happened and is outside
the scope of what a read-only verification can authorize. Of this phase's four live scenarios,
**LIVE-07** is the only one whose code path is the one CR-01 touches: its recovery step is a
tool-page `Resume` sent while no `Transfer` is in flight (the orphaned `Transfer` thread holds the
motion lock) — exactly the "lock acquired, crash-recovery" branch in `Resume()`'s docstring. The
`03-ACCEPTANCE.md` LIVE-07 record shows that scenario's actual reply was a normal acceptance
(`SUCCESS`), which both the old and new code paths treat identically, so there is no reason to
believe the live result itself was wrong — but the code that produced it has since changed, and
that specific change was never re-exercised live.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | Deployment followed the safe order (core → `.venv` → restart `galago-tools` → rebuild `galago-web`), no window with a new UI against an ungated core (Roadmap SC1) | ✓ VERIFIED | Unaffected by the CR-01 change — a historical record of the deploy sequence. `03-ACCEPTANCE.md` "LIVE-04 Deploy" four strictly increasing UTC timestamps; `03-DEPLOY.md` entry/pre-deploy/runbook sections unchanged since prior verification (not touched by 134e097/7c2e15a). |
| 2 | Deck-3 scenario: prompt names the deck/plate, operator fixes the deck and resumes, same step ends SUCCESS (Roadmap SC2 / LIVE-05) | ✓ VERIFIED | `03-ACCEPTANCE.md` `## LIVE-05`, unaffected — this scenario's code path (instrument-initiated pause via `Transfer`'s `through_pauses`/`on_pause`, then an in-flight `Resume`) is not the crash-recovery branch CR-01 touches. |
| 3 | Pause → Resume ends SUCCESS (Roadmap SC3a / LIVE-06a) | ✓ VERIFIED | `03-ACCEPTANCE.md` `## LIVE-06a`, unaffected — in-flight `Resume` (lock held by the running `Transfer`), not the crash-recovery branch. |
| 4 | Pause → Abort ends "aborted by operator at `<p>`%", queue FAILED, no later step runs (Roadmap SC3b / LIVE-06b) | ✓ VERIFIED | `03-ACCEPTANCE.md` `## LIVE-06b`, unaffected — `Abort`'s acceptance path already used `_accepted()` before CR-01 (CR-01 only changed `Resume`'s crash-recovery branch). |
| 5 | After restarting `galago-web` mid-run, the operator recovers through the tool page (Roadmap SC4 / LIVE-07) | ✓ VERIFIED (code since changed, not re-exercised — see finding below and human_verification) | `03-ACCEPTANCE.md` `## LIVE-07`: the recorded live result (tool-page Resume accepted, run completed) stands as an accurate historical record of what happened against the code that was deployed at the time. The crash-recovery `Resume` code this scenario exercises has since changed (CR-01) and that change has not been redeployed or rerun live. This does not retroactively make the recorded PASS false, but it means the *current* repository HEAD's behavior on this exact path is unverified live. |
| 6 | D-01 entry gate re-checked live at execution time before any deploy action; PASS recorded with evidence (LIVE-04) | ✓ VERIFIED | `03-DEPLOY.md` "Entry gate (D-01)", unaffected — historical gate record. |
| 7 | D-04 pre-deploy record captures service core, `galago-tools`/`galago-core`/`galago-web` state and rollback anchors (LIVE-04) | ✓ VERIFIED | `03-DEPLOY.md` "Pre-deploy record (D-04)", unaffected. |
| 8 | D-05/D-06 deploy runbook with exact commands/checks and reverse-order rollback (LIVE-04) | ✓ VERIFIED | `03-DEPLOY.md`, unaffected. |
| 9 | `scripts/fast_status.py` is restricted to the read-only `GetStatus` RPC, never `ExecuteCommand`/`Configure` (LIVE-04) | ✓ VERIFIED | `grep -n "stub\." scripts/fast_status.py` → exactly one call site, `stub.GetStatus(...)`, file unchanged since prior verification. |
| 10 | Dry run (D-07) exercises the deployed UI against a simulated F.A.S.T. tool with zero production risk, before any live scenario starts | ✓ VERIFIED | `scripts/fast_dryrun.py` unchanged since prior verification; `grep -c 'class DryRunFastServer(FastServer)' scripts/fast_dryrun.py` → 1. |
| 11 | D-14 FAIL→fix→rerun cycles (LIVE-05, LIVE-06b, LIVE-07) are each handled by stopping, fixing, re-running the gate, redeploying, and keeping the FAILed attempt as preserved history | ✓ VERIFIED | All three FAIL records remain present in `03-ACCEPTANCE.md` (not deleted), unaffected by the Phase-2 CR-01 change (CR-01 is a Phase 2 gap-closure plan, `02-05`, not one of this phase's own D-14 cycles). |
| 12 | Live re-verification of galago-core `261015-o44` fixes resolves FINDING (a)/(b) | ✓ VERIFIED | `03-ACCEPTANCE.md` `## 261015-o44 live verification`, unaffected — galago-core-side fix, unrelated to CR-01. |
| 13 | Safety invariant audit: every `Pause`/`Resume`/`Abort` line since the LIVE-04 deploy restart maps to a recorded operator action, 0 unmapped, restarts explained | ✓ VERIFIED | `03-ACCEPTANCE.md` `## Safety invariant audit`, unaffected — a record of what the log showed during acceptance, not a claim about current code. |
| 14 | Code unchanged since the last actual redeploy; post-acceptance gate green | ⚠️ UNCERTAIN — see human_verification | `git diff --stat 201d987 HEAD -- tools/ interfaces/ setup.py requirements.txt` is **no longer empty**: `tools/fast/server.py \| 27 ++++++++++-------` and `tools/tests/fast_test.py \| 79 ++...` (commits `134e097`, `7c2e15a`). The "post-acceptance gate green" half still holds and is *stronger* now (147 passed, up from 144, including the 2 new CR-01 regression tests, independently re-run here). But the "code unchanged" half is now literally false, and the change was not a D-14 gap fix of *this* phase with a recorded redeploy/rerun — it is an unrelated Phase 2 gap-closure plan that happens to touch the same file. Not marked FAILED: nothing about this phase's own evidence is wrong or fabricated; this is new information about code drift since acceptance that needs a human redeploy/rerun decision (see human_verification). |
| 15 | D-13 completeness: all six Summary rows PASS, every scenario section has its required fields, Edge-probe fallback accounted for | ✓ VERIFIED | `03-ACCEPTANCE.md` Summary table unaffected, unchanged since prior verification. |
| 16 | REQUIREMENTS.md LIVE-04..07 marked Complete only from this phase's evidence; no orphaned requirements | ✓ VERIFIED | `.planning/REQUIREMENTS.md` traceability table: LIVE-04, LIVE-05, LIVE-06, LIVE-07 all "Complete", mapped to Phase 3, "Unmapped: 0". (CR-01's own requirement, LIVE-02, belongs to Phase 2 and is tracked/closed there — `02-VERIFICATION.md` shows it re-verified `passed` 5/5 after gap-closure `02-05`; it is not one of this phase's four requirement IDs and does not create an orphan here.) |

**Score:** 15/16 truths verified (0 present-behavior-unverified; 1 routed to human_verification as UNCERTAIN rather than scored pass/fail)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `03-DEPLOY.md` | Entry gate, pre-deploy record, runbook, rollback, deploy evidence rows | ✓ VERIFIED | Unchanged since prior verification; 610 lines, all sections present. |
| `03-ACCEPTANCE.md` | Summary + 6 scenario sections + Safety invariant audit + Flagged assumptions | ✓ VERIFIED | Unchanged since prior verification; 1387 lines. |
| `scripts/fast_status.py` | Read-only `GetStatus` printer | ✓ VERIFIED | Unchanged; single `stub.GetStatus` call site. |
| `scripts/fast_dryrun.py` | Simulated-only dry-run harness | ✓ VERIFIED | Unchanged; `DryRunFastServer(FastServer)` present. |
| `tools/fast/server.py` | `_is_no_error` fix (D-14 LIVE-06b) present; adapter code otherwise matches deployed SHA | ⚠️ CHANGED SINCE DEPLOY | `_is_no_error` fix (`201d987`) still present and correct. Additionally, `Resume`'s crash-recovery branch changed again after `201d987` (CR-01, `134e097`) — this later change is substantive, tested, and present in the file, but not yet deployed to forb01. See Truth 14. |
| `tools/tests/fast_test.py` | Regression coverage for the `_is_no_error` fix and (new) CR-01 | ✓ VERIFIED | 147-test suite passes live (up from 144), including both the original `_is_no_error` coverage and the 2 new CR-01 regression tests (`test_crash_recovery_resume_bool_false_error_code_is_not_success`, `test_crash_recovery_resume_reply_without_error_code_is_not_success`), independently re-run here. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `scripts/fast_status.py` | `ToolDriverStub.GetStatus` | single RPC call | ✓ WIRED | Unchanged; confirmed by grep. |
| `scripts/fast_dryrun.py` | `FastServer.simulate_pause` | FIFO + auto-pause timer | ✓ WIRED | Unchanged. |
| `03-ACCEPTANCE.md` Safety invariant audit | post-deploy `F.A.S.T.log` | 20 cited control-command lines | ✓ WIRED | Unchanged, historical record. |
| `03-ACCEPTANCE.md` LIVE-04 block | `03-DEPLOY.md` evidence rows | cited SHAs/timestamps | ✓ WIRED | Unchanged. |
| `Resume`'s crash-recovery branch | `_accepted()` | gates `service.wait` | ✓ WIRED (new, post-acceptance) | Confirmed present at `tools/fast/server.py:908-924`; not the code that ran during the live LIVE-07 acceptance. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full local test suite passes on current HEAD | `.../galago-py310/bin/python -m unittest discover -s tools/tests/ -p "*_test.py"` | `Ran 147 tests ... OK` | ✓ PASS |
| CR-01 regression tests specifically pass | `.../python -m unittest tools.tests.fast_test.TestRecoveryCommands -v` | `test_crash_recovery_resume_bool_false_error_code_is_not_success ... ok`; `test_crash_recovery_resume_reply_without_error_code_is_not_success ... ok`; 22/22 in this class | ✓ PASS |
| Code unchanged since deployed SHA (`201d987`) | `git diff --stat 201d987 HEAD -- tools/ interfaces/ setup.py requirements.txt` | **non-empty**: `tools/fast/server.py \| 27 +++--`, `tools/tests/fast_test.py \| 79 +` | ✗ CHANGED (expected per context; routed to human_verification, not scored as a code defect) |
| No debt markers introduced by the CR-01 diff | `git diff 201d987 HEAD -- tools/fast/server.py tools/tests/fast_test.py \| grep -iE "TBD\|FIXME\|XXX\|TODO\|HACK\|PLACEHOLDER"` | no matches | ✓ PASS |
| `tools/base_server.py` unchanged (shared by every tool type; prohibition in every plan) | `git diff --stat 201d987 HEAD -- tools/base_server.py` | empty | ✓ PASS |

No command was sent to `forb01`'s live services or the instrument during this re-verification
(`systemctl`/`docker inspect`/`fast_status.py` against the running service were deliberately
**not** re-run here, per the explicit read-only instruction for this pass).

### Probe Execution

Not applicable — same as prior verification; this phase's evidentiary record (`03-ACCEPTANCE.md`)
plays that role.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| LIVE-04 | 03-01, 03-02 | Deployed in the safe order | ✓ SATISFIED | `03-ACCEPTANCE.md` LIVE-04 block, Result: PASS; `REQUIREMENTS.md` Complete. Unaffected by CR-01. |
| LIVE-05 | 03-05 | Deck 3 empty → prompt → fix → Resume → SUCCESS | ✓ SATISFIED | `03-ACCEPTANCE.md` LIVE-05 section, Result: PASS. Unaffected by CR-01 (different code path). |
| LIVE-06 | 03-04, 03-06 | Pause→Resume→SUCCESS; Pause→Abort→"aborted by operator", queue FAILED | ✓ SATISFIED | `03-ACCEPTANCE.md` LIVE-06a + LIVE-06b, both Result: PASS. Unaffected by CR-01 (both are in-flight-lock paths, not the crash-recovery branch). |
| LIVE-07 | 03-07, 03-08 | Restart `galago-web` mid-run, recover via tool page | ⚠️ SATISFIED HISTORICALLY, CODE SINCE CHANGED | `03-ACCEPTANCE.md` LIVE-07 section, Result: PASS, accurate record of what happened against `201d987`. The crash-recovery `Resume` code this scenario depends on has since changed (CR-01) and is undeployed/unexercised live. See human_verification. |

No orphaned requirements: `REQUIREMENTS.md`'s coverage line still reads "Milestone requirements:
17 total / Mapped to phases: 17 / Unmapped: 0". CR-01's own requirement (LIVE-02) belongs to
Phase 2 and was closed there (`02-VERIFICATION.md`, re-verified `passed` 5/5 after `02-05`); it is
correctly out of scope for this phase's four requirement IDs.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `scripts/fast_dryrun.py` | 99-181 | WR-01 (open, `03-REVIEW.md`) — unchanged since prior verification | ⚠️ Warning | Confined to the dev-only, already-torn-down dry-run harness. Unaffected by CR-01. |
| `tools/fast/server.py:310-318` | 310-318 | WR-02 (open, `03-REVIEW.md`): `_is_no_error`'s `error_code in (None, 0)` still uses `==`-style membership, diverging from the file's own `type(code) is int` convention — **still unresolved**; CR-01 fixed the analogous issue in `Resume`'s crash-recovery gate but did not touch `_is_no_error` | ⚠️ Warning | Confirmed still present at the cited lines after the CR-01 commits. Not required by any phase must-have. The CR-01 fix (134e097) explicitly scoped itself to the `Resume` gate only — see `02-05-SUMMARY.md` key-decisions: "WR-02 ... intentionally excluded ... tracked separately in Phase 3's review disposition." Still open there. |
| `tools/fast/server.py:125,140,145` | — | `D-16 ASSUMED PLACEHOLDER` comments | ℹ️ Info | Pre-dates this phase, references tracked decision D-16, exception to debt-marker gate applies. Unaffected. |
| `.planning/ROADMAP.md:22` | 22 | Phase 3's milestone-overview bullet still reads `- [ ]` while every plan-level bullet is `- [x]` and `REQUIREMENTS.md` shows all four IDs Complete | ℹ️ Info | Cosmetic, unaffected. |

No `TBD`/`FIXME`/`XXX` markers found in the CR-01 diff or any other file this phase touched.

### Human Verification Required

### 1. Redeploy/rerun decision for the CR-01 fix on forb01

**Test:** Decide whether forb01's deployed `galago-tools` (still on adapter SHA `201d987`, per
`03-DEPLOY.md`) needs to be redeployed with the CR-01 fix (`134e097`/`7c2e15a`, from Phase 2's
gap-closure plan `02-05`) before this phase's live-acceptance evidence is treated as covering the
*current* repository HEAD, and whether LIVE-07 — the only one of the four live scenarios whose
code path is the crash-recovery `Resume` branch CR-01 touches — needs to be rerun live against the
redeployed adapter.
**Expected:** A recorded team decision: either (a) redeploy forb01 with `134e097`/`7c2e15a` in the
safe order (`03-DEPLOY.md`'s pattern) and rerun LIVE-07 live, adding the rerun to
`03-ACCEPTANCE.md` as a new entry, or (b) explicitly accept the current production baseline
(`201d987`) as-is for now and record that decision somewhere durable (a new deploy plan, a
REQUIREMENTS.md note, or an accepted override on this VERIFICATION.md).
**Why human:** This is a live-instrument redeploy/rerun decision requiring an operator and
e-stop-in-reach, which this read-only re-verification is explicitly instructed not to perform.

### Gaps Summary

No gaps. All 16 observable truths derived from the Roadmap Success Criteria and this phase's own
PLAN must-haves remain supported by accurate, unaltered evidence for what happened during the
live acceptance. One truth (14, "code unchanged since deploy") no longer holds as a static fact
about the *current* repository, because an unrelated Phase 2 gap-closure plan (`02-05`, commits
`134e097`/`7c2e15a`) modified `tools/fast/server.py`'s crash-recovery `Resume` path after this
phase's acceptance evidence and prior verification were recorded. This is not treated as a defect
in this phase's own work — the live-acceptance record remains an accurate account of what was
proven at the time, against the code that was actually running — but it is new information the
team has not yet acted on: the fix is tested in isolation (147/147, including 2 new regression
tests re-run here) but not deployed to forb01 or exercised on the instrument. Routed to human
verification above rather than scored as a pass or a fail.

---

_Verified: 2026-10-16T05:40:00Z_
_Verifier: Claude (gsd-verifier)_
