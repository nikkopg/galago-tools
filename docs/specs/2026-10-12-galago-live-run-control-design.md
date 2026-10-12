# Galago Live Run Control for the F.A.S.T. — Design (Galago side)

**Date:** 2026-10-12
**Status:** Draft — pending review
**Owner:** Nikko Gunara
**Amends:** fast-mcp `docs/specs/2026-10-06-fast-mcp-dual-frontend-design.md` (GitLab `nikkopg/fast-mcp`)
- §4.3: the Galago mapping of `Paused`.
- §6: Galago adapter commands.
- §11 #1, as already amended for operator Abort/Resume.

**Supersedes, as the primary recovery path:** the operator Abort/Resume protocol-step commands.
- galago-tools `feat/fast-tool`: `7e42f2e`, `916d2ca`, `5006108`, `7c0ff7b`.
- galago-core `feat/fast-tool`: `ce8d40d`.

**Depends on:** the fast-mcp core change "wait through pauses" (§4), already delivered by fast-mcp quick task 261012-o24 (`b30b38d`, branch `fix/run-recovery-gate`).

**Planning:** this spec governs two GSD projects, one per repo.
- **galago-tools** (`.planning/` here): the adapter work, the re-pin, deployment and the supervised live acceptance.
- **galago-core** (its own `.planning/`): the queue, tRPC and run-page work.

It moved here from fast-mcp on 2026-10-12, so the Galago-side design lives with the Galago code.

**Scope:**
- **In:** galago-tools (`tools/fast/`, `tool_base.proto`) and galago-core (queue, tRPC, run page).
- **Out:** fast-mcp internals, beyond the API this design assumes from it (§4).

## 1. Problem

A F.A.S.T. run is one long-running Galago protocol step, `transfer` or `run_protocol`. Today that step either succeeds or fails:

- **An instrument pause fails the step.** E.g. `-645 WrongPlateType` at 0% because deck 3 has no plate. The step returns `ERROR_FROM_TOOL`, the queue marks it failed and goes `FAILED`, and the instrument is left paused.
  - Seen in production on 2026-10-09.
  - Seen again in the supervised test on 2026-10-12.
- **The current recovery path doesn't fit how operators work.** Abort and Resume exist only as commands. They must either be planned into a protocol in advance, or sent from the tool page's **Send Command** form. Neither is the natural reaction when a run pauses in front of you.
- **Nothing in Galago can reach a step that's already running:**
  - Galago's **Pause** only acts between steps (`CommandQueue.pause()`).
  - **Stop** waits for the in-flight step to finish (`stop()` awaits `_runningPromise`).
  - The adapter's motion lock refuses a second motion command while `Transfer` runs.

**Goal:** while a F.A.S.T. step runs, the operator can **pause, resume and abort it live** from the Galago run page. An instrument-initiated pause becomes an **on-screen prompt** that keeps the step alive until the operator decides.

Software must still never pause, resume or abort on its own.

## 2. Decision

Three changes, one per layer:

1. **The step stays open through pauses.** A paused F.A.S.T. run is "waiting for the operator", not a failure. The adapter keeps the step's wait open across pauses. The step ends only when the run really ends: done, aborted, timed out or cancelled.
2. **Out-of-band control.** galago-core gets a control path that sends Pause, Resume or Abort **directly to the tool of the running step**. These are never enqueued as protocol steps. The adapter accepts them while the step's `Transfer`/`RunProtocol` is still in flight.
3. **Run state is visible.** While a controllable step runs, galago-core polls the tool's run state. It shows live controls, and a pause prompt with the instrument's reason and the operator's explicit choices.

The design is **generic**: a tool type declares that it supports live run control, and the F.A.S.T. is the first one. Other tools that can pause mid-run can reuse the same queue path, modal and buttons.

Rejected alternatives:
- **Keep Abort/Resume as protocol steps.** That's the status quo; it requires planning recovery in advance (§1).
- **Fail the step on pause, then offer Resume/Abort in the error banner.** The step has already ended, so a Resume would continue an instrument run that Galago no longer tracks. The run's outcome would then belong to no step.
- **The adapter auto-resumes or auto-aborts on a pause.** This violates the operator-only rule.

## 3. Interaction model

### 3.1 States of a controllable step

