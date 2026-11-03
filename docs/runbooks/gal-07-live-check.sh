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
# Checks (every check runs; there is no `set -e`; the operator sees every failure in one run):
#   1. the STACK manager at STACK_MANAGER_URL answers GET /api/general/application with
#      productName "Stack manager"
#   2. the STACK owner lock for $STACK_HOST:$STACK_PORT is free — probed through the pinned
#      core's own endpoint_key/lock_path/default_lock_dir (honors STACK_MCP_LOCK_DIR) plus a
#      non-blocking flock, never a re-implemented lock name; a held lock is refused with the
#      StackOwnedError wording naming the holder record, EXCEPT a holder with owner `galago`
#      — the session's own STACK tool server, the expected single-owner state after a
#      real-mode Configure — which is reported as an `ok:` line and does not block
#      (owner `mcp`, stack-mcp, or an unknown/absent owner still blocks)
#   3. the service venv holds stack_automation_layer pinned at
#      934a621ece116a8b263897c1e9b62b57374f4ef3 — asserted from the distribution's
#      direct_url.json vcs_info.commit_id
#   4. the DEP-02 gate re-run (GAL07_DEP02_GATE) ends with "DEP-02 OK"
#   5. the galago-web container bundle under /app/gen-interfaces exports Command_Transfer
#   6. the tool store at $GALAGO_WEB_URL/api/tools holds a configured stack tool AND a fast
#      tool, with the stack tool's stored config host byte-equal to $STACK_HOST (D-12: a
#      different host string is, by core design, a different lock/state key)
#   7. the run list at $GALAGO_WEB_URL/api/runs holds no run in state RUNNING
#   8. the operator credentials env file (GAL07_STACK_ENV) exists, holds exactly an assignment
#      line for STACK_USER, and has mode 0600 — presence-only, never a value; an absent file is
#      a warn: (advisory) unless GAL07_REQUIRE_STACK_ENV=1, which makes it blocking
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
        owner = obj.get("owner")
    except Exception:
        holder = str(LockHolder(None, None))  # "an unknown process", the core's fallback
        owner = None
    # A holder record with owner `galago` is the session's own STACK tool server — the
    # expected single-owner state after the runbook's real-mode Configure (Parts 2-3 run
    # while the tool server is up). It passes as LOCK-FREE-equivalent; any other owner
    # (mcp / stack-mcp / unknown / a record that will not parse) still blocks.
    if owner == "galago":
        print("GALAGO-OWNED", holder)
        sys.exit(0)
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
    if [ "${lock_probe_out%% *}" = "GALAGO-OWNED" ]; then
      echo "ok: the owner lock at $STACK_HOST_PORT:$STACK_PORT_PORT is held by ${lock_probe_out#GALAGO-OWNED } — the expected single-owner state (the session's own STACK tool server holds the lock; Galago permits itself)"
    fi
  elif [ "$lock_probe_rc" -eq 3 ]; then
    echo "missing: an owner lock free at $STACK_HOST_PORT:$STACK_PORT_PORT — STACK manager $lock_probe_out"
    failed=1
  else
    echo "missing: the owner-lock probe failed ($lock_probe_path exited $lock_probe_rc) — resolve manually before the session"
    failed=1
  fi
fi

# 3. Core pin in the service venv (DEP-02 build lineage). The dist-info's direct_url.json is the
# discriminating piece: an unrelated stack_automation_layer-*.dist-info tree without the file,
# or one recording a different commit, both fail.
pin_target="934a621ece116a8b263897c1e9b62b57374f4ef3"
direct_url_file=""
if [ -d "$SERVICES_VENV/lib" ]; then
  direct_url_file="$(find "$SERVICES_VENV/lib" \
    -path '*stack_automation_layer-*.dist-info/direct_url.json' -print 2>/dev/null | head -n 1)"
fi
if [ -z "$direct_url_file" ] \
    || ! jq -re --arg want "$pin_target" '.vcs_info.commit_id == $want' \
        "$direct_url_file" >/dev/null 2>&1; then
  echo "missing: stack_automation_layer pinned at $pin_target in the service venv $SERVICES_VENV (stack_automation_layer-*.dist-info/direct_url.json absent or a different commit)"
  failed=1
fi

# 4. DEP-02 gate re-run. The Phase 6 gate's own verdict is the authority; a missing, crashing or
# failing gate script can never count as OK (the last line must be exactly DEP-02 OK).
dep02_rc=0
dep02_out="$(bash "$DEP02_GATE" 2>&1)" || dep02_rc=$?
if [ "$dep02_rc" -ne 0 ] \
    || ! printf '%s\n' "$dep02_out" | tail -n 1 | grep -q '^DEP-02 OK$'; then
  echo "missing: the DEP-02 gate re-run did not end with DEP-02 OK ($DEP02_GATE exited $dep02_rc)"
  failed=1
fi

# 5. Web bundle. What the operator's browser runs is the container's copy of the generated
# stack types, not the galago-core checkout.
bundle_rc=0
bundle_out="$("$DOCKER" exec "$WEB_CONTAINER" grep -rl Command_Transfer /app/gen-interfaces \
  2>/dev/null)" || bundle_rc=$?
if [ "$bundle_rc" -ne 0 ] || [ -z "$bundle_out" ]; then
  echo "missing: Command_Transfer under /app/gen-interfaces in container $WEB_CONTAINER (rebuild galago-web from the DEP-02 build)"
  failed=1
fi

