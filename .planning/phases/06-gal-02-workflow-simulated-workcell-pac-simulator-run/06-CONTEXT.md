# Phase 6: GAL-02 Workflow, Simulated Workcell & PAC-Simulator Run - Context

**Gathered:** 2026-11-02
**Status:** Ready for planning
**Mode:** `--auto` (every gray area resolved with the recommended option; see `06-DISCUSSION-LOG.md`)

<domain>
## Phase Boundary

Deliver GAL-02, the STACK -> F.A.S.T. -> STACK plate handoff, as a Galago **script-mode protocol**
kept in this repo beside its runbook, and prove in simulation that a re-dispatched STACK step never
sends a second transfer:

- **FLOW-01:** the protocol (importable JSON) and its runbook. It mints per-run `step_key`s and
  takes the nest triples as parameters.
- **FLOW-02:** a fully Galago-simulated workcell run (both tools `simulated=true`) completes all three
  steps.
- **FLOW-03:** a forced re-dispatch of a completed STACK step sends no second transfer. This is proven
  offline on a fake core and re-exercised in a simulated run.
- **FLOW-04:** an operator-run GAL-02 with the STACK tool in real mode against the loopback PAC
  simulator, and the F.A.S.T. Galago-simulated, completes. It includes a forced re-dispatch that sends
  no second POST. It never targets `10.150.1.125` / `stack-server`.

**Hard external gate, as found during the scout (2026-11-02):** DEP-02 has **not landed**. galago-core
`feat/stack-tool` is still in its Phase 5 ("STACK Codegen & Command Forms", not started). This repo's
frozen `stack.proto` is already pushed to `origin/feat/stack-tool` (`9592509`), so the codegen side
is unblocked but not done. FLOW-01 and the offline half of FLOW-03 do not need DEP-02. FLOW-02, the
simulated half of FLOW-03, and FLOW-04 do.

Not in this phase:
- any adapter behaviour change in `tools/stack/server.py` or `ledger.py`. Phase 5 froze the
  Transfer/ledger semantics. A defect found here goes through a normal fix plan, not a redesign;
- any `stack.proto` or `Config` change (frozen since Phase 4 D-01..D-05);
- galago-core code (codegen, forms, Ack control: DEP-02/DEP-03);
- deploy, hardware names and any live motion (Phase 7);
- a runtime sim/hardware guard in the adapter (G7, out of scope; enforced by fixtures and the runbook).

</domain>

<decisions>
## Implementation Decisions

### DEP-02 gate and plan split
- **D-01:** Phase 6 is planned in two parts and **does not work around DEP-02**:
  - **Part 1, autonomous, no DEP-02:** FLOW-01 (protocol JSON + runbook), the offline FLOW-03 proof,
    and a protocol-script harness test (D-08). Fakes only; nothing moves.
  - **Part 2, operator-run, gated on DEP-02:** FLOW-02, the simulated half of FLOW-03, and FLOW-04.
    Each is a `checkpoint:human-action` plan (`autonomous: false`). Each opens with a precondition
    check: galago-core builds with `ToolType.stack`, `commandFields.stack` is present without
    `acknowledge_failure`, and the vendored galago-tools submodule is at or past the frozen proto.
    If the check fails, the plan **stops as `blocking-human`** with a pointer to galago-core Phase 5.
    It must never hand-write stack types into galago-core or drive the queue some other way.
  - The phase is complete only after Part 2 has run. Part 1 can be executed and verified on its own
    first.

