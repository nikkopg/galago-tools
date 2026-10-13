# Phase 3: Deploy & Supervised Live Acceptance - Context

**Gathered:** 2026-10-14
**Status:** Ready for planning (execution is blocked on the entry gate, D-01)
**Mode:** `--auto` (every gray area resolved with the recommended option; see 03-DISCUSSION-LOG.md)

<domain>
## Phase Boundary

The live-control stack from Phases 1-2 (and galago-core's companion milestone) runs on forb01 and is
proven on the real F.A.S.T. (`10.150.1.170:5003`, tool port `40001`) with an operator present:

- **LIVE-04:** deploy in the safe order: fast-mcp core `b30b38d` into the service `.venv`, restart
  `galago-tools`, rebuild `galago-web`.
- **LIVE-05:** deck-3 scenario: an instrument pause names the deck and plate, the operator fixes the
  deck and resumes, and the same step ends SUCCESS.
- **LIVE-06:** Pause → Resume → SUCCESS; Pause → Abort → "aborted by operator", queue FAILED.
- **LIVE-07:** restart `galago-web` mid-run, then recover through the tool page's Resume or Abort.

This phase is mostly **operations and evidence**, not code. Code changes happen only as gap fixes
for a failed scenario (D-14).

**Not in this phase:**
- New adapter features, hard pause (D5), a second `runControl` tool type.
- galago-core queue/UI work (its own `.planning/`; Phase 3 consumes its finished milestone).
- Pushing any branch to GitHub or GitLab (the user's action; see D-02, Deferred).
- galago-core F5/F3 debt.
- Editing `tools/base_server.py`.

</domain>

<decisions>
## Implementation Decisions

### Entry gate (prerequisites)
- **D-01:** Phase 3 execution does not start until all of these hold. The first plan task checks
  them and stops (checkpoint) if any fails:
  1. galago-core's "Live Run Control: queue & run page" milestone is complete and verified (on
     2026-10-14 its Phase 2 is at plan 5 of 6, so this is **not yet met**).
  2. This repo's gate is green on `feat/fast-tool` (`bin/make proto test`, 143 tests at Phase 2).
  3. galago-core's `vendor/galago-tools` submodule points at a commit with `StatusReply.run_state`
     and the `Pause` command (today `cb7886d`, which has both; Phase 2 changed no proto), and its
     `tsc` and tests are green.
  4. The local fast-mcp clone has `b30b38d` (branch `fix/run-recovery-gate`).
- **D-02:** Install the service `.venv` core **from the local fast-mcp clone at the pinned SHA**,
  as every forb01 deploy so far has (`76f8c3f` on 2026-10-12):
  `~/.local/bin/uv pip install --python .venv/bin/python "git+file:///home/formulatrix/data/nikko/fast/fast-mcp@b30b38df48e8480f325228145ccae7915a56e437"`
  (the service `.venv` is uv-managed; no pip). Pushing `fix/run-recovery-gate` to GitLab is
  **not** a blocker for this deploy; it stays the user's action and is needed only for a clean
  install from the pin URL elsewhere. — **Reversibility:** reversible — reinstall `76f8c3f` the same way.

### Deploy procedure (LIVE-04)
- **D-03:** Deploy is a written runbook in the phase dir (`03-DEPLOY.md` or a plan section) with the
  exact commands, a check after each step, and the rollback. Claude runs the non-motion steps
  itself, **after the user's explicit go-ahead for the deploy as a whole** (it restarts a shared
  service and the web app). No motion happens during deploy.
- **D-04:** Pre-deploy checks: no Galago run in flight (queue idle), instrument idle (read-only
  `GetStatus`), and the current SHAs recorded for rollback: service `.venv` core `76f8c3fe`,
  galago-tools deployed checkout, galago-core deployed checkout (last recorded deploy:
  galago-tools `7c0ff7b`, galago-core `ce8d40d`; the checkouts have since moved on locally, so the
  runbook records `git rev-parse HEAD` and the running image ID at deploy time).
