import importlib.metadata
import json
import os
import socket
import tempfile
import threading
import time
import types
import unittest
from concurrent import futures
from dataclasses import fields
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, call, patch

import grpc
import httpx
from google.protobuf.json_format import MessageToDict

from fast_mcp.errors import Finding
from fast_mcp.orchestration import RunOutcome
from fast_mcp.results import (
    Aborted,
    Cancelled,
    DeckMove,
    DeckSuggestion,
    NeedsConfirmation,
    NeedsInput,
    Paused,
    Ran,
    Refused,
    Rejected,
    TimedOut,
    TipRescan,
    TipScan,
    TrayEjected,
    ValidationReport,
)
from fast_mcp.service import FastService, TransferRequest
from fast_mcp.transport import InstrumentHTTPError

from tools.fast.server import COMMAND_TO_SERVICE_METHOD, FastServer
from tools.grpc_interfaces import controller_pb2, fast_pb2, tool_base_pb2
from tools.grpc_interfaces.tool_base_pb2 import (
    ERROR_FROM_TOOL,
    INVALID_ARGUMENTS,
    NOT_READY,
    READY,
    SUCCESS,
)
from tools.grpc_interfaces.tool_driver_pb2_grpc import (
    ToolDriverStub,
    add_ToolDriverServicer_to_server,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]

_ALL_TRANSFER_FIELDS: dict[str, Any] = dict(
    source_deck=1, dest_deck=3, source_plate_id=1, dest_plate_id=1,
    source_start_row="A", source_start_col=1, dest_start_row="A", dest_start_col=1,
    num_rows=8, num_cols=1, volume=10.0, tip_reuse="fresh",
)


def _free_tcp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


class TestTransferEndToEndOverGrpc(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._env_patcher = patch.dict(os.environ, {"FAST_MCP_LOCK_DIR": self._tmpdir.name})
        self._env_patcher.start()
        self.addCleanup(self._env_patcher.stop)
        self.addCleanup(self._tmpdir.cleanup)

        self._closed_port = _free_tcp_port()

        self.fs = FastServer()
        self._grpc_port = _free_tcp_port()
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        add_ToolDriverServicer_to_server(self.fs, self._server)
        self._server.add_insecure_port(f"127.0.0.1:{self._grpc_port}")
        self._server.start()

        self._channel = grpc.insecure_channel(f"127.0.0.1:{self._grpc_port}")
        self.stub = ToolDriverStub(self._channel)

    def tearDown(self) -> None:
        if self.fs._owned is not None:
            self.fs._owned.close()
        self._channel.close()
        self._server.stop(None)

    def test_configure_takes_galago_lock_and_transfer_reports_unreachable_instrument(self) -> None:
        config_request = tool_base_pb2.Config(
            simulated=False, toolId="fast-test",
            fast=fast_pb2.Config(host="127.0.0.1", port=self._closed_port),
        )

        reply = self.stub.Configure(config_request)
        self.assertEqual(reply.response, tool_base_pb2.SUCCESS)

        lock_files = [f for f in os.listdir(self._tmpdir.name) if not f.startswith(".")]
        self.assertEqual(len(lock_files), 1)
        with open(os.path.join(self._tmpdir.name, lock_files[0])) as fh:
            holder_record = fh.read()
        self.assertIn('"owner": "galago"', holder_record)
        self.assertIn(str(os.getpid()), holder_record)

        command = tool_base_pb2.Command(
            fast=fast_pb2.Command(transfer=fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS)))
        exec_reply = self.stub.ExecuteCommand(command)
        self.assertEqual(exec_reply.response, ERROR_FROM_TOOL)
        self.assertTrue(exec_reply.error_message.startswith("instrument unreachable"))
        self.assertNotIn("Traceback", exec_reply.error_message)
        self.assertNotIn("\n", exec_reply.error_message)

        # D-09 reuse: re-Configure to the same endpoint on the same server succeeds.
        reply2 = self.stub.Configure(config_request)
        self.assertEqual(reply2.response, tool_base_pb2.SUCCESS)

        # D-07: a second FastServer on the same endpoint is refused, naming galago.
        second = FastServer()
        second_reply = second.Configure(config_request, None)  # type: ignore[arg-type]
        self.assertEqual(second_reply.response, tool_base_pb2.NOT_READY)
        self.assertIn("galago", second_reply.error_message)