### Protocol artifact (FLOW-01)
- **D-02:** Location: create `docs/runbooks/` in this repo:
  - `docs/runbooks/gal-02-handoff.md`: the runbook;
  - `docs/runbooks/gal-02-handoff.protocol.json`: the protocol.

  The JSON is galago-core's script-protocol export format exactly: `{"protocol": {name, category,
  description, "mode": "script", scriptContent, parameters[], "commands": []}, exportedAt,
  "version": "1.0"}` (`../galago-core/docs/script-protocols.md` § Import / Export). It must import
  through galago-core's normal protocol import, with no hand edits.
- **D-03:** Script style follows the sandbox rules: `var` not `const`/`let`, no `require`/`fetch`,
  `Number(params.x) || default` for numerics, and only `galago.command` / `galago.note` / `galago.timer`.
  Command order:
  1. a `galago.note` naming the run's key base;
  2. STACK `transfer` (in: source nest/hotel -> F.A.S.T. deck position);
  3. F.A.S.T. `transfer`;
  4. STACK `transfer` (out: F.A.S.T. deck position -> back to the source).
  It emits no `acknowledge_failure` and no other operator-only command. galago-core refuses those in
  any protocol anyway.
- **D-04:** Parameters (all strings, as the sandbox delivers them):
  - **Run identity:** `batch_label` (required).
  - **Tool instance names:** `stack_tool` (default `STACK`) and `fast_tool` (default `FAST`). These are
    workcell instance names, not types.
  - **STACK common:** `robot` and `labware_profile`.
  - **STACK source triple:** `source_device`, `source_deck`, `source_nest`, `source_transfer_profile`.
    This is where the plate starts and where it returns.
  - **STACK F.A.S.T.-side triple:** `fast_device`, `fast_deck`, `fast_nest`, `fast_transfer_profile`.
    This is the STACK's name for the F.A.S.T. deck position.
  - **Timeout:** `stack_timeout_s`. Blank means the Config/adapter default.
  - **F.A.S.T. transfer:** its fields pass through as parameters (deck, plate ids, rows/cols, volume,
    tip_reuse, expected_tray_id), with defaults from the v1 F.A.S.T. runbook.

  The return leg is the in leg's triples swapped. Defaults are the **PAC-sim lab names**
  (`sim-arm-1`, `greiner 96 white`, source `sim-nest-a`/`sim-A1`, F.A.S.T.-side stand-in
  `sim-nest-b`/`sim-B1`; runbook A4). The protocol is therefore safe by default, and hardware names
  are entered by the operator in Phase 7. A missing required triple field fails at queue time (script
  throws), not at the tool.
  — **Reversibility:** costly — parameter names become the operator's saved-run inputs and Phase 7's
  runbook vocabulary; renaming later breaks stored runs.
- **D-05:** `step_key` minting:
  - Base: `var base = params.batch_label + "-" + new Date().toISOString() + "-" + Math.random().toString(16).slice(2, 10);`.
  - Keys: `base + "-in"` and `base + "-out"`.
  - Stability: the keys are computed once at queue time and stored with the queued commands. They stay
    stable across F5 re-dispatch and retry-after-failure, and differ on every new run (Pitfall 1).
  - Length: the planner checks the key against the adapter's display bound (WR-03) and step-key
    validation in `tools/stack/server.py`. If the batch label is long, the script truncates the label,
    never the timestamp or random suffix.

### Forced re-dispatch proof (FLOW-03)
- **D-06:** Offline proof, the substantive one. It lives in a new test module:
  - The test runs the protocol's `scriptContent` (D-08), takes the two STACK `transfer` param dicts,
    and drives them through a real-mode `StackServer` on the existing fake core.
  - First dispatch: one `execute_transfer`.
  - Re-dispatch of the same stored params: `SUCCESS` with `replayed: true`, and the fake core's submit
    count **stays at 1**.
  - Retry-after-failure path: a fake `Refused` on the first try releases the key, the re-dispatch
    submits once, and the total stays at 1 successful submit.
  - A second script evaluation (a new run) yields different keys.
- **D-07:** What the simulated-run half of FLOW-03 asserts (this resolves the roadmap note): in
  Galago-simulated mode, re-dispatching the completed STACK step from the run returns `SUCCESS`, and no
  ledger file appears in the configured `ledger_dir` (STK-06). It proves the protocol shape survives a
  re-dispatch through the real queue. It does **not** claim the no-second-transfer property, which only
  the D-06 test and FLOW-04 prove. The runbook and the verification report must say exactly this.

### Protocol harness (supports FLOW-01, FLOW-03)
- **D-08:** Python test that runs the protocol script in `node`:
  - It runs `scriptContent` in `node` (`vm` with a stub `galago` object that records
    `command(tool, cmd, params)` calls and the given `params`), and asserts:
    - the export JSON shape (D-02);
    - three commands in order, plus the note;
    - both STACK keys non-blank, distinct and run-unique;
    - the return leg is the swap of the in leg;
    - no operator-only command;
    - defaults are the sim lab names.
  - Placement: alongside `tools/tests/`.
  - If `node` is not on PATH, the test **skips with a stated reason**. It is not silently green.
  - The stub mirrors only the documented sandbox API. It is not a reimplementation of galago-core's
    executor. Part 2's real import is the authority.

### PAC-simulator run (FLOW-04)
- **D-09:** Host and preconditions:
  - Host: the galago-tools host itself. Docker is installed and usable there, confirmed by the scout.
    The PAC sim images are **not yet built**; the operator builds them per the SAL runbook Part A.1.
    The sim publishes on loopback only, so the tool server must run on that same host.
  - Environment: the tool server is started with the **sim account** in `STACK_USER`/`STACK_PASSWORD`.
  - Configure: `host=127.0.0.1`, `port=5005`, and a **sim-only absolute `ledger_dir`** (e.g.
    `~/.local/state/galago-tools/stack-sim`), so sim keys never share a ledger with hardware.
  - Switching back to hardware means restarting the service with different environment values
    (credentials are process-global). The runbook says so.
- **D-10:** Hardware refusal: a runbook preflight step refuses to continue if the configured host is
  `10.150.1.125` or `stack-server`. The step also confirms the robot list contains only `sim-` names,
  via `GetRobotStates` (the A.0 sentinel). Any new test fixture in this phase that builds a real-mode
  Configure asserts the same deny-set. No adapter runtime guard is added (G7 out of scope).
- **D-11:** Forced re-dispatch in FLOW-04:
  - When: after the run completes and within `REPLAY_WINDOW_S` (600 s).
  - How: the operator re-sends the in-leg STACK `transfer` with the **same stored params** (copied
    from the run's queued command) from the tool page.
  - Expected: `SUCCESS` with `replayed: true` in meta, and the PAC sim manager's task list shows
    **one** task for that leg. The task count is the "no second POST" evidence.
  - Also run: one re-send after the window, expecting the refusal line, so the operator sees both
    branches of D-07 (Phase 5).
- **D-12:** Evidence:
  - FLOW-02/FLOW-04 results go into a **Findings log** section of `gal-02-handoff.md`, mirroring the v1
    and SAL runbooks: timestamps, keys, replies and sim task counts.
  - The Part 2 plans are human-action checkpoints. The executor never starts Docker, the sim or the
    run itself (SAL runbook A.0/A.10 operator rule).

### Claude's Discretion
- The runbook's internal layout and wording, and the exact F.A.S.T. parameter defaults (taken from the
  v1 F.A.S.T. runbook).
- How the harness invokes `node` (inline script vs a small `.js` helper under `tools/tests/`).
- Whether the D-06 and D-08 tests share one module.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements and roadmap
- `.planning/ROADMAP.md` § Phase 6: goal, success criteria, DEP-02 dependency, research flag.
- `.planning/REQUIREMENTS.md`: FLOW-01..04, DEP-02, Out of Scope (G7).
- `.planning/research/SUMMARY.md` § 3 (identifiers / script mode), § Q4 (two simulation levels),
  Critical Pitfalls 1-2, § Phase 6.

### Prior phase decisions
- `.planning/phases/05-f5-safe-transfer-operator-acknowledge/05-CONTEXT.md` D-05..D-11: ledger states,
  repeat-key table, `REPLAY_WINDOW_S`, release rules (what a re-dispatch returns).
- `.planning/phases/04-stack-tool-registration-reads-estimate/04-CONTEXT.md`: frozen proto
  (D-01..D-05), simulated mode (STK-06).

### Galago script protocols (galago-core, sibling repo)
- `../galago-core/docs/script-protocols.md`: sandbox API, parameters, Import / Export JSON format, tips.
- `../galago-core/controller/server/scripting/protocol-script-executor.ts`: sandbox (`Date`, `Math`).
- `../galago-core/.planning/ROADMAP.md` § Phase 5: DEP-02 delivery and its status.

### PAC simulator
- `../stack-automation-layer/docs/runbooks/stack-validation.md` Part A: A.0 safety rules, A.1
  build/start, A.3 mode/recovery, A.4 sim lab names, A.7 sim limits, A.10 teardown.

### F.A.S.T. reference
- `/home/formulatrix/data/nikko/fast/fast-mcp/docs/runbooks/phase5-galago-live-run.md`: v1 Galago run
  runbook shape, Finding F5 (:489-530), F.A.S.T. transfer params.
- `interfaces/tools/grpc_interfaces/fast.proto` `Command.Transfer`, `interfaces/tools/grpc_interfaces/stack.proto` `Command.Transfer`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tools/tests/stack_test.py` already has the fake core with a submit counter and real-mode
  `StackServer` fixtures. These are the base for D-06.
