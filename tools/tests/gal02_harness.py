"""Shared harness for the GAL-02 protocol tests (not collected as tests).

Runs the protocol's ``scriptContent`` in a node ``vm`` stub of galago-core's
documented script sandbox and returns the commands the script emitted. The stub
mirrors only the documented sandbox API (galago.command, galago.note, galago.timer
and the listed globals). It is not a reimplementation of galago-core's executor:
the real import and Preview in the operator run are the authority.
"""
import json
import os
import re
import shutil
import subprocess
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

PROTOCOL_PATH = (
    Path(__file__).resolve().parents[2] / "docs" / "runbooks" / "gal-02-handoff.protocol.json")

# The real STACK. Same values as the SAL netguard deny-set.
HARDWARE_DENY = frozenset({"10.150.1.125", "stack-server"})

# galago-core refuses these in any protocol; the script must never emit them.
OPERATOR_ONLY_COMMANDS = frozenset({"acknowledge_failure", "pause", "resume", "abort"})

NODE_SKIP_REASON = "node not found: tried PATH, $NODE, ~/.nvm/versions/node/*/bin/node"

_VERSION_DIR = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")

_HARNESS_JS = r"""
const vm = require("vm");
const fs = require("fs");
const calls = [];
const galago = {
  command(tool, command, params) { calls.push({tool: tool, command: command, params: params}); },
  note(message) { calls.push({tool: "Tool Box", command: "note", params: {message: message}}); },
  timer(seconds) { calls.push({tool: "Tool Box", command: "timer", params: {seconds: seconds}}); }
};
const input = JSON.parse(fs.readFileSync(0, "utf8"));
const context = vm.createContext({
  galago: galago, params: input.params, console: console, Math: Math, Array: Array,
  Object: Object, String: String, Number: Number, Boolean: Boolean, JSON: JSON, Date: Date,
  parseInt: parseInt, parseFloat: parseFloat, isNaN: isNaN, isFinite: isFinite
});
try {
  new vm.Script(input.script, {filename: "protocol-script.js"}).runInContext(context, {timeout: 5000});
  console.log(JSON.stringify({ok: true, calls: calls, error: ""}));
} catch (e) {
  // A throw inside the vm context is not an instance of this realm's Error: read the message.
  console.log(JSON.stringify({ok: false, calls: calls, error: String(e && e.message)}));
}
"""


@dataclass(frozen=True)
class ScriptResult:
    ok: bool
    calls: list[dict[str, Any]]
    error: str


def _is_executable_file(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def find_node(
    *,
    which: Callable[[str], Optional[str]] = shutil.which,
    environ: Optional[Mapping[str, str]] = None,
    home: Optional[Path] = None,
) -> Optional[str]:
    """Find node: PATH first, then $NODE, then the newest ~/.nvm/versions/node/v*/bin/node
    by numeric version (so v24 beats v9). Returns None when none exists."""
    found = which("node")
    if found:
        return found
    env = os.environ if environ is None else environ
    override = env.get("NODE", "")
    if override and _is_executable_file(override):
        return override
    root = (Path.home() if home is None else home) / ".nvm" / "versions" / "node"
    best: Optional[tuple[tuple[int, int, int], str]] = None
    if root.is_dir():
        for entry in root.iterdir():
            match = _VERSION_DIR.match(entry.name)
            candidate = entry / "bin" / "node"
            if match is None or not _is_executable_file(str(candidate)):
                continue
            version = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
            if best is None or version > best[0]:
                best = (version, str(candidate))
    return best[1] if best else None


def require_node() -> str:
    node = find_node()
    if node is None:
        raise unittest.SkipTest(NODE_SKIP_REASON)
    return node


def load_export() -> dict[str, Any]:
    with open(PROTOCOL_PATH, encoding="utf-8") as handle:
        loaded: dict[str, Any] = json.load(handle)
    return loaded


def default_params(export: Optional[dict[str, Any]] = None) -> dict[str, str]:
    """Each parameter name mapped to its defaultValue ("" when absent): what the run form sends."""
    document = load_export() if export is None else export
    return {p["name"]: p.get("defaultValue", "") for p in document["protocol"]["parameters"]}


def run_script(script: str, params: Mapping[str, Any], *, strict: bool = False) -> ScriptResult:
    """Evaluate the script in the node sandbox stub with the given params."""
    node = require_node()
    source = '"use strict";\n' + script if strict else script
    completed = subprocess.run(
        [node, "-e", _HARNESS_JS],
        input=json.dumps({"script": source, "params": dict(params)}),
        capture_output=True,
        encoding="utf-8",
        timeout=30,
        check=True,
    )
    last = completed.stdout.strip().splitlines()[-1]
    parsed = json.loads(last)
    return ScriptResult(ok=bool(parsed["ok"]), calls=list(parsed["calls"]), error=str(parsed["error"]))


def stack_legs(result: ScriptResult) -> tuple[dict[str, Any], dict[str, Any]]:
    """The in leg and the out leg params (calls 1 and 3), both asserted to be transfers."""
    assert result.ok, result.error
    for index in (1, 3):
        assert result.calls[index]["command"] == "transfer", result.calls[index]
    return result.calls[1]["params"], result.calls[3]["params"]
