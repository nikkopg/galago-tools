# Phase 2: Wait Through Pauses on the Pinned Core - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-13
**Phase:** 02-wait-through-pauses-on-the-pinned-core
**Areas discussed:** Pin target & install source, LIVE-01 core check, Wiring scope, Abort wording, Timeout proof, Test harness
**Mode:** `--auto` — every question resolved with the recommended option, no user prompts.

---

## Pin target & install source

| Option | Description | Selected |
|--------|-------------|----------|
| Pin `b30b38d`, install gate venv from local clone | Commit named by LIVE-01; branch not on GitLab yet | ✓ |
| Pin branch HEAD `b4b67d8` | Later, but only planning docs | |
| Push the branch to GitLab first | Outward-facing action on another repo | |

[auto] Pin — Q: "Which SHA, and where does the install come from?" → Selected: "b30b38d from the local clone" (recommended default)

## LIVE-01 "installed core is checked"

| Option | Description | Selected |
|--------|-------------|----------|
| Gate test: capability + behavioural state gates over a stub transport | Catches a wrong install automatically | ✓ |
| Manual pre-go-live checklist step | Easy to skip | |

[auto] Core check — Q: "How is the installed core verified?" → Selected: "gate test" (recommended default)

## Wiring scope

| Option | Description | Selected |
|--------|-------------|----------|
| Transfer/RunProtocol through mode; crash-recovery Resume stays default mode | Matches design §5.2 | ✓ |
| Through mode everywhere, Resume included | Loses the Paused message on the crash-recovery path | |

[auto] Wiring — Q: "Which commands wait through pauses?" → Selected: "Transfer/RunProtocol only" (recommended default)
[auto] Limitation test — Q: "What happens to the pinned leading-paused limitation test?" → Selected: "flip it to pin the core's fix" (recommended default)

## Abort wording

| Option | Description | Selected |
|--------|-------------|----------|
| "by operator" only when the adapter's own Abort was accepted (record-only flag) | Never blames the operator for an instrument-side abort | ✓ |
| Every Aborted → "run aborted by operator at <p>%" | Spec literal; misattributes non-operator aborts | |

[auto] Abort — Q: "When does an Aborted result say 'by operator'?" → Selected: "flag-based" (recommended default)

## Timeout proof

| Option | Description | Selected |
|--------|-------------|----------|
| Rely on core S6; adapter only passes through_pauses; real-core test with injected clock | No duplicate timing logic | ✓ |
| Adapter-side pause timer | Duplicates a core rule (Core Value: adapter holds no copy of a safety rule) | |

[auto] Timeout — Q: "Who excludes paused time?" → Selected: "the core" (recommended default)

## Test harness

| Option | Description | Selected |
|--------|-------------|----------|
| Real FastService over MagicMock transport, Event-gated status script | Proves the real core path, no motion | ✓ |
| Mocked FastService | Doesn't prove through_pauses behaviour | |

[auto] Harness — Q: "What does 'real core (stub transport)' mean?" → Selected: "real FastService over a stub transport" (recommended default)

## Claude's Discretion

- Operator-abort flag name and how `_message_for` receives it
- Where the LIVE-01 capability test lives
- Plan split and stub-transport helpers

## Deferred Ideas

- Pushing `fix/run-recovery-gate` to GitLab (user action, before Phase 3)
- Crash-recovery Resume under `_run_in_flight()`
- Splitting `EstimateResume`; hard pause
