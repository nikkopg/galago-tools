---
phase: 06-gal-02-workflow-simulated-workcell-pac-simulator-run
verified: 2026-11-02T05:00:00Z
status: human_needed
score: 5/6 must-haves verified
covered_files:
  - ".planning/phases/06-gal-02-workflow-simulated-workcell-pac-simulator-run/06-01-PLAN.md"
  - ".planning/phases/06-gal-02-workflow-simulated-workcell-pac-simulator-run/06-01-SUMMARY.md"
  - ".planning/phases/06-gal-02-workflow-simulated-workcell-pac-simulator-run/06-02-PLAN.md"
  - ".planning/phases/06-gal-02-workflow-simulated-workcell-pac-simulator-run/06-02-SUMMARY.md"
  - ".planning/phases/06-gal-02-workflow-simulated-workcell-pac-simulator-run/06-03-PLAN.md"
  - ".planning/phases/06-gal-02-workflow-simulated-workcell-pac-simulator-run/06-03-SUMMARY.md"
  - ".planning/phases/06-gal-02-workflow-simulated-workcell-pac-simulator-run/06-04-PLAN.md"
  - ".planning/phases/06-gal-02-workflow-simulated-workcell-pac-simulator-run/06-04-SUMMARY.md"
  - "docs/runbooks/gal-02-dep02-check.sh"
  - "docs/runbooks/gal-02-handoff.md"
  - "docs/runbooks/gal-02-handoff.protocol.json"
  - "tools/tests/gal02_handoff_test.py"
  - "tools/tests/gal02_harness.py"
  - "tools/tests/gal02_replay_test.py"
  - "tools/tests/gal02_runbook_test.py"
covered_digest: "v3:sha256:499a8e2d33ca8ef3ac497febd01b95ba604deb6b52960e5724282baff0b85531"
behavior_unverified: 0
overrides_applied: 0
human_verification:
  - test: "Open the STACK tool page for a real-mode STACK tool in the dev galago-core (:3020), open the transfer form for a completed GAL-02 in-leg, leave the optional fields (source_transfer_profile, destination_transfer_profile, timeout_s) blank, and re-send it with the stored step_key inside the 600 s replay window (needs a fresh run, the 156f9e5c3701e7000 window is long past)."
    expected: "The form delivers the blank optionals as unset (absent, empty string, or timeout_s 0) and the re-send replies SUCCESS with replayed true and the same task guid, not a fingerprint-mismatch refusal. The manager submit counter stays unchanged."
    why_human: "Plan 06-04 tagged this truth verification:backstop. Both Part 2a and Part 2b re-sends were sent by the orchestrator through tRPC tool.runCommand with params copied byte-exact, so the real tool-page form's blank handling was never exercised in this phase. The adapter side is covered offline (test_redispatch_tool_page_resend_with_blank_optionals_replays passes), and galago-core controller code for the page form changed at 04:03-04:08Z (commits 2ca4e4e, debc038, a127fb2) between the 2a and 2b runs. Low risk to the goal, but not observed."
---

# Phase 6: GAL-02 Workflow, Simulated Workcell & PAC-Simulator Run Verification Report

**Phase Goal:** The STACK -> F.A.S.T. -> STACK plate handoff runs end to end in simulation, and a forced re-dispatch of a completed STACK step is shown to send no second transfer, with no real instrument involved.
**Verified:** 2026-11-02
**Status:** human_needed
**Re-verification:** No, initial verification

## Verdict

The phase goal is achieved. All four ROADMAP success criteria are VERIFIED against code and independently re-read live state. The only `human_needed` item is one plan-level `backstop` truth (real tool-page blank-field handling) that was never observed. It does not weaken the goal. No FAILED truths and no BLOCKERs.

## Goal Achievement

