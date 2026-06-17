#!/usr/bin/env python3
"""Run LLaMA Factory LoRA training with the project config."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/qwen3_5_9b_lora.yaml"))
    parser.add_argument("--repo-dir", type=Path, default=Path.cwd())
    args = parser.parse_args()

    env = os.environ.copy()
    env.setdefault("HIP_VISIBLE_DEVICES", "0")
    env.setdefault("CUDA_VISIBLE_DEVICES", "0")
    env.setdefault("PYTORCH_HIP_ALLOC_CONF", "expandable_segments:True")
    env.setdefault("TOKENIZERS_PARALLELISM", "false")

    cmd = ["llamafactory-cli", "train", str(args.config)]
    print("$", " ".join(cmd))
    subprocess.run(cmd, cwd=args.repo_dir, env=env, check=True)


if __name__ == "__main__":
    main()
