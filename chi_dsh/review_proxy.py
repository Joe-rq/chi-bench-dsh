"""Interpose a one-time advisory before the first packet write in one trial."""

import argparse
import asyncio
import json
import time
from pathlib import Path

import httpx
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

BUNDLE = "docs_create_submission_bundle"
FORM = "forms_save_form_response"


def update_draft(state, args):
    answers = args.get("answers", {})
    if isinstance(answers, str):
        try:
            answers = json.loads(answers)
        except ValueError:
            return
    if not isinstance(answers, dict):
        return
    entries = state["draft_questionnaire_entries"]
    for key, value in answers.items():
        if key == "request_description":
            state["submitted_form_draft_description"] = str(value)[:1000]
        elif not key.startswith("request_") and (key in entries or len(entries) < 6):
            entries[key] = str(value)[:120]


async def serve(args, upstream):
    server = Server("chi-rejev-review")
    lock = asyncio.Lock()
    state = {"submitted_form_draft_description": "", "draft_questionnaire_entries": {}}
    reviewed = False
    form_calls = 0

    def log(**event):
        with Path(args.log).open("a") as f:
            f.write(json.dumps(event) + "\n")

    @server.list_tools()
    async def list_tools():
        tools = []
        cursor = None
        while True:
            page = await upstream.list_tools(cursor=cursor)
            tools.extend(page.tools)
            cursor = page.nextCursor
            if not cursor:
                return tools

    @server.call_tool(validate_input=False)
    async def call(name, arguments):
        nonlocal reviewed, form_calls
        async with lock:
            if name == BUNDLE and not reviewed:
                start = time.monotonic()
                proc = await asyncio.create_subprocess_exec(
                    *args.scorer,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                )
                try:
                    out, _ = await asyncio.wait_for(
                        proc.communicate(json.dumps(state).encode()), 90
                    )
                    if proc.returncode:
                        raise RuntimeError("ReJev scorer failed")
                    verdict = json.loads(out)
                    if verdict["action"] not in ("allow", "gather", "stop"):
                        raise ValueError("Unexpected ReJev choice")
                except BaseException as exc:
                    if proc.returncode is None:
                        proc.kill()
                        await proc.wait()
                    log(event="scorer_failure", error=type(exc).__name__)
                    raise
                log(
                    event="notice",
                    form_calls=form_calls,
                    **verdict,
                    seconds=round(time.monotonic() - start, 3),
                )
                reviewed = True
                notice = (
                    f"Pre-bundle review: {verdict['action']}. No packet has been created. "
                    "Consider this advisory using your own evidence. You may gather evidence, "
                    "record a determination, or call this tool again to proceed."
                )
                return types.CallToolResult(
                    isError=True, content=[types.TextContent(type="text", text=notice)]
                )
            result = await upstream.call_tool(name, arguments)
            if name == FORM:
                form_calls += 1
                update_draft(state, arguments)
            if name == BUNDLE:
                log(event="bundle_forwarded", tool_error=bool(result.isError))
            return result

    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("log")
    parser.add_argument("scorer", nargs="+")
    args = parser.parse_args()
    async with (
        httpx.AsyncClient(trust_env=False, timeout=120) as client,
        streamable_http_client(args.url, http_client=client) as (reader, writer, _),
        ClientSession(reader, writer) as upstream,
    ):
        await upstream.initialize()
        await serve(args, upstream)


if __name__ == "__main__":
    asyncio.run(main())
