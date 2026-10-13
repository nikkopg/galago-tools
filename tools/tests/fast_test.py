import ast
import copy
import importlib.metadata
import json
import os
import queue
import socket
import tempfile
import threading
import time
import types
import unittest
from concurrent import futures
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, cast
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
    from fast_mcp.orchestration import PauseInfo, RunOutcome
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
    from fast_mcp.run_control import RunHandle, RunOptions
    from fast_mcp.service import FastService, TransferRequest
    from fast_mcp.session import InstrumentSession
    from fast_mcp.transport import InstrumentHTTPError

    from tools.fast.server import (
        CONTROL_COMMANDS,
        COMMAND_TO_SERVICE_METHOD,
        MOTION_LOCK_COMMANDS,
        FastServer,
        _check_args,
        _message_for,
    )
except ModuleNotFoundError as exc:
    if exc.name and exc.name.split(".")[0] in ("fast_mcp", "httpx"):
        raise unittest.SkipTest(
            "fast_mcp core is not installed (private GitLab dependency, see "
            "tools/fast/requirements.txt); the local Python 3.10 bin/make test run "
            "is the authoritative gate") from exc
    raise

from tools.grpc_interfaces import controller_pb2, fast_pb2, tool_base_pb2, toolbox_pb2
from tools.grpc_interfaces.tool_base_pb2 import (
    BUSY,
    DRIVER_ERROR,
    ERROR_FROM_TOOL,
    INVALID_ARGUMENTS,
    NOT_READY,
    READY,
    SUCCESS,
    UNRECOGNIZED_COMMAND,
    WRONG_TOOL,
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


class _StubPauseInfo:
    """D-13: tests may now use the real PauseInfo (TestRunState does); this
    stub stays for payloads the real PauseInfo would sanitise away, such as
    the unencodable object in test_unencodable_run_state_falls_back_to_unknown."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = dict(data)

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


_WRONG_PLATE_PAUSE: dict[str, Any] = {
    "errorCode": -645,
    "errorName": "WrongPlateType",
    "percent": 0,
    "eventPayload": {
        "wrongDetection": [{"expectedPlateID": 1, "detectedPlateID": None, "position": 3}]
    },
}

_TRAY_ID = 90

# Copied verbatim from fast-mcp's fixtures/labware/getplatedefinitions.json (plate id 1,
# "Default 96-Well Conical"), so this fork test does not depend on the fast-mcp checkout's
# location (the EXAMPLE1_CSV convention above).
_PLATE_ONE_DEFINITION: dict[str, Any] = {
    "id": 1,
    "description": "Default 96-Well Conical",
    "rowCount": 8,
    "colCount": 12,
    "wellCapacity": 401.92,
    "workingCapacity": 401.92,
    "deadVolume": 0,
    "valid": True,
}

_STATUS_IDLE: dict[str, Any] = {"currentState": "idle"}

_STATUS_DONE: dict[str, Any] = {
    "currentState": "idle",
    "percentProgress": 100,
    "lastEvent": {"messageType": 5, "payload": {"errorCode": 0}},
}


def _running(percent: int) -> dict[str, Any]:
    return {"currentState": "running", "percentProgress": percent}


def _aborted(percent: int, error_code: Optional[int] = None) -> dict[str, Any]:
    """A fresh aborted reading at `percent`; a lastEvent carrying `error_code`
    is included only when one is given, so an instrument-side abort with no
    error reads with no lastEvent at all (D-16)."""
    reading: dict[str, Any] = {"currentState": "aborted", "percentProgress": percent}
    if error_code is not None:
        reading["lastEvent"] = {"messageType": 1, "payload": {"errorCode": error_code}}
    return reading


def _wrong_plate_paused(percent: int) -> dict[str, Any]:
    """A fresh paused reading at `percent` whose lastEvent carries -645
    WrongPlateType merged with _WRONG_PLATE_PAUSE["eventPayload"], so the
    core's PauseInfo.event_payload equals _WRONG_PLATE_PAUSE["eventPayload"]
    (errorCode is excluded from event_payload by the core's _pause_info)."""
    return {
        "currentState": "paused",
        "percentProgress": percent,
        "lastEvent": {
            "messageType": 1,
            "payload": {"errorCode": -645, **_WRONG_PLATE_PAUSE["eventPayload"]},
        },
    }


def _stub_transport() -> MagicMock:
    """D-14 stub transport: a MagicMock standing in for the real instrument
    transport. The real core's run_transfer calls, in order: get_active_tray,
    get_plate_definitions (the first knowledge read), get_status (idle
    gate), run_protocol (submit), then get_status once per poll; each
    pause/resume/abort gate reads get_status once more."""
    transport = MagicMock()
    transport.get_active_tray.return_value = {"id": _TRAY_ID}
    transport.get_plate_definitions.return_value = [dict(_PLATE_ONE_DEFINITION)]
    transport.pause.return_value = {"errorCode": 0}
    transport.resume.return_value = {"errorCode": 0}
    transport.abort.return_value = {"errorCode": 0}
    return transport


def _real_core(case: unittest.TestCase, transport: MagicMock, **options: Any) -> Any:
    """D-14 real core: a real FastService built on InstrumentSession wrapping
    the stub transport, with the bundled OpenAPI spec kept open for the
    case's lifetime (the TestRecoveryCommands.setUp shape). Never
    open_service, never a host."""
    cm = default_openapi_path()
    openapi_path = cm.__enter__()
    case.addCleanup(cm.__exit__, None, None, None)
    options.setdefault("poll_interval_s", 0.01)
    return FastService(InstrumentSession(transport, openapi_path), **options)


class _Stepper:
    """Paces the real core's poll loop one step at a time from the test
    thread (research Pattern 3, ported from fast-mcp's
    tests/test_run_control_threads.py, which is not importable from this
    fork: Pitfall 5). Pacing goes through the injected `sleep` and never
    through `get_status`: ResumeMarker holds its own lock across the
    get_status call, so a blocking get_status would deadlock any concurrent
    Resume, Abort or status call issued from the test thread. This refines
    D-15's mechanism and keeps its observable assertions unchanged."""

    def __init__(self) -> None:
        self._sleeping = threading.Event()
        self._sem = threading.Semaphore(0)
        self._closed = False

    def sleep(self, _seconds: float) -> None:
        if self._closed:
            return
        self._sleeping.set()
        if not self._sem.acquire(timeout=5):
            raise AssertionError("stepper sleep() timed out waiting for step()")

    def wait_sleeping(self) -> None:
        if not self._sleeping.wait(timeout=5):
            raise AssertionError("timed out waiting for the wait thread to sleep")
        self._sleeping.clear()

    def step(self) -> None:
        self._sem.release()

    def close(self) -> None:
        self._closed = True
        self._sem.release()


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

    def _run_state(self) -> dict[str, Any]:
        return MessageToDict(self.stub.GetStatus(empty_pb2.Empty()).run_state)

    def test_simulated_control_commands_check_arguments_then_succeed(self) -> None:
        """D-18, ADP-10, ADP-06: simulated Pause/Resume/Abort check their
        arguments through _check_args, then sleep their own estimate via
        base_server's simulated branch and succeed -- never building a
        service or taking the owner lock."""
        reply = self.stub.ExecuteCommand(
            tool_base_pb2.Command(fast=fast_pb2.Command(pause=fast_pb2.Command.Pause())))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        reply = self.stub.ExecuteCommand(
            tool_base_pb2.Command(fast=fast_pb2.Command(
                resume=fast_pb2.Command.Resume(is_tip_broken="yes"))))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        reply = self.stub.ExecuteCommand(
            tool_base_pb2.Command(fast=fast_pb2.Command(
                abort=fast_pb2.Command.Abort(return_liquid="no"))))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.assertEqual(
            self.fake_sleep.call_args_list, [call(1.0), call(15.0), call(15.0)])

        self.fake_sleep.reset_mock()
        bad_commands = [
            fast_pb2.Command(resume=fast_pb2.Command.Resume(is_tip_broken="")),
            fast_pb2.Command(resume=fast_pb2.Command.Resume()),
            fast_pb2.Command(abort=fast_pb2.Command.Abort()),
            fast_pb2.Command(abort=fast_pb2.Command.Abort(return_liquid="maybe")),
        ]
        for fast_command in bad_commands:
            with self.subTest(command=fast_command.WhichOneof("command")):
                reply = self.stub.ExecuteCommand(
                    tool_base_pb2.Command(fast=fast_command))
                self.assertEqual(reply.response, INVALID_ARGUMENTS)
        self.fake_sleep.assert_not_called()

        self.mock_open_service.assert_not_called()
        self.assertIsNone(self.fs.service)

    def test_simulated_run_state_is_running_during_a_transfer_sleep_then_idle(
            self) -> None:
        """D-19: simulated run_state is running while a simulated Transfer
        sleeps and idle otherwise; the health status stays SIMULATED
        throughout."""
        self.assertEqual(
            self._run_state(), {"state": "idle", "percent": None, "pause": None})

        entered = threading.Event()
        release = threading.Event()

        def _blocking_sleep(duration: float) -> None:
            if duration == 80.0:
                entered.set()
                release.wait(timeout=10)

        self.fake_sleep.side_effect = _blocking_sleep

        result: dict[str, Any] = {}

        def _run_transfer() -> None:
            result["reply"] = self.stub.ExecuteCommand(self._valid_transfer_command())

        thread = threading.Thread(target=_run_transfer)
        thread.start()
        # Cleanups run LIFO: release before join, so a failing assertion
        # above never leaves the gRPC worker thread blocked forever.
        self.addCleanup(thread.join, 10)
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(timeout=5))

        self.assertEqual(
            self._run_state(), {"state": "running", "percent": None, "pause": None})
        self.assertEqual(
            self.stub.GetStatus(empty_pb2.Empty()).status, tool_base_pb2.SIMULATED)

        release.set()
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["reply"].response, SUCCESS)

        self.assertEqual(
            self._run_state(), {"state": "idle", "percent": None, "pause": None})

    def test_two_overlapping_simulated_transfers_read_running_until_both_end(
            self) -> None:
        """D-19, RESEARCH Pitfall 3: _active_runs is a counter, not a
        boolean -- two overlapping simulated Transfers read running until
        both have ended."""
        gate_queue: "queue.Queue[threading.Event]" = queue.Queue()
        gate_queue.put(threading.Event())
        gate_queue.put(threading.Event())
        pulled_gates: list[threading.Event] = []
        pulled_lock = threading.Lock()
        both_entered = threading.Event()

        def _blocking_sleep(duration: float) -> None:
            if duration != 80.0:
                return
            gate = gate_queue.get()
            with pulled_lock:
                pulled_gates.append(gate)
                if len(pulled_gates) == 2:
                    both_entered.set()
            gate.wait(timeout=10)

        self.fake_sleep.side_effect = _blocking_sleep

        completed: "queue.Queue[Any]" = queue.Queue()

        def _run() -> None:
            completed.put(self.stub.ExecuteCommand(self._valid_transfer_command()))

        threads = [threading.Thread(target=_run) for _ in range(2)]
        for th in threads:
            th.start()

        def _join_all() -> None:
            for t in threads:
                t.join(10)

        self.addCleanup(_join_all)
        self.assertTrue(both_entered.wait(timeout=5))

        self.assertEqual(
            self._run_state(), {"state": "running", "percent": None, "pause": None})

        pulled_gates[0].set()
        first_reply = completed.get(timeout=10)
        self.assertEqual(first_reply.response, SUCCESS)
        self.assertEqual(
            self._run_state(), {"state": "running", "percent": None, "pause": None})

        pulled_gates[1].set()
        second_reply = completed.get(timeout=10)
        self.assertEqual(second_reply.response, SUCCESS)
        self.assertEqual(
            self._run_state(), {"state": "idle", "percent": None, "pause": None})

        for th in threads:
            th.join(timeout=10)

    def test_pause_recorded_during_one_run_survives_a_second_overlapping_runs_entry(
            self) -> None:
        """CR-01 regression (D-19, D-20): _run_in_flight only
        (re)initializes _run_record on the 0->1 transition, mirroring the
        exit guard. A pause recorded via simulate_pause while run A is
        still in flight must survive run B's overlapping entry into
        _run_in_flight -- not be silently wiped back to
        running/no-pause -- and must stay reported until the last
        overlapping run ends."""
        gate_a = threading.Event()
        gate_b = threading.Event()
        entered_a = threading.Event()
        entered_b = threading.Event()
        seen_count = {"n": 0}
        seen_lock = threading.Lock()

        def _blocking_sleep(duration: float) -> None:
            if duration != 80.0:
                return
            with seen_lock:
                seen_count["n"] += 1
                first = seen_count["n"] == 1
            if first:
                entered_a.set()
                gate_a.wait(timeout=10)
            else:
                entered_b.set()
                gate_b.wait(timeout=10)

        self.fake_sleep.side_effect = _blocking_sleep

        completed: "queue.Queue[Any]" = queue.Queue()

        def _run() -> None:
            completed.put(self.stub.ExecuteCommand(self._valid_transfer_command()))

        thread_a = threading.Thread(target=_run)
        thread_a.start()
        self.addCleanup(thread_a.join, 10)
        self.addCleanup(gate_a.set)
        self.assertTrue(entered_a.wait(timeout=5))

        # Run A is now in flight (_active_runs == 1). Record a pause for it.
        self.fs.simulate_pause(dict(_WRONG_PLATE_PAUSE))
        run_state = self._run_state()
        self.assertEqual(run_state["state"], "paused")

        # Start a second, overlapping Transfer (run B). Its entry into
        # _run_in_flight (_active_runs 1 -> 2) must NOT reset
        # _run_record -- A's pause must survive.
        thread_b = threading.Thread(target=_run)
        thread_b.start()
        self.addCleanup(thread_b.join, 10)
        self.addCleanup(gate_b.set)
        self.assertTrue(entered_b.wait(timeout=5))

        run_state = self._run_state()
        self.assertEqual(run_state["state"], "paused")
        self.assertEqual(
            set(run_state["pause"]),
            {"errorCode", "errorName", "percent", "eventPayload", "since"})

        gate_a.set()
        first_reply = completed.get(timeout=10)
        self.assertEqual(first_reply.response, SUCCESS)
        # A ended but B is still in flight (_active_runs == 1): the pause
        # must still be reported, since only the 1 -> 0 transition clears it.
        run_state = self._run_state()
        self.assertEqual(run_state["state"], "paused")

        gate_b.set()
        second_reply = completed.get(timeout=10)
        self.assertEqual(second_reply.response, SUCCESS)
        # Both runs have ended: the pause is cleared on the last exit.
        self.assertEqual(
            self._run_state(), {"state": "idle", "percent": None, "pause": None})

        thread_a.join(timeout=10)
        thread_b.join(timeout=10)

    def test_simulated_pause_does_not_shorten_the_transfer_sleep(self) -> None:
        """D-18: a simulated Pause sent while a simulated Transfer sleeps
        returns SUCCESS without shortening the Transfer's 80s sleep; the
        Transfer still ends SUCCESS when its own sleep ends."""
        entered = threading.Event()
        release = threading.Event()

        def _blocking_sleep(duration: float) -> None:
            if duration == 80.0:
                entered.set()
                release.wait(timeout=10)

        self.fake_sleep.side_effect = _blocking_sleep

        result: dict[str, Any] = {}

        def _run_transfer() -> None:
            result["reply"] = self.stub.ExecuteCommand(self._valid_transfer_command())

        thread = threading.Thread(target=_run_transfer)
        thread.start()
        self.addCleanup(thread.join, 10)
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(timeout=5))

        pause_reply = self.stub.ExecuteCommand(
            tool_base_pb2.Command(fast=fast_pb2.Command(pause=fast_pb2.Command.Pause())))
        self.assertEqual(pause_reply.response, SUCCESS, pause_reply.error_message)
        self.assertTrue(thread.is_alive())
        self.assertIn(call(80.0), self.fake_sleep.call_args_list)
        self.assertIn(call(1.0), self.fake_sleep.call_args_list)

        release.set()
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["reply"].response, SUCCESS)

    def test_hooked_pause_reads_paused_with_its_detail(self) -> None:
        """D-20: the simulate_pause hook drives run_state to paused with the
        hooked dict's detail; simulate_pause(None) clears it back to idle.
        The health status stays SIMULATED throughout."""
        self.fs.simulate_pause(dict(_WRONG_PLATE_PAUSE))
        run_state = self._run_state()
        self.assertEqual(run_state["state"], "paused")
        self.assertEqual(run_state["percent"], 0)
        self.assertEqual(
            set(run_state["pause"]),
            {"errorCode", "errorName", "percent", "eventPayload", "since"})
        self.assertEqual(
            self.stub.GetStatus(empty_pb2.Empty()).status, tool_base_pb2.SIMULATED)

        self.fs.simulate_pause(None)
        self.assertEqual(
            self._run_state(), {"state": "idle", "percent": None, "pause": None})

    def test_simulated_resume_or_abort_clears_a_hooked_pause_and_invalid_args_do_not(
            self) -> None:
        """D-20: a simulated Resume/Abort that returns SUCCESS clears a
        hooked pause; a Resume rejected as INVALID_ARGUMENTS, and a
        simulated Pause, leave it in place."""
        self.fs.simulate_pause(dict(_WRONG_PLATE_PAUSE))

        reply = self.stub.ExecuteCommand(
            tool_base_pb2.Command(fast=fast_pb2.Command(
                resume=fast_pb2.Command.Resume(is_tip_broken=""))))
        self.assertEqual(reply.response, INVALID_ARGUMENTS)
        self.assertEqual(self._run_state()["state"], "paused")

        reply = self.stub.ExecuteCommand(
            tool_base_pb2.Command(fast=fast_pb2.Command(pause=fast_pb2.Command.Pause())))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.assertEqual(self._run_state()["state"], "paused")

        reply = self.stub.ExecuteCommand(
            tool_base_pb2.Command(fast=fast_pb2.Command(
                resume=fast_pb2.Command.Resume(is_tip_broken="no"))))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.assertEqual(
            self._run_state(), {"state": "idle", "percent": None, "pause": None})

        self.fs.simulate_pause(dict(_WRONG_PLATE_PAUSE))
        reply = self.stub.ExecuteCommand(
            tool_base_pb2.Command(fast=fast_pb2.Command(
                abort=fast_pb2.Command.Abort(return_liquid="yes"))))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.assertEqual(
            self._run_state(), {"state": "idle", "percent": None, "pause": None})

    def test_pause_prompt_round_trip_without_hardware(self) -> None:
        """D-20, ADP-10: galago-core's prompt round trip without hardware --
        a simulated Transfer sleeping reads running, the hook makes it
        paused, a simulated Resume makes it running again, and the end of
        the sleep makes it idle with the Transfer SUCCESS."""
        entered = threading.Event()
        release = threading.Event()

        def _blocking_sleep(duration: float) -> None:
            if duration == 80.0:
                entered.set()
                release.wait(timeout=10)

        self.fake_sleep.side_effect = _blocking_sleep

        result: dict[str, Any] = {}

        def _run_transfer() -> None:
            result["reply"] = self.stub.ExecuteCommand(self._valid_transfer_command())

        thread = threading.Thread(target=_run_transfer)
        thread.start()
        self.addCleanup(thread.join, 10)
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(timeout=5))

        self.assertEqual(
            self._run_state(), {"state": "running", "percent": None, "pause": None})

        self.fs.simulate_pause(dict(_WRONG_PLATE_PAUSE))
        self.assertEqual(self._run_state()["state"], "paused")

        reply = self.stub.ExecuteCommand(
            tool_base_pb2.Command(fast=fast_pb2.Command(
                resume=fast_pb2.Command.Resume(is_tip_broken="no"))))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.assertEqual(
            self._run_state(), {"state": "running", "percent": None, "pause": None})

        release.set()
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["reply"].response, SUCCESS)
        self.assertEqual(
            self._run_state(), {"state": "idle", "percent": None, "pause": None})
        self.mock_open_service.assert_not_called()

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


