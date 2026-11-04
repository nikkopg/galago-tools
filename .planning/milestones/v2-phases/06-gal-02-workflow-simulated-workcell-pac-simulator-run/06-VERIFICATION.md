---
phase: 06-gal-02-workflow-simulated-workcell-pac-simulator-run
verified: 2026-11-02T07:45:00Z
status: passed
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
covered_digest: "v3:sha256:f197a0598a891f943e6616bd3ff5596464b73307be0a9c6687891180b7fbf466"
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: human_needed
  previous_score: 5/6
  gaps_closed:
    - "CR-01 gate false-OK on decoy transfer keys (a56927d); WR-03 gate checks 1-3 tightened (beb22d8)"
    - "WR-01/WR-02 (+ iter-2 normalized same-tool compare): F.A.S.T. input and degenerate-handoff validation at queue time (817587f, b056152, d21936d)"
    - "Findings row 2b-0 stale 'controller unchanged since a5fa75f' claim corrected (03f09e8)"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Open the STACK tool page for a real-mode STACK tool in the dev galago-core (:3020), open the transfer form for a completed GAL-02 in-leg, leave the optional fields (source_transfer_profile, destination_transfer_profile, timeout_s) blank, fill step_key and the required fields from the stored run row, and re-send inside the 600 s replay window (needs a fresh run, the 156f9e5c3701e7000 window is long past)."
    expected: "The form delivers the blank optionals as unset (absent, empty string, or timeout_s 0) and the re-send replies SUCCESS with replayed true and the same task guid, not a fingerprint-mismatch refusal. The manager submit counter (count-submits.sh) stays unchanged."
    why_human: "Plan 06-04 tagged this truth verification:backstop. Both Part 2a and Part 2b re-sends went through tRPC tool.runCommand, so the real tool-page form's blank handling was never exercised successfully. The gal02-stack-pacsim.log shows eleven tool-page Transfer attempts at 05:08-05:14Z (12:08-12:14 local), all refused by the adapter before any HTTP call (INVALID_ARGUMENTS 'step_key is required' x7, ERROR_FROM_TOOL 'needsInput; missing: robot, labwareProfile, source,...' x4); none reached the replay path. 06-UAT.md result is still [pending]. The adapter side is covered offline (test_redispatch_tool_page_resend_with_blank_optionals_replays passes)."
  - test: "Re-import docs/runbooks/gal-02-handoff.protocol.json (the post-WR-01/WR-02 script) into the dev galago-core (or any galago-core with the script executor) and open the protocol's Preview with default parameters; also try one bad input (for example fast_step_num_rows 0, or fast_tool equal to stack_tool)."
    expected: "Preview lists the note plus the three transfer commands (STACK in, F.A.S.T., STACK out), and the bad inputs are refused at queue time with a 'GAL-02: ...' message before anything is queued."
    why_human: "The script grew from 3028 to 4774 chars (regex literal in toolKey, String.indexOf, Array.from, Math.floor, isFinite). The node vm stub mirrors galago-core's documented sandbox but is not its executor, and the recorded Part 2a/2b runs used the pre-fix script. Dev galago is torn down, so this cannot be confirmed read-only."
---

# Phase 6: GAL-02 Workflow, Simulated Workcell & PAC-Simulator Run Verification Report

**Phase Goal:** The STACK -> F.A.S.T. -> STACK plate handoff runs end to end in simulation, and a forced re-dispatch of a completed STACK step is shown to send no second transfer, with no real instrument involved.
**Verified:** 2026-11-02
**Status:** human_needed
**Re-verification:** Yes. The earlier report went stale after code-review fixes (a56927d..d22fd4c, 03f09e8, d21936d, 7acbfc2). Every previous must-have was re-checked. Items that need live infrastructure (torn down) carry forward from the previous report, with the evidence re-read where it was still readable.

## Verdict

