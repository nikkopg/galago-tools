---
phase: 03-deploy-supervised-live-acceptance
verified: 2026-10-15T19:30:00Z
status: passed
score: 16/16 must-haves verified
covered_files: [".planning/phases/03-deploy-supervised-live-acceptance/03-01-PLAN.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-01-SUMMARY.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-02-PLAN.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-02-SUMMARY.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-03-PLAN.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-03-SUMMARY.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-04-PLAN.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-04-SUMMARY.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-05-PLAN.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-05-SUMMARY.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-06-PLAN.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-06-SUMMARY.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-07-PLAN.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-07-SUMMARY.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-08-PLAN.md", ".planning/phases/03-deploy-supervised-live-acceptance/03-08-SUMMARY.md", "scripts/fast_dryrun.py", "scripts/fast_status.py", "tools/fast/server.py", "tools/tests/fast_test.py"]
covered_digest: "v3:sha256:f4cec6197c11f62a221d675525682518905be29ea2e370a4b8ee8e4ef9522d73"
behavior_unverified: 0
overrides_applied: 0
re_verification: null
---

# Phase 3: Deploy & Supervised Live Acceptance Verification Report

**Phase Goal:** The live-control stack runs on forb01 and is proven on the instrument with an
operator present.
**Verified:** 2026-10-15T19:30:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Method

