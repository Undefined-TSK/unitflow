"""LLM 接口基类。所有通道（Mock/百炼/Ollama）实现统一契约。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class LLMInterface(ABC):
    name: str = "base"

    @abstractmethod
    def complete(self, prompt: str, system: str = "", *, temperature: float = 0.3) -> str:
        """给定用户 prompt 与系统指令，返回模型生成的文本。"""
        raise NotImplementedError

    def stream(self, prompt: str, system: str = "", *, temperature: float = 0.3):
        """流式生成：迭代产出文本增量（默认实现=整段一次性返回）。

        真实通道（百炼 SSE）覆写为逐段增量；Mock 通道覆写为定长切片，
        使离线环境也能验证「逐字到达」的前端与协议行为。
        """
        yield self.complete(prompt, system=system, temperature=temperature)
