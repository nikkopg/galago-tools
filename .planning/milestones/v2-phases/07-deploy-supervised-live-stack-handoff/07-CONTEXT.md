# Phase 7: Deploy & Supervised Live STACK + Handoff - Context

**Gathered:** 2026-11-02
**Status:** Ready for planning

<domain>
## Phase Boundary

Deploy the DEP-02 galago-core build in the safe order on the existing live stack, then prove —
with the user present and explicit per-event go-aheads — (1) a supervised, runbook-gated live
STACK `Transfer` on `stack2-6` (manager `10.150.1.125:5005`) and (2) a supervised live GAL-02
STACK → F.A.S.T. → STACK handoff on the hardware. Requirements LIVE-08, LIVE-09, LIVE-10. This is
the only phase allowed to send live STACK motion or target `10.150.1.125` / `stack-server`.

</domain>

<decisions>
## Implementation Decisions

### DEP-03 go/no-go
- **D-01:** Live runs proceed **without DEP-03** (no galago-core operator AcknowledgeFailure UI
  control, F3 tool-error display, or F5 root cause required first). LIVE-08..10 run on the DEP-02
  core. — **Reversibility:** reversible — waiting for DEP-03 later only changes what UI affordances
  exist during a future session, not what was proven live.
- **D-02:** Operator clearing of a latched failure live happens from the **stack-manager UI**
  (user: "think it's still possible from stack-manager-ui"); the adapter-side `AcknowledgeFailure`
  tool-page command remains the in-Galago fallback. The runbook documents the manager-UI path as
  the primary live recovery route with the recorded guid + `"yes"` arm-inspected decision.

### Deploy procedure
- **D-03:** Deploy on **forb01**, same host as the F.A.S.T. deployment (core in `.venv`,
  `galago-tools` systemd user service, manager on `:8081`), reusing the v1 LIVE-04 safe-order
  procedure.
- **D-04:** DEP-02 core install is a **pin bump** in the fork to the DEP-02 build lineage
  (galago-core `a5fa75f`) into the service `.venv`, followed by the `galago-tools` restart and the
  `galago-web` rebuild — not a local-clone install.
- **D-05:** stack-mcp closure is enforced by a **pre-flight check that refuses** the session if a
  lock is held (reuse the Configure lock-holder failure message as the detection signal) — the
  runbook does not actively stop stack-mcp.
- **D-06:** **Backup each restart**: every restart in the session prefixes a timestamped copy of
  the relevant service/tool logs (F.A.S.T.log precedent, extended to the STACK/manager logs) into
  a backups directory.

### Runbook scope & live run order
- **D-07:** The live runbook is a **new file** `docs/runbooks/gal-07-live-handoff.md`; the
  Phase 6 simulated-session runbook `docs/runbooks/gal-02-handoff.md` stays pristine as reference
  and its `10.150.1.125|stack-server` refusal remains in force there.
- **D-08:** The runbook gets an **executable exit-code pre-flight gate** (like
  `docs/runbooks/gal-02-dep02-check.sh`) verifying live preconditions: correct manager host
  (`10.150.1.125:5005` / `stack2-6`), stack-mcp absent, DEP-02 build installed, core reachable.
- **D-09:** Staged order: **pre-flight + deploy → supervised live single `Transfer` (LIVE-09,
  rehearsal) → supervised live GAL-02 handoff on hardware (LIVE-10)**. The rehearsal catches any
  motion-path surprise while only one command is in the blast radius.

### Approval & live protocol
- **D-10:** **Explicit per-event go-ahead**: each live event (deploy, LIVE-09, LIVE-10) waits for
  a typed go-ahead from the user, recorded in the session log with a timestamp; no auto-advance
  passes a GO gate.
- **D-11:** Drill for an **ambiguous or failed live outcome**: stop the session, inspect the
  ledger state and the core in-flight guard, operator inspects the arm, then clear via the
  manager UI affected state (D-09 restart rule recalled: a restart-during-transfer is reported as
  needing arm inspection, never replayed as SUCCESS).
- **D-12:** **Pre-store check** guards against the Phase 6 UAT watch item (a tool vanishing from
  the dev tool-store when another tool was reconfigured): the pre-flight/first-run checklist
  verifies every tool in the GAL-02 protocol (STACK and F.A.S.T.) is configured in the tool store
  in an up-front-decided configuration order before a run is started.

### the agent's Discretion
- Exact contents/format of the runbook sections and the pre-flight script implementation details
- Backup directory naming and log file selection specifics
- How the pre-store check is expressed (script assertion vs runbook checklist) — planner's call
- Internal ordering of the three-part check script assertions

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase & requirements
- `.planning/ROADMAP.md` § Phase 7 — goal, success criteria, DEPs, notes (tool-server PID tracking)
- `.planning/REQUIREMENTS.md` § LIVE-08..LIVE-10 — the three live requirements this phase closes
- `.planning/PROJECT.md` § Validated — v1 LIVE-04 safe-order deploy precedent and forb01 topology

### Runbooks (authored in Phase 6)
- `docs/runbooks/gal-02-handoff.md` — the simulated-session handoff runbook; reference for tone,
  structure, and the still-in-force pre-Phase-7 host refusal
- `docs/runbooks/gal-02-handoff.protocol.json` — the importable GAL-02 protocol (27 params) whose
  store/config values the live pre-store check must verify
- `docs/runbooks/gal-02-dep02-check.sh` — the exit-code gate script pattern the live pre-flight
  mirrors

### Research & decisions
- `.planning/research/SUMMARY.md` § Addendum — core limits and re-checked findings from Phase 5
- `.planning/state.json` + `.planning/STATE.md` § Decisions — D-07 live-mode semantics (restart
  warning, `reattachedAfterRestart`), orphaned in-flight guard → Phase 7 runbook agreement

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `docs/runbooks/gal-02-dep02-check.sh` — exit-code gate script skeleton with host-refusal
  assertions; the live pre-flight is a new sibling script with inverted assertions
- `docs/runbooks/gal-02-handoff.md` — runbook structure, protocol import steps, and findings-row
  format to extend for a post-live report
- `tools/stack/ledger.py` — the persisted F5 ledger; runbook recovery drills read its state
- v1 deployment runbook trail in PROJECT.md Validated (forb01, `.venv`, systemd user service)

### Established Patterns
- Safe deploy order (core → service `.venv` → `galago-tools` → `galago-web`) is a proven v1 SC and
  a STATE.md carried decision; tool-server restart via the manager page (track listener PID, not
  only service MainPID) is a ROADMAP note
- Runbook + protocol-JSON + check-script triple pattern from Phase 6
- Findings rows (G0/2a/2b style) record supervised-run evidence with PASS criteria

### Integration Points
- galago-core store configuration (STACK-PACSIM/STACK-SIM/FAST-SIM tool entries) — pre-store check
  target
- `galago-web` rebuild after service restart (LIVE-08 order)
- STACK manager `10.150.1.125:5005` for state reads and operator recovery

</code_context>

<specifics>
## Specific Ideas

- Operator recovery path without galago-core DEP-03 UI is the **stack-manager UI** (user-stated
  fact; document it as the primary route in the runbook)
- Live runs are user-present sessions; each event separately approved (explicit per-event rule)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 07-Deploy & Supervised Live STACK + Handoff*
*Context gathered: 2026-11-02*