The phase goal is still achieved. No previous must-have regressed; the two warnings of the previous report (CR-01 gate, WR-01 validation) are now closed and the validation truths are strictly stronger. Status stays `human_needed` for two non-blocking items: the never-observed tool-page blank-optionals backstop truth (06-UAT.md, still pending), and a real-executor Preview of the re-imported, longer script. There are no FAILED truths and no BLOCKERs.

## Goal Achievement

### Observable Truths

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | SC1: script-mode GAL-02 protocol as importable JSON beside its runbook; per-run `step_key` per STACK step; nest/hotel triples are parameters; runs STACK -> F.A.S.T. -> STACK | ✓ VERIFIED | Compared the committed script with the pre-fix one (`git show cb65be2:...`): `name`, `category`, `description`, `mode: script`, `commands: []` and all 27 `parameters` are byte-equal; only `scriptContent` changed (3028 -> 4774 chars). I executed both scripts in the repo's node vm harness with the default parameters: both ok, and the emitted calls are identical after stripping the timestamp/random part of the key: note, STACK `transfer` (`GAL02-in`, 9 required fields, swapped triple), FAST `transfer` (12 fields), STACK `transfer` (`GAL02-out`). So the recorded Part 2a/2b runs (run ids 156f910fe281e7000, 156f9e5c3701e7000; keys `...-in/-out`) remain valid evidence for this protocol's calls, parameter names, defaults and export shape. |
| 2 | SC2: fully Galago-simulated run completes all three steps | ✓ VERIFIED (carried forward, tool logs re-read) | Findings 2a-2 (run 156f910fe281e7000, queueIds 8-11 COMPLETED in order). Re-read `gal02-stack-sim.log`: 3 `Running command Transfer` (two legs, one re-send), 2 `Received configuration`; `gal02-fast.log`: one 10:50:46 Transfer SUCCESS (the second F.A.S.T. Transfer at 11:19:19 belongs to the 2b run). Log mtimes unchanged since the earlier verification (stack-sim.log 10:54). Persisted ledger directory holds only `stack-sim`, so the simulated run wrote none. |
| 3 | SC3: forced re-dispatch of a completed STACK step sends no second transfer (offline on a fake core: submit count stays 1; re-exercised in a simulated run) | ✓ VERIFIED (judged per D-07) | `gal02_replay_test.py` re-run in this verification: all pass under `GAL02_REQUIRE_ALL=1` (56 passed, 0 skipped, across the three gal02 modules). The simulated half is credited only with "survives a re-dispatch through the real queue and writes no ledger", as D-07 states; the no-second-transfer proof rests on the offline test plus SC4. The replay test also uses `REPLAY_WINDOW_S` from the frozen `tools/stack/ledger`. |
| 4 | SC4: operator-run GAL-02 with STACK real mode vs loopback PAC simulator, F.A.S.T. simulated, incl. forced re-dispatch with no second POST; never 10.150.1.125 / stack-server | ✓ VERIFIED (carried forward; adapter-side evidence re-read) | Re-read `gal02-stack-pacsim.log`: exactly two `POST http://127.0.0.1:15005/api/v2/transfer` (11:18:56 in leg, 11:20:41 out leg local = 04:18:56Z/04:20:41Z), each preceded by one `/transfer/estimation`; none at the 11:21:33 in-window re-send (the Transfer at 11:21:33 has no HTTP call), none at the 11:29:40 late re-send (`ERROR_FROM_TOOL`, "step key already completed ... nothing was sent"). Persisted ledger (read-only): version 1, exactly 2 records, both `done`, result `ran`, guids `1fcb9340-...` and `0e253706-...` as in Findings 2b-2/2b-5. `count-baseline.txt` = `baseline=0 at 2026-11-02T04:17:44Z`. `grep` for `10.150.1.125` / `stack-server` over all gal06 logs and env files is empty. Manager-side counter (docker logs) cannot be re-read, the containers are down; Findings 2b-1/2b-3 and the prior report's live read (counter 2) are carried forward. See the log note below for the later tool-page attempts. |
| 5 | 06-04 plan truth (`verification: backstop`): post-DEP-02 tool-page transfer form delivers blank optional fields as unset so the re-send replays | ? UNCERTAIN (insufficient_spec) | Unchanged. The only tool-page attempts on record (05:08-05:14Z) were refused before replay (missing step_key / needsInput), so they neither prove nor disprove blank handling. Abstain per backstop rule, routed to Human Verification (06-UAT.md pending). |
| 6 | 06-02 plan truth: read-only DEP-02 gate prints `DEP-02 OK` only when all conditions hold; fixtures prove it cannot pass falsely | ✓ VERIFIED (strengthened; CR-01 closed) | I ran `bash docs/runbooks/gal-02-dep02-check.sh` against `../galago-core` (HEAD a799627, previously 370b40e): last line `DEP-02 OK`, exit 0. Gate source read: check 4 now anchors on `^    transfer[[:space:]]*:` inside the stack block, the block ends at its first `  },` (a one-line block cannot spill into the next tool), a missing `stack:` opener fails by itself, `acknowledge` is still forbidden; check 2 is scoped to `export enum ToolType {`, check 3 requires an exported `Command_Transfer`, HEAD is printed only for a checkout root. `TestDep02Gate` now has decoy, one-line, enum-scope, Command_Transfer, git-repo read-only and real-sibling-tree consistency cases, all passing. The earlier false-OK reproduction (only `list_transfer_profiles`/`get_transfer_estimate`) is now covered by `test_dep02_gate_does_not_count_substring_decoys_as_stack_transfer`. |

