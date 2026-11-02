#!/usr/bin/env bash
# GAL-07 live pre-flight gate (Phase 7, D-05/D-08).
#
# Purpose: decide whether the supervised live session may start, so that any part of
# docs/runbooks/gal-07-live-handoff.md (Part 1 deploy LIVE-08, Part 2 rehearsal Transfer LIVE-09,
# Part 3 GAL-02 handoff LIVE-10) runs only with every precondition in place. It is never worked
# around: a failing check sets failed=1, the session stops, and the operator fixes the named
# piece through the runbook's own steps instead of hand-editing around the gate.
#
# READ-ONLY: this script writes no file, changes no git state, and never deletes or creates a
# state, ledger or lock file (the lock probe opens the lock file without O_CREAT and never
# unlinks it). The only network calls are read-only GETs (manager identity, the tool store, the
# run list). Body strings read from files or sockets are parsed, never echoed as values — a
# credentials file is checked by presence (assignment-line count, file mode) only.
#
# Checks (every check runs; there is no `set -e`):
#   1. the STACK manager at STACK_MANAGER_URL answers GET /api/general/application with
#      productName "Stack manager"
#   2. the STACK owner lock for $STACK_HOST:$STACK_PORT is free — probed through the pinned
#      core's own endpoint_key/lock_path/default_lock_dir (honors STACK_MCP_LOCK_DIR) plus a
#      non-blocking flock, never a re-implemented lock name; a held lock is refused with the
#      StackOwnedError wording naming the holder record
#
# Exit codes: 0 = "PREFLIGHT OK" (last line); 1 = "BLOCKED: ..." (last line).
#
# Environment overrides (all optional; defaults suit the forb01 deployment):
#   GALAGO_TOOLS_DIR         the galago-tools root   (default: two levels above this script)
#   GALAGO_CORE_DIR          the galago-core checkout (default: $GALAGO_TOOLS_DIR/../galago-core)
#   STACK_MANAGER_URL        the STACK manager base URL (default: http://10.150.1.125:5005)
#   STACK_HOST               the live manager host string (default: 10.150.1.125)
#   STACK_PORT               the live manager port (default: 5005)
#   GALAGO_SERVICES_VENV     the service venv (default: $GALAGO_TOOLS_DIR/.venv)
#   GALAGO_WEB_URL           the galago-web base URL (default: http://localhost:3010)
#   GAL07_DEP02_GATE         the DEP-02 gate script
#                            (default: $GALAGO_TOOLS_DIR/docs/runbooks/gal-02-dep02-check.sh)
#   GAL07_LOCK_PROBE_PYTHON  the probe python for check 2 (default: the first of the service
#                            venv python and the gate venv python that can import
#                            stack_automation_layer.owner_lock)
#   GAL07_STACK_ENV          the operator credentials env file
#                            (default: $HOME/.config/galago-tools/stack.env)
#   GAL07_REQUIRE_STACK_ENV  set to 1 to make a missing credentials env file blocking instead of
#                            warn-only (Parts 2-3 of the runbook set this)
#   GAL07_DOCKER             the docker CLI (default: docker)
#   GAL07_WEB_CONTAINER      the galago-web container name (default: galago-web)
#   STACK_MCP_LOCK_DIR       honored by the core's default_lock_dir (probe and tool server)

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GT="${GALAGO_TOOLS_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
GC="${GALAGO_CORE_DIR:-$GT/../galago-core}"
MGR_URL="${STACK_MANAGER_URL:-http://10.150.1.125:5005}"
STACK_HOST_PORT="${STACK_HOST:-10.150.1.125}"
STACK_PORT_PORT="${STACK_PORT:-5005}"
SERVICES_VENV="${GALAGO_SERVICES_VENV:-$GT/.venv}"
WEB_URL="${GALAGO_WEB_URL:-http://localhost:3010}"
DEP02_GATE="${GAL07_DEP02_GATE:-$GT/docs/runbooks/gal-02-dep02-check.sh}"
STACK_ENV_FILE="${GAL07_STACK_ENV:-$HOME/.config/galago-tools/stack.env}"
REQUIRE_STACK_ENV="${GAL07_REQUIRE_STACK_ENV:-}"
DOCKER="${GAL07_DOCKER:-docker}"
WEB_CONTAINER="${GAL07_WEB_CONTAINER:-galago-web}"