### Observable Truths

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | SC1: script-mode GAL-02 protocol exists as importable JSON beside its runbook; mints per-run `step_key` for each STACK step, nest/hotel triples are parameters, runs STACK -> F.A.S.T. -> STACK | ✓ VERIFIED | `docs/runbooks/gal-02-handoff.protocol.json` exists next to `gal-02-handoff.md`; `mode: script`, 3028-char `scriptContent`, 27 parameters, `commands: []`. I read the script: key base is label(20 cp) + ISO timestamp + 8 hex, legs suffixed `-in`/`-out`, out leg is the in leg swapped, all required inputs go through `need()`, emits note, STACK transfer, F.A.S.T. transfer, STACK transfer. Live dev galago (`GET /api/protocols`) lists protocol 2, mode script, scriptContent 3028. Stored run rows (`GET /api/runs`) show the keys `...-0cb7fd09-in/-out` and `...-b7ffcec0-in/-out` and the swapped triples. 45 gal02 tests pass (below). |
| 2 | SC2: fully Galago-simulated workcell run (both tools simulated) completes all three steps | ✓ VERIFIED | Run `156f910fe281e7000` (stored rows confirmed via `GET /api/runs/...`). Tool logs: STACK-SIM config `simulated: true`, Transfer in 10:50:09-10:50:44 SUCCESS, FAST-SIM Transfer 10:50:46-10:52:06 SUCCESS, STACK-SIM out 10:52:07-10:52:42 SUCCESS, in order (local time, UTC+7, equals the Findings 03:50-03:52Z). `ls ~/.local/state/galago-tools` holds only `stack-sim` (no `stack-galago-simulated`, no `stack`), consistent with simulated mode writing no ledger. Deviation `FAST-SIM` name is justified (dev DB already holds real tool `Fast`, id 1, verified in `GET /api/tools`). |
| 3 | SC3: forced re-dispatch of a completed STACK step sends no second transfer; proven offline on a fake core (submit count stays 1) and re-exercised in a simulated run | ✓ VERIFIED (judged per D-07) | Offline: `gal02_replay_test.py::TestGal02Redispatch` (7 tests, pass). Replay returns SUCCESS with meta keys exactly `stepKey, ledgerState, result, replayed`, `execute_calls` stays 1, `plan_transfer` once, late send refused "step key already completed ... nothing was sent", Refused releases key then exactly one accepted submit, blank optionals still replay, byte-exact key equality. Simulated half: re-dispatch at 10:53:33 replied SUCCESS (35 s sleep) and no ledger exists; STACK-SIM log has exactly 3 `Running command Transfer`. This half is credited only with "survives a re-dispatch through the real queue and writes no ledger", as D-07 and the runbook's "What each part proves" table state verbatim. It is not over-credited; the no-second-transfer proof rests on the offline test plus SC4. |
| 4 | SC4: operator-run GAL-02 with STACK in real mode against the loopback PAC simulator and F.A.S.T. simulated completes, incl. a forced re-dispatch with no second POST; never targets 10.150.1.125 / stack-server | ✓ VERIFIED | See "FLOW-04 evidence" below. Counter calibrated (+1 on in leg, +1 on out leg, +0 on both re-sends); ledger holds two `done` records whose guids match the Findings; stored run rows confirm STACK-PACSIM real tool; no hardware host appears anywhere. |
| 5 | 06-04 plan truth (`verification: backstop`): post-DEP-02 tool-page transfer form delivers blank optional fields as unset so the re-send replays | ? UNCERTAIN (insufficient_spec) | Re-sends were issued via tRPC `tool.runCommand`, params byte-exact from stored queueId 13, with blanks omitted. The real tool-page form was never driven. Abstain per backstop rule; routed to Human Verification. |
| 6 | 06-02 plan truth: read-only DEP-02 gate prints `DEP-02 OK` only when all conditions hold; fixture trees prove it cannot pass falsely | ✓ VERIFIED as phrased, with WARNING (CR-01) | I ran the gate: last line `DEP-02 OK`, exit 0 (galago-core HEAD now 370b40e). `TestDep02Gate` (7) pass. I confirmed by hand the real `commandFields.stack` block begins with a `transfer:` key (line 2) and has no `acknowledge`. CR-01 is real, but only for a decoy case the fixtures do not model (see Anti-Patterns). |

