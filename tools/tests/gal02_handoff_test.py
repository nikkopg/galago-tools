"""GAL-02 protocol tests (FLOW-01): the committed export JSON, evaluated in a node sandbox stub.

Every test reads scriptContent and the parameter defaults from
docs/runbooks/gal-02-handoff.protocol.json. The stub mirrors only the documented galago-core
script sandbox; the operator's real import and Preview (plan 06-03) stay the authority.
"""
import re
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from unittest.mock import patch

from google.protobuf.descriptor import FieldDescriptor
from google.protobuf.json_format import ParseDict

from tools.grpc_interfaces import fast_pb2, stack_pb2
from tools.tests import gal02_harness as harness
from tools.tests.gal02_harness import (
    NODE_SKIP_REASON,
    OPERATOR_ONLY_COMMANDS,
    PROTOCOL_PATH,
    ScriptResult,
    default_params,
    find_node,
    load_export,
    require_node,
    run_script,
    stack_legs,
)

_EXPECTED_NAMES = [
    "batch_label", "stack_tool", "fast_tool",
    "robot", "labware_profile",
    "source_device", "source_deck", "source_nest", "source_transfer_profile",
    "fast_device", "fast_deck", "fast_nest", "fast_transfer_profile",
    "stack_timeout_s",
    "fast_step_source_deck", "fast_step_dest_deck",
    "fast_step_source_plate_id", "fast_step_dest_plate_id",
    "fast_step_source_start_row", "fast_step_source_start_col",
    "fast_step_dest_start_row", "fast_step_dest_start_col",
    "fast_step_num_rows", "fast_step_num_cols",
    "fast_step_volume", "fast_step_tip_reuse", "fast_step_expected_tray_id",
]

_OPTIONAL_NAMES = {
    "source_transfer_profile", "fast_transfer_profile", "stack_timeout_s",
    "fast_step_expected_tray_id",
}

_KEY_TAIL = re.compile(
    r"-\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z-[0-9a-f]{8}-(in|out)$")

_FAST_INT_FIELDS = (
    "source_deck", "dest_deck", "source_plate_id", "dest_plate_id",
    "source_start_col", "dest_start_col", "num_rows", "num_cols",
)

