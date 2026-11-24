# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v2 — STACK Tool & STACK↔F.A.S.T. Handoff

**Shipped:** 2026-11-04
**Phases:** 4 | **Plans:** 20

### What Was Built
- The STACK gRPC adapter (`tools/stack/`): reads, estimate, simulated mode, and the F5-safe
  step-key ledger (one submission per key, re-attach on re-execution, outcomeUnknown on loss) —
  90-test ledger contract + 12-scenario fake-core matrix, all test-first.
- The GAL-02 workflow: the script-mode protocol (per-run minted `-in`/`-out` keys), the
  read-only DEP-02 gate, the operator runbook, and the simulated + loopback-PAC proof runs.
- The live proof: the fail-closed pre-flight gate, the supervised live runbook with typed-GO
  gates, the LIVE-09 rehearsal (`ran`), and the two-plate LIVE-10 handoff to all-legs SUCCESS —
  findings log 15/15 PASS incl. the post-phase reconciliation.
- Post-milestone same-day hardening (recorded in the runbook, outside the milestone scope): the
  step-key auto-mint (blank key → timestamp+random mint), the visual-protocol fixes, the
  owner-lock corroboration fail-closed fix, and the official product icons.

### What Worked
- The offline falsification harness before any store import (the broken id-12 script never
  reached a queue attempt).
- The executor/hand-off split at the typed-go gates: the operator's own hands on every motion;
  the agent's read-only verification from ledger/log/PID state — the D-11 lineage held through
  two movementErrors and a latch.
- The ledger-vs-log reconciliation discipline (one record + one attempt line per leg) caught the
  replay-window reply class and the invalidSource refusals as separate phenomena.
- The three-way repo split (adapter here / queue+UI in galago-core / core gaps in
  stack-automation-layer) held through the live cycles.

### What Was Inefficient
- The visual protocol was built wrong three times before the operator's two-plate correction
  surfaced (labware profile + transfer profiles + the missing F.A.S.T. leg); a protocol-authoring
  preview that understood visual mode would have caught the shape earlier (the store's preview
  only executes scriptContent).
- The fixture's environment assumption (the pytest interpreter importing the pinned core) cost a
  post-merge failure cycle in Wave 1.
- The interrupted 07-02 executor left evidence rows uncommitted; the recovery worked but the
  reconciliation cost a full read-back.
- The verification staleness from the post-verification adapter commit forced an override
  closeout instead of a fresh re-verification pass.

### Patterns Established
- Step-key auto-mint: the authoring surface omits the key; the adapter mints timestamp+random —
  one-shot safety without the operator knob.
- The live pre-flight's owner-lock probe accepts the galago single-owner state and corroborates
  any fallback interpreter's lock-dir resolution fail-closed.
- Practice cycles after a milestone get their own findings rows (3a-4/3a-5 style) — never silent
  queue runs.
- The tool-store protocol import is verified by an offline node harness (Function(params,
  galago)) before it touches the live store.

### Key Lessons
- The manager's `InvalidSource` collapses unknown-labware-profile, unresolvable-nest and
  wrong-source-position into one code — read the manager's own log lines, not the adapter's hint,
  when triaging.
- A visual protocol's fixed step keys make it single-shot by construction; repeatability needs
  minted keys (script mode or variable_assignment steps).
- The systemd unit is an editable install: a service restart IS the adapter deployment — no uv
  dance.

### Cost Observations
- Model mix: mostly sonnet-class executors + one opus verification pass; the live supervision
  ran main-session (operator-delegated).
- Sessions: one long execute session (4 waves) + verify-work + the post-milestone fixes; the
  interrupted-executor recovery added ~1 h.
- Notable: the offline protocol harness caught a syntax-broken import before any live attempt —
  the cheapest save of the milestone.

## Milestone: v1 — Live Run Control

**Shipped:** 2026-10-16
**Phases:** 3 | **Plans:** 18 | **Sessions:** several (not tracked precisely)

### What Was Built
- `FastServer.ExecuteCommand` override: Pause/Resume/Abort reach an in-flight run without touching
  `base_server.py`; soft-only Pause, two-path Resume, fail-closed decisions.
- `StatusReply.run_state` with state, percent and pause detail; heartbeat never fails.
- Reusable AST safety invariant with planted violations (no software-initiated control, no
  adapter-side state checks).
- Wait-through-pauses on the re-pinned core, paused time excluded from the timeout, operator-abort
  wording.
- Safe-order deploy and four supervised live scenarios (LIVE-04..07) on the instrument.

### What Worked
- Failing real-mode test before the `ExecuteCommand` override: the simulated test could never have
  caught the BUSY gate.
- Stop → fix → gate → redeploy → rerun (D-14) on live failures; failed attempts kept as history.
  It surfaced three real defects (two in galago-core, one in the adapter).
- Re-deriving live evidence from logs, not operator summaries. That caught timing discrepancies,
  and at close it showed LIVE-07 never touched the CR-01 path.
- Re-verifying stale phases before archiving instead of overriding.

### What Was Inefficient
- A gap-closure fix (02-05) landed after Phases 1 and 3 were verified, forcing re-verification and
  a redeploy decision at milestone close.
- Review dispositions were not updated when a later plan fixed the finding (Phase 1 WR-01).
- Security audits ran only at milestone close; all 85 threats were planned but no SECURITY.md
  existed until then.
- The `:8081` manager page restarted tool servers outside the runbook and overwrote `F.A.S.T.log`.

### Patterns Established
- Track the tool-server listener PID, not just the service MainPID; back up logs before restarts.
- Read galago-web state read-only via a `docker cp` copy of `queue.db`.
- Every motion step needs the operator's literal go-ahead; restarts too.
- Procedural safety rules need either a code backstop or an explicit logged exception.

### Key Lessons
1. Run `/gsd-secure-phase` at each phase's end, not at milestone close.
2. When a later plan fixes an earlier phase's code, update that phase's review disposition and
   re-verify it in the same step.
3. Before a live rerun, check which code path the scenario actually exercises. LIVE-07 used the
   in-flight path, so rerunning it would not have tested CR-01.
4. A verifier's claim about runtime behavior needs a log check; the Phase 3 re-verifier got the
   Resume path wrong.

### Cost Observations
- Model mix: orchestration on Opus; executors, verifiers and auditors on Sonnet.
- Notable: parallel per-phase verifiers and security auditors kept the close-out fast.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1 | several | 3 | First milestone planned per repo; live acceptance with D-14 fix/rerun cycles |

### Cumulative Quality

| Milestone | Tests | Coverage | Zero-Dep Additions |
|-----------|-------|----------|-------------------|
| v1 | 147 | not measured | 0 (stdlib only; fast-mcp re-pin) |

### Top Lessons (Verified Across Milestones)

1. (Needs a second milestone to cross-validate.)
