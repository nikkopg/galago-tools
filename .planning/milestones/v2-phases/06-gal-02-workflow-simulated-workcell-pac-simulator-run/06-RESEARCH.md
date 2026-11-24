# Phase 6: GAL-02 Workflow, Simulated Workcell & PAC-Simulator Run - Research

**Researched:** 2026-11-02
**Domain:** Galago script-mode protocol authoring (JS sandbox in galago-core), offline fake-core replay proof (Python unittest/pytest), operator runbook against the loopback PAC simulator
**Confidence:** HIGH for the sandbox, payload, adapter and test-fixture facts (all read from source this session, and the protocol script plus the offline replay test were prototyped and run in a scratch dir). MEDIUM for the Part 2 operator flow (nothing could be started). LOW for how to count submitted tasks on the PAC sim manager (see Open Question 1).

**Method note:** every question here is answered by local source (galago-core, this repo, stack-automation-layer, the v1 F.A.S.T. runbook). No external library docs were needed and no packages are added, so the `research-plan` / `classify-confidence` / `package-legitimacy` seams were not used. `gsd-tools` was not invoked. File:line citations below are the evidence.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
(Copied from `06-CONTEXT.md` `## Implementation Decisions`; D-01..D-12 are locked.)

- **D-01:** Phase 6 is planned in two parts and **does not work around DEP-02**:
  - **Part 1, autonomous, no DEP-02:** FLOW-01 (protocol JSON + runbook), the offline FLOW-03 proof, and a protocol-script harness test (D-08). Fakes only; nothing moves.
  - **Part 2, operator-run, gated on DEP-02:** FLOW-02, the simulated half of FLOW-03, and FLOW-04. Each is a `checkpoint:human-action` plan (`autonomous: false`). Each opens with a precondition check: galago-core builds with `ToolType.stack`, `commandFields.stack` is present without `acknowledge_failure`, and the vendored galago-tools submodule is at or past the frozen proto. If the check fails, the plan **stops as `blocking-human`** with a pointer to galago-core Phase 5. It must never hand-write stack types into galago-core or drive the queue some other way.
  - The phase is complete only after Part 2 has run. Part 1 can be executed and verified on its own first.
