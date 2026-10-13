# Phase 2: Wait Through Pauses on the Pinned Core - Research

**Researched:** 2026-10-13
**Domain:** Adapter re-pin to a fast-mcp core with wait-through-pauses, pause-episode state, and a
thread-safe recovery API; proving it with a real `FastService` over a stub transport.
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

D-01 through D-17, verbatim from `.planning/phases/02-wait-through-pauses-on-the-pinned-core/02-CONTEXT.md`:

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
- **D-12:** The core already excludes live-paused time from the deadline at poll granularity
  (`poll_run`, S6). The adapter adds **no** timer, clock or deadline logic of its own; its only job is
  passing `through_pauses=True` (D-04). Stale paused readings still count toward the timeout, so a
  masked re-pause ends as TimedOut rather than hanging (core S10).
- **D-13:** Prove it with the real core and an injected clock: build `FastService` with
  `clock=` / `sleep=` fakes, a short timeout, and a stub transport that stays paused for far longer
  than the timeout before running → idle+done. The `Transfer` ends SUCCESS. A control case with the
  same total time spent `running` ends TimedOut, with the transport's `abort` never called.
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
  **Research finding:** literally gating `get_status` on a `threading.Event` creates a real
  deadlock risk against `ResumeMarker` (see Pattern 3 / Pitfall 3 below) — the planner should gate
  the *pacing* through the injected `sleep` callback instead, with `get_status` staying a plain,
  non-blocking sequence. This is a refinement of D-15's mechanism, not a change to its observable
  behavior/assertions.
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

### Deferred Ideas (OUT OF SCOPE)

- Pushing fast-mcp `fix/run-recovery-gate` to GitLab: the user's action; required before Phase 3's
  clean install on forb01.
- Crash-recovery `Resume` under `_run_in_flight()` so `run_state` reports its wait from the adapter's
  record (with pause detail) instead of `service.status()`. Revisit if galago-core's tool page needs
  it.
- Splitting `EstimateResume` (carried from Phase 1).
- Hard pause (D5).

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| LIVE-01 | `tools/fast/requirements.txt` pins fast-mcp `b30b38d` or later; before go-live the installed core is checked to have the state-gated `pause`/`resume`/`abort` and `through_pauses` | Standard Stack (exact pin verification commands, `direct_url.json` shape), Package Legitimacy Audit (why N/A), Validation Architecture row LIVE-01 (behavioral gate tests already exist; only a new capability assertion is Wave 0), Pitfall 4 (`direct_url.json` shape for a `file://` install). |
| LIVE-02 | `Transfer`/`RunProtocol` keep their step open through instrument and operator pauses (`through_pauses` + `on_pause` feeding `run_state`), end SUCCESS on completion and "run aborted by operator at <p>%" on an operator abort | Pattern 1 (exact `RunOptions(...)` wiring diff), Pattern 3 (deadlock-safe end-to-end test design), Pattern 4 (cross-thread `_record_pause`/`_build_run_state` safety), Code Examples D-04/D-09/D-10, Pitfalls 1-3 and 6, Validation Architecture row LIVE-02. |
| LIVE-03 | Time spent paused doesn't count toward the run timeout | Pattern 2 (`FastService(clock=, sleep=)` injection), Code Example D-13 (test shape), Don't Hand-Roll (pause-time exclusion is core logic, never adapter logic), Open Question 2 (poll-count budget sizing), Validation Architecture row LIVE-03. |
</phase_requirements>

## Summary

The target core commit `b30b38df48e8480f325228145ccae7915a56e437` is three commits ahead of the
currently-pinned `76f8c3fee41b0a2df3519aa74b022152df673824`
`[VERIFIED: git -C ~/data/nikko/fast/fast-mcp log 76f8c3f..b30b38d]`. The three commits add exactly
the capability this phase wires up: `RunOptions.through_pauses`/`on_pause`, `PauseInfo`, a
`ResumeMarker` that classifies every status observation as live or stale-paused so a masked leading
`paused` after an accepted `resume()` no longer blocks the wait, and `FastService(clock=, sleep=)`
injection already wired through to `poll_run`'s deadline math. `HEAD` (`b4b67d8`) adds nothing past
`b30b38d`: it is exclusively `.planning/`/`docs/specs/` content with zero changes under `fast_mcp/`
`[VERIFIED: git -C ~/data/nikko/fast/fast-mcp log b30b38d..b4b67d8 --stat]`, confirming D-01's pin
choice.

The adapter-side change is small and almost entirely additive: `Transfer`/`RunProtocol` add
`through_pauses=True, on_pause=self._record_pause` to their existing `RunOptions(...)` call, and
`Abort`/`_message_for` grow one record-only flag plus a text branch. The one *necessarily breaking*
change is `test_resume_known_limitation_leading_paused_poll_reads_as_paused`
(`tools/tests/fast_test.py:2170`): under `b30b38d` this test's `MagicMock.side_effect` list of two
`{"currentState": "paused"}` readings will be **exhausted mid-poll** (not just differently
asserted) once the re-pin lands, because the second `paused` reading is now classified `stale` by
`ResumeMarker` and is no longer terminal — `poll_run` calls `get_status()` a third time that the
mock has no canned answer for, raising `StopIteration` from inside `FastService.wait`. This is a
concrete, verified regression signature the planner must have the fix-up plan rewrite, not just a
reworded assertion.

The core's own test suite (`tests/test_run_control_threads.py`) demonstrates the exact threading
pattern this phase's end-to-end tests need (deterministic "stepper" gating on `sleep`, never on
`get_status`), and it reveals a genuine deadlock risk in the pattern CONTEXT.md's D-15 describes
literally ("a transport whose `get_status` script is gated by `threading.Event`s"): `ResumeMarker`
holds its own lock *across* the `get_status()` call, so if the scripted `get_status` blocks on an
`Event` while holding that lock, a concurrent `Resume`/`Abort`/`status()` call from the test's main
thread — which must acquire the same lock before it can even check the state gate — deadlocks
immediately. The safe, core-proven alternative is to gate the poll loop's pacing through the
injected `sleep` callback (which runs *outside* the marker lock) and let `get_status` return
canned values from a plain, non-blocking sequence.

