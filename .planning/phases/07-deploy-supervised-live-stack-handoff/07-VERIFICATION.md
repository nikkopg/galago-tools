---
phase: 07-deploy-supervised-live-stack-handoff
verified: 2026-11-03T06:16:00Z
status: passed
score: 22/24 must-haves verified
covered_files:
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-01-PLAN.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-01-SUMMARY.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-02-PLAN.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-02-SUMMARY.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-03-PLAN.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-03-SUMMARY.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-04-PLAN.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-04-SUMMARY.md"
  - "docs/runbooks/gal-07-live-check.sh"
  - "docs/runbooks/gal-07-live-handoff.md"
  - "tools/tests/gal07_live_runbook_test.py"
covered_digest: "v4:sha256:c7792ee17a265b83e41a1c769de4493d54fdc1c1d8e0f89f53bbd66b429fbf35"
pre_execution_head: 7d158fb8e00921ac9c680e491cc8bccca98f190b
post_execution_head: 24bcf311d75e0bf7833d1b6a1d18f35b5d0fb477
behavior_unverified: 2
re_verification: 0
unverified_prohibitions: 10
warnings:
  - "deferred-items.md still marks the owner-lock probe item `status: open` — the fix landed in 07-03 (commit 9344957) and was live-verified by this verifier (gate exits 0, PREFLIGHT OK). Stale record; informational only."
  - "Findings row 3a-3 enumerates the 16 STACK2-6.log attempt lines with a breakdown that sums to 15 (its `2 additional short tool exchanges` timestamps 05:36:41Z/05:38:44Z do not match the raw log lines 05:36:18/05:37:58/05:38:31 local=UTC+7). The total (16) and the four leg timestamps match the raw log exactly; only the D-14-history accounting prose is off by one component."
  - "ROADMAP.md line 44 still shows `- [ ] Phase 7` while its three success criteria are met; top-level checkbox flip is an orchestrator/bookkeeping step."
  - "live Transfer duration 27 s is below the 30-32 s expected band — recorded honestly in rows 2a-2/2a-3 as observed-vs-estimate, not asserted as in-band."
behavior_unverified_items:
  - truth: "07-03 backstop truth — the live Transfer reached ran on stack2-6 with the user present"
    test: "Operator vouches they were physically/interactively present during the LIVE-09 event (go 2026-11-03T03:51:07Z, terminal reply 03:58:25Z)"
    expected: "The typed go at 03:51:07Z was genuinely operator-typed; nobody replayed it later; the session was supervised end to end"
    why_human: "Presence and the genuine act of typing the go are operator-only facts; the ledger/log corroborate the mechanical chain (one record, state done, one Transfer line at 03:57:58Z) but cannot prove who was watching"
  - truth: "07-04 backstop truth — the live GAL-02 handoff ran to SUCCESS with the user present"
    test: "Operator vouches they were present through the two-plate run (go recorded in row 3a-1; legs 05:40:15Z-05:43:00Z)"
    expected: "The typed go in row 3a-1 was genuinely typed; the queue session was supervised; queue rows as reported are what the operator saw"
    why_human: "Same evidence class: motion facts are triple-corroborated (ledger 4 fresh done/ran keys, 4 leg log lines with matching UTC stamps, FA100056 log line at 05:41:16Z), but supervision and the go's authenticity are operator-only"
