#!/usr/bin/env python3
"""Merge a LoRA adapter into the base model."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen3.5-9B")
    parser.add_argument("--adapter", required=True)
    parser.add_argument("--out", type=Path, required=True)
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
    merged = PeftModel.from_pretrained(base, args.adapter).merge_and_unload()
    args.out.mkdir(parents=True, exist_ok=True)
    merged.save_pretrained(args.out, safe_serialization=True)
    tokenizer.save_pretrained(args.out)
    print(f"saved merged model to {args.out}")


if __name__ == "__main__":
    main()
