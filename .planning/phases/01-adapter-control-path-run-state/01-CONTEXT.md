# Phase 1: Adapter Control Path & Run State - Context

**Gathered:** 2026-10-12
**Status:** Ready for planning
**Mode:** `--auto` (every gray area resolved with the recommended option; see 01-DISCUSSION-LOG.md)

<domain>
## Phase Boundary

The F.A.S.T. adapter (`tools/fast/server.py`, `fast.proto`, `tool_base.proto`) gains the following:

- A soft-only `Pause` command.
- `Pause`/`Resume`/`Abort` that reach `FastService` while a `Transfer`/`RunProtocol` is in flight,
  through a `FastServer.ExecuteCommand` override. A control command never changes the tool's status.
- `StatusReply.run_state`, reported by the health `GetStatus` RPC.
- A simulated-mode pause hook.
- Extended no-auto-abort invariants and a real-mode concurrency test.

Everything is proven against a mocked `FastService` on the **currently pinned core (`76f8c3f`)**.

**Not in this phase:**
- Re-pinning the core, `through_pauses`/`on_pause` wiring into `Transfer`/`RunProtocol`, and paused
  time excluded from the timeout (Phase 2).
- Deploy and live acceptance (Phase 3).
- All galago-core work (its own `.planning/`).
- Editing `tools/base_server.py`.

</domain>

<decisions>
## Implementation Decisions

### ExecuteCommand override (ADP-02, ADP-03, ADP-06)
- **D-01:** `FastServer.ExecuteCommand(request, context)` checks for a control command **before**
  `parseCommand`:
  - `request.WhichOneof("tool_command") == "fast"`, and
  - the inner `WhichOneof("command")` is one of `pause`/`resume`/`abort`.

  The control commands are named in one module-level `CONTROL_COMMANDS` frozenset. Every other
  request, a wrong tool type included, calls `super().ExecuteCommand(request, context)` unchanged.
  `tools/base_server.py` is not edited.
- **D-02:** The control path skips `isReady()` and never calls `setStatus`, so a BUSY tool stays
  BUSY and a READY tool stays READY.
  - It dispatches through `self._dispatchCommand(command)`, so `_check_args` (blank or unclear
    decisions are `INVALID_ARGUMENTS`) and base_server's simulated-mode branch apply exactly as for
    other commands.
  - It catches `Exception` → `DRIVER_ERROR` and sets `last_error`, mirroring base_server's handler.
  - It logs `Running command <Name>` like base_server.
- **D-03:** The tool-type check stays: a non-`fast` request never takes the control path; it falls
  through to base_server, which returns `WRONG_TOOL`.
- **D-04:** Write the failing **real-mode** concurrency test first, as its own task/commit (ADP-08):
  - Setup: `simulated=False`, status READY, mocked `FastService`.
  - A `Transfer` is blocked inside `run_transfer` on a `threading.Event`, so `ExecuteCommand` has
    set BUSY.
  - `Pause`, `Resume` and `Abort` sent through `ExecuteCommand` each reach the mock exactly once.
  - Status is BUSY after each one.
  - Release the event: the Transfer ends SUCCESS and status returns to READY (base_server's
    `finally` for the Transfer).

  Then build the override to make it pass.

