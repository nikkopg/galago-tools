---
phase: 06-gal-02-workflow-simulated-workcell-pac-simulator-run
reviewed: 2026-11-02T00:00:00Z
depth: standard
iteration: 2
diff_base: fe0c5aa
files_reviewed: 7
files_reviewed_list:
  - docs/runbooks/gal-02-dep02-check.sh
  - docs/runbooks/gal-02-handoff.protocol.json
  - docs/runbooks/gal-02-handoff.md
  - tools/tests/gal02_harness.py
  - tools/tests/gal02_handoff_test.py
  - tools/tests/gal02_replay_test.py
  - tools/tests/gal02_runbook_test.py
findings:
  critical: 0
  warning: 2
  info: 7
  total: 9
status: issues_found
---

# Phase 6: Code Review Report (iteration 2)

**Reviewed:** 2026-11-02
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

I re-reviewed the fix commits a56927d..d22fd4c and 03f09e8 against the iteration-1 findings. I ran the
suite with `GAL02_REQUIRE_ALL=1` and got 56 passed, 0 skipped. I also ran the gate against the real
sibling checkout. It prints `DEP-02 OK` (HEAD a799627, exit 0). It does not fail closed on the real
galago-core layout: the real `commandFields.stack` block has a multi-line opener, `transfer:` at
four-space indent, and the `ToolType` enum and the generated `stack.ts` match the new patterns.

Iteration-1 findings:

| ID | Verdict |
|----|---------|
| CR-01 | Resolved. Check 4 now needs the `transfer` key at the block's indent. The block ends at its first closing line, and a missing `stack:` opener is reported on its own. The decoy, nested, quoted-name and one-line fixtures all behave as the commit says. |
| WR-01 | Resolved. The script mirrors every `_check_args` rule (decks 1-6, ids and columns and rows at least 1, one or two letters, volume above 0, `tip_reuse` fresh or reuse), plus int32 bounds. `expected_tray_id` is not checked by the adapter, and the script only requires a whole int32, which is the correct subset. No valid F.A.S.T. value is rejected. The boundary test shows the accepted values agree with `_check_args`. All checks run before the first `galago` call. |
| WR-02 | Partly resolved. See WR-01 below: tool names are compared with `===`, but galago-core matches them with `normalizeToolKey`. |
| WR-03 | Resolved. Check 2 is scoped to the enum block. Check 3 requires an exported `Command_Transfer`. The revision is printed only at a checkout root, with `pwd -P` handling symlinks. |
| WR-04 | Resolved. The read-only test runs on a real git repo and compares galago-tools `git status --porcelain` before and after. The sibling-tree test now checks that the verdict agrees with the exit code and the missing/forbidden lines. |
| WR-05 | Partly resolved. `GAL02_REQUIRE_ALL` turns every environment skip into a failure. The default (non-strict) behaviour still silently drops the new WR-01 and WR-02 script-side coverage. See WR-02 below. |
| IN-01..IN-05 | Still open, carried forward. |

No Critical issues were found. Two Warnings and the carried-forward Info items remain.

## Warnings

### WR-01: Degenerate-handoff guard compares tool names with `===`, but galago-core matches them case- and punctuation-insensitively

**File:** `docs/runbooks/gal-02-handoff.protocol.json:7` (scriptContent, `if (stackTool === fastTool)`)
**Issue:** This is the iteration-1 WR-02 fix, and it is incomplete. galago-core resolves a tool name with
`normalizeToolKey` (`controller/server/toolKey.ts`: `toLowerCase().replace(/[^a-z0-9]/g, "")`). The
runbook's own Findings row 2a-1 records this as the reason `FAST` could not be used (it resolved to the
real `Fast` tool). So `stack_tool="STACK"` with `fast_tool="Stack"`, or `"FAST-SIM"` with `"fastsim"`,
is the same tool in galago-core but passes the `===` check. The queue then holds a STACK `transfer`
addressed to the F.A.S.T. tool (or the reverse), which is the case the guard was added to stop. The
default values are `STACK` and `FAST`, and the operator edits them by hand in Phase 7, so a case
variation is a plausible typo. The location check (`source_*` vs `fast_*`) has the same exact-string
weakness, but hardware names may be case-sensitive there, so it is less clear.
**Fix:** Compare the normalized names:
```js
function toolKey(s) { return s.toLowerCase().replace(/[^a-z0-9]/g, ""); }
if (toolKey(stackTool) === toolKey(fastTool)) { throw new Error("GAL-02: parameter 'fast_tool' must differ from 'stack_tool'"); }
```
Add a test with `stack_tool="STACK"`, `fast_tool="stack"` and one with `"FAST-SIM"`/`"fastsim"`, each
asserting `result.calls == []`.

### WR-02: Without the strict switch, the new queue-time validation tests are skipped as a whole when `fast_mcp` is missing