human_verification:
  - test: "Operator vouches presence and the typed go for the LIVE-09 event (see behavior_unverified_items #1)"
    expected: "go 03:51:07Z was typed by the operator in a supervised session"
    why_human: "recorded-evidence class; not observable programmatically"
  - test: "Operator vouches presence and the typed go for the LIVE-10 event, and that the reported queue rows (all legs ran/SUCCESS) match what the manager UI showed"
    expected: "go recorded in row 3a-1 was typed; five legs ran under supervision"
    why_human: "recorded-evidence class; motion corroborated, supervision not"
  - test: "Review the 10 judgment-tier prohibitions (all marked `descriptor-less, flagged-unverified` in the plans) — operator confirms the supervised sessions honored them (never worked around a BLOCKED line by hand-editing; no restart-to-clear-failure; no state/ledger deletion; no re-send with a fresh key after an ambiguous outcome; no auto-advancing a GO gate)"
    expected: "The ledger's D-14 history (three earlier attempt keys kept, not deleted; movementErrors stopped the session and were fixed by physical adjustment, not re-send) supports this; operator confirms"
    why_human: "negative claims about what a supervised session did not do — judgment-tier by the plans' own designation"
  - test: "Triage the two open high-severity review items in 07-REVIEW-DISPOSITION.md (H-01 runbook Pre-flight text vs the gate's galago-holder exemption; H-02 lock-probe fail-open fallback to an unpinned core)"
    expected: "A disposition decision (fix now, defer to a `/gsd-code-review 07 --fix` pass, or accept-risk) recorded per item"
    why_human: "both are judgment/tolerance calls, recorded open by design at the code_review_gate"
---

# Phase 7: Deploy & Supervised Live STACK + Handoff — Verification Report

**Phase Goal:** The STACK tool is deployed in the safe order and proven on the real STACK: a supervised live Transfer, then a supervised live STACK -> F.A.S.T. -> STACK handoff, with the user present.
**Verified:** 2026-11-03T06:16:00Z
**Status:** human_needed (all verifiable must-haves verified; 2 backstop presence truths and the prohibition/supervision items routed to the operator)
**Re-verification:** No — initial verification

## Goal Achievement

### Method note (evidence class)

LIVE-08/09/10 are manual-recorded-evidence requirements by design (07-RESEARCH Validation Architecture). The verifier's own reach is therefore: every file, code, test-gate and regression must-have was checked directly on disk/live host; every live-fact truth was checked through the recorded artifacts **plus independent corroboration** (ledger file, tool logs, live gate run, live API reads). Where even that corroboration cannot reach (operator presence, authenticity of the typed go, supervision), the item is reported for human verification per the plans' own backstop semantics — never silently passed.

### Covered must-haves table (per-item verdicts)

**07-01 — pre-flight gate + runbook + falsification tests (LIVE-08 scriptable half)**

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Gate exits 0 only when every live precondition holds (identity, lock, core pin, DEP-02 gate re-run, web bundle, D-12 store with byte-exact host, no RUNNING run, credentials) | VERIFIED | `tools/tests/gal07_live_runbook_test.py` 15/15 green incl. the 12-piece removal matrix (tests run today by this verifier); live gate run `bash docs/runbooks/gal-07-live-check.sh` → exit 0, last line `PREFLIGHT OK` |
| 2 | Every check runs after one fails (no `set -e`); last line is `BLOCKED:` remedy (exit 1) or `PREFLIGHT OK` | VERIFIED | Script structure (failed accumulator, no `set -e`); line 288 BLOCKED remedy; tests assert both verdict shapes |
| 3 | Held lock refused with verbatim StackOwnedError wording naming the holder, probed through the pinned core's own `endpoint_key`/`lock_path`/`default_lock_dir` | VERIFIED | Held-lock flock fixture test green; script heredoc imports the core's owner_lock helpers (lines ~100-170) |
| 4 | (backstop) Gate fails closed on empty/non-JSON identity/store/runs responses and an unresolvable probe python | VERIFIED | Degenerate-input fail-closed tests in TestLiveGate green (productions API shapes allow-listed with fail-closed fallback — the 07-01 deviations) |
| 5 | Runbook exists with Safety rules / Pre-flight / Part 1 / Part 2 / Part 3 / Recovery drill / Findings log in order; typed-go gates with UTC, never-delete clauses, manager-UI-first recovery, 600 s replay rule all pinned | VERIFIED | TestRunbookContent pins green; 13 findings rows G0, 1a-1..6, 2a-1..3, 3a-1..3 present; `Reply: literal go` count == 3 (asserted today) |
| 6 | `docs/runbooks/gal-02-handoff.md` byte-unchanged and its 10.150.1.125 refusal remains in force (D-07) | VERIFIED | `git status --porcelain` → pristine; refusal lines at 12/271 confirmed today |

