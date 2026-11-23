"""Score the first Claude Code bundle attempt using only preceding form writes."""
import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path

from replay import PACKETS, REV
from run import ADAPTER, ADAPTER_REV, BASE, BASE_REV, ACTIONS, messages


def pre_bundle_state(trace):
    description = ""
    questionnaire = {}
    for line in trace.splitlines():
        step = json.loads(line)
        calls = step.get("tool_calls", [])
        if any(c["function_name"].endswith("__docs_create_submission_bundle") for c in calls):
            # The guard can see attempted form entries, including the original agent's
            # interpretation. They are not independent observations or a complete chart.
            return step["step_id"], {"submitted_form_draft_description": description,
                                     "draft_questionnaire_entries": questionnaire}
        for call in calls:
            if not call["function_name"].endswith("__forms_save_form_response"):
                continue
            answers = call["arguments"]["answers"]
            if isinstance(answers, str):
                try:
                    answers = json.loads(answers)
                except ValueError:
                    # A malformed attempted write has no reliably extractable fields.
                    continue
            if not isinstance(answers, dict):
                continue
            for key, value in answers.items():
                if key == "request_description":
                    description = str(value)[:1000]
                elif not key.startswith("request_") and (key in questionnaire or len(questionnaire) < 6):
                    questionnaire[key] = str(value)[:120]
    raise ValueError("Expected a first bundle attempt")


def main():
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--base-dir")
    parser.add_argument("--adapter-dir")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    rev = subprocess.check_output(["git", "-C", args.checkout, "rev-parse", "HEAD"], text=True).strip()
    if rev != REV:
        parser.error(f"Expected source at {REV}")
    torch.set_num_threads(args.threads)
    tok = AutoTokenizer.from_pretrained(args.base_dir or BASE, revision=BASE_REV)
    base = AutoModelForCausalLM.from_pretrained(args.base_dir or BASE, revision=BASE_REV,
              dtype=torch.bfloat16, attn_implementation="sdpa")
    model = PeftModel.from_pretrained(base, args.adapter_dir or ADAPTER, revision=ADAPTER_REV).eval()
    ids = [tok.encode(s, add_special_tokens=False) for s in "ABC"]
    if any(len(s) != 1 for s in ids):
        raise ValueError("Expected single-token choices")
    letters = [s[0] for s in ids]
    runs = args.checkout / "benchmarks/chi-bench/submissions" / PACKETS[0] / "trials/pa_provider"
    trials = sorted(runs.iterdir())
    if len(trials) != 25:
        raise ValueError("Expected the complete Claude Code packet")
    with args.output.open("w", newline="") as f, torch.inference_mode():
        w = csv.writer(f, lineterminator="\n")
        w.writerow(("task", "step", "prompt_sha256", "tokens", "base", "rejev"))
        for trial in trials:
            trace = subprocess.check_output(["zstd", "-dc", trial / "agent/trajectory.jsonl.zst"])
            step, state = pre_bundle_state(trace)
            prompt = tok.apply_chat_template(messages(state, ACTIONS), tokenize=False,
                       add_generation_prompt=True, enable_thinking=False)
            tokens = tok(prompt, return_tensors="pt", add_special_tokens=False)
            def choose():
                logits = model(**tokens, use_cache=False, logits_to_keep=1).logits
                return ACTIONS[logits[0, -1, letters].argmax().item()]
            with model.disable_adapter():
                baseline = choose()
            rejev = choose()
            task = json.loads((trial / "result.json").read_text())["task_name"]
            w.writerow((task, step, hashlib.sha256(prompt.encode()).hexdigest(),
                        tokens.input_ids.shape[-1], baseline, rejev))
            f.flush()
            print(f"Scored {task[:7]}", flush=True)


if __name__ == "__main__":
    main()
