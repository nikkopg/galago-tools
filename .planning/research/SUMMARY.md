# Project Research Summary

**Project:** Galago Live F.A.S.T. Run Control (v2 milestone)
**Domain:** Live run-control additions to an existing gRPC tool-driver adapter (galago-tools, F.A.S.T.) and its Next.js/tRPC orchestrator (galago-core), on top of an already-shipped wait-through-pauses core (fast-mcp)
**Researched:** 2026-10-12
**Confidence:** HIGH

## Executive Summary

This milestone closes a real production incident (2026-10-09: a run paused at 0% on a wrong-plate-type error, with no way to resume or abort, stranding the instrument) by letting an operator pause/resume/abort a F.A.S.T. run while it is still in flight, and by turning an instrument-initiated pause into an on-screen recovery prompt instead of a failed step. All four research tracks agree this is wiring work, not invention: no new library is needed (gRPC/protobuf Struct, ts-proto, @tanstack/react-query polling, and Chakra modals are all already pinned and already used for the exact same patterns elsewhere in the two repos), the industry pattern (Hamilton, Opentrons, Tecan, ISA-88) for exactly this flow is well established, and the governing design doc (docs/specs/2026-10-12-galago-live-run-control-design.md, decisions D1-D6) has already settled nearly every open question, including two corrections already folded in from this research (a required FastServer.ExecuteCommand override, and having tool_paused read its own run_state query rather than reuse the queue's blocking modal plumbing).

The recommended approach is two-track: build the entire control path, run-state transport, and UI against a mocked FastService first (Phase 6 - can start immediately, needs no core change), then separately wire Transfer/RunProtocol to actually wait through pauses against the real, already-shipped core, re-pin, deploy in the documented order, and run supervised live acceptance (Phase 7). This split exists because only one piece of the whole change (actually waiting through pauses) needs the real core; everything else - the runControl capability, the toolControl/runState tRPC paths, the Pause/Resume/Abort control bar, the ToolPausedModal, the Stop-during-a-step confirmation, and the heartbeat retry fix - can be built and tested without it.

The key risk is not "will this work" but "will it be built safely": architecture research found a genuine concurrency bug the design doc's own prose gets wrong (base_server.py's shared self.status BUSY/READY gate will refuse every control command for the entire duration of a run unless FastServer.ExecuteCommand is overridden to bypass it), and pitfalls research found two "obvious, least-code" implementation shortcuts that would silently reintroduce the exact safety invariant this milestone exists to enforce - reusing StopRunModal's auto-countdown for an instrument-involving Stop (an unattended software abort), and wiring tool_paused through the queue's existing _messageResolve modal machinery (which would falsely mark an in-flight step complete). Both are real risks a naive "reuse the nearest existing pattern" implementation would hit, and both are now explicitly called out with concrete prevention tests.

## Key Findings

### Recommended Stack

No new npm or pip package is required anywhere in this milestone. Every piece needed is already pinned and already proven for the identical pattern elsewhere in the codebase.

**Core technologies:**
- grpcio/grpcio-tools 1.70.0 + protobuf 5.29.6 - Python gRPC server and codegen; tool_base.proto already imports google.protobuf.Struct for meta_data, so adding optional google.protobuf.Struct run_state = 4 to StatusReply (D1) needs zero new imports
- ts-proto 1.151.1 (global, not the broken local node_modules 1.153.2) - TypeScript codegen for the new run_state field, via bin/make proto_ts, unchanged pattern from meta_data
- @grpc/grpc-js 1.12.2 - one persistent client per tool already multiplexes concurrent unary calls (the new toolControl call) over the existing connection; no second channel needed
- @tanstack/react-query v4 via @trpc/react-query 10.9.0 - refetchInterval polling is already the house pattern (RunsComponent.tsx already polls at 1000-2000ms); the new 2s run_state poll (D2) is the same idiom, not a new mechanism
- @chakra-ui/react 2.8.2 - Modal + RadioGroup/Radio for the new ToolPausedModal/control bar, matching every existing run-page modal and the existing yesno command-field pattern

**What NOT to add:** a WebSocket/SSE/tRPC-subscription push channel (polling is the settled, scoped answer), a second gRPC client/channel per tool, a deadline/timeout on control-command calls (the design relies on no deadline so a step can stay open through an arbitrarily long human decision), or any new state-machine/lock library in the adapter (gating is already owned by FastService).

### Expected Features

This milestone is narrowly scoped - not "what should a liquid-handler UI have," but "let an operator pause/resume/abort a live step and turn an instrument pause into a recovery prompt." Industry prior art (Hamilton Venus, Opentrons Flex 8.0+, Tecan FluentControl, ISA-88) confirms the shape, but Galago's design is deliberately coarser (whole-run resume/abort, not per-action retry/skip) and stricter (zero auto-recovery) than any of the three.

