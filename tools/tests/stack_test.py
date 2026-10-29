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
import stat
import tempfile
import threading
import time
import types
import unittest
from concurrent import futures
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from unittest.mock import MagicMock, call as mock_call, patch

import grpc
from google.protobuf import empty_pb2
from google.protobuf.json_format import MessageToDict
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
    from stack_automation_layer.knowledge import LabwareProfile, TransferProfile
    from stack_automation_layer.model import Location, TransferRequest
    from stack_automation_layer.results import (
        Aborted,
        Cancelled,
        CancelRequested,
        DeviceTree,
        Estimated,
        Failed,
        FailureAcknowledged,
        KnowledgeRefreshed,
        LabwarePresence,
        LabwareProfiles,
        LatchStatus,
        Lost,
        ManagerState,
        NeedsInput,
        Ran,
        ReadFailed,
        Refused,
        Rejected,
        RobotStates,
        TaskHandle,
        TaskSnapshot,
        TimedOut,
        TransferPlan,
        TransferProfiles,
        TransferSummary,
        ValidationReport,
    )
    from stack_automation_layer.service import StackService

    from tools.stack import server as stack_server
    from tools.stack.server import READ_COMMANDS, StackServer, _result_reply
except ModuleNotFoundError as exc:
    if exc.name and exc.name.split(".")[0] in ("stack_automation_layer", "httpx"):
        raise unittest.SkipTest(
            "stack_automation_layer core is not installed (private GitLab dependency, see "
            "tools/stack/requirements.txt); the local Python 3.10 bin/make test run "
            "is the authoritative gate") from exc
    raise

