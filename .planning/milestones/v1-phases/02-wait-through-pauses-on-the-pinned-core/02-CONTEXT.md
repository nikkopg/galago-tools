# Phase 2: Wait Through Pauses on the Pinned Core - Context

**Gathered:** 2026-10-13
**Status:** Ready for planning
**Mode:** `--auto` (every gray area resolved with the recommended option; see 02-DISCUSSION-LOG.md)

<domain>
## Phase Boundary

The adapter moves onto the fast-mcp core that can wait through pauses, and the long-running
commands use it:

- `tools/fast/requirements.txt` pins fast-mcp `b30b38d` (LIVE-01), and the gate proves the installed
  core has the state-gated `pause`/`resume`/`abort` and `through_pauses`.
- `Transfer` and `RunProtocol` keep their step open through instrument and operator pauses
  (`through_pauses=True`, `on_pause` feeding `run_state`). They end SUCCESS on completion and
  "run aborted by operator at <p>%" on an operator abort (LIVE-02).
- Paused time doesn't count toward the run timeout (LIVE-03).

Everything is proven against the **real core over a stub transport**. No motion, no instrument.

**Not in this phase:**
- Deploying the new core to the service `.venv` on forb01, restarting `galago-tools`, rebuilding
  `galago-web`, and every live check (Phase 3).
- Pushing fast-mcp's `fix/run-recovery-gate` branch to GitLab (an outward-facing action on another
  repo; the user does it, see D-02).
- All galago-core work (its own `.planning/`).
- Editing `tools/base_server.py`.

</domain>

<decisions>
## Implementation Decisions

### Re-pin and install (LIVE-01)
- **D-01:** Pin exactly `b30b38d` (full 40-char SHA from the fast-mcp clone), the commit named in
  LIVE-01 and the roadmap. Later commits on `fix/run-recovery-gate` (`b4b67d8`) are planning docs
  only and add nothing the adapter needs. The URL stays
  `git+https://gitlab.formulatrix.com/nikkopg/fast-mcp.git@<sha>`, so `TestRequirementsPin`'s
  credential-free regex still holds. Update the pin comment to name the reason (wait-through-pauses
  core).
- **D-02:** `fix/run-recovery-gate` is not on GitLab (only `origin/main` is known). Install the gate
  venv (`~/data/nikko/.venvs/galago-py310`) from the local clone at the pinned SHA, exactly as today:
  `pip install "git+file:///home/formulatrix/data/nikko/fast/fast-mcp@<sha>"`. `direct_url.json`
  then records `commit_id == <sha>`, which is all `TestRequirementsPin` compares. The plan records
  the push as a **prerequisite for Phase 3's clean install**, not a task here. — **Reversibility:**
  reversible — re-installing a different SHA undoes it.
- **D-03:** The "installed core is checked" part of LIVE-01 becomes a **gate test**, not a manual
  step:
  - Capability: `RunOptions` has `through_pauses` and `on_pause` fields, and `PauseInfo` imports
    from `fast_mcp.orchestration`.
  - State gates, behaviourally: a real `FastService` over a stub transport reporting `idle` returns
    `Refused` from `pause(hard=False)`, `resume(is_tip_broken=False)` and
    `abort(return_liquid=False)`, and the transport's pause/resume/abort are never called.

  A core without the gates or the fields fails the gate, so a wrong install is caught before
  Phase 3's deploy. The adapter itself still adds no state check (ADP-09).

### Wait-through-pauses wiring (LIVE-02)
- **D-04:** `Transfer` and `RunProtocol` pass
  `RunOptions(timeout_s=..., on_progress=self._log_progress, on_pause=self._record_pause,
  through_pauses=True)`. `through_pauses` is the literal `True` (the core rejects a non-bool).
  Nothing else in either method changes: same motion lock, same `_run_in_flight()`, same transport
  error handling.
- **D-05:** `_record_pause` keeps Phase 1's duck-typed `_PauseInfoLike` signature (no import needed
  in production code; the real `PauseInfo` satisfies it). Tests may now use the real `PauseInfo`.
  The Phase 1 docstrings that say "Phase 2 wires it" are updated to describe the wiring as done.
- **D-06:** Pause clearing stays where Phase 1 put it: `_log_progress` clears the recorded pause on
  an observed `running`. The core fires `on_progress` before `on_pause` on the same poll, so a new
  pause is never cleared by its own poll. No new clearing path is added.
- **D-07:** The crash-recovery `Resume` (lock acquired, no run in flight) keeps the **default**
  (non-through) wait, per design §5.2: its Paused result and the actionable Paused message stay
  meaningful there. It does not pass `on_pause` either: with no run in flight, `run_state` comes
  from `service.status()`, so a recorded pause would never be read.