class _RealModeGrpcTestCase(unittest.TestCase):
    """Shared real-mode in-process gRPC fixture (RESEARCH Pattern 1): a
    FastServer with a MagicMock(spec=FastService) injected directly, a real
    gRPC server/stub pair, and the blocked-Transfer helper (RESEARCH Pitfall
    6) that actually exercises base_server.ExecuteCommand's
    parseCommand/isReady/setStatus(BUSY) bracket. Declares no tests of its
    own."""

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

    def _start_blocked_transfer(
        self, progress: Optional[tuple[int, str]] = None,
    ) -> tuple[threading.Event, threading.Thread, dict[str, Any]]:
        """Blocks a real Transfer sent over the gRPC stub inside run_transfer,
        so base_server.ExecuteCommand's parseCommand/isReady/setStatus(BUSY)
        bracket is actually exercised (RESEARCH Pitfall 6) -- driving the
        Transfer through self.server.Transfer(...) directly would never reach
        that gate. When `progress` is given, the blocking side effect first
        reports it via the on_progress callback (RunOptions.on_progress),
        before blocking on the release event."""
        release = threading.Event()
        entered = threading.Event()

        def _blocking_run_transfer(*args: Any, **kwargs: Any) -> Any:
            if progress is not None:
                kwargs["options"].on_progress(*progress)
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


