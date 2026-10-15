No external API integration: this phase re-pins the in-house fast-mcp core to b30b38df48e8480f325228145ccae7915a56e437 (installed from the local clone) and wires its existing RunOptions fields (through_pauses, on_pause) into Transfer/RunProtocol plus adapter-side abort wording; it calls no external or third-party API.

Note: the two Phase 1 COVERAGE.md opt-outs deferred to this phase ("wait through_pauses / on_pause (PauseInfo)" and "paused time excluded from the run timeout") are integrated here by plans 02-01 and 02-04; hard pause stays out of scope (design D5).