**07-02 — deploy in the safe order (LIVE-08)**

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Install source is the user's explicit decision in row 1a-1 (credentials or local-clone-waiver), never a silent fallback | VERIFIED | Row 1a-1 records local-clone-waiver with the local clone HEAD == pin verification and the stalled OAuth device flow |
| 2 | Core installed into the service .venv at 934a621… via direct_url.json, stack_test green under it | VERIFIED | Live probe (this verifier): `.venv/bin/python` direct_url.json vcs_info.commit_id == 934a621ece116a8b263897c1e9b62b57374f4ef3; row 1a-2 records stack_test 271 OK |
| 3 | Credentials reach the tool server only via the operator's 0600 env file; values appear nowhere | VERIFIED (mechanical) | Live: `chmod` 600 owner formulatrix, service active; credential-regex test green; row 1a-3 presence-only recording. Values themselves unreadable by design |
| 4 | Every restart preceded by a timestamped backup; listener PIDs re-baselined (not just MainPID) | VERIFIED (recorded) | Row 1a-4: backup `pre-gal07-20261102T112327Z`, MainPID 1940146→3973399, no traceback, ss re-baseline |
| 5 | Safe order proven by four strictly-increasing UTC timestamps in row 1a-6 | VERIFIED | Asserted today: 11:20:00Z < 11:24:34Z < 12:18:28Z < 01:31:16Z(+1d), four distinct sorted ISO-8601 stamps |
| 6 | After reconnect the store holds both a stack and a fast tool; D-12 passes; stack2-6 idle (operator-reported) | VERIFIED | Live `GET /api/tools` today: fast FA100056 + stack STACK2-6, stored host byte-exact `10.150.1.125`; gate D-12 passes live |
| 7 | galago-web runs a new image ≠ rollback anchor, /api/health 200, container bundle exports Command_Transfer | VERIFIED | Live today: running image sha256:2f609032… ≠ anchor tag 938217230697 (both tags still present), `/api/health` = `{"status":"ok"}`, Command_Transfer found in the bundle |

**07-03 — supervised live Transfer (LIVE-09)**

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | LIVE-09 pre-flight with GAL07_REQUIRE_STACK_ENV=1 ended PREFLIGHT OK before the event; typed go recorded in row 2a-1 with UTC; no auto-advance | VERIFIED (recorded; gate live-verified) | Row 2a-1: PREFLIGHT OK both forms at 03:13:42Z incl. the post-fix galago-holder handling (9344957), re-gate 03:47:58Z, operator go 03:51:07Z. Live gate re-run today: exit 0, PREFLIGHT OK |
| 2 | Transfer parameters chosen reads-first (ListDevices / ListLabwareProfiles / GetLabwarePresence), not hardcoded | VERIFIED (recorded) | Row 2a-2 carries the actual read-derived values (triple, profile, 55 s estimate) including the pre-event D-14 reconnect cycle |
| 3 | Exactly one live Transfer submitted, reached `ran` on stack2-6: SUCCESS reply, ledger record state done, exactly one `Running command Transfer` line | VERIFIED (live-corroborated) | Ledger (never edited): `GAL07-LIVE9-20261103T035107Z` state done, result.kind ran, guid bea7d9f1…; STACK2-6.log rehearsal line at local 10:57:58 (=03:57:58Z), exactly one; count 0→1 vs baseline |
| 4 | transfer_duration_s within bounds (0 < t ≤ 3600.0); expected hardware duration recorded as the observation baseline | VERIFIED | 27 s wall clock within bounds; 55 s estimate vs 27 s actual recorded honestly in rows 2a-2/2a-3 (band mismatch warned above, not hidden) |
| 5 | (backstop) reached `ran` **with the user present** | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Ran + single-submission are triple-corroborated (ledger, log, runbook row); presence/authenticity of the typed go is operator-only → human verification |

