"""Tests for the STACK tool adapter (tools/stack/server.py).

Hermetic by construction: every _StackTestCase uses a temp owner-lock
directory, explicit fake credentials, no proxy environment, and a guard that
fails any socket connect to a non-loopback address.
"""
import ast
import copy
import importlib.metadata
import json
import os
import socket
import tempfile
import unittest
from concurrent import futures
from pathlib import Path
from typing import Any, Callable, Optional
from unittest.mock import MagicMock, patch

import grpc
from google.protobuf import empty_pb2
from google.protobuf.struct_pb2 import Struct
from google.protobuf.descriptor import FieldDescriptor

# Every import that depends on the private stack-automation-layer core (a
# git+https install against an internal GitLab, tools/stack/requirements.txt)
# is collected into this one try block so a missing core skips these tests
# with a clear reason instead of erroring. httpx arrives only transitively
# with the core. The local Python 3.10 `bin/make test` run (core installed)
# stays the authoritative gate.
try:
    import httpx  # noqa: F401
    import stack_automation_layer.composition as core_composition
    from stack_automation_layer.owner_lock import StackOwnedError, acquire_owner_lock
    from stack_automation_layer.model import Location, TransferRequest
    from stack_automation_layer.results import (
        Estimated,
        NeedsInput,
        ReadFailed,
        Rejected,
    )
    from stack_automation_layer.service import StackService

    from tools.stack.server import StackServer
except ModuleNotFoundError as exc:
    if exc.name and exc.name.split(".")[0] in ("stack_automation_layer", "httpx"):
        raise unittest.SkipTest(
            "stack_automation_layer core is not installed (private GitLab dependency, see "
            "tools/stack/requirements.txt); the local Python 3.10 bin/make test run "
            "is the authoritative gate") from exc
    raise

from tools.grpc_interfaces import controller_pb2, stack_pb2, tool_base_pb2
from tools.grpc_interfaces.tool_base_pb2 import (
    ERROR_FROM_TOOL,
    FAILED,
    NOT_READY,
    READY,
    SUCCESS,
)
from tools.grpc_interfaces.tool_driver_pb2_grpc import (
    ToolDriverStub,
    add_ToolDriverServicer_to_server,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

_LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")


def _free_tcp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


def _loopback_guard(real: Callable[..., Any]) -> Callable[..., Any]:
    def guarded(self: Any, address: Any, *args: Any, **kwargs: Any) -> Any:
        if self.family != socket.AF_UNIX:
            host = address[0] if isinstance(address, tuple) else address
            if host not in _LOOPBACK_HOSTS:
                raise AssertionError(f"non-loopback socket connect blocked: {address!r}")
        return real(self, address, *args, **kwargs)
    return guarded


class _StackTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.lock_dir = self._tmpdir.name

        env_patcher = patch.dict(os.environ, {
            "STACK_MCP_LOCK_DIR": self.lock_dir,
            "STACK_USER": "galago-test-user",
            "STACK_PASSWORD": "galago-test-password",
        })
        env_patcher.start()
        self.addCleanup(env_patcher.stop)
        for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                     "http_proxy", "https_proxy", "all_proxy"):
            os.environ.pop(name, None)

        for attr in ("connect", "connect_ex"):
            patcher = patch.object(
                socket.socket, attr, _loopback_guard(getattr(socket.socket, attr)))
            patcher.start()
            self.addCleanup(patcher.stop)


def _serve_in_process(case: unittest.TestCase, server: StackServer) -> ToolDriverStub:
    port = _free_tcp_port()
    grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    add_ToolDriverServicer_to_server(server, grpc_server)
    grpc_server.add_insecure_port(f"127.0.0.1:{port}")
    grpc_server.start()
    channel = grpc.insecure_channel(f"127.0.0.1:{port}")

    def _close_owned() -> None:
        if server._owned is not None:
            server._owned.close()

    case.addCleanup(grpc_server.stop, None)
    case.addCleanup(channel.close)
    case.addCleanup(_close_owned)
    return ToolDriverStub(channel)


def _fake_transport() -> MagicMock:
    transport = MagicMock()
    transport.get_application.return_value = {"productName": "Stack manager"}
    transport.get_versions.return_value = {"2": "/api/v2", "3": "/api/v3"}
    transport.get_manager_state.return_value = {"managerState": "Idle"}
    return transport


def _fake_open_service(transport: MagicMock) -> Callable[..., Any]:
    def opener(host: str, port: int, *, owner: str) -> Any:
        return core_composition.open_service(host, port, owner=owner, transport=transport)
    return opener