```
             operator Pause            instrument pause (e.g. -645)
   RUNNING ───────────────────► PAUSED ◄──────────────────────────── RUNNING
      ▲                           │  │
      │  operator Resume          │  │ operator Abort
      └───────────────────────────┘  ▼
                                   ABORTING ──► step ends: Aborted (by operator)
   RUNNING ──► done (idle + completion event) ──► step ends: SUCCESS
   any     ──► run timeout (paused time excluded, §4) ──► step ends: TimedOut (never aborts)
```

| Trigger | Who | Effect on the instrument | Effect on the Galago step |
|---|---|---|---|
| Pause button | Operator | `pause` (gated: running only) | Stays open; state shows PAUSED |
| Instrument pause | Instrument | Already paused | Stays open; pause prompt opens |
| Resume (button or prompt) | Operator | `resume` (gated: paused only) | Stays open; back to RUNNING |
| Abort (button or prompt) | Operator | `abort` (gated: running or paused) | Ends as Aborted; the queue stops the run (§6.6) |
| Galago Stop | Operator | Only through an explicit "abort the instrument run?" confirmation (§6.6) | — |
| Timeout or cancel | Software | **Nothing**: never pause, resume or abort | Ends as TimedOut or Cancelled |

### 3.2 Physical decisions

Each recovery action carries a physical decision that the operator must make explicitly:

| Action | Decision |
|---|---|
| Resume | `is_tip_broken` |
| Abort | `return_liquid` |
| Pause | `hard` (hard vs soft pause) |

In the UI each is a two-option choice with **nothing preselected**. The action button stays disabled until a choice is made. On the wire each is the existing required `"yes"`/`"no"` string, which fails closed (§5.1).

## 4. Core prerequisites (fast-mcp, specified separately)

The adapter relies on the following core behaviour. Names are **provisional** until the fast-mcp change lands. The adapter then pins that commit, as before (D-03).

- **Wait through pauses (opt-in):**
  - The run options get a mode in which a `paused` poll does **not** end `wait`.
  - A callback (`on_pause(PauseInfo)`) fires once per pause episode.
  - The wait ends only on done, aborted, timeout or cancel.
  - The default behaviour, the MCP tool JSON and `RunResult` contract v1 are unchanged.
- **Pause episodes:** a transition into `paused`, or a `paused` first observation of a newly submitted run. After an accepted resume, a stale leading `paused` neither re-fires `on_pause` nor ends the wait. This fixes the limitation pinned in galago-tools today (`test_resume_known_limitation_leading_paused_poll_reads_as_paused`).
- **PauseInfo** carries:
  - the error code and catalog name;
  - the percent complete;
  - the instrument's sanitized `lastEvent` detail, e.g. `wrongDetection: [{expectedPlateID, detectedPlateID, position}]`.
- **Paused time doesn't count toward the run timeout.** An operator may need minutes to fix the deck.
- **Concurrency:** `pause`, `resume`, `abort` and `status` may be called from another thread while `wait` is polling on the same `FastService`. They keep their state gates and return `Refused` with no instrument call when the state is wrong.

Until the core change lands, galago-core and the adapter's control path (§5.1–5.3, §6) can be built and tested against a mocked `FastService`. Only §5.2's wait-through-pause wiring needs the real core API.

## 5. Adapter (galago-tools `tools/fast/`)

### 5.1 Control commands

- **New `Pause`** command, alongside the existing `Abort` and `Resume`:
  - It maps 1:1 to `FastService.pause(hard=...)`.
  - `hard` is a required `"yes"`/`"no"` string, the same fail-closed representation as `return_liquid` and `is_tip_broken`.
- **Control commands don't take the motion lock.** They act on the run that the in-flight `Transfer`/`RunProtocol` owns. Their state gates stay in the core, so the adapter adds no state check (unchanged rule).
  - **Correction (2026-10-12, architecture research):** the 10-worker thread pool (`serve()`) is not enough on its own.
    - **The readiness check blocks them.** In real mode, `ToolServer.parseCommand` refuses every `ExecuteCommand` with `NOT_READY` unless `status == READY` (`base_server.py:200`). `ExecuteCommand` sets `BUSY` for the whole duration of any command (`base_server.py:236`), so while a `Transfer` runs, every control command would be refused before reaching the adapter.
    - **Its `finally` would corrupt the status.** It resets `status` to `READY` when *any* command ends (`base_server.py:254`), so a control command finishing mid-run would mark the tool `READY` while the `Transfer` is still running.
  - **Required fix:** `FastServer` overrides `ExecuteCommand`, the same way it already overrides `_dispatchCommand` and `GetStatus`. For `Pause`, `Resume` and `Abort` it skips the readiness check and leaves `status` untouched; it still checks the tool type and runs `_check_args`. Every other command takes the unchanged `base_server` path. `tools/base_server.py`, which every tool type shares, is not edited.
  - **Required test:** before §5.2 is wired, a **real-mode** (not simulated) test shows a `Pause`/`Resume`/`Abort` sent through `ExecuteCommand` reaching the service while a `Transfer` is blocked, with `status` still `BUSY` afterwards. The existing concurrency test only runs in simulated mode, where `isReady()` always returns `True`, so it can't catch this.
  - With no run in flight, they still work. This is the crash-recovery path, e.g. an instrument left paused after Galago restarted. The core gate decides.
