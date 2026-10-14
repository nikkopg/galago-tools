# Phase 3: Deploy & Supervised Live Acceptance - Research

**Researched:** 2026-10-14
**Domain:** Production deployment runbook + supervised hardware acceptance testing (no new application code expected)
**Confidence:** MEDIUM — the deploy procedure and most environment facts are `[VERIFIED]` this session; the acceptance-scenario mechanics (especially the simulated dry run) rest on real gaps in existing tooling, tagged `[ASSUMED]`/Open Questions below.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Entry gate (prerequisites)**
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

**Deploy procedure (LIVE-04)**
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

**Acceptance protocol (LIVE-05, LIVE-06, LIVE-07)**
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

**Failure handling**
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

### Deferred Ideas (OUT OF SCOPE)
- Pushing fast-mcp `fix/run-recovery-gate` to GitLab, and `feat/fast-tool` of both Galago forks to
  GitHub (`nikkopg` only, never upstream): the user's action, not needed for the forb01 deploy.
- Crash-recovery `Resume` reporting `run_state` from the adapter's record (carried from Phase 2).
- Splitting `EstimateResume`; hard pause (D5); a second `runControl` tool type.
- A `galago-tools` restart mid-run scenario (design §8 row 2) — not a LIVE requirement.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LIVE-04 | Deployed in the safe order: core into the service `.venv`, restart `galago-tools`, rebuild `galago-web` | Deploy procedure verified against the live forb01 host (current running SHAs, service unit, docker compose config) — see Architecture Patterns §1 and Code Examples |
| LIVE-05 | Supervised live: deck 3 empty → pause prompt shows "Deck 3: expected plate 1, found none" → fix the deck → Resume (tip intact) → the same step ends SUCCESS | Confirmed the wording source (`PauseInfo.eventPayload`) and that this exact scenario is the one galago-core's own Phase 2 UAT explicitly defers to this phase (see Pitfall 1) |
| LIVE-06 | Supervised live: Pause → Resume → SUCCESS; Pause → Abort (return liquid yes/no) → "aborted by operator", queue FAILED | Verified exact abort message string in `tools/fast/server.py:350`; verified `galago-core`'s Stop/Abort confirmation modal is the new no-timer modal, not the auto-confirming `StopRunModal` |
| LIVE-07 | Supervised live: restart `galago-web` while a step runs, then recover through the tool page's Resume or Abort | Verified `docker compose` restart mechanics and that the adapter's motion lock is unaffected by a gRPC client disconnect (design §8, confirmed against `FastServer` code) |
</phase_requirements>

## Summary

This phase ships no new product code under normal conditions — it is a deployment runbook plus a
four-scenario supervised hardware acceptance test, executed by a human operator at the instrument
with Claude preparing and observing. Research this session focused on **verifying the actual state
of the forb01 host and the two dependent repos right now**, because the CONTEXT.md entry gate
(D-01) is a hard checkpoint and its preconditions change daily as both repos' phases progress.

**Critical finding: the entry gate is currently NOT met.** `[VERIFIED: this session]` galago-core's
companion milestone (`galago-core/.planning/phases/02-run-page-live-controls/02-UAT.md`) shows
`status: testing`, 8/8 tests `pending`, 0 passed — the conversational UAT for its Phase 2 has not
been run yet. Its `02-VERIFICATION.md` independently reports `status: human_needed`, `12/16
must-haves verified`, with the deck-3/pause-prompt scenario explicitly listed as a manual item
deferred to "galago-tools' supervised live acceptance" (this phase). The planner's first task must
be the D-01 checkpoint, and as of this research it will stop there — this is expected, not a
planning defect.

The deploy mechanics themselves are well-understood and low-risk: the currently running service
`.venv` core is `76f8c3fee41b0a2df3519aa74b022152df673824` `[VERIFIED: direct_url.json]`,
`galago-tools` runs as a healthy systemd **user** unit (no `sudo` needed to restart it)
`[VERIFIED: systemctl --user status]`, and `galago-web` runs as a healthy Docker container rebuilt
from local source `[VERIFIED: docker ps]`. The main technical risk is not the deploy order (already
proven twice on this host) but the **simulated dry run (D-07)**: the `simulate_pause` test hook has
deliberately **no gRPC surface** — it is an in-process Python method only reachable from test code
or a throwaway script, not from the already-running systemd service. Nobody has built a documented
way to drive it during manual QA (confirmed by searching both repos for prior art — none exists).
This is the one place in the phase where "Claude's Discretion" genuinely needs a concrete, reviewed
plan, not an on-the-fly script.

