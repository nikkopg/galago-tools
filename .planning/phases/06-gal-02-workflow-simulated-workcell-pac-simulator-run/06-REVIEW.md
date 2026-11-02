---
phase: 06-gal-02-workflow-simulated-workcell-pac-simulator-run
reviewed: 2026-11-02T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - docs/runbooks/gal-02-handoff.protocol.json
  - docs/runbooks/gal-02-dep02-check.sh
  - tools/tests/gal02_harness.py
  - tools/tests/gal02_handoff_test.py
  - tools/tests/gal02_replay_test.py
  - tools/tests/gal02_runbook_test.py
findings:
  critical: 1
  warning: 5
  info: 5
  total: 11
status: issues_found
---

# Phase 6: Code Review Report

**Reviewed:** 2026-11-02
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

The protocol script is correct on the points the phase set out to prove. Step keys are minted once per run and suffixed `-in` and `-out`. Blank optionals are omitted. The out leg is a correct swap, including the per-location transfer profiles. Only `transfer` and the Tool Box `note` are emitted. The sandbox globals the script uses (`Math`, `Date`, `Array`, `Number`, `String`, `isFinite`, `Error`) all exist in galago-core's `protocol-script-executor.ts` context. All three parameter objects are built before the first `galago` call, so the checks that exist do throw with nothing queued. The 45 GAL-02 tests pass in this environment.

Main concerns:

1. The DEP-02 gate can print `DEP-02 OK` when `commandFields.stack.transfer` is absent. This is a proven false-OK path.
2. The "everything is validated before anything is queued" claim does not hold for the F.A.S.T. step. Values the F.A.S.T. adapter rejects pass the script, so such a run fails after the STACK in-leg has already moved the plate.
3. Several test gaps leave both of the above unpinned.

## Critical Issues

### CR-01: DEP-02 gate can report OK without `commandFields.stack.transfer`

**File:** `docs/runbooks/gal-02-dep02-check.sh:67-72`
**Issue:** Check 4 is `printf '%s\n' "$stack_block" | grep -q 'transfer'`. That is a bare substring match over the whole stack block. The real block in galago-core's `constants.ts` (lines 346-381) also contains `list_transfer_profiles` and `get_transfer_estimate`. The check therefore passes even if the `transfer:` key is missing or renamed. I reproduced this with a fixture whose stack block holds only those two keys. The awk range yields them and `grep -c transfer` returns 2, so the gate would print `DEP-02 OK`. Part 2 is gated on this verdict ("no false OK").

The awk range `/^  stack: \{/,/^  \},/` has a second hole. A one-line block such as `  stack: { get_manager_state: [] },` never matches the end pattern on its own line. The range then spills into the following tool's block, and that block's `transfer` satisfies the check. I reproduced this with a fixture where a later `zzz:` block holds `transfer`.

`TestDep02Gate` does not cover either case. Its fixture is always the clean `transfer: [],` shape.

**Fix:** Match the key itself, anchored at the block's indent, and stop the awk range at the first closing line:
```bash
stack_block="$(awk '/^  stack: \{/{f=1; next} f && /^  \},?$/{exit} f' "$CONSTANTS_TS")"
if ! printf '%s\n' "$stack_block" | grep -qE '^    transfer: \['; then
  echo "missing: commandFields.stack.transfer in controller/components/tools/constants.ts"
  failed=1
fi
```
Also treat a missing `stack:` opener as a failure of its own. Add tests where the block holds only `get_transfer_estimate`/`list_transfer_profiles`, and where `stack: {` is a one-liner followed by another tool that has `transfer`.

## Warnings

### WR-01: F.A.S.T. inputs are only partly validated, so a bad value fails after the STACK in-leg has moved the plate

**File:** `docs/runbooks/gal-02-handoff.protocol.json:7` (scriptContent: `whole`, `fastStep`, and the header comment)
**Issue:** The header comment says "Every input is validated ... so a bad input throws with nothing queued". For the F.A.S.T. step that is false.
- `whole()` only checks that the value is integral. It accepts `0`, negatives, hex strings such as `0x10`, and values beyond int32.
- `positive()` is used only for `volume` and `stack_timeout_s`.
- `start_row` and `tip_reuse` are only checked for non-blank. A select option is not enforced on the script side.

