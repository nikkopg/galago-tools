---
phase: 07-deploy-supervised-live-stack-handoff
verified: 2026-11-03T07:44:30Z
status: passed
score: 24/24 must-haves verified
covered_files:
  - ".planning/REQUIREMENTS.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-01-PLAN.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-01-SUMMARY.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-02-PLAN.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-02-SUMMARY.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-03-PLAN.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-03-SUMMARY.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-04-PLAN.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-04-SUMMARY.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-COVERAGE.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-REVIEW-DISPOSITION.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-REVIEW.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-SECURITY.md"
  - ".planning/phases/07-deploy-supervised-live-stack-handoff/07-UAT.md"
  - "docs/runbooks/gal-07-live-check.sh"
  - "docs/runbooks/gal-07-live-handoff.md"
  - "tools/tests/gal07_live_runbook_test.py"
covered_digest: "v4:sha256:ab3482d26c113586786c6e3c99d29c1aa17230ba5ebad00c7ae42633ac261e80"
pre_execution_head: 7d158fb8e00921ac9c680e491cc8bccca98f190b
post_execution_head: ecf424ebb1c1d268760444eaa233e60564a4fe93
behavior_unverified: 0
re_verification: 1
unverified_prohibitions: 0
re_verification:
  previous_status: human_needed
  previous_score: 22/24
  gaps_closed:
    - "07-03 backstop — live Transfer ran with the user present: VERIFIED-BY-OPERATOR-VOUCH (07-UAT.md test 1, operator's typed vouch, result: pass)"
    - "07-04 backstop — live GAL-02 handoff ran to SUCCESS with the user present: VERIFIED-BY-OPERATOR-VOUCH (07-UAT.md test 1, covering both live events; test 2's machine half cross-checked run 157256d45c81e7000 leg-by-leg)"
    - "Judgment-tier prohibition review (10 items): resolved by 07-UAT.md test 3 — five verified mechanically (ledger holds all 8 records incl. the 3 D-14 history keys, listener PIDs continuous, zero per-key duplicates, edit trail = public git log, every go tied to a recorded operator reply); the memory-resting negatives folded into test 1's single vouch"
    - "H-01 / H-02 review triage: resolved fix-now by 07-UAT.md test 4 — commit ff8aac6 rewrote the runbook exemption wording (H-01) and made the fallback lock-probe interpreter corroborate the service venv core's default_lock_dir, refusing uncorroborated probes `forbidden:` fail-closed (H-02, closing L-03's promised line class); re-proven live by this verifier (see spot-checks)"
  gaps_remaining: []
  regressions: []
warnings:
  - "NEW (found by this re-verification 2026-11-03T07:21-07:44Z, after the phase evidence window): the live ledger at ~/.local/state/galago-tools/stack/stack-ledger.json now holds 15 records (the verified 2026-11-03T06:16Z snapshot held 8). Four unrecorded post-phase GAL-02 runs (06:58:11Z, 07:11-07:15Z keys 7c17a721-in/85bf4fa2-in1/e46a27ec-in1 - all failed, and a second two-plate run d1626a4b at 07:22:06Z whose in1/in2/out1 legs ran and whose out2 leg FAILED smartAlignmentMaxNumRetry errorCode 15 at 07:24:33Z) appear in NO findings row, NO go-gate record and NO phase artifact (grepped the whole repo for the key fragments: zero matches). They queued the same protocol id 15 through the galago-web queue. The recorded phase events are untouched and remain verified; this is post-phase host activity outside the supervised phase sessions."
  - "NEW (consequence of the above): at verification time the STACK tool server (:40012) holds a live failure latch — fast_status :40012 error_message 'stack: failed; latched guid 4f1c93e5-b68f-40b9-aedf-6cc07bdfc9d8' — and the last logged ExecuteCommand answered ERROR_FROM_TOOL (07:24:51Z). D-11 recovery (physical arm inspection, acknowledge in the manager UI at 10.150.1.125:5005 with the guid and the literal yes) is OUTSTANDING and needs an operator, with the outcome recorded in a findings row. The core's fail-closed design held under it exactly as designed: no motion after the failure, the stuck attempt refused with the latch wording, ledger untouched, nothing deleted — corroborating T-07. But nobody has triaged it on the recorded record yet."
  - "Carried: deferred-items.md still marks the owner-lock probe item `status: open` — the fix landed in 07-03 (commit 9344957) and was live-verified again today (gate exits 0, galago-holder ok line). Stale record; informational only."
  - "Carried: the 16-attempt-line accounting in row 3a-3 enumerates 15 components (1+5+1+2+4+2); 07-SECURITY.md's Threat Flags re-explanation has the same one-component gap. The total (16) and the four leg timestamps match the raw log exactly; only the prose enumeration is off by one. Note the log now holds 25 Transfer lines total (9 more from the post-phase 06:58-07:24Z activity above) — any new accounting must be against a fresh baseline."
  - "Carried: ROADMAP.md still shows the Phase-7 top-level checkbox unchecked while its three success criteria and REQUIREMENTS.md rows (LIVE-08/09/10 Complete) are met."
  - "Carried: live Transfer duration 27 s is below the 30-32 s expected band — recorded honestly in rows 2a-2/2a-3 as observed-vs-estimate, not asserted as in-band."