### Control commands (ADP-01, ADP-04, ADP-09)
- **D-05:** New `message Pause {}` in `fast.proto`, with no fields (D5: soft only). It is oneof
  `Pause pause = 10;`. `Pause()` calls `service.pause(hard=False)`, with `hard` passed explicitly as
  a keyword. Its result maps through `_recovery_reply("pause", ...)`:
  - `Refused` → `ERROR_FROM_TOOL` "instrument not ready…";
  - `errorCode` 0 → `SUCCESS`;
  - anything else → `ERROR_FROM_TOOL`.

  Add `"Pause": "pause"` to `COMMAND_TO_SERVICE_METHOD`, so the 1:1 surface tests cover it, and add
  `EstimatePause` (small flat value, `EST_READ_S`-sized or `EST_ABORT_S`; planner's choice).
- **D-06:** `Pause` and `Abort` never touch `_motion_lock`. `ScanTips` and `EjectTray` keep the lock
  exactly as today; only the three control commands change (research Pitfall 5).
  - Replace `MOTION_COMMANDS` so it no longer lists `Abort`/`Resume`; the long-running commands are
    named separately from `CONTROL_COMMANDS`. Exact constant names are the planner's choice.
- **D-07:** `Resume` decides between the two paths with a **non-blocking `_motion_lock.acquire()`**.
  - **Lock acquired** → no motion command is in flight (crash recovery): keep today's behaviour.
    `service.resume(...)`, then `service.wait(RunHandle(...))` with the same timeout and progress
    logging, holding the lock for the whole wait, so no new Transfer can start under it.
  - **Lock not acquired** → a run is in flight: call `service.resume(...)` and return as soon as the
    instrument accepts. No wait, and no lock taken. The in-flight step's own wait reports the
    outcome.

  This is adapter bookkeeping about its own threads, not an instrument-state check. The core still
  decides whether a resume is allowed.
- **D-08:** No instrument-state check of any kind in the adapter (ADP-09):
  - control commands never call `service.status()` before acting;
  - no comparison against instrument state strings anywhere in the control path.

  Test it this way: with the mock's `status` returning any state, each control command calls its
  service method exactly once, and `status` zero times.

### run_state reporting (ADP-05)
- **D-09:** Add `optional google.protobuf.Struct run_state = 4;` to `StatusReply` in
  `tool_base.proto`. `struct.proto` is already imported. Regenerate Python with `bin/make proto`.
  - TS regeneration (ts-proto 1.151.1) belongs to galago-core through its `vendor/galago-tools`
    submodule, not this phase.
- **D-10:** The health `GetStatus` (2-arg arity branch) calls `super().GetStatus(...)` and fills
  `run_state` on the reply. The intent-command `GetStatus` (1-arg) is unchanged. Other tool types
  never set it.
- **D-11:** `run_state` shape:
  - camelCase keys, matching `PauseInfo.to_dict()`'s style, which galago-core reads:
    `{"state": str, "percent": int | null, "pause": {...} | null}`.
  - `pause` = `PauseInfo.to_dict()` (`errorCode`, `errorName`, `percent`, `eventPayload`) plus
    `"since"`, an ISO-8601 UTC timestamp of when the adapter recorded the pause.
- **D-12:** Source of `run_state`:
  - **Run in flight:** the adapter's own record, under a small dedicated `threading.Lock`, never
    `_motion_lock`.
    - `_log_progress` already receives `(percent, state)` on every poll; it also updates the record.
    - A recorder method (`_record_pause(info)`, name at the planner's choice) stores the pause and
      its timestamp.
    - An observation of `running` clears the pause.
    - Long-running commands set the record on entry and clear it on exit.
  - **No run in flight:** a fresh `service.status()`, mapped to `state`/`percent` with
    `pause: null`. Crash-recovery detail stays on the tool page's raw `GetStatus` intent command.
  - **Service not configured:** `run_state` unset.
  - **`status()` transport error:** `{"state": "unknown"}`, and the health RPC still returns
    normally. A heartbeat must never fail because of run state.
- **D-13:** Phase 1 must not import `PauseInfo`, `ResumeMarker` or the new `RunOptions` fields: the
  pinned core `76f8c3f` (and the gate venv) doesn't have them.
  - The recorder accepts any object with `to_dict()` (duck-typed, a `Protocol` for mypy).
  - Its unit tests feed a stub.
  - Phase 2 connects it as `RunOptions(on_pause=...)`.
- **D-14:** Reading `run_state` never commands the instrument. `service.status()` is the only call
  on that path (Safety invariant 4).

### Invariants (ADP-07)
- **D-15:** Extend `TestAdapterInvariant`'s scoped-attribute map:
  - `.pause` only in `Pause`;
  - `.resume` only in `Resume`;
  - `.abort` only in `Abort`;
  - `.wait` only in `Resume` (crash-recovery path) plus `Transfer`/`RunProtocol` if they ever call
    it directly (today they call `run_transfer`/`run_protocol`).
- **D-16:** The pause recorder and `_log_progress` may only record state:
  - an AST check asserts their bodies make no call on `self.service`/`service`, and call no control
    method;
  - `GetStatus`'s run_state builder may call only `.status()`.
- **D-17:** Keep and extend the planted-violation pattern. For each new rule, a test plants a
  violating call (e.g. `.pause()` inside `_record_pause`, `.abort()` inside `Transfer`) in a source
  copy and asserts the checker fails. The existing invariants still hold:
  - no `fast_mcp.mcp` import;
  - no raw `:5003`;
  - `open_service` is the only way to get a service.

### Simulated mode (ADP-10)
- **D-18:** In simulated mode, control commands go through `_check_args`, then base_server's
  simulated branch: sleep the estimate, return SUCCESS. Nothing is ever sent to an instrument, and
  the simulated `Transfer` sleep is never shortened.
- **D-19:** Simulated `run_state`:
  - `{"state": "running", "percent": null, "pause": null}` while a simulated long-running command
    sleeps;
  - `{"state": "idle", ...}` otherwise.

  The adapter's `_dispatchCommand` override marks the simulated run's start and end, since
  base_server does the sleep.
- **D-20:** The test hook is an **in-process method on `FastServer`**, e.g.
  `simulate_pause(pause: dict | None)`. Only in simulated mode; it raises otherwise.
  - It sets or clears the recorded pause, so `run_state` reads `paused` with that `PauseInfo` dict.
  - galago-core exercises its prompt by running the tool server under a small dev script or test
    that calls the hook. No new gRPC command, so the 1:1 command surface is unchanged.
  - A simulated `Resume` or `Abort` clears a hooked pause, so the UI's controls round-trip without
    hardware.

### Claude's Discretion
- Exact names of constants, helpers and the recorder; where the override sits in `server.py`.
- Whether the real-mode concurrency test lives in `tools/tests/fast_test.py` or a new test class in
  the same file (keep to the `_MockedFastServerTestCase` tearDown invariant check).
- How the simulated run's start and end are detected around base_server's sleep (D-19).
- Docstring updates: `Resume`'s known-limitation note now applies only to the crash-recovery path.
- `EstimateResume` stays a flat placeholder. It is accepted debt once mid-run Resume no longer
  waits (research Pitfall 8); note it in a comment, as the D-16 placeholders are.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Governing design
- `docs/specs/2026-10-12-galago-live-run-control-design.md`:
  - §5.1: control commands and the ExecuteCommand correction;
  - §5.3: run_state, option A;
  - §5.4: invariants;
  - §5.5: simulated mode;
  - §7: safety invariants;
  - §11: decisions D1-D6, notably D5 (soft pause only).
- `.planning/REQUIREMENTS.md`: ADP-01..ADP-10. ADP-10 (simulated pause hook) overrides the spec's
  §5.5 "out of scope" note.
- `.planning/ROADMAP.md`: Phase 1 success criteria and research flags.

### Research
- `.planning/research/SUMMARY.md`: Critical Pitfall 1 (base_server BUSY gate), Pitfall 5 (motion
  lock scope).
- `.planning/research/ARCHITECTURE.md`: suggested build order, override recommendation (MEDIUM
  confidence).
- `.planning/research/PITFALLS.md`: Pitfalls 4, 5, 8 (EstimateResume), 10.

### Core API (fast-mcp, read-only reference)
- `~/data/nikko/fast/fast-mcp/fast_mcp/orchestration.py`: `PauseInfo` and its `to_dict()` key names.
- `~/data/nikko/fast/fast-mcp/fast_mcp/service.py`: `pause(*, hard=False)`, `resume`, `abort`,
  `status`, `wait(..., on_pause, through_pauses)` and their state gates.
- `~/data/nikko/fast/fast-mcp/fast_mcp/run_control.py`: `RunOptions.on_pause`, `ResumeMarker`.

These exist at `b30b38d`, not at the current pin `76f8c3f`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_recovery_reply(action, result)` (`tools/fast/server.py:314`): the `Refused`/`errorCode` mapping
  for Pause, unchanged.
- `_decision` / `_RECOVERY_DECISION_FIELD` / `_check_args` (`server.py:134-215`): fail-closed yes/no
  checking. Pause has no decision, so `_check_args` returns `[]` for it.
- `_MockedFastServerTestCase` (`tools/tests/fast_test.py:304`): mocked-service base with a
  per-class tearDown invariant check.
- `TestMotionSerialization` (`fast_test.py:545`): the threading/Event pattern for a blocked
  Transfer.
- `TestAdapterInvariant` (`fast_test.py:1140`): AST scoped-attribute check with a planted-violation
  test.

### Established Patterns
- `FastServer` already overrides `_dispatchCommand` (argument checks before base dispatch) and
  `GetStatus` (arity-discriminated dual purpose). The new `ExecuteCommand` override follows the
  same "override, never edit base_server" pattern.
- base_server `ExecuteCommand` (`tools/base_server.py:226-256`): `parseCommand` refuses unless
  READY (`:200`), `setStatus(BUSY)` (`:236`), `finally: setStatus(READY)` (`:254`). These are what
  the override bypasses for control commands.
- base_server `isReady()` returns True in simulated mode, which is why the existing simulated
  concurrency test can't catch the gate.
- Physical decisions are `"yes"`/`"no"` strings, never bools.

### Integration Points
- `interfaces/tools/grpc_interfaces/fast.proto`: add `Pause` (oneof 10).
- `interfaces/tools/grpc_interfaces/tool_base.proto:128`: `StatusReply` gets field 4.
- Generated Python protos via `bin/make proto`. Gate: `bin/make proto test` on
  `~/data/nikko/.venvs/galago-py310` (ruff, mypy, unittest, pytest; last green 70 tests).
- galago-core consumes the proto through its `vendor/galago-tools` submodule (companion milestone).

</code_context>

<specifics>
## Specific Ideas

- Order of work inside the phase follows research: proto `Pause`, then the failing real-mode
  concurrency test, then the `ExecuteCommand` override and lock changes, then `run_state` proto and
  wiring, then the invariant extensions, then the simulated hook.
- The pinned limitation test `test_resume_known_limitation_leading_paused_poll_reads_as_paused`
  stays as is in Phase 1. It covers the crash-recovery Resume on the old core; Phase 2's re-pin
  revisits it.

</specifics>

<deferred>
## Deferred Ideas

- Hard pause: needs the F.A.S.T. team to document `hardPause` (D5); future requirement.
- `run_state` pause detail for the no-run-in-flight (crash-recovery) case. Today the tool page reads
  raw `GetStatus`. Revisit if galago-core's crash-recovery UI needs a structured pause.
- Out-of-process trigger for the simulated pause hook (gRPC command or env var). Not needed while
  the in-process hook serves galago-core's dev tests.
- Splitting `EstimateResume` into in-flight vs crash-recovery estimates (Pitfall 8).

</deferred>

---

*Phase: 01-adapter-control-path-run-state*
*Context gathered: 2026-10-12*
