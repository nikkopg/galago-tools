# Pitfalls Research

**Domain:** Live pause/resume/abort control of an in-flight instrument run, added across three
repos (fast-mcp core, the `nikkopg/galago-tools` F.A.S.T. adapter, galago-core's queue/tRPC/run
page). Confidence is HIGH where a pitfall is grounded in a specific file/line/test already in the
repos; MEDIUM where it's inferred from the design doc's intent without a concrete code citation;
LOW is not used below without saying so explicitly.

**Researched:** 2026-10-12
**Confidence:** HIGH (most findings cite an exact file; a few inferred ones are marked MEDIUM)

**Phase key:** Phase 6 = control path + run state + UI, built and tested against a mocked core
(design §10 step 2, can start now). Phase 7 = wire wait-through-pauses against the real core,
re-pin, deploy in order, supervised live acceptance (design §10 steps 3-4).

## Critical Pitfalls

### Pitfall 1: Reusing `StopRunModal`'s auto-countdown for the instrument-involving Stop

**What goes wrong:**
`components/runs/StopRunModal.tsx` (the only Stop-confirmation modal that exists today) auto-fires
`onConfirm()` after a 5-second countdown unless the operator clicks "Continue" to cancel
(`handleConfirm` → `setInterval` → `onConfirm()` when the countdown reaches 0,
`StopRunModal.tsx:46-62`). D4 requires Stop during a controllable step to **ask** "abort the
instrument run (return liquid? yes/no)" or Cancel, with "nothing preselected" (§3.2, §6.4) and the
action button disabled until a choice is made. If D4 is implemented by routing the controllable-step
Stop through this existing component (the obvious, least-code path — it's already wired to the
queue's Stop button), the result is a confirmation that **completes itself** on operator inaction,
auto-sending `return_liquid` at whatever default the code falls back to. That is software
auto-aborting a live instrument run — the exact thing §7 invariant 1 forbids — disguised as "just
reusing the existing Stop modal."

**Why it happens:** `StopRunModal` was built for queue-only steps where "stop eventually, with a
grace window to cancel" is the right UX (no physical motion decision attached). The new case
(§6.6) has a instrument physically in motion and a required yes/no decision; the two look like the
same UI pattern ("a Stop confirmation modal") but have opposite default-safety requirements.

**How to avoid:** Build a distinct modal for the controllable-step Stop path (or add a prop that
disables the auto-countdown entirely and requires an explicit return-liquid radio before the Abort
button enables). Never let any auto-timer fire an instrument command. Code review should check
specifically that no `setInterval`/`setTimeout` in the new Stop-during-a-step path can call
`toolControl` with an abort action.

**Warning signs:** A PR that passes `onConfirm` from the existing `StopRunModal` straight into a
`toolControl({action: "abort", ...})` call; no explicit yes/no radio state gating the Abort button
in that code path; a UAT test plan that says "click Stop and wait" instead of "click Stop, choose
return-liquid, click Abort."

**Phase to address:** Phase 6 (the control bar and Stop confirmation are built against a mocked
core in Phase 6, per design §10 step 2 — this is exactly where the wrong modal would get wired in).

---

### Pitfall 2: `tool_paused` modal wired through the existing `_messageResolve` pattern, ending the step

**What goes wrong:**
Every existing `UIMessage` type in `command_queue.ts` (`pause`, `message`, `timer`, `user_form`,
`stop_run`) follows one pattern: `await this._ensureModalReady(); ... this._isWaitingForInput =
true; this._currentMessage = {...}; return new Promise<void>((resolve) => { this._messageResolve =
resolve; })`, and the **busy loop itself calls these and awaits the returned promise before marking
the command complete** (e.g. `await this.pause(message); continue;` at
`command_queue.ts:751-753`, or `await this.showMessage(...)` at `:816-818`). The design requires
`tool_paused` to be different in exactly one way: "unlike `pause`, `message`, `timer` and
`user_form`, it doesn't resolve the step" (§6.3) — the step is still open inside the tool's own
in-flight `ExecuteCommand` call (the `Transfer`/`RunProtocol` RPC), not inside the queue's busy
loop. Every other modal type in this file is implemented by pattern-matching the five existing
ones; `tool_paused` is the one case where copying that pattern is wrong. If an implementer follows
the existing five as a template (there is no fifth example of "a modal that does NOT resolve
anything" to copy from), `tool_paused` gets wired through `_ensureModalReady`/`_messageResolve`
too — which would either falsely mark the in-flight `Transfer`/`RunProtocol` command complete while
the instrument is still paused mid-run, or desynchronize the queue's own waiting-for-input state
from the step that's actually still open inside the tool.

**Why it happens:** All five precedent types in the file share one shape, and `tool_paused` is
deliberately not supposed to share it — that is easy to miss when extending a `switch`/union type
that the rest of the file treats uniformly.

**How to avoid:** Keep `tool_paused` entirely outside `UIMessage`'s `_isWaitingForInput` /
`_messageResolve` machinery. It should be populated purely from the run-state poll (§6.3) and
rendered by the run page as read-only observation data, with its own Resume/Abort buttons calling
`toolControl` directly — never through `commandQueue.resume()`. Add a test asserting that a
pause-episode transition never calls `this.pause()`/`showMessage()`/`_ensureModalReady()`, and that
`this.commands.complete()` is not called as a side effect of a pause episode.

**Warning signs:** A new `case "tool_paused":` branch inside `_runBusyLoopWhileQueueNotEmpty`'s
`if (nextCommand.commandInfo.toolId === "Tool Box")` block (that block is for the Tool Box's own
synthetic step-level commands, never for an in-flight third-party tool run); `tool_paused` added to
the `UIMessage.type` union and then handled by the same `isModalOpen`/`messageData` state in
`RunsComponent.tsx` that the other five use.

**Phase to address:** Phase 6 (the modal and queue wiring are the explicit Phase 6 deliverable,
built against a mocked core per design §10 step 2).

---

### Pitfall 3: Deploying the new galago-core against an old, ungated fast-mcp core

**What goes wrong:**
This exact failure already happened once in this project: PROJECT.md's Key Decisions table records
that "a production Galago run with no plate on deck 3 paused the instrument at 0%... Galago had no
way to resume or abort, so the run was stranded," and the fix required adding the state gate
(`_require_state`) to `FastService` itself so pause/resume/abort are refused in the wrong state
*no matter which front end calls them*. PROJECT.md's milestone context states plainly: "deployment
order matters... because an older core has no state gate on abort/resume." If galago-core's new
`toolControl` UI ships to a `galago-tools` process still running against an older pinned
`fast-mcp` core (no `_require_state` gate, no `ResumeMarker`, no `through_pauses`), the UI will let
an operator send Resume/Abort/Pause in states the old core cannot safely refuse — recreating the
production incident with a friendlier front end on top of it.

**Why it happens:** The core, the adapter, and galago-core are three separately deployed
artifacts with no single version check between them; "re-pin, then restart, then rebuild" is a
manual, ordered checklist (design §10 step 4), not something the deploy pipeline enforces.

**How to avoid:** Follow the documented order exactly: new core into the galago-tools `.venv`
first, restart `galago-tools`, then rebuild `galago-web` — never the reverse. Before the
supervised live acceptance, confirm the installed core's pinned SHA (`pip show fast-mcp` or the
`git+...@<sha>` line in `tools/fast/requirements.txt`) matches the SHA the design's §4 prerequisites
were built against, and confirm `FastService._require_state` is present (e.g. a quick
`python -c "import inspect; from fast_mcp.service import FastService; print(inspect.getsource(FastService._require_state))"`
smoke check) before enabling the new UI against a live instrument.

**Warning signs:** `tools/fast/requirements.txt`'s pinned SHA is older than the commit documented in
the Core prerequisites section of the design (currently `b30b38d` plus quick task 261012-o24); the
supervised test reaches a pause state and Resume succeeds from an unexpected instrument state
without a `Refused` ever being observed in logs during negative testing.

**Phase to address:** Phase 7 (re-pin, deploy, supervised live acceptance is explicitly the Phase 7
scope; this pitfall cannot be hit in Phase 6 since that phase runs only against a mocked core).

---

### Pitfall 4: `ExecuteCommand`'s shared `self.status`/`self.last_error` race once control commands no longer wait for the motion lock

**What goes wrong:**
`tools/base_server.py`'s `ExecuteCommand` wraps every dispatched command the same way:
`self.setStatus(BUSY)` → `self._dispatchCommand(command)` → `finally: self.setStatus(READY)`
(`base_server.py:239-254`). Today this is harmless because `Abort`/`Resume` are both in
`MOTION_COMMANDS` and take `self._motion_lock` (`tools/fast/server.py:66-67`, `:520-578`), so while
a `Transfer` holds that lock, a concurrent `Abort`/`Resume`/`Pause`-to-be call is refused before it
ever reaches `ExecuteCommand`'s BUSY/READY bracket. The design's whole point (§5.1) is to remove
that refusal: "Control commands don't take the motion lock... they reach the instrument
concurrently... this needs no `base_server` change." That statement is true for the instrument HTTP
calls (httpx's client is documented thread-safe, `service.py:106-111`), but it overlooks that
`ExecuteCommand`'s own BUSY→dispatch→READY bracket runs on **every** gRPC worker thread handling
**every** command, including the new unlocked control commands. Once a `Pause`/`Resume`/`Abort`
call can run concurrently with the in-flight `Transfer`'s own `ExecuteCommand` call, the control
command's `finally: self.setStatus(READY)` can fire while `Transfer`'s `ExecuteCommand` is still
mid-flight, flipping the generic tool health status (`self.status`, read by the separate `GetStatus`
RPC and surfaced to galago-core's heartbeat, `tools.ts:fetchStatus` → `this.status =
statusReply.status`) back to READY while the F.A.S.T. run is still physically executing. `self.status`
and `self.last_error` are plain unsynchronized instance attributes, mutated from whichever gRPC
worker thread's command finishes last.

**Why it happens:** `base_server.py` is explicitly off-limits ("Never edits tools/base_server.py,"
`server.py:16` and `:348`), so the natural fix (give the BUSY/READY bracket its own reentrant
counter, or make it per-run rather than per-command) can't be made in the file that owns the bug;
it has to be worked around in `FastServer` instead, which is easy to defer as "someone else's
problem" since the design doc doesn't mention it.

**How to avoid:** Decide explicitly, in the Phase 6 design-for-code pass, whether the generic
health status (`self.status`/`GetStatus`) is allowed to say READY while a controllable run is still
open, and if not, override `GetStatus`'s *health* branch (already dual-dispatched by arity in
`FastServer.GetStatus`, `server.py:450-469`) to report BUSY whenever the adapter's own `run_state`
tracking says a run is in flight, regardless of what `self.status` last settled to from a racing
control command. Add a concurrency test with a real blocked thread (mirroring
`test_second_motion_command_refused_while_first_in_flight`'s shape) that drives a `Transfer` and a
concurrent `Abort` through two real gRPC worker threads and asserts `GetStatus`'s *health* reply
never reports READY while the `Transfer` call is still open.

**Warning signs:** A supervised test where the run page's heartbeat/tool-status indicator
momentarily shows "ready" while the F.A.S.T. is mid-run and a control command was just sent; any
other part of galago-core that gates new work on `Tool.status === ToolStatus.READY` (worth a quick
grep before Phase 7) accepting a command mid-run because of this flicker.

**Phase to address:** Phase 6 (the control path's interaction with `base_server`'s unlock can and
should be proven with a mocked-core, real-thread test before the real core is wired in); re-verify
under live timing in Phase 7.

---

### Pitfall 5: The galago-core heartbeat still stops polling on a single failed status check

**What goes wrong:**
`Tool.fetchStatus()` in `controller/server/tools.ts` (`:99-111`) calls `this.stopHeartbeat()` in its
`catch` block on *any* single failed `getStatus` RPC. The design explicitly names this as a bug to
fix (§6.3: "Today `Tool.fetchStatus` stops the heartbeat after a single failure... During a
controllable step, a failed poll must retry, and must show 'run state unknown' without changing the
step"). If this fix is skipped or only partially done, one transient gRPC hiccup during a long
`Transfer`/`RunProtocol` permanently kills that tool's heartbeat for the rest of the run (and every
run after it, until something restarts polling) — not just the "run state unknown" UI, but the
generic health heartbeat for every other command type that tool offers.

**Why it happens:** `fetchStatus` is shared by all ~20 tool types through one `Tool` class; the
2026-10-12 live-run-control work only has eyes on the F.A.S.T. tool, so a fix scoped only to "while
a controllable step runs" is easy to leave half-done (e.g. retry logic added to the run-state poll
path but the underlying `startHeartbeat`/`fetchStatus` loop left exactly as is), or conversely a
blanket "never stop the heartbeat" fix applied everywhere risks masking a genuinely dead tool
forever with no backoff, spamming `console.error` indefinitely.

**How to avoid:** Fix `fetchStatus`'s catch path to retry (with backoff) instead of calling
`stopHeartbeat()`, generically — not a special case gated on "is this tool mid-run" — since any
tool's heartbeat stopping silently on one failure is already a latent bug this milestone happens to
expose. Add a test that a single failed `getStatus` leaves `this.heartbeat` still scheduled.

**Warning signs:** The heartbeat interval id (`this.heartbeat`) becomes `undefined` after one
simulated gRPC error in a test; the run page's tool-status indicator freezes at "unknown" instead of
recovering after the transient failure clears.

**Phase to address:** Phase 6 (this is pure galago-core wiring, independently testable without the
real core — design §10 step 2 and §9 list "heartbeat retry" as an explicit galago-core test item).

---

### Pitfall 6: The motion lock removal reopens a window the lock used to close for *other* motion commands

**What goes wrong:**
`FastServer`'s `_motion_lock` today serializes `Transfer`, `RunProtocol`, `ScanTips`, `EjectTray`,
`Abort` and `Resume` against each other (`MOTION_COMMANDS`, `server.py:66-67`; each handler does
`if not self._motion_lock.acquire(blocking=False): return _reply(NOT_READY, message=_BUSY_MESSAGE)`).
The design (§5.1, §5.2) removes the lock specifically for the *recovery* commands (`Pause`,
`Resume`, `Abort`) so they can reach a running step. It's easy, while making that change, to also
accidentally drop or weaken the lock's protection for `ScanTips`/`EjectTray` (which still must stay
serialized against `Transfer`/`RunProtocol` — those are unrelated motions, not control commands) if
the lock-acquisition logic is refactored into one shared helper that treats "is this one of the
commands the live-control design talks about" as the same question as "does this command need the
motion lock."

**Why it happens:** All six commands currently share one `MOTION_COMMANDS` set and nearly identical
"`acquire(blocking=False)` or return busy" boilerplate; the natural refactor when carving out
Pause/Resume/Abort is to touch that shared logic, risking a scope slip onto `ScanTips`/`EjectTray`.

**How to avoid:** Keep `MOTION_COMMANDS`/the lock-acquiring set and the new "control, no lock" set
as two clearly separate, independently named constants, and keep a test asserting `ScanTips` and
`EjectTray` are still refused with `NOT_READY`/busy while a `Transfer` holds the lock (an extension
of the existing `test_second_motion_command_refused_while_first_in_flight`), alongside a new test
that `Pause`/`Resume`/`Abort` are *not* refused in the same situation.

**Warning signs:** `test_second_motion_command_refused_while_first_in_flight` gets weakened or
deleted instead of split into "still-locked" and "no-longer-locked" variants during this work.

**Phase to address:** Phase 6.

---

## Moderate Pitfalls

### Pitfall 7: `on_pause` quietly growing into a command site

**What goes wrong:** The core's contract is that `on_pause(PauseInfo)` only *records* state — "a
callback... fires once per pause episode," never commands anything (design §4, §5.2: "`on_pause`
records the current pause... in adapter state... A resume... clears it"). The existing AST invariant
(`TestAdapterInvariant` in `fast_test.py`, scoping `.pause`/`.resume`/`.wait` to only appear inside
`Abort`/`Resume`'s own function bodies) does not yet know about `on_pause`, `Pause`, or `run_state`
at all — those are new to v2. If the invariant test isn't extended when `Pause` is added, there are
two ways to go wrong simultaneously: (a) legitimate new code referencing `.pause` anywhere outside a
new `Pause` method trips a false positive and blocks the PR, or (b) the scoping is extended too
loosely (e.g. by name alone) and a line added to the `on_pause` callback or to the long-running
`Transfer`/`RunProtocol` handler that calls `.abort()`/`.resume()` "just this once, to be safe"
passes silently because the AST scoping was defined to tolerate it.

**Why it happens:** AST invariants pin a specific shape; every new call site this milestone adds
(`Pause`, `on_pause`, `run_state` reporting) is new surface the existing invariant was never written
to cover, so it protects nothing by default until deliberately extended.

**How to avoid:** Extend `scoped_attrs` to add `"pause": "Pause"`; keep `on_pause` and `run_state`
reporting entirely free of `.pause`/`.resume`/`.abort`/`.wait` calls (verified by the unscoped
default, i.e. don't add `on_pause` to `scoped_attrs`). Add the "planted violation" check the design
doc already names in §9 ("the planted-violation check") as a literal test: deliberately insert an
`.abort()` call inside `on_pause`'s body in a throwaway copy of the AST and confirm the invariant
test fails — proving the invariant actually catches the mistake it's meant to catch, not just that
it currently passes.

**Warning signs:** `TestAdapterInvariant` isn't touched in the same PR that adds `Pause`/`on_pause`;
no new test name resembling "on_pause never commands."

**Phase to address:** Phase 6 (the adapter-side control commands and `on_pause` wiring, per design
§4/§5.1-§5.2, start in Phase 6 against the mocked core — the invariant must be extended at the same
time, not deferred to Phase 7 when the real core lands).

---

### Pitfall 8: `EstimateResume`'s flat 15s placeholder is now wrong for the common case

**What goes wrong:** `EST_RESUME_S = 15` (`server.py:117`, "the same flat placeholder as Abort")
was calibrated under the old rule that `Resume` always waits for the resumed run to finish. The
design changes this: "Resume no longer waits when a run is in flight" (§5.1) — only the
crash-recovery path (no run in flight) still waits. After this change, the *common* operator path
(resume a step that's live-paused) returns almost immediately, while `EstimateResume` still reports
15s to the Gantt/ETA display, and the *rare* crash-recovery path can take as long as the remaining
run — which 15s badly underestimates. `EstimateResume` has no way to distinguish the two cases: the
`EstimateDuration` RPC bypasses `_check_args` and dispatch entirely (`base_server.py`'s
`EstimateDuration` calls `_estimateDuration` directly, never through `ExecuteCommand`), so it never
sees whether a run is in flight.

**Why it happens:** The estimate methods were written against the "Resume always waits" contract;
the live-control design changes `Resume`'s behavior without revisiting its estimate. This is the
D-16 "ASSUMED PLACEHOLDERS" debt already flagged as unresolved — this milestone makes the existing
inaccuracy worse specifically for the newly-common case.

**How to avoid:** If `self.service` can report whether a run is currently in flight without a
transport call (e.g. by checking the adapter's own `run_state` tracking added for §5.3), split
`EstimateResume` into two branches; otherwise, explicitly document the estimate as wrong for the
in-flight case and leave a backlog item rather than silently shipping a stale number as if it were
calibrated.

**Warning signs:** The Gantt chart shows a 15s bar for a Resume that actually returns in under a
second once a run is in flight, every single time (not just occasionally) — this is deterministic,
not a timing fluke.

**Phase to address:** Phase 7 (only observable once the real wait-through-pauses behavior is wired
in and timed against the live instrument; acceptable to leave as documented debt if deprioritized,
matching the D-16 precedent).

---

### Pitfall 9: `run_state` polling races the queue's own independently-cadenced polls

**What goes wrong:** `RunsComponent.tsx` already runs several independently-cadenced polls:
`commandQueue.getAll` (2000ms), `commandQueue.getAllRuns`/`getAll` (1000ms), and
`commandQueue.modalState` (1000ms) — the last one is explicitly commented "Combined modal state
query — atomic to prevent race conditions" (`RunsComponent.tsx:112-115`), i.e. the codebase already
had to fix one such race by merging several derived-state reads into one atomic query. Adding a
*fourth*, separately-cadenced 2s `run_state` poll (§6.3/D2) as its own independent `useQuery` risks
reintroducing exactly the class of bug that `modalState` was created to prevent: the pause-prompt
state (driven by `run_state`) and the generic command/progress state (driven by the other queries)
can each land mid-way through the other's refetch, producing a flash of contradictory UI (e.g. the
progress bar still reading 10% "running" for one tick after the pause prompt has already appeared,
or the reverse on resume).

**Why it happens:** It's simpler to add `run_state` as its own new `useQuery` next to the existing
ones than to fold it into the existing atomic `modalState` query, especially since it's driven by a
different backend source (a new `toolControl`-adjacent read vs. the queue's own in-memory
`UIMessage` state).

**How to avoid:** Fold the `tool_paused` prompt and run-state display into the same atomically-read
query pattern `modalState` already established, rather than introducing a fifth independently-polled
query; if that's not practical, keep `run_state` polling scoped to only the currently-running
controllable step the other queries already report, so there is a single source of truth for "is a
step running" that gates all of them consistently.

**Warning signs:** Two different areas of the run page briefly disagree about whether a step is
paused immediately after a pause or resume (visible in manual testing, or in a UI test asserting
on render order across two mocked query resolutions that complete in different ticks).

**Phase to address:** Phase 6 (all of this is pure galago-core UI/polling work, testable against a
mocked core per design §10 step 2).

---

### Pitfall 10: Crash-recovery Resume/Abort rendering conditioned on "a step is running," hiding them exactly when needed

**What goes wrong:** D3 moves `abort`/`resume` off the protocol step editor and onto the tool page
specifically so they're reachable when "no run is tracked" (PROJECT.md Active requirement:
"Crash recovery: Resume/Abort stay reachable from the tool page when no run is tracked"; design §8
failure-mode table: "After the restart, the queue has no running step, so the run page shows no
control bar. The tool page's control commands (crash recovery) still work, because they don't take
the motion lock"). If the tool page's Resume/Abort buttons are implemented by reusing the same
"is a controllable step currently running" condition that gates the *run page's* control bar (a
natural code-reuse move, since both are "show controls for a controllable tool"), they'll disappear
from the tool page in exactly the scenario they exist for: after `galago-web` restarts and the queue
has lost track of the step, "a step is running" is false from the queue's point of view even though
the instrument itself may still be paused mid-run.

**Why it happens:** "Show live controls when a controllable step is running" (run page) and "always
show recovery controls for this tool type" (tool page) look like the same UI condition if the
tool-page implementation is copied from the run-page one without re-deriving the condition from
first principles.

**How to avoid:** Gate the tool page's Resume/Abort purely on "this tool type declares `runControl`"
(D6), never on queue/step state; verify with a test (or a supervised-test step) that explicitly
restarts galago-web (or simulates "no running step") and confirms the tool page's Resume/Abort are
still present and enabled.

**Warning signs:** A shared `useControllableStep()`-style hook or condition used by both the run
page's control bar and the tool page's crash-recovery buttons.

**Phase to address:** Phase 6 for the rendering condition; Phase 7's supervised acceptance should
include an explicit "restart galago-web mid-run, confirm tool-page Resume/Abort still work" step
(this scenario is in the design's §8 failure-mode table but not explicitly listed among the three
§9 supervised-acceptance scenarios — worth adding).

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|-----------------|-----------------|
| Hard pause (`hardPause`) left unimplemented, Pause always sends `hard=False` (D5) | Avoids guessing at undocumented instrument behavior | Operators who need a true hard stop still have no live-control path for it; must use the e-stop or instrument's own controls | Acceptable now — explicitly deferred (D5) pending F.A.S.T. team confirmation of `hardPause`'s physical behavior |
| Simulated mode never produces a simulated pause (§5.5) | No simulated-pause plumbing to build and maintain | `tool_paused` modal and run-state polling logic have no hardware-free regression path except mocking `FastService` directly | Acceptable if Phase 6 compensates by mocking at the Python service boundary (see Pitfall testing note below) rather than skipping coverage entirely |
| `EstimateResume`'s single flat placeholder for two now-different-latency paths (Pitfall 8) | No new branching logic needed in an already-placeholder estimate | Gantt/ETA display is predictably wrong for the common resume-while-running case | Acceptable short-term per the existing D-16 "ASSUMED PLACEHOLDERS" precedent; revisit if an operator complains the ETA is misleading |
| F5 (queue re-ran one non-idempotent `transfer` three times) and F3 (run UI hides tool errors) kept out of scope | Avoids re-opening `command_queue.ts`/`SqliteQueue.ts` internals this milestone doesn't otherwise touch | A wait-through-pauses step sits open in the queue far longer than today's steps did; if the F5 retry path can still fire on a long-open step, a live-paused `Transfer` could in principle be retried while still "open," which would be a new, more dangerous manifestation of F5 than the one already recorded | Accepted by explicit 2026-10-12 user decision (PROJECT.md "Out of Scope") — but worth a deliberate sanity check in Phase 7 that nothing in the longer-lived wait-through-pauses step changes F5's blast radius |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|--------------|----------------|-------------------|
| `tool_base.proto` → ts-proto codegen | Regenerating with whatever `ts-proto` version `node_modules` happens to resolve (1.153.2 is known broken for this file) instead of the pinned 1.151.1 | Pin `ts-proto` explicitly for this regeneration and diff the generated `tool_base.ts` against the previous known-good output before committing it |
| `tool_base.proto`'s new `run_state` field | Adding `run_state` as a plain (non-`optional`) `Struct` field, which proto3 treats as always-present with an empty-struct default — breaking every other tool type's `StatusReply`, which never set it | Use `optional google.protobuf.Struct run_state = 4;` exactly as D1 specifies, and confirm presence-checking (`HasField`/`hasRunState` equivalent) is used on read, not a truthy-empty-struct check |
| galago-web Docker build | Host `node_modules` leaking into the image (already happened once per the milestone's own history; `.dockerignore` was added as the fix) | Confirm `.dockerignore` still excludes `node_modules` before rebuilding `galago-web` in Phase 7's deploy step; a clean rebuild (not an incremental one) is the cheapest way to catch a regression here |
| fast-mcp core SHA pin (`tools/fast/requirements.txt`) | Re-pinning to "whatever's on the branch" at deploy time instead of the exact SHA the design's §4 prerequisites were authored against | Pin to the exact commit that implements `through_pauses`/`on_pause`/`ResumeMarker` and record that SHA in the same place prior re-pins were recorded (PROJECT.md Key Decisions) |
| galago-core `resume` naming | `commandQueue.resume()` already exists and means "resume the *queue's* pause/message modal" (`command_queue.ts:527`); the new instrument-control "resume" is a different concept entirely | Keep the new action namespaced under `commandQueue.toolControl({ action: "resume", ... })` (as the design already specifies) and never let review/implementation conflate the two "resume"s |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| 2 s `run_state` polling (D2) stacking with the existing 1-2 s queue polls on the same run page | Extra load on `galago-web` and the gRPC link per controllable step; noticeable only with several controllable tools running steps at once | Scope the poll to controllable steps only (already the design's intent — "while a controllable step runs," §6.3), and share one combined query where possible (Pitfall 9) | Breaks first as a UI race (Pitfall 9) long before it breaks as a load problem — the single F.A.S.T. workcell scale here is not large enough for raw polling volume to matter on its own |
| `ExecuteCommand`'s BUSY/READY bracket now flips on every control command sent during a run | Each Pause/Resume/Abort momentarily perturbs the shared `self.status` the heartbeat reads (Pitfall 4) | Decouple the controllable-run's reported health state from the generic per-command BUSY/READY bracket | Breaks as soon as a control command and the heartbeat poll land close together — observable even at the single-instrument scale of this project, not just "at scale" |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| `toolControl` calling the tool's gRPC `ExecuteCommand` directly, "not enqueued, not stored as a step, and never awaited by the busy loop" (§6.2) | If the gRPC call fails or the connection drops mid-call, there is no queue-tracked record of whether the instrument received it — an operator could believe a Resume/Abort was sent when it wasn't, or send it twice unsure of the first attempt's outcome | Surface the tRPC mutation's success/failure directly and synchronously in the UI (never optimistic-update the control bar before the call resolves); rely on `logAction` (already specified, §6.2) as the audit trail, and make sure the UI's error state is at least as visible as its success state |
| Two operators (or two browser tabs) issuing conflicting controls at once | The core gate correctly `Refused`s the second one (§7 invariant 2, §8 failure-mode table), but if the UI doesn't clearly surface *which* action won, an operator may assume their own click succeeded when it was refused | Show the `Refused` reason text (already produced by `_message_for`/`_recovery_reply` in `server.py`) directly in the UI rather than a generic "command failed" toast |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-------------------|
| Resume/Abort/Pause buttons left enabled while a `toolControl` mutation is in flight | A slow round trip (gRPC call + up to one 2 s poll interval before the UI reflects the new state) invites a double-click, sending the same command twice | Disable the clicked button (and its sibling choice) the instant the mutation fires, re-enabling only on error — not merely "disable until a choice is made," but also "disable once a choice is submitted" |
| Radio-style yes/no choices given any pre-set value (even a "safe-looking" `defaultChecked` on "no") | Violates "nothing preselected" (§3.2, §6.4) in spirit even if not in the literal wire value, since operators click fast and may not notice a preselected default before confirming | Render both options with no `checked` state until the operator interacts; keep the action button's `isDisabled` tied to "a choice has been made," not to component mount |
| `tool_paused` prompt closing only on a direct resume/abort success, with no indication while "run state unknown" (poll failure, Pitfall 5) is active | Operator can't tell whether the pause is still real or whether the UI has simply stopped updating | Show an explicit "run state unknown, retrying" affordance distinct from both "running" and "paused," per §6.3's own requirement |

## "Looks Done But Isn't" Checklist

- [ ] **Control commands skip the motion lock:** verify `Pause`/`Resume`/`Abort` no longer call
      `self._motion_lock.acquire(...)` in `tools/fast/server.py`, and that `ScanTips`/`EjectTray`
      still do (Pitfall 6) — check both, not just the removal.
- [ ] **`tool_paused` never resolves the step:** verify no code path calls
      `this._messageResolve()`/`this._ensureModalReady()`/`this.commands.complete()` as a side
      effect of a pause-episode transition (Pitfall 2).
- [ ] **AST invariant extended, not just passing:** verify `TestAdapterInvariant` explicitly scopes
      `.pause` to a `Pause` method, and that a deliberately-planted violation (an `.abort()` call
      inside `on_pause`) makes the test fail before the real fix is in place (Pitfall 7).
- [ ] **Heartbeat retries, not just "retries for controllable tools":** verify `Tool.fetchStatus`'s
      catch path no longer unconditionally calls `stopHeartbeat()` for *any* tool type, with a
      bounded backoff, not an unbounded retry storm (Pitfall 5).
- [ ] **Re-pinned core SHA matches the one the design was built against,** confirmed by inspecting
      `tools/fast/requirements.txt` and `FastService._require_state`'s presence, before the
      supervised live acceptance (Pitfall 3).
- [ ] **Stop-during-a-step confirmation has no auto-countdown / auto-fire path** — distinct
      component or explicitly disabled timer, not the existing `StopRunModal` reused unmodified
      (Pitfall 1).
- [ ] **Tool-page crash-recovery controls render independent of queue/step state,** verified by a
      restart-mid-run check, not just a code read (Pitfall 10).

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|----------------|-----------------|
| `tool_paused` wired through `_messageResolve` ships and marks a paused run's step complete | HIGH | The queue believes the step finished while the instrument is still paused/running; an operator must notice the mismatch, manually track down the real instrument state via the tool page, and the fix requires separating the modal's lifecycle from the step's — not a quick patch once other code assumes the merged lifecycle |
| Old core deployed under new galago-core UI (Pitfall 3) | MEDIUM | Roll galago-tools back to the correctly-pinned core and restart; no data loss expected since the core's state gate is a runtime check, not a migration, but any live run active during the mismatch window should be manually verified against the instrument before trusting the UI again |
| `ExecuteCommand`'s shared status race causes a false-READY flicker (Pitfall 4) | LOW-MEDIUM | If nothing downstream actually gates new work on `Tool.status`, this is a cosmetic/observability bug fixable with a follow-up patch; if something does gate on it, treat as HIGH and audit every consumer of `Tool.status` before re-enabling live control on that tool type |
| `StopRunModal` auto-countdown reused for instrument Stop (Pitfall 1) | HIGH | Equivalent to a software-initiated abort reaching the instrument; treat exactly like any other safety-invariant violation found live — stop testing immediately, and do not proceed to the supervised live acceptance until the modal is replaced and re-reviewed |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|-------------------|----------------|
| 1. StopRunModal auto-countdown reused for instrument Stop | Phase 6 | Code review confirms no timer can fire `toolControl`'s abort path; UAT clicks Stop and waits without choosing, confirms nothing happens |
| 2. `tool_paused` wired through `_messageResolve` | Phase 6 | Test asserts a pause episode never calls `_ensureModalReady`/`_messageResolve`/`commands.complete` |
| 3. Deploying new UI against an old, ungated core | Phase 7 | Pinned SHA and `_require_state` presence checked before supervised live acceptance |
| 4. `ExecuteCommand` BUSY/READY race once the lock is removed | Phase 6 (prove with mocked core + real threads); re-check Phase 7 | Real-thread concurrency test mirroring `test_second_motion_command_refused_while_first_in_flight`, extended for the health-status read |
| 5. Heartbeat stops on one failed poll | Phase 6 | Test: one failed `getStatus` leaves `this.heartbeat` scheduled |
| 6. Motion-lock removal scope creep onto ScanTips/EjectTray | Phase 6 | Existing lock-contention test split into "still locked" / "no longer locked" variants, both passing |
| 7. AST invariant not extended for `.pause`/`on_pause` | Phase 6 | `TestAdapterInvariant` scopes `.pause`; a planted-violation mutation test fails as expected |
| 8. `EstimateResume` wrong for the in-flight case | Phase 7 (observable only with live timing) | Documented as known debt if not split; Gantt display sanity-checked during supervised acceptance |
| 9. `run_state` poll races the existing atomic `modalState` query | Phase 6 | UI test or manual check: no observed frame where progress and pause-prompt state disagree |
| 10. Crash-recovery controls gated on step-running state | Phase 6 (render condition); Phase 7 (live restart check) | Supervised acceptance adds an explicit "restart galago-web mid-run, confirm tool-page Resume/Abort still reachable" step |

## Sources

- `/home/formulatrix/data/nikko/fast/fast-mcp/.planning/PROJECT.md` (PROJECT.md Key Decisions,
  Active requirements, Context, Out of Scope — the F5/F3 debt decisions, the production-incident
  decision log, deployment-order note)
- `/home/formulatrix/data/nikko/fast/fast-mcp/docs/specs/2026-10-12-galago-live-run-control-design.md`
  (governing design — §3-§9 cited throughout)
- `/home/formulatrix/data/nikko/fast/fast-mcp/.planning/milestones/v1-MILESTONE-AUDIT.md` (F5 queue
  retry finding, F3 run-UI finding, galago cancel-path debt)
- `/home/formulatrix/data/nikko/fast/fast-mcp/fast_mcp/service.py`,
  `run_control.py`, `session.py`, `orchestration.py` (core state gates, `ResumeMarker`,
  wait-through-pauses semantics, thread-safety docstrings)
- `/home/formulatrix/data/nikko/galago-tools/tools/fast/server.py`,
  `/home/formulatrix/data/nikko/galago-tools/tools/base_server.py` (motion lock, `MOTION_COMMANDS`,
  `ExecuteCommand`'s BUSY/READY bracket, `EstimateResume` placeholder)
- `/home/formulatrix/data/nikko/galago-tools/tools/tests/fast_test.py` (`TestAdapterInvariant`'s AST
  scoping, `test_second_motion_command_refused_while_first_in_flight`)
- `/home/formulatrix/data/nikko/galago-core/controller/server/command_queue.ts` (the five
  `UIMessage` types' shared `_messageResolve` pattern, `_runningPromise`, `CommandQueue.resume()`)
- `/home/formulatrix/data/nikko/galago-core/controller/server/tools.ts` (`fetchStatus`'s
  stop-on-failure heartbeat bug)
- `/home/formulatrix/data/nikko/galago-core/controller/components/runs/StopRunModal.tsx`,
  `RunsComponent.tsx` (auto-countdown Stop modal; the existing atomic `modalState` query comment)
- `/home/formulatrix/data/nikko/galago-core/controller/server/routers/command_queue.ts` (existing
  tRPC procedure surface, confirming no `toolControl` procedure exists yet)

---
*Pitfalls research for: Galago live F.A.S.T. run control (pause/resume/abort of an in-flight
instrument run)*
*Researched: 2026-10-12*
