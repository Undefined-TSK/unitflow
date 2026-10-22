"""本地重排模型（BAAI/bge-reranker，sentence-transformers CrossEncoder）。

调研结论（2026-10）：
- 百炼 gte-rerank 已于 2026-05-30 官方下线；继任者 qwen3-rerank 需账号开通；
- qwen-plus LLM 兼职重排 NDCG@10 仅 ~0.70 且每次灌 20+ chunk，费用最高；
- 专用 cross-encoder（bge-reranker）NDCG 0.85+、CPU 200-420ms、零边际成本、离线可用。

设计（桌面场景）：
- 懒加载：首次使用时才加载/下载模型（~1.1GB），不拖慢启动；
- 下载走 HF 国内镜像（settings.HF_ENDPOINT），后台线程 + 状态可查询；
- 未就绪时上层自动降级到向量分数排序，功能不中断。
"""
from __future__ import annotations

import os
import threading

from .config import settings
from .plugins import plugin_registry


class LocalReranker:
    """bge-reranker 单例：ready / downloading / failed / disabled 四态。"""

    def __init__(self) -> None:
        self._model = None
        self._status = "idle"  # idle|downloading|ready|failed|disabled
        self._error = ""
        self._lock = threading.Lock()

    # —— 状态（供能力面板展示） —— #
    def status(self) -> str:
        if not plugin_registry.is_enabled("local-rerank"):
            return "disabled"
        return self._status

    def detail(self) -> str:
        return self._error or {
            "idle": "尚未使用（首次检索时加载）",
            "downloading": "模型下载/加载中（约 1.1GB，仅首次）",
            "ready": "已就绪（本地推理，离线可用）",
            "failed": "加载失败，已降级向量分数排序",
            "disabled": "已在配置中关闭",
        }.get(self._status, self._status)

    def model_name(self) -> str:
        return settings.RERANK_LOCAL_MODEL

    # —— 确保就绪（懒加载；下载中返回 None 让上层降级） —— #
    def _ensure(self):
        if self._status in ("ready", "disabled", "downloading"):
            return self._model if self._status == "ready" else None
        if not plugin_registry.is_enabled("local-rerank"):
            self._status = "disabled"
            return None
        with self._lock:
            if self._status == "ready":
                return self._model
            if self._status == "downloading":
                return None
            self._status = "downloading"
        try:
            # HuggingFace 国内镜像（模型下载源），可用环境变量覆盖
            os.environ.setdefault("HF_ENDPOINT", settings.HF_ENDPOINT)
            from sentence_transformers import CrossEncoder

            self._model = CrossEncoder(
                settings.RERANK_LOCAL_MODEL, max_length=512
            )
            self._status = "ready"
            self._error = ""
        except Exception as e:  # noqa: BLE001
            self._status = "failed"
            self._error = f"{type(e).__name__}: {e}"[:120]
        return self._model if self._status == "ready" else None

    def ensure_async(self) -> None:
        """后台预热（应用启动时调用，不阻塞）。"""
        if self._status in ("idle", "failed"):
            threading.Thread(target=self._ensure, daemon=True).start()

    # —— 重排：输入 (query, docs) → 按相关性降序的 [{index, relevance_score}] —— #
    def rank(self, query: str, documents: list[str]) -> list[dict] | None:
        """返回按相关性降序的 [{index, relevance_score}]；不可用时返回 None（上层降级）。"""
        if not documents:
            return []
        model = self._ensure()
        if model is None:
            return None
        try:
            scores = model.predict([[query, d] for d in documents])
            scored = sorted(
                ({"index": i, "relevance_score": round(float(s), 4)}
                 for i, s in enumerate(scores)),
                key=lambda x: -x["relevance_score"],
            )
            return scored
        except Exception:  # noqa: BLE001
            return None


reranker = LocalReranker()
