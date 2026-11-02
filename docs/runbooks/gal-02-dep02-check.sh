#!/usr/bin/env bash
# GAL-02 DEP-02 gate (Phase 6, D-01).
#
# Purpose: decide whether galago-core Phase 5 (DEP-02, "STACK Codegen & Command Forms") has landed,
# so that Part 2 of docs/runbooks/gal-02-handoff.md may start. Part 2 never works around DEP-02.
#
# READ-ONLY: this script writes no file, makes no network call and changes no git state. The only
# git command it runs is `git rev-parse --short HEAD`, to print the galago-core revision.
#
# Checks (every check runs; there is no `set -e`):
#   1. a galago-core checkout exists (controller/ directory)
#   2. ToolType.stack in controller/gen-interfaces/controller.ts
#   3. generated controller/gen-interfaces/tools/grpc_interfaces/stack.ts
#   4. commandFields.stack has the `transfer` key itself (controller/components/tools/constants.ts);
#      list_transfer_profiles / get_transfer_estimate do not count
#   5. commandFields.stack does NOT expose acknowledge_failure (forbidden in any protocol)
#   6. vendored stack.proto is byte-equal to this repo's frozen interfaces/.../stack.proto
#
# Exit codes: 0 = "DEP-02 OK" (last line); 1 = "BLOCKED: ..." (last line).
#
# Environment overrides:
#   GALAGO_TOOLS_DIR  the galago-tools root   (default: two levels above this script)
#   GALAGO_CORE_DIR   the galago-core checkout (default: $GALAGO_TOOLS_DIR/../galago-core)

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GT="${GALAGO_TOOLS_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
GC="${GALAGO_CORE_DIR:-$GT/../galago-core}"

failed=0

head_sha="unknown"
if [ -d "$GC" ]; then
  head_sha="$(git -C "$GC" rev-parse --short HEAD 2>/dev/null)" || head_sha="unknown"
  [ -n "$head_sha" ] || head_sha="unknown"
fi
echo "galago-core: $GC"
echo "galago-core HEAD: $head_sha"

CONTROLLER_TS="$GC/controller/gen-interfaces/controller.ts"
STACK_TS="$GC/controller/gen-interfaces/tools/grpc_interfaces/stack.ts"
CONSTANTS_TS="$GC/controller/components/tools/constants.ts"
VENDORED_PROTO="$GC/vendor/galago-tools/interfaces/tools/grpc_interfaces/stack.proto"
FROZEN_PROTO="$GT/interfaces/tools/grpc_interfaces/stack.proto"

# 1. checkout
if [ ! -d "$GC/controller" ]; then
  echo "missing: galago-core checkout at $GC"
  failed=1
fi

# 2. ToolType.stack
if ! grep -qE '^[[:space:]]+stack = "stack",' "$CONTROLLER_TS" 2>/dev/null; then
  echo "missing: ToolType.stack in controller/gen-interfaces/controller.ts"
  failed=1
fi

# 3. generated message file
if [ ! -f "$STACK_TS" ]; then
  echo "missing: generated controller/gen-interfaces/tools/grpc_interfaces/stack.ts"
  failed=1
fi

# 4 and 5. the stack block of commandFields (two-space-indented tool block closed by `  },`).
# The block ends at the FIRST closing line, so a one-line `  stack: { ... },` can never spill into
# the next tool's block. A one-line block is rewritten to its first key at four-space indent, so
# the same anchored key match below applies (a one-line block whose first key is not `transfer`
# fails closed).
stack_open=0
stack_block=""
if [ -f "$CONSTANTS_TS" ]; then
  if grep -qE '^  stack: \{' "$CONSTANTS_TS" 2>/dev/null; then
    stack_open=1
  fi
  stack_block="$(awk '
    /^  stack: \{/ {
      if ($0 ~ /\}[[:space:]]*,?[[:space:]]*$/) {
        line = $0
        sub(/^  stack: \{[[:space:]]*/, "    ", line)
        print line
        exit
      }
      f = 1
      next
    }
    f && /^  \}[,;]?[[:space:]]*$/ { exit }
    f
  ' "$CONSTANTS_TS" 2>/dev/null)"
fi
if [ "$stack_open" -eq 0 ]; then
  echo "missing: commandFields.stack block in controller/components/tools/constants.ts"
  failed=1
elif ! printf '%s\n' "$stack_block" | grep -qE '^    transfer[[:space:]]*:'; then
  # The key itself, at the block's own indent: list_transfer_profiles / get_transfer_estimate and
  # nested field names must not satisfy it.
  echo "missing: commandFields.stack.transfer in controller/components/tools/constants.ts"
  failed=1
fi
if printf '%s\n' "$stack_block" | grep -q 'acknowledge'; then
  echo "forbidden: commandFields.stack exposes acknowledge_failure"
  failed=1
fi

# 6. vendored proto equals the frozen proto
if [ ! -f "$FROZEN_PROTO" ] || [ ! -f "$VENDORED_PROTO" ] || ! cmp -s "$FROZEN_PROTO" "$VENDORED_PROTO"; then
  echo "missing: vendored stack.proto equal to the frozen galago-tools stack.proto"
  failed=1
fi

if [ "$failed" -eq 0 ]; then
  echo "DEP-02 OK"
  exit 0
fi
echo "BLOCKED: galago-core Phase 5 (DEP-02, STACK Codegen & Command Forms) has not landed; see $GC/.planning/ROADMAP.md Phase 5"
exit 1
