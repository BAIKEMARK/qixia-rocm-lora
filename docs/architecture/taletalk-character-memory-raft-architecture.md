# TaleTalk Character Memory + RAFT Architecture Spec

Date: 2026-06-29
Status: proposed

## 1. First Principles

TaleTalk is not primarily a LoRA trainer. It is a system that turns a novel into an interactive character.

A convincing novel character must satisfy four properties at the same time:

- Identity: the model consistently behaves as the target character.
- Grounded memory: the model can answer questions about the character's experiences, relationships, and motives using novel evidence.
- Cognitive boundary: the model does not answer with omniscient narrator knowledge when the character should not know it.
- Conversational continuity: the model can handle new user questions and follow-ups, not only replay extracted lines.

This implies a separation of responsibilities:

- The memory store owns novel facts.
- The character profile owns stable persona and speaking rules.
- LoRA owns response style and the learned protocol for using memory.
- The runtime prompt owns current user intent, retrieved memories, and dialogue history.

The core design goal is:

> Facts come from memory, voice comes from the character, and uncertainty is allowed when memory is insufficient.

## 2. Existing System Context

Current TaleTalk already has a useful pipeline:

```text
novel txt
-> extract dialogue jsonl
-> build ShareGPT SFT
-> train LoRA with LLaMA Factory
-> infer with Gradio
```

The project also has a CLI entrypoint (`main.py`) and `config.toml`, so future architecture should extend the existing steps instead of replacing them.

Important existing assets:

- `extract/dialogue_extractor.py` already assigns `chunk_id` and can save chunk text.
- `scripts/build_chat_sft_multiturn.py` already groups dialogue by `chunk_id`.
- `src/*` and `main.py` already define a step-based CLI.
- `notebooks/01_extract.ipynb`, `02_train.ipynb`, and `03_infer.ipynb` remain useful for cloud workflows.

This spec keeps the same high-level steps, but adds a memory layer between extraction and SFT construction, then uses the same memory protocol during inference.

## 3. Non-Goals

The first implementation should not attempt all possible role-play features.

- Do not rely on LoRA to memorize the whole novel.
- Do not build a full GraphRAG system first.
- Do not train on raw single-turn Q/A only.
- Do not expose retrieved text as a normal user message.
- Do not make the character omniscient over the entire novel.
- Do not add agent planning, long-term user memory, voice, image, or game mechanics in this architecture phase.

These can be added later if the core memory/persona loop works.

## 4. Target Architecture

The recommended architecture is:

```text
Novel TXT
  -> Scene Builder
  -> Character Profile Builder
  -> Memory Store
  -> RAFT SFT Builder
  -> LoRA Training
  -> RAG Runtime Inference
```

Runtime path:

```text
User message
  -> query rewrite / retrieval query
  -> retrieve scene memories
  -> filter by character cognitive boundary
  -> assemble role prompt with same protocol used in training
  -> LoRA model generates answer
```

This is the practical blend of three known ideas:

- ChatHaruhi-style role memory: role prompt plus retrieved character memories.
- RAFT-style training: train with relevant documents and distractors.
- RoleRAG-style boundary: retrieve only knowledge appropriate to the character.

## 5. Data Artifacts

Each `run_name` should produce these artifacts.

### 5.1 Character Profile

Path:

```text
data/profiles/{run_name}_profile.json
```

Schema:

```json
{
  "role": "齐夏",
  "aliases": ["齐夏", "阿夏"],
  "novel_title": "十日终焉",
  "identity": "...",
  "core_goals": ["..."],
  "personality": ["冷静", "克制", "善于推理"],
  "speech_style": ["少废话", "警惕", "逻辑优先"],
  "relationships": [
    {
      "name": "余念安",
      "relation": "...",
      "importance": "high",
      "evidence_scene_ids": ["scene_001"]
    }
  ],
  "knowledge_boundary": "Only answer from first-hand experience, heard information, or reasonable inference from retrieved memories.",
  "answer_rules": [
    "Use memory for facts.",
    "Use the character voice for expression.",
    "If memory is insufficient, do not invent specific novel facts.",
    "Stay in first person unless the role naturally would not."
  ]
}
```

The profile should be editable by the user. Automatic generation is useful, but manual correction must be supported because profile mistakes poison every answer.

### 5.2 Scene Memory

Path:

```text
data/memory/{run_name}_scenes.jsonl
```

Schema:

```json
{
  "scene_id": "scene_000123",
  "chunk_id": 42,
  "chapter": "",
  "text": "原文片段或对话片段",
  "summary": "这一段发生了什么",
  "characters": ["齐夏", "余念安"],
  "target_role_present": true,
  "target_role_knows": true,
  "events": ["齐夏发现..."],
  "relations": [
    {"subject": "齐夏", "relation": "在意", "object": "余念安"}
  ],
  "quotes": ["齐夏原话..."],
  "source": {
    "novel_path": "novels/...",
    "start_offset": 0,
    "end_offset": 0
  }
}
```

The initial implementation can build scenes from existing chunks. Later, scenes can be improved with chapter detection, overlap, and entity extraction.

