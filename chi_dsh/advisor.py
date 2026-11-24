"""One-shot CPU ReJev inference using the frozen study-02 choice protocol."""

import argparse
import hashlib
import importlib.util
import json
import sys


def main():
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    parser = argparse.ArgumentParser()
    parser.add_argument("protocol")
    parser.add_argument("base")
    parser.add_argument("adapter")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("choice_protocol", args.protocol)
    protocol = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(protocol)
    state = json.load(sys.stdin)
    torch.set_num_threads(3)
    tok = AutoTokenizer.from_pretrained(args.base, local_files_only=True)
    base = AutoModelForCausalLM.from_pretrained(
        args.base,
        dtype=torch.bfloat16,
        attn_implementation="sdpa",
        local_files_only=True,
    )
    model = PeftModel.from_pretrained(base, args.adapter, local_files_only=True).eval()
    prompt = tok.apply_chat_template(
        protocol.messages(state, protocol.ACTIONS),
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    inputs = tok(prompt, return_tensors="pt", add_special_tokens=False)
    letters = [tok.encode(s, add_special_tokens=False) for s in "ABC"]
    if any(len(ids) != 1 for ids in letters):
        raise ValueError("Expected single-token choices")
    with torch.inference_mode():
        logits = model(**inputs, use_cache=False, logits_to_keep=1).logits[0, -1]
        choice = logits[[ids[0] for ids in letters]].argmax().item()
    print(
        json.dumps(
            {
                "action": protocol.ACTIONS[choice],
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "tokens": inputs.input_ids.shape[-1],
            }
        )
    )


if __name__ == "__main__":
    main()