class TestControlCommandsOverGrpc(_RealModeGrpcTestCase):
    """D-04/ADP-08: the real-mode gRPC tracer for Pause (Task 1), extended
    (Task 2/3) into the concurrency test proving Pause/Resume/Abort reach a
    Transfer in flight through the real base_server.ExecuteCommand gate.
    Deliberately does NOT inherit _MockedFastServerTestCase: this class calls
    control methods on purpose, so its own tearDown allows at most one call
    each -- no test here may reach a control method more than the operator
    asked."""

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

    def test_blank_or_unclear_decisions_are_invalid_arguments_through_the_control_path(
            self) -> None:
        cases: list[tuple[str, Any, str]] = [
            ("Abort", fast_pb2.Command.Abort(), "return_liquid"),
            ("Abort", fast_pb2.Command.Abort(return_liquid=""), "return_liquid"),
            ("Abort", fast_pb2.Command.Abort(return_liquid="   "), "return_liquid"),
            ("Abort", fast_pb2.Command.Abort(return_liquid="false"), "return_liquid"),
            ("Abort", fast_pb2.Command.Abort(return_liquid="y"), "return_liquid"),
            ("Abort", fast_pb2.Command.Abort(return_liquid="1"), "return_liquid"),
            ("Resume", fast_pb2.Command.Resume(), "is_tip_broken"),
            ("Resume", fast_pb2.Command.Resume(is_tip_broken=""), "is_tip_broken"),
            ("Resume", fast_pb2.Command.Resume(is_tip_broken="maybe"), "is_tip_broken"),
            ("Resume", fast_pb2.Command.Resume(is_tip_broken="true"), "is_tip_broken"),
            ("Resume", fast_pb2.Command.Resume(is_tip_broken="yes please"), "is_tip_broken"),
        ]
        for name, command, field_name in cases:
            field_key = name.lower()
            value = getattr(command, field_name)
            with self.subTest(command=name, value=value):
                reply = self.stub.ExecuteCommand(self._fast(**{field_key: command}))
                self.assertEqual(reply.response, INVALID_ARGUMENTS)
                self.assertIn(f"{field_name} must be 'yes' or 'no'", reply.error_message)
                missing = MessageToDict(reply.meta_data)["missing"]
                self.assertEqual(len(missing), 1)
                if not command.HasField(field_name):
                    self.assertIn("got 'unset'", missing[0])
        self.service.abort.assert_not_called()
        self.service.resume.assert_not_called()
        self.assertEqual(self._health().status, READY)

    def test_blank_decisions_mid_run_are_invalid_arguments_and_leave_the_tool_busy(
            self) -> None:
        release, thread, result = self._start_blocked_transfer()
        self.assertEqual(self._health().status, BUSY)

        reply = self.stub.ExecuteCommand(self._fast(abort=fast_pb2.Command.Abort()))
        self.assertEqual(reply.response, INVALID_ARGUMENTS)
        reply = self.stub.ExecuteCommand(
            self._fast(resume=fast_pb2.Command.Resume(is_tip_broken="")))
        self.assertEqual(reply.response, INVALID_ARGUMENTS)

        self.service.abort.assert_not_called()
        self.service.resume.assert_not_called()
        self.assertEqual(self._health().status, BUSY)

        release.set()
        thread.join(timeout=10)
        self.assertEqual(result["transfer"].response, SUCCESS)

    def test_trimmed_case_insensitive_yes_no_is_accepted(self) -> None:
        self.service.abort.return_value = {"errorCode": 0}
        self.service.resume.return_value = {"errorCode": 0}
        self.service.wait.return_value = Ran(
            outcome=RunOutcome(state="idle", done=True, percent=100))

        reply = self.stub.ExecuteCommand(
            self._fast(abort=fast_pb2.Command.Abort(return_liquid=" YES ")))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.service.abort.assert_called_once_with(return_liquid=True)

        reply = self.stub.ExecuteCommand(
            self._fast(resume=fast_pb2.Command.Resume(is_tip_broken="No")))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.service.resume.assert_called_once_with(is_tip_broken=False)

    def test_wrong_tool_type_never_takes_the_control_path(self) -> None:
        reply = self.stub.ExecuteCommand(
            tool_base_pb2.Command(toolbox=toolbox_pb2.Command()))
        self.assertEqual(reply.response, WRONG_TOOL)

        reply = self.stub.ExecuteCommand(tool_base_pb2.Command(fast=fast_pb2.Command()))
        self.assertEqual(reply.response, UNRECOGNIZED_COMMAND)

        self.assertEqual(self.service.method_calls, [])

    def test_non_control_commands_still_take_the_base_server_gate_mid_run(self) -> None:
        release, thread, result = self._start_blocked_transfer()
        reply = self.stub.ExecuteCommand(
            self._fast(get_tip_status=fast_pb2.Command.GetTipStatus()))
        self.assertEqual(reply.response, NOT_READY)
        self.service.tip_status.assert_not_called()
        self.assertEqual(self._health().status, BUSY)

        release.set()
        thread.join(timeout=10)
        self.assertEqual(result["transfer"].response, SUCCESS)

    def test_control_command_exception_is_driver_error_and_sets_last_error(self) -> None:
        self.service.pause.side_effect = RuntimeError("boom")
        reply = self.stub.ExecuteCommand(self._fast(pause=fast_pb2.Command.Pause()))
        self.assertEqual(reply.response, DRIVER_ERROR)
        self.assertEqual(reply.error_message, "boom")
        self.assertEqual(self.server.last_error, "boom")
        self.assertEqual(self._health().status, READY)

    def test_control_commands_never_call_set_status(self) -> None:
        self.service.pause.return_value = {"errorCode": 0}
        self.service.resume.return_value = {"errorCode": 0}
        self.service.abort.return_value = {"errorCode": 0}
        self.service.wait.return_value = Ran(
            outcome=RunOutcome(state="idle", done=True, percent=100))

        with patch.object(self.server, "setStatus", wraps=self.server.setStatus) as spy:
            reply = self.stub.ExecuteCommand(self._fast(pause=fast_pb2.Command.Pause()))
            self.assertEqual(reply.response, SUCCESS, reply.error_message)
            reply = self.stub.ExecuteCommand(
                self._fast(resume=fast_pb2.Command.Resume(is_tip_broken="no")))
            self.assertEqual(reply.response, SUCCESS, reply.error_message)
            reply = self.stub.ExecuteCommand(
                self._fast(abort=fast_pb2.Command.Abort(return_liquid="no")))
            self.assertEqual(reply.response, SUCCESS, reply.error_message)
            spy.assert_not_called()

            self.service.tip_status.return_value = TipScan(tips={})
            reply = self.stub.ExecuteCommand(
                self._fast(get_tip_status=fast_pb2.Command.GetTipStatus()))
            self.assertEqual(reply.response, SUCCESS, reply.error_message)
            self.assertEqual(spy.call_count, 2)

    def test_control_commands_never_check_instrument_state(self) -> None:
        status_values: list[Any] = [
            {"state": s, "percentProgress": 0, "remainingTime": 0, "done": False}
            for s in ("idle", "running", "paused", "error")
        ] + [{}]

        for status_value in status_values:
            with self.subTest(via="grpc", status=status_value):
                self.service.reset_mock()
                self.service.status.return_value = status_value
                self.service.pause.return_value = {"errorCode": 0}
                self.service.resume.return_value = {"errorCode": 0}
                self.service.abort.return_value = {"errorCode": 0}
                self.service.wait.return_value = Ran(
                    outcome=RunOutcome(state="idle", done=True, percent=100))

                self.stub.ExecuteCommand(self._fast(pause=fast_pb2.Command.Pause()))
                self.stub.ExecuteCommand(
                    self._fast(resume=fast_pb2.Command.Resume(is_tip_broken="no")))
                self.stub.ExecuteCommand(
                    self._fast(abort=fast_pb2.Command.Abort(return_liquid="no")))

                self.assertEqual(self.service.pause.call_count, 1)
                self.assertEqual(self.service.resume.call_count, 1)
                self.assertEqual(self.service.abort.call_count, 1)
                self.assertEqual(self.service.status.call_count, 0)

        with self.subTest(via="grpc", status="connect_error"):
            self.service.reset_mock()
            self.service.status.side_effect = httpx.ConnectError("x")
            self.service.pause.return_value = {"errorCode": 0}
            self.service.resume.return_value = {"errorCode": 0}
            self.service.abort.return_value = {"errorCode": 0}
            self.service.wait.return_value = Ran(
                outcome=RunOutcome(state="idle", done=True, percent=100))

            self.stub.ExecuteCommand(self._fast(pause=fast_pb2.Command.Pause()))
            self.stub.ExecuteCommand(
                self._fast(resume=fast_pb2.Command.Resume(is_tip_broken="no")))
            self.stub.ExecuteCommand(
                self._fast(abort=fast_pb2.Command.Abort(return_liquid="no")))

            self.assertEqual(self.service.pause.call_count, 1)
            self.assertEqual(self.service.resume.call_count, 1)
            self.assertEqual(self.service.abort.call_count, 1)
            self.assertEqual(self.service.status.call_count, 0)

        # Repeat the same matrix with direct method calls on self.server --
        # these need no gRPC.
        direct_values: list[Any] = list(status_values) + ["connect_error"]
        for status_value in direct_values:
            with self.subTest(via="direct", status=status_value):
                self.service.reset_mock()
                if status_value == "connect_error":
                    self.service.status.side_effect = httpx.ConnectError("x")
                else:
                    self.service.status.return_value = status_value
                self.service.pause.return_value = {"errorCode": 0}
                self.service.resume.return_value = {"errorCode": 0}
                self.service.abort.return_value = {"errorCode": 0}
                self.service.wait.return_value = Ran(
                    outcome=RunOutcome(state="idle", done=True, percent=100))

                self.server.Pause(fast_pb2.Command.Pause())
                self.server.Resume(fast_pb2.Command.Resume(is_tip_broken="no"))
                self.server.Abort(fast_pb2.Command.Abort(return_liquid="no"))

                self.assertEqual(self.service.pause.call_count, 1)
                self.assertEqual(self.service.resume.call_count, 1)
                self.assertEqual(self.service.abort.call_count, 1)
                self.assertEqual(self.service.status.call_count, 0)

    def test_control_commands_reach_the_service_in_send_order(self) -> None:
        self.service.pause.return_value = {"errorCode": 0}
        self.service.abort.return_value = {"errorCode": 0}
        self.service.resume.return_value = {"errorCode": 0}
        self.service.wait.return_value = Ran(
            outcome=RunOutcome(state="idle", done=True, percent=100))

        self.stub.ExecuteCommand(self._fast(pause=fast_pb2.Command.Pause()))
        self.stub.ExecuteCommand(
            self._fast(abort=fast_pb2.Command.Abort(return_liquid="no")))
        self.stub.ExecuteCommand(
            self._fast(resume=fast_pb2.Command.Resume(is_tip_broken="no")))

        self.assertEqual(
            [c[0] for c in self.service.method_calls],
            ["pause", "abort", "resume", "wait"])