The important field is `target_role_knows`. It prevents the character from using narrator-only knowledge.

### 5.3 Memory Index

Path:

```text
data/memory/{run_name}_bm25.pkl
data/memory/{run_name}_index_meta.json
```

Initial implementation should use BM25 over:

- scene summary
- text
- characters
- events
- quotes

BM25 is a better first step than embeddings for this project because names, aliases, and exact phrases matter heavily in novels. Embeddings and rerankers can be added later.

### 5.4 RAFT SFT Dataset

Path:

```text
data/{run_name}_raft_train.json
data/{run_name}_raft_valid.json
```

Format should remain LLaMA Factory-compatible ShareGPT.

Each training sample should use the same prompt protocol as runtime inference:

```json
{
  "id": "xyj_wukong-raft-000001",
  "conversations": [
    {
      "from": "system",
      "value": "你正在扮演...【角色设定】...【记忆片段】..."
    },
    {
      "from": "human",
      "value": "你为什么要这么做？"
    },
    {
      "from": "gpt",
      "value": "..."
    }
  ],
  "metadata": {
    "oracle_scene_ids": ["scene_001"],
    "distractor_scene_ids": ["scene_050"],
    "sample_type": "grounded_fact"
  }
}
```

If LLaMA Factory ignores `metadata`, keep a sidecar file:

```text
data/{run_name}_raft_train.meta.jsonl
```

## 6. Prompt Protocol

Training and inference must use one shared function to build the system prompt.

Template:

```text
你正在扮演《{novel_title}》中的{role}。

你必须遵守：
1. 如果记忆片段包含答案，优先依据记忆回答。
2. 不要逐字复述记忆片段，要用{role}自己的口吻回答。
3. 如果记忆片段没有答案，不要编造具体小说事实。
4. 始终保持第一人称，除非这个角色在该场景下不会这么说。
5. 不要续写 user/assistant，不要展开新对话。

【角色设定】
{character_profile}

【记忆片段】
{memory_snippets}
```

This protocol is the central contract of the architecture.

If training uses one format and inference uses another, the model will drift. The prompt builder must live in a shared module used by both SFT construction and inference.

## 7. RAFT Dataset Design

Each RAFT sample should contain:

- Oracle memory: a scene that actually supports the answer.
- Retrieved memory: top-k scenes from the retriever.
- Distractor memory: unrelated or weakly related scenes.
- Target answer: role-style answer grounded in the oracle memory.

Recommended sample mix:

- 60-70% grounded fact or relationship questions with oracle memories.
- 15-25% partial-memory questions where the model should answer cautiously.
- 10-15% no-answer questions where the model must refuse to invent facts.
- 10-20% multi-turn follow-ups using previous conversation history.

Recommended question types:

- identity: "你是谁？"
- relationship: "余念安和你是什么关系？"
- event: "当时发生了什么？"
- motivation: "你为什么那样选择？"
- correction: "用户说错事实，角色纠正"
- boundary: "用户问角色不该知道的事"
- casual: "资料无关，但角色仍需自然聊天"

The answer should not include citations by default. Evidence IDs should be stored in metadata for evaluation and debugging.

## 8. Retrieval Design

The first implementation should use hybrid-light retrieval:

```text
query = latest user message + important recent conversation terms
candidate_scenes = BM25(query, scene text + summary + aliases + events)
filtered = keep scenes where target_role_knows is true or policy allows world knowledge
ranked = top_k by score with diversity over chunk_id / chapter
```

Recommended defaults:

- `top_k_memory = 3`
- `max_memory_chars = 1800`
- `max_one_scene_chars = 600`
- `include_quotes = true`
- `prefer_target_present = true`

If BM25 fails on semantic questions, add embedding retrieval later:

```text
final_candidates = union(BM25 top 10, embedding top 10)
rerank to top 3
```

Do not add full GraphRAG until simple scene retrieval has measurable failures.

## 9. Cognitive Boundary Policy

TaleTalk must distinguish three knowledge levels:

- `first_hand`: target role was present or spoke in the scene.
- `heard_or_inferred`: role was told this information or can reasonably infer it.
- `narrator_only`: novel reader knows it, but target role should not.

Runtime policy:

- Prefer `first_hand`.
- Allow `heard_or_inferred` when no first-hand memory exists.
- Exclude `narrator_only` for first-person role answers unless the user asks for out-of-character analysis.

This should be configurable later, but the default role-play mode should not be omniscient.

## 10. Pipeline Changes

### 10.1 New Step: build_memory

Inputs:

- novel txt
- raw dialogue jsonl
- target role aliases

Outputs:

- character profile
- scene memory jsonl
- BM25 index

Implementation should start from existing chunk output. It can improve scene segmentation later.

### 10.2 Modified Step: build_sft

Current behavior:

```text
raw dialogue jsonl -> multi-turn ShareGPT
```

Target behavior:

```text
raw dialogue jsonl + scene memory + profile
-> style ShareGPT + RAFT ShareGPT
```

The system should support a config option:

```toml
sft_mode = "raft"  # options: "style", "raft", "mixed"
```

Recommended default after implementation:

