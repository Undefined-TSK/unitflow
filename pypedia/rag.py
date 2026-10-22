"""基于 LlamaIndex 的知识检索层（成熟框架，不自造索引/检索算法）。

组件全部为现成轮子：
- 向量化：llama-index-embeddings-dashscope（text-embedding-v4；v3 免费额度已耗尽）
- 向量库：LanceDB（磁盘列存、桌面友好；替代 chromadb，2026-10 调研选型）
- 索引/分块/检索：llama_index.core（VectorStoreIndex / SentenceSplitter / retriever）
- 关键词检索：BM25Retriever（底层 bm25s），tokenizer 用 jieba 中文分词
  （修复项：默认 token_pattern 会把连续中文串当单一 token，中文检索实际失效）
- 精排三级链：百炼 qwen3-rerank（云端，开通即用）→ 本地 bge-reranker →
  向量分数兜底（见 models/dashscope.rerank 与 rerank_local.py）
按角色分表：main / supplement_a / supplement_b 各自独立 table，供级联检索调用。
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import lancedb
from llama_index.core import Document, Settings, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.retrievers import QueryFusionRetriever
from llama_index.core.schema import TextNode
from llama_index.embeddings.dashscope import DashScopeEmbedding

from .embed_cache import CachedDashScopeEmbedding, EmbedCache
from llama_index.llms.openai import OpenAI as LlamaOpenAI
from llama_index.retrievers.bm25 import BM25Retriever
from llama_index.vector_stores.lancedb import LanceDBVectorStore

from .config import settings
from .models.dashscope import CHAT_MODEL, rerank as ds_rerank
from .models.registry import registry
from .textutil import tokens as zh_tokens

DATA_DIR = Path(os.getenv("PYPEDIA_DATA", str(Path.home() / ".pypedia")))
VEC_DIR = DATA_DIR / "vector_lancedb"          # LanceDB 新库目录
LEGACY_VEC_DIR = DATA_DIR / "vector"           # 旧 chromadb 目录（仅用于一次性迁移）
EMBED_MODEL = registry.name("embed_v4")
TABLE_PREFIX = "pypedia_"
ROLES = ("main", "supplement_a", "supplement_b")
# LanceDB 顶层展开列（metadata JSON 之外的同名字段，_nodes 还原节点用）
META_COLUMNS = ("role", "src_id", "source", "title", "url", "freshness", "tags")


def _doc_id(role: str, text: str, source: str) -> str:
    h = hashlib.sha1(f"{role}|{source}|{text}".encode("utf-8")).hexdigest()[:16]
    return f"{role}-{h}"


class KnowledgeIndex:
    def __init__(self, persist_dir: Path | None = None):
        persist_dir = persist_dir or VEC_DIR
        persist_dir.mkdir(parents=True, exist_ok=True)
        self._dir = persist_dir
        self._client = lancedb.connect(str(persist_dir))
        self._embed = CachedDashScopeEmbedding(
            model_name=EMBED_MODEL,
            api_key=settings.BAILIAN_API_KEY or None,
            embed_batch_size=10,
            cache=EmbedCache(settings.EMBED_CACHE_DIR or None),
        )
        Settings.embed_model = self._embed
        self._splitter = SentenceSplitter(chunk_size=512, chunk_overlap=64)
        self._indexes: dict[str, VectorStoreIndex] = {}
        self._bm25: dict[str, list[TextNode]] = {}  # 角色 -> 节点缓存（供 BM25 混合检索）
        # LlamaIndex 的 LLM 抽象也指向百炼（成熟集成）：QueryFusionRetriever 等需要
        Settings.llm = LlamaOpenAI(
            model=CHAT_MODEL,
            api_base=settings.BAILIAN_BASE_URL,
            api_key=settings.BAILIAN_API_KEY or "sk-unconfigured",
            temperature=0.2,
            timeout=120,
            max_retries=2,
        )
        self._migrate_legacy_chroma()

    # —— 旧 chromadb 数据一次性迁移（存量用户无感升级） —— #
    def _migrate_legacy_chroma(self) -> None:
        flag = self._dir / "migrated_from_chroma.flag"
        legacy_db = LEGACY_VEC_DIR / "chroma.sqlite3"
        if flag.exists() or not legacy_db.exists():
            return
        try:
            import chromadb

            old = chromadb.PersistentClient(path=str(LEGACY_VEC_DIR))
            # 旧版只有一个名为 pypedia 的 collection，role 在 metadata 里，按角色分组迁移
            try:
                col = old.get_collection("pypedia")
            except Exception:
                col = None
            if col is None:
                flag.write_text("no legacy collection\n", encoding="utf-8")
                return
            got = col.get(include=["documents", "metadatas"])
            docs_by_role: dict[str, list[Document]] = {r: [] for r in ROLES}
            for t, m in zip(got.get("documents") or [], got.get("metadatas") or []):
                if not t:
                    continue
                m = m or {}
                role = str(m.get("role", "supplement_b"))
                if role not in docs_by_role:
                    role = "supplement_b"
                docs_by_role[role].append(
                    Document(text=t, metadata=m,
                              doc_id=_doc_id(role, t, str(m.get("source", ""))))
                )
            total = 0
            for role, docs in docs_by_role.items():
                if not docs:
                    continue
                nodes = self._splitter.get_nodes_from_documents(docs)
                self._index(role).insert_nodes(nodes)
                self._bm25.pop(role, None)
                total += len(nodes)
            flag.write_text(f"migrated {total} nodes\n", encoding="utf-8")
            print(f"[PyPedia] 已从旧 chromadb 迁移 {total} 个节点到 LanceDB")
        except Exception as e:  # noqa: BLE001
            print(f"[PyPedia] chroma 迁移跳过（不影响使用）：{e}", file=sys.stderr)

    # —— 索引构建（按角色独立 table） —— #
    def _table_name(self, role: str) -> str:
        return TABLE_PREFIX + role

    def _index(self, role: str) -> VectorStoreIndex:
        if role not in self._indexes:
            vs = LanceDBVectorStore(
                uri=str(self._dir), table_name=self._table_name(role), mode="overwrite"
            )
            sc = StorageContext.from_defaults(vector_store=vs)
            self._indexes[role] = VectorStoreIndex.from_vector_store(
                vector_store=vs, storage_context=sc, embed_model=self._embed
            )
        return self._indexes[role]

    def _count(self, role: str) -> int:
        try:
            return self._client.open_table(self._table_name(role)).count_rows()
        except Exception:
            return 0

    def count(self, role: str | None = None) -> int:
        if role:
            return self._count(role)
        return sum(self._count(r) for r in ROLES)

    # —— 写入 —— #
    def add(self, role: str, docs: list[dict]) -> int:
        """docs: [{text, source, title, url, freshness, tags}]。同 src_id 覆盖（upsert）。"""
        if not docs:
            return 0
        # 幂等 upsert：先删该 src_id 的旧行再插入——
        # LanceDB insert 是 append 语义，不去重会导致重复导入同源内容翻倍
        # （业务字段在 metadata struct 里，过滤条件走 metadata.src_id 路径）
        src_ids = {str(d.get("src_id", "")) for d in docs if d.get("src_id")}
        if src_ids:
            try:
                t = self._client.open_table(self._table_name(role))
                for sid in src_ids:
                    t.delete(f"metadata.src_id = '{sid.replace(chr(39), chr(39) * 2)}'")
            except Exception:
                pass  # 表不存在（首次写入）时无需删
        documents = []
        for d in docs:
            meta = {
                "role": role,
                "src_id": d.get("src_id", ""),
                "source": d.get("source", ""),
                "title": d.get("title", ""),
                "url": d.get("url", ""),
                "freshness": float(d.get("freshness", 1.0)),
                "tags": ",".join(d.get("tags", [])),
            }
            documents.append(
                Document(
                    text=d["text"],
                    metadata=meta,
                    doc_id=_doc_id(role, d["text"], d.get("source", "")),
                )
            )
        nodes = self._splitter.get_nodes_from_documents(documents)
        self._index(role).insert_nodes(nodes)
        self._bm25.pop(role, None)  # 失效缓存，下次检索从 LanceDB 还原最新节点
        return len(nodes)

    def delete_source(self, role: str, src_id: str) -> None:
        # 业务字段在 metadata struct 里（顶层只有 id/doc_id/vector/text/metadata 五列）
        try:
            t = self._client.open_table(self._table_name(role))
            t.delete(f"metadata.src_id = '{src_id.replace(chr(39), chr(39) * 2)}'")
        except Exception:
            pass
        self._indexes.pop(role, None)
        self._bm25.pop(role, None)

    # —— BM25 节点缓存（混合检索用；从 LanceDB 还原，跨会话保留） —— #
    def _nodes(self, role: str) -> list[TextNode]:
        if role in self._bm25:
            return self._bm25[role]
        try:
            t = self._client.open_table(self._table_name(role))
            rows = t.to_arrow().to_pylist()
            # metadata 是 struct：只取业务键，剔除 _node_content 等 llama 内部字段
            nodes = []
            for r in rows:
                text = r.get("text")
                if not text:
                    continue
                md = r.get("metadata") or {}
                nodes.append(TextNode(
                    text=text,
                    metadata={k: md.get(k) for k in META_COLUMNS if k in md},
                ))
        except Exception:
            nodes = []
        self._bm25[role] = nodes
        return nodes

    # —— 检索：向量 + BM25(jieba 分词) 混合（RRF 融合）→ 三级精排链 —— #
    def search(self, query: str, role: str | None = None, top_k: int = 5,
               rerank_top: int = 20, use_rerank: bool = True) -> list:
        from .retrieval.sources import RetrievedChunk

        if self.count() == 0:
            return []
        roles = [role] if role else list(ROLES)

        candidates: list[tuple[dict, str, float]] = []
        for r in roles:
            try:
                idx = self._index(r)
                n = self._count(r)
                k = min(rerank_top, max(n, 1))
                vector_ret = idx.as_retriever(similarity_top_k=k)
                nodes = self._nodes(r)
                if nodes:
                    # bm25s 新版把 tokenizer 参数标记为弃用（建议 PyStemmer），
                    # 但中文分词必须用 jieba，此处屏蔽弃用警告保留能力
                    import warnings

                    with warnings.catch_warnings():
                        warnings.filterwarnings("ignore", message=".*tokenizer parameter.*")
                        bm25 = BM25Retriever.from_defaults(
                            nodes=nodes, similarity_top_k=min(k, len(nodes)),
                            tokenizer=zh_tokens,
                        )
                    fused = QueryFusionRetriever(
                        retrievers=[vector_ret, bm25],
                        similarity_top_k=rerank_top, num_queries=1,
                    )
                    hits = fused.retrieve(query)
                else:
                    hits = vector_ret.retrieve(query)
            except Exception:
                continue
            for node in hits:
                meta = node.metadata or {}
                candidates.append(
                    (meta, node.get_content(), float(getattr(node, "score", 0.0) or 0.0))
                )
        if not candidates:
            return []
        # 去重：融合检索中同一节点会同时来自向量路与 BM25 路，按文本归并保留最高分
        dedup: dict[str, tuple[dict, str, float]] = {}
        for meta, text, score in candidates:
            prev = dedup.get(text)
            if prev is None or score > prev[2]:
                dedup[text] = (meta, text, score)
        candidates = list(dedup.values())

        if use_rerank and len(candidates) > 1:
            try:
                rr = ds_rerank(query, [c[1] for c in candidates], top_n=top_k)
                ordered = [candidates[x["index"]] for x in rr]
            except Exception:
                candidates.sort(key=lambda c: -c[2])
                ordered = candidates[:top_k]
        else:
            candidates.sort(key=lambda c: -c[2])
            ordered = candidates[:top_k]

        out = []
        for m, text, score in ordered:
            tags = str(m.get("tags", "")).split(",") if m.get("tags") else []
            out.append(RetrievedChunk(
                role=str(m.get("role", role or "")),
                source=str(m.get("source", "")),
                title=str(m.get("title", "")),
                url=str(m.get("url", "")),
                text=text,
                tags=tags,
                freshness=float(m.get("freshness", 1.0)),
                score=round(float(score), 4),
            ))
        return out


_index_cache = None


def get_index() -> KnowledgeIndex:
    """进程内共享单例，避免多连接实例冲突。"""
    global _index_cache
    if _index_cache is None:
        _index_cache = KnowledgeIndex()
    return _index_cache