**Score:** 5/6 truths verified (0 present-but-behavior-unverified, 1 uncertain)

Validation truths of 06-01 (blank, non-whole, volume/timeout <= 0 throw): still hold and are widened. The script now also enforces F.A.S.T. decks 1-6, plate ids/columns/rows >= 1, 1-2 letter start rows, `tip_reuse` fresh|reuse, 32-bit bounds (mirroring `tools/fast/server.py` `_check_args`), refuses `stack_tool` equal to `fast_tool` under galago-core's `normalizeToolKey` rule (lower-case, alphanumerics), and refuses an F.A.S.T. triple equal to the source triple, all before the first `galago` call. `gal02_handoff_test.py` grew by about 146 lines and passes. Checks (a)-(c) from the request: (a) confirmed above, (b) confirmed, (c) confirmed.

### Note on the pacsim log (new since the previous report)

`gal02-stack-pacsim.log` now holds 15 `Running command Transfer` lines versus the 4 the previous report and Findings 2b-5 quote. The 11 extra ones (12:08-12:14 local) are the tool-page attempts described under human item 1: seven `INVALID_ARGUMENTS`, four `ERROR_FROM_TOOL needsInput`, no HTTP request, no state change (the ledger still has exactly 2 records, the log has still only 2 `POST /api/v2/transfer`). The 2b-5 sentence "exactly 4 lines" was true when written and is not contradicted in substance. It would be cleaner if the Findings row recorded the later attempts, but SC4 is unaffected.

### Part 1 automated gate (D-16c)

