---
created: 2026-11-03
source: Phase 7 operator debrief (the row 3a-8 conclusion + the sequential-fleet limitation the operator ran into at the post-milestone practice cycles)
resolves_phase: ""
---

# galago-core scheduler: per-toolId concurrency lanes for live two-tool runs

## The problem (from Phase 7 evidence)

The run queue in galago-core keeps a single global running-step slot
(`_runningStep`, `controller/server/command_queue.ts`) with one busy-loop; a
queue start while another step runs is ignored ("already running; nothing
was dispatched again"). `advancedParameters.runAsynchronously` exists on every
command row but is only ever written as literal `false`
(`runs.ts:117`, `protocol-script-executor.ts:30`) — no scheduler read consumes
it: it is a dead flag.

So today, within a run, the F.A.S.T. liquid leg (73 s inside the instrument) and
the STACK arm motion cannot overlap — even though the tool servers themselves
are frictionless for concurrency (separate ports, separate motion locks, separate
state files):
- the STACK tool server's motion lock is stack-only (`tools/stack/server.py`
  `_MOTION_LOCK`);
- the F.A.S.T. tool server carries its own run-state machinery on :40001.

For a supervised live cycle, the operator ultimately wants:

```
in1 (STACK) → in2 (STACK) → { FAST liquid (73s) ∥ STACK goto-safe } → out1 → out2
```

saving ~10 s per cycle (the F.A.S.T. window fully hides a short STACK maneuver)
and a cleaner hand-off posture after each in-leg.

## What has to change (galago-core)

- **Scheduler lane split** — one running-step per-`toolId` lane instead of a
  single global slot (or a small DAG view per run: F.A.S.T. lane + STACK lane
  with fork/join semantics at the desired fork point in the protocol).
- **Modal-state entanglement** — today `variable_assignment` / `showUserForm` /
  pause/resume weave through the interleaved stepper. With lanes, these need a
  home (probably: only stack-lane commands may see certain variables; the F.A.S.T.
  lane is env-isolated); `skipExecutionVariable`-based warping and `user_form`
  ticks need a lane-aware rewrite or a promise that non-toolIO steps only live
  on the stack lane.
- **Evidence discipline** — findings-row accounting (the row 3a-3
  "one ledger record + one attempt line per leg" shape) picks up 2 timestamps per
  leg with possible overlap; the ledger keeps one record per minted key (league
  intact), and log-line accounting gains one slot per parallel leg (still monotone
  per lane).
- **Threat register update** (new entry, needs its own file + the D-11 drill
  expansion): the F.A.S.T. internal carriage (`:5003`) moves concurrently with
  the STACK arm; the operator guarantees no physical interference (the tray's
  prism space is disjoint) — but the *ledger guarantee* currently chains on
  "one motion at a time in my run" and needs the per-lane version of the same
  audit trail.

## What to NOT break

- The step-key ledger's per-key one-shot safety (T-07-10/XFR-05) — unchanged:
  each leg still mints its own key in its own lane; the replay-window rule
  stays per-key.
- The D-11 drill (a latched failure → operator inspects the arm while nothing
  else moves) — needs an explicit lane-halt: **both lanes** freeze when one lane
  reports a failure that would latch, so an operator inspecting the arm never
  shares the physical space with a still-running F.A.S.T. carriage.
- The typed-GO (D-10) gates — a run that wants parallelism needs its own GO
  framing ("two-tool live run") rather than inheriting the per-lane GO-gate
  count; the runbook's four-per-run sequence proofs re-shape into a
  per-lane "ordered within my lane" proof.

## Suggested execution order (if picked next cycle)

1. galago-core queue: land a `--lane` dimension (or toolId-keyed lanes) and
   start the moving steps are the same command shape they carry today;
   regression: the sequential `run-start` path must be unchanged for
   single-tool runs.
2. galago-core runs/scheduler: implement the fork/join protocol-level syntax
   (either a `useParallelToolLanes: true` in the protocol's `advancedParameters`
   for the visual/sample (script) protocols, or a step-level `lane: fast|stack`
   annotation), gated behind a scoped feature flag.
3. Add the new threat-model entry, update the runbook (docs/runbooks/) with a
   parallel-shape variant of the two-plate cycle as a documented preparation,
   then a separate typed-GO for the first live parallel run.

## Volume

- The F.A.S.T. liquid transfer is already the first concurrent leg design; this
  unlocks pool/conveyor kind of patterns for future workcells beyond
  Phase 7's exact flow.

## Acceptance

- [ ] A live two-tool run where the STACK arm completes a short maneuver while
      the F.A.S.T. executes its internal transfer, with recorded per-lane
      evidence rows and one clear account of the run's ledger keys.
- [ ] The ledger's per-key one-shot safety and the D-11 lane-halt behavior both
      verified in the falsification suite (gal02/gal07 tests).
- [ ] The threat-model entry merged and the runbook's GO-gate framing updated.