**07-04 — supervised live GAL-02 handoff (LIVE-10, as amended)**

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | LIVE-10 pre-flight (GAL07_REQUIRE_STACK_ENV=1) + D-12 pre-store check passed before the event; typed go recorded in row 3a-1 with UTC | VERIFIED (recorded; gate + store live-verified today) | Row 3a-1 gate evidence incl. the galago single-owner probe ok; live /api/tools holds both tools; live gate exit 0 |
| 2 | One GAL-02 run (numberOfRuns 1, reads-first live params) completed all tool legs to SUCCESS — **as amended to the two-plate cycle: 4 STACK legs + one F.A.S.T. liquid leg (deck 5→6)** | VERIFIED (live-corroborated) | Ledger: 4 fresh keys (…-127473f5-in1/in2/out1/out2) all state done, each with a distinct request fingerprint; STACK2-6.log leg lines at 12:40:15/12:40:46/12:42:31/12:43:02 local (=05:40:15Z…05:43:02Z, matching row 3a-2); FA100056.log `Running command Transfer` at 12:41:16 local (=05:41:16Z) with the fast progress 0→100% class |
| 3 | LIVE-10 D-14 amendment recorded: two-plate shape replaces the plan's Phase-6 three-leg sim shape; per the recorded amendment, "exactly one submission per STACK leg" = one ledger record + one log attempt line | VERIFIED | Amendment in 07-04-PLAN must_haves (truth 3) and rows 3a-1/3a-3; protocol history (visual GAL02 → id 11 → id 12 → id 13 → id 15) documented in row 3a-1 |
| 4 | Each STACK leg submitted exactly once; F.A.S.T. submission evidence in its own tool log | VERIFIED (live-corroborated) | One ledger record per key (no duplicate fingerprints across the four leg keys); four leg log lines each appearing once; 16-line STACK2-6.log, ledger + refusals + D-14 history accounted in row 3a-3 (breakdown prose off-by-one — warned above) |
| 5 | A FAIL row / ambiguous outcome / mid-run anomaly stopped the session at a blocking-human checkpoint; evidence never edited to pass | VERIFIED (recorded) | Row 1a-5 swapped-ports D-14 repair; row 3a-1/3a-3 two movementError attempts (keys kept in the ledger as D-14 history, never deleted); fix was the operator's physical nest adjustment, not a re-send |
| 6 | (backstop) ran to SUCCESS **with the user present** | ⚠️ PRESENT_BEHAVIOR_UNVERIFIED | Motion and queue outcome triple-corroborated; presence/supervision is operator-only → human verification |

**Score: 22/24 truths verified** (2 backstop presence truths present + fully mechanically corroborated, but the operator-presence invariant is not exercisable by any automated check).

### Requirements traceability

| Requirement | Source plans | Verdict | Evidence |
|-------------|--------------|---------|----------|
| LIVE-08 | 07-01, 07-02 | SATISFIED | SC 1 fully verified above (safe order = four-timestamp proof; stack-mcp closed = lock probe owner-galago/mcp-out logic verified in script + live run; both front ends on the identical `10.150.1.125` string byte-exact in the store). REQUIREMENTS.md row: Complete |
| LIVE-09 | 07-03 | SATISFIED | SC 2 verified mechanically (ran, ledger, log); presence → human verification. REQUIREMENTS.md row: Complete |
| LIVE-10 | 07-04 | SATISFIED | SC 3 verified mechanically under the recorded D-14 two-plate amendment (4+1 legs, 4 fresh keys done/ran); presence → human verification. REQUIREMENTS.md row: Complete |

All three requirement IDs are claimed by plans (`requirements:` frontmatter per plan) and present in REQUIREMENTS.md traceability — no orphaned requirement, no unmapped ID.

### Prohibitions (ADR-550 D4 routing)

- **Test-tier (2, 07-01):** never-delete clauses and the credential-value regex — both have wired enforcement and the tests pass (in the 15-test green module). PASS (wired test).
- **Judgment-tier (10: 07-01 ×1, 07-02 ×3, 07-03 ×3, 07-04 ×3):** all designated `descriptor-less, flagged-unverified` in the plans. Per ADR-550 D4 this is a NON-AUTHORITATIVE LLM-judge verdict: the recorded session behavior (D-14 history kept in the ledger, stops at blocking-human checkpoints, no re-sends, no restarts, no state deletion; listener PIDs unchanged across the whole phase) is consistent with all ten, but they are **not machine-verifiable**. **Unverified-prohibition — human review recommended** (see the human_verification item).
- **This is never a silent pass:** the prohibition items are listed verbatim above for operator vouching.

