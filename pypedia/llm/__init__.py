"""可插拔 LLM 子包。

真实生成由 pypedia.models.dashscope（百炼，走注册表/预留入口）承担，
无密钥或调用失败时由 MockLLM 兜底（见 engine._complete）。
通道选择由 config.LLM_PROVIDER 决定（bailian | mock | ollama 预留）。
"""
from .base import LLMInterface
from .mock import MockLLM

__all__ = ["LLMInterface", "MockLLM", "provider_name"]


def provider_name() -> str:
    """当前生效的 LLM 通道名（供状态接口展示）。"""
    from ..config import settings

    if settings.LLM_PROVIDER == "bailian" and not settings.BAILIAN_API_KEY:
        return "mock"
    return settings.LLM_PROVIDER