class TestRunStateOverGrpc(_RealModeGrpcTestCase):
    """D-09/D-10/D-12: the health GetStatus's run_state, sourced from the
    adapter's own record while a Transfer is in flight and from a mapped
    service.status() once it ends."""

    def test_run_state_is_running_with_the_latest_progress_while_a_transfer_runs(
            self) -> None:
        release, thread, result = self._start_blocked_transfer(progress=(42, "running"))
        reply = self._health()
        self.assertTrue(reply.HasField("run_state"))
        self.assertEqual(
            MessageToDict(reply.run_state),
            {"state": "running", "percent": 42, "pause": None})
        self.assertEqual(self.service.status.call_count, 0)

        self.service.status.return_value = {
            "state": "idle", "percentProgress": 100, "remainingTime": 0, "done": True}
        release.set()
        thread.join(timeout=10)

        run_state = MessageToDict(self._health().run_state)
        self.assertEqual(run_state, {"state": "idle", "percent": 100, "pause": None})
        self.assertNotIn("percentProgress", run_state)
        self.assertEqual(self.service.status.call_count, 1)

    def test_run_state_at_transfer_entry_has_no_percent_yet(self) -> None:
        release, thread, result = self._start_blocked_transfer()
        self.assertEqual(
            MessageToDict(self._health().run_state),
            {"state": "running", "percent": None, "pause": None})
        release.set()


class _RealCoreGrpcTestCase(_RealModeGrpcTestCase):
    """D-14 (real core, stub transport), D-15 (gRPC path): a FastServer
    wired to a real FastService over a stub transport, paced by an injected
    _Stepper, reached through the real in-process gRPC stub so base_server's
    BUSY bracket and the Phase 1 control override are exercised on the real
    core. Declares no tests of its own."""

    def setUp(self) -> None:
        super().setUp()
        self.transport = _stub_transport()
        self.stepper = _Stepper()
        self.core = _real_core(self, self.transport, sleep=self.stepper.sleep)
        self.server.service = self.core
        self.server.config = fast_pb2.Config(host="h", expected_tray_id=_TRAY_ID)

    def tearDown(self) -> None:
        super().tearDown()
        self.assertLessEqual(self.transport.pause.call_count, 1)
        self.assertLessEqual(self.transport.resume.call_count, 1)
        self.assertLessEqual(self.transport.abort.call_count, 1)

    def _start_command_thread(self, **command: Any) -> tuple[threading.Thread, dict[str, Any]]:
        result: dict[str, Any] = {}

        def _run() -> None:
            result["reply"] = self.stub.ExecuteCommand(self._fast(**command))

        thread = threading.Thread(target=_run)
        thread.start()
        # Cleanups run LIFO: close the stepper (freeing a worker blocked in
        # sleep) before joining, so a failing assertion above never leaves
        # the gRPC worker thread blocked forever.
        self.addCleanup(thread.join, 10)
        self.addCleanup(self.stepper.close)
        return thread, result


class TestPauseThroughRealCore(_RealCoreGrpcTestCase):
    """D-14 (real core, stub transport), D-15 (gRPC path): a Transfer paused
    by the instrument stays open on the real core, run_state reports the
    pause, and an operator Resume through ExecuteCommand ends the same step
    SUCCESS."""

    def test_paused_transfer_stays_open_and_ends_success_after_resume(self) -> None:
        self.transport.get_status.side_effect = [
            _STATUS_IDLE, _running(10), _wrong_plate_paused(40), _wrong_plate_paused(40),
            _running(60), _STATUS_DONE, _STATUS_DONE,
        ]
        thread, result = self._start_command_thread(
            transfer=fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS))
        self.stepper.wait_sleeping()
        health = self._health()
        self.assertEqual(health.status, BUSY)
        self.assertEqual(
            MessageToDict(health.run_state), {"state": "running", "percent": 10, "pause": None})

        before = datetime.now(timezone.utc)
        self.stepper.step()
        self.stepper.wait_sleeping()
        after = datetime.now(timezone.utc)
        health = self._health()
        self.assertEqual(health.status, BUSY)
        self.assertTrue(thread.is_alive())
        run_state = MessageToDict(health.run_state)
        self.assertEqual(run_state["state"], "paused")
        self.assertEqual(run_state["percent"], 40)
        pause = run_state["pause"]
        self.assertEqual(
            set(pause.keys()), {"errorCode", "errorName", "percent", "eventPayload", "since"})
        self.assertEqual(pause["errorCode"], -645)
        self.assertEqual(pause["errorName"], "WrongPlateType")
        self.assertEqual(pause["eventPayload"], _WRONG_PLATE_PAUSE["eventPayload"])
        since = datetime.fromisoformat(pause["since"])
        self.assertEqual(since.utcoffset(), timedelta(0))
        self.assertTrue(before <= since <= after)

        reply = self.stub.ExecuteCommand(
            self._fast(resume=fast_pb2.Command.Resume(is_tip_broken="no")))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.transport.resume.assert_called_once_with(is_tip_broken=False)
        health = self._health()
        self.assertEqual(health.status, BUSY)
        self.assertTrue(thread.is_alive())

        self.stepper.step()
        self.stepper.wait_sleeping()
        self.assertEqual(
            MessageToDict(self._health().run_state),
            {"state": "running", "percent": 60, "pause": None})

        self.stepper.step()
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["reply"].response, SUCCESS)
        self.assertEqual(MessageToDict(result["reply"].meta_data)["kind"], "ran")
        health = self._health()
        self.assertEqual(health.status, READY)
        self.assertEqual(
            MessageToDict(health.run_state), {"state": "idle", "percent": 100, "pause": None})
        self.assertEqual(self.transport.get_status.call_count, 7)
        self.transport.pause.assert_not_called()
        self.transport.abort.assert_not_called()

    def test_operator_pause_then_resume_keeps_the_transfer_open_and_ends_success(self) -> None:
        self.transport.get_status.side_effect = [
            _STATUS_IDLE, _running(10), _running(10),
            {"currentState": "paused", "percentProgress": 30},
            {"currentState": "paused", "percentProgress": 30},
            _running(60), _STATUS_DONE, _STATUS_DONE,
        ]
        thread, result = self._start_command_thread(
            transfer=fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS))
        self.stepper.wait_sleeping()

        reply = self.stub.ExecuteCommand(self._fast(pause=fast_pb2.Command.Pause()))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.transport.pause.assert_called_once_with(hard=False)
        health = self._health()
        self.assertEqual(health.status, BUSY)
        self.assertTrue(thread.is_alive())

        self.stepper.step()
        self.stepper.wait_sleeping()
        run_state = MessageToDict(self._health().run_state)
        self.assertEqual(run_state["state"], "paused")
        self.assertEqual(run_state["percent"], 30)
        pause = run_state["pause"]
        self.assertIsNone(pause.get("errorCode"))
        self.assertIsNone(pause.get("errorName"))
        self.assertEqual(pause["eventPayload"], {})
        self.assertIn("since", pause)

        reply = self.stub.ExecuteCommand(
            self._fast(resume=fast_pb2.Command.Resume(is_tip_broken="no")))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.transport.resume.assert_called_once_with(is_tip_broken=False)

        self.stepper.step()
        self.stepper.wait_sleeping()
        self.assertEqual(
            MessageToDict(self._health().run_state),
            {"state": "running", "percent": 60, "pause": None})

        self.stepper.step()
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["reply"].response, SUCCESS)
        self.assertEqual(MessageToDict(result["reply"].meta_data)["kind"], "ran")
        health = self._health()
        self.assertEqual(health.status, READY)
        self.assertEqual(self.transport.get_status.call_count, 8)
        self.transport.abort.assert_not_called()

    def test_instrument_pause_keeps_a_run_protocol_open_with_no_command_sent(self) -> None:
        with patch.object(
                self.server, "_record_pause", wraps=self.server._record_pause) as spy:
            def _p() -> dict[str, Any]:
                return {
                    "currentState": "paused", "percentProgress": 20,
                    "lastEvent": {"messageType": 1, "payload": {"errorCode": -301}},
                }

            self.transport.get_status.side_effect = [
                _STATUS_IDLE, _running(10), _p(), _p(), _running(60), _STATUS_DONE, _STATUS_DONE,
            ]
            thread, result = self._start_command_thread(
                run_protocol=fast_pb2.Command.RunProtocol(csv=EXAMPLE1_CSV))
            self.stepper.wait_sleeping()

            self.stepper.step()
            self.stepper.wait_sleeping()
            run_state = MessageToDict(self._health().run_state)
            self.assertEqual(run_state["state"], "paused")
            self.assertEqual(run_state["percent"], 20)
            self.assertEqual(run_state["pause"]["errorCode"], -301)
            self.assertEqual(run_state["pause"]["errorName"], "TipsNotEnough")
            since = run_state["pause"]["since"]

            self.stepper.step()
            self.stepper.wait_sleeping()
            run_state = MessageToDict(self._health().run_state)
            self.assertEqual(run_state["state"], "paused")
            self.assertEqual(run_state["pause"]["since"], since)
            self.assertEqual(spy.call_count, 1)

            self.stepper.step()
            self.stepper.wait_sleeping()
            self.assertEqual(
                MessageToDict(self._health().run_state),
                {"state": "running", "percent": 60, "pause": None})

            self.stepper.step()
            thread.join(timeout=10)
            self.assertFalse(thread.is_alive())
            self.assertEqual(result["reply"].response, SUCCESS)
            self.assertEqual(MessageToDict(result["reply"].meta_data)["kind"], "ran")
            health = self._health()
            self.assertEqual(health.status, READY)
            self.assertEqual(self.transport.get_status.call_count, 7)
            self.transport.pause.assert_not_called()
            self.transport.resume.assert_not_called()
            self.transport.abort.assert_not_called()