`tools/fast/server.py:_check_args` (lines 199-226) rejects all of these:
- decks outside `1.._DECK_SLOTS`;
- plate ids, start cols, `num_rows` and `num_cols` below 1;
- a row that is not 1-2 letters;
- a `tip_reuse` outside `_TIP_REUSE_MODES`.

The run is queued as three steps. A value like `fast_step_num_rows=0` or `tip_reuse=fresh2` therefore queues normally. The STACK in-leg runs and moves the plate to the F.A.S.T. position. The F.A.S.T. step then returns `INVALID_ARGUMENTS`, and the run stops with the plate stranded mid-handoff. The default-parameter test run never exercises this.

**Fix:** Mirror the F.A.S.T. rules in the script before the first `galago` call:
```js
function atLeast(name, min) { var n = whole(name); if (n < min) { throw new Error("GAL-02: parameter '" + name + "' must be at least " + min); } return n; }
// deck: 1..8 (match _DECK_SLOTS), ids/cols/rows/cols: atLeast(..., 1)
if (!/^[A-Za-z]{1,2}$/.test(p.source_start_row)) { throw new Error("GAL-02: parameter 'fast_step_source_start_row' must be one or two letters"); }
if (["fresh", "reuse"].indexOf(p.tip_reuse) < 0) { throw new Error("GAL-02: parameter 'fast_step_tip_reuse' must be fresh or reuse"); }
```
Add a test per field that checks `result.calls == []`. A cross-check against `tools.fast.server._check_args` would also keep the script and the adapter from drifting.

### WR-02: No guard against a degenerate handoff (same tool, or same location on both sides)

**File:** `docs/runbooks/gal-02-handoff.protocol.json:7` (scriptContent, the `stackTool`/`fastTool` and `legIn` lines)
**Issue:** Nothing checks that `stack_tool !== fast_tool`. Nothing checks that the F.A.S.T.-side `device/deck/nest` differs from the source triple. In Phase 7 the operator types hardware names by hand, and a copy-paste error gives an in leg with source equal to destination. It would be issued as a real STACK transfer. Only the tool's own rules stop it, and they may not. The same-tool case sends a STACK `transfer` to the F.A.S.T. tool name, or the reverse.
**Fix:** Throw at queue time when `stackTool === fastTool`. Also throw when `source_device`, `source_deck` and `source_nest` all equal the `fast_*` triple. Add tests for both.

### WR-03: Gate checks 2 and 3 are weaker than the runbook claims

**File:** `docs/runbooks/gal-02-dep02-check.sh:53-62`
**Issue:**
- Check 2 greps the whole `controller.ts` for `stack = "stack",`. It is not scoped to the `ToolType` enum, so any other enum or map with the same line satisfies it.
- Check 3 only tests that `stack.ts` exists. An empty or stale file passes.
- Check 1 reports the HEAD of any enclosing git repo when `$GC` is a plain directory inside another repo (`git -C "$GC" rev-parse`). That would put a wrong revision in the Findings log (G0).

All three lean toward a false OK. The result is lower assurance than D-01 describes ("galago-core builds with `ToolType.stack`").
**Fix:** Scope check 2 with awk to the `export enum ToolType {` block. For check 3, grep `stack.ts` for an exported `Command_Transfer`/`Transfer` symbol. For the revision, require `git -C "$GC" rev-parse --show-toplevel` to equal `$GC`, or label the value as best effort.

### WR-04: Test coverage does not pin the validation or the gate decoy cases

**File:** `tools/tests/gal02_handoff_test.py:312-328`, `tools/tests/gal02_runbook_test.py:169-225`
**Issue:**
- `test_throws_on_invalid_numbers` covers only `num_rows="1.5"`, `volume="0"`, `stack_timeout_s="abc"` and `"-1"`. There is no case for `num_rows` of 0 or negative, a non-letter start row, a bad `tip_reuse`, a deck outside the slot range, or an overflowing int. This is why WR-01 is not caught.
- `test_dep02_gate_blocks_each_single_missing_piece` removes whole pieces only (see CR-01). It has no decoy-substring case.
- `test_dep02_gate_on_the_real_sibling_tree_prints_one_verdict` accepts both exit 0 and exit 1. It can never fail on the gate's verdict, and it is environment dependent.
- `test_dep02_gate_is_read_only` snapshots only the fixture core tree. It does not snapshot `REPO_ROOT` or the cwd, and `git` is never run inside a real repo.

