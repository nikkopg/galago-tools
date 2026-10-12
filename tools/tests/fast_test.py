import ast
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
from google.protobuf import empty_pb2
from google.protobuf.json_format import MessageToDict

# Item 6 (PROJECT.md "Fork CI GitLab credential"): option approve-all-ci-skip (6b).
# The private fast-mcp core (tools/fast/requirements.txt, a git+https install
# against an internal GitLab) is not reachable from a GitHub-hosted CI runner
# (RESEARCH.md Pitfall 4) and no deploy-token secret is created for it. Every
# import that depends on that core -- including httpx, which is pulled in only
# transitively through fast_mcp's own install, never by this fork's own
# requirements.txt -- is collected into this one try block so a missing core
# skips these tests with a clear reason instead of erroring with a raw import
# traceback. The local Python 3.10 `bin/make test` run (core installed) stays
# the authoritative gate.
try:
    import httpx

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
    from fast_mcp.resources import default_openapi_path
    from fast_mcp.run_control import RunHandle
    from fast_mcp.service import FastService, TransferRequest
    from fast_mcp.session import InstrumentSession
    from fast_mcp.transport import InstrumentHTTPError

    from tools.fast.server import (
        CONTROL_COMMANDS,
        COMMAND_TO_SERVICE_METHOD,
        MOTION_LOCK_COMMANDS,
        FastServer,
        _check_args,
    )
except ModuleNotFoundError as exc:
    if exc.name and exc.name.split(".")[0] in ("fast_mcp", "httpx"):
        raise unittest.SkipTest(
            "fast_mcp core is not installed (private GitLab dependency, see "
            "tools/fast/requirements.txt); the local Python 3.10 bin/make test run "
            "is the authoritative gate") from exc
    raise

