#!/usr/bin/env python3
"""批量版：一次请求处理多条，绕过 API 单账户并发上限。

- BATCH_SIZE: 一次 API 调用处理多少条（默认 10）
- CONCURRENCY: 同时发起多少个 batch 请求（默认 8，阶跃单账户并发 10）
- 单条解析失败会自动 fallback 到单条重试
- 断点续传，输出文件和 build_chat_sft_full.py 共享：data/qixia_chat_train_full.json
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    print("请先安装：pip install openai", file=sys.stderr)
    sys.exit(1)

REPO_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = REPO_DIR / "data" / "qixia_train.json"
OUTPUT_PATH = REPO_DIR / "data" / "qixia_chat_train_full.json"
CHECKPOINT_PATH = REPO_DIR / "data" / "_chat_conversion_full_progress.json"
_candidates = [
    REPO_DIR / ".env",
    REPO_DIR.parent / "extract-dialogue" / ".env",
    REPO_DIR.parent / "extract-dialogue" / ".env.stepfun",
    REPO_DIR / "extract-dialogue" / ".env.stepfun",
]
ENV_PATH = next((p for p in _candidates if p.exists()), _candidates[0])

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "10"))
CONCURRENCY = int(os.environ.get("CONCURRENCY", "8"))
SAMPLE_COUNT = int(os.environ.get("SAMPLE_COUNT", "0"))


def load_env_file(path):
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


env = load_env_file(ENV_PATH)
API_KEY = os.environ.get("STEPFUN_API_KEY") or os.environ.get("CUSTOM_API_KEY") or env.get("STEPFUN_API_KEY") or env.get("CUSTOM_API_KEY")
BASE_URL = os.environ.get("STEPFUN_BASE_URL") or os.environ.get("CUSTOM_BASE_URL") or env.get("STEPFUN_BASE_URL") or env.get("CUSTOM_BASE_URL") or "https://api.stepfun.com/v1"
MODEL = os.environ.get("STEPFUN_MODEL") or os.environ.get("STEPFUN_MODEL_NAME") or os.environ.get("CUSTOM_MODEL_NAME") or env.get("STEPFUN_MODEL") or env.get("STEPFUN_MODEL_NAME") or env.get("CUSTOM_MODEL_NAME") or "step-1.5-flash"

if not API_KEY:
    print(f"ERROR: 没找到 API key。检查 {ENV_PATH}", file=sys.stderr)
    sys.exit(1)

print(f"API base:    {BASE_URL}")
print(f"Model:       {MODEL}")
print(f"Batch size:  {BATCH_SIZE}")
print(f"Concurrency: {CONCURRENCY}")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

SYSTEM_PROMPT = (
    "你是一个 SFT 数据标注员。任务：把小说对话改造成高质量聊天训练数据。\n"
    "你会收到多条样本，每条有 id、上下文、齐夏原台词。\n"
    "为每条生成一个用户问题（自然口语，不要书面，不要提'小说片段'）和齐夏的回答（30~200 字，冷静克制、善于观察、逻辑严密，基于原台词扩展，不加原创设定）。\n"
    "严格只输出一个 JSON 数组，不要 markdown 代码块，不要任何前后说明文字。\n"
    "格式：[{\"id\": 原样本id, \"user\": \"...\", \"qixia\": \"...\"}, ...]\n"
    "数组里的条目数必须和输入完全一致，id 必须原样返回。"
)


def clean_context(context_raw):
    parts = context_raw.split("齐夏：")
    body = "齐夏：".join(parts[:-1]).strip() if len(parts) > 1 else context_raw
    if "下面是《十日终焉》" in body:
        body = body.split("\n\n", 1)[-1].strip()
    return body


def build_user_prompt(batch):
    parts = ["请处理以下样本，返回与输入数量、id 一一对应的 JSON 数组：\n"]
    for idx, item in batch:
        line = item["conversations"][1]["value"]
        context = clean_context(item["conversations"][0]["value"])
        parts.append(f"--- id={idx} ---")
        parts.append(f"上下文：\n{context}")
        parts.append(f"齐夏原台词：{line}\n")
    return "\n".join(parts)


def to_chat_item(idx, parsed):
    return {
        "id": f"qixia-chat-{idx:05d}",
        "system": "你正在扮演《十日终焉》中的齐夏。保持冷静、克制、善于观察和推理，根据对话上下文自然回应。",
        "conversations": [
            {"from": "human", "value": str(parsed["user"]).strip()},
            {"from": "gpt", "value": str(parsed["qixia"]).strip()},
        ],
    }


def call_api(messages):
    last_err = None
    for attempt in range(4):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                temperature=0.6,
                stream=False,
                timeout=120,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            last_err = e
            err_msg = str(e)
            if "429" in err_msg or "rate_limit" in err_msg.lower() or "concurrency" in err_msg.lower():
                wait = 5 + attempt * 5
            else:
                wait = 1 + attempt * 2
            if attempt == 3:
                raise
            time.sleep(wait)
    raise last_err


def convert_single(idx, item):
    line = item["conversations"][1]["value"]
    context = clean_context(item["conversations"][0]["value"])
    user_prompt = (
        f"上下文：\n{context}\n\n齐夏原台词：{line}\n\n"
        '严格只输出 JSON：{"user": "...", "qixia": "..."}'
    )
    try:
        text = call_api([
            {"role": "system", "content": (
                "你是 SFT 数据标注员。生成一个用户问题（口语自然）和齐夏的回答（30~200 字，冷静克制）。"
                "严格只输出 JSON 对象，不要 markdown。"
            )},
            {"role": "user", "content": user_prompt},
        ])
        m = re.search(r"\{[\s\S]+\}", text)
        if not m:
            raise ValueError("no json")
        parsed = json.loads(m.group(0))
        if not parsed.get("user") or not parsed.get("qixia"):
            raise ValueError("missing fields")
        return to_chat_item(idx, parsed)
    except Exception as e:
        print(f"  ❌ #{idx} 单条也失败: {e}")
        return None


def convert_batch(batch):
    user_prompt = build_user_prompt(batch)
    try:
        text = call_api([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ])
        m = re.search(r"\[[\s\S]+\]", text)
        if not m:
            raise ValueError("no json array")
        arr = json.loads(m.group(0))
        if not isinstance(arr, list):
            raise ValueError("not a list")
    except Exception as e:
        print(f"  ⚠️  batch 失败 (size={len(batch)}): {e}，转单条")
        return {idx: convert_single(idx, item) for idx, item in batch}

    by_id = {}
    for entry in arr:
        try:
            eid = int(entry.get("id"))
            if entry.get("user") and entry.get("qixia"):
                by_id[eid] = to_chat_item(eid, entry)
        except Exception:
            continue

    result = {}
    missing = []
    for idx, item in batch:
        if idx in by_id:
            result[idx] = by_id[idx]
        else:
            missing.append((idx, item))

    if missing:
        print(f"  🔧 batch 缺 {len(missing)}/{len(batch)} 条，单条补")
        for idx, item in missing:
            result[idx] = convert_single(idx, item)
    return result


def main():
    done = {}
    if OUTPUT_PATH.exists():
        try:
            for x in json.loads(OUTPUT_PATH.read_text(encoding="utf-8")):
                done[x["id"]] = x
        except Exception:
            pass

    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if SAMPLE_COUNT > 0:
        data = data[:SAMPLE_COUNT]
    total = len(data)

    results = []
    pending = []
    for idx, item in enumerate(data):
        eid = f"qixia-chat-{idx:05d}"
        if eid in done:
            results.append(done[eid])
        else:
            pending.append((idx, item))

    print(f"\n共 {total} 条，已完成 {len(results)}，待处理 {len(pending)}\n")
    if not pending:
        print("没有待处理的样本。")
        return

    batches = [pending[i:i + BATCH_SIZE] for i in range(0, len(pending), BATCH_SIZE)]
    print(f"切成 {len(batches)} 个 batch，每个 {BATCH_SIZE} 条\n")

    lock = threading.Lock()
    last_save_time = [time.time()]

    def save_progress():
        results.sort(key=lambda r: r["id"])
        OUTPUT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futures = {ex.submit(convert_batch, batch): batch for batch in batches}
        for fut in as_completed(futures):
            batch_result = fut.result()
            with lock:
                for chat_item in batch_result.values():
                    if chat_item:
                        results.append(chat_item)
                if time.time() - last_save_time[0] > 20:
                    save_progress()
                    last_save_time[0] = time.time()
                    print(f"  ✅ 已保存 {len(results)}/{total}")

    save_progress()

    print("\n" + "=" * 60)
    print(f"完成！共生成 {len(results)}/{total} 条")
    print(f"输出: {OUTPUT_PATH}")
    print("=" * 60)