**Primary recommendation:** Plan the phase in the three waves CONTEXT.md already suggests (entry
gate + deploy → simulated dry run → live scenarios), but make the dry-run wave's first task a
*design* task (not an execution task): write and get a look over a short-lived helper script that
runs a second `FastServer` instance in simulated mode on a spare port with a stdin-driven loop
calling `simulate_pause`, point `galago-core`'s Tool Box at that port temporarily, run the dry
checks, then tear it down — never touching the production `:40001` instance or `tools/base_server.py`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Core install into service `.venv` | Host / Package management (uv) | — | `uv`-managed venv on forb01, outside any tier's runtime; a pure ops step |
| `galago-tools` process supervision | Host / systemd (user unit) | API/Backend (the gRPC tool servers it runs) | systemd owns start/stop/restart; the gRPC servers inside are the API tier |
| `galago-web` container lifecycle | Host / Docker | Frontend Server (SSR, Next.js) | `docker compose` owns the container; the app inside is galago-core's SSR/queue tier |
| Instrument motion and state gates | External device (F.A.S.T. via fast-mcp core) | API / Backend (adapter pass-through) | The core (fast-mcp) owns every state gate per design §7 invariant 2; the adapter adds none |
| Pause/Resume/Abort command path | API / Backend (`FastServer.ExecuteCommand` override) | Browser / Client (operator's button press) | Operator-originated per design §7 invariant 1; adapter is pure pass-through |
| Run-state visibility / polling | API / Backend (`GetStatus.run_state`) | Frontend Server (galago-core's 2s poll) | Read-only observation (design §7 invariant 4); adapter publishes, galago-core consumes |
| Acceptance evidence capture | Host / operator + Claude (read-only) | — | No code tier owns this; it is an operational record (`03-ACCEPTANCE.md`) |

## Standard Stack

### Core
No new libraries are introduced by this phase. The phase operates the stack already built in
Phases 1-2:

| Component | Version | Purpose | Why Standard |
|-----------|---------|---------|--------------|
| fast-mcp core | `b30b38df48e8480f325228145ccae7915a56e437` | Instrument driver with wait-through-pauses, state-gated pause/resume/abort | `[VERIFIED: tools/fast/requirements.txt:5]` — pinned by SHA; already gated by Phase 2's `TestRequirementsPin`/`test_installed_core_has_wait_through_pauses_and_pause_info` |
| uv | 0.11.2 | Installs the pinned core into the service `.venv` | `[VERIFIED: ~/.local/bin/uv --version]`; D-02 mandates uv, not pip, for this venv |
| systemd (user) | host-provided | Supervises `galago-tools` | `[VERIFIED: systemctl --user status galago-tools]` — unit loaded, active, enabled; **no sudo required** to restart it |
| Docker / Docker Compose | Compose v2.29.1 | Builds and runs `galago-web` | `[VERIFIED: docker compose version]`; user is in the `docker` group, no sudo needed |

### Supporting
| Component | Version | Purpose | When to Use |
|-----------|---------|---------|-------------|
| Python | 3.10.12 | Gate venv for `bin/make proto test` | `[VERIFIED: $HOME/data/nikko/.venvs/galago-py310/bin/python --version]` |
| `journalctl --user -u galago-tools` | host-provided | Live observation during acceptance scenarios | Per D-08, Claude watches this and read-only status, never sends commands |

### Alternatives Considered
Not applicable — this phase deploys and verifies existing code; it does not select new libraries.

**Installation:** No package installation beyond the pinned core re-install already specified in
D-02 (reproduced here verified against the live host):
```bash
~/.local/bin/uv pip install --python .venv/bin/python \
  "git+file:///home/formulatrix/data/nikko/fast/fast-mcp@b30b38df48e8480f325228145ccae7915a56e437"
```

**Version verification:** `[VERIFIED: direct_url.json]` — the service `.venv` currently has
`fast_mcp` installed from `file:///home/formulatrix/data/nikko/fast/fast-mcp` at commit
`76f8c3fee41b0a2df3519aa74b022152df673824` (full content below in Code Examples). The local
fast-mcp clone's `fix/run-recovery-gate` branch HEAD is `b4b67d8`, and
`git merge-base --is-ancestor b30b38df48e8480f325228145ccae7915a56e437 HEAD` returned true
`[VERIFIED: git merge-base, this session]` — the pin commit is present and reachable from the local
clone that D-02's `file://` URL points at, so the install command will succeed without network
access to GitLab.

## Package Legitimacy Audit

**Not applicable to this phase.** The only "package" install is the fast-mcp core, pinned by full
40-character SHA and installed via `git+file://` from an already-vetted private GitLab clone
(`nikkopg/fast-mcp`), not a public package registry. There is no npm/PyPI/crates install to run
through the legitimacy gate, and no new dependency is added to `requirements.txt` or `package.json`
by this phase.

**Packages removed due to [SLOP] verdict:** none (gate not applicable)
**Packages flagged as suspicious [SUS]:** none (gate not applicable)

## Architecture Patterns

### System Architecture Diagram

```
                     ┌─────────────────────────────────────────────┐
                     │   forb01 host (10.150.1.138)                 │
                     │                                               │
  Operator ──click──▶│  galago-web (Docker :3010)                   │
  (run page /        │    - run page: control bar, tool_paused      │
   tool page)        │      modal, Stop confirmation                │
                     │    - polls run_state every ~2s while a        │
                     │      controllable step runs (read-only)       │
                     │           │         ▲                         │
                     │   toolControl        │ GetStatus.run_state     │
                     │   (Pause/Resume/     │ (read-only)             │
                     │    Abort, direct     │                         │
                     │    gRPC, not an      │                         │
                     │    enqueued step)    │                         │
                     │           ▼         │                         │
                     │  galago-tools (systemd user unit, :8081/      │
                     │                :11010 Tool Box)                │
                     │    FastServer (:40001)                        │
                     │      - ExecuteCommand override: Pause/Resume/ │
                     │        Abort bypass BUSY gate + motion lock   │
                     │      - Transfer/RunProtocol hold the motion   │
                     │        lock, wait through pauses              │
                     │           │         ▲                         │
                     │   pause/resume/      │ status()/run_state      │
                     │   abort/wait         │                         │
                     │           ▼         │                         │
                     │  fast-mcp core (service .venv)                │
                     │    FastService — owns EVERY state gate         │
                     └───────────│──────────────────────────────────┘
                                 │ HTTP (OpenAPI)
                                 ▼
                      F.A.S.T. instrument (10.150.1.170:5003)
```
Deploy flow (LIVE-04) moves bottom-to-top: core into `.venv` first, then `galago-tools` restart,
then `galago-web` rebuild — so the UI layer is always the last thing to see a new contract, never
the first (design §10 step 4).

### Recommended Project Structure
No new source directories. Phase artifacts live alongside existing phase docs:
```
.planning/phases/03-deploy-supervised-live-acceptance/
├── 03-RESEARCH.md          # this file
├── 03-DEPLOY.md            # the runbook (Claude's Discretion: separate file vs plan section)
├── 03-0N-PLAN.md           # per-wave plans
└── 03-ACCEPTANCE.md        # evidence record (D-13)
```

### Pattern 1: Safe-order deploy with a check gate after each step
**What:** Never advance to the next deploy step until the current one's check passes.
**When to use:** Every deploy step in D-05.
**Example (step 1 check, reusing the LIVE-01 gate pattern verified this session):**
```python
# Source: tools/tests/fast_test.py:3422-3445 (TestRequirementsPin, Phase 2) — run the same
# checks against .venv/bin/python as a one-off script per D-05 step 1's check.
option_fields = {f.name: f for f in fields(RunOptions)}
assert "through_pauses" in option_fields
assert option_fields["through_pauses"].default is False
assert "on_pause" in option_fields

assert PauseInfo.__module__ == "fast_mcp.orchestration"

transport = MagicMock()
core = _real_core(transport)          # real FastService over a stub transport
pause_result = core.pause(hard=False)
assert isinstance(pause_result, Refused)   # idle core refuses, no transport call
```
`[VERIFIED: tools/tests/fast_test.py:3405-3465, this session]` — this is the exact test body
already in the repo; D-05 step 1's check is "the same capability/state-gate checks as the LIVE-01
gate tests... run against `.venv/bin/python`", so the cheapest correct implementation is importing
and invoking these same two test methods against `.venv/bin/python` rather than hand-rolling new
checks (Claude's Discretion explicitly leaves this choice open).

### Pattern 2: Toggling "Simulated" is a normal Galago operation; `simulate_pause` is not
**What:** The F.A.S.T. tool's simulated/real mode is a per-tool `Config.simulated` field, set via
the standard `Configure` RPC (`tools/base_server.py:89-119`) — i.e. the ordinary "Simulated"
checkbox in Galago's Tool Box UI. This is safe to flip on an already-registered tool and does not
need a code change or a new process.

`simulate_pause(pause: Optional[dict])`, however, is declared as "In-process test hook... no new
gRPC command" `[VERIFIED: tools/fast/server.py:610-625, read this session]`:
```python
def simulate_pause(self, pause: Optional[dict[str, Any]]) -> None:
    if not self.simulated:
        raise RuntimeError("simulate_pause is only available in simulated mode")
    if pause is None:
        self._clear_pause()
    else:
        self._record_pause(_DictPauseInfo(pause))
```
It can only be called on a live Python object reference — never over the wire. The production
`galago-tools` systemd unit runs `python -m tools.fast.server --port=40001` as a separate OS
process with no interactive hook; there is no way to call this method on it from outside that
process. See Pitfall 2 and Open Question 1 for the consequence.

**When to use:** Any time the dry run (D-07) needs to make the simulated F.A.S.T. "look paused" to
exercise the `tool_paused` modal and controls without hardware.

### Anti-Patterns to Avoid
- **Calling `simulate_pause` via gRPC or expecting it on the deployed `:40001` instance:** it does
  not exist on that surface; this will fail immediately and is not a configuration bug.
- **Editing `tools/base_server.py` to add a temporary trigger for the dry run:** explicitly out of
  scope (phase boundary) and would itself need the full gate + review cycle mid-deploy-phase.
- **Reusing `StopRunModal` for the D4 Stop-during-a-controllable-step confirmation:** galago-core's
  design research already flagged this (its 5s countdown auto-confirms on inaction, which would
  abort a real instrument run) — confirm the deployed `galago-web` build uses the new
  `InstrumentStopModal` (file present: `[VERIFIED: ls controller/components/runs/, this session]`
  shows `InstrumentStopModal.tsx` already exists alongside `RunControlConfirmModal.tsx`), not the
  old one, during acceptance.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Verifying the installed core's capabilities after re-pinning | A new ad-hoc Python snippet | Re-run `TestRequirementsPin`'s two methods (`fast_test.py:3422`, `:3447`) against `.venv/bin/python` | Already written, already reviewed, already the LIVE-01 gate; D-05 explicitly says to reuse it |
| Checking if the deploy order held safely | A custom "is the old UI talking to a new core" probe | The additive-proto-compatibility argument already made in D-05 step 2 ("old `galago-web` against new adapter is safe... proto change is additive and the old UI never sends `Pause`") | The safety argument is already verified by the proto being additive (`optional ... run_state = 4`) — no new tooling needed, just confirm the field number is unchanged |
| Observing acceptance-scenario outcomes | A log-scraping script that parses `journalctl` for pass/fail | Direct human observation of the run page + `journalctl --user -u galago-tools` tail, per D-08 | D-08 requires Claude to watch and record, not automate judgment about a live hardware run — automating this would also violate "Claude never sends a motion or control command itself" by creating an unreviewed inference step |

**Key insight:** Nearly everything this phase needs already exists from Phase 1/2 (test helpers,
exact message strings, UI components). The only genuinely unbuilt piece is the dry-run harness for
`simulate_pause` (Pattern 2) — treat that as the one real engineering task in an otherwise
operational phase.

## Common Pitfalls

### Pitfall 1: The entry gate (D-01 condition 1) is not met as of this research
**What goes wrong:** Planning or executing live scenarios before galago-core's Phase 2 is actually
verified complete.
**Why it happens:** `[VERIFIED: this session]` `galago-core/.planning/phases/02-run-page-live-controls/02-UAT.md`
shows `status: testing`, all 8 conversational-UAT tests `pending` (0 passed); its
`02-VERIFICATION.md` shows `status: human_needed`, `score: 12/16`. Notably, UAT test 5 in that file
is *literally* the deck-3 scenario this phase also needs to run, and `02-VALIDATION.md` states
outright: `"No jsdom/RTL (D-24); rendering not covered by node tests | Run galago-web against a
simulated F.A.S.T. and observe the run page during a transfer"` is one of several rows explicitly
pushed to manual verification, and the phase's own text says the deck-3 live check is "to be
finished in galago-tools' supervised live acceptance" (this phase).
**How to avoid:** The planner's first task (per D-01) must be a `checkpoint:human-verify`-style gate
that re-checks all four D-01 conditions at execution time (not planning time, since they can change
daily) and stops cleanly if any still fail. Given galago-core's UAT test 5 overlaps functionally
with this phase's LIVE-05 scenario, flag to the user that passing LIVE-05 here may also retroactively
satisfy that pending galago-core UAT item — worth a cross-repo note, not a blocker.
**Warning signs:** `galago-core/.planning/STATE.md` `status` field not `shipped`/`complete`;
`02-UAT.md` `summary.pending > 0`.

### Pitfall 2: `simulate_pause` has no reachable surface on the deployed service
**What goes wrong:** Assuming D-07's dry run can be performed against the production `:40001`
`galago-tools` instance just by toggling "Simulated" in the Tool Box.
**Why it happens:** Toggling simulated mode (the `Config.simulated` field) is easy and already
supported `[VERIFIED: tools/base_server.py:89-119]`, which makes it easy to miss that
`simulate_pause` (the thing that actually drives the `tool_paused` modal without hardware) is a
Python-only method with explicitly "no new gRPC command" `[VERIFIED: tools/fast/server.py:618]` —
there is no way to invoke it on a process you don't control interactively. No existing dev script,
test runner, or doc in either repo demonstrates calling it outside `fast_test.py`
`[VERIFIED: repo-wide grep, this session — only hit is the test file and docstrings]`.
**How to avoid:** Plan a small, explicit task to build a throwaway harness script (not committed to
either repo's gated source, or committed under a clearly-labeled `scripts/dryrun/` path if kept)
that: (1) imports `FastServer`, sets `simulated=True` directly in-process, (2) serves it on a spare
port via `tools.base_server.serve`, started in a background thread, (3) reads lines from stdin (or a
watched file) to call `.simulate_pause({...})` / `.simulate_pause(None)` on the live object, and
(4) is torn down after the dry run. Point galago-core's Tool Box at that spare port only for the
duration of the dry run; never touch the production tool's `:40001` registration.
**Warning signs:** Any plan step that says "call `simulate_pause` on the running galago-tools
service" without first standing up a second instance.

### Pitfall 3: Entry-gate-check scripts drifting from the actual gate
**What goes wrong:** The D-05 step 1 check (capability/state-gate test against `.venv`) silently
diverges from `TestRequirementsPin` over time if hand-copied instead of imported/invoked.
**Why it happens:** Copy-paste drift between `tools/tests/fast_test.py` (gated, reviewed) and a
one-off deploy script (ungated).
**How to avoid:** Invoke the existing test methods directly (e.g.
`python -m unittest tools.tests.fast_test.TestRequirementsPin -v` run with `.venv/bin/python` on
`PYTHONPATH`, or a tiny wrapper that imports and calls them) rather than re-typing their assertions.
**Warning signs:** A deploy script with its own copy of the `through_pauses`/`PauseInfo` assertions.

### Pitfall 4: GitLab push requires interactive OAuth, not a plain `git push`
**What goes wrong:** Assuming `fix/run-recovery-gate` can be pushed non-interactively as part of
"the deploy."
**Why it happens:** `[VERIFIED: this session]` running `git ls-remote --heads origin` against the
local fast-mcp clone triggered a browser-based OAuth device flow
(`https://gitlab.formulatrix.com/oauth/authorize?...`) rather than returning data — this GitLab
instance is configured for interactive/browser auth, not a stored credential or deploy token in
this environment. The command timed out waiting for a browser action nobody took.
**How to avoid:** This is already out of scope (Deferred: "the user's action, not needed for the
forb01 deploy" — D-02 explicitly routes around it via `git+file://`). Do not attempt `git push` to
GitLab as part of any automated step in this phase; it cannot complete non-interactively in this
environment. Confirm D-02's `file://` install path continues to be used.
**Warning signs:** A plan step scripted as `git push origin fix/run-recovery-gate` run by Claude.

### Pitfall 5: `galago-web` restart recovery depends on the tool page, not the run page
**What goes wrong:** Looking for a Resume/Abort control on the run page after `docker restart
galago-web` (LIVE-07) and concluding the deploy is broken.
**Why it happens:** This is by design (design §8, confirmed unchanged in the deployed `galago-core`
checkout): a restart clears the queue's in-memory view of the running step, so the run page
correctly shows **no control bar**. Recovery is only ever possible from the tool page's Run Recovery
card, because that path doesn't depend on the queue's step state.
**How to avoid:** The acceptance checklist for LIVE-07 (D-12) must explicitly tell the operator to
go to the **tool page**, not wait for the run page to recover a control bar that will never reappear
for that step.
**Warning signs:** Treating "no control bar after restart" as a failure rather than the documented,
correct behavior.

## Code Examples

### Verified current deploy state (reproduce before deploying, per D-04)
```bash
# Source: direct_url.json inside the service .venv, read this session
# {"url":"file:///home/formulatrix/data/nikko/fast/fast-mcp",
#  "vcs_info":{"vcs":"git","commit_id":"76f8c3fee41b0a2df3519aa74b022152df673824",
#              "requested_revision":"76f8c3fee41b0a2df3519aa74b022152df673824"}}

# Source: systemctl --user status galago-tools, read this session
# Active: active (running) since Mon 2026-10-12 13:15:55 WIB
# Main PID 944069 runs .venv/bin/galago --http-port 8081 --host 0.0.0.0 --toolbox-port 11010
# Child 944148 runs .venv/bin/python3 -m tools.fast.server --port=40001

# Source: docker ps, read this session
# galago-web container cfa4e187b018, image galago-core-galago-web, "Up 2 days",
# ports 0.0.0.0:3010->3010/tcp
```

### Re-pin command (D-02, verified against the live local clone)
```bash
# Source: .planning/phases/03-deploy-supervised-live-acceptance/03-CONTEXT.md D-02;
# verified this session that b30b38d is reachable from the local clone's current HEAD:
#   git merge-base --is-ancestor b30b38df48e8480f325228145ccae7915a56e437 HEAD   # => true
~/.local/bin/uv pip install --python .venv/bin/python \
  "git+file:///home/formulatrix/data/nikko/fast/fast-mcp@b30b38df48e8480f325228145ccae7915a56e437"
```

### galago-web rebuild command (D-05 step 3, verified against docker-compose.yml)
```bash
# Source: galago-core/docker-compose.yml, read this session — TOOLBOX_PORT defaults to 1010 if
# unset, so it MUST be passed explicitly to match the Tool Box's actual port (11010):
cd /home/formulatrix/data/nikko/galago-core
TOOLBOX_PORT=11010 docker compose up -d --build
```
`[VERIFIED: galago-core/docker-compose.yml:14]` — `TOOLBOX_PORT=${TOOLBOX_PORT:-1010}` — confirms
the env var is required, not optional, given the Tool Box actually runs on 11010.

### Exact abort/success wording to check for during LIVE-06b (D-11)
```python
# Source: tools/fast/server.py:350, read this session (verbatim)
text = f"run aborted by operator at {result.percent}%"
```

### `simulate_pause` signature for the dry-run harness (Pitfall 2)
```python
# Source: tools/fast/server.py:610-625, read this session (verbatim)
def simulate_pause(self, pause: Optional[dict[str, Any]]) -> None:
    """In-process test hook (D-20, ADP-10), simulated mode only. ...
    `pause=None` clears a hooked pause, as a successful Resume/Abort would; a dict is wrapped as
    _DictPauseInfo and fed to the same _record_pause that Transfer and RunProtocol wire as
    RunOptions(on_pause=self._record_pause)."""
    if not self.simulated:
        raise RuntimeError("simulate_pause is only available in simulated mode")
    if pause is None:
        self._clear_pause()
    else:
        self._record_pause(_DictPauseInfo(pause))
```

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | A throwaway stdin-driven harness script is the right shape for driving `simulate_pause` during the dry run (no existing prior art confirms this exact approach) | Pattern 2 / Pitfall 2 | Low — it's a disposable dev-only script; if the approach doesn't work, the dry run can fall back to code review only, with the risk simply shifting more validation weight onto the live-instrument scenarios |
| A2 | galago-core's UAT test 5 (deck-3/pause-prompt) being satisfied by this phase's LIVE-05 scenario is a reasonable cross-repo inference, not something either repo's planning doc states explicitly as linked | Pitfall 1 | Low — worst case the user has to separately re-run galago-core's UAT test 5; no safety or correctness impact |
| A3 | ufw rules for ports 40001/11010/3010 are already correctly configured (not re-verified this session; `sudo ufw status` requires a password not available non-interactively) | Standard Stack / Environment Availability | Low-Medium — if a rule were missing, `galago-web`'s existing 2-day uptime and successful operation already demonstrates connectivity works today; a NEW port would need a new rule, but none is introduced this phase |

**If this table is empty:** N/A — three low-risk assumptions above.

## Open Questions

1. **How exactly should the `simulate_pause` dry-run harness be invoked and torn down?**
   - What we know: the method exists, has no gRPC surface, and no prior script in either repo
     exercises it outside `unittest`.
   - What's unclear: whether a stdin loop, a tiny temporary gRPC/HTTP trigger added only to the
     harness script (never to `tools/base_server.py` or `tools/fast/server.py`), or simply running
     specific `fast_test.py` test methods interactively (e.g. via `python -i`) is the cleanest fit.
   - Recommendation: make this its own planning task with a short design note before building it,
     since it's the one piece of real engineering in the phase; confirm with the user whether a
     disposable script under `.planning/phases/03.../scratch/` (untracked) is acceptable, or whether
     they'd rather skip the modal-rendering dry run and rely on galago-core's existing unit-level
     coverage (`pausePrompt.test.ts` etc., already passing) plus the live instrument scenarios.

2. **Does galago-core's Phase 2 UAT need to complete before Phase 3 planning, or only before Phase 3 execution?**
   - What we know: D-01 frames this as an execution-time checkpoint ("the first plan task checks
     them and stops... if any fails"), and CONTEXT.md was written when galago-core was at "plan 5 of
     6"; it has since reached "plan 6 of 6" but UAT is still pending (not yet "complete and verified").
   - What's unclear: whether the user wants the plan written now (with the gate as its first task,
     expected to stop) or wants to wait for galago-core's UAT before even planning this phase.
   - Recommendation: plan now per D-01's own instruction ("the first plan task checks them and
     stops") — this matches the explicit design intent and avoids blocking planning on another
     team/repo's pace.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `uv` | D-02 core install | ✓ `[VERIFIED]` | 0.11.2 | — |
| `systemctl --user` | `galago-tools` restart (D-05 step 2) | ✓ `[VERIFIED]`, no sudo needed (user unit) | — | — |
| `docker` / `docker compose` | `galago-web` rebuild (D-05 step 3) | ✓ `[VERIFIED]`, user in `docker` group, no sudo needed | Compose v2.29.1 | — |
| `journalctl --user -u galago-tools` | Observation during acceptance (D-08) | ✓ `[VERIFIED]`, readable without sudo | — | — |
| Python 3.10.12 gate venv | `bin/make proto test` pre-deploy gate check | ✓ `[VERIFIED]` at `$HOME/data/nikko/.venvs/galago-py310` | 3.10.12 | — |
| `sudo` (passwordless) | Not required for any planned step | ✗ `[VERIFIED]` — `sudo -n` prompts for a password | Not needed: all planned commands (systemd user unit, docker as group member, uv in user venv) run without sudo; if a plan step is later found to need sudo (e.g. a missing ufw rule), it needs the operator, not Claude |
| GitLab push access (non-interactive) | Not required this phase (D-02 avoids it) | ✗ `[VERIFIED]` — triggers an OAuth browser flow, no stored token | D-02's `git+file://` install path; GitLab push remains the user's deferred action |
| Network path to F.A.S.T. (`10.150.1.170:5003`) | Live scenarios | Not independently re-probed this session (would require contacting the live instrument — deferred to the supervised session itself per the no-motion research constraint) | — | — |

**Missing dependencies with no fallback:** none — every planned automated step runs without sudo or
GitLab network access.

**Missing dependencies with fallback:** `sudo` and GitLab push are both unavailable non-interactively
but neither is needed given D-02's and the existing systemd/Docker user-level setup.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `unittest` + `pytest` (Python 3.10, via `bin/make proto test`: ruff, mypy, `python -m unittest discover`, `pytest -vv`) `[VERIFIED: bin/make, read this session]` |
| Config file | `pyproject.toml` (mypy config); no pytest.ini — discovery via `tools/tests/*_test.py` |
| Quick run command | `$HOME/data/nikko/.venvs/galago-py310/bin/python -m unittest tools.tests.fast_test.TestRequirementsPin -v` (re-run D-05 step 1's two capability/gate methods against the freshly-installed `.venv` interpreter, per Claude's Discretion note) |
| Full suite command | `bin/make proto test` (143 tests at Phase 2 close) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LIVE-04 | Core installed at pinned SHA, gated, service healthy | automated (pre/post-step checks) | `python -m unittest tools.tests.fast_test.TestRequirementsPin -v` against `.venv/bin/python`; `systemctl --user is-active galago-tools`; `docker ps --filter name=galago-web` | ✅ (`TestRequirementsPin` exists; systemctl/docker are host commands) |
| LIVE-05 | Deck-3 pause prompt + same-step SUCCESS after fix+Resume | manual-only (live instrument) | — (operator-driven; Claude observes `journalctl` and run page) | ❌ — inherently manual; no automated harness can safely move the instrument |
| LIVE-06 | Pause→Resume→SUCCESS; Pause→Abort→FAILED w/ exact wording | manual-only (live instrument), with an automated string check as a static pre-check | Live: operator-driven. Static pre-check: `grep -n "run aborted by operator at" tools/fast/server.py` to confirm the wording hasn't drifted before the live run | ✅ for the static pre-check; live portion is manual by design |
| LIVE-07 | `galago-web` restart recovery via tool page | manual-only (live instrument + container restart) | `docker restart galago-web` is automatable, but the recovery click must be the operator's (per D-08) | — |

### Sampling Rate
- **Per deploy step:** the D-05 check immediately following that step (capability test / service
  status / container status) — never advance without it passing.
- **Per acceptance scenario:** the D-11 pass criteria, recorded live into `03-ACCEPTANCE.md`.
- **Phase gate:** `bin/make proto test` green (no production code is expected to change; if a gap
  fix is needed per D-14, this full suite re-runs before any redeploy).

### Wave 0 Gaps
None — the Python gate test infrastructure (`fast_test.py`, `TestRequirementsPin`) already covers
every automatable check this phase needs. The genuinely new artifact needed is the dry-run harness
script from Open Question 1, which is explicitly an ops/QA tool, not a gated test file.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | No new auth surface; GitLab's existing OAuth flow is unchanged and out of scope |
| V3 Session Management | No | No session changes |
| V4 Access Control | Yes (operational) | Physical access control substitutes for software ACL here: only an operator physically present at the instrument, e-stop within reach, may trigger a motion-affecting command (design §7 invariant 1, enforced procedurally by D-08, not by new code) |
| V5 Input Validation | Already covered | `_check_args`/fail-closed `"yes"`/`"no"` decisions were built and gated in Phase 1 (ADP-06); this phase changes no input-handling code |
| V6 Cryptography | No | No new crypto surface |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| An unattended confirmation dialog silently acting after a timeout (software-initiated motion) | Elevation of Privilege (software acting as if it were the operator) | Already mitigated in galago-core: the new `InstrumentStopModal`/`RunControlConfirmModal` have no auto-confirm timer, unlike the old `StopRunModal` (verify the deployed build uses the new modal — Anti-Pattern above) |
| A stale/duplicate control command reaching the tool after the step already ended | Tampering / Repudiation | Core state gates (`Refused` when state doesn't allow the action) plus galago-core's "stale request" closing rule (D-02/D-12 in its own planning) — both already built, this phase only needs to confirm they hold under the real deploy |
| Deploying an ungated core before the UI update (window where new UI commands reach an old, ungated core) | Tampering (instrument acts without a state gate) | D-05's safe order: core → `galago-tools` restart → `galago-web` rebuild, with a check after each step, specifically engineered to prevent this window |
| Operator fatigue / rushing through "yes/no" physical decisions during a live scenario | n/a (human-factors, not STRIDE) | D-11's explicit "nothing is preselected" pass criteria, re-verified live, is the control; Claude's checklist should read the choice back before Resume/Abort is sent |

## Sources

### Primary (HIGH confidence — read directly this session)
- `tools/fast/server.py` (lines 350, 425-460, 610-650, 765-790, 985-999) — abort wording, `simulate_pause`, run_state builder, service entry point
- `tools/base_server.py` (lines 60-120, 296) — `Configure`/`setSimulated`, `serve()`
- `tools/tests/fast_test.py` (lines 3405-3470) — `TestRequirementsPin` gate test bodies
- `interfaces/tools/grpc_interfaces/tool_base.proto:135`, `fast.proto:16,57-72` — `run_state` field, `Pause` message
- `tools/fast/requirements.txt` — the pin line and its comment
- `bin/make` — gate command composition (`test()` function)
- `galago-core/docker-compose.yml`, `.dockerignore` — rebuild command correctness
- `galago-core/.planning/phases/02-run-page-live-controls/02-VERIFICATION.md`, `02-UAT.md`, `02-VALIDATION.md` — companion milestone's actual current status
- `galago-core/.planning/STATE.md`, `ROADMAP.md` — Phase 2 plan/verify status
- Live host commands this session: `systemctl --user status galago-tools`, `journalctl --user -u galago-tools`, `docker ps`, `docker compose version`, `uv --version`, `groups`, `git log`/`git branch`/`git rev-parse`/`git merge-base` in galago-tools, galago-core, and the local fast-mcp clone, `direct_url.json` contents, `git ls-remote` (OAuth prompt observed)

### Secondary (MEDIUM confidence)
- `docs/specs/2026-10-12-galago-live-run-control-design.md` — governing design, cited extensively for architecture/safety invariants (not independently re-verified against running code beyond what's cited above, but authoritative as the project's own approved spec)
- `~/.claude/.../memory/galago-local-setup.md` (project memory) — port/service history, used to corroborate live findings, not as a standalone source

### Tertiary (LOW confidence)
- None used as a basis for any claim in this document.

## Metadata

**Confidence breakdown:**
- Deploy procedure: HIGH — every command verified against the actual live host this session
- Entry-gate status: HIGH — read directly from galago-core's own verification/UAT artifacts this session
- Simulated dry-run mechanics: MEDIUM — the gap is real and verified (no gRPC surface, no prior art), but the recommended harness design (Pattern 2/Open Question 1) is a reasoned proposal, not something already built and tested
- Live acceptance pass criteria: HIGH — copied verbatim from CONTEXT.md (user-approved) and cross-checked against actual source strings

**Research date:** 2026-10-14
**Valid until:** This research is time-sensitive on two fronts that change daily — galago-core's
milestone status (re-check `02-UAT.md`/`02-VERIFICATION.md` immediately before executing the entry
gate, not just before planning) and the local fast-mcp clone's state (re-check `direct_url.json` and
`git merge-base` if the clone moves). Treat anything about "current state" as valid for **this
session only**; re-verify at execution time regardless of calendar age.
