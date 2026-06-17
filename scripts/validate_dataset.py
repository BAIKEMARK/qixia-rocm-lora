#!/usr/bin/env python3
"""Validate ShareGPT role-play datasets for direct LoRA training."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Any


class DatasetValidationError(ValueError):
    pass


def load_json(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise DatasetValidationError(f"expected top-level JSON list: {path}")
    return data


def _message_text(message: dict[str, Any], role_key: str, content_key: str) -> tuple[str, str]:
    role = message.get(role_key)
    content = message.get(content_key)
    if not isinstance(role, str) or not role:
        raise DatasetValidationError(f"invalid message role: {message!r}")
    if not isinstance(content, str) or not content.strip():
        raise DatasetValidationError(f"invalid message content: {message!r}")
    return role, content.strip()


def validate_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise DatasetValidationError("dataset is empty")

    turn_counts: list[int] = []
    user_lengths: list[int] = []
    assistant_lengths: list[int] = []

    for index, row in enumerate(rows):
        conversations = row.get("conversations")
        if not isinstance(conversations, list) or len(conversations) < 2:
            raise DatasetValidationError(f"row {index} must contain at least 2 conversation turns")

        seen_user = False
        seen_assistant = False
        for message in conversations:
            if not isinstance(message, dict):
                raise DatasetValidationError(f"row {index} has non-object message: {message!r}")
            role, content = _message_text(message, "from", "value")
            if role == "human":
                seen_user = True
                user_lengths.append(len(content))
            elif role == "gpt":
                seen_assistant = True
                assistant_lengths.append(len(content))
            else:
                raise DatasetValidationError(f"row {index} has unsupported role: {role}")

        if conversations[0].get("from") != "human" or conversations[-1].get("from") != "gpt":
            raise DatasetValidationError(f"row {index} must start with human and end with gpt")
        if not seen_user or not seen_assistant:
            raise DatasetValidationError(f"row {index} must include human and gpt messages")

        system = row.get("system", "")
        if system is not None and not isinstance(system, str):
            raise DatasetValidationError(f"row {index} system must be a string when present")
        turn_counts.append(len(conversations))

    return {
        "examples": len(rows),
        "min_turns": min(turn_counts),
        "max_turns": max(turn_counts),
        "avg_turns": round(mean(turn_counts), 2),
        "avg_user_chars": round(mean(user_lengths), 2),
        "avg_assistant_chars": round(mean(assistant_lengths), 2),
        "max_user_chars": max(user_lengths),
        "max_assistant_chars": max(assistant_lengths),
    }


def validate_dataset_file(path: Path) -> dict[str, Any]:
    stats = validate_rows(load_json(path))
    stats["path"] = str(path)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args()

    results = [validate_dataset_file(path) for path in args.paths]
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