class TestRegistration(unittest.TestCase):
    def test_tool_type_stack_is_24(self) -> None:
        self.assertEqual(controller_pb2.ToolType.Value("stack"), 24)  # type: ignore[attr-defined]

    def test_command_oneof_registration(self) -> None:
        field = tool_base_pb2.Command.DESCRIPTOR.fields_by_name["stack"]
        self.assertEqual(field.number, 24)
        self.assertEqual(field.containing_oneof.name, "tool_command")

    def test_config_oneof_registration(self) -> None:
        field = tool_base_pb2.Config.DESCRIPTOR.fields_by_name["stack"]
        self.assertEqual(field.number, 43)
        self.assertEqual(field.containing_oneof.name, "config")

    def test_server_tool_type(self) -> None:
        self.assertEqual(StackServer.toolType, "stack")


_STRING = FieldDescriptor.TYPE_STRING
_DOUBLE = FieldDescriptor.TYPE_DOUBLE
_BOOL = FieldDescriptor.TYPE_BOOL

_COMMAND_ONEOF = [
    ("transfer", 1),
    ("get_manager_state", 2),
    ("get_robot_states", 3),
    ("list_devices", 4),
    ("list_labware_profiles", 5),
    ("list_transfer_profiles", 6),
    ("get_labware_presence", 7),
    ("get_transfer_estimate", 8),
    ("acknowledge_failure", 9),
    ("get_failure_latch", 10),
]

_LOCATION_FIELDS = [
    ("robot", _STRING),
    ("labware_profile", _STRING),
    ("source_device", _STRING),
    ("source_deck", _STRING),
    ("source_nest", _STRING),
    ("source_transfer_profile", _STRING),
    ("destination_device", _STRING),
    ("destination_deck", _STRING),
    ("destination_nest", _STRING),
    ("destination_transfer_profile", _STRING),
]

_NESTED_SHAPES: dict[str, list[tuple[str, int]]] = {
    "Transfer": [("step_key", _STRING)] + _LOCATION_FIELDS[:] + [("timeout_s", _DOUBLE)],
    "GetManagerState": [],
    "GetRobotStates": [],
    "ListDevices": [("refresh", _BOOL)],
    "ListLabwareProfiles": [("refresh", _BOOL)],
    "ListTransferProfiles": [("refresh", _BOOL)],
    "GetLabwarePresence": [("robot", _STRING)],
    "GetTransferEstimate": _LOCATION_FIELDS[:],
    "AcknowledgeFailure": [("guid", _STRING), ("arm_inspected", _STRING)],
    "GetFailureLatch": [],
}


class TestProtoFreeze(unittest.TestCase):
    """One-way door (D-01..D-05): the published v2 field list is pinned."""

    def test_package_name(self) -> None:
        self.assertEqual(
            stack_pb2.DESCRIPTOR.package,
            "com.science.foundry.tools.grpc_interfaces.stack")

    def test_command_oneof_is_the_d01_list(self) -> None:
        oneof = stack_pb2.Command.DESCRIPTOR.oneofs_by_name["command"]
        self.assertEqual([(f.name, f.number) for f in oneof.fields], _COMMAND_ONEOF)
        self.assertEqual(len(stack_pb2.Command.DESCRIPTOR.fields), len(_COMMAND_ONEOF))

    def test_nested_message_shapes(self) -> None:
        nested = stack_pb2.Command.DESCRIPTOR.nested_types_by_name
        self.assertEqual(sorted(nested), sorted(_NESTED_SHAPES))
        for name, shape in _NESTED_SHAPES.items():
            fields = nested[name].fields
            self.assertEqual(
                [(f.name, f.number, f.type) for f in fields],
                [(fname, i + 1, ftype) for i, (fname, ftype) in enumerate(shape)],
                name)

    def test_every_command_field_has_presence(self) -> None:
        for message in stack_pb2.Command.DESCRIPTOR.nested_types:
            for f in message.fields:
                self.assertTrue(f.has_presence, f"{message.name}.{f.name}")

    def test_config_fields(self) -> None:
        fields = stack_pb2.Config.DESCRIPTOR.fields
        self.assertEqual(
            [(f.name, f.number) for f in fields],
            [("host", 1), ("port", 2), ("transfer_timeout_s", 3), ("ledger_dir", 4)])
        for f in fields:
            self.assertFalse(f.has_presence, f.name)
            for banned in ("lock_dir", "user", "password", "token"):
                self.assertNotIn(banned, f.name)

    def test_no_reserved_or_estimate_messages(self) -> None:
        for name in stack_pb2.Command.DESCRIPTOR.nested_types_by_name:
            self.assertNotIn(name, ("GetStatus", "EstimateDuration", "Configure", "ExecuteCommand"))
            self.assertFalse(name.startswith("Estimate"), name)

    def test_presence_of_empty_string(self) -> None:
        msg = stack_pb2.Command.GetLabwarePresence(robot="")
        self.assertTrue(msg.HasField("robot"))
        self.assertFalse(stack_pb2.Command.GetLabwarePresence().HasField("robot"))