- **Result mapping:**
  - `Refused` → `ERROR_FROM_TOOL` "instrument not ready: <reason> (state <state>)" (unchanged).
  - `errorCode` 0 → `SUCCESS`.
  - Any other or missing `errorCode` → `ERROR_FROM_TOOL`.
- **Resume no longer waits** when a run is in flight. The in-flight step's wait already covers the rest of the run, so `Resume` returns once the instrument accepts it.
  - With no run in flight (crash recovery), keep today's behaviour: `Resume` waits for the resumed run, because no other step will report its outcome.

### 5.2 Long-running commands

`Transfer` and `RunProtocol` call the core with wait-through-pauses on.

- **`on_pause`** records the current pause (`PauseInfo` plus a timestamp) in adapter state, readable by §5.3. A resume (observed as running again) clears it.
- **Final results:**
  - `Ran` → `SUCCESS`.
  - `Aborted` → `ERROR_FROM_TOOL` "run aborted by operator at <p>%" (plus the instrument error if any).
  - `TimedOut` and `Cancelled` → unchanged, never aborted.
- **The Paused message from `5006108`** remains only for the default (non-waiting) mode, i.e. the crash-recovery `Resume`.
- **The motion lock** still serialises `Transfer`, `RunProtocol`, `ScanTips` and `EjectTray` against each other.

### 5.3 Reporting run state

The current `StatusReply` carries only `uptime`, `status` and `error_message`. The queue needs the run state of a controllable tool: running or paused, percent, and the pause reason and detail.

**Option A: extend `StatusReply` (recommended, decision D1)**
- Add `optional google.protobuf.Struct run_state = 4;` to `tool_base.proto`.
- The change is additive and backward compatible: other tools leave it unset.
- galago-core's existing 5 s heartbeat already calls `GetStatus`. The queue polls faster (§6.3) only while a controllable step runs.
- For the F.A.S.T., `run_state = {state, percent, pause: PauseInfo | null}`, taken from the in-flight wait's latest observation. With no run in flight, it comes from a fresh `service.status()`.

**Option B: a `GetRunState` intent command**
- Read through `ExecuteCommand`; no shared-proto change.
- But it's F.A.S.T.-specific, and the reply's `meta_data` is the only channel.

Either way, run state is **observation only**: reading it never commands the instrument.

### 5.4 Invariants (extend the AST and tearDown checks)

- `.pause`, `.resume` and `.abort` appear only inside the `Pause()`, `Resume()` and `Abort()` control methods. `.wait` appears only in the long-running commands and the crash-recovery `Resume`.
- No code path calls a control method on a pause, timeout, cancel or error. `on_pause` only records state.
- Still enforced: no `fast_mcp.mcp` import, no raw `:5003` access, and `open_service` as the only way to get a service.

### 5.5 Simulated mode

`ToolServer` simulates a `Transfer` as a sleep, so there is no simulated run to pause.

- In simulated mode, the control commands validate their arguments and return `SUCCESS` without affecting the sleep.
- `run_state` reports `{state: "running"}` during the sleep and `idle` otherwise.

Simulating a pause, e.g. so a UI can be tested without hardware, is **out of scope**. It is a candidate follow-up: an adapter test hook that drives `run_state` to paused in simulated mode.

## 6. galago-core

### 6.1 Capability declaration

A tool type declares live run control, e.g. a `runControl` entry next to `commandFields`:

```ts
fast: { pause: { hard: "yesno" }, resume: { is_tip_broken: "yesno" }, abort: { return_liquid: "yesno" } }
```

