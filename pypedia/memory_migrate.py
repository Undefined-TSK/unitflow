"""Mem0 向量库一次性迁移：chroma（旧） → qdrant 本地模式（新）。

背景：2026-10 架构统一——向量库收敛为「零服务嵌入式」：RAG 用 LanceDB，
记忆层用 qdrant 本地模式（mem0ai 硬依赖自带 qdrant-client，零新增依赖）。
旧版 chroma 记忆数据目录 <数据目录>/mem0_chroma 保留不删，迁移确认无误后可手动清理。

用法：
    python3.11 -m pypedia.cli memory-migrate

特性：
- 幂等：无旧目录 / 新库已有记忆 / 缺 API Key 时安全跳过或报错，不重复写入；
- 保真：infer=False 原文直存，不再走 LLM 抽取（一次性迁移，零额外 LLM 成本）；
- chromadb 未安装时给出可操作提示（而非堆栈）。
"""
from __future__ import annotations

import os

from mem0 import Memory

from .config import settings
from .memory_store import COLLECTION, DATA_DIR, DEFAULT_USER, _embedder_config, _llm_config

CHROMA_DIR = DATA_DIR / "mem0_chroma"
QDRANT_DIR = DATA_DIR / "mem0_qdrant"


def _old_config() -> dict:
    """旧版配置：chroma 持久化（仅供读取迁移）。"""
    return {
        "version": "v1.1",
        "llm": _llm_config(),
        "embedder": _embedder_config(),
        "vector_store": {
            "provider": "chroma",
            "config": {"collection_name": COLLECTION, "path": str(CHROMA_DIR)},
        },
    }


def _new_config() -> dict:
    """新版配置：qdrant 本地模式（与 memory_store._mem0_config 一致）。"""
    return {
        "version": "v1.1",
        "llm": _llm_config(),
        "embedder": _embedder_config(),
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": COLLECTION,
                "path": str(QDRANT_DIR),
                "embedding_model_dims": int(os.getenv("BAILIAN_EMBED_DIMS", "1024")),
                "on_disk": True,
            },
        },
    }


def _items(res) -> list:
    """mem0 get_all 返回值兼容 dict/results 与裸列表两种形状。"""
    if isinstance(res, dict):
        return res.get("results", []) or []
    return res or []


def migrate(user_id: str = DEFAULT_USER) -> dict:
    """执行迁移。返回 {status: ok|skipped|error, migrated, total, detail}。"""
    if not CHROMA_DIR.exists():
        return {"status": "skipped", "migrated": 0, "total": 0,
                "detail": f"无旧版 chroma 数据目录（{CHROMA_DIR}），无需迁移"}
    if not settings.BAILIAN_API_KEY:
        return {"status": "error", "migrated": 0, "total": 0,
                "detail": "未配置百炼 API Key，无法完成向量化迁移（.env 配置后重试）"}

    try:
        old = Memory.from_config(_old_config())
    except ImportError:
        return {"status": "error", "migrated": 0, "total": 0,
                "detail": ("chromadb 未安装，无法读取旧版数据。"
                           "如仍需迁移：pip install chromadb 后重试；"
                           f"旧数据目录 {CHROMA_DIR} 会一直保留")}
    new = Memory.from_config(_new_config())

    existing = _items(new.get_all(filters={"user_id": user_id}))
    if existing:
        return {"status": "skipped", "migrated": 0, "total": len(existing),
                "detail": f"新库已有 {len(existing)} 条记忆（疑似已迁移），跳过以避免重复"}

    memories = _items(old.get_all(filters={"user_id": user_id}))
    migrated = 0
    for m in memories:
        text = (m.get("memory", "") if isinstance(m, dict) else str(m)) or ""
        if not text.strip():
            continue
        # infer=False：原文直存——迁移保真，且不产生额外 LLM 调用
        new.add(messages=[{"role": "user", "content": text}],
                user_id=user_id, infer=False)
        migrated += 1
    return {"status": "ok", "migrated": migrated, "total": len(memories),
            "detail": (f"已迁移 {migrated}/{len(memories)} 条记忆到 qdrant 本地库"
                       f"（{QDRANT_DIR}）；旧目录 {CHROMA_DIR} 保留，确认无误后可手动删除")}
