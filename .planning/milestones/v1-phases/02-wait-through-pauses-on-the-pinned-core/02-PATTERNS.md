# Phase 2: Wait Through Pauses on the Pinned Core - Pattern Map

**Mapped:** 2026-10-13
**Files analyzed:** 3 (no new files; all modifications to existing tracked files)
**Analogs found:** 3 / 3

No new files are created this phase (per RESEARCH.md "Recommended Project Structure": "No new files.
All production changes stay in `tools/fast/server.py`; all new tests stay in
`tools/tests/fast_test.py`"). `tools/fast/requirements.txt` gets a one-line SHA edit. This PATTERNS.md
therefore maps **modification sites within existing files** to their own closest in-file precedent,
since the best analog for "how to extend `Transfer`'s `RunOptions(...)`" is the adjacent, already-built
`RunProtocol` call, not an external file.

## File Classification

| Modified File | Role | Data Flow | Closest Analog (in-file or sibling) | Match Quality |
|---------------|------|-----------|--------------------------------------|---------------|
| `tools/fast/requirements.txt` (pin bump) | config | batch (pip resolve) | same file, same line, prior SHA | exact |
| `tools/fast/server.py::Transfer` / `::RunProtocol` (`RunOptions(...)` wiring) | controller (gRPC command handler) | request-response (long-running, polled) | each method is the other's analog; both already call `RunOptions(timeout_s=..., on_progress=self._log_progress)` | exact |
| `tools/fast/server.py::Abort` (operator-abort flag) | controller | request-response | `_run_in_flight`'s record-write-under-lock style (`server.py:524-526`, `546-559`) | exact (pattern donor), role-match (call site) |
| `tools/fast/server.py::_message_for` (Aborted branch rewording) | utility (pure mapper) | transform | its own existing `Paused`/`Refused` branches in the same function | exact |
| `tools/fast/server.py::Resume` (docstring only — remove "Known limitation") | controller | request-response | no code change, doc-only | n/a |
| `tools/tests/fast_test.py::TestRequirementsPin` (add capability assertion) | test | request-response / batch | same class, same file | exact |
| `tools/tests/fast_test.py::TestRecoveryCommands` (rewrite leading-paused test; add timeout-exclusion test) | test | CRUD-ish (state-machine polling) | `TestRecoveryCommands` itself (`fast_test.py:2073-2283`), esp. `test_resume_while_paused_waits_for_the_run_and_reports_ran` (:2127) and `test_resume_that_pauses_again_reports_the_actionable_paused_message` (:2155) | exact |
| `tools/tests/fast_test.py` (new end-to-end pause/abort/timeout tests, new `_Stepper` helper) | test | event-driven / streaming (threaded, poll-paced) | `_RealModeGrpcTestCase` + `_start_blocked_transfer` (`fast_test.py:666-738`) and `TestControlCommandsOverGrpc.test_pause_resume_abort_reach_service_while_transfer_in_flight` (`fast_test.py:761-792`) | role-match (combine with `TestRecoveryCommands`'s real-`FastService` fixture, D-14) |
| `tools/tests/fast_test.py::TestAdapterInvariant` (new AST rule only if a new method is extracted) | test | transform (AST check) | `test_planted_record_and_state_violations_are_caught` cases list (`fast_test.py:2586-2604`), `_RECORD_ONLY_FUNCTIONS` set (`:2299-2300`) | exact |

## Pattern Assignments

### `tools/fast/requirements.txt`

**Analog:** itself — the existing pin line, unchanged in form.

**Current line** (verify exact text before editing):
```
fast-mcp @ git+https://gitlab.formulatrix.com/nikkopg/fast-mcp.git@76f8c3fee41b0a2df3519aa74b022152df673824
```

**Target shape** (D-01): change only the SHA to the full 40-char
`b30b38df48e8480f325228145ccae7915a56e437`; keep the GitLab HTTPS URL form unchanged (do not switch
to `file://` — `TestRequirementsPin`'s `assertRegex` pattern requires the GitLab HTTPS form); update
any preceding `#` comment line to name the reason ("wait-through-pauses core") instead of whatever it
currently says. `TestRequirementsPin` (`fast_test.py:2616-2631`) only ever compares
`direct_url["vcs_info"]["commit_id"]` against this file's SHA — the install mechanism (D-02, local
`git+file://` clone into the gate venv) is independent of what this file's URL says.

---

### `tools/fast/server.py::Transfer` and `::RunProtocol` — `RunOptions(...)` wiring (D-04)

**Analog:** each method is the direct analog of the other; both already share the identical call
shape minus the two new kwargs.

**Current code, `Transfer`** (`server.py:673-680`):
```python
with self._run_in_flight():
    try:
        result = service.run_transfer(
            request, expected_tray_id=expected,
            options=RunOptions(timeout_s=self._timeout(None), on_progress=self._log_progress))
    except (InstrumentHTTPError, httpx.HTTPError) as exc:
        return _transport_error_reply(exc)
```

**Current code, `RunProtocol`** (`server.py:692-699`):
```python
with self._run_in_flight():
    try:
        result = service.run_protocol(
            params.csv,
            options=RunOptions(timeout_s=self._timeout(per_command),
                               on_progress=self._log_progress))
    except (InstrumentHTTPError, httpx.HTTPError) as exc:
        return _transport_error_reply(exc)
```

**Target diff (identical two-kwarg addition to both `RunOptions(...)` calls):**
```python
options=RunOptions(
    timeout_s=self._timeout(None),           # or self._timeout(per_command) for RunProtocol
    on_progress=self._log_progress,
    on_pause=self._record_pause,
    through_pauses=True)
```
`through_pauses` must be the literal Python `True` (core raises `TypeError` on a non-`bool`).
Nothing else in either method's body, lock usage, or exception handling changes — same
`self._motion_lock`, same `self._run_in_flight()`, same `except (InstrumentHTTPError,
httpx.HTTPError)` catch.

---

### `tools/fast/server.py::_record_pause` / `_log_progress` / `_run_in_flight` — already-built, no change

**Analog:** themselves (Phase 1 output); cited here because they are the callbacks `RunOptions(...)`
now wires in and because their docstrings need a wording update, not a logic change.

**`_record_pause`** (`server.py:546-559`, full body — copy its locking style for the Abort flag below):
```python
def _record_pause(self, info: "_PauseInfoLike") -> None:
    """Records the current pause for run_state (D-11, D-12). Phase 1 has
    no caller in production code -- the simulated hook (Plan 01-05) and
    the tests are the callers; Phase 2 wires it as
    RunOptions(on_pause=self._record_pause). Records only: no service
    call, no control method (D-16)."""
    pause = dict(info.to_dict())
    pause["since"] = datetime.now(timezone.utc).isoformat()
    with self._run_state_lock:
        self._run_record["pause"] = pause
        self._run_record["state"] = "paused"
        percent = _run_percent(pause.get("percent"))
        if percent is not None:
            self._run_record["percent"] = percent
```
Docstring update per D-05/the "Specific Ideas" note: the "Phase 2 wires it as ..." phrasing (also at
`server.py:379`, `388`, `549-550`, `575-576`) should become past tense ("Phase 2 wired it as ...")
since the wiring will now be done.

**`_run_in_flight`** (`server.py:514-534`, full body — the 0→1 reset this phase must also clear the
new abort flag in, per D-09 "`_run_in_flight()`'s 0→1 reset clears it"):
```python
@contextmanager
def _run_in_flight(self) -> Iterator[None]:
    """... Entry increments the nesting counter under _run_state_lock
    (never _motion_lock) and, only on the 0->1 transition, resets the
    record to running/no-percent/no-pause ..."""
    with self._run_state_lock:
        if self._active_runs == 0:
            self._run_record = {"state": "running", "percent": None, "pause": None}
        self._active_runs += 1
    try:
        yield
    finally:
        with self._run_state_lock:
            self._active_runs -= 1
            if self._active_runs == 0:
                self._run_record["pause"] = None
```
**Target:** the `self._run_record = {"state": "running", "percent": None, "pause": None}` literal on
the 0→1 reset line needs a third key added, e.g. `"operator_abort": False`, so every fresh run starts
with the flag cleared — this is the "no new reset logic needed" callout from RESEARCH.md's D-09 code
example, just extending the existing dict literal, not adding new lock/branch logic.

---

### `tools/fast/server.py::Abort` — operator-abort record-only flag (D-09)

**Analog:** `_record_pause`'s locking style (above) — write to `self._run_record[...]` under
`self._run_state_lock`, nothing else.

**Current code** (`server.py:813-830`, full body):
```python
def Abort(self, params: "Command.Abort") -> ExecuteCommandReply:
    """Operator-issued abort of a running or paused run. The core
    refuses in any other state without contacting the instrument. Never
    takes the motion lock (D-06), so it reaches a run in flight. Returns
    once the instrument has accepted the abort; it does not wait for the
    head to park."""
    return_liquid = _decision(params, "return_liquid")
    if return_liquid is None:
        return _reply(INVALID_ARGUMENTS,
                      message="return_liquid must be 'yes' or 'no'")
    service = self.service
    if service is None:
        return _reply(NOT_READY, message=_NOT_CONNECTED_MESSAGE)
    try:
        result = service.abort(return_liquid=return_liquid)
    except (InstrumentHTTPError, httpx.HTTPError) as exc:
        return _transport_error_reply(exc)
    return _recovery_reply("abort", result)
```

**Target shape (D-09), setting the flag inline — no new method, so no new AST rule needed per
Pitfall 6):**
```python
try:
    result = service.abort(return_liquid=return_liquid)
except (InstrumentHTTPError, httpx.HTTPError) as exc:
    return _transport_error_reply(exc)
if isinstance(result, dict) and result.get("errorCode") == 0:
    with self._run_state_lock:
        self._run_record["operator_abort"] = True
return _recovery_reply("abort", result)
```
Mirrors `_record_pause`'s `with self._run_state_lock: self._run_record[...] = ...` shape exactly.
`Abort` still calls only `.abort` on the service — no new control-method call (ADP-07 preserved,
`_SCOPED_ATTRS["abort"] == frozenset({"Abort"})` at `fast_test.py:2293` needs no change).

---

### `tools/fast/server.py::_message_for` — Aborted branch rewording (D-09/D-10)

**Analog:** the function's own neighboring branches (`Paused`, `Refused`) — same `isinstance` chain,
same `_one_line(text, 500)` wrap at the end.

**Current code** (`server.py:307-341`, full function; the branch to change is lines 334-335):
```python
def _message_for(result: RunResult, expected_tray_id: Optional[int]) -> str:
    """D-12: every message passes through _one_line with limit 500."""
    text = ""
    ...
    elif isinstance(result, Paused):
        text = (f"run paused at {result.percent}%: {_outcome_text(result.outcome)}; "
                "fix the deck, then send Resume (is_tip_broken) or Abort (return_liquid)")
    elif isinstance(result, Aborted):
        text = f"run aborted at {result.percent}%: {_outcome_text(result.outcome)}"
    elif isinstance(result, TimedOut):
        ...
    return _one_line(text, 500)
```

**Target shape (D-09/D-10 — parameter addition is the smaller diff against the existing
`_message_for(result, expected_tray_id)` signature, per RESEARCH Open Question 1):**
```python
def _message_for(result: RunResult, expected_tray_id: Optional[int],
                  operator_abort: bool = False) -> str:
    ...
    elif isinstance(result, Aborted):
        outcome_text = _outcome_text(result.outcome)
        if operator_abort:
            text = f"run aborted by operator at {result.percent}%"
            if outcome_text != "no error reported":
                text += f": {outcome_text}"
        else:
            text = f"run aborted at {result.percent}%: {outcome_text}"
    ...
```
Both call sites must pass the flag: `_result_reply` (`server.py:344-347`, reads it from the run
record once, likely via a new optional parameter threaded from `Abort`'s caller context) and the
direct `_message_for(result, None)` call inside `_recovery_reply` (`server.py:365`) for the
`Refused` case is unaffected (Refused is a different branch, never Aborted). `_message_for` stays
pure — it takes the flag as an argument, never reads `self._run_record` itself (D-10).

`result.percent` for `Aborted` is `self.outcome.percent` (confirmed in RESEARCH from
`fast_mcp/results.py`); `_outcome_text`'s "no error reported" fallback is the existing function
above, unchanged (`server.py:285-304`).

---

### `tools/tests/fast_test.py::TestRequirementsPin` — LIVE-01 capability assertion (D-03)

**Analog:** itself; add either a new test method on this class or a small sibling class (Claude's
Discretion).

**Current full class** (`fast_test.py:2616-2631`):
```python
class TestRequirementsPin(unittest.TestCase):
    def test_requirements_txt_pins_exactly_one_credential_free_sha(self) -> None:
        req_path = _REPO_ROOT / "tools" / "fast" / "requirements.txt"
        lines = [
            line.strip() for line in req_path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self.assertEqual(len(lines), 1)
        pattern = (r"^fast-mcp @ git\+https://gitlab\.formulatrix\.com/"
                  r"nikkopg/fast-mcp\.git@[0-9a-f]{40}$")
        self.assertRegex(lines[0], pattern)

        pinned_sha = lines[0].rsplit("@", 1)[1]
        direct_url = json.loads(
            importlib.metadata.distribution("fast_mcp").read_text("direct_url.json") or "{}")
        self.assertEqual(direct_url["vcs_info"]["commit_id"], pinned_sha)
```

**New capability test (same class or sibling), per D-03:**
```python
def test_installed_core_has_through_pauses_and_pause_info(self) -> None:
    field_names = {f.name for f in dataclasses.fields(RunOptions)}
    self.assertIn("through_pauses", field_names)
    self.assertIn("on_pause", field_names)
    from fast_mcp.orchestration import PauseInfo  # noqa: F401 -- import succeeds or raises
```
Uses the same bare `assertRegex`/`assertEqual`-style direct assertions as the sibling test in this
class — no mocking, since this is a static capability check against the installed package, exactly
like the existing `direct_url.json` check.

**Behavioral state-gate assertions** (idle → `Refused` from `pause`/`resume`/`abort`, transport never
called): already exist and need no new code — `test_abort_while_idle_is_refused_without_an_abort_call`
(`fast_test.py:2104`), `test_resume_while_idle_is_refused_without_a_resume_call` (`:2181`),
`test_pause_while_not_running_is_refused_without_a_pause_call` (`:2238`) already cover this against
the real `FastService`/stub-transport fixture (D-14) — simply re-running them after the re-pin is
the gate.

---

### `tools/tests/fast_test.py::TestRecoveryCommands` — fixture, `_statuses`, and the leading-paused rewrite (D-08, Pitfall 1)

**Analog:** the class's own `setUp`/`_statuses` fixture, and its sibling resume tests.

**Fixture** (`fast_test.py:2079-2092`, full — this is the D-14 "real FastService over MagicMock
transport" pattern every new test in this phase should reuse or extend):
```python
def setUp(self) -> None:
    self._openapi = default_openapi_path()
    openapi_path = self._openapi.__enter__()
    self.addCleanup(self._openapi.__exit__, None, None, None)
    self.transport = MagicMock()
    self.service = FastService(InstrumentSession(self.transport, openapi_path),
                               sleep=lambda _s: None, poll_interval_s=0.01)
    self.server = FastServer()
    self.server.service = self.service
    self.server.config = fast_pb2.Config(host="h")
    self.server.status = READY

def _statuses(self, *states: dict) -> None:
    self.transport.get_status.side_effect = list(states)
```
For D-13's timeout test, construct a **separate** `FastService` (don't reuse `self.service`) with
`sleep=`/`clock=` fakes and a short `run_timeout_s`, following this exact `InstrumentSession(self.
transport, openapi_path)` construction shape.

**Sibling resume test whose shape the Pitfall-1 rewrite should mirror** (`fast_test.py:2127-2139`,
full — this is the "first post-gate reading is `running`, not `paused`" shape that is NOT affected by
the re-pin, and is the template for the rewritten test's new terminal tail):
```python
def test_resume_while_paused_waits_for_the_run_and_reports_ran(self) -> None:
    self._statuses(
        {"currentState": "paused"},  # core state gate
        {"currentState": "running", "percentProgress": 50},
        {"currentState": "idle", "percentProgress": 100,
         "lastEvent": {"messageType": 5, "payload": {"errorCode": 0}}},
    )
    self.transport.resume.return_value = {"errorCode": 0}
    reply = self.server.Resume(fast_pb2.Command.Resume(is_tip_broken="yes"))
    self.assertEqual(reply.response, SUCCESS)
    self.assertEqual(MessageToDict(reply.meta_data)["kind"], "ran")
    self.transport.resume.assert_called_once_with(is_tip_broken=True)
    self.transport.abort.assert_not_called()
```

**Test to rewrite** (`fast_test.py:2170-2179`, full current body — D-08, Pitfall 1: this will
`StopIteration` under `b30b38d` because it only has 2 canned readings):
```python
def test_resume_known_limitation_leading_paused_poll_reads_as_paused(self) -> None:
    """Pins the documented limitation on FastServer.Resume: if the
    instrument still says paused on the first poll after accepting the
    resume, the wait reports Paused. Change this test if the core's wait
    learns to ignore a leading paused."""
    self._statuses({"currentState": "paused"}, {"currentState": "paused"})
    self.transport.resume.return_value = {"errorCode": 0}
    reply = self.server.Resume(fast_pb2.Command.Resume(is_tip_broken="no"))
    self.assertEqual(reply.response, ERROR_FROM_TOOL)
    self.assertEqual(MessageToDict(reply.meta_data)["kind"], "paused")
```

**Target rewrite (D-08 — pins the fixed behavior: a masked stale leading `paused` no longer blocks the
wait; ends SUCCESS/`"ran"`, not Paused):**
```python
def test_resume_masks_a_stale_leading_paused_and_reports_ran(self) -> None:
    """D-08: the re-pinned core's ResumeMarker classifies the first
    post-resume `paused` reading as stale (not live) when it immediately
    follows an accepted resume, so it is never terminal and never re-fires
    on_pause; the wait continues to a real terminal state."""
    self._statuses(
        {"currentState": "paused"},   # core state gate
        {"currentState": "paused"},   # stale, masked by ResumeMarker -- no longer terminal
        {"currentState": "running", "percentProgress": 50},
        {"currentState": "idle", "percentProgress": 100,
         "lastEvent": {"messageType": 5, "payload": {"errorCode": 0}}},
    )
    self.transport.resume.return_value = {"errorCode": 0}
    reply = self.server.Resume(fast_pb2.Command.Resume(is_tip_broken="no"))
    self.assertEqual(reply.response, SUCCESS)
    self.assertEqual(MessageToDict(reply.meta_data)["kind"], "ran")
```
Also remove the "Known limitation" paragraph from `Resume`'s docstring (`server.py:843-848`), per
D-08 — see the `Resume` excerpt above under the `server.py::Abort` section's sibling, reproduced in
full in the "Core Patterns" section below.

---

### `tools/tests/fast_test.py` — new end-to-end pause/abort/timeout tests (D-15, D-16, D-13)

**Analog combination:** `_RealModeGrpcTestCase`/`_start_blocked_transfer` (threading + gRPC shape)
**plus** `TestRecoveryCommands`'s real-`FastService`-over-stub-transport fixture (D-14) — these two
patterns must be *combined*, since `_RealModeGrpcTestCase` today injects a `MagicMock(spec=
FastService)` (not a real one), which does not satisfy D-14 for this phase's new tests.

**gRPC/threading shape to copy** (`fast_test.py:666-738`, full `_RealModeGrpcTestCase` plus
`_start_blocked_transfer` — note `setUp`'s `self.service = MagicMock(spec=FastService)` on line 676
must be replaced with the real `FastService` construction from `TestRecoveryCommands.setUp` for any
new test class built on this pattern):
```python
class _RealModeGrpcTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.server = FastServer()
        self.service = MagicMock(spec=FastService)  # <- replace with real FastService, D-14
        self.server.service = self.service
        self.server.config = fast_pb2.Config(host="h")
        self.server.status = READY

        self._grpc_port = _free_tcp_port()
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        add_ToolDriverServicer_to_server(self.server, self._server)
        self._server.add_insecure_port(f"127.0.0.1:{self._grpc_port}")
        self._server.start()
        self.addCleanup(self._server.stop, None)

        self._channel = grpc.insecure_channel(f"127.0.0.1:{self._grpc_port}")
        self.addCleanup(self._channel.close)
        self.stub = ToolDriverStub(self._channel)

    def _fast(self, **command: Any) -> tool_base_pb2.Command:
        return tool_base_pb2.Command(fast=fast_pb2.Command(**command))

    def _health(self) -> tool_base_pb2.StatusReply:
        return cast(tool_base_pb2.StatusReply, self.stub.GetStatus(empty_pb2.Empty()))
```

**Concurrency-test driving shape to copy** (`fast_test.py:761-792`, full body — the exact
pause/resume/abort-while-Transfer-in-flight interleaving pattern; the new test replaces the
`self.service.pause.return_value = ...` MagicMock-return-value style with real transport
`side_effect` scripting via `_statuses`):
```python
def test_pause_resume_abort_reach_service_while_transfer_in_flight(self) -> None:
    self.service.pause.return_value = {"errorCode": 0}
    self.service.resume.return_value = {"errorCode": 0}
    self.service.abort.return_value = {"errorCode": 0}

    release, thread, result = self._start_blocked_transfer()
    self.assertEqual(self._health().status, BUSY)

    for field, message, method, kwargs in (
        ("pause", fast_pb2.Command.Pause(), "pause", {"hard": False}),
        ("resume", fast_pb2.Command.Resume(is_tip_broken="no"), "resume",
         {"is_tip_broken": False}),
        ("abort", fast_pb2.Command.Abort(return_liquid="no"), "abort",
         {"return_liquid": False}),
    ):
        status_before = self.service.status.call_count
        reply = self.stub.ExecuteCommand(self._fast(**{field: message}))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        getattr(self.service, method).assert_called_once_with(**kwargs)
        self.assertEqual(self.service.status.call_count, status_before)
        self.assertEqual(self._health().status, BUSY)
        self.assertTrue(thread.is_alive())

    self.service.wait.assert_not_called()
    self.service.status.assert_not_called()

    release.set()
    thread.join(timeout=10)
    self.assertFalse(thread.is_alive())
    self.assertEqual(result["transfer"].response, SUCCESS)
    self.service.run_transfer.assert_called_once()
    self.assertEqual(self._health().status, READY)
```
**IMPORTANT deviation per RESEARCH.md Pattern 3/Pitfall 3:** do NOT literally gate `get_status` on a
`threading.Event` (the literal D-15 phrasing) — `ResumeMarker` holds its own lock across the
`get_status()` call, so an `Event`-blocked `get_status` deadlocks any concurrent `resume`/`abort`/
`status` call from the main thread. Instead, build a **new local stepper helper** (Claude's
Discretion) copying the core's own `_Stepper` pattern (reproduced verbatim in RESEARCH.md's Pattern
3, source: `fast-mcp tests/test_run_control_threads.py`, not importable — copy the pattern, not the
import):
```python
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
Gate the real `FastService` with `sleep=stepper.sleep, poll_interval_s=0.01`; keep
`self.transport.get_status.side_effect` a **plain pre-built list** (`_statuses(...)`-style, never a
blocking function). Drive the worker-thread `Transfer` via `self.stub.ExecuteCommand(...)` exactly as
`_start_blocked_transfer` does, then interleave `stepper.wait_sleeping()` / assertions /
`stepper.step()` from the main thread to read health `GetStatus` and send `Resume`/`Abort` via
`ExecuteCommand` at the right poll boundary.

**Timeout-exclusion test (D-13)** — pattern from RESEARCH.md's Code Examples (portable, not
importable; the "far longer than timeout, still SUCCESS" vs. "same running time, TimedOut" control
pair):
```python
stub_statuses = (
    [{"currentState": "running"}]
    + [{"currentState": "paused", "percentProgress": 10,
       "lastEvent": {"messageType": 1, "payload": {"errorCode": -301}}}] * 20
    + [{"currentState": "running", "percentProgress": 50},
       {"currentState": "idle", "percentProgress": 100,
        "lastEvent": {"messageType": 5, "payload": {"errorCode": 0}}}])
# FastService(sleep=no-op, clock=_fake_clock(step=1.0), run_timeout_s=6.0)
# Control case: replace the 20 paused readings with 20 running readings at the
# same step size -- MUST end TimedOut.
```
`_fake_clock`/`_no_sleep` helpers (new local test helpers, copy the pattern verbatim from RESEARCH.md
Pattern 2 / `fast-mcp tests/test_pause_control.py`):
```python
def _no_sleep(_seconds):
    return None

def _fake_clock(step: float = 2.0):
    t = 0.0
    def _clock():
        nonlocal t
        t += step
        return t
    return _clock
```
Assert `self.transport.abort.assert_not_called()` / `self.transport.pause.assert_not_called()` /
`self.transport.resume.assert_not_called()` in the timeout case, per D-16's "a timeout case asserts
the transport's abort/pause/resume are never called."

---

### `tools/tests/fast_test.py::TestAdapterInvariant` — no new rule unless a method is extracted (Pitfall 6, D-17)

**Analog:** `test_planted_record_and_state_violations_are_caught`'s case list (`fast_test.py:2586-
2604`) and the `_RECORD_ONLY_FUNCTIONS` set (`:2299-2300`), only if the chosen `Abort` implementation
extracts a separate method (e.g. `_mark_operator_abort()`) instead of writing the flag inline.

**If a new method is extracted, add it to `_RECORD_ONLY_FUNCTIONS`** (`fast_test.py:2299-2300`,
current value):
```python
_RECORD_ONLY_FUNCTIONS = frozenset(
    {"_record_pause", "_log_progress", "simulate_pause", "_clear_pause"})
```
and add a matching planted-violation case to `test_planted_record_and_state_violations_are_caught`
(`fast_test.py:2586-2596`), following the existing shape exactly:
```python
("_mark_operator_abort", "self.service.pause(hard=False)", "_mark_operator_abort"),
```
**If the flag is set inline inside `Abort()`** (the recommended, smaller-diff shape per RESEARCH
Pitfall 6 — `Abort` is already an allowed caller of `.abort` in `_SCOPED_ATTRS`), **no change to this
class is needed at all.**

## Shared Patterns

### Real `FastService` over `MagicMock` transport (D-14) — the mandatory fixture for every new test this phase
**Source:** `tools/tests/fast_test.py:2079-2092` (`TestRecoveryCommands.setUp`/`_statuses`)
**Apply to:** every new or rewritten test in this phase (LIVE-01 capability+behavioral, LIVE-02
end-to-end pause/abort, LIVE-03 timeout-exclusion). No test in this phase may use
`MagicMock(spec=FastService)` in place of a real one — only the transport is mocked.
```python
self._openapi = default_openapi_path()
openapi_path = self._openapi.__enter__()
self.addCleanup(self._openapi.__exit__, None, None, None)
self.transport = MagicMock()
self.service = FastService(InstrumentSession(self.transport, openapi_path),
                           sleep=lambda _s: None, poll_interval_s=0.01)
```

### Record-only writes under `_run_state_lock`, never `_motion_lock`
**Source:** `tools/fast/server.py:546-559` (`_record_pause`), `:514-534` (`_run_in_flight`)
**Apply to:** the new operator-abort flag in `Abort` (D-09) — always `with self._run_state_lock:
self._run_record[...] = ...`, never a call to a control/motion method from inside that block.

### `RunOptions(...)` single call-site shape shared by both long-running commands
**Source:** `tools/fast/server.py:673-680` (`Transfer`), `:692-699` (`RunProtocol`)
**Apply to:** both methods get the identical two-kwarg addition (`on_pause=self._record_pause,
through_pauses=True`); no other line in either method changes (D-04).

### Sleep-gated stepper, never Event-gated `get_status` (deadlock avoidance)
**Source:** RESEARCH.md Pattern 3, portable from `fast-mcp tests/test_run_control_threads.py`
(not importable — `tests/` is excluded from the installed package, Pitfall 5)
**Apply to:** every threaded end-to-end test (D-15/D-16) and nowhere else; `get_status`'s
`side_effect` must always stay a plain, pre-built, non-blocking list.

### `_one_line(text, 500)` cap on every operator-facing message
**Source:** `tools/fast/server.py:341` (`_message_for`'s return statement)
**Apply to:** the reworded `Aborted` branch — the new "run aborted by operator at <p>%[: <error>]"
text passes through the same `_one_line(text, 500)` wrap as every other branch; no new truncation
logic needed.

## No Analog Found

None — every file/site touched this phase has a strong in-file or sibling-file analog; this is a
narrow, additive phase on a codebase whose Phase 1 work already built every pattern this phase reuses.

## Metadata

**Analog search scope:** `tools/fast/server.py` (full), `tools/tests/fast_test.py` (lines 1-130,
666-1505, 2060-2636), `tools/fast/requirements.txt`.
**Files scanned:** 3 (all pre-read in full or targeted by RESEARCH.md this session; no additional
Glob/Grep search was needed since RESEARCH.md already pinpointed every relevant line number with
`[VERIFIED]` tags).
**Pattern extraction date:** 2026-10-13

## PATTERN MAPPING COMPLETE