class TestTracerManagerStateOverGrpc(_StackTestCase):
    def _configure(self, stub: ToolDriverStub, port: int) -> Any:
        return stub.Configure(tool_base_pb2.Config(
            simulated=False, toolId="stack-test",
            stack=stack_pb2.Config(host="127.0.0.1", port=port)))

    def _get_manager_state(self, stub: ToolDriverStub) -> Any:
        return stub.ExecuteCommand(tool_base_pb2.Command(
            stack=stack_pb2.Command(get_manager_state=stack_pb2.Command.GetManagerState())))

    def test_configure_then_get_manager_state_succeeds(self) -> None:
        transport = _fake_transport()
        port = _free_tcp_port()
        with patch("tools.stack.server.open_service", _fake_open_service(transport)):
            stub = _serve_in_process(self, StackServer())
            self.assertEqual(self._configure(stub, port).response, SUCCESS)
            reply = self._get_manager_state(stub)
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(reply.error_message, "")
        self.assertEqual(reply.meta_data["kind"], "managerState")
        self.assertEqual(reply.meta_data["mode"], "Idle")
        transport.get_manager_state.assert_called_once()

        with self.assertRaises(StackOwnedError) as ctx:
            acquire_owner_lock("127.0.0.1", port, owner="mcp", lock_dir=self.lock_dir)
        self.assertEqual(ctx.exception.holder.owner, "galago")
        self.assertEqual(ctx.exception.holder.pid, os.getpid())

    def test_read_failed_is_never_success(self) -> None:
        transport = _fake_transport()
        transport.get_manager_state.side_effect = RuntimeError("boom")
        with patch("tools.stack.server.open_service", _fake_open_service(transport)):
            stub = _serve_in_process(self, StackServer())
            self.assertEqual(self._configure(stub, _free_tcp_port()).response, SUCCESS)
            reply = self._get_manager_state(stub)
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertTrue(reply.error_message.startswith("stack: readFailed"), reply.error_message)
        self.assertNotIn("\n", reply.error_message)


def _real_config(host: str, port: int, **kwargs: Any) -> tool_base_pb2.Config:
    return tool_base_pb2.Config(
        simulated=False, toolId="stack-test",
        stack=stack_pb2.Config(host=host, port=port, **kwargs))


class TestStackOwned(_StackTestCase):
    """STK-02: an owner lock held by another front end (stack-mcp) fails
    Configure once, names the holder, and is left untouched."""

    def test_mcp_holder_fails_configure_naming_the_holder(self) -> None:
        port = _free_tcp_port()
        held = acquire_owner_lock("127.0.0.1", port, owner="mcp", lock_dir=self.lock_dir)
        self.addCleanup(held.release)
        server = StackServer()
        stub = _serve_in_process(self, server)
        with patch.object(core_composition, "RestStackClient") as rest_client:
            reply = stub.Configure(_real_config("127.0.0.1", port))
        self.assertEqual(reply.response, NOT_READY)
        self.assertIn("already owned by mcp", reply.error_message)
        self.assertEqual(stub.GetStatus(empty_pb2.Empty()).status, FAILED)
        self.assertIsNone(server.service)
        self.assertIsNone(server._owned)
        rest_client.assert_not_called()
        with self.assertRaises(StackOwnedError) as ctx:
            acquire_owner_lock("127.0.0.1", port, owner="mcp", lock_dir=self.lock_dir)
        self.assertEqual(ctx.exception.holder.owner, "mcp")