**File:** `tools/tests/gal02_handoff_test.py:349-420` (`test_fast_step_invalid_values_throw_...`, the boundary test at 378, and `_fast_check_args` at 397)
**Issue:** `_fast_check_args` calls `skip_or_fail` when `fast_mcp` cannot be imported. It is called from
inside the first buildable `subTest`. Under pytest 7.4.3 (the version in this venv, no subtests plugin) a
`SkipTest` raised in a `subTest` propagates and aborts the whole test method. I reproduced it by blocking
the `fast_mcp` import: both tests skip, and no script-side assertion runs. About 50 of the invalid-value
assertions and all the boundary assertions need only node and the script, not `fast_mcp`. The result is
that WR-01's and WR-02's script-side checks (throws, `calls == []`, accepted values) are not run in any
environment without the private F.A.S.T. core. That is the default developer or CI setup. Strict mode
(`GAL02_REQUIRE_ALL=1`) does catch it, but it is opt-in. The same defect that WR-05 targeted survives for
the checks added by the fixes.
**Fix:** Make the cross-check optional inside the loop so the script assertions always run. For example,
compute `check_args = self._load_check_args()` once (returning `None` when unavailable and calling
`skip_or_fail` only if strict) and guard only the `_check_args` assertion on it. Or split the cross-check
into its own test method.

## Info

### IN-01: `find_node` lets PATH win over the `$NODE` "override" (carried forward)

**File:** `tools/tests/gal02_harness.py:81-88`
**Issue:** Lookup order is PATH, then `$NODE`, then nvm. `$NODE` is consulted only when no `node` is on
PATH. An invalid `$NODE` falls through silently. Unchanged since iteration 1.
**Fix:** Check `$NODE` first, or call it a fallback in the docs and comment. Report an invalid `$NODE`.

### IN-02: The harness `galago.timer` stub does not match galago-core's signature (carried forward)

**File:** `tools/tests/gal02_harness.py:44`
**Issue:** The stub takes `timer(seconds)`. The real executor takes `timer({minutes, seconds, message})`.
The script does not use `timer`, so nothing breaks. Unchanged.
**Fix:** Mirror the documented signature, or remove stub members the script does not use.

### IN-03: The hardware deny assertion is a tautology (carried forward)

**File:** `tools/tests/gal02_replay_test.py:50`
**Issue:** `assertNotIn(self.server.config.host, HARDWARE_DENY)` is an exact, case-sensitive check on a
hard-coded fixture host. Unchanged.
**Fix:** Normalise before comparing (`host.strip().lower().rstrip(".")`).

### IN-04: `stack_legs` uses bare `assert` in a helper module (carried forward)

**File:** `tools/tests/gal02_harness.py:147-149`
**Issue:** The checks vanish under `python -O`, after which the helper indexes `result.calls[1]` and
`[3]` unvalidated. Unchanged.
**Fix:** Raise `AssertionError` explicitly.

### IN-05: Magic numbers and the `stack_timeout_s=0` rule (carried forward)

**File:** `tools/tests/gal02_handoff_test.py:250,260,322`, `tools/tests/gal02_runbook_test.py:418`; script `positive("stack_timeout_s")`
**Issue:** The tests hard-code 23 required parameters, 27 total parameters and a key length of 58. The
tool form documents "blank/0 = adapter default" for `timeout_s`, but the script throws on 0 (the
parameter description only says "blank uses the adapter default", so this is consistent with the
protocol, not with the tool page). Unchanged.
**Fix:** Derive the counts from the export. Document that 0 is rejected, or treat `"0"` as blank.

### IN-06: The valid deck range (1-6) and the `tip_reuse` choices are not stated where the operator enters them

**File:** `docs/runbooks/gal-02-handoff.protocol.json:7` (parameters `fast_step_source_deck`, `fast_step_dest_deck`; descriptions say only "deck slot number")
**Issue:** The script now rejects a deck outside 1-6 and the start-row description says "one or two
letters", but the deck descriptions do not give the range. The hard-coded `6` in the script duplicates
`_DECK_SLOTS` in `tools/fast/server.py`. The test cross-check covers drift only when `fast_mcp` is
installed (see WR-02).
**Fix:** Add "1-6" to the two deck descriptions, and note the coupling to `_DECK_SLOTS` in the header
comment (the comment already points at `_check_args`).

### IN-07: The gate's `acknowledge` check matches comments in the stack block

**File:** `docs/runbooks/gal-02-dep02-check.sh:115`
**Issue:** `grep -q 'acknowledge'` runs over the whole stack block, including comment lines. A comment
such as "acknowledge_failure is deliberately not exposed" inside the block would make the gate print
`forbidden:` and block Part 2. It fails closed, so this is a nuisance, not a false OK. The real
galago-core block has no such comment today.
**Fix:** Match the key shape: `grep -qE '^    acknowledge[A-Za-z_]*[[:space:]]*:'`.

---

_Reviewed: 2026-11-02_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