from tools.grpc_interfaces import controller_pb2, fast_pb2, stack_pb2, tool_base_pb2
from tools.grpc_interfaces.tool_base_pb2 import (
    DRIVER_ERROR,
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
from tools.stack.ledger import Ledger, LedgerError, fingerprint

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
        # The core persists its failure latch per endpoint under STACK_STATE_DIR
        # (default ~/.local/state/stack-automation-layer, shared with stack-mcp);
        # tests must never read or write the real one.
        self.state_dir = os.path.join(self._tmpdir.name, "state")
        # The adapter's own step ledger defaults to $XDG_STATE_HOME/galago-tools/stack
        # (else ~/.local/state/...). Both are pointed at temp dirs so no test can
        # ever read or write the real ledger (T-05-07).
        self.xdg_state_home = os.path.join(self._tmpdir.name, "xdg-state")
        self.fake_home = os.path.join(self._tmpdir.name, "home")
        os.makedirs(self.fake_home)

        env_patcher = patch.dict(os.environ, {
            "STACK_MCP_LOCK_DIR": self.lock_dir,
            "STACK_STATE_DIR": self.state_dir,
            "XDG_STATE_HOME": self.xdg_state_home,
            "HOME": self.fake_home,
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


class TestConfigureHostValidation(_StackTestCase):
    """WR-05: the host is interpolated into a URL that receives the STACK
    credentials, so URL metacharacters are refused before any open. Real host
    forms are accepted; these strings are only ever handed to a mocked
    open_service, never connected to."""

    ACCEPTED = (
        "127.0.0.1", "localhost", "LOCALHOST", "stack-server", "stack_server",
        "stack.example.com", "10.150.1.125", "[::1]", "[fe80::1]", "  127.0.0.1  ",
    )
    REJECTED = (
        "good-host@attacker", "user:pw@host", "host/path", "host/", "host?x=",
        "host#frag", "host\\evil", "http://host", "https://host", "ho st",
        "host\tname", "host:80", "::1", "[::1", "[]", "[g::1]", "[::1]:80",
        "host\nname",
    )

    def test_bare_hosts_are_accepted(self) -> None:
        for host in self.ACCEPTED:
            with self.subTest(host=host):
                opener = MagicMock(side_effect=_fake_open_service(_fake_transport()))
                with patch("tools.stack.server.open_service", opener):
                    server = StackServer()
                    stub = _serve_in_process(self, server)
                    reply = stub.Configure(_real_config(host, _free_tcp_port()))
                self.assertEqual(reply.response, SUCCESS, reply.error_message)
                self.assertEqual(opener.call_count, 1)

    def test_url_metacharacters_are_refused_before_any_open(self) -> None:
        for host in self.REJECTED:
            with self.subTest(host=host):
                opener = MagicMock()
                with patch("tools.stack.server.open_service", opener):
                    server = StackServer()
                    stub = _serve_in_process(self, server)
                    reply = stub.Configure(_real_config(host, _free_tcp_port()))
                self.assertEqual(reply.response, NOT_READY)
                self.assertIn("Config.host must be a bare hostname", reply.error_message)
                self.assertEqual(stub.GetStatus(empty_pb2.Empty()).status, FAILED)
                self.assertIsNone(server.service)
                opener.assert_not_called()

    def test_port_outside_1_to_65535_is_refused_before_any_open(self) -> None:
        for port in (-1, 65536, 100000):
            with self.subTest(port=port):
                opener = MagicMock()
                with patch("tools.stack.server.open_service", opener):
                    stub = _serve_in_process(self, StackServer())
                    reply = stub.Configure(_real_config("127.0.0.1", port))
                self.assertEqual(reply.response, NOT_READY)
                self.assertIn("Config.port must be in 1..65535", reply.error_message)
                opener.assert_not_called()

    def test_port_zero_means_the_default_port(self) -> None:
        opener = MagicMock(side_effect=_fake_open_service(_fake_transport()))
        with patch("tools.stack.server.open_service", opener):
            stub = _serve_in_process(self, StackServer())
            reply = stub.Configure(_real_config("127.0.0.1", 0))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.assertEqual(opener.call_args.args[1], 5005)


class TestConfigureCloseFails(_StackTestCase):
    """WR-01: the core's OwnedService.close() marks itself closed before it
    closes the transport, so a raising close skips the lock release. The
    adapter must still end with no service and no lock held."""

    def _assert_free(self, port: int) -> None:
        acquire_owner_lock(
            "127.0.0.1", port, owner="mcp", lock_dir=self.lock_dir).release()

    def test_a_raising_close_leaves_no_service_and_no_lock(self) -> None:
        port_a, port_b = _free_tcp_port(), _free_tcp_port()
        while port_b == port_a:
            port_b = _free_tcp_port()
        opener = MagicMock(side_effect=_fake_open_service(_fake_transport()))
        with patch("tools.stack.server.open_service", opener):
            server = StackServer()
            stub = _serve_in_process(self, server)
            self.assertEqual(stub.Configure(_real_config("127.0.0.1", port_a)).response, SUCCESS)
            first = server.service
            assert server._owned is not None

            def _boom() -> None:
                raise RuntimeError("transport close failed")

            server._owned._stack.callback(_boom)

            reply = stub.Configure(_real_config("127.0.0.1", port_b))
            self.assertEqual(reply.response, NOT_READY)
            self.assertIn("transport close failed", reply.error_message)
            self.assertEqual(stub.GetStatus(empty_pb2.Empty()).status, FAILED)
            self.assertIsNone(server.service)
            self.assertIsNone(server._owned)
            self.assertEqual(opener.call_count, 1)
            # The old endpoint's lock was released despite the raise ...
            self._assert_free(port_a)
            # ... and a retry for the same endpoint opens a fresh session
            # instead of reusing the half-closed one.
            self.assertEqual(stub.Configure(_real_config("127.0.0.1", port_a)).response, SUCCESS)
            self.assertEqual(opener.call_count, 2)
            self.assertIsNotNone(server.service)
            self.assertIsNot(server.service, first)


class TestConfigureFailureDropsService(_StackTestCase):
    """WR-02: FAILED always implies no service. A Configure that fails
    validation must not leave the previous endpoint serving reads."""

    def _assert_free(self, port: int) -> None:
        acquire_owner_lock(
            "127.0.0.1", port, owner="mcp", lock_dir=self.lock_dir).release()

    def test_validation_failure_drops_the_previous_service(self) -> None:
        bad_configs = {
            "blank host": lambda port: _real_config("   ", port),
            "bad timeout": lambda port: _real_config(
                "127.0.0.1", port, transfer_timeout_s=float("nan")),
        }
        for label, make_config in bad_configs.items():
            with self.subTest(label):
                port = _free_tcp_port()
                transport = _fake_transport()
                with patch("tools.stack.server.open_service",
                           _fake_open_service(transport)):
                    server = StackServer()
                    stub = _serve_in_process(self, server)
                    self.assertEqual(
                        stub.Configure(_real_config("127.0.0.1", port)).response, SUCCESS)
                    ok = stub.ExecuteCommand(tool_base_pb2.Command(
                        stack=stack_pb2.Command(
                            get_manager_state=stack_pb2.Command.GetManagerState())))
                    self.assertEqual(ok.response, SUCCESS)

                    reply = stub.Configure(make_config(port))
                    self.assertEqual(reply.response, NOT_READY)
                    self.assertEqual(stub.GetStatus(empty_pb2.Empty()).status, FAILED)
                    self.assertIsNone(server.service)
                    self.assertIsNone(server._owned)
                    self._assert_free(port)
                    # The read bypass no longer answers from the old endpoint.
                    transport.get_manager_state.reset_mock()
                    read = stub.ExecuteCommand(tool_base_pb2.Command(
                        stack=stack_pb2.Command(
                            get_manager_state=stack_pb2.Command.GetManagerState())))
                    self.assertEqual(read.response, NOT_READY)
                    self.assertEqual(read.error_message, "stack: not configured")
                    transport.get_manager_state.assert_not_called()


class TestConfigureConcurrency(_StackTestCase):
    """WR-03: Configure is serialised against in-flight commands and against
    other Configures, and _owned/service always change together."""

    def _read(self, stub: ToolDriverStub) -> tool_base_pb2.ExecuteCommandReply:
        return stub.ExecuteCommand(tool_base_pb2.Command(  # type: ignore[no-any-return]
            stack=stack_pb2.Command(get_manager_state=stack_pb2.Command.GetManagerState())))

    def test_configure_waits_for_an_in_flight_read_before_closing(self) -> None:
        port_a, port_b = _free_tcp_port(), _free_tcp_port()
        while port_b == port_a:
            port_b = _free_tcp_port()
        transport = _fake_transport()
        entered, release = threading.Event(), threading.Event()
        closed_while_reading: list[bool] = []

        def _slow_read() -> dict[str, str]:
            entered.set()
            release.wait(timeout=10)
            # The transport must still be open: Configure has not closed it.
            closed_while_reading.append(server_owned_closed())
            return {"managerState": "Idle"}

        transport.get_manager_state.side_effect = _slow_read
        with patch("tools.stack.server.open_service", _fake_open_service(transport)):
            server = StackServer()

            def server_owned_closed() -> bool:
                assert server._owned is not None
                return bool(server._owned._closed)

            stub = _serve_in_process(self, server)
            self.assertEqual(stub.Configure(_real_config("127.0.0.1", port_a)).response, SUCCESS)

            results: dict[str, Any] = {}
            read_thread = threading.Thread(
                target=lambda: results.__setitem__("read", self._read(stub)))
            read_thread.start()
            self.addCleanup(read_thread.join, 10)
            self.addCleanup(release.set)
            self.assertTrue(entered.wait(timeout=5))

            configure_thread = threading.Thread(target=lambda: results.__setitem__(
                "configure", stub.Configure(_real_config("127.0.0.1", port_b))))
            configure_thread.start()
            self.addCleanup(configure_thread.join, 10)
            configure_thread.join(0.3)
            # Configure is parked behind the read; the old owner is untouched.
            self.assertTrue(configure_thread.is_alive())
            self.assertNotIn("configure", results)
            with self.assertRaises(StackOwnedError):
                acquire_owner_lock("127.0.0.1", port_a, owner="mcp", lock_dir=self.lock_dir)

            release.set()
            read_thread.join(10)
            configure_thread.join(10)
            self.assertEqual(results["read"].response, SUCCESS, results["read"].error_message)
            self.assertEqual(closed_while_reading, [False])
            self.assertEqual(results["configure"].response, SUCCESS)
            assert server._owned is not None
            self.assertEqual(server._owned.endpoint, f"127.0.0.1:{port_b}")
            self.assertIs(server.service, server._owned.service)

    def test_concurrent_configures_leave_one_consistent_owner_and_no_leak(self) -> None:
        ports = [_free_tcp_port(), _free_tcp_port()]
        while ports[1] == ports[0]:
            ports[1] = _free_tcp_port()
        fake_open = _fake_open_service(_fake_transport())

        def slow_open(host: str, port: int, *, owner: str) -> Any:
            time.sleep(0.2)  # widen the window so unserialised Configures overlap
            return fake_open(host, port, owner=owner)

        with patch("tools.stack.server.open_service", MagicMock(side_effect=slow_open)):
            server = StackServer()
            stub = _serve_in_process(self, server)
            replies: list[Any] = []
            threads = [
                threading.Thread(target=lambda p=p: replies.append(
                    stub.Configure(_real_config("127.0.0.1", p))))
                for p in ports
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(10)
        self.assertEqual([r.response for r in replies], [SUCCESS, SUCCESS])
        assert server._owned is not None
        self.assertIs(server.service, server._owned.service)
        final = int(server._owned.endpoint.rsplit(":", 1)[1])
        self.assertIn(final, ports)
        (other,) = [p for p in ports if p != final]
        # The Configure that lost the race closed its owner: no leaked lock.
        acquire_owner_lock("127.0.0.1", other, owner="mcp", lock_dir=self.lock_dir).release()
        with self.assertRaises(StackOwnedError):
            acquire_owner_lock("127.0.0.1", final, owner="mcp", lock_dir=self.lock_dir)


class TestConfigureBusy(_StackTestCase):
    """WR-01: Configure's drain of in-flight commands is bounded and refuses
    with "busy" without dropping a healthy owner; an unchanged endpoint never
    drains; the I/O-heavy open runs outside _state."""

    def _two_ports(self) -> tuple[int, int]:
        port_a, port_b = _free_tcp_port(), _free_tcp_port()
        while port_b == port_a:
            port_b = _free_tcp_port()
        return port_a, port_b

    def _read(self, stub: ToolDriverStub) -> tool_base_pb2.ExecuteCommandReply:
        return stub.ExecuteCommand(tool_base_pb2.Command(  # type: ignore[no-any-return]
            stack=stack_pb2.Command(get_manager_state=stack_pb2.Command.GetManagerState())))

    def _park_a_read(self, stub: ToolDriverStub, transport: MagicMock) -> dict[str, Any]:
        """Start a read that stays in flight until the returned release()."""
        entered, release = threading.Event(), threading.Event()
        results: dict[str, Any] = {}

        def _slow_read() -> dict[str, str]:
            entered.set()
            release.wait(timeout=10)
            return {"managerState": "Idle"}

        transport.get_manager_state.side_effect = _slow_read
        thread = threading.Thread(target=lambda: results.__setitem__("read", self._read(stub)))
        thread.start()
        self.addCleanup(thread.join, 10)
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(timeout=5))
        results["release"] = release
        results["thread"] = thread
        return results

    def test_busy_configure_refuses_and_keeps_the_healthy_owner(self) -> None:
        port_a, port_b = self._two_ports()
        transport = _fake_transport()
        opener = MagicMock(side_effect=_fake_open_service(transport))
        configs = {
            "new endpoint": _real_config("127.0.0.1", port_b),
            "malformed": _real_config("   ", port_a),
        }
        with patch("tools.stack.server.open_service", opener), \
                patch("tools.stack.server.CONFIGURE_DRAIN_TIMEOUT_S", 0.05):
            server = StackServer()
            stub = _serve_in_process(self, server)
            self.assertEqual(stub.Configure(_real_config("127.0.0.1", port_a)).response, SUCCESS)
            owned = server._owned
            assert owned is not None
            parked = self._park_a_read(stub, transport)
            for label, config in configs.items():
                with self.subTest(label):
                    reply = stub.Configure(config)
                    self.assertEqual(reply.response, NOT_READY)
                    self.assertIn("stack: busy", reply.error_message)
                    self.assertNotIn("\n", reply.error_message)
                    self.assertEqual(opener.call_count, 1)
                    # The healthy owner was neither closed nor dropped.
                    self.assertIs(server._owned, owned)
                    self.assertIs(server.service, owned.service)
                    self.assertFalse(owned._closed)
                    with self.assertRaises(StackOwnedError):
                        acquire_owner_lock(
                            "127.0.0.1", port_a, owner="mcp", lock_dir=self.lock_dir)
            parked["release"].set()
            parked["thread"].join(10)
            self.assertEqual(parked["read"].response, SUCCESS)
            # With nothing in flight the same Configure now goes through.
            transport.get_manager_state.side_effect = None
            self.assertEqual(stub.Configure(configs["new endpoint"]).response, SUCCESS)
            assert server._owned is not None
            self.assertEqual(server._owned.endpoint, f"127.0.0.1:{port_b}")
            self.assertTrue(owned._closed)

    def test_same_endpoint_configure_does_not_drain(self) -> None:
        port_a, _ = self._two_ports()
        transport = _fake_transport()
        opener = MagicMock(side_effect=_fake_open_service(transport))
        with patch("tools.stack.server.open_service", opener), \
                patch("tools.stack.server.CONFIGURE_DRAIN_TIMEOUT_S", 0.05):
            server = StackServer()
            stub = _serve_in_process(self, server)
            self.assertEqual(stub.Configure(_real_config("127.0.0.1", port_a)).response, SUCCESS)
            owned = server._owned
            parked = self._park_a_read(stub, transport)
            # A drain would time out as "busy"; an unchanged endpoint returns.
            reply = stub.Configure(_real_config("127.0.0.1", port_a))
            self.assertEqual(reply.response, SUCCESS, reply.error_message)
            self.assertEqual(opener.call_count, 1)
            self.assertIs(server._owned, owned)
            parked["release"].set()
            parked["thread"].join(10)

    def test_open_service_runs_without_holding_state(self) -> None:
        port_a, _ = self._two_ports()
        fake_open = _fake_open_service(_fake_transport())
        entered, release = threading.Event(), threading.Event()
        probe: list[bool] = []

        def blocking_open(host: str, port: int, *, owner: str) -> Any:
            entered.set()
            release.wait(timeout=10)
            return fake_open(host, port, owner=owner)

        with patch("tools.stack.server.open_service", blocking_open):
            server = StackServer()
            stub = _serve_in_process(self, server)
            results: dict[str, Any] = {}
            thread = threading.Thread(target=lambda: results.__setitem__(
                "configure", stub.Configure(_real_config("127.0.0.1", port_a))))
            thread.start()
            self.addCleanup(thread.join, 10)
            self.addCleanup(release.set)
            self.assertTrue(entered.wait(timeout=5))
            # Configure is inside open_service. _state must be free: a command
            # (or GetStatus) can take it without waiting for the network.
            got = server._state.acquire(blocking=False)
            probe.append(got)
            if got:
                server._state.release()
            self.assertEqual(probe, [True])
            release.set()
            thread.join(10)
        self.assertEqual(results["configure"].response, SUCCESS)


class TestReconfiguringAdmission(_StackTestCase):
    """WR-02: a command is never parked behind a Configure. Admission and the
    service snapshot are taken together; a command refused during a Configure
    says so at once, handlers use the service they were admitted against, and a
    stale READY cannot outlive a failed Configure."""

    def _two_ports(self) -> tuple[int, int]:
        port_a, port_b = _free_tcp_port(), _free_tcp_port()
        while port_b == port_a:
            port_b = _free_tcp_port()
        return port_a, port_b

    def _read(self, stub: ToolDriverStub, **kwargs: Any) -> tool_base_pb2.ExecuteCommandReply:
        return stub.ExecuteCommand(  # type: ignore[no-any-return]
            tool_base_pb2.Command(stack=stack_pb2.Command(
                get_manager_state=stack_pb2.Command.GetManagerState())), **kwargs)

    def test_commands_during_a_configure_are_refused_immediately(self) -> None:
        port_a, port_b = self._two_ports()
        fake_open = _fake_open_service(_fake_transport())
        entered, release = threading.Event(), threading.Event()

        def gated_open(host: str, port: int, *, owner: str) -> Any:
            if port == port_b:
                entered.set()
                release.wait(timeout=10)
            return fake_open(host, port, owner=owner)

        with patch("tools.stack.server.open_service", gated_open):
            server = StackServer()
            stub = _serve_in_process(self, server)
            self.assertEqual(stub.Configure(_real_config("127.0.0.1", port_a)).response, SUCCESS)
            results: dict[str, Any] = {}
            thread = threading.Thread(target=lambda: results.__setitem__(
                "configure", stub.Configure(_real_config("127.0.0.1", port_b))))
            thread.start()
            self.addCleanup(thread.join, 10)
            self.addCleanup(release.set)
            self.assertTrue(entered.wait(timeout=5))
            # The Configure is blocked inside open_service. Each call below
            # would hang (and hit the gRPC deadline) if it parked behind it.
            read = self._read(stub, timeout=5)
            transfer = stub.ExecuteCommand(tool_base_pb2.Command(stack=stack_pb2.Command(
                transfer=stack_pb2.Command.Transfer(step_key="s"))), timeout=5)
            for reply in (read, transfer):
                self.assertEqual(reply.response, ERROR_FROM_TOOL)
                self.assertEqual(reply.error_message, "stack: reconfiguring")
            self.assertEqual(stub.GetStatus(empty_pb2.Empty(), timeout=5).status, READY)
            release.set()
            thread.join(10)
            self.assertEqual(results["configure"].response, SUCCESS)
            # Admission reopens as soon as the Configure ends.
            self.assertEqual(self._read(stub, timeout=5).response, SUCCESS)

    def test_a_handler_uses_the_service_it_was_admitted_against(self) -> None:
        first, second = MagicMock(spec=StackService), MagicMock(spec=StackService)
        server = StackServer()
        server.service = first
        seen: list[Any] = []

        def _manager_state() -> dict[str, str]:
            server.service = second  # whatever swaps the owner mid-command
            seen.append(server._require_service())
            return {"kind": "managerState"}

        first.manager_state.side_effect = _manager_state
        reply = server._dispatchCommand(stack_pb2.Command.GetManagerState())
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(seen, [first])
        second.manager_state.assert_not_called()
        # The snapshot does not outlive the dispatch.
        self.assertIs(server._require_service(), second)
        self.assertEqual(server._readers, 0)

    def test_a_stale_ready_does_not_survive_a_failed_configure(self) -> None:
        port_a, _ = self._two_ports()
        reached, proceed = threading.Event(), threading.Event()
        gate_open = [False]
        with patch("tools.stack.server.open_service",
                   _fake_open_service(_fake_transport())):
            server = StackServer()
            stub = _serve_in_process(self, server)
            self.assertEqual(stub.Configure(_real_config("127.0.0.1", port_a)).response, SUCCESS)
            real_set_status = server.setStatus

            def _gated(status: Any) -> None:
                # The motion command's trailing setStatus(READY), held until
                # after the failed Configure has reported FAILED.
                if gate_open[0] and status == READY:
                    reached.set()
                    proceed.wait(timeout=10)
                real_set_status(status)

            with patch.object(server, "setStatus", _gated):
                gate_open[0] = True
                self.addCleanup(proceed.set)
                thread = threading.Thread(target=lambda: stub.ExecuteCommand(
                    tool_base_pb2.Command(stack=stack_pb2.Command(
                        transfer=stack_pb2.Command.Transfer(step_key="s")))))
                thread.start()
                self.addCleanup(thread.join, 10)
                self.assertTrue(reached.wait(timeout=5))
                gate_open[0] = False
                reply = stub.Configure(_real_config("   ", port_a))
                self.assertEqual(reply.response, NOT_READY)
                self.assertEqual(stub.GetStatus(empty_pb2.Empty()).status, FAILED)
                proceed.set()
                thread.join(10)
            status = stub.GetStatus(empty_pb2.Empty())
            self.assertIsNone(server.service)
            self.assertEqual(status.status, FAILED)
            # A successful Configure lifts the hold.
            self.assertEqual(stub.Configure(_real_config("127.0.0.1", port_a)).response, SUCCESS)
            self.assertEqual(stub.GetStatus(empty_pb2.Empty()).status, READY)


class TestConfigureWarning(_StackTestCase):
    """D-09: a fresh open warns once about what a restart can still lose."""

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

    def test_a_relative_ledger_dir_fails_before_open(self) -> None:
        for value in ("relative/ledger", "ledger", "./ledger", "  rel  "):
            with self.subTest(value=value):
                opener = MagicMock()
                server = StackServer()
                with patch("tools.stack.server.open_service", opener):
                    stub = _serve_in_process(self, server)
                    reply = stub.Configure(
                        _real_config("127.0.0.1", _free_tcp_port(), ledger_dir=value))
                    status = stub.GetStatus(empty_pb2.Empty()).status
                self.assertEqual(reply.response, NOT_READY)
                self.assertIn("ledger_dir", reply.error_message)
                self.assertEqual(status, FAILED)
                opener.assert_not_called()
                self.assertIsNone(server.service)

    def test_an_absolute_or_blank_ledger_dir_is_accepted_and_nothing_is_created(self) -> None:
        absolute = os.path.join(self.lock_dir, "abs", "ledger")
        for value in (absolute, "", "   "):
            with self.subTest(value=value):
                server = StackServer()
                with patch("tools.stack.server.open_service",
                           MagicMock(side_effect=_fake_open_service(_fake_transport()))):
                    stub = _serve_in_process(self, server)
                    reply = stub.Configure(
                        _real_config("127.0.0.1", _free_tcp_port(), ledger_dir=value))
                self.assertEqual(reply.response, SUCCESS)
                self.assertEqual(server._ledger_dir, value)
        self.assertFalse(os.path.exists(os.path.dirname(absolute)))
        self.assertFalse(os.path.exists(os.path.join(self.xdg_state_home, "galago-tools")))

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


_PINNED_CORE_SHA = "934a621ece116a8b263897c1e9b62b57374f4ef3"


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

# D-16 (replaces Phase 4 D-20): no adapter code may call these core methods,
# on any receiver. The one motion submit (execute_transfer) and the plan call
# are allowed at a single call site each, and acknowledge_failure in a single
# handler; those narrower rules live in _stack_adapter_violations.
_FORBIDDEN_SERVICE_CALLS = frozenset({
    "start_transfer", "cancel_transfer", "go_to_safe_position",
    "wait_safe_position", "validate_transfer",
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
_REQUIRED_FUNCTIONS = (
    "_configure", "_result_reply", "GetManagerState", "_run_fresh", "Transfer",
    "AcknowledgeFailure", "GetFailureLatch")
# D-16 call-site rules: each of these has exactly one call site, in the named
# function; execute_transfer additionally never sits in a loop and always after
# the write-ahead claim; acknowledge_failure may appear only in its handler.
_SINGLE_SITE_CALLS = {"execute_transfer": "_run_fresh", "plan_transfer": "_run_fresh"}
_LOOP_NODES = (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.SetComp,
               ast.DictComp, ast.GeneratorExp, ast.Lambda)
_WRITE_AHEAD_CALL = "claim"
_ACK_CALL = "acknowledge_failure"
_ACK_HANDLER = "AcknowledgeFailure"
# The handler must compare against this constant before its one acknowledge call.
_ACK_YES_CONSTANT = "yes"


def _name_of(func: ast.expr) -> Optional[str]:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _enclosing_function(
        node: ast.AST, parents: dict[ast.AST, ast.AST]) -> Optional[ast.FunctionDef]:
    """The nearest FunctionDef above `node`, or None at module level."""
    ancestor = parents.get(node)
    while ancestor is not None:
        if isinstance(ancestor, ast.FunctionDef):
            return ancestor
        ancestor = parents.get(ancestor)
    return None


# Call sites of the single-site and acknowledge methods: (location, enclosing
# FunctionDef, the Call, the tree's child-to-parent map).
_Site = tuple[str, Optional[ast.FunctionDef], ast.Call, dict[ast.AST, ast.AST]]


def _stack_adapter_violations(trees: dict[str, ast.Module]) -> list[str]:
    """Pure, assertion-free no-MCP / open_service-shape / call-site checks
    (D-16, D-21) over every tools/stack module. Returns "<file>:<line>:
    <reason>" strings, or [] when clean. Never raises, so planted copies can
    be checked without failing the test that plants them.

    Call-site rules (XFR-05): the _FORBIDDEN_SERVICE_CALLS names are never
    called; execute_transfer and plan_transfer each have exactly one call site
    across all modules, inside _run_fresh; execute_transfer has no loop,
    comprehension or lambda ancestor and sits after the write-ahead claim call;
    acknowledge_failure appears exactly once, inside AcknowledgeFailure, after a
    comparison against the constant "yes" in that function;
    none of these is reached through getattr with a string or held as an
    uncalled attribute. wait_transfer and wait are read-only and unrestricted."""
    violations: list[str] = []
    open_service_calls = 0
    defined: set[str] = set()
    sites: dict[str, list[_Site]] = {}
    guarded = _FORBIDDEN_SERVICE_CALLS | set(_SINGLE_SITE_CALLS) | {_ACK_CALL}

    for fname, tree in sorted(trees.items()):
        parents = {
            child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        for node in ast.walk(tree):
            at = f"{fname}:{getattr(node, 'lineno', 0)}"
            if isinstance(node, ast.FunctionDef):
                defined.add(node.name)
            if isinstance(node, ast.Attribute) and node.attr in guarded:
                parent = parents.get(node)
                if not (isinstance(parent, ast.Call) and parent.func is node):
                    violations.append(f"{at}: .{node.attr} referenced without a call")
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
            if isinstance(func, ast.Attribute) and (
                    func.attr in _SINGLE_SITE_CALLS or func.attr == _ACK_CALL):
                sites.setdefault(func.attr, []).append(
                    (at, _enclosing_function(node, parents), node, parents))
            if (name == "getattr" and len(node.args) >= 2
                    and isinstance(node.args[1], ast.Constant)
                    and node.args[1].value in guarded):
                violations.append(f"{at}: .{node.args[1].value}() reached via getattr")
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

    for call_name in (*_SINGLE_SITE_CALLS, _ACK_CALL):
        found = sites.get(call_name, [])
        home = _SINGLE_SITE_CALLS.get(call_name, _ACK_HANDLER)
        if len(found) != 1:
            violations.append(
                f"tools/stack: {call_name}() must have exactly one call site, found {len(found)}")
        for at, enclosing, _call, _parents in found:
            if enclosing is None or enclosing.name != home:
                violations.append(f"{at}: {call_name}() called outside {home}")
    for at, enclosing, call, _parents in sites.get(_ACK_CALL, []):
        if enclosing is not None and enclosing.name == _ACK_HANDLER:
            checks = [
                c for c in ast.walk(enclosing)
                if isinstance(c, ast.Compare) and any(
                    isinstance(operand, ast.Constant) and operand.value == _ACK_YES_CONSTANT
                    for operand in (c.left, *c.comparators))]
            if not any(c.lineno < call.lineno for c in checks):
                violations.append(
                    f"{at}: acknowledge_failure() without a preceding {_ACK_YES_CONSTANT!r} check")
    for at, enclosing, call, parents in sites.get("execute_transfer", []):
        ancestor = parents.get(call)
        while ancestor is not None:
            if isinstance(ancestor, _LOOP_NODES):
                violations.append(
                    f"{at}: execute_transfer() inside a loop ({type(ancestor).__name__})")
                break
            ancestor = parents.get(ancestor)
        if enclosing is not None and enclosing.name == "_run_fresh":
            claims = [
                c for c in ast.walk(enclosing)
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                and c.func.attr == _WRITE_AHEAD_CALL]
            if not any(c.lineno < call.lineno for c in claims):
                violations.append(f"{at}: execute_transfer() sent before the write-ahead claim")

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
        self._assert_trees_reported(self._with(tree), fragment)

    def _assert_trees_reported(self, trees: dict[str, ast.Module], fragment: str) -> None:
        violations = _stack_adapter_violations(trees)
        self.assertTrue(violations, "expected a violation")
        self.assertTrue(any(fragment in v for v in violations), f"{fragment!r} not in {violations}")

    def _assert_clean(self, tree: ast.Module) -> None:
        self.assertEqual(_stack_adapter_violations(self._with(tree)), [])

    def _renamed_call(self, old: str, new: str) -> ast.Module:
        """Deep copy of server.py with every attribute call `.old(` renamed."""
        tree = copy.deepcopy(self.server)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                    and node.func.attr == old:
                node.func.attr = new
        return tree

    def test_real_sources_are_clean(self) -> None:
        self.assertIn("server.py", self.trees)
        self.assertEqual(_stack_adapter_violations(self.trees), [])

    def test_every_forbidden_service_call_is_reported(self) -> None:
        self.assertEqual(len(_FORBIDDEN_SERVICE_CALLS), 5)
        for name in sorted(_FORBIDDEN_SERVICE_CALLS):
            with self.subTest(name=name):
                self._assert_reported(
                    _plant(self.server, "GetManagerState", f"self.service.{name}()"), f".{name}()")

    def test_module_level_forbidden_call_is_reported(self) -> None:
        self._assert_reported(
            _plant(self.server, None, "service.start_transfer()"), ".start_transfer()")

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
            "self.service.latch_status()",
            'self.service.wait_transfer("g", timeout_s=1.0)',
            "self.service.wait(None, timeout_s=1.0)",
        ):
            with self.subTest(statement=statement):
                planted = _plant(self.server, "GetManagerState", statement)
                self.assertEqual(_stack_adapter_violations(self._with(planted)), [])

    # -- XFR-05 call-site rules (D-16) -----------------------------------

    def test_a_second_execute_transfer_is_reported(self) -> None:
        self._assert_reported(
            _plant(self.server, "GetManagerState", "self.service.execute_transfer(p)"),
            "exactly one call site")
        self._assert_reported(
            _plant(self.server, "GetManagerState", "self.service.execute_transfer(p)"),
            "outside _run_fresh")

    def test_execute_transfer_in_a_loop_or_comprehension_is_reported(self) -> None:
        for label, statement in (
            ("for", "for _ in range(2):\n    service.execute_transfer(p)"),
            ("while", "while True:\n    service.execute_transfer(p)"),
            ("list", "[service.execute_transfer(p) for _ in range(2)]"),
            ("set", "{service.execute_transfer(p) for _ in range(2)}"),
            ("dict", "{_: service.execute_transfer(p) for _ in range(2)}"),
            ("generator", "list(service.execute_transfer(p) for _ in range(2))"),
            ("lambda", "f = lambda: service.execute_transfer(p)"),
        ):
            with self.subTest(label):
                self._assert_reported(
                    _plant(self.server, "_run_fresh", statement), "inside a loop")

    def test_removing_the_real_execute_transfer_call_is_reported(self) -> None:
        self._assert_reported(
            self._renamed_call("execute_transfer", "execute_transfer_renamed"),
            "exactly one call site")

    def test_execute_transfer_before_the_write_ahead_claim_is_reported(self) -> None:
        self._assert_reported(
            self._renamed_call("claim", "claim_renamed"), "before the write-ahead claim")

    def test_a_second_plan_transfer_is_reported(self) -> None:
        self._assert_reported(
            _plant(self.server, "GetManagerState", "self.service.plan_transfer(r)"),
            "exactly one call site")
        self._assert_reported(
            _plant(self.server, "GetManagerState", "self.service.plan_transfer(r)"),
            "outside _run_fresh")

    def test_getattr_reaching_a_guarded_method_is_reported(self) -> None:
        guarded = sorted(_FORBIDDEN_SERVICE_CALLS | set(_SINGLE_SITE_CALLS) | {_ACK_CALL})
        for name in guarded:
            with self.subTest(name=name):
                self._assert_reported(
                    _plant(self.server, "GetManagerState", f'getattr(service, "{name}")(p)'),
                    "via getattr")

    def test_an_aliased_guarded_method_is_reported(self) -> None:
        self._assert_reported(
            _plant(self.server, "GetManagerState", "fn = self.service.execute_transfer"),
            "without a call")

    def test_acknowledge_failure_outside_its_handler_is_reported(self) -> None:
        self._assert_reported(
            _plant(self.server, "GetManagerState",
                   'self.service.acknowledge_failure("g", confirm=True)'),
            "outside AcknowledgeFailure")

    def test_a_second_acknowledge_failure_call_is_reported(self) -> None:
        self._assert_reported(
            _plant(self.server, "AcknowledgeFailure",
                   'self.service.acknowledge_failure("g", confirm=True)'),
            "exactly one call site")

    def test_removing_the_real_acknowledge_failure_call_is_reported(self) -> None:
        self._assert_reported(
            self._renamed_call("acknowledge_failure", "acknowledge_failure_renamed"),
            "acknowledge_failure() must have exactly one call site, found 0")

    def test_acknowledge_failure_planted_in_transfer_is_reported(self) -> None:
        self._assert_reported(
            _plant(self.server, "Transfer",
                   'self.service.acknowledge_failure("g", confirm=True)'),
            "outside AcknowledgeFailure")

    def _handler(self, tree: ast.Module) -> ast.FunctionDef:
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == _ACK_HANDLER:
                return node
        raise AssertionError("no AcknowledgeFailure handler")

    def test_the_real_handler_has_exactly_one_call_after_a_yes_check(self) -> None:
        handler = self._handler(self.server)
        calls = [n for n in ast.walk(handler) if isinstance(n, ast.Call)
                 and _name_of(n.func) == _ACK_CALL]
        self.assertEqual(len(calls), 1)
        self._assert_clean(self.server)

    def test_deleting_the_yes_comparison_from_the_handler_is_reported(self) -> None:
        tree = copy.deepcopy(self.server)
        for node in ast.walk(self._handler(tree)):
            if isinstance(node, ast.Constant) and node.value == _ACK_YES_CONSTANT:
                node.value = "nope"
        self._assert_reported(tree, "without a preceding 'yes' check")

    def test_a_yes_comparison_after_the_call_does_not_count(self) -> None:
        tree = copy.deepcopy(self.server)
        handler = self._handler(tree)
        guard = next(n for n in handler.body if any(
            isinstance(c, ast.Compare) for c in ast.walk(n)))
        ast.increment_lineno(guard, 1000)
        self._assert_reported(tree, "without a preceding 'yes' check")

    def test_a_yes_comparison_elsewhere_does_not_cover_the_handler(self) -> None:
        tree = copy.deepcopy(self.server)
        for node in ast.walk(self._handler(tree)):
            if isinstance(node, ast.Constant) and node.value == _ACK_YES_CONSTANT:
                node.value = "nope"
        planted = _plant(tree, "GetManagerState", 'x = "yes" == "yes"')
        self._assert_reported(planted, "without a preceding 'yes' check")

    def test_the_call_site_count_spans_every_stack_module(self) -> None:
        trees = dict(self.trees)
        trees["ledger.py"] = _plant(self.trees["ledger.py"], None, "service.execute_transfer(p)")
        self._assert_trees_reported(trees, "exactly one call site")

    def test_wait_transfer_in_a_loop_is_not_reported(self) -> None:
        self._assert_clean(_plant(
            self.server, "_run_fresh",
            'for _ in range(3):\n    service.wait_transfer("g", timeout_s=1.0)'))

    def test_the_fresh_path_and_transfer_are_required_functions(self) -> None:
        for required in ("_run_fresh", "Transfer", "AcknowledgeFailure", "GetFailureLatch"):
            with self.subTest(required=required):
                self.assertIn(required, _REQUIRED_FUNCTIONS)
                tree = copy.deepcopy(self.server)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name == required:
                        node.name = required + "_renamed"
                self._assert_reported(tree, f"{required}() is missing")


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


_GUID = "11111111-2222-3333-4444-555555555555"
_STEP_KEY = "run-1:stack-1"


def _ran_snapshot(guid: str = _GUID) -> TaskSnapshot:
    return TaskSnapshot(guid=guid, state="completed", raw_state="completed", error_code=None,
                        error_name=None, description=None, elapsed="00:00:30")


class _FakeCore:
    """A stand-in for StackService built from the core's real result classes.

    It implements plan_transfer, execute_transfer, wait, wait_transfer,
    latch_status and acknowledge_failure only, so any other method access
    raises AttributeError: a test never moves the (absent) arm by accident. An
    attribute holding an Exception instance is raised; a callable is called
    with the call's arguments. Every call is recorded in `calls`."""

    def __init__(self) -> None:
        request = TransferRequest(
            robot="R1", labware_profile="plate96",
            source=Location(device="SD", deck="SK", nest="SN", transfer_profile="STP"),
            destination=Location(device="DD", deck="DK", nest="DN", transfer_profile="DTP"))
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.plan_result: Any = TransferPlan(
            plan_id="plan-1", summary=TransferSummary.from_request(request),
            estimated_time="00:00:30", estimated_s=30.0)
        self.execute_result: Any = TaskHandle(guid=_GUID, robot="R1", estimated_s=30.0)
        self.wait_result: Any = Ran(task=_ran_snapshot())
        self.wait_transfer_results: list[Any] = []
        self.latch_result: Any = LatchStatus(latched=False)
        self.ack_result: Any = FailureAcknowledged(guid=_GUID, result_kind="failed")

    @property
    def execute_calls(self) -> int:
        return sum(1 for name, _a, _k in self.calls if name == "execute_transfer")

    @property
    def call_names(self) -> list[str]:
        return [name for name, _a, _k in self.calls]

    def _answer(self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any],
                value: Any) -> Any:
        self.calls.append((name, args, kwargs))
        if isinstance(value, BaseException):
            raise value
        if callable(value):
            return value(*args, **kwargs)
        return value

    def plan_transfer(self, request: Any) -> Any:
        return self._answer("plan_transfer", (request,), {}, self.plan_result)

    def execute_transfer(self, plan_id: Any) -> Any:
        return self._answer("execute_transfer", (plan_id,), {}, self.execute_result)

    def wait(self, handle: Any, *, timeout_s: float = 600.0) -> Any:
        return self._answer("wait", (handle,), {"timeout_s": timeout_s}, self.wait_result)

    def wait_transfer(self, guid: Any, *, timeout_s: float = 300.0) -> Any:
        value = self.wait_transfer_results.pop(0) if self.wait_transfer_results else self.wait_result
        return self._answer("wait_transfer", (guid,), {"timeout_s": timeout_s}, value)

    def latch_status(self) -> Any:
        return self._answer("latch_status", (), {}, self.latch_result)

    def acknowledge_failure(self, guid: Any, *, confirm: bool = False) -> Any:
        return self._answer("acknowledge_failure", (guid,), {"confirm": confirm}, self.ack_result)


class _TransferTestCase(_RealModeGrpcTestCase):
    """A real-mode Transfer fixture: a _FakeCore as the service, and the step
    ledger in a fresh absolute temp directory."""

    def setUp(self) -> None:
        super().setUp()
        self.ledger_dir = os.path.join(self._tmpdir.name, "ledger")
        self.server._ledger_dir = self.ledger_dir
        self.core = _FakeCore()
        self.server.service = self.core  # type: ignore[assignment]
        self.addCleanup(self._assert_motion_lock_free)

    @staticmethod
    def _assert_motion_lock_free() -> None:
        assert not stack_server._MOTION_LOCK.locked(), "the motion lock leaked"

    @property
    def ledger_path(self) -> str:
        return os.path.join(self.ledger_dir, "stack-ledger.json")

    def _transfer(self, step_key: str = _STEP_KEY, **fields: Any) -> Any:
        for name, value in _ESTIMATE_FIELDS.items():
            fields.setdefault(name, value)
        return self.stub.ExecuteCommand(self._stack(
            transfer=stack_pb2.Command.Transfer(step_key=step_key, **fields)))

    def _records(self) -> dict[str, Any]:
        with open(self.ledger_path, encoding="utf-8") as handle:
            document = json.load(handle)
        assert document["version"] == 1
        return dict(document["records"])


class TestTransferFreshPath(_TransferTestCase):
    """XFR-01 / XFR-02 tracer: plan, write-ahead, execute, started, wait, done."""

    def test_the_happy_path_is_success_with_ran_meta_and_the_ordered_calls(self) -> None:
        reply = self._transfer()
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(reply.error_message, "")
        self.assertEqual(reply.meta_data, _struct(Ran(task=_ran_snapshot()).to_dict()))
        self.assertEqual(self.core.call_names, ["plan_transfer", "execute_transfer", "wait"])
        self.assertEqual(self.core.execute_calls, 1)
        self.assertEqual(self.core.calls[1][1], ("plan-1",))
        self.assertEqual(self.core.calls[2][2], {"timeout_s": 300.0})

    def test_the_ledger_ends_with_a_done_record_carrying_handle_and_result(self) -> None:
        self._transfer()
        records = self._records()
        self.assertEqual(list(records), [_STEP_KEY])
        record = records[_STEP_KEY]
        self.assertEqual(record["state"], "done")
        self.assertRegex(record["fingerprint"], r"^[0-9a-f]{64}$")
        self.assertEqual(record["instance"], self.server._instance)
        self.assertEqual(record["handle"], self.core.execute_result.to_dict())
        self.assertEqual(record["result"], Ran(task=_ran_snapshot()).to_dict())
        for field in ("createdAt", "updatedAt"):
            stamp = datetime.fromisoformat(record[field])
            self.assertEqual(stamp.utcoffset(), timedelta(0))

    def test_the_write_ahead_record_is_on_disk_when_execute_transfer_is_called(self) -> None:
        seen: list[Any] = []
        handle = TaskHandle(guid=_GUID, robot="R1", estimated_s=30.0)

        def _execute(plan_id: str) -> Any:
            seen.append(self._records().get(_STEP_KEY))
            return handle

        self.core.execute_result = _execute
        self._transfer()
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0]["state"], "submitting")
        self.assertEqual(seen[0]["instance"], self.server._instance)
        self.assertRegex(seen[0]["fingerprint"], r"^[0-9a-f]{64}$")

    def test_a_fresh_ledger_directory_is_0700_and_the_files_are_0600(self) -> None:
        self._transfer()
        self.assertEqual(stat.S_IMODE(os.stat(self.ledger_dir).st_mode), 0o700)
        for name in ("stack-ledger.json", "stack-ledger.json.lock"):
            with self.subTest(name=name):
                mode = stat.S_IMODE(os.stat(os.path.join(self.ledger_dir, name)).st_mode)
                self.assertEqual(mode, 0o600)

    def test_a_blank_ledger_dir_lands_under_xdg_state_home(self) -> None:
        self.server._ledger_dir = ""
        self.assertEqual(self._transfer().response, SUCCESS)
        expected = os.path.join(
            os.environ["XDG_STATE_HOME"], "galago-tools", "stack", "stack-ledger.json")
        self.assertTrue(os.path.isfile(expected))
        self.assertFalse(os.path.exists(os.path.join(self.fake_home, ".local")))

    def test_a_repeat_of_the_step_key_sends_nothing(self) -> None:
        self._transfer()
        self.assertEqual(self.core.execute_calls, 1)
        before = len(self.core.calls)
        reply = self._transfer()
        self.assertEqual(self.core.execute_calls, 1)
        self.assertEqual(len(self.core.calls), before)
        self.assertEqual(self.core.call_names.count("plan_transfer"), 1)
        # A done+ran record inside the replay window is replayed (D-07).
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(reply.meta_data["replayed"], True)

    def test_a_corrupt_ledger_refuses_the_transfer_and_is_left_untouched(self) -> None:
        os.makedirs(self.ledger_dir, mode=0o700)
        with open(self.ledger_path, "wb") as handle:
            handle.write(b"{not json")
        reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn(self.ledger_path, reply.error_message)
        self.assertIn("do not delete it", reply.error_message)
        self.assertEqual(self.core.calls, [])
        with open(self.ledger_path, "rb") as handle:
            self.assertEqual(handle.read(), b"{not json")

    def test_execute_raising_leaves_the_record_submitting(self) -> None:
        self.core.execute_result = RuntimeError("secret detail")
        reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("RuntimeError", reply.error_message)
        self.assertNotIn("secret detail", reply.error_message)
        self.assertEqual(self._records()[_STEP_KEY]["state"], "submitting")
        self._transfer()
        self.assertEqual(self.core.execute_calls, 1)

    def test_a_plan_that_is_not_a_plan_writes_no_record(self) -> None:
        self.core.plan_result = NeedsInput(missing=["robot"])
        reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertEqual(self.core.call_names, ["plan_transfer"])
        self.assertFalse(os.path.exists(self.ledger_path))

    def test_a_non_ran_wait_result_is_an_error_and_the_unfinished_record_is_kept(self) -> None:
        self.core.wait_result = TimedOut(handle=self.core.execute_result)
        reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertEqual(self._records()[_STEP_KEY]["state"], "started")
        self.assertEqual(self.core.call_names.count("wait"), 1)

    def test_an_unconfigured_transfer_is_not_ready(self) -> None:
        self.server.service = None
        reply = self._transfer()
        self.assertEqual(reply.response, NOT_READY)
        self.assertEqual(reply.error_message, "stack: not configured")

    def test_the_motion_lock_is_free_after_every_outcome(self) -> None:
        self._transfer()
        self.core.execute_result = RuntimeError("x")
        self._transfer("run-2:stack-1")
        self.assertFalse(stack_server._MOTION_LOCK.locked())


class TestFailureLatch(_RealModeGrpcTestCase):
    """ACK-02 / D-13: GetFailureLatch is latch_status() 1:1, zero I/O, idempotent."""

    LATCHES = (
        ("task guid", LatchStatus(latched=True, guid=_GUID, result_kind="failed", reason=None)),
        ("submit id", LatchStatus(latched=True, guid="submit-0123456789abcdef",
                                  result_kind="lost", reason="submitOutcomeUnknown")),
        ("state id", LatchStatus(latched=True, guid="state-0123456789abcdef",
                                 result_kind="stateUnreadable", reason="stateUnreadable")),
        ("unlatched", LatchStatus(latched=False)),
    )

    def _latch(self) -> Any:
        return self.stub.ExecuteCommand(self._stack(
            get_failure_latch=stack_pb2.Command.GetFailureLatch()))

    def test_every_latch_shape_is_success_with_latch_status_meta(self) -> None:
        for label, status in self.LATCHES:
            with self.subTest(label):
                self.service.reset_mock()
                self.service.latch_status.return_value = status
                reply = self._latch()
                self.assertEqual(reply.response, SUCCESS, reply.error_message)
                self.assertEqual(reply.error_message, "")
                self.assertEqual(reply.meta_data, _struct(status.to_dict()))
                self.assertEqual(self.service.mock_calls, [mock_call.latch_status()])

    def test_the_unlatched_status_carries_a_null_guid(self) -> None:
        self.service.latch_status.return_value = LatchStatus(latched=False)
        meta = MessageToDict(self._latch().meta_data)
        self.assertIs(meta["latched"], False)
        self.assertIsNone(meta["guid"])
        self.assertEqual(meta["kind"], "latchStatus")

    def test_two_reads_return_the_same_meta_and_change_nothing(self) -> None:
        self.service.latch_status.return_value = self.LATCHES[1][1]
        first, second = self._latch(), self._latch()
        self.assertEqual(first.meta_data, second.meta_data)
        self.assertEqual(self.service.mock_calls, [mock_call.latch_status()] * 2)
        self.assertEqual(self._health().status, READY)

    def test_the_latch_answers_while_a_transfer_holds_the_tool_busy(self) -> None:
        self.service.latch_status.return_value = self.LATCHES[0][1]
        release = threading.Event()
        entered = threading.Event()

        def _blocking(*_a: Any, **_k: Any) -> Any:
            entered.set()
            release.wait(timeout=10)
            return tool_base_pb2.ExecuteCommandReply(response=SUCCESS, return_reply=True)

        patcher = patch.object(self.server, "Transfer", MagicMock(side_effect=_blocking))
        patcher.start()
        self.addCleanup(patcher.stop)
        thread = threading.Thread(target=lambda: self.stub.ExecuteCommand(self._stack(
            transfer=stack_pb2.Command.Transfer(step_key="busy-1"))))
        thread.start()
        self.addCleanup(thread.join, 10)
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(timeout=5))
        self.assertEqual(self._health().status, tool_base_pb2.BUSY)
        reply = self._latch()
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(reply.meta_data, _struct(self.LATCHES[0][1].to_dict()))

    def test_unconfigured_the_latch_is_not_ready(self) -> None:
        self.server.service = None
        reply = self._latch()
        self.assertEqual(reply.response, NOT_READY)
        self.assertEqual(reply.error_message, "stack: not configured")

    def test_latch_status_is_the_only_core_call_and_no_ledger_is_made(self) -> None:
        self.service.latch_status.return_value = self.LATCHES[0][1]
        self._latch()
        self.assertEqual([c[0] for c in self.service.mock_calls], ["latch_status"])
        self.assertFalse(os.path.exists(os.path.join(self.xdg_state_home, "galago-tools")))


_SUBMIT_GUID = "submit-0123456789abcdef"
_STATE_GUID = "state-0123456789abcdef"


class TestLatchGuidInMessage(_TransferTestCase):
    """ACK-02 / A-2: every Transfer error whose cause can latch names the guid
    from latch_status() first, labels the result's own guid "task guid", and
    keeps that guid inside the 300-character cap."""

    def _latched(self, guid: str = _SUBMIT_GUID, kind: str = "lost") -> LatchStatus:
        return LatchStatus(latched=True, guid=guid, result_kind=kind,
                           reason="submitOutcomeUnknown")

    def test_a_failed_task_names_the_latched_guid_before_the_task_guid(self) -> None:
        failed = Failed(task=_snapshot("g-task"))
        self.core.wait_result = failed
        self.core.latch_result = self._latched()
        reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        message = reply.error_message
        self.assertIn(f"latched guid {_SUBMIT_GUID}", message)
        self.assertIn("AcknowledgeFailure", message)
        self.assertLess(message.index(f"latched guid {_SUBMIT_GUID}"),
                        message.index("task guid g-task"))
        self.assertNotIn("latched guid g-task", message)
        self.assertEqual(reply.meta_data, _struct(failed.to_dict()))
        self.assertEqual(self.core.call_names.count("latch_status"), 1)

    def test_the_first_failure_wins_and_the_task_guid_is_never_the_one_to_acknowledge(self) -> None:
        self.core.wait_result = Failed(task=_snapshot("g-task"))
        self.core.latch_result = self._latched("g-earlier", "failed")
        message = self._transfer().error_message
        self.assertIn("latched guid g-earlier (failed)", message)
        self.assertIn("task guid g-task", message)
        self.assertNotIn("latched guid g-task", message)
        self.assertLess(message.index("g-earlier"), message.index("g-task"))

    def test_aborted_and_lost_with_an_unlatched_core_say_it_did_not_latch(self) -> None:
        for label, result in (
            ("aborted", Aborted(task=_snapshot("g-task"))),
            ("lost", Lost(reason="taskNotFound", handle=TaskHandle(guid="g-handle"))),
        ):
            with self.subTest(label):
                self.core.wait_result = result
                self.core.latch_result = LatchStatus(latched=False)
                reply = self._transfer(f"run-{label}:k")
                self.assertEqual(reply.response, ERROR_FROM_TOOL)
                self.assertIn("did not latch", reply.error_message)
                self.assertIn("inspect the arm", reply.error_message)
                self.assertNotIn("latched guid", reply.error_message)
                self.assertEqual(reply.meta_data, _struct(result.to_dict()))

    def test_a_failure_latched_plan_refusal_names_the_latch_and_sends_nothing(self) -> None:
        refused = Refused(reason="failureLatched", detail={"guid": _STATE_GUID})
        self.core.plan_result = refused
        self.core.latch_result = self._latched(_STATE_GUID, "stateUnreadable")
        reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn(f"latched guid {_STATE_GUID} (stateUnreadable)", reply.error_message)
        self.assertEqual(reply.meta_data, _struct(refused.to_dict()))
        self.assertEqual(self.core.call_names, ["plan_transfer", "latch_status"])
        self.assertFalse(os.path.exists(self.ledger_path))

    def test_the_latched_guid_survives_the_cap_with_a_400_character_reason(self) -> None:
        self.core.latch_result = self._latched()
        self.core.wait_result = Lost(reason="r" * 400, handle=TaskHandle(guid="g-handle"))
        message = self._transfer("wait:k").error_message
        self.assertIn(_SUBMIT_GUID, message)
        self.assertLessEqual(len(message), 300)
        self.assertIn("AcknowledgeFailure", message)
        reply = stack_server._transfer_error_reply(
            self.core, Failed(task=_snapshot("g" * 400)))
        self.assertLessEqual(len(reply.error_message), 300)
        self.assertIn(_SUBMIT_GUID, reply.error_message)

    def test_non_latching_errors_keep_the_phase_4_line_and_make_no_latch_call(self) -> None:
        for label, plan in (
            ("rejected", Rejected(stage="local", findings=[{"name": "stackArmNotFound"}])),
            ("needsInput", NeedsInput(missing=["robot"])),
            ("readFailed", ReadFailed(error={"status": 503, "name": "Busy"})),
            ("robotNotIdle", Refused(reason="robotNotIdle", detail={"robot": "R1"})),
        ):
            with self.subTest(label):
                self.core.calls.clear()
                self.core.plan_result = plan
                reply = self._transfer()
                self.assertEqual(reply.response, ERROR_FROM_TOOL)
                self.assertEqual(reply.error_message, _result_reply(plan).error_message)
                self.assertEqual(reply.meta_data, _struct(plan.to_dict()))
                self.assertNotIn("latch_status", self.core.call_names)

    def test_the_ran_path_makes_no_latch_call(self) -> None:
        reply = self._transfer()
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(reply.error_message, "")
        self.assertNotIn("latch_status", self.core.call_names)

    def test_a_raising_latch_status_still_returns_the_error(self) -> None:
        self.core.wait_result = Failed(task=_snapshot("g-task"))
        self.core.latch_result = RuntimeError("secret detail")
        reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("latch status unavailable; read GetFailureLatch", reply.error_message)
        self.assertNotIn("secret detail", reply.error_message)
        self.assertIn("task guid g-task", reply.error_message)

    def test_a_malformed_latch_answer_is_unavailable_never_a_guess(self) -> None:
        for label, answer in (
            ("string", "submit-0123456789abcdef"),
            ("none", None),
            ("dict", {"latched": True, "guid": "g"}),
            ("latched without a guid", LatchStatus(latched=True, guid=None)),
            ("latched with a blank guid", LatchStatus(latched=True, guid="  ")),
        ):
            with self.subTest(label):
                self.core.latch_result = answer
                clause = stack_server._latch_clause(self.core)
                self.assertEqual(clause, "latch status unavailable; read GetFailureLatch")

    def test_the_clause_templates_are_the_spike_wording(self) -> None:
        self.core.latch_result = self._latched("g-1", "failed")
        self.assertEqual(stack_server._latch_clause(self.core),
                         "latched guid g-1 (failed); inspect the arm, then AcknowledgeFailure")
        self.core.latch_result = LatchStatus(latched=False)
        self.assertEqual(stack_server._latch_clause(self.core),
                         "the core did not latch this; inspect the arm")

    def test_the_explanation_text_is_never_read(self) -> None:
        self.core.wait_result = Failed(task=_snapshot("g-task"), explanation=_SENTINEL)
        self.core.latch_result = LatchStatus(
            latched=True, guid="g-1", result_kind="failed", explanation=_SENTINEL)
        self.assertNotIn(_SENTINEL, self._transfer().error_message)

    def test_a_ledger_write_failure_after_a_failure_still_names_the_latch(self) -> None:
        self.core.wait_result = Failed(task=_snapshot("g-task"))
        self.core.latch_result = self._latched()
        with patch.object(stack_server.Ledger, "mark_done",
                          side_effect=LedgerError("unwritable", self.ledger_path)):
            reply = self._transfer()
        message = reply.error_message
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("ledger could not record it", message)
        self.assertIn(f"latched guid {_SUBMIT_GUID}", message)
        self.assertLess(message.index("latched guid"), message.index("will not send a second"))
        self.assertLessEqual(len(message), 300)

    def test_a_ledger_write_failure_after_ran_has_no_latch_clause(self) -> None:
        with patch.object(stack_server.Ledger, "mark_done",
                          side_effect=LedgerError("unwritable", self.ledger_path)):
            reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("transfer ran, but the ledger could not record it", reply.error_message)
        self.assertNotIn("latch_status", self.core.call_names)


class TestKeyRelease(_TransferTestCase):
    """XFR-04 / D-08: a step key is released only when execute_transfer
    returned one of the core's "nothing was sent" classes (by isinstance);
    anything ambiguous or unknown keeps the key and is never deleted."""

    def _ledger(self) -> Ledger:
        return Ledger(Path(self.ledger_dir))

    def _rerun_succeeds(self, key: str) -> None:
        """The key was released: a re-run calls plan and execute again."""
        self.core.calls.clear()
        self.core.execute_result = TaskHandle(guid=_GUID, robot="R1", estimated_s=30.0)
        self.core.wait_result = Ran(task=_ran_snapshot())
        reply = self._transfer(key)
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(self.core.call_names.count("plan_transfer"), 1)
        self.assertEqual(self.core.call_names.count("execute_transfer"), 1)

    def test_every_nothing_was_sent_result_releases_the_key(self) -> None:
        results = (
            ("planNotFound", Refused(reason="planNotFound")),
            ("planExpired", Refused(reason="planExpired")),
            ("failureLatched", Refused(reason="failureLatched", detail={"guid": "g-latched"})),
            ("inFlight", Refused(reason="inFlight", detail={"guid": "g-running"})),
            ("stackBusy", Refused(reason="stackBusy")),
            ("managerNotAutomated", Refused(reason="managerNotAutomated")),
            ("recoveryPending", Refused(reason="recoveryPending")),
            ("robotNotIdle", Refused(reason="robotNotIdle")),
            ("rejected-instrument", Rejected(stage="instrument", findings=[{"name": "x"}])),
            ("rejected-local", Rejected(stage="local", findings=[])),
            ("needsInput", NeedsInput(missing=["robot"])),
            ("readFailed", ReadFailed(error={"name": "boom", "status": 500})),
        )
        for label, result in results:
            with self.subTest(label):
                key = f"run-{label}:k"
                self.core.calls.clear()
                self.core.execute_result = result
                reply = self._transfer(key)
                self.assertEqual(reply.response, ERROR_FROM_TOOL)
                self.assertNotIn(key, self._records())
                self.assertEqual(self.core.call_names.count("execute_transfer"), 1)
                self._rerun_succeeds(key)

    def test_a_submit_outcome_unknown_keeps_the_key_with_the_latch_guid(self) -> None:
        self.core.execute_result = Lost(reason="submitOutcomeUnknown")
        self.core.latch_result = LatchStatus(
            latched=True, guid=_SUBMIT_GUID, result_kind="lost", reason="submitOutcomeUnknown")
        reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        record = self._records()[_STEP_KEY]
        self.assertEqual(record["state"], "outcomeUnknown")
        self.assertEqual(record["latchGuid"], _SUBMIT_GUID)
        self.assertIn(_SUBMIT_GUID, reply.error_message)
        self.assertIn("will not be re-sent", reply.error_message)
        self.assertGreaterEqual(self.core.call_names.count("latch_status"), 1)
        before = list(self.core.calls)
        self._transfer()
        self.assertEqual(
            [n for n in self.core.call_names if n in ("plan_transfer", "execute_transfer")],
            [n for n, _a, _k in before if n in ("plan_transfer", "execute_transfer")])

    def test_an_unlatched_submit_outcome_unknown_records_no_guid(self) -> None:
        self.core.execute_result = Lost(reason="submitOutcomeUnknown")
        self.core.latch_result = LatchStatus(latched=False)
        reply = self._transfer()
        record = self._records()[_STEP_KEY]
        self.assertEqual(record["state"], "outcomeUnknown")
        self.assertIsNone(record["latchGuid"])
        self.assertIn("did not latch", reply.error_message)
        self.assertIn("will not be re-sent", reply.error_message)
        self._transfer()
        self.assertEqual(self.core.execute_calls, 1)
        self.assertEqual(self.core.call_names.count("plan_transfer"), 1)

    def test_an_unexpected_lost_or_unknown_shape_is_kept_as_outcome_unknown(self) -> None:
        shapes = (
            ("taskNotFound", Lost(reason="taskNotFound")),
            ("mock", MagicMock()),
            ("string", "garbage"),
        )
        for label, shape in shapes:
            with self.subTest(label):
                key = f"run-{label}:k"
                self.core.calls.clear()
                self.core.execute_result = shape
                reply = self._transfer(key)
                self.assertEqual(reply.response, ERROR_FROM_TOOL)
                self.assertEqual(self._records()[key]["state"], "outcomeUnknown")
                self._transfer(key)
                self.assertEqual(self.core.call_names.count("execute_transfer"), 1)
                self.assertEqual(self.core.call_names.count("plan_transfer"), 1)

    def test_an_exception_from_execute_names_only_its_type(self) -> None:
        self.core.execute_result = RuntimeError("SECRET-TEXT")
        reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("RuntimeError", reply.error_message)
        self.assertNotIn("SECRET-TEXT", reply.error_message)
        self.assertEqual(self._records()[_STEP_KEY]["state"], "submitting")
        self._transfer()
        self.assertEqual(self.core.execute_calls, 1)

    def test_a_plan_that_is_not_a_plan_leaves_no_ledger_file(self) -> None:
        plans = (
            Rejected(stage="local", findings=[]),
            NeedsInput(missing=["robot"]),
            ReadFailed(error={"name": "boom"}),
            Refused(reason="failureLatched", detail={"guid": "g"}),
        )
        for plan in plans:
            with self.subTest(type(plan).__name__):
                self.core.plan_result = plan
                reply = self._transfer()
                self.assertEqual(reply.response, ERROR_FROM_TOOL)
                self.assertFalse(os.path.exists(self.ledger_path))
                self.assertNotIn("execute_transfer", self.core.call_names)

    def test_an_in_flight_refusal_names_the_step_key_that_owns_the_guid(self) -> None:
        other = Ledger(Path(self.ledger_dir))
        now = datetime.now(timezone.utc)
        self.assertTrue(other.claim("other-step", fingerprint="a" * 64, instance="x", now=now))
        other.mark_started(
            "other-step", handle=TaskHandle(guid="g-owner", robot="R1").to_dict(), now=now)
        self.core.execute_result = Refused(reason="inFlight", detail={"guid": "g-owner"})
        reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("g-owner", reply.error_message)
        self.assertIn("step key other-step is still running", reply.error_message)
        self.assertIn("re-run that step to re-attach", reply.error_message)
        self.assertLess(reply.error_message.index("g-owner"),
                        reply.error_message.index("other-step"))
        self.assertNotIn(_STEP_KEY, self._records())
        self.assertIn("other-step", self._records())

    def test_an_in_flight_refusal_with_an_unknown_guid_names_no_step_key(self) -> None:
        self.core.execute_result = Refused(reason="inFlight", detail={"guid": "g-nobody"})
        reply = self._transfer()
        self.assertIn("g-nobody", reply.error_message)
        self.assertNotIn("is still running", reply.error_message)

    def test_a_failed_release_keeps_the_record_and_says_it_will_not_be_re_sent(self) -> None:
        self.core.execute_result = Refused(reason="stackBusy")
        with patch.object(Ledger, "release", side_effect=LedgerError("unwritable", "p")):
            reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("will not be re-sent", reply.error_message)
        self.assertEqual(self._records()[_STEP_KEY]["state"], "submitting")
        self._transfer()
        self.assertEqual(self.core.execute_calls, 1)

    def test_a_failed_outcome_unknown_write_still_says_it_will_not_be_re_sent(self) -> None:
        self.core.execute_result = Lost(reason="submitOutcomeUnknown")
        self.core.latch_result = LatchStatus(
            latched=True, guid=_SUBMIT_GUID, result_kind="lost", reason="submitOutcomeUnknown")
        with patch.object(
                Ledger, "mark_outcome_unknown", side_effect=LedgerError("unwritable", "p")):
            reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn(_SUBMIT_GUID, reply.error_message)
        self.assertIn("will not be re-sent", reply.error_message)
        self.assertEqual(self._records()[_STEP_KEY]["state"], "submitting")

    def test_the_message_suffix_survives_the_300_character_cap(self) -> None:
        self.core.execute_result = Lost(reason="x" * 400)
        self.core.latch_result = LatchStatus(
            latched=True, guid=_SUBMIT_GUID, result_kind="lost", reason="x")
        reply = self._transfer()
        self.assertLessEqual(len(reply.error_message), 300)
        self.assertIn(_SUBMIT_GUID, reply.error_message)
        self.assertTrue(reply.error_message.endswith("will not be re-sent"))


class TestLedgerFailClosed(_TransferTestCase):
    """D-04: a ledger that cannot be trusted refuses the Transfer before any
    core call; a failed write-ahead sends nothing; a failed later write is
    reported even for a ran result."""

    def _record(self, **override: Any) -> dict[str, Any]:
        stamp = datetime.now(timezone.utc).isoformat()
        record: dict[str, Any] = {
            "fingerprint": "a" * 64, "state": "submitting", "instance": "x",
            "handle": None, "result": None, "createdAt": stamp, "updatedAt": stamp}
        record.update(override)
        return record

    def test_every_malformed_ledger_refuses_with_zero_core_calls(self) -> None:
        cases = (
            ("bad-utf8", b"\xff\xfe"),
            ("bad-json", b"{not json"),
            ("version-2", json.dumps({"version": 2, "records": {}}).encode()),
            ("version-true", json.dumps({"version": True, "records": {}}).encode()),
            ("records-list", json.dumps({"version": 1, "records": []}).encode()),
            ("unknown-state", json.dumps(
                {"version": 1, "records": {"k": self._record(state="weird")}}).encode()),
            ("directory", None),
        )
        for label, content in cases:
            with self.subTest(label):
                directory = os.path.join(self._tmpdir.name, f"ledger-{label}")
                path = os.path.join(directory, "stack-ledger.json")
                self.server._ledger_dir = directory
                self.core.calls.clear()
                if content is None:
                    os.makedirs(path)
                else:
                    os.makedirs(directory, mode=0o700)
                    with open(path, "wb") as handle:
                        handle.write(content)
                reply = self._transfer()
                self.assertEqual(reply.response, ERROR_FROM_TOOL)
                self.assertIn(path, reply.error_message)
                self.assertIn("do not delete it", reply.error_message)
                self.assertIn("no transfer was sent", reply.error_message)
                self.assertEqual(self.core.calls, [])
                if content is None:
                    self.assertTrue(os.path.isdir(path))
                else:
                    with open(path, "rb") as handle:
                        self.assertEqual(handle.read(), content)

    def test_a_failed_write_ahead_claim_sends_nothing(self) -> None:
        with patch.object(Ledger, "claim", side_effect=LedgerError("unwritable", "p")):
            reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("no transfer was sent", reply.error_message)
        self.assertEqual(self.core.call_names, ["plan_transfer"])

    def test_a_failed_mark_started_still_waits_once_and_reports_it(self) -> None:
        with patch.object(Ledger, "mark_started", side_effect=LedgerError("unwritable", "p")):
            reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("but the ledger could not record it", reply.error_message)
        self.assertEqual(self.core.call_names.count("wait"), 1)
        self.assertEqual(self._records()[_STEP_KEY]["state"], "submitting")
        self._transfer()
        self.assertEqual(self.core.execute_calls, 1)

    def test_a_failed_mark_done_reports_it_even_for_a_ran_result(self) -> None:
        self.assertIsInstance(self.core.wait_result, Ran)
        with patch.object(Ledger, "mark_done", side_effect=LedgerError("unwritable", "p")):
            reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("but the ledger could not record it", reply.error_message)
        self.assertEqual(self.core.call_names.count("wait"), 1)
        self.assertEqual(self._records()[_STEP_KEY]["state"], "started")
        self._transfer()
        self.assertEqual(self.core.execute_calls, 1)


class TestWaitBudget(_TransferTestCase):
    """D-11: Transfer.timeout_s, else Config.transfer_timeout_s, else 300,
    clamped to 3600; zero means unset."""

    def _wait_timeout(self, key: str, **fields: Any) -> float:
        self.core.calls.clear()
        self.assertEqual(self._transfer(key, **fields).response, SUCCESS)
        waits = [kwargs for name, _a, kwargs in self.core.calls if name == "wait"]
        self.assertEqual(len(waits), 1)
        return float(waits[0]["timeout_s"])

    def test_the_budget_rules(self) -> None:
        cases = (
            ("request", 0.0, {"timeout_s": 42.0}, 42.0),
            ("config", 120.0, {}, 120.0),
            ("default", 0.0, {}, 300.0),
            ("zero-falls-through", 120.0, {"timeout_s": 0.0}, 120.0),
            ("zero-and-unset", 0.0, {"timeout_s": 0.0}, 300.0),
            ("request-clamped", 0.0, {"timeout_s": 1e9}, 3600.0),
            ("config-clamped", 1e6, {}, 3600.0),
            ("request-beats-config", 120.0, {"timeout_s": 42.0}, 42.0),
        )
        for label, config_s, fields, expected in cases:
            with self.subTest(label):
                self.server._transfer_timeout_s = config_s
                self.assertEqual(self._wait_timeout(f"run-{label}:k", **fields), expected)


class TestMotionLock(_TransferTestCase):
    """D-12: the process-wide motion lock is a backstop behind the BUSY status."""

    def test_a_direct_transfer_is_refused_while_the_lock_is_held(self) -> None:
        self.assertTrue(stack_server._MOTION_LOCK.acquire(blocking=False))
        self.addCleanup(stack_server._MOTION_LOCK.release)
        reply = self.server.Transfer(stack_pb2.Command.Transfer(step_key="k"))
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("busy", reply.error_message)
        self.assertEqual(self.core.calls, [])
        self.assertFalse(os.path.exists(self.ledger_path))

    def test_the_lock_is_released_after_every_outcome(self) -> None:
        self.assertEqual(self._transfer("run-ok:k").response, SUCCESS)
        self.assertFalse(stack_server._MOTION_LOCK.locked())
        self.core.execute_result = Refused(reason="stackBusy")
        self.assertEqual(self._transfer("run-refused:k").response, ERROR_FROM_TOOL)
        self.assertFalse(stack_server._MOTION_LOCK.locked())

    def test_an_exception_from_plan_transfer_propagates_and_releases_the_lock(self) -> None:
        self.core.plan_result = RuntimeError("boom")
        fields: dict[str, Any] = dict(_ESTIMATE_FIELDS)
        with self.assertRaises(RuntimeError):
            self.server.Transfer(stack_pb2.Command.Transfer(step_key="k", **fields))
        self.assertFalse(stack_server._MOTION_LOCK.locked())
        reply = self._transfer("run-after:k")
        self.assertEqual(reply.response, DRIVER_ERROR)
        self.assertFalse(stack_server._MOTION_LOCK.locked())


def _write_record(ledger_dir: str, key: str, **fields: Any) -> None:
    """Write (or replace) one record in the ledger file by hand, so a test can
    plant any state, instance, fingerprint or timestamp. Other records stay."""
    stamp = datetime.now(timezone.utc).isoformat()
    record: dict[str, Any] = {
        "fingerprint": "a" * 64, "state": "submitting", "instance": "old-instance",
        "handle": None, "result": None, "createdAt": stamp, "updatedAt": stamp}
    record.update(fields)
    path = os.path.join(ledger_dir, "stack-ledger.json")
    os.makedirs(ledger_dir, mode=0o700, exist_ok=True)
    document: dict[str, Any] = {"version": 1, "records": {}}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            document = json.load(handle)
    document["records"][key] = record
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle)


