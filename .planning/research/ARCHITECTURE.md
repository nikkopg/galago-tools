# Architecture Research — Galago Live F.A.S.T. Run Control

**Domain:** Live run control for an unattended lab-automation workcell (Galago) driving a
long-running instrument step (F.A.S.T. liquid handler) through a gRPC tool-driver adapter.
**Researched:** 2026-10-12
**Confidence:** HIGH for integration points and data flow (traced against the actual code, not the
design doc's prose); MEDIUM for the recommended fix to the base_server.py concurrency mismatch
(the mismatch itself is HIGH confidence — line-traced — the fix is a recommendation, not yet
built or tested).

This is project-specific integration-tracing research, not generic domain survey. It answers: how
does `docs/specs/2026-10-12-galago-live-run-control-design.md` map onto the real code in
`fast-mcp`, `galago-tools` (`nikkopg` fork, `tools/fast/`), and `galago-core`
(`controller/server/`, `controller/components/runs/`)?

## System Overview

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ galago-core (controller, Next.js/tRPC)                                            │
│                                                                                     │
│  components/runs/RunsComponent.tsx          components/runs/ (NEW)                │
│   - modalStateQuery (1s poll) ─────────────► ControlBar + ToolPausedModal          │
│   - existing: Pause/Message/Timer/Stop modals     (NEW: runStateQuery, 2s poll)    │
│                                                                                     │
│  server/command_queue.ts (CommandQueue)      server/routers/command_queue.ts       │
│   - _runningPromise (whole busy loop)         - toolControl (NEW tRPC mutation)    │
│   - executeCommand(cmd): awaits              - runState (NEW tRPC query)          │
│     Tool.executeCommand then commands.complete                                    │
│   - stop(): awaits _runningPromise            server/tools.ts (Tool)              │
│                                                - fetchStatus(): heartbeat, 5s,     │
│                                                  stops on 1st failure (BUG, fix    │
│                                                  needed for D2 2s poll)            │
│                                                - executeCommand(): grpc.executeCommand│
│                                                  (NEW: controlCommand() wrapper,   │
│                                                  same RPC, called directly,        │
│                                                  bypassing SqliteQueue)            │
└───────────────────────────────────┬────────────────────────┬──────────────────────┘
                                     │ gRPC ExecuteCommand     │ gRPC GetStatus
                                     │ (fast.Command.{Transfer,│ (health RPC, no
                                     │  RunProtocol,Pause,     │  isReady() gate)
                                     │  Resume,Abort})         │
                                     ▼                         ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│ galago-tools fork (nikkopg), tools/fast/server.py :: FastServer(ToolServer)        │
│                                                                                     │
│  tools/base_server.py ToolServer (SHARED, all tool types — generated/vendor code)  │
│   - ExecuteCommand(): parseCommand() → isReady() gate on self.status ──────┐       │
│     self.status = BUSY before dispatch, READY in finally (ALL commands,    │       │
│     not just motion ones)                                                  │ GATE  │
│   - GetStatus(): no isReady() gate — direct StatusReply, always answers    │       │
│   - serve(): grpc.server(ThreadPoolExecutor(max_workers=10)) — concurrency │       │
│     capacity exists, but the status gate above serializes anyway ◄─────────┘       │
│                                                                                     │
│  FastServer (adapter, this fork only)                                             │
│   - _motion_lock: threading.Lock — Transfer/RunProtocol/ScanTips/EjectTray/        │
│     (today) Abort/Resume all acquire it, blocking=False → NOT_READY if busy       │
│   - Transfer/RunProtocol: service.run_transfer/run_protocol(options=RunOptions(    │
│     through_pauses=True (NEW), on_pause=... (NEW)))                               │
│   - Pause (NEW), Resume/Abort (MODIFIED: drop _motion_lock per D5.1)              │
│   - GetStatus: dual-bound health RPC vs. Command.GetStatus intent (arity trick)   │
│     (MODIFIED: add run_state Struct, D1)                                          │
└───────────────────────────────────┬────────────────────────────────────────────────┘
                                     │ httpx REST (:5003)
                                     ▼
┌───────────────────────────────────────────────────────────────────────────────────┐
│ fast-mcp core (fast_mcp/service.py :: FastService) — single allowlist             │
│  - pause()/resume()/abort(): state-gated (_require_state), thread-safe via         │
│    ResumeMarker (holds its own lock across get_status)                            │
│  - wait()/poll_run(): through_pauses, on_pause(PauseInfo) per episode (ALREADY     │
│    SHIPPED, quick 261012-o24 / core b30b38d)                                      │
└───────────────────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | File | Responsibility | New / Modified / Unchanged |
|---|---|---|---|
| `FastService.wait`/`poll_run` | `fast-mcp/fast_mcp/service.py:221-279`, `fast_mcp/orchestration.py:186-305` | Wait-through-pauses, pause episodes, `PauseInfo`, paused time excluded from deadline | **Unchanged for v2** — already shipped (core prerequisite, §4) |
| `FastService.pause/resume/abort` | `fast_mcp/service.py:321-352` | State-gated recovery calls; thread-safe via `ResumeMarker` | **Unchanged** — the gate the design relies on already exists |
| `FastServer.Pause` | `galago-tools/tools/fast/server.py` (new method, pattern at lines 520-578) | Maps 1:1 to `FastService.pause(hard=False)` (D5: no hard-pause arg) | **New** |
| `FastServer.Resume`/`Abort` | `server.py:520-578` | Resume must stop waiting when a run is in flight (§5.1); must drop `_motion_lock.acquire()` (lines 532, 564) | **Modified** |
| `FastServer._motion_lock` | `server.py:338, 401, 423, 494, 509, 532, 564` | Serializes `Transfer`/`RunProtocol`/`ScanTips`/`EjectTray` against each other; currently also guards `Abort`/`Resume` | **Modified** — Pause/Resume/Abort must stop acquiring it |
| `FastServer.GetStatus`/`_get_status` | `server.py:450-478` | Dual-bound: gRPC health RPC vs. `Command.GetStatus` intent, discriminated by arg arity | **Modified** — add `run_state` to the `StatusReply` built in the health-RPC branch (`super().GetStatus`) |
| `ToolServer.ExecuteCommand`/`parseCommand`/`isReady` | `galago-tools/tools/base_server.py:70-78, 195-198, 200-221, 223-256` | Generic per-command-type dispatch for **every** tool type; gates on `self.status`/`isReady()`, sets `BUSY` around every dispatch | **Flagged mismatch — see below.** Not edited by this fork's convention (shared vendor code) |
| `Tool.fetchStatus` | `galago-core/controller/server/tools.ts:99-111` | 5 s heartbeat `GetStatus` poll; `catch` calls `stopHeartbeat()` on first failure | **Modified** (D2/§6.3): must retry on failure, never stop, while a controllable step runs |
| `Tool.executeCommand`/`Tool.controlCommand` | `tools.ts:333-349, 350-416` | Single gRPC `ExecuteCommand` stub already used for queued steps; design's `Tool.controlCommand` is a thin new wrapper around the **same** RPC, called directly instead of through `CommandQueue` | **New** (thin wrapper) + reuse of existing plumbing |
| `CommandQueue.executeCommand`/`_runBusyLoopWhileQueueNotEmpty` | `galago-core/controller/server/command_queue.ts:387-390, 672-1060` | Awaits `Tool.executeCommand` synchronously inside the single busy-loop promise (`_runningPromise`) | **Unchanged mechanism**, but needs a lookup for "which command/tool is currently STARTED" |
| `CommandQueue` running-step lookup | *new method, e.g.* `command_queue.ts` | `toolControl` needs to find the tool of the currently running step | **New** — no such helper exists today; `SqliteQueue` tracks per-command `status` ("STARTED" set in `startNext()`, `SqliteQueue.ts:144-145`) but nothing queries "the one STARTED row" directly |
| `commandQueue.toolControl` tRPC procedure | `galago-core/controller/server/routers/command_queue.ts` (new, alongside existing procedures at lines 7-140) | Validates `runControl` capability + decision values, calls `Tool.controlCommand` directly, `logAction`s the operator's choice | **New** |
| `commandQueue.runState` tRPC query | same router | Surfaces `run_state` from the running tool's `StatusReply`/heartbeat for the 2 s poll | **New** |
| `UIMessage`/`_isWaitingForInput`/`_messageResolve` | `command_queue.ts:25-33, 190-198, 315-337` | Queue-level "between steps" modals (`pause`,`message`,`timer`,`stop_run`,`user_form`); each blocks the busy loop until `resume()` resolves the promise | **Do not literally extend** — see Anti-Pattern below. `tool_paused` must NOT plug into this machinery |
| `ToolPausedModal`, run-page control bar | `galago-core/controller/components/runs/` (new files, next to `PauseModal.tsx`, `StopRunModal.tsx`) | Pause/Resume/Abort buttons + pause prompt, each a two-option fail-closed choice | **New** |
| `StopRunModal` / Stop button wiring | `RunsComponent.tsx:104, 204-214`; `StopRunModal.tsx` | Today: `stopQueueMutation.mutate()` (queue `stop()`) fires directly with **no confirmation** for the plain Stop button (only the `stop_run` **protocol step** shows `StopRunModal`) | **Modified** (D4): Stop during a controllable step must ask "abort (return liquid?)" or cancel before calling `stop()`/`abort()` |

## Integration Points (file:line)

| # | Integration point | File:line | Direction |
|---|---|---|---|
| 1 | Core wait-through-pauses, already shipped | `fast_mcp/run_control.py:67-139`, `fast_mcp/orchestration.py:186-305`, `fast_mcp/service.py:221-279` | fast-mcp core → adapter (consumed, not built in this milestone) |
| 2 | Adapter calls core with `through_pauses=True` | `galago-tools/tools/fast/server.py:397-417` (`Transfer`), `:419-436` (`RunProtocol`) — currently `RunOptions(timeout_s=..., on_progress=...)` with no `through_pauses`/`on_pause` | Adapter → core (needs the new kwargs added) |
| 3 | Adapter motion lock vs. control commands | `server.py:338` (`self._motion_lock = threading.Lock()`), `:401,423,494,509` (motion commands acquire), `:532,564` (Abort/Resume **currently** also acquire — must stop) | Internal to adapter |
| 4 | Base-server command gate (the mismatch) | `galago-tools/tools/base_server.py:195-198` (`isReady`), `:200-221` (`parseCommand`), `:223-256` (`ExecuteCommand`, sets `BUSY`/`READY`) | Shared vendor code the adapter dispatches through for **every** command including the new Pause/Resume/Abort |
| 5 | Health RPC bypasses the gate | `base_server.py:70-78` (`ToolServer.GetStatus`), dual-bound via `server.py:450-468` | Used by the heartbeat/run-state poll — unaffected by #4 |
| 6 | galago-core heartbeat | `galago-core/controller/server/tools.ts:85-111` (`startHeartbeat`, `fetchStatus`) | Needs the retry fix (D2/§6.3) |
| 7 | galago-core single gRPC call site for steps | `tools.ts:333-349` (static `Tool.executeCommand`), `:350-416` (instance `executeCommand`, ends with `this.grpc.executeCommand(...)` at line ~535) | Reused unmodified for the new direct control path |
| 8 | Queue's single running promise | `galago-core/controller/server/command_queue.ts:37` (`_runningPromise`), `:611-637` (`_start`), `:640-670` (`stop`, awaits `_runningPromise`), `:672-1060` (busy loop), `:387-390` (`executeCommand`) | `toolControl` must never touch this; `stop()`'s await-blocking-until-step-ends behavior is exactly what D4's confirmation must warn about |
| 9 | Per-command status tracking | `galago-core/controller/server/utils/SqliteQueue.ts:112-150` (`startNext` sets `status: "STARTED"`) | No existing accessor returns "the STARTED row"; needed for `toolControl`'s "the tool of the currently running step" |
| 10 | Existing modal plumbing (do not reuse for `tool_paused`) | `command_queue.ts:25-33` (`UIMessage`), `:315-337` (`_ensureModalReady`), `:527-567` (`resume`, resolves `_messageResolve`) | Queue-level, resolves-the-step semantics — incompatible with "stays open" requirement |
| 11 | Stop button, no confirmation today | `components/runs/RunsComponent.tsx:104` (`stopQueueMutation`), `:204-214` (`handleRunStop`) | Needs D4's confirmation gate inserted before the mutation fires |
| 12 | Proto surfaces to extend | `galago-tools/interfaces/tools/grpc_interfaces/fast.proto:5-16` (new `Pause` message in the `Command` oneof), `.../tool_base.proto` (`StatusReply`, need to locate `run_state` field slot) | D1/D6 |

## Flagged Mismatch: the design's concurrency assumption vs. the real gate

**§5.1 of the governing design states:** *"With a run in flight, they [control commands] reach the
instrument concurrently. The tool server already handles each command on its own worker thread
(`serve()`, 10 workers), so this needs no `base_server` change."*

**This is contradicted by the code.** `tools/base_server.py`'s `ToolServer.ExecuteCommand` (lines
223-256) calls `parseCommand` (lines 200-221) first, which calls `isReady()` (lines 195-198):

