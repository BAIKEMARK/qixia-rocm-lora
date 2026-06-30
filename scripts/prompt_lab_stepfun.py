#!/usr/bin/env python3
"""Small StepFun prompt lab for TaleTalk prompts.

This script samples real novel text, calls the one-pass prompt, then optionally
uses the adversarial reviewer prompt to critique the output. Results are written
under cache/prompt_lab/ and are not intended for Git.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    from openai import OpenAI
except ImportError:
    print("Missing dependency: pip install openai", file=sys.stderr)
    sys.exit(1)


REPO_DIR = Path(__file__).resolve().parents[1]
PROMPT_DIR = REPO_DIR / "prompts" / "taletalk"
NOVEL_PATH = REPO_DIR / "novels" / "《十日终焉》（校对全本）.txt"
ENV_CANDIDATES = [
    REPO_DIR / ".env",
    REPO_DIR / ".env.stepfun",
    REPO_DIR.parent / "extract-dialogue" / ".env",
    REPO_DIR.parent / "extract-dialogue" / ".env.stepfun",
    REPO_DIR / "extract-dialogue" / ".env.stepfun",
]


def load_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip("\"'")
    return out


def load_stepfun_env() -> tuple[str, str, str, Path | None]:
    env_path = next((path for path in ENV_CANDIDATES if path.exists()), None)
    file_env = load_env_file(env_path) if env_path else {}
    api_key = os.environ.get("STEPFUN_API_KEY") or os.environ.get("CUSTOM_API_KEY") or file_env.get("CUSTOM_API_KEY")
    base_url = (
        os.environ.get("STEPFUN_BASE_URL")
        or os.environ.get("CUSTOM_BASE_URL")
        or file_env.get("CUSTOM_BASE_URL")
        or "https://api.stepfun.com/step_plan/v1"
    )
    model = (
        os.environ.get("STEPFUN_MODEL")
        or os.environ.get("STEPFUN_MODEL_NAME")
        or os.environ.get("CUSTOM_MODEL_NAME")
        or file_env.get("CUSTOM_MODEL_NAME")
        or file_env.get("STEPFUN_MODEL_NAME")
        or "step-3.7-flash"
    )
    if not api_key:
        checked = ", ".join(str(path) for path in ENV_CANDIDATES)
        raise SystemExit(f"Missing StepFun key. Checked env vars and: {checked}")
    return api_key, base_url, model, env_path


def read_prompt(name: str) -> str:
    text = (PROMPT_DIR / name).read_text(encoding="utf-8")
    match = re.search(r"<!-- PROMPT_START -->(.*?)<!-- PROMPT_END -->", text, re.S)
    if not match:
        raise ValueError(f"Prompt markers not found: {name}")
    return match.group(1).strip()


def parse_one_pass_json(text: str, payload: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str | None]:
    try:
        parsed = json.loads(text)
    except Exception as exc:
        return None, str(exc)
    if not isinstance(parsed, dict):
        return None, "top-level JSON is not an object"
    if parsed.get("version") != "taletalk-one-pass-v1":
        return None, "missing or invalid version"
    for key in ["scene_memories", "profile_observations", "candidate_samples", "batch_warnings"]:
        if key not in parsed:
            return None, f"missing key: {key}"
        if not isinstance(parsed[key], list):
            return None, f"key is not a list: {key}"
    if payload is not None:
        scene_ids = {str(scene["scene_id"]) for scene in payload.get("scenes", [])}
        scene_count = max(1, len(scene_ids))
        if len(parsed["candidate_samples"]) > scene_count:
            return None, f"too many candidate_samples: {len(parsed['candidate_samples'])} > {scene_count}"
        if len(parsed["profile_observations"]) > 2:
            return None, f"too many profile_observations: {len(parsed['profile_observations'])} > 2"
        for scene in parsed["scene_memories"]:
            if str(scene.get("scene_id")) not in scene_ids:
                return None, f"unknown scene_id in scene_memories: {scene.get('scene_id')}"
            for key in [
                "coverage",
                "summary",
                "characters",
                "target_role_present",
                "target_role_knows",
                "knowledge_level",
                "events",
                "relations",
                "quotes",
                "source_risks",
            ]:
                if key not in scene:
                    return None, f"missing scene key {key} in {scene.get('scene_id')}"
            if not isinstance(scene.get("characters"), list):
                return None, f"scene characters is not a list: {scene.get('scene_id')}"
            for field, limit in [("events", 3), ("relations", 2), ("quotes", 2)]:
                value = scene.get(field, [])
                if not isinstance(value, list):
                    return None, f"scene field is not a list: {field}"
                if len(value) > limit:
                    return None, f"too many {field} in {scene.get('scene_id')}: {len(value)} > {limit}"
            for quote in scene.get("quotes", []):
                if not isinstance(quote, dict) or "role" not in quote or "text" not in quote:
                    return None, f"invalid quote object in {scene.get('scene_id')}"
        for obs in parsed["profile_observations"]:
            if not isinstance(obs, dict):
                return None, "profile_observations item is not an object"
            for key in ["aspect", "value", "source_scene_ids", "confidence"]:
                if key not in obs:
                    return None, f"missing profile_observations key: {key}"
            ids = obs.get("source_scene_ids", [])
            if not isinstance(ids, list):
                return None, "profile_observations source_scene_ids is not a list"
            unknown = [scene_id for scene_id in ids if str(scene_id) not in scene_ids]
            if unknown:
                return None, f"unknown profile source_scene_ids: {unknown}"
        for sample in parsed["candidate_samples"]:
            if not isinstance(sample, dict):
                return None, "candidate_samples item is not an object"
            for key in [
                "sample_type",
                "question",
                "answer",
                "source_scene_ids",
                "knowledge_level",
                "answer_policy",
                "must_not_claim",
                "risk_tags",
            ]:
                if key not in sample:
                    return None, f"missing candidate_samples key: {key}"
            ids = sample.get("source_scene_ids", [])
            if not isinstance(ids, list):
                return None, "source_scene_ids is not a list"
            unknown = [scene_id for scene_id in ids if str(scene_id) not in scene_ids]
            if unknown:
                return None, f"unknown source_scene_ids: {unknown}"
    return parsed, None


def make_scene(text: str, keyword: str, scene_id: str, radius: int, coverage: str = "full") -> dict[str, Any]:
    pos = text.find(keyword)
    if pos < 0:
        raise ValueError(f"Keyword not found: {keyword}")
    start = max(0, pos - radius)
    end = min(len(text), pos + radius)
    raw = text[start:end].strip()
    return {
        "scene_id": scene_id,
        "chapter": "",
        "source_start": start,
        "source_end": end,
        "coverage": coverage,
        "raw_text": raw,
        "dialogues": [],
    }


def build_case(case_name: str) -> dict[str, Any]:
    text = NOVEL_PATH.read_text(encoding="utf-8", errors="ignore")
    if case_name == "qixia":
        scenes = [make_scene(text, "齐夏", "lab_qixia_001", 650)]
    elif case_name == "yuniannian":
        scenes = [make_scene(text, "余念安", "lab_yuniannian_001", 700)]
    elif case_name == "long":
        scenes = [
            make_scene(text, "齐夏", "lab_long_001", 900),
            make_scene(text, "规则", "lab_long_002", 900),
            make_scene(text, "余念安", "lab_long_003", 900, coverage="partial"),
        ]
    else:
        raise ValueError(f"Unknown case: {case_name}")
    return {
        "target_role": "齐夏",
        "target_aliases": ["齐夏", "老齐", "齐哥", "小齐"],
        "novel_title": "十日终焉",
        "context_budget_chars": sum(len(scene["raw_text"]) for scene in scenes),
        "scenes": scenes,
    }


def call_model(
    client: OpenAI,
    model: str,
    system_prompt: str,
    user_payload: dict[str, Any],
    max_tokens: int,
    json_mode: bool,
) -> str:
    kwargs: dict[str, Any] = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
            timeout=180,
            **kwargs,
        )
    except Exception:
        if not json_mode:
            raise
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=max_tokens,
            timeout=180,
        )
    return (response.choices[0].message.content or "").strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="qixia,yuniannian", help="Comma-separated: qixia,yuniannian,long")
    parser.add_argument("--review", action="store_true", help="Run adversarial review after one-pass generation")
    parser.add_argument("--dry-run", action="store_true", help="Print request payloads without calling API")
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--json-mode", action="store_true", help="Enable OpenAI-compatible JSON mode if the endpoint handles it well")
    parser.add_argument("--repair", action="store_true", help="Run one repair attempt when one-pass JSON is invalid")
    args = parser.parse_args()

    one_pass_prompt = read_prompt("02_one_pass_scene_generation.md")
    review_prompt = read_prompt("07_adversarial_prompt_review.md")
    repair_prompt = read_prompt("08_json_repair.md")
    case_names = [item.strip() for item in args.cases.split(",") if item.strip()]
    cases = {name: build_case(name) for name in case_names}

    if args.dry_run:
        print(json.dumps({"cases": cases, "prompt_chars": len(one_pass_prompt)}, ensure_ascii=False, indent=2)[:4000])
        return

    api_key, base_url, model, env_path = load_stepfun_env()
    print(f"API base: {base_url}")
    print(f"Model:    {model}")
    print(f"Env:      {env_path}")
    client = OpenAI(api_key=api_key, base_url=base_url)

    out_dir = REPO_DIR / "cache" / "prompt_lab" / datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    for name, payload in cases.items():
        print(f"\n=== case: {name} ===")
        output = call_model(client, model, one_pass_prompt, payload, args.max_tokens, args.json_mode)
        parsed, parse_error = parse_one_pass_json(output, payload)
        if parsed is not None:
            print("[parse] one-pass JSON OK")
        else:
            print(f"[parse] one-pass JSON FAIL: {parse_error}")
            if args.repair:
                repair_payload = {
                    "original_input": payload,
                    "failed_output": output,
                    "parse_error": parse_error,
                }
                repaired = call_model(client, model, repair_prompt, repair_payload, args.max_tokens, args.json_mode)
                repaired_parsed, repair_error = parse_one_pass_json(repaired, payload)
                if repaired_parsed is not None:
                    print("[parse] repaired JSON OK")
                    output = repaired
                else:
                    print(f"[parse] repaired JSON FAIL: {repair_error}")
        print(output[:1200])
        record: dict[str, Any] = {"case": name, "payload": payload, "one_pass_output": output}

        if args.review:
            review_payload = {
                "prompt_name": "02_one_pass_scene_generation.md",
                "test_case": payload,
                "model_output": output,
            }
            review = call_model(client, model, review_prompt, review_payload, args.max_tokens, args.json_mode)
            try:
                json.loads(review)
                print("[parse] review JSON OK")
            except Exception as exc:
                print(f"[parse] review JSON FAIL: {exc}")
            print("\n--- adversarial review ---")
            print(review[:1200])
            record["adversarial_review"] = review

        (out_dir / f"{name}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nSaved: {out_dir}")


if __name__ == "__main__":
    main()