class TestOperatorAbortRealCore(_RealCoreGrpcTestCase):
    """D-14 (real core, stub transport), D-16/D-17 (real-core proof): an
    operator Abort of a paused Transfer ends the step "run aborted by
    operator at <p>%"; an instrument-side abort (no Abort sent) keeps the
    instrument's wording; and an operator abort on one run never carries
    into the next (the _run_in_flight 0->1 reset clears it)."""

    def test_operator_abort_while_paused_ends_the_step_aborted_by_operator(self) -> None:
        self.transport.get_status.side_effect = [
            _STATUS_IDLE, _running(10), _wrong_plate_paused(40), _wrong_plate_paused(40),
            _aborted(40), _STATUS_IDLE,
        ]
        thread, result = self._start_command_thread(
            transfer=fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS))
        self.stepper.wait_sleeping()
        self.stepper.step()
        self.stepper.wait_sleeping()
        health = self._health()
        self.assertEqual(MessageToDict(health.run_state)["state"], "paused")

        reply = self.stub.ExecuteCommand(
            self._fast(abort=fast_pb2.Command.Abort(return_liquid="no")))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.transport.abort.assert_called_once_with(return_liquid=False)
        health = self._health()
        self.assertEqual(health.status, BUSY)
        self.assertTrue(thread.is_alive())

        self.stepper.step()
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["reply"].response, ERROR_FROM_TOOL)
        self.assertEqual(result["reply"].error_message, "run aborted by operator at 40%")
        self.assertEqual(MessageToDict(result["reply"].meta_data)["kind"], "aborted")
        health = self._health()
        self.assertEqual(health.status, READY)
        self.assertEqual(self.transport.get_status.call_count, 6)
        self.transport.pause.assert_not_called()
        self.transport.resume.assert_not_called()

    def test_instrument_side_abort_keeps_the_instruments_wording(self) -> None:
        self.transport.get_status.side_effect = [
            _STATUS_IDLE, _running(10), _aborted(40, error_code=-645), _STATUS_IDLE,
        ]
        thread, result = self._start_command_thread(
            transfer=fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS))
        self.stepper.wait_sleeping()
        self.stepper.step()
        thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result["reply"].response, ERROR_FROM_TOOL)
        self.assertEqual(
            result["reply"].error_message, "run aborted at 40%: WrongPlateType (-645)")
        health = self._health()
        self.assertEqual(health.status, READY)
        self.assertEqual(self.transport.get_status.call_count, 4)
        self.transport.pause.assert_not_called()
        self.transport.resume.assert_not_called()
        self.transport.abort.assert_not_called()

    def test_operator_abort_on_one_run_is_not_carried_into_the_next(self) -> None:
        self.transport.get_status.side_effect = [
            _STATUS_IDLE, _running(10), _running(10), _aborted(30), _STATUS_IDLE,
            _running(10), _aborted(50), _STATUS_IDLE,
        ]
        thread1, result1 = self._start_command_thread(
            transfer=fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS))
        self.stepper.wait_sleeping()

        reply = self.stub.ExecuteCommand(
            self._fast(abort=fast_pb2.Command.Abort(return_liquid="no")))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)

        self.stepper.step()
        thread1.join(timeout=10)
        self.assertFalse(thread1.is_alive())
        self.assertEqual(result1["reply"].error_message, "run aborted by operator at 30%")

        thread2, result2 = self._start_command_thread(
            transfer=fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS))
        self.stepper.wait_sleeping()
        self.stepper.step()
        thread2.join(timeout=10)
        self.assertFalse(thread2.is_alive())
        self.assertEqual(result2["reply"].error_message, "run aborted at 50%: no error reported")

        health = self._health()
        self.assertEqual(health.status, READY)
        self.assertEqual(self.transport.abort.call_count, 1)
        self.assertEqual(self.transport.get_status.call_count, 8)


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
        self.assertIs(call.kwargs["options"].through_pauses, True)
        self.assertEqual(call.kwargs["options"].on_pause, self.server._record_pause)
        self.assertEqual(call.kwargs["options"].on_progress, self.server._log_progress)


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
        self.assertIs(call.kwargs["options"].through_pauses, True)
        self.assertEqual(call.kwargs["options"].on_pause, self.server._record_pause)
        self.assertEqual(call.kwargs["options"].on_progress, self.server._log_progress)

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
        self.service.status.return_value = {
            "state": "idle", "percentProgress": 0, "remainingTime": 0, "done": True}
        reply = self.server.GetStatus(empty_pb2.Empty(), None)
        self.assertIsInstance(reply, tool_base_pb2.StatusReply)
        self.assertEqual(
            MessageToDict(cast(tool_base_pb2.StatusReply, reply).run_state),
            {"state": "idle", "percent": 0, "pause": None})

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


class TestOperatorAbortWording(unittest.TestCase):
    """D-09/D-10: an Aborted result reads "run aborted by operator" only
    when this adapter's own Abort was accepted for the run in flight; any
    other abort keeps the instrument's wording. Calls Abort on purpose, so
    it does not inherit _MockedFastServerTestCase (which forbids that)."""

    def setUp(self) -> None:
        self.server = FastServer()
        self.service = MagicMock(spec=FastService)
        self.server.service = self.service
        self.server.config = fast_pb2.Config(host="h")
        self.server.status = READY

    def test_message_for_names_the_operator_only_when_the_flag_is_set(self) -> None:
        no_error = Aborted(outcome=RunOutcome(state="aborted", done=False, percent=40))
        with_error = Aborted(outcome=RunOutcome(
            state="aborted", done=False, error_code=-645, error_name="WrongPlateType",
            percent=40))

        self.assertEqual(
            _message_for(no_error, None, operator_abort=True),
            "run aborted by operator at 40%")
        self.assertEqual(
            _message_for(with_error, None, operator_abort=True),
            "run aborted by operator at 40%: WrongPlateType (-645)")
        self.assertEqual(
            _message_for(no_error, None, operator_abort=False),
            "run aborted at 40%: no error reported")
        self.assertEqual(
            _message_for(with_error, None, operator_abort=False),
            "run aborted at 40%: WrongPlateType (-645)")
        self.assertEqual(
            _message_for(no_error, None),
            "run aborted at 40%: no error reported")

    def test_timed_out_cancelled_and_paused_text_ignores_the_flag(self) -> None:
        timed_out = TimedOut(outcome=RunOutcome(state="timeout", done=False, percent=40))
        cancelled = Cancelled(percent=40)
        paused = Paused(outcome=RunOutcome(state="paused", done=False, percent=40))
        for result in (timed_out, cancelled, paused):
            with self.subTest(kind=type(result).__name__):
                self.assertEqual(
                    _message_for(result, None, operator_abort=True),
                    _message_for(result, None))
        self.assertIn("the instrument run was NOT aborted", _message_for(timed_out, None))
        self.assertEqual(_message_for(cancelled, None), "cancelled by operator")

    def test_only_an_accepted_abort_sets_the_flag(self) -> None:
        self.assertFalse(self.server._run_record["operator_abort"])

        def _fresh_server() -> FastServer:
            server = FastServer()
            server.service = MagicMock(spec=FastService)
            server.config = fast_pb2.Config(host="h")
            server.status = READY
            return server

        cases: list[tuple[str, Any]] = [
            ("accepted", {"errorCode": 0}),
            ("rejected", {"errorCode": -1}),
            ("no_error_code", {}),
            ("refused",
             Refused(reason="no running or paused protocol to abort", state="idle")),
        ]
        for name, result in cases:
            with self.subTest(case=name):
                server = _fresh_server()
                cast(MagicMock, server.service).abort.return_value = result
                server.Abort(fast_pb2.Command.Abort(return_liquid="no"))
                expected = name == "accepted"
                self.assertIs(server._run_record["operator_abort"], expected)

        with self.subTest(case="transport_error"):
            server = _fresh_server()
            cast(MagicMock, server.service).abort.side_effect = httpx.ConnectError("refused")
            server.Abort(fast_pb2.Command.Abort(return_liquid="no"))
            self.assertFalse(server._run_record["operator_abort"])

        with self.subTest(case="blank_decision"):
            server = _fresh_server()
            reply = server.Abort(fast_pb2.Command.Abort(return_liquid=""))
            self.assertEqual(reply.response, INVALID_ARGUMENTS)
            cast(MagicMock, server.service).abort.assert_not_called()
            self.assertFalse(server._run_record["operator_abort"])

        with self.subTest(case="accepted_pause"):
            server = _fresh_server()
            cast(MagicMock, server.service).pause.return_value = {"errorCode": 0}
            server.Pause(fast_pb2.Command.Pause())
            self.assertFalse(server._run_record["operator_abort"])

        with self.subTest(case="accepted_resume_in_flight"):
            server = _fresh_server()
            server._motion_lock.acquire()
            self.addCleanup(server._motion_lock.release)
            cast(MagicMock, server.service).resume.return_value = {"errorCode": 0}
            server.Resume(fast_pb2.Command.Resume(is_tip_broken="no"))
            self.assertFalse(server._run_record["operator_abort"])

    def test_a_new_run_starts_with_the_flag_cleared(self) -> None:
        self.service.abort.return_value = {"errorCode": 0}
        self.server.Abort(fast_pb2.Command.Abort(return_liquid="no"))
        self.assertTrue(self.server._run_record["operator_abort"])

        recorded: dict[str, Any] = {}

        def _run_transfer(*args: Any, **kwargs: Any) -> Any:
            recorded["operator_abort"] = self.server._run_record["operator_abort"]
            return Aborted(outcome=RunOutcome(state="aborted", done=False, percent=40))

        self.service.run_transfer.side_effect = _run_transfer
        reply = self.server.Transfer(fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS))
        self.assertEqual(reply.response, ERROR_FROM_TOOL)
        self.assertEqual(reply.error_message, "run aborted at 40%: no error reported")
        self.assertFalse(recorded["operator_abort"])

    def test_an_abort_accepted_mid_run_reaches_the_steps_message(self) -> None:
        cases = [
            ("Transfer", lambda: fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS),
             "run_transfer"),
            ("RunProtocol", lambda: fast_pb2.Command.RunProtocol(csv=EXAMPLE1_CSV),
             "run_protocol"),
        ]
        for name, build_command, service_method in cases:
            with self.subTest(command=name):
                self.service.reset_mock()
                self.service.abort.return_value = {"errorCode": 0}
                recorded: dict[str, Any] = {}

                def _side_effect(*args: Any, **kwargs: Any) -> Any:
                    self.server.Abort(fast_pb2.Command.Abort(return_liquid="yes"))
                    run_state = self.server._build_run_state()
                    assert run_state is not None
                    recorded["run_state_keys"] = set(run_state)
                    return Aborted(outcome=RunOutcome(state="aborted", done=False, percent=40))

                getattr(self.service, service_method).side_effect = _side_effect
                reply = getattr(self.server, name)(build_command())

                self.assertEqual(reply.response, ERROR_FROM_TOOL)
                self.assertEqual(reply.error_message, "run aborted by operator at 40%")
                self.assertEqual(MessageToDict(reply.meta_data)["kind"], "aborted")
                self.service.abort.assert_called_once_with(return_liquid=True)
                self.assertEqual(recorded["run_state_keys"], {"state", "percent", "pause"})

        with self.subTest(command="Transfer", case="rejected_mid_run"):
            self.service.reset_mock()
            self.service.abort.return_value = {"errorCode": -1}

            def _side_effect_rejected(*args: Any, **kwargs: Any) -> Any:
                self.server.Abort(fast_pb2.Command.Abort(return_liquid="yes"))
                return Aborted(outcome=RunOutcome(state="aborted", done=False, percent=40))

            self.service.run_transfer.side_effect = _side_effect_rejected
            reply = self.server.Transfer(fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS))
            self.assertEqual(reply.error_message, "run aborted at 40%: no error reported")


