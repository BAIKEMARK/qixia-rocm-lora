#!/usr/bin/env python3
"""Patch LLaMA Factory to load Qwen3.5 as a text-only causal LM.

Qwen3.5 checkpoints are natively multimodal, but Transformers exposes
Qwen3_5ForCausalLM for text-only generation and fine-tuning. LLaMA Factory
currently routes qwen3_5 configs through AutoModelForImageTextToText, which
loads the vision tower and trips torch 2.9.x + Conv3D checks on ROCm.
"""

from __future__ import annotations

import argparse
from pathlib import Path


OLD = """            if type(config) in AutoModelForImageTextToText._model_mapping.keys():  # image-text
                load_class = AutoModelForImageTextToText
            elif type(config) in AutoModelForSeq2SeqLM._model_mapping.keys():  # audio-text
"""

NEW = """            if getattr(config, "model_type", None) == "qwen3_5":
                from transformers import Qwen3_5ForCausalLM
                init_kwargs["config"] = config.text_config
                load_class = Qwen3_5ForCausalLM
            elif type(config) in AutoModelForImageTextToText._model_mapping.keys():  # image-text
                load_class = AutoModelForImageTextToText
            elif type(config) in AutoModelForSeq2SeqLM._model_mapping.keys():  # audio-text
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--loader",
        type=Path,
        default=Path("/LlamaFactory/src/llamafactory/model/loader.py"),
        help="Path to LLaMA Factory loader.py.",
    )
    args = parser.parse_args()

    text = args.loader.read_text(encoding="utf-8")
    if 'getattr(config, "model_type", None) == "qwen3_5"' in text and 'init_kwargs["config"] = config.text_config' in text:
        print(f"already patched: {args.loader}")
        return

    if OLD not in text:
        raise SystemExit(f"patch pattern not found in {args.loader}")

    backup = args.loader.with_suffix(args.loader.suffix + ".bak_qwen35_text_only")
    if not backup.exists():
        backup.write_text(text, encoding="utf-8")

    args.loader.write_text(text.replace(OLD, NEW), encoding="utf-8")
    print(f"patched: {args.loader}")
    print(f"backup: {backup}")


if __name__ == "__main__":
    main()