- **D-02:** Location: create `docs/runbooks/` in this repo: `docs/runbooks/gal-02-handoff.md` (the runbook) and `docs/runbooks/gal-02-handoff.protocol.json` (the protocol). The JSON is galago-core's script-protocol export format exactly: `{"protocol": {name, category, description, "mode": "script", scriptContent, parameters[], "commands": []}, exportedAt, "version": "1.0"}` (`../galago-core/docs/script-protocols.md` § Import / Export). It must import through galago-core's normal protocol import, with no hand edits.
- **D-03:** Script style follows the sandbox rules: `var` not `const`/`let`, no `require`/`fetch`, `Number(params.x) || default` for numerics, and only `galago.command` / `galago.note` / `galago.timer`. Command order: (1) a `galago.note` naming the run's key base; (2) STACK `transfer` (in: source nest/hotel -> F.A.S.T. deck position); (3) F.A.S.T. `transfer`; (4) STACK `transfer` (out: F.A.S.T. deck position -> back to the source). It emits no `acknowledge_failure` and no other operator-only command. galago-core refuses those in any protocol anyway.
- **D-04:** Parameters (all strings, as the sandbox delivers them): **Run identity:** `batch_label` (required). **Tool instance names:** `stack_tool` (default `STACK`) and `fast_tool` (default `FAST`), workcell instance names, not types. **STACK common:** `robot` and `labware_profile`. **STACK source triple:** `source_device`, `source_deck`, `source_nest`, `source_transfer_profile` (where the plate starts and returns). **STACK F.A.S.T.-side triple:** `fast_device`, `fast_deck`, `fast_nest`, `fast_transfer_profile` (the STACK's name for the F.A.S.T. deck position). **Timeout:** `stack_timeout_s` (blank means the Config/adapter default). **F.A.S.T. transfer:** its fields pass through as parameters (deck, plate ids, rows/cols, volume, tip_reuse, expected_tray_id), with defaults from the v1 F.A.S.T. runbook. The return leg is the in leg's triples swapped. Defaults are the **PAC-sim lab names** (`sim-arm-1`, `greiner 96 white`, source `sim-nest-a`/`sim-A1`, F.A.S.T.-side stand-in `sim-nest-b`/`sim-B1`; runbook A4). A missing required triple field fails at queue time (script throws), not at the tool. *Reversibility: costly - parameter names become the operator's saved-run inputs and Phase 7's runbook vocabulary.*
- **D-05:** `step_key` minting: base `var base = params.batch_label + "-" + new Date().toISOString() + "-" + Math.random().toString(16).slice(2, 10);`; keys `base + "-in"` and `base + "-out"`; computed once at queue time and stored with the queued commands (stable across F5 re-dispatch and retry-after-failure, different on every new run). The planner checks the key against the adapter's display bound (WR-03) and step-key validation in `tools/stack/server.py`. If the batch label is long, the script truncates the label, never the timestamp or random suffix.
- **D-06:** Offline proof, the substantive one, in a new test module: run the protocol's `scriptContent` (D-08), take the two STACK `transfer` param dicts, drive them through a real-mode `StackServer` on the existing fake core. First dispatch: one `execute_transfer`. Re-dispatch of the same stored params: `SUCCESS` with `replayed: true`, fake core's submit count **stays at 1**. Retry-after-failure path: a fake `Refused` on the first try releases the key, the re-dispatch submits once, total stays at 1 successful submit. A second script evaluation (a new run) yields different keys.
- **D-07:** The simulated-run half of FLOW-03 asserts: in Galago-simulated mode, re-dispatching the completed STACK step returns `SUCCESS`, and no ledger file appears in the configured `ledger_dir` (STK-06). It proves the protocol shape survives a re-dispatch through the real queue. It does **not** claim the no-second-transfer property, which only the D-06 test and FLOW-04 prove. The runbook and the verification report must say exactly this.
- **D-08:** Python test that runs the protocol script in `node` (`vm` with a stub `galago` object that records `command(tool, cmd, params)` calls and the given `params`), asserting: export JSON shape (D-02); three commands in order plus the note; both STACK keys non-blank, distinct and run-unique; the return leg is the swap of the in leg; no operator-only command; defaults are the sim lab names. Placement alongside `tools/tests/`. If `node` is not on PATH, the test **skips with a stated reason**, never silently green. The stub mirrors only the documented sandbox API, not a reimplementation of galago-core's executor. Part 2's real import is the authority.
- **D-09:** Host and preconditions: the galago-tools host itself; Docker installed and usable; PAC sim images **not yet built** (operator builds per SAL runbook Part A.1); the sim publishes on loopback only so the tool server runs on that same host. Tool server started with the **sim account** in `STACK_USER`/`STACK_PASSWORD`. Configure `host=127.0.0.1`, `port=5005`, and a **sim-only absolute `ledger_dir`** (e.g. `~/.local/state/galago-tools/stack-sim`). Switching back to hardware means restarting the service with different environment values.
- **D-10:** Hardware refusal: a runbook preflight step refuses to continue if the configured host is `10.150.1.125` or `stack-server`, and confirms the robot list contains only `sim-` names via `GetRobotStates` (the A.0 sentinel). Any new test fixture in this phase that builds a real-mode Configure asserts the same deny-set. No adapter runtime guard (G7 out of scope).
- **D-11:** Forced re-dispatch in FLOW-04: after the run completes and within `REPLAY_WINDOW_S` (600 s), the operator re-sends the in-leg STACK `transfer` with the **same stored params** from the tool page; expected `SUCCESS` with `replayed: true` in meta, and the PAC sim manager's task list shows **one** task for that leg (the "no second POST" evidence). Also run one re-send after the window, expecting the refusal line.
- **D-12:** FLOW-02/FLOW-04 results go into a **Findings log** section of `gal-02-handoff.md` (timestamps, keys, replies, sim task counts), mirroring the v1 and SAL runbooks. The Part 2 plans are human-action checkpoints; the executor never starts Docker, the sim or the run itself (SAL runbook A.0/A.10 operator rule).

### Claude's Discretion
- The runbook's internal layout and wording, and the exact F.A.S.T. parameter defaults (taken from the v1 F.A.S.T. runbook).
- How the harness invokes `node` (inline script vs a small `.js` helper under `tools/tests/`).
- Whether the D-06 and D-08 tests share one module.

### Deferred Ideas (OUT OF SCOPE)
- Building and committing a Docker compose wrapper for the PAC sim in this repo (the SAL runbook owns the build).
- Hardware-name parameter presets for `stack2-6`: Phase 7.
- A ledger-dir backup/never-delete rule: Phase 7 deploy runbook.

**Out of scope for this phase (CONTEXT `<domain>`):** any adapter behaviour change in `tools/stack/server.py` or `ledger.py`; any `stack.proto` or `Config` change (frozen); galago-core code (DEP-02/DEP-03); deploy, hardware names and live motion (Phase 7); a runtime sim/hardware guard in the adapter (G7).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FLOW-01 | Script-mode GAL-02 protocol as importable JSON beside its runbook; mints per-run `step_key`s; STACK nest triples are parameters | Sandbox API and import schema (sections "Galago script sandbox", "Import path"); verified-in-node script skeleton (Code Examples); parameter table; the Protocols-page import drops `mode`/`scriptContent` (Pitfall 1) |
| FLOW-02 | Fully Galago-simulated workcell run completes all three steps | Simulated adapter behaviour (35 s STACK, 80 s F.A.S.T. sleeps, no meta, no ledger); DEP-02 precondition check; separate tool-server process rule (Pitfall 5); operator runbook outline |
| FLOW-03 | Forced re-dispatch of a completed STACK step sends no second transfer: offline on a fake core and in a simulated run | Offline test recipe prototyped and passing (Code Examples); fixtures to reuse (`_TransferTestCase`, `_FakeCore`); exact replay meta; what the sim half can and cannot prove (D-07) |
| FLOW-04 | Operator-run GAL-02, STACK real-mode against loopback PAC sim, F.A.S.T. simulated, forced re-dispatch with no second POST; never `10.150.1.125`/`stack-server` | PAC sim lab names incl. the decks D-04 omitted, port 5005 clash on this host, env/launch commands, hardware-refusal deny-set, evidence strategy and its open question |
</phase_requirements>

## Summary

The protocol is a pure JavaScript script evaluated **once at run-creation** by galago-core (`RunStore.createFromProtocol` -> `generateCommandsFromProtocol` -> `executeProtocolScript`), and its output is stored as the queued commands. So a key minted in the script is computed once per run and re-used by every re-dispatch or retry of that row, and a new run (including `numberOfRuns > 1`, which calls the script again per run) gets new keys. The payload sent to the tool is `{ [toolType]: { [command]: params } }` with `params` passed through untouched, so the script must emit `{stack: {transfer: {step_key, robot, ..., destination_*...}}}` using the **proto field names** (`destination_*`, not `fast_*`) and real JS numbers for numeric fields. I prototyped the whole script in a node `vm` with a stub `galago`, fed its outputs through `ParseDict` into `stack_pb2.Command.Transfer` / `fast_pb2.Command.Transfer`, and the F.A.S.T. adapter's own `_check_args` returned `[]` on the generated F.A.S.T. step.

The offline FLOW-03 proof is cheap and works on the existing fixtures: a subclass of `tools.tests.stack_test._TransferTestCase` dispatches the script's two STACK param dicts through a real in-process gRPC stub. I ran it: first dispatch `SUCCESS` (1 execute), re-dispatch `SUCCESS` with meta keys `['ledgerState','replayed','result','stepKey']` and `replayed=True` (still 1 execute), and a re-dispatch with `_utcnow` patched past `REPLAY_WINDOW_S` returns `ERROR_FROM_TOOL` "stack: step key already completed at ...; nothing was sent; step key ...". The full existing suite is green at **510 passed in 10.8 s** (`pytest tools/tests -q`).

Five findings change the plan and need the planner's attention (each is detailed below): (1) galago-core's **Protocols-page import silently drops `mode` and `scriptContent`**, so "imports with no hand edits" is true only through `POST /api/protocols`, `protocol.import` over tRPC, or the Hub, not the Import button; (2) CONTEXT's parameter names **collide**: STACK's `source_deck` (a string) and the F.A.S.T. proto field `source_deck` (an int) share one flat `params` object and one Galago-variable namespace; (3) the PAC sim's default port **5005 is already bound on this host** by a Docker container (`scoringservice-scoring-service-1`, `0.0.0.0:5005`), so D-09's `port=5005` cannot be used as written; (4) **`node` is not on the default PATH** (only under `~/.nvm/versions/node/v24.14.1/bin`), so the D-08 test would skip in a plain `bin/make test`; (5) the adapter inherits the base-server quirk that **simulated -> real Configure on the same process never connects**, so FLOW-02 and FLOW-04 need separate STACK tool-server processes.

**Primary recommendation:** Author the protocol JSON by generating it with `json.dumps` from the prototyped script (single source of truth = the JSON), prefix F.A.S.T. parameters `fast_step_` to avoid the name clash, put both the D-08 harness and D-06 proof in one module `tools/tests/gal02_handoff_test.py` that subclasses `_TransferTestCase`, and have the operator import through `POST /api/protocols`. Plan Part 1 as three autonomous plans (protocol+harness, offline FLOW-03, runbook) and Part 2 as two `checkpoint:human-action` plans (FLOW-02 + sim half of FLOW-03; FLOW-04), each opening with the DEP-02 precondition script below.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Mint per-run `step_key` | galago-core controller (script sandbox at run creation) | - | Script runs once in `createFromProtocol`; result stored as queued commands, so keys are stable across re-dispatch [VERIFIED: server/runs.ts:88-97, 213-226] |
| Param validation of script inputs | galago-core UI (`validateParams`) + the script itself | - | UI checks required/number only; the script must re-validate (blank, whole number) and throw |
| Reject a repeated/invalid step key | galago-tools STACK adapter (`tools/stack/server.py`) | Ledger (`tools/stack/ledger.py`) | Phase 5 froze the semantics; Phase 6 only proves them |
| Operator-only command refusal | galago-core (`operatorOnlyCommands.ts`, enqueue + execute guards) | - | Defence in depth; the protocol simply never emits them |
| Sim / hardware separation | Operator runbook + test-fixture deny-set | - | No adapter runtime guard (G7 out of scope) |
| "No second POST" evidence | Offline: fake core submit counter; Online: PAC sim manager side | Adapter ledger file | Adapter-side evidence alone is self-referential; see Open Question 1 |
| Protocol storage / import | galago-core DB via REST/tRPC | - | Not code in this repo; the JSON lives in `docs/runbooks/` |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python `unittest` + `pytest` | venv `galago-py310` (Python 3.10.12) | Test module; both are run by `bin/make test` (`python -m unittest discover -s tools/tests/ -p "*_test.py"`, then `pytest tools/tests/ -vv`) | [VERIFIED: bin/make:39-49] existing suite is 4846-line `stack_test.py` in this style |
| `grpc` in-process server + `ToolDriverStub` | already installed | Real-mode `StackServer` over a real stub (existing `_serve_in_process`) | [VERIFIED: tools/tests/stack_test.py:158-173] |
| Node `vm` (built-in) | node v24.14.1 at `~/.nvm/versions/node/v24.14.1/bin/node` | Run `scriptContent` with a stub `galago` | Same mechanism galago-core uses [VERIFIED: protocol-script-executor.ts:1,85-91] |
| `google.protobuf.json_format.ParseDict` | already installed | Convert the script's param dict to `stack_pb2.Command.Transfer` / `fast_pb2.Command.Transfer`; rejects unknown field names, which is a free contract check | [VERIFIED: ran in scratch, accepted both generated dicts] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `subprocess`, `json`, `shutil.which` (stdlib) | - | Invoke node with the script on stdin | Harness |
| `tools.fast.server._check_args` | repo | Assert the generated F.A.S.T. step passes the adapter's own structural checks | Harness (skip if `fast_mcp` missing, as `fast_test.py` does) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Inline node harness string in the test | Separate `.js` helper under `tools/tests/` | Both allowed by CONTEXT; inline keeps one file and no packaging (MANIFEST) question. Recommend inline, passed via `node -e`, script+params on stdin |
| New module importing from `stack_test` | Add classes to `stack_test.py` | `stack_test.py` is already 4.8k lines; a new module is cleaner, at the cost of importing private (underscore) fixtures |

**Installation:** none. No new packages (Python or npm). **Package Legitimacy Audit:** not applicable, this phase installs nothing external.

## Package Legitimacy Audit

No external packages are installed or recommended in this phase. `node` is a pre-installed runtime, not a package. **Packages removed due to [SLOP] verdict:** none. **Packages flagged [SUS]:** none.

## Architecture Patterns

### System Architecture Diagram

```
 operator ──import──▶ galago-core DB (protocol: mode=script, scriptContent, parameters[])
    │                          │
    │ "Queue run" (params: strings, defaults pre-filled by NewProtocolRunModal)
    ▼                          ▼
 run.create ──▶ upsertParameterVariables (creates a Galago VARIABLE per param name)
    │
    ▼
 createFromProtocol ──▶ executeProtocolScript (vm, 5 s, strings in / objects out)
    │      throw ──▶ ProtocolGenerationFailedError ──▶ BAD_REQUEST "Could not generate commands for the given params."
    ▼
 resolveToolTypes (tool NAME -> type, exact match; "Tool Box" virtual)
    │      unknown name ──▶ "Unknown tools: ..."
    ▼
 enqueue-time operator-only scan ──▶ stored queue rows [note, STACK in, FAST, STACK out]
    │                                  (keys fixed here)
    ▼ Start / F5 re-dispatch / retry of FAILED row re-sends the SAME stored params
 Tool.executeCommand ──▶ payload { [toolType]: { [command]: params } } ──▶ gRPC ExecuteCommand
    │
    ├──▶ FAST tool server  (simulated: sleep EstimateTransfer = 80 s @ 10 uL, SUCCESS, no meta)
    └──▶ STACK tool server
          ├ simulated: _check_args, sleep EST_TRANSFER_S = 35 s, SUCCESS, no meta, NO ledger
          └ real:  _check_args ─▶ Ledger.decide(step_key, fingerprint)
                     FRESH ─▶ plan ─▶ write-ahead claim ─▶ execute_transfer (ONCE) ─▶ wait ─▶ done
                     REPLAY (done+ran, age < 600 s) ─▶ SUCCESS meta {stepKey, ledgerState, result, replayed:true}
                     else refuse / re-attach / mismatch (never a second execute)
                       └──▶ PAC sim manager (loopback only, Docker, operator-built)
```

### Recommended Project Structure
```
docs/runbooks/                         # new directory (docs/ today holds only specs/)
├── gal-02-handoff.md                  # runbook + Findings log (D-02, D-12)
└── gal-02-handoff.protocol.json       # export-format JSON (D-02)
tools/tests/
└── gal02_handoff_test.py              # D-08 harness + D-06 offline proof (one module, discretion)
```

### Galago script sandbox (exact API) [VERIFIED: ../galago-core/controller/server/scripting/protocol-script-executor.ts]

- `galago.command(toolId, command, cmdParams = {})` pushes `{toolId, toolType: "unknown", command, params: cmdParams, label: "", advancedParameters: {...}}` (`:21-33`). `toolId` is the **workcell tool instance name**, not the type; `resolveToolTypes` builds `toolTypeMap.set(t.name, t.type)` and looks up `toolTypeMap.get(cmd.toolId)` with an **exact, case-sensitive** match, else `Unknown tools: ...` (`server/scripting/resolve-tool-types.ts`).
- `command` is the proto oneof field name, i.e. **snake_case**: payload is built as `[this.toolType]: { [command.command]: command.params }` (`server/tools.ts:361-367`). So `"transfer"` for both STACK and F.A.S.T.
- `galago.note(message)` is `this.command("Tool Box", "note", { message })` (`:47-49`), i.e. a **real queue row**: `command_queue.ts:1254` handles `command === "note"` by completing the row immediately. So a run has **4 queue rows** (note + 3 tool steps); "three steps" = the three tool steps.
- Sandbox globals are exactly `galago, params, console, Math, Array, Object, String, Number, Boolean, JSON, Date, parseInt, parseFloat, isNaN, isFinite` (`:67-83`). `Date` and `Math` are the outer-realm objects. Everything else (`Error`, `String.prototype`, ...) is the vm context's own builtins, so `throw new Error(...)` works.
- Timeout 5000 ms (`:16`, `:91`). Zero commands is an error (`:93-100`). A throw is caught and returned as `{success:false, error: error.message}` (`:109-122`). The doc claim "strict mode" is not enforced by the executor (no `"use strict"` is prepended); keep `var` and function declarations anyway.
- `params` is `Record<string,string>`: **all values are strings**, including blanks `""` (the run modal sends every parameter, defaults pre-filled by `buildDefaultValues`, `NewProtocolRunModal.tsx:47-53`). A parameter absent from the object is `undefined`. The script must treat `undefined`, `null` and blank identically.
- Param values are passed to the tool **as the script built them**. ts-proto's generated encoder writes a field when `message.<f> !== undefined` (verified for F.A.S.T.: `gen-interfaces/tools/grpc_interfaces/fast.ts:321-362`), so: emit real numbers via `Number()` for `double`/`int32`; **omit** optional keys rather than send `""` or `null` (a present blank number is a present `0`; a present blank string passes `HasField`). [VERIFIED for the `!== undefined` check; protobufjs' coercion of `null`/string to int is from training, `[ASSUMED]`, and the recommendation does not depend on it.]
- A script error reaches the operator only as the generic tRPC message `"Could not generate commands for the given params."` (`server/routers/run.ts:99-105`; `ProtocolGenerationFailedError(`Script execution failed: ${result.error}`)` at `server/runs.ts:91`). The specific message is in the app log ("Protocol Script Error") and in the **Preview** result (`protocol.preview` returns `error: result.error` plus `logs`). The runbook must tell the operator to use **Preview** to see a throw message.
- `run.create` first calls `upsertParameterVariables` when parameters are non-empty (`server/routers/run.ts:60-77`, `server/runs.ts:120-155`): **every parameter becomes a workcell-scoped Galago variable named after the parameter** (non-blank values only; a required blank throws `Required parameter '<label>' is missing`). Parameter names therefore must be unique and should be specific.
- `numberOfRuns` (1..100) loops `createFromProtocol` (`run.ts:83-86`), so each run re-evaluates the script and gets fresh keys. Keep it at 1 in the runbook.

