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
    scorer = ()

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
                *(["--scorer", *self.scorer] if self.scorer else []),
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


class DshReviewAgent(DshAgent):
    """Dedicated arm with identical DSH model and a local CPU decision model."""

    scorer = (
        "/tmp/chi-review-venv/bin/python",
        "/tmp/advisor.py",
        "/tmp/choice_protocol.py",
        "/tmp/chi-review-base",
        "/tmp/chi-review-adapter",
    )

    @staticmethod
    def name():
        return "dsh-rejev"

    async def install(self, environment):
        import hashlib
        from importlib.resources import files

        assets = []
        for key, target, weight, expected in (
            (
                "CHI_REJEV_BASE",
                self.scorer[-2],
                "model-00000-of-00001.safetensors",
                "14fb8e7f0a18d53d1f239773758bf581cee7e456a4523a54622c3a245b64402c",
            ),
            (
                "CHI_REJEV_ADAPTER",
                self.scorer[-1],
                "adapter_model.safetensors",
                "294b07beac96e42e4a69af41c1121bc2aa0a18cf4634ef2ea9e17b8032b9973e",
            ),
        ):
            if not os.environ.get(key):
                raise ValueError(f"Set {key} to a local pinned weight snapshot")
            root = Path(os.environ[key])
            with (root / weight).open("rb") as f:
                if hashlib.file_digest(f, "sha256").hexdigest() != expected:
                    raise ValueError(f"Unexpected weights in {key}")
            assets.append((root, target, weight))
        await super().install(environment)
        await self.exec_as_root(
            environment,
            command=(
                "uv pip install --python /workspace/.venv mcp==1.26.0 && "
                "uv venv --python /workspace/.venv/bin/python /tmp/chi-review-venv && "
                "uv pip install --python /tmp/chi-review-venv/bin/python torch==2.8.0 "
                "--index-url https://download.pytorch.org/whl/cpu && "
                "uv pip install --python /tmp/chi-review-venv/bin/python transformers==5.6.2 "
                "peft==0.21.0 accelerate==1.16.0 && mkdir -p /tmp/chi-review-base /tmp/chi-review-adapter"
            ),
        )
        for source, target in (
            ("review_proxy.py", "/tmp/review_proxy.py"),
            ("advisor.py", self.scorer[1]),
            ("choice_protocol.py", self.scorer[2]),
        ):
            await environment.upload_file(
                source_path=Path(str(files("chi_dsh") / source)), target_path=target
            )
        for root, target, weight in assets:
            for file in sorted(root.iterdir()):
                if file.name == weight or file.suffix in (".json", ".jinja"):
                    await environment.upload_file(
                        source_path=file, target_path=f"{target}/{file.name}"
                    )