class TestConfigureOwnership(_StackTestCase):
    def _patched_open(self) -> MagicMock:
        return MagicMock(side_effect=_fake_open_service(_fake_transport()))

    def _assert_free(self, port: int) -> None:
        # acquire succeeds only when nobody holds the endpoint.
        acquire_owner_lock(
            "127.0.0.1", port, owner="mcp", lock_dir=self.lock_dir).release()

    def test_first_configure_holds_the_lock_as_galago(self) -> None:
        port = _free_tcp_port()
        with patch("tools.stack.server.open_service", self._patched_open()):
            stub = _serve_in_process(self, StackServer())
            self.assertEqual(stub.Configure(_real_config("127.0.0.1", port)).response, SUCCESS)
        with self.assertRaises(StackOwnedError) as ctx:
            acquire_owner_lock("127.0.0.1", port, owner="mcp", lock_dir=self.lock_dir)
        self.assertEqual(ctx.exception.holder.owner, "galago")
        self.assertEqual(ctx.exception.holder.pid, os.getpid())

    def test_same_endpoint_reconfigure_reuses_the_session(self) -> None:
        port = _free_tcp_port()
        opener = self._patched_open()
        with patch("tools.stack.server.open_service", opener):
            server = StackServer()
            stub = _serve_in_process(self, server)
            self.assertEqual(stub.Configure(_real_config("127.0.0.1", port)).response, SUCCESS)
            first = server.service
            for host in ("127.0.0.1", "  127.0.0.1  "):
                with self.subTest(host=host):
                    reply = stub.Configure(_real_config(host, port))
                    self.assertEqual(reply.response, SUCCESS)
                    self.assertEqual(opener.call_count, 1)
                    self.assertIs(server.service, first)

    def test_case_variants_of_a_hostname_reuse_the_session(self) -> None:
        port = _free_tcp_port()
        opener = self._patched_open()
        with patch("tools.stack.server.open_service", opener):
            server = StackServer()
            stub = _serve_in_process(self, server)
            self.assertEqual(stub.Configure(_real_config("localhost", port)).response, SUCCESS)
            first = server.service
            self.assertEqual(stub.Configure(_real_config("LOCALHOST", port)).response, SUCCESS)
            self.assertEqual(opener.call_count, 1)
            self.assertIs(server.service, first)

    def test_moving_endpoints_closes_the_old_lock_first(self) -> None:
        port_a, port_b, port_c = _free_tcp_port(), _free_tcp_port(), _free_tcp_port()
        while port_b == port_a:
            port_b = _free_tcp_port()
        while port_c in (port_a, port_b):
            port_c = _free_tcp_port()
        fake_open = _fake_open_service(_fake_transport())
        seen_free: list[bool] = []

        def opener(host: str, port: int, *, owner: str) -> Any:
            if port == port_b:
                # Proves endpoint A was already released when B is opened.
                self._assert_free(port_a)
                seen_free.append(True)
            return fake_open(host, port, owner=owner)

        with patch("tools.stack.server.open_service", MagicMock(side_effect=opener)):
            server = StackServer()
            stub = _serve_in_process(self, server)
            self.assertEqual(stub.Configure(_real_config("127.0.0.1", port_a)).response, SUCCESS)
            self.assertEqual(stub.Configure(_real_config("127.0.0.1", port_b)).response, SUCCESS)
            self.assertEqual(seen_free, [True])
            self._assert_free(port_a)
            with self.assertRaises(StackOwnedError) as ctx:
                acquire_owner_lock("127.0.0.1", port_b, owner="mcp", lock_dir=self.lock_dir)
            self.assertEqual(ctx.exception.holder.owner, "galago")

        # The real open_service against a port another front end owns.
        held = acquire_owner_lock("127.0.0.1", port_c, owner="mcp", lock_dir=self.lock_dir)
        self.addCleanup(held.release)
        with patch.object(core_composition, "RestStackClient"):
            reply = stub.Configure(_real_config("127.0.0.1", port_c))
        self.assertEqual(reply.response, NOT_READY)
        self.assertIn("already owned by mcp", reply.error_message)
        self._assert_free(port_b)
        self.assertIsNone(server.service)
        self.assertIsNone(server._owned)