class TestRunState(unittest.TestCase):
    """D-11/D-12/D-13/D-14: run_state's record, recorder and read-path
    builder, driven directly against FastServer (TestRunStateOverGrpc covers
    the same guarantees through the real gRPC health RPC)."""

    def setUp(self) -> None:
        self.server = FastServer()
        self.service = MagicMock(spec=FastService)
        self.server.service = self.service
        self.server.config = fast_pb2.Config(host="h")
        self.server.status = READY

    def test_run_protocol_marks_its_run_in_flight(self) -> None:
        captured: dict[str, Any] = {}

        def _capturing_run_protocol(*args: Any, **kwargs: Any) -> Any:
            captured["run_state"] = self.server._build_run_state()
            return Ran(outcome=RunOutcome(state="idle", done=True, percent=100))

        self.service.run_protocol.side_effect = _capturing_run_protocol
        reply = self.server.RunProtocol(fast_pb2.Command.RunProtocol(csv=EXAMPLE1_CSV))
        self.assertEqual(reply.response, SUCCESS, reply.error_message)
        self.assertEqual(captured["run_state"]["state"], "running")
        self.assertEqual(self.server._active_runs, 0)

    def test_a_run_that_raises_leaves_no_run_in_flight(self) -> None:
        self.service.run_transfer.side_effect = RuntimeError("boom")
        with self.assertRaises(RuntimeError):
            self.server.Transfer(fast_pb2.Command.Transfer(**_ALL_TRANSFER_FIELDS))
        self.assertEqual(self.server._active_runs, 0)

    def _run_state(self) -> dict[str, Any]:
        return MessageToDict(
            cast(tool_base_pb2.StatusReply,
                 self.server.GetStatus(empty_pb2.Empty(), None)).run_state)

    def test_recorded_pause_is_reported_with_its_detail_and_a_utc_since(self) -> None:
        with self.server._run_in_flight():
            before = datetime.now(timezone.utc)
            self.server._record_pause(_StubPauseInfo(_WRONG_PLATE_PAUSE))
            after = datetime.now(timezone.utc)
            run_state = self._run_state()

        self.assertEqual(run_state["state"], "paused")
        self.assertEqual(run_state["percent"], 0)
        pause = run_state["pause"]
        self.assertEqual(
            set(pause), {"errorCode", "errorName", "percent", "eventPayload", "since"})
        self.assertEqual(pause["errorCode"], -645)
        self.assertEqual(pause["errorName"], "WrongPlateType")
        self.assertEqual(pause["eventPayload"], _WRONG_PLATE_PAUSE["eventPayload"])
        since = datetime.fromisoformat(pause["since"])
        self.assertEqual(since.utcoffset(), timedelta(0))
        self.assertLessEqual(before, since)
        self.assertLessEqual(since, after)
        self.assertEqual(self.service.method_calls, [])

    def test_real_pause_info_records_like_the_stub(self) -> None:
        """D-05: pins compatibility, not a drive -- the duck-typed recorder
        already accepts the real PauseInfo, so this test passes at once."""
        with self.server._run_in_flight():
            self.server._record_pause(
                PauseInfo(error_code=-645, error_name="WrongPlateType", percent=0,
                          event_payload=dict(_WRONG_PLATE_PAUSE["eventPayload"])))
            run_state = self._run_state()

        self.assertEqual(run_state["state"], "paused")
        self.assertEqual(run_state["percent"], 0)
        pause = run_state["pause"]
        self.assertEqual(
            set(pause), {"errorCode", "errorName", "percent", "eventPayload", "since"})
        self.assertEqual(pause["errorCode"], -645)
        self.assertEqual(pause["errorName"], "WrongPlateType")
        self.assertEqual(pause["eventPayload"], _WRONG_PLATE_PAUSE["eventPayload"])
        since = datetime.fromisoformat(pause["since"])
        self.assertEqual(since.utcoffset(), timedelta(0))
        self.assertEqual(self.service.method_calls, [])

    def test_running_observation_clears_the_pause_and_paused_keeps_it(self) -> None:
        with self.server._run_in_flight():
            self.server._record_pause(_StubPauseInfo(_WRONG_PLATE_PAUSE))
            self.server._log_progress(10, "paused")
            paused_state = self._run_state()
            self.assertEqual(paused_state["state"], "paused")
            self.assertIsNotNone(paused_state["pause"])

            self.server._log_progress(10, "running")
            running_state = self._run_state()
        self.assertEqual(
            running_state, {"state": "running", "percent": 10, "pause": None})

    def test_log_progress_sanitizes_the_percent_like_every_other_path(self) -> None:
        """WR-01 regression (D-11/ADP-05): _log_progress must route percent
        through the same _run_percent sanitizer that _record_pause and
        _build_run_state's service.status() path already use -- a bool,
        a string, or a non-finite float must read as null in run_state
        rather than being stored verbatim."""
        for invalid in (float("nan"), float("inf"), float("-inf"), True, False, "50"):
            with self.subTest(invalid=invalid):
                with self.server._run_in_flight():
                    self.server._log_progress(invalid, "running")  # type: ignore[arg-type]
                    self.assertIsNone(self._run_state()["percent"])

        with self.server._run_in_flight():
            self.server._log_progress(10, "running")
            self.assertEqual(self._run_state()["percent"], 10)
            # An invalid percent delivered after a valid one must not
            # clobber the last valid value with garbage.
            self.server._log_progress(float("nan"), "running")  # type: ignore[arg-type]
            self.assertEqual(self._run_state()["percent"], 10)

    def test_no_run_in_flight_maps_status_and_renames_percent(self) -> None:
        cases: list[tuple[Any, Any]] = [(0, 0), (100, 100), (42, 42)]
        for percent_progress, expected in cases:
            with self.subTest(percentProgress=percent_progress):
                self.service.reset_mock()
                self.service.status.return_value = {
                    "state": "idle", "percentProgress": percent_progress,
                    "remainingTime": 0, "done": True}
                run_state = self._run_state()
                self.assertEqual(
                    run_state, {"state": "idle", "percent": expected, "pause": None})
                self.assertNotIn("percentProgress", run_state)

        with self.subTest(percentProgress="missing"):
            self.service.reset_mock()
            self.service.status.return_value = {
                "state": "idle", "remainingTime": 0, "done": True}
            run_state = self._run_state()
            self.assertEqual(
                run_state, {"state": "idle", "percent": None, "pause": None})

        self.assertEqual(self.service.method_calls, [call.status()])

    def test_percent_is_passed_through_without_rounding_or_coercion(self) -> None:
        cases: list[tuple[Any, Any]] = [
            (42.5, 42.5), (True, None), ("50", None), (float("nan"), None),
        ]
        for percent_progress, expected in cases:
            with self.subTest(percentProgress=percent_progress):
                self.service.reset_mock()
                self.service.status.return_value = {
                    "state": "idle", "percentProgress": percent_progress,
                    "remainingTime": 0, "done": True}
                run_state = self._run_state()
                self.assertEqual(run_state.get("percent"), expected)

    def test_unconfigured_tool_leaves_run_state_unset(self) -> None:
        self.server.service = None
        reply = cast(
            tool_base_pb2.StatusReply, self.server.GetStatus(empty_pb2.Empty(), None))
        self.assertFalse(reply.HasField("run_state"))

    def test_status_failure_reports_unknown_and_the_heartbeat_still_answers(self) -> None:
        side_effects: list[Any] = [
            InstrumentHTTPError(500, "boom"), httpx.ConnectError("x"), RuntimeError("y"),
        ]
        for exc in side_effects:
            with self.subTest(side_effect=type(exc).__name__):
                self.service.reset_mock()
                self.service.status.side_effect = exc
                reply = cast(
                    tool_base_pb2.StatusReply,
                    self.server.GetStatus(empty_pb2.Empty(), None))
                self.assertEqual(MessageToDict(reply.run_state), {"state": "unknown"})
                self.assertEqual(reply.status, READY)
                self.assertGreaterEqual(reply.uptime, 0)

        return_values: list[Any] = ["garbage", {"state": None}]
        for value in return_values:
            with self.subTest(return_value=value):
                self.service.reset_mock()
                self.service.status.side_effect = None
                self.service.status.return_value = value
                reply = cast(
                    tool_base_pb2.StatusReply,
                    self.server.GetStatus(empty_pb2.Empty(), None))
                self.assertEqual(MessageToDict(reply.run_state), {"state": "unknown"})
                self.assertEqual(reply.status, READY)
                self.assertGreaterEqual(reply.uptime, 0)

    def test_unencodable_run_state_falls_back_to_unknown(self) -> None:
        with self.server._run_in_flight():
            self.server._record_pause(_StubPauseInfo({"eventPayload": {"blob": object()}}))
            run_state = self._run_state()
        self.assertEqual(run_state, {"state": "unknown"})

    def test_other_tool_types_leave_run_state_unset(self) -> None:
        from tools.lcus1_relay.server import Lcus1RelayServer
        server = Lcus1RelayServer()
        reply = cast(
            tool_base_pb2.StatusReply,
            server.GetStatus(empty_pb2.Empty(), None))  # type: ignore[arg-type]
        self.assertFalse(reply.HasField("run_state"))

    def test_intent_get_status_is_unchanged(self) -> None:
        self.service.status.return_value = {
            "state": "idle", "percentProgress": 0, "remainingTime": 0, "done": True}
        reply = cast(
            tool_base_pb2.ExecuteCommandReply,
            self.server.GetStatus(fast_pb2.Command.GetStatus()))
        meta = MessageToDict(reply.meta_data)
        self.assertIn("percentProgress", meta)
        self.assertNotIn("pause", meta)

    def test_run_state_lock_is_not_the_motion_lock(self) -> None:
        self.assertIsNot(self.server._run_state_lock, self.server._motion_lock)
        spy = MagicMock(wraps=threading.Lock())
        self.server._motion_lock = spy
        self.service.status.return_value = {
            "state": "idle", "percentProgress": 0, "remainingTime": 0, "done": True}
        self.server.GetStatus(empty_pb2.Empty(), None)
        spy.acquire.assert_not_called()