```python
def isReady(self) -> bool:
    if self.simulated:
        return True
    return self.status == tool_base_pb2.READY
```

`ExecuteCommand` sets `self.status = BUSY` before dispatch and back to `READY` in a `finally`
(lines 239-240, 253-254). This is **one shared instance field on the `ToolServer`**, not a
per-command or per-motion-type gate. The 10-worker `ThreadPoolExecutor` (line 297) gives each
concurrent gRPC call its own worker thread, but every one of those threads calls the *same*
`parseCommand`/`isReady()` check against the *same* `self.status`. While `Transfer`'s
`ExecuteCommand` call has set `status=BUSY` (for the whole duration of the run, including every
paused episode, because `_dispatchCommand`'s synchronous call to `FastServer.Transfer` doesn't
return until `service.run_transfer` returns), a concurrently arriving `ExecuteCommand` for `Pause`,
`Resume`, or `Abort` will have `parseCommand` return `(None, NOT_READY, None)` **before it ever
reaches `FastServer`'s dispatch, the motion lock, or `FastService`'s own state gate.** The operator
would see every live control command refused with "not ready" for the entire duration of the run —
exactly the opposite of the goal.

**Why the existing test suite hasn't caught this:** `isReady()` returns `True` unconditionally
when `self.simulated` is set (line 196), and the one existing concurrency test exercising this path
(`galago-tools/tools/tests/fast_test.py:236-271`,
`test_simulated_invalid_args_rejected_while_another_simulated_command_is_in_flight`) runs in
simulated mode, where the gate never triggers. The recovery-command tests
(`fast_test.py:961-989`, `TestRecoveryCommands`) call `self.server.Abort(...)` and
`self.server.Resume(...)` directly as Python method calls, **not** through the in-process gRPC
`ExecuteCommand` stub, so they never exercise `base_server.py`'s gate either. Nothing in the
current suite, and nothing in the 2026-10-09/2026-10-12 supervised runs (which never had a
control command in flight concurrently with a motion command), would have surfaced this.

