# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

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
