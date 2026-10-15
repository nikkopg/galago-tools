# Milestones

## v1 Live Run Control (Shipped: 2026-10-16)

**Delivered:** An operator's Pause, Resume and Abort reach a F.A.S.T. run while its Galago step is
still in flight, the adapter reports live `run_state` to galago-core, a running step stays open
through an instrument pause, and the stack is proven live on the instrument.

**Phases completed:** 3 phases, 18 plans, 43 tasks
**Timeline:** 2026-10-13 → 2026-10-16 (4 days), 119 commits (`309a55e`..`07a081d`)
**Code:** 6 files changed under `tools/`, `scripts/`, `interfaces/` (+3,159 / −177); 147 tests
**Closeout:** verified_closeout — all 3 phases verified `passed`, 17/17 requirements, 85/85 threats
closed (`threats_open: 0`), open-artifact audit clear

**Key accomplishments:**
- `FastServer.ExecuteCommand` override lets Pause/Resume/Abort reach the instrument mid-run without
  touching `tools/base_server.py`; soft-only Pause, two-path Resume, fail-closed decisions.
- `StatusReply.run_state` reports live state, percent and pause detail; any read failure collapses
  to `{state: unknown}` so the heartbeat never fails.
- A reusable AST invariant, with planted violations, proves no adapter code path pauses, resumes,
  aborts or checks instrument state on its own.
- Re-pinned fast-mcp `b30b38d`: Transfer/RunProtocol wait through pauses, paused time is excluded
  from the timeout, and an operator abort reads "run aborted by operator at <p>%".
- Deployed in the safe order and proven live with an operator: deck-3 prompt → fix → Resume,
  Pause → Resume, Pause → Abort, and `galago-web` restart mid-run → tool-page recovery.
- Three live-found defects fixed and re-run (galago-core `-1` plate prompt, adapter `NoError (0)`
  suffix, galago-core queue re-dispatch); crash-recovery Resume hardened (CR-01) and redeployed
  2026-10-16.

**Known caveats carried forward:**
- WR-02: `_is_no_error()` uses `error_code in (None, 0)` (true for `False`) — medium, reporting
  integrity only; v2 debt.
- T-03-05/T-03-08 closed as a logged exception: on 2026-10-16, at the user's request, Claude sent
  `Configure` to reconnect tools after the CR-01 redeploy (no run in flight, same configs, no
  motion). Rule now: Claude sends `Configure` only on explicit request and only with no run in
  flight. A code backstop (refuse `Configure` mid-run) is a v2 candidate.
- fast-mcp `fix/run-recovery-gate` not on GitLab; branches on all repos not pushed.

**Deployed state (forb01):** core `b30b38d` in the service `.venv`; `galago-tools` at HEAD incl.
CR-01 (MainPID `1940146`); `galago-web` from galago-core's queue-fix build.

**Archive:** `milestones/v1-ROADMAP.md`, `milestones/v1-REQUIREMENTS.md`, `milestones/v1-phases/`

---