**Must have (table stakes, all P1):**
- Step stays open through an instrument-initiated pause (no step failure on pause) - directly closes the incident
- On-screen tool_paused prompt with human-rendered reason/detail that does not resolve the step
- Live Pause/Resume/Abort control bar, every decision non-defaulted
- Generic runControl capability + toolControl tRPC path (not hardcoded to F.A.S.T.)
- StatusReply.run_state (D1) + 2s polling (D2) + heartbeat-retry fix
- abort/resume removed from the protocol step editor (D3), kept on the tool page for crash recovery
- Stop-during-a-step asks "abort (return liquid?)" or cancel - never silently detaches (D4)
- Soft pause only (D5) - no hard decision exposed yet
- Supervised live acceptance reproducing the deck-3 scenario

**Should have / differentiators:** generic (not F.A.S.T.-specific) runControl capability so a future tool type gets this for free; human-rendered pause detail instead of a raw error code; paused time excluded from the run timeout (core already does this).

**Defer (explicitly out of scope, by design or by 2026-10-12 user decision):** hard pause, simulated-mode pause test hook, a second runControl-capable tool type, galago-core's F5 (queue re-ran a transfer 3x) and F3 (run UI hides tool errors) as tracked debt, fine-grained per-action retry/skip, full cross-machine instrument-ownership enumeration, auto-resume/auto-abort of any kind (explicitly forbidden - the project's "software never decides" invariant is stronger than any vendor reviewed).

### Architecture Approach

The change spans three repos along one request path: galago-core's run page/control-bar UI -> a new toolControl tRPC mutation and runState query that bypass the command queue's single-flight busy loop entirely -> the existing single gRPC client per tool -> galago-tools' FastServer adapter (new Pause, modified Resume/Abort that drop the motion lock) -> the already-shipped fast-mcp core (FastService's state-gated pause/resume/abort, ResumeMarker, wait-through-pauses). The control path is deliberately parallel to, and must never touch, the queue's existing _runningPromise/UIMessage/_messageResolve modal machinery - that machinery exists to block the busy loop until a promise resolves, but a F.A.S.T. pause happens while the step's own ExecuteCommand call is still in flight, with nothing to resolve.

**Major components:**
1. FastService (fast-mcp core, unchanged) - the single source of truth for state-gated pause/resume/abort and wait-through-pauses; already shipped
2. FastServer (galago-tools adapter) - new Pause, modified Resume/Abort (drop _motion_lock), a new required ExecuteCommand override (see Critical Pitfall below) to bypass base_server.py's shared BUSY/READY gate for these three commands, and a modified GetStatus/_get_status that builds run_state from the adapter's own recorded on_pause state
3. CommandQueue/Tool (galago-core server) - a new Tool.controlCommand thin wrapper reusing the existing gRPC stub, a new helper to find the currently-STARTED command's tool, and a fixed fetchStatus heartbeat that retries instead of stopping on one failure
4. commandQueue.toolControl/commandQueue.runState tRPC procedures - new, validate the runControl capability, never touch SqliteQueue/_runningPromise
5. Run-page UI (ToolPausedModal, control bar, Stop confirmation) - new Chakra components, each decision non-defaulted, entirely outside the existing modalState/_isWaitingForInput plumbing

### Critical Pitfalls

1. **The design doc's own concurrency claim is wrong and must be corrected in code, not just acknowledged.** base_server.py's ExecuteCommand gates every command on one shared self.status flag (BUSY during dispatch, READY in finally); without a FastServer.ExecuteCommand override that bypasses this gate for Pause/Resume/Abort, every live control command will be refused with NOT_READY for the entire duration of a run - the opposite of the goal. Prevention: write the real-mode (non-simulated) concurrency test before building the override, so the gap is proven in CI, not discovered live.
2. **Reusing StopRunModal's auto-countdown for the instrument-involving Stop** would auto-fire an abort after 5 seconds of inaction - a software-initiated abort disguised as "reusing the existing modal," directly violating the no-auto-abort invariant. Build a distinct component or explicitly disable the timer; code review must confirm no setInterval/setTimeout can reach toolControl's abort path.
3. **Wiring tool_paused through the queue's existing _messageResolve pattern** (the shape every other modal type in command_queue.ts shares) would falsely mark the in-flight Transfer/RunProtocol step complete while the instrument is still paused, since there is no second promise to resolve. tool_paused must be populated purely from the run_state poll and rendered read-only, with its own buttons calling toolControl directly.
4. **Deploying the new galago-core UI against an old, ungated fast-mcp core** would recreate the original incident with a friendlier front end - the new UI must never ship ahead of the re-pinned core with _require_state present; documented deploy order (core -> restart galago-tools -> rebuild galago-web) must be followed exactly.
5. **The motion-lock removal scope-creeping onto ScanTips/EjectTray** if the lock-acquisition refactor is done as one shared helper instead of two clearly separate constants - those two commands must stay locked against Transfer/RunProtocol; only Pause/Resume/Abort lose the lock.

