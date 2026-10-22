"""模型适配层：统一封装百炼（DashScope）现成模型服务。

对外暴露：
  embed_texts / embed_one   —— 向量模型（text-embedding-v4）
  rerank                    —— 重排模型（gte-rerank）
  chat                      —— 通义千问大模型（qwen-plus 等）
  evaluate_confidence       —— 置信度评估（qwen-plus）
"""
from .dashscope import (
    chat,
    embed_one,
    embed_texts,
    evaluate_confidence,
    rerank,
)

__all__ = [
    "chat",
    "embed_texts",
    "embed_one",
    "rerank",
    "evaluate_confidence",
]