**Score:** 5/6 truths verified (0 present-but-behavior-unverified, 1 uncertain)

### FLOW-04 evidence (independently re-read)

| Check | Result |
| ----- | ------ |
| Submit counter `count-submits.sh` | reads `2` |
| Manager `POST /api/v2/transfer` entries (read-only `docker logs stack-sim-manager`) | exactly two, at 04:18:56.516Z (in leg) and 04:20:41.562Z (out leg), matching the Findings |
| Anything at 04:21:33Z (in-window re-send) or 04:29:40Z (late re-send) | none. Not even a `/api/v2/transfer/estimation` call, so the replay short-circuited before any planning. The counter is calibrated by the +1 on the in leg, so the +0 is falsifiable |
| Tool log gal02-stack-pacsim.log | 4 `Running command Transfer` (2 legs, 2 re-sends), 1 `Received configuration`; re-send 1 = SUCCESS in same second, re-send 2 = ERROR_FROM_TOOL "step key already completed ... nothing was sent" |
| Ledger `~/.local/state/galago-tools/stack-sim/stack-ledger.json` (read-only) | version 1, exactly 2 records, both `state: done`, result `ran`, guids `1fcb9340-...` (in) and `0e253706-...` (out), identical to Findings 2b-2/2b-3; in leg is sim-A1 -> sim-B1, out leg swapped. File not modified or deleted |
| Sim manager | `127.0.0.1:15005->5005` only, `Stack manager 0.12.0-beta.1+1157`, `automated`, robots `[sim-arm-1 idle]` only |
| Hardware targeting | `grep` of the gal06 logs and configs for `10.150.1.125` / `stack-server` is empty. In the repo, the strings appear only as deny-sets (harness `HARDWARE_DENY`, test assertions, the runbook safety line and refusal preflight `REFUSED:` case). Dev galago `GET /api/tools` lists STACK-SIM (host.docker.internal:40010), STACK-PACSIM (:40012), FAST-SIM (:40011) and the pre-existing localhost `Fast`. No tool points at the real STACK. Production galago-web :3010 is up and untouched |

### Part 1 automated gate (D-16c)

