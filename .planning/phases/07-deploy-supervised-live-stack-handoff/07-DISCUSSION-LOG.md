# Phase 7: Deploy & Supervised Live STACK + Handoff - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-11-02
**Phase:** 07-Deploy & Supervised Live STACK + Handoff
**Areas discussed:** DEP-03 go/no-go, Deploy procedure, Runbook scope/order, Approval & live protocol

---

## DEP-03 go/no-go

| Option | Description | Selected |
|--------|-------------|----------|
| Live now, no DEP-03 | Live Transfer + handoff with what's deployed today (DEP-02 core) | ✓ |
| Wait for DEP-03 | Block live hardware until operator Ack control, F3 error display, F5 root cause land | |
| Split gates | Live Transfer now; handoff waits for DEP-03 | |

**User's choice:** Live now, no DEP-03
**Notes:** Follow-up: how is a latched failure cleared live without the galago-core Ack UI? Free-text
answer: "think it's still possible from stack-manager-ui" → captured as decision D-02 (manager UI is
the primary live recovery route; adapter `AcknowledgeFailure` tool-page command stays the fallback).

---

## Deploy procedure

| Option | Description | Selected |
|--------|-------------|----------|
| forb01 (Recommended) | Same host as the F.A.S.T. deployment — reuses the proven safe-order procedure | ✓ |
| Other host | A different/first-time host — procedure needs discovery | |

**User's choice:** forb01
**Notes:** —

| Option | Description | Selected |
|--------|-------------|----------|
| Pin bump + .venv (Recommended) | Bump the fork's core pin to the DEP-02 build, install into service .venv | ✓ |
| Local clone | Install galago-core from a local clone path instead | |

**User's choice:** Pin bump + .venv
**Notes:** —

| Option | Description | Selected |
|--------|-------------|----------|
| Check + refuse (Recommended) | Pre-flight verifies stack-mcp is not running (lock-holder test as the gate) | ✓ |
| Active stop | Runbook actively stops stack-mcp as part of the procedure | |

**User's choice:** Check + refuse
**Notes:** —

| Option | Description | Selected |
|--------|-------------|----------|
| Backup each restart (Recommended) | Timestamped log copy before every restart | ✓ |
| Backup once | Backup only before the first live run | |

**User's choice:** Backup each restart
**Notes:** —

---

## Runbook scope/order

| Option | Description | Selected |
|--------|-------------|----------|
| New gal-07 file (Recommended) | New docs/runbooks/gal-07-live-handoff.md + own exit-code pre-flight script | ✓ |
| Extend gal-02 | Extend docs/runbooks/gal-02-handoff.md live sections | |

**User's choice:** New gal-07 file
**Notes:** —

| Option | Description | Selected |
|--------|-------------|----------|
| Exit-code pre-flight (Recommended) | Executable gate verifying live preconditions, nonzero refusal | ✓ |
| Prose only | Checklist without an executable gate | |
| Gate + shared flag | Also flip gal-02's `10.150.1.125` refusal to a per-phase flag | |

**User's choice:** Exit-code pre-flight (standalone)
**Notes:** —

| Option | Description | Selected |
|--------|-------------|----------|
| Rehearsal + handoff (Recommended) | Live single Transfer (LIVE-09) first, then live GAL-02 handoff (LIVE-10) | ✓ |
| Handoff directly | Single Transfer absorbed into the handoff | |
| Transfer only this session | LIVE-09 only; handoff scheduled later | |

**User's choice:** Rehearsal + handoff
**Notes:** User first asked "what's the difference between transfer and handoff? i think we can
transfer to fast instrument as well in stack" — clarified: the handoff *is* STACK transfers to/from
the F.A.S.T. instrument orchestrated as a 3-step protocol through galago-core's queue; LIVE-09 is
one isolated supervised `Transfer` on stack2-6 as a rehearsal. User then accepted the staged order.

---

## Approval & live protocol

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit per-event (Recommended) | Each live event waits for a typed go-ahead recorded with timestamp | ✓ |
| One session approval | Single go-ahead unlocks the whole sequence | |
| Two approvals | Go-ahead at deploy + at handoff | |

**User's choice:** Explicit per-event
**Notes:** —

| Option | Description | Selected |
|--------|-------------|----------|
| Stop → inspect → clear (Recommended) | Stop the session, inspect ledger + in-flight guard, operator inspects arm, clear via manager UI | ✓ |
| In-session retry | Retry same step key in-session after inspection | |
| Ad-hoc decide | Decide in the moment with runbook as reference | |

**User's choice:** Stop → inspect → clear
**Notes:** —

| Option | Description | Selected |
|--------|-------------|----------|
| Pre-store check (Recommended) | Pre-flight verifies all GAL-02 tools configured in the store in a decided order | ✓ |
| Fail then fix | Rely on runtime error; reconfigure and re-run | |

**User's choice:** Pre-store check
**Notes:** Directly addresses the Phase 6 UAT watch item (STACK-PACSIM lost from the dev tool-store
after STACK-SIM was reconfigured in real mode).

---

## the agent's Discretion

- Runbook section contents/format; pre-flight script implementation details
- Backup directory naming and log file selection
- Pre-store check expression (script assertion vs checklist)

## Deferred Ideas

None — discussion stayed within phase scope