- `tools/stack/server.py`:
  - `_check_args` enforces a non-blank `step_key`;
  - the ledger replay path returns meta `{result, stepKey, replayed: true}`;
  - `REPLAY_WINDOW_S = 600`.
- `tools/stack/ledger.py` `resolve_ledger_dir`: an explicit absolute `ledger_dir` wins, otherwise
  `$XDG_STATE_HOME/galago-tools/stack` or `~/.local/state/galago-tools/stack`.

### Established Patterns
- Verification gate: `bin/make proto test` on `~/data/nikko/.venvs/galago-py310`. The Phase 4
  re-verification saw it at 510 passed.
- Runbooks carry a Findings log and an operator-only teardown, and the executor never runs live or sim
  infrastructure (SAL A.0/A.10).
- Simulated mode never writes the ledger. A sim run cannot poison real keys.

### Integration Points
- galago-core imports the protocol JSON and runs the script at queue time. Its output becomes stored
  commands: `{stack: {transfer: {...}}}`, `{fast: {transfer: {...}}}`.
- Tool instances (STACK `{host, port, ledger_dir}`, F.A.S.T. `{host, port, ...}`) are workcell records
  in galago-core's DB. Setting them up is a config action in the runbook, not code.
- Phase 7 reuses this protocol with hardware triples and the default ledger dir.

</code_context>

<specifics>
## Specific Ideas

- Sim lab mapping for the three steps:
  - in: `sim-nest-a/sim-A1` -> `sim-nest-b/sim-B1`;
  - F.A.S.T. step: Galago-simulated;
  - out: `sim-nest-b/sim-B1` -> `sim-nest-a/sim-A1`.
- The PAC sim models no plate presence or real grip (A.7). A "completed" sim run proves sequencing and
  the ledger, not plate handling.

</specifics>

<deferred>
## Deferred Ideas

- Building and committing a Docker compose wrapper for the PAC sim in this repo. The SAL runbook owns
  the build. Revisit only if Phase 7 needs repeatable sim bring-up.
- Hardware-name parameter presets for `stack2-6`: Phase 7.
- A ledger-dir backup/never-delete rule: Phase 7 deploy runbook (Phase 5 deferral).

</deferred>

---

*Phase: 06-gal-02-workflow-simulated-workcell-pac-simulator-run*
*Context gathered: 2026-11-02*
