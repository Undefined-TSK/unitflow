"""Mock LLM：离线、确定性、零依赖。用于无密钥/无网络时端到端跑通与演示。"""
from __future__ import annotations

from .base import LLMInterface


class MockLLM(LLMInterface):
    name = "mock"

    def complete(self, prompt: str, system: str = "", *, temperature: float = 0.3) -> str:
        # 从 system 中解析出角色定义与等级，从 prompt 中提取证据，拼出结构化答案。
        level = _extract_level(system)
        role_block = _extract_block(system, "【角色与主要/补充】")
        evidence = _extract_evidence(prompt)

        answer = (
            f"（Mock 模式 · {level}）\n\n"
            f"根据你的问题，我优先采用**主源**的权威说法，并以补充源佐证：\n\n"
        )
        for i, e in enumerate(evidence, 1):
            answer += f"{i}. {e}\n"
        answer += (
            "\n> 说明：这是离线 Mock 生成的答案，用于演示级联检索→置信度→等级适配的完整链路。"
            "配置百炼/Ollama 密钥后将由真实模型生成通俗、可视化、可直接运行的讲解。\n"
        )
        if role_block:
            answer += f"\n角色约定：{role_block}\n"
        return answer

    def stream(self, prompt: str, system: str = "", *, temperature: float = 0.3):
        """定长切片逐段产出（模拟流式通道），拼接结果与 complete 完全一致。"""
        text = self.complete(prompt, system=system, temperature=temperature)
        step = 8
        for i in range(0, len(text), step):
            yield text[i:i + step]


def _extract_level(system: str) -> str:
    import re

    m = re.search(r"等级：?(L\d)", system)
    return m.group(1) if m else "L3"


def _extract_block(system: str, marker: str) -> str:
    if marker in system:
        return system.split(marker, 1)[1].split("【", 1)[0].strip()
    return ""


def _extract_evidence(prompt: str) -> list[str]:
    # 证据以「证据 N」标记，真实引擎会替换为检索片段
    out = []
    for line in prompt.splitlines():
        line = line.strip()
        if line.startswith("证据"):
            out.append(line.split("：", 1)[-1].strip())
    return out[:5] or ["（未检索到相关证据，请检查查询或知识源）"]
