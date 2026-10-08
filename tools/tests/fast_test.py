import os
import socket
import tempfile
import unittest
from concurrent import futures
from dataclasses import fields
from typing import Any, cast
from unittest.mock import MagicMock, patch

import grpc
from google.protobuf.json_format import MessageToDict

from fast_mcp.orchestration import RunOutcome
from fast_mcp.results import Ran
from fast_mcp.service import FastService, TransferRequest

from tools.grpc_interfaces import fast_pb2, tool_base_pb2
from tools.grpc_interfaces.tool_base_pb2 import ERROR_FROM_TOOL, READY
from tools.grpc_interfaces.tool_driver_pb2_grpc import (
    ToolDriverStub,
    add_ToolDriverServicer_to_server,
)
from tools.fast.server import FastServer

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


if __name__ == "__main__":
    unittest.main()