class _LedgerCase(_TransferTestCase):
    """Shared helpers for the repeat-key tests: the request fingerprint a
    Transfer computes, a planted record, and a call-name tally."""

    def _fp(self) -> str:
        fields: dict[str, Any] = dict(_ESTIMATE_FIELDS)
        request = stack_server._transfer_request(stack_pb2.Command.Transfer(**fields))
        return fingerprint(self.server._endpoint(), request)

    def _seed(self, key: str = _STEP_KEY, **fields: Any) -> None:
        fields.setdefault("fingerprint", self._fp())
        fields.setdefault("instance", self.server._instance)
        _write_record(self.ledger_dir, key, **fields)

    def _at(self, now: datetime, age_s: float) -> str:
        return (now - timedelta(seconds=age_s)).isoformat()

    def _assert_no_motion_calls(self) -> None:
        for name in ("plan_transfer", "execute_transfer", "wait", "wait_transfer"):
            self.assertNotIn(name, self.core.call_names)


_NOW = datetime(2026, 10, 29, 12, 0, 0, tzinfo=timezone.utc)


class TestRepeatKey(_LedgerCase):
    """XFR-03 / D-07 as amended by 05-SPIKE.md 6b: a repeated step key never
    submits. A different request is INVALID_ARGUMENTS; a done+ran record inside
    the replay window replays; every other state is refused with a next action,
    and no refusal calls plan, execute, wait or wait_transfer (A-6)."""

    def _transfer_at(self, now: datetime, **fields: Any) -> Any:
        with patch.object(stack_server, "_utcnow", return_value=now):
            return self._transfer(**fields)

    def test_a_different_request_is_invalid_arguments_for_every_state(self) -> None:
        handle = TaskHandle(guid=_GUID, robot="R1", estimated_s=30.0).to_dict()
        ran = Ran(task=_ran_snapshot()).to_dict()
        states = (
            ("submitting", {}),
            ("started", {"handle": handle}),
            ("outcomeUnknown", {"latchGuid": _SUBMIT_GUID}),
            ("done-ran", {"handle": handle, "result": ran}),
            ("done-failed", {"handle": handle, "result": Failed(task=_snapshot("g-task")).to_dict()}),
        )
        for label, extra in states:
            with self.subTest(label):
                key = f"run-1:{label}"
                state = "done" if label.startswith("done") else label
                self._seed(key, state=state, fingerprint="b" * 64, **extra)
                self.core.calls.clear()
                reply = self._transfer(key)
                self.assertEqual(reply.response, tool_base_pb2.INVALID_ARGUMENTS)
                self.assertEqual(self.core.calls, [])
                self.assertEqual(reply.meta_data["stepKey"], key)

    def test_the_same_request_against_another_stack_endpoint_is_a_mismatch(self) -> None:
        self.assertEqual(self._transfer().response, SUCCESS)
        self.core.calls.clear()
        self.server.config = stack_pb2.Config(host="127.0.0.2")
        reply = self._transfer()
        self.assertEqual(reply.response, tool_base_pb2.INVALID_ARGUMENTS)
        self.assertIn("different request or STACK", reply.error_message)
        self.assertEqual(self.core.calls, [])

    def test_a_done_ran_record_inside_the_window_is_replayed(self) -> None:
        ran = Ran(task=_ran_snapshot()).to_dict()
        self._seed(state="done", handle=TaskHandle(guid=_GUID).to_dict(), result=ran,
                    updatedAt=self._at(_NOW, 1))
        reply = self._transfer_at(_NOW)
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(reply.error_message, "")
        self.assertEqual(reply.meta_data, _struct({
            "stepKey": _STEP_KEY, "ledgerState": "done", "result": ran, "replayed": True}))
        self.assertEqual(self.core.calls, [])

    def test_a_done_ran_record_at_the_window_edges(self) -> None:
        ran = Ran(task=_ran_snapshot()).to_dict()
        cases = (("599.9 s", 599.9, SUCCESS), ("600 s", 600.0, ERROR_FROM_TOOL),
                 ("601 s", 601.0, ERROR_FROM_TOOL), ("future-dated", -5.0, ERROR_FROM_TOOL))
        for label, age, expected in cases:
            with self.subTest(label):
                self._seed(state="done", handle=TaskHandle(guid=_GUID).to_dict(), result=ran,
                            updatedAt=self._at(_NOW, age))
                reply = self._transfer_at(_NOW)
                self.assertEqual(reply.response, expected)
                if expected == ERROR_FROM_TOOL:
                    self.assertIn("already completed at", reply.error_message)
                    self.assertIn("mint a new step key", reply.error_message)
                self.assertEqual(self.core.calls, [])

    def test_a_submitting_record_is_refused_and_never_re_sent(self) -> None:
        self._seed(state="submitting")
        reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        for fragment in ("outcome unknown", "GetFailureLatch", "will not be re-sent"):
            self.assertIn(fragment, reply.error_message)
        self.assertNotIn("tool restarted", reply.error_message)
        self._assert_no_motion_calls()
        self.assertEqual(reply.meta_data, _struct({"stepKey": _STEP_KEY, "ledgerState": "submitting"}))

    def test_an_outcome_unknown_record_names_its_recorded_latch_guid(self) -> None:
        self._seed(state="outcomeUnknown", latchGuid=_SUBMIT_GUID)
        reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn(_SUBMIT_GUID, reply.error_message)
        self.assertIn("AcknowledgeFailure", reply.error_message)
        self.assertIn("will not be re-sent", reply.error_message)
        self._assert_no_motion_calls()

    def test_an_outcome_unknown_record_without_a_latch_guid_says_to_read_the_latch(self) -> None:
        self._seed(state="outcomeUnknown", latchGuid=None)
        reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("no latch guid was recorded", reply.error_message)
        self.assertIn("GetFailureLatch", reply.error_message)
        self._assert_no_motion_calls()

    def test_a_done_failed_record_repeats_kind_reason_and_task_guid(self) -> None:
        lost = Lost(reason="taskNotFound", handle=TaskHandle(guid="g-task")).to_dict()
        for label, result, kind in (
                ("failed", Failed(task=_snapshot("g-task"), reason="robotError").to_dict(), "failed"),
                ("aborted", Aborted(task=_snapshot("g-task")).to_dict(), "aborted"),
                ("lost", lost, "lost")):
            with self.subTest(label):
                self._seed(state="done", handle=TaskHandle(guid="g-task").to_dict(), result=result)
                self.core.calls.clear()
                self.core.latch_result = LatchStatus(latched=True, guid="g-task", result_kind=kind)
                reply = self._transfer()
                self.assertEqual(reply.response, ERROR_FROM_TOOL)
                message = reply.error_message
                self.assertIn(kind, message)
                if result.get("reason"):
                    self.assertIn(str(result["reason"]), message)
                self.assertIn("latched guid g-task", message)
                self.assertIn("AcknowledgeFailure", message)
                self.assertIn("new step key", message)
                self.assertIn("task guid g-task", message)
                self._assert_no_motion_calls()
                self.assertLessEqual(self.core.call_names.count("latch_status"), 1)

    def test_a_key_that_differs_by_a_trailing_space_takes_the_fresh_path(self) -> None:
        key = "run-1:stack-1"
        self._seed(key, state="done", result=Ran(task=_ran_snapshot()).to_dict())
        reply = self._transfer(key + " ")
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(self.core.call_names.count("plan_transfer"), 1)
        self.assertEqual(self.core.execute_calls, 1)
        self.assertEqual(sorted(self._records()), [key, key + " "])

    def test_a_280_character_step_key_keeps_every_refusal_within_300_characters(self) -> None:
        key = "k" * 280
        ran = Ran(task=_ran_snapshot()).to_dict()
        failed = Failed(task=_snapshot(_GUID)).to_dict()
        cases = (
            ("submitting", {"state": "submitting"}, None),
            ("outcomeUnknown", {"state": "outcomeUnknown", "latchGuid": _SUBMIT_GUID}, _SUBMIT_GUID),
            ("completed", {"state": "done", "result": ran, "updatedAt": self._at(_NOW, 9999)}, None),
            ("failed", {"state": "done", "result": failed}, _GUID),
            ("mismatch", {"state": "submitting", "fingerprint": "b" * 64}, None),
        )
        for label, fields, guid in cases:
            with self.subTest(label):
                self._seed(key, **fields)
                self.core.latch_result = LatchStatus(latched=True, guid=_GUID, result_kind="failed")
                with patch.object(stack_server, "_utcnow", return_value=_NOW):
                    reply = self._transfer(key)
                self.assertLessEqual(len(reply.error_message), 300)
                if guid:
                    self.assertIn(guid, reply.error_message)

    def test_a_repeat_of_a_just_completed_step_replays_without_a_core_call(self) -> None:
        self.assertEqual(self._transfer().response, SUCCESS)
        self.assertEqual(self.core.execute_calls, 1)
        before = len(self.core.calls)
        reply = self._transfer()
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(reply.meta_data["replayed"], True)
        self.assertEqual(len(self.core.calls), before)
        self.assertEqual(self.core.execute_calls, 1)


