# Phase 4: STACK Tool Registration, Reads & Estimate - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-28
**Phase:** 04-stack-tool-registration-reads-estimate
**Mode:** `--auto` — every question resolved with the recommended option, no user prompts
**Areas discussed:** Frozen proto surface, Configure & ownership, Reply mapping, Reads while BUSY, Simulated mode & estimates, Safety invariant & pin

[--auto] Selected all gray areas: Frozen proto surface, Configure & ownership, Reply mapping, Reads while BUSY, Simulated mode & estimates, Safety invariant & pin.

---

## Frozen proto surface

| Option | Description | Selected |
|--------|-------------|----------|
| Full v2 surface incl. `ListTransferProfiles` + `GetFailureLatch` | Ten commands; keeps per-location transfer-profile fields; latch read declared now for ACK-02 | ✓ |
| Research proposal as-is (8 commands) | No transfer-profiles read, no latch read; would force a proto change in Phase 5 | |
| Drop `*_transfer_profile` fields | Smaller proto, but STK-03 names transfer profiles as a read | |

[auto] Frozen proto surface — Q: "Which commands does the frozen `stack.proto` declare?" → Selected: "Full v2 surface incl. ListTransferProfiles + GetFailureLatch" (recommended default)
[auto] Frozen proto surface — Q: "Config fields?" → Selected: "host, port, transfer_timeout_s, ledger_dir; no lock_dir" (recommended default)
**Notes:** Proto freeze is binding (roadmap, 2026-10-28); a later change re-opens DEP-02.

## Configure & ownership

| Option | Description | Selected |
|--------|-------------|----------|
| Mirror `FastServer._configure`; relay `StackOwnedError` text; log a G1 restart warning | Endpoint reuse, close-then-reopen, holder named by the core's own message | ✓ |
| Reword the holder message in the adapter | Duplicates core text | |
| No restart warning | Silent about G1 | |

[auto] Configure & ownership — Q: "How does Configure open and report ownership?" → Selected: "Mirror fast; relay StackOwnedError; WARNING log about G1" (recommended default)

## Reply mapping

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit SUCCESS allowlist; every other kind → `ERROR_FROM_TOOL`; adapter arg errors → `INVALID_ARGUMENTS` | galago-core shows `ERROR_FROM_TOOL` text, hides INVALID_ARGUMENTS/NOT_READY text | ✓ |
| fast-style (`refused → NOT_READY`, `rejected/needsInput → INVALID_ARGUMENTS`) | Hides the guid and reason the operator needs | |

[auto] Reply mapping — Q: "How do core kinds map to Galago codes?" → Selected: "SUCCESS allowlist, everything else ERROR_FROM_TOOL" (recommended default)
[auto] Reply mapping — Q: "Message content?" → Selected: "One line from structured fields (kind, reason, guid); explanation stays in meta" (recommended default)

## Reads while BUSY

| Option | Description | Selected |
|--------|-------------|----------|
| `READ_COMMANDS` bypass incl. `GetTransferEstimate` and `GetFailureLatch` | fast-style override; motion stays serialised | ✓ |
| Reads only, estimate serialised | Estimate is a POST but moves nothing; no reason to block it | |

[auto] Reads while BUSY — Q: "Which commands bypass the BUSY gate?" → Selected: "All eight non-motion commands" (recommended default)
[auto] Reads while BUSY — Q: "How is STK-05 proven before Transfer exists?" → Selected: "Patched blocking Transfer handler in real mode, test written first" (recommended default)

## Simulated mode & estimates

| Option | Description | Selected |
|--------|-------------|----------|
| Validate adapter-owned args only (step_key, timeout_s, guid, arm_inspected) | Instrument completeness stays the core's job | ✓ |
| Also validate robot/nest/profile presence | Copies a core rule into the adapter | |

[auto] Simulated mode — Q: "What does simulated mode validate?" → Selected: "Adapter-owned args only" (recommended default)
[auto] Real-mode Transfer/Ack/Latch — Q: "How are not-yet-built commands refused?" → Selected: "Args checked first, then ERROR_FROM_TOOL 'not available in this build'" (recommended default)
[auto] Estimates — Q: "Basis for EstimateTransfer?" → Selected: "Hardware actual 30-32 s + margin → 35 s" (recommended default)

## Safety invariant & pin

| Option | Description | Selected |
|--------|-------------|----------|
| AST invariant forbidding every motion/ack/plan method + no-mcp-import test + SHA pin `ed8ce47` | Proves "no real-mode path can move the arm" | ✓ |
| Rely on review only | No mechanical proof | |

[auto] Safety invariant & pin — Q: "How is 'nothing moves' proven?" → Selected: "AST invariant with planted violation" (recommended default)

## Claude's Discretion

- Module layout inside `tools/stack/`, exact message wording, exact estimate constants, optional tool image, fake-result construction in tests.

## Deferred Ideas

- STACK `run_state` heartbeat on health `GetStatus`
- `refresh()` / `refresh_devices()` commands
- Tool-page-only command list for `AcknowledgeFailure` (galago-core)
- Adapter refusal of `Configure` mid-run (v2 Future Requirement)