**Recommended resolution (not yet built, MEDIUM confidence):** Override `ExecuteCommand` itself in
`FastServer` (not just `_dispatchCommand`, which `FastServer` already overrides at lines 340-356),
following the same pattern as the existing dual-purpose `GetStatus` override (lines 450-468).
Peek the oneof command name from the request; if it is `Pause`/`Resume`/`Abort`, bypass
`self.isReady()`/`self.status` entirely and call `self._dispatchCommand(command)` directly without
touching `self.status`; for every other command, delegate to `super().ExecuteCommand(request,
context)` unchanged. This keeps `tools/base_server.py` — shared across every other tool type in the
fork — untouched, matching the adapter's existing convention. The AST/invariant tests (§5.4) should
gain a case: a control command sent via the real in-process gRPC stub while a motion command's
`ExecuteCommand` holds the base class `status=BUSY` must still succeed. This is also the cleanest
place to confirm the unused `MOTION_COMMANDS` constant (`server.py:66-67`, currently defined but
never referenced) — it may be exactly the anchor this override needs ("is this command name exempt
from the BUSY gate"), repurposed rather than left dead.

## Data Flow

### 1. Operator Pause/Resume/Abort while a Transfer `ExecuteCommand` is in flight

```
Run page control bar → trpc.commandQueue.toolControl.mutate({action: "pause"/"resume"/"abort", params})
  → router: look up the STARTED command's {toolId, toolType} (NEW helper over SqliteQueue)
  → validate params against the tool type's `runControl` capability (NEW capability table)
  → Tool.controlCommand(toolId, {toolType: fast, command: "pause"/"resume"/"abort", params})
      (NEW wrapper; internally identical to the existing `tool.executeCommand()` at tools.ts:350+,
       ending in `this.grpc.executeCommand(this._payloadForCommand(command))`)
  → gRPC ExecuteCommand RPC, a NEW worker thread from the 10-worker pool (base_server.py:297)
  → FastServer.ExecuteCommand (NEW override, see "Flagged Mismatch") bypasses the BUSY gate for
    this command name, calls self._dispatchCommand(command)
  → FastServer.Pause/Resume/Abort (new/modified, server.py ~520-578) — no `_motion_lock.acquire()`
    (D5.1, lock removed from these three)
  → FastService.pause/resume/abort (service.py:321-352) — state-gated, thread-safe via
    ResumeMarker; runs concurrently with the in-flight Transfer's `poll_run` loop
       (fast_mcp/orchestration.py:186-305), which is reading status through the SAME
       ResumeMarker-guarded `_read_status` (service.py:122-127) from its own thread
  → instrument REST call (pause/resume/abort) or Refused with no instrument call
  → ExecuteCommandReply (SUCCESS / ERROR_FROM_TOOL / NOT_READY) → tRPC response
  → UI: Resume success closes ToolPausedModal implicitly (next run_state poll shows "running");
    Abort success means the in-flight Transfer's wait (still polling) will itself observe
    `state="aborted"` and the ORIGINAL Transfer ExecuteCommand (the queue step) returns its own
    reply — Aborted → "run aborted by operator at <p>%" (§5.2) — separately from toolControl's reply
```

Two independent gRPC calls are in flight on two different worker threads for the whole exchange:
the original `Transfer`/`RunProtocol` call (still blocked in `poll_run`, inside `FastServer.Transfer`
which still holds `_motion_lock`), and the `toolControl` call (no lock, now bypassing the BUSY gate
per the fix above). `FastService`'s internal state is the only serialization point, and it already
handles this (service.py:99-111 docstring).

### 2. Instrument-initiated pause → `run_state` → polling → `tool_paused` modal → operator decision

```
Instrument pauses (e.g. -645 WrongPlateType) while FastServer.Transfer's poll_run loop is running
  → poll_run (orchestration.py:258-305) observes `currentState == "paused"`, live (not stale from a
    resume marker); `in_episode` was False → fires on_pause(PauseInfo) ONCE (line 281-285)
  → adapter's on_pause callback (NEW, §5.2) records {PauseInfo, timestamp} in FastServer instance
    state (not yet in the code — a new field, analogous to `self._motion_lock`)
  → meanwhile, galago-core's heartbeat (tools.ts:99-111, MODIFIED to retry, D2 2s cadence while a
    controllable step runs) calls GetStatus — bypasses the BUSY gate entirely (it's a different
    RPC, bound directly by generated code, base_server.py:70-78)
  → FastServer.GetStatus / _get_status (server.py:450-478, MODIFIED) builds `run_state` from
    `self.service.status()` PLUS the adapter's own recorded on_pause state (the service's
    synchronous `status()` call alone cannot see "why" it's paused — PauseInfo only exists inside
    the wait loop's closure; the adapter must surface its own recorded on_pause as the run_state
    source of truth while a wait is in flight, per design §5.3 "taken from the in-flight wait's
    latest observation")
  → StatusReply.run_state Struct: {state: "paused", percent, pause: {errorCode, errorName, percent,
    eventPayload}}
  → galago-core NEW runState tRPC query (poll 1-2s while a controllable step is STARTED) surfaces
    this to the run page
  → frontend detects a NEW pause episode (run_state.pause transitions from null→non-null) → opens
    ToolPausedModal (NEW component) — this does NOT touch CommandQueue._isWaitingForInput/
    UIMessage/_messageResolve (see Anti-Pattern below); the step is still open inside
    FastServer.Transfer's still-executing ExecuteCommand call
  → operator picks Resume(is_tip_broken) or Abort(return_liquid) in the modal
  → same path as Flow 1 (toolControl mutation → Tool.controlCommand → gRPC ExecuteCommand →
    FastServer override → FastService.resume/abort)
  → on resume: poll_run's resume_marker (service.py `_resume_marker`, ResumeMarker class) swallows
    the next stale `paused` reading (S2); the ORIGINAL Transfer's poll_run loop continues, sees
    `running` again, in_episode flips False → modal closes on the next run_state poll
  → on abort: poll_run's next poll observes `aborted`, terminal → Transfer's ExecuteCommand reply
    is Aborted; step ends FAILED per §6.6
```

### 3. Stop during a controllable step

```
Operator clicks Stop on the run page (RunsComponent.tsx:204-214 today: stopQueueMutation.mutate()
  fires immediately, no confirmation)
  → MODIFIED (D4): before firing, check if the STARTED command's tool declares `runControl`; if so,
    open a NEW confirmation ("Abort the instrument run? return liquid yes/no" or Cancel) instead of
    calling stop() directly
  → Cancel: no-op, nothing sent
  → Confirm "abort": toolControl({action: "abort", params: {return_liquid}}) — same path as Flow 1
    — THEN commandQueue.stop() — CommandQueue.stop() (command_queue.ts:640-670) sets state OFFLINE
    and `await this._runningPromise`, i.e. it still blocks until the in-flight step's
    `executeCommand` (awaiting Tool.executeCommand → the Transfer gRPC call) returns. Aborting the
    instrument first is what makes that wait short — without the abort, Stop would still hang
    exactly as the Problem section describes (§1: "Stop waits for the in-flight step to finish")
  → Transfer's poll_run observes `aborted` → FastServer.Transfer returns Aborted → queue step fails
    with "aborted by operator" → busy loop's catch block (command_queue.ts:1023-1053) marks the
    command failed, sets state FAILED → stop()'s already-pending `_runningPromise` resolves
```

Important: **D4's Stop confirmation does not replace `CommandQueue.stop()`'s existing await
semantics** — it runs the abort *before* calling `stop()` so the await is no longer indefinite.
`stop()` itself needs no code change; only the UI layer in front of the `stopQueueMutation` call
needs the new confirmation + ordering.

### 4. Crash recovery (no run in flight)

```
Operator on the tool page (not the run page — D3 removed abort/resume from the protocol step
  editor, but the tool page keeps them for this path) sends Abort or Resume
  → same ExecuteCommand path, but no Transfer/RunProtocol holds _motion_lock
  → Resume (crash recovery branch, UNCHANGED per §5.1's second bullet): acquires _motion_lock,
    calls service.resume(...), then service.wait(RunHandle(...), through_pauses=False (default))
    — server.py:543-578, unchanged behavior
  → the adapter needs a signal to distinguish "run in flight" (skip the wait) from "no run in
    flight" (wait as before) — NOT present in the code today. Candidate signal:
    `self._motion_lock.locked()` (threading.Lock exposes `.locked()`) checked at the top of the
    NEW Resume handler, since Transfer/RunProtocol still hold that lock for their whole duration
    even though Resume itself no longer takes it
```

## Concurrency & State Ownership

| Layer | Owns | Mechanism | Notes |
|---|---|---|---|
| `FastService` | The only state gate (`running`/`paused`/`idle` transitions for pause/resume/abort) | `_require_state` (service.py:159-164) + `ResumeMarker` (run_control.py:89-139, its own internal lock held only across `get_status`) | Already thread-safe by design (service.py:99-111 docstring); nothing in this milestone changes it |
| `FastServer._motion_lock` | Serializes **motion** commands against each other (`Transfer`/`RunProtocol`/`ScanTips`/`EjectTray`) | `threading.Lock`, non-blocking `acquire` | Must stop guarding `Pause`/`Resume`/`Abort` (D5.1); `Resume`'s crash-recovery branch keeps acquiring it |
| `ToolServer.status` (base_server.py) | A **server-wide** busy/ready flag covering every command, every tool type | Plain instance attribute, set in `ExecuteCommand`'s try/finally | **Not** designed as a per-command-type gate; this is the flagged mismatch — it currently blocks concurrent control commands regardless of the motion lock |
| gRPC server | Thread pool capacity | `ThreadPoolExecutor(max_workers=10)` (base_server.py:297) | Capacity is not the bottleneck; the `status` gate is |
| `CommandQueue._runningPromise` | The queue's own single-flight execution state | One promise per busy-loop iteration; `stop()` awaits it | `toolControl` must never await or touch this — it is a parallel, out-of-band path (§6.2, confirmed by tracing: nothing in `toolControl`'s design touches `SqliteQueue` or `_runningPromise`) |
| `CommandQueue._isWaitingForInput`/`UIMessage` | Queue-level "between steps" modal gate | `_messageResolve` promise resolved by `resume()` | Wrong tool for `tool_paused` — see Anti-Pattern |

