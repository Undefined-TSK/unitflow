"""嵌入向量落盘缓存 —— 额度保护核心（D3：切换前必落）。

问题背景
--------
``rag.py`` 用 ``DashScopeEmbedding`` 实时嵌入，相同文本（重复 ingest / preset 重导 /
重建向量表）会反复调用百炼，**把新额度（v4）烧光**。本模块在 ``DashScopeEmbedding``
前加一层**磁盘缓存**：命中直接返回，未命中才请求百炼，并把结果写回。

设计要点
--------
- 缓存键：``sha1(f"{model_name}\\0{text}")``，按模型隔离（v3/v4 向量空间不同，绝不能混）。
- 存储：SQLite（stdlib，零新增依赖），主键 (model, key)；sqlite 文件锁天然并发安全。
- 接入点：仅替换 ``rag.py`` 的 ``DashScopeEmbedding`` 实例为 ``CachedDashScopeEmbedding``，
  LlamaIndex 的 ``insert_nodes`` / 检索 query 嵌入全部透明走缓存。
- **切模型（v3→v4）后必须清空缓存目录**（维度虽同为 1024，但语义空间不同；
  保留旧 v3 向量会污染 v4 检索）。``clear()`` / CLI 提供清空入口。

注意：本模块**不消耗任何额度**——只有 cache miss 且真跑 ingest 时才触网。
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Iterable, Optional, Sequence

from llama_index.embeddings.dashscope import DashScopeEmbedding

_DEFAULT_DIR = Path(
    os.getenv("PYPEDIA_DATA", str(Path.home() / ".pypedia"))
) / "embed_cache"


class EmbedCache:
    """按 (model, sha1(text)) 落盘向量；sqlite 存储，并发安全。"""

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        self._dir = Path(cache_dir) if cache_dir else _DEFAULT_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._db = self._dir / "embed_cache.db"
        self._conn = sqlite3.connect(str(self._db), check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS cache ("
            "  model TEXT, key TEXT, vec TEXT, ts REAL, "
            "  PRIMARY KEY (model, key))"
        )
        self._conn.commit()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _key(model: str, text: str) -> str:
        return hashlib.sha1(f"{model}\x00{text}".encode("utf-8")).hexdigest()

    def get(self, model: str, text: str) -> Optional[list[float]]:
        row = self._conn.execute(
            "SELECT vec FROM cache WHERE model=? AND key=?",
            (model, self._key(model, text)),
        ).fetchone()
        if row:
            self._hits += 1
            return json.loads(row[0])  # noqa: S301 仅还原本进程写出的向量
        self._misses += 1
        return None

    def mset(self, model: str, pairs: Iterable[tuple[str, list[float]]]) -> None:
        ts = time.time()
        self._conn.executemany(
            "INSERT OR REPLACE INTO cache (model, key, vec, ts) VALUES (?,?,?,?)",
            [(model, self._key(model, t), json.dumps(v), ts) for t, v in pairs],
        )
        self._conn.commit()

    def stats(self) -> dict:
        total = self._hits + self._misses
        rows = self._conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": (self._hits / total) if total else 0.0,
            "rows": rows,
        }

    def clear(self) -> int:
        """清空全部缓存（切 embedding 模型后必须调用）。返回删除行数。"""
        n = self._conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        self._conn.execute("DELETE FROM cache")
        self._conn.commit()
        return n

    def close(self) -> None:
        self._conn.close()


def global_stats() -> dict:
    """跨进程读取持久化缓存库的统计（不依赖运行期连接，零触网）。

    用于「成本 / token 面板」：展示已落盘向量数、按模型分布、以及据此粗略估算
    已为额度节省的嵌入 token（每次命中 = 一次本需重算的百炼嵌入调用）。
    """
    d = Path(os.getenv("EMBED_CACHE_DIR")) if os.getenv("EMBED_CACHE_DIR") else _DEFAULT_DIR
    db = d / "embed_cache.db"
    if not db.exists():
        return {"rows": 0, "by_model": {}, "estimated_saved_tokens": 0,
                "cache_dir": str(d)}
    try:
        conn = sqlite3.connect(str(db))
        rows = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        by_model = {m: n for m, n in conn.execute(
            "SELECT model, COUNT(*) FROM cache GROUP BY model")}
        conn.close()
    except sqlite3.Error:
        return {"rows": 0, "by_model": {}, "estimated_saved_tokens": 0,
                "cache_dir": str(d)}
    # 粗估：每条缓存向量 = 一次本需重算的嵌入；按 ~150 token/片段 估算节省量
    return {"rows": rows, "by_model": by_model,
            "estimated_saved_tokens": rows * 150, "cache_dir": str(d)}


class CachedDashScopeEmbedding(DashScopeEmbedding):
    """在 ``DashScopeEmbedding`` 前加磁盘缓存；miss 才走网络。

    仅替换 rag.py 中的 ``DashScopeEmbedding(...)`` 调用即可，其余代码无感。

    接线点说明（2026-10 实测本仓 llama_index 版本）：
    ``get_text_embeddings``（复数公共方法）在本版本 llama_index **不存在**，
    真正的批量/单条/query 嵌入最终都落在私有 worker
    ``_get_text_embeddings`` / ``_get_text_embedding`` / ``_get_query_embedding``
    （DashScopeEmbedding 定义，公共方法 ``get_text_embedding`` / ``get_query_embedding``
    在无内存缓存时直接委托它们）。故在此三者上加缓存，覆盖 ingest 批量与检索 query。
    """

    def __init__(self, *args, cache: EmbedCache | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._cache = cache or EmbedCache(os.getenv("EMBED_CACHE_DIR"))

    def _model(self) -> str:
        return getattr(self, "model_name", "unknown")

    # 批量入口（ingest 的 insert_nodes 走这里）；命中直接返回，仅嵌入 miss 部分
    def _get_text_embeddings(self, texts: Sequence[str]) -> list[list[float]]:
        model = self._model()
        cached = [self._cache.get(model, t) for t in texts]
        misses = [(i, txt) for i, (txt, c) in enumerate(zip(texts, cached)) if c is None]
        if misses:
            idxs, miss_texts = zip(*misses)
            vecs = super()._get_text_embeddings(list(miss_texts))
            self._cache.mset(model, zip(miss_texts, vecs))
            for i, v in zip(idxs, vecs):
                cached[i] = v
        return [c for c in cached]  # type: ignore[list-item]

    # 单条入口；先查缓存
    def _get_text_embedding(self, text: str) -> list[float]:
        model = self._model()
        hit = self._cache.get(model, text)
        if hit is not None:
            return hit
        vec = super()._get_text_embedding(text)
        self._cache.mset(model, [(text, vec)])
        return vec

    # query 入口：text-embedding 系列 query/doc 同向量空间，复用同一 key
    def _get_query_embedding(self, query: str) -> list[float]:
        return self._get_text_embedding(query)