| Command | Result |
| ------- | ------ |
| `pytest tools/tests/gal02_handoff_test.py gal02_replay_test.py gal02_runbook_test.py -q -rs` (node on PATH) | 45 passed, no skip lines (0 skipped, as D-16c requires) |
| `pytest tools -q -rs` | 555 passed, no skip lines |
| `git diff --quiet 477b0ed -- tools/stack tools/fast tools/base_server.py interfaces requirements.txt` | exit 0 (frozen adapter, protos and requirements unchanged) |

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `docs/runbooks/gal-02-handoff.protocol.json` | script protocol, 27 params | ✓ VERIFIED | exists, substantive, imported live, used by 2 runs |
| `docs/runbooks/gal-02-handoff.md` | runbook + Findings log G0, 2a-1..2a-3, 2b-0..2b-5 | ✓ VERIFIED | all 10 rows present and PASS; D-07 sentence present in "What each part proves" |
| `docs/runbooks/gal-02-dep02-check.sh` | read-only gate | ✓ VERIFIED (CR-01 warning) | runs, exit 0 / `DEP-02 OK` |
| `tools/tests/gal02_harness.py` | node stub runner | ✓ VERIFIED | used by all three test modules |
| `tools/tests/gal02_handoff_test.py` | FLOW-01 matrix | ✓ VERIFIED | 23 tests pass |
| `tools/tests/gal02_replay_test.py` | FLOW-03 offline proof | ✓ VERIFIED | 7 tests pass, uses real `StackServer` on fake core, imported `REPLAY_WINDOW_S` from `tools.stack.ledger` |
| `tools/tests/gal02_runbook_test.py` | gate + content tests | ✓ VERIFIED | 15 tests pass |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `gal02_harness.load_export` | protocol JSON | committed file path | WIRED | tests read `scriptContent`/defaults from the file |
| `gal02_replay_test` | `tools/stack/server.py` Transfer + ledger | `ParseDict` into `stack_pb2.Command.Transfer`, in-process gRPC | WIRED | replayed/accepted counts asserted |
| runbook Part 2 gate | `gal-02-dep02-check.sh` | `bash docs/runbooks/gal-02-dep02-check.sh` | WIRED | recorded in G0 and 2b-0; re-run here, OK |
| protocol `stackLeg` | `stack.proto` Command.Transfer | proto field names | WIRED | `ParseDict` + `_check_args` tests pass |
| STACK-PACSIM re-send | `Ledger.decide` REPLAY | same step_key + fingerprint in 600 s | WIRED (live) | reply `replayed true`, no manager POST |
| sim counter | rows 2b-1 / 2b-3 | +1 calibration before +0 | WIRED (live) | confirmed from manager log |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| protocol script -> galago queue | step-key params | `galago.command` at queue time, stored in run rows | stored rows contain real keys and swapped triples | ✓ FLOWING |
| STACK-PACSIM -> PAC sim | transfer submit | `POST /api/v2/transfer` on the manager | 2 real submits, 2 ledger records | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Gate on real sibling tree | `bash docs/runbooks/gal-02-dep02-check.sh` | `DEP-02 OK`, exit 0 | ✓ PASS |
| Replay never submits twice (named tests) | `pytest tools/tests/gal02_replay_test.py -rs` (within the 45) | pass | ✓ PASS |
| Submit counter | `count-submits.sh` | `2` | ✓ PASS |
| Sim manager state | GET `/api/v3/info/manager-state`, `/robot-state` | `automated`, `sim-arm-1 idle` | ✓ PASS |
| WR-01 reproduction | run script with `fast_step_num_rows=0`, `tip_reuse=fresh2`, `source_deck=99` | all emit 4 calls (not rejected) | confirms WR-01 |
| CR-01 reproduction | scratch fixture with only `list_transfer_profiles`/`get_transfer_estimate` in the stack block | gate check 4 passes (false OK) | confirms CR-01 |

### Probe Execution

SKIPPED: the phase declares no `probe-*.sh`. The DEP-02 gate script was run as a gate (above).

### Requirements Coverage

Plan frontmatter IDs: 06-01 [FLOW-01, FLOW-03]; 06-02 [FLOW-01, FLOW-02, FLOW-03, FLOW-04]; 06-03 [FLOW-02, FLOW-03]; 06-04 [FLOW-04, FLOW-03]. All four are defined in REQUIREMENTS.md and mapped to Phase 6. No orphaned requirement IDs.

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| FLOW-01 | 06-01, 06-02 | script-mode GAL-02 protocol as importable JSON beside its runbook, per-run step_keys, nest triples as parameters | ✓ SATISFIED | SC1 evidence. Bookkeeping: REQUIREMENTS.md still shows `- [ ] **FLOW-01**` and traceability `FLOW-01 \| Phase 6 \| Pending`, while FLOW-02..04 are already `[x]`/Complete. The summaries claim FLOW-01 complete and the code supports it, so the orchestrator should tick it on phase completion. |
| FLOW-02 | 06-02, 06-03 | fully Galago-simulated run completes all three steps | ✓ SATISFIED | SC2 evidence |
| FLOW-03 | 06-01, 06-02, 06-03, 06-04 | forced re-dispatch of a completed STACK step sends no second transfer, offline and in a simulated run | ✓ SATISFIED | offline fake-core proof (the substantive proof) plus simulated half credited per D-07 plus FLOW-04 live corroboration |
| FLOW-04 | 06-02, 06-04 | real-mode STACK vs loopback PAC sim, F.A.S.T. simulated, forced re-dispatch with no second POST, never hardware | ✓ SATISFIED | FLOW-04 evidence table |

