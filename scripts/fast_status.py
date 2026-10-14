#!/usr/bin/env python
"""Read-only tool-health printer (D-04, D-05 steps 1-2, Phase 3 LIVE-04).

Calls GetStatus on a running tool server's ToolDriver gRPC service -- the same
heartbeat RPC galago-core already polls -- and prints one JSON line with the
reply. This script sends no command and no configuration: it never calls
ExecuteCommand or Configure, and must never be changed to do so (T-03-03,
the galago-tools restart-during-a-run prohibition relies on this script
staying read-only so it is safe to run against a live instrument at any
time).

Usage:
    .venv/bin/python scripts/fast_status.py [--host HOST] [--port PORT] [--timeout SECONDS]
"""
import argparse
import json
import sys
from typing import Optional

import grpc
from google.protobuf import empty_pb2
from google.protobuf.json_format import MessageToDict

from tools.grpc_interfaces import tool_base_pb2, tool_driver_pb2_grpc


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Tool server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=40001, help="Tool server port (default: 40001)")
    parser.add_argument("--timeout", type=float, default=5.0, help="RPC timeout in seconds (default: 5.0)")
    args = parser.parse_args(argv)

    channel = grpc.insecure_channel(f"{args.host}:{args.port}")
    stub = tool_driver_pb2_grpc.ToolDriverStub(channel)

    try:
        reply = stub.GetStatus(empty_pb2.Empty(), timeout=args.timeout)
    except grpc.RpcError as e:
        print(json.dumps({"port": args.port, "error": e.code().name}))
        return 2

    run_state = MessageToDict(reply.run_state) if reply.HasField("run_state") else None
    print(json.dumps({
        "port": args.port,
        "status": tool_base_pb2.ToolStatus.Name(reply.status),
        "uptime": reply.uptime,
        "error_message": reply.error_message,
        "run_state": run_state,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
