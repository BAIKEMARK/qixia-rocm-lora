from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .memory import CharacterProfile, read_profile
from .memory_pack import retrieve_memory_items
from .prompting import build_roleplay_system_prompt_from_memory_pack
from .retrieval import BM25MemoryIndex
from .semantic_retrieval import SemanticMemoryIndex, rerank_items


@dataclass
class RuntimeMemory:
    profile: CharacterProfile
    index: BM25MemoryIndex
    semantic_index: SemanticMemoryIndex | None = None


def load_runtime_memory(config: Config) -> RuntimeMemory | None:
    if not config.enable_memory:
        return None
    if not config.profile_json.exists() or not config.memory_index_json.exists():
        return None
    index = BM25MemoryIndex.load(config.memory_index_json)
    semantic_index = None
    if config.retrieval_mode in {"embedding", "semantic", "hybrid"} and config.embedding_npy.exists():
        semantic_index = SemanticMemoryIndex.from_artifacts(index.scenes, config.embedding_npy, config)
    return RuntimeMemory(profile=read_profile(config.profile_json), index=index, semantic_index=semantic_index)


def build_runtime_system_prompt(config: Config, memory: RuntimeMemory | None, user_message: str) -> str:
    if memory is None:
        return (
            f"你正在扮演《{config.novel_title}》中的{config.canonical_role}。"
            f"严格保持{config.canonical_role}的语气、性格、说话习惯和价值观，"
            "根据对话上下文自然回应，不要跳出角色，不要续写其他角色的发言。"
        )
    items = retrieve_memory_items(
        user_message,
        memory.index,
        excluded_scene_ids=[],
        max_one_scene_chars=config.max_one_scene_chars,
        retrieval_mode=config.retrieval_mode,
        bm25_top_k=config.bm25_top_k,
        embedding_top_k=config.embedding_top_k,
        rerank_top_k=config.top_k_memory,
        semantic_index=memory.semantic_index,
        rerank_fn=lambda query, rows, top_k: rerank_items(config, query, rows, top_k),
    )
    return build_roleplay_system_prompt_from_memory_pack(
        memory.profile,
        items,
        max_memory_chars=config.max_memory_chars,
    )
