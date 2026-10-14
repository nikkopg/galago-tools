# Phase 3 Acceptance Evidence (D-13)

Evidence record for the deploy and supervised live acceptance scenarios. Fed from
`03-DEPLOY.md`'s runbook/evidence where noted. Created by plan 03-02; later plans in this
phase (03-03 to 03-08) fill the remaining sections.

## Summary

| Requirement | Scenario | Result | Evidence |
|---|---|---|---|
| LIVE-04 | LIVE-04 Deploy (core → galago-tools → galago-web, safe order) | PASS | `03-DEPLOY.md` Deploy evidence table (Steps 1, 2, 2b reconnect, Step 3 cached + no-cache); `## LIVE-04 Deploy` below |
| — | Dry run (D-07) | not run | — |
| LIVE-06 | LIVE-06a: Pause → Resume → SUCCESS | not run | — |
| LIVE-05 | LIVE-05: Deck 3 empty → prompt → fix deck → Resume → SUCCESS | not run | — |
| LIVE-06 | LIVE-06b: Pause → Abort → aborted by operator, queue FAILED | not run | — |
| LIVE-07 | LIVE-07: galago-web restart mid-run → tool-page recovery | not run | — |

## LIVE-04 Deploy

- **Date/time:** 2026-10-14, 2026-10-14T10:38:29Z (Step 1 start) through 2026-10-14T13:10:08Z
  (no-cache Step 3 `docker compose up -d` complete), UTC.
- **Operator:** the user gave the go-ahead (D-03, literal reply `go`) and reconnected the
  production F.A.S.T. tool from `galago-web` (Step 2b, Simulate off, configuration unchanged);
  the user also made the Step 3 "No cache rebuild" decision after the cached attempt's finding.
  Claude ran every command and check; Claude sent no `Configure`, `ExecuteCommand`, or any
  other command to any tool.
- **SHAs and images:**
  - Service core (fast-mcp): pre-deploy `76f8c3fee41b0a2df3519aa74b022152df673824` → deployed
    `b30b38df48e8480f325228145ccae7915a56e437`.
  - `galago-tools` deployed HEAD: `fdbe1303b102c877e67ce9bca18600cc9ac8ed64` (last code commit
    `d9acdcf0e8f203cd553aaafad2e262b387bcdc06`); running adapter SHA before restart was
    `7c0ff7b953986bbc62221a14bad8b9594795b1f4`.
  - `galago-core` HEAD (entry-gate and both Step 3 attempts, unchanged throughout):
    `d95c2e143ca13d8837bd9c248d6579777b2ebdc9`.
  - `galago-web` image before: `sha256:9ad9c64fee6baa7ea9351c7cfa03bceb8f0db7f974fabbb6865b1143948880ca`
    (also tagged `galago-core-galago-web:rollback-pre-live04`).
  - `galago-web` image after (final, no-cache rebuild):
    `sha256:26917ca79a781bb3b3563b481d1845ce1defeb92c33a0dc97e9368baf39029a2`.
- **Step checks:**
  - Step 1 (core into the service `.venv`, D-05 step 1): PASS — `direct_url.json` pinned to
    `b30b38d`, `TestRequirementsPin` 3/3 `OK`, freeze diff shows only `fast-mcp` changed.
  - Step 2 (restart `galago-tools`, D-05 step 2): PASS — `is-active` → `active`, new MainPID
    `4044033`, journal/trace-log clean, no traceback.
  - Step 2b (operator reconnect, plan 03-02 Task 1): PASS — `fast_status.py --port 40001` →
    `READY`/`run_state.state: idle`; `F.A.S.T.log` shows a real-mode `Received configuration`
    line with the pre-deploy host/port/`expected_tray_id` and no `simulated` flag; non-blocking
    observation: the operator needed to navigate away from and back to the tools page to see
    the `READY` status render (UI staleness, not a functional blocker).
  - Step 3, cached attempt (D-05 step 3, plan 03-02 Task 2): BLOCKED, not scored PASS/FAIL —
    every content/connectivity/safety check PASSed (`/api/health` 200, `/runs` 200,
    `is_tip_broken` under `/app/.next/server`, `run_state` under `/app/gen-interfaces`, host
    port reachable, `fast_status.py` READY/idle, `galago-tools` MainPID unchanged), but the
    rebuild reused Docker's cache for every layer (galago-core `controller/` unchanged since an
    out-of-runbook rebuild already recorded in `03-DEPLOY.md`'s Pre-deploy record) and produced
    a running image ID byte-identical to `rollback-pre-live04`.
  - Step 3, no-cache rebuild (user decision "No cache rebuild"): PASS — re-confirmed read-only
    before the rebuild (no run `RUNNING`, `fast_status.py` READY/idle, `galago-tools`
    MainPID/`galago-core` HEAD unchanged); `rollback-pre-live04` left untouched; ran
    `docker compose build --no-cache galago-web` then `docker compose up -d` (the compose file
    defines only the `galago-web` service, so nothing else was recreated); the running image ID
    (`sha256:26917ca7...`) differs from the rollback tag and every Step 3 check PASSed.