class TestTimedOutReattach(_LedgerCase):
    """XFR-06 / D-11 / A-1: a timedOut wait leaves the arm running and the record
    started; re-running the step re-attaches read-only (wait_transfer only,
    never plan or execute) and finishes it. The re-attach loop is bounded by the
    budget in 300 s slices and never calls with a non-positive timeout."""

    def _timed_out(self) -> TimedOut:
        return TimedOut(handle=TaskHandle(guid=_GUID, robot="R1", estimated_s=30.0))

    def _start_then_time_out(self, key: str = _STEP_KEY) -> None:
        """A fresh Transfer whose wait times out: the record is left started."""
        self.core.wait_result = self._timed_out()
        reply = self._transfer(key)
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertEqual(self._records()[key]["state"], "started")
        self.core.calls.clear()

    def test_a_timed_out_wait_is_still_running_and_the_record_stays_started(self) -> None:
        self.core.wait_result = self._timed_out()
        reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("still running", reply.error_message)
        self.assertIn("re-run this step to re-attach", reply.error_message)
        self.assertIn(_GUID, reply.error_message)
        self.assertEqual(reply.meta_data["kind"], "timedOut")
        self.assertEqual(self._records()[_STEP_KEY]["state"], "started")

    def test_re_running_a_timed_out_step_re_attaches_and_finishes_it(self) -> None:
        self._start_then_time_out()
        self.core.wait_transfer_results = [Ran(task=_ran_snapshot())]
        reply = self._transfer()
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(reply.error_message, "")
        self.assertEqual(reply.meta_data, _struct(Ran(task=_ran_snapshot()).to_dict()))
        self.assertEqual(self.core.call_names, ["wait_transfer"])
        self.assertEqual(self.core.calls[0][1], (_GUID,))
        self.assertEqual(self.core.calls[0][2], {"timeout_s": 300.0})
        self.assertEqual(self._records()[_STEP_KEY]["state"], "done")
        self.assertEqual(self._records()[_STEP_KEY]["result"], Ran(task=_ran_snapshot()).to_dict())

    def _time_out_every_slice(self, clock: list[float]) -> list[float]:
        """Make every wait_transfer slice time out after consuming its whole
        timeout on the fake clock. Returns the list the timeouts are logged to."""
        timeouts: list[float] = []

        def _wait_transfer(guid: str, *, timeout_s: float) -> Any:
            timeouts.append(timeout_s)
            clock[0] += timeout_s
            return self._timed_out()

        self.core.wait_result = _wait_transfer
        return timeouts

    def test_a_timed_out_step_is_sent_exactly_once_in_total(self) -> None:
        self.core.wait_result = self._timed_out()
        self._transfer()
        clock = [1000.0]
        self._time_out_every_slice(clock)
        with patch.object(stack_server, "_monotonic", side_effect=lambda: clock[0]):
            self.assertEqual(self._transfer().response, ERROR_FROM_TOOL)
        self.core.wait_transfer_results = [Ran(task=_ran_snapshot())]
        self.assertEqual(self._transfer().response, SUCCESS)
        replay = self._transfer()
        self.assertEqual(replay.response, SUCCESS)
        self.assertEqual(replay.meta_data["replayed"], True)
        self.assertEqual(self.core.execute_calls, 1)
        self.assertEqual(self.core.call_names.count("plan_transfer"), 1)

    def test_the_re_attach_never_plans_executes_or_waits_on_a_handle(self) -> None:
        self._start_then_time_out()
        clock = [1000.0]
        self._time_out_every_slice(clock)
        with patch.object(stack_server, "_monotonic", side_effect=lambda: clock[0]):
            reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("still running", reply.error_message)
        self.assertEqual(set(self.core.call_names), {"wait_transfer"})

    def test_the_budget_is_spent_in_slices_and_never_called_with_nothing_left(self) -> None:
        self._start_then_time_out()
        clock = [1000.0]
        timeouts = self._time_out_every_slice(clock)
        with patch.object(stack_server, "_monotonic", side_effect=lambda: clock[0]):
            reply = self._transfer(timeout_s=650)
        self.assertEqual(timeouts, [300.0, 300.0, 50.0])
        self.assertTrue(all(t > 0 for t in timeouts))
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("still running", reply.error_message)
        self.assertEqual(self._records()[_STEP_KEY]["state"], "started")

    def test_a_loop_with_no_budget_makes_no_call_and_reads_as_timed_out(self) -> None:
        result = self.server._reattach_loop(self.core, _GUID, 0.0)
        self.assertIsInstance(result, TimedOut)
        self.assertEqual(result.handle.guid, _GUID)
        self.assertEqual(self.core.calls, [])

    def test_a_poll_failure_leaves_the_record_started_and_a_re_run_re_attaches(self) -> None:
        self._start_then_time_out()
        self.core.latch_result = LatchStatus(
            latched=True, guid=_SUBMIT_GUID, result_kind="lost", reason="pollFailed")
        lost = Lost(reason="pollFailed", handle=TaskHandle(guid=_GUID))
        self.core.wait_transfer_results = [lost]
        reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertEqual(self.core.call_names.count("wait_transfer"), 1)
        self.assertIn(f"latched guid {_SUBMIT_GUID}", reply.error_message)
        self.assertIn("re-run this step to re-attach", reply.error_message)
        self.assertEqual(self._records()[_STEP_KEY]["state"], "started")
        self.core.calls.clear()
        self.core.wait_transfer_results = [Ran(task=_ran_snapshot())]
        again = self._transfer()
        self.assertEqual(again.response, SUCCESS)
        self.assertEqual(self.core.call_names, ["wait_transfer"])
        self.assertEqual(self._records()[_STEP_KEY]["state"], "done")

    def test_the_fresh_path_keeps_pollfailed_started_and_ends_tasknotfound(self) -> None:
        cases = (("pollFailed", "started"), ("taskNotFound", "done"))
        for reason, state in cases:
            with self.subTest(reason):
                key = f"run-1:{reason}"
                self.core.wait_result = Lost(reason=reason, handle=TaskHandle(guid=_GUID))
                reply = self._transfer(key)
                self.assertEqual(reply.response, ERROR_FROM_TOOL)
                self.assertEqual(self._records()[key]["state"], state)

    def test_a_failed_mark_done_after_a_re_attach_keeps_the_record_started(self) -> None:
        self._start_then_time_out()
        self.core.wait_transfer_results = [Ran(task=_ran_snapshot())]
        with patch.object(Ledger, "mark_done", side_effect=LedgerError("unwritable", "p")):
            reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("but the ledger could not record it", reply.error_message)
        self.assertEqual(self._records()[_STEP_KEY]["state"], "started")
        self.assertEqual(self.core.call_names, ["wait_transfer"])

    def test_a_re_attach_to_a_failed_transfer_reports_the_latch_and_records_it_done(self) -> None:
        self._start_then_time_out()
        self.core.latch_result = LatchStatus(latched=True, guid=_GUID, result_kind="failed")
        self.core.wait_transfer_results = [Failed(task=_snapshot(_GUID))]
        reply = self._transfer()
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn(f"latched guid {_GUID}", reply.error_message)
        self.assertEqual(self._records()[_STEP_KEY]["state"], "done")
        self.assertNotIn("tool restarted", reply.error_message)

    def test_a_same_instance_re_attach_to_ran_carries_no_restart_flag(self) -> None:
        self._start_then_time_out()
        self.core.wait_transfer_results = [Ran(task=_ran_snapshot())]
        reply = self._transfer()
        self.assertNotIn("reattachedAfterRestart", reply.meta_data)


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


