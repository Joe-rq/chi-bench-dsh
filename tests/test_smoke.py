"""Run the real DSH SDK with a scripted model and a local MCP server."""

import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from chi_dsh.runner import run
from chi_dsh.trajectory import export


class Fixture(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, body=b"", content_type="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.reply(405)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path == "/mcp":
            return self.mcp(body)
        if self.path.split("?")[0].endswith("/messages"):
            return self.model(body)
        self.reply(404)

    def mcp(self, body):
        if "id" not in body:
            return self.reply(202)
        method = body["method"]
        if method == "initialize":
            result = {
                "protocolVersion": "2025-03-26",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fixture", "version": "1"},
            }
        elif method == "tools/list":
            result = {
                "tools": [
                    {
                        "name": "case_status",
                        "description": "Read synthetic case status",
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                ]
            }
        elif method == "tools/call" and body["params"]["name"] == "case_status":
            self.server.calls.append("case_status")
            result = {"content": [{"type": "text", "text": "fixture-case-ready"}]}
        else:
            return self.reply(
                200,
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": body["id"],
                        "error": {"code": -32601, "message": "Unknown method"},
                    }
                ).encode(),
            )
        self.reply(
            200,
            json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": result}).encode(),
        )

    def model(self, body):
        tool = next(
            (t["name"] for t in body["tools"] if t["name"].endswith("case_status")),
            None,
        )
        received = "fixture-case-ready" in json.dumps(body["messages"])
        if not tool and not received:
            return self.reply(400, b'{"error":{"message":"Missing role tool"}}')
        events = [
            {
                "type": "message_start",
                "message": {
                    "type": "message",
                    "id": "m1",
                    "role": "assistant",
                    "model": body["model"],
                    "content": [],
                    "usage": {"input_tokens": 15, "output_tokens": 0},
                },
            }
        ]
        if received:
            block = {"type": "text", "text": ""}
            delta = {"type": "text_delta", "text": "Synthetic case checked."}
            stop = "end_turn"
        else:
            block = {"type": "tool_use", "name": tool, "input": {}, "id": "call_1"}
            delta = {"type": "input_json_delta", "partial_json": "{}"}
            stop = "tool_use"
        events.extend(
            [
                {"type": "content_block_start", "index": 0, "content_block": block},
                {"type": "content_block_delta", "index": 0, "delta": delta},
                {"type": "content_block_stop", "index": 0},
                {
                    "type": "message_delta",
                    "delta": {"stop_reason": stop, "stop_sequence": None},
                    "usage": {"output_tokens": 3},
                },
                {"type": "message_stop"},
            ]
        )
        stream = "".join(
            f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events
        )
        self.reply(200, stream.encode(), "text/event-stream")


class RuntimeSmoke(unittest.TestCase):
    def test_dsh_calls_role_tool_and_records_events(self):
        with ThreadingHTTPServer(("127.0.0.1", 0), Fixture) as server:
            server.calls = []
            threading.Thread(target=server.serve_forever, daemon=True).start()
            url = f"http://127.0.0.1:{server.server_port}"
            env = {
                "DEEPSEEK_BASE_URL": url,
                "DEEPSEEK_API_KEY": "local-fixture",
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
            }
            try:
                with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, env):
                    workspace = Path(temp)
                    attempt = run(
                        "Use the role tool to check the case.",
                        url + "/mcp",
                        "deepseek-v4-pro",
                        workspace,
                        workspace / "runs",
                    )
                    self.assertEqual(server.calls, ["case_status"])
                    self.assertEqual(
                        (attempt / "response.txt").read_text(),
                        "Synthetic case checked.",
                    )
                    self.assertEqual(
                        json.loads((attempt / "execution.json").read_text())[
                            "execution"
                        ],
                        "completed",
                    )
                    kinds = {
                        json.loads(line)["type"]
                        for line in (attempt / "events.jsonl").read_text().splitlines()
                    }
                    self.assertTrue({"tool/call", "tool/result"} <= kinds, kinds)
                    trajectory = export(attempt)
                    steps = [step for step in trajectory.steps if step.tool_calls]
                    self.assertEqual(len(steps), 1)
                    self.assertEqual(
                        steps[0].tool_calls[0].function_name,
                        "mcp__chi_bench__case_status",
                    )
                    result = steps[0].observation.results[0]
                    self.assertEqual(
                        result.source_call_id, steps[0].tool_calls[0].tool_call_id
                    )
                    self.assertIn("fixture-case-ready", result.content)
                    self.assertEqual(trajectory.final_metrics.total_prompt_tokens, 30)
            finally:
                server.shutdown()
