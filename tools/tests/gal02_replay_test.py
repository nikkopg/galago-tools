"""GAL-02 offline proof (FLOW-03): the protocol's own stored STACK params, re-dispatched.

The protocol's scriptContent is evaluated in a node sandbox stub (gal02_harness), the two STACK
transfer param dicts it emits are parsed into the real stack.proto message and driven through a
real-mode StackServer on the fake core over in-process gRPC. Nothing here contacts a STACK.
"""
import unittest
from typing import Any

try:
    import httpx  # noqa: F401
    import stack_automation_layer  # noqa: F401
except ModuleNotFoundError as exc:
    if exc.name and exc.name.split(".")[0] in ("stack_automation_layer", "httpx"):
        raise unittest.SkipTest(
            "stack_automation_layer core is not installed (private GitLab dependency, see "
            "tools/stack/requirements.txt); the local Python 3.10 bin/make test run "
            "is the authoritative gate") from exc
    raise

from google.protobuf.json_format import ParseDict

from tools.grpc_interfaces import stack_pb2, tool_base_pb2
from tools.grpc_interfaces.tool_base_pb2 import SUCCESS
from tools.tests.gal02_harness import (
    HARDWARE_DENY,
    default_params,
    load_export,
    require_node,
    run_script,
    stack_legs,
)
from tools.tests.stack_test import _TransferTestCase


class TestGal02Redispatch(_TransferTestCase):
    """The script's stored STACK params, sent through the frozen Phase 5 adapter."""

    def setUp(self) -> None:
        require_node()
        super().setUp()
        # D-10: a real-mode fixture must never be configured for the hardware STACK.
        self.assertNotIn(self.server.config.host, HARDWARE_DENY)
        self.script = load_export()["protocol"]["scriptContent"]
        self.params = default_params()
        result = run_script(self.script, self.params)
        self.assertTrue(result.ok, result.error)
        self.in_leg, self.out_leg = stack_legs(result)

    def _dispatch(self, params: dict[str, Any]) -> tool_base_pb2.ExecuteCommandReply:
        reply: tool_base_pb2.ExecuteCommandReply = self.stub.ExecuteCommand(
            self._stack(transfer=ParseDict(params, stack_pb2.Command.Transfer())))
        return reply

    def test_redispatch_tracer_in_leg_replays_and_submit_count_stays_one(self) -> None:
        first = self._dispatch(self.in_leg)
        self.assertEqual(first.response, SUCCESS)
        self.assertEqual(self.core.execute_calls, 1)
        again = self._dispatch(self.in_leg)
        self.assertEqual(again.response, SUCCESS)
        self.assertIs(again.meta_data["replayed"], True)
        self.assertEqual(self.core.execute_calls, 1)
