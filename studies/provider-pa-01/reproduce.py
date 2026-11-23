"""Build the paired audit from the pinned public Git snapshot. Requires git and zstd."""
import argparse
import csv
import json
import subprocess
from collections import Counter
from pathlib import Path

REV = "86ef971ff809f037dd4c502d099733b7dc23f9b2"
PACKETS = {"cc": "2026-07-24-opus-5-claude-code", "erius": "2026-07-26-erius-opus5"}
ROOT = Path("benchmarks/chi-bench/submissions")
TRACKED = {
    "docs_create_submission_bundle": "bundle",
    "auth_finalize_provider_determination": "decision",
    "auth_submit_authorization": "submit",
}
CHECK = "provider_pre_submission.packet_absent"


def read_json(path):
    return json.loads(path.read_text())


def collect(repo, packet):
    domain = repo / ROOT / packet / "trials/pa_provider"
    runs = {}
    for trial in sorted(domain.iterdir()):
        result = read_json(trial / "result.json")
        card = read_json(trial / "verifier/scorecard.json")
        reward = read_json(trial / "verifier/reward.json")["reward"]
        if reward not in (0, 1) or reward != card["binary_reward"]:
            raise ValueError(f"Inconsistent reward: {trial}")
        actions = []
        trace = subprocess.check_output(["zstd", "-dc", trial / "agent/trajectory.jsonl.zst"])
        for line in trace.splitlines():
            step = json.loads(line)
            for call in step.get("tool_calls", []):
                name = call["function_name"].removeprefix("mcp__healthverse__")
                if name not in TRACKED:
                    continue
                action = TRACKED[name]
                if action == "decision":
                    action += "=" + call["arguments"]["final_action"]
                actions.append(f"{step['step_id']}:{action}")
        task = result["task_name"]
        if task in runs:
            raise ValueError(f"Duplicate trial for {task}")
        runs[task] = {
            "reward": int(reward), "checks": f"{card['passed_checks']}/{card['total_checks']}",
            "failed": "|".join(card["failed_checks"]), "calls": "|".join(actions),
            "task_checksum": result["task_checksum"],
            "source": f"https://github.com/actava-ai/leaderboard/tree/{REV}/{trial.relative_to(repo)}",
        }
    return runs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    repo = args.source.resolve()
    revision = subprocess.check_output(["git", "-C", repo, "rev-parse", "HEAD"], text=True).strip()
    if revision != REV:
        parser.error(f"Check out source commit {REV}")
    cc, erius = [collect(repo, packet) for packet in PACKETS.values()]
    if cc.keys() != erius.keys() or len(cc) != 25:
        raise ValueError("Expected the same 25 distinct Provider PA task names")
    pairs = Counter()
    packet_fail = submit_calls = checksum_matches = 0
    rows = []
    for task in sorted(cc):
        a, b = cc[task], erius[task]
        pairs[a["reward"], b["reward"]] += 1
        checksum_matches += a["task_checksum"] == b["task_checksum"]
        if CHECK in a["failed"].split("|"):
            packet_fail += 1
            submit_calls += any(x.endswith(":submit") for x in a["calls"].split("|"))
        row = {"task": task}
        for label, run in (("cc", a), ("erius", b)):
            row.update({f"{label}_{k}": v for k, v in run.items()})
        rows.append(row)
    with args.output.open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print("Paired outcomes (Claude Code, Erius):", sorted(pairs.items()))
    print(f"Claude Code: {packet_fail} packet_absent failures; {submit_calls} with a submit call")
    print(f"Matching task checksums: {checksum_matches}/{len(rows)}")


if __name__ == "__main__":
    main()
