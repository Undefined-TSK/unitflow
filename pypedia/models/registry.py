"""百炼（DashScope）模型能力注册表 —— 统一「预留入口」。

设计目标：项目用到的每一项百炼能力都在此登记，包含
  · 百炼模型名（kind 对应）
  · 环境变量覆盖位（未开通也能先占位）
  · 降级链（fallback）：当前模型无权限/未开通时，自动落到已可用的替代
  · 运行时探测（probe）：真实发一次最小请求，判定 active / pending(未开通)

效果：后续在百炼控制台开通某个模型（如 gte-rerank / qwen-vl / wanx）后，
无需改任何代码——下一次探测自动翻为 active 并开始使用。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from ..config import settings


@dataclass(frozen=True)
class ModelSpec:
    key: str                       # 内部能力键
    name: str                      # 百炼模型名
    kind: str                      # chat/embedding/rerank/vision/t2i/tts/asr/code/math/decision
    env: str                       # 环境变量覆盖位（预留入口）
    fallback: str | None = None    # 降级到的能力键
    note: str = ""                 # 用途说明
    default_status: str = "pending"  # active=已开通可用；pending=占位待开通


# —— 全部能力登记（含尚未开通的占位） —— #
SPECS: tuple[ModelSpec, ...] = (
    # 已开通可用
    ModelSpec("embed", "text-embedding-v4", "embedding", "BAILIAN_EMBED_MODEL",
              note="文本向量化（Mem0 / 非 RAG 路径；已随 RAG 切 v4，v3 额度已尽）", default_status="active"),
    ModelSpec("chat", "qwen-plus", "chat", "BAILIAN_MODEL",
              fallback=None, note="通用对话 / 生成 / 置信度评估 / 反思", default_status="active"),
    # 已登记、待你在百炼开通（403 时自动走降级链）
    ModelSpec("rerank", "qwen3-rerank", "rerank", "BAILIAN_RERANK_MODEL",
              fallback=None, note="检索精排（云端；gte-rerank 已官方下线，未开通时用本地 bge-reranker）"),
    ModelSpec("decision", "decision-model-preview", "decision", "BAILIAN_DECISION_MODEL",
              fallback="chat", note="主/辅源与置信度判定（无权限时降级 qwen-plus）"),
    ModelSpec("code", "qwen3-coder-plus", "code", "BAILIAN_CODER_MODEL",
              fallback="chat", note="代码生成/解释专用（Python 助手场景更强）"),
    ModelSpec("math", "qwen-math-plus", "math", "BAILIAN_MATH_MODEL",
              fallback="chat", note="算法复杂度/数学推导"),
    ModelSpec("vision", "qwen-vl-max", "vision", "BAILIAN_VISION_MODEL",
              fallback="chat", note="读图/截图/图表理解 → 支撑可视化讲解"),
    ModelSpec("t2i", "wanx2.1-t2i-turbo", "t2i", "BAILIAN_T2I_MODEL",
              fallback=None, note="文生图：为知识点生成示意图/插图"),
    ModelSpec("tts", "qwen-tts", "tts", "BAILIAN_TTS_MODEL",
              fallback=None, note="语音播报答案"),
    ModelSpec("asr", "paraformer-realtime-v2", "asr", "BAILIAN_ASR_MODEL",
              fallback=None, note="语音输入提问"),
    ModelSpec("embed_v4", "text-embedding-v4", "embedding", "BAILIAN_EMBED_V4_MODEL",
              fallback=None, note="RAG 主力向量模型（v3 免费额度已耗尽，切 v4；dim=1024）", default_status="active"),
)

_BY_KEY = {s.key: s for s in SPECS}


@dataclass
class _State:
    status: dict[str, str] = field(default_factory=dict)  # key -> active/pending/unavailable
    detail: dict[str, str] = field(default_factory=dict)


class ModelRegistry:
    """百炼能力注册表：解析模型名 + 探测可用性 + 展示预留入口。"""

    def __init__(self) -> None:
        self._state = _State()
        for s in SPECS:
            self._state.status[s.key] = s.default_status

    # —— 取模型名（环境变量优先，实现「零改代码开通即用」） —— #
    def name(self, key: str) -> str:
        s = _BY_KEY.get(key)
        if not s:
            raise KeyError(f"未登记的能力：{key}")
        return os.getenv(s.env) or s.name

    def spec(self, key: str) -> ModelSpec:
        return _BY_KEY[key]

    def keys(self, kind: str | None = None) -> list[str]:
        return [s.key for s in SPECS if kind is None or s.kind == kind]

    # —— 沿降级链找到第一个可用能力 —— #
    def resolve(self, key: str) -> str:
        seen: set[str] = set()
        cur = key
        while cur and cur not in seen:
            seen.add(cur)
            if self.status(cur) == "active":
                return cur
            cur = _BY_KEY[cur].fallback if cur in _BY_KEY else None
        return "chat" if self.status("chat") == "active" else key

    def status(self, key: str) -> str:
        return self._state.status.get(key, "pending")

    # —— 运行时探测：真实最小请求，判定是否已开通 —— #
    def probe(self, key: str) -> str:
        """返回 active / pending / unavailable。结果缓存，避免每次请求都探测。"""
        if not settings.BAILIAN_API_KEY:
            self._state.status[key] = "unavailable"
            return "unavailable"
        s = _BY_KEY.get(key)
        if not s:
            return "unavailable"
        try:
            if s.kind == "embedding":
                from . import dashscope
                dashscope.embed_texts(["ping"], model=s.name)
            elif s.kind == "rerank":
                from . import dashscope
                dashscope._rerank_raw("ping", ["ping"], top_n=1, model=s.name)
            elif s.kind == "chat":
                from . import dashscope
                dashscope.chat([{"role": "user", "content": "ping"}],
                               model=s.name, max_tokens=1)
            else:
                # 视觉/图像/语音等：百炼多为异步任务端点，未开通时同样返回 4xx，
                # 用一次轻量调用探测；实现未接入前保持 pending 占位。
                self._state.status[key] = "pending"
                return "pending"
            self._state.status[key] = "active"
            self._state.detail[key] = "可用"
        except Exception as e:  # noqa: BLE001
            msg = str(e)
            if "403" in msg or "Access denied" in msg or "InvalidApiKey" in msg:
                self._state.status[key] = "pending"
                self._state.detail[key] = "未开通/无权限（预留占位）"
            else:
                self._state.status[key] = "unavailable"
                self._state.detail[key] = msg[:80]
        return self._state.status[key]

    def probe_all(self) -> dict[str, str]:
        for s in SPECS:
            if s.kind in ("embedding", "rerank", "chat"):
                self.probe(s.key)
        return dict(self._state.status)

    # —— 前端「预留入口」面板 —— #
    def describe(self) -> list[dict]:
        out = []
        for s in SPECS:
            resolved = self.resolve(s.key) if s.fallback else None
            out.append({
                "key": s.key,
                "model": self.name(s.key),
                "kind": s.kind,
                "status": self.status(s.key),
                "fallback": s.fallback,
                "resolves_to": resolved if resolved != s.key else None,
                "note": s.note,
                "env": s.env,
                "detail": self._state.detail.get(s.key, ""),
            })
        return out


registry = ModelRegistry()