| Command | Result |
| ------- | ------ |
| `GAL02_REQUIRE_ALL=1 python -m pytest tools/tests/gal02_handoff_test.py gal02_replay_test.py gal02_runbook_test.py -q -rs` | 56 passed, 0 skipped |
| `GAL02_REQUIRE_ALL=1 bin/make proto test` (venv + node on PATH) | 566 passed in 15.68 s (baseline 555); the make target ran to the end (ruff/mypy are part of it per the orchestrator, only the pytest tail was inspected here) |
| `git diff --quiet 477b0ed -- tools/stack tools/fast tools/base_server.py interfaces requirements.txt` | exit 0, the frozen adapter, protos and requirements are unchanged |

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `docs/runbooks/gal-02-handoff.protocol.json` | script protocol, 27 params | ✓ VERIFIED | exists, same 27 params, longer validated script, identical calls for default params |
| `docs/runbooks/gal-02-handoff.md` | runbook + Findings G0, 2a-1..2a-3, 2b-0..2b-5 | ✓ VERIFIED | all 10 rows present; 2b-0 wording now names 2ca4e4e/debc038/a127fb2; Part 1 commands set `GAL02_REQUIRE_ALL` |
| `docs/runbooks/gal-02-dep02-check.sh` | read-only gate | ✓ VERIFIED | `DEP-02 OK`, exit 0; decoy-proof |
| `tools/tests/gal02_harness.py` | node stub runner + `skip_or_fail` | ✓ VERIFIED | used by all three modules |
| `tools/tests/gal02_handoff_test.py` | FLOW-01 matrix | ✓ VERIFIED | passes (includes new validation and normalized same-tool cases) |
| `tools/tests/gal02_replay_test.py` | FLOW-03 offline proof | ✓ VERIFIED | passes, real `StackServer` on fake core |
| `tools/tests/gal02_runbook_test.py` | gate + content tests | ✓ VERIFIED | passes, includes real-git read-only and sibling-tree tests |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `gal02_harness.load_export` | protocol JSON | committed file path | WIRED | I ran the same harness against the file |
| `gal02_replay_test` | `tools/stack/server.py` Transfer + ledger | `ParseDict`, in-process gRPC | WIRED | passes |
| runbook Part 2 gate | `gal-02-dep02-check.sh` | `bash docs/runbooks/gal-02-dep02-check.sh` | WIRED | re-run here, OK |
| protocol `stackLeg` / `fastStep` | `stack.proto` Command.Transfer / `tools/fast/server.py` `_check_args` | proto field names; mirrored rules | WIRED | cross-check test skips only without `fast_mcp`, fails under `GAL02_REQUIRE_ALL`; ran with it set, no skip |
| STACK-PACSIM re-send | `Ledger.decide` REPLAY | same step_key + fingerprint in 600 s | WIRED (live, carried forward) | pacsim log: no HTTP call at 11:21:33 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| protocol script -> galago queue | step-key params | `galago.command` at queue time, stored rows (Findings 2a-2, 2b-2) | keys `...-0cb7fd09-in/-out`, `...-b7ffcec0-in/-out` | ✓ FLOWING (carried forward) |
| STACK-PACSIM -> PAC sim | transfer submit | `POST /api/v2/transfer` | 2 submits in the adapter log, 2 ledger records | ✓ FLOWING (re-read) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Gate on real sibling tree | `bash docs/runbooks/gal-02-dep02-check.sh` | `DEP-02 OK`, exit 0 | ✓ PASS |
| Old vs new script, default params | node vm harness, both scripts | both ok, identical 4 calls (timestamp/random stripped) | ✓ PASS |
| gal02 modules | pytest with `GAL02_REQUIRE_ALL=1` | 56 passed, 0 skipped | ✓ PASS |
| Full gate | `GAL02_REQUIRE_ALL=1 bin/make proto test` | 566 passed | ✓ PASS |
| Ledger | read-only parse of `stack-sim/stack-ledger.json` | version 1, 2 records, both `done`/`ran` | ✓ PASS |
| Frozen files | `git diff --quiet 477b0ed -- ...` | exit 0 | ✓ PASS |

### Probe Execution

SKIPPED: the phase declares no `probe-*.sh`. The DEP-02 gate script was run as a gate (above).

### Requirements Coverage