class TestConfigureFails(_StackTestCase):
    """D-04/D-08: every Configure failure is NOT_READY carrying the core's own
    text, and no failure leaves an owner lock behind."""

    def _assert_free(self, port: int) -> None:
        acquire_owner_lock(
            "127.0.0.1", port, owner="mcp", lock_dir=self.lock_dir).release()

    def test_bad_transfer_timeout_fails_before_open(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf"), -1.0):
            with self.subTest(value=value):
                opener = MagicMock()
                with patch("tools.stack.server.open_service", opener):
                    stub = _serve_in_process(self, StackServer())
                    reply = stub.Configure(
                        _real_config("127.0.0.1", _free_tcp_port(), transfer_timeout_s=value))
                self.assertEqual(reply.response, NOT_READY)
                self.assertIn("transfer_timeout_s", reply.error_message)
                opener.assert_not_called()

    def test_blank_host_fails_before_open(self) -> None:
        opener = MagicMock()
        with patch("tools.stack.server.open_service", opener):
            stub = _serve_in_process(self, StackServer())
            reply = stub.Configure(_real_config("   ", _free_tcp_port()))
        self.assertEqual(reply.response, NOT_READY)
        self.assertIn("Config.host is required", reply.error_message)
        opener.assert_not_called()

    def test_closed_port_is_a_transport_error_and_releases_the_lock(self) -> None:
        port = _free_tcp_port()
        server = StackServer()
        stub = _serve_in_process(self, server)
        reply = stub.Configure(_real_config("127.0.0.1", port))
        self.assertEqual(reply.response, NOT_READY)
        self.assertIn("transport error", reply.error_message)
        self.assertEqual(stub.GetStatus(empty_pb2.Empty()).status, FAILED)
        self.assertIsNone(server.service)
        self.assertIsNone(server._owned)
        self._assert_free(port)

    def test_missing_credentials_fail_with_the_core_text(self) -> None:
        os.environ.pop("STACK_USER", None)
        os.environ.pop("STACK_PASSWORD", None)
        port = _free_tcp_port()
        stub = _serve_in_process(self, StackServer())
        reply = stub.Configure(_real_config("127.0.0.1", port))
        self.assertEqual(reply.response, NOT_READY)
        self.assertIn("STACK credentials missing", reply.error_message)
        self._assert_free(port)

    def test_password_never_appears_in_replies_or_logs(self) -> None:
        sentinel = "s3ntinel-p4ssw0rd-do-not-leak"
        os.environ["STACK_PASSWORD"] = sentinel
        with self.assertLogs(level="DEBUG") as logs:
            stub = _serve_in_process(self, StackServer())
            closed = stub.Configure(_real_config("127.0.0.1", _free_tcp_port()))
            with patch("tools.stack.server.open_service",
                       _fake_open_service(_fake_transport())):
                ok = stub.Configure(_real_config("127.0.0.1", _free_tcp_port()))
        self.assertEqual(closed.response, NOT_READY)
        self.assertEqual(ok.response, SUCCESS)
        self.assertNotIn(sentinel, closed.error_message)
        self.assertNotIn(sentinel, ok.error_message)
        for record in logs.records:
            self.assertNotIn(sentinel, record.getMessage())
            self.assertNotIn(sentinel, str(record.args))


class TestConfigureWarning(_StackTestCase):
    """D-09: a fresh open warns once that a restart clears the core's latch."""

    def test_fresh_open_warns_once_and_reuse_is_silent(self) -> None:
        port = _free_tcp_port()
        with patch("tools.stack.server.open_service",
                   MagicMock(side_effect=_fake_open_service(_fake_transport()))):
            stub = _serve_in_process(self, StackServer())
            with self.assertLogs(level="WARNING") as logs:
                self.assertEqual(stub.Configure(_real_config("127.0.0.1", port)).response, SUCCESS)
            self.assertEqual(len(logs.records), 1)
            text = logs.records[0].getMessage()
            for fragment in ("restart", "failure latch", "acknowledge"):
                self.assertIn(fragment, text)
            with self.assertNoLogs(level="WARNING"):
                self.assertEqual(stub.Configure(_real_config("127.0.0.1", port)).response, SUCCESS)


class TestConfigureLedgerDir(_StackTestCase):
    def test_ledger_dir_is_recorded_but_never_created(self) -> None:
        ledger = os.path.join(self.lock_dir, "ledger-not-created")
        server = StackServer()
        with patch("tools.stack.server.open_service",
                   MagicMock(side_effect=_fake_open_service(_fake_transport()))):
            stub = _serve_in_process(self, server)
            reply = stub.Configure(_real_config("127.0.0.1", _free_tcp_port(), ledger_dir=ledger))
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(server._ledger_dir, ledger)
        self.assertFalse(os.path.exists(ledger))

    def test_port_zero_means_5005(self) -> None:
        opener = MagicMock(side_effect=_fake_open_service(_fake_transport()))
        with patch("tools.stack.server.open_service", opener):
            stub = _serve_in_process(self, StackServer())
            self.assertEqual(stub.Configure(_real_config("127.0.0.1", 0)).response, SUCCESS)
        self.assertEqual(opener.call_args.args, ("127.0.0.1", 5005))

    def test_transfer_timeout_is_recorded(self) -> None:
        for value in (0.0, 600.0):
            with self.subTest(value=value):
                server = StackServer()
                with patch("tools.stack.server.open_service",
                           MagicMock(side_effect=_fake_open_service(_fake_transport()))):
                    stub = _serve_in_process(self, server)
                    reply = stub.Configure(
                        _real_config("127.0.0.1", _free_tcp_port(), transfer_timeout_s=value))
                self.assertEqual(reply.response, SUCCESS)
                self.assertEqual(server._transfer_timeout_s, value)


_PINNED_CORE_SHA = "ed8ce478d8881a517eb93ed233707f81aea01238"


class TestRequirementsPin(unittest.TestCase):
    """D-22: one direct git reference at a 40-hex SHA, no [mcp] extra, and the
    installed core is exactly that commit."""

    def test_requirements_txt_pins_exactly_one_credential_free_sha(self) -> None:
        req_path = _REPO_ROOT / "tools" / "stack" / "requirements.txt"
        lines = [
            line.strip() for line in req_path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self.assertEqual(len(lines), 1)
        # The anchored pattern also rules out an [mcp] extra.
        self.assertRegex(
            lines[0],
            r"^stack-automation-layer @ git\+https://gitlab\.formulatrix\.com/"
            r"nikkopg/stack-automation-layer\.git@[0-9a-f]{40}$")
        self.assertEqual(lines[0].rsplit("@", 1)[1], _PINNED_CORE_SHA)

    def test_installed_core_is_the_pinned_commit(self) -> None:
        direct_url = json.loads(
            importlib.metadata.distribution("stack_automation_layer").read_text(
                "direct_url.json") or "{}")
        self.assertEqual(direct_url["vcs_info"]["commit_id"], _PINNED_CORE_SHA)


_STACK_SOURCES = sorted((_REPO_ROOT / "tools" / "stack").glob("*.py"))

# D-20: no adapter code may reach any core motion, cancel, safe-position,
# validate or acknowledge method (any receiver).
_FORBIDDEN_SERVICE_CALLS = frozenset({
    "plan_transfer", "execute_transfer", "start_transfer", "wait",
    "wait_transfer", "cancel_transfer", "go_to_safe_position",
    "wait_safe_position", "acknowledge_failure", "validate_transfer",
})
# The core is reached only through open_service (never built by hand here).
_FORBIDDEN_CONSTRUCTORS = frozenset({
    "StackService", "RestStackClient", "StackJwtAuth", "Credentials",
    "acquire_owner_lock",
})
_MCP_MODULE = "stack_automation_layer.mcp"
# The core MCP subpackage, the hardware STACK manager address and the
# stack-server host must never appear in adapter code (hard constraints).
_FORBIDDEN_LITERALS = (_MCP_MODULE, "10.150.1.125", "stack-server")
_REQUIRED_FUNCTIONS = ("_configure", "_result_reply", "GetManagerState")


def _name_of(func: ast.expr) -> Optional[str]:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _stack_adapter_violations(trees: dict[str, ast.Module]) -> list[str]:
    """Pure, assertion-free no-motion / no-MCP / open_service-shape checks
    (D-20, D-21) over every tools/stack module. Returns "<file>:<line>:
    <reason>" strings, or [] when clean. Never raises, so planted copies can
    be checked without failing the test that plants them."""
    violations: list[str] = []
    open_service_calls = 0
    defined: set[str] = set()

    for fname, tree in sorted(trees.items()):
        for node in ast.walk(tree):
            at = f"{fname}:{getattr(node, 'lineno', 0)}"
            if isinstance(node, ast.FunctionDef):
                defined.add(node.name)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == _MCP_MODULE or alias.name.startswith(_MCP_MODULE + "."):
                        violations.append(f"{at}: import of the core MCP subpackage {alias.name}")
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == _MCP_MODULE or module.startswith(_MCP_MODULE + "."):
                    violations.append(f"{at}: import from the core MCP subpackage {module}")
                if module == "stack_automation_layer" and any(
                        alias.name == "mcp" for alias in node.names):
                    violations.append(f"{at}: import of the core MCP subpackage (from-import mcp)")
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for literal in _FORBIDDEN_LITERALS:
                    if literal in node.value:
                        violations.append(f"{at}: string constant contains {literal!r}")
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = _name_of(func)
            if isinstance(func, ast.Attribute) and func.attr in _FORBIDDEN_SERVICE_CALLS:
                violations.append(f"{at}: forbidden core call .{func.attr}()")
            if name in _FORBIDDEN_CONSTRUCTORS or (
                    isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                    and func.value.id in _FORBIDDEN_CONSTRUCTORS):
                violations.append(f"{at}: direct use of core constructor/helper {ast.unparse(func)}")
            if name == "open_service":
                open_service_calls += 1
                owner = next((k for k in node.keywords if k.arg == "owner"), None)
                if not (owner is not None and isinstance(owner.value, ast.Constant)
                        and owner.value.value == "galago"):
                    violations.append(f'{at}: open_service must pass owner="galago"')
                for keyword in node.keywords:
                    if keyword.arg is None:
                        violations.append(f"{at}: open_service must not take ** keywords")
                    elif keyword.arg in ("lock_dir", "transport"):
                        violations.append(f"{at}: open_service must not pass {keyword.arg}=")

    if open_service_calls == 0:
        violations.append("tools/stack: open_service is never called")
    for required in _REQUIRED_FUNCTIONS:
        if required not in defined:
            violations.append(f"tools/stack: {required}() is missing from the sources")
    return violations


def _plant(tree: ast.Module, function: Optional[str], statement: str) -> ast.Module:
    """Deep copy of `tree` with `statement` inserted at module top (function
    is None) or as the first statement of the FunctionDef `function` (after
    its docstring). Proves each rule depends on the code it checks."""
    planted = copy.deepcopy(tree)
    new_statements = ast.parse(statement).body
    if function is None:
        planted.body = new_statements + planted.body
    else:
        target: Optional[ast.FunctionDef] = None
        for node in ast.walk(planted):
            if isinstance(node, ast.FunctionDef) and node.name == function:
                target = node
                break
        if target is None:
            raise ValueError(f"no such function: {function}")
        insert_at = 0
        if (target.body and isinstance(target.body[0], ast.Expr)
                and isinstance(target.body[0].value, ast.Constant)
                and isinstance(target.body[0].value.value, str)):
            insert_at = 1
        target.body[insert_at:insert_at] = new_statements
    ast.fix_missing_locations(planted)
    return planted


class TestAdapterInvariant(unittest.TestCase):
    """STK-05 safety half: nothing under tools/stack/ can move the arm, clear
    a latch, import the MCP surface or open the core other than as galago."""

    def setUp(self) -> None:
        self.trees = {path.name: ast.parse(path.read_text()) for path in _STACK_SOURCES}
        self.server = self.trees["server.py"]

    def _with(self, tree: ast.Module) -> dict[str, ast.Module]:
        trees = dict(self.trees)
        trees["server.py"] = tree
        return trees

    def _assert_reported(self, tree: ast.Module, fragment: str) -> None:
        violations = _stack_adapter_violations(self._with(tree))
        self.assertTrue(violations, "expected a violation")
        self.assertTrue(any(fragment in v for v in violations), f"{fragment!r} not in {violations}")

    def test_real_sources_are_clean(self) -> None:
        self.assertIn("server.py", self.trees)
        self.assertEqual(_stack_adapter_violations(self.trees), [])

    def test_every_forbidden_service_call_is_reported(self) -> None:
        self.assertEqual(len(_FORBIDDEN_SERVICE_CALLS), 10)
        for name in sorted(_FORBIDDEN_SERVICE_CALLS):
            with self.subTest(name=name):
                self._assert_reported(
                    _plant(self.server, "GetManagerState", f"self.service.{name}()"), f".{name}()")

    def test_module_level_forbidden_call_is_reported(self) -> None:
        self._assert_reported(_plant(self.server, None, "service.wait(None)"), ".wait()")

    def test_mcp_imports_are_reported(self) -> None:
        for statement in (
            "from stack_automation_layer.mcp import server",
            "import stack_automation_layer.mcp.server",
            "from stack_automation_layer import mcp",
        ):
            with self.subTest(statement=statement):
                self._assert_reported(_plant(self.server, None, statement), "MCP subpackage")

    def test_open_service_shape_is_enforced(self) -> None:
        for statement, fragment in (
            ('open_service("h", 1, owner="galago", lock_dir="/x")', "lock_dir"),
            ('open_service("h", 1, owner="galago", transport=None)', "transport"),
            ('open_service("h", 1, owner="galago", **{})', "** keywords"),
            ('open_service("h", 1, owner="mcp")', 'owner="galago"'),
            ('open_service("h", 1)', 'owner="galago"'),
        ):
            with self.subTest(statement=statement):
                self._assert_reported(_plant(self.server, "_configure", statement), fragment)

    def test_open_service_must_be_called_somewhere(self) -> None:
        tree = copy.deepcopy(self.server)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _name_of(node.func) == "open_service":
                node.func = ast.Name(id="something_else", ctx=ast.Load())
        self._assert_reported(tree, "open_service is never called")

    def test_core_constructors_are_reported(self) -> None:
        for statement in (
            "StackService(None)",
            "Credentials.from_env()",
            'acquire_owner_lock("h", 1, owner="galago")',
            'RestStackClient("http://h")',
            "StackJwtAuth(None)",
        ):
            with self.subTest(statement=statement):
                self._assert_reported(
                    _plant(self.server, "_configure", statement), "core constructor")

    def test_forbidden_literals_are_reported(self) -> None:
        for literal in _FORBIDDEN_LITERALS:
            with self.subTest(literal=literal):
                self._assert_reported(
                    _plant(self.server, None, f"_X = {literal!r}"), repr(literal))

    def test_renaming_a_required_function_is_reported(self) -> None:
        for required in _REQUIRED_FUNCTIONS:
            with self.subTest(required=required):
                tree = copy.deepcopy(self.server)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name == required:
                        node.name = required + "_renamed"
                self._assert_reported(tree, f"{required}() is missing")

    def test_allowed_read_calls_are_not_reported(self) -> None:
        for statement in (
            "self.service.manager_state()",
            "self.service.estimate_transfer(None)",
            "self.service.labware_presence(None)",
        ):
            with self.subTest(statement=statement):
                planted = _plant(self.server, "GetManagerState", statement)
                self.assertEqual(_stack_adapter_violations(self._with(planted)), [])


def _struct(d: dict) -> Struct:
    s = Struct()
    s.update(d)
    return s


class _RealModeGrpcTestCase(_StackTestCase):
    """Shared real-mode in-process gRPC fixture: a StackServer with a
    MagicMock(spec=StackService) injected directly (no open_service, no lock,
    no network) and a real gRPC server/stub pair. Declares no tests."""

    def setUp(self) -> None:
        super().setUp()
        self.server = StackServer()
        self.service = MagicMock(spec=StackService)
        self.server.service = self.service
        self.server.config = stack_pb2.Config(host="127.0.0.1")
        self.server.status = READY
        self.stub = _serve_in_process(self, self.server)

    def _stack(self, **command: Any) -> tool_base_pb2.Command:
        return tool_base_pb2.Command(stack=stack_pb2.Command(**command))

    def _health(self) -> tool_base_pb2.StatusReply:
        return self.stub.GetStatus(empty_pb2.Empty())  # type: ignore[no-any-return]


_ESTIMATE_FIELDS = {
    "robot": "R1",
    "labware_profile": "plate96",
    "source_device": "SD",
    "source_deck": "SK",
    "source_nest": "SN",
    "source_transfer_profile": "STP",
    "destination_device": "DD",
    "destination_deck": "DK",
    "destination_nest": "DN",
    "destination_transfer_profile": "DTP",
}


class TestTransferEstimate(_RealModeGrpcTestCase):
    """STK-04: GetTransferEstimate -> estimate_transfer, once, nothing else."""

    def _estimate(self, **fields: Any) -> Any:
        return self.stub.ExecuteCommand(self._stack(
            get_transfer_estimate=stack_pb2.Command.GetTransferEstimate(**fields)))

    def test_all_fields_reach_estimate_transfer_once_and_nothing_else(self) -> None:
        self.service.estimate_transfer.return_value = Estimated(
            estimated_time="00:00:48", guid=None, advisories=[], seconds=48.0)
        self._estimate(**_ESTIMATE_FIELDS)
        self.service.estimate_transfer.assert_called_once_with(TransferRequest(
            robot="R1", labware_profile="plate96",
            source=Location(device="SD", deck="SK", nest="SN", transfer_profile="STP"),
            destination=Location(device="DD", deck="DK", nest="DN", transfer_profile="DTP")))
        self.assertEqual(len(self.service.mock_calls), 1)

    def test_unset_empty_and_blank_fields_become_none(self) -> None:
        self.service.estimate_transfer.return_value = NeedsInput(missing=["robot"])
        for label, fields in (
            ("unset", {}),
            ("empty", {name: "" for name in _ESTIMATE_FIELDS}),
            ("blank", {name: "   " for name in _ESTIMATE_FIELDS}),
        ):
            with self.subTest(label):
                self.service.reset_mock()
                self._estimate(**fields)
                self.service.estimate_transfer.assert_called_once_with(TransferRequest(
                    robot=None, labware_profile=None,
                    source=Location(None, None, None, None),
                    destination=Location(None, None, None, None)))
                self.assertEqual(len(self.service.mock_calls), 1)

    def test_a_non_blank_value_passes_unchanged(self) -> None:
        self.service.estimate_transfer.return_value = NeedsInput(missing=[])
        self._estimate(robot="  R1  ")
        request = self.service.estimate_transfer.call_args.args[0]
        self.assertEqual(request.robot, "  R1  ")

    def test_estimated_is_success_with_empty_message_and_core_meta(self) -> None:
        result = Estimated(estimated_time="00:00:48", guid=None, advisories=[], seconds=48.0)
        self.service.estimate_transfer.return_value = result
        reply = self._estimate(**_ESTIMATE_FIELDS)
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(reply.error_message, "")
        self.assertEqual(reply.meta_data, _struct(result.to_dict()))
        self.assertEqual(self._health().status, READY)

    def test_needs_input_rejected_and_read_failed_are_never_success(self) -> None:
        cases = (
            ("needsInput", NeedsInput(missing=["robot", "source"])),
            ("rejected", Rejected(stage="local", findings=[{"name": "unknownNest"}])),
            ("readFailed", ReadFailed(error={"status": None, "name": "ConnectError"})),
        )
        for kind, result in cases:
            with self.subTest(kind):
                self.service.estimate_transfer.return_value = result
                reply = self._estimate(**_ESTIMATE_FIELDS)
                self.assertEqual(reply.response, ERROR_FROM_TOOL)
                self.assertTrue(reply.error_message.startswith(f"stack: {kind}"),
                                reply.error_message)
                self.assertEqual(self._health().status, READY)

    def test_all_blank_request_is_judged_by_the_core_not_the_adapter(self) -> None:
        self.service.estimate_transfer.return_value = NeedsInput(
            missing=["robot", "labwareProfile"])
        reply = self._estimate()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertEqual(self.service.estimate_transfer.call_count, 1)


if __name__ == "__main__":
    unittest.main()
