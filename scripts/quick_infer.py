#!/usr/bin/env python3
"""Quick base-model + LoRA inference smoke test."""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen3.5-9B")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--prompt", default="如果一个规则看起来互相矛盾，你会怎么判断？")
    parser.add_argument("--max-new-tokens", type=int, default=160)
    args = parser.parse_args()

    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
    import torch

    tokenizer = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(base, args.adapter)

    messages = [
        {
            "role": "system",
            "content": "你正在扮演《十日终焉》中的齐夏。保持冷静、克制、善于观察和推理。只输出齐夏会说的话。",
        },
        {"role": "user", "content": args.prompt},
    ]
    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer([text], return_tensors="pt").to(model.device)
    with torch.no_grad():
        output = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=True, temperature=0.7)
    new_tokens = output[0][inputs.input_ids.shape[-1] :]
    print(tokenizer.decode(new_tokens, skip_special_tokens=True).strip())


if __name__ == "__main__":
    main()
