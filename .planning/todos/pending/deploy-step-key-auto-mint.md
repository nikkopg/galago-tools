---
created: 2026-11-03
source: 【gsd-quick candidate — v2.1】
resolves_phase: ""
---

# Deploy the adapter's step-key auto-mint to the live service

## Context

Post-milestone (v2 closed at `3138ffe`; adapter fix committed at `0604348` in
galago-tools). The STACK tool server on forb01 runs the adapter from the
service venv (`~/data/nikko/.venvs/galago-py310`); until the redeploy, the
live tool keeps the old behavior (a blank step_key refuses with
`INVALID_ARGUMENTS: step_key is required`, and visual protocols must mint
their own keys). The committed adapter change auto-mints a fresh key
(UTC timestamp microseconds + 8 hex random, no model prefix) whenever a
caller omits a blank one — making visual protocols and tool-page manual
sends one-shot safe without the authoring knob.

## Steps (the 07-02 safe-order dance, per D-03/D-04/D-06/D-10)

- [ ] Type-go gate: present '' + the redeploy decision (the operator's literal go recorded with a UTC timestamp — D-10)
- [ ] D-06 pre-restart backup: newest trace_logs folder + journal + MainPID.record + `ss -ltnp` listener baseline into ~/.local/share/galago/log-backups/pre-stepkey-<ts>/
- [x]SIMPLIFIED (verified 2026-11-03}: the unit already runs an editable install (ExecStart galago-tools/.venv/bin/galago; __editable__.galago_tools-0.19.10.pth; import resolves to the repo's tools/stack/server.py) — NO reinstall: a service restart alone picks up commit 0604348. Nothing to reinstall; no uv dance. (The safe-order gate flow stays.)
- [ ] Operator restarts `systemctl --user restart galago-tools` (after the D-06 backup gate below); checks: is-active✓, new MainPID, no traceback in journal, listeners re-baselined (the five ports), both tool servers READY
- [ ] Live GO-gated proof: one tool-page Transfer with the step_key field LEFT BLANK → reply SUCCESS with the minted key visible in the new ledger record (the record's key matches timestamp format) — and a second blank-key transfer minutes later with a DIFFERENT minted key (no same-key refusal, part of it expected)
- [ ] Findings: record the evidence in docs/runbooks/gal-07-live-handoff.md (a new findings row family or the 3a-n sequence follow-on) and the README's tool-page note: the field may be left blank to auto-mint

## Done

The service runs the auto-mint adapter; the operator's visual/manual workflows
never type step keys again; the ledger keys stay of-uniqueness-proven per run.
