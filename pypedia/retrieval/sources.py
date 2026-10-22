"""检索结果数据模型 + 角色标签（主要 / 补充A / 补充B）。

说明（遵循「零自造轮子」）：
- 本文件只保留**数据模型与角色定义**，不含任何检索算法。
- 关键词/向量混合召回与精排全部由 rag.py 基于 LlamaIndex（BM25Retriever +
  VectorStoreIndex）+ 百炼 gte-rerank 承担——不再手写分词器与关键词检索。
- 网页正文抽取由 ingest.py 用成熟库 trafilatura 承担。
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 角色 -> 中文标签（主要 / 补充A / 补充B）
ROLE_LABEL = {
    "main": "主要（官方主站）",
    "supplement_a": "补充A（GitHub 源码/文档）",
    "supplement_b": "补充B（离线文档/论坛）",
}


@dataclass
class RetrievedChunk:
    role: str
    source: str          # 来源名（文档/仓库/书名/论坛）
    title: str
    url: str
    text: str
    tags: list[str] = field(default_factory=list)
    freshness: float = 1.0
    score: float = 0.0   # 0~1 相关度（向量分数或精排分数）