## Anti-Patterns to Avoid

### Anti-Pattern 1: Routing `tool_paused` through `CommandQueue`'s existing modal plumbing

**What it would look like:** Adding `"tool_paused"` to the `UIMessage.type` union
(`command_queue.ts:26`) and driving it through `_isWaitingForInput`/`_currentMessage`/
`_messageResolve`, reusing `modalStateQuery` on the frontend.

**Why it's wrong:** Every existing `UIMessage` type exists specifically to **block the busy
loop** — `pause()`, `showMessage()`, `startTimer()`, `stopRunRequest()` all return a `Promise` that
only resolves when `resume()` fires `_messageResolve()`, and the busy loop `await`s that promise
before continuing to the next command (command_queue.ts:748-935). A F.A.S.T. pause happens
**while the step's own `ExecuteCommand` is still in flight**, inside `Tool.executeCommand`, which
the busy loop is *already* awaiting (`CommandQueue.executeCommand`, line 387-390). There is no
second promise to resolve — the step hasn't returned yet. Plugging `tool_paused` into this
machinery would either do nothing (because nothing calls `resume()` to resolve the already-absent
promise) or, worse, interact badly with `_ensureModalReady()`'s side effects (clearing any other
active queue modal) if a true queue-level pause happens to coincide with a tool pause.