**Fix:** Add the cases above. Drop or demote the sibling-tree test to an informational skip. Extend the snapshot to the galago-tools tree, or at least `git status --porcelain` before and after.

### WR-05: Replay and F.A.S.T. contract tests can skip silently, so the "0 skipped" requirement is only enforced for node

**File:** `tools/tests/gal02_replay_test.py:12-25`, `tools/tests/gal02_handoff_test.py:353-360`
**Issue:**
- Module-level `unittest.SkipTest` skips every FLOW-03 offline test when `stack_automation_layer` or `httpx` is missing.
- In `test_proto_contract_...`, a missing `fast_mcp` skips the F.A.S.T. `_check_args` assertion. That assertion is the one that would otherwise have caught WR-01.
- D-16c requires the verification run to have 0 skipped, but nothing fails when these two skips fire. `TestNodeLookup` guards only the node path.

**Fix:** Add an opt-in strict switch, for example `GAL02_REQUIRE_ALL=1`, that turns these skips into failures. The verification command would set it. Alternatively, move the F.A.S.T. rule check into a pure test that does not need `fast_mcp`.

## Info

### IN-01: `find_node` lets PATH win over the `$NODE` "override"

**File:** `tools/tests/gal02_harness.py:76-82`
**Issue:** Lookup order is PATH, then `$NODE`, then nvm. D-16c calls `$NODE` an override, but it is consulted only when no `node` is on PATH. An operator setting `NODE` to pin a version is silently ignored. A set but invalid `$NODE` also falls through quietly to nvm instead of saying so.
**Fix:** Check `$NODE` first, or rename it in the docs and comment as a fallback. Report an invalid `$NODE` explicitly.

### IN-02: The harness `galago.timer` stub does not match galago-core's signature

**File:** `tools/tests/gal02_harness.py:39`
**Issue:** The stub takes `timer(seconds)`. The real executor takes `timer({minutes, seconds, message})` and emits Tool Box `timer`. The script does not use timer today, so nothing breaks. The stub claims to mirror the documented API but does not, and `console` is the full node console instead of the log/warn/error trio.
**Fix:** Mirror the documented signature, or remove the stub members the script does not need.

### IN-03: The hardware deny assertion is a tautology

**File:** `tools/tests/gal02_replay_test.py:49`, `tools/tests/gal02_harness.py:23`
**Issue:** `assertNotIn(self.server.config.host, HARDWARE_DENY)` checks a value hard-coded elsewhere (`"127.0.0.1"` in `stack_test.py:1692`). The comparison is exact and case-sensitive, so `STACK-SERVER` or a trailing-dot name would pass. D-10 asks for the deny-set on "any real-mode Configure fixture", but this fixture injects the service directly and never calls Configure.
**Fix:** Normalise before comparing (`host.strip().lower().rstrip(".")`). Optionally assert the ledger dir is under a temp root.

### IN-04: `stack_legs` uses bare `assert` in a helper module

**File:** `tools/tests/gal02_harness.py:135-137`
**Issue:** Under `python -O` these checks vanish, and the helper then indexes `result.calls[1]` and `[3]` without validation, producing IndexError/KeyError instead of a clear failure.
**Fix:** Raise `AssertionError` explicitly, or use `unittest.TestCase.fail`.

### IN-05: Magic numbers and a non-strict zero rule in the script and tests

**File:** `tools/tests/gal02_handoff_test.py:303`, `tools/tests/gal02_runbook_test.py:262`, `tools/tests/gal02_handoff_test.py:231`; script `positive("stack_timeout_s")`
**Issue:**
- The tests hard-code `23` required parameters, `27` total parameters and a key length of `58`. Adding an optional parameter breaks them for a non-behavioural reason.
- The tool form documents "blank/0 = adapter default" for `timeout_s` (`constants.ts`), but the script throws on `stack_timeout_s=0`. That is an inconsistency with the tool page vocabulary, not a bug.

**Fix:** Derive the counts from the export (`len([p for p in params if p["required"]])`). Compute 58 from the label cap and the fixed suffixes. Either document that 0 is rejected, or treat `"0"` as blank.

---

_Reviewed: 2026-11-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