---

# Phase 7: Deploy & Supervised Live STACK + Handoff — Verification Report (regenerated)

**Phase Goal:** The STACK tool is deployed in the safe order and proven on the real STACK: a supervised live Transfer, then a supervised live STACK -> F.A.S.T. -> STACK handoff, with the user present.
**Verified:** 2026-11-03T07:44:30Z
**Status:** passed (canonicalized: UAT 4/4 recorded in 07-UAT.md; operator vouch is the recorded evidence for the two presence truths; review triage fix-now committed)
**Re-verification:** Yes — after gap closure (UAT + security audit) and after the covered inputs changed (commits ff8aac6, 2f7becc/11bacd4/3b033b9, ecf424e)

## Goal Achievement

### Method note (evidence class)

LIVE-08/09/10 are manual-recorded-evidence requirements by design (07-RESEARCH Validation Architecture). The verifier's own reach is therefore: every file, code, test-gate and regression must-have checked directly on disk/live host this run; every live-fact truth checked through the recorded artifacts in the runbook's 13-row findings log **plus independent corroboration** (ledger file, tool logs, live gate run, live API reads); the two operator-presence truths now carry the **operator's typed vouch recorded in 07-UAT.md test 1** (result: pass) — per the plans' backstop semantics, the vouch itself is the recorded evidence class, so these are VERIFIED-BY-OPERATOR-VOUCH rather than human_pending.

### Changes since the previous verified report (regeneration delta)

1. **Commit ff8aac6 (H-01/H-02/L-03 fix-now):** `docs/runbooks/gal-07-live-check.sh` gained an +18-line corroboration branch (lines 108-122): when the chosen lock-probe interpreter is a host fallback rather than the service venv's python, its `default_lock_dir()` must equal the service-venv core's — mismatch or unresolvable → `forbidden: … uncorroborated … (review H-02)` and failed=1. `docs/runbooks/gal-07-live-handoff.md` Safety rules (lines 20-25) and Pre-flight text (lines 51-58) now name the foreign owner classes (mcp/stack-mcp/unknown), the galago-holder exemption (9344957) and the corroboration clause (H-01); the `forbidden:` line class the runbook and BLOCKED footer always promised now actually exists (L-03 closed). Test file unchanged by this commit.
2. **UAT completed 4/4 (07-UAT.md):** test 1 operator's typed vouch covers both live events' presence and the typed gos; tests 2/3/4 carry `source: automated` / `automated corroboration` / `automated fix` notes.
3. **07-SECURITY.md added:** verdict SECURED, threats_open 0, 8/8 mitigations MITIGATED_VERIFIED with file:line citations (T-07-10..16 + the install-surface register T-07-SC + the ledger-replay spot-check); spot-verified against the actual sources by this verifier (line numbers checked: gate corroboration 108-122, check 3 at 187-201, check 6 at 223-245, checks 7-8 at 247-298; runbook citations present).

