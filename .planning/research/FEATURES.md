# Feature Research

**Domain:** Live run-control UX for a lab-automation scheduler driving a liquid-handler instrument (Galago + F.A.S.T.)
**Researched:** 2026-10-12
**Confidence:** MEDIUM (governing design docs: HIGH/curated-primary; external liquid-handler UX claims: MEDIUM, cross-checked across 3 independent vendors + 1 industrial-automation standard)

## Scope note

This milestone is **not** "what features should a liquid-handler UI have in general" — it is narrowly: *while a Galago step is running the F.A.S.T., let the operator pause/resume/abort it live, and turn an instrument-initiated pause into an on-screen recovery prompt.* The governing design (`docs/specs/2026-10-12-galago-live-run-control-design.md`, decisions D1–D6) and `PROJECT.md`'s Active/Out-of-Scope sections already settle most of what's in vs out. This research validates those choices against how the rest of the industry does live run control, and flags where Galago's design is deliberately *narrower* than the industry norm (and why that's correct for this milestone, not a gap).

## Feature Landscape

### Table Stakes (Users Expect These)

Features operators of any lab-automation / liquid-handler control software assume exist. Missing these = the product feels broken, which is exactly the incident this milestone fixes (run paused at 0%, no in-run recovery).

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Instrument-initiated pause surfaces as an on-screen prompt, not a failure | Hamilton Venus beeps and offers Resume/Abort on any pause (MEDIUM confidence, web); Opentrons Flex 8.0+ enters a dedicated "error recovery mode" instead of cancelling (MEDIUM, web); ISA-88's `Held` state exists precisely so a paused batch is not the same as a failed one (MEDIUM, web). Today Galago does the opposite — `-645 WrongPlateType` fails the step and strands the instrument (PROJECT.md incident, 2026-10-09). | MEDIUM | Already decided: step stays open through pauses (design §2.1); requires fast-mcp's wait-through-pauses core change (§4) — **hard dependency**, see Feature Dependencies. |
| Operator-issued Pause/Resume/Abort reachable *while the step is running*, not only pre-planned | Hamilton, Tecan and Opentrons all expose live run controls during execution, not just as pre-authored script steps (web, MEDIUM). Galago's current Abort/Resume are protocol-step commands planned in advance or sent via the tool page's generic Send Command form — not the natural reaction to a live pause (design §1). | MEDIUM-HIGH | New `commandQueue.toolControl` tRPC path that bypasses the queue's enqueue/await machinery (design §6.2) and a generic `runControl` capability declaration (§6.1, D6). Depends on existing `command_queue.ts`/tool gRPC plumbing. |
| Run state visibility (running/paused, percent, reason) during the step | Hamilton shows an audible/visual pause indicator; Opentrons shows the specific error and percent/step context; ISA-88 phase status reporting (Idle/Running/Held/Complete/Aborted/Failed) is the whole point of the standard (web, MEDIUM). | LOW-MEDIUM | `StatusReply.run_state` additive Struct field (D1), 2 s polling while a controllable step runs (D2), heartbeat-retry-on-failure fix (§6.3) — the current `fetchStatus` stops the heartbeat after one failure, which must not happen during a tracked step. |
| Explicit, non-defaulted physical-decision prompts (tip broken? return liquid?) before a recovery action executes | Universal across the industry: Hamilton's per-error recovery selection, Opentrons' per-error-type recovery menu (retry/skip/ignore/cancel, each a deliberate choice), and Galago's own prior Abort/Resume design already established this pattern (fail-closed `"yes"/"no"`, nothing preselected). This milestone extends it to the live path. | LOW | Already built core-side (gated `is_tip_broken`, `return_liquid`); UI work is two-option radio with no default and a disabled action button until chosen (design §6.4). |
| Stop never silently detaches from a running instrument | Every system reviewed treats "operator wants to stop the whole run" as requiring an explicit decision about in-flight physical state (Hamilton's Abort confirm/cancel; Opentrons' cancel path; ISA-88 distinguishes Stop from Abort precisely so operators aren't surprised). Galago's current `stop()` waits for the in-flight step — it does not ask what to do with it. | LOW-MEDIUM | D4: Stop during a controllable step asks "abort the instrument run (return liquid? yes/no)" or Cancel — never leaves the instrument running while Galago forgets about it. |
| Crash-recovery path independent of the queue | If the orchestrator (galago-web) restarts mid-run, the instrument keeps going unsupervised; every reviewed system needs *some* way back in that doesn't depend on the orchestrator's in-memory step state (ISA-88 phase status is designed to be queried fresh after a controller restart). | LOW (already proven) | Tool-page Abort/Resume already exist from the prior protocol-step milestone and are kept, specifically because they don't take the motion lock (design §8, §12). |

### Differentiators (Competitive Advantage)

Not required by the incident, but align with the project's Core Value ("one shared safety policy, neither front end can drift") and make the feature reusable beyond this one instrument.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Generic `runControl` capability (D6) — not F.A.S.T.-specific | A PF400 arm or Liconic incubator that can pause mid-run gets the same modal, buttons and queue path for free; no other tool type needs its own bespoke recovery UI later (design §2, §6.1). | MEDIUM | Pays off only if a second tool ever declares `runControl`; for this milestone it's a design-quality choice, not a requirement — worth keeping because the cost over a F.A.S.T.-only path is small (one capability-declaration layer vs. hardcoding `fast` everywhere). |
| Human-rendered pause detail, not a raw error code | Hamilton and Opentrons both translate the underlying fault into an operator-actionable sentence ("No liquid detected", "Deck X: expected plate Y, found none") rather than showing a bare code — this is what actually lets an operator act in seconds instead of looking up a finding-code table. | LOW | `PauseInfo` already carries sanitized `lastEvent` detail (e.g. `wrongDetection`); `ToolPausedModal` renders it as "Deck 3: expected plate 1, found none" (design §6.4). This directly targets the motivating incident. |
| Paused time excluded from the run timeout | Lets an operator take the minutes they actually need to walk to the deck and fix a plate, without the step racing a clock that was sized for motion time, not human time. Not something the three vendor products reviewed document explicitly, but it is the correct behavior implied by ISA-88's "Held is a stable, resumable condition" semantics. | LOW (core already implements it) | Core prerequisite, not new adapter/UI work — just needs to not be broken by the Galago-side wiring. |
| Shared queue/modal pattern reused for the pause prompt (`tool_paused` alongside existing `pause`/`message`/`timer`/`user_form`) | Keeps the operator's mental model consistent — one family of modals for "the queue needs something from you," with a clearly labeled distinction ("Pause queue" vs "Pause instrument", design §6.5) instead of a bolted-on special case. | LOW-MEDIUM | Differentiator relative to building a one-off dialog; still needs its own semantics because, unlike the other four modal types, `tool_paused` must *not* resolve the step (§6.3). |

### Anti-Features (Commonly Requested, Often Problematic)

Patterns the industry does use elsewhere, that would look like reasonable asks here, but are explicitly wrong for this milestone — either because the design already rejected them or because they violate the project's safety invariants.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|------------------|-------------|
| Software auto-resume or auto-abort on pause/timeout/error/reconnect | Hamilton's "automatic recovery" mode and Opentrons' auto-fill-and-retry flows exist and look convenient; an operator might reasonably ask "why doesn't it just fix itself and continue?" | Violates the project's hard invariant (every pause/resume/abort is operator-issued, no exceptions — design §7 #1, PROJECT.md Out of Scope). A physical liquid-handling decision (tip intact? liquid still good?) made by software with no operator confirmation is exactly the failure mode the whole milestone exists to prevent. | Keep every recovery action gated behind an explicit, non-defaulted operator choice, as already decided. |
| Hard pause | The instrument API exposes a `hardPause` boolean; it looks like "the stronger version of the Pause we're already building," so a tempting scope-add. | Its physical behavior is undocumented (no OpenAPI description) — shipping it means guessing what it does to a moving liquid-handling head. ISA-88 draws a hard line between Hold (controlled, resumable) and Abort (immediate, may need recovery before restart); without knowing which bucket `hardPause` falls into, it can't be exposed safely. | Deferred (D5): Pause always calls `hard=False`; adding hard pause later is one explicit, non-defaulted choice once the F.A.S.T. team confirms behavior. |
| Per-error granular retry/skip (as in Opentrons' "retry with new tips" / "skip to next step" / Hamilton's "repeat, else exclude channel") | This is genuinely table stakes *in those products* — but those systems expose pause/retry at the level of an individual pipetting action inside one script. It's the most natural-looking next ask once live pause/resume exists. | A Galago "step" is one entire F.A.S.T. run (`Transfer`/`RunProtocol`), not a single aspirate/dispense action — there is no mid-run "skip this action, continue the rest" concept in the adapter or the instrument API as integrated. Building fine-grained retry/skip here would require instrument-level step addressing that doesn't exist in this contract, well beyond this milestone's prerequisites. | Recovery stays coarse: fix the physical problem, then Resume the whole in-flight run (tip-intact decision only) or Abort the whole run (return-liquid decision only) — matches what the instrument's own pause/resume primitive actually supports. |
| Simulating a pause in simulated mode, for UI testing without hardware | Looks like free test coverage — every other UI feature in this codebase gets a simulated-mode test path. | `ToolServer` simulates `Transfer` as a sleep with nothing to pause; faking a pause mid-sleep is non-trivial plumbing with no production behavior behind it. Design explicitly marks this out of scope, as a candidate follow-up only (§5.5). | Supervised live acceptance test is the real gate for this milestone (design §9 #3); a simulated-mode pause test hook is backlog, not v2. |
| Fixing galago-core F5 (queue re-ran one `transfer` 3 times) and F3 (run UI hides tool errors) while touching this same code | Both bugs live in exactly the code this milestone touches (`command_queue.ts`, run UI) — tempting to fold in "while we're here." | User explicitly decided (2026-10-12) to keep both as tracked debt, out of this milestone, to keep the live-control change reviewable and scoped. | Leave as tracked debt per PROJECT.md Out of Scope; file separately if encountered during implementation. |
| Full cross-machine / network-wide instrument-ownership enumeration as part of this milestone | Live run control touches the same "who owns the instrument" question as the existing single-owner lock; it's tempting to harden it alongside. | Already explicitly out of scope and solved at minimum-viable level by the host-keyed lock file (§11 #2 in PROJECT.md); unrelated to pause/resume/abort UX. | Leave as-is; known limitation, not this milestone's problem. |

## Feature Dependencies

```
fast-mcp core: "wait through pauses" (on_pause callback, pause episodes, timeout excludes paused time)
    └──requires (hard blocker)──> Adapter §5.2: Transfer/RunProtocol call core with wait-through-pauses on
                                      └──requires──> Step stays open through an instrument pause (table stakes #1)
                                                         └──enables──> on-screen tool_paused modal (doesn't resolve the step)

Adapter §5.1: new Pause command + control commands skip the motion lock
    └──requires (core, already shipped)──> FastService state gates (pause/resume/abort gated by run state, Refused otherwise)
    └──independent of──> §5.2 (can be built/tested now against a mocked FastService, design §10 item 2)

galago-core §6.1: runControl capability declaration
    └──requires──> §6.2: toolControl tRPC procedure (targets the tool of the currently running step)
                      └──requires──> D1: StatusReply.run_state (tool_base.proto change) OR an equivalent GetRunState read path
                                         └──enables──> §6.3: 2 s run-state polling + heartbeat-retry fix
                                                           └──enables──> tool_paused modal triggered on a new pause episode

Run-page control bar + ToolPausedModal (§6.4)
    └──requires──> runControl capability declared (§6.1) AND run_state polling live (§6.3)
    └──enhances──> operator reaction time to the motivating incident (deck-3 WrongPlateType)

D3: abort/resume removed from protocol step editor
    └──conflicts with (superseded)──> the prior milestone's protocol-step Abort/Resume as the primary recovery path
    └──does NOT conflict with──> crash-recovery Abort/Resume kept on the tool page (different code path, no motion lock)

D4: Stop-during-step confirmation ("abort, return liquid? yes/no" or Cancel)
    └──requires──> Abort control command (§5.1) already wired
    └──independent of──> run-state polling (Stop doesn't need live state to ask its question)
```

### Dependency Notes

- **The single hard blocker is the fast-mcp core change.** Everything in galago-core (§6.1–6.6) and the adapter's control path (§5.1, §5.3–5.5) can be built and tested in parallel against a mocked `FastService` (design §10, item 2) — only §5.2 (wiring `Transfer`/`RunProtocol` to actually wait through pauses) needs the real core API. This is why the design's own order-of-work puts the core change on a separate track rather than gating all work on it.
- **Control commands bypassing the motion lock enables, not conflicts with, long-running commands holding it.** `Pause`/`Resume`/`Abort` reach the instrument concurrently with an in-flight `Transfer`/`RunProtocol` precisely because the state gates (not the motion lock) are what keeps them safe — this is a deliberate design choice (§5.1), not an oversight.
- **D3 (remove from step editor) depends on D6 (generic runControl) existing as the replacement**, so operators aren't left without *any* way to issue these commands mid-protocol-authoring — the tool page remains the fallback for crash recovery specifically because it's a different, lock-free code path (§5.1, §8).
- **Run-state polling (§6.3) is a prerequisite for the pause prompt, not an independent feature** — the modal only exists because `run_state` is now observable; without D1 there is nothing to poll and no event to trigger `tool_paused`.

## MVP Definition

Because this is a scoped milestone (not a 0-to-1 product), "MVP" here means: the minimum slice that closes the motivating incident and is explicitly required by PROJECT.md's Active requirements and the design's D1–D6.

### Launch With (v1 — this milestone)

- [ ] Step stays open through an instrument-initiated pause (no step failure on pause) — directly closes the 2026-10-09 incident
- [ ] On-screen `tool_paused` prompt with human-rendered reason/detail, that does not resolve the step
- [ ] Live Pause/Resume/Abort control bar on the running step, each decision non-defaulted
- [ ] `runControl` capability + `toolControl` tRPC path, generic (not hardcoded to F.A.S.T.)
- [ ] `StatusReply.run_state` (D1) + 2 s polling (D2) + heartbeat-retry fix
- [ ] `abort`/`resume` removed from the protocol step editor (D3), kept on the tool page for crash recovery
- [ ] Stop-during-step asks abort(return liquid?)/cancel, never silently detaches (D4)
- [ ] Soft pause only (D5) — no `hard` decision exposed yet
- [ ] Supervised live acceptance: reproduce the deck-3 scenario, pause→resume, pause→abort (design §9 #3)

### Add After Validation (v1.x)

- [ ] Hard pause, once the F.A.S.T. team documents `hardPause`'s physical behavior (D5 deferred path)
- [ ] Simulated-mode pause test hook (drive `run_state` to paused without hardware) — named candidate follow-up in the design (§5.5)
- [ ] A second `runControl`-capable tool type (e.g. PF400, Liconic) to prove the generic path actually generalizes

### Future Consideration (v2+)

- [ ] galago-core F5 (queue re-ran a `transfer` 3 times) and F3 (run UI hides tool errors) — tracked debt, deliberately not bundled here
- [ ] Fine-grained per-action retry/skip (would require instrument-level step addressing not present today)
- [ ] Full cross-machine instrument-ownership enumeration beyond the host-keyed lock file
- [ ] C#/on-instrument reimplementation of the core (integration-design §14 "Stage C")

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Step stays open through pause (wait-through-pauses wiring) | HIGH | MEDIUM | P1 |
| On-screen pause prompt (`tool_paused` modal) | HIGH | MEDIUM | P1 |
| Live Pause/Resume/Abort control bar | HIGH | MEDIUM-HIGH | P1 |
| `run_state` transport + polling + heartbeat fix | HIGH | LOW-MEDIUM | P1 |
| Stop-during-step confirmation | HIGH | LOW-MEDIUM | P1 |
| Remove abort/resume from step editor | MEDIUM | LOW | P1 |
| Generic `runControl` (vs. F.A.S.T.-only) | MEDIUM | LOW extra (over F.A.S.T.-only) | P1 (cheap enough not to defer) |
| Human-rendered pause detail | HIGH | LOW | P1 |
| Hard pause | LOW (no confirmed use case yet) | MEDIUM (unknown instrument behavior) | P3 |
| Simulated-mode pause test hook | LOW | MEDIUM | P3 |
| Per-action retry/skip | MEDIUM (industry-standard elsewhere) | HIGH (needs instrument step addressing) | P3 / out of scope |

**Priority key:**
- P1: Must have for this milestone (already decided D1–D6 / PROJECT.md Active)
- P2: Should have, add when possible (none identified beyond P1 for this milestone — it's tightly scoped)
- P3: Nice to have, future consideration (explicitly deferred by the design or by user decision)

## Competitor Feature Analysis

Treat these less as "competitors" and more as prior art for the interaction model — none of these products run *inside* a multi-instrument workcell scheduler the way Galago does, so the comparison is about recovery-UX conventions, not head-to-head features.

| Feature | Hamilton Venus (MEDIUM confidence, web) | Opentrons Flex 8.0+ (MEDIUM confidence, web) | Tecan FluentControl (MEDIUM confidence, web) | Galago v2 approach |
|---------|--------------------------------------|----------------------------------------------|-----------------------------------------------|---------------------|
| Pause → operator prompt | Per-step configurable auto/semi-auto/manual recovery; audible pause alert, Resume/Abort | Dedicated "error recovery mode," per-error-type options | Dialog: ignore-and-continue vs abort (coarser than the other two) | On-screen `tool_paused` modal with human-rendered detail; doesn't resolve the step until operator acts |
| Recovery granularity | Per-error-type, sometimes per-channel (e.g. exclude a channel) | Per-action (retry same/new tips, skip to next step, ignore, cancel) | Whole-script (continue-with-errors or abort) | Whole-run only (resume in-flight run, or abort it) — matches the instrument's own run-level pause/resume primitive, no per-action addressing |
| Physical decision explicitness | Implicit in the chosen recovery mode (configured in advance per method) | Explicit per incident (what to retry/skip) | Implicit (single ignore/abort toggle) | Explicit and non-defaulted every time (tip broken?/return liquid?), independent of how the method was authored — closer to Opentrons' explicitness, applied at whole-run granularity like Tecan |
| Stop/Abort distinction | Abort requires a confirm click | Cancel protocol run is explicit per error-recovery screen | Abort is one of two dialog choices | Stop asks "abort (return liquid?) or cancel" — closest to Hamilton's confirm-gated abort, with the added physical decision |
| Auto-recovery | Supported for some errors (automatic mode) | Supported for some errors (auto-fill-and-retry style flows) | Not clearly documented | Explicitly rejected (design §7 #1) — this is Galago's deliberate point of difference, driven by the project's "software never decides" invariant, not a parity gap |

**Takeaway:** Galago's design is intentionally coarser-grained (whole-run resume/abort, not per-action retry/skip) and stricter (no auto-recovery at all) than any of the three products reviewed. Both choices are correct for this milestone: the instrument/adapter contract only supports run-level pause/resume/abort today, and the project's governing safety invariant (operator-only recovery, no software-initiated action) is stronger than any of the three vendors enforce.

## Sources

- `docs/specs/2026-10-12-galago-live-run-control-design.md` (HIGH — curated primary source, this project's own settled design, D1–D6)
- `.planning/PROJECT.md` (HIGH — curated primary source, Active/Out-of-Scope requirements and Key Decisions table)
- Hamilton Venus / Microlab STAR error handling and run-control behavior — web search, cross-checked across Illumina's Hamilton reference guide and labautomation.io forum threads (MEDIUM confidence, unverified against primary Hamilton docs beyond the Illumina PDF excerpt)
- Tecan FluentControl error-handling dialogs and known retry/abort gaps — web search across Tecan's own ReadMe/knowledge-portal pages and a third-party dev-tooling issue discussing a recovery-policy model (MEDIUM confidence)
- Opentrons Flex error recovery mode (8.0+) and `pause()` semantics — web search, Opentrons' own documentation and GitHub release notes (MEDIUM confidence)
- ISA-88.01 / IEC 61512-1 batch-control state model (Idle/Running/Held/Complete/Aborted/Stopped) — web search across several industrial-automation knowledge-base summaries, not the ISA standard text itself (MEDIUM confidence; treat exact state-name claims as indicative of the convention, not a verbatim standard quote)

---
*Feature research for: Galago live F.A.S.T. run control (v2 milestone)*
*Researched: 2026-10-12*