class TestSimulatedTransferOverGrpc(unittest.TestCase):
    """GAL-03 tracer: a simulated tool validates arguments, sleeps the named
    D-16 estimate and never builds a FastService or takes the owner lock,
    over a real in-process gRPC server (RESEARCH Pattern 1)."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._env_patcher = patch.dict(os.environ, {"FAST_MCP_LOCK_DIR": self._tmpdir.name})
        self._env_patcher.start()
        self.addCleanup(self._env_patcher.stop)
        self.addCleanup(self._tmpdir.cleanup)

        self._open_service_patcher = patch("tools.fast.server.open_service")
        self.mock_open_service = self._open_service_patcher.start()
        self.addCleanup(self._open_service_patcher.stop)

        self.fake_sleep = MagicMock()
        self._time_patcher = patch(
            "tools.base_server.time",
            types.SimpleNamespace(time=time.time, sleep=self.fake_sleep))
        self._time_patcher.start()
        self.addCleanup(self._time_patcher.stop)

        self.fs = FastServer()
        self._grpc_port = _free_tcp_port()
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        add_ToolDriverServicer_to_server(self.fs, self._server)
        self._server.add_insecure_port(f"127.0.0.1:{self._grpc_port}")
        self._server.start()
        self.addCleanup(self._server.stop, None)

        self._channel = grpc.insecure_channel(f"127.0.0.1:{self._grpc_port}")
        self.addCleanup(self._channel.close)
        self.stub = ToolDriverStub(self._channel)

        config_request = tool_base_pb2.Config(
            simulated=True, toolId="fast-sim",
            fast=fast_pb2.Config(host="sim-no-contact.invalid"))
        reply = self.stub.Configure(config_request)
        self.assertEqual(reply.response, tool_base_pb2.SUCCESS)

    def _valid_transfer_command(self) -> tool_base_pb2.Command:
        return tool_base_pb2.Command(
            fast=fast_pb2.Command(transfer=fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS)))

    def test_simulated_transfer_sleeps_estimate_without_service_or_lock(self) -> None:
        exec_reply = self.stub.ExecuteCommand(self._valid_transfer_command())
        self.assertEqual(exec_reply.response, SUCCESS)
        self.fake_sleep.assert_called_once_with(80.0)

        estimate_reply = self.stub.EstimateDuration(self._valid_transfer_command())
        self.assertEqual(estimate_reply.response, SUCCESS)
        self.assertEqual(estimate_reply.estimated_duration_seconds, 80)

        self.mock_open_service.assert_not_called()
        self.assertIsNone(self.fs.service)
        self.assertEqual(
            [f for f in os.listdir(self._tmpdir.name) if not f.startswith(".")], [])

    def test_simulated_transfer_is_idempotent(self) -> None:
        for _ in range(2):
            exec_reply = self.stub.ExecuteCommand(self._valid_transfer_command())
            self.assertEqual(exec_reply.response, SUCCESS)
        self.assertEqual(self.fake_sleep.call_args_list, [call(80.0), call(80.0)])
        self.mock_open_service.assert_not_called()
        self.assertIsNone(self.fs.service)
        self.assertEqual(
            [f for f in os.listdir(self._tmpdir.name) if not f.startswith(".")], [])

    def test_simulated_invalid_args_rejected_while_another_simulated_command_is_in_flight(
            self) -> None:
        entered = threading.Event()
        release = threading.Event()

        def _blocking_sleep(duration: float) -> None:
            entered.set()
            release.wait(timeout=10)

        self.fake_sleep.side_effect = _blocking_sleep

        result: dict[str, Any] = {}

        def _run_a() -> None:
            result["reply"] = self.stub.ExecuteCommand(self._valid_transfer_command())

        thread_a = threading.Thread(target=_run_a)
        thread_a.start()
        self.assertTrue(entered.wait(timeout=5))

        bad_fields = dict(_ALL_TRANSFER_FIELDS)
        del bad_fields["volume"]
        bad_command = tool_base_pb2.Command(
            fast=fast_pb2.Command(transfer=fast_pb2.Command.Transfer(**bad_fields)))
        bad_reply = self.stub.ExecuteCommand(bad_command)
        self.assertEqual(bad_reply.response, INVALID_ARGUMENTS)
        self.assertIn("volume", bad_reply.error_message)
        self.assertEqual(MessageToDict(bad_reply.meta_data)["kind"], "needsInput")

        self.assertTrue(thread_a.is_alive())

        release.set()
        thread_a.join(timeout=5)
        self.assertFalse(thread_a.is_alive())
        self.assertEqual(result["reply"].response, SUCCESS)

        self.mock_open_service.assert_not_called()


class TestTransferMapping(unittest.TestCase):
    def setUp(self) -> None:
        self.server = FastServer()
        self.server.service = MagicMock(spec=FastService)
        self.server.config = fast_pb2.Config(host="h")
        self.server.status = READY

    def test_ran_is_success_with_ran_metadata(self) -> None:
        service = cast(MagicMock, self.server.service)
        outcome = RunOutcome(state="idle", done=True, percent=100)
        service.run_transfer.return_value = Ran(outcome=outcome)

        params = fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS)
        reply = self.server.Transfer(params)

        self.assertEqual(reply.response, tool_base_pb2.SUCCESS)
        self.assertTrue(reply.return_reply)
        self.assertEqual(MessageToDict(reply.meta_data)["kind"], "ran")

        service.run_transfer.assert_called_once()
        call = service.run_transfer.call_args
        expected_request = TransferRequest(**{
            f.name: getattr(params, f.name) for f in fields(TransferRequest)
        })
        self.assertEqual(call.args[0], expected_request)
        self.assertIsNone(call.kwargs["expected_tray_id"])
        self.assertIsNone(call.kwargs["options"].cancel)


class _MockedFastServerTestCase(unittest.TestCase):
    """Shared setUp/tearDown for tests driving FastServer against a
    MagicMock(spec=FastService). D-18 (Task 2 behavior #11): abort/pause/resume
    must never be called by this adapter, enforced once per test class in
    tearDown."""

    def setUp(self) -> None:
        self.server = FastServer()
        self.service = MagicMock(spec=FastService)
        self.server.service = self.service
        self.server.config = fast_pb2.Config(host="h")
        self.server.status = READY

    def tearDown(self) -> None:
        self.service.abort.assert_not_called()
        self.service.pause.assert_not_called()
        self.service.resume.assert_not_called()


class TestResultMapping(_MockedFastServerTestCase):
    def _transfer_params(self) -> "fast_pb2.Command.Transfer":
        return fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS)

    def test_transfer_result_variants(self) -> None:
        cases = [
            ("ran", Ran(outcome=RunOutcome(state="idle", done=True, percent=100)),
             SUCCESS, ""),
            ("rejected", Rejected(
                stage="validate",
                findings=[Finding(-813, "UnknownPlateID", "validation", "x")]),
             INVALID_ARGUMENTS, "-813 UnknownPlateID"),
            ("needsInput", NeedsInput(missing=["volume"]),
             INVALID_ARGUMENTS, "missing or invalid: volume"),
            ("needsConfirmation", NeedsConfirmation(tray_id=90, caddy_deck=2),
             ERROR_FROM_TOOL, "tray 90 installed, no expected tray configured"),
            ("deckSuggestion", DeckSuggestion(
                moves=[DeckMove(plate_id=1, description="plate one", from_deck=1, to_deck=2)],
                tray_ejected=True, outcome=RunOutcome(state="idle", done=False, percent=0)),
             ERROR_FROM_TOOL, "move plate"),
            ("refused", Refused(reason="instrument not idle", state="running"),
             NOT_READY, "instrument not ready"),
            ("paused", Paused(outcome=RunOutcome(state="paused", done=False, percent=40)),
             ERROR_FROM_TOOL, "run paused"),
            ("aborted", Aborted(outcome=RunOutcome(state="aborted", done=False, percent=40)),
             ERROR_FROM_TOOL, "run aborted"),
            ("timedOut", TimedOut(outcome=RunOutcome(state="timeout", done=False, percent=40)),
             ERROR_FROM_TOOL, "NOT aborted"),
            ("cancelled", Cancelled(percent=40), ERROR_FROM_TOOL, "cancelled by operator"),
        ]
        for kind, result, expected_response, fragment in cases:
            with self.subTest(kind=kind):
                self.service.reset_mock()
                self.service.run_transfer.return_value = result
                reply = self.server.Transfer(self._transfer_params())
                self.assertEqual(reply.response, expected_response)
                self.assertIn(fragment, reply.error_message)
                self.assertTrue(reply.return_reply)
                self.assertEqual(MessageToDict(reply.meta_data)["kind"], kind)

    def test_run_protocol_result_variants(self) -> None:
        cases = [
            ("ran", Ran(outcome=RunOutcome(state="idle", done=True, percent=100)), SUCCESS, ""),
            ("rejected", Rejected(
                stage="validate",
                findings=[Finding(-813, "UnknownPlateID", "validation", "x")]),
             INVALID_ARGUMENTS, "-813 UnknownPlateID"),
            ("refused", Refused(reason="instrument not idle", state="running"),
             NOT_READY, "instrument not ready"),
            ("timedOut", TimedOut(outcome=RunOutcome(state="timeout", done=False, percent=40)),
             ERROR_FROM_TOOL, "NOT aborted"),
        ]
        for kind, result, expected_response, fragment in cases:
            with self.subTest(kind=kind):
                self.service.reset_mock()
                self.service.run_protocol.return_value = result
                reply = self.server.RunProtocol(fast_pb2.Command.RunProtocol(csv="x"))
                self.assertEqual(reply.response, expected_response)
                self.assertIn(fragment, reply.error_message)
                self.assertTrue(reply.return_reply)
                self.assertEqual(MessageToDict(reply.meta_data)["kind"], kind)

    def test_run_protocol_always_verify_layout_true_and_no_cancel(self) -> None:
        self.service.run_protocol.return_value = Ran(
            outcome=RunOutcome(state="idle", done=True, percent=100))
        self.server.RunProtocol(fast_pb2.Command.RunProtocol(csv="x"))
        call = self.service.run_protocol.call_args
        self.assertTrue(call.kwargs["verify_layout"])
        self.assertIsNone(call.kwargs["options"].cancel)

    def test_run_protocol_timeout_resolution(self) -> None:
        self.service.run_protocol.return_value = Ran(
            outcome=RunOutcome(state="idle", done=True, percent=100))

        # Per-command timeout_s overrides Config.run_timeout_s.
        self.server.config = fast_pb2.Config(host="h", run_timeout_s=600.0)
        self.server.RunProtocol(fast_pb2.Command.RunProtocol(csv="x", timeout_s=30.0))
        self.assertEqual(
            self.service.run_protocol.call_args.kwargs["options"].timeout_s, 30.0)

        # Config.run_timeout_s used when per-command is unset.
        self.service.reset_mock()
        self.service.run_protocol.return_value = Ran(
            outcome=RunOutcome(state="idle", done=True, percent=100))
        self.server.RunProtocol(fast_pb2.Command.RunProtocol(csv="x"))
        self.assertEqual(
            self.service.run_protocol.call_args.kwargs["options"].timeout_s, 600.0)

        # Config.run_timeout_s == 0 gives timeout_s None.
        self.service.reset_mock()
        self.service.run_protocol.return_value = Ran(
            outcome=RunOutcome(state="idle", done=True, percent=100))
        self.server.config = fast_pb2.Config(host="h", run_timeout_s=0.0)
        self.server.RunProtocol(fast_pb2.Command.RunProtocol(csv="x"))
        self.assertIsNone(
            self.service.run_protocol.call_args.kwargs["options"].timeout_s)


class TestReadAndRecoveryCommands(_MockedFastServerTestCase):
    def test_validate_protocol_no_findings_is_success(self) -> None:
        self.service.validate.return_value = ValidationReport(findings=[], csv="x")
        reply = self.server.ValidateProtocol(fast_pb2.Command.ValidateProtocol(csv="x"))
        self.assertEqual(reply.response, SUCCESS)
        meta = MessageToDict(reply.meta_data)
        self.assertEqual(meta["kind"], "validationReport")
        self.assertTrue(meta["valid"])

    def test_validate_protocol_with_findings_is_invalid_arguments(self) -> None:
        self.service.validate.return_value = ValidationReport(
            findings=[Finding(-9000, "LocalParseError", "local", "bad csv")], csv="x")
        reply = self.server.ValidateProtocol(fast_pb2.Command.ValidateProtocol(csv="x"))
        self.assertEqual(reply.response, INVALID_ARGUMENTS)
        self.assertIn("validation findings:", reply.error_message)
        meta = MessageToDict(reply.meta_data)
        self.assertEqual(meta["kind"], "validationReport")
        self.assertFalse(meta["valid"])

    def test_get_status_is_success_with_status_dict(self) -> None:
        self.service.status.return_value = {
            "state": "idle", "percentProgress": 0, "remainingTime": 0, "done": True}
        reply = self.server._get_status(fast_pb2.Command.GetStatus())
        self.assertEqual(reply.response, SUCCESS)
        meta = MessageToDict(reply.meta_data)
        self.assertEqual(meta["state"], "idle")

    def test_get_status_dual_dispatch_delegates_health_rpc_to_super(self) -> None:
        from google.protobuf import empty_pb2
        reply = self.server.GetStatus(empty_pb2.Empty(), None)
        self.assertIsInstance(reply, tool_base_pb2.StatusReply)

    def test_get_status_dual_dispatch_single_arg_is_intent_command(self) -> None:
        self.service.status.return_value = {
            "state": "idle", "percentProgress": 0, "remainingTime": 0, "done": True}
        reply = cast(tool_base_pb2.ExecuteCommandReply,
                    self.server.GetStatus(fast_pb2.Command.GetStatus()))
        self.assertEqual(reply.response, SUCCESS)
        self.service.status.assert_called_once()

    def test_get_tip_status_tip_scan_is_success(self) -> None:
        self.service.tip_status.return_value = TipScan(tips={"a": 1})
        reply = self.server.GetTipStatus(fast_pb2.Command.GetTipStatus())
        self.assertEqual(reply.response, SUCCESS)

    def test_get_tip_status_refused_is_not_ready(self) -> None:
        self.service.tip_status.return_value = Refused(reason="instrument is running",
                                                        state="running")
        reply = self.server.GetTipStatus(fast_pb2.Command.GetTipStatus())
        self.assertEqual(reply.response, NOT_READY)

    def test_scan_tips_passes_is_tip_broken(self) -> None:
        self.service.scan_tips.return_value = TipRescan(response={})
        self.server.ScanTips(fast_pb2.Command.ScanTips(is_tip_broken=True))
        self.service.scan_tips.assert_called_once_with(is_tip_broken=True)

    def test_eject_tray_is_success(self) -> None:
        self.service.eject_tray.return_value = TrayEjected(response={})
        reply = self.server.EjectTray(fast_pb2.Command.EjectTray())
        self.assertEqual(reply.response, SUCCESS)


class TestExpectedTrayId(_MockedFastServerTestCase):
    def _run_transfer_once(self) -> Any:
        self.service.run_transfer.return_value = Ran(
            outcome=RunOutcome(state="idle", done=True, percent=100))
        self.server.Transfer(fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS))
        return self.service.run_transfer.call_args.kwargs["expected_tray_id"]

    def test_no_config_and_no_per_command_gives_none(self) -> None:
        self.server.config = fast_pb2.Config(host="h", expected_tray_id=0)
        self.assertIsNone(self._run_transfer_once())

    def test_config_only_gives_config_value(self) -> None:
        self.server.config = fast_pb2.Config(host="h", expected_tray_id=90)
        self.assertEqual(self._run_transfer_once(), 90)

    def test_per_command_overrides_config(self) -> None:
        self.server.config = fast_pb2.Config(host="h", expected_tray_id=90)
        self.service.run_transfer.return_value = Ran(
            outcome=RunOutcome(state="idle", done=True, percent=100))
        fields_with_override = dict(_ALL_TRANSFER_FIELDS, expected_tray_id=91)
        self.server.Transfer(fast_pb2.Command.Transfer(**fields_with_override))
        self.assertEqual(
            self.service.run_transfer.call_args.kwargs["expected_tray_id"], 91)


class TestMotionSerialization(_MockedFastServerTestCase):
    def test_second_motion_command_refused_while_first_in_flight(self) -> None:
        release = threading.Event()
        entered = threading.Event()

        def _blocking_run_transfer(*args: Any, **kwargs: Any) -> Any:
            entered.set()
            release.wait(timeout=5)
            return Ran(outcome=RunOutcome(state="idle", done=True, percent=100))

        self.service.run_transfer.side_effect = _blocking_run_transfer
        self.service.tip_status.return_value = TipScan(tips={})
        self.service.validate.return_value = ValidationReport(findings=[], csv="x")

        thread_a = threading.Thread(
            target=self.server.Transfer,
            args=(fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS),))
        thread_a.start()
        self.assertTrue(entered.wait(timeout=5))

        try:
            reply = self.server.Transfer(fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS))
            self.assertEqual(reply.response, NOT_READY)
            self.assertIn("another motion command is in progress", reply.error_message)

            reply = self.server.RunProtocol(fast_pb2.Command.RunProtocol(csv="x"))
            self.assertEqual(reply.response, NOT_READY)

            reply = self.server.ScanTips(fast_pb2.Command.ScanTips())
            self.assertEqual(reply.response, NOT_READY)

            reply = self.server.EjectTray(fast_pb2.Command.EjectTray())
            self.assertEqual(reply.response, NOT_READY)

            # Not gated by the motion lock.
            reply = self.server.GetTipStatus(fast_pb2.Command.GetTipStatus())
            self.assertEqual(reply.response, SUCCESS)
            reply = self.server.ValidateProtocol(fast_pb2.Command.ValidateProtocol(csv="x"))
            self.assertEqual(reply.response, SUCCESS)
        finally:
            release.set()
            thread_a.join(timeout=5)

        self.service.run_transfer.assert_called_once()

        # Lock released: a fresh Transfer succeeds.
        self.service.run_transfer.side_effect = None
        self.service.run_transfer.return_value = Ran(
            outcome=RunOutcome(state="idle", done=True, percent=100))
        reply = self.server.Transfer(fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS))
        self.assertEqual(reply.response, SUCCESS)

    def test_lock_released_on_exception_and_next_transfer_acquires_normally(self) -> None:
        self.service.run_transfer.side_effect = RuntimeError("boom")
        with self.assertRaises(RuntimeError):
            self.server.Transfer(fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS))

        self.service.run_transfer.side_effect = None
        self.service.run_transfer.return_value = Ran(
            outcome=RunOutcome(state="idle", done=True, percent=100))
        reply = self.server.Transfer(fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS))
        self.assertEqual(reply.response, SUCCESS)


class TestTransportErrors(_MockedFastServerTestCase):
    def test_instrument_http_error_is_error_from_tool_single_line_bounded(self) -> None:
        body = "boom\n at Vendor.Stack()\n" + "x" * 400
        self.service.run_transfer.side_effect = InstrumentHTTPError(500, body)
        reply = self.server.Transfer(fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS))
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertTrue(reply.error_message.startswith("instrument HTTP 500: "))
        self.assertNotIn("\n", reply.error_message)
        self.assertLessEqual(len(reply.error_message), 230)

    def test_httpx_connect_error_is_error_from_tool(self) -> None:
        self.service.run_transfer.side_effect = httpx.ConnectError("refused")
        reply = self.server.Transfer(fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS))
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertEqual(reply.error_message, "instrument unreachable: ConnectError: refused")


class TestNotConfigured(unittest.TestCase):
    def setUp(self) -> None:
        self.server = FastServer()
        self.server.config = fast_pb2.Config(host="h")
        self.server.status = READY
        self.assertIsNone(self.server.service)

    def test_every_command_refuses_when_not_connected(self) -> None:
        checks = [
            ("Transfer", fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS)),
            ("RunProtocol", fast_pb2.Command.RunProtocol(csv="x")),
            ("ValidateProtocol", fast_pb2.Command.ValidateProtocol(csv="x")),
            ("GetTipStatus", fast_pb2.Command.GetTipStatus()),
            ("ScanTips", fast_pb2.Command.ScanTips()),
            ("EjectTray", fast_pb2.Command.EjectTray()),
        ]
        for name, params in checks:
            with self.subTest(command=name):
                reply = getattr(self.server, name)(params)
                self.assertEqual(reply.response, NOT_READY)
                self.assertIn("not connected to an instrument", reply.error_message)

        with self.subTest(command="GetStatus"):
            reply = self.server._get_status(fast_pb2.Command.GetStatus())
            self.assertEqual(reply.response, NOT_READY)
            self.assertIn("not connected to an instrument", reply.error_message)


class TestReconfigure(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self._env_patcher = patch.dict(os.environ, {"FAST_MCP_LOCK_DIR": self._tmpdir.name})
        self._env_patcher.start()
        self.addCleanup(self._env_patcher.stop)
        self.addCleanup(self._tmpdir.cleanup)
        self.server = FastServer()
        self.addCleanup(self._close_owned)

    def _close_owned(self) -> None:
        if self.server._owned is not None:
            self.server._owned.close()

    def test_reconfigure_different_endpoint_releases_old_lock_first(self) -> None:
        from fast_mcp.owner_lock import acquire_owner_lock

        port_a = _free_tcp_port()
        port_b = _free_tcp_port()

        config_a = tool_base_pb2.Config(
            simulated=False, toolId="fast-test",
            fast=fast_pb2.Config(host="127.0.0.1", port=port_a))
        reply = self.server.Configure(config_a, None)  # type: ignore[arg-type]
        self.assertEqual(reply.response, tool_base_pb2.SUCCESS)

        config_b = tool_base_pb2.Config(
            simulated=False, toolId="fast-test",
            fast=fast_pb2.Config(host="127.0.0.1", port=port_b))
        reply = self.server.Configure(config_b, None)  # type: ignore[arg-type]
        self.assertEqual(reply.response, tool_base_pb2.SUCCESS)

        # A's lock is free: a fresh acquire succeeds (and is released again).
        lock_a = acquire_owner_lock("127.0.0.1", port_a, owner="mcp",
                                    lock_dir=self._tmpdir.name)
        lock_a.release()

        # B's lock is held by the server's own FastService.
        from fast_mcp.owner_lock import InstrumentOwnedError
        with self.assertRaises(InstrumentOwnedError):
            acquire_owner_lock("127.0.0.1", port_b, owner="mcp", lock_dir=self._tmpdir.name)


class TestOneToOneSurface(unittest.TestCase):
    def test_command_to_service_method_matches_oneof_message_names(self) -> None:
        oneof_fields = fast_pb2.Command.DESCRIPTOR.oneofs_by_name["command"].fields
        message_names = {f.message_type.name for f in oneof_fields}
        self.assertEqual(set(COMMAND_TO_SERVICE_METHOD), message_names)

    def test_every_key_is_callable_fastserver_attribute(self) -> None:
        server = FastServer()
        for name in COMMAND_TO_SERVICE_METHOD:
            self.assertTrue(callable(getattr(server, name)), name)

    def test_every_value_is_fastservice_attribute(self) -> None:
        for method_name in COMMAND_TO_SERVICE_METHOD.values():
            self.assertTrue(hasattr(FastService, method_name), method_name)

    def test_invoking_each_command_records_exactly_one_mapped_call(self) -> None:
        server = FastServer()
        service = MagicMock(spec=FastService)
        server.service = service
        server.config = fast_pb2.Config(host="h")
        service.run_transfer.return_value = Ran(
            outcome=RunOutcome(state="idle", done=True, percent=100))
        service.run_protocol.return_value = Ran(
            outcome=RunOutcome(state="idle", done=True, percent=100))
        service.validate.return_value = ValidationReport(findings=[], csv="x")
        service.status.return_value = {"state": "idle", "percentProgress": 0,
                                       "remainingTime": 0, "done": True}
        service.tip_status.return_value = TipScan(tips={})
        service.scan_tips.return_value = TipRescan(response={})
        service.eject_tray.return_value = TrayEjected(response={})

        calls = {
            "Transfer": (fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS),),
            "RunProtocol": (fast_pb2.Command.RunProtocol(csv="x"),),
            "ValidateProtocol": (fast_pb2.Command.ValidateProtocol(csv="x"),),
            "GetStatus": (fast_pb2.Command.GetStatus(),),
            "GetTipStatus": (fast_pb2.Command.GetTipStatus(),),
            "ScanTips": (fast_pb2.Command.ScanTips(),),
            "EjectTray": (fast_pb2.Command.EjectTray(),),
        }
        for command_name, args in calls.items():
            with self.subTest(command=command_name):
                service.reset_mock()
                getattr(server, command_name)(*args)
                mocked = getattr(service, COMMAND_TO_SERVICE_METHOD[command_name])
                mocked.assert_called_once()

    def test_transfer_field_names_match_transfer_request_order(self) -> None:
        transfer_fields = [
            f.name for f in fast_pb2.Command.Transfer.DESCRIPTOR.fields
            if f.name != "expected_tray_id"
        ]
        request_fields = [f.name for f in fields(TransferRequest)]
        self.assertEqual(transfer_fields, request_fields)


class TestRegistration(unittest.TestCase):
    def test_tool_type_fast_is_registered(self) -> None:
        self.assertIsInstance(controller_pb2.ToolType.Value("fast"), int)  # type: ignore[attr-defined]

    def test_command_oneof_registration(self) -> None:
        field = tool_base_pb2.Command.DESCRIPTOR.fields_by_name["fast"]
        self.assertEqual(field.containing_oneof.name, "tool_command")

    def test_config_oneof_registration(self) -> None:
        field = tool_base_pb2.Config.DESCRIPTOR.fields_by_name["fast"]
        self.assertEqual(field.containing_oneof.name, "config")


class TestRequirementsPin(unittest.TestCase):
    def test_requirements_txt_pins_exactly_one_credential_free_sha(self) -> None:
        req_path = _REPO_ROOT / "tools" / "fast" / "requirements.txt"
        lines = [
            line.strip() for line in req_path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        self.assertEqual(len(lines), 1)
        pattern = (r"^fast-mcp @ git\+https://gitlab\.formulatrix\.com/"
                  r"nikkopg/fast-mcp\.git@[0-9a-f]{40}$")
        self.assertRegex(lines[0], pattern)

        pinned_sha = lines[0].rsplit("@", 1)[1]
        direct_url = json.loads(
            importlib.metadata.distribution("fast_mcp").read_text("direct_url.json") or "{}")
        self.assertEqual(direct_url["vcs_info"]["commit_id"], pinned_sha)


if __name__ == "__main__":
    unittest.main()
