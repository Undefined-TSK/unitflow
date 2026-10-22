"""级联检索：主站 -> GitHub -> 离线/论坛，逐级收窄，并明确标注主要与补充。

这是 PyPedia 的核心差异化业务逻辑（框架无等价物，故保留自编排）：
  ① 官方主站 + 提问        → role=main          （主要源，权威性最高）
  ② GitHub 源码/文档       → role=supplement_a  （补充A）
  ③ 离线文档 / 论坛        → role=supplement_b  （补充B）

每一级的召回/精排都交给 rag.py（LlamaIndex + 百炼），本模块只做编排与主/辅判定。
"""
from __future__ import annotations

from dataclasses import asdict

from .sources import RetrievedChunk, ROLE_LABEL
from ..rag import get_index


class Stage:
    def __init__(self, name: str, role: str, chunks: list[RetrievedChunk]):
        self.name = name
        self.role = role
        self.role_label = ROLE_LABEL.get(role, role)
        self.chunks = chunks


class CascadeResult:
    def __init__(self, query: str, stages: list[Stage]):
        self.query = query
        self.stages = stages

    @property
    def primary(self) -> list[RetrievedChunk]:
        # 主源 = 第一级（官方主站）
        for s in self.stages:
            if s.role == "main":
                return s.chunks
        return []

    @property
    def supplements(self) -> list[RetrievedChunk]:
        out: list[RetrievedChunk] = []
        for s in self.stages:
            if s.role != "main":
                out.extend(s.chunks)
        return out

    @property
    def all_chunks(self) -> list[RetrievedChunk]:
        out: list[RetrievedChunk] = []
        for s in self.stages:
            out.extend(s.chunks)
        return out

    def to_dict(self) -> dict:
        """转为纯 dict，供 JSON 序列化（API 使用）。"""
        return {
            "query": self.query,
            "stages": [
                {
                    "name": s.name,
                    "role": s.role,
                    "role_label": s.role_label,
                    "chunks": [asdict(c) for c in s.chunks],
                }
                for s in self.stages
            ],
            "primary": [asdict(c) for c in self.primary],
            "supplements": [asdict(c) for c in self.supplements],
        }


class CascadeRetriever:
    """三级级联：先主站，再 GitHub，最后离线/论坛。各阶段按角色在对应向量库召回。"""

    def __init__(self, top_k: int = 3):
        self.top_k = top_k
        self.index = get_index()

    def retrieve(self, query: str, history: list[str] | None = None) -> CascadeResult:
        # 结合多轮上下文扩展查询（取最近一轮用户问题做补充召回）
        expanded = query
        if history:
            expanded = query + " " + " ".join(history[-2:])

        main = self.index.search(expanded, role="main", top_k=self.top_k)
        gh = self.index.search(expanded, role="supplement_a", top_k=self.top_k)
        off = self.index.search(expanded, role="supplement_b", top_k=self.top_k)

        stages = [
            Stage("① 官方主站 + 提问", "main", main),
            Stage("② GitHub 源码/文档", "supplement_a", gh),
            Stage("③ 离线文档/论坛", "supplement_b", off),
        ]
        return CascadeResult(query, stages)