### Import path [VERIFIED: ../galago-core/controller/server/routers/protocol.ts:30-44, 215-247; components/protocols/ProtocolPageComponent.tsx:132-146]

- `zProtocolImport = { workcellId: number, protocol: { name: string, category?: string, description?: string, commands?: any[], parameters?: zProtocolParameter[] | null, mode?: "visual"|"script", scriptContent?: string|null } }`; the tRPC `protocol.import` inserts `mode: input.protocol.mode || "visual"` and `scriptContent: input.protocol.scriptContent ?? null`.
- `zProtocolParameter` (`protocols/params.ts`): `name` min 1, `label` min 1, `type` in `"string"|"number"|"boolean"|"select"`, `defaultValue?: string`, `required?: boolean`, `options?: string[]`, `description?: string`. `defaultValue` must be a **string** (so `"1"`, not `1`).
- **The Protocols-page Import button drops `mode` and `scriptContent`.** `ProtocolPageComponent.tsx:137-146` calls `importMutation.mutateAsync({ workcellId, protocol: { name, category, description, commands, parameters } })`. A script protocol imported this way arrives as a **visual** protocol with no commands and no script (parameters survive). It also rejects a duplicate name client-side.
- Paths that **do** carry the script: the Hub `loadProtocol` (`components/hub/HubComponent.tsx:202-212` passes the whole `protocol` object), whole-workcell `importConfig`, direct tRPC `protocol.import` (superjson transformer, body `{"json": {...}}`), and `POST /api/protocols`, which calls `protocol.create(req.body)` with `zProtocolCreate` (accepts `name, category, workcellId?, description?, commands, parameters, mode, scriptContent`; uses the **selected workcell** when `workcellId` is omitted, `server/routers/protocol.ts:103-135`). The simplest operator command that needs no content edit, only unwrapping:
  `jq .protocol docs/runbooks/gal-02-handoff.protocol.json | curl -sS -X POST http://localhost:<UI port>/api/protocols -H 'content-type: application/json' --data @-` (`jq` and `curl` are installed). [Command shape derived from the cited code; **not run** against a live galago-core.]
- This is a galago-core defect against the doc's stated Import/Export behaviour. Fixing it is galago-core scope (out of scope here). Recommend recording it in the runbook as a finding and, if the user agrees, adding a one-line follow-up for the galago-core milestone. Part 2's post-import check (open the protocol: Mode = Script, script present, **Preview** shows 4 commands) catches it either way.

### Pattern 1: protocol script (prototyped, run in node, outputs parsed by both adapters)
**What:** validate every input, build all three param objects **before** emitting any command, so a bad input throws before the first `galago.command` (nothing half-queued).
**When to use:** the whole protocol.
**Example:** see Code Examples. Verified this session: node v24.14.1 `vm`, stub `galago`; STACK dicts accepted by `ParseDict(.., stack_pb2.Command.Transfer())`; F.A.S.T. dict accepted by `ParseDict(.., fast_pb2.Command.Transfer())` and `tools.fast.server._check_args(...) == []`; key lengths 42/43 for label `GAL02`.

### Pattern 2: offline replay proof on the existing fixtures (prototyped, 2 tests passed)
**What:** subclass `_TransferTestCase`, dispatch `ParseDict(params, stack_pb2.Command.Transfer())` through `self.stub.ExecuteCommand(self._stack(transfer=...))`, assert on `self.core.execute_calls` / `call_names` and `reply.meta_data`.
**Example:** see Code Examples.

### Anti-Patterns to Avoid
- **Embedding script-side defaults for STACK instrument fields.** `Number(params.x) || default` (the D-03 style) is fine for harmless numerics but a silent fallback to sim names would send sim names to hardware in Phase 7 if a field is blanked. Keep defaults only in the JSON `parameters[].defaultValue` (single source of truth, visible in the run form) and have the script **throw on blank**. For numbers use a strict helper (reject blank, NaN, non-integers for int32 fields); `Number("") || d` would also turn a legitimate `0`/blank into the default.
- **Using `instanceof Error` in the harness.** A throw inside a vm context is not an instance of the outer realm's `Error` (I observed `instanceof Error (outer): false`, `name: "Error"`). Read `e.message` / `e.name`.
- **Counting `execute_calls` as "submits" in the retry test.** `_FakeCore.execute_calls` counts *attempts*, including the first one that returned `Refused`. After a `Refused` then a `TaskHandle` the count is 2, with exactly **one** accepted submit. Assert on "calls that returned a `TaskHandle`" (wrap `execute_result` in a callable that records it) or assert `execute_calls == 2` and then stays 2.
- **Importing test classes that contain tests** from `stack_test` into the new module; unittest would collect and re-run them. Import only `_TransferTestCase`, `_FakeCore`, `_ESTIMATE_FIELDS`, `_GUID`, result classes and constants.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| A fake STACK core with a submit counter | A new mock | `_FakeCore` (`stack_test.py:1726-1785`) via `_TransferTestCase` (`:1787-1818`) | Already built from the core's real result classes; `calls`, `execute_calls`, `call_names` exist |
| Real-mode `StackServer` on a stub | Hand-wired gRPC | `_RealModeGrpcTestCase` / `_serve_in_process` | Includes loopback-only socket guard and temp `HOME`/`XDG_STATE_HOME`/`STACK_STATE_DIR` isolation (`_StackTestCase.setUp`, `:121-156`) so a test can never touch the real ledger or latch |
| Dict -> proto message | Manual field copying | `ParseDict(params, stack_pb2.Command.Transfer())` | Accepts proto field names, rejects unknown ones: it is the contract test between script and `.proto` |
| JSON export file | Hand-escaped `scriptContent` | `json.dumps` from the script text, then commit the JSON | The JSON stays the single source of truth; the test loads `scriptContent` from it |
| Replay-window arithmetic | Sleeping 600 s | `patch.object(stack_server, "_utcnow", return_value=...)` (`:271`, used the same way in `TestRepeatKey._transfer_at`) | Deterministic |
| Hardware deny-set | New constants everywhere | One module-level `frozenset({"10.150.1.125", "stack-server"})` in the new test, mirroring SAL `tests/netguard.py:24-26` and `tests/sim_support.py:46-48` | Same values as the upstream guards; `tools/tests/` is not scanned by the adapter-literal AST test (`_STACK_SOURCES` globs only `tools/stack/*.py`, `stack_test.py:1175`) |