- **Safe order (the four times, strictly increasing):** step 1 check passed
  `2026-10-14T10:38:46Z` < `galago-tools` restart `2026-10-14T10:39:24Z` < step 2 run_state
  check passed `2026-10-14T10:50:24Z` < `galago-web` build start `2026-10-14T13:08:07Z`
  (the no-cache rebuild that produced the final PASSing result).
- **Rollback anchors:** `galago-core-galago-web:rollback-pre-live04` =
  `sha256:9ad9c64fee6baa7ea9351c7cfa03bceb8f0db7f974fabbb6865b1143948880ca`; service core
  rollback target `76f8c3fee41b0a2df3519aa74b022152df673824`; running adapter SHA rollback
  target `7c0ff7b953986bbc62221a14bad8b9594795b1f4`. **Caveat:** `rollback-pre-live04` was built
  at `2026-10-14T08:10:47Z` from the same `galago-core` HEAD `d95c2e1` as the final deploy, so
  rolling `galago-web` back to it restores identical content, not the pre-milestone UI; a true
  pre-milestone rollback needs a fresh rebuild from the pre-milestone `galago-core` commit (see
  `03-DEPLOY.md` Rollback (D-06) section).
- **Result: PASS** — every Step 1/2/2b/3 check PASSed (Step 3 PASSed on the no-cache rebuild
  after the cached attempt's documented, non-blocking finding was resolved by explicit user
  decision); the safe order holds; rollback anchors are recorded for every layer.

## Dry run (D-07)

(Not run — plan 03-03 fills this section.)

## LIVE-06a: Pause -> Resume -> SUCCESS

(Not run — plan 03-04 fills this section.)

## LIVE-05: Deck 3 empty -> prompt -> fix deck -> Resume -> SUCCESS

(Not run — plan 03-05 fills this section.)

## LIVE-06b: Pause -> Abort -> aborted by operator, queue FAILED

(Not run — plan 03-06 fills this section.)

## LIVE-07: galago-web restart mid-run -> tool-page recovery

(Not run — plan 03-07 fills this section.)

## Safety invariant audit

(Not run — a later plan in this phase fills this section.)

## Flagged assumptions

- **A-EDGE-LIVE-04** (edge-probe fallback, `unclassified` / `unresolved`): deploy edge cases
  were not auto-classified. Handled explicitly, not silently: plan 03-01 stops the deploy on
  any failed check and rolls back in reverse order only on the user's go-ahead; plan 03-02
  compared the Step 3 cached-rebuild finding against the reconnect host's pre-deploy record
  rather than assuming it, stopped on the finding, and proceeded only after the user's explicit
  "No cache rebuild" decision.
- **A-EDGE-LIVE-05** (edge-probe fallback, `unclassified` / `unresolved`): the instrument's
  exact `eventPayload` shape for the deck-3-empty pause is not assumed; plan 03-05's record
  quotes both the raw payload and the rendered text. Plan 03-03's dry run also exercises the UI
  paths this scenario uses, without hardware.
- **A-EDGE-LIVE-06** (edge-probe fallback, `unclassified` / `unresolved`): pause/resume edges
  were not auto-classified. Plan 03-04 checks the step stays open and ends with the run's real
  outcome, stopping on anything else; plan 03-06 treats the F.A.S.T.log as the authoritative
  source for the step's reply if the run view shows no error text (galago-core debt F3, out of
  scope here), and the record says so. Plan 03-03's dry run also exercises these UI paths
  without hardware.
- **A-EDGE-LIVE-07** (edge-probe fallback, `unclassified` / `unresolved`): after a
  `galago-web` restart mid-run, the queue is assumed not to re-dispatch the held step (design
  section 8, not re-verified by probe); plan 03-07 checks for any new `Transfer` command after
  the restart and stops if one appears. Plan 03-03's dry run also exercises these UI paths
  without hardware.
- **Edge-probe fallback accounting for the phase:** 4 items surfaced (A-EDGE-LIVE-04 to 07), 0
  authored into truths as resolved edges, all 4 carried as flagged assumptions here, each with
  the plan that handles it.
- **RESEARCH A1:** a throwaway stdin-driven harness script is the right shape for driving
  `simulate_pause` during the dry run (no existing prior art confirms this exact approach) —
  low risk, disposable dev-only script; plan 03-03 owns this.
- **RESEARCH A2:** galago-core's UAT test 5 (deck-3/pause-prompt) being satisfied by this
  phase's LIVE-05 scenario is a reasonable cross-repo inference, not something either repo's
  planning doc states explicitly as linked — low risk; worst case the user re-runs galago-core's
  UAT test 5 separately.
- **RESEARCH A3:** ufw rules for ports 40001/11010/3010 are already correctly configured (not
  re-verified via `sudo ufw status`, which requires a password unavailable non-interactively) —
  low-to-medium risk in principle, but plan 03-02's Step 3 checks (both the cached and the
  no-cache attempt) confirmed the container reaches `host.docker.internal:40001` directly,
  resolving this assumption for the deploy itself; no new port was introduced.
