"""GAL-02 offline proof (FLOW-03): the protocol's own stored STACK params, re-dispatched.

The protocol's scriptContent is evaluated in a node sandbox stub (gal02_harness), the two STACK
transfer param dicts it emits are parsed into the real stack.proto message and driven through a
real-mode StackServer on the fake core over in-process gRPC. Nothing here contacts a STACK.
"""
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from tools.tests.gal02_harness import skip_or_fail

try:
    import httpx  # noqa: F401
    from stack_automation_layer.results import Refused, TaskHandle

    from tools.stack import server as stack_server
    from tools.stack.ledger import REPLAY_WINDOW_S
    from tools.stack.server import _check_args
except ModuleNotFoundError as exc:
    if exc.name and exc.name.split(".")[0] in ("stack_automation_layer", "httpx"):
        skip_or_fail(
            "stack_automation_layer core is not installed (private GitLab dependency, see "
            "tools/stack/requirements.txt); the local Python 3.10 bin/make test run "
            "is the authoritative gate")
    raise

from google.protobuf.json_format import ParseDict

from tools.grpc_interfaces import stack_pb2, tool_base_pb2
from tools.grpc_interfaces.tool_base_pb2 import ERROR_FROM_TOOL, SUCCESS
from tools.tests.gal02_harness import (
    HARDWARE_DENY,
    default_params,
    load_export,
    require_node,
    run_script,
    stack_legs,
)
from tools.tests.stack_test import _GUID, _TransferTestCase


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

    def test_redispatch_window_then_refusal_and_out_leg_is_fresh(self) -> None:
        in_key = self.in_leg["step_key"]
        self.assertEqual(self._dispatch(self.in_leg).response, SUCCESS)
        self.assertEqual(self.core.execute_calls, 1)
        again = self._dispatch(self.in_leg)
        self.assertEqual(again.response, SUCCESS)
        self.assertEqual(
            set(again.meta_data.keys()), {"stepKey", "ledgerState", "result", "replayed"})
        self.assertEqual(again.meta_data["stepKey"], in_key)
        self.assertEqual(again.meta_data["ledgerState"], "done")
        self.assertIs(again.meta_data["replayed"], True)
        self.assertEqual(self.core.execute_calls, 1)
        self.assertEqual(self.core.call_names.count("plan_transfer"), 1)
        # The out leg is another step key: a fresh transfer, not a replay.
        out = self._dispatch(self.out_leg)
        self.assertEqual(out.response, SUCCESS)
        self.assertNotIn("replayed", out.meta_data)
        self.assertEqual(self.core.execute_calls, 2)
        # Past REPLAY_WINDOW_S the completed key is refused and nothing is sent.
        future = stack_server._utcnow() + timedelta(seconds=REPLAY_WINDOW_S + 5)
        with patch.object(stack_server, "_utcnow", return_value=future):
            late = self._dispatch(self.in_leg)
        self.assertEqual(late.response, ERROR_FROM_TOOL)
        self.assertIn("step key already completed", late.error_message)
        self.assertIn("nothing was sent", late.error_message)
        self.assertEqual(self.core.execute_calls, 2)

    def test_redispatch_after_refused_releases_the_key_then_one_accepted_submit(self) -> None:
        in_key = self.in_leg["step_key"]
        # execute_calls counts every attempt, a Refused one included: count accepted submits apart.
        self.core.execute_result = Refused(reason="robotNotIdle")
        refused = self._dispatch(self.in_leg)
        self.assertEqual(refused.response, ERROR_FROM_TOOL)
        self.assertNotIn(in_key, self._records())
        accepted: list[Any] = []

        def accept(plan_id: Any) -> TaskHandle:
            accepted.append(plan_id)
            return TaskHandle(guid=_GUID, robot="sim-arm-1", estimated_s=30.0)

        self.core.execute_result = accept
        retry = self._dispatch(self.in_leg)
        self.assertEqual(retry.response, SUCCESS)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(self.core.execute_calls, 2)
        third = self._dispatch(self.in_leg)
        self.assertEqual(third.response, SUCCESS)
        self.assertIs(third.meta_data["replayed"], True)
        self.assertEqual(self.core.execute_calls, 2)
        self.assertEqual(len(accepted), 1)

    def test_redispatch_tool_page_resend_with_blank_optionals_replays(self) -> None:
        self.assertEqual(self._dispatch(self.in_leg).response, SUCCESS)
        resend = dict(self.in_leg)
        resend["source_transfer_profile"] = ""
        resend["destination_transfer_profile"] = ""
        resend["timeout_s"] = 0
        again = self._dispatch(resend)
        self.assertEqual(again.response, SUCCESS)
        self.assertIs(again.meta_data["replayed"], True)
        self.assertEqual(self.core.execute_calls, 1)

    def test_redispatch_key_equality_is_byte_exact(self) -> None:
        """A key that differs by one character is a new step to the adapter and submits again.
        This is why the runbook requires copying the stored step key exactly."""
        self.assertEqual(self._dispatch(self.in_leg).response, SUCCESS)
        self.assertEqual(self.core.execute_calls, 1)
        spaced = dict(self.in_leg)
        spaced["step_key"] = self.in_leg["step_key"] + " "
        first = self._dispatch(spaced)
        self.assertEqual(first.response, SUCCESS)
        self.assertNotIn("replayed", first.meta_data)
        self.assertEqual(self.core.execute_calls, 2)
        upper = dict(self.in_leg)
        upper["step_key"] = self.in_leg["step_key"].upper()
        self.assertNotEqual(upper["step_key"], self.in_leg["step_key"])
        second = self._dispatch(upper)
        self.assertEqual(second.response, SUCCESS)
        self.assertNotIn("replayed", second.meta_data)
        self.assertEqual(self.core.execute_calls, 3)

    def test_redispatch_second_run_mints_new_keys_and_is_fresh(self) -> None:
        self.assertEqual(self._dispatch(self.in_leg).response, SUCCESS)
        second = run_script(self.script, self.params)
        self.assertTrue(second.ok, second.error)
        in_two, out_two = stack_legs(second)
        keys_one = {self.in_leg["step_key"], self.out_leg["step_key"]}
        keys_two = {in_two["step_key"], out_two["step_key"]}
        self.assertEqual(len(keys_one | keys_two), 4)
        before = self.core.execute_calls
        fresh = self._dispatch(in_two)
        self.assertEqual(fresh.response, SUCCESS)
        self.assertNotIn("replayed", fresh.meta_data)
        self.assertEqual(self.core.execute_calls, before + 1)

    def test_redispatch_both_legs_pass_the_adapter_argument_check(self) -> None:
        for leg in (self.in_leg, self.out_leg):
            self.assertEqual(_check_args(ParseDict(leg, stack_pb2.Command.Transfer())), [])