- **D-08:** The re-pinned core masks a stale leading `paused` after an accepted resume
  (`ResumeMarker`). `test_resume_known_limitation_leading_paused_poll_reads_as_paused` therefore
  flips: rewrite it to pin the fixed behaviour (paused, then running, then idle+done after a resume
  ends SUCCESS, not Paused) and remove the "Known limitation" paragraph from `Resume`'s docstring.

### Abort result (LIVE-02)
- **D-09:** The adapter cannot read from the instrument who aborted a run. It knows only that its
  own `Abort` command was accepted. So:
  - `Abort()`, on an accepted abort (`errorCode` 0), sets a record-only flag in the run record
    (`_run_record["operator_abort"] = True`, name at the planner's choice) under
    `_run_state_lock`. `_run_in_flight()`'s 0→1 reset clears it.
  - `Aborted` results map to `ERROR_FROM_TOOL` **"run aborted by operator at <p>%"** when the flag
    is set, with `: <instrument error>` appended only when `_outcome_text` has a real error (not
    "no error reported").
  - Without the flag (an abort the adapter didn't send), keep today's
    "run aborted at <p>%: <outcome text>", so an instrument-side abort is never blamed on the
    operator. This keeps the Core Value: the operator sees what the instrument did.

  The flag is adapter bookkeeping about its own commands, never an instrument-state check (ADP-09).
  `Abort` still calls only `.abort` on the service (ADP-07). — **Reversibility:** costly — galago-core
  shows this text verbatim and its run-page tests may assert it; changing the wording later touches
  both repos.
- **D-10:** `_message_for` gets the flag as an argument (or the reply builder reads it once). It
  stays a pure function of its inputs; it never reads adapter state itself.
- **D-11:** `TimedOut` and `Cancelled` messages and codes are unchanged, and neither ever causes a
  pause, resume or abort (Safety invariant 1).

### Paused time and the timeout (LIVE-03)
- **D-12:** The core already excludes live-paused time from the deadline at poll granularity
  (`poll_run`, S6). The adapter adds **no** timer, clock or deadline logic of its own; its only job is
  passing `through_pauses=True` (D-04). Stale paused readings still count toward the timeout, so a
  masked re-pause ends as TimedOut rather than hanging (core S10).
- **D-13:** Prove it with the real core and an injected clock: build `FastService` with
  `clock=` / `sleep=` fakes, a short timeout, and a stub transport that stays paused for far longer
  than the timeout before running → idle+done. The `Transfer` ends SUCCESS. A control case with the
  same total time spent `running` ends TimedOut, with the transport's `abort` never called.

### Tests (success criteria 2-4)
- **D-14:** "Real core (stub transport)" means a real `FastService` built on
  `InstrumentSession(MagicMock transport, openapi_path)`, the `TestRecoveryCommands` pattern
  (`fast_test.py:2073`), injected into `FastServer.service`. No mocked `FastService` for these
  tests.
- **D-15:** The end-to-end pause test (criterion 2) runs a `Transfer` on a worker thread against a
  transport whose `get_status` script is gated by `threading.Event`s:
  running → paused (with a `lastEvent` payload) → [test reads the health `GetStatus`: `run_state`
  is `paused` with the `PauseInfo` dict and `since`; the `Transfer` is still blocked] → the test
  sends `Resume` through `ExecuteCommand` (in-flight path, returns on acceptance) → running →
  idle+done → `Transfer` ends SUCCESS and `run_state` no longer shows the pause. Use gRPC
  (`_RealModeGrpcTestCase`) if it fits; otherwise call `ExecuteCommand` directly as the Phase 1
  real-mode test does.
- **D-16:** The abort test (criterion 3): same shape, but the test sends `Abort` (return_liquid
  "no") and the script turns `aborted`. The step ends `ERROR_FROM_TOOL` "run aborted by operator at
  <p>%". A second case where the script turns `aborted` with no `Abort` sent keeps the old
  wording (D-09). A timeout case asserts the transport's `abort`/`pause`/`resume` are never called.
- **D-17:** Every existing invariant still holds and the AST checks need no new rules: `.wait` stays
  out of `Transfer`/`RunProtocol` (they call `run_transfer`/`run_protocol`), `_record_pause` still
  records only. Add a planted-violation check only if the abort flag adds a new method that must stay
  record-only.

### Claude's Discretion
- The operator-abort flag's name and whether `_message_for` takes it as a parameter or the reply
  builder pre-formats it (D-09/D-10).
- Whether the LIVE-01 capability/gate test joins `TestRequirementsPin` or is its own class.
- Splitting into plans: a natural order is re-pin + capability test, then wiring + limitation-test
  flip, then abort wording, then the end-to-end/timeout tests. Each touches `server.py` or
  `fast_test.py`, so waves are likely sequential, as in Phase 1.
- Exact stub-transport scripting helpers for the Event-gated status sequences.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Governing design
- `docs/specs/2026-10-12-galago-live-run-control-design.md`:
  - §4: core prerequisites (pause episodes, stale leading `paused`, paused time excluded);
  - §5.2: long-running commands (through_pauses, on_pause, final result mapping, Paused message
    only for crash-recovery Resume);
  - §6.6: "aborted by operator" and the queue going FAILED (galago-core consumes the text);
  - §7: safety invariants (only operators command recovery);
  - §9: testing (`on_pause` sets run_state, resume clears it, `Aborted` maps to "aborted by
    operator").
- `.planning/REQUIREMENTS.md`: LIVE-01, LIVE-02, LIVE-03.
- `.planning/ROADMAP.md`: Phase 2 success criteria and the GitLab-push note.
- `.planning/phases/01-adapter-control-path-run-state/01-CONTEXT.md`: D-07 (Resume's two paths),
  D-11/D-12 (run_state shape and source), D-13 (duck-typed recorder), D-15/D-16 (invariants).

### Core API (fast-mcp at `b30b38d`, read-only reference)
- `~/data/nikko/fast/fast-mcp/fast_mcp/run_control.py`: `RunOptions` (`on_pause`, `through_pauses`),
  `ResumeMarker`.
- `~/data/nikko/fast/fast-mcp/fast_mcp/orchestration.py`: `PauseInfo` / `to_dict()`, `poll_run`
  docstring (pause episodes, S6 paused-time exclusion, S10 stale-paused bound).
- `~/data/nikko/fast/fast-mcp/fast_mcp/service.py`: `FastService.__init__(clock=, sleep=)`,
  `wait(..., on_pause, through_pauses)`, `run_transfer`/`run_protocol` forwarding `RunOptions`,
  the state gates on `pause`/`resume`/`abort`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_record_pause`, `_log_progress`, `_run_in_flight`, `_build_run_state` (`tools/fast/server.py:515-640`):
  already built in Phase 1 for exactly this wiring.
- `_message_for` / `_result_reply` / `_outcome_text` (`server.py:285-348`): the Aborted mapping to
  change.
- `TestRecoveryCommands` (`tools/tests/fast_test.py:2073`): real `FastService` over a `MagicMock`
  transport with `_statuses(...)`; the base for the real-core tests.
- `_RealModeGrpcTestCase` (`fast_test.py:666`) and the Phase 1 real-mode concurrency test: the
  threading/Event pattern for a blocked `Transfer` plus a control command through `ExecuteCommand`.
- `TestRequirementsPin` (`fast_test.py:2616`): SHA regex + `direct_url.json` commit check.

### Established Patterns
- Override, never edit `base_server.py`.
- Record-only callbacks under `_run_state_lock`, never `_motion_lock`.
- Physical decisions are `"yes"`/`"no"` strings.
- The gate venv installs fast-mcp from the local clone (`direct_url.json` today:
  `file:///home/formulatrix/data/nikko/fast/fast-mcp` at `76f8c3f`).

### Integration Points
- `tools/fast/requirements.txt` (the pin).
- `server.py` `Transfer`/`RunProtocol` `RunOptions(...)` calls (`:677`, `:696`), `Abort` (`:813`),
  `Resume` docstring (`:832`).
- Gate: `bin/make proto test` on `~/data/nikko/.venvs/galago-py310` (ruff, mypy, unittest, pytest).
- galago-core reads the abort text and `run_state` (companion milestone); no proto change here.

</code_context>

<specifics>
## Specific Ideas

- Re-install the gate venv at the new SHA **before** writing tests that import `PauseInfo` or set
  `through_pauses`, or the whole `fast_test.py` import block fails.
- The Phase 1 docstrings and test docstrings that mention "pinned core 76f8c3f has no PauseInfo"
  (`fast_test.py:113`, `server.py:378-395`) are updated with the re-pin.

</specifics>

<deferred>
## Deferred Ideas

- Pushing fast-mcp `fix/run-recovery-gate` to GitLab: the user's action; required before Phase 3's
  clean install on forb01.
- Crash-recovery `Resume` under `_run_in_flight()` so `run_state` reports its wait from the adapter's
  record (with pause detail) instead of `service.status()`. Revisit if galago-core's tool page needs
  it.
- Splitting `EstimateResume` (carried from Phase 1).
- Hard pause (D5).

</deferred>

---

*Phase: 02-wait-through-pauses-on-the-pinned-core*
*Context gathered: 2026-10-13*
