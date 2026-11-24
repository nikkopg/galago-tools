# Phase 4: STACK Tool Registration, Reads & Estimate - Research

**Researched:** 2026-10-28
**Domain:** Galago gRPC tool adapter (Python 3.10) over a pinned in-house core (`stack-automation-layer` @ `ed8ce47`); proto registration; reply/Struct mapping; BUSY-bypass reads; AST safety invariants
**Confidence:** HIGH (everything below was read from code or executed against the real core and the real protoc toolchain in this session; open items are marked `[ASSUMED]`)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
D-01 .. D-22 are LOCKED (see `04-CONTEXT.md`, copied here in short form; the file is authoritative):

- **D-01** `interfaces/tools/grpc_interfaces/stack.proto`, package `com.science.foundry.tools.grpc_interfaces.stack`, `Command` oneof `command` with exactly ten entries in this order: `Transfer transfer = 1`, `GetManagerState get_manager_state = 2`, `GetRobotStates get_robot_states = 3`, `ListDevices list_devices = 4`, `ListLabwareProfiles list_labware_profiles = 5`, `ListTransferProfiles list_transfer_profiles = 6`, `GetLabwarePresence get_labware_presence = 7`, `GetTransferEstimate get_transfer_estimate = 8`, `AcknowledgeFailure acknowledge_failure = 9`, `GetFailureLatch get_failure_latch = 10`. One-way (DEP-02 freeze).
- **D-02** `ListTransferProfiles` is added; `Transfer`/`GetTransferEstimate` keep per-location `*_transfer_profile` fields.
- **D-03** Shapes follow SUMMARY.md "Proposed stack.proto" with fixes: every string field proto3 `optional`; adapter passes unset/blank instrument fields to the core as `None` (core's `missing_fields` makes `NeedsInput`); `Transfer` = `step_key`(1), `robot`, `labware_profile`, `source_{device,deck,nest,transfer_profile}`, `destination_{device,deck,nest,transfer_profile}`, `optional double timeout_s`(12); `GetTransferEstimate` = same request fields without `step_key`/`timeout_s`; `List*` = `optional bool refresh = 1`; `GetLabwarePresence` = `optional string robot = 1`; `AcknowledgeFailure` = `optional string guid = 1`, `optional string arm_inspected = 2`; `GetFailureLatch {}`.
- **D-04** `Config`: `string host = 1`, `int32 port = 2` (0 -> 5005), `double transfer_timeout_s = 3` (0 -> adapter default, Phase 5), `string ledger_dir = 4` (blank -> per-user state dir, Phase 5). **No `lock_dir` field.** Phase 4 validates `transfer_timeout_s` (finite, >= 0) and stores `ledger_dir`, creates nothing on disk. One-way.
- **D-05** No message named `GetStatus`, `EstimateDuration`, `Configure`, `ExecuteCommand`, or starting with `Estimate`.
- **D-06** `tool_base.proto` imports `tools/grpc_interfaces/stack.proto`, adds Command `stack = 24` and Config `stack = 43`; `controller.proto` `ToolType` adds `stack = 24`. `bin/make proto test` green on the 3.10 venv.
- **D-07** `_configure` mirrors `FastServer._configure`: host stripped non-blank; `port or 5005`; validate `transfer_timeout_s`; same `endpoint_key(host, port)` already owned -> return without reopening; else close old `OwnedService` first, then `open_service(host, port, owner="galago")` with no `lock_dir`. Credentials only from `STACK_USER`/`STACK_PASSWORD`. Compare using the core's `endpoint_key` and `OwnedService.endpoint`; no other host normalisation.
- **D-08** Any `open_service` failure propagates (`StackOwnedError`, missing credentials, identity probe, closed port); `base_server.Configure` returns `NOT_READY` with `error_message=str(e)`, status FAILED. Adapter does not reword the holder text. A test proves a lock held by an `owner="mcp"` holder in a temp `STACK_MCP_LOCK_DIR` fails Configure and the reply names it.
- **D-09** On a successful real-mode Configure log one WARNING: restarting this tool server clears the core's failure latch and in-flight guard (core gap G1); a failure must be acknowledged, not cleared by restart. A log line, not a policy check.
- **D-10** One `_reply(code, message="", meta=None)` helper copied from fast, always `return_reply=True`, meta from a Struct. Read kinds, `estimated`, `failureAcknowledged`, `ran` -> SUCCESS with an **empty** message, meta = `result.to_dict()` unchanged. Any other kind (and any unrecognised kind) -> `ERROR_FROM_TOOL` with meta = `to_dict()`. Adapter argument errors -> `INVALID_ARGUMENTS`. SUCCESS kinds are an explicit allowlist.
- **D-11** `ERROR_FROM_TOOL` message is one line, no newline, built from structured fields (kind, reason when present, guid when present), not the core's agent-worded `explanation` (G5). Full `explanation` stays in meta. Wording is planner's choice within these rules.
- **D-12** Map by `kind` (from `to_dict()` or the result class) using one table; map every kind regardless of a method's narrower return annotation (G4). Accept Struct number-to-double.
- **D-13** fast-style `StackServer.ExecuteCommand` override with one module-level `READ_COMMANDS` frozenset (`get_manager_state`, `get_robot_states`, `list_devices`, `list_labware_profiles`, `list_transfer_profiles`, `get_labware_presence`, `get_transfer_estimate`, `get_failure_latch`). A request with `WhichOneof("tool_command") == "stack"` whose inner command is in it skips `isReady`/`parseCommand`/`setStatus`, goes through `self._dispatchCommand(command)`, turns an `Exception` into `DRIVER_ERROR` and sets `last_error`. Everything else -> `super().ExecuteCommand(...)`. `tools/base_server.py` not edited.
- **D-14** Real mode, bypass read with no configured service -> `NOT_READY` "stack: not configured"; never reaches a `None` service.
- **D-15** `GetTransferEstimate` is in the bypass set (one estimation POST, never moves anything; core is thread-safe).
- **D-16** Prove STK-05 with an injected slow command: real mode, `MagicMock(spec=StackService)`, block a non-read command (patch the `Transfer` handler) on a `threading.Event`; reads return their result, status stays BUSY, a second non-read gets NOT_READY, after release status returns to READY. Write the failing test first.
- **D-17** Simulated mode validates adapter-owned arguments only (`Transfer.step_key` set and non-blank; `Transfer.timeout_s`, if set, finite and >= 0; `AcknowledgeFailure.guid` non-blank; `AcknowledgeFailure.arm_inspected` exactly `"yes"` or `"no"`) -> `INVALID_ARGUMENTS`; sleeps the `Estimate<Cmd>` constant, returns SUCCESS, never contacts the core, never writes a ledger.
- **D-18** Same adapter-argument checks run first in real mode (one shared `_check_args`). Only after they pass does real mode refuse `Transfer` / `AcknowledgeFailure` / `GetFailureLatch` with `ERROR_FROM_TOOL` and a one-line "not available in this build" message.
- **D-19** `Estimate<Cmd>` hooks return local integer constants, no I/O, never raise: `EST_TRANSFER_S = 35`, `EST_TRANSFER_ESTIMATE_S = 3`, `EST_READ_S = 2` (every read incl. `GetFailureLatch`), `EST_ACK_S = 2`. Planner may tune but must keep constant.
- **D-20** AST test over `tools/stack/` with a planted-violation check; fails if adapter code calls `plan_transfer`, `execute_transfer`, `start_transfer`, `wait`, `wait_transfer`, `cancel_transfer`, `go_to_safe_position`, `wait_safe_position`, `acknowledge_failure` or `validate_transfer` on the service. Phase 5 replaces it with the narrower XFR-05 invariant.
- **D-21** A second test asserts no module under `tools/stack/` imports `stack_automation_layer.mcp`.
- **D-22** `tools/stack/requirements.txt` pins `stack-automation-layer @ git+https://gitlab.formulatrix.com/nikkopg/stack-automation-layer.git@ed8ce478d8881a517eb93ed233707f81aea01238`, no `[mcp]` extra. A test asserts the SHA pin mirroring fast's. `pyproject.toml` gets a mypy override for `stack_automation_layer` and `stack_automation_layer.*`. If the GitLab install fails on forb01, install from the local clone at `ed8ce47` (fast-mcp precedent). `stack_test.py` skips cleanly when the core is missing.

### Claude's Discretion
- File layout inside `tools/stack/server.py` (mapping table / message builder in module or small helper module).
- Exact one-line message wording (D-11) and exact estimate values (D-19), within the stated rules.
- Whether to add `tools/tool_images/stack.png` (optional; fast has none).
- How tests build fake results: real core result classes preferred over hand-built dicts.

### Deferred Ideas (OUT OF SCOPE)
- `run_state`-style STACK heartbeat on the health `GetStatus` (fast's ADP-05).
- Exposing `refresh()` / `refresh_devices()` as commands (`devices(refresh=True)` covers v2).
- A tool-page-only command list so `AcknowledgeFailure` stays out of the protocol builder (galago-core decision, DEP-02/DEP-03).
- Adapter refusal of `Configure` while a run is in flight (v2 Future Requirement).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STK-01 | `stack.proto` exists and is registered; `bin/make proto test` green | Proto draft compiled and introspected with the real grpcio-tools 1.70 / protobuf 5.29 (Registration section, Pattern 1); gate command and baseline (147 tests, ruff clean, mypy clean) |
| STK-02 | Configure with host/port; `open_service(..., owner="galago")`; env credentials; no `.mcp` import; SHA pin; no `lock_dir`; stack-mcp lock fails Configure naming holder | `open_service` order, exception types, lock-contention test recipe executed in-process; install step; AST/pin tests |
| STK-03 | Six reads, each 1:1 onto a core method, contract v1 `to_dict()` in meta | Verified kinds, signatures and Struct round-trip of every read via the real core with fixtures |
| STK-04 | `GetTransferEstimate` -> `estimate_transfer`; `Estimate<Cmd>` local constants | `estimate_transfer` result kinds (`estimated`/`rejected`/`needsInput`/`readFailed`) verified; hooks pattern from fast |
| STK-05 | Reads work while a command holds BUSY; motion stays serialised | base_server gate read; fast override + blocked-Transfer test pattern (line cites) |
| STK-06 | Simulated mode validates args, sleeps the constant, no core contact | base_server simulated branch; `_check_args` placement; sleep-patching pattern |
| STK-07 | Result mapping table; non-read kinds -> `ERROR_FROM_TOOL`; never SUCCESS on rejection | Per-kind `reason`/`guid` locations table; galago-core reply handling read |
</phase_requirements>

## Summary

Phase 4 is mechanical on the galago-tools side (fast is a close template) and its genuine risk is in four places the milestone research did not pin down: (1) the STACK core **probes the instrument eagerly at `open_service`**, so a Configure against a closed port **fails** (`NOT_READY`, `StackTransportError`), unlike fast where a closed-port Configure succeeds; every test that needs a *successful* real-mode Configure must patch `tools.stack.server.open_service` to inject a fake transport; (2) the owner lock is an in-process-visible `flock`, so a test can hold an `owner="mcp"` lock in the same process and Configure fails before any network I/O; (3) the core is **not installed** in the 3.10 venv and the GitLab HTTPS URL is not installable non-interactively from this shell (auth failure), so the plan needs an explicit install step via `git+file://` (same as the fast-mcp precedent; dry-run verified); (4) galago-core **does** display `ConfigureReply.error_message` for a failed Configure (error toast), so D-08's lock-holder text reaches the operator.

Everything else is exactly as CONTEXT.md decided. The core's contract v1 shapes, constructor signatures, exception types and the `OwnedService` API are pinned below with verbatim quotes. The proto draft compiles cleanly with the repo's protoc toolchain and the registration numbers (24 / 43 / 24) resolve; the compiled descriptors confirm `optional` presence semantics, including the trap that `HasField` is `True` for a field set to `""`.

**Primary recommendation:** Build in this order, with the gate green after each wave: (W0) install the core via `git+file://` at `ed8ce47`, write `stack.proto` + the three registration edits, run `bin/make proto test`; (W1) `tools/stack/server.py` skeleton, `_configure`, `_reply`, kind mapping table, reads, sim mode, estimate hooks; (W2) the red-then-green BUSY-bypass test and `ExecuteCommand` override, then the AST/pin/proto-freeze invariant tests.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Operator command forms, error toast, run orchestration | galago-core (controller/UI, external repo) | - | Out of scope here; DEP-02/03. Only its contract matters: error-text visibility rules (below) |
| gRPC surface, Configure, BUSY gate, simulated mode, reply mapping | Tool-server adapter (`tools/stack/`, this repo) | `tools/base_server.py` (unchanged) | Adapter owns argument checks, reply codes, constants; holds no instrument rule |
| Single-owner lock, credentials, identity probe, validation, estimation, reads | Pinned core (`stack_automation_layer`) | - | The core owns every decision; adapter is 1:1 |
| Instrument state, planning, motion | STACK manager (`10.150.1.125`, **never contacted**) | - | Phase 4 has no real-mode path that moves the arm; tests use mocks, loopback closed ports and temp lock dirs |
| Step-key ledger | (Phase 5) | - | Phase 4 stores `ledger_dir` only; creates nothing on disk |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `stack-automation-layer` | 0.1.0 @ `ed8ce478d8881a517eb93ed233707f81aea01238` | The only way the adapter reaches STACK (`composition.open_service`) | Locked D-22. First-party core on `origin/feat/initial-layer` (`git branch -r --contains ed8ce47` -> `origin/feat/initial-layer`) [VERIFIED: git] |
| `httpx` | 0.28.1 (already in venv) | Core's only dependency (`httpx>=0.27,<1`) | Transitive via the core; not added by this phase [VERIFIED: `pip list`, core `pyproject.toml`] |
| `grpcio` / `grpcio-tools` / `protobuf` | 1.70.0 / 1.70.0 / 5.29.6 | Server, protoc, Struct | Already pinned by repo [VERIFIED: `pip list` in venv] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `unittest` + `unittest.mock` | stdlib (py 3.10.12) | Test framework; `MagicMock(spec=StackService)` | All tests (fast precedent); pytest 7.4.3 also runs the same files [VERIFIED: `pip list`] |
| `ruff` 0.9.4, `mypy` 1.11.2 | pinned in `requirements-dev.txt` | Gate | `bin/make test` [VERIFIED: requirements-dev.txt] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `git+file://` install | `git archive` + `pip install <dir>` | Archive install has no `direct_url.json` `vcs_info`, so the fast-style pin test (`commit_id == pinned SHA`) would fail. Use `git+file://` |
| `git worktree` of the core | - | Writes into the core repo's `.git` (forbidden). Not needed |

**Installation (recommended plan step; NOT run in this research):**
```bash
# One-off, per developer machine. The GitLab HTTPS URL in requirements.txt is the canonical pin
# but is not installable non-interactively from this shell (git ls-remote -> "Authentication failed").
~/data/nikko/.venvs/galago-py310/bin/python -m pip install --no-cache-dir \
  "stack-automation-layer @ git+file:///home/formulatrix/data/nikko/stack-automation-layer@ed8ce478d8881a517eb93ed233707f81aea01238"
```
**Evidence:** `pip install --dry-run --no-deps "<that spec>"` in the 3.10 venv ended `Would install stack-automation-layer-0.1.0` (pip 26.2.1) [VERIFIED: command run]. `pip show stack-automation-layer` -> `WARNING: Package(s) not found` (core currently NOT installed) [VERIFIED]. `git ls-remote https://gitlab.formulatrix.com/nikkopg/stack-automation-layer.git` -> `fatal: Authentication failed` in this shell [VERIFIED]. Precedent: `fast_mcp`'s `direct_url.json` is `{"url": "file:///home/formulatrix/data/nikko/fast/fast-mcp", "vcs_info": {"commit_id": "b30b38df48e8480f325228145ccae7915a56e437", "requested_revision": "b30b38df48e8480f325228145ccae7915a56e437", "vcs": "git"}}` [VERIFIED: file read], i.e. a `git+file://` install records the SHA that the pin test compares. `bin/make deps` swallows install failures (`|| echo "Failed to install $req" >&2 || true`), so a failed GitLab install is silent; the local `git+file` install must be done explicitly [VERIFIED: bin/make deps()]. Note the local checkout is on `main` (unrelated initial commit `0ff8f87`); `git+file://...@<sha>` works because pip clones then checks out the SHA, which exists locally under `origin/feat/initial-layer`. Do not check out or modify the core repo.

**Version verification:** the version is pinned by SHA, not by registry; PyPI does not host this package (see Audit).

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| `stack-automation-layer` | none (in-house GitLab, git+SHA only) | first-party (user's own fork `nikkopg`) | n/a | `gitlab.formulatrix.com/nikkopg/stack-automation-layer` | seam: SLOP (`does-not-exist` on PyPI) | **Approved by locked decision D-22; NOT removed.** The seam rates any non-PyPI package SLOP; this is a false positive. It is never resolved from PyPI (a `name @ git+URL@sha` direct reference does not consult the index), pinned by 40-hex SHA, and the installed SHA is asserted by a test. Planner: make the install a `checkpoint:human-action` (GitLab credentials / local clone), not a silent `pip install` |
| `httpx` | PyPI | 6 yrs | seam: unknown (data gap) | github.com/encode/httpx | seam: SUS (`unknown-downloads`) | Already installed (0.28.1) as the core's own dependency; this phase adds no `httpx` requirement. No action |

**Packages removed due to [SLOP] verdict:** none (the one SLOP is the locked first-party core; see above).
**Packages flagged as suspicious [SUS]:** `httpx` (registry data gap only; well-known, pre-installed, not added by this phase).

`gsd_run query package-legitimacy check --ecosystem pypi stack-automation-layer httpx` was run [VERIFIED: tool output]. No other package is introduced.

## Core Contract (pinned at `ed8ce47`, executed against the real classes)

All shapes below were checked by importing a `git archive` extract of `ed8ce47` into the venv interpreter (no install) and calling the real classes and `FakeTransport` fixtures from the core's own `tests/` [VERIFIED: executed]. Line numbers are in `git show ed8ce47:<file>`.

### Result kinds (`stack_automation_layer/results.py`)
`CONTRACT_VERSION = 1` (:64). `kind` strings (quoted verbatim from the class bodies):

| Class | `kind` | Line | Top-level `to_dict()` keys (verified) | Carries `reason`? | Carries `guid`? |
|-------|--------|------|---------------------------------------|-------------------|-----------------|
| `ManagerState` | `managerState` | 104 | `kind, mode, recovery, apiVersion` (+`productVersion` if reported) | no | no |
| `ReadFailed` | `readFailed` | 151 | `kind, error{status,name,family,code,detail}` (+`message` for presence) | no | no |
| `DeviceTree` | `deviceTree` | 194 | `kind, deviceCount, devices, ambiguous, apiVersion` | no | no |
| `RobotStates` | `robotStates` | 225 | `kind, robots` | no | no |
| `LabwareProfiles` | `labwareProfiles` | 236 | `kind, profiles` | no | no |
| `TransferProfiles` | `transferProfiles` | 247 | `kind, profiles` | no | no |
| `LabwarePresence` | `labwarePresence` | 258 | `kind, robotName, hasLabware` | no | no |
| `KnowledgeRefreshed` | `knowledgeRefreshed` | 278 | counts | no | no (adapter never calls `refresh()`) |
| `NeedsInput` | `needsInput` | 352 | `kind, missing, detail` | no | no |
| `Rejected` | `rejected` | 371 | `kind, stage, findings, httpStatus, advisories` | no (stage/findings) | no |
| `Estimated` | `estimated` | 474 | `kind, estimatedTime, guid, advisories` (+`seconds` if parsed) | no | **top-level `guid` (the estimation guid, may be `null`)** |
| `Refused` | `refused` | 702 | `kind, reason, state, detail` | **`reason`** | only inside `detail.guid` (`failureLatched`, `inFlight`, `notOwned`, ...) |
| `FailureAcknowledged` | `failureAcknowledged` | 773 | `kind, guid, resultKind, explanation` | no | top-level `guid` |
| `Ran` | `ran` | 791 | `kind, task, transfer` | no | `task.guid` |
| `Failed` | `failed` | 823 | `kind, task, transfer, recovery, reason, managerMode, explanation, context` | `reason` (may be `null`) | `task.guid` |
| `Aborted` | `aborted` | 894 | `kind, task, transfer, initiator, message` | no | `task.guid` |
| `Cancelled` | `cancelled` | 938 | `kind, handle, lastState, message` | no | `handle.guid` |
| `TimedOut` | `timedOut` | 972 | `kind, task, handle, message` | no | `handle.guid` (and `task.guid` if any) |
| `Lost` | `lost` | 1019 | `kind, handle, lastState, reason, detail, message, explanation, context` | **`reason`** | `handle.guid`; **`null` for `submitOutcomeUnknown`** (the `submit-<hex>` id is only in free-text `explanation`) |
| `TaskHandle` | (instance field `kind`, default `"transfer"`) | 658 | `kind, guid, robot, estimatedS` | n/a | `guid` — **not a result kind; never return it from a handler** |

Generic guid extraction for D-11 (first hit wins): `d["guid"]` -> `d["task"]["guid"]` -> `d["handle"]["guid"]` -> `d["detail"]["guid"]`, each guarded with `isinstance(..., dict)`. Reasons: `d.get("reason")`. Verified examples: `{"kind": "refused", "reason": "failureLatched", "state": null, "detail": {"guid": "g1", "kind": "failed", "explanation": "x"}}`; `{"kind": "needsInput", "missing": ["robot"], "detail": null}`; `{"kind": "readFailed", "error": {"status": null, "name": "Exception", "family": "http", "code": null, "detail": null}}`; `Estimated` on the sim fixtures: `{"kind": "estimated", "estimatedTime": "00:00:48", "guid": null, "advisories": [], "seconds": 48.0}`.

**Reachable in Phase 4** (reads + estimate only): the six read kinds, `estimated`, `readFailed`, `rejected`, `needsInput`. The other kinds are reachable only via the mapping-table unit test (build them with the real result classes: `Refused(reason=...)`, `Lost(reason="submitOutcomeUnknown")`, `Failed(task=TaskSnapshot(...))`, etc.). `to_dict()` output for every read kind round-trips through `Struct.update()` (checked with sim fixtures); numbers become doubles (`code: -9001.0`, `deviceCount: 3.0`) [VERIFIED: executed].

### Service API (`stack_automation_layer/service.py`, signatures via `inspect.signature`)
```
manager_state(self) -> 'ManagerState | ReadFailed'                         # :376
devices(self, *, refresh: 'bool' = False) -> 'DeviceTree | ReadFailed'      # :389
robot_states(self) -> 'RobotStates | ReadFailed'                           # :406
labware_profiles(self, *, refresh: 'bool' = False) -> 'LabwareProfiles | ReadFailed'     # :418
transfer_profiles(self, *, refresh: 'bool' = False) -> 'TransferProfiles | ReadFailed'   # :428
labware_presence(self, robot: 'str') -> 'LabwarePresence | ReadFailed'     # :438
estimate_transfer(self, request: 'TransferRequest') -> 'Estimated | Rejected | NeedsInput | ReadFailed'  # :561
```
`refresh` is keyword-only. The service is "typed, never-raising" (docstring :269-270): every read wraps `except Exception` into `ReadFailed`. The adapter should still treat an exception from a service call as `DRIVER_ERROR` (D-13 does so on the bypass path; base_server does on the normal path).

**Blank `robot` trap (executed):** `labware_presence(None)` returns `readFailed` (`TypeError`) with **zero I/O**, but `labware_presence("")` **issues a request** for path `/api/v2/robot//labware/presence`. So the adapter must normalise unset/blank `robot` to `None` (as D-03 says for every instrument field), never forward `""` [VERIFIED: executed against `RestStackClient` on a closed loopback port]. mypy is unaffected (the core ships no `py.typed`).

### Request types (`stack_automation_layer/model.py`, executed signatures)
```
TransferRequest (robot: 'str | None' = None, labware_profile: 'str | None' = None,
                 source: 'Location | None' = None, destination: 'Location | None' = None)
Location (device: 'str | None' = None, deck: 'str | None' = None, nest: 'str | None' = None,
          transfer_profile: 'str | None' = None)
```
Frozen dataclasses; `missing_fields()` treats blank/whitespace as absent and reports containing fields `robot, labwareProfile, source, destination`. Reference mapping (read, never import): `mcp/server.py:67-97` `_transfer_request` builds `TransferRequest(robot=..., labware_profile=..., source=Location(device=, deck=, nest=, transfer_profile=), destination=Location(...))`. The adapter builds the same object from the ten proto fields, with blank -> `None`.

### `open_service` / `OwnedService` (`composition.py`, `owner_lock.py`, `errors.py`, `transport.py`)
```
open_service (host: 'str', port: 'int' = 5005, *, owner: 'str', lock_dir: 'str | None' = None, transport=None) -> 'OwnedService'
```
- **Order** (docstring + body): `acquire_owner_lock` -> `Credentials.from_env()` -> build `RestStackClient` (unless `transport` given) -> `_probe_identity` (anonymous GETs) -> `StackService`. On any exception the stack is closed and the lock released before re-raising (executed: lock re-acquirable after a failed open).
- `OwnedService` instance attributes (executed `vars()`): `service`, `owner`, `endpoint`, `identity`, plus private `_stack/_lock/_closed`. `.endpoint` is `lock.key` = `endpoint_key(host, port)` = `"<lowercased host>:<port>"` (executed: `127.0.0.1:5005`). `.close()` is idempotent; closes the client first, releases the lock last. Also a context manager.
- `endpoint_key` lives in `owner_lock` (`composition.__all__ = ["OwnedService", "StartupIdentity", "open_service", "StackOwnedError"]` does **not** re-export it). Import `from stack_automation_layer.owner_lock import endpoint_key` (the AST allowlist for tests must permit `stack_automation_layer.owner_lock`).
- `StackOwnedError(RuntimeError)`; `str()` verbatim: `STACK manager 127.0.0.1:53693 is already owned by mcp (pid 764738); only one front end may hold it at a time (stop the other owner first)` [VERIFIED: executed, in-process]. Attributes `.host .port .holder`. It is importable from `composition` and `owner_lock`.
- Missing credentials: `StackCredentialsMissing(StackError)`, `str()`: `STACK credentials missing: set STACK_USER and STACK_PASSWORD in the environment` [VERIFIED: executed]. Raised **after** the lock is taken and **before** any request.
- **Closed port: `StackTransportError(StackError)`**, `str()`: `transport error calling /api/general/application: ConnectError` [VERIFIED: executed on a closed loopback port]. Wrong target: `StackIdentityError` (`Target is not a STACK manager (productName mismatch or no supported API version)`); a 401 on a probe route: `StackLicenseError`. All derive from `StackError(Exception)`; none echo bodies or credentials.
- **Injected transport (tests):** yes. `open_service(..., transport=fake)` skips `RestStackClient` but still calls `Credentials.from_env()` (so `STACK_USER`/`STACK_PASSWORD` must be set) and still runs `_probe_identity`, which needs `fake.get_application()` -> `{"productName": "Stack manager", ...}` and `fake.get_versions()` -> `{"2": ..., "3": ...}` (exact casing `"Stack manager"`; version keys must contain `"2"`; `"3"` selects api v3). A bare `MagicMock()` with those two return values suffices (its `set_api_version` is a harmless MagicMock). `EXPECTED_PRODUCT_NAME = "Stack manager"` (composition.py:37). The core's richer `FakeTransport` is in the core repo's `tests/fakes.py`, **not shipped**, so galago-tools tests use `MagicMock(spec=StackService)` for handlers and a two-method fake transport for Configure.

### Lock directory
`LOCK_DIR_ENV = "STACK_MCP_LOCK_DIR"`; `default_lock_dir()` reads the env **at call time** (owner_lock.py:42-47), so with no `lock_dir` argument (D-07/D-04) tests redirect locks via `patch.dict(os.environ, {"STACK_MCP_LOCK_DIR": tmp})` (executed: contention observed through the env dir). `OWNERS = ("mcp", "galago")`.

## Registration (files and the proven draft)

| # | File | Change |
|---|------|--------|
| 1 | `interfaces/tools/grpc_interfaces/stack.proto` | NEW (draft below) |
| 2 | `interfaces/tools/grpc_interfaces/tool_base.proto` | `import "tools/grpc_interfaces/stack.proto";` after the `fast.proto` import; `tools.grpc_interfaces.stack.Command stack = 24;` after `...fast.Command fast = 23;` (Command oneof `tool_command`); `tools.grpc_interfaces.stack.Config stack = 43;` after `...fast.Config fast = 42;` (Config oneof `config`) |
| 3 | `interfaces/controller.proto` | `stack = 24;` after `fast = 23;` in `enum ToolType` |
| 4 | `tools/stack/__init__.py` | NEW, empty (`find_tool_packages()` ships any `tools/**` dir with `__init__.py`: setup.py:104-117) |
| 5 | `tools/stack/server.py` | NEW; `class StackServer(ToolServer)`, `toolType = "stack"`, `__main__` with `--port` calling `serve(StackServer(), str(args.port))` (fast server.py:1008-1015); launched as `python -m tools.stack.server --port=N` (`get_shell_command`, utils.py:30-31) |
| 6 | `tools/stack/requirements.txt` | NEW; the single SHA-pinned line (D-22), comments allowed |
| 7 | `pyproject.toml` | mypy override `module = ["stack_automation_layer", "stack_automation_layer.*"]`, `ignore_missing_imports = true` (copy fast's block, pyproject.toml lines at the end) |
| 8 | `tools/tests/stack_test.py` | NEW |

Current values quoted verbatim from this session's reads: `tool_base.proto` has `tools.grpc_interfaces.fast.Command fast = 23;` (Command oneof `tool_command`) and `tools.grpc_interfaces.fast.Config fast = 42;` (Config oneof `config`); `controller.proto` has `fast = 23;` as the last `ToolType` entry. 24 and 43 are unused [VERIFIED: file reads]. `ToolType` has pre-existing gaps (no 8) — irrelevant.

**Toolchain proof.** I wrote the D-01..D-04 proto to a scratch copy of `interfaces/`, applied the three registration edits there, and compiled with the repo's own commands (`python -m grpc_tools.protoc -Iinterfaces/ --python_out --pyi_out --grpc_python_out ...`, both invocations of `proto_py`) [VERIFIED: executed; nothing written in the repo]. Introspection of the compiled modules (protobuf 5.29.6):

```
oneof: [('transfer', 1), ('get_manager_state', 2), ('get_robot_states', 3), ('list_devices', 4),
        ('list_labware_profiles', 5), ('list_transfer_profiles', 6), ('get_labware_presence', 7),
        ('get_transfer_estimate', 8), ('acknowledge_failure', 9), ('get_failure_latch', 10)]
Transfer fields: [('step_key', 1, True), ('robot', 2, True), ('labware_profile', 3, True)] ...   # has_presence True
Config: [('host', 1, False), ('port', 2, False), ('transfer_timeout_s', 3, False), ('ledger_dir', 4, False)]
cmd stack 24 tool_command ; cfg stack 43 config ; ToolType stack: 24
HasField robot: False ; HasField step_key: True ; blank-set (robot=""): True
ListDevices().HasField("refresh") False ; ListDevices(refresh=False).HasField("refresh") True
```
Consequences: (a) `HasField` is `True` for a field set to `""`, so the adapter's normaliser must be `value if HasField(name) and value.strip() else None`, never `HasField` alone; (b) `Config` scalars have no presence (0/"" mean unset: `port or 5005`, `transfer_timeout_s == 0` -> default); (c) the generated `.pyi` contains no per-field `HasField` literals, so a `HasField(name_variable)` loop type-checks without `cast(Any, ...)` `[ASSUMED: mypy not run on stack code; follow fast's cast(Any, command) if mypy complains]`.

The draft proto used for the probe (carry the comment block of CONTEXT `<specifics>` into the real file: `step_key` unique per run; `arm_inspected` is `"yes"` only after the arm was inspected and STACK recovered in the STACK Manager; there is no `lock_dir` because both front ends must contend on the same lock):
```proto
syntax = 'proto3';
package com.science.foundry.tools.grpc_interfaces.stack;
message Command {
  oneof command {
    Transfer transfer = 1;                          GetManagerState get_manager_state = 2;
    GetRobotStates get_robot_states = 3;            ListDevices list_devices = 4;
    ListLabwareProfiles list_labware_profiles = 5; ListTransferProfiles list_transfer_profiles = 6;
    GetLabwarePresence get_labware_presence = 7;    GetTransferEstimate get_transfer_estimate = 8;
    AcknowledgeFailure acknowledge_failure = 9;     GetFailureLatch get_failure_latch = 10;
  }
  message Transfer { optional string step_key = 1; optional string robot = 2; optional string labware_profile = 3;
    optional string source_device = 4; optional string source_deck = 5; optional string source_nest = 6;
    optional string source_transfer_profile = 7; optional string destination_device = 8;
    optional string destination_deck = 9; optional string destination_nest = 10;
    optional string destination_transfer_profile = 11; optional double timeout_s = 12; }
  message GetManagerState {}  message GetRobotStates {}
  message ListDevices { optional bool refresh = 1; } message ListLabwareProfiles { optional bool refresh = 1; }
  message ListTransferProfiles { optional bool refresh = 1; } message GetLabwarePresence { optional string robot = 1; }
  message GetTransferEstimate { optional string robot = 1; optional string labware_profile = 2;
    optional string source_device = 3; optional string source_deck = 4; optional string source_nest = 5;
    optional string source_transfer_profile = 6; optional string destination_device = 7;
    optional string destination_deck = 8; optional string destination_nest = 9;
    optional string destination_transfer_profile = 10; }
  message AcknowledgeFailure { optional string guid = 1; optional string arm_inspected = 2; }
  message GetFailureLatch {}
}
message Config { string host = 1; int32 port = 2; double transfer_timeout_s = 3; string ledger_dir = 4; }
```
(Reformat one field per line in the real file.) Note this ordering differs from SUMMARY.md's draft (presence=6 / estimate=7 / ack=8 there); **D-01's order is the frozen one** — add a "proto freeze" test pinning every `(name, number)` pair.

After editing any `.proto`, run `bin/make proto` before tests: generated `*_pb2*.py[i]` are gitignored (`.gitignore:1` `*_pb2*.py`), so `stack_pb2` and the regenerated `tool_base_pb2`/`controller_pb2` do not exist until regenerated [VERIFIED: `git check-ignore -v`].

## Test Gate and Baseline

- **Gate:** `bin/make proto test` (`bin/make` `test()`): `ruff check .` -> `mypy --config-file=pyproject.toml tools --install-types --non-interactive` -> `python -m unittest discover -s tools/tests/ -p "*_test.py"` -> `pytest tools/tests/ -vv`. `proto()` = `clean_proto` (removes `tools/*_pb2*.py*`) + `proto_py` (two protoc invocations) [VERIFIED: bin/make]. Needs the venv on PATH: `source ~/data/nikko/.venvs/galago-py310/bin/activate && bin/make proto test`.
- **Discovery:** both runners pick up `tools/tests/stack_test.py` automatically (pattern `*_test.py`; pytest's default `python_files` also matches `*_test.py`); `tools/tests/__init__.py` exists. Test classes must subclass `unittest.TestCase`.
- **Baseline (executed read-only this session):** unittest ran **147 tests OK** (1.3 s); pytest collected 147 (`fast_test.py` 143, `lcus1_relay_test.py` 3, `slack_helper_test.py` 1); `ruff check .` -> `All checks passed!`; `mypy --config-file=pyproject.toml tools` -> `Success: no issues found in 89 source files` (without `--install-types`). Expect the count to rise by the number of new stack tests; the pre-existing 147 must stay green. (`ruff` prints a harmless deprecation warning about top-level settings.)
- **Mypy constraints that bite test and server code:** `disallow_untyped_defs = "True"`, `check_untyped_defs`, `warn_return_any`, `no_implicit_optional` — every function incl. test methods needs annotations (`-> None`); `tools/tests/` is inside the mypy scope (`mypy ... tools`) [VERIFIED: pyproject.toml].

### fast_test.py anchors to mirror (line numbers in the current file)
| Need | Anchor |
|------|--------|
| Skip guard: one `try` around every core-dependent import; `except ModuleNotFoundError` -> `raise unittest.SkipTest(...)` when `exc.name.split(".")[0]` is the core (or httpx) | `fast_test.py:31-79`; the `except` at `:70` |
| `_free_tcp_port()` helper (copy it; do not import across test modules) | `:271` |
| In-process gRPC server + stub fixture; closed-port Configure through the stub; lock-file holder record check (`'"owner": "galago"'`, `os.getpid()`); re-Configure same endpoint reuse; second server on same endpoint refused naming `galago` | `TestTransferEndToEndOverGrpc` `:279-337`, test at `:305` |
| `patch("tools.fast.server.open_service")` and `patch("tools.base_server.time", types.SimpleNamespace(time=time.time, sleep=self.fake_sleep))` to avoid real sleeps in simulated tests | `:352`, `:357` |
| Real-mode in-process gRPC fixture with `MagicMock(spec=...)` injected, `status = READY`, `config` set | `_RealModeGrpcTestCase` `:804-838` |
| Blocked-Transfer helper (block the service call on a `threading.Event` over the gRPC stub; cleanups LIFO: `addCleanup(thread.join, 10)` then `addCleanup(release.set)`) | `_start_blocked_transfer` `:841` |
| "controls reach a run in flight; health stays BUSY; after release READY" assertions | `:899-935` |
| Not-configured behaviour, reconfigure (close old lock first; `acquire_owner_lock(...).release()`; held lock raises `InstrumentOwnedError`) | `TestNotConfigured` `:2517`, `TestReconfigure` `:2548` |
| 1:1 surface tests: handler-name set == oneof message names; `MagicMock(spec=Service)` each command records exactly one mapped call | `TestOneToOneSurface` `:2591-2654` |
| Registration tests (`controller_pb2.ToolType.Value`, `fields_by_name[...]...containing_oneof.name`) | `TestRegistration` `:2656-2667` |
| Estimate tests (each hook returns int >= 1 for an *empty* message; never raises) | `TestEstimates` `:2768` |
| AST invariant: assertion-free `..._violations(tree) -> list[str]`, `_plant(tree, function, statement)`, class that asserts clean tree `[]`, each planted violation reported with a fragment, each planted *allowed* call not reported | `_adapter_invariant_violations` `:3212`, `_plant` `:3391`, `TestAdapterInvariant` `:3421` |
| Pin test: exactly one non-comment line, regex on `name @ git+https://gitlab.formulatrix.com/nikkopg/<repo>.git@[0-9a-f]{40}`, then `importlib.metadata.distribution(...).read_text("direct_url.json")` `vcs_info.commit_id == pinned_sha` | `TestRequirementsPin` `:3508-3522` |

**Closed-port difference (important).** fast's test expects Configure against a closed port to **succeed** (fast's `open_service` is lazy). The STACK core probes eagerly, so against a closed loopback port Configure returns **`NOT_READY`** with `transport error calling /api/general/application: ConnectError`, status FAILED, and the owner lock is released afterwards (executed). That closed-port case is itself the "Configure fails cleanly, no off-host contact" test. A *successful* real-mode Configure in tests needs the patched-`open_service` seam (Code Examples).

## Architecture Patterns

### System Architecture Diagram
```
galago-core (controller)                                         STACK manager (never contacted)
   | gRPC Configure / ExecuteCommand / EstimateDuration / GetStatus        ^
   v                                                                       | HTTP via core only
ToolServer (base_server)  <---- StackServer(ToolServer)  ------------>  stack_automation_layer
  Configure -> _configure(cfg)      |                                       open_service(host,port,owner="galago")
     host/port/timeout checks       |  ExecuteCommand override                 lock -> creds -> probe -> StackService
     same endpoint? reuse           |    stack + inner in READ_COMMANDS?
     else close old, open_service   |      yes -> _dispatchCommand (no isReady/BUSY)  --+
     NOT_READY(str(e)) on failure   |      no  -> super().ExecuteCommand (BUSY gate)    |
                                    v                                                   v
                         _dispatchCommand: _check_args (both modes) -> INVALID_ARGUMENTS
                            simulated: Estimate<Cmd> sleep -> SUCCESS (no core)
                            real: handler named after message class
                                  reads/estimate -> service.<method> -> kind table -> _reply
                                  Transfer/Ack/Latch -> ERROR_FROM_TOOL "not available in this build"
```

### Recommended Project Structure
```
tools/stack/
├── __init__.py        # empty
├── server.py          # StackServer, _reply, kind table, _check_args, READ_COMMANDS, EST_* constants
└── requirements.txt   # one SHA-pinned line
tools/tests/stack_test.py
interfaces/tools/grpc_interfaces/stack.proto
```
Keep everything in `server.py` unless it grows past roughly 600 lines; a second module under `tools/stack/` is fine but the AST/import tests must glob `tools/stack/*.py`, not just `server.py`.

### Pattern 1: `_reply` and the kind table
**What:** one reply builder, one explicit kind -> code table, one message builder from structured fields.
```python
# Source: tools/fast/server.py:273-282 (shape), D-10..D-12; kinds verified in results.py
def _reply(code: ResponseCode, *, message: str = "", meta: Optional[dict] = None) -> ExecuteCommandReply:
    reply = ExecuteCommandReply(response=code, error_message=message, return_reply=True)
    if meta is not None:
        s = Struct(); s.update(meta); reply.meta_data.CopyFrom(s)
    return reply

_SUCCESS_KINDS = frozenset({
    "managerState", "deviceTree", "robotStates", "labwareProfiles", "transferProfiles",
    "labwarePresence", "estimated", "failureAcknowledged", "ran"})

def _result_reply(result: object) -> ExecuteCommandReply:
    to_dict = getattr(result, "to_dict", None)
    d = to_dict() if callable(to_dict) else None
    if not isinstance(d, dict):                       # unrecognised object: never SUCCESS
        return _reply(ERROR_FROM_TOOL, message="stack: unrecognised result")
    kind = d.get("kind")
    if kind in _SUCCESS_KINDS:
        return _reply(SUCCESS, meta=d)                # message MUST be empty
    return _reply(ERROR_FROM_TOOL, message=_error_line(d), meta=d)
```
`_error_line(d)`: `"stack: " + kind`, `+ f" ({reason})"` when `d.get("reason")` is a str, `+ f", guid {guid}"` when a guid is found by the extraction order above; collapse whitespace and cap length with `_one_line(text, 500)` (copy fast's helper, server.py:170-176). Never include `explanation`, `message`, `detail` or `error.detail` text (G5, and `detail` is server-controlled). D-11 lists only kind/reason/guid; for the Phase 4-reachable non-read kinds a bare `stack: needsInput` is unhelpful because galago-core drops `meta` on any non-SUCCESS reply (it throws from the message alone: tools.ts:598-646). Recommendation (planner to confirm, still "structured fields only"): append `missing: robot, source` for `needsInput.missing`, the first finding `name` for `rejected`, and `error.name`/`status` for `readFailed`.

### Pattern 2: `ExecuteCommand` override (D-13)
```python
# Source: tools/fast/server.py:515-544 (shape), base_server.py:223-256 (what it bypasses)
READ_COMMANDS = frozenset({"get_manager_state", "get_robot_states", "list_devices",
    "list_labware_profiles", "list_transfer_profiles", "get_labware_presence",
    "get_transfer_estimate", "get_failure_latch"})

def ExecuteCommand(self, request: ToolCommand, context: grpc.ServicerContext) -> ExecuteCommandReply:
    if request.WhichOneof("tool_command") == self.toolType:
        stack_command = request.stack
        field_name = stack_command.WhichOneof("command")
        if field_name in READ_COMMANDS:
            command = getattr(stack_command, field_name)
            try:
                return self._dispatchCommand(command)
            except Exception as e:
                logging.error(f"Error on Tool ={self.toolId}")
                self.last_error = str(e)
                return ExecuteCommandReply(response=DRIVER_ERROR, error_message=str(e))
    return super().ExecuteCommand(request, context)
```
`WhichOneof` returns `None` for an unset inner command and a non-`stack` outer returns another name -> both fall through to `super()` (WRONG_TOOL / UNRECOGNIZED_COMMAND unchanged).

### Pattern 3: `_configure` (D-07)
```python
# Source: tools/fast/server.py:546-562 (shape); open_service/OwnedService verified
def _configure(self, config: Config) -> None:
    host = config.host.strip()
    if not host:
        raise ValueError("stack: Config.host is required")
    port = config.port or DEFAULT_PORT                      # 5005
    t = config.transfer_timeout_s
    if not math.isfinite(t) or t < 0:
        raise ValueError(f"stack: Config.transfer_timeout_s must be finite and >= 0, got {t!r}")
    key = endpoint_key(host, port)                           # from stack_automation_layer.owner_lock
    if self._owned is not None and self._owned.endpoint == key:
        return
    if self._owned is not None:
        self._owned.close(); self._owned = None; self.service = None
    self._owned = open_service(host, port, owner="galago")   # no lock_dir, no transport
    self.service = self._owned.service
    logging.warning("stack: restarting this tool server clears the core's failure latch and in-flight guard (core gap G1); ...")
```
`endpoint_key` raises `ValueError` for a port outside 1..65535 or an empty host — it propagates as NOT_READY text via base `Configure` (acceptable). The same-endpoint early `return` is **not optional**: a second `open_service` for the same endpoint in the same process would contend with the first (`flock` on a second open file description conflicts even in-process) and fail naming `galago (pid <self>)`.

### Anti-Patterns to Avoid
- **Copying fast's `_decision`** (`.strip().lower()`; fast_test `:2851` region): STACK's `arm_inspected` must be *exactly* `"yes"` or `"no"` (ACK-01 says "exact string"); no strip, no case folding.
- **Forwarding `""`** for instrument fields (see blank `robot` trap).
- **Calling `HasField` alone** as the "was it provided" test (true for `""`).
- **Returning `SUCCESS` with a message** (galago-core throws on it).
- **Using `INVALID_ARGUMENTS`/`NOT_READY` for operator-visible text** (galago-core replaces it with a generic sentence).
- **Importing across tool packages**, adding a `transport=` or `lock_dir=` argument to the adapter's `open_service` call, or constructing `StackService`/`RestStackClient`/`Credentials` in `tools/stack/`.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Owner lock / endpoint key | own lock file or host normalisation | `open_service(..., owner="galago")` + `owner_lock.endpoint_key` / `OwnedService.endpoint` | Same key as stack-mcp is the whole point; any extra normalisation could let both front ends own the arm |
| Completeness of a transfer request | adapter-side required-field logic | pass `None`s; core `missing_fields` -> `NeedsInput` | CONTEXT D-03 / adapter holds no instrument rule |
| Credentials | read env in the adapter | the core's `Credentials.from_env()` (inside `open_service`) | Masking and `StackCredentialsMissing` come with it |
| Struct conversion | custom JSON walker | `Struct().update(d)` | Verified round-trip on every read kind |
| Concurrency gate for reads | new lock | fast-style `ExecuteCommand` override | `base_server` stays unedited; the core is thread-safe (`_lock`, `_submit_lock`, `_state_lock`, service.py:285-318) |
| Fake STACK for Configure tests | HTTP test server | patched `open_service` + two-method `MagicMock` transport | Fully offline, deterministic |

**Key insight:** the adapter is a thin 1:1 shim; every piece of logic that is not an argument check, a kind->code table, a message line or a constant belongs to the core.

## Runtime State Inventory
Not applicable: greenfield tool addition, no rename/refactor/migration. **Nothing found in any of the five categories** (no stored data, no live service config, no OS-registered state, no secrets beyond the process env `STACK_USER`/`STACK_PASSWORD` read by the core, no build artifacts carrying an old name). The only on-disk side effect of this phase is the owner-lock file the core creates in the lock dir during a real-mode Configure (`D-04`: `ledger_dir` creates nothing).

## Common Pitfalls

### Pitfall 1: A closed port now fails Configure
**What goes wrong:** copying fast's "Configure succeeds against a closed port" test makes the STACK test fail.
**Why:** `open_service` runs the anonymous identity probe eagerly (composition.py).
**How to avoid:** assert `NOT_READY` + `transport error` for the closed-loopback case; use patched `open_service` for success paths.
**Warning signs:** `ConnectError` in a test that expected READY.

### Pitfall 2: In-process lock self-contention and leaked locks
**What goes wrong:** a second `StackServer` (or a re-open) on the same endpoint raises `StackOwnedError` naming `galago (pid <own pid>)`; an un-closed `OwnedService` in one test keeps the `flock` for the life of the process.
**How to avoid:** unique `tempfile.TemporaryDirectory()` per test via `STACK_MCP_LOCK_DIR`, `addCleanup` closing `server._owned`, and the same-endpoint early return in `_configure`.

### Pitfall 3: Ambient credentials and lock dir
`STACK_USER`/`STACK_PASSWORD`/`STACK_MCP_LOCK_DIR` may exist on a developer machine. Every Configure-touching test must set them explicitly (`patch.dict(os.environ, {...})`) and one test must clear the credentials to assert the `StackCredentialsMissing` text.

### Pitfall 4: Simulated sleeps are real
`EST_TRANSFER_S = 35` would stall the suite. Patch `tools.base_server.time` as fast_test does (`:357`) and assert `fake_sleep` was called with the constant.

### Pitfall 5: The blocked-slow-command needs valid args
`_check_args` runs before the handler, so the blocked `Transfer` used for D-16 must carry a non-blank `step_key`, otherwise it returns `INVALID_ARGUMENTS` instantly and nothing blocks. Patch with `patch.object(server, "Transfer", side_effect=blocking)` (`_dispatchCommand` resolves `getattr(self, "Transfer")`, so an instance attribute wins). Also: `get_failure_latch` is in `READ_COMMANDS` but refused in real mode, so during the BUSY window it must return `ERROR_FROM_TOOL` ("not available"), **not** `NOT_READY`; assert that explicitly.

### Pitfall 6: Simulated -> real switch leaves the service `None`
`base_server.Configure` (:98-101) returns SUCCESS for a simulated->real switch **without** calling `_configure`. A bypass read then reaches a `None` service; D-14 turns that into `NOT_READY` "stack: not configured". Test it (`server.simulated = False`, `service = None`, status not READY).

### Pitfall 7: Which error text the operator actually sees
| Reply | galago-core shows | Source |
|-------|-------------------|--------|
| `Configure` not SUCCESS | the tool's `error_message`, as an error toast "Failed to connect to instrument" + message | `controller/server/tools.ts:331-350` (throws `ToolCommandExecutionError(reply.error_message ?? "Connect Command failed")`); `controller/components/tools/ToolConfigEditor.tsx:55-72` (`onError` -> `errorToast("Failed to connect to instrument", data.message)`) [VERIFIED: read]. That the tRPC layer passes `error.message` through unredacted is `[ASSUMED]` (default tRPC behaviour, not verified) |
| `ExecuteCommand` `ERROR_FROM_TOOL` | `Error from tool "<id>": <message>` | tools.ts:598-623 [VERIFIED: read] |
| `INVALID_ARGUMENTS`, `NOT_READY` | generic sentences; message **discarded** | tools.ts:598-612 |
| `SUCCESS` with `error_message` | **throws** (SUCCESS must have an empty message) | tools.ts:635-646 |
| any non-SUCCESS | `meta_data` is lost (throw happens before it is returned) | tools.ts:598-646 |
So D-08's lock-holder text reaches the operator on Configure (HIGH), D-14's "not configured" and adapter argument-error texts do not (log/`last_error` only), and meta for failures is never displayed — only the message line.

### Pitfall 8: `HasField` on `optional` is true for `""`
See Registration. Normalise with `value.strip()`.

### Pitfall 9: mypy scope includes tests
Untyped test helpers fail `bin/make test`. Annotate everything; type the mocked service as `Any` where needed.

### Pitfall 10: Hardware safety in tests
Nothing may reach `10.150.1.125` / `stack-server`. Defence in depth: add a setUp guard that wraps `socket.socket.connect`/`connect_ex` to raise for any non-loopback, non-`AF_UNIX` address (the core's own `tests/netguard.py` does this). Python-level sockets cover httpx; gRPC's C-core in-process loopback is unaffected `[ASSUMED: httpx path goes through Python sockets]`.

## Code Examples

### Test seam: successful real-mode Configure without any network
```python
# Source: composition.open_service contract (verified); fast_test.py:352 (patch shape)
def _fake_open_service(host: str, port: int, *, owner: str) -> Any:
    transport = MagicMock()
    transport.get_application.return_value = {"productName": "Stack manager"}
    transport.get_versions.return_value = {"2": "/api/v2", "3": "/api/v3"}
    return real_open_service(host, port, owner=owner, transport=transport)   # lock dir from env

with patch.dict(os.environ, {"STACK_USER": "u", "STACK_PASSWORD": "p", "STACK_MCP_LOCK_DIR": tmp}), \
     patch("tools.stack.server.open_service", side_effect=_fake_open_service):
    reply = stub.Configure(tool_base_pb2.Config(simulated=False, toolId="stack-test",
                           stack=stack_pb2.Config(host="127.0.0.1", port=5005)))
```
`real_open_service` is `stack_automation_layer.composition.open_service` imported in the test module. The lock is real (temp dir); only HTTP is replaced.

### Test: stack-mcp holds the lock -> Configure fails naming the holder, before any I/O (STK-02)
```python
# Source: owner_lock.acquire_owner_lock (verified executed in-process)
from stack_automation_layer.owner_lock import acquire_owner_lock
port = _free_tcp_port()
holder = acquire_owner_lock("127.0.0.1", port, owner="mcp", lock_dir=tmp)   # tmp == STACK_MCP_LOCK_DIR
self.addCleanup(holder.release)
with patch.dict(os.environ, {"STACK_USER": "u", "STACK_PASSWORD": "p", "STACK_MCP_LOCK_DIR": tmp}), \
     patch("stack_automation_layer.composition.RestStackClient") as rest:
    reply = server.Configure(tool_base_pb2.Config(simulated=False, toolId="t",
              stack=stack_pb2.Config(host="127.0.0.1", port=port)), None)
rest.assert_not_called()                                  # no client, so no network
self.assertEqual(reply.response, tool_base_pb2.NOT_READY)
self.assertIn("already owned by mcp", reply.error_message)  # verbatim: "...is already owned by mcp (pid N); only one front end ..."
self.assertEqual(server.status, tool_base_pb2.FAILED)
self.assertIsNone(server.service)
```
Observed message: `STACK manager 127.0.0.1:53693 is already owned by mcp (pid 764738); only one front end may hold it at a time (stop the other owner first)`.

### AST invariant skeleton (D-20, D-21) with planted violations
Mirror `_adapter_invariant_violations` / `_plant` (fast_test.py:3212, :3391). Rules to implement over `ast.parse` of **every** `tools/stack/*.py`:
1. Forbidden attribute calls: any `ast.Call` whose `func` is `ast.Attribute` with `attr in {"plan_transfer","execute_transfer","start_transfer","wait","wait_transfer","cancel_transfer","go_to_safe_position","wait_safe_position","acknowledge_failure","validate_transfer"}`. Caveat: `threading.Event.wait` and `str`/other `.wait` calls would false-positive — the real adapter has none in Phase 4, and a `.wait(` there is itself worth a review; if one is ever needed, narrow the rule to receivers named `service`/`self.service`/`svc` like fast's scoped rule.
2. No `.mcp`: `ast.Import` alias or `ast.ImportFrom` module equal to or starting with `stack_automation_layer.mcp`; **also** `ImportFrom(module="stack_automation_layer", names=[... "mcp" ...])` (the `from stack_automation_layer import mcp` form that fast's check does not cover); and string constants containing `stack_automation_layer.mcp`.
3. `open_service` is called at least once; its `Call` has `owner="galago"` and **no** `lock_dir` or `transport` keyword; no direct call to `StackService`, `RestStackClient`, `StackJwtAuth`, `Credentials`, `acquire_owner_lock`.
4. No string constant containing `10.150.1.125` or `stack-server` under `tools/stack/`.
5. Required functions exist (so renames cannot silently disable a rule).
Plant cases (must be reported): `service.execute_transfer("p")` in `Transfer`; `service.wait(None)` module-level helper; `from stack_automation_layer.mcp import server`; `from stack_automation_layer import mcp`; `open_service("h", 1, owner="galago", lock_dir="/x")`; `StackService(None)`. Plant allowed (must not be reported): `service.manager_state()` in a read handler.

### Proto-freeze test
Assert `[(f.name, f.number) for f in stack_pb2.Command.DESCRIPTOR.oneofs_by_name["command"].fields]` equals the D-01 list verbatim; `Config` field names/numbers; no `lock_dir`; every `string` field in every command message has presence (`f.has_presence`); no nested message name in `{"GetStatus","EstimateDuration","Configure","ExecuteCommand"}` and none starting with `"Estimate"` (D-05); `Command.Transfer` field numbers 1..12 match D-03.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| fast: lazy `open_service`, closed-port Configure succeeds | STACK: eager identity probe, closed-port Configure fails | core `composition.py` @ `ed8ce47` | Tests differ (Pitfall 1) |
| fast: `refused -> NOT_READY`, `rejected -> INVALID_ARGUMENTS` | STACK: every non-success kind -> `ERROR_FROM_TOOL` | milestone v2 decision (galago-core hides those texts) | Message is the only operator-visible channel |

**Deprecated/outdated:** SUMMARY.md's proto ordering (presence=6, estimate=7, acknowledge=8) is superseded by D-01 (adds `ListTransferProfiles = 6`, `GetFailureLatch = 10`).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | tRPC delivers the thrown `ToolCommandExecutionError.message` unredacted to `ToolConfigEditor`'s `onError` (so the lock-holder text is shown) | Pitfall 7 | D-08's holder text would only reach galago-core's log and the tool's `last_error`; Phase 7 runbook would need to tell operators to read the tool log |
| A2 | mypy accepts `HasField(<str variable>)` on generated messages without `cast(Any, ...)` | Registration | Minor: add `cast(Any, ...)` as fast does |
| A3 | Python-level socket guard also covers httpx traffic | Pitfall 10 | Guard is only defence in depth; tests already use mocks/closed loopback ports |
| A4 | ts-proto delivers an untouched `optional` string as unset (not `""`) | D-03 (CONTEXT) | Blank-as-`None` normalisation already makes both cases safe |

## Open Questions

1. **Order of D-14 vs D-18 for `GetFailureLatch` (and `Transfer`/`AcknowledgeFailure`) in real mode with no service.**
   - What we know: D-14 says a bypass read without a service returns `NOT_READY`; D-18 says the three Phase-5 commands are refused with `ERROR_FROM_TOOL`.
   - What's unclear: which wins when both apply (real mode, unconfigured, `GetFailureLatch`).
   - Recommendation: refuse the three Phase-5 commands **first** (they need no service, and the refusal text is operator-visible, unlike `NOT_READY`); apply the `service is None` check only for the real handlers (reads and estimate).
2. **Extra structured hints in the `ERROR_FROM_TOOL` line** (`needsInput.missing`, first `rejected` finding name, `readFailed.error.name`): D-11 names only kind/reason/guid. Recommendation: include the bounded extras (all structured, no `explanation`/`detail`), since meta never reaches the operator on failure. Planner confirms.
3. **Blank `robot` for `GetLabwarePresence`:** normalise to `None` (core returns `readFailed` with zero I/O) vs adapter `INVALID_ARGUMENTS`. D-17 says the adapter checks only its own arguments, so recommend `None` pass-through; note the resulting `readFailed` name is `TypeError` (ugly but safe, no request sent).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10 venv `~/data/nikko/.venvs/galago-py310` | whole gate | yes | 3.10.12 | - |
| `stack-automation-layer` in that venv | server import, tests | **no** (`pip show` -> not found) | - | `git+file://` install at `ed8ce47` (dry-run OK); tests skip cleanly without it |
| GitLab HTTPS for the pinned URL | `requirements.txt` canonical install | no (auth failure from this shell) | - | local clone via `git+file://` (fast-mcp precedent) |
| `httpx`, `grpcio-tools`, `protobuf`, `pytest`, `ruff`, `mypy` | gate | yes | 0.28.1, 1.70.0, 5.29.6, 7.4.3, 0.9.4, 1.11.2 | - |
| Local core checkout containing `ed8ce47` | fallback install | yes (`origin/feat/initial-layer`; working tree on unrelated `main`) | - | - |
| STACK manager / PAC simulator / Docker | **not needed in Phase 4** | n/a | - | all tests use mocks, closed loopback ports, temp lock dirs |
| galago-core checkout (read-only) | Configure-text question | yes (`~/data/nikko/galago-core`) | `57d55e9` | - |

**Missing dependencies with no fallback:** none.
**Missing with fallback:** the core install (use the `git+file://` step above as the first task, flagged as a human-action checkpoint).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `unittest` (stdlib) run by both `unittest discover` and pytest 7.4.3 |
| Config file | `pyproject.toml` (`[tool.ruff]`, `[tool.mypy]`); no pytest config; `bin/make` `test()` |
| Quick run command | `source ~/data/nikko/.venvs/galago-py310/bin/activate && python -m pytest tools/tests/stack_test.py -x -q -p no:cacheprovider` |
| Full suite command | `source ~/data/nikko/.venvs/galago-py310/bin/activate && bin/make proto test` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STK-01 | `ToolType.Value("stack") == 24`; Command `stack` in oneof `tool_command`; Config `stack` in oneof `config`; frozen field list (D-01/D-03/D-04, no `lock_dir`, D-05 names, `has_presence`) | unit | `python -m pytest tools/tests/stack_test.py -k "Registration or ProtoFreeze" -q` | ❌ Wave 0 |
| STK-01 | server starts as `stack` type: `StackServer.toolType == "stack"`; `python -m tools.stack.server --port=N` listens | unit + smoke | `-k Registration`; smoke: `timeout 5 python -m tools.stack.server --port=$(python -c "import socket;s=socket.socket();s.bind(('127.0.0.1',0));print(s.getsockname()[1])")` (expect log "stack server started, listening on") | ❌ Wave 0 |
| STK-01 | whole gate green | gate | `bin/make proto test` | gate exists |
| STK-02 | Configure real mode (patched `open_service`) takes `galago` lock: lock file holder record has `"owner": "galago"` and own pid; re-Configure same endpoint reuses (no second `open_service` call); host change closes old lock first | integration (in-process gRPC) | `-k "Configure or Reconfigure"` | ❌ Wave 0 |
| STK-02 | `owner="mcp"` holder in temp `STACK_MCP_LOCK_DIR` -> `NOT_READY`, message contains `already owned by mcp`, `RestStackClient` never constructed, status FAILED | integration | `-k StackOwned` | ❌ Wave 0 |
| STK-02 | closed loopback port -> `NOT_READY` `transport error`; missing creds -> `STACK credentials missing`; blank host / bad `transfer_timeout_s` -> NOT_READY; `ledger_dir` creates nothing | integration | `-k "ConfigureFails"` | ❌ Wave 0 |
| STK-02 | no `.mcp` import (D-21); `open_service` only, `owner="galago"`, no `lock_dir`/`transport` kw (AST) | AST | `-k AdapterInvariant` | ❌ Wave 0 |
| STK-02 | SHA pin: one non-comment line, regex, no `[mcp]` extra, installed `direct_url.json` `commit_id` equals pinned SHA | unit | `-k RequirementsPin` | ❌ Wave 0 (needs core installed via `git+file`) |
| STK-03 | each of six reads calls exactly one mapped service method (`manager_state`, `robot_states`, `devices(refresh=)`, `labware_profiles(refresh=)`, `transfer_profiles(refresh=)`, `labware_presence(robot)`), SUCCESS, empty message, meta == `to_dict()` (kind strings above); `refresh` unset -> `False`; blank robot -> `None` | unit (`MagicMock(spec=StackService)`) | `-k ReadCommands` | ❌ Wave 0 |
| STK-03 | 1:1 surface: handler names == oneof message names; every mapped method exists on `StackService` | unit | `-k OneToOne` | ❌ Wave 0 |
| STK-04 | `GetTransferEstimate` builds `TransferRequest(Location...)` with blank->`None`, calls `estimate_transfer` once, `estimated` -> SUCCESS; `needsInput`/`rejected`/`readFailed` -> `ERROR_FROM_TOOL`; `Estimate<Cmd>` hooks return the D-19 ints, `>= 1`, never raise on empty messages | unit | `-k "Estimate"` | ❌ Wave 0 |
| STK-05 | **red first**: with an injected blocked non-read (patched `Transfer`, valid `step_key`) the 8 reads return results (not NOT_READY), health status stays BUSY, second non-read -> NOT_READY, after release READY; `get_failure_latch` returns `ERROR_FROM_TOOL` not-available while BUSY | integration (in-process gRPC) | `-k BusyReads` | ❌ Wave 0 |
| STK-05 | real mode, `service is None`, bypass read -> `NOT_READY` "stack: not configured" (also the simulated->real switch case) | unit | `-k NotConfigured` | ❌ Wave 0 |
| STK-06 | simulated: no `open_service` call, no core, no lock file; `Estimate<Cmd>` slept via patched `tools.base_server.time`; `step_key` missing/blank/whitespace, `timeout_s` nan/inf/negative, `guid` blank, `arm_inspected` not exactly `yes`/`no` (incl. `"Yes"`, `" yes"`) -> `INVALID_ARGUMENTS`; valid -> SUCCESS; same checks first in real mode | unit + integration | `-k "Simulated or CheckArgs"` | ❌ Wave 0 |
| STK-06 | real mode: after args pass, `Transfer`/`AcknowledgeFailure`/`GetFailureLatch` -> `ERROR_FROM_TOOL`, one line, "not available", service never touched | unit | `-k RealModeRefusals` | ❌ Wave 0 |
| STK-07 | mapping table over real result classes: every `_SUCCESS_KINDS` -> SUCCESS with `error_message == ""`; every other kind (`readFailed`, `refused` w/ reason+`detail.guid`, `rejected`, `needsInput`, `lost` w/ `handle.guid` and with `handle=None`, `failed`, `aborted`, `cancelled`, `timedOut`, unknown kind, non-result object) -> `ERROR_FROM_TOOL`; message single line (no `\n`), contains kind, reason and guid when present, excludes `explanation`; never SUCCESS | unit | `-k ResultMapping` | ❌ Wave 0 |
| (safety, SC 5) | AST: no forbidden core call in `tools/stack/*.py`; planted violations caught, planted allowed call not | AST | `-k AdapterInvariant` | ❌ Wave 0 |
| (log, D-09) | successful real Configure logs one WARNING mentioning restart/latch | unit | `-k ConfigureWarning` (`assertLogs(level="WARNING")`) | ❌ Wave 0 |

All commands run in the 3.10 venv from the repo root with no network access beyond loopback and no motion (the core is mocked or probed against a closed loopback port; the net-guard in `setUp` enforces it).

### Sampling Rate
- **Per task commit:** the quick run command (whole `stack_test.py` runs in ~1-3 s with sleeps patched).
- **Per wave merge:** `bin/make proto test` (ruff + mypy + unittest + pytest; baseline 147 + new).
- **Phase gate:** full gate green before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `stack-automation-layer` installed at `ed8ce47` in the 3.10 venv (`git+file://` step; human-action checkpoint)
- [ ] `interfaces/tools/grpc_interfaces/stack.proto` + the three registration edits, then `bin/make proto` (generated `stack_pb2*` is gitignored)
- [ ] `tools/stack/__init__.py`, `tools/stack/requirements.txt`, `pyproject.toml` mypy override
- [ ] `tools/tests/stack_test.py` (skip guard first; helpers `_free_tcp_port`, in-process gRPC fixture, blocked-command helper, net-guard)
- [ ] Failing STK-05 test committed **before** the `ExecuteCommand` override (v1 D-04 / CONTEXT D-16)

## Security Domain

### Applicable ASVS Categories (level 1, `security_enforcement` enabled)

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes (service credentials) | credentials only from `STACK_USER`/`STACK_PASSWORD` via the core (`Credentials` masks password in `repr`/`str`); no credential fields in `Config`; never log env or tokens (base `Configure` logs only the request, which carries host/port) |
| V3 Session Management | no (core manages JWT lazily) | - |
| V4 Access Control | yes | single-owner `flock` via `open_service(owner="galago")`; no `lock_dir` field; `AcknowledgeFailure` is refused in real mode this phase (operator-only enforcement is a galago-core/Phase 5 concern, DEP-03) |
| V5 Input Validation | yes | adapter checks its own args (D-17/D-18) exactly; instrument fields validated by the core; host passed through `endpoint_key` validation; `transfer_timeout_s` finite/non-negative |
| V6 Cryptography | no | none implemented; do not hand-roll |
| V7 Error handling / logging | yes | one-line messages, no tracebacks, no `explanation`/`detail` echo (core errors already omit bodies and credentials: errors.py secrecy rule) |
| V14 Config / supply chain | yes | SHA-pinned first-party dependency; installed-SHA test; no `[mcp]` extra; PyPI-name squat risk avoided because the requirement is a direct git reference |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Two front ends drive the arm at once | Tampering / DoS | core owner lock, identical host string, same lock dir (no `lock_dir`), Configure fails naming the holder |
| Adapter motion path reachable by a remote command | Elevation of privilege | no real-mode handler calls a motion method; AST invariant (D-20); `Transfer`/`AcknowledgeFailure` refused until Phase 5 |
| Operator-configured host is an arbitrary endpoint (SSRF-like) | Spoofing | core identity probe requires `productName == "Stack manager"` before any tool is served; tests never use real hosts |
| Credential leakage via logs/errors | Information disclosure | core masks credentials; adapter never formats env or `Credentials`; messages built from structured fields only |
| Unrecognised/failed core result presented as success | Tampering | explicit SUCCESS allowlist; unknown kind -> `ERROR_FROM_TOOL` |
| Dependency confusion on `stack-automation-layer` | Tampering | direct `git+URL@sha` reference; SHA asserted by test |
| Ambient env makes a test hit hardware | Information disclosure / safety | tests set env explicitly; loopback-only socket guard; AST rule bans the hardware host literals in `tools/stack/` |

## Project Constraints (from CLAUDE.md)
No `./CLAUDE.md` exists in the repo, and there are no `.claude/skills/`. Constraints in force come from CONTEXT.md and the user's memory file: push only to the `nikkopg` fork remote; never contact `10.150.1.125` / `stack-server`; do not modify `stack-automation-layer` or `galago-core`; do not edit `tools/base_server.py` (D-13).

## Sources

### Primary (HIGH confidence)
- `git show ed8ce47:stack_automation_layer/{results,service,model,composition,owner_lock,errors,transport}.py`, `mcp/server.py:55-110`, `pyproject.toml` — read in full for the cited ranges and executed via an extracted copy on the 3.10 venv interpreter (no install); core `tests/fakes.py`, `tests/conftest.py`, `tests/test_composition.py`, `tests/test_owner_lock.py` for seams
- `tools/base_server.py` (all 317 lines), `tools/fast/server.py` (:1-300, :440-700, :770-800, :940-1015), `tools/tests/fast_test.py` (anchors in the table), `interfaces/**.proto`, `bin/make`, `pyproject.toml`, `setup.py:95-125`, `requirements-dev.txt`
- `~/data/nikko/galago-core`: `controller/server/tools.ts:325-360, 596-660`, `controller/components/tools/ToolConfigEditor.tsx:50-130`, `controller/server/routers/tool.ts:455-495` (read-only)
- Executed: `pip show`, `pip install --dry-run --no-deps` (git+file), `pytest --collect-only`, `unittest discover`, `ruff check .`, `mypy`, scratch-copy protoc compile + descriptor introspection, `gsd package-legitimacy check`

### Secondary (MEDIUM confidence)
- `.planning/research/SUMMARY.md` (milestone research; its proto ordering is superseded by D-01)

### Tertiary (LOW confidence)
- none beyond the items in the Assumptions Log

## Metadata

**Confidence breakdown:**
- Standard stack / install: HIGH — dry-run executed; precedent file read
- Core contract: HIGH — executed against the real classes and fixtures
- Architecture / test patterns: HIGH — fast code and tests read; proto compiled
- galago-core Configure text: HIGH for the code path, MEDIUM for tRPC passthrough (A1)
- Pitfalls: HIGH (most were reproduced)

**Research date:** 2026-10-28
**Valid until:** 2026-11-27 (stable; re-check only if the core SHA, `base_server.py` or the galago-core Configure path changes)
