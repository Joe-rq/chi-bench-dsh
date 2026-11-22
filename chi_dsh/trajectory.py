"""Translate DSH transcript events into Harbor's validated ATIF trajectory."""

import json
from pathlib import Path

from harbor.models.trajectories.trajectory import Trajectory


def content(blocks):
    return "\n".join(
        b["text"] if b.get("type") == "text" else json.dumps(b, ensure_ascii=False)
        for b in blocks
    )


def export(attempt: Path):
    metadata = json.loads((attempt / "execution.json").read_text())
    steps = []
    calls = {}
    usage_rows = []

    for line in (attempt / "events.jsonl").read_text().splitlines():
        event = json.loads(line)
        kind, data = event["type"], event["data"]
        if kind == "tool/result":
            message = data["message"]
            call_id = message["toolCallId"]
            step = calls[call_id]
            observation = step.setdefault("observation", {"results": []})
            observation["results"].append(
                {
                    "source_call_id": call_id,
                    "content": content(message["content"]),
                    "extra": {"is_error": message.get("isError")},
                }
            )
            continue
        if kind not in ("system/message", "user/message", "assistant/message"):
            continue
        message = data if kind == "user/message" else data["message"]
        source = {"assistant": "agent", "user": "user", "system": "system"}[
            message["role"]
        ]
        blocks = message["content"]
        step = {
            "step_id": len(steps) + 1,
            "source": source,
            "message": content([b for b in blocks if b.get("type") != "tool-call"]),
        }
        steps.append(step)
        for block in blocks:
            if block.get("type") == "tool-call":
                arguments = block["arguments"]
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except ValueError:
                        arguments = {"unparsed_arguments": arguments}
                call_id = block["id"]
                calls[call_id] = step
                step.setdefault("tool_calls", []).append(
                    {
                        "tool_call_id": call_id,
                        "function_name": block["name"],
                        "arguments": arguments
                        if isinstance(arguments, dict)
                        else {"value": arguments},
                    }
                )
        if source == "agent":
            usage = data.get("usage") or {}
            usage_rows.append(usage)
            step["metrics"] = {
                "prompt_tokens": usage.get("inputTokens"),
                "completion_tokens": usage.get("outputTokens"),
            }

    def total(key):
        if usage_rows and all(isinstance(row.get(key), int) for row in usage_rows):
            return sum(row[key] for row in usage_rows)
        return None

    return Trajectory.model_validate(
        {
            "schema_version": "ATIF-v1.2",
            "session_id": metadata.get("session_id", attempt.name),
            "agent": {
                "name": "dsh",
                "version": metadata["sdk"],
                "model_name": metadata["model"],
            },
            "steps": steps,
            "final_metrics": {
                "total_prompt_tokens": total("inputTokens"),
                "total_completion_tokens": total("outputTokens"),
                "total_steps": len(steps),
            },
        }
    )
