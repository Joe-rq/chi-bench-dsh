"""Host-side Harbor adapter for CHI-Bench's isolated agent container."""

import json
import os
import shlex
from pathlib import Path

from harbor.agents.installed.base import BaseInstalledAgent, with_prompt_template

from .runner import SDK_VERSION
from .trajectory import export


class DshAgent(BaseInstalledAgent):
    SUPPORTS_ATIF = True

    @staticmethod
    def name():
        return "dsh"

    def get_version_command(self):
        return "/workspace/.venv/bin/python -c \"from importlib.metadata import version; print(version('deepseek-harness-sdk'))\""

    async def install(self, environment):
        # Keep contestant dependencies out of the simulator and judge environments.
        await self.exec_as_root(
            environment,
            command=f"uv pip install --python /workspace/.venv deepseek-harness-sdk=={SDK_VERSION}",
        )
        await environment.upload_file(
            source_path=Path(__file__).with_name("runner.py"),
            target_path="/tmp/chi_dsh_runner.py",
        )

    @with_prompt_template
    async def run(self, instruction, environment, context):
        urls = [server.url for server in self.mcp_servers if server.url]
        if len(urls) != 1:
            raise ValueError("Expected exactly one role-scoped task MCP endpoint")
        key = self._extra_env.get("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
        if not key or not self.model_name:
            raise ValueError("A DeepSeek model and DEEPSEEK_API_KEY are required")
        model = self.model_name.removeprefix("deepseek/")
        command = shlex.join(
            [
                "/workspace/.venv/bin/python",
                "/tmp/chi_dsh_runner.py",
                "--instruction-file",
                "/tmp/chi_dsh_instruction.md",
                "--mcp-url",
                urls[0],
                "--model",
                model,
            ]
        )
        await self.exec_as_agent(
            environment,
            command=(
                f"printf %s {shlex.quote(instruction)} > /tmp/chi_dsh_instruction.md && "
                f"{command} > /logs/agent/dsh.log 2>&1"
            ),
            env={"DEEPSEEK_API_KEY": key},
        )

    def populate_context_post_run(self, context):
        attempts = list(self.logs_dir.glob("dsh-*/events.jsonl"))
        if not attempts:
            return
        if len(attempts) != 1:
            raise ValueError("Multiple DSH executions in one Harbor trial directory")
        if not attempts[0].stat().st_size:
            return
        trajectory = export(attempts[0].parent)
        path = self.logs_dir / "trajectory.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(trajectory.to_json_dict(), ensure_ascii=False, indent=2)
        )
        tmp.replace(path)
        context.n_input_tokens = trajectory.final_metrics.total_prompt_tokens
        context.n_output_tokens = trajectory.final_metrics.total_completion_tokens
