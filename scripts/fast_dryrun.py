#!/usr/bin/env python
"""Simulated-only dry-run harness for D-07.

Serves a second, simulated :class:`tools.fast.server.FastServer` on a spare
port so a deployed ``galago-web`` build can be exercised end to end (run page
control bar, ``tool_paused`` prompt, Stop confirmation, tool-page Run
Recovery) with no hardware involved. Pauses come from
``FastServer.simulate_pause`` (ADP-10), driven either by a control FIFO or by
an auto-pause timer that models an instrument-initiated pause. This harness
can never open an instrument connection: a real ``Configure`` is refused and
``_configure`` always raises.

It imports :class:`FastServer` from :mod:`tools.fast.server` and never edits
anything under ``tools/``.

Usage:
    .venv/bin/python scripts/fast_dryrun.py --port 40003 --control /path/to/control \\
        --auto-pause-after 90 --auto-pause-count 2
    .venv/bin/python scripts/fast_dryrun.py --self-test
"""
import argparse
import logging
import os
import socket
import stat
import sys
import tempfile
import threading
import time
from concurrent import futures
from typing import Any, Optional

import grpc
from google.protobuf import empty_pb2, json_format
from google.protobuf.json_format import MessageToDict

from tools.fast.server import FastServer
from tools.grpc_interfaces import fast_pb2, tool_base_pb2
from tools.grpc_interfaces.tool_driver_pb2_grpc import (
    ToolDriverStub,
    add_ToolDriverServicer_to_server,
)

# The same shape as tools/tests/fast_test.py's _WRONG_PLATE_PAUSE, but percent
# 40 so galago-core renders "Deck 3: expected plate 1, found none" mid-run,
# not at 0%.
WRONG_PLATE_PAUSE: dict[str, Any] = {
    "errorCode": -645,
    "errorName": "WrongPlateType",
    "percent": 40,
    "eventPayload": {
        "wrongDetection": [{"expectedPlateID": 1, "detectedPlateID": None, "position": 3}]
    },
}


def _free_tcp_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


class DryRunFastServer(FastServer):
    """A FastServer that is simulated from construction, refuses a real
    Configure and never opens an instrument connection (D-07). Pauses come
    from an auto-pause timer that models an instrument-initiated pause
    (episode 1 a fixed time after a transfer starts, one re-arm after the
    operator's Resume) or from the control FIFO's "pause"/"clear" lines."""

    def __init__(
        self, auto_pause_after: Optional[float] = None, auto_pause_count: int = 2,
        rearm_delay: float = 5.0,
    ) -> None:
        super().__init__()
        self.setSimulated(True)
        self._auto_pause_after = auto_pause_after
        self._auto_pause_count = auto_pause_count
        self._rearm_delay = rearm_delay
        self._auto_pause_lock = threading.Lock()
        self._episodes_left = 0
        self._pause_timer: Optional[threading.Timer] = None
        self._suppress_rearm = False

    # RED (D-07): the real-Configure refusal is not yet implemented -- a
    # request with simulated=False currently falls through to the inherited
    # ToolServer.Configure, which does not refuse it. self_test()'s first
    # assertion is expected to fail here.

    def _configure(self, config: fast_pb2.Config) -> None:
        raise RuntimeError("dry-run harness never opens an instrument connection")

    def _arm_auto_pause(self) -> None:
        if self._auto_pause_after is None:
            return
        with self._auto_pause_lock:
            self._episodes_left = self._auto_pause_count
            if self._pause_timer is not None:
                self._pause_timer.cancel()
            self._pause_timer = threading.Timer(self._auto_pause_after, self._fire_auto_pause)
            self._pause_timer.daemon = True
            self._pause_timer.start()

    def _fire_auto_pause(self) -> None:
        with self._auto_pause_lock:
            with self._run_state_lock:
                in_flight = self._active_runs > 0
            if self._episodes_left <= 0 or not in_flight:
                return
            self._episodes_left -= 1
            episode = self._auto_pause_count - self._episodes_left
        self.simulate_pause(dict(WRONG_PLATE_PAUSE))
        logging.info("DRYRUN auto pause episode %d", episode)

    def _clear_pause(self) -> None:
        super()._clear_pause()
        with self._auto_pause_lock:
            if self._suppress_rearm:
                return
            with self._run_state_lock:
                in_flight = self._active_runs > 0
            if self._episodes_left > 0 and in_flight:
                if self._pause_timer is not None:
                    self._pause_timer.cancel()
                self._pause_timer = threading.Timer(self._rearm_delay, self._fire_auto_pause)
                self._pause_timer.daemon = True
                self._pause_timer.start()

    def ExecuteCommand(
        self, request: tool_base_pb2.Command, context: grpc.ServicerContext
    ) -> tool_base_pb2.ExecuteCommandReply:
        logging.info("DRYRUN command %s", json_format.MessageToJson(request, indent=None))
        is_transfer = (
            request.WhichOneof("tool_command") == "fast"
            and request.fast.WhichOneof("command") == "transfer")
        if is_transfer:
            self._arm_auto_pause()
        reply = super().ExecuteCommand(request, context)
        if is_transfer:
            with self._auto_pause_lock:
                if self._pause_timer is not None:
                    self._pause_timer.cancel()
                    self._pause_timer = None
                self._episodes_left = 0
        logging.info(
            "DRYRUN reply %s %s",
            tool_base_pb2.ResponseCode.Name(reply.response), reply.error_message)
        return reply


