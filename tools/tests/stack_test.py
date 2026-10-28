"""Tests for the STACK tool adapter (tools/stack/server.py).

Hermetic by construction: every _StackTestCase uses a temp owner-lock
directory, explicit fake credentials, no proxy environment, and a guard that
fails any socket connect to a non-loopback address.
"""
import os
import socket
import tempfile
import unittest
from concurrent import futures
from typing import Any, Callable
from unittest.mock import MagicMock, patch

import grpc
from google.protobuf import empty_pb2
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
    from stack_automation_layer.results import ReadFailed  # noqa: F401
    from stack_automation_layer.service import StackService  # noqa: F401

    from tools.stack.server import StackServer
except ModuleNotFoundError as exc:
    if exc.name and exc.name.split(".")[0] in ("stack_automation_layer", "httpx"):
        raise unittest.SkipTest(
            "stack_automation_layer core is not installed (private GitLab dependency, see "
            "tools/stack/requirements.txt); the local Python 3.10 bin/make test run "
            "is the authoritative gate") from exc
    raise

from tools.grpc_interfaces import controller_pb2, stack_pb2, tool_base_pb2
from tools.grpc_interfaces.tool_base_pb2 import ERROR_FROM_TOOL, FAILED, NOT_READY, SUCCESS
from tools.grpc_interfaces.tool_driver_pb2_grpc import (
    ToolDriverStub,
    add_ToolDriverServicer_to_server,
)

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


if __name__ == "__main__":
    unittest.main()
