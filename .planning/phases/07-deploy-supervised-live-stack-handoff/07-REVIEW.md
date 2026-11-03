---
capability: code-review
phase: 07-deploy-supervised-live-stack-handoff
status: reviewed
counts: {critical: 0, high: 2, medium: 1, low: 8}
reviewed: 2026-11-03T00:00:00Z
depth: standard
files_reviewed_list:
  - docs/runbooks/gal-07-live-check.sh
  - tools/tests/gal07_live_runbook_test.py
  - docs/runbooks/gal-07-live-handoff.md
---

## Reviewed

Scope: `docs/runbooks/gal-07-live-check.sh` (8-check fail-closed gate), `tools/tests/gal07_live_runbook_test.py` (fixture matrix, 15 methods / 22+ subtests, both holder pins), `docs/runbooks/gal-07-live-handoff.md` (safety clauses). Verified empirically on the host: `bash -n` clean, `python -m unittest tools.tests.gal07_live_runbook_test` → 15/15 OK; no hardcoded credential values in any of the three files (leaks in the runbook are image shas, internal IPs and usernames only); the gate prints no `warn:` value leakage (presence-only credential discipline holds); a gate that aborts early under `set -u` cannot print `PREFLIGHT OK`, so every crash path fails closed. Two fail-open-direction issues were still proven from the source (below), plus one runbook/gate contradiction.

## Finding H-01 (high) — Runbook Pre-flight text contradicts the gate's galago-holder exemption

**File:** `docs/runbooks/gal-07-live-handoff.md:51-52`
**Issue:** The Pre-flight section states "check 2 refuses the session when the owner lock for `10.150.1.125:5005` is already held" — but the gate (`gal-07-live-check.sh:144-160`, fix 9344957) does NOT refuse when the holder's owner is `galago`: it prints `ok: ... the expected single-owner state` and passes. In any post-real-mode-Configure run (Parts 2 and 3, per evidence rows 2a-1/3a-1) the lock is permanently held by `galago` and the gate MUST pass — so the runbook sentence is false in the very states Parts 2-3 execute in. The Safety rules line 20 ("refuses whenever *another* front end holds") is correct; only the Pre-flight wording omits the exemption. An operator reading lines 51-52 literally could either flag every steady-state pre-flight as defective or — worse — release the lock by restarting the tool server, exactly the D-11-forbidden restart-to-reset.
**Fix:** Amend the sentence to "…check 2 refuses the session when the owner lock is already held by a front end other than the session's own STACK tool server (owner `mcp`/`stack-mcp`/unknown still block; a holder with owner `galago` is the expected single-owner state and passes)".

## Finding H-02 (high) — Silent lock-probe fallback to an unpinned core can probe a different lock namespace (check 2 fail-open)

**File:** `docs/runbooks/gal-07-live-check.sh:92-102` (fallback candidate hardcoded at line 95; duplicated in `tools/tests/gal07_live_runbook_test.py:28`)
**Issue:** The header promises check 2 probes "through the pinned core's own endpoint_key/lock_path/default_lock_dir" — but the candidate loop silently falls back to `$HOME/data/nikko/.venvs/galago-py310/bin/python` when the service-venv python cannot import `stack_automation_layer.owner_lock` (broken/changed venv — a state check 3 does NOT catch, since it only reads `direct_url.json`). The fallback interpreter may host an older/different core whose `default_lock_dir()` resolves a different lock directory, so the probe can answer `LOCK-FREE` against the wrong namespace while a real holder holds the lock under the true one — a `PREFLIGHT OK` with check 2 effectively bypassed. The fallback is also silent (no probe-python-drift line), and the machine-specific path is hardcoded twice (gate + test) with no pin keeping them in sync.
**Fix:** Make the probe fail closed on descent: if the chosen probe python is not `$SERVICES_VENV/bin/python`, emit a `missing:` line naming the interpreter drift (or verify the import resolves from `SERVICES_VENV/site-packages` before accepting any candidate); drive the fallback path from one shared constant instead of two hardcoded copies.

## Finding M-01 (medium) — Check 6 accepts the wanted host among several config tools; a divergent-host stack tool in the store passes silently (D-12 split risk)