### Behavioral spot-checks (run today by this verifier)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Pre-flight gate verdict contract | `bash docs/runbooks/gal-07-live-check.sh` (read-only pledge) | exit 0, last line `PREFLIGHT OK`; galago-holder ok line (pid 4004972) | PASS |
| Gate falsification module | `python -m pytest tools/tests/gal07_live_runbook_test.py` | 15 passed | PASS |
| Phase-relevant regression trio | `bin/make proto` + `pytest gal07 + gal02_runbook + stack_ledger` | proto regen OK; 129 passed | PASS |
| Service venv core pin | `.venv/bin/python` direct_url.json probe | commit == 934a621… | PASS |
| Credential env file mode + service | `stat` + `systemctl --user is-active` | 600, active | PASS |
| Store state (D-12) | `curl /api/tools` | fast FA100056 + stack STACK2-6, host byte-exact 10.150.1.125 | PASS |
| Ledger (LIVE-09 + LIVE-10) | python read of `stack-ledger.json` | 8 records; LIVE9 key + 4 leg keys done; 3 earlier D-14 attempt keys preserved | PASS |
| STACK log submission count | count `Running command Transfer` in STACK2-6.log | 16 (matches row 3a-3 total) | PASS |
| F.A.S.T. leg evidence | FA100056.log | `Running command Transfer` at 12:41:16 local = 05:41:16Z | PASS |
| Web rebuild | docker inspect/images + exec grep + health | running ≠ anchor; Command_Transfer present; ok | PASS |
| D-07 regression | `git status` gal-02-handoff.md + refusal lines | pristine; refusal intact | PASS |

Full-suite note: 07-04's recorded full gate (`bin/make proto test`, 581 passed) was re-run at execution; this verifier re-ran the phase-scoped modules above instead of the full suite (single-run rule).

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes are declared for this phase (the gal-02/gal-07 gates are the scripted checks themselves, exercised above).

### Human Verification Required

1. **LIVE-09 supervision vouch** — operator confirms presence and the typed go at 2026-11-03T03:51:07Z (detailed in `behavior_unverified_items`).
2. **LIVE-10 supervision vouch** — operator confirms presence through the two-plate run and that the reported queue rows match what the manager UI showed.
3. **Judgment-tier prohibition review** — operator confirms the ten flagged prohibitions were honored across the whole supervised phase.
4. **H-01 / H-02 triage** — the two open high-severity review items in 07-REVIEW-DISPOSITION.md (runbook text vs galago-holder exemption; lock-probe fail-open fallback to an unpinned core) need a disposition decision.

### Warnings carried

1. `deferred-items.md` still shows the owner-lock probe as `status: open` although the fix landed (9344957, verified live here) — stale record.
2. Row 3a-3's breakdown of the 16 log lines sums to 15 (the total and the four leg stamps are exact; the D-14-history prose enumeration is off by one component).
3. ROADMAP.md line 44 Phase-7 checkbox still unchecked (top-level bookkeeping).
4. 27 s actual vs the 30–32 s expected band — honestly recorded in-row, not asserted in-band.

### Gaps Summary

**None.** No must-have truth FAILED; no artifact missing/stub; no key link broken; all requirements accounted for. The phase goal — deployed in the safe order (LIVE-08), then a supervised live Transfer reaching `ran` (LIVE-09), then a supervised live STACK → F.A.S.T. → STACK handoff to SUCCESS (LIVE-10) — is met by the codebase + recorded live evidence with independent corroboration of every mechanical claim. The `human_needed` status is driven solely by the two operator-presence backstop truths, the ten judgment-tier prohibitions, and the two open advisory review items — all operator-side vouching/triage, not missing implementation.

---

_Verified: 2026-11-03T06:16:00Z_
_Verifier: the agent (gsd-verifier)_