```toml
sft_mode = "mixed"
style_data_ratio = 0.35
raft_data_ratio = 0.65
```

Pure RAFT can over-anchor the model to memory snippets. A mixed dataset preserves open conversation style.

### 10.3 Train Step

Training can remain LLaMA Factory LoRA.

Recommended default changes for RAFT:

- `cutoff_len = 2048` minimum.
- Keep memory snippets compact.
- Avoid stuffing more than three memory snippets into each sample.

### 10.4 Infer Step

Inference must:

- load character profile
- load memory index
- retrieve scene memories for each user message
- build the same system prompt format as training
- preserve normal multi-turn chat history

Conversation history and retrieved memory should be separate. Do not dump the full chat history into the memory store during this phase.

## 11. Notebook and CLI Mapping

Notebook mapping:

- `01_extract.ipynb`: add optional sections for building profile, scenes, memory index, and RAFT SFT.
- `02_train.ipynb`: mostly unchanged, but points to RAFT or mixed dataset.
- `03_infer.ipynb`: adds memory retrieval before generation.

CLI mapping:

```text
extract
build_memory
build_sft
train
infer
```

The CLI should keep checkpoint semantics. `build_memory` and `build_sft` should be independently rerunnable.

## 12. Evaluation

The system should be evaluated with a small fixed test set before comparing models.

Minimum eval set:

- 20 factual questions answerable from target memories.
- 20 relationship questions.
- 20 motivation questions.
- 20 false-premise correction questions.
- 20 no-answer or boundary questions.
- 20 casual role-style questions.

Evaluate five variants:

- base model + prompt only
- LoRA only
- RAG only
- LoRA + RAG
- RAFT LoRA + RAG

Scoring dimensions:

- factual grounding
- role voice
- cognitive boundary
- refusal quality when unknown
- repetition / user-assistant leakage
- response latency

Do not rely only on subjective chat feel. Keep a regression file of questions that previously failed, such as relationship questions around important characters.

## 13. Implementation Phases

### Phase 1: Runtime RAG without retraining

Add character profile, scene memory, BM25 index, and inference-time memory injection.

Purpose:

- validate whether retrieved memories improve factual answers.
- reveal prompt drift before changing training data.

### Phase 2: RAFT SFT generation

Generate mixed style + RAFT ShareGPT data.

Purpose:

- align training and inference prompt formats.
- teach the model to use memory snippets without copying them.

### Phase 3: Cognitive boundary improvement

Add better scene metadata:

- target present
- target heard
- narrator only
- relation triples
- event summaries

Purpose:

- prevent omniscient answers.
- improve role authenticity.

### Phase 4: Optional richer retrieval

Only add this if eval shows BM25 is insufficient:

- embedding retrieval
- reranker
- lightweight entity graph
- GraphRAG-like global relationship summaries

## 14. Configuration Additions

Recommended new `config.toml` fields:

```toml
# memory / RAG
enable_memory = true
memory_backend = "bm25"
top_k_memory = 3
max_memory_chars = 1800
max_one_scene_chars = 600
prefer_target_present = true
exclude_narrator_only = true

# SFT
sft_mode = "mixed"
style_data_ratio = 0.35
raft_data_ratio = 0.65
raft_include_distractors = true
raft_no_answer_ratio = 0.1

# prompt
roleplay_mode = "in_character"  # future: "analysis" can allow omniscient explanations
```

## 15. References

Relevant designs and papers:

- ChatHaruhi: role prompt plus memories extracted from scripts, then retrieved during chat. https://arxiv.org/abs/2308.09597
- ChatHaruhi GitHub: https://github.com/LC1332/Chat-Haruhi-Suzumiya
- RAFT: Retrieval Augmented Fine-Tuning for open-book in-domain QA. https://arxiv.org/abs/2403.10131
- RoleLLM: role profile construction, role-specific knowledge extraction, role prompting, and role-conditioned instruction tuning. https://arxiv.org/abs/2310.00746
- Character-LLM: experience reconstruction for trainable role-playing agents. https://arxiv.org/abs/2310.10158
- RoleRAG: graph-guided retrieval and cognitive boundaries for role-playing. https://arxiv.org/abs/2505.18541
- Anthropic Contextual Retrieval: chunk context improves retrieval quality. https://www.anthropic.com/news/contextual-retrieval
- Microsoft GraphRAG: graph-based RAG for complex relation-heavy corpora. https://github.com/microsoft/graphrag

## 16. Open Decisions

These should be decided before implementation:

- Whether the first memory builder should rely only on existing chunks or also ask an LLM to summarize scenes.
- Whether profile generation should be automatic only, or automatic plus user-editable checkpoint.
- Whether default training should use `mixed` mode immediately or keep `style` as default until RAFT is validated.
- Whether `target_role_knows` should initially be heuristic or LLM-classified.

Recommended defaults:

- Build scenes from existing chunks first.
- Generate profile automatically, then expose it as editable JSON.
- Keep `style` available, but make new architecture examples use `mixed`.
- Start `target_role_knows` with heuristics: target present means true, target absent means unknown/narrator-only unless dialogue explicitly tells the target.