### Covered must-haves table (per-item verdicts)

**07-01 — pre-flight gate + runbook + falsification tests (LIVE-08 scriptable half)**

| # | Truth | Status | Evidence (re-checked this run) |
|---|-------|--------|----------|
| 1 | Gate exits 0 only when every live precondition holds (identity, lock, core pin, DEP-02 gate re-run, web bundle, D-12 store with byte-exact host, no RUNNING run, credentials) | VERIFIED | `python3 -m pytest tools/tests/gal07_live_runbook_test.py` → 15 passed, 82 subtests (run by this verifier today, 23.3 s); live gate run exit 0, last line `PREFLIGHT OK` with the galago-holder `ok:` line (pid 4004972) |
| 2 | Every check runs after one fails (no `set -e`); last line is `BLOCKED:` remedy (exit 1) or `PREFLIGHT OK` | VERIFIED | Script structure (failed accumulator, `set -u` only, footer line 304); both verdict shapes asserted by the green matrix |
| 3 | Held lock refused with verbatim StackOwnedError wording naming the holder, probed through the pinned core's own `endpoint_key`/`lock_path`/`default_lock_dir` | VERIFIED | Held-lock flock fixture test green (`held_lock` case); probe imports the core's owner_lock helpers (gate lines ~127-135) |
| 4 | (backstop) Gate fails closed on empty/non-JSON identity/store/runs responses and an unresolvable probe python | VERIFIED | Degenerate-input matrix green; probe-python absence prints its own `missing:` (gate 104-107) — re-checked in source |
| 5 | Runbook exists with Safety rules / Pre-flight / Part 1 / Part 2 / Part 3 / Recovery drill / Findings log in order; typed-go gates with UTC, never-delete clauses, manager-UI-first recovery, 600 s replay rule all pinned | VERIFIED | TestRunbookContent pins green; 13 findings rows G0, 1a-1..6, 2a-1..3, 3a-1..3 present; `Reply: literal go` count == 3 (asserted today); H-01 text rewrite keeps every pinned phrase intact |
| 6 | `docs/runbooks/gal-02-handoff.md` byte-unchanged and its 10.150.1.125 refusal remains in force (D-07) | VERIFIED | `git status --porcelain` pristine this run; untouched by ff8aac6 (stat: gate + runbook + disposition only) |

**07-02 — deploy in the safe order (LIVE-08)**

| # | Truth | Status | Evidence (unchanged by the delta commits; re-read today) |
|---|-------|--------|----------|
| 1 | Install source is the user's explicit decision in row 1a-1, never a silent fallback | VERIFIED | Row 1a-1 local-clone-waiver with clone HEAD == pin verification |
| 2 | Core installed into the service .venv at 934a621 via direct_url.json, stack_test green | VERIFIED | Gate check 3 passes live today (asserted from direct_url.json == 934a621ece116a8b263897c1e9b62b57374f4ef3); row 1a-2 stack_test 271 OK |
| 3 | Credentials reach the tool server only via the operator's 0600 env file; values appear nowhere | VERIFIED (mechanical) | Recorded in row 1a-3 presence-only; no credential-value regex hits (test green; `STACK_(USER\\|PASSWORD)=` pin intact) |
| 4 | Every restart preceded by a timestamped backup; listener PIDs re-baselined | VERIFIED (recorded) | Row 1a-4 backup pre-gal07-20261102T112327Z, MainPID 1940146→3973399, ss re-baseline |
| 5 | Safe order proven by four strictly-increasing UTC timestamps in row 1a-6 | VERIFIED | 11:20:00Z < 11:24:34Z < 12:18:28Z < 01:31:16Z(+1d) |
| 6 | After reconnect the store holds both a stack and a fast tool; D-12 passes; stack2-6 idle | VERIFIED | Live `/api/tools` today: fast FA100056 + stack STACK2-6, config.host byte-exact `10.150.1.125`; gate check 6 passes live |
| 7 | galago-web runs a new image ≠ rollback anchor, /api/health 200, bundle exports Command_Transfer | VERIFIED | Live `/api/health` = `{"status":"ok"}` today; row 1a-6 image sha256:2f609032… ≠ anchor 938217230697 |