class TestSimulatePauseHook(unittest.TestCase):
    """D-20, T-01-21: the in-process simulate_pause hook raises outside
    simulated mode before recording anything, and is not a gRPC command."""

    def test_hook_raises_in_real_mode_and_records_nothing(self) -> None:
        server = FastServer()
        service = MagicMock(spec=FastService)
        server.service = service
        server.config = fast_pb2.Config(host="h")
        server.status = READY
        with self.assertRaises(RuntimeError):
            server.simulate_pause(dict(_WRONG_PLATE_PAUSE))
        self.assertIsNone(server._run_record["pause"])
        self.assertEqual(service.method_calls, [])

    def test_hook_is_not_a_grpc_command(self) -> None:
        oneof_fields = fast_pb2.Command.DESCRIPTOR.oneofs_by_name["command"].fields
        field_names = {f.name for f in oneof_fields}
        self.assertNotIn("simulate_pause", field_names)
        self.assertNotIn("SimulatePause", COMMAND_TO_SERVICE_METHOD)


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
        self.assertNotIn("on_pause", service.wait.call_args.kwargs)
        self.assertNotIn("through_pauses", service.wait.call_args.kwargs)
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

    def test_resume_masks_a_stale_leading_paused_and_reports_ran(self) -> None:
        """D-08: the re-pinned core classifies the first post-resume paused
        reading as stale, so it is never terminal and the wait continues to
        the run's real end."""
        self._statuses(
            {"currentState": "paused"},
            {"currentState": "paused"},
            {"currentState": "running", "percentProgress": 50},
            {"currentState": "idle", "percentProgress": 100,
             "lastEvent": {"messageType": 5, "payload": {"errorCode": 0}}},
        )
        self.transport.resume.return_value = {"errorCode": 0}
        reply = self.server.Resume(fast_pb2.Command.Resume(is_tip_broken="no"))
        self.assertEqual(reply.response, SUCCESS)
        self.assertEqual(MessageToDict(reply.meta_data)["kind"], "ran")
        self.assertEqual(self.transport.get_status.call_count, 4)
        self.transport.resume.assert_called_once_with(is_tip_broken=False)
        self.transport.abort.assert_not_called()

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


# D-15, D-17: scoped attribute -> the method name(s) allowed to use it. Each
# value is a frozenset of owning FunctionDef names, so an attribute can
# belong to more than one method (`.wait` belongs to Resume's crash-recovery
# path, and to Transfer/RunProtocol if they ever call it directly).
_SCOPED_ATTRS: dict[str, frozenset[str]] = {
    "pause": frozenset({"Pause"}),
    "resume": frozenset({"Resume"}),
    "abort": frozenset({"Abort"}),
    "wait": frozenset({"Resume", "Transfer", "RunProtocol"}),
}
# D-16: functions that may only record observed state -- no access to
# .service, and no call naming a control or motion method. Plan 01-05 adds
# the simulated hook's two functions here.
_RECORD_ONLY_FUNCTIONS = frozenset(
    {"_record_pause", "_log_progress", "simulate_pause", "_clear_pause"})
# D-14: the only functions allowed to call service.status().
_STATUS_READERS = frozenset({"_get_status", "_build_run_state"})
# D-08: functions on the control path, which must never compare against an
# instrument-state string.
_CONTROL_PATH_FUNCTIONS = frozenset(
    {"Pause", "Resume", "Abort", "ExecuteCommand", "_dispatchCommand"})
# Every service method and adapter method name that moves or queries the
# instrument -- used by the record-only and status-only-reader rules below.
_COMMANDING_NAMES = frozenset({
    "pause", "resume", "abort", "wait", "status",
    "Pause", "Resume", "Abort", "ExecuteCommand", "_dispatchCommand",
    "Transfer", "RunProtocol", "ScanTips", "EjectTray",
    "run_transfer", "run_protocol", "scan_tips", "eject_tray",
})
# The instrument-state strings a control-path function must never compare
# against (D-08, ADP-09).
_INSTRUMENT_STATES = frozenset({"idle", "running", "paused", "error", "unknown"})


def _adapter_invariant_violations(tree: ast.Module) -> list[str]:
    """Pure, assertion-free version of the adapter's safety invariants
    (D-17): returns one human-readable violation message per broken rule, or
    an empty list when `tree` is clean. Never raises -- that is what lets
    `_plant`'s deliberately-broken copies be checked without failing the
    test that plants them. Run against the real tools/fast/server.py (must
    return []) and against planted copies (must report the planted
    mistake), so the checker is shown to depend on content in both
    directions (T-01-20)."""
    violations: list[str] = []
    function_defs = {
        node.name: node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
    }

    # A rename or deletion of any owning/scoped method must not silently
    # disable the rule that depends on it.
    required_functions: set[str] = set()
    for owners in _SCOPED_ATTRS.values():
        required_functions |= owners
    required_functions |= _RECORD_ONLY_FUNCTIONS | _STATUS_READERS | _CONTROL_PATH_FUNCTIONS
    for name in sorted(required_functions):
        if name not in function_defs:
            violations.append(f"{name}() is missing from the tree")

    # No plain `import fast_mcp...`; ImportFrom restricted to the allowed
    # modules, with an exact-name allowlist for a few of them.
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
                if module not in allowed_modules:
                    violations.append(
                        f"import from disallowed fast_mcp module {module} "
                        f"at line {node.lineno}")
                elif module in exact_names:
                    names = {alias.name for alias in node.names}
                    if names != exact_names[module]:
                        violations.append(
                            f"{module} imports {sorted(names)} at line {node.lineno}, "
                            f"expected {sorted(exact_names[module])}")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "fast_mcp" or alias.name.startswith("fast_mcp."):
                    violations.append(
                        f"plain import of {alias.name} at line {node.lineno}")

    # The adapter obtains its FastService only through open_service -- never
    # by constructing FastService/InstrumentSession/RestInstrumentClient
    # directly.
    banned_calls = {"FastService", "InstrumentSession", "RestInstrumentClient"}
    open_service_called = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in banned_calls:
                violations.append(
                    f"direct construction of {node.func.id} at line {node.lineno}")
            if node.func.id == "open_service":
                open_service_called = True
    if not open_service_called:
        violations.append("open_service must be called at least once")

    # Attributes the adapter must never touch at all, scoped attributes
    # confined to their owning method(s) (D-15), and httpx limited to
    # HTTPError.
    banned_attrs = {
        "verify_deck_layout", "active_tray",
        "plate_definitions", "dispense_report", "start_run",
    }
    allowed_nodes: dict[str, set[int]] = {}
    for attr, owners in _SCOPED_ATTRS.items():
        ids: set[int] = set()
        for owner in owners:
            fn = function_defs.get(owner)
            if fn is not None:
                ids |= {id(n) for n in ast.walk(fn)}
        allowed_nodes[attr] = ids
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if node.attr in banned_attrs:
                violations.append(f".{node.attr} at line {node.lineno} is banned")
            if node.attr in _SCOPED_ATTRS:
                if id(node) not in allowed_nodes[node.attr]:
                    owners_text = "/".join(sorted(_SCOPED_ATTRS[node.attr]))
                    violations.append(
                        f".{node.attr} at line {node.lineno} is outside {owners_text}()")
            if isinstance(node.value, ast.Name) and node.value.id == "httpx":
                if node.attr != "HTTPError":
                    violations.append(
                        f"httpx.{node.attr} at line {node.lineno} is not HTTPError")

    # No raw :5003 or REST path literal anywhere in the module.
    banned_substrings = (":5003", "/manualoperation", "/protocol/", "/sim/")
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            for substring in banned_substrings:
                if substring in node.value:
                    violations.append(
                        f"string constant at line {node.lineno} contains "
                        f"banned substring {substring!r}")

    # D-16: the pause recorder and progress callback may only record state --
    # no access to .service, and no call naming a control or motion method.
    for name in sorted(_RECORD_ONLY_FUNCTIONS):
        fn = function_defs.get(name)
        if fn is None:
            continue  # already reported above
        for node in ast.walk(fn):
            if isinstance(node, ast.Attribute) and node.attr == "service":
                violations.append(f"{name}() touches .service at line {node.lineno}")
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in _COMMANDING_NAMES):
                violations.append(
                    f"{name}() calls .{node.func.attr}() at line {node.lineno}, "
                    "a control or motion method")

    # D-14: _build_run_state may call only .status() on the service, and no
    # other control or motion method anywhere in its body.
    build_run_state = function_defs.get("_build_run_state")
    if build_run_state is not None:
        for node in ast.walk(build_run_state):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                root = node.func.value
                service_rooted = (
                    (isinstance(root, ast.Name) and root.id == "service")
                    or (isinstance(root, ast.Attribute) and root.attr == "service"))
                if service_rooted and node.func.attr != "status":
                    violations.append(
                        f"_build_run_state() calls .{node.func.attr}() on the service "
                        f"at line {node.lineno}, only .status() is allowed")
                if node.func.attr in (_COMMANDING_NAMES - {"status"}):
                    violations.append(
                        f"_build_run_state() calls .{node.func.attr}() at line "
                        f"{node.lineno}, a control or motion method")

    # D-08, ADP-09: status() is read-only and confined to the status readers.
    status_reader_ids: set[int] = set()
    for name in _STATUS_READERS:
        fn = function_defs.get(name)
        if fn is not None:
            status_reader_ids |= {id(n) for n in ast.walk(fn)}
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "status"):
            if id(node) not in status_reader_ids:
                readers_text = "/".join(sorted(_STATUS_READERS))
                violations.append(
                    f".status() call at line {node.lineno} is outside {readers_text}()")

    # D-08: no control-path function may compare against an instrument-state
    # string. _log_progress's `state == "running"` bookkeeping is deliberately
    # not covered -- it observes, it does not gate a command.
    for name in sorted(_CONTROL_PATH_FUNCTIONS):
        fn = function_defs.get(name)
        if fn is None:
            continue  # already reported above
        for node in ast.walk(fn):
            if isinstance(node, ast.Compare):
                for candidate in (node.left, *node.comparators):
                    if (isinstance(candidate, ast.Constant)
                            and isinstance(candidate.value, str)
                            and candidate.value in _INSTRUMENT_STATES):
                        violations.append(
                            f"{name}() compares against instrument state "
                            f"{candidate.value!r} at line {node.lineno}")

    return violations