_LOCATION_PARTS = ("device", "deck", "nest", "transfer_profile")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class TestNodeLookup(unittest.TestCase):
    """find_node / require_node (D-16c). These run without node."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _fake_node(self, path: Path) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n", encoding="utf-8")
        path.chmod(0o755)
        return str(path)

    def _nvm(self, home: Path, version: str) -> str:
        return self._fake_node(home / ".nvm" / "versions" / "node" / version / "bin" / "node")

    def test_node_lookup_prefers_path(self) -> None:
        home = self.root / "home"
        self._nvm(home, "v24.14.1")
        env_node = self._fake_node(self.root / "env" / "node")
        found = find_node(
            which=lambda name: "/opt/path/node", environ={"NODE": env_node}, home=home)
        self.assertEqual(found, "/opt/path/node")

    def test_node_lookup_then_node_env(self) -> None:
        home = self.root / "home"
        env_node = self._fake_node(self.root / "env" / "node")
        self.assertEqual(
            find_node(which=lambda name: None, environ={"NODE": env_node}, home=home), env_node)
        missing = str(self.root / "nowhere" / "node")
        self.assertIsNone(
            find_node(which=lambda name: None, environ={"NODE": missing}, home=home))

    def test_node_lookup_then_newest_nvm_by_number(self) -> None:
        home = self.root / "home"
        self._nvm(home, "v9.1.0")
        newest = self._nvm(home, "v24.14.1")
        self._nvm(home, "v18.20.4")
        self.assertEqual(find_node(which=lambda name: None, environ={}, home=home), newest)

    def test_node_lookup_none_when_nothing_found(self) -> None:
        home = self.root / "empty-home"
        home.mkdir()
        self.assertIsNone(find_node(which=lambda name: None, environ={}, home=home))

    def test_require_node_skips_with_the_stated_reason(self) -> None:
        with patch.object(harness, "find_node", return_value=None):
            with self.assertRaises(unittest.SkipTest) as caught:
                require_node()
        self.assertEqual(str(caught.exception), NODE_SKIP_REASON)
        for place in ("PATH", "$NODE", "~/.nvm/versions/node/*/bin/node"):
            self.assertIn(place, NODE_SKIP_REASON)


class TestGal02Protocol(unittest.TestCase):
    export: dict[str, Any]
    script: str
    defaults: dict[str, str]
    result: ScriptResult

    @classmethod
    def setUpClass(cls) -> None:
        require_node()
        cls.export = load_export()
        cls.script = cls.export["protocol"]["scriptContent"]
        cls.defaults = default_params(cls.export)
        cls.result = run_script(cls.script, cls.defaults)

    def _run(self, **overrides: Optional[str]) -> ScriptResult:
        """Evaluate with the defaults, a value of None removing the parameter."""
        params: dict[str, Any] = dict(self.defaults)
        for name, value in overrides.items():
            if value is None:
                params.pop(name, None)
            else:
                params[name] = value
        return run_script(self.script, params)

    def test_export_shape_matches_the_galago_core_export_format(self) -> None:
        export = self.export
        self.assertEqual(set(export), {"protocol", "exportedAt", "version"})
        self.assertEqual(export["version"], "1.0")
        stamp = export["exportedAt"]
        self.assertTrue(stamp.endswith("Z"), stamp)
        datetime.fromisoformat(stamp[:-1] + "+00:00")
        protocol = export["protocol"]
        self.assertEqual(
            set(protocol),
            {"name", "category", "description", "mode", "scriptContent", "parameters", "commands"})
        self.assertEqual(protocol["mode"], "script")
        self.assertEqual(protocol["commands"], [])
        self.assertIsInstance(protocol["scriptContent"], str)
        self.assertTrue(protocol["scriptContent"].strip())
        for key in ("name", "category", "description"):
            self.assertTrue(protocol[key].strip(), key)

    def test_parameters_satisfy_the_galago_core_parameter_schema(self) -> None:
        names: list[str] = []
        for entry in self.export["protocol"]["parameters"]:
            name = entry["name"]
            names.append(name)
            self.assertRegex(name, r"^[a-z][a-z0-9_]*$")
            self.assertTrue(entry["label"].strip(), name)
            self.assertIn(entry["type"], {"string", "number", "boolean", "select"}, name)
            self.assertIsInstance(entry["defaultValue"], str, name)
            self.assertIsInstance(entry["required"], bool, name)
            self.assertTrue(entry["description"].strip(), name)
            if entry["type"] == "select":
                options = entry["options"]
                self.assertIsInstance(options, list)
                self.assertTrue(options)
                self.assertTrue(all(isinstance(o, str) and o for o in options))
                self.assertIn(entry["defaultValue"], options)
        self.assertEqual(len(names), len(set(names)))

    def test_parameter_names_are_the_locked_vocabulary(self) -> None:
        parameters = self.export["protocol"]["parameters"]
        self.assertEqual([p["name"] for p in parameters], _EXPECTED_NAMES)
        fast_fields = set(fast_pb2.Command.Transfer.DESCRIPTOR.fields_by_name)
        for entry in parameters:
            if entry["name"].startswith("fast_step_"):
                self.assertIn(entry["name"][len("fast_step_"):], fast_fields, entry["name"])
        optional = {p["name"] for p in parameters if not p["required"]}
        self.assertEqual(optional, _OPTIONAL_NAMES)

    def test_command_order_is_note_stack_in_fast_stack_out(self) -> None:
        result = self.result
        self.assertTrue(result.ok, result.error)
        self.assertEqual(
            [(c["tool"], c["command"]) for c in result.calls],
            [("Tool Box", "note"), ("STACK", "transfer"), ("FAST", "transfer"),
             ("STACK", "transfer")])
        in_leg, _out = stack_legs(result)
        base = in_leg["step_key"][: -len("-in")]
        self.assertIn(base, result.calls[0]["params"]["message"])

    def test_command_order_uses_the_tool_instance_names(self) -> None:
        result = self._run(stack_tool="STACK-PACSIM", fast_tool="FAST-SIM")
        self.assertTrue(result.ok, result.error)
        self.assertEqual(
            [c["tool"] for c in result.calls],
            ["Tool Box", "STACK-PACSIM", "FAST-SIM", "STACK-PACSIM"])

    def test_step_key_is_non_blank_distinct_and_run_unique(self) -> None:
        in_leg, out_leg = stack_legs(self.result)
        key_in, key_out = in_leg["step_key"], out_leg["step_key"]
        self.assertTrue(key_in.strip())
        self.assertTrue(key_out.strip())
        self.assertNotEqual(key_in, key_out)
        self.assertTrue(key_in.endswith("-in"))
        self.assertTrue(key_out.endswith("-out"))
        self.assertEqual(key_in[: -len("-in")], key_out[: -len("-out")])
        second_in, second_out = stack_legs(self._run())
        self.assertEqual(
            len({key_in, key_out, second_in["step_key"], second_out["step_key"]}), 4)

    def test_step_key_long_label_is_truncated_never_the_timestamp_or_suffix(self) -> None:
        label = "".join(chr(ord("A") + (i % 26)) for i in range(100))
        in_leg, out_leg = stack_legs(self._run(batch_label=label))
        for key in (in_leg["step_key"], out_leg["step_key"]):
            self.assertLessEqual(len(key), 58, key)
            self.assertTrue(key.startswith(label[:20] + "-"), key)
            self.assertNotIn(label[:21], key)
            self.assertRegex(key, _KEY_TAIL)

    def test_step_key_label_is_truncated_by_code_point(self) -> None:
        label = "a" * 19 + "\U0001F600" + "tail-text-after"
        in_leg, out_leg = stack_legs(self._run(batch_label=label))
        for key in (in_leg["step_key"], out_leg["step_key"]):
            self.assertTrue(key.startswith("a" * 19 + "\U0001F600" + "-"), key)
            self.assertLessEqual(len(key), 58)
            key.encode("utf-8")  # raises on a lone surrogate

    def test_swap_return_leg_is_the_in_leg_swapped(self) -> None:
        result = self._run(source_transfer_profile="SRC-PROFILE", fast_transfer_profile="FAST-PROFILE")
        in_leg, out_leg = stack_legs(result)
        for part in _LOCATION_PARTS:
            self.assertEqual(out_leg["source_" + part], in_leg["destination_" + part], part)
            self.assertEqual(out_leg["destination_" + part], in_leg["source_" + part], part)
        self.assertEqual(in_leg["source_transfer_profile"], "SRC-PROFILE")
        self.assertEqual(in_leg["destination_transfer_profile"], "FAST-PROFILE")
        self.assertEqual(out_leg["robot"], in_leg["robot"])
        self.assertEqual(out_leg["labware_profile"], in_leg["labware_profile"])

    def test_safe_defaults_are_the_pac_sim_lab_names(self) -> None:
        in_leg, out_leg = stack_legs(self.result)
        self.assertEqual(in_leg["robot"], "sim-arm-1")
        self.assertEqual(in_leg["labware_profile"], "greiner 96 white")
        self.assertEqual(
            (in_leg["source_device"], in_leg["source_deck"], in_leg["source_nest"]),
            ("sim-nest-a", "sim-deck-a", "sim-A1"))
        self.assertEqual(
            (in_leg["destination_device"], in_leg["destination_deck"], in_leg["destination_nest"]),
            ("sim-nest-b", "sim-deck-b", "sim-B1"))
        self.assertEqual(
            (out_leg["source_device"], out_leg["destination_device"]),
            ("sim-nest-b", "sim-nest-a"))
        for name in ("source_transfer_profile", "fast_transfer_profile", "stack_timeout_s"):
            self.assertEqual(self.defaults[name], "", name)

    def test_safe_defaults_emit_no_operator_only_command(self) -> None:
        self.assertTrue(self.result.ok, self.result.error)
        for call in self.result.calls:
            self.assertNotIn(call["command"], OPERATOR_ONLY_COMMANDS)
            if call["tool"] == "Tool Box":
                self.assertEqual(call["command"], "note")

    def test_optional_keys_are_omitted_when_blank_and_numbers_are_real(self) -> None:
        in_leg, out_leg = stack_legs(self.result)
        fast = self.result.calls[2]["params"]
        for leg in (in_leg, out_leg):
            for key in ("source_transfer_profile", "destination_transfer_profile", "timeout_s"):
                self.assertNotIn(key, leg)
        self.assertNotIn("expected_tray_id", fast)
        for field in _FAST_INT_FIELDS:
            self.assertTrue(_is_int(fast[field]), field)
        self.assertTrue(_is_number(fast["volume"]))
        result = self._run(
            source_transfer_profile="P1", fast_transfer_profile="P2",
            stack_timeout_s="45.5", fast_step_expected_tray_id="2")
        set_in, set_out = stack_legs(result)
        for leg in (set_in, set_out):
            self.assertIn("source_transfer_profile", leg)
            self.assertIn("destination_transfer_profile", leg)
            self.assertEqual(leg["timeout_s"], 45.5)
            self.assertTrue(_is_number(leg["timeout_s"]))
        fast_set = result.calls[2]["params"]
        self.assertEqual(fast_set["expected_tray_id"], 2)
        self.assertTrue(_is_int(fast_set["expected_tray_id"]))

    def test_throws_on_blank_or_absent_required_input_before_any_command(self) -> None:
        required = [p["name"] for p in self.export["protocol"]["parameters"] if p["required"]]
        self.assertEqual(len(required), 23)
        for name in required:
            for label, value in (("blank", ""), ("whitespace", "   \t"), ("absent", None)):
                with self.subTest(parameter=name, case=label):
                    result = self._run(**{name: value})
                    self.assertFalse(result.ok)
                    self.assertIn(name, result.error)
                    self.assertEqual(result.calls, [])

    def test_throws_on_invalid_numbers(self) -> None:
        cases = {
            "fast_step_num_rows": "1.5",
            "fast_step_volume": "0",
            "stack_timeout_s": "abc",
        }
        for name, value in cases.items():
            with self.subTest(parameter=name, value=value):
                result = self._run(**{name: value})
                self.assertFalse(result.ok)
                self.assertIn(name, result.error)
                self.assertEqual(result.calls, [])
        with self.subTest(parameter="stack_timeout_s", value="-1"):
            result = self._run(stack_timeout_s="-1")
            self.assertFalse(result.ok)
            self.assertIn("stack_timeout_s", result.error)
            self.assertEqual(result.calls, [])

    def test_fast_step_invalid_values_throw_at_queue_time_with_zero_commands(self) -> None:
        # WR-01: each of these is rejected by tools/fast/server.py _check_args, so it must throw
        # before the STACK in-leg is queued, not come back as INVALID_ARGUMENTS after the plate moved.
        # The last element says whether the value can be built into a fast_pb2 message to cross-check.
        invalid: list[tuple[str, str, bool]] = []
        for name in ("source_deck", "dest_deck"):
            invalid += [(f"fast_step_{name}", v, True) for v in ("0", "-1", "7", "99")]
            invalid += [(f"fast_step_{name}", "2147483648", False)]
        for name in ("source_plate_id", "dest_plate_id", "source_start_col", "dest_start_col",
                     "num_rows", "num_cols"):
            invalid += [(f"fast_step_{name}", v, True) for v in ("0", "-3")]
            invalid += [(f"fast_step_{name}", v, False) for v in ("2147483648", "1e12", "Infinity")]
        for name in ("source_start_row", "dest_start_row"):
            invalid += [(f"fast_step_{name}", v, True) for v in ("ABC", "1", "A1", "A-", "a b", "\u00c9")]
        invalid += [("fast_step_volume", v, True) for v in ("-5", "0")]
        invalid += [("fast_step_volume", v, False) for v in ("Infinity", "NaN", "abc")]
        invalid += [("fast_step_tip_reuse", v, True) for v in ("fresh2", "Fresh", "none", "reuse,fresh")]
        invalid += [("fast_step_expected_tray_id", v, False) for v in ("1.5", "abc", "2147483648")]
        self.assertGreater(len(invalid), 40)
        for name, value, buildable in invalid:
            with self.subTest(parameter=name, value=value):
                result = self._run(**{name: value})
                self.assertFalse(result.ok, f"{name}={value!r} was accepted")
                self.assertIn(name, result.error)
                self.assertEqual(result.calls, [])
                if buildable and not name.endswith("expected_tray_id"):
                    problems = self._fast_check_args({**self.defaults, name: value})
                    self.assertTrue(problems, f"_check_args accepts {name}={value!r}")

    def test_fast_step_boundary_values_are_accepted_and_agree_with_check_args(self) -> None:
        valid = [
            ("fast_step_source_deck", "1"), ("fast_step_source_deck", "6"),
            ("fast_step_dest_deck", "6"), ("fast_step_num_rows", "1"),
            ("fast_step_num_cols", "2147483647"), ("fast_step_source_plate_id", "1"),
            ("fast_step_source_start_col", "1"), ("fast_step_source_start_row", "AB"),
            ("fast_step_dest_start_row", "z"), ("fast_step_volume", "0.5"),
            ("fast_step_tip_reuse", "reuse"), ("fast_step_expected_tray_id", "0"),
        ]
        for name, value in valid:
            with self.subTest(parameter=name, value=value):
                result = self._run(**{name: value})
                self.assertTrue(result.ok, result.error)
                self.assertEqual(
                    [(c["tool"], c["command"]) for c in result.calls],
                    [("Tool Box", "note"), ("STACK", "transfer"), ("FAST", "transfer"),
                     ("STACK", "transfer")])
                self.assertEqual(self._fast_check_args({**self.defaults, name: value}), [])

    def _fast_check_args(self, params: dict[str, str]) -> list[str]:
        """Run the script with params (must succeed for valid input) or build the F.A.S.T. message
        straight from them, and return tools.fast.server._check_args for it."""
        try:
            from tools.fast.server import _check_args
        except ModuleNotFoundError as exc:
            if exc.name and exc.name.split(".")[0] in ("fast_mcp", "httpx"):
                self.skipTest(
                    "fast_mcp core is not installed (private GitLab dependency, see "
                    "tools/fast/requirements.txt); F.A.S.T. _check_args not asserted")
            raise
        message: dict[str, Any] = {}
        for field in fast_pb2.Command.Transfer.DESCRIPTOR.fields_by_name:
            raw = params.get("fast_step_" + field, "")
            if raw == "":
                continue
            kind = fast_pb2.Command.Transfer.DESCRIPTOR.fields_by_name[field].type
            if kind == FieldDescriptor.TYPE_INT32:
                message[field] = int(raw)
            elif kind == FieldDescriptor.TYPE_DOUBLE:
                message[field] = float(raw)
            else:
                message[field] = raw
        return list(_check_args(ParseDict(message, fast_pb2.Command.Transfer())))

    def test_throws_on_a_degenerate_handoff_before_any_command(self) -> None:
        # WR-02: same tool on both sides, or the same device/deck/nest on both sides.
        with self.subTest(case="same tool"):
            result = self._run(stack_tool="TOOL-X", fast_tool="TOOL-X")
            self.assertFalse(result.ok)
            self.assertIn("fast_tool", result.error)
            self.assertEqual(result.calls, [])
        same = {
            "fast_device": self.defaults["source_device"],
            "fast_deck": self.defaults["source_deck"],
            "fast_nest": self.defaults["source_nest"],
        }
        with self.subTest(case="same location"):
            result = self._run(**same)
            self.assertFalse(result.ok)
            self.assertIn("fast_nest", result.error)
            self.assertEqual(result.calls, [])
        for part in ("fast_device", "fast_deck", "fast_nest"):
            with self.subTest(case="one part differs", part=part):
                result = self._run(**{**same, part: "elsewhere"})
                self.assertTrue(result.ok, result.error)
                self.assertEqual(len(result.calls), 4)

    def test_script_style_uses_only_the_documented_sandbox_api(self) -> None:
        script = self.script
        self.assertIsNone(re.search(r"\b(let|const)\b", script))
        self.assertNotIn("require(", script)
        self.assertNotIn("fetch(", script)
        members = set(re.findall(r"\bgalago\.(\w+)", script))
        self.assertEqual(members, {"command", "note"})

    def test_strict_mode_gives_the_same_commands(self) -> None:
        strict = run_script(self.script, self.defaults, strict=True)
        self.assertTrue(strict.ok, strict.error)
        plain = self.result
        self.assertEqual(
            [(c["tool"], c["command"]) for c in strict.calls],
            [(c["tool"], c["command"]) for c in plain.calls])
        self.assertEqual(
            [set(c["params"]) for c in strict.calls], [set(c["params"]) for c in plain.calls])

    def test_proto_contract_stack_and_fast_dicts_parse_and_fast_check_args_passes(self) -> None:
        in_leg, out_leg = stack_legs(self.result)
        for leg in (in_leg, out_leg):
            ParseDict(leg, stack_pb2.Command.Transfer())
        fast = ParseDict(self.result.calls[2]["params"], fast_pb2.Command.Transfer())
        try:
            from tools.fast.server import _check_args
        except ModuleNotFoundError as exc:
            if exc.name and exc.name.split(".")[0] in ("fast_mcp", "httpx"):
                self.skipTest(
                    "fast_mcp core is not installed (private GitLab dependency, see "
                    "tools/fast/requirements.txt); F.A.S.T. _check_args not asserted")
            raise
        self.assertEqual(_check_args(fast), [])

    def test_no_hardware_names_in_the_protocol(self) -> None:
        text = PROTOCOL_PATH.read_text(encoding="utf-8")
        for name in ("10.150.1.125", "stack-server", "stack2-6"):
            self.assertNotIn(name, text)


if __name__ == "__main__":
    unittest.main()
