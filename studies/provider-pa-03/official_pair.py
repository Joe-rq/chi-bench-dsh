"""Run four official trials in a prepared CHI-Bench checkout and render matched audits."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from audit import load

HERE = Path(__file__).resolve().parent
REV = "9d5a48277d4f5867e70e171d9a670d4c1bd19b5a"
TASKS = (
    "pa_t013_t013_o002_p01_new_referral_provider",
    "pa_t015_t015_o002_p01_new_referral_provider",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("tasks", type=Path, help="Provider PA tasks directory")
    parser.add_argument(
        "output", type=Path, help="New directory, or a previous successful partial run"
    )
    parser.add_argument("--environment", choices=["docker", "modal"], default="docker")
    args = parser.parse_args()
    repo, tasks, out = [p.resolve() for p in (args.checkout, args.tasks, args.output)]
    if (
        subprocess.check_output(
            ["git", "-C", repo, "rev-parse", "HEAD"], text=True
        ).strip()
        != REV
    ):
        parser.error(f"Expected upstream commit {REV}")
    cli = repo / ".venv/bin/cb-dsh"
    if not cli.is_file() or not all((tasks / t / "task.toml").is_file() for t in TASKS):
        parser.error(
            "Install the adapter in the upstream venv and provide the two official task directories"
        )
    required = [
        "DEEPSEEK_API_KEY",
        "ANTHROPIC_API_KEY",
        "CHI_REJEV_BASE",
        "CHI_REJEV_ADAPTER",
    ]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        parser.error("Missing environment settings: " + ", ".join(missing))
    for task in TASKS:
        trials = []
        for agent, arm in (("dsh", "none"), ("dsh-rejev", "rejev-advice")):
            path = out / task / agent
            if not path.exists():
                path.mkdir(parents=True)
                subprocess.run(
                    [
                        cli,
                        "experiment",
                        "run",
                        "--dataset",
                        str(tasks / task),
                        "--agent",
                        agent,
                        "--model",
                        "deepseek/deepseek-v4-pro",
                        "--environment",
                        args.environment,
                        "--trials-dir",
                        str(path),
                    ],
                    env={**os.environ, "CHI_BENCH_MCP_TOOL_SEP": "_"},
                    cwd=repo,
                    check=True,
                )
            scores = list(path.rglob("verifier/scorecard.json"))
            if len(scores) != 1:
                raise RuntimeError(
                    f"Expected one completed scorecard in {path}. Preserve failed trials and retry in a new output directory."
                )
            trial = scores[0].parents[1]
            identity, _ = load(trial, arm, False)
            if identity[0].split("/")[-1] != task:
                raise ValueError("Unexpected task in existing trial")
            trials.append(trial)
        rendered = subprocess.check_output(
            [sys.executable, HERE / "audit.py", *trials], text=True
        )
        (out / task / "audit.md").write_text(rendered)
        print(out / task / "audit.md", flush=True)


if __name__ == "__main__":
    main()