class TestReadCommands(_RealModeGrpcTestCase):
    """STK-03: each read calls exactly one mapped core method and returns the
    core's to_dict() untouched as meta."""

    def _read(self, **command: Any) -> Any:
        return self.stub.ExecuteCommand(self._stack(**command))

    def _only_call(self, name: str) -> Any:
        self.assertEqual([c[0] for c in self.service.mock_calls], [name])
        return self.service.mock_calls[0]

    def test_robot_states_and_manager_state_take_no_arguments(self) -> None:
        self.service.robot_states.return_value = RobotStates(robots=[])
        self._read(get_robot_states=stack_pb2.Command.GetRobotStates())
        self.assertEqual(self._only_call("robot_states").args, ())
        self.assertEqual(self.service.robot_states.call_args.kwargs, {})
        self.service.reset_mock()
        self.service.manager_state.return_value = ManagerState(
            mode="Idle", recovery=None, api_version="3")
        self._read(get_manager_state=stack_pb2.Command.GetManagerState())
        self.assertEqual(self._only_call("manager_state").args, ())
        self.assertEqual(self.service.manager_state.call_args.kwargs, {})

    def test_refresh_flag_reaches_the_core_as_a_keyword(self) -> None:
        reads = (
            ("devices", "list_devices", stack_pb2.Command.ListDevices,
             DeviceTree(devices=(), ambiguous=[], api_version="3")),
            ("labware_profiles", "list_labware_profiles",
             stack_pb2.Command.ListLabwareProfiles, LabwareProfiles(profiles=[])),
            ("transfer_profiles", "list_transfer_profiles",
             stack_pb2.Command.ListTransferProfiles, TransferProfiles(profiles=[])),
        )
        for method, field, message, result in reads:
            getattr(self.service, method).return_value = result
            for label, kwargs, expected in (
                ("unset", {}, False), ("true", {"refresh": True}, True),
                ("false", {"refresh": False}, False),
            ):
                with self.subTest(method=method, refresh=label):
                    self.service.reset_mock()
                    reply = self._read(**{field: message(**kwargs)})
                    self.assertEqual(reply.response, SUCCESS)
                    self._only_call(method)
                    call = getattr(self.service, method).call_args
                    self.assertEqual(call.args, ())
                    self.assertEqual(call.kwargs, {"refresh": expected})

    def test_presence_robot_blank_reaches_the_core_as_none(self) -> None:
        self.service.labware_presence.return_value = ReadFailed(
            error={"status": None, "name": "malformedPresence"})
        for label, kwargs in (("unset", {}), ("empty", {"robot": ""}),
                              ("blank", {"robot": "   "})):
            with self.subTest(label):
                self.service.reset_mock()
                self._read(get_labware_presence=stack_pb2.Command.GetLabwarePresence(**kwargs))
                self.service.labware_presence.assert_called_once_with(None)
                self.assertEqual(len(self.service.mock_calls), 1)
        self.service.reset_mock()
        self.service.labware_presence.return_value = LabwarePresence(
            robot_name="R1", has_labware=True)
        self._read(get_labware_presence=stack_pb2.Command.GetLabwarePresence(robot="R1"))
        self.service.labware_presence.assert_called_once_with("R1")

    def test_each_read_returns_success_with_core_meta(self) -> None:
        cases = (
            ("robot_states", "get_robot_states", stack_pb2.Command.GetRobotStates(),
             RobotStates(robots=[{"robotName": "R1", "state": "Idle"}])),
            ("devices", "list_devices", stack_pb2.Command.ListDevices(),
             DeviceTree(devices=(), ambiguous=["dupDeck"], api_version="3")),
            ("labware_profiles", "list_labware_profiles",
             stack_pb2.Command.ListLabwareProfiles(),
             LabwareProfiles(profiles=[LabwareProfile(name="plate96", grip_force=4.5)])),
            ("transfer_profiles", "list_transfer_profiles",
             stack_pb2.Command.ListTransferProfiles(),
             TransferProfiles(profiles=[TransferProfile(name="slow", fields={"v": 1.5})])),
            ("labware_presence", "get_labware_presence",
             stack_pb2.Command.GetLabwarePresence(robot="R1"),
             LabwarePresence(robot_name="R1", has_labware=True)),
        )
        for method, field, message, result in cases:
            with self.subTest(method):
                self.service.reset_mock()
                getattr(self.service, method).return_value = result
                reply = self._read(**{field: message})
                self.assertEqual(reply.response, SUCCESS)
                self.assertEqual(reply.error_message, "")
                self.assertEqual(reply.meta_data, _struct(result.to_dict()))
                self.assertEqual(len(self.service.mock_calls), 1)
                self.assertEqual(self._health().status, READY)

    def test_list_order_and_duplicates_are_preserved(self) -> None:
        self.service.robot_states.return_value = RobotStates(robots=[
            {"name": "R2"}, {"name": "R1"}, {"name": "R1"}])
        self.service.labware_profiles.return_value = LabwareProfiles(profiles=[
            LabwareProfile(name=n) for n in ("zeta", "alpha", "zeta")])
        self.service.transfer_profiles.return_value = TransferProfiles(profiles=[
            TransferProfile(name=n) for n in ("zeta", "alpha", "zeta")])
        robots = MessageToDict(self._read(
            get_robot_states=stack_pb2.Command.GetRobotStates()).meta_data)
        self.assertEqual([r["name"] for r in robots["robots"]], ["R2", "R1", "R1"])
        labware = MessageToDict(self._read(
            list_labware_profiles=stack_pb2.Command.ListLabwareProfiles()).meta_data)
        self.assertEqual([p["name"] for p in labware["profiles"]], ["zeta", "alpha", "zeta"])
        transfer = MessageToDict(self._read(
            list_transfer_profiles=stack_pb2.Command.ListTransferProfiles()).meta_data)
        self.assertEqual([p["name"] for p in transfer["profiles"]], ["zeta", "alpha", "zeta"])

    def test_has_labware_false_is_kept_not_dropped(self) -> None:
        self.service.labware_presence.return_value = LabwarePresence(
            robot_name="R1", has_labware=False)
        reply = self._read(
            get_labware_presence=stack_pb2.Command.GetLabwarePresence(robot="R1"))
        self.assertEqual(reply.response, SUCCESS)
        self.assertIn("hasLabware", reply.meta_data)
        self.assertIs(reply.meta_data["hasLabware"], False)

    def test_presence_unavailable_is_an_error_without_has_labware(self) -> None:
        self.service.labware_presence.return_value = ReadFailed(
            error={"status": None, "name": "malformedPresence", "family": "http",
                   "code": None, "detail": None},
            message="presence unavailable")
        reply = self._read(
            get_labware_presence=stack_pb2.Command.GetLabwarePresence(robot="R1"))
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertNotIn("hasLabware", reply.meta_data)
        self.assertTrue(reply.error_message.startswith("stack: readFailed"))