Plan frontmatter IDs: 06-01 [FLOW-01, FLOW-03]; 06-02 [FLOW-01..FLOW-04]; 06-03 [FLOW-02, FLOW-03]; 06-04 [FLOW-04, FLOW-03]. All four exist in REQUIREMENTS.md and map to Phase 6. No orphaned IDs.

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ---------- | ----------- | ------ | -------- |
| FLOW-01 | 06-01, 06-02 | script-mode protocol as importable JSON beside its runbook, per-run step_keys, nest triples as parameters | ✓ SATISFIED | SC1 evidence. Bookkeeping: REQUIREMENTS.md still shows `- [ ] **FLOW-01**` (line 68) and traceability `FLOW-01 \| Phase 6 \| Pending` (line 138), while FLOW-02..04 are `[x]`/Complete. Tick it on phase completion. |
| FLOW-02 | 06-02, 06-03 | fully Galago-simulated run completes all three steps | ✓ SATISFIED | SC2 evidence |
| FLOW-03 | 06-01..06-04 | forced re-dispatch sends no second transfer, offline and in a simulated run | ✓ SATISFIED | offline fake-core proof plus D-07 simulated half plus FLOW-04 corroboration |
| FLOW-04 | 06-02, 06-04 | real-mode STACK vs loopback PAC sim, F.A.S.T. simulated, no second POST, never hardware | ✓ SATISFIED | SC4 evidence |

### Anti-Patterns Found

No `TBD`/`FIXME`/`XXX`/`TODO`/`HACK` markers in the covered docs, scripts or tests. No stubs.

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `docs/runbooks/gal-02-dep02-check.sh` | n/a | CR-01 (previous Warning) | closed | fixed in a56927d, tested |
| `docs/runbooks/gal-02-handoff.protocol.json` | scriptContent | WR-01 (previous Warning) | closed | fixed in 817587f/b056152/d21936d, tested; real-executor Preview still open as human item 2 |
| `docs/runbooks/gal-02-handoff.md` | Findings 2b-5 | quotes "exactly 4 `Running command Transfer`" while the log now has 15 (11 refused tool-page attempts after the report) | ℹ️ Info | point-in-time claim, no HTTP side effect, optional doc touch-up |
| IN-01..IN-05 | n/a | open Info items in 06-REVIEW-DISPOSITION.md | ℹ️ Info | advisory, none touches a roadmap SC |

### Human Verification Required

### 1. Real tool-page re-send with blank optionals

**Test:** Run a fresh GAL-02 (STACK-PACSIM or any real-mode STACK) in the dev galago-core. On the tool page open the transfer form, fill step_key and the required fields from the stored in-leg row, leave `source_transfer_profile`, `destination_transfer_profile` and `timeout_s` blank, and re-send inside 600 s.
**Expected:** SUCCESS with `replayed` true and the same task guid, not a fingerprint-mismatch refusal; the manager submit counter does not move.
**Why human:** The only tool-page attempts so far (05:08-05:14Z) were refused for missing required fields before reaching the replay path; the blank-optionals behavior is unobserved. Tracked in 06-UAT.md (pending). Can fold into the Phase 7 supervised checklist.

### 2. Preview of the re-imported protocol in galago-core's real executor

**Test:** Re-import `docs/runbooks/gal-02-handoff.protocol.json` and open Preview with defaults; try one bad input.
**Expected:** Preview shows the note plus three transfers; bad input is refused with a `GAL-02: ...` message before anything queues.
**Why human:** The extended script is proven in the repo's node vm stub only; galago-core's own executor was last seen running the shorter pre-fix script. Infrastructure is torn down.

### Gaps Summary

No gaps. All four ROADMAP success criteria hold; the two earlier warnings are closed by the review fixes and the guarding tests are stronger than before. Open items for the orchestrator:

1. `human_needed`: the two non-blocking items above (both reasonable to accept into Phase 7's supervised checklist).
2. Tick FLOW-01 in `.planning/REQUIREMENTS.md` (checkbox and traceability row) on phase completion.
3. Optional: add a Findings line for the 05:08-05:14Z tool-page attempts so the "4 Transfer lines" count in 2b-5 is not misread against the current log.

---

_Verified: 2026-11-02_
_Verifier: Claude (gsd-verifier)_
