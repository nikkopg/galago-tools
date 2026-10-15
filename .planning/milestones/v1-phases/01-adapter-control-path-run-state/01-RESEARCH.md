# Phase 1: Adapter Control Path & Run State - Research

**Researched:** 2026-10-12
**Domain:** gRPC tool-driver adapter control path (galago-tools `tools/fast/server.py`), extending an
existing Python 3.10 adapter over a mocked `fast_mcp.FastService` core
**Confidence:** HIGH — every claim below that matters for planning was either (a) read directly from
a source file this session, or (b) proven by actually running `bin/make proto`/`bin/make test` against
this repo's pinned gate venv and observing the result. No web search was needed: this phase has zero
new external packages and the governing design (`docs/specs/2026-10-12-galago-live-run-control-design.md`)
plus the milestone-level research already answer the "what"; this document answers the "how" with
file:line evidence and verified tool output.

## Summary

Phase 1 adds one new proto message (`fast.Command.Pause`), one new proto field
(`tool_base.StatusReply.run_state`), a `FastServer.ExecuteCommand` override, lock changes to
`Abort`/`Resume`/`Pause`, a `run_state` recorder, an extended AST invariant, and a simulated-mode
test hook — all against a mocked `FastService` and the currently pinned core `76f8c3f`. Every
structural question the plan needs answered has been verified directly against this repository and
the pinned core checkout this session:

- `bin/make proto` regenerates cleanly with both new proto changes added (verified by actually adding
  them, running the generator, inspecting the generated `.pyi`, then reverting). Exactly one existing
  test breaks as a direct, expected consequence (`TestOneToOneSurface.test_command_to_service_method_matches_oneof_message_names`),
  which is the live proof that `"Pause": "pause"` must be added to `COMMAND_TO_SERVICE_METHOD` (D-05).
- `optional google.protobuf.Struct run_state` has exactly the presence semantics D-09/D-12 need:
  `HasField` is `False` until the submessage is mutated (e.g. via `.update(...)`), and `.update()`
  converts a Python `None` value to protobuf's `null_value: NULL_VALUE` automatically — verified live
  in a Python REPL against the regenerated pb2 module.
- The pinned core (`76f8c3f`) was read directly (`git cat-file -p 76f8c3f...:fast_mcp/service.py`):
  `pause`/`resume`/`abort` already exist with exactly the signatures D-05/D-07/D-08 assume, but
  `wait`/`RunOptions` have no `on_pause`/`through_pauses` parameters and `PauseInfo`/`ResumeMarker`
  don't exist yet — confirming D-13's constraint precisely.
- `TestAdapterInvariant`'s AST check currently has `"pause"` in its **fully-banned** `banned_attrs` set
  (`fast_test.py:1184`), not in the scoped set — this is the single most important gotcha in this
  phase: adding a `Pause()` method that calls `.pause` will fail the existing invariant test
  immediately unless `"pause"` is moved from `banned_attrs` to `scoped_attrs` in the same change.
- `add_ToolDriverServicer_to_server` binds `servicer.ExecuteCommand` by ordinary Python attribute
  lookup at server-start time (`tool_driver_pb2_grpc.py:96`) — standard MRO dispatch, so a
  `FastServer.ExecuteCommand` override is picked up with zero special handling, exactly as the
  existing `GetStatus` override already proves.
- The gate command (`bin/make proto test` under `~/data/nikko/.venvs/galago-py310`) was actually run:
  baseline is **70 tests**, ruff and mypy are both clean on `tools/fast/server.py` today.

**Primary recommendation:** Follow the build order in `<specifics>` of 01-CONTEXT.md exactly (proto
`Pause` → failing real-mode concurrency test → `ExecuteCommand` override + lock changes → `run_state`
proto + wiring → invariant extension → simulated hook), and make the `banned_attrs` → `scoped_attrs`
move for `"pause"` part of the *same* task/commit that adds the `Pause` message to `fast.proto`, not
a later cleanup — otherwise every intermediate commit between adding `Pause` and extending the
invariant will fail `TestAdapterInvariant` for an unrelated-looking reason.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (D-01 through D-20)

See `.planning/phases/01-adapter-control-path-run-state/01-CONTEXT.md` for the full text. Summarized
by area (verbatim decision IDs preserved so the planner can cite them):

