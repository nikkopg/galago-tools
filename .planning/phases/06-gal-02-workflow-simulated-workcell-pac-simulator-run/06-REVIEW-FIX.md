---
phase: 06
review: 06-REVIEW.md
iteration: 2
fix_scope: critical_warning
status: all_fixed
fixed: 6
skipped: 0
out_of_scope: 5
commits: [a56927d, 817587f, b056152, beb22d8, 40a9dd7, d22fd4c, 03f09e8, d21936d, 7acbfc2]
verification: "GAL02_REQUIRE_ALL=1 bin/make proto test -> 566 passed (baseline 555), ruff + mypy clean; gal02 modules 56 passed, 0 skipped under -rs; gate prints DEP-02 OK against ../galago-core feat/stack-tool; frozen files (tools/stack, tools/fast, base_server.py, interfaces, requirements.txt) unchanged since 477b0ed"
---

# Phase 6: Code Review Fix Report (iteration 1)

Fixed in the main checkout (branch `feat/stack-tool`), one commit per finding. No Docker, simulator,
galago-core or tool server was started, and no tool command was sent.

## Fixed

| ID | Commit | Files | Fix |
|----|--------|-------|-----|
| CR-01 | a56927d | `docs/runbooks/gal-02-dep02-check.sh`, `tools/tests/gal02_runbook_test.py` | Check 4 matches the `transfer` key itself at the stack block's indent, not substrings like `list_transfer_profiles` or `get_transfer_estimate`. The block ends at its first closing line, so a one-line block no longer spills into the next tool's block. A missing `stack:` opener fails on its own. A one-line block passes only if `transfer` is its first key, otherwise the gate fails closed. Added decoy, nested, quoted-name and one-line fixtures, plus cases that should pass. |
| WR-01 | 817587f | `docs/runbooks/gal-02-handoff.protocol.json`, `tools/tests/gal02_handoff_test.py` | The script now mirrors `tools/fast/server.py` `_check_args` before the first `galago` call: decks 1-6, ids/cols/rows/cols counts ≥ 1, start rows of one or two letters, volume > 0, `tip_reuse` fresh or reuse, int32 bounds. About 50 invalid values throw with zero commands, and are cross-checked against `_check_args`. Accepted boundary values are also tested. Parameter names, defaults and export shape are unchanged. |
| WR-02 | b056152 | same as WR-01 | Throws at queue time when `stack_tool == fast_tool`, or when the F.A.S.T.-side device/deck/nest equals the source triple. |
| WR-03 | beb22d8 | `docs/runbooks/gal-02-dep02-check.sh`, `tools/tests/gal02_runbook_test.py` | Check 2 is limited to the `export enum ToolType {` block. Check 3 requires `stack.ts` to export `Command_Transfer`. The HEAD is printed only when `GALAGO_CORE_DIR` is itself a git checkout root, else `unknown`. |
| WR-04 | 40a9dd7 | `tools/tests/gal02_runbook_test.py` | New read-only test runs the gate on a real git-repo fixture and compares the galago-tools `git status --porcelain` before and after. The sibling-tree test now requires the verdict to agree with the exit code and the missing/forbidden lines. |
| WR-05 | d22fd4c | `tools/tests/gal02_harness.py`, the three gal02 test modules, `docs/runbooks/gal-02-handoff.md` | New helper `skip_or_fail`: with `GAL02_REQUIRE_ALL` set (and not `0`), every environment skip becomes a failure. That covers node, `stack_automation_layer`, `fast_mcp`, bash, git and the sibling checkout. It is opt-in, and the runbook's Part 1 commands now set it. |

Also corrected, docs only (03f09e8): Findings row 2b-0's "controller unchanged since a5fa75f" now names
galago-core commits 2ca4e4e/debc038/a127fb2, which changed the tool-page form between the 2a and 2b
runs. The row also says the runs used the script queue and tRPC `tool.runCommand`, so the evidence
stands.

WR-01 and WR-02 add queue-time validation logic. The tests prove it in the node stub, not in
galago-core's real executor. Re-importing the protocol into a dev Galago and checking Preview is a
human check, folded into the pending 06-UAT item.

## Skipped

None.

## Out of scope (Info, `fix_scope: critical_warning`)

IN-01, IN-02, IN-03, IN-04, IN-05: still open.

## Iteration 2

The iteration-2 re-review confirmed CR-01, WR-01, WR-03 and WR-04 resolved, and WR-02/WR-05 partly. It raised two new warnings, both fixed:

| ID (iter 2) | Commit | Fix |
|---|---|---|
| WR-01 | d21936d | The same-tool guard compares names the way galago-core's `normalizeToolKey` does (lower-case, alphanumerics only), so `STACK`/`stack` and `FAST-SIM`/`fastsim` are refused. Tests added. |
| WR-02 | 7acbfc2 | The F.A.S.T. validation tests run every node-only assertion even when `fast_mcp` is missing. Only the `_check_args` cross-check skips, at the end, or fails under `GAL02_REQUIRE_ALL`. This was reproduced with the `fast_mcp` import blocked. |

Re-verified: `GAL02_REQUIRE_ALL=1 bin/make proto test` gives 566 passed, and ruff and mypy are clean.