## Implications for Roadmap

The user's proposed two-phase shape (Phase 6 = control path + run state + UI against a mocked core; Phase 7 = re-pin core, wire wait-through-pauses, deploy in safe order, supervised live acceptance) is directly validated by all four research tracks - pitfalls research explicitly frames its "Phase key" around this exact split, and architecture research's dependency trace confirms only one piece of work (wiring through_pauses=True/on_pause into Transfer/RunProtocol) actually needs the real core. Below is a refinement with explicit sub-steps, since both phases have internally-ordered work that matters.

### Phase 6: Control path, run state, and UI (against a mocked core)
**Rationale:** Every component in this phase - the runControl capability, toolControl/runState tRPC procedures, the heartbeat fix, the control bar, ToolPausedModal, Stop confirmation, D3's editor removal, and the adapter-side Pause/Resume/Abort lock changes plus the ExecuteCommand override - can be built and tested against MagicMock(spec=FastService) without the real core SHA being pinned. Doing this work first and in parallel (galago-core track independent of the galago-tools adapter track) is the only way to de-risk the base_server concurrency bug before any live instrument time is spent.
**Delivers:** A fully wired, fully tested control path and UI, provably correct against a mocked core, including the real-mode (non-simulated) concurrency test that proves the ExecuteCommand override actually works.
**Addresses:** All P1 features from FEATURES.md except "step stays open through pause" itself (which needs the real core's wait-through-pauses, Phase 7).
**Avoids:** Pitfalls 1, 2, 4, 5, 6, 7, 9, 10 (all explicitly scoped to Phase 6 in PITFALLS.md) - most importantly the StopRunModal auto-countdown reuse and the _messageResolve wiring mistake, both of which are easiest to make exactly at this build stage.

**Suggested internal order within Phase 6** (from ARCHITECTURE.md's "Suggested Build Order"):
1. Fix Tool.fetchStatus's heartbeat retry first - pure bug fix, no dependencies, unblocks D2 testing
2. galago-core: runControl capability declaration -> toolControl/runState tRPC procedures (against a fixture Struct) -> ControlBar/ToolPausedModal -> remove D3's editor fields -> Stop confirmation (D4)
3. Adapter: add Pause to fast.proto, strip _motion_lock.acquire() from Abort/Resume, write the real-mode concurrency test (expected to fail against today's code), then implement the FastServer.ExecuteCommand override to make it pass
4. Add run_state to tool_base.proto's StatusReply (D1) and wire _get_status to build it from adapter-recorded PauseInfo state (can still use a stub on_pause recorder at this stage)
5. Extend TestAdapterInvariant's AST scoping to cover .pause/Pause, with a planted-violation test proving it actually catches a mistake

### Phase 7: Real core wiring, deploy order, and supervised live acceptance
**Rationale:** This is the only phase that touches the live instrument and the only phase where the real core SHA matters. Architecture research's dependency trace shows this is a thin final step once Phase 6 is solid: wire RunOptions(through_pauses=True, on_pause=...) into Transfer/RunProtocol, connect the adapter's recorded on_pause state into _get_status, re-run the full offline gate, then deploy in the documented order.
**Delivers:** A working, live-validated pause->resume and pause->abort recovery for the deck-3 scenario that originally motivated this milestone.
**Uses:** The already-shipped fast-mcp core SHA (confirm b30b38d + quick task 261012-o24, or later, is pinned and FastService._require_state is present before enabling the UI).
**Implements:** Flow 2 end-to-end (instrument pause -> run_state -> polling -> tool_paused modal -> operator decision -> resume/abort) and Flow 3 (Stop-during-a-step) against real hardware.
**Avoids:** Pitfall 3 (old ungated core deployed under new UI - the single highest-cost mistake in this research) via the documented "core -> restart galago-tools -> rebuild galago-web" order, never reversed; also re-verifies Pitfall 4's concurrency fix under live timing, and adds the "restart galago-web mid-run, confirm tool-page Resume/Abort still reachable" scenario that design section 8 implies but section 9 doesn't explicitly list (Pitfall 10).

### Phase Ordering Rationale

- **Dependency-driven split, not arbitrary parallelism theater:** architecture research's dependency graph shows exactly one hard blocker (the core's wait-through-pauses) gating only one sub-piece of work (section 5.2); everything else is independently testable against a mock, so sequencing it as "mock-first, real-core-last" is the only ordering that lets the hardest bug (the base_server concurrency gate) get found in CI during Phase 6 rather than live during Phase 7.
- **The StopRunModal and _messageResolve pitfalls are maximally likely during initial UI wiring** (Phase 6), which is exactly where PITFALLS.md scopes them - the roadmap should make both explicit UAT/code-review gates at the end of Phase 6, not deferred checks.
- **Phase 7 is intentionally thin and checklist-shaped** (re-pin, verify, deploy in order, run three supervised scenarios) because every substantive risk was front-loaded into Phase 6's mocked-core testing; this matches the "Looks Done But Isn't" checklist in PITFALLS.md, which is almost entirely Phase-6-completable.

### Research Flags

Needs deeper research during planning:
- **Phase 6, the FastServer.ExecuteCommand override specifically:** architecture research marks its recommended fix MEDIUM confidence ("a recommendation, not yet built or tested") - plan-phase should budget explicit design time for this override and its concurrency test, not treat it as routine wiring.
- **Phase 6, the run_state polling/UI race (Pitfall 9):** whether to fold run_state into the existing atomic modalState query or keep it separate is an open implementation choice with real race-condition risk; worth a short design spike during planning rather than assuming either approach.

Phases with standard, well-documented patterns (skip research-phase):
- **Phase 6, tRPC/useQuery polling, Chakra modals, and gRPC Struct plumbing:** all directly copy existing, working patterns in the codebase (RunsComponent.tsx's refetchInterval, meta_data's Struct handling, PauseModal.tsx's Chakra shape) - HIGH confidence, no new research needed.
- **Phase 7, deploy order:** already a documented, previously-executed checklist (the abort/resume rollout's order) - HIGH confidence, standard pattern.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Every recommendation verified by direct inspection of installed packages and existing code usage, not general knowledge |
| Features | MEDIUM | Scope/MVP itself is HIGH (curated primary source: the project's own settled design + PROJECT.md); competitor UX claims are MEDIUM (web-sourced, cross-checked across 3 vendors + 1 standard, not primary vendor docs) |
| Architecture | HIGH for integration points/data flow (line-traced against real code); MEDIUM for the recommended ExecuteCommand override fix specifically (a recommendation, not yet built/tested) |
| Pitfalls | HIGH | Most findings cite an exact file/line/test already in the repos; a handful of inferred ones are explicitly marked MEDIUM in the source document |

**Overall confidence:** HIGH

### Gaps to Address

- The FastServer.ExecuteCommand override (base_server concurrency fix) is a recommendation, not proven code - Phase 6 planning must include writing the failing real-mode concurrency test first, then building the fix against it, per architecture research's own suggested order.
- EstimateResume's flat 15s placeholder becomes actively wrong once Resume stops waiting for in-flight runs (Pitfall 8) - not a blocker, but should be explicitly logged as accepted debt (matching the existing D-16 precedent) rather than silently left stale, unless Phase 7 planning decides to split the estimate.
- Whether run_state polling is folded into the existing atomic modalState query or kept as a separate useQuery (Pitfall 9) is unresolved - flag for a short design decision during Phase 6 planning.
- F5/F3 are explicitly out of scope per user decision, but pitfalls research notes the longer-lived wait-through-pauses step may change F5's blast radius (a live-paused Transfer sitting open longer could, in principle, interact with F5's retry path) - worth a deliberate sanity check during Phase 7, not a full fix.

## Sources

### Primary (HIGH confidence - direct repository inspection)
- docs/specs/2026-10-12-galago-live-run-control-design.md - governing design, decisions D1-D6
- .planning/PROJECT.md - Active/Out-of-Scope requirements, Key Decisions, incident history
- fast-mcp/fast_mcp/{service,run_control,orchestration}.py - core prerequisites, already shipped
- galago-tools/tools/{base_server.py,fast/server.py,tests/fast_test.py}, interfaces/tools/grpc_interfaces/{fast,tool_base}.proto
- galago-core/controller/server/{command_queue.ts,tools.ts,routers/command_queue.ts,utils/SqliteQueue.ts,utils/promisifyGrpcCall.ts}
- galago-core/controller/components/runs/{RunsComponent.tsx,PauseModal.tsx,StopRunModal.tsx}
- .venvs/galago-py310 pip-show output; controller/package.json and installed node_modules package metadata
- .planning/milestones/v1-MILESTONE-AUDIT.md - F5/F3 debt provenance

### Secondary (MEDIUM confidence)
- Hamilton Venus / Microlab STAR error-handling and run-control behavior - web search, cross-checked against an Illumina reference guide and forum threads
- Tecan FluentControl error-handling dialogs - web search across Tecan knowledge-portal pages and a third-party issue discussion
- Opentrons Flex 8.0+ error recovery mode - web search, Opentrons documentation and release notes
- ISA-88.01/IEC 61512-1 batch-control state model - web search across industrial-automation summaries, not the standard text itself

---
*Research completed: 2026-10-12*
*Ready for roadmap: yes*