def _plant(tree: ast.Module, function: Optional[str], statement: str) -> ast.Module:
    """Returns a deep copy of `tree` with `statement` (parsed as Python
    source) inserted either at the top of the module body (`function` is
    None) or as the first statement(s) of the FunctionDef named `function`,
    after its docstring when it has one. Used to prove each invariant rule
    actually depends on the code it is supposed to check (D-17): a planted
    violation must be reported by `_adapter_invariant_violations`, and a
    planted allowed call must not be."""
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
    """The adapter's core-only, open_service-only, no-abort, no-passthrough
    shape, held mechanically (mirrors fast_mcp/tests/test_service.py's
    test_adapter_server_is_pure style for the MCP entry). The checker itself
    (`_adapter_invariant_violations`) is a reusable, assertion-free function;
    the planted-violation tests below prove it actually depends on the code
    it checks, in both directions (D-17, T-01-20)."""

    def setUp(self) -> None:
        server_path = Path(__file__).resolve().parents[1] / "fast" / "server.py"
        self.tree = ast.parse(server_path.read_text())

    def test_adapter_obtains_service_only_through_open_service(self) -> None:
        self.assertEqual(_adapter_invariant_violations(self.tree), [])

    def test_planted_scoped_call_violations_are_caught(self) -> None:
        cases = [
            ("Abort", "service.pause(hard=False)", ".pause"),
            ("Transfer", "service.abort(return_liquid=False)", ".abort"),
            ("Pause", "service.resume(is_tip_broken=False)", ".resume"),
            ("ScanTips", "service.wait(None)", ".wait"),
            (None, "def _auto_pause(service):\n    service.pause(hard=False)", ".pause"),
        ]
        for function, statement, fragment in cases:
            with self.subTest(function=function, statement=statement):
                planted = _plant(self.tree, function, statement)
                violations = _adapter_invariant_violations(planted)
                self.assertTrue(violations, f"expected a violation for {statement!r}")
                self.assertTrue(
                    any(fragment in v for v in violations),
                    f"no violation mentions {fragment!r}: {violations}")

    def test_planted_existing_invariant_violations_are_caught(self) -> None:
        cases = [
            (None, "from fast_mcp.mcp import server", "fast_mcp.mcp"),
            (None, '_RAW = "http://h:5003/"', ":5003"),
            ("_configure", "FastService(None)", "FastService"),
            ("Transfer", "self.service.verify_deck_layout()", "verify_deck_layout"),
        ]
        for function, statement, fragment in cases:
            with self.subTest(function=function, statement=statement):
                planted = _plant(self.tree, function, statement)
                violations = _adapter_invariant_violations(planted)
                self.assertTrue(violations, f"expected a violation for {statement!r}")
                self.assertTrue(
                    any(fragment in v for v in violations),
                    f"no violation mentions {fragment!r}: {violations}")

    def test_planted_allowed_calls_add_no_violation(self) -> None:
        for function, statement in [
            ("Pause", "service.pause(hard=False)"),
            ("Transfer", "service.wait(None)"),
        ]:
            with self.subTest(function=function, statement=statement):
                planted = _plant(self.tree, function, statement)
                self.assertEqual(_adapter_invariant_violations(planted), [])

    def test_planted_record_and_state_violations_are_caught(self) -> None:
        cases = [
            ("_record_pause", "self.service.pause(hard=False)", "_record_pause"),
            ("_log_progress", "self.service.status()", "_log_progress"),
            ("_log_progress", "self._dispatchCommand(None)", "_log_progress"),
            ("_build_run_state", "self.service.abort(return_liquid=False)", "_build_run_state"),
            ("Abort", "service.status()", ".status"),
            ("Resume", "if state == \"paused\":\n    pass", "Resume"),
            ("simulate_pause", "self.service.pause(hard=False)", "simulate_pause"),
            ("_clear_pause", "self._dispatchCommand(None)", "_clear_pause"),
        ]
        for function, statement, fragment in cases:
            with self.subTest(function=function, statement=statement):
                planted = _plant(self.tree, function, statement)
                violations = _adapter_invariant_violations(planted)
                self.assertTrue(violations, f"expected a violation for {statement!r}")
                self.assertTrue(
                    any(fragment in v for v in violations),
                    f"no violation mentions {fragment!r}: {violations}")

    def test_planted_allowed_record_and_reader_calls_add_no_violation(self) -> None:
        for function, statement in [
            ("_log_progress", 'logging.info("x")'),
            ("_build_run_state", "service.status()"),
        ]:
            with self.subTest(function=function, statement=statement):
                planted = _plant(self.tree, function, statement)
                self.assertEqual(_adapter_invariant_violations(planted), [])


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

    def test_installed_core_has_wait_through_pauses_and_pause_info(self) -> None:
        """D-03/LIVE-01: the installed core exposes the wait-through-pauses
        capability (RunOptions.through_pauses/on_pause), PauseInfo from
        fast_mcp.orchestration with the expected to_dict shape, and a
        bool-only guard on wait()'s through_pauses before any transport
        call -- a core without these would reach Phase 3 ungated."""
        option_fields = {f.name: f for f in fields(RunOptions)}
        self.assertIn("through_pauses", option_fields)
        self.assertIs(option_fields["through_pauses"].default, False)
        self.assertIn("on_pause", option_fields)
        self.assertIsNone(option_fields["on_pause"].default)

        self.assertEqual(PauseInfo.__module__, "fast_mcp.orchestration")
        info = PauseInfo(error_code=-645, error_name="WrongPlateType", percent=0,
                          event_payload={"k": 1})
        self.assertEqual(set(info.to_dict()), {"errorCode", "errorName", "percent",
                                                 "eventPayload"})

        transport = MagicMock()
        core = _real_core(self, transport)
        with self.assertRaises(TypeError):
            core.wait(RunHandle(), through_pauses=cast(Any, "yes"))
        transport.get_status.assert_not_called()
        transport.get_plate_definitions.assert_not_called()

    def test_installed_core_refuses_pause_resume_abort_while_idle(self) -> None:
        """D-03/LIVE-01: the installed core's own state gates refuse
        pause/resume/abort while idle, with no transport call -- checked on
        the core directly, not just at the FastServer layer."""
        transport = MagicMock()
        transport.get_status.return_value = {"currentState": "idle"}
        core = _real_core(self, transport)

        pause_result = core.pause(hard=False)
        self.assertIsInstance(pause_result, Refused)
        self.assertEqual(pause_result.state, "idle")
        self.assertEqual(pause_result.reason, "no running protocol to pause")

        resume_result = core.resume(is_tip_broken=False)
        self.assertIsInstance(resume_result, Refused)
        self.assertEqual(resume_result.state, "idle")
        self.assertEqual(resume_result.reason, "no paused protocol to resume")

        abort_result = core.abort(return_liquid=False)
        self.assertIsInstance(abort_result, Refused)
        self.assertEqual(abort_result.state, "idle")
        self.assertEqual(abort_result.reason, "no running or paused protocol to abort")

        transport.pause.assert_not_called()
        transport.resume.assert_not_called()
        transport.abort.assert_not_called()


if __name__ == "__main__":
    unittest.main()