**File:** `docs/runbooks/gal-07-live-check.sh:214-224`
**Issue:** The guard is `any stack tool host == STACK_HOST` (`index($want)` — an any-of test), not an all-of test. If the store holds a second stack tool with a different host string (the Phase 6 repair history in row 1a-5 shows the store does churn), the gate passes while a mis-keyed stack tool remains one operator click away — precisely the silent lock/state-key split D-12 and the Safety rules (`gal-07-live-handoff.md:16-19`) exist to prevent. The failure message (line 222, "host string(s)") already anticipates plurality without acting on it.
**Fix:** Require that *every* type-stack tool's configured host equals `$STACK_HOST_PORT` (e.g. `jq 'all(.[]; select((.type? // "") == "stack") | … == $want)'`), failing with the offender's host when not.

## Finding L-01 (low) — Degenerate multi-document runs body silently skips the RUNNING refusal

**File:** `docs/runbooks/gal-07-live-check.sh:241-250`
**Issue:** If `/api/runs` yields multiple JSON documents, `runs_array` holds several lines; `running` then holds digits on multiple lines and `[ "$running" -gt 0 ]` errors, which bash treats as false — neither the empty check nor the running check fires, so check 7 passes without a refusal (fail-open only in inherently degenerate input; offline curl failures are already fail-closed).
**Fix:** Validate `running` is a single non-negative numeral (`case "$running" in ''|*[!0-9]*) fail ;; esac`) before the `-gt` test.

## Finding L-02 (low) — "Exactly an assignment line" overpromise: duplicated `STACK_USER=` lines pass

**File:** `docs/runbooks/gal-07-live-check.sh:35-37` (comment) vs `:257-265` (code)
**Issue:** The header says check 8 verifies the file "holds exactly an assignment line for STACK_USER", but the code only fails on count == 0; a file with two `STACK_USER=` lines passes silently, while runbook Step 2 (`gal-07-live-handoff.md:119`) instructs "exactly one assignment line per credential name".
**Fix:** Treat `env_assigns -ne 1` as the failure/warn condition (not just `-eq 0`) or reword the header to "at least one".

## Finding L-03 (low) — Runbook and BLOCKED footer promise a `forbidden:` line class the gate never emits

**File:** `docs/runbooks/gal-07-live-handoff.md:50` and `docs/runbooks/gal-07-live-check.sh:288`
**Issue:** Both tell the operator to resolve `missing:`/`forbidden:`/`warn:` lines, but no check in the gate ever prints `forbidden:` — dead vocabulary that erodes trust in the enumerated line classes; the footer also tells an operator to "resolve every ... warn: line" although warn lines are explicitly advisory (exit 0).
**Fix:** Either reserve `forbidden:` explicitly in the header/comments before first use or drop it from both texts; reword the footer to "resolve every `missing:` line above".

## Finding L-04 (low) — Check 3 inspects an arbitrarily-ordered dist-info when the venv holds several

**File:** `docs/runbooks/gal-07-live-check.sh:176-178`
**Issue:** `find … -print | head -n 1` picks the traversal-order-first `stack_automation_layer-*.dist-info/direct_url.json`; with two matching trees (upgrade residue) the gate may inspect the wrong one — a different-commit file first fails the check although the pinned version is installed (fail-closed annoyance), or passes while a competing unpinned tree also sits in the venv (ambiguous import resolution).
**Fix:** Iterate all matching `direct_url.json` files and pass only when one records the pinned commit AND no other `stack_automation_layer-*.dist-info` tree exists (report "multiple dist-info trees" otherwise).

## Finding L-05 (low) — Test matrix omits the third blocked owner class named by the gate (`stack-mcp`)

**File:** `tools/tests/gal07_live_runbook_test.py:359-367, 443-451` (vs gate header `gal-07-live-check.sh:25`)
**Issue:** The gate comment promises owner classes `mcp`, `stack-mcp`, and unknown/absent all block; the falsification matrix pins `mcp` (`held_lock` case) and unknown (`holder_owner=None`) but never `holder_owner="stack-mcp"`. Same code path today (single `== "galago"` branch), so this is a pin-gap, not an open hole — but the promised matrix is not fully nailed down.
**Fix:** Add a `held_lock`-style subtest with `holder_owner="stack-mcp"` asserting the "only one front end may hold it" block.

## Finding L-06 (low) — Test matrix omits the stale-record trial (record present, no live flock → LOCK-FREE)

**File:** `tools/tests/gal07_live_runbook_test.py:270-286` (holder setup)
**Issue:** Both holder pins exercise the live-flock branch (`BlockingIOError`); nothing pins the other green direction — a leftover 256-byte holder record with no live flock must still read LOCK-FREE (the probe flocks *first* and reads the record only under contention). A regression that treated any present record as held would false-block every pre-flight after an unclean exit.
**Fix:** Add a trial that writes the record + releases/never takes the flock and asserts exit 0 with `PREFLIGHT OK` and no lock line.

## Finding L-07 (low) — Credential-leak regex misses quoted and whitespace-padded values

**File:** `tools/tests/gal07_live_runbook_test.py:565-567`
**Issue:** `STACK_(USER|PASSWORD)=[^\s$"']` requires the char right after `=` to be a non-space non-quote, so `STACK_USER="secret"` or an inline-commented assignment slips through the pin that is supposed to certify the runbook stays credential-free.
**Fix:** Widen to reject any `STACK_(USER|PASSWORD)\s*=` occurrence in the runbook text (references-without-value are the sanctioned form anyway) or explicitly enumerate the two allowed shapes and assert everything else breaks.

## Finding L-08 (low) — The galago-holder exemption trusts the record's owner string uncorroborated

**File:** `docs/runbooks/gal-07-live-check.sh:136-145`
**Issue:** When a live flock exists, the probe prints `GALAGO-OWNED` purely from the record's `owner` field: any holder (or its stale record rewritten under a re-acquired flock) that names owner `galago` is reported as "the session's own STACK tool server" without verifying the pid is this deployment's tool server. Flock exclusivity (one live lock holder) and the local single-frontend deployment bound the risk, so this is residual-trust documentation rather than a live hole.
**Fix:** Corroborate with a cheap `kill -0 $pid` + readlink of the holder pid's argv within the probe (still read-only), or record the exemption's trust boundary as an accepted decision in the runbook Safety rules.

## Review Complete