from tools.grpc_interfaces import controller_pb2, fast_pb2, tool_base_pb2
from tools.grpc_interfaces.tool_base_pb2 import (
    BUSY,
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

# Copied verbatim from fast-mcp's fixtures/protocol-examples/example1.csv so this
# fork test does not depend on the fast-mcp checkout's location (4 task rows:
# PickTip, Aspirate, Dispense, EjectTip).
EXAMPLE1_CSV = """PlateList,1,,1
PickTip,2,8,12
Aspirate,1,8,12,A,1,10
Dispense,3,8,12,A,1,10
EjectTip"""


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


class TestControlCommandsOverGrpc(unittest.TestCase):
    """D-04/ADP-08: the real-mode gRPC tracer for Pause (Task 1), extended
    (Task 2/3) into the concurrency test proving Pause/Resume/Abort reach a
    Transfer in flight through the real base_server.ExecuteCommand gate.
    Deliberately does NOT inherit _MockedFastServerTestCase: this class calls
    control methods on purpose, so its own tearDown allows at most one call
    each -- no test here may reach a control method more than the operator
    asked."""

    def setUp(self) -> None:
        self.server = FastServer()
        self.service = MagicMock(spec=FastService)
        self.server.service = self.service
        self.server.config = fast_pb2.Config(host="h")
        self.server.status = READY

        self._grpc_port = _free_tcp_port()
        self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
        add_ToolDriverServicer_to_server(self.server, self._server)
        self._server.add_insecure_port(f"127.0.0.1:{self._grpc_port}")
        self._server.start()
        self.addCleanup(self._server.stop, None)

        self._channel = grpc.insecure_channel(f"127.0.0.1:{self._grpc_port}")
        self.addCleanup(self._channel.close)
        self.stub = ToolDriverStub(self._channel)

    def tearDown(self) -> None:
        self.assertLessEqual(self.service.pause.call_count, 1)
        self.assertLessEqual(self.service.resume.call_count, 1)
        self.assertLessEqual(self.service.abort.call_count, 1)

    def _fast(self, **command: Any) -> tool_base_pb2.Command:
        return tool_base_pb2.Command(fast=fast_pb2.Command(**command))

    def _health(self) -> tool_base_pb2.StatusReply:
        return cast(tool_base_pb2.StatusReply, self.stub.GetStatus(empty_pb2.Empty()))

    def test_pause_over_grpc_reaches_service_as_soft_pause(self) -> None:
        self.service.pause.return_value = {"errorCode": 0}
        reply = self.stub.ExecuteCommand(self._fast(pause=fast_pb2.Command.Pause()))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.service.pause.assert_called_once_with(hard=False)
        self.assertEqual(self.service.status.call_count, 0)
        self.service.resume.assert_not_called()
        self.service.abort.assert_not_called()
        self.service.wait.assert_not_called()
        self.assertEqual(self._health().status, READY)

    def _start_blocked_transfer(self) -> tuple[threading.Event, threading.Thread, dict[str, Any]]:
        """Blocks a real Transfer sent over the gRPC stub inside run_transfer,
        so base_server.ExecuteCommand's parseCommand/isReady/setStatus(BUSY)
        bracket is actually exercised (RESEARCH Pitfall 6) -- driving the
        Transfer through self.server.Transfer(...) directly would never reach
        that gate."""
        release = threading.Event()
        entered = threading.Event()

        def _blocking_run_transfer(*args: Any, **kwargs: Any) -> Any:
            entered.set()
            release.wait(timeout=10)
            return Ran(outcome=RunOutcome(state="idle", done=True, percent=100))

        self.service.run_transfer.side_effect = _blocking_run_transfer

        result: dict[str, Any] = {}

        def _run_transfer() -> None:
            result["transfer"] = self.stub.ExecuteCommand(
                self._fast(transfer=fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS)))

        thread = threading.Thread(target=_run_transfer)
        thread.start()
        # Cleanups run LIFO: release before join, so a failing assertion above
        # never leaves the gRPC worker thread blocked forever.
        self.addCleanup(thread.join, 10)
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(timeout=5))
        return release, thread, result

    def test_pause_resume_abort_reach_service_while_transfer_in_flight(self) -> None:
        self.service.pause.return_value = {"errorCode": 0}
        self.service.resume.return_value = {"errorCode": 0}
        self.service.abort.return_value = {"errorCode": 0}

        release, thread, result = self._start_blocked_transfer()
        self.assertEqual(self._health().status, BUSY)

        for field, message, method, kwargs in (
            ("pause", fast_pb2.Command.Pause(), "pause", {"hard": False}),
            ("resume", fast_pb2.Command.Resume(is_tip_broken="no"), "resume",
             {"is_tip_broken": False}),
            ("abort", fast_pb2.Command.Abort(return_liquid="no"), "abort",
             {"return_liquid": False}),
        ):
            status_before = self.service.status.call_count
            reply = self.stub.ExecuteCommand(self._fast(**{field: message}))
            self.assertEqual(reply.response, SUCCESS, reply.error_message)
            getattr(self.service, method).assert_called_once_with(**kwargs)
            self.assertEqual(self.service.status.call_count, status_before)
            self.assertEqual(self._health().status, BUSY)
            self.assertTrue(thread.is_alive())

        self.service.wait.assert_not_called()
        self.service.status.assert_not_called()

        release.set()
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["transfer"].response, SUCCESS)
        self.service.run_transfer.assert_called_once()
        self.assertEqual(self._health().status, READY)


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
    MagicMock(spec=FastService). D-18 (Task 2 behavior #11), as amended by
    dual-frontend section 11 #1: abort/pause/resume are never called on the
    adapter's own initiative -- only the operator's Pause/Abort/Resume
    commands may call them, and those are tested in TestRecoveryCommands and
    TestControlCommandsOverGrpc, which do not use this base. Enforced once
    per test class in tearDown."""

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
             ERROR_FROM_TOOL,
             "fix the deck, then send Resume (is_tip_broken) or Abort (return_liquid)"),
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

    def test_run_protocol_passes_no_verify_layout_and_no_cancel(self) -> None:
        self.service.run_protocol.return_value = Ran(
            outcome=RunOutcome(state="idle", done=True, percent=100))
        self.server.RunProtocol(fast_pb2.Command.RunProtocol(csv="x"))
        call = self.service.run_protocol.call_args
        self.assertNotIn("verify_layout", call.kwargs)
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

    def test_per_command_zero_falls_back_to_config(self) -> None:
        """D-26, GAL-05 F2: galago-core's blank form field arrives as a
        per-command expected_tray_id of 0, which must fall back to Config
        (the live runbook B5 failure, attempts 1-2)."""
        self.server.config = fast_pb2.Config(host="h", expected_tray_id=90)
        self.service.run_transfer.return_value = Ran(
            outcome=RunOutcome(state="idle", done=True, percent=100))
        fields_with_zero = dict(_ALL_TRANSFER_FIELDS, expected_tray_id=0)
        self.server.Transfer(fast_pb2.Command.Transfer(**fields_with_zero))
        self.assertEqual(
            self.service.run_transfer.call_args.kwargs["expected_tray_id"], 90)

    def test_per_command_zero_and_config_zero_gives_none(self) -> None:
        """D-26: both unset (0 means unset on both sides) passes None."""
        self.server.config = fast_pb2.Config(host="h", expected_tray_id=0)
        self.service.run_transfer.return_value = Ran(
            outcome=RunOutcome(state="idle", done=True, percent=100))
        fields_with_zero = dict(_ALL_TRANSFER_FIELDS, expected_tray_id=0)
        self.server.Transfer(fast_pb2.Command.Transfer(**fields_with_zero))
        self.assertIsNone(
            self.service.run_transfer.call_args.kwargs["expected_tray_id"])

    def test_blank_per_command_with_no_config_is_error_from_tool(self) -> None:
        """D-26: both unset gives None passed to run_transfer, which still
        fails closed -- an installed tray with no expected tray configured
        comes back as ERROR_FROM_TOOL, not a silent auto-confirm."""
        self.server.config = fast_pb2.Config(host="h", expected_tray_id=0)
        self.service.run_transfer.return_value = NeedsConfirmation(
            tray_id=90, caddy_deck=None)
        fields_with_zero = dict(_ALL_TRANSFER_FIELDS, expected_tray_id=0)
        reply = self.server.Transfer(fast_pb2.Command.Transfer(**fields_with_zero))
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("no expected tray configured", reply.error_message)


class TestMotionSerialization(_MockedFastServerTestCase):
    def test_motion_lock_and_control_command_sets_are_disjoint(self) -> None:
        self.assertEqual(MOTION_LOCK_COMMANDS, {"Transfer", "RunProtocol", "ScanTips", "EjectTray"})
        self.assertEqual(CONTROL_COMMANDS, {"pause", "resume", "abort"})

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


class TestControlCommandsBypassMotionLock(unittest.TestCase):
    """D-06/D-07/ADP-04: Resume's two paths and the lock-free guarantee for
    Pause and Abort, driven directly against FastServer (TestControlCommandsOverGrpc
    covers the same guarantees through the gRPC override). Does not inherit
    _MockedFastServerTestCase: it calls control methods on purpose and
    manipulates _motion_lock directly."""

    def setUp(self) -> None:
        self.server = FastServer()
        self.service = MagicMock(spec=FastService)
        self.server.service = self.service
        self.server.config = fast_pb2.Config(host="h")
        self.server.status = READY

    def test_pause_and_abort_never_touch_the_motion_lock(self) -> None:
        spy = MagicMock(wraps=threading.Lock())
        self.server._motion_lock = spy
        self.service.pause.return_value = {"errorCode": 0}
        self.service.abort.return_value = {"errorCode": 0}

        reply = self.server.Pause(fast_pb2.Command.Pause())
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        reply = self.server.Abort(fast_pb2.Command.Abort(return_liquid="no"))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)

        spy.acquire.assert_not_called()
        spy.release.assert_not_called()

    def test_pause_and_abort_succeed_while_another_command_holds_the_lock(self) -> None:
        self.server._motion_lock.acquire()
        self.addCleanup(self.server._motion_lock.release)
        self.service.pause.return_value = {"errorCode": 0}
        self.service.abort.return_value = {"errorCode": 0}

        reply = self.server.Pause(fast_pb2.Command.Pause())
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        reply = self.server.Abort(fast_pb2.Command.Abort(return_liquid="no"))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)

        self.service.pause.assert_called_once_with(hard=False)
        self.service.abort.assert_called_once_with(return_liquid=False)

    def test_resume_with_a_run_in_flight_returns_on_acceptance_without_waiting(self) -> None:
        self.server._motion_lock.acquire()
        self.addCleanup(self.server._motion_lock.release)
        self.service.resume.return_value = {"errorCode": 0}

        reply = self.server.Resume(fast_pb2.Command.Resume(is_tip_broken="yes"))

        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.service.resume.assert_called_once_with(is_tip_broken=True)
        self.service.wait.assert_not_called()
        self.assertTrue(self.server._motion_lock.locked())

    def test_resume_in_flight_failures_never_wait_or_release_the_owners_lock(self) -> None:
        self.server._motion_lock.acquire()
        self.addCleanup(self.server._motion_lock.release)

        cases: list[tuple[str, Any, str]] = [
            ("refused", Refused(reason="no paused protocol to resume", state="running"),
             "instrument not ready: no paused protocol to resume (state running)"),
            ("rejected", {"errorCode": -2}, "instrument rejected resume: errorCode -2"),
        ]
        for name, outcome, fragment in cases:
            with self.subTest(case=name):
                self.service.reset_mock()
                self.service.resume.return_value = outcome
                reply = self.server.Resume(fast_pb2.Command.Resume(is_tip_broken="no"))
                self.assertEqual(reply.response, ERROR_FROM_TOOL)
                if name == "refused":
                    self.assertEqual(reply.error_message, fragment)
                else:
                    self.assertIn(fragment, reply.error_message)
                self.service.wait.assert_not_called()
                self.assertTrue(self.server._motion_lock.locked())

        with self.subTest(case="unreachable"):
            self.service.reset_mock()
            self.service.resume.side_effect = httpx.ConnectError("refused")
            reply = self.server.Resume(fast_pb2.Command.Resume(is_tip_broken="no"))
            self.assertEqual(reply.response, ERROR_FROM_TOOL)
            self.assertEqual(
                reply.error_message, "instrument unreachable: ConnectError: refused")
            self.service.wait.assert_not_called()
            self.assertTrue(self.server._motion_lock.locked())

    def test_crash_recovery_resume_waits_and_holds_the_lock(self) -> None:
        self.service.resume.return_value = {"errorCode": 0}
        entered = threading.Event()
        release = threading.Event()

        def _blocking_wait(*args: Any, **kwargs: Any) -> Any:
            entered.set()
            release.wait(timeout=10)
            return Ran(outcome=RunOutcome(state="idle", done=True, percent=100))

        self.service.wait.side_effect = _blocking_wait

        result: dict[str, Any] = {}

        def _run_resume() -> None:
            result["reply"] = self.server.Resume(fast_pb2.Command.Resume(is_tip_broken="no"))

        thread = threading.Thread(target=_run_resume)
        thread.start()
        # Cleanups run LIFO: release before join, so a failing assertion
        # above never leaves the worker thread blocked forever.
        self.addCleanup(thread.join, 10)
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(timeout=5))

        direct = self.server.Transfer(fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS))
        self.assertEqual(direct.response, NOT_READY)
        self.assertIn("another motion command is in progress", direct.error_message)
        self.service.run_transfer.assert_not_called()

        release.set()
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())

        reply = result["reply"]
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.assertEqual(MessageToDict(reply.meta_data)["kind"], "ran")
        self.assertFalse(self.server._motion_lock.locked())


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
            ("Abort", fast_pb2.Command.Abort(return_liquid="no")),
            ("Resume", fast_pb2.Command.Resume(is_tip_broken="no")),
            ("Pause", fast_pb2.Command.Pause()),
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
        service.abort.return_value = {"errorCode": 0}
        service.resume.return_value = {"errorCode": 0}
        service.pause.return_value = {"errorCode": 0}
        service.wait.return_value = Ran(
            outcome=RunOutcome(state="idle", done=True, percent=100))

        calls = {
            "Transfer": (fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS),),
            "RunProtocol": (fast_pb2.Command.RunProtocol(csv="x"),),
            "ValidateProtocol": (fast_pb2.Command.ValidateProtocol(csv="x"),),
            "GetStatus": (fast_pb2.Command.GetStatus(),),
            "GetTipStatus": (fast_pb2.Command.GetTipStatus(),),
            "ScanTips": (fast_pb2.Command.ScanTips(),),
            "EjectTray": (fast_pb2.Command.EjectTray(),),
            "Abort": (fast_pb2.Command.Abort(return_liquid="no"),),
            "Resume": (fast_pb2.Command.Resume(is_tip_broken="no"),),
            "Pause": (fast_pb2.Command.Pause(),),
        }
        self.assertEqual(set(calls), set(COMMAND_TO_SERVICE_METHOD))
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


class TestCheckArgs(unittest.TestCase):
    """D-15: pure, instrument-free structural argument checks (both modes)."""

    def test_fully_valid_transfer_gives_no_problems(self) -> None:
        command = fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS)
        self.assertEqual(_check_args(command), [])

    def test_each_single_bad_field_gives_exactly_one_problem(self) -> None:
        cases: list[tuple[str, Any, str]] = [
            ("source_deck", 0, "must be 1-6"),
            ("dest_deck", 7, "must be 1-6"),
            ("source_plate_id", 0, "source_plate_id"),
            ("source_start_col", 0, "source_start_col"),
            ("num_rows", 0, "num_rows"),
            ("num_cols", 0, "num_cols"),
            ("source_start_row", "A1", "1-2 letters"),
            ("dest_start_row", "", "1-2 letters"),
            ("dest_start_row", "ABC", "1-2 letters"),
            ("volume", 0.0, "positive number"),
            ("volume", -1.0, "positive number"),
            ("volume", float("nan"), "positive number"),
            ("volume", float("inf"), "positive number"),
            ("tip_reuse", "always", "one of fresh, reuse"),
        ]
        for field_name, bad_value, fragment in cases:
            with self.subTest(field=field_name, value=bad_value):
                command = fast_pb2.Command.Transfer(
                    **dict(_ALL_TRANSFER_FIELDS, **{field_name: bad_value}))
                problems = _check_args(command)
                self.assertEqual(len(problems), 1, problems)
                self.assertIn(fragment, problems[0])

    def test_only_tip_reuse_set_gives_eleven_missing_fields_in_order(self) -> None:
        command = fast_pb2.Command.Transfer(tip_reuse="fresh")
        expected = [f.name for f in fields(TransferRequest) if f.name != "tip_reuse"]
        self.assertEqual(len(expected), 11)
        self.assertEqual(_check_args(command), expected)

    def test_expected_tray_id_negative_or_zero_adds_no_problem(self) -> None:
        for value in (-1, 0):
            with self.subTest(expected_tray_id=value):
                command = fast_pb2.Command.Transfer(
                    **dict(_ALL_TRANSFER_FIELDS, expected_tray_id=value))
                self.assertEqual(_check_args(command), [])

    def test_run_protocol_and_validate_protocol_csv_checks(self) -> None:
        for message_cls in (fast_pb2.Command.RunProtocol, fast_pb2.Command.ValidateProtocol):
            with self.subTest(message=message_cls.__name__):
                self.assertEqual(_check_args(message_cls(csv="")), ["csv is required"])
                problems = _check_args(message_cls(csv="Hello,1"))
                self.assertEqual(len(problems), 1)
                self.assertIn("csv does not parse: ValueError", problems[0])
                self.assertEqual(_check_args(message_cls(csv=EXAMPLE1_CSV)), [])

    def test_run_protocol_timeout_s_must_be_positive(self) -> None:
        for bad_timeout in (0.0, float("nan")):
            with self.subTest(timeout_s=bad_timeout):
                command = fast_pb2.Command.RunProtocol(csv=EXAMPLE1_CSV, timeout_s=bad_timeout)
                self.assertEqual(
                    _check_args(command),
                    ["timeout_s must be a positive number of seconds"])

    def test_read_and_recovery_commands_give_no_problems(self) -> None:
        for command in (
            fast_pb2.Command.GetStatus(), fast_pb2.Command.GetTipStatus(),
            fast_pb2.Command.ScanTips(), fast_pb2.Command.EjectTray(),
            fast_pb2.Command.Pause(),
        ):
            with self.subTest(command=type(command).__name__):
                self.assertEqual(_check_args(command), [])


class TestRealModeArgumentCheck(unittest.TestCase):
    """D-15: the same _check_args gate runs in real mode too, via the
    FastServer._dispatchCommand override, before any FastService call."""

    def setUp(self) -> None:
        self.server = FastServer()
        self.server.simulated = False
        self.server.status = READY
        self.server.service = MagicMock(spec=FastService)
        self.server.config = fast_pb2.Config(host="h")

    def test_invalid_transfer_rejected_before_reaching_service(self) -> None:
        command = fast_pb2.Command.Transfer(**dict(_ALL_TRANSFER_FIELDS, volume=0.0))
        reply = self.server._dispatchCommand(command)
        self.assertEqual(reply.response, INVALID_ARGUMENTS)
        self.assertEqual(MessageToDict(reply.meta_data)["kind"], "needsInput")
        cast(MagicMock, self.server.service).run_transfer.assert_not_called()

    def test_valid_transfer_reaches_service_exactly_once(self) -> None:
        cast(MagicMock, self.server.service).run_transfer.return_value = Ran(
            outcome=RunOutcome(state="idle", done=True, percent=100))
        command = fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS)
        reply = self.server._dispatchCommand(command)
        self.assertEqual(reply.response, SUCCESS)
        cast(MagicMock, self.server.service).run_transfer.assert_called_once()


class TestEstimates(unittest.TestCase):
    """D-16: named, documented estimate constants; every method returns an
    int >= 1 and never raises, even on malformed/empty input (the
    EstimateDuration RPC bypasses _check_args entirely)."""

    def setUp(self) -> None:
        self.server = FastServer()

    def test_estimate_transfer_values(self) -> None:
        cases = [
            (10.0, 80), (25.0, 100), (13.0, 80), (13.5, 100),
        ]
        for volume, expected in cases:
            with self.subTest(volume=volume):
                command = fast_pb2.Command.Transfer(
                    **dict(_ALL_TRANSFER_FIELDS, volume=volume))
                self.assertEqual(self.server.EstimateTransfer(command), expected)

        with self.subTest(volume="unset"):
            command = fast_pb2.Command.Transfer(
                **{k: v for k, v in _ALL_TRANSFER_FIELDS.items() if k != "volume"})
            self.assertEqual(self.server.EstimateTransfer(command), 80)

        with self.subTest(volume="nan"):
            command = fast_pb2.Command.Transfer(
                **dict(_ALL_TRANSFER_FIELDS, volume=float("nan")))
            self.assertEqual(self.server.EstimateTransfer(command), 80)

    def test_estimate_run_protocol_values(self) -> None:
        cases = [
            (EXAMPLE1_CSV, 120),
            ("", 75),
            ("garbage\nline2\nline3", 90),
        ]
        for csv, expected in cases:
            with self.subTest(csv=csv[:20]):
                command = fast_pb2.Command.RunProtocol(csv=csv)
                self.assertEqual(self.server.EstimateRunProtocol(command), expected)

    def test_read_and_motion_estimate_values(self) -> None:
        self.assertEqual(
            self.server.EstimateValidateProtocol(fast_pb2.Command.ValidateProtocol()), 1)
        self.assertEqual(self.server.EstimateGetStatus(fast_pb2.Command.GetStatus()), 1)
        self.assertEqual(self.server.EstimateGetTipStatus(fast_pb2.Command.GetTipStatus()), 1)
        self.assertEqual(self.server.EstimateScanTips(fast_pb2.Command.ScanTips()), 30)
        self.assertEqual(self.server.EstimateEjectTray(fast_pb2.Command.EjectTray()), 15)
        self.assertEqual(self.server.EstimateAbort(fast_pb2.Command.Abort()), 15)
        self.assertEqual(self.server.EstimateResume(fast_pb2.Command.Resume()), 15)
        self.assertEqual(self.server.EstimatePause(fast_pb2.Command.Pause()), 1)

    def test_no_estimate_method_raises_for_an_empty_message_of_its_type(self) -> None:
        empty_messages = [
            fast_pb2.Command.Transfer(),
            fast_pb2.Command.RunProtocol(),
            fast_pb2.Command.ValidateProtocol(),
            fast_pb2.Command.GetStatus(),
            fast_pb2.Command.GetTipStatus(),
            fast_pb2.Command.ScanTips(),
            fast_pb2.Command.EjectTray(),
            fast_pb2.Command.Abort(),
            fast_pb2.Command.Resume(),
            fast_pb2.Command.Pause(),
        ]
        estimate_methods: dict[str, Any] = {
            "Transfer": self.server.EstimateTransfer,
            "RunProtocol": self.server.EstimateRunProtocol,
            "ValidateProtocol": self.server.EstimateValidateProtocol,
            "GetStatus": self.server.EstimateGetStatus,
            "GetTipStatus": self.server.EstimateGetTipStatus,
            "ScanTips": self.server.EstimateScanTips,
            "EjectTray": self.server.EstimateEjectTray,
            "Abort": self.server.EstimateAbort,
            "Resume": self.server.EstimateResume,
            "Pause": self.server.EstimatePause,
        }
        for message in empty_messages:
            name = type(message).__name__
            with self.subTest(command=name):
                estimate = estimate_methods[name](message)
                self.assertIsInstance(estimate, int)
                self.assertGreaterEqual(estimate, 1)


class TestRecoveryCommands(unittest.TestCase):
    """Operator-issued Abort and Resume (dual-frontend section 11 #1, amended).
    The core owns the state gate; these tests use the real FastService around
    a stub transport wherever the gate itself is the point, so "refused"
    proves no recovery request reached the instrument."""

    def setUp(self) -> None:
        self._openapi = default_openapi_path()
        openapi_path = self._openapi.__enter__()
        self.addCleanup(self._openapi.__exit__, None, None, None)
        self.transport = MagicMock()
        self.service = FastService(InstrumentSession(self.transport, openapi_path),
                                   sleep=lambda _s: None, poll_interval_s=0.01)
        self.server = FastServer()
        self.server.service = self.service
        self.server.config = fast_pb2.Config(host="h")
        self.server.status = READY

    def _statuses(self, *states: dict) -> None:
        self.transport.get_status.side_effect = list(states)

    def test_abort_while_paused_is_success_and_passes_the_decision(self) -> None:
        for value, expected in (("yes", True), ("no", False), (" YES ", True)):
            with self.subTest(return_liquid=value):
                self.transport.reset_mock()
                self._statuses({"currentState": "paused"})
                self.transport.abort.return_value = {"errorCode": 0}
                reply = self.server.Abort(fast_pb2.Command.Abort(return_liquid=value))
                self.assertEqual(reply.response, SUCCESS)
                self.transport.abort.assert_called_once_with(return_liquid=expected)

    def test_abort_while_idle_is_refused_without_an_abort_call(self) -> None:
        self._statuses({"currentState": "idle"})
        reply = self.server.Abort(fast_pb2.Command.Abort(return_liquid="no"))
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertEqual(
            reply.error_message,
            "instrument not ready: no running or paused protocol to abort (state idle)")
        self.assertEqual(MessageToDict(reply.meta_data)["kind"], "refused")
        self.transport.abort.assert_not_called()

    def test_abort_nonzero_error_code_is_error_from_tool(self) -> None:
        self._statuses({"currentState": "paused"})
        self.transport.abort.return_value = {"errorCode": -1}
        reply = self.server.Abort(fast_pb2.Command.Abort(return_liquid="no"))
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("instrument rejected abort: errorCode -1", reply.error_message)

    def test_abort_reply_without_error_code_is_not_success(self) -> None:
        self._statuses({"currentState": "paused"})
        self.transport.abort.return_value = {}
        reply = self.server.Abort(fast_pb2.Command.Abort(return_liquid="no"))
        self.assertEqual(reply.response, ERROR_FROM_TOOL)

    def test_resume_while_paused_waits_for_the_run_and_reports_ran(self) -> None:
        self._statuses(
            {"currentState": "paused"},  # core state gate
            {"currentState": "running", "percentProgress": 50},
            {"currentState": "idle", "percentProgress": 100,
             "lastEvent": {"messageType": 5, "payload": {"errorCode": 0}}},
        )
        self.transport.resume.return_value = {"errorCode": 0}
        reply = self.server.Resume(fast_pb2.Command.Resume(is_tip_broken="yes"))
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(MessageToDict(reply.meta_data)["kind"], "ran")
        self.transport.resume.assert_called_once_with(is_tip_broken=True)
        self.transport.abort.assert_not_called()

    def test_resume_wait_uses_a_fresh_handle_and_transfer_options(self) -> None:
        service = MagicMock(spec=FastService)
        service.resume.return_value = {"errorCode": 0}
        service.wait.return_value = Ran(outcome=RunOutcome(state="idle", done=True, percent=100))
        self.server.service = service
        self.server.config = fast_pb2.Config(host="h", run_timeout_s=300)
        self.server.Resume(fast_pb2.Command.Resume(is_tip_broken="no"))
        handle = service.wait.call_args.args[0]
        self.assertEqual(handle, RunHandle(plates=None, stale_done=False))
        self.assertEqual(service.wait.call_args.kwargs["timeout_s"], 300)
        self.assertEqual(service.wait.call_args.kwargs["on_progress"],
                         self.server._log_progress)
        service.abort.assert_not_called()

    def test_resume_that_pauses_again_reports_the_actionable_paused_message(self) -> None:
        self._statuses(
            {"currentState": "paused"},
            {"currentState": "running", "percentProgress": 10},
            {"currentState": "paused", "percentProgress": 10,
             "lastEvent": {"messageType": 1, "payload": {"errorCode": -645}}},
        )
        self.transport.resume.return_value = {"errorCode": 0}
        reply = self.server.Resume(fast_pb2.Command.Resume(is_tip_broken="no"))
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("run paused at 10%", reply.error_message)
        self.assertIn("then send Resume (is_tip_broken) or Abort (return_liquid)",
                      reply.error_message)
        self.transport.abort.assert_not_called()

    def test_resume_known_limitation_leading_paused_poll_reads_as_paused(self) -> None:
        """Pins the documented limitation on FastServer.Resume: if the
        instrument still says paused on the first poll after accepting the
        resume, the wait reports Paused. Change this test if the core's wait
        learns to ignore a leading paused."""
        self._statuses({"currentState": "paused"}, {"currentState": "paused"})
        self.transport.resume.return_value = {"errorCode": 0}
        reply = self.server.Resume(fast_pb2.Command.Resume(is_tip_broken="no"))
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertEqual(MessageToDict(reply.meta_data)["kind"], "paused")

    def test_resume_while_idle_is_refused_without_a_resume_call(self) -> None:
        self._statuses({"currentState": "idle"})
        reply = self.server.Resume(fast_pb2.Command.Resume(is_tip_broken="no"))
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertEqual(
            reply.error_message,
            "instrument not ready: no paused protocol to resume (state idle)")
        self.transport.resume.assert_not_called()

    def test_resume_rejected_by_instrument_does_not_wait(self) -> None:
        service = MagicMock(spec=FastService)
        service.resume.return_value = {"errorCode": -2}
        self.server.service = service
        reply = self.server.Resume(fast_pb2.Command.Resume(is_tip_broken="no"))
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("instrument rejected resume: errorCode -2", reply.error_message)
        service.wait.assert_not_called()

    def test_missing_or_unclear_decision_is_invalid_arguments_in_real_mode(self) -> None:
        self.server.simulated = False
        cases = [
            ("Abort", fast_pb2.Command.Abort(), "return_liquid"),
            ("Abort", fast_pb2.Command.Abort(return_liquid=""), "return_liquid"),
            ("Abort", fast_pb2.Command.Abort(return_liquid="false"), "return_liquid"),
            ("Resume", fast_pb2.Command.Resume(), "is_tip_broken"),
            ("Resume", fast_pb2.Command.Resume(is_tip_broken=""), "is_tip_broken"),
            ("Resume", fast_pb2.Command.Resume(is_tip_broken="maybe"), "is_tip_broken"),
        ]
        for name, command, field_name in cases:
            with self.subTest(command=name, value=getattr(command, field_name)):
                reply = self.server._dispatchCommand(command)
                self.assertEqual(reply.response, INVALID_ARGUMENTS)
                self.assertIn(f"{field_name} must be 'yes' or 'no'", reply.error_message)
                # Called directly, the method itself also refuses to default.
                direct = getattr(self.server, name)(command)
                self.assertEqual(direct.response, INVALID_ARGUMENTS)
        self.transport.get_status.assert_not_called()
        self.transport.abort.assert_not_called()
        self.transport.resume.assert_not_called()

    def test_check_args_recovery_decisions(self) -> None:
        self.assertEqual(_check_args(fast_pb2.Command.Abort(return_liquid="yes")), [])
        self.assertEqual(_check_args(fast_pb2.Command.Resume(is_tip_broken="No")), [])
        self.assertEqual(_check_args(fast_pb2.Command.Abort()),
                         ["return_liquid must be 'yes' or 'no' (got 'unset')"])
        self.assertEqual(_check_args(fast_pb2.Command.Resume(is_tip_broken="")),
                         ["is_tip_broken must be 'yes' or 'no' (got '')"])

    def test_pause_while_running_is_a_soft_pause_and_success(self) -> None:
        self._statuses({"currentState": "running"})
        self.transport.pause.return_value = {"errorCode": 0}
        reply = self.server.Pause(fast_pb2.Command.Pause())
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.transport.pause.assert_called_once_with(hard=False)
        self.transport.abort.assert_not_called()
        self.transport.resume.assert_not_called()

    def test_pause_while_not_running_is_refused_without_a_pause_call(self) -> None:
        for state in ("idle", "paused"):
            with self.subTest(state=state):
                self.transport.reset_mock()
                self._statuses({"currentState": state})
                reply = self.server.Pause(fast_pb2.Command.Pause())
                self.assertEqual(reply.response, ERROR_FROM_TOOL)
                self.assertEqual(
                    reply.error_message,
                    f"instrument not ready: no running protocol to pause (state {state})")
                self.assertEqual(MessageToDict(reply.meta_data)["kind"], "refused")
                self.transport.pause.assert_not_called()

    def test_pause_nonzero_or_missing_error_code_is_error_from_tool(self) -> None:
        self._statuses({"currentState": "running"})
        self.transport.pause.return_value = {"errorCode": -1}
        reply = self.server.Pause(fast_pb2.Command.Pause())
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertIn("instrument rejected pause: errorCode -1", reply.error_message)

        self._statuses({"currentState": "running"})
        self.transport.pause.return_value = {}
        reply = self.server.Pause(fast_pb2.Command.Pause())
        self.assertEqual(reply.response, ERROR_FROM_TOOL)

    def test_simulated_mode_checks_decisions_and_sleeps_the_estimate(self) -> None:
        fake_sleep = MagicMock()
        with patch("tools.base_server.time",
                   types.SimpleNamespace(time=time.time, sleep=fake_sleep)):
            server = FastServer()
            server.config = fast_pb2.Config(host="sim-no-contact.invalid")
            server.status = READY
            server.simulated = True
            for name, bad, good in (
                ("Abort", fast_pb2.Command.Abort(),
                 fast_pb2.Command.Abort(return_liquid="no")),
                ("Resume", fast_pb2.Command.Resume(is_tip_broken="nope"),
                 fast_pb2.Command.Resume(is_tip_broken="yes")),
            ):
                with self.subTest(command=name):
                    fake_sleep.reset_mock()
                    self.assertEqual(server._dispatchCommand(bad).response, INVALID_ARGUMENTS)
                    fake_sleep.assert_not_called()
                    self.assertEqual(server._dispatchCommand(good).response, SUCCESS)
                    fake_sleep.assert_called_once_with(15.0)
        self.assertIsNone(server.service)


class TestAdapterInvariant(unittest.TestCase):
    """The adapter's core-only, open_service-only, no-abort, no-passthrough
    shape, held mechanically (mirrors fast_mcp/tests/test_service.py's
    test_adapter_server_is_pure style for the MCP entry)."""

    def test_adapter_obtains_service_only_through_open_service(self) -> None:
        server_path = Path(__file__).resolve().parents[1] / "fast" / "server.py"
        tree = ast.parse(server_path.read_text())

        allowed_modules = {
            "fast_mcp.composition", "fast_mcp.service", "fast_mcp.results",
            "fast_mcp.run_control", "fast_mcp.model", "fast_mcp.authoring",
            "fast_mcp.transport",
        }
        exact_names = {
            "fast_mcp.model": {"Protocol"},
            "fast_mcp.authoring": {"_TIP_REUSE_MODES"},
            "fast_mcp.transport": {"InstrumentHTTPError"},
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "fast_mcp" or module.startswith("fast_mcp."):
                    self.assertIn(module, allowed_modules, module)
                    if module in exact_names:
                        names = {alias.name for alias in node.names}
                        self.assertEqual(names, exact_names[module], module)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.assertFalse(
                        alias.name == "fast_mcp" or alias.name.startswith("fast_mcp."),
                        alias.name)

        banned_calls = {"FastService", "InstrumentSession", "RestInstrumentClient"}
        open_service_called = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                self.assertNotIn(node.func.id, banned_calls, node.func.id)
                if node.func.id == "open_service":
                    open_service_called = True
        self.assertTrue(open_service_called, "open_service must be called at least once")

        banned_attrs = {
            "verify_deck_layout", "active_tray",
            "plate_definitions", "dispense_report", "start_run",
        }
        # Dual-frontend section 11 #1 (amended): pause/abort/resume/wait exist
        # only inside the operator's own Pause/Abort/Resume commands, so the
        # adapter can never pause, abort or resume on its own initiative.
        scoped_attrs = {
            "pause": "Pause", "abort": "Abort", "resume": "Resume", "wait": "Resume",
        }
        recovery_defs = {
            node.name: node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name in ("Pause", "Abort", "Resume")
        }
        self.assertEqual(set(recovery_defs), {"Pause", "Abort", "Resume"})
        allowed_nodes = {
            attr: {id(n) for n in ast.walk(recovery_defs[owner])}
            for attr, owner in scoped_attrs.items()
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                self.assertNotIn(node.attr, banned_attrs, node.attr)
                if node.attr in scoped_attrs:
                    self.assertTrue(
                        id(node) in allowed_nodes[node.attr],
                        f".{node.attr} at line {node.lineno} is outside "
                        f"{scoped_attrs[node.attr]}()")
                if isinstance(node.value, ast.Name) and node.value.id == "httpx":
                    self.assertEqual(node.attr, "HTTPError", node.attr)

        banned_substrings = (":5003", "/manualoperation", "/protocol/", "/sim/")
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                for substring in banned_substrings:
                    self.assertNotIn(substring, node.value, (substring, node.value))


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