class TestOneToOneSurface(_StackTestCase):
    def test_map_has_nine_keys_matching_the_oneof_names(self) -> None:
        mapping = stack_server.COMMAND_TO_SERVICE_METHOD
        self.assertEqual(len(mapping), 9)
        oneof = stack_pb2.Command.DESCRIPTOR.oneofs_by_name["command"].fields
        names = {f.message_type.name for f in oneof}
        self.assertEqual(set(mapping) | {"Transfer"}, names)

    def test_every_oneof_message_has_a_handler_and_the_sets_are_disjoint(self) -> None:
        oneof = stack_pb2.Command.DESCRIPTOR.oneofs_by_name["command"].fields
        names = {f.message_type.name for f in oneof}
        self.assertEqual(len(names), 10)
        server = StackServer()
        for name in names:
            self.assertTrue(callable(getattr(server, name, None)), name)
        mapped = set(stack_server.COMMAND_TO_SERVICE_METHOD)
        self.assertNotIn("Transfer", mapped)
        self.assertEqual(mapped | {"Transfer"}, names)

    def test_every_key_is_a_server_method_and_every_value_a_service_method(self) -> None:
        server = StackServer()
        for name, method in stack_server.COMMAND_TO_SERVICE_METHOD.items():
            self.assertTrue(callable(getattr(server, name)), name)
            self.assertTrue(hasattr(StackService, method), method)
            self.assertNotIn(method, _FORBIDDEN_SERVICE_CALLS)

    def test_each_mapped_command_records_exactly_one_mapped_call(self) -> None:
        results = {
            "manager_state": ManagerState(mode="Idle", recovery=None, api_version="3"),
            "robot_states": RobotStates(robots=[]),
            "devices": DeviceTree(devices=(), ambiguous=[], api_version="3"),
            "labware_profiles": LabwareProfiles(profiles=[]),
            "transfer_profiles": TransferProfiles(profiles=[]),
            "labware_presence": LabwarePresence(robot_name="R1", has_labware=False),
            "estimate_transfer": Estimated(estimated_time="00:00:01", guid=None),
            "latch_status": LatchStatus(latched=False),
            "acknowledge_failure": FailureAcknowledged(
                guid="g", result_kind="failed", explanation=None),
        }
        messages = {
            "GetManagerState": stack_pb2.Command.GetManagerState(),
            "GetRobotStates": stack_pb2.Command.GetRobotStates(),
            "ListDevices": stack_pb2.Command.ListDevices(),
            "ListLabwareProfiles": stack_pb2.Command.ListLabwareProfiles(),
            "ListTransferProfiles": stack_pb2.Command.ListTransferProfiles(),
            "GetLabwarePresence": stack_pb2.Command.GetLabwarePresence(robot="R1"),
            "GetTransferEstimate": stack_pb2.Command.GetTransferEstimate(**_ESTIMATE_FIELDS),
            "GetFailureLatch": stack_pb2.Command.GetFailureLatch(),
            "AcknowledgeFailure": stack_pb2.Command.AcknowledgeFailure(
                guid="g", arm_inspected="yes"),
        }
        self.assertEqual(set(messages), set(stack_server.COMMAND_TO_SERVICE_METHOD))
        for command, method in stack_server.COMMAND_TO_SERVICE_METHOD.items():
            with self.subTest(command=command):
                server = StackServer()
                service = MagicMock(spec=StackService)
                getattr(service, method).return_value = results[method]
                server.service = service
                server.config = stack_pb2.Config(host="127.0.0.1")
                reply = getattr(server, command)(messages[command])
                self.assertEqual(reply.response, SUCCESS)
                self.assertEqual([c[0] for c in service.mock_calls], [method])
                if method == "acknowledge_failure":
                    self.assertEqual(service.mock_calls,
                                     [mock_call.acknowledge_failure("g", confirm=True)])


_SENTINEL = "AGENT-WORDS-SENTINEL"


def _snapshot(guid: str = "g-task") -> TaskSnapshot:
    return TaskSnapshot(guid=guid, state="failed", raw_state="failed", error_code=1,
                        error_name="boom", description=_SENTINEL, elapsed="00:00:01")


class _DictResult:
    """A stub result whose to_dict returns whatever it was given."""

    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def to_dict(self) -> Any:
        return self._payload


class TestResultMapping(_StackTestCase):
    """STK-07: one explicit table. The allowlist is SUCCESS with an empty
    message; every other kind is one structured ERROR_FROM_TOOL line."""

    SUCCESS_RESULTS = (
        ManagerState(mode="Idle", recovery=None, api_version="3"),
        DeviceTree(devices=(), ambiguous=[], api_version="3"),
        RobotStates(robots=[{"robotName": "R1", "state": "Idle"}]),
        LabwareProfiles(profiles=[LabwareProfile(name="plate96")]),
        TransferProfiles(profiles=[TransferProfile(name="slow")]),
        LabwarePresence(robot_name="R1", has_labware=False),
        Estimated(estimated_time="00:00:48", guid=None, advisories=[], seconds=48.0),
        FailureAcknowledged(guid="g1", result_kind="failed", explanation=_SENTINEL),
        LatchStatus(latched=False),
        LatchStatus(latched=True, guid="submit-0123456789abcdef", result_kind="lost",
                    reason="submitOutcomeUnknown", explanation=_SENTINEL),
        Ran(task=_snapshot()),
    )

    def _failure_results(self) -> list[Any]:
        handle = TaskHandle(guid="g-handle")
        return [
            ReadFailed(error={"status": 500, "name": "boom"}, message=_SENTINEL),
            Refused(reason="failureLatched", state="x", detail={"guid": "g-latched"}),
            Rejected(stage="local", findings=[{"name": "stackArmNotFound"}]),
            NeedsInput(missing=["robot"], detail=_SENTINEL),
            Lost(reason="taskNotFound", handle=handle, explanation=_SENTINEL),
            Lost(reason="submitOutcomeUnknown", handle=None),
            Failed(task=_snapshot(), explanation=_SENTINEL),
            Aborted(task=_snapshot()),
            Cancelled(handle=handle),
            TimedOut(handle=handle),
            KnowledgeRefreshed(),
            ValidationReport(),
            CancelRequested(guid="g-cancel", confirmed=False),
            TaskHandle(guid="g-handle", kind="transfer"),
        ]

    def test_allowlisted_kinds_are_success_with_empty_message_and_core_meta(self) -> None:
        self.assertEqual(len(self.SUCCESS_RESULTS), 11)
        for result in self.SUCCESS_RESULTS:
            with self.subTest(kind=result.to_dict()["kind"]):
                reply = _result_reply(result)
                self.assertEqual(reply.response, SUCCESS)
                self.assertEqual(reply.error_message, "")
                self.assertEqual(reply.meta_data, _struct(result.to_dict()))
                self.assertTrue(reply.return_reply)

    def test_every_other_core_kind_is_error_from_tool_with_core_meta(self) -> None:
        for result in self._failure_results():
            kind = result.to_dict()["kind"]
            with self.subTest(kind=kind):
                reply = _result_reply(result)
                self.assertEqual(reply.response, ERROR_FROM_TOOL)
                self.assertTrue(reply.error_message.startswith(f"stack: {kind}"),
                                reply.error_message)
                self.assertEqual(reply.meta_data, _struct(result.to_dict()))

    def test_unknown_and_case_variant_kinds_are_never_success(self) -> None:
        for kind in ("brandNewKind", "ManagerState", "managerstate", " managerState",
                     "managerState ", "RAN", "LatchStatus", "latchstatus", "latchStatus "):
            with self.subTest(kind=kind):
                reply = _result_reply(_DictResult({"kind": kind}))
                self.assertEqual(reply.response, ERROR_FROM_TOOL)
                self.assertTrue(reply.error_message.startswith("stack:"))
                self.assertNotEqual(reply.error_message, "")
        for payload in ({"kind": 7}, {}, {"kind": ""}, {"kind": None}):
            with self.subTest(payload=payload):
                reply = _result_reply(_DictResult(payload))
                self.assertEqual(reply.response, ERROR_FROM_TOOL)
                self.assertEqual(reply.error_message, "stack: unrecognised result")

    def test_non_result_objects_are_unrecognised_with_empty_meta(self) -> None:
        for label, obj in (("list", _DictResult(["kind", "ran"])), ("object", object()),
                           ("magicmock", MagicMock()), ("none", None), ("str", "ran")):
            with self.subTest(label):
                reply = _result_reply(obj)
                self.assertEqual(reply.response, ERROR_FROM_TOOL)
                self.assertEqual(reply.error_message, "stack: unrecognised result")
                self.assertEqual(len(reply.meta_data), 0)

    def test_message_shape_is_one_bounded_line_with_kind_reason_guid_in_order(self) -> None:
        reply = _result_reply(Refused(reason="failureLatched", detail={"guid": "g-latched"}))
        self.assertEqual(reply.error_message, "stack: refused (failureLatched), guid g-latched")
        reply = _result_reply(Lost(reason="taskNotFound", handle=TaskHandle(guid="g-handle")))
        message = reply.error_message
        self.assertLess(message.index("stack: lost"), message.index("(taskNotFound)"))
        self.assertLess(message.index("(taskNotFound)"), message.index("guid g-handle"))
        for result in self._failure_results():
            with self.subTest(kind=result.to_dict()["kind"]):
                message = _result_reply(result).error_message
                self.assertNotEqual(message, "")
                self.assertNotIn("\n", message)
                self.assertNotIn("\r", message)
                self.assertLessEqual(len(message), 300)

    def test_absent_reason_and_guid_are_omitted_not_rendered_as_none(self) -> None:
        reply = _result_reply(Lost(reason="submitOutcomeUnknown", handle=None))
        self.assertEqual(reply.error_message, "stack: lost (submitOutcomeUnknown)")
        for result in (NeedsInput(missing=[]), Rejected(stage="local"),
                       ReadFailed(error={"status": None, "name": None}),
                       KnowledgeRefreshed(), TaskHandle(guid="")):
            with self.subTest(kind=result.to_dict()["kind"]):
                message = _result_reply(result).error_message
                self.assertNotIn("None", message)
                self.assertNotIn("null", message)
                self.assertNotIn("guid", message)
                self.assertNotEqual(message, "")

    def test_agent_worded_text_never_reaches_the_message(self) -> None:
        stuffed = [
            ReadFailed(error={"status": 500, "name": "boom", "detail": _SENTINEL},
                       message=_SENTINEL),
            Refused(reason="failureLatched", state=_SENTINEL,
                    detail={"guid": "g", "message": _SENTINEL, "explanation": _SENTINEL}),
            Rejected(stage=_SENTINEL, findings=[{"name": "f", "message": _SENTINEL,
                                                  "detail": _SENTINEL}],
                     advisories=[{"message": _SENTINEL}]),
            NeedsInput(missing=["robot"], detail=_SENTINEL),
            Lost(reason="taskNotFound", explanation=_SENTINEL, detail={"d": _SENTINEL}),
            Failed(task=_snapshot(), explanation=_SENTINEL, context={"c": _SENTINEL}),
            Aborted(task=_snapshot()),
            _DictResult({"kind": "failed", "explanation": _SENTINEL, "message": _SENTINEL,
                         "detail": _SENTINEL}),
        ]
        for result in stuffed:
            with self.subTest(kind=result.to_dict()["kind"]):
                self.assertNotIn(_SENTINEL, _result_reply(result).error_message)

    def test_hints_follow_the_guid_part(self) -> None:
        self.assertEqual(_result_reply(NeedsInput(missing=["robot", "source"])).error_message,
                         "stack: needsInput; missing: robot, source")
        self.assertEqual(
            _result_reply(Rejected(stage="local", findings=[
                {"name": "stackArmNotFound"}, {"name": "second"}])).error_message,
            "stack: rejected; finding: stackArmNotFound")
        self.assertEqual(
            _result_reply(ReadFailed(error={"status": None, "name": "ConnectError"})
                          ).error_message,
            "stack: readFailed; error: ConnectError")
        self.assertEqual(
            _result_reply(ReadFailed(error={"status": 503, "name": "Busy"})).error_message,
            "stack: readFailed; error: Busy (HTTP 503)")
        # The hint sits after kind, reason and guid when those are present.
        message = _result_reply(_DictResult({
            "kind": "needsInput", "reason": "why", "guid": "g9", "missing": ["robot"],
        })).error_message
        self.assertEqual(message, "stack: needsInput (why), guid g9; missing: robot")

    def test_hint_edge_cases(self) -> None:
        for payload, expected in (
            ({"kind": "needsInput", "missing": []}, "stack: needsInput"),
            ({"kind": "needsInput", "missing": ["", 3, None, "a"]}, "stack: needsInput; missing: a"),
            ({"kind": "needsInput", "missing": "robot"}, "stack: needsInput"),
            ({"kind": "rejected", "findings": []}, "stack: rejected"),
            ({"kind": "rejected", "findings": ["x"]}, "stack: rejected"),
            ({"kind": "rejected", "findings": [{"name": 5}]}, "stack: rejected"),
            ({"kind": "readFailed", "error": "oops"}, "stack: readFailed"),
            ({"kind": "readFailed", "error": {"name": "E", "status": True}},
             "stack: readFailed; error: E"),
            ({"kind": "readFailed", "error": {"status": 404}}, "stack: readFailed"),
        ):
            with self.subTest(payload=payload):
                self.assertEqual(_result_reply(_DictResult(payload)).error_message, expected)

    def test_control_characters_collapse_and_long_hints_are_capped(self) -> None:
        reply = _result_reply(Refused(reason="a\nb\r\nc\rd", detail={"guid": "g\n1"}))
        self.assertNotIn("\n", reply.error_message)
        self.assertNotIn("\r", reply.error_message)
        reply = _result_reply(NeedsInput(missing=["x" * 400]))
        self.assertLessEqual(len(reply.error_message), 300)
        self.assertTrue(reply.error_message.endswith("..."))
        self.assertTrue(reply.error_message.startswith("stack: needsInput; missing: xxx"))

    def test_success_empty_message_survives_the_wire(self) -> None:
        server = StackServer()
        service = MagicMock(spec=StackService)
        server.service = service
        server.config = stack_pb2.Config(host="127.0.0.1")
        server.status = READY
        stub = _serve_in_process(self, server)
        command = tool_base_pb2.Command(stack=stack_pb2.Command(
            get_manager_state=stack_pb2.Command.GetManagerState()))
        for result in (ManagerState(mode="Idle", recovery=None, api_version="3"),
                       ReadFailed(error={"status": None, "name": "X"})):
            service.manager_state.return_value = result
            reply = stub.ExecuteCommand(command)
            if result.kind == "managerState":
                self.assertEqual(reply.response, SUCCESS)
                self.assertEqual(reply.error_message, "")
                self.assertEqual(reply.meta_data, _struct(result.to_dict()))
            else:
                self.assertEqual(reply.response, ERROR_FROM_TOOL)
                self.assertEqual(reply.error_message, "stack: readFailed; error: X")