**07-03 — supervised live Transfer (LIVE-09)**

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | LIVE-09 pre-flight with GAL07_REQUIRE_STACK_ENV=1 ended PREFLIGHT OK before the event; typed go recorded in row 2a-1 with UTC; no auto-advance | VERIFIED (recorded; gate live-verified) | Row 2a-1: PREFLIGHT OK both forms at 03:13:42Z, re-gate 03:47:58Z, operator go 03:51:07Z; live gate re-run today exit 0 |
| 2 | Transfer parameters chosen reads-first, not hardcoded | VERIFIED (recorded) | Row 2a-2 carries the read-derived values (nest-1/deck1/A1 → nest-2/"deck`"/A1, profile Default, 55 s estimate) |
| 3 | Exactly one live Transfer submitted, reached `ran` on stack2-6: SUCCESS reply, ledger state done, exactly one `Running command Transfer` for the event | VERIFIED (live-corroborated) | Ledger record `GAL07-LIVE9-20261103T035107Z state done/ran (verified today on disk); row 2a-3 count baseline(0)+1 |
| 4 | transfer_duration_s within bounds; expected hardware duration recorded as the observation baseline | VERIFIED | 27 s within 0<t≤3600; 55 s estimate vs 27 s actual recorded honestly (see carried warning) |
| 5 | (backstop) reached `ran` **with the user present** | VERIFIED-BY-OPERATOR-VOUCH | 07-UAT.md test 1: operator's typed vouch at the UAT checkpoint for BOTH live events, result pass; motion facts triple-corroborated (ledger, STACK2-6.log one 03:57:58Z line, runbook rows) |

**07-04 — supervised live GAL-02 handoff (LIVE-10, as amended by D-14)**

The plan's 07-04 must_haves note is the recorded D-14 amendment (truth 3): the live trap runs the TWO-PLATE cycle — 4 STACK legs + 1 F.A.S.T. liquid leg (deck 5→6), 4 per-run minted keys — verified against the recorded evidence rows 3a-1..3a-3.

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | LIVE-10 pre-flight + D-12 pre-store check passed before the event; typed go recorded in row 3a-1 with UTC | VERIFIED (recorded; gate + store live-verified today) | Row 3a-1 gate evidence incl. galago single-owner probe ok; live /api/tools holds both tools host byte-exact; live gate exit 0 today |
| 2 | One GAL-02 run (numberOfRuns 1, reads-first params) completed all tool legs to SUCCESS — as amended: 4 STACK legs + one F.A.S.T. liquid leg (deck 5→6) | VERIFIED (live-corroborated) | Ledger (verified today): keys …-127473f5-in1/in2/out1/out2 all state done/ran; STACK2-6.log leg lines 05:40:15/05:40:46/05:42:31/05:43:02Z; FA100056.log `Running command Transfer` 05:41:16Z, fast run progress 0→100% |
| 3 | LIVE-10 D-14 amendment recorded: two-plate shape replaces the plan's three-leg sim shape; one ledger record + one log attempt line per leg | VERIFIED | Amendment in 07-04-PLAN truth 3 + rows 3a-1/3a-3; protocol history documented in row 3a-1 |
| 4 | Each STACK leg submitted exactly once; F.A.S.T. submission evidence in its own tool log | VERIFIED (live-corroborated) | One ledger record per key, no duplicate fingerprints; four leg log lines each once; the run-store run 157256d45c81e7000 cross-checked leg-by-leg by UAT test 2's machine half |
| 5 | A FAIL row / ambiguous outcome / mid-run anomaly stopped the session at a blocking-human checkpoint; evidence never edited to pass | VERIFIED (recorded) | Rows 1a-5 (swapped-ports D-14 repair), 3a-1/3a-3 (two movementError attempts, keys KFT as D-14 history); fix was the operator's physical adjustment, not a re-send; findings rows unchanged since the event (git history) |
| 6 | (backstop) ran to SUCCESS **with the user present** | VERIFIED-BY-OPERATOR-VOUCH | 07-UAT.md test 1 (single vouch covering both events); test 2's automated machine half cross-checked the run store; motion triple-corroborated |

**Score: 24/24 truths verified** (22 previously verified + 2 presence truths now VERIFIED-BY-OPERATOR-VOUCH per the recorded UAT evidence; 0 behavior-unverified, 0 overrides)

### Requirements traceability

| Requirement | Source plans | Verdict | Evidence |
|-------------|--------------|---------|----------|
| LIVE-08 | 07-01, 07-02 | SATISFIED | Safe order (four-timestamp proof), lock probe verified incl. the galago exemption and (new) corroboration fail-closed, both front ends byte-exact `10.150.1.125` in the store. REQUIREMENTS.md line 81 `[x]`, traceability row Complete |
| LIVE-09 | 07-03 | SATISFIED | ran verified mechanically; presence recorded by the operator's typed UAT vouch. REQUIREMENTS.md line 85 `[x]`, Complete |
| LIVE-10 | 07-04 | SATISFIED | Two-plate D-14-amended shape verified mechanically (4+1 legs, 4 fresh keys done/ran); presence recorded by the same vouch. REQUIREMENTS.md line 87 `[x]`, Complete |

No orphaned REQUIREMENTS IDs for Phase 7; all three are claimed by plans (`requirements:` frontmatter) and present in REQUIREMENTS.md traceability.

### Review-findings triage state (07-REVIEW 11 findings)

- **H-01 fixed** (ff8aac6): runbook lines 20-25/51-58 now name the foreign owner classes, the galago exemption and the corroboration clause exactly as pinned — read in full this run; consistent with the gate (gate lines 160-166 exemption, 108-122 corroboration).
- **H-02 fixed** (ff8aac6): corroboration branch verified in source and **re-proven live twice by this verifier** (fake-venv `GALAGO_SERVICES_VENV` → gate exit 1, `forbidden: the fallback lock-probe interpreter … is uncorroborated … (review H-02)` followed by `BLOCKED:`; real host unaffected → PREFLIGHT OK).
- **L-03 closed** by H-02: the promised `forbidden:` class is emitted (seen in the reproduction above).
- **M-01 + 7 lows open** in the advisory ledger (07-REVIEW-DISPOSITION.md, unfixed by design pending a `--fix` pass): M-01 divergent-host stack tool passes check 6 (any-of not all-of), L-01 multi-doc runs body, L-02 duplicate STACK_USER assignment, L-04 dist-info ordering, L-05 stack-mcp test pin, L-06 stale-record trial pin, L-07 credential-leak regex gaps, L-08 galago-exemption trust boundary. All are advisory-grade hardening items; none re-verified as a live blocker this run.

### Security audit (07-SECURITY.md) spot-verification

The audit's verdict (SECURED, threats_open 0) was not taken on faith: its central citations were cross-read this run — gate corroboration at 108-122 (matches), check 3 at 187-201, check 6 at 223-245, runs check fail-closed at 247-267, credentials at 269-298 (all match the actual script); ledger-replay citations point at `tools/stack/ledger.py` REPLAY_WINDOW_S 600.0 and the `tools/stack/server.py` refusal wording; the D-14 two-plate surface is correctly classified a recorded deviation, not an unregistered threat. The audit's own observational note (the fallback-corroboration branch not exercised by the fixture matrix) is answered by this verifier's live fake-venv reproduction above — the branch fails closed exactly as coded.

### Behavioral spot-checks (run this run, 2026-11-03T07:35-07:44Z)

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Gate falsification module | `python3 -m pytest tools/tests/gal07_live_runbook_test.py -q` | 15 passed, 82 subtests, 0 skipped | PASS |
| Live gate verdict | `bash docs/runbooks/gal-07-live-check.sh` | exit 0, last line `PREFLIGHT OK`; galago-holder `ok:` line (pid 4004972) | PASS |
| H-02 fail-closed direction | fake venv (probe falls back to the host python) | exit 1, `forbidden: … uncorroborated … (review H-02)` then `BLOCKED:` | PASS |
| Real host through the primary path | gate re-run unperturbed after the fake-venv trial | PREFLIGHT OK | PASS |
| Store state (D-12) | `curl /api/tools` | fast FA100056 + stack STACK2-6, config.host byte-exact 10.150.1.125 | PASS |
| Service/web health | `curl /api/health` | {"status":"ok"} | PASS |
| Ledger (LIVE-09 + LIVE-10 + D-14 history) | python read of stack-ledger.json | LIVE9 key + 4 leg keys done/ran; 4 fresh per-run keys intact; 3 movementError keys preserved | PASS |
| Current latch state | `scripts/fast_status.py --port 40012` | latched guid 4f1c93e5 from the OUT-OF-PHASE 07:22Z run — see NEW warning (out-of-scope for the phase's own must-haves; core behaved fail-closed) | INFO |
| D-07 regression | gal-02-handoff.md unchanged | pristine in git status | PASS |

Phase regression module re-run note: the phase-scoped gal07 module (15 tests) was re-run by this verifier; the full gate (`bin/make proto test`, 581 passed) was last run at ff8aac6 per its commit message and 07-UAT.md test 4 — not re-run here (single-run rule; the phase-scoped modules are the discriminators).

### Probe Execution

No `scripts/*/tests/probe-*.sh` probes declared for this phase (the gal-07 gate and its test module are the scripted checks themselves).

### Human Verification Required

**None outstanding for the phase's own must-haves.** The previous report's four human items are all closed on the recorded record:
1. LIVE-09/LIVE-10 presence-and-vouch — 07-UAT.md test 1 (operator's typed vouch, pass).
2. Queue-rows-vs-UI reconciliation — 07-UAT.md test 2 (automated machine half).
3. Judgment-tier prohibitions — 07-UAT.md test 3 (5 verified mechanically, remainder folded into test 1's vouch).
4. H-01/H-02 triage — 07-UAT.md test 4 (fix-now, ff8aac6).

**Operator follow-ups surfaced by this re-verification (host state, outside the phase's recorded must-haves — tracked by Warnings, not blocking the phase):**
1. **Recover the latched failure per D-11:** physical arm inspection, then clear via the manager UI at http://10.150.1.125:5005 with guid 4f1c93e5-b68f-40b9-aedf-6cc07bdfc9d8 and the literal yes (AcknowledgeFailure from the STACK tool page is the fallback) — then record the outcome in a findings row.
2. **Reconcile the four unrecorded post-phase GAL-02 runs** (06:58–07:24Z ledger keys) in a findings row or another recorded artifact, so every live motion stays attributable on the recorded record.

### Gaps Summary

**None for the phase goal.** The phase goal — deployed in the safe order (LIVE-08), then a supervised live Transfer reaching `ran` (LIVE-09), then a supervised live STACK → F.A.S.T. → STACK handoff to SUCCESS under the recorded D-14 two-plate amendment (LIVE-10) — is met and independently corroborated this run with the changed inputs folded in: the H-01 runbook text now matches the gate's exemption exactly, the H-02 corroboration is in the gate and re-proven fail-closed live, L-03's promised line class exists, the UAT record closes every human item with the operator's vouch as recorded evidence, and the security audit holds up on spot-check. Requirements LIVE-08/09/10 are Complete in REQUIREMENTS.md with the phase's success criteria all evidenced.

The one material NEW finding of this re-verification is out-of-phase host activity: four unrecorded post-phase GAL-02 queue runs (06:58–07:24Z), one of which left a live failure latch pending operator recovery. They do not retro-flunk any phase must-have (the recorded events and the never-edit evidence rule stand; the core's fail-closed design demonstrably held under the failure), but they are loudly carried in `warnings` above rather than absorbed.

---

_Re-verified: 2026-11-03T07:44:30Z_
_Verifier: the agent (gsd-verifier)_
