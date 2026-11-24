"""Exercise real DSH + ReJev on published pre-bundle drafts, with local test doubles."""

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from chi_dsh import advisor, choice_protocol
from chi_dsh.runner import run
from chi_dsh.trajectory import export

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "tests"))
from test_smoke import Fixture

FORMS = "forms_save_form_response"
BUNDLE = "docs_create_submission_bundle"
DECISION = "auth_finalize_provider_determination"
REV = "86ef971ff809f037dd4c502d099733b7dc23f9b2"


class LocalRole(Fixture):
    def mcp(self, rpc):
        if rpc.get("method") == "tools/list":
            tools = [
                {"name": name, "description": name, "inputSchema": {"type": "object"}}
                for name in (FORMS, BUNDLE, DECISION)
            ]
            result = {"tools": tools}
        elif rpc.get("method") == "tools/call":
            name = rpc["params"]["name"]
            if name not in (FORMS, BUNDLE, DECISION):
                raise ValueError(name)
            self.server.writes.append(name)
            result = {"content": [{"type": "text", "text": name + " recorded locally"}]}
        else:
            return super().mcp(rpc)
        self.reply(
            200,
            json.dumps({"jsonrpc": "2.0", "id": rpc["id"], "result": result}).encode(),
        )

    def model(self, body):
        # This actor deterministically follows an advisory; it cannot test model autonomy.
        turns = json.dumps(body["messages"])
        args = {}
        if (
            DECISION + " recorded locally" in turns
            or BUNDLE + " recorded locally" in turns
        ):
            action = None
        elif "Pre-bundle review: gather" in turns or "Pre-bundle review: stop" in turns:
            action = DECISION
            args = {
                "final_action": "gather_more_evidence"
                if "review: gather" in turns
                else "do_not_submit"
            }
        elif FORMS + " recorded locally" in turns:
            action = BUNDLE
        else:
            action = FORMS
            args = {"answers": self.server.answers}
        if action:
            name = next(
                (t["name"] for t in body["tools"] if t["name"].endswith("__" + action)),
                None,
            )
            if not name:
                return self.reply(400, b'{"error":{"message":"Missing role tool"}}')
            block = {
                "type": "tool_use",
                "name": name,
                "input": {},
                "id": "step_" + str(len(body["messages"])),
            }
            delta = {"type": "input_json_delta", "partial_json": json.dumps(args)}
        else:
            block, delta = (
                {"type": "text", "text": ""},
                {"type": "text_delta", "text": "Local trial complete."},
            )
        events = [
            {
                "type": "message_start",
                "message": {
                    "type": "message",
                    "id": "fixture",
                    "role": "assistant",
                    "model": body["model"],
                    "content": [],
                    "usage": {"input_tokens": 0, "output_tokens": 0},
                },
            },
            {"type": "content_block_start", "index": 0, "content_block": block},
            {"type": "content_block_delta", "index": 0, "delta": delta},
            {"type": "content_block_stop", "index": 0},
            {
                "type": "message_delta",
                "delta": {
                    "stop_reason": "tool_use" if action else "end_turn",
                    "stop_sequence": None,
                },
                "usage": {"output_tokens": 0},
            },
            {"type": "message_stop"},
        ]
        self.reply(
            200,
            "".join(
                f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events
            ).encode(),
            "text/event-stream",
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "output", "model_python", "base", "adapter"):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    if (
        subprocess.check_output(
            ["git", "-C", args.source, "rev-parse", "HEAD"], text=True
        ).strip()
        != REV
    ):
        raise ValueError("Unexpected upstream revision")
    study02 = HERE.parent / "provider-pa-02"
    sys.path.insert(0, str(study02))
    from model_replay import pre_bundle_state

    with (study02 / "model_replay.csv").open() as f:
        previous = {r["task"]: r for r in csv.DictReader(f)}
    scorer = [
        str(args.model_python),
        advisor.__file__,
        choice_protocol.__file__,
        str(args.base),
        str(args.adapter),
    ]
    domain = (
        args.source
        / "benchmarks/chi-bench/submissions/2026-07-24-opus-5-claude-code/trials/pa_provider"
    )
    for task in ("t013", "t015"):
        (trial,) = domain.glob("pa_" + task + "_*")
        task_name = json.loads((trial / "result.json").read_text())["task_name"]
        _, state = pre_bundle_state(
            subprocess.check_output(
                ["zstd", "-dc", trial / "agent/trajectory.jsonl.zst"]
            )
        )
        answers = {
            "request_description": state["submitted_form_draft_description"],
            **state["draft_questionnaire_entries"],
        }
        for arm in ("baseline", "advice"):
            out = args.output / task / arm
            with ThreadingHTTPServer(("127.0.0.1", 0), LocalRole) as server:
                server.answers, server.writes = answers, []
                threading.Thread(target=server.serve_forever, daemon=True).start()
                url = f"http://127.0.0.1:{server.server_port}"
                try:
                    with (
                        patch.dict(
                            os.environ,
                            {
                                "DEEPSEEK_API_KEY": "local-fixture",
                                "DEEPSEEK_BASE_URL": url,
                                "NO_PROXY": "127.0.0.1,localhost",
                                "no_proxy": "127.0.0.1,localhost",
                            },
                        ),
                        tempfile.TemporaryDirectory() as tmp,
                    ):
                        attempt = run(
                            "Process the local referral.",
                            url + "/mcp",
                            "deepseek-v4-pro",
                            Path(tmp),
                            out / "agent",
                            scorer if arm == "advice" else None,
                        )
                    trajectory = export(attempt)
                    (out / "agent/trajectory.json").write_text(
                        json.dumps(trajectory.to_json_dict())
                    )
                    if arm == "advice":
                        logs = [
                            json.loads(l)
                            for l in (attempt / "review.jsonl").read_text().splitlines()
                        ]
                        (notice,) = [l for l in logs if l["event"] == "notice"]
                        expected = previous[task_name]
                        assert (notice["action"], notice["prompt_sha256"]) == (
                            expected["rejev"],
                            expected["prompt_sha256"],
                        )
                        assert server.writes == [
                            FORMS,
                            BUNDLE if notice["action"] == "allow" else DECISION,
                        ]
                    else:
                        assert server.writes == [FORMS, BUNDLE]
                    (out / "local.json").write_text(
                        json.dumps({"task": task_name, "writes": server.writes})
                    )
                    print(task, arm, server.writes, flush=True)
                finally:
                    server.shutdown()


if __name__ == "__main__":
    main()