failed=0

# 1. STACK manager identity. An empty body, a non-JSON body or a wrong productName each fails.
identity_body="$(curl -fsS -m 5 "$MGR_URL/api/general/application" 2>/dev/null || true)"
if [ -z "$identity_body" ] \
    || ! printf '%s' "$identity_body" | jq -re '.productName == "Stack manager"' >/dev/null 2>&1; then
  echo "missing: STACK manager identity at $MGR_URL (GET /api/general/application must answer productName \"Stack manager\")"
  failed=1
fi

# 2. Owner lock free (D-05). The probe runs through the pinned core's own resolution helpers so
# it cannot drift from what open_service actually locks. STACK_MCP_LOCK_DIR is honored by
# default_lock_dir() itself (read at call time), so the probe inherits the operator's env.
lock_probe_path=""
if [ -n "${GAL07_LOCK_PROBE_PYTHON:-}" ]; then
  _lock_candidates=("$GAL07_LOCK_PROBE_PYTHON")
else
  _lock_candidates=("$SERVICES_VENV/bin/python" "$HOME/data/nikko/.venvs/galago-py310/bin/python")
fi
for _cand in "${_lock_candidates[@]}"; do
  if [ -x "$_cand" ] && "$_cand" -c "import stack_automation_layer.owner_lock" >/dev/null 2>&1; then
    lock_probe_path="$_cand"
    break
  fi
done

if [ -z "$lock_probe_path" ]; then
  echo "missing: a python that can import stack_automation_layer.owner_lock (tried: ${_lock_candidates[*]})"
  failed=1
else
  lock_probe_out="$(
    "$lock_probe_path" - "$STACK_HOST_PORT" "$STACK_PORT_PORT" <<'STACK_LOCK_PROBE'
import fcntl, os, sys, json
from stack_automation_layer.owner_lock import (
    LockHolder,
    default_lock_dir,
    endpoint_key,
    lock_path,
)

host, port = sys.argv[1], int(sys.argv[2])
path = lock_path(endpoint_key(host, port), default_lock_dir())
try:
    fd = os.open(path, os.O_RDWR)          # no O_CREAT: an absent file means nobody holds it
except FileNotFoundError:
    print("LOCK-FREE")
    sys.exit(0)
fd2 = os.open(path, os.O_RDONLY)
try:
    fcntl.flock(fd2, fcntl.LOCK_EX | fcntl.LOCK_NB)
    fcntl.flock(fd2, fcntl.LOCK_UN)
    print("LOCK-FREE")
    sys.exit(0)
except BlockingIOError:
    raw = os.read(fd2, 256)                # the 256-byte holder record
    try:
        obj = json.loads(raw.decode("utf-8").strip())
        holder = str(LockHolder(obj.get("owner"), obj.get("pid")))
    except Exception:
        holder = str(LockHolder(None, None))  # "an unknown process", the core's fallback
    print(
        f"{host}:{port} is already owned by {holder}; only one front end may hold "
        "it at a time (stop the other owner first)"
    )
    sys.exit(3)
finally:
    os.close(fd2)
    os.close(fd)
STACK_LOCK_PROBE
  )"
  lock_probe_rc=$?
  if [ "$lock_probe_rc" -eq 0 ]; then
    :
  elif [ "$lock_probe_rc" -eq 3 ]; then
    echo "missing: an owner lock free at $STACK_HOST_PORT:$STACK_PORT_PORT — STACK manager $lock_probe_out"
    failed=1
  else
    echo "missing: the owner-lock probe failed ($lock_probe_path exited $lock_probe_rc) — resolve manually before the session"
    failed=1
  fi
fi

if [ "$failed" -eq 0 ]; then
  echo "PREFLIGHT OK"
  exit 0
fi
echo "BLOCKED: the GAL-07 live pre-flight failed; resolve every missing:/forbidden:/warn: line above through docs/runbooks/gal-07-live-handoff.md (never hand-edit a config, hand-write a store entry or delete a file to clear one), re-run this script and expect PREFLIGHT OK"
exit 1