### Anti-Patterns Found

No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK` markers in any file this phase created. No stubs.

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `docs/runbooks/gal-02-dep02-check.sh` | 67-72 | CR-01: `grep -q 'transfer'` over the whole stack block matches `list_transfer_profiles` / `get_transfer_estimate`; awk range can spill past a one-line `stack: {...},` | ⚠️ Warning (review rated Critical) | Gate can print a false `DEP-02 OK`. Does not defeat a must-have: the roadmap SCs do not mention the gate; the 06-02 truth holds for the fixtures it defines; on this run the OK was true (verified by hand: real block has `transfer:` at its second line, no `acknowledge`; commandFields vitest 5/5 recorded in G0; STACK commands ran through the generated forms/queue). Fix before relying on the gate again (Phase 7). |
| `docs/runbooks/gal-02-handoff.protocol.json` | scriptContent | WR-01: F.A.S.T. `deck`, ids, cols, rows, row letters and `tip_reuse` are not validated in the script (reproduced: `num_rows=0`, `tip_reuse=fresh2`, `source_deck=99` all emit 4 calls) although the header comment claims all inputs are validated | ⚠️ Warning | Does not defeat 06-01's validation truth (that truth lists blank, non-whole, and volume/timeout <= 0, all of which throw). Real operational risk for Phase 7: a bad F.A.S.T. value fails after the STACK in leg has moved the plate. Fix before hardware runs (`/gsd-code-review 6 --fix`). |
| `docs/runbooks/gal-02-handoff.md` | Findings row 2b-0 | Stale claim: "controller unchanged since a5fa75f". galago-core `controller/` changed in commits 2ca4e4e, debc038, a127fb2 (04:03-04:08Z, before the 2b Configure at 04:17Z): `commandParams.ts`, `pages/tools/[id].tsx` (tool-page form blank/boolean coercion) and tests. The same-checkout bind mount means 2b ran with that code | ℹ️ Info | The runs used the script queue and tRPC `runCommand`, not the changed tool-page form, so the evidence is unaffected. Row 2b-0 wording should be corrected, and it feeds the human item above. |
| WR-02..WR-05, IN-01..IN-05 | n/a | open in 06-REVIEW-DISPOSITION.md | ℹ️ Info | advisory, none touches a roadmap SC |

### Human Verification Required

### 1. Real tool-page re-send with blank optionals

**Test:** On a fresh real-mode (or any) STACK run in the dev galago-core, open the STACK tool page transfer form, populate it from a just-completed in-leg, leave the optional fields blank, and re-send inside the 600 s window.
**Expected:** Reply SUCCESS with `replayed` true and the same guid (not a fingerprint-mismatch refusal); manager submit counter unchanged.
**Why human:** The phase never drove the real tool-page form (both re-sends went through tRPC `tool.runCommand`), and the form code changed upstream mid-phase. The offline adapter test covers the server side only. Can be folded into the Phase 7 supervised checklist.

### Gaps Summary

No gaps. All roadmap success criteria are met and independently corroborated from code, tests and read-only live state. Open items for the orchestrator:

1. `human_needed`: the single backstop item above (non-blocking to the goal; reasonable to accept into Phase 7).
2. Tick FLOW-01 in `.planning/REQUIREMENTS.md` (checkbox and traceability row) on phase completion.
3. Before Phase 7: fix CR-01 (gate) and WR-01 (F.A.S.T. validation), and correct the "controller unchanged since a5fa75f" wording in row 2b-0.
4. Documented deviations (FAST-SIM name, gal02-fast.log, orchestrator-sent re-sends via tRPC, PAC on main with build from 26e00251e, port 15005, A8 nest rebind, leftover batch_label) were checked and none weakens a success criterion.

---

_Verified: 2026-11-02_
_Verifier: Claude (gsd-verifier)_