def handle_command(server: DryRunFastServer, line: str) -> bool:
    """Handles one control-FIFO line. Returns True unless "quit" was sent."""
    line = line.strip()
    if not line:
        return True
    parts = line.split()
    cmd = parts[0]
    if cmd == "pause":
        pause = dict(WRONG_PLATE_PAUSE)
        if len(parts) > 1:
            try:
                pause["percent"] = int(parts[1])
            except ValueError:
                logging.warning("DRYRUN control: invalid percent %r", parts[1])
        server.simulate_pause(pause)
        return True
    if cmd == "clear":
        with server._auto_pause_lock:
            server._suppress_rearm = True
            server._episodes_left = 0
        server.simulate_pause(None)
        with server._auto_pause_lock:
            server._suppress_rearm = False
        return True
    if cmd == "status":
        logging.info("DRYRUN status %s", server._build_run_state())
        return True
    if cmd == "quit":
        return False
    logging.warning("DRYRUN control: unrecognized command %r", line)
    return True


def _read_control(server: DryRunFastServer, path: str, stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            with open(path, "r") as fifo:
                for line in fifo:
                    if not handle_command(server, line):
                        stop.set()
                        return
        except OSError:
            if stop.is_set():
                return
            time.sleep(0.1)


def serve_dryrun(
    port: int, control: str, auto_pause_after: Optional[float], auto_pause_count: int,
) -> int:
    test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    test_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        test_sock.bind(("0.0.0.0", port))
    except OSError:
        test_sock.close()
        logging.error("port %d is in use", port)
        return 1
    test_sock.close()

    if os.path.exists(control):
        if not stat.S_ISFIFO(os.stat(control).st_mode):
            logging.error("control path %s exists and is not a FIFO", control)
            return 1
    else:
        os.mkfifo(control, 0o600)

    server_obj = DryRunFastServer(
        auto_pause_after=auto_pause_after, auto_pause_count=auto_pause_count)
    grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    add_ToolDriverServicer_to_server(server_obj, grpc_server)
    grpc_server.add_insecure_port(f"0.0.0.0:{port}")
    grpc_server.start()
    logging.info("DRYRUN harness listening on %d, simulated-only", port)

    stop_event = threading.Event()

    def _handle_signal(signum: int, frame: Any) -> None:
        logging.info("DRYRUN received signal %s, shutting down", signum)
        stop_event.set()

    import signal
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    reader = threading.Thread(
        target=_read_control, args=(server_obj, control, stop_event), daemon=True)
    reader.start()

    stop_event.wait()
    grpc_server.stop(2)
    try:
        os.remove(control)
    except OSError:
        pass
    return 0


def self_test() -> int:
    def fail(reason: str) -> int:
        print(f"SELF-TEST FAIL: {reason}")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        control = os.path.join(tmp, "control")
        os.mkfifo(control, 0o600)
        port = _free_tcp_port()
        server_obj = DryRunFastServer(auto_pause_after=0.2, auto_pause_count=2, rearm_delay=0.2)
        grpc_server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
        add_ToolDriverServicer_to_server(server_obj, grpc_server)
        grpc_server.add_insecure_port(f"127.0.0.1:{port}")
        grpc_server.start()

        stop_event = threading.Event()
        reader = threading.Thread(
            target=_read_control, args=(server_obj, control, stop_event), daemon=True)
        reader.start()

        channel = grpc.insecure_channel(f"127.0.0.1:{port}")
        stub = ToolDriverStub(channel)

        try:
            # 1. Real Configure refusal.
            reply = stub.Configure(tool_base_pb2.Config(
                simulated=False, toolId="dryrun-self-test",
                fast=fast_pb2.Config(host="real-not-allowed.invalid")))
            if reply.response != tool_base_pb2.NOT_READY or "simulated-only" not in reply.error_message:
                return fail(f"real Configure not refused: {reply}")

            # 2. Simulated Configure SUCCESS; GetStatus SIMULATED/idle.
            reply = stub.Configure(tool_base_pb2.Config(
                simulated=True, toolId="dryrun-self-test",
                fast=fast_pb2.Config(host="sim-no-contact.invalid")))
            if reply.response != tool_base_pb2.SUCCESS:
                return fail(f"simulated Configure failed: {reply}")
            status = stub.GetStatus(empty_pb2.Empty())
            if tool_base_pb2.ToolStatus.Name(status.status) != "SIMULATED":
                return fail(f"status not SIMULATED: {status}")
            run_state = MessageToDict(status.run_state)
            if run_state.get("state") != "idle":
                return fail(f"run_state not idle after configure: {run_state}")

            # 3. FIFO "pause 40" read back over GetStatus.
            with open(control, "w") as fifo:
                fifo.write("pause 40\n")
            run_state = _poll_run_state(stub, "paused", timeout=2.0)
            if run_state.get("state") != "paused":
                return fail(f"FIFO pause 40 did not produce paused run_state: {run_state}")
            pause = run_state.get("pause") or {}
            if (run_state.get("percent") != 40 or pause.get("errorCode") != -645
                    or pause.get("errorName") != "WrongPlateType"):
                return fail(f"paused run_state fields wrong: {run_state}")
            wrong_detection = (pause.get("eventPayload") or {}).get("wrongDetection") or []
            if (not wrong_detection or wrong_detection[0].get("expectedPlateID") != 1
                    or wrong_detection[0].get("position") != 3
                    or wrong_detection[0].get("detectedPlateID") is not None):
                return fail(f"wrongDetection payload wrong: {wrong_detection}")

            # 4. FIFO "clear" returns to idle, no re-arm.
            with open(control, "w") as fifo:
                fifo.write("clear\n")
            run_state = _poll_run_state(stub, "idle", timeout=2.0)
            if run_state.get("state") != "idle":
                return fail(f"FIFO clear did not return to idle: {run_state}")

            # 5. A blank Resume is rejected before any instrument contact.
            reply = stub.ExecuteCommand(tool_base_pb2.Command(
                fast=fast_pb2.Command(resume=fast_pb2.Command.Resume(is_tip_broken=""))))
            if reply.response != tool_base_pb2.INVALID_ARGUMENTS:
                return fail(f"blank Resume not INVALID_ARGUMENTS: {reply}")

            # 6. Auto pause episodes while a run is marked in flight.
            with server_obj._run_in_flight():
                server_obj._arm_auto_pause()
                run_state = _poll_run_state(stub, "paused", timeout=2.0)
                if run_state.get("state") != "paused":
                    return fail(f"auto pause episode 1 did not fire: {run_state}")

                reply = stub.ExecuteCommand(tool_base_pb2.Command(
                    fast=fast_pb2.Command(resume=fast_pb2.Command.Resume(is_tip_broken="no"))))
                if reply.response != tool_base_pb2.SUCCESS:
                    return fail(f"Resume during run not SUCCESS: {reply}")

                run_state = _poll_run_state(stub, "paused", timeout=2.0)
                if run_state.get("state") != "paused":
                    return fail(f"auto pause episode 2 did not fire: {run_state}")

            time.sleep(0.5)
            run_state = MessageToDict(stub.GetStatus(empty_pb2.Empty()).run_state)
            if run_state.get("state") != "idle" or run_state.get("pause") is not None:
                return fail(f"run_state not idle with no pause after run ended: {run_state}")
        finally:
            with open(control, "w") as fifo:
                fifo.write("quit\n")
            reader.join(timeout=5)
            channel.close()
            grpc_server.stop(2)

    print("SELF-TEST OK")
    return 0


def _poll_run_state(stub: ToolDriverStub, want_state: str, timeout: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    run_state: dict[str, Any] = {}
    while time.monotonic() < deadline:
        run_state = MessageToDict(stub.GetStatus(empty_pb2.Empty()).run_state)
        if run_state.get("state") == want_state:
            return run_state
        time.sleep(0.05)
    return run_state


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, help="Port to serve the dry-run harness on")
    parser.add_argument("--control", help="Path to the control FIFO")
    parser.add_argument(
        "--auto-pause-after", type=float, default=None,
        help="Seconds after a transfer starts before the first simulated pause (default: off)")
    parser.add_argument(
        "--auto-pause-count", type=int, default=2,
        help="Number of auto-pause episodes per transfer (default: 2)")
    parser.add_argument("--self-test", action="store_true", help="Run the self-test and exit")
    args = parser.parse_args(argv)

    if args.self_test:
        return self_test()
    if not args.port or not args.control:
        parser.error("--port and --control are required unless --self-test is given")
    return serve_dryrun(args.port, args.control, args.auto_pause_after, args.auto_pause_count)


if __name__ == "__main__":
    sys.exit(main())