**Instead:** Surface `run_state.pause` through its own new read path — the `runState` tRPC query —
entirely separate from `modalState`. The frontend opens `ToolPausedModal` based on `runState`
transitions, independent of `isWaitingForInput`.

### Anti-Pattern 2: Giving the control-command gRPC calls a deadline/timeout

**What it would look like:** Adding `options: { deadline: ... }` to the `toolControl` → `grpc.executeCommand` call, to avoid a control command hanging forever if the tool server is unresponsive.

**Why it's wrong:** The design explicitly relies on **no gRPC deadline** so a step (and, by
extension, a control command sent while a pause prompt is open) can stay open through an arbitrarily
long human decision (§6.2). `promisifyGrpcCall` (`galago-core/controller/server/utils/
promisifyGrpcCall.ts:19-32`) already passes no default `CallOptions`, confirmed by inspection — do
not introduce one for control commands specifically; a hung tool server should surface as a failed
heartbeat (Flow 2's "run state unknown"), not a timed-out control action that silently never
reached the instrument.

### Anti-Pattern 3: Treating `FastServer._motion_lock.locked()` as authoritative state

It is a reasonable signal for "is a run in flight" (Flow 4), but it is **not** the system of
record — `FastService`'s own `currentState` (via `status()`) is. Use the lock only to pick which
*adapter-level* code path to take (wait vs. don't-wait for Resume), never to decide whether to
send a command to the instrument; that gate belongs entirely to `FastService._require_state`.

## Failure Modes (cross-checked against design §8)

| Event | Design's claim | Code confirms / corrects |
|---|---|---|
| galago-web restarts mid-step | gRPC call dropped; adapter thread keeps waiting, holds motion lock; tool page's control commands still work "because they don't take the motion lock" | **Confirmed for the motion lock** — but tool-page control commands going through `ExecuteCommand` still hit the base_server `status=BUSY` gate (the flagged mismatch) for as long as the orphaned `Transfer` call's `ExecuteCommand` frame is still on the stack. If galago-tools itself didn't restart, `self.status` stays `BUSY` until that orphaned wait eventually terminates (done/aborted/timeout) — tool-page recovery is **not** actually available during this window until the fix above is applied. |
| galago-tools restarts mid-step | Instrument continues unsupervised; after reconnecting, use tool page Resume/Abort | Confirmed — a fresh process means `self.status` resets to `NOT_CONFIGURED`→`READY` after `Configure`, so the gate issue above doesn't apply post-restart |
| Run-state poll fails | Show "run state unknown", keep retrying, don't change the step | Requires the `fetchStatus` fix (`tools.ts:105-110`, currently calls `stopHeartbeat()` on any error) — confirmed this is a real bug in the current code, not just a theoretical risk |
| Two operators act at once | Core gate `Refused`s the second; both logged | Confirmed — `FastService._require_state` is check-then-act but instrument-backstopped (service.py:159-164 docstring), consistent with the design's acceptance of this pre-existing TOCTOU |

## Suggested Build Order

Refines the design's §10 with file-level sequencing and one inserted validation step the design's
order doesn't surface.

1. **Confirm the fast-mcp core SHA to pin** (already in progress per PROJECT.md; not reproduced
   here).
2. **In parallel, against a mocked `FastService`** (`MagicMock(spec=FastService)`, same pattern as
   `fast_test.py:275-299` `TestTransferMapping`):
   - **galago-core, independent of the adapter:**
     a. Add the `runControl` capability declaration (a plain object/table, not yet present
        anywhere — new).
     b. Add the `toolControl` tRPC procedure and the "find the STARTED command's tool" helper
        (new; `SqliteQueue` already has the `status` column, just needs a query/filter).
     c. Add the `runState` tRPC query (can return a hand-built fixture Struct at this stage, since
        there's no real `run_state` field yet).
     d. Fix `Tool.fetchStatus`'s heartbeat retry (`tools.ts:105-110`) — this is a pure bug fix, no
        dependency on anything else; do it first, it's the easiest win and unblocks D2 testing.
     e. Build `ControlBar` + `ToolPausedModal` against the mocked `runState`/`toolControl` shapes.
     f. Remove `abort`/`resume` from the protocol step editor (D3) — purely additive-subtractive,
        no dependency.
     g. Build the Stop confirmation (D4) in front of the existing `stopQueueMutation` call
        (`RunsComponent.tsx:204-214`) — needs only the `runControl` capability check, not real
        run_state.
   - **Adapter control path, independent of wiring Transfer/RunProtocol through pauses:**
     a. Add the `Pause` message to `fast.proto`'s `Command` oneof (mirrors `Abort`/`Resume` at
        `fast.proto:60-66`).
     b. Add `FastServer.Pause`, and strip `_motion_lock.acquire()` from `Abort`/`Resume`
        (`server.py:532, 564`).
     c. **Write the real-mode (non-simulated) concurrency test now, not at live-acceptance time:**
        send a blocking `Transfer` via the in-process gRPC stub on one thread (the pattern already
        exists at `fast_test.py:236-271`, but currently only proven in simulated mode — set
        `self.server.simulated = False` / `self.server.status = BUSY` manually and confirm a
        concurrent `self.stub.ExecuteCommand(Abort(...))` call is **not** immediately refused).
        This test will fail against today's code and is exactly what proves the base_server gate
        fix (see "Flagged Mismatch") is necessary — do this *before* investing in wiring §5.2, so
        the gap is found in CI, not on the instrument.
     d. Implement the `FastServer.ExecuteCommand` override that bypasses the gate for
        `Pause`/`Resume`/`Abort` (the recommended fix above), proven by the test from (c).
     e. Add `run_state` to `tool_base.proto`'s `StatusReply` (D1) and wire
        `FastServer._get_status`/`GetStatus` to build it from `self.service.status()` plus adapter-
        recorded `PauseInfo` state.
   - **Can be stubbed/skipped until step 3:** the actual `on_pause` recording inside
     `Transfer`/`RunProtocol` (needs the real `through_pauses`/`on_pause` kwargs on `RunOptions`,
     which exist in the core today but aren't yet passed from `server.py:412, 430`).
3. **Once the core SHA is pinned:** wire `RunOptions(through_pauses=True, on_pause=...)` into
   `Transfer`/`RunProtocol` (`server.py:412, 430`), connect the adapter's recorded `on_pause` state
   into `_get_status`'s `run_state`, re-run the full fork gate (offline suite) and `tsc`.
4. **Deploy in the abort/resume rollout's order** (core into `.venv`, restart `galago-tools`,
   rebuild `galago-web`), then run the supervised live acceptance scenarios from design §9 — by
   this point the base_server concurrency question should already be closed by step 2(c)/(d)'s
   test, not discovered live.

## Sources

All findings are traced directly against the repository state at the time of this research
(2026-10-12), not inferred from the design document's prose:

- `fast-mcp/fast_mcp/run_control.py`, `orchestration.py`, `service.py` (core prerequisites, already
  shipped)
- `galago-tools` fork (`nikkopg`), `tools/fast/server.py`, `tools/base_server.py`,
  `tools/tests/fast_test.py`, `interfaces/tools/grpc_interfaces/fast.proto`,
  `interfaces/tools/grpc_interfaces/tool_base.proto`
- `galago-core/controller/server/command_queue.ts`, `server/tools.ts`,
  `server/routers/command_queue.ts`, `server/utils/SqliteQueue.ts`,
  `server/utils/promisifyGrpcCall.ts`
- `galago-core/controller/components/runs/RunsComponent.tsx`, `PauseModal.tsx`, `StopRunModal.tsx`
- `docs/specs/2026-10-12-galago-live-run-control-design.md` (governing design, cross-checked
  against the above, not taken at face value)
- `.planning/PROJECT.md`, `.planning/codebase/ARCHITECTURE.md` (pre-milestone fast-mcp core map)

---
*Architecture research for: Galago live F.A.S.T. run control (v2 milestone)*
*Researched: 2026-10-12*
