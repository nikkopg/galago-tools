# Stack Research

**Domain:** Live control additions to an existing gRPC (Python tool server) + Next.js/tRPC (galago-core) workcell system
**Researched:** 2026-10-12
**Confidence:** HIGH (every recommendation below is verified against code and installed packages actually present in the two repos, not from general knowledge)

## Headline finding

**No new library is needed anywhere in this milestone.** Every one of the four asks (a)-(d) is already
one additive use of a dependency that is already pinned, already installed, and in most cases already
used for the *exact same pattern* elsewhere in these repos. The work is wiring, not stack selection.

## Recommended Stack

### Core Technologies (already in place — confirmed by reading the installed trees)

| Technology | Version (confirmed installed) | Purpose | Why Recommended |
|------------|-------------------------------|---------|-----------------|
| `grpcio` / `grpcio-tools` / `grpcio-reflection` | **1.70.0** (galago-tools `requirements.txt`; confirmed identical in `.venvs/galago-py310` via `pip show`) | Python gRPC server + codegen for `tool_base.proto` | Already the pinned version across the fork; `grpc.server(futures.ThreadPoolExecutor(max_workers=10))` is already how `tools/base_server.py::serve()` is built — (b) is a documentation fact, not a code change |
| `protobuf` | **5.29.6** (confirmed via `pip show` in the same venv) | Carries `google.protobuf.Struct`/`struct_pb2` for the new `run_state` field | `tool_base.proto` **already imports** `google/protobuf/struct.proto` (used today for `ExecuteCommandReply.meta_data`); adding `optional google.protobuf.Struct run_state = 4` to `StatusReply` needs zero new imports |
| `ts-proto` | **1.151.1**, pinned via `npm install -g ts-proto@1.151.1` in galago-core's `bin/make deps`/`proto_ts` | TypeScript codegen for the `.proto` files, including the `run_state` Struct | **Do not regenerate with the local `node_modules/ts-proto` (1.153.2)** — per the milestone context this version is confirmed broken for `tool_base.ts`. `bin/make proto_ts` resolves `protoc-gen-ts_proto` off `$PATH` (global npm bin), so as long as the global 1.151.1 install exists and precedes `node_modules/.bin` on `PATH`, codegen is already correct; this is an existing, unrelated-to-this-milestone constraint to respect, not something to fix here |
| `@grpc/grpc-js` | **1.12.2** (confirmed in `controller/node_modules/@grpc/grpc-js/package.json`; `package.json` declares `^1.8.4`) | galago-core's gRPC client to each tool server | One persistent `ToolDriverClient` per `Tool` instance (`server/tools.ts`), HTTP/2-multiplexed — see (c) below |
| `@tanstack/react-query` v4 (via `@trpc/react-query`) | **4.22.0** / `@trpc/*` **10.9.0** | Client-side polling | `trpc.<router>.<query>.useQuery(undefined, { refetchInterval: N })` is **already the house pattern** — `RunsComponent.tsx` already polls `commandQueue.getAll` at `refetchInterval: 2000` and others at 1000/1500ms. 2 s run-state polling (D2) is the same idiom at the same cadence, not a new mechanism |
| `@chakra-ui/react` | **2.8.2** | New `ToolPausedModal`, control bar, confirmation dialogs | Matches every existing run-page modal (`PauseModal.tsx`, `StopRunModal.tsx`, `UserFormModal.tsx`); `RadioGroup`/`Radio` is already the component used for the existing `yesno` command-field type (`components/forms/formFieldComponent.tsx`) — reuse it for the non-defaulted Resume/Abort/Stop choices, don't introduce a different form library |

### Supporting Libraries — none to add

No new npm or pip package is required for (a), (b), (c), or (d). The "supporting libraries" table from the
template is intentionally empty; see "What NOT to Use" for the specific things that might look tempting but
aren't needed.

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `python -m grpc_tools.protoc` (galago-tools `bin/make proto`) | Regenerate `tool_base_pb2.py`/`.pyi` after the proto edit | Already invoked with `grpcio-tools==1.70.0`; Struct support is built in, no plugin flags change |
| `python -m grpc_tools.protoc --ts_proto_out=...` (galago-core `bin/make proto_ts`) | Regenerate `gen-interfaces/tools/grpc_interfaces/tool_base.ts` | Confirmed today's generated `tool_base.ts` already imports `Struct` from `../../google/protobuf/struct` and types `meta_data` as `{ [key: string]: any }` — the new `run_state` field will generate identically, same optional-field pattern (`run_state?: { [key: string]: any }`) |
| `tsc --noEmit` (`npm run test` in `controller/package.json`) | Type-check after regen | Unchanged; just the existing gate |

## Installation

No installs are needed. For completeness, this is how to reproduce the already-pinned toolchain if a fresh
environment is ever built:

```bash
# galago-tools Python side (already satisfied in .venvs/galago-py310)
pip install grpcio==1.70.0 grpcio-tools==1.70.0 grpcio-reflection==1.70.0

# galago-core codegen + runtime (already satisfied in controller/node_modules)
npm install -g grpc-tools@1.12.4 ts-proto@1.151.1   # codegen plugin, NOT the local node_modules copy
cd controller && npm install                          # @grpc/grpc-js 1.12.2, @tanstack/react-query 4.22.0, @trpc/* 10.9.0, @chakra-ui/react 2.8.2 all come from package.json as-is
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|--------------------------|
| Extend `StatusReply` with `optional google.protobuf.Struct run_state = 4` (design D1, option A) | A `GetRunState` intent read through `ExecuteCommand`, F.A.S.T.-specific, no shared-proto change (design's option B) | Never for this milestone — D1 is already decided in the governing design (§11). Option B would also fight the existing heartbeat/`GetStatus` polling path that `Tool.fetchStatus()` already owns |
| One persistent `@grpc/grpc-js` client per tool, reused for both the queue's `ExecuteCommand` and the new out-of-band `toolControl` call | A second gRPC channel/client dedicated to control commands, or a connection-pooling library (e.g. `generic-pool`) | Never here — gRPC over HTTP/2 already multiplexes independent concurrent calls over one connection; `@grpc/grpc-js` handles this natively. A second client would only be useful if you needed independent channel-level settings (e.g. different deadlines) per call class, which this design doesn't ask for |
| `@tanstack/react-query`'s `refetchInterval` via the existing `trpc.*.useQuery(...)` idiom | A dedicated polling library (e.g. `swr`, a custom `setInterval` hook), or a push channel (WebSocket/SSE/tRPC subscription) | A push channel would be the "more correct" long-term answer for the heartbeat problem (§6.3's "failed poll must retry"), but `@trpc/server` here is pinned to v10.9.0 with no subscriptions transport (no `wsLink`) wired up in this app; introducing one is a much bigger change than this milestone's scope (D2 already settles on polling) |
| `Struct().update(python_dict)` (already used for `meta_data`) to build `run_state` | `google.protobuf.json_format.ParseDict(d, Struct())` | Equivalent result; the codebase's existing convention in `tools/fast/server.py` (`_estimateReply`/meta helper) already uses `Struct().update(meta)`, so match that, don't introduce `json_format` as a second idiom for the same thing |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|--------------|
| Upgrading `ts-proto` to the `node_modules`-resolved **1.153.2** for this change | Per the milestone's own context, that version generates a broken `tool_base.ts`; regenerating `run_state` codegen with it would silently produce the same breakage class in a file this milestone directly edits | Keep using the globally pinned **ts-proto 1.151.1** that `bin/make proto_ts` already resolves off `PATH` |
| A new gRPC deadline/timeout on `ExecuteCommand` calls to make `toolControl` "safer" during a long-running step | The design explicitly relies on `Tool.executeCommand` having **no gRPC deadline** so a step can stay open through an arbitrarily long pause (§6.2); imposing one on the control path would be an undocumented behavior change not asked for | Leave both call paths deadline-free, exactly as today |
| A second `ToolDriverClient`/channel per tool so control commands "don't contend with" the running step's call | Unnecessary: gRPC-js already runs concurrent unary calls over one HTTP/2 connection without head-of-line blocking between distinct RPCs; `tools/base_server.py`'s 10-worker `ThreadPoolExecutor` already serves them on independent threads server-side | Reuse the existing `Tool.grpc` client instance from `getToolFromStore`/the global tool map |
| Any new state-machine or lock library in the adapter to gate Pause/Resume/Abort by run phase | The gating already lives in `fast_mcp`'s `FastService` (per `PROJECT.md`'s Validated section — state gates return `Refused` with no instrument call when the state is wrong); duplicating it in `tools/fast/server.py` would violate the single-source-of-truth invariant (§5.4 of the design, §7.2 "the core owns the state gates") | Call `FastService.pause/resume/abort` directly and map `Refused` the same way existing Abort/Resume commands already do |
| A WebSocket/SSE push channel, or a tRPC v10 subscription link, to replace 2 s polling | D2 already settles on polling; `@trpc/server` 10.9.0 here has no `wsLink`/subscriptions transport configured anywhere in `controller/`, so adding one is a cross-cutting infra change, not a one-field addition | `refetchInterval: 2000` on a plain `useQuery`, identical to the existing `commandQueue.getAll` poll |
| A different modal/dialog primitive (e.g. Radix, Headless UI, a bespoke `<dialog>`) for `ToolPausedModal` | Every other run-page prompt (`PauseModal`, `StopRunModal`, `MessageModal`, `TimerModal`, `UserFormModal`) is Chakra `Modal`/`ModalOverlay`/`ModalContent`; a second UI kit would break visual and keyboard-handling consistency for no benefit | `@chakra-ui/react` `Modal` + `RadioGroup`/`Radio` (already used for `yesno` fields) |
| `google-protobuf` (the pure-JS/closure-compiler Protobuf runtime, `^3.21.2` in `package.json`) or `@bufbuild/protobuf` (`^2.2.0`) for handling `run_state` client-side | Both are present in `package.json` but neither is what actually decodes `Struct` today — `ts-proto`-generated code (`gen-interfaces/google/protobuf/struct.ts`) already has its own `Struct.wrap`/`Struct.unwrap` used for `meta_data`, giving a plain `{ [key: string]: any }` on the TS side with no extra runtime call | Let ts-proto's generated `Struct` wrapper handle it, exactly as `meta_data` already does — no manual (de)serialization code needed in `tools.ts` or any router |

## Stack Patterns by Variant

**If a later tool type beyond F.A.S.T. needs `runControl` (design D6, generic capability):**
- Reuse the same `run_state` Struct shape idea (`{state, percent, pause}` or whatever that tool needs) and the same `commandQueue.toolControl` tRPC procedure — no per-tool-type plumbing beyond the `runControl` capability declaration next to `commandFields`.
- Because the Struct field is intentionally untyped protobuf (`google.protobuf.Struct`), each tool can shape its own `run_state` payload without a shared-proto schema change per tool — this is precisely why D1 chose Struct over a strongly-typed message.

**If hard pause (`hardPause`) is ever added (deferred per D5):**
- Add one more non-defaulted `"yes"/"no"` field to the existing `Pause` command/`runControl` entry (`{ pause: { hard: "yesno" } }`), the same `yesno` field type already used for `return_liquid`/`is_tip_broken`.
- No new library — it's the same Chakra `RadioGroup` pattern and the same proto `oneof`/string convention.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|------------------|-------|
| `grpcio-tools==1.70.0` (Python codegen) | `protobuf==5.29.6` | Confirmed co-installed in `.venvs/galago-py310`; `grpcio-tools` 1.70.0's bundled protoc generates code against this protobuf runtime without a pin mismatch — already proven by the existing `meta_data` Struct field working today |
| `ts-proto@1.151.1` (global) | Node v24.14.1 (`~/.nvm/versions/node/v24.14.1/bin`) | This is the pinned combination per the milestone context; **do not** let `npm install` in `controller/` upgrade the global binary — `bin/make deps` reinstalls `ts-proto@1.151.1` globally every time, so always run codegen through `bin/make proto_ts`, never `npx ts-proto` bare (which would resolve to the local 1.153.2) |
| `@trpc/server` 10.9.0 / `@trpc/react-query` 10.9.0 / `@tanstack/react-query` 4.22.0 | Next.js 13.1.2, React 18.2.0 | All already mutually pinned in `package.json`; the `useQuery(..., { refetchInterval })` API used for 2 s polling is stable across this entire v10/v4 combination, no migration risk |
| `@grpc/grpc-js` 1.12.2 | `grpcio` 1.70.0 (Python server) | Different gRPC implementations (grpc-js is a pure-JS/HTTP2 client, grpcio is C-core) talking plain unary gRPC over insecure HTTP/2 — already proven working for every existing `ExecuteCommand`/`GetStatus` call; adding one more unary RPC path (`toolControl`) changes nothing about this compatibility |

## Sources

- Direct inspection (HIGH confidence, primary source — not web research):
  - `/home/formulatrix/data/nikko/galago-tools/requirements.txt`, `pyproject.toml`, `tools/base_server.py`, `tools/fast/server.py`, `interfaces/tools/grpc_interfaces/tool_base.proto`, `bin/make`
  - `/home/formulatrix/data/nikko/.venvs/galago-py310` — `pip show grpcio grpcio-tools grpcio-reflection protobuf fast-mcp`
  - `/home/formulatrix/data/nikko/galago-core/controller/package.json`, `controller/node_modules/{ts-proto,@grpc/grpc-js,@tanstack/react-query,@trpc/server,next}/package.json`, `bin/make`
  - `/home/formulatrix/data/nikko/galago-core/controller/server/tools.ts`, `server/command_queue.ts`, `server/utils/promisifyGrpcCall.ts`
  - `/home/formulatrix/data/nikko/galago-core/controller/components/runs/RunsComponent.tsx` (existing `refetchInterval` idiom), `components/runs/PauseModal.tsx` (existing Chakra modal idiom), `components/forms/formFieldComponent.tsx` (existing `yesno`/`RadioGroup` idiom)
  - `/home/formulatrix/data/nikko/galago-core/controller/gen-interfaces/tools/grpc_interfaces/tool_base.ts` (current generated Struct handling for `meta_data`, proving the pattern for the new `run_state` field)
  - `/home/formulatrix/data/nikko/fast/fast-mcp/fast_mcp/orchestration.py` (`PauseInfo.to_dict()`, confirmed present)
  - `/home/formulatrix/data/nikko/fast/fast-mcp/.planning/PROJECT.md` and `docs/specs/2026-10-12-galago-live-run-control-design.md` (governing design, decisions D1-D6)

---
*Stack research for: Galago live F.A.S.T. run control (v2 milestone)*
*Researched: 2026-10-12*