**Primary recommendation:** Re-pin to `b30b38d`, wire `through_pauses=True`/`on_pause=self._record_pause`
into `Transfer`/`RunProtocol`'s existing `RunOptions(...)`, add the operator-abort record-only flag
to `Abort`, rewrite (don't just re-assert) the leading-paused test to pin the fixed Paused→Ran
behavior, and build the end-to-end pause/abort/timeout tests on a `sleep`-gated stepper against a
plain `side_effect` list, never an `Event`-gated `get_status`.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| State-gated pause/resume/abort | Core (fast-mcp, `FastService`) | — | ADP-09: the adapter adds no instrument-state check of its own; every gate lives in the core, already true today and unchanged by this phase. |
| Wait-through-pauses polling, deadline math, stale-pause masking | Core (fast-mcp, `poll_run`/`ResumeMarker`) | — | All pause-episode detection, timeout exclusion and stale-reading classification is core logic; the adapter never touches a clock or a deadline (D-12). |
| Run state surfaced to galago-core | API/Backend (adapter, `FastServer._run_record`/`_build_run_state`) | — | The adapter's only job is recording what the core's callbacks report (`on_progress`, `on_pause`) under its own lock and serving it over `GetStatus`. |
| Operator-abort wording | API/Backend (adapter, `_message_for`) | — | The core cannot know who issued an abort; the adapter's own command bookkeeping (a flag set only by its own `Abort()` handler) is the only source for "by operator". |
| Pin/install verification | Build/Packaging (`requirements.txt` + gate test) | — | A credential-free SHA regex plus a `direct_url.json` commit check, already proven infrastructure (`TestRequirementsPin`). |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| fast-mcp | `b30b38df48e8480f325228145ccae7915a56e437` (pinned commit, private GitLab) | Instrument control core: `FastService`, `RunOptions`, `PauseInfo`, `ResumeMarker` | Already the project's sole core dependency; this phase only advances the pin `[VERIFIED: git -C ~/data/nikko/fast/fast-mcp rev-parse b30b38d]` |

No other new dependency is introduced by this phase — this is a same-package re-pin, not a new
install.

### Supporting
_No new supporting libraries this phase._

### Alternatives Considered
_None — the core package is fixed by prior project decisions (Phase 1); this phase only advances
its pinned commit per the roadmap._

**Installation (gate venv, local clone — D-02, not a clean install):**
```bash
PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH \
  pip install "git+file:///home/formulatrix/data/nikko/fast/fast-mcp@b30b38df48e8480f325228145ccae7915a56e437"
```
This is the exact command the gate venv needs; do **not** run it during research (per the
additional-context instruction) — the planner's tasks run it. `requirements.txt` itself keeps the
GitLab HTTPS URL (`git+https://gitlab.formulatrix.com/nikkopg/fast-mcp.git@<sha>`) unchanged in
form — only the SHA changes — because `TestRequirementsPin` only ever compares
`direct_url.json`'s `vcs_info.commit_id` against the pinned SHA, never the install URL
`[VERIFIED: tools/tests/fast_test.py:2616-2631]`. A clean install from that GitLab URL will 404
until `fix/run-recovery-gate` is pushed (Phase 3 prerequisite, not a task here).

**Version verification:**
```bash
cd ~/data/nikko/fast/fast-mcp && git rev-parse b30b38d
# -> b30b38df48e8480f325228145ccae7915a56e437  [VERIFIED]
git log 76f8c3f..b30b38d --stat -- fast_mcp/
# -> fast_mcp/orchestration.py | 161 ++++--   fast_mcp/results.py | 10 +-
#    fast_mcp/run_control.py  |  60 ++        fast_mcp/service.py | 90 ++--
#    fast_mcp/session.py      |  12 +-                                   [VERIFIED]
git log b30b38d..b4b67d8 --stat
# -> only .planning/* and docs/specs/* files touched, 0 files under fast_mcp/  [VERIFIED]
```
The currently-installed gate-venv pin is `76f8c3fee41b0a2df3519aa74b022152df673824`
`[VERIFIED: ~/data/nikko/.venvs/galago-py310/.../fast_mcp-0.1.0.dist-info/direct_url.json]`, matching
`tools/fast/requirements.txt`'s current line exactly.

## Package Legitimacy Audit

> Not applicable — this phase advances the pin of an already-approved, privately-hosted internal
> package (`fast-mcp`, Formulatrix's own GitLab `nikkopg/fast-mcp`). No new third-party package is
> introduced; there is no public registry entry to check, and the package-legitimacy gate (built for
> public npm/PyPI slopsquatting risk) does not apply to a private, internally-authored dependency
> whose previous SHA is already running in this gate venv.

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
 Operator (galago-core)                 galago-tools adapter (FastServer)                fast-mcp core (FastService)              Real/stub instrument
┌─────────────────────┐        ExecuteCommand       ┌──────────────────────┐    run_transfer/run_protocol    ┌──────────────────┐      get_status / pause /
│ Transfer / RunProtocol│ ───────────────────────────▶│ Transfer/RunProtocol │ ────────────────────────────────▶│ start_run + wait  │ ───────────────────────▶ resume / abort
└─────────────────────┘                              │  options=RunOptions(  │                                 │  (poll_run loop)  │
                                                       │    timeout_s=...,     │                                 └─────────┬─────────┘
                                                       │    on_progress=self._log_progress,                               │ on_progress(pct,state)
                                                       │    on_pause=self._record_pause,                                  │ on_pause(PauseInfo)   [fires once per
                                                       │    through_pauses=True)│◀──────────────────────────────────────────┘    pause episode, S4]
                                                       └──────────┬───────────┘
                                                                  │ writes under _run_state_lock
                                                                  ▼
                                                       ┌──────────────────────┐
 Operator (galago-core)      GetStatus (health RPC)    │ _run_record (state,  │
┌─────────────────────┐ ───────────────────────────▶  │  percent, pause dict)│
│ run_state poller     │ ◀─────────────────────────────│ _build_run_state()   │
└─────────────────────┘      run_state struct          └──────────────────────┘

 Operator (galago-core)      ExecuteCommand (control)
┌─────────────────────┐ ───────────────────────────▶  FastServer.ExecuteCommand override
│ Pause/Resume/Abort   │                                 │ bypasses isReady/setStatus,
└─────────────────────┘                                  │ calls service.pause/resume/abort
                                                          │ directly (never through _motion_lock)
                                                          ▼
                                            FastService.pause/resume/abort
                                            (state-gated: Refused if wrong state,
                                             no instrument call sent on Refused)
                                                          │ resume(): marks ResumeMarker pending
                                                          │ on an accepted reply, so the NEXT
                                                          │ paused reading on ANY thread/path
                                                          │ (including the Transfer's own wait
                                                          │  loop above) is read as stale, not
                                                          │ live -- never re-fires on_pause,
                                                          │ never ends the wait.
```

### Recommended Project Structure

No new files. All production changes stay in `tools/fast/server.py`; all new tests stay in
`tools/tests/fast_test.py`, following the existing single-file-per-fork-tool layout.

### Pattern 1: Wiring `through_pauses`/`on_pause` into the existing `RunOptions(...)` call

**What:** `Transfer` and `RunProtocol` each already build a `RunOptions(timeout_s=..., on_progress=self._log_progress)` (`server.py:677`, `:696-697`). This phase adds exactly two keyword arguments to each; nothing else in either method changes.
**When to use:** Any long-running command whose step must stay open through a live instrument pause.
**Example (current code to be extended, `server.py:673-680`):**
```python
# Source: tools/fast/server.py:673-680 [VERIFIED: read this session]
with self._run_in_flight():
    try:
        result = service.run_transfer(
            request, expected_tray_id=expected,
            options=RunOptions(timeout_s=self._timeout(None), on_progress=self._log_progress))
    except (InstrumentHTTPError, httpx.HTTPError) as exc:
        return _transport_error_reply(exc)
```
The target shape per D-04 adds `on_pause=self._record_pause, through_pauses=True` to that same
`RunOptions(...)` call (and the matching one in `RunProtocol`, `server.py:696-697`). `_record_pause`
already exists and is fully built (`server.py:546-559`); it needs no changes.

### Pattern 2: `FastService` clock/sleep injection for a deterministic timeout test

**What:** `FastService.__init__` accepts `sleep=time.sleep, clock=time.monotonic` as overridable keyword arguments `[VERIFIED: fast-mcp/fast_mcp/service.py (`b30b38d`) class FastService.__init__ signature: "def __init__(self, session: InstrumentSession, *, run_timeout_s: float = 1200.0, poll_interval_s: float = 2.0, sleep=time.sleep, clock=time.monotonic) -> None:"]`. `poll_run`'s deadline math (`deadline += now - pause_clock` on the iteration *after* a live-paused one) means a fake clock that advances in fixed steps on each call makes the pause-exclusion arithmetic fully deterministic without any wall-clock sleeping.
**When to use:** D-13's timeout test (paused far longer than the timeout still ends SUCCESS; a control case spending the same *running* time ends TimedOut).
**Example (the pattern fast-mcp's own tests use, not importable but directly portable — `tests/test_pause_control.py`, `b30b38d`):**
```python
# Source: fast-mcp tests/test_pause_control.py (b30b38d), portable pattern -- NOT importable
# from the installed package (tests/ is not packaged; see Pitfall 5 below).
def _no_sleep(_seconds):
    return None

def _fake_clock(step: float = 2.0):
    t = 0.0
    def _clock():
        nonlocal t
        t += step
        return t
    return _clock

service = FastService(InstrumentSession(transport, openapi_path),
                      sleep=_no_sleep, clock=_fake_clock(), run_timeout_s=6.0)
```
A deadline-exclusion test for Phase 2 wants the *opposite* bias from the core's own suite (which
proves timeouts fire); it wants a paused run to survive a timeout window many times its length, so
set `run_timeout_s` small (e.g. `6.0`) and script a `get_status` sequence with many more `paused`
readings than would fit in that budget if they counted, followed by `running`→`idle+done`. The
control case uses the same count of `running` readings instead of `paused` ones and must end
`TimedOut`.

### Pattern 3: Driving the end-to-end pause/abort test without a `ResumeMarker` deadlock

**What:** `FastService._read_status()` is the *only* `get_status` call site, and it goes through
`ResumeMarker.read()`, which **holds `ResumeMarker`'s own lock across the `get_status()` call**
`[VERIFIED: fast-mcp/fast_mcp/run_control.py (`b30b38d`) ResumeMarker.read: "with self._lock: status = get_status() ..."; fast_mcp/service.py `_read_status`: "status, _stale = self._resume_marker.read(self._session.transport.get_status); return status"]`.
Every state-gated call (`pause`, `resume`, `abort`, `status`) calls `_read_status()` before doing
anything else, so **every one of them needs that same lock**.
**When to use:** Any test that runs a `Transfer`/`RunProtocol` on a worker thread while the main
test thread concurrently drives `Resume`/`Abort`/`GetStatus` over gRPC.
**Why the literal CONTEXT.md D-15 phrasing is a trap:** if the scripted `get_status` (a
`MagicMock.side_effect` function) *blocks on a `threading.Event`* to pace the test, it does so
**while holding `ResumeMarker`'s lock** (the lock is acquired before `get_status()` is called and
released only after it returns). A concurrent `service.resume()`/`service.abort()`/`service.status()`
call from the main test thread calls `_read_status()` → `ResumeMarker.read()` → tries to acquire the
*same* lock, and blocks forever, because the only thing that would ever release the scripted
`get_status`'s `Event.wait()` is the main thread itself proceeding past the now-deadlocked call.
**The core's own test suite never does this.** `tests/test_run_control_threads.py`'s `_Stepper`
gates the *wait loop's `sleep()`* (called **after** `_read_status()` returns and the lock is
released, see `poll_run`'s loop: status read → callbacks → deadline check → `sleep(poll_interval)`),
never `get_status` itself:
```python
# Source: fast-mcp tests/test_run_control_threads.py (b30b38d) -- portable pattern, not importable
class _Stepper:
    """Drives a wait thread one poll at a time: the main thread acts only
    while the wait thread is blocked in `sleep`, so the order of
    status-sequence consumption is deterministic."""
    def __init__(self) -> None:
        self._sleeping = threading.Event()
        self._sem = threading.Semaphore(0)
    def sleep(self, _seconds) -> None:
        self._sleeping.set()
        if not self._sem.acquire(timeout=5):
            raise AssertionError("stepper sleep() timed out waiting for step()")
    def wait_sleeping(self) -> None:
        if not self._sleeping.wait(timeout=5):
            raise AssertionError("timed out waiting for the wait thread to sleep")
        self._sleeping.clear()
    def step(self) -> None:
        self._sem.release()
```
Build the galago-tools version of this stepper as a new test helper (`tools/tests/fast_test.py`;
Claude's Discretion per CONTEXT.md) and gate the real `FastService` with `sleep=stepper.sleep,
poll_interval_s=0.01`, while `self.transport.get_status.side_effect` stays a **plain, pre-built
list** (never a blocking function). Drive the worker-thread Transfer with
`self.stub.ExecuteCommand(...)` (as `_RealModeGrpcTestCase._start_blocked_transfer` already does),
and interleave `stepper.wait_sleeping()` / assertions / `stepper.step()` from the main test thread to
read health `GetStatus` and send `Resume`/`Abort` at exactly the right poll boundary — mirroring
`test_threads_galago_flow_pause_then_resume_gives_ran` and
`test_threads_abort_while_paused_gives_aborted_one_abort_call`
`[VERIFIED: fast-mcp tests/test_run_control_threads.py (b30b38d), lines defining those two tests]`.

### Pattern 4: `_build_run_state()` observes `_record_pause`'s write safely across threads

**What:** `on_pause` fires **synchronously on the wait/worker thread**, inside `poll_run`, *before*
the loop calls `sleep()` for that iteration `[VERIFIED: fast-mcp/fast_mcp/orchestration.py poll_run body (`b30b38d`): the `if live_paused and not in_episode and on_pause is not None: ... on_pause(...)` block runs before the `sleep(poll_interval)` call at the bottom of the loop]`. So once a stepper-paced test observes `stepper.wait_sleeping()` after a scripted `paused` reading, `_record_pause` has already written `self._run_record["pause"]` under `_run_state_lock` (`server.py:546-559`), and the main thread's `GetStatus` call (`_build_run_state`, also under `_run_state_lock`, `server.py:620-627`) is guaranteed to observe it — no additional synchronization needed.

### Anti-Patterns to Avoid
- **Event-gated `get_status`:** blocks inside `ResumeMarker`'s lock; any concurrent `pause`/`resume`/`abort`/`status` call deadlocks (Pattern 3).
- **Importing `fast_mcp`'s own `tests/` helpers** (`FakeTransport`, `ThreadSafeFakeTransport`, `_Stepper`): `tests/` is excluded from the package build (`pyproject.toml`'s `[tool.setuptools.packages.find] include = ["fast_mcp*"]`) and is not present in the installed `site-packages` tree `[VERIFIED: ls ~/data/nikko/.venvs/galago-py310/lib/python3.10/site-packages/ shows only fast_mcp/ and fast_mcp-0.1.0.dist-info/, no tests/; `python -c "import tests"` fails]`. Copy the pattern, don't import it.
- **Re-asserting the leading-paused test with new expectations but the same `side_effect` list:** it will raise `StopIteration`, not just fail an assertion — the list needs a third (and likely fourth) entry to carry the poll through to a terminal state (see Common Pitfalls below).
- **Letting the adapter infer "who aborted":** the core has no concept of operator vs. instrument-initiated abort; the only true source is the adapter's own record of whether *it* sent the `Abort` command (D-09). Never try to read this back from the instrument.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Pause-time exclusion from a run timeout | A wall-clock/accumulator in the adapter | `fast_mcp.orchestration.poll_run`'s built-in `pause_clock` deadline-shift logic (S6) | Already implemented, already tested at the core level (`test_marker_through_pauses_stale_pause_counts_toward_timeout`, `test_through_pauses_episode_fires_twice_when_separated_by_running`); D-12 explicitly forbids the adapter adding its own timer/clock/deadline logic. |
| Stale-vs-live pause classification after a resume | A "debounce" or "grace period" heuristic in the adapter | `fast_mcp.run_control.ResumeMarker`, wired in automatically by `FastService.resume()`/`wait()` | The core already solves the exact "stale leading paused" problem the Phase 1 docstring flagged as a known limitation (D-08); re-solving it in the adapter would duplicate and could desync from the core's own state. |
| Deterministic thread-paced polling tests | Manual `time.sleep()` calls with race-prone timing assumptions | The stepper-on-`sleep` pattern (Pattern 3) | `time.sleep()`-based synchronization is inherently flaky; gating the injected `sleep` callback with an `Event`+`Semaphore` pair gives exact, zero-flake step control, as fast-mcp's own test suite demonstrates. |

**Key insight:** every piece of "wait through a pause and still respect the timeout" logic this
phase's success criteria describe is *already built and already tested* in the core at `b30b38d`.
The entire adapter-side job is wiring two keyword arguments into an existing call plus one
record-only bookkeeping flag — resist any temptation to replicate pause-episode or
timeout-exclusion logic locally.

## Runtime State Inventory

> Not applicable — this is not a rename/refactor/migration phase. The phase changes code behavior
> (wiring new `RunOptions` fields, adding one record-only flag) and advances a pinned dependency
> SHA; it introduces no renamed identifiers, no datastore keys, no OS-registered state, and no
> secrets. Skipping this section per the stated trigger condition.

## Common Pitfalls

### Pitfall 1: The leading-paused test will raise `StopIteration`, not just assert wrong
**What goes wrong:** `test_resume_known_limitation_leading_paused_poll_reads_as_paused`
(`fast_test.py:2170-2179`) sets `self._statuses({"currentState": "paused"}, {"currentState": "paused"})`
— exactly two canned readings. Under `76f8c3f` both polls are each independently terminal-eligible
(no `ResumeMarker`), so the test only ever consumes the first of the two. Under `b30b38d`, `resume()`'s
own gate check (`_require_state({"paused"}, ...)` → `_read_status()`) consumes the *first* canned
reading, and `resume()` then marks the `ResumeMarker` pending on the accepted reply. The wait's own
first poll consumes the *second* canned reading — now classified `stale` because the marker is
pending — which is **not terminal**, so `poll_run` loops and calls `get_status()` a **third** time.
The mock's `side_effect` list has only two entries, so `MagicMock` raises `StopIteration` on the
third call, which propagates out of `FastService.wait` as an uncaught exception, not a clean
assertion failure.
**Why it happens:** `ResumeMarker` is new; this test was written to pin a documented core limitation
that `b30b38d` specifically fixes (D-08).
**How to avoid:** Per D-08, rewrite the test (don't patch assertions in place) to script enough
readings to reach a real terminal state after the masked stale pause, e.g.
`{"paused"} [gate], {"paused"} [stale, masked], {"running"}, {"idle", done-event}` and assert the
final reply is `SUCCESS` with `kind == "ran"`. Remove the "Known limitation" paragraph from
`Resume`'s docstring (`server.py:843-848`) per D-08.
**Warning signs:** `StopIteration` surfacing from inside `unittest`'s traceback for this specific
test immediately after the re-pin is installed — that is expected and is the trigger to do the
rewrite, not a sign something else broke.

### Pitfall 2: `TestRecoveryCommands`'s other tests are unaffected — don't over-rewrite
**What goes wrong:** It's tempting to assume every test in `TestRecoveryCommands` that scripts a
`paused`→... sequence around a `Resume` call needs rework for the re-pin.
**Why it doesn't happen elsewhere:** `test_resume_while_paused_waits_for_the_run_and_reports_ran`
(`fast_test.py:2127-2139`) and `test_resume_that_pauses_again_reports_the_actionable_paused_message`
(`fast_test.py:2155-2168`) both have the poll's *first post-gate* reading be `running`, not `paused`
— so the `ResumeMarker` is cleared on that very first post-resume observation
(`ResumeMarker.read`: any non-`paused` observation clears `_pending` immediately,
`[VERIFIED: fast-mcp/fast_mcp/run_control.py ResumeMarker.read (b30b38d)]`), and any later `paused`
reading in those sequences is a *new*, live episode, not a stale one. These tests' current behavior
is unchanged by the re-pin.
**How to avoid:** Only the test whose first post-resume reading is itself `paused`
(`test_resume_known_limitation_leading_paused_poll_reads_as_paused`) is affected. Verify this by
running the full `TestRecoveryCommands` suite once the gate venv is re-pinned, rather than
rewriting defensively.
**Warning signs:** If a test other than the leading-paused one fails after re-pin, re-check whether
its scripted sequence has a `paused` reading immediately following the resume's gate-check read —
that is the only shape the `ResumeMarker` changes.

### Pitfall 3: `on_pause`/`on_progress` ordering assumption must hold for D-06 to be safe
**What goes wrong:** If a future change reorders `poll_run`'s callback firing so `on_pause` runs
*before* `on_progress` on the same poll, `_log_progress`'s `state == "running"` clear
(`server.py:543-544`) could theoretically race a fresh `_record_pause` write from the *same* poll
and wipe a pause that was just recorded.
**Why it doesn't happen today:** `poll_run` fires `on_progress` first, unconditionally (subject to
its own dedup check), then checks `live_paused and not in_episode` for `on_pause`
`[VERIFIED: fast-mcp/fast_mcp/orchestration.py poll_run body (b30b38d), the `on_progress` call
precedes the `if live_paused and not in_episode and on_pause is not None:` block]`. A poll that is
itself a pause observation never also reports `state="running"` to `on_progress` in the same call,
so D-06's ordering guarantee holds by construction, not by adapter-side defense.
**How to avoid:** Do not add any ordering assumption or lock-juggling in `_log_progress`/`_record_pause`
beyond what Phase 1 already built; the invariant is enforced by the core, and a test
(`test_through_pauses_episode_fires_twice_when_separated_by_running`-equivalent on the adapter side,
if written) should assert it rather than the production code defending against it.
**Warning signs:** A recorded pause disappearing immediately after being set with no intervening
`Resume`/`Abort` — would indicate the core's ordering guarantee broke, not an adapter bug.

### Pitfall 4: `direct_url.json`'s `commit_id` key path for a file:// install
**What goes wrong:** Assuming a local `file://` clone install's `direct_url.json` looks different
from a GitLab HTTPS install's and might not populate `vcs_info.commit_id` the same way.
**Why it doesn't happen:** The currently-running gate venv (installed from
`file:///home/formulatrix/data/nikko/fast/fast-mcp` at `76f8c3f` per D-02's exact pattern) already
has `direct_url.json` = `{"url": "file:///...", "vcs_info": {"commit_id": "76f8c3f...", ...}}`
`[VERIFIED: cat ~/data/nikko/.venvs/galago-py310/.../fast_mcp-0.1.0.dist-info/direct_url.json]` —
the exact shape `TestRequirementsPin` already asserts against. Installing at `b30b38d` from the same
local clone will produce the identical shape with the new SHA.
**How to avoid:** No special-casing needed; the existing `TestRequirementsPin` assertion
(`direct_url["vcs_info"]["commit_id"] == pinned_sha`) works unchanged after the re-pin and the
re-install.
**Warning signs:** None expected; flag only if the actual post-install `direct_url.json` differs
from this shape.

### Pitfall 5: `fast_mcp`'s own test helpers are not importable from the installed package
**What goes wrong:** Trying `from tests.fakes import ThreadSafeFakeTransport` or
`from tests.test_run_control_threads import _Stepper` inside `galago-tools`' own test file.
**Why it happens:** `fast-mcp`'s `pyproject.toml` restricts the package build to `fast_mcp*`
(`[tool.setuptools.packages.find] include = ["fast_mcp*"]`), so `pip install` from either the
GitLab URL or the local clone never ships a `tests/` package into `site-packages`
`[VERIFIED: ls ~/data/nikko/.venvs/galago-py310/lib/python3.10/site-packages/ -- no tests/ directory
present; `import tests` fails in that venv]`.
**How to avoid:** Copy the *pattern* (stepper-on-sleep, `_fake_clock`, `_no_sleep`) into
`tools/tests/fast_test.py` as a local helper — this is explicitly "Claude's Discretion" per
CONTEXT.md ("Exact stub-transport scripting helpers for the Event-gated status sequences").
**Warning signs:** `ModuleNotFoundError: No module named 'tests'` at test-collection time.

### Pitfall 6 (from CONTEXT.md D-13/D-17 interaction): `TestAdapterInvariant` AST checks need no new rule unless a new method is extracted
**What goes wrong:** Assuming the operator-abort flag (D-09) automatically needs a new AST
invariant rule the way `_record_pause`/`_log_progress`/`simulate_pause`/`_clear_pause` do
(`fast_test.py:2300`, `_STATUS_READERS`/`_CONTROL_PATH_FUNCTIONS` sets).
**Why it might not:** If the flag is set inline inside `Abort()` itself
(`self._run_record["operator_abort"] = True` under `_run_state_lock`, right where `Abort()` already
calls `service.abort(...)`), no new function is introduced and the existing `_adapter_invariant_violations`
checker (which scopes `.pause`/`.resume`/`.abort`/`.wait` calls to specific named functions) needs no
change — `Abort` is already an allowed caller of `.abort`.
**How to avoid:** Only add a new AST rule (per D-17) if the planner's chosen implementation extracts
a separate method (e.g. `_mark_operator_abort()`) that must itself stay record-only and never call a
control method — mirror the existing `_record_pause`/`_clear_pause` pattern
(`fast_test.py:2588-2613`) in that case.
**Warning signs:** A planted-violation test added for a flag-setting function that never actually
calls a control/motion method would trivially pass with zero coverage value — don't add the rule
unless the function genuinely needs the record-only guarantee enforced.

## Code Examples

### D-04: the target `Transfer`/`RunProtocol` wiring (production code, after this phase)
```python
# Target shape for server.py:673-680 (Transfer) -- D-04
with self._run_in_flight():
    try:
        result = service.run_transfer(
            request, expected_tray_id=expected,
            options=RunOptions(
                timeout_s=self._timeout(None),
                on_progress=self._log_progress,
                on_pause=self._record_pause,
                through_pauses=True))
    except (InstrumentHTTPError, httpx.HTTPError) as exc:
        return _transport_error_reply(exc)
# RunProtocol (server.py:692-699) gets the identical two added kwargs.
```
`through_pauses=True` must be the literal Python `True` — `RunOptions.wait()`/`run_protocol`/`run_transfer`
raise `TypeError` if it is not a plain `bool`
`[VERIFIED: fast-mcp/fast_mcp/service.py wait() (b30b38d): "if not isinstance(through_pauses, bool): raise TypeError(...)"]`,
so D-04's "the core rejects a non-bool" claim is directly confirmed.

### D-09/D-10: target Abort / `_message_for` change (production code, after this phase)
```python
# Abort(), after an accepted abort (errorCode 0) -- record-only, under _run_state_lock,
# mirroring _record_pause's own locking style (server.py:546-559):
with self._run_state_lock:
    self._run_record["operator_abort"] = True   # name at planner's discretion, D-09

# _run_in_flight()'s 0->1 transition (server.py:524-527) already resets the whole
# _run_record dict, which clears this flag for free between runs -- no new reset logic
# needed, but the planner should add an explicit assertion in a test that a *new* run's
# record starts with operator_abort unset/False.

# _message_for's Aborted branch (today, server.py:334-335):
#   text = f"run aborted at {result.percent}%: {_outcome_text(result.outcome)}"
# becomes, per D-09/D-10 (flag passed in, or read once by the reply builder):
elif isinstance(result, Aborted):
    outcome_text = _outcome_text(result.outcome)
    if operator_abort_flag:
        text = f"run aborted by operator at {result.percent}%"
        if outcome_text != "no error reported":
            text += f": {outcome_text}"
    else:
        text = f"run aborted at {result.percent}%: {outcome_text}"
```
`result.percent` for `Aborted` reads `self.outcome.percent`
`[VERIFIED: fast-mcp/fast_mcp/results.py (b30b38d), Aborted dataclass: "@property\n    def percent(self) -> int:\n        return self.outcome.percent"]`,
and `_outcome_text`'s "no error reported" fallback is the existing function at `server.py:285-304`
(unchanged) — confirming D-09's "appended only when `_outcome_text` has a real error" is a literal
string-equality check against that exact fallback value.

### D-13: timeout-exclusion test shape (new test, proposed)
```python
# Paused-longer-than-timeout case: ends SUCCESS, transport.abort never called.
stub_statuses = (
    [{"currentState": "running"}]
    + [{"currentState": "paused", "percentProgress": 10,
       "lastEvent": {"messageType": 1, "payload": {"errorCode": -301}}}] * 20  # far more
                                                                                # iterations than
                                                                                # run_timeout_s/step
                                                                                # would allow if
                                                                                # they counted
    + [{"currentState": "running", "percentProgress": 50},
       {"currentState": "idle", "percentProgress": 100,
        "lastEvent": {"messageType": 5, "payload": {"errorCode": 0}}}])
# FastService(sleep=no-op, clock=_fake_clock(step=1.0), run_timeout_s=6.0) -- 20 paused
# iterations alone would blow a 6-step budget if each counted; the pause-exclusion logic
# (poll_run's `pause_clock` shift) must keep the deadline from advancing during them.
#
# Control case: same transport.abort assertion, but replace the 20 paused readings with
# 20 "running" readings at the same step size -- this MUST end TimedOut, proving the test
# actually distinguishes pause-exclusion from "a long timeout budget happens to cover it".
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|---------------|--------|
| A live `paused` reading always ends `wait()` (`through_pauses` did not exist) | `RunOptions(through_pauses=True)` lets a pause episode fire `on_pause` and continue polling | `c908465` (`fast-mcp`, this phase's pin range) | Adapter must opt in explicitly per command; default mode is unchanged for callers that don't pass it. |
| A stale `paused` reading right after an accepted `resume()` was read as a fresh terminal pause (documented limitation) | `ResumeMarker` classifies it as stale; it is never terminal and never re-fires `on_pause`, but still counts toward the timeout (S10) | `8110efb` (`fast-mcp`, this phase's pin range) | `test_resume_known_limitation_leading_paused_poll_reads_as_paused` must be rewritten, not just re-asserted (Pitfall 1). |
| `FastService.pause/resume/abort` could, in principle, race `wait`'s own polling from another thread with no serialization | All `get_status` calls (including gate checks) route through `ResumeMarker.read()`, serializing observations across threads | `8110efb` | Enables the cross-thread end-to-end test design this phase needs (Pattern 3); also the source of the deadlock risk to avoid. |

**Deprecated/outdated:**
- The "Known limitation" paragraph in `Resume`'s docstring (`server.py:843-848`): describes exactly
  the behavior `b30b38d` fixes. Remove it per D-08.
- The `_PauseInfoLike` docstring's claim "the pinned core 76f8c3f has no `PauseInfo`"
  (`server.py:376-377`) and the matching `fast_test.py:112-114` comment: both are now false — the
  re-pinned core exports `PauseInfo` from `fast_mcp.orchestration`. Update per the "Specific Ideas"
  note in CONTEXT.md; `_PauseInfoLike`/`_DictPauseInfo` themselves stay (D-05: no import needed in
  production code, tests *may* now use the real `PauseInfo`, but don't have to).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The planner will name the operator-abort record flag `_run_record["operator_abort"]` as shown in the Code Examples — CONTEXT.md D-09 explicitly leaves the name to Claude's Discretion | Code Examples, D-09 | Low — purely cosmetic; any name works as long as it's reset by `_run_in_flight()`'s 0→1 transition and read once by the reply builder. |
| A2 | No new AST invariant rule is needed for the abort flag (Pitfall 6) — depends on the planner choosing to set it inline in `Abort()` rather than extracting a new method | Pitfall 6, Don't Hand-Roll | Medium — if a new method is extracted, skipping the AST rule leaves a blind spot in the record-only guarantee that D-17 asks for. |

**If this table is empty:** N/A — two low/medium-risk naming/structure assumptions are logged above;
every other claim in this document is `[VERIFIED]` against the actual `fast-mcp` source at
`b30b38d`/`76f8c3f` or the actual `galago-tools` source read this session.

## Open Questions (RESOLVED)

1. **Does `_message_for` take the abort flag as a parameter, or does the reply builder pre-format
   the text (D-10)?**
   - What we know: D-10 requires `_message_for` to stay a pure function of its inputs and never read
     adapter state itself; the flag must be read once by the caller (`Abort()` or `_result_reply`)
     and passed in.
   - What's unclear: the exact call-site shape — whether `_message_for` gains a new parameter
     (`operator_abort: bool = False`) or a dedicated `_aborted_message(result, operator_abort)`
     helper wraps it.
   - Recommendation: leave to the planner/Claude's Discretion per CONTEXT.md; either shape satisfies
     D-10's purity requirement. A parameter addition is the smaller diff against the existing
     `_message_for(result, expected_tray_id)` signature.
   - RESOLVED: `_message_for` gains an `operator_abort: bool = False` parameter (02-03, CONTEXT D-10).

2. **Exact poll-count budget for the D-13 timeout-exclusion test's "far longer than the timeout"
   requirement.**
   - What we know: the mechanism (pause_clock shift in `poll_run`) is deterministic and proven at the
     core level with as few as a handful of `PAUSED` readings exceeding a `run_timeout_s=6.0`/`step=2.0`
     budget (`test_marker_through_pauses_stale_pause_counts_toward_timeout` uses just 1 stale
     reading against a 6.0s budget with 2.0s clock steps).
   - What's unclear: how many *live* (non-stale) paused readings the planner should script to make
     "far longer than the timeout" unambiguous to a reviewer, versus keeping the test fast.
   - Recommendation: script at least 3-5x the number of iterations a 6.0s/2.0s-per-poll budget would
     allow (i.e., more than 3 iterations) while keeping `sleep` a no-op so wall-clock test time stays
     near zero regardless of the count chosen.
   - RESOLVED: 20 live paused polls against a 6.0 timeout with 1.0 clock steps, plus the one-step-either-side threshold cases (02-04, CONTEXT D-13).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| fast-mcp (pinned, local clone) | LIVE-01/02/03 (core behavior under test) | ✓ (clone present, not yet installed at `b30b38d` in the gate venv) | `76f8c3fee41b0a2df3519aa74b022152df673824` currently installed; `b30b38df48e8480f325228145ccae7915a56e437` is the target | — (install step is an explicit plan task, not run during research per instructions) |
| Gate venv `~/data/nikko/.venvs/galago-py310` | `bin/make proto test` (ruff, mypy, unittest, pytest) | ✓ | Python 3.10 `[VERIFIED: ~/data/nikko/.venvs/galago-py310/bin/python3.10 present]`; `ruff`/`mypy`/`pytest` binaries present in `bin/` | — |
| GitLab `nikkopg/fast-mcp` `fix/run-recovery-gate` branch | A clean install via `requirements.txt`'s HTTPS URL | ✗ (not pushed; only `origin/main` is known per STATE.md) | — | Install from local clone at the pinned SHA (D-02); push is an explicit, out-of-scope, user-owned prerequisite for Phase 3. |

**Missing dependencies with no fallback:**
- None — the one missing piece (the GitLab branch push) has an explicit, documented fallback (D-02)
  that this phase already plans around.

**Missing dependencies with fallback:**
- `fix/run-recovery-gate` not on GitLab → install from the local clone (`pip install "git+file:///home/formulatrix/data/nikko/fast/fast-mcp@<sha>"`), exactly as the gate venv is configured today.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `unittest` (via `python -m unittest discover`) + `pytest` (re-run over the same files), both invoked by `bin/make test` |
| Config file | `pyproject.toml` (mypy config); no separate pytest ini beyond defaults (fast-mcp's own `pyproject.toml` `[tool.pytest.ini_options]` governs only the fast-mcp repo, not this one) |
| Quick run command | `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH python -m pytest tools/tests/fast_test.py -k TestRecoveryCommands -vv` (targets the affected class only) |
| Full suite command | `PATH=$HOME/data/nikko/.venvs/galago-py310/bin:$PATH bash bin/make proto test` (ruff, mypy, unittest, pytest — the authoritative gate) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LIVE-01 | `requirements.txt` pins `b30b38d`; installed core has state-gated pause/resume/abort + `through_pauses`/`PauseInfo` | unit (capability + behavioral gate) | `pytest tools/tests/fast_test.py -k "TestRequirementsPin or TestRecoveryCommands" -vv` | ✅ `TestRequirementsPin` (`fast_test.py:2616`) exists; behavioral idle-refusal tests exist (`fast_test.py:2104,2181,2238`); a new capability assertion (RunOptions fields + PauseInfo import) is the only addition, ❌ Wave 0 for that one assertion. |
| LIVE-02 | Pause keeps the step open; SUCCESS on completion; "run aborted by operator at `<p>`%" on operator abort | integration (real `FastService` + stub transport, threaded end-to-end) | `pytest tools/tests/fast_test.py -k "TestRecoveryCommands or TestResultMapping" -vv` | ❌ Wave 0 — new end-to-end pause/resume test and new Abort-wording tests needed. |
| LIVE-03 | Paused time doesn't count toward the run timeout | unit (deterministic clock/sleep injection) | `pytest tools/tests/fast_test.py -k TestRecoveryCommands -vv` (new test class/method within or near `TestRecoveryCommands`) | ❌ Wave 0 — new timeout-exclusion test needed. |

### Sampling Rate
- **Per task commit:** `pytest tools/tests/fast_test.py -k <affected class> -vv` (seconds; no real sleeping anywhere in this suite since all services here use `sleep=` injection).
- **Per wave merge:** `bash bin/make proto test` (ruff + mypy + full unittest + full pytest).
- **Phase gate:** Full suite green before `/gsd-verify-work`, run against the gate venv re-pinned to `b30b38d`.

### Wave 0 Gaps
- [ ] A capability assertion for LIVE-01: `RunOptions` has `through_pauses`/`on_pause` fields (via `dataclasses.fields`) and `from fast_mcp.orchestration import PauseInfo` succeeds — add to `TestRequirementsPin` or a new small class (Claude's Discretion per CONTEXT.md).
- [ ] Rewrite of `test_resume_known_limitation_leading_paused_poll_reads_as_paused` per D-08 (Pitfall 1) — ends `SUCCESS`/`kind == "ran"`, not `Paused`.
- [ ] A local `_Stepper`-equivalent helper in `tools/tests/fast_test.py` (Pattern 3) — not importable from `fast_mcp`.
- [ ] A real-`FastService`-plus-gRPC end-to-end pause test (D-15): running → paused (with `lastEvent` payload) → health `GetStatus` shows `paused` with `PauseInfo`+`since` → `Resume` via `ExecuteCommand` → running → idle+done → `Transfer` ends SUCCESS, `run_state` no longer shows the pause.
- [ ] A matching abort test (D-16): same shape but `Abort(return_liquid="no")` → `aborted` → `ERROR_FROM_TOOL` "run aborted by operator at `<p>`%"; a second case with no `Abort` sent keeps the old wording; a timeout case asserts `transport.abort`/`pause`/`resume` are never called.
- [ ] A deterministic timeout-exclusion test (D-13): fake clock/sleep, paused far longer than `run_timeout_s`, ends SUCCESS; control case with equivalent *running* time ends TimedOut.
- [ ] Update `_PauseInfoLike`'s docstring (`server.py:376-377`) and `_StubPauseInfo`'s comment (`fast_test.py:112-114`) to drop the "pinned core 76f8c3f has no PauseInfo" claim (now false).
- [ ] Remove the "Known limitation" paragraph from `Resume`'s docstring (`server.py:843-848`).

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | No auth surface changes in this phase — gRPC transport/auth is unchanged, out of phase scope. |
| V3 Session Management | no | No session concept in this adapter. |
| V4 Access Control | no | No new access-control surface; the existing `ExecuteCommand` override (Phase 1) is unchanged by this phase. |
| V5 Input Validation | yes (unchanged, inherited from Phase 1) | `_check_args`/`_decision` already enforce `is_tip_broken`/`return_liquid` as exact `"yes"`/`"no"` strings (ADP-06); this phase adds no new user-facing input. |
| V6 Cryptography | no | No cryptographic material touched. |
| V7 Error Handling and Logging | yes | `_outcome_text`/`_message_for`/`_one_line(..., 500)` already bound and sanitize every operator-facing message; the new Aborted-wording branch must stay within the same 500-char `_one_line` cap and must not leak raw instrument payloads beyond what `PauseInfo.to_dict()`'s `_json_safe` sanitizer already bounds (depth/item/string caps, confirmed in `fast_mcp/orchestration.py`'s `_json_safe`, `b30b38d`). |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Unbounded/malicious `lastEvent.payload` from the instrument reaching an operator UI as `PauseInfo.eventPayload` | Information disclosure / resource exhaustion | Already mitigated by the core's `_json_safe` sanitizer (depth 6 / 50 items / 500-char strings, NaN/inf → None) before `PauseInfo.to_dict()` is ever serialized into `run_state` — no adapter-side change needed; just don't bypass `to_dict()`. |
| Adapter misattributing an instrument-initiated abort as operator-initiated (or vice versa) | Spoofing / repudiation (who commanded the abort) | D-09's record-only `operator_abort` flag, set *only* inside the adapter's own `Abort()` handler on an accepted reply — never inferred from instrument state — is itself the mitigation; a planted-violation AST test (Pitfall 6) should gate this if a new method is extracted. |
| A deadlocked gRPC worker thread (Pitfall 3's `ResumeMarker`-lock risk) exhausting the server's bounded `ThreadPoolExecutor(max_workers=4)` | Denial of service | Entirely a test-design risk, not a production code path — avoided by using the sleep-gated stepper pattern (Pattern 3), never an `Event`-gated `get_status`. |

## Sources

### Primary (HIGH confidence)
- `~/data/nikko/fast/fast-mcp` git history and source at `b30b38df48e8480f325228145ccae7915a56e437` and `76f8c3fee41b0a2df3519aa74b022152df673824` — `fast_mcp/run_control.py`, `fast_mcp/orchestration.py`, `fast_mcp/service.py`, `fast_mcp/results.py`, `tests/test_pause_control.py`, `tests/test_run_control_threads.py`, `tests/fakes.py`, `pyproject.toml` — all read directly this session via `git show <sha>:<path>`.
- `/home/formulatrix/data/nikko/galago-tools/tools/fast/server.py` (lines 260-934) — read directly this session.
- `/home/formulatrix/data/nikko/galago-tools/tools/tests/fast_test.py` (lines 1-130, 666-1505, 2060-2636) — read directly this session.
- `~/data/nikko/.venvs/galago-py310/lib/python3.10/site-packages/fast_mcp-0.1.0.dist-info/direct_url.json` and the installed `fast_mcp/` package tree — inspected directly this session.
- `/home/formulatrix/data/nikko/galago-tools/tools/fast/requirements.txt`, `.planning/config.json`, `interfaces/tools/grpc_interfaces/fast.proto` — read directly this session.

### Secondary (MEDIUM confidence)
_None — every claim in this document traces to a file read directly this session; no web search or
external documentation was consulted (none was needed or applicable for this private, internal
codebase)._

### Tertiary (LOW confidence)
_None._

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — the exact pinned commit, its diff against the current pin, and the
  subsequent docs-only commit were all read and diffed directly.
- Architecture: HIGH — every production code path this phase touches (`Transfer`, `RunProtocol`,
  `Abort`, `Resume`, `_message_for`, `_record_pause`, `_run_in_flight`, `_build_run_state`) was read
  in full this session, as was the exact core API it calls into (`RunOptions`, `PauseInfo`,
  `ResumeMarker`, `FastService.wait`/`resume`/`abort`).
- Pitfalls: HIGH — the `StopIteration` regression (Pitfall 1) and the `ResumeMarker`-lock deadlock
  risk (Pitfall 3) are both derived from reading the actual lock-acquisition order in
  `fast_mcp/run_control.py`/`service.py` and the actual mock `side_effect` list length in the
  existing test, not from inference.

**Research date:** 2026-10-13
**Valid until:** 30 days, or immediately if `fast-mcp`'s `fix/run-recovery-gate` branch advances
past `b30b38d`/`b4b67d8` before this phase is planned/executed (re-check `git log` on the local
clone before relying on this document).
