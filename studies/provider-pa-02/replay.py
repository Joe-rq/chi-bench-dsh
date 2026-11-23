"""Apply an explicit missing-field rule to the first bundle attempt in public runs."""
import argparse
import csv
import json
import subprocess
from collections import Counter
from pathlib import Path

REV = "86ef971ff809f037dd4c502d099733b7dc23f9b2"
PACKETS = ("2026-07-24-opus-5-claude-code", "2026-07-26-erius-opus5")


def gate(trace):
    known = {}
    for line in trace.splitlines():
        step = json.loads(line)
        calls = step.get("tool_calls", [])
        names = {c["tool_call_id"]: c["function_name"].removeprefix("mcp__healthverse__")
                 for c in calls}
        if "docs_create_submission_bundle" in names.values():
            return step["step_id"], len(known), sum(len(x) for x in known.values())
        for response in step.get("observation", {}).get("results", []):
            if names.get(response.get("source_call_id")) not in (
                    "forms_validate_form", "forms_save_form_response"):
                continue
            try:
                payload = json.loads(response["content"])
            except (TypeError, ValueError):
                continue
            if isinstance(payload, dict):
                for form in payload.get("form_validations", []):
                    known[form["form_id"]] = form["missing_required_fields"]
    return None, 0, 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    revision = subprocess.check_output(["git", "-C", args.checkout, "rev-parse", "HEAD"],
                                       text=True).strip()
    if revision != REV:
        parser.error(f"Expected {REV}")
    with args.output.open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(("packet", "task", "step", "forms_seen", "missing_count", "prediction", "packet_target"))
        for packet in PACKETS:
            root = args.checkout / "benchmarks/chi-bench/submissions" / packet / "trials/pa_provider"
            counts = Counter()
            for trial in sorted(root.iterdir()):
                trace = subprocess.check_output(["zstd", "-dc", trial / "agent/trajectory.jsonl.zst"])
                step, seen, missing = gate(trace)
                pred = "no_attempt" if step is None else ("gather" if missing else "allow")
                # Gold is joined only after the prediction. An applicable absence check
                # requires no packet even when the trajectory failed that check.
                checks = json.loads((trial / "verifier/scorecard.json").read_text())["checks"]
                absent = isinstance(checks.get("provider_pre_submission.packet_absent"), bool)
                required = isinstance(checks.get("judge.provider_pre_submission.submission.service_request"), bool)
                if absent == required:
                    raise ValueError(f"Ambiguous packet target for {trial.name}")
                target = "absent" if absent else "required"
                name = json.loads((trial / "result.json").read_text())["task_name"]
                w.writerow((packet, name, step, seen if step else None, missing if step else None, pred, target))
                counts[pred, target] += 1
            if counts.total() != 25:
                raise ValueError(f"Expected 25 trials for {packet}")
            print(packet, sorted(counts.items()))


if __name__ == "__main__":
    main()