- **D-05:** Safe order with a check after each step, so there's never a window where the new UI
  runs against an ungated core:
  1. Install the core into `.venv` (D-02). Check: `direct_url.json` `commit_id == b30b38d…`, and the
     same capability/state-gate checks as the LIVE-01 gate tests (`RunOptions.through_pauses`/
     `on_pause`, `PauseInfo` importable, `Refused` from `pause`/`resume`/`abort` on an idle stub),
     run against `.venv/bin/python`.
  2. `systemctl --user restart galago-tools`. Check: service active, journal clean, the F.A.S.T.
     tool reachable on `:40001`, health `GetStatus` returns `run_state` (read-only).
     The old `galago-web` against the new adapter is safe in this window: the proto change is
     additive and the old UI never sends `Pause`.
  3. Rebuild `galago-web` from galago-core `feat/fast-tool` (`TOOLBOX_PORT=11010 docker compose up -d
     --build`, `.dockerignore` present). Check: container up, run page loads, the F.A.S.T. tool
     shows the control bar capability.
  The deploy evidence (commands, SHAs, check output) goes into the phase record.
- **D-06:** Rollback is the reverse order: previous `galago-web` image/checkout first, then the
  previous galago-tools checkout + restart, then core `76f8c3f` into `.venv`. Never roll the core
  back while the new UI and adapter are running. — **Reversibility:** reversible — every step is a
  reinstall/restart of a recorded SHA.

### Acceptance protocol (LIVE-05, LIVE-06, LIVE-07)
- **D-07:** **Simulated dry run first, no motion:** after deploy, run the run-page and tool-page
  flows against a simulated F.A.S.T. tool (the `simulate_pause` hook, ADP-10) to confirm the
  control bar, the `tool_paused` modal, the Stop confirmation and the tool-page controls render and
  send the right commands. Only then move to the instrument.
- **D-08:** Every live scenario is driven by the operator through the Galago UI, at the instrument,
  e-stop within reach. Claude prepares each scenario (protocol/queue setup that causes no motion,
  the checklist, the expected observations), then **stops and waits for the operator's explicit
  go-ahead before every step that moves the head** (start run, Pause, Resume, Abort). Claude never
  sends a motion or control command itself during acceptance. Claude watches
  `journalctl --user -u galago-tools` and read-only status, and records what it sees.
- **D-09:** Scenario order, least to most disruptive:
  1. Pause → Resume → SUCCESS (LIVE-06a)
  2. Deck-3 empty → prompt → fix deck → Resume (tip intact) → SUCCESS (LIVE-05)
  3. Pause → Abort → "aborted by operator", queue FAILED (LIVE-06b)
  4. Restart `galago-web` mid-run → tool-page recovery (LIVE-07)
  A failure stops the sequence (D-14).
- **D-10:** Transfer setup: reuse the plates and plate definitions registered for the GAL-05
  supervised transfer (2026-10-09), water only, a multi-well block sized so the run lasts long
  enough to pause mid-run. Exact wells and volume are the operator's call at the time; the plan
  proposes values and asks.
- **D-11:** Pass criteria per scenario (all must be observed and recorded):
  - **LIVE-06a:** run page shows PAUSED with percent after Pause; the step stays open; after Resume
    the state returns to running and the step ends SUCCESS.
  - **LIVE-05:** the `tool_paused` modal shows the reason (e.g. `WrongPlateType (-645)`) and
    "Deck 3: expected plate 1, found none" (wording as rendered from `PauseInfo.eventPayload`);
    nothing is preselected; after the deck fix + Resume (tip intact "no") the **same** step ends
    SUCCESS, with no retry or second step.
  - **LIVE-06b:** the Abort choice (return liquid) has no preselection; the step ends
    `ERROR_FROM_TOOL` "run aborted by operator at <p>%"; the queue is FAILED and no later step runs.
    One abort run is enough; the operator picks yes or no at the time and the record notes which.
  - **LIVE-07:** see D-12.
  - For every scenario: no pause/resume/abort appears in the journal that the operator didn't send
    (Safety invariant 1).
- **D-12:** Restart scenario (LIVE-07): start a transfer, operator Pauses it (so the run is held in a
  known state), then `docker restart galago-web` (or `docker compose restart`). After the restart:
  the run page shows no control bar (expected, design §8); from the **tool page** the operator sends
  Resume (tip intact) — the in-flight path returns on acceptance — and the instrument finishes. Pass
  when the instrument run completes, the adapter's original `Transfer` wait ends (journal), the
  motion lock clears, and a following short command on the tool runs normally. Abort from the tool
  page is the fallback if Resume is refused.
- **D-13:** Evidence lives in `03-ACCEPTANCE.md` (or the phase VERIFICATION/UAT record): per
  scenario the date/time, operator, transfer parameters, decisions chosen, journal excerpt, the
  final step result and queue state, and screenshots of the run page/modal when available.
  Requirements LIVE-04..07 are marked complete only from this evidence.