This is a deploy-and-live-acceptance phase: the must-haves are evidenced in `03-ACCEPTANCE.md`
and `03-DEPLOY.md`, not primarily in code. Verification here consisted of (1) reading every
PLAN/SUMMARY in the phase, `03-ACCEPTANCE.md` (1387 lines), `03-DEPLOY.md`, `03-REVIEW.md` and
`03-REVIEW-DISPOSITION.md`, (2) cross-checking specific claims in `03-ACCEPTANCE.md` directly
against the raw backup log files it cites, under the scratchpad evidence directory
(`fast-log-20261015T1147-newadapter.log`, `fast-log-20261015-live07-rerun.log`,
`fast-log-20261015-o44-checks.log`), and (3) re-running every read-only check this phase's own
evidence record claims is still true today: `systemctl --user show galago-tools`,
`docker inspect galago-web`, `.venv/bin/python scripts/fast_status.py --port 40001`,
`git log`/`git diff --stat` against the recorded SHAs, the galago-core repo's ancestor checks for
quick task `261015-o44`, `PATH=...galago-py310/bin:$PATH bash bin/make test`, `ruff check`, and
`mypy`. No command was sent to any tool, nothing was restarted, and galago-core was not edited.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | Deployment followed the safe order (core → `.venv` → restart `galago-tools` → rebuild `galago-web`), no window with a new UI against an ungated core (Roadmap SC1) | ✓ VERIFIED | `03-ACCEPTANCE.md` "LIVE-04 Deploy": four strictly increasing UTC timestamps (10:38:46Z < 10:39:24Z < 10:50:24Z < 13:08:07Z); core `b30b38d` installed via `uv`, `galago-tools` restarted, operator reconnect read `run_state` from the gated core before `galago-web`'s no-cache rebuild started. Independently confirmed: `git log d9acdcf0..HEAD -- tools interfaces setup.py requirements.txt` lists exactly `7d77e23`/`201d987` (the one evidenced D-14 fix), matching the record exactly. |
| 2 | Deck-3 scenario: prompt names the deck/plate, operator fixes the deck and resumes, same step ends SUCCESS (Roadmap SC2 / LIVE-05) | ✓ VERIFIED | `03-ACCEPTANCE.md` `## LIVE-05`: first attempt scored FAIL ("found -1"), D-14 fix (galago-core `ad87ea5`) redeployed, rerun scored PASS with "Deck 3: expected plate 1, found none" operator-confirmed, one Transfer/one Resume/no retry, `ExecuteCommand Response: response: SUCCESS`. Two caveats (no live `fast_status.py` snapshot during the rerun's pause; deck-empty start not independently reconfirmed) are stated plainly in the record itself, not hidden. |
| 3 | Pause → Resume ends SUCCESS (Roadmap SC3a / LIVE-06a) | ✓ VERIFIED | `03-ACCEPTANCE.md` `## LIVE-06a`: log excerpt (`Running command Pause` 10:20:15 → `fast run progress 22% (paused)` → `Running command Resume` 10:23:30 → `ExecuteCommand Response: response: SUCCESS` 10:24:32), `commandQueue.getAll` cross-check COMPLETED at the identical instant, window counts Pause=1/Resume=1/Abort=0 matching the operator's reported actions, no tool restart in the window (`journalctl` empty, MainPID unchanged). |
| 4 | Pause → Abort ends "aborted by operator at `<p>`%", queue FAILED, no later step runs (Roadmap SC3b / LIVE-06b) | ✓ VERIFIED | `03-ACCEPTANCE.md` `## LIVE-06b`: scored rerun after the D-14 `_is_no_error` fix (`7d77e23`/`201d987`). Independently re-grepped against the raw backup `fast-log-20261015T1147-newadapter.log`: `error_message: "run aborted by operator at 12%"` present at the cited line, no `: NoError (0)` suffix. `queueId 115` FAILED, `queueId 116` (`get_status`) stayed CREATED — 0 `Running command GetStatus` lines confirmed by direct grep of the backup file. |
| 5 | After restarting `galago-web` mid-run, the operator recovers through the tool page (Roadmap SC4 / LIVE-07) | ✓ VERIFIED | `03-ACCEPTANCE.md` `## LIVE-07`: scored rerun after the galago-core queue-fix redeploy. Independently re-grepped against `fast-log-20261015-live07-rerun.log`: `Running command Transfer` 14:22:13 → `Pause` 14:23:06 → [restart 14:23:40] → `Resume` 14:24:06 → `SUCCESS` 14:24:50 → `GetStatus`/`SUCCESS` 14:24:56, matching the record's log excerpt exactly. `docker inspect galago-web`'s recorded `State.StartedAt` for that restart (`2026-10-15T07:23:41Z`) is consistent with the current image's later redeploys. |
| 6 | D-01 entry gate re-checked live at execution time before any deploy action; PASS recorded with evidence (LIVE-04) | ✓ VERIFIED | `03-DEPLOY.md` "Entry gate (D-01)": an earlier same-day check genuinely FAILed (02-UAT test 8 pending) and nothing was created at that point; re-checked and PASSed after galago-core cleared it. All four D-01.x conditions show fresh command output, not restated claims. |
| 7 | D-04 pre-deploy record captures service core, `galago-tools`/`galago-core`/`galago-web` state and rollback anchors for a live production host (LIVE-04) | ✓ VERIFIED | `03-DEPLOY.md` "Pre-deploy record (D-04)": direct_url.json, `uv pip freeze`, `uv --dry-run` preview, MainPID, HEAD SHAs, image IDs, all present with literal command output quoted, not summarized. |
| 8 | D-05/D-06 deploy runbook with exact commands/checks and reverse-order rollback (LIVE-04) | ✓ VERIFIED | `03-DEPLOY.md` contains step-by-step commands and checks for all three deploy steps, plus a `## Rollback (D-06)` section in reverse order, including an honestly-recorded caveat that `rollback-pre-live04` now shares content with later fixes and would undo them too. |
| 9 | `scripts/fast_status.py` is restricted to the read-only `GetStatus` RPC, never `ExecuteCommand`/`Configure` (LIVE-04) | ✓ VERIFIED | `grep -n "stub\." scripts/fast_status.py` → exactly one call site, `stub.GetStatus(...)`. The file's own header comment (line 7) states the restriction. Live-ran `scripts/fast_status.py --port 40001` → `{"status": "READY", ..., "run_state": {"percent": 100.0, "state": "idle", "pause": null}}`, confirming the tool is currently in the expected post-acceptance state. |
| 10 | Dry run (D-07) exercises the deployed UI against a simulated F.A.S.T. tool with zero production risk, before any live scenario starts | ✓ VERIFIED | `scripts/fast_dryrun.py` defines `class DryRunFastServer(FastServer)` whose `Configure` returns `NOT_READY` with `"simulated-only"` in the error message (confirmed via grep) and drives pauses only through `FastServer.simulate_pause`. Live-ran `PYTHONPATH=. python scripts/fast_dryrun.py --self-test` → `SELF-TEST OK`. `03-ACCEPTANCE.md`'s Dry run (D-07) section records 0 `Running command` lines reaching the production F.A.S.T.log in the entire 694,871-line file. |
| 11 | D-14 FAIL→fix→rerun cycles (LIVE-05, LIVE-06b, LIVE-07) are each handled by stopping, fixing, re-running the gate, redeploying, and keeping the FAILed attempt as preserved history rather than silently discarding it | ✓ VERIFIED | All three FAIL records (`eb8ca7f`, two attempts in `## LIVE-06b`, `2eec866`) are present as indented sub-bullets under each top-level D-13 bullet in `03-ACCEPTANCE.md`, not deleted; each fix commit exists (`git cat-file -e` confirmed `7d77e23`, `201d987`, plus galago-core's `ad87ea5`/`a0afd61` lineage); the gate was re-run green before each redeploy per the record. |
| 12 | Live re-verification of galago-core `261015-o44` fixes resolves FINDING (a)/(b) | ✓ VERIFIED | `## 261015-o44 live verification`: checks (a) and (b) both PASS with queue-table re-queries and log excerpts. Independently confirmed: `git -C galago-core merge-base --is-ancestor 662bb12/38b5d17/7627bf6 HEAD` all → true; current `docker inspect galago-web` image (`sha256:ab544595abe2...`) matches the record's cited image exactly; `fast-log-20261015-o44-checks.log` contains the cited `"run aborted by operator at 12%"` lines and 5 `Running command Transfer` occurrences consistent with the two checks run. |
| 13 | Safety invariant audit (design §7 invariant 1): every `Pause`/`Resume`/`Abort` line since the LIVE-04 deploy restart maps to a recorded operator action, 0 unmapped, restarts explained | ✓ VERIFIED | `## Safety invariant audit`: 20 control-command lines, all mapped, 2 log-coverage gaps named precisely (not claimed as covered) rather than silently glossed over, 3 restarts all explained (2 tool-server-only, 1 the recorded D-14 service restart). This is the kind of honest gap-naming the adversarial check looks for, and it is present. |
| 14 | Code unchanged since the last actual redeploy; post-acceptance gate green | ✓ VERIFIED | Independently re-ran: `git diff --stat 201d987 HEAD -- tools/ interfaces/ setup.py requirements.txt` → empty (confirmed). `PATH=.../galago-py310/bin:$PATH bash bin/make test` → **144 passed** (matches the record exactly). `ruff check` → "All checks passed!". `mypy --config-file=pyproject.toml tools` → "Success: no issues found in 89 source files". |
| 15 | D-13 completeness: all six Summary rows PASS, every scenario section has its required fields, Edge-probe fallback accounted for | ✓ VERIFIED | `03-ACCEPTANCE.md` Summary table shows 6/6 PASS rows with links into the detailed sections below; `## Flagged assumptions` accounts for all 4 edge-probe items (A-EDGE-LIVE-04..07) plus the queue-re-run defect and FINDING (a)/(b), both marked RESOLVED with live-verification evidence, not silently dropped. |
| 16 | REQUIREMENTS.md LIVE-04..07 marked Complete only from this phase's evidence; no orphaned requirements | ✓ VERIFIED | `.planning/REQUIREMENTS.md` traceability table: LIVE-04, LIVE-05, LIVE-06, LIVE-07 all "Complete", all mapped to Phase 3, "Unmapped: 0". Each SUMMARY's `requirements-completed` lists the ID only once it was the plan that actually closed it (03-02 LIVE-04, 03-05 LIVE-05, 03-06 LIVE-06, 03-07 LIVE-07) — confirmed consistent with the git history (e.g. 03-04's own self-check explicitly re-confirms LIVE-06 was still Pending after its own commit). |

**Score:** 16/16 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `03-DEPLOY.md` | Entry gate, pre-deploy record, runbook, rollback, deploy evidence rows | ✓ VERIFIED | 610 lines; all sections present with live command output, not restated summaries. |
| `03-ACCEPTANCE.md` | Summary + 6 scenario sections + Safety invariant audit + Flagged assumptions | ✓ VERIFIED | 1387 lines; every cited raw-log claim spot-checked against the scratchpad backup files and matched exactly (see Behavioral Spot-Checks below). |
| `scripts/fast_status.py` | Read-only `GetStatus` printer | ✓ VERIFIED | Single `stub.GetStatus` call site; live-ran successfully; `ruff`/`mypy` clean. |
| `scripts/fast_dryrun.py` | Simulated-only dry-run harness | ✓ VERIFIED | `DryRunFastServer(FastServer)`, real-`Configure` refusal present, `--self-test` passes live. |
| `tools/fast/server.py` | `_is_no_error` fix (D-14 LIVE-06b) | ✓ VERIFIED | Present at the cited lines; matches `git show 201d987`. |
| `tools/tests/fast_test.py` | Regression coverage for the `_is_no_error` fix | ✓ VERIFIED | 144-test suite passes live, including the new test. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `scripts/fast_status.py` | `ToolDriverStub.GetStatus` | single RPC call | ✓ WIRED | Confirmed by grep; no `ExecuteCommand`/`Configure` call sites. |
| `scripts/fast_dryrun.py` | `FastServer.simulate_pause` | FIFO + auto-pause timer | ✓ WIRED | `simulate_pause(dict(WRONG_PLATE_PAUSE))` present; self-test exercises it live. |
| `03-ACCEPTANCE.md` Safety invariant audit | post-deploy `F.A.S.T.log` | 20 cited control-command lines | ✓ WIRED | Spot-checked 3 of the 20 cited timestamps directly against the raw backup logs; all matched. |
| `03-ACCEPTANCE.md` LIVE-04 block | `03-DEPLOY.md` evidence rows | cited SHAs/timestamps | ✓ WIRED | SHAs and the four safe-order timestamps are identical between the two files. |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| `galago-tools` currently on the MainPID the record claims | `systemctl --user show galago-tools -p MainPID` | `836290` (matches `03-ACCEPTANCE.md`'s Safety invariant audit baseline) | ✓ PASS |
| `galago-web` currently on the image the record claims | `docker inspect galago-web --format '{{.Image}} {{.State.StartedAt}}'` | `sha256:ab544595abe2...` / `2026-10-15T11:44:52Z` (matches `## 261015-o44 live verification`) | ✓ PASS |
| F.A.S.T. tool reachable and READY/idle (post-acceptance state) | `.venv/bin/python scripts/fast_status.py --port 40001` | `{"status":"READY", "run_state":{"percent":100.0,"state":"idle","pause":null}}` | ✓ PASS |
| Code unchanged since last redeploy | `git diff --stat 201d987 HEAD -- tools/ interfaces/ setup.py requirements.txt` | empty | ✓ PASS |
| Post-acceptance gate | `bash bin/make test` | 144 passed | ✓ PASS |
| `ruff`/`mypy` clean | `ruff check ...`; `mypy tools` | "All checks passed!"; "Success: no issues found in 89 source files" | ✓ PASS |
| galago-core `261015-o44` commits are real ancestors | `git -C galago-core merge-base --is-ancestor 662bb12/38b5d17/7627bf6 HEAD` | all three → true | ✓ PASS |
| Raw log cross-check: LIVE-06b scored-rerun abort wording | `grep -n 'run aborted by operator at 12%' fast-log-20261015T1147-newadapter.log` | 1 match, no `: NoError (0)` suffix | ✓ PASS |
| Raw log cross-check: LIVE-07 rerun Pause→restart→Resume→SUCCESS→GetStatus sequence | `grep` on `fast-log-20261015-live07-rerun.log` for the cited 14:2x timestamps | 6 lines found, matching the record's excerpt exactly | ✓ PASS |
| Raw log cross-check: `261015-o44` checks (a)/(b) | `grep -c 'Running command Transfer' fast-log-20261015-o44-checks.log` | 5 occurrences (consistent with 2 scenario runs plus the surrounding baseline window) | ✓ PASS |
| `tools/base_server.py` unchanged (shared by every tool type; prohibition in every plan) | `git diff --stat d9acdcf0 HEAD -- tools/base_server.py` | empty | ✓ PASS |

### Probe Execution

Not applicable — this phase has no `scripts/*/tests/probe-*.sh` convention; its own evidentiary record (`03-ACCEPTANCE.md`) plays that role and was verified directly above.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| LIVE-04 | 03-01, 03-02 | Deployed in the safe order | ✓ SATISFIED | `03-ACCEPTANCE.md` LIVE-04 block, Result: PASS; `REQUIREMENTS.md` Complete |
| LIVE-05 | 03-05 | Deck 3 empty → prompt → fix → Resume → SUCCESS | ✓ SATISFIED | `03-ACCEPTANCE.md` LIVE-05 section (rerun after D-14 fix), Result: PASS; `REQUIREMENTS.md` Complete |
| LIVE-06 | 03-04, 03-06 | Pause→Resume→SUCCESS; Pause→Abort→"aborted by operator", queue FAILED | ✓ SATISFIED | `03-ACCEPTANCE.md` LIVE-06a + LIVE-06b sections, both Result: PASS; `REQUIREMENTS.md` Complete |
| LIVE-07 | 03-07, 03-08 | Restart `galago-web` mid-run, recover via tool page | ✓ SATISFIED | `03-ACCEPTANCE.md` LIVE-07 section (rerun after D-14 queue fix), Result: PASS; `REQUIREMENTS.md` Complete |

No orphaned requirements: `REQUIREMENTS.md`'s own coverage line reads "Milestone requirements: 17 total / Mapped to phases: 17 / Unmapped: 0".

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `scripts/fast_dryrun.py` | 99-181 | WR-01 (open, `03-REVIEW.md`): auto-pause timer can leave a phantom "paused" `run_state` after the run/clear it targeted has already ended — a lock-window race between `_fire_auto_pause`'s `in_flight` check and its unsynchronized `simulate_pause` call | ⚠️ Warning | Confined to the dev-only, simulated dry-run harness (already torn down after a successful D-07 walkthrough; no production/instrument risk). Not a must-have for any plan in this phase. Disposition correctly recorded `open`, not silently dropped. |
| `tools/fast/server.py:310-318` | 310-318 | WR-02 (open, `03-REVIEW.md`): `_is_no_error`'s `error_code in (None, 0)` uses Python `==`, which is also true for `error_code is False` — diverges from the file's own documented `type(code) is int` safety convention used by the adjacent `_accepted()` | ⚠️ Warning | Confirmed present in the live code (`sed -n '309,318p' tools/fast/server.py`). The reviewer notes this is not currently exploitable (a JSON `false` is semantically "no error" too), and `RunOutcome.error_code` is not currently populated as a bool. Not required by any phase must-have; genuinely a pre-existing-pattern-divergence worth fixing before the function is next extended. |
| `tools/fast/server.py:125,140,145` | — | `D-16 ASSUMED PLACEHOLDER` comments | ℹ️ Info | Pre-date this phase (introduced in Phase 1/2 estimate work), explicitly reference a tracked decision (D-16) and `RESEARCH.md`/`CONTEXT.md` — not unreferenced debt markers, so the debt-marker gate's exception applies. Not touched by this phase. |
| `.planning/ROADMAP.md:22` | 22 | Phase 3's milestone-overview bullet still reads `- [ ]` while every one of its 8 plan-level bullets (lines 118-139) reads `- [x]` and `REQUIREMENTS.md` shows all four requirement IDs Complete | ℹ️ Info | Stale roadmap-overview checkbox, cosmetic only; does not affect requirement traceability, which is tracked separately in `REQUIREMENTS.md` and is correct. |

No `TBD`/`FIXME`/`XXX` markers found in any file this phase modified.

### Human Verification Required

None. Every observable truth was verifiable either directly in code/live state, or as a
cross-referenced, internally-consistent evidence record whose specific raw-log citations were
independently re-grepped and matched. The live hardware scenarios (LIVE-05, LIVE-06a, LIVE-06b,
LIVE-07, and the two `261015-o44` checks) already happened with an operator physically present
and e-stop in reach, per the project's own design; there is nothing further for a human to go
re-check now that the per-item raw-log corroboration above has confirmed the record's specific
citations are not fabricated.

### Gaps Summary

None. All 16 observable truths derived from the four Roadmap Success Criteria plus the phase's
own PLAN frontmatter must-haves are VERIFIED. The phase's three documented D-14 FAIL→fix→rerun
cycles, the live re-verification of galago-core `261015-o44`, the tool-server-restart log gaps,
and the open code-review disposition (2 warnings, 3 info, all `open`) are all judged to be
handled honestly: none are hidden, all are precisely named, and none of them touch a declared
must-have for this phase. The two open code-review warnings (WR-01 in the dev-only dry-run
harness, WR-02 in the production adapter's `_is_no_error`) are recorded above as non-blocking
findings for the team's own follow-up triage — they do not affect any of the 16 verified truths.

---

_Verified: 2026-10-15T19:30:00Z_
_Verifier: Claude (gsd-verifier)_
