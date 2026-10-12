# API Coverage — fast-mcp FastService run-control surface (pinned core 76f8c3f)

> Full coverage by default. Opt-outs are explicit, reasoned decisions.
> Scope: the run-control methods of the in-house fast-mcp core that the F.A.S.T. adapter calls.
> The adapter's other FastService methods (run_transfer, run_protocol, validate, tip_status,
> scan_tips, eject_tray) were integrated by the shipped adapter and are unchanged here.

| capability | decision | reason |
|---|---|---|
| pause (soft, hard=False) | INTEGRATE | |
| pause (hard=True) | OPT-OUT | explicitly out of scope: design D5, hardPause is undocumented; future requirement |
| resume | INTEGRATE | |
| abort | INTEGRATE | |
| status | INTEGRATE | |
| wait (crash-recovery Resume) | INTEGRATE | |
| wait through_pauses / on_pause (PauseInfo) | OPT-OUT | not needed yet: absent from the pinned core 76f8c3f (D-13); Phase 2 wires it after the re-pin (LIVE-02) |
| paused time excluded from the run timeout | OPT-OUT | not needed yet: core behaviour behind the re-pin; Phase 2 (LIVE-03) |