### Failure handling
- **D-14:** If a scenario fails, stop: the operator makes the instrument safe (tool page or the
  instrument itself). Claude does not retry or recover on its own. Diagnose with `/gsd-debug` in the
  repo that owns the fault; fixes go through the normal gate (and, for galago-core, its own
  planning) as gap work, then redeploy in the safe order (D-05) and rerun from the failed scenario.
  Phase 3 is complete only when all four scenarios pass on the deployed build.

### Claude's Discretion
- Whether the runbook is a separate `03-DEPLOY.md` or a plan section; how the capability check in
  D-05 step 1 is run against `.venv` (one-off script vs reusing the gate test module).
- Plan split: a natural order is (1) entry gate + deploy, (2) simulated dry run, (3) live scenarios
  with an operator checkpoint per scenario. Live plans are `autonomous: false`.
- Exact wording of the operator checklists.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Governing design
- `docs/specs/2026-10-12-galago-live-run-control-design.md`:
  - §3: interaction model and physical decisions;
  - §6.3-6.6: what the run page, `tool_paused` modal and Stop confirmation should show;
  - §7: safety invariants (only operators command recovery);
  - §8: failure modes (galago-web restart mid-run, motion lock held until the wait ends);
  - §9: supervised live acceptance scenarios;
  - §10 step 4: deploy order.
- `.planning/REQUIREMENTS.md`: LIVE-04..07.
- `.planning/ROADMAP.md`: Phase 3 success criteria and safety note.
- `.planning/PROJECT.md`: Constraints (no motion in default tests; supervised live checks only with
  the operator's go-ahead), deployment rule.
- `.planning/phases/02-wait-through-pauses-on-the-pinned-core/02-CONTEXT.md`: D-02 (install from the
  local clone), D-03 (LIVE-01 capability/state-gate checks to repeat against `.venv`), D-09 (abort
  wording).
- `.planning/phases/01-adapter-control-path-run-state/01-CONTEXT.md`: D-07 (Resume's two paths, the
  basis of LIVE-07), D-11/D-12 (run_state shape), D-19/D-20 (simulated hook for the dry run).

### Companion milestone (read-only)
- `../galago-core/.planning/ROADMAP.md`, `STATE.md`: the entry-gate check (D-01).
- `../galago-core/.planning/phases/02-run-page-live-controls/`: the UI the operator will use.

### Gate and pin
- `tools/fast/requirements.txt`: pin `b30b38df48e8480f325228145ccae7915a56e437`.
- `tools/tests/fast_test.py` `TestRequirementsPin`: the capability/state-gate checks to repeat.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `TestRequirementsPin` LIVE-01 checks (Phase 2): reuse their logic to verify the service `.venv`.
- `FastServer.simulate_pause` (Phase 1, ADP-10): drives the simulated dry run (D-07).
- Health `GetStatus` → `run_state`: read-only post-restart check.

### Established Patterns
- Service: systemd user unit `galago-tools` (`galago --http-port 8081 --host 0.0.0.0
  --toolbox-port 11010`), journal via `journalctl --user -u galago-tools`.
- `galago-web`: Docker, built from local galago-core source, `GRPC_HOST=host.docker.internal`;
  ufw already allows the tool ports.
- The service `.venv` is uv-managed; current core `76f8c3fe` from the local clone.
- Claude desktop shells need `export PATH=$HOME/.local/bin:$HOME/.nvm/versions/node/v24.14.1/bin:$PATH`.

### Integration Points
- `.venv` (core), `galago-tools` service, `galago-web` container, galago-core `vendor/galago-tools`
  submodule, the F.A.S.T. at `10.150.1.170:5003`.

</code_context>

<specifics>
## Specific Ideas

- The deck-3 scenario reproduces the 2026-10-12 incident where an empty deck 3 paused the
  instrument (`-645`) and the old Galago step ended instead of waiting.
- The restart scenario exercises the design's claim that the tool page's control commands work
  while the orphaned `Transfer` thread holds the motion lock.

</specifics>

<deferred>
## Deferred Ideas

- Pushing fast-mcp `fix/run-recovery-gate` to GitLab, and `feat/fast-tool` of both Galago forks to
  GitHub (`nikkopg` only, never upstream): the user's action, not needed for the forb01 deploy.
- Crash-recovery `Resume` reporting `run_state` from the adapter's record (carried from Phase 2).
- Splitting `EstimateResume`; hard pause (D5); a second `runControl` tool type.
- A `galago-tools` restart mid-run scenario (design §8 row 2) — not a LIVE requirement.

</deferred>

---

*Phase: 03-deploy-supervised-live-acceptance*
*Context gathered: 2026-10-14*
