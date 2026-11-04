# Milestones

## v2 STACK Tool & STACK↔F.A.S.T. Handoff (Shipped: 2026-11-04)

**Phases completed:** 4 phases, 20 plans, 31 tasks

**Key accomplishments:**
- Written design spike for the F5-safe step-key ledger: three D-01 questions answered against core 934a621 with executed probe evidence, six amendments (done-set mirrors `_task_ended`, acknowledge guid from `latch_status()` first), and one binding contract for plans 05-02..05-07.
- A real-mode `Transfer` now runs plan, write-ahead `submitting` record, `execute_transfer`, `started`, one `wait` and `done` through a new core-free flock-and-atomic-write step ledger, and Phase 4's blanket no-motion AST rule is replaced by XFR-05 call-site rules (single sites, no loop, after the claim, no indirection) with 13 new planted-violation tests.
- The core-free step ledger now has a 90-test contract (fail closed, atomic, flock, 0700/0600, path resolution, fingerprint), the pure `decide()` repeat-key state machine from 05-SPIKE.md 6b, and the release / outcomeUnknown / find-by-guid / 7-day-retention transitions, all written test first.
- `GetFailureLatch` now reads `latch_status()` 1:1 (including `submit-<hex>` and `state-<hex>` ids, mid-transfer), `AcknowledgeFailure` reaches the core only for an exact `"yes"` through a single AST-pinned call site, and every latching Transfer error names the guid to acknowledge from `latch_status()` first, with the result's own guid labelled "task guid" and the latched guid kept inside the 300-character cap.
- A step key is deleted only when execute_transfer returns one of the core's real Refused, Rejected, NeedsInput or ReadFailed classes (by isinstance); Lost(submitOutcomeUnknown), any other Lost and any unknown shape become a permanent outcomeUnknown record carrying the latch guid, and a relative `Config.ledger_dir` now fails Configure before the owner is swapped.
- Transfer now runs every repeated step key through `decide()`: a different request is INVALID_ARGUMENTS, a recent done+ran is replayed, a started record is re-attached with a read-only bounded `wait_transfer` loop, everything else is refused with the guid and the next action, and across a tool-server restart a live ran is SUCCESS flagged `reattachedAfterRestart` while every other outcome tells the operator to inspect the arm.
- A 12-scenario fake-core matrix proves that no repeat, retry, timeout or restart sends a second `execute_transfer` or acknowledges on its own, and the BUSY-read tests now run against the real Transfer blocked inside the core wait; the full gate is green at 478 tests with no adapter behaviour change.
- GAL-02 script-mode protocol as galago-core export JSON (27 sim-default parameters, per-run `-in`/`-out` STACK step keys) with a node vm harness and fake-core tests proving a re-dispatched STACK step never causes a second accepted submit.
- Read-only `gal-02-dep02-check.sh` gate (six checks, tested on fixture trees) plus the full GAL-02 operator runbook for Part 2a/2b, with the D-07 limit stated verbatim, a hardware-refusal preflight and a ready Findings log.
- A Galago-simulated GAL-02 run completed all four rows through galago-core's real queue, and a simulated re-dispatch of the in-leg STACK step returned SUCCESS without writing a ledger. Findings rows G0, 2a-1, 2a-2 and 2a-3 are recorded as PASS.
- A GAL-02 run with the real-mode STACK tool against the loopback PAC simulator completed, and a re-send of the completed in leg replayed with the same task guid and no second POST, proven by a manager submit counter that was calibrated first (+1 on the in leg, +0 on the re-send). Findings rows 2b-0..2b-5 are recorded as PASS.
- Executable fail-closed live pre-flight gate (8 checks incl. core-pin assert and owner-lock probe through the pinned STACK core), the supervised-live runbook with per-event GO gates and recovery drill, and a falsification-test module that proves the gate cannot pass falsely — the real-host pre-deploy run BLOCKs on exactly the two known gaps (service-venv core pin, missing F.A.S.T. store entry).
- STACK production stack deployed in the LIVE-04 safe order — DEP-02 core (`934a621`) into the service `.venv` via an operator-approved local-clone waiver, credentials + backup + restart, FAST-first/STACK-Last reconnect closing the D-12 store gap, and `galago-web` rebuilt on a new image (anchor `93821723…` → `2f609032…`) with all five findings rows PASS and the four-timestamp safe-order proof.
- The milestone's first live motion: exactly one supervised live STACK `Transfer` on `stack2-6` reached `ran` — with the typed go recorded, reads-first parameters, one submission verified by ledger and log, and no restart at any point.
- The milestone's end-to-end live proof: the supervised two-plate GAL-02 handoff ran STACK -> F.A.S.T. -> STACK to SUCCESS on hardware, under the typed-go gates and the full D-11 discipline, with all four STACK legs submitted exactly once and the findings log complete (13/13 PASS).

---

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
