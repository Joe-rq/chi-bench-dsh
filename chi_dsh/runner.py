"""DSH contestant process. Executed under the trial's agent identity."""

import argparse
import json
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path

SDK_VERSION = "0.2.2rc2"


def profile_patch(url, review=None):
    transport = {"transport": "streamable-http", "url": url}
    if review:
        transport = {
            "transport": "stdio",
            "command": sys.executable,
            "cwd": str(Path(__file__).resolve().parent),
            "args": [str(Path(__file__).with_name("review_proxy.py")), url, *review],
            "toolCallTimeoutMs": 120000,
        }
    return [
        {"id": "session-log-deepseek", "disabled": True},
        {
            "insert": [
                {
                    "id": "chi-role-tools",
                    "name": "@deepseek-ai/dsh-mcp-client",
                    "config": {
                        "serverName": "chi_bench",
                        **transport,
                        "failOnStartupError": True,
                        "startupTimeoutMs": 30000,
                    },
                }
            ]
        },
    ]


def run(instruction, url, model, workspace, output, scorer=None):
    from deepseek_harness import DeepSeekHarness

    output.mkdir(parents=True, exist_ok=True)
    # Independent directories also keep evidence from an interrupted run intact.
    attempt = Path(tempfile.mkdtemp(prefix="dsh-", dir=output))
    metadata = {
        "model": model,
        "sdk": version("deepseek-harness-sdk"),
        "profile": "sdk-minimal",
        "execution": "started",
        "review": "rejev-advice" if scorer else "none",
    }
    status = attempt / "execution.json"

    def save():
        temporary = status.with_suffix(".tmp")
        temporary.write_text(json.dumps(metadata, indent=2) + "\n")
        temporary.replace(status)

    save()
    try:
        with tempfile.TemporaryDirectory(prefix="chi-dsh-") as private:
            patch = Path(private) / "role.yml"
            patch.write_text(
                json.dumps(
                    profile_patch(
                        url,
                        [str(attempt / "review.jsonl"), *scorer] if scorer else None,
                    )
                )
            )
            with (attempt / "events.jsonl").open("x") as events:
                review_tools_ready = False

                def record(notification):
                    nonlocal review_tools_ready
                    if notification.method == "session.event":
                        event = notification.payload["event"]
                        if scorer and event["type"] == "request/header":
                            names = {
                                t["name"]
                                for t in event["data"]["header"].get("tools", [])
                            }
                            review_tools_ready |= {
                                "mcp__chi_bench__forms_save_form_response",
                                "mcp__chi_bench__docs_create_submission_bundle",
                            } <= names
                        events.write(json.dumps(event, ensure_ascii=False) + "\n")
                        events.flush()

                with DeepSeekHarness(
                    provider="deepseek-official",
                    model=model,
                    cwd=str(workspace.resolve()),
                    profile="sdk-minimal",
                    dsh_home=str(Path(private) / "home"),
                    patches=(str(patch),),
                ) as harness:
                    result = harness.run(instruction, on_notification=record)
                metadata["session_id"] = result.session_id
                metadata["finish_reason"] = result.finish_reason
                if result.finish_reason != "completed":
                    raise RuntimeError(f"DSH stopped with {result.finish_reason!r}")
                if scorer and not review_tools_ready:
                    raise RuntimeError(
                        "Pre-bundle review tools did not activate. Check MCP startup and the tool separator."
                    )
                (attempt / "response.txt").write_text(result.final_response)
                metadata["execution"] = "completed"
    except BaseException as error:
        metadata.update(execution="interrupted", error_type=type(error).__name__)
        raise
    finally:
        save()
    return attempt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--instruction-file", required=True, type=Path)
    parser.add_argument("--mcp-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--workspace", type=Path, default=Path("/workspace"))
    parser.add_argument("--output", type=Path, default=Path("/logs/agent"))
    parser.add_argument("--scorer", nargs="+")
    args = parser.parse_args()
    run(
        args.instruction_file.read_text(),
        args.mcp_url,
        args.model,
        args.workspace,
        args.output,
        args.scorer,
    )