**Key insight:** every behaviour Phase 6 must prove already exists and is tested in Phase 5; Phase 6 adds only a new *caller* (the script's output). The risk is in the seam (names, types, import path, process separation), not in the adapter.

## Runtime State Inventory

Phase 6 is not a rename/refactor/migration phase. Omitted per the template, with one note: the operator run **creates** persistent state that must not be confused with production: galago-core workcell variables named after every parameter (`upsertParameterVariables`), a protocol row, tool rows, and (FLOW-04) one adapter ledger file in the sim-only `ledger_dir`. See Pitfalls 6 and 8.

## Common Pitfalls

### Pitfall 1: the Protocols-page Import silently produces a visual protocol
**What goes wrong:** the operator imports the JSON with the Import button, sees "Protocol imported", queues a run, and gets "has no commands" / no script, or a protocol with the right parameters and an empty body.
**Why:** `ProtocolPageComponent.tsx:139-145` forwards only name/category/description/commands/parameters.
**How to avoid:** runbook imports through `POST /api/protocols` (or tRPC/Hub). Post-import checklist: Mode shows Script, script text present, Preview shows `note, STACK transfer, FAST transfer, STACK transfer`.
**Warning signs:** the protocol detail page opens in visual mode with 0 steps.

### Pitfall 2: parameter-name collision (`source_deck`)
**What goes wrong:** CONTEXT D-04 names the STACK source triple `source_device/source_deck/source_nest` (strings like `sim-deck-a`) and says F.A.S.T. fields "pass through as parameters". The F.A.S.T. proto field `source_deck` is an `int32` (`interfaces/tools/grpc_interfaces/fast.proto:19-21`). One flat `params` object and one Galago-variable namespace cannot hold both. Likewise `fast_deck` (D-04's STACK name for the F.A.S.T.-side position) is the obvious name for the F.A.S.T. deck number.
**How to avoid:** prefix every F.A.S.T. pass-through parameter `fast_step_` (`fast_step_source_deck`, `fast_step_dest_deck`, `fast_step_source_plate_id`, ..., `fast_step_volume`, `fast_step_tip_reuse`, `fast_step_expected_tray_id`). D-04's STACK names stay exactly as locked. This is within Claude's discretion (F.A.S.T. param names are unspecified); flag it to the user because the names are costly to rename (D-04 reversibility).
**Warning signs:** the F.A.S.T. step receives `source_deck: "sim-deck-a"` and fails `_check_args`, or Preview shows one param overwriting another.

### Pitfall 3: D-04's triples omit the `deck` that the sim lab needs
**What goes wrong:** CONTEXT lists defaults "source `sim-nest-a`/`sim-A1`, stand-in `sim-nest-b`/`sim-B1`" (device/nest) but a STACK `Location` is device + **deck** + nest + transfer_profile.
**Fact:** the SAL sim lab is `SimLab`: `robot: str = "sim-arm-1"`, `labware_profile: str = "greiner 96 white"`, source `Location(device="sim-nest-a", deck="sim-deck-a", nest="sim-A1")`, destination `Location(device="sim-nest-b", deck="sim-deck-b", nest="sim-B1")` [VERIFIED: stack-automation-layer/tests/sim_support.py:352-367]. The SAL sim round-trip test passes **no** transfer profile (`tests/test_sim_flows.py:106-120`), so `source_transfer_profile`/`fast_transfer_profile` default to **blank = omit the key**. The `Default` transfer profile exists in the sim lab (`test_sim_flows.py:342-345`).
**How to avoid:** defaults `sim-deck-a` / `sim-deck-b`; transfer-profile params optional with blank default, omitted from the dict when blank.

### Pitfall 4: PAC sim port 5005 is already taken on this host
**What goes wrong:** `scripts/sim_up.sh` publishes `127.0.0.1:${STACK_SIM_PORT:-5005}:5005` (`sim_up.sh:22,31,185`). On this host `ss -ltn` shows `0.0.0.0:5005` and `[::]:5005` LISTEN, and `docker ps` shows `scoringservice-scoring-service-1  0.0.0.0:5005->5005/tcp, [::]:5005->5005/tcp`. Starting the sim on 5005 will fail to bind (or, worse, someone points a tool at the wrong service). [VERIFIED: commands run this session.]
**How to avoid:** the operator sets `STACK_SIM_PORT` to a free port (e.g. 15005 after checking `ss -ltn`) before `sim_up.sh up`; `sim.env` records it; the STACK tool Config `port` takes that value. This **deviates from D-09's literal `port=5005`**; the intent (loopback sim, sim-only ledger) is unchanged. Surface to the user. Never configure port 5006 (Device master, `sim_support.py:DEVICE_MASTER_PORT = 5006`; SAL A.0).

### Pitfall 5: sim -> real Configure on one tool-server process does not connect
**What goes wrong:** `ToolServer.Configure` (`tools/base_server.py:98-101`) `if not request.simulated and self.simulated:` sets simulated False and returns SUCCESS **without** calling `_configure`; `StackServer` does not override this (grep: `simulated` appears in `tools/stack/server.py` only at `:131,948,979,985`). The tool then answers `NOT_READY "stack: not configured"`. The v1 runbook documents the same trap for F.A.S.T. (Pattern 2).
**How to avoid:** separate processes and separate Galago tool instances for FLOW-02 (STACK simulated) and FLOW-04 (STACK real). `stack_tool` is a protocol parameter precisely so the same protocol can name `STACK-SIM` vs `STACK-PACSIM`. Restart the STACK process between modes; the v1 runbook step 7 says the same.

### Pitfall 6: `node` is not on the default PATH
**What goes wrong:** verified under `env -i PATH=/usr/local/bin:/usr/bin:/bin`: `node NOT on default PATH`; there is no `/usr/bin/node`. Node lives at `/home/formulatrix/.nvm/versions/node/v24.14.1/bin/node` and Claude desktop shells do not load the profile (memory note). A plain `bin/make test` would **skip** the D-08 and D-06 script tests and still go green.
**How to avoid:** the test finds node via `shutil.which("node")`, then an env override (e.g. `GALAGO_TEST_NODE`), then a glob of `~/.nvm/versions/node/*/bin/node` (newest), and otherwise skips with a reason naming all three. Plan verification must run with `PATH=$HOME/.nvm/versions/node/v24.14.1/bin:$PATH` and **assert the new module has 0 skipped** (`pytest -rs`). Because the D-06 test consumes the script output it should also skip (not fail) without node.

### Pitfall 7: replay meta shape differs slightly from CONTEXT
CONTEXT says meta `{result, stepKey, replayed: true}`. Actual (`tools/stack/server.py:671-674`, used at `:1112-1113`, asserted at `stack_test.py:2575`): `{"stepKey": ..., "ledgerState": "done", "result": <ran dict>, "replayed": True}`. I observed keys `['ledgerState', 'replayed', 'result', 'stepKey']`. Simulated-mode replies carry **no** meta at all (`base_server.py:138-145`), so D-07's sim assertion is "SUCCESS" only, never `replayed`.

### Pitfall 8: `~` is not expanded in `ledger_dir`
D-09's example `~/.local/state/galago-tools/stack-sim` would be **refused**: `_apply_config` raises `stack: Config.ledger_dir must be an absolute path` for any non-blank value where `os.path.isabs` is false (`tools/stack/server.py:886-889`; `ledger.py:91-104`). Use `/home/formulatrix/.local/state/galago-tools/stack-sim`. The ledger dir is also **pinned** after the first Transfer, and a different `ledger_dir` is then refused by Configure (`_commit_settings`, `:914-937`), so choose it once before the run.

### Pitfall 9: simulated runs are slow and silent
Simulated STACK transfer sleeps `EST_TRANSFER_S = 35` s (`server.py:133`); simulated F.A.S.T. transfer sleeps `EST_TRANSFER_OVERHEAD_S 60 + EST_TRANSFER_PER_CYCLE_S 20 * ceil(10 / EST_TIP_MAX_VOLUME_UL)` = 80 s at 10 uL (`fast/server.py:149-150, 968-973`; v1 runbook A3 recorded 80 s). A FLOW-02 run is about 150 s; a simulated re-dispatch of a STACK step is another 35 s. Mark expected durations in the runbook so the operator does not abort a healthy run.

### Pitfall 10: key length and the display bound (WR-03)
There is **no length or charset limit** on `step_key`: `_check_args` requires only `HasField("step_key") and step_key.strip()` (`server.py:454-457`), and the key is used byte-exact (`:1084`). The bounds are display-only: `_KEY_SHOWN_MAX = 60` applies to the *other* step's key in the "still running" owner clause (`:200, :639`); every operator line is cut to 300 chars by `_fit`. I computed `_fit(_REFUSE_COMPLETED.format(at=..., key=...))` for keys of 43, 58, 78 and 118 chars: the line is 188, 203, 223, 263 chars and **still ends with the full key**. To keep keys <= 60 (full display everywhere): key = label + 1 + 24 (`toISOString()`) + 1 + 8 + 3/4 (`-in`/`-out`) = label + 37/38, so **`label.slice(0, 20)` gives <= 58**. Truncate the label, never the timestamp/suffix (D-05).

### Pitfall 11: `Math.random().toString(16).slice(2, 10)` can be short
`Math.random() === 0` gives `"0".slice(2,10) === ""`, and `0.5` gives `"0.8"` -> `"8"`. Uniqueness still holds because of the millisecond timestamp, but pad: `(Math.random().toString(16) + "00000000").slice(2, 10)` (used in the prototype).

### Pitfall 12: a forced re-dispatch cannot be done from the run page
galago-core re-sends a stored row only through its own queue (Start / F5 / retry of a FAILED row); there is no UI to re-send a *completed* row (that is Finding F5, a bug, v1 runbook `:495-530`). The forced re-dispatch (D-07, D-11) is therefore an operator **re-send from the tool page command form** with the same param values. After DEP-02 the form must expose `step_key` and the 10 location fields; blank number fields are sent as `0` (v1 runbook `:200-203`), which is harmless for STACK: `timeout_s: 0` passes `_check_args` (`>= 0`) and `_wait_budget` treats `<= 0` as unset (`server.py:1049-1058`), and `timeout_s` is excluded from the fingerprint (`ledger.py:110-117`). A blank string field is a present `""`, which `_text_or_none` treats as unset (`server.py:317-324`).

## Code Examples

### Protocol script (verified in node v24.14.1; outputs parsed by both adapters)
```javascript
// Source: prototyped this session. Stored as the JSON string `protocol.scriptContent`.
function text(name) {
  var v = params[name];
  return v === undefined || v === null ? "" : String(v).trim();
}
function need(name) {
  var v = text(name);
  if (v === "") { throw new Error("GAL-02: parameter '" + name + "' is required"); }
  return v;
}
function whole(name) {
  var n = Number(need(name));
  if (!isFinite(n) || Math.floor(n) !== n) { throw new Error("GAL-02: parameter '" + name + "' must be a whole number"); }
  return n;
}
function positive(name) {
  var n = Number(need(name));
  if (!isFinite(n) || n <= 0) { throw new Error("GAL-02: parameter '" + name + "' must be a number above 0"); }
  return n;
}
var label = need("batch_label").slice(0, 20);
var rand = (Math.random().toString(16) + "00000000").slice(2, 10);
var base = label + "-" + new Date().toISOString() + "-" + rand;

function stackLeg(suffix, from, to) {
  var p = {
    step_key: base + suffix,
    robot: need("robot"),
    labware_profile: need("labware_profile"),
    source_device: need(from + "_device"),
    source_deck: need(from + "_deck"),
    source_nest: need(from + "_nest"),
    destination_device: need(to + "_device"),
    destination_deck: need(to + "_deck"),
    destination_nest: need(to + "_nest")
  };
  if (text(from + "_transfer_profile") !== "") { p.source_transfer_profile = text(from + "_transfer_profile"); }
  if (text(to + "_transfer_profile") !== "") { p.destination_transfer_profile = text(to + "_transfer_profile"); }
  if (text("stack_timeout_s") !== "") { p.timeout_s = positive("stack_timeout_s"); }
  return p;
}

function fastStep() {
  var p = {};
  var ints = ["source_deck", "dest_deck", "source_plate_id", "dest_plate_id", "source_start_col", "dest_start_col", "num_rows", "num_cols"];
  for (var i = 0; i < ints.length; i++) { p[ints[i]] = whole("fast_step_" + ints[i]); }
  p.source_start_row = need("fast_step_source_start_row");
  p.dest_start_row = need("fast_step_dest_start_row");
  p.volume = positive("fast_step_volume");
  p.tip_reuse = need("fast_step_tip_reuse");
  if (text("fast_step_expected_tray_id") !== "") { p.expected_tray_id = whole("fast_step_expected_tray_id"); }
  return p;
}

var stackTool = need("stack_tool");
var fastTool = need("fast_tool");
var legIn = stackLeg("-in", "source", "fast");     // source_* -> fast_*  (maps to destination_* on the wire)
var legOut = stackLeg("-out", "fast", "source");   // the in leg's triples swapped
var fastParams = fastStep();

galago.note("GAL-02 key base " + base);
galago.command(stackTool, "transfer", legIn);
galago.command(fastTool, "transfer", fastParams);
galago.command(stackTool, "transfer", legOut);
```
Run with the sim defaults below it emitted: STACK in `{step_key: "GAL02-2026-11-02T02:46:01.749Z-e9016f45-in", robot: "sim-arm-1", labware_profile: "greiner 96 white", source_device: "sim-nest-a", source_deck: "sim-deck-a", source_nest: "sim-A1", destination_device: "sim-nest-b", destination_deck: "sim-deck-b", destination_nest: "sim-B1"}`; F.A.S.T. `{source_deck: 1, dest_deck: 3, source_plate_id: 1, dest_plate_id: 1, source_start_col: 1, dest_start_col: 1, num_rows: 8, num_cols: 1, source_start_row: "A", dest_start_row: "A", volume: 10, tip_reuse: "fresh"}` (`expected_tray_id` omitted).

### Parameter table (proposal; all `defaultValue` are strings)
| name | type | required | default | note |
|------|------|----------|---------|------|
| `batch_label` | string | yes | `GAL02` (recommended so Preview works; operator overwrites) | D-04 "required"; label is sliced to 20 chars |
| `stack_tool` / `fast_tool` | string | yes | `STACK` / `FAST` | workcell instance **names**, exact case |
| `robot` | string | yes | `sim-arm-1` | |
| `labware_profile` | string | yes | `greiner 96 white` | |
| `source_device`, `source_deck`, `source_nest` | string | yes | `sim-nest-a`, `sim-deck-a`, `sim-A1` | return destination too |
| `source_transfer_profile` | string | no | blank | omitted when blank |
| `fast_device`, `fast_deck`, `fast_nest` | string | yes | `sim-nest-b`, `sim-deck-b`, `sim-B1` | STACK's name for the F.A.S.T. position |
| `fast_transfer_profile` | string | no | blank | omitted when blank |
| `stack_timeout_s` | number | no | blank | blank = Config/adapter default (300 s, max 3600 s clamp, `server.py:98-99`) |
| `fast_step_source_deck` / `_dest_deck` | number | yes | `1` / `3` | v1 runbook Step 4 (`:196-203`) |
| `fast_step_source_plate_id` / `_dest_plate_id` | number | yes | `1` / `1` | |
| `fast_step_source_start_row` / `_dest_start_row` | string | yes | `A` / `A` | `^[A-Za-z]{1,2}$` (`fast/server.py:130`) |
| `fast_step_source_start_col` / `_dest_start_col` | number | yes | `1` / `1` | |
| `fast_step_num_rows` / `_num_cols` | number | yes | `8` / `1` | |
| `fast_step_volume` | number | yes | `10` | uL; > 0 |
| `fast_step_tip_reuse` | select | yes | `fresh` | options `["fresh","reuse"]` (`fast_mcp.authoring._TIP_REUSE_MODES`, verified `('fresh','reuse')`) |
| `fast_step_expected_tray_id` | number | no | blank | omitted when blank; avoids the v1 F2 "0 overrides Config" bug |

F.A.S.T. `Transfer` requires **all 12** `TransferRequest` fields present (`source_deck, dest_deck, source_plate_id, dest_plate_id, source_start_row, source_start_col, dest_start_row, dest_start_col, num_rows, num_cols, volume, tip_reuse`) or `_check_args` returns the missing names (`fast/server.py:194-197`); deck is `1.._DECK_SLOTS` = 6, ids/cols/rows >= 1, volume finite > 0 (`:197-228`). The mapping "STACK delivers the plate to F.A.S.T. deck `fast_step_source_deck`" is `[ASSUMED]` for hardware (Phase 7 decides); in sim it is only a stand-in.

### Offline FLOW-03 proof (prototyped, 2 passed)
```python
# Source: scratch prototype built on tools/tests/stack_test.py fixtures.
from tools.tests.stack_test import (_TransferTestCase, Refused, TaskHandle, _GUID,
    SUCCESS, ERROR_FROM_TOOL, stack_server, stack_pb2)   # NOT classes that contain tests
from google.protobuf.json_format import ParseDict

class TestGal02Replay(_TransferTestCase):
    def dispatch(self, p):                        # p = one STACK param dict from the script
        return self.stub.ExecuteCommand(self._stack(transfer=ParseDict(p, stack_pb2.Command.Transfer())))

    def test_forced_redispatch_sends_no_second_transfer(self):
        in_leg, out_leg = stack_legs_from_script()          # harness helper (node)
        self.assertEqual(self.dispatch(in_leg).response, SUCCESS)
        self.assertEqual(self.core.execute_calls, 1)
        again = self.dispatch(in_leg)                        # same stored params
        self.assertEqual(again.response, SUCCESS)
        self.assertIs(again.meta_data["replayed"], True)
        self.assertEqual(self.core.execute_calls, 1)         # submit count stays at 1
        self.assertEqual(self.core.call_names.count("plan_transfer"), 1)
        # different leg = different key + request: a normal fresh transfer
        self.assertEqual(self.dispatch(out_leg).response, SUCCESS)
        self.assertEqual(self.core.execute_calls, 2)
        # after REPLAY_WINDOW_S: refusal line, still no second submit
        future = stack_server._utcnow() + timedelta(seconds=REPLAY_WINDOW_S + 5)
        with patch.object(stack_server, "_utcnow", return_value=future):
            late = self.dispatch(in_leg)
        self.assertEqual(late.response, ERROR_FROM_TOOL)
        self.assertIn("step key already completed", late.error_message)
        self.assertEqual(self.core.execute_calls, 2)

    def test_refused_first_try_releases_key_then_submits_once(self):
        in_leg, _ = stack_legs_from_script()
        self.core.execute_result = Refused(reason="robotNotIdle")
        self.assertEqual(self.dispatch(in_leg).response, ERROR_FROM_TOOL)     # attempt 1: nothing sent
        self.core.execute_result = TaskHandle(guid=_GUID, robot="sim-arm-1", estimated_s=30.0)
        self.assertEqual(self.dispatch(in_leg).response, SUCCESS)             # attempt 2: the one submit
        self.assertEqual(self.core.execute_calls, 2)         # 1 refused + 1 accepted; see anti-pattern
        self.assertEqual(self.dispatch(in_leg).meta_data["replayed"], True)   # now replayed
        self.assertEqual(self.core.execute_calls, 2)
```
Observed this session: `execute calls 2`, replay meta keys `['ledgerState','replayed','result','stepKey']`, late refusal text "stack: step key already completed at 2026-11-02T02:44:26.603297+00:00; the protocol must mint a new step key per run; nothing was sent; step key b1-...-in". Add: a second script evaluation yields different `step_key` values (distinct from the first run's, `in != out`), and the hardware deny-set assertion `self.server.config.host not in {"10.150.1.125", "stack-server"}` (the fixture sets `config = stack_pb2.Config(host="127.0.0.1")`; it never calls Configure, so no real network).

### Node harness (stdin = `{"script", "params"}`; prototyped)
```python
HARNESS = r'''
const vm = require("vm"); const calls = [];
const galago = { command(t, c, p) { calls.push({tool: t, command: c, params: p}); },
                 note(m) { calls.push({tool: "Tool Box", command: "note", params: {message: m}}); } };
const input = JSON.parse(require("fs").readFileSync(0, "utf8"));
const ctx = vm.createContext({galago, params: input.params, console, Math, Array, Object, String,
  Number, Boolean, JSON, Date, parseInt, parseFloat, isNaN, isFinite});
try { new vm.Script(input.script, {filename: "protocol-script.js"}).runInContext(ctx, {timeout: 5000});
      console.log(JSON.stringify({ok: true, calls})); }
catch (e) { console.log(JSON.stringify({ok: false, error: String(e && e.message)})); }   // not instanceof Error!
'''
# subprocess.run([node, "-e", HARNESS], input=json.dumps({...}), capture_output=True, text=True, check=True)
```
Run the script once as is and once with `"use strict";` prepended (the docs claim strict mode; the executor does not add it). Params for the test = `{p["name"]: p.get("defaultValue", "") for p in protocol["parameters"]}`, which also proves the JSON defaults satisfy the script.

### DEP-02 precondition check (read-only; verified to FAIL today, as expected)
```bash
GC=/home/formulatrix/data/nikko/galago-core; GT=/home/formulatrix/data/nikko/galago-tools; ok=1
grep -q 'stack = "stack"' $GC/controller/gen-interfaces/controller.ts                || { echo "no ToolType.stack"; ok=0; }
test -f $GC/controller/gen-interfaces/tools/grpc_interfaces/stack.ts                 || { echo "no generated stack.ts"; ok=0; }
awk '/^  stack: \{/,/^  \},/' $GC/controller/components/tools/constants.ts | grep -q 'transfer' \
                                                                                      || { echo "no commandFields.stack.transfer"; ok=0; }
awk '/^  stack: \{/,/^  \},/' $GC/controller/components/tools/constants.ts | grep -q 'acknowledge' \
                                                                                      && { echo "commandFields.stack exposes acknowledge"; ok=0; }
cmp -s $GT/interfaces/tools/grpc_interfaces/stack.proto $GC/vendor/galago-tools/interfaces/tools/grpc_interfaces/stack.proto \
                                                                                      || { echo "vendored stack.proto != frozen"; ok=0; }
[ $ok = 1 ] && echo DEP-02 OK || echo "BLOCKED: galago-core Phase 5 (DEP-02) has not landed"
```
Results today (galago-core `feat/stack-tool`, HEAD `710d26b`): `grep -c 'stack = "stack"'` = 0; `stack.ts` absent; `commandFields` has no `stack:`; `vendor/galago-tools/.../stack.proto` absent (submodule at `cb7886d`, "heads/feat/fast-tool-39-gcb7886d"). Also confirm the galago-web **image/dev server in use** was built or started from that source (the production `galago-web` container, up 3 days on :3010, predates it) and run galago-core's own `commandFields` test (`controller/test/commandFields.test.ts`) there.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Idempotency only by the operator not clicking twice (v1 F.A.S.T. Finding F5, one queued transfer ran 3x) | Per-run `step_key` + persisted ledger in the STACK adapter | Phase 5 | A re-dispatch is a replay/refusal, never a second submit |
| Operator-only commands filtered only in the form | Deny-by-default tables enforced at enqueue and execute (`operatorOnlyCommands.ts:25-28`: `stack: ["acknowledge_failure"]`, `fast: ["pause", "resume", "abort"]`) | galago-core Phase 4 | The protocol must not emit them; it would be refused with `OperatorOnlyCommandError` |

**Deprecated/outdated:** CONTEXT's `port=5005` for this host (Pitfall 4); the doc claim that the script runs in strict mode (executor does not enforce it).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The PAC sim manager's logs (`docker logs stack-sim-manager` or `$STACK_SIM_DIR/logs-mgr`) record each `POST /api/v2/transfer`, so a before/after line count can serve as the "no second POST" counter | Open Question 1 | The "+0" evidence would be unfalsifiable; fall back to indirect evidence (same task guid, instant reply, robot idle) and say so in the Findings log |
| A2 | The sim DB at `$STACK_SIM_DIR/db/pac-manager.db` holds a queryable task table | Open Question 1 | Same as A1 |
| A3 | Tool-server ports in the 400xx range are reachable from the dev galago-core container through ufw (v1 runbook A3: 40000/11010 reachable, 4010 blocked, 40003 used) | Runbook outline | Container cannot reach the tool; operator adds a ufw rule (needs sudo, not an agent action) |
| A4 | Hardware mapping "STACK hands the plate to F.A.S.T. deck 1 (source), which then transfers to deck 3" is a sim stand-in only | Parameter table | Phase 7 must re-derive; no effect on Phase 6 |
| A5 | protobufjs coerces numeric strings and treats a present `null` as a present zero/crash for int32/string | Sandbox section | None: the recommendation (real numbers, omit optionals) does not depend on it |
| A6 | The dev galago-core compose (`docker-compose.dev.yml`, `-p galago-gal06`, ports override, `extra_hosts host-gateway`) can host the sim run on :3020 with its own fresh DB, as in v1 | Runbook outline | If not, the operator would need the production DB; **do not** use production `galago-web` on :3010 for sim tools |
| A7 | The sim account (`STACK_USER`/`STACK_PASSWORD` from `sim-account.env`) works for the tool server exactly as for stack-mcp (same core `open_service`, owner `galago`) | FLOW-04 | Auth failure at Configure; SUMMARY.md Q4 states the identity probe and `galago` owner pass, `[V facts, I end-to-end]` |

## Open Questions

1. **How is "the PAC sim manager's task list" read to count submitted tasks (D-11)?**
   - What we know: the core's transport has no list-tasks GET; the only task read is `GET /api/v2/transfer/{guid}` (`stack_automation_layer/transport.py:48-49`). SAL's own A.8 evidence says "No second POST reached STACK in the whole session" without naming a counter. The manager container mounts `${sim_real}/logs-mgr` at `/app/LogFiles` and `${sim_real}/db` at `/app/Database` (`sim_up.sh:188`); the `docker logs` of `stack-sim-manager` carried resolver diagnostics (A6/A7 rows).
   - What's unclear: whether those logs/DB record submissions in a countable form. [ASSUMED A1, A2]
   - Recommendation: add a **calibration step** to the FLOW-04 checkpoint before the replay: take the count (log lines matching `POST` + `/api/v2/transfer`, or the DB row count), run the first leg (expect +1), re-send (expect +0). If the counter does not move on the first leg it cannot prove a +0: record that as a Finding and rest the claim on (a) the replay reply carrying the **same task guid** as the first reply (`meta.result.task.guid`), (b) the reply returning in well under the ~20 s a real sim transfer takes, (c) `GET /api/v3/info/robot-state` showing `sim-arm-1` `idle` throughout, (d) exactly one ledger record, and (e) the FLOW-03 offline counter. Let the user judge whether (a)-(e) suffice for FLOW-04's "no second POST".

2. **Does the user accept the `port=5005` deviation and the `fast_step_` prefix?** Both are small but touch locked text (D-09, D-04 reversibility). Recommend yes to both; ask in the plan summary.

3. **Should the galago-core Protocols-page import defect be queued upstream?** It is galago-core scope; the workaround is documented. Recommend noting it in the runbook Findings and telling the user.

4. **Is a PAC checkout available at the pinned commit `26e00251e`?** `STACK_PAC_DIR` is unset and no checkout was found within depth 4; `/home/formulatrix/Stack-PAC/` holds `.deb` packages and a `db-backup/pac-manager.db`, which is not what `sim_up.sh` builds from (`sim_up.sh:160-170` checks `git describe --tags` ends `-g26e00251e`). Operator precondition for FLOW-04; first build is about 12 min and needs >= 3 GB on the scratch filesystem (`/home` has 50 G free; `/` and Docker's root `/var/lib/docker` have 19 G, 96% used).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python venv `galago-py310` | all tests | yes | 3.10.12; `pytest`, `ruff`, `mypy` present in `bin/` | - |
| `stack_automation_layer` in the venv | `stack_test` imports (else module skips) | yes | importable from the venv | - |
| `fast_mcp` in the venv | `tools.fast.server._check_args` in the harness | yes (`TransferRequest` fields listed) | - | skip that one assertion |
| `node` | D-08 harness, D-06 | **only via nvm** | v24.14.1 at `~/.nvm/versions/node/v24.14.1/bin/node`; **not** on default PATH | test locates it (Pitfall 6); skip with reason |
| `jq`, `curl` | runbook import/preflight | yes | `/usr/bin/jq`, `/usr/bin/curl` | python3 |
| Docker | Part 2 (operator) | yes | 29.1.3; `docker ps` works (not built/started by me) | - |
| PAC sim images / `stack-sim-*` containers / network | FLOW-04 | **no** | none present (`docker images` shows only unrelated stack-monitor images) | operator builds via SAL A.1 |
| PAC checkout `STACK_PAC_DIR` @ `26e00251e` | FLOW-04 build | **not found** | - | Open Question 4 |
| Port 5005 on loopback | PAC sim default | **taken** | `scoringservice-scoring-service-1` publishes `0.0.0.0:5005` | `STACK_SIM_PORT=<free>` (Pitfall 4) |
| Free tool-server ports | Part 2 | yes | only `40000` (a tool server), `11010` (Tool Box), `8081` (manager) in use among the relevant ports | use e.g. 40010/40011; ufw per A3 |
| galago-core with DEP-02 | FLOW-02..04 | **no** | `feat/stack-tool`, Phase 5 not started; no `ToolType.stack` | hard gate; plan stops `blocking-human` |
| Production `galago-web` (:3010) | - | running, 3 days | must **not** be used for sim tools | separate dev compose project on :3020 |

**Missing dependencies with no fallback:** galago-core DEP-02 (blocks FLOW-02/03-sim/04).
**Missing dependencies with fallback:** node on PATH, free sim port, PAC build, ufw rules.

### Operator run outline (for the runbook plans; none of it executed here)
- **Tool servers** (host, foreground, separate processes): F.A.S.T. sim: `FAST_MCP_LOCK_DIR=<empty dir> python -m tools.fast.server --port=40011` (v1 runbook Part A step 1). STACK simulated: `python -m tools.stack.server --port=40010` (`__main__` at `tools/stack/server.py:1365-1372`, `--port` required) with **no** sim credentials needed. STACK real vs PAC sim (a **different** process and port, e.g. 40012): `set -a; . $STACK_SIM_DIR/sim.env; . $STACK_SIM_DIR/sim-account.env; set +a; STACK_MCP_LOCK_DIR=<sim-only dir> STACK_STATE_DIR=<sim-only dir> python -m tools.stack.server --port=40012`. Use the venv python `~/data/nikko/.venvs/galago-py310/bin/python`, cwd = galago-tools root. Do **not** use the systemd `galago-tools` service (its env/ports are production's; its manager page restarts tool servers).
- **galago-core:** dev compose as a separate project so the production DB and `galago-web` are untouched: `docker compose -p galago-gal06 -f docker-compose.dev.yml -f <ports-override.yml> up -d` with a ports override like `~/data/nikko/.venvs/gal05-ports.override.yml` (`ports: !override ["3020:3010","9239:9229"]` plus `extra_hosts: host.docker.internal:host-gateway`). galago-core ignores the per-tool IP and uses `GRPC_HOST=host.docker.internal` (`server/tools.ts:76`), so only the tool's **port** matters. The dev compose bind-mounts `./controller`, so DEP-02 code is picked up without an image rebuild once present.
- **Workcell setup (operator, UI):** tools `STACK-SIM` (type `stack`, port 40010, Simulated ON), `FAST` (type `fast`, port 40011, Simulated ON, host `sim-no-contact.invalid` as in v1), `STACK-PACSIM` (type `stack`, port 40012, Simulated OFF, host `127.0.0.1`, port `$STACK_SIM_PORT`, absolute sim-only `ledger_dir`). Real Configure is clicked by the operator (an executor-issued real Configure was denied in v1 row B2).
- **Preflight (FLOW-04):** configured host is not `10.150.1.125` / `stack-server` (literal deny-set), `GetRobotStates` returns only `sim-` names, anonymous reads `GET /api/v3/info/manager-state` = `automated` and `robot-state` `sim-arm-1` `idle` (SAL A.3), `sim_seed.py check` printed `reach: reachable`.
- **Run:** import (Pitfall 1) -> Preview (4 commands, keys, no throw) -> queue once (runs = 1) -> run completes (about 150 s sim; about 60-100 s real STACK legs) -> record keys from the stored rows -> forced re-send of the in leg within 600 s from the tool page -> expect SUCCESS + `replayed: true` (real) / SUCCESS only (sim) -> wait > 600 s, re-send again -> expect the "step key already completed" refusal (real only).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `unittest` (class style) executed by both `python -m unittest discover` and `pytest`; plus `ruff check .` and `mypy --config-file=pyproject.toml tools` (all part of `bin/make test`) |
| Config file | `pyproject.toml` (`[tool.ruff]` line-length 100, py310; `[tool.mypy]` `disallow_untyped_defs = "True"`, tests are **not** excluded, so every test method needs `-> None` annotations) |
| Quick run command | `cd /home/formulatrix/data/nikko/galago-tools && PATH=$HOME/.nvm/versions/node/v24.14.1/bin:$PATH ~/data/nikko/.venvs/galago-py310/bin/python -m pytest tools/tests/gal02_handoff_test.py -q -rs -p no:cacheprovider` |
| Full suite command | `source ~/data/nikko/.venvs/galago-py310/bin/activate && export PATH=$HOME/.nvm/versions/node/v24.14.1/bin:$PATH && bin/make proto test` (baseline: `pytest tools/tests -q` = **510 passed in 10.8 s**, run this session) |

Note `python -m unittest discover -s tools/tests/ -p "*_test.py"` makes `tools/tests` the top-level dir, so modules load as `stack_test`, not `tools.tests.stack_test`. `from tools.tests.stack_test import ...` therefore imports a second copy under the package name; `tools/` is importable (cwd on `sys.path`; `stack_test` itself does `from tools.stack import ...`), so it works, but the plan should run **both** runners once to confirm.

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FLOW-01 | Export JSON shape: top-level keys exactly `protocol`, `exportedAt`, `version == "1.0"`; protocol keys `name, category, description, mode == "script", scriptContent, parameters, commands == []` | unit | `pytest tools/tests/gal02_handoff_test.py -k export_shape -q` | Wave 0 |
| FLOW-01 | Every `parameters[]` entry satisfies `zProtocolParameter` (name/label non-empty, type in enum, `defaultValue` is `str`, `required` is `bool`, `select` has `options`); names unique | unit | `-k parameters` | Wave 0 |
| FLOW-01 | Script emits `note`, STACK `transfer`, FAST `transfer`, STACK `transfer` in that order, using `stack_tool`/`fast_tool` names | unit (node) | `-k command_order` | Wave 0 |
| FLOW-01 | Keys non-blank, distinct (`-in` != `-out`), run-unique (two evaluations differ), <= 60 chars for the default label, label sliced at 20, timestamp/suffix preserved for a 100-char label | unit (node) | `-k step_key` | Wave 0 |
| FLOW-01 | Return leg is the swap of the in leg (`destination_*` of in == `source_*` of out and vice versa; robot/labware equal) | unit (node) | `-k swap` | Wave 0 |
| FLOW-01 | No operator-only command (`stack`: `acknowledge_failure`; `fast`: `pause`, `resume`, `abort`) and no `Tool Box` command other than `note`; defaults equal the sim lab (`sim-arm-1`, `greiner 96 white`, `sim-nest-a/sim-deck-a/sim-A1`, `sim-nest-b/sim-deck-b/sim-B1`) | unit (node) | `-k safe_defaults` | Wave 0 |
| FLOW-01 | A blank required input, or non-integer int field, makes the script throw (message read via `e.message`) and emit **zero** commands | unit (node) | `-k throws` | Wave 0 |
| FLOW-01 | Generated dicts parse into `stack_pb2.Command.Transfer` / `fast_pb2.Command.Transfer`; `fast.server._check_args == []` | unit | `-k proto_contract` | Wave 0 |
| FLOW-01 | The protocol JSON contains neither `10.150.1.125`, `stack-server` nor `stack2-6` (safe by default) | unit | `-k no_hardware_names` | Wave 0 |
| FLOW-03 (offline) | Re-dispatch -> `SUCCESS` + `replayed True`, `execute_calls == 1`; late re-dispatch -> refusal text, still 1; out leg is a separate fresh key; Refused-then-success total = 2 attempts / 1 accepted, then replay | integration (in-process gRPC, fake core) | `-k redispatch` | Wave 0 |
| FLOW-03 | Real-mode fixture host is not in the deny-set | unit | in the same class | Wave 0 |
| FLOW-02 | Both tools simulated: run completes 3 tool steps (+ note row) | **manual-only** (operator checkpoint; needs DEP-02, Docker UI, ~150 s) | runbook Part 2a; evidence in Findings log | n/a |
| FLOW-03 (sim half) | Simulated re-dispatch of the completed STACK step returns SUCCESS; `ls <ledger_dir>` shows no ledger file | **manual-only** | runbook Part 2a | n/a |
| FLOW-04 | Real STACK vs PAC sim + FAST sim completes; forced re-dispatch -> `replayed: true`; sim-side evidence per Open Question 1; late re-send refusal | **manual-only** (operator checkpoint, hardware-refusal preflight) | runbook Part 2b | n/a |
| FLOW-02..04 gate | DEP-02 precondition script returns 0 | scripted read-only check | the block in Code Examples | n/a |

Manual-only justification: they need galago-core with DEP-02, an operator-built PAC simulator and Docker, and a human at the keyboard (SAL A.0/A.10: no agent starts Docker, the sim or the run).

### Sampling Rate
- **Per task commit:** the quick command above (fast, about 1-2 s of node + the small gRPC fixture).
- **Per wave merge:** `pytest tools/tests -q -rs` with node on PATH, expecting 510 + new tests passed and **0 skipped in `gal02_handoff_test.py`**.
- **Phase gate (Part 1):** `bin/make proto test` green (ruff, mypy, unittest, pytest) with node on PATH; confirm the new module's tests ran (not skipped) in both runners.
- **Phase gate (Part 2):** Findings log rows for FLOW-02, FLOW-03-sim, FLOW-04 filled; `/gsd-verify-work` states explicitly (D-07) which property each environment proves.

### Wave 0 Gaps
- [ ] `tools/tests/gal02_handoff_test.py`: covers FLOW-01 and FLOW-03 (offline); new file
- [ ] `docs/runbooks/gal-02-handoff.protocol.json`: the artifact under test; created by the first task
- [ ] `docs/runbooks/` directory (does not exist; `docs/` has only `specs/`)
- No framework install needed.

## Security Domain

`security_enforcement` is enabled (`.planning/config.json`, `security_asvs_level: 1`).

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (sim account only) | Credentials only via the tool-server process environment (`STACK_USER`/`STACK_PASSWORD`, sourced from `sim-account.env`, mode 0600); never in the runbook, the JSON, the Findings log or shell history; the adapter already reads them only from env |
| V3 Session Management | no | - |
| V4 Access Control | yes | Operator-only commands stay refused (galago-core tables); protocol emits none; hardware deny-set in the runbook preflight and test fixtures |
| V5 Input Validation | yes | Script re-validates every parameter (blank, whole number, positive) and throws before emitting; adapter `_check_args` enforces `step_key`/`timeout_s`; `ParseDict` rejects unknown proto fields in the test |
| V6 Cryptography | no | none hand-rolled; step key uses `Math.random` for **uniqueness only, not secrecy** (documented) |
| V7 Logging | yes | Findings log may carry keys, guids, timestamps and replies; must not carry credentials or the Bearer token from the A.3 `curl` login |
| V14 Configuration | yes | Sim is loopback-only; sim-only absolute `ledger_dir`, `STACK_MCP_LOCK_DIR`, `STACK_STATE_DIR`; separate processes per mode |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Sim run reaches the real STACK (`10.150.1.125` / `stack-server`) | Tampering / Elevation | Runbook preflight refuses those hosts and non-`sim-` robot names; test fixtures assert the deny-set; protocol defaults are sim names; hardware names only in Phase 7 |
| Step key reused across runs (replayed SUCCESS while the plate sits elsewhere) | Tampering | Run-unique key from timestamp + random in the script; test asserts two evaluations differ |
| Sim keys poisoning hardware ledger (or vice versa) | Tampering | Simulated mode never writes the ledger (STK-06); FLOW-04 uses a sim-only `ledger_dir`; never delete the ledger file (Phase 5) |
| Wrong port: the Device master API (5006) or the unrelated service on 5005 | Tampering | Configure only `$STACK_SIM_PORT`; preflight reads `/api/general/application` productName `Stack manager` and robot names |
| `{{var}}` substitution in param values (`Tool.executeCommand` replaces any value that starts with `{{` and ends with `}}`) | Tampering | The step key always ends in `-in`/`-out`; other values are operator-typed; note only |
| Credentials leaking into logs/evidence | Information disclosure | Source env files inside the shell; paste nothing from `ps`/env into the Findings log |
| Operator queues `numberOfRuns > 1` | Repudiation / confusion | Runbook says 1; each run still gets its own keys |

## Sources

### Primary (HIGH confidence): read this session
- `/home/formulatrix/data/nikko/galago-core/controller/server/scripting/protocol-script-executor.ts` (whole file, 124 lines)
- `.../controller/server/runs.ts` (`generateCommandsFromProtocol` `:62-111`, `upsertParameterVariables` `:120-155`, `createFromProtocol`), `server/scripting/resolve-tool-types.ts`, `server/tools.ts` (`:361-367`, `:410-460`, `:606-628`), `server/operatorOnlyCommands.ts`, `server/routers/protocol.ts`, `server/routers/run.ts`, `server/command_queue.ts:1254`
- `.../controller/components/protocols/ProtocolPageComponent.tsx:92-146`, `components/hub/HubComponent.tsx:202-212`, `components/protocols/NewProtocolRunModal.tsx:47-153`, `components/tools/constants.ts` (`commandFields.fast`), `protocols/params.ts`, `pages/api/protocols/index.ts`, `gen-interfaces/tools/grpc_interfaces/fast.ts:321-362`
- `/home/formulatrix/data/nikko/galago-core/docs/script-protocols.md`, `.planning/ROADMAP.md`, `.planning/STATE.md` (DEP-02 not landed)
- This repo: `tools/stack/server.py`, `tools/stack/ledger.py`, `tools/fast/server.py`, `tools/base_server.py`, `tools/tests/stack_test.py` (fixtures), `interfaces/tools/grpc_interfaces/stack.proto` and `fast.proto`, `bin/make`, `pyproject.toml`, `.planning/{REQUIREMENTS,ROADMAP,STATE}.md`, `06-CONTEXT.md`
- `/home/formulatrix/data/nikko/stack-automation-layer/`: `docs/runbooks/stack-validation.md` Part A (A.0-A.10), `scripts/sim_up.sh`, `tests/sim_support.py:40-60,285-370`, `tests/netguard.py:15-26`, `tests/test_sim_flows.py:100-125`, `stack_automation_layer/transport.py:39-51`
- `/home/formulatrix/data/nikko/fast/fast-mcp/docs/runbooks/phase5-galago-live-run.md` (Parts A and B, rows A3/B2, Finding F5)
- Commands run: `node --version` (v24.14.1 under nvm only), `docker --version`/`docker ps`/`docker images`, `ss -ltnp`, `df -h`, `pytest tools/tests -q` (510 passed), scratch prototypes (node vm harness, `ParseDict`, replay test: 2 passed)

### Secondary (MEDIUM)
- `.planning/research/SUMMARY.md` § 3 and Q4 (earlier research, consistent with the above)
- Memory note `galago-local-setup.md` (ports, ufw, nvm PATH caveat)

### Tertiary (LOW)
- None used for recommendations. PAC manager log/DB contents are unverified (A1, A2).

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH, no new packages; all fixtures read and exercised.
- Architecture: HIGH for script/payload/import (source read, prototyped); MEDIUM for the Part 2 operator flow (nothing started).
- Pitfalls: HIGH for 1-3, 5-12 (each tied to a read line or a run command); MEDIUM for 4 (port taken is verified, the chosen replacement port is not).
- Sim-side "no second POST" counter: LOW until calibrated (Open Question 1).

**Research date:** 2026-11-02
**Valid until:** 2026-11-09 for the DEP-02 status and host port/Docker facts (fast-moving); 2026-12-02 for the sandbox/adapter facts unless galago-core Phase 5 or the Protocols-page import changes.
