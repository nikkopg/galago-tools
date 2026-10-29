# Phase 5: F5-safe Transfer & Operator Acknowledge - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-29
**Phase:** 05-f5-safe-transfer-operator-acknowledge
**Mode:** `--auto` — every question resolved with the recommended option; no user prompts.
**Areas discussed:** Ledger storage, Record & fingerprint, Repeat-key state machine, Restart mid-transfer, Wait & timeout, Acknowledge & latch read, Safety invariant, Tests

---

## Ledger storage

| Option | Description | Selected |
|--------|-------------|----------|
| One JSON doc, atomic replace + flock, fail closed | Mirrors core `StateStore`; corrupt → refuse Transfer | ✓ |
| One file per step key | Simpler writes, harder pruning and locking | |
| SQLite | Transactions for free, new dependency and file format | |

[auto] Ledger storage — Q: "Format and failure behaviour?" → Selected: "One JSON doc, atomic, fail closed" (recommended default)
[auto] Ledger storage — Q: "Default location?" → Selected: "`$XDG_STATE_HOME/galago-tools/stack` else `~/.local/state/galago-tools/stack`; Config path must be absolute" (recommended default)

## Record & fingerprint

| Option | Description | Selected |
|--------|-------------|----------|
| sha256 of endpoint key + request fields, excluding step_key/timeout | Same request on another STACK is a mismatch | ✓ |
| Request fields only | A key could replay across instruments | |

[auto] Record & fingerprint — Q: "What goes into the fingerprint?" → Selected: "endpoint + request fields" (recommended default)

## Repeat-key state machine

| Option | Description | Selected |
|--------|-------------|----------|
| Non-`ran` terminal → refuse permanently; operator uses a new key after ack | Never re-sends a transfer that started | ✓ |
| Non-`ran` terminal → release after acknowledge | Convenient retry, but re-sends motion for a step that already moved | |

[auto] State machine — Q: "Failed step re-run?" → Selected: "refuse; new key" (recommended default)
[auto] State machine — Q: "Replay window?" → Selected: "`REPLAY_WINDOW_S = 600` constant, older `ran` refused" (recommended default)
[auto] State machine — Q: "What releases a key?" → Selected: "execute_transfer Refused/Rejected/NeedsInput/ReadFailed delete the record; Lost(submitOutcomeUnknown) and exceptions keep it" (recommended default)

## Restart mid-transfer (core limit 1)

| Option | Description | Selected |
|--------|-------------|----------|
| Re-attach read-only; `ran` SUCCESS flagged, any other outcome adds arm-inspection clause; spike confirms | Observed `ran` is STACK's own word, failure may not latch | ✓ |
| Refuse every cross-restart re-attach | Safest, but a TimedOut-then-restart step can never finish | |

[auto] Restart — Q: "How is a cross-restart re-attach reported?" → Selected: "re-attach with arm-inspection wording; spike may tighten" (recommended default)

## Wait & timeout

| Option | Description | Selected |
|--------|-------------|----------|
| Fresh: one `wait(handle, T)`; re-attach: `wait_transfer` slices ≤300 s; T default 300 s | Matches roadmap wording, never re-sends | ✓ |
| Re-attach via `wait(TaskHandle.from_dict(...))` | Unclamped, bypasses the core's `_started` lookup | |

[auto] Wait — Q: "Wait API and default budget?" → Selected: "wait / wait_transfer slices, 300 s default" (recommended default)

## Acknowledge & latch read

| Option | Description | Selected |
|--------|-------------|----------|
| `"yes"` only reaches the core; `"no"` → INVALID_ARGUMENTS; ack never touches ledger | Per ACK-01 | ✓ |
| `"no"` as a no-op SUCCESS | Would hide a not-inspected arm | |

[auto] Ack — Q: "Error replies name the guid how?" → Selected: "result fields, then zero-I/O `latch_status()`" (recommended default)

## Safety invariant

| Option | Description | Selected |
|--------|-------------|----------|
| AST: forbidden calls + single, loop-free execute_transfer site, + behavioural submit counter | Structural and behavioural proof of XFR-05 | ✓ |
| AST only | Cannot prove "once per key" across restart | |

[auto] Invariant — Q: "How to prove at-most-once?" → Selected: "AST + submit counter" (recommended default)

## Tests

[auto] Tests — Q: "Order and harness?" → Selected: "pure state-machine tests first, mocked core with real result classes, STK-05 re-proved on real Transfer" (recommended default)

## Claude's Discretion

- Ledger module location, message wording, constant values, retention, timestamp format.

## Deferred Ideas

- Ledger inspect/clear command (needs proto change → v3)
- STACK heartbeat on GetStatus
- Ledger-dir runbook rule (Phase 7)
- Configure refusal mid-run (v2 Future Requirement)