- **D-01..D-04 (ExecuteCommand override):** `FastServer.ExecuteCommand` checks for a control command
  (`tool_command == "fast"` and inner `command` is `pause`/`resume`/`abort`) before `parseCommand`.
  Control commands are named in one module-level `CONTROL_COMMANDS` frozenset. Every other request
  (wrong tool type included) calls `super().ExecuteCommand(request, context)` unchanged. The control
  path skips `isReady()`, never calls `setStatus`, dispatches through `self._dispatchCommand(command)`
  (so `_check_args` and base_server's simulated branch apply), catches `Exception` → `DRIVER_ERROR`,
  sets `last_error`, and logs `Running command <Name>`. The tool-type check stays (non-fast falls
  through to `WRONG_TOOL`). Write the failing real-mode concurrency test first, as its own
  task/commit (ADP-08): `simulated=False`, status READY, mocked `FastService`, a `Transfer` blocked on
  a `threading.Event`, then Pause/Resume/Abort sent through `ExecuteCommand` each reach the mock
  exactly once, status stays BUSY, then releasing the event lets Transfer finish SUCCESS and status
  returns to READY.
- **D-05..D-09 (control commands):** New `message Pause {}` in `fast.proto`, no fields (soft only),
  oneof `Pause pause = 10;`. `Pause()` calls `service.pause(hard=False)` with `hard` as an explicit
  keyword; result maps through `_recovery_reply("pause", ...)`. Add `"Pause": "pause"` to
  `COMMAND_TO_SERVICE_METHOD` and an `EstimatePause`. `Pause`/`Abort` never touch `_motion_lock`;
  `ScanTips`/`EjectTray` keep it exactly as today. `MOTION_COMMANDS` is replaced so it no longer lists
  `Abort`/`Resume`; exact constant names are the planner's choice. `Resume` decides between
  crash-recovery (lock acquired → wait as today) and in-flight (lock not acquired → call
  `service.resume(...)` and return once accepted, no wait, no lock) via a **non-blocking**
  `_motion_lock.acquire()`. No instrument-state check anywhere in the adapter (ADP-09): control
  commands never call `service.status()` before acting.
- **D-09..D-14 (run_state):** Add `optional google.protobuf.Struct run_state = 4;` to `StatusReply`
  in `tool_base.proto`; `struct.proto` already imported. Regenerate Python with `bin/make proto`; TS
  regeneration belongs to galago-core, not this phase. The health `GetStatus` (2-arg branch) calls
  `super().GetStatus(...)` and fills `run_state`; the intent-command `GetStatus` (1-arg) is unchanged.
  Shape: camelCase keys matching `PauseInfo.to_dict()`'s style —
  `{"state": str, "percent": int | null, "pause": {...} | null}`; `pause` = `PauseInfo.to_dict()`
  (`errorCode`, `errorName`, `percent`, `eventPayload`) plus `"since"` (ISO-8601 UTC). Source: run in
  flight → the adapter's own record under a small dedicated `threading.Lock` (never `_motion_lock`);
  `_log_progress` already receives `(percent, state)` on every poll and also updates the record; a
  recorder method (`_record_pause(info)`, name at planner's choice) stores the pause plus timestamp;
  an observation of `running` clears the pause; long-running commands set the record on entry, clear
  on exit. No run in flight → a fresh `service.status()` mapped to `state`/`percent`, `pause: null`.
  Service not configured → `run_state` unset. `status()` transport error → `{"state": "unknown"}`, the
  health RPC still returns normally. Phase 1 must not import `PauseInfo`/`ResumeMarker`/new
  `RunOptions` fields (pinned core `76f8c3f` lacks them) — the recorder accepts any object with
  `to_dict()` (duck-typed `Protocol` for mypy), tested with a stub. Reading `run_state` never commands
  the instrument — `service.status()` is the only call on that path.
- **D-15..D-17 (invariants):** Extend `TestAdapterInvariant`'s scoped-attribute map: `.pause` only in
  `Pause`; `.resume` only in `Resume`; `.abort` only in `Abort`; `.wait` only in `Resume`
  (crash-recovery) plus `Transfer`/`RunProtocol` if they ever call it directly. The pause recorder and
  `_log_progress` may only record state — an AST check asserts their bodies make no call on
  `self.service`/`service` and call no control method; `GetStatus`'s run_state builder may call only
  `.status()`. Keep and extend the planted-violation pattern for each new rule; existing invariants
  (no `fast_mcp.mcp` import, no raw `:5003`, `open_service` the only way to get a service) still hold.
- **D-18..D-20 (simulated mode):** Simulated control commands go through `_check_args`, then
  base_server's simulated branch: sleep the estimate, return SUCCESS — nothing is sent to an
  instrument, and the simulated `Transfer` sleep is never shortened. Simulated `run_state`:
  `{"state": "running", "percent": null, "pause": null}` while a simulated long-running command
  sleeps, `{"state": "idle", ...}` otherwise; `_dispatchCommand`'s override marks the simulated run's
  start and end. The test hook is an in-process method on `FastServer`, e.g.
  `simulate_pause(pause: dict | None)`, simulated-mode only (raises otherwise); it sets/clears the
  recorded pause so `run_state` reads `paused`; a simulated Resume/Abort clears a hooked pause; no new
  gRPC command.

### Claude's Discretion
- Exact names of constants, helpers and the recorder; where the override sits in `server.py`.
- Whether the real-mode concurrency test lives in `fast_test.py` or a new test class in the same file
  (keep to the `_MockedFastServerTestCase` tearDown invariant check).
- How the simulated run's start and end are detected around base_server's sleep (D-19).
- Docstring updates: `Resume`'s known-limitation note now applies only to the crash-recovery path.
- `EstimateResume` stays a flat placeholder — accepted debt, note it in a comment (D-16 precedent).

### Deferred Ideas (OUT OF SCOPE)
- Hard pause: needs the F.A.S.T. team to document `hardPause`; future requirement.
- `run_state` pause detail for the no-run-in-flight (crash-recovery) case — today the tool page reads
  raw `GetStatus`.
- Out-of-process trigger for the simulated pause hook (gRPC command or env var).
- Splitting `EstimateResume` into in-flight vs crash-recovery estimates.
- **Also out of scope for this phase (from the phase boundary):** re-pinning the core,
  `through_pauses`/`on_pause` wiring into `Transfer`/`RunProtocol`, paused time excluded from the
  timeout (Phase 2); deploy and live acceptance (Phase 3); all galago-core work; editing
  `tools/base_server.py`.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ADP-01 | Pause reaches the instrument as a soft pause; no hard/soft choice on the wire | Confirmed `FastService.pause(*, hard: bool = False)` exists in pinned core `76f8c3f` with exactly this signature (verified via `git cat-file`). `message Pause {}` (no fields) confirmed to regenerate cleanly. See "Control commands" pattern below. |
| ADP-02 | Pause/Resume/Abort reach `FastService` while a Transfer/RunProtocol is in flight, via an `ExecuteCommand` override; `base_server.py` unchanged | `base_server.py:195-256` read and quoted in full below — the exact gate the override must bypass. `add_ToolDriverServicer_to_server` binding mechanics verified (`tool_driver_pb2_grpc.py:96`) to confirm the override is picked up. |
| ADP-03 | A control command never changes the tool's status | Satisfied by construction: the override (D-02) never calls `self.setStatus(...)` for control commands, so `self.status` is left exactly as the in-flight motion command's own `ExecuteCommand` set it. |
| ADP-04 | Resume returns on acceptance mid-run; waits when no run is in flight | `threading.Lock.acquire(blocking=False)` as the in-flight signal (D-07) — sketch provided in Code Examples, grounded in the existing `Resume` structure at `server.py:543-578`. |
| ADP-05 | `GetStatus` returns `StatusReply.run_state` for F.A.S.T.; other tools unset | `optional google.protobuf.Struct` presence semantics verified live (HasField False until mutated); proto field-number slot (4) confirmed vacant; regeneration verified end-to-end. |
| ADP-06 | Blank/unclear decisions are `INVALID_ARGUMENTS` on every path | Existing `_decision`/`_check_args`/`_RECOVERY_DECISION_FIELD` pattern (`server.py:84, 134-215, 208-214`) read in full; `Pause` has no decision field so `_check_args` returns `[]` for it unchanged. |
| ADP-07 | No-auto-abort invariant extended; planted violation fails | `TestAdapterInvariant` read in full (`fast_test.py:1140-1215`); the critical `banned_attrs` vs `scoped_attrs` distinction for `"pause"` documented with exact line numbers. |
| ADP-08 | Real-mode concurrency test | `_MockedFastServerTestCase` (`fast_test.py:304-322`), `TestMotionSerialization` (`fast_test.py:545-608`), and the real-in-process-gRPC pattern (`TestSimulatedTransferOverGrpc`, `fast_test.py:167-229`) all read; composition for the new real-mode+mocked-service+gRPC-stub test documented below. |
| ADP-09 | No instrument-state check in the adapter | `FastService.pause/resume/abort` (pinned core) confirmed to do their own `_require_state` gating; adapter's `Resume`/`Abort`/`Pause` never call `service.status()` — verified absent from current `Abort`/`Resume` code and recommended absent from new `Pause`. |
| ADP-10 | Simulated mode: control commands SUCCESS after arg checks; test hook drives `run_state` to paused | `base_server._dispatchCommand`'s simulated branch read in full (`base_server.py:138-166`); no existing `simulate_*` hook pattern found (confirmed via repo-wide grep) — this is genuinely new surface, flagged as an Open Question for its exact wiring to the recorder. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Control-command dispatch (Pause/Resume/Abort reaching the instrument mid-run) | API/Backend (gRPC adapter, `FastServer`) | — | The adapter is the single process boundary between galago-core and the instrument; galago-core's tRPC/UI side is a separate repo's milestone, explicitly out of scope here |
| Instrument state gating (who may pause/resume/abort, in what instrument state) | Database/Storage-equivalent (the instrument itself, via `FastService._require_state`) | — | D-08/ADP-09: the adapter must add zero state checks of its own; the core (`fast-mcp`) is the sole source of truth, confirmed unchanged in the pinned core |
| run_state observation (GetStatus reporting state/percent/pause) | API/Backend (`FastServer.GetStatus`/`_get_status`) | — | Pure read, never commands the instrument (D-14); lives entirely in the adapter process, no new tier |
| Argument validation (yes/no decisions, blank → INVALID_ARGUMENTS) | API/Backend (`_check_args`, `_decision`) | — | Existing pattern, called from `_dispatchCommand` before any instrument contact, runs identically in simulated and real mode |
| Simulated-mode behavior (sleep-and-succeed, test hook) | API/Backend (`FastServer`/`base_server.ToolServer`) | — | `base_server.py`'s shared simulated-dispatch branch; the test hook is adapter-only, no instrument or network involved |
| Safety invariants (AST-checked no-auto-command rule) | Build/CI tooling (test suite, not runtime) | — | `TestAdapterInvariant` statically inspects `server.py`'s source text; it is a development-time control, not a request-path component |

## Standard Stack

**No new libraries are required for this phase.** Every piece needed — `grpcio`/`grpcio-tools`
1.70.0, `google.protobuf.struct_pb2.Struct`, `threading.Lock`, `typing.Protocol` — is already pinned
and already used in this exact codebase for the identical pattern (`meta_data` already uses
`Struct`; `_motion_lock` already uses `threading.Lock`). `typing.Protocol` is stdlib (Python 3.10,
already the pinned interpreter) and needs no install; it is simply unused elsewhere in this repo
today (verified via grep — zero existing `Protocol`/`runtime_checkable` usage), so the duck-typed
recorder interface (D-13) will be the first.

**What NOT to add:** no new pip package; no `fast_mcp.mcp` import (banned by the existing invariant);
no gRPC deadline/timeout on the control path (not even hinted at by the design for this phase — that
concern belongs to galago-core's `toolControl` caller, out of scope here).

**Installation:** none — this phase touches only files already in the repo and the two already-vendored
proto imports (`google/protobuf/struct.proto`, already imported by `tool_base.proto`).

**Version verification performed this session:**
```
$ source ~/data/nikko/.venvs/galago-py310/bin/activate && pip show fast-mcp
Version: 0.1.0 (installed from git+...@76f8c3fee41b0a2df3519aa74b022152df673824)
```
`[VERIFIED: ~/data/nikko/.venvs/galago-py310 pip show, this session]` — matches
`tools/fast/requirements.txt`'s pin exactly, and matches `TestRequirementsPin`'s regex assertion in
`fast_test.py:1218-1233`.

## Package Legitimacy Audit

**Not applicable.** This phase adds zero new third-party packages to `requirements.txt` or
`tools/fast/requirements.txt`. The only "new" imports are stdlib (`typing.Protocol`, already-imported
`threading`) and already-vendored proto (`google.protobuf.struct_pb2`, already imported by this file).
No package-legitimacy gate is required.

## Architecture Patterns

### System Architecture Diagram

```
galago-core (out of scope this phase)
        │ gRPC ExecuteCommand(Command{fast: Command{pause|resume|abort|transfer|...}})
        ▼
┌───────────────────────────────────────────────────────────────────────┐
│ tools/base_server.py :: ToolServer (SHARED across every tool type)    │
│                                                                         │
│   ExecuteCommand(request, context)                                    │
│     └─ parseCommand(request)                                          │
│          └─ isReady() ── False if self.status != READY ──► NOT_READY  │
│     └─ setStatus(BUSY) ── dispatch ── finally: setStatus(READY)       │
│                                                                         │
│   This is the gate ADP-02 requires bypassing for control commands.    │
│   NOT edited by this phase (project invariant).                       │
└───────────────────────────────┬─────────────────────────────────────┘
                                 │ overridden by subclass MRO
                                 ▼
┌───────────────────────────────────────────────────────────────────────┐
│ tools/fast/server.py :: FastServer(ToolServer)                        │
│                                                                         │
│  NEW: ExecuteCommand(request, context) override                       │
│    if request.WhichOneof("tool_command")=="fast" and                  │
│       fast.WhichOneof("command") in CONTROL_COMMANDS:                 │
│         → self._dispatchCommand(command) directly, no isReady/setStatus│
│    else:                                                               │
│         → super().ExecuteCommand(request, context)  (unchanged path)  │
│                                                                         │
│  _dispatchCommand(command)  [already overridden, D-15 existing]       │
│    └─ _check_args(command) → INVALID_ARGUMENTS early, else super()    │
│                                                                         │
│  Transfer/RunProtocol/ScanTips/EjectTray — still take _motion_lock    │
│  Pause/Abort — NEVER take _motion_lock (D-06)                         │
│  Resume — non-blocking acquire decides crash-recovery vs in-flight(D-07)│
│                                                                         │
│  NEW: _record_pause(info) / pause-clear-on-running, under its own     │
│       small threading.Lock (never _motion_lock) — feeds run_state     │
│                                                                         │
│  GetStatus(*args)  [already dual-dispatched by arity, D-10 extends it]│
│    2-arg (health RPC) → super().GetStatus() then fill reply.run_state │
│    1-arg (intent cmd) → unchanged, self._get_status(params)           │
└───────────────────────────────┬─────────────────────────────────────┘
                                 │ httpx REST (or MagicMock(spec=FastService)
                                 │  in every test this phase adds)
                                 ▼
┌───────────────────────────────────────────────────────────────────────┐
│ fast_mcp.service.FastService (pinned core 76f8c3f, UNCHANGED)        │
│   pause(hard=False) / resume(is_tip_broken=...) / abort(return_liquid=…)│
│   each gated by _require_state({...}) — the adapter never duplicates  │
│   this gate (ADP-09)                                                  │
└───────────────────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

No new files. All changes land in the three files CONTEXT.md names:

```
interfaces/tools/grpc_interfaces/
├── fast.proto            # + message Pause {}, + Pause pause = 10 in Command oneof
└── tool_base.proto       # + optional google.protobuf.Struct run_state = 4 on StatusReply

tools/fast/
└── server.py             # + CONTROL_COMMANDS, + ExecuteCommand override, + Pause(),
                           #   modified Abort()/Resume(), + recorder, + run_state builder,
                           #   + simulate_pause() test hook, + EstimatePause

tools/tests/
└── fast_test.py          # + real-mode concurrency test(s), extended TestAdapterInvariant,
                           #   + TestOneToOneSurface coverage for Pause (automatic, via the
                           #   existing parametrized tests once COMMAND_TO_SERVICE_METHOD updates),
                           #   + run_state / recorder / simulate_pause tests
```

### Pattern 1: Dual-purpose method override via arity/oneof discrimination (ALREADY ESTABLISHED)

**What:** `FastServer.GetStatus(*args)` already distinguishes the gRPC health RPC (`(request,
context)`, 2 args) from the adapter's own intent command (`(params,)`, 1 arg) by counting
positional arguments, because both bind to the literal attribute name `GetStatus`
(`server.py:450-468`, docstring explains the collision in detail). The new `ExecuteCommand` override
follows the identical idiom, discriminating by oneof contents instead of arity, because
`ExecuteCommand`'s signature is always `(request, context)` — the discriminator here is
`request.WhichOneof("tool_command")` plus the inner `WhichOneof("command")`.

**When to use:** Any time a subclass must special-case a subset of calls to a method the base class
(`ToolServer`, shared vendor code) also implements, without editing the base class.

**Example (existing code, read this session, `server.py:450-468`):**
```python
# Source: tools/fast/server.py:450-468 (existing, unmodified)
def GetStatus(self, *args: object) -> object:  # type: ignore[override]
    if len(args) == 2:
        return super().GetStatus(*args)  # type: ignore[arg-type]
    (params,) = args
    return self._get_status(params)  # type: ignore[arg-type]
```

### Pattern 2: `ExecuteCommand` override sketch (NEW this phase — illustrative, not verbatim)

Grounded in `base_server.py:223-256` (read in full) and D-01/D-02's exact wording. This is a design
sketch for the planner to hand to the executor, not verified/tested code:

```python
# Illustrative sketch -- grounded in base_server.py:223-256 and D-01/D-02, NOT yet written or tested.
CONTROL_COMMANDS = frozenset({"pause", "resume", "abort"})  # fast.Command oneof field names

def ExecuteCommand(self, request, context):
    if request.WhichOneof("tool_command") == "fast":
        fast_command = request.fast
        field_name = fast_command.WhichOneof("command")
        if field_name in CONTROL_COMMANDS:
            command = getattr(fast_command, field_name)
            try:
                logging.info("Running command %s", command.__class__.__name__)
                response = self._dispatchCommand(command)
                self.last_error = response.error_message
                return response
            except Exception as e:
                self.last_error = str(e)
                return tool_base_pb2.ExecuteCommandReply(
                    response=tool_base_pb2.DRIVER_ERROR, error_message=str(e))
    return super().ExecuteCommand(request, context)
```

Note: `field_name` from `WhichOneof` is the lowercase oneof field name (`"pause"`), matching
`CONTROL_COMMANDS`'s members; the dispatched `command`'s Python class name is `"Pause"`
(PascalCase) — this is the same naming split `_dispatchCommand`/`COMMAND_TO_SERVICE_METHOD` already
rely on (`method_name = command.__class__.__name__` in `base_server.py:129`).

### Pattern 3: Resume's non-blocking-acquire branch (NEW this phase — illustrative, not verbatim)

Grounded in the existing `Resume` method (`server.py:543-578`, read in full) and D-07's exact wording.
The critical correctness point: **never call `_motion_lock.release()` on the branch that never
acquired it** — this is a different control-flow shape than every other motion-lock user in this
file, which all use `if not acquire(...): return NOT_READY` (a single early-return guard, not a
two-branch split):

```python
# Illustrative sketch -- grounded in server.py:543-578 and D-07, NOT yet written or tested.
def Resume(self, params):
    is_tip_broken = _decision(params, "is_tip_broken")
    if is_tip_broken is None:
        return _reply(INVALID_ARGUMENTS, message="is_tip_broken must be 'yes' or 'no'")
    service = self.service
    if service is None:
        return _reply(NOT_READY, message=_NOT_CONNECTED_MESSAGE)
    if self._motion_lock.acquire(blocking=False):
        # Crash-recovery path: no motion command in flight. Unchanged behavior.
        try:
            try:
                accepted = service.resume(is_tip_broken=is_tip_broken)
                if isinstance(accepted, Refused) or accepted.get("errorCode") != 0:
                    return _recovery_reply("resume", accepted)
                result = service.wait(
                    RunHandle(plates=None, stale_done=False),
                    on_progress=self._log_progress, timeout_s=self._timeout(None))
            except (InstrumentHTTPError, httpx.HTTPError) as exc:
                return _transport_error_reply(exc)
            return _result_reply(result)
        finally:
            self._motion_lock.release()
    # In-flight path: a motion command holds the lock. No wait, no lock interaction.
    try:
        accepted = service.resume(is_tip_broken=is_tip_broken)
    except (InstrumentHTTPError, httpx.HTTPError) as exc:
        return _transport_error_reply(exc)
    return _recovery_reply("resume", accepted)
```

### Pattern 4: `optional google.protobuf.Struct` presence and `None`-safe `.update()` (VERIFIED this session)

**What:** proto3 `optional` message fields report `HasField(...) == False` until the submessage is
actually mutated. `Struct.update(dict)` safely converts a Python `None` value into protobuf's
`null_value: NULL_VALUE` wire representation — no manual null-handling code is needed.

**Verified live, this session**, against the regenerated `tool_base_pb2` module (with the `run_state`
field temporarily added, then reverted — see Common Pitfalls below for the full transcript):
```python
>>> r = tool_base_pb2.StatusReply()
>>> r.HasField('run_state')
False
>>> r.run_state.update({'state': 'running', 'percent': None, 'pause': None})
>>> r.HasField('run_state')
True
>>> r
run_state {
  fields { key: "state" value { string_value: "running" } }
  fields { key: "percent" value { null_value: NULL_VALUE } }
  fields { key: "pause" value { null_value: NULL_VALUE } }
}
```
`[VERIFIED: live Python REPL against this repo's regenerated tool_base_pb2, this session]`

**Implication for "service not configured: run_state unset" (D-12):** simply never touch
`reply.run_state` on that path — do not call `.run_state.update(...)` or `.run_state.CopyFrom(...)`
at all. This also explains, with zero code change needed, why "other tool types leave it unset"
(ADP-05) is automatically true: `base_server.ToolServer.GetStatus` (`base_server.py:70-78`) never
references `run_state`.

### Pattern 5: AST-invariant scoped-attribute extension (ESTABLISHED pattern, NEW entries)

**What:** `TestAdapterInvariant` (`fast_test.py:1140-1215`, read in full) walks the AST of
`server.py` once and enforces, per attribute name, that every `ast.Attribute` node with that `.attr`
appears only inside an allowed function's subtree (by `id()` identity of the AST node, computed once
via `ast.walk(recovery_defs[owner])`).

**Verified this session — the critical gotcha:**
```python
# fast_test.py:1183-1190 (read this session, verbatim)
banned_attrs = {
    "pause", "verify_deck_layout", "active_tray",
    "plate_definitions", "dispense_report", "start_run",
}
# Dual-frontend section 11 #1 (amended): abort/resume/wait exist only
# inside the operator's own Abort/Resume commands, so the adapter can
# never abort or resume on its own initiative.
scoped_attrs = {"abort": "Abort", "resume": "Resume", "wait": "Resume"}
```
`"pause"` is in `banned_attrs` — **fully forbidden anywhere in the file, including inside a method
named `Pause`**. D-15 requires `.pause` scoped to `Pause` only. The required change is therefore
**two-part, in the same commit that adds the `Pause` method**:
1. Remove `"pause"` from `banned_attrs`.
2. Add `"pause": "Pause"` to `scoped_attrs`.

Skipping step 1 means `TestAdapterInvariant` fails the instant `Pause()` is written (even if step 2
is done correctly), because the banned-list check (`fast_test.py:1200-1202`) runs unconditionally for
every `ast.Attribute` node, independent of the scoped-list check.

### Pattern 6: Composing the real-mode (not simulated) concurrency test for `ExecuteCommand` (NEW — composed from 3 existing fragments)

No existing test combines all three ingredients ADP-08 needs. The planner should compose:

1. **Real in-process gRPC server + stub**, exactly as `TestSimulatedTransferOverGrpc.setUp`
   (`fast_test.py:167-200`, read in full) builds: `grpc.server(...)`,
   `add_ToolDriverServicer_to_server(self.fs, self._server)`, `ToolDriverStub(channel)`.
2. **A mocked `FastService`** injected directly onto the server instance, exactly as
   `_MockedFastServerTestCase.setUp` (`fast_test.py:312-317`) does: `self.server.service =
   MagicMock(spec=FastService)`. (`TestSimulatedTransferOverGrpc` instead patches `open_service` and
   calls the real `Configure` RPC — not needed here since real mode with a pre-injected mock skips
   `Configure` entirely, matching `_MockedFastServerTestCase`'s own setUp pattern.)
3. **The blocked-thread technique** from `TestMotionSerialization.test_second_motion_command_refused_while_first_in_flight`
   (`fast_test.py:546-604`, read in full): a `threading.Event`-gated `side_effect` on
   `service.run_transfer`, a background thread calling `Transfer` directly, then the main thread
   driving the control commands.

The one new wrinkle: steps 1+2 together mean `self.server.status` must be set to `READY` **and**
`self.server.simulated` must be `False` (the default from `ToolServer.__init__`, so no explicit set
is even needed) before the gRPC server is driven through its stub — not before calling `Transfer`
directly in Python as `TestMotionSerialization` does, but through `self.stub.ExecuteCommand(...)`,
so that `base_server.ExecuteCommand`'s real gate (`parseCommand`→`isReady`→`setStatus(BUSY)`) is
actually exercised by the blocking `Transfer` call, proving the override bypasses it. Driving
`Transfer` itself through the stub too (not a direct Python call) is what makes this a genuine
`base_server.py` gate test rather than a repeat of `TestMotionSerialization`'s already-covered
in-process lock test.

### Anti-Patterns to Avoid

- **Reusing the existing `MOTION_COMMANDS` acquire-or-busy boilerplate for the Resume split:** D-07's
  two branches (acquire-and-wait vs. no-acquire-no-wait) are not a "refused" case at all on the
  in-flight branch — there is no `NOT_READY`/busy reply anywhere in that path. Do not copy the
  `if not acquire(...): return _reply(NOT_READY, ...)` idiom used by `Transfer`/`RunProtocol`/
  `ScanTips`/`EjectTray`; it is structurally wrong for `Resume`'s new shape.
  (Pitfall 6 from `.planning/research/PITFALLS.md` — motion-lock removal scope creep — restated for
  this specific method.)
- **Leaving `MOTION_COMMANDS` as a frozenset that still lists `Abort`/`Resume`.** It is currently
  defined (`server.py:66-67`) and never referenced anywhere (verified via repo-wide grep this
  session) — D-06 requires it be replaced, not just left stale alongside a new, separately-named set.
- **A boolean "is a simulated run active" flag for D-19.** The existing test
  `test_simulated_invalid_args_rejected_while_another_simulated_command_is_in_flight`
  (`fast_test.py:236-271`, read in full) proves two simulated commands **can** be concurrently
  in-flight on two gRPC worker threads (nothing in simulated mode takes `_motion_lock` — that lock is
  only acquired inside `Transfer`/`RunProtocol`/etc.'s real-mode bodies, which the simulated branch of
  `base_server._dispatchCommand` never reaches). A plain boolean would flip back to "idle" the moment
  the *first* of two concurrent simulated long-running commands finishes, even though the second is
  still sleeping. Use a counter (increment on enter, decrement in a `finally`) under the same lock the
  recorder uses.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Struct null handling for `run_state`'s `percent`/`pause` fields | Manual `Value(null_value=...)` construction | `Struct.update({...with Python None...})` | Verified this session: `.update()` already converts `None` → `null_value: NULL_VALUE` correctly; no wrapper needed |
| "Is a run in flight" signal for Resume's branch (D-07) | A new boolean flag set/cleared by Transfer/RunProtocol | `self._motion_lock.acquire(blocking=False)` / `.locked()` | The lock already tracks exactly this, is already thread-safe, and architecture research (`ARCHITECTURE.md` "Anti-Pattern 3") already confirms this is the adapter-level signal to use (never as instrument-state truth, only as "which code path") |
| Duck-typed pause-info acceptance (D-13) | A concrete dataclass importing `fast_mcp.orchestration.PauseInfo` early | `typing.Protocol` with a `to_dict() -> dict` method | The pinned core doesn't have `PauseInfo` yet (verified via `git cat-file` against `76f8c3f`); importing it would break at runtime against the pinned core, not just violate D-13 on principle |

**Key insight:** Every "hard" piece of this phase (Struct null semantics, in-flight detection,
duck-typed core objects) already has an existing, already-verified primitive in this codebase or the
stdlib; the risk in this phase is wiring order and invariant scope, not missing tooling.

## Common Pitfalls

### Pitfall 1: `TestAdapterInvariant`'s `banned_attrs` already forbids `.pause` everywhere

**What goes wrong:** Writing `Pause()` and calling `service.pause(hard=False)` inside it, without
first moving `"pause"` out of `banned_attrs` (`fast_test.py:1184`), fails `TestAdapterInvariant`
immediately — and the failure message (`".pause at line N is outside Pause()"`) does **not** appear,
because the *banned* check runs first and unconditionally (`fast_test.py:1202`,
`self.assertNotIn(node.attr, banned_attrs, node.attr)`), before the scoped check is even reached. The
test fails with a plain "'pause' unexpectedly found in banned_attrs"-style message, which looks like
an unrelated/pre-existing invariant violation rather than a missing migration step.

**Why it happens:** `banned_attrs` currently contains `"pause"` as a legacy artifact (likely a
forward-looking ban from before this milestone existed) — it predates D-15's scoped design for this
exact attribute.

**How to avoid:** In the same commit/task that adds `message Pause {}` and `FastServer.Pause()`,
remove `"pause"` from `banned_attrs` **and** add `"pause": "Pause"` to `scoped_attrs` in
`fast_test.py:1184,1190`.

**Warning signs:** `TestAdapterInvariant` fails with a banned-attribute assertion the moment `Pause()`
is written, before the planted-violation test for `.pause` has even been added.

### Pitfall 2: `service.status()`'s key is `percentProgress`, not `percent`

**What goes wrong:** D-12's no-run-in-flight path says "a fresh `service.status()`, mapped to
`state`/`percent`". `FastService.status()` (pinned core, `service.py:129-130`, calling
`_interpret_status`) returns `{"state": ..., "percentProgress": ..., "remainingTime": ..., "done":
...}` — verified by reading `fast_mcp/orchestration.py:15-24` directly this session
(`_interpret_status` builds exactly this dict shape). `run_state`'s contract (D-11) names the key
`"percent"`. Passing the raw status dict straight into the Struct would silently produce a
`percentProgress` key where galago-core expects `percent`, with no test catching it unless the test
asserts the exact key name.

**How to avoid:** When building the no-run-in-flight branch of `run_state`, explicitly map
`status["percentProgress"]` → `run_state["percent"]`; do not pass the status dict through unchanged.

**Warning signs:** A test asserting `run_state["percent"] == N` passes only because it also
doesn't check for the *absence* of `percentProgress`, or because the test fixture happens to use a
key name that matches by accident.

### Pitfall 3: Simulated long-running commands can run concurrently without `_motion_lock`

See "Anti-Patterns to Avoid" above — restated here because it's easy to miss in isolation: the
simulated branch of `base_server._dispatchCommand` (`base_server.py:138-166`) never touches
`FastServer`'s motion-lock-guarded real handler methods at all; it sleeps and returns directly. A
start/end marker for D-19's `run_state` must be a counter, not a boolean, or two concurrent simulated
`Transfer`s will produce a flickering `run_state` that reports "idle" while one of them is still
sleeping.

### Pitfall 4: `MOTION_COMMANDS` is dead code today — don't extend it, replace it

**Verified this session:** `grep -rn "MOTION_COMMANDS" tools/` returns exactly one hit — the
definition itself (`server.py:66-67`). It is never read anywhere in `server.py` or
`fast_test.py`. D-06 says "Replace `MOTION_COMMANDS` so it no longer lists `Abort`/`Resume`" — since
nothing reads it today, this is purely documentation/clarity debt if left as-is, but leaving a
misleadingly-named, unused constant that still lists `Abort`/`Resume` as "motion commands" will
confuse the next reader into thinking it's load-bearing. Per D-06, split it into two accurately-named,
actually-referenced-or-removed constants.

### Pitfall 5: `EstimatePause` must be added explicitly, or simulated Pause sleeps 0s

`base_server._estimateDuration` (`base_server.py:258-266`) falls back to `return 0, None` via a caught
`AttributeError` if no `Estimate<CommandName>` method exists. Without an explicit `EstimatePause`
method, simulated-mode `Pause` would sleep `0` seconds (not technically wrong, but inconsistent with
every other command's named placeholder, and the standalone `EstimateDuration` RPC would report `0`
to any caller, e.g. a Gantt/ETA display). D-05 explicitly calls for this method with a small flat
value sized like `EST_READ_S` or `EST_ABORT_S`.

### Pitfall 6: The `TestMotionSerialization`/`_MockedFastServerTestCase` pattern calls `FastServer` methods *directly in Python*, not through gRPC — this does not exercise `base_server.py`'s gate

**What goes wrong:** Every existing concurrency-shaped test in this file
(`TestMotionSerialization`, `TestRecoveryCommands`) calls `self.server.Transfer(...)`,
`self.server.Abort(...)` etc. as plain Python method calls. This proves the `_motion_lock`'s own
behavior correctly, but it **never** goes through `base_server.ExecuteCommand`'s
`parseCommand`/`isReady`/`setStatus` bracket at all — those tests structurally cannot detect the
base_server concurrency gate this phase's override exists to fix. (This is exactly what
`.planning/research/ARCHITECTURE.md`'s "Flagged Mismatch" section already identifies as why "nothing
in the current suite... would have surfaced this.") ADP-08's required test must drive the blocked
`Transfer` and the concurrent control commands **through the real in-process gRPC stub**
(`self.stub.ExecuteCommand(...)`), not through direct Python calls on `self.server`, or it will pass
trivially without proving anything about the override.

## Code Examples

### Verified: proto regeneration end-to-end (this session)

```bash
# Source: this session, actually run against this repo
$ source ~/data/nikko/.venvs/galago-py310/bin/activate
$ bash bin/make proto   # with Pause (field 10) and run_state (field 4) temporarily added
# ... regenerates cleanly, no errors ...
$ python -m unittest discover -s tools/tests/ -p "*_test.py"
# Ran 70 tests: 1 expected failure —
#   TestOneToOneSurface.test_command_to_service_method_matches_oneof_message_names
#   AssertionError: Items in the second set but not the first: 'Pause'
# (proves COMMAND_TO_SERVICE_METHOD["Pause"] = "pause" is required, and nothing else broke)
```
This is the single cleanest "is my proto change safe" check available to the executor before writing
any `server.py` code: add the proto fields, regenerate, run the suite, and confirm the *only* failure
is the expected `COMMAND_TO_SERVICE_METHOD` one.

### Verified: pinned-core signatures (this session, read-only reference)

```python
# Source: ~/data/nikko/fast/fast-mcp @ 76f8c3fee41b0a2df3519aa74b022152df673824 (pinned SHA),
# fast_mcp/service.py:272-290 (git cat-file -p, read this session)
def pause(self, *, hard: bool = False) -> dict | Refused:
    guard = self._require_state({"running"}, "no running protocol to pause")
    if guard:
        return guard
    return self._session.transport.pause(hard=hard)

def resume(self, *, is_tip_broken: bool = False) -> dict | Refused:
    guard = self._require_state({"paused"}, "no paused protocol to resume")
    if guard:
        return guard
    return self._session.transport.resume(is_tip_broken=is_tip_broken)

def abort(self, *, return_liquid: bool = False) -> dict | Refused:
    guard = self._require_state({"running", "paused"}, "no running or paused protocol to abort")
    if guard:
        return guard
    return self._session.transport.abort(return_liquid=return_liquid)
```
Confirms D-05's `service.pause(hard=False)` call is a drop-in match for this phase's pinned core —
no core change needed for ADP-01.

### Verified: `PauseInfo.to_dict()` key names (current fast-mcp checkout, for D-11's naming contract)

```python
# Source: ~/data/nikko/fast/fast-mcp/fast_mcp/orchestration.py:85-87 (HEAD checkout, read this
# session — NOT the pinned 76f8c3f, since PauseInfo doesn't exist there yet; this is the naming
# CONTRACT D-11 asks the Phase 1 recorder to match, for forward compatibility with Phase 2)
def to_dict(self) -> dict:
    return {"errorCode": self.error_code, "errorName": self.error_name,
            "percent": self.percent, "eventPayload": _json_safe(self.event_payload)}
```

## State of the Art

Not applicable in the traditional sense (no external library/framework to track) — the only "state of
the art" consideration is that the pinned core (`76f8c3f`) is intentionally behind the fast-mcp HEAD
(`b4b67d8`, which already has `ResumeMarker`, `PauseInfo`, and `through_pauses`). This gap is
deliberate (D-13, confirmed Phase 2 territory) and the recorder's duck-typed `Protocol` design exists
specifically to make that gap not matter for Phase 1's own code or tests.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The "long-running commands" that set/clear the pause record and the simulated run_state marker (D-12, D-19) are exactly `Transfer` and `RunProtocol`, not `ScanTips`/`EjectTray` | Architecture Patterns, Open Questions | If `ScanTips`/`EjectTray` were meant to be included, the simulated `run_state` would under-report "running" during those commands' simulated sleeps. Design §5.2 is literally titled "Long-running commands" and discusses only `Transfer`/`RunProtocol`, making this a `[CITED: docs/specs/2026-10-12-galago-live-run-control-design.md §5.2]` claim rather than a pure guess, but the planner should confirm explicitly since D-12/D-19's prose doesn't name the two commands directly |
| A2 | D-20's test hook signature `simulate_pause(pause: dict | None)` accepts a raw dict (not a `to_dict()`-able object), while D-13's recorder is specified to accept "any object with `to_dict()`" | Open Questions | Low risk, implementation-detail only: either the hook wraps the dict in a trivial adapter before calling the recorder, or the recorder gains a second raw-dict entry point. Does not affect requirements coverage, only internal plumbing — flagged so the planner picks one explicitly rather than the executor guessing mid-implementation |

## Open Questions

1. **Does `_record_pause`'s recorder also need to accept the test hook's raw `dict` directly, or
   always via a trivial duck-typed wrapper?**
   - What we know: D-13 specifies the recorder accepts "any object with `to_dict()`" (a `Protocol`);
     D-20 specifies the test hook's parameter as `pause: dict | None`.
   - What's unclear: whether `simulate_pause` is expected to construct a tiny stub object
     (`type("_Stub", (), {"to_dict": lambda self: pause})()`) before calling the same recorder method
     real `on_pause` callbacks use, or whether the recorder should expose a second, dict-accepting
     entry point.
   - Recommendation: keep one recorder method accepting the `Protocol`-typed object (used by real
     `on_pause` wiring in Phase 2), and have `simulate_pause` build a trivial one-off object
     implementing `to_dict()` around the given dict before calling it — this keeps the recorder's
     contract singular and matches D-13's "duck-typed" framing literally for both callers.

2. **Exact value for `EstimatePause`.**
   - What we know: D-05 says "small flat value, `EST_READ_S`-sized or `EST_ABORT_S`-sized"; both
     constants already exist (`EST_READ_S = 1`, `EST_ABORT_S = 15`).
   - What's unclear: which one. A pause command is a quick instrument call (closer to `EST_READ_S`'s
     intent — a fast read/signal) but shares the "recovery command" category with Abort/Resume
     (`EST_ABORT_S`/`EST_RESUME_S = 15`).
   - Recommendation: use `EST_ABORT_S` (15s) for consistency with the other two recovery commands'
     estimates, since all three go through the same `_recovery_reply` mapping and the same
     `ExecuteCommand` override — explicitly left to planner's discretion per CONTEXT.md.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10 gate venv (`~/data/nikko/.venvs/galago-py310`) | `bin/make proto test` | ✓ (verified, used this session) | 3.10 | — |
| `fast-mcp` pinned core | `FastService` import, all real-mode tests | ✓ (verified installed, SHA matches pin) | `76f8c3f` (0.1.0) | — |
| `grpcio-tools` | `bin/make proto` | ✓ (verified, used this session) | matches `pyproject.toml`'s `grpcio-tools==1.70.0` build dep | — |
| `ruff`, `mypy` | `bin/make test` lint/type gate | ✓ (verified, both clean on `server.py` baseline) | per `pyproject.toml` | — |
| galago-core / TS tooling | TS proto regeneration | N/A in this repo (confirmed: no `package.json`, no `.ts` files, no `proto_ts` function in `bin/make` anywhere in this repo) | — | Out of scope per D-09; galago-core regenerates via its own `vendor/galago-tools` submodule, a separate repo's milestone |

**Missing dependencies with no fallback:** none — everything this phase needs is already present and
was exercised live this session.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | Python `unittest` (discovery) + `pytest` (same files, second pass) |
| Config file | None dedicated — `pyproject.toml` carries only `[tool.ruff]`/`[tool.mypy]`, no `[tool.pytest.ini_options]` or `pytest.ini`/`setup.cfg` found (verified via search this session) |
| Quick run command | `python -m unittest discover -s tools/tests/ -p "*_test.py"` (≈0.1-3s locally, verified this session) |
| Full suite / gate command | `bash bin/make proto test` (regenerates protos, then `ruff check .`, `mypy --config-file=pyproject.toml tools`, `python -m unittest discover ...`, `pytest tools/tests/ -vv`) under `~/data/nikko/.venvs/galago-py310` |

**Baseline, verified this session:** 70 tests pass; ruff and mypy both clean on `tools/fast/server.py`.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ADP-01 | Pause maps 1:1 to `service.pause(hard=False)` | unit | `python -m unittest fast_test.TestOneToOneSurface -v` (extend existing parametrized test) | ✅ extend existing |
| ADP-02 | Control commands reach the mock while a Transfer is blocked | integration (real in-process gRPC) | New test class, pattern in "Architecture Patterns" Pattern 6 | ❌ Wave 0 — new test |
| ADP-03 | Status stays BUSY through a control command | integration | Same new test as ADP-02, asserting `GetStatus` health RPC reports BUSY mid-flight | ❌ Wave 0 — same new test |
| ADP-04 | Resume returns fast when in flight, waits when not | unit | Extend `TestRecoveryCommands`-style tests with a `_motion_lock`-held fixture | ❌ Wave 0 — new tests |
| ADP-05 | `GetStatus.run_state` shape per tool type | unit | Extend `TestReadAndRecoveryCommands.test_get_status_dual_dispatch_delegates_health_rpc_to_super` | ❌ Wave 0 — new assertions |
| ADP-06 | Blank/unclear decisions → `INVALID_ARGUMENTS` everywhere, including `Pause`/the override path | unit | Extend `test_missing_or_unclear_decision_is_invalid_arguments_in_real_mode` (`fast_test.py:1087`) and `_check_args` tests | ❌ Wave 0 — extend existing |
| ADP-07 | Planted-violation AST check for `.pause`, `on_pause`, `run_state` builder | unit (static) | `python -m unittest fast_test.TestAdapterInvariant -v` (extend) | ❌ Wave 0 — extend existing |
| ADP-08 | Real-mode concurrency test (the headline requirement) | integration | New test, see Pattern 6 above | ❌ Wave 0 — new test |
| ADP-09 | Zero `service.status()` calls from control commands | unit | Extend `_MockedFastServerTestCase`-based tests asserting `service.status.assert_not_called()` for Pause/Resume/Abort | ❌ Wave 0 — new assertions |
| ADP-10 | Simulated control commands succeed; `simulate_pause` hook drives `run_state` | unit | New tests alongside `TestSimulatedTransferOverGrpc` pattern | ❌ Wave 0 — new tests |

### Sampling Rate
- **Per task commit:** `python -m unittest discover -s tools/tests/ -p "*_test.py"` (fast, ≈seconds,
  verified this session)
- **Per wave merge:** `bash bin/make proto test` (full gate: proto regen + ruff + mypy + unittest +
  pytest)
- **Phase gate:** Full gate green before `/gsd-verify-work`, run under
  `~/data/nikko/.venvs/galago-py310`

### Wave 0 Gaps
- [ ] New test class for ADP-02/ADP-03/ADP-08 (real-mode `ExecuteCommand` concurrency, through the
      gRPC stub, per Pattern 6 above) — the single highest-priority new test in this phase.
- [ ] Extended `TestAdapterInvariant` cases: `.pause` scoped to `Pause`, planted-violation tests for
      `.pause` inside the recorder/`_log_progress`/`run_state` builder.
- [ ] New tests for the `simulate_pause` hook (ADP-10) — no existing pattern to extend, this is new
      surface end-to-end.
- [ ] New tests for the recorder (`_record_pause`, clear-on-running) — new surface, feed it a stub
      object per D-13.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-------------------|
| V2 Authentication | No | This is an internal gRPC service-to-service call on a trusted network segment (unchanged by this phase; out of scope per the governing design, which assumes the existing trust boundary) |
| V3 Session Management | No | No session concept in this adapter |
| V4 Access Control | No | Access control (which operator may send a control command) is galago-core's concern, out of scope for this phase |
| V5 Input Validation | Yes | Already-established fail-closed pattern: `_decision`/`_check_args`/`_RECOVERY_DECISION_FIELD` (`server.py:84, 134-215, 208-214`) reject blank/unclear yes-no decisions as `INVALID_ARGUMENTS` on every path (ADP-06) — this phase extends the pattern to `Pause` (which has no decision field, so `_check_args` returns `[]` unchanged) and must verify the `ExecuteCommand` override still routes through `_check_args` via `_dispatchCommand`, never bypassing it |
| V6 Cryptography | No | No cryptographic operation in this phase |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Software-initiated instrument command (an auto-pause/resume/abort not triggered by an operator) | Elevation of Privilege (software acting with operator authority) | This is the entire purpose of the no-auto-abort AST invariant (`TestAdapterInvariant`, scoped attrs + planted-violation tests) — a static, mechanically-enforced control rather than a runtime check, which is the correct mitigation for "a code review might miss a one-line regression" |
| Bypassing the instrument's own state gate from the adapter (duplicating or second-guessing `_require_state`) | Tampering (adapter overrides the core's safety decision) | ADP-09: the adapter adds zero instrument-state checks of its own; verified absent from `Abort`/`Resume` today and required absent from the new `Pause`/`ExecuteCommand` override — enforced by a unit test asserting `service.status()` is called zero times from control commands |
| A control command silently defaulting an unset/blank physical decision (e.g. treating blank `return_liquid` as `"no"`) | Tampering / unsafe default | `_decision()` returns `None` (never a default `False`) for anything other than exactly `"yes"`/`"no"` (case-insensitive, trimmed) — `_check_args` turns that into `INVALID_ARGUMENTS` before any instrument contact, on every path including simulated mode (ADP-06) |

## Sources

### Primary (HIGH confidence — direct repository inspection and live tool execution, this session)
- `.planning/phases/01-adapter-control-path-run-state/01-CONTEXT.md` — locked decisions D-01..D-20
- `.planning/REQUIREMENTS.md`, `.planning/STATE.md` — ADP-01..ADP-10, project history
- `docs/specs/2026-10-12-galago-live-run-control-design.md` — governing design, §5.1-§5.5, §7, §11
- `tools/fast/server.py` (read in full, 633 lines)
- `tools/base_server.py` (read in full, 318 lines)
- `tools/tests/fast_test.py` (read in full, 1237 lines — `_MockedFastServerTestCase`,
  `TestMotionSerialization`, `TestRecoveryCommands`, `TestAdapterInvariant`, `TestOneToOneSurface`,
  `TestSimulatedTransferOverGrpc`, `TestTransferEndToEndOverGrpc`)
- `interfaces/tools/grpc_interfaces/fast.proto`, `tool_base.proto` (read in full, and live-edited +
  regenerated + reverted this session to verify proto regeneration and presence semantics)
- `tools/grpc_interfaces/tool_driver_pb2_grpc.py` (read, to verify `ExecuteCommand` binding mechanics)
- `bin/make` (read in full — `proto_py`, `proto`, `test`, `clean_proto` functions)
- `pyproject.toml` (ruff/mypy config)
- `~/data/nikko/fast/fast-mcp/fast_mcp/service.py` at pinned SHA `76f8c3f` (via `git cat-file -p`,
  this session) — `pause`/`resume`/`abort`/`wait`/`status` signatures
- `~/data/nikko/fast/fast-mcp/fast_mcp/run_control.py` at pinned SHA `76f8c3f` (via `git cat-file -p`)
  — confirms `RunOptions` has no `on_pause`/`through_pauses` at this pin
- `~/data/nikko/fast/fast-mcp/fast_mcp/orchestration.py` (current HEAD checkout, for `PauseInfo`
  naming contract only — explicitly not imported by Phase 1 code per D-13) and (pinned SHA, for
  `_interpret_status`'s actual return shape used by `service.status()` today)
- `~/data/nikko/.venvs/galago-py310` — live `pip show fast-mcp`, live `bash bin/make proto`, live
  `python -m unittest discover`, live `ruff check`, live `mypy`
- `.planning/config.json` — `workflow.nyquist_validation: true`, `workflow.security_enforcement: true`

### Secondary (MEDIUM confidence)
- `.planning/research/SUMMARY.md`, `ARCHITECTURE.md`, `PITFALLS.md` — milestone-level research,
  already-settled findings reused and cross-checked against this session's direct file reads (no
  contradictions found; the "Flagged Mismatch"/Pitfall 1 and Pitfall 4 findings are both already
  resolved by D-01/D-02's exact design, confirmed by this session's reading of the design doc)

### Tertiary (LOW confidence)
None — this phase required no web search; everything was either read from the repo/core this session
or executed live against the gate venv.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — zero new packages, everything already pinned and in use
- Architecture: HIGH — every integration point traced to file:line this session, override mechanics
  (arity/oneof discrimination, servicer binding) verified against existing working code
- Pitfalls: HIGH — the `banned_attrs`/`scoped_attrs` gotcha, the `percentProgress` key mismatch, and
  the dead-`MOTION_COMMANDS` finding are all newly-verified this session (not present in the
  milestone-level PITFALLS.md), each with exact file:line citations
- Validation architecture: HIGH — gate command actually run, baseline test count and lint/type-check
  cleanliness confirmed live

**Research date:** 2026-10-12
**Valid until:** 30 days, or immediately if `tools/fast/requirements.txt`'s pinned SHA changes
(re-pin is explicitly Phase 2 scope) or if `fast.proto`/`tool_base.proto` are touched by another
change before this phase lands