- This entry drives the run-page controls and the pause prompt.
- The control commands are **removed from the protocol step editor's command list** (decision D3). `commandFields` feeds both the step editor and the tool page, so control commands live only in `runControl`, and the tool page offers them separately for crash recovery.

### 6.2 Control path (queue and tRPC)

- **New tRPC procedure** `commandQueue.toolControl({ action, params })`:
  - It targets the **tool of the currently running step**. It refuses if no step is running or that tool type has no `runControl` entry.
    - Needs a new accessor: `SqliteQueue` marks the running command `"STARTED"` in `startNext()`, but nothing reads that row back today.
  - It validates the decision values against `runControl`.
  - It calls the tool's gRPC `ExecuteCommand` **directly** (`Tool.controlCommand`): not enqueued, not stored as a step, and never awaited by the busy loop.
  - It records the action with `logAction`, including the operator's choices.
- **`Tool.executeCommand` stays as is for steps.** There is no gRPC deadline, so a step can stay open through a long pause; this is already the case.

### 6.3 Run-state polling and the pause prompt

- **Poll while a controllable step runs.** The queue polls the tool's run state every 1–2 s (decision D2), and stops when the step ends.
- **Fix the heartbeat.** Today `Tool.fetchStatus` stops the heartbeat after a single failure (`stopHeartbeat` in its `catch`). During a controllable step, a failed poll must retry, and must show "run state unknown" without changing the step.
- **The pause prompt:** on `run_state.pause` (a new pause episode), the run page opens a `tool_paused` modal. The modal closes when run state returns to running, or the step ends.
  - **Not through the existing modal plumbing** (2026-10-12, architecture research). The queue's `UIMessage`/`_isWaitingForInput`/`_messageResolve` mechanism (`command_queue.ts`, `pause()`/`resume()`) exists to **block the busy loop** until `resume()` resolves it. A F.A.S.T. pause happens *inside* the step's `ExecuteCommand`, which the busy loop is already awaiting, so that mechanism doesn't fit.
  - The modal reads its own `commandQueue.runState` tRPC query (the running step's tool `run_state`), independent of `modalState`. The queue's `resume()` and modal state are never touched by it.

### 6.4 Run page UI (`components/runs/`)

- **Control bar** on the running step of a controllable tool: **Pause**, **Resume** and **Abort**, enabled according to run state. It shows the state and percent.
- **`ToolPausedModal`** (new, next to `PauseModal` etc.) shows:
  - the reason, e.g. "WrongPlateType (-645)";
  - the detail rendered for people, e.g. "Deck 3: expected plate 1, found none";
  - when the pause started;
  - **Resume**, with "Tip broken? ○ yes ○ no";
  - **Abort**, with "Return liquid? ○ yes ○ no".

  Neither choice is preselected, and each action button stays disabled until its choice is made.
- **Every control action asks for confirmation** ("Resume the F.A.S.T. run with tip intact?"). All of them move the head.

### 6.5 Concurrency with the queue

- `toolControl` never touches the queue's state machine: it only commands the tool. The step's result still arrives through the normal `executeCommand` return.
- The queue's own **Pause** (between steps) is unchanged, and labelled to tell it apart: "Pause queue" vs "Pause instrument".

### 6.6 Stop and Abort

- **Stop during a controllable step** opens a confirmation, decision D4. Recommended: **"Abort the instrument run (return liquid? yes/no)"** or **Cancel**. Stop never leaves an instrument run going while Galago forgets it.
  - **Do not reuse `StopRunModal`** (2026-10-12, pitfalls research). It calls `onConfirm()` automatically when its 5 s countdown expires (`StopRunModal.tsx:47-56`), so inaction would abort the instrument run.
  - The D4 confirmation is a new modal with no timer and no default. Closing it, or doing nothing, means Cancel.
- **When a step ends `Aborted` by the operator,** the queue goes to `FAILED`, as for other step failures, with the message "aborted by operator". Later steps don't run automatically, and the operator decides to retry, skip or clear as today.

## 7. Safety invariants

1. **Only operators command recovery.** Every pause, resume and abort comes from a person in the run page or tool page. Pause episodes, timeouts, cancels, errors, restarts and reconnects never trigger one.
2. **The core owns the state gates.** Neither the adapter nor galago-core adds its own state checks, so there's one source of truth.
3. **Physical decisions are explicit.** UI choices have no default selection, and wire values are `"yes"`/`"no"`; blank or unknown values are `INVALID_ARGUMENTS`.
4. **Observation never commands.** Run-state polling is read-only.
5. **One owner.** The single-instrument-owner rules (owner lock, identical host string, no MCP server against a Galago-owned instrument) are unchanged.

## 8. Failure modes

| Event | Behaviour |
|---|---|
| galago-web restarts while a step runs | The gRPC call is dropped; the adapter's handler thread keeps waiting and holds the motion lock. The instrument continues. After the restart, the queue has no running step, so the run page shows no control bar. The **tool page's** control commands (crash recovery) still work, because they don't take the motion lock. A stuck motion lock clears when that wait ends (done, aborted or timeout). |
| galago-tools restarts while a step runs | The instrument continues unsupervised. After reconnecting, use the tool page's Resume or Abort, or the instrument itself. |
| Run-state poll fails | Show "run state unknown", keep retrying, and don't change the step (§6.3). |
| Two operators act at once | The core gate makes the second action `Refused` when the state no longer allows it. Both are logged. |

## 9. Testing

- **Adapter (offline):**
  - With `Transfer` blocked in a thread, a concurrent `Pause`, `Resume` or `Abort` reaches the service. The motion lock doesn't block control commands.
  - `on_pause` sets `run_state` and resume clears it.
  - `Aborted` maps to "aborted by operator".
  - The scoped invariants hold (§5.4), including the planted-violation check.
  - Simulated-mode control commands behave as in §5.5.
- **galago-core:**
  - `toolControl` refuses with no running step, with a tool that lacks `runControl`, and with blank decisions.
  - The `tool_paused` modal opens on a pause episode, closes on resume, and doesn't resolve the step.
  - Heartbeat retry.
  - `tsc` adds no errors.
- **Supervised live acceptance (operator at the instrument, e-stop within reach):**
  1. Reproduce the 2026-10-12 scenario: deck 3 empty → the prompt shows "Deck 3: expected plate 1, found none" → fix the deck → Resume (tip intact) → the same step ends `SUCCESS`.
  2. Pause mid-run (soft) → Resume → `SUCCESS`.
  3. Pause → Abort (return liquid yes/no) → the step ends "aborted by operator", and the queue is `FAILED`.

## 10. Order of work

1. **fast-mcp core (§4).** In progress in a separate session; produces the SHA to pin.
2. **Can start now, in parallel with 1, against a mocked `FastService`:**
   - galago-core: §6.1–6.6;
   - adapter control path: §5.1, §5.3–5.5;
   - the `tool_base.proto` change, if D1 = A.
3. **Once the core lands:** re-pin, wire §5.2 (wait through pauses), and run the full fork gate and `tsc`.
4. **Deploy**, in the order from the abort/resume rollout: core into `.venv`, restart `galago-tools`, rebuild `galago-web`. Then the supervised live acceptance (§9).

## 11. Decisions (settled 2026-10-12)

- **D1, run-state transport:** **extend `StatusReply`** with `optional google.protobuf.Struct run_state` (option A).
- **D2, polling interval:** **2 s** while a controllable step runs.
- **D3, step-editor commands:** **remove** `abort` and `resume` from the protocol step editor. They stay available from the tool page for crash recovery.
- **D4, Stop during a controllable step:** Stop **asks** "abort the instrument run (return liquid? yes/no)" or **Cancel**. It never detaches from a running instrument.
- **D5, Pause:** **soft pause only.** The instrument API's `hardPause` boolean is undocumented (no description in the OpenAPI spec), so hard pause is deferred until the F.A.S.T. team confirms its physical behaviour.
  - Consequence for §3.2 and §5.1: `Pause` carries no `hard` decision. The adapter always calls `FastService.pause(hard=False)`, and the run-page Pause button asks only for confirmation.
  - Adding hard pause later means one explicit, non-defaulted choice in the Pause control.
- **D6, scope:** **generic** `runControl` capability; the F.A.S.T. is the first tool type to declare it.

## 12. What carries over from the abort/resume protocol-step work

These carry over unchanged:
- the core's state gates;
- the `"yes"`/`"no"` fail-closed decisions;
- the `Refused` and `errorCode` mapping;
- the scoped no-auto-abort invariants and their tests;
- crash-recovery Abort/Resume from the tool page.

These change:
- Resume no longer waits when a run is in flight;
- `abort` and `resume` leave the protocol step editor;
- the Paused message only applies to the crash-recovery path.