# 6. D-12 pre-store check. Both GAL-02 protocol tools must exist, and the stack tool's stored host
# must equal STACK_HOST byte-for-byte (Pitfall 6: any other string splits lock and state keys).
tools_body="$(curl -fsS -m 5 "$WEB_URL/api/tools" 2>/dev/null || true)"
if [ -z "$tools_body" ] || ! printf '%s' "$tools_body" | jq -e 'type == "array"' >/dev/null 2>&1; then
  echo "missing: a JSON tool array from $WEB_URL/api/tools (the galago-web tool store is unreachable or not JSON)"
  failed=1
else
  stack_present="$(printf '%s' "$tools_body" | jq 'any(.[]; (.type? // "") == "stack")' 2>/dev/null || echo false)"
  fast_present="$(printf '%s' "$tools_body" | jq 'any(.[]; (.type? // "") == "fast")' 2>/dev/null || echo false)"
  stacked_hosts="$(printf '%s' "$tools_body" \
    | jq -r '[.[] | select((.type? // "") == "stack") | (.config.host? // .config.stack.host? // null)] | unique' 2>/dev/null || true)"
  if ! printf '%s' "$stack_present" | grep -q '^true$'; then
    echo "missing: a type stack tool in $WEB_URL/api/tools (the store holds none)"
    failed=1
  elif ! printf '%s\n' "$stacked_hosts" | jq -e --arg want "$STACK_HOST_PORT" 'index($want)' >/dev/null 2>&1; then
    echo "missing: a type stack tool with host $STACK_HOST_PORT byte-exactly in $WEB_URL/api/tools (the stored host string(s): $stacked_hosts — a different string is a different lock/state key)"
    failed=1
  fi
  if ! printf '%s' "$fast_present" | grep -q '^true$'; then
    echo "missing: a type fast tool in $WEB_URL/api/tools (create and configure the F.A.S.T. tool through its tool page before any run)"
    failed=1
  fi
fi

# 7. No run in flight (D-12/T-07-03). A RUNNING run must reach a terminal state before the
# session (or a GO gate) starts, so a stale or reused step key can never move the arm. The run
# list is a bare JSON array or galago-web's {"count": n, "data": [...]} envelope; any other
# shape fails closed.
runs_body="$(curl -fsS -m 5 "$WEB_URL/api/runs" 2>/dev/null || true)"
runs_array="$(printf '%s' "$runs_body" | jq -c 'if type == "array" then . elif type == "object" and ((.data? | type) == "array") then .data else empty end' 2>/dev/null || true)"
if [ -z "$runs_array" ]; then
  echo "missing: a parsable runs list from $WEB_URL/api/runs (it must be a JSON array or a {\"count\": n, \"data\": [...]} envelope; the run list is unreachable or unexpected)"
  failed=1
else
  running="$(printf '%s' "$runs_array" \
    | jq '[.[] | select((.state? == "RUNNING") or (.status? == "RUNNING"))] | length' \
    2>/dev/null || true)"
  if [ -z "$running" ]; then
    echo "missing: a parsable runs list from $WEB_URL/api/runs (entries without state/status fields are not recognised)"
    failed=1
  elif [ "$running" -gt 0 ]; then
    echo "missing: no run in flight at $WEB_URL/api/runs — a run with state RUNNING is present; let it reach a terminal state before any part starts"
    failed=1
  fi
fi

# 8. Credential presence (D-06/T-07-02), advisory by default. Existence, an assignment line and
# mode 0600 are checked; values are never read, matched or printed.
if [ -f "$STACK_ENV_FILE" ]; then
  env_mode="$(stat -c '%a' "$STACK_ENV_FILE" 2>/dev/null || echo "unstatable")"
  env_assigns="$(grep -c '^STACK_USER=' "$STACK_ENV_FILE" 2>/dev/null)" || true
  : "${env_assigns:=0}"
  if [ "$env_assigns" -eq 0 ]; then
    if [ "$REQUIRE_STACK_ENV" = "1" ]; then
      echo "missing: a ^STACK_USER= assignment line in the credentials env file $STACK_ENV_FILE"
      failed=1
    else
      echo "warn: no ^STACK_USER= assignment line in the credentials env file $STACK_ENV_FILE (real-mode Configure needs the credentials there)"
    fi
  fi
  if [ "$env_mode" != "600" ]; then
    if [ "$REQUIRE_STACK_ENV" = "1" ]; then
      echo "missing: $STACK_ENV_FILE has mode $env_mode, expected 0600 (chmod 600 it)"
      failed=1
    else
      echo "warn: $STACK_ENV_FILE has mode $env_mode, expected 0600 (chmod 600 it)"
    fi
  fi
else
  if [ "$REQUIRE_STACK_ENV" = "1" ]; then
    echo "missing: the stack credentials env file $STACK_ENV_FILE (the operator's 0600 env file holding STACK_USER/STACK_PASSWORD)"
    failed=1
  else
    echo "warn: no stack credentials env file at $STACK_ENV_FILE (real-mode Configure will need it; create it 0600 through this runbook's operator steps)"
  fi
fi

if [ "$failed" -eq 0 ]; then
  echo "PREFLIGHT OK"
  exit 0
fi
echo "BLOCKED: the GAL-07 live pre-flight failed; resolve every missing:/forbidden:/warn: line above through docs/runbooks/gal-07-live-handoff.md (never hand-edit a config, hand-write a store entry or delete a file to clear one), re-run this script and expect PREFLIGHT OK"
exit 1
