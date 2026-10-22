"""检索子包。

级联检索编排（cascade）+ 结果数据模型（sources）。
向量召回/混合检索/精排由 rag.py 基于 LlamaIndex + 百炼承担，不自造检索算法。
"""
from .cascade import CascadeRetriever, CascadeResult, Stage
from .sources import RetrievedChunk, ROLE_LABEL

__all__ = [
    "CascadeRetriever",
    "CascadeResult",
    "Stage",
    "RetrievedChunk",
    "ROLE_LABEL",
]