if __name__ == "__main__":
    unittest.main()


class _SimulatedGrpcTestCase(_StackTestCase):
    """Shared simulated-mode in-process gRPC fixture: open_service is replaced
    by a MagicMock that must never be called, and tools.base_server.time.sleep
    is faked so the constant estimates are recorded, not slept. Declares no
    tests."""

    def setUp(self) -> None:
        super().setUp()
        self.open_service = MagicMock()
        patcher = patch("tools.stack.server.open_service", self.open_service)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.sleeps: list[float] = []
        time_patcher = patch(
            "tools.base_server.time",
            types.SimpleNamespace(time=time.time, sleep=self._fake_sleep))
        time_patcher.start()
        self.addCleanup(time_patcher.stop)

        self.ledger_path = Path(self.lock_dir) / "ledger"
        self.server = StackServer()
        self.stub = _serve_in_process(self, self.server)
        reply = self.stub.Configure(tool_base_pb2.Config(
            simulated=True, toolId="stack-sim",
            stack=stack_pb2.Config(host="127.0.0.1", ledger_dir=str(self.ledger_path))))
        self.assertEqual(reply.response, SUCCESS)

    def _fake_sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def _stack(self, **command: Any) -> tool_base_pb2.Command:
        return tool_base_pb2.Command(stack=stack_pb2.Command(**command))

    def _assert_core_free(self) -> None:
        self.open_service.assert_not_called()
        self.assertIsNone(self.server.service)
        self.assertEqual(list(Path(self.lock_dir).glob("*.lock")), [])
        self.assertFalse(self.ledger_path.exists())


class TestSimulatedTransferOverGrpc(_SimulatedGrpcTestCase):
    """STK-06 tracer: a simulated Transfer validates the adapter's arguments,
    sleeps the constant estimate and never touches the core."""

    def _transfer(self, **fields: Any) -> Any:
        return self.stub.ExecuteCommand(self._stack(
            transfer=stack_pb2.Command.Transfer(**fields)))

    def test_status_is_simulated(self) -> None:
        self.assertEqual(self.stub.GetStatus(empty_pb2.Empty()).status,
                         tool_base_pb2.SIMULATED)

    def test_valid_transfer_sleeps_the_constant_and_succeeds(self) -> None:
        reply = self._transfer(step_key="run-1:stack-1", robot="R1")
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(self.sleeps, [35.0])
        self._assert_core_free()

    def test_missing_or_blank_step_key_is_invalid_and_does_not_sleep(self) -> None:
        for label, fields in (("unset", {}), ("blank", {"step_key": "   "})):
            with self.subTest(label):
                reply = self._transfer(**fields)
                self.assertEqual(reply.response, tool_base_pb2.INVALID_ARGUMENTS)
                self.assertIn("step_key", reply.error_message)
                self.assertEqual(self.sleeps, [])
        self._assert_core_free()

    def test_nan_timeout_is_invalid(self) -> None:
        reply = self._transfer(step_key="k", timeout_s=float("nan"))
        self.assertEqual(reply.response, tool_base_pb2.INVALID_ARGUMENTS)
        self.assertEqual(self.sleeps, [])
        self._assert_core_free()


class TestCheckArgs(unittest.TestCase):
    """D-17: the adapter checks only its own arguments, exactly."""

    def _problems(self, name: str, **fields: Any) -> list[str]:
        return stack_server._check_args(getattr(stack_pb2.Command, name)(**fields))

    def test_transfer_step_key(self) -> None:
        for label, fields in (("unset", {}), ("empty", {"step_key": ""}),
                              ("blank", {"step_key": "   "})):
            with self.subTest(label):
                self.assertEqual(len(self._problems("Transfer", **fields)), 1)
        self.assertEqual(self._problems("Transfer", step_key="k"), [])

    def test_transfer_timeout(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf"), -0.5):
            with self.subTest(value=value):
                problems = self._problems("Transfer", step_key="k", timeout_s=value)
                self.assertEqual(len(problems), 1)
                self.assertIn("timeout_s", problems[0])
        for value in (0.0, 30.0):
            with self.subTest(value=value):
                self.assertEqual(self._problems("Transfer", step_key="k", timeout_s=value), [])
        self.assertEqual(self._problems("Transfer", step_key="k"), [])

    def test_transfer_with_both_problems_reports_both(self) -> None:
        self.assertEqual(len(self._problems("Transfer", timeout_s=-1.0)), 2)

    def test_acknowledge_guid(self) -> None:
        for label, fields in (("unset", {}), ("empty", {"guid": ""}), ("blank", {"guid": "  "})):
            with self.subTest(label):
                problems = self._problems("AcknowledgeFailure", arm_inspected="yes", **fields)
                self.assertEqual(len(problems), 1)
                self.assertIn("guid", problems[0])

    def test_acknowledge_arm_inspected_is_exactly_yes_or_no(self) -> None:
        for bad in ("", "Yes", "YES", " yes", "yes ", "y", "true", "no ", "No", "maybe"):
            with self.subTest(bad=bad):
                problems = self._problems("AcknowledgeFailure", guid="g", arm_inspected=bad)
                self.assertEqual(len(problems), 1)
                self.assertIn("arm_inspected", problems[0])
        problems = self._problems("AcknowledgeFailure", guid="g")
        self.assertEqual(len(problems), 1)
        self.assertIn("unset", problems[0])
        for good in ("yes", "no"):
            with self.subTest(good=good):
                self.assertEqual(
                    self._problems("AcknowledgeFailure", guid="g", arm_inspected=good), [])

    def test_reads_and_the_latch_and_blank_estimate_pass(self) -> None:
        for name in ("GetManagerState", "GetRobotStates", "ListDevices", "ListLabwareProfiles",
                     "ListTransferProfiles", "GetLabwarePresence", "GetTransferEstimate",
                     "GetFailureLatch"):
            with self.subTest(name):
                self.assertEqual(self._problems(name), [])
        self.assertEqual(self._problems("GetTransferEstimate", robot="", source_nest=" "), [])


def _ack_message(guid: str = "g-1", **fields: Any) -> stack_pb2.Command.AcknowledgeFailure:
    return stack_pb2.Command.AcknowledgeFailure(guid=guid, **fields)


# Everything except the exact string "yes": the operator must state it, and
# nothing close to it counts (T-05-13). "ｙｅｓ" is the full-width form.
_NOT_YES = ("no", "Yes", "YES", " yes", "yes ", "yes\n", "y", "true", "ｙｅｓ", "")


class TestAcknowledge(_RealModeGrpcTestCase):
    """ACK-01 / D-14: AcknowledgeFailure reaches the core only with an exact
    "yes", exactly once, with the guid stripped and confirm=True."""

    def _ack(self, guid: str = "g-1", **fields: Any) -> Any:
        return self.stub.ExecuteCommand(self._stack(
            acknowledge_failure=_ack_message(guid, **fields)))

    def test_yes_reaches_the_core_once_with_a_stripped_guid_and_confirm(self) -> None:
        result = FailureAcknowledged(guid="g-1", result_kind="failed", explanation=_SENTINEL)
        self.service.acknowledge_failure.return_value = result
        reply = self._ack("  g-1 ", arm_inspected="yes")
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.assertEqual(reply.error_message, "")
        self.assertEqual(reply.meta_data, _struct(result.to_dict()))
        self.assertEqual(self.service.mock_calls,
                         [mock_call.acknowledge_failure("g-1", confirm=True)])
        self.assertEqual(self._health().status, READY)

    def test_every_core_refusal_and_failure_is_error_from_tool(self) -> None:
        answers = (
            ("refused", Refused(reason="guidMismatch", state="x")),
            ("refused", Refused(reason="nothingLatched", state="x")),
            ("refused", Refused(reason="recoveryPending", state="x")),
            ("refused", Refused(reason="stateUnsaved", state="x")),
            ("needsInput", NeedsInput(missing=["guid"])),
            ("readFailed", ReadFailed(error={"status": None, "name": "ConnectError"})),
        )
        for kind, answer in answers:
            with self.subTest(kind=kind, answer=answer.to_dict().get("reason")):
                self.service.reset_mock()
                self.service.acknowledge_failure.return_value = answer
                reply = self._ack(arm_inspected="yes")
                self.assertEqual(reply.response, ERROR_FROM_TOOL)
                self.assertTrue(reply.error_message.startswith(f"stack: {kind}"),
                                reply.error_message)
                self.assertEqual(reply.meta_data, _struct(answer.to_dict()))
                self.assertEqual(len(self.service.mock_calls), 1)

    def test_anything_but_an_exact_yes_is_invalid_arguments_with_no_core_call(self) -> None:
        for bad in _NOT_YES:
            with self.subTest(arm_inspected=bad):
                reply = self._ack(arm_inspected=bad)
                self.assertEqual(reply.response, tool_base_pb2.INVALID_ARGUMENTS)
                self.assertEqual(self.service.mock_calls, [])
        with self.subTest("unset"):
            reply = self._ack()
            self.assertEqual(reply.response, tool_base_pb2.INVALID_ARGUMENTS)
            self.assertEqual(self.service.mock_calls, [])
        self.assertEqual(self._health().status, READY)

    def test_a_valid_no_says_what_to_do(self) -> None:
        reply = self._ack(arm_inspected="no")
        self.assertEqual(reply.response, tool_base_pb2.INVALID_ARGUMENTS)
        self.assertIn("exactly 'yes'", reply.error_message)
        self.assertIn("inspect the arm", reply.error_message)

    def test_the_handler_called_directly_enforces_the_gate_too(self) -> None:
        for bad in _NOT_YES:
            with self.subTest(arm_inspected=bad):
                reply = self.server.AcknowledgeFailure(_ack_message("g", arm_inspected=bad))
                self.assertEqual(reply.response, tool_base_pb2.INVALID_ARGUMENTS)
        reply = self.server.AcknowledgeFailure(_ack_message("g"))
        self.assertEqual(reply.response, tool_base_pb2.INVALID_ARGUMENTS)
        self.assertEqual(self.service.mock_calls, [])

    def test_the_gate_wins_over_not_configured_and_makes_no_core_contact(self) -> None:
        self.server.service = None
        for bad in ("no", "Yes", ""):
            with self.subTest(arm_inspected=bad):
                reply = self._ack("g", arm_inspected=bad)
                self.assertEqual(reply.response, tool_base_pb2.INVALID_ARGUMENTS)
        direct = self.server.AcknowledgeFailure(_ack_message("g", arm_inspected="no"))
        self.assertEqual(direct.response, tool_base_pb2.INVALID_ARGUMENTS)
        self.assertEqual(self.service.mock_calls, [])

    def test_a_blank_guid_never_reaches_the_core(self) -> None:
        for guid in ("", "   "):
            with self.subTest(guid=guid):
                reply = self._ack(guid, arm_inspected="yes")
                self.assertEqual(reply.response, tool_base_pb2.INVALID_ARGUMENTS)
        self.assertEqual(self.service.mock_calls, [])

    def test_a_yes_acknowledge_with_no_service_is_not_ready(self) -> None:
        self.server.service = None
        reply = self._ack("g", arm_inspected="yes")
        self.assertEqual(reply.response, NOT_READY)
        self.assertEqual(reply.error_message, "stack: not configured")


class TestAcknowledgeLeavesTheLedgerAlone(_TransferTestCase):
    """ACK-01 / D-15: an acknowledge never reads, writes or deletes a record."""

    def test_the_ledger_bytes_are_identical_across_an_acknowledge(self) -> None:
        self.core.wait_result = Failed(task=_snapshot("g-task"))
        self.assertEqual(self._transfer().response, ERROR_FROM_TOOL)
        with open(self.ledger_path, "rb") as handle:
            before = handle.read()
        mtime = os.stat(self.ledger_path).st_mtime_ns
        reply = self.stub.ExecuteCommand(self._stack(
            acknowledge_failure=_ack_message(_GUID, arm_inspected="yes")))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.assertEqual(self.core.call_names[-1], "acknowledge_failure")
        with open(self.ledger_path, "rb") as handle:
            self.assertEqual(handle.read(), before)
        self.assertEqual(os.stat(self.ledger_path).st_mtime_ns, mtime)

    def test_an_acknowledge_with_no_ledger_directory_creates_none(self) -> None:
        reply = self.stub.ExecuteCommand(self._stack(
            acknowledge_failure=_ack_message(_GUID, arm_inspected="yes")))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.assertFalse(os.path.exists(self.ledger_dir))
        self.assertEqual(self.core.call_names, ["acknowledge_failure"])
        self.assertEqual(self.core.calls[0][2], {"confirm": True})


class TestUnconfiguredOrdering(_StackTestCase):
    """D-14: with no service every real-mode command is NOT_READY (the Phase 4
    not-yet-available refusals are gone); adapter arguments are checked first."""

    def setUp(self) -> None:
        super().setUp()
        self.server = StackServer()
        self.assertIsNone(self.server.service)
        self.assertFalse(self.server.simulated)

    def _dispatch(self, name: str, **fields: Any) -> Any:
        return self.server._dispatchCommand(getattr(stack_pb2.Command, name)(**fields))

    def test_every_command_with_good_arguments_is_not_ready(self) -> None:
        for name, fields in (
            ("Transfer", {"step_key": "k"}),
            ("AcknowledgeFailure", {"guid": "g", "arm_inspected": "yes"}),
            ("GetFailureLatch", {}),
            ("GetManagerState", {}), ("GetRobotStates", {}), ("ListDevices", {}),
            ("ListLabwareProfiles", {}), ("ListTransferProfiles", {}),
            ("GetLabwarePresence", {}), ("GetTransferEstimate", {}),
        ):
            with self.subTest(name):
                reply = self._dispatch(name, **fields)
                self.assertEqual(reply.response, NOT_READY)
                self.assertEqual(reply.error_message, "stack: not configured")

    def test_transfer_without_step_key_is_invalid_arguments(self) -> None:
        self.assertEqual(self._dispatch("Transfer").response, tool_base_pb2.INVALID_ARGUMENTS)

    def test_the_refusal_machinery_is_gone(self) -> None:
        self.assertFalse(hasattr(stack_server, "UNAVAILABLE_COMMANDS"))
        self.assertFalse(hasattr(stack_server, "_unavailable_reply"))


_ESTIMATE_CONSTANTS = {
    "Transfer": 35,
    "GetTransferEstimate": 3,
    "AcknowledgeFailure": 2,
    "GetManagerState": 2,
    "GetRobotStates": 2,
    "ListDevices": 2,
    "ListLabwareProfiles": 2,
    "ListTransferProfiles": 2,
    "GetLabwarePresence": 2,
    "GetFailureLatch": 2,
}

# Valid adapter arguments for every command (the instrument fields stay blank).
_VALID_ARGS: dict[str, dict[str, Any]] = {
    "Transfer": {"step_key": "run-1:stack-1"},
    "AcknowledgeFailure": {"guid": "g", "arm_inspected": "yes"},
}


class TestEstimates(_RealModeGrpcTestCase):
    """D-19: every Estimate<Cmd> hook is a local constant."""

    def test_the_hook_set_matches_the_ten_commands(self) -> None:
        hooks = {n for n in dir(StackServer) if n.startswith("Estimate") and n != "EstimateDuration"}
        self.assertEqual(hooks, {"Estimate" + n for n in _ESTIMATE_CONSTANTS})
        names = {f.message_type.name
                 for f in stack_pb2.Command.DESCRIPTOR.oneofs_by_name["command"].fields}
        self.assertEqual(set(_ESTIMATE_CONSTANTS), names)

    def test_each_hook_returns_its_constant_as_an_int(self) -> None:
        for name, expected in _ESTIMATE_CONSTANTS.items():
            with self.subTest(name):
                value = getattr(StackServer(), "Estimate" + name)(
                    getattr(stack_pb2.Command, name)())
                self.assertEqual(value, expected)
                self.assertIs(type(value), int)

    def test_hooks_ignore_malformed_messages_and_never_touch_the_service(self) -> None:
        bad = {
            "Transfer": stack_pb2.Command.Transfer(timeout_s=float("nan")),
            "AcknowledgeFailure": stack_pb2.Command.AcknowledgeFailure(arm_inspected="maybe"),
        }
        for name, message_ in bad.items():
            with self.subTest(name):
                self.assertEqual(getattr(self.server, "Estimate" + name)(message_),
                                 _ESTIMATE_CONSTANTS[name])
        for name in _ESTIMATE_CONSTANTS:
            with self.subTest(f"no-service {name}"):
                self.assertEqual(
                    getattr(StackServer(), "Estimate" + name)(getattr(stack_pb2.Command, name)()),
                    _ESTIMATE_CONSTANTS[name])
        self.assertEqual(self.service.mock_calls, [])

    def test_estimate_duration_rpc_returns_the_constant_for_every_command(self) -> None:
        for name, expected in _ESTIMATE_CONSTANTS.items():
            with self.subTest(name):
                snake = "".join("_" + c.lower() if c.isupper() else c for c in name).lstrip("_")
                reply = self.stub.EstimateDuration(self._stack(
                    **{snake: getattr(stack_pb2.Command, name)(**_VALID_ARGS.get(name, {}))}))
                self.assertEqual(reply.response, SUCCESS)
                self.assertEqual(reply.estimated_duration_seconds, expected)
        self.assertEqual(self.service.mock_calls, [])

    def test_estimate_duration_rpc_survives_malformed_arguments(self) -> None:
        reply = self.stub.EstimateDuration(self._stack(
            transfer=stack_pb2.Command.Transfer(timeout_s=float("nan"))))
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(reply.estimated_duration_seconds, 35)


class TestSimulatedCommands(_SimulatedGrpcTestCase):
    """STK-06: all ten commands rehearse core-free in simulated mode."""

    def test_every_command_sleeps_its_constant_and_succeeds(self) -> None:
        for name, expected in _ESTIMATE_CONSTANTS.items():
            with self.subTest(name):
                snake = "".join("_" + c.lower() if c.isupper() else c for c in name).lstrip("_")
                before = len(self.sleeps)
                reply = self.stub.ExecuteCommand(self._stack(
                    **{snake: getattr(stack_pb2.Command, name)(**_VALID_ARGS.get(name, {}))}))
                self.assertEqual(reply.response, SUCCESS, reply.error_message)
                self.assertEqual(self.sleeps[before:], [float(expected)])
        self._assert_core_free()

    def test_acknowledge_with_no_is_also_success(self) -> None:
        reply = self.stub.ExecuteCommand(self._stack(
            acknowledge_failure=stack_pb2.Command.AcknowledgeFailure(
                guid="g", arm_inspected="no")))
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(self.sleeps, [2.0])
        self._assert_core_free()

    def test_blank_instrument_fields_pass_the_argument_check(self) -> None:
        reply = self.stub.ExecuteCommand(self._stack(
            get_transfer_estimate=stack_pb2.Command.GetTransferEstimate(
                robot="", source_nest="  ")))
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(self.sleeps, [3.0])

    def test_bad_adapter_arguments_are_rejected_in_simulated_mode_too(self) -> None:
        reply = self.stub.ExecuteCommand(self._stack(
            acknowledge_failure=stack_pb2.Command.AcknowledgeFailure(
                guid="g", arm_inspected="Yes")))
        self.assertEqual(reply.response, tool_base_pb2.INVALID_ARGUMENTS)
        self.assertEqual(self.sleeps, [])
        self._assert_core_free()


_BUSY_READS = (
    ("manager_state", "get_manager_state", stack_pb2.Command.GetManagerState),
    ("robot_states", "get_robot_states", stack_pb2.Command.GetRobotStates),
    ("devices", "list_devices", stack_pb2.Command.ListDevices),
    ("labware_profiles", "list_labware_profiles", stack_pb2.Command.ListLabwareProfiles),
    ("transfer_profiles", "list_transfer_profiles", stack_pb2.Command.ListTransferProfiles),
    ("labware_presence", "get_labware_presence", stack_pb2.Command.GetLabwarePresence),
    ("estimate_transfer", "get_transfer_estimate", stack_pb2.Command.GetTransferEstimate),
)


class TestBusyReads(_RealModeGrpcTestCase):
    """STK-05 tracer (D-13..D-16): while a non-read command holds the tool BUSY,
    every read answers with its own result and a second non-read is refused.
    The real Transfer lands in Phase 5, so the slow command is an injected
    Transfer handler."""

    def setUp(self) -> None:
        super().setUp()
        self.results = {
            "manager_state": ManagerState(mode="Idle", recovery=None, api_version="3"),
            "robot_states": RobotStates(robots=[]),
            "devices": DeviceTree(devices=(), ambiguous=[], api_version="3"),
            "labware_profiles": LabwareProfiles(profiles=[]),
            "transfer_profiles": TransferProfiles(profiles=[]),
            "labware_presence": LabwarePresence(robot_name="R1", has_labware=True),
            "estimate_transfer": Estimated(
                estimated_time="00:00:48", guid=None, advisories=[], seconds=48.0),
        }
        self.results["latch_status"] = LatchStatus(latched=False)
        for method, result in self.results.items():
            getattr(self.service, method).return_value = result

    def _start_blocked_command(self) -> tuple[threading.Event, threading.Thread, dict[str, Any], MagicMock]:
        """Blocks a Transfer sent over the gRPC stub inside its handler so
        base_server's isReady/setStatus(BUSY) bracket is really exercised. The
        step_key must be non-blank or the argument check answers
        INVALID_ARGUMENTS instantly (Pitfall 5). An instance attribute wins
        over the class handler because base _dispatchCommand resolves the
        handler with getattr(self, name)."""
        release = threading.Event()
        entered = threading.Event()

        def _blocking(*args: Any, **kwargs: Any) -> Any:
            entered.set()
            release.wait(timeout=10)
            return tool_base_pb2.ExecuteCommandReply(response=SUCCESS, return_reply=True)

        handler = MagicMock(side_effect=_blocking)
        patcher = patch.object(self.server, "Transfer", handler)
        patcher.start()
        self.addCleanup(patcher.stop)

        result: dict[str, Any] = {}

        def _send() -> None:
            result["transfer"] = self.stub.ExecuteCommand(self._stack(
                transfer=stack_pb2.Command.Transfer(step_key="busy-1")))

        thread = threading.Thread(target=_send)
        thread.start()
        # Cleanups run LIFO: release before join, so a failing assertion never
        # leaves the gRPC worker thread blocked forever.
        self.addCleanup(thread.join, 10)
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(timeout=5))
        return release, thread, result, handler

    def test_reads_answer_while_busy_and_a_second_transfer_is_refused(self) -> None:
        release, thread, result, handler = self._start_blocked_command()
        self.assertEqual(self._health().status, tool_base_pb2.BUSY)

        for method, field, message in _BUSY_READS:
            with self.subTest(field):
                reply = self.stub.ExecuteCommand(self._stack(**{field: message()}))
                self.assertEqual(reply.response, SUCCESS, reply.error_message)
                self.assertEqual(reply.meta_data, _struct(self.results[method].to_dict()))
                getattr(self.service, method).assert_called_once()
        with self.subTest("get_failure_latch"):
            reply = self.stub.ExecuteCommand(self._stack(
                get_failure_latch=stack_pb2.Command.GetFailureLatch()))
            self.assertEqual(reply.response, SUCCESS, reply.error_message)
            self.assertEqual(reply.meta_data, _struct(self.results["latch_status"].to_dict()))
            self.service.latch_status.assert_called_once()

        self.assertEqual(self._health().status, tool_base_pb2.BUSY)
        second = self.stub.ExecuteCommand(self._stack(
            transfer=stack_pb2.Command.Transfer(step_key="busy-2")))
        self.assertEqual(second.response, NOT_READY)
        self.assertEqual(handler.call_count, 1)

        release.set()
        thread.join(10)
        self.assertEqual(result["transfer"].response, SUCCESS)
        self.assertEqual(self._health().status, READY)


    def test_reads_do_not_clear_or_overwrite_the_last_error(self) -> None:
        """WR-04: a motion command's failure text in GetStatus.error_message
        survives successful, refused and failed (non-exception) reads."""
        self.server.last_error = "transfer failed: arm fault"
        self.service.latch_status.return_value = LatchStatus(latched=False)
        self.service.robot_states.return_value = ReadFailed(
            error={"status": 500, "name": "Boom"})
        for field, message in (
            ("get_manager_state", stack_pb2.Command.GetManagerState),    # SUCCESS
            ("get_robot_states", stack_pb2.Command.GetRobotStates),      # ERROR_FROM_TOOL
            ("get_failure_latch", stack_pb2.Command.GetFailureLatch),    # SUCCESS
        ):
            with self.subTest(field):
                self.stub.ExecuteCommand(self._stack(**{field: message()}))
                self.assertEqual(self.server.last_error, "transfer failed: arm fault")
                self.assertEqual(
                    self._health().error_message, "transfer failed: arm fault")

    def test_last_error_survives_reads_while_a_transfer_is_in_flight(self) -> None:
        release, thread, result, _handler = self._start_blocked_command()
        self.server.last_error = "transfer failed: arm fault"
        reply = self.stub.ExecuteCommand(self._stack(
            get_manager_state=stack_pb2.Command.GetManagerState()))
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(self._health().status, tool_base_pb2.BUSY)
        self.assertEqual(self._health().error_message, "transfer failed: arm fault")
        release.set()
        thread.join(10)

    def test_a_non_read_command_still_records_its_error(self) -> None:
        self.service.plan_transfer.return_value = NeedsInput(missing=["robot"])
        self.server.last_error = "stale"
        reply = self.stub.ExecuteCommand(self._stack(
            transfer=stack_pb2.Command.Transfer(step_key="s-1")))
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertEqual(self.server.last_error, reply.error_message)
        self.assertNotEqual(self.server.last_error, "stale")


