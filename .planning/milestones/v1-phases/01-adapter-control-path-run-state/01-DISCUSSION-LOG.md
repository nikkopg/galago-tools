# Phase 1: Adapter Control Path & Run State - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-12
**Phase:** 01-adapter-control-path-run-state
**Mode:** `--auto` (recommended option selected for every question, no user prompts)
**Areas discussed:** ExecuteCommand override shape, Resume in-flight detection, run_state shape & source, Core pin during Phase 1, Invariant scope, Simulated pause hook

---

## ExecuteCommand override shape

| Option | Description | Selected |
|--------|-------------|----------|
| Peek oneof before parseCommand; control path skips isReady/setStatus, dispatches via `_dispatchCommand` | Keeps `_check_args`, simulated branch and tool-type check; base path untouched for others | ✓ |
| Temporarily patch `self.status` around `super().ExecuteCommand` | Racy with the in-flight Transfer's `finally` | |
| Edit `base_server.py` | Out of scope (shared by every tool type) | |

**Auto-selection:** `[auto] ExecuteCommand override — Q: "How do control commands bypass the readiness gate?" → Selected: "Peek oneof before parseCommand" (recommended default)`

## Resume in-flight detection

| Option | Description | Selected |
|--------|-------------|----------|
| Non-blocking `_motion_lock.acquire()`: acquired → crash-recovery wait (holding lock); not acquired → fire and return | No new state; the lock-held wait also stops a new Transfer starting under it | ✓ |
| Separate `_run_in_flight` flag set by Transfer/RunProtocol | Extra state; a race between the flag and the lock | |
| Ask the instrument (`status()`) | Violates ADP-09 (no adapter state check) | |

**Auto-selection:** `[auto] Resume — Q: "How does Resume know whether a run is in flight?" → Selected: "Non-blocking motion-lock acquire" (recommended default)`

## run_state shape & source

| Option | Description | Selected |
|--------|-------------|----------|
| `{state, percent, pause: PauseInfo.to_dict() + since \| null}`; adapter record while in flight, fresh `status()` when idle, `{state: unknown}` on transport error | Matches spec §5.3; the heartbeat never fails | ✓ |
| Always a fresh `service.status()` | Loses the PauseInfo detail the wait observed | |
| Leave run_state unset on error | The UI can't tell "unknown" from "not a controllable tool" | |

**Auto-selection:** `[auto] run_state — Q: "Shape and source of run_state?" → Selected: "Adapter record in flight / fresh status idle / unknown on error" (recommended default)`

## Core pin during Phase 1

| Option | Description | Selected |
|--------|-------------|----------|
| Stay on `76f8c3f`; duck-typed pause recorder (no `PauseInfo` import) | Matches the roadmap (re-pin is Phase 2); the gate venv lacks PauseInfo | ✓ |
| Re-pin to `b30b38d` now | Pulls Phase 2 work forward; the GitLab branch isn't pushed | |

**Auto-selection:** `[auto] Core pin — Q: "Which core does Phase 1 build against?" → Selected: "Stay on 76f8c3f, duck-typed recorder" (recommended default)`

## Invariant scope

| Option | Description | Selected |
|--------|-------------|----------|
| Per-method scoped attrs (pause/resume/abort/wait) + AST "record-only" check on recorder/progress + planted violations per rule | Extends the existing TestAdapterInvariant pattern | ✓ |
| Code review only | No regression guard | |

**Auto-selection:** `[auto] Invariants — Q: "How far does the AST invariant extend?" → Selected: "Scoped attrs + record-only + planted violations" (recommended default)`

## Simulated pause hook

| Option | Description | Selected |
|--------|-------------|----------|
| In-process `simulate_pause(dict \| None)` method, simulated-only; simulated Resume/Abort clear it | No new gRPC surface; the 1:1 tests stay intact | ✓ |
| Hidden gRPC command | Widens the command surface, breaks the 1:1 mapping | |
| Env var read at GetStatus | Needs a process restart to change; fiddly | |

**Auto-selection:** `[auto] Simulated hook — Q: "How is a simulated pause driven?" → Selected: "In-process method" (recommended default)`

## Claude's Discretion

- Constant/helper names, override placement, test class placement
- Detecting the simulated run's start and end around base_server's sleep
- `EstimatePause` value; the `EstimateResume` debt comment
- Docstring updates for Resume

## Deferred Ideas

- Hard pause (D5)
- Structured pause detail for the idle/crash-recovery run_state
- Out-of-process simulated pause trigger
- Split `EstimateResume` (Pitfall 8)