class TestReadCommandSet(unittest.TestCase):
    """T-04-19: the BUSY-bypass set is pinned so a motion or acknowledge command
    can never join it silently."""

    def test_the_set_is_exactly_the_eight_reads(self) -> None:
        self.assertEqual(READ_COMMANDS, frozenset({
            "get_manager_state", "get_robot_states", "list_devices",
            "list_labware_profiles", "list_transfer_profiles", "get_labware_presence",
            "get_transfer_estimate", "get_failure_latch",
        }))

    def test_motion_and_acknowledge_are_excluded(self) -> None:
        self.assertNotIn("transfer", READ_COMMANDS)
        self.assertNotIn("acknowledge_failure", READ_COMMANDS)

    def test_every_entry_is_a_field_of_the_stack_command_oneof(self) -> None:
        oneof = {f.name for f in stack_pb2.Command.DESCRIPTOR.oneofs_by_name["command"].fields}
        self.assertLessEqual(READ_COMMANDS, oneof)


_ALL_READ_COMMANDS = (
    ("manager_state", "get_manager_state", stack_pb2.Command.GetManagerState),
    ("robot_states", "get_robot_states", stack_pb2.Command.GetRobotStates),
    ("devices", "list_devices", stack_pb2.Command.ListDevices),
    ("labware_profiles", "list_labware_profiles", stack_pb2.Command.ListLabwareProfiles),
    ("transfer_profiles", "list_transfer_profiles", stack_pb2.Command.ListTransferProfiles),
    ("labware_presence", "get_labware_presence", stack_pb2.Command.GetLabwarePresence),
    ("estimate_transfer", "get_transfer_estimate", stack_pb2.Command.GetTransferEstimate),
)


class TestNotConfigured(_StackTestCase):
    """D-14: a bypassed read never reaches a None service."""

    def setUp(self) -> None:
        super().setUp()
        self.open_service = MagicMock()
        patcher = patch("tools.stack.server.open_service", self.open_service)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.server = StackServer()
        self.stub = _serve_in_process(self, self.server)

    def _stack(self, **command: Any) -> tool_base_pb2.Command:
        return tool_base_pb2.Command(stack=stack_pb2.Command(**command))

    def _health(self) -> tool_base_pb2.StatusReply:
        return self.stub.GetStatus(empty_pb2.Empty())  # type: ignore[no-any-return]

    def test_fresh_server_reads_and_the_latch_are_not_ready(self) -> None:
        self.assertEqual(self._health().status, tool_base_pb2.NOT_CONFIGURED)
        for field, message in (("get_manager_state", stack_pb2.Command.GetManagerState),
                               ("get_transfer_estimate", stack_pb2.Command.GetTransferEstimate)):
            with self.subTest(field):
                reply = self.stub.ExecuteCommand(self._stack(**{field: message()}))
                self.assertEqual(reply.response, NOT_READY)
                self.assertEqual(reply.error_message, "stack: not configured")
        reply = self.stub.ExecuteCommand(self._stack(
            get_failure_latch=stack_pb2.Command.GetFailureLatch()))
        self.assertEqual(reply.response, NOT_READY)
        self.assertEqual(reply.error_message, "stack: not configured")
        self.assertEqual(self._health().status, tool_base_pb2.NOT_CONFIGURED)
        self.open_service.assert_not_called()

    def test_simulated_to_real_switch_leaves_reads_not_configured(self) -> None:
        sim = self.stub.Configure(tool_base_pb2.Config(
            simulated=True, toolId="stack-sim", stack=stack_pb2.Config(host="127.0.0.1")))
        self.assertEqual(sim.response, SUCCESS)
        real = self.stub.Configure(tool_base_pb2.Config(
            simulated=False, stack=stack_pb2.Config(host="127.0.0.1")))
        self.assertEqual(real.response, SUCCESS)
        self.assertIsNone(self.server.service)
        reply = self.stub.ExecuteCommand(self._stack(
            get_manager_state=stack_pb2.Command.GetManagerState()))
        self.assertEqual(reply.response, NOT_READY)
        self.assertEqual(reply.error_message, "stack: not configured")
        self.open_service.assert_not_called()


class TestReadBypassEdges(_RealModeGrpcTestCase):
    """D-13: the bypass never touches status, never hides an exception, and
    leaves every non-read request to base_server."""

    def test_exception_becomes_driver_error_with_last_error_and_status_kept(self) -> None:
        self.service.manager_state.side_effect = RuntimeError("boom")
        reply = self.stub.ExecuteCommand(self._stack(
            get_manager_state=stack_pb2.Command.GetManagerState()))
        self.assertEqual(reply.response, tool_base_pb2.DRIVER_ERROR)
        self.assertEqual(reply.error_message, "boom")
        self.assertEqual(self.server.last_error, "boom")
        self.assertEqual(self._health().status, READY)

    def test_reads_never_call_set_status_but_a_transfer_brackets_busy_ready(self) -> None:
        for method in ("manager_state", "robot_states", "devices", "labware_profiles",
                       "transfer_profiles", "labware_presence", "estimate_transfer"):
            getattr(self.service, method).return_value = ReadFailed(
                error={"status": None, "name": "x"})
        self.service.plan_transfer.return_value = NeedsInput(missing=["robot"])
        calls: list[Any] = []
        real_set_status = self.server.setStatus

        def _wrapped(status: Any) -> None:
            calls.append(status)
            real_set_status(status)

        with patch.object(self.server, "setStatus", side_effect=_wrapped):
            for _method, field, message in _ALL_READ_COMMANDS:
                self.stub.ExecuteCommand(self._stack(**{field: message()}))
            self.stub.ExecuteCommand(self._stack(
                get_failure_latch=stack_pb2.Command.GetFailureLatch()))
            self.assertEqual(calls, [])
            self.assertEqual(self._health().status, READY)
            self.stub.ExecuteCommand(self._stack(
                transfer=stack_pb2.Command.Transfer(step_key="k")))
            self.assertEqual(calls, [tool_base_pb2.BUSY, READY])

    def test_empty_stack_command_and_other_tool_fall_through(self) -> None:
        empty = self.stub.ExecuteCommand(tool_base_pb2.Command(stack=stack_pb2.Command()))
        self.assertEqual(empty.response, tool_base_pb2.UNRECOGNIZED_COMMAND)
        other = self.stub.ExecuteCommand(tool_base_pb2.Command(
            fast=fast_pb2.Command(pause=fast_pb2.Command.Pause())))
        self.assertEqual(other.response, tool_base_pb2.WRONG_TOOL)

    def test_estimate_read_while_ready_calls_the_core_once_and_stays_ready(self) -> None:
        self.service.estimate_transfer.return_value = Estimated(
            estimated_time="00:00:48", guid=None, advisories=[], seconds=48.0)
        reply = self.stub.ExecuteCommand(self._stack(
            get_transfer_estimate=stack_pb2.Command.GetTransferEstimate(**_ESTIMATE_FIELDS)))
        self.assertEqual(reply.response, SUCCESS)
        self.service.estimate_transfer.assert_called_once()
        self.assertEqual(len(self.service.mock_calls), 1)
        self.assertEqual(self._health().status, READY)


class TestSimulatedBypassRead(_SimulatedGrpcTestCase):
    """A bypassed read in simulated mode still goes through _dispatchCommand:
    the constant estimate is slept and the core is never contacted."""

    def test_manager_state_sleeps_the_read_constant_core_free(self) -> None:
        reply = self.stub.ExecuteCommand(self._stack(
            get_manager_state=stack_pb2.Command.GetManagerState()))
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(self.sleeps, [2.0])
        self._assert_core_free()
