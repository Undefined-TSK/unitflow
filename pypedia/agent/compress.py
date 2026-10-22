"""历史压缩：pydantic-ai history processor（Hermes 上下文管理的确定性版）。

机制：Agent(capabilities=[ProcessHistory(compress_history)]) —— 每次模型
请求前对历史做有界化；result.all_messages() 返回的是压缩后的历史 + 新消息，
因此序列化回前端的 state 天然有界（详见 transport 模块 docstring）。

压缩策略（v1 确定性截断，非 LLM 摘要——零额外调用、可测试、行为可预期）：
- 总量（字符数或条数）超预算才动手，否则原样返回；
- 恒保留首条消息（协议冻结的 SystemPromptPart + 首问）；
- 从尾部保留最近的消息直到填满预算（新用户 prompt 必在尾部，
  满足框架「处理后历史须以 ModelRequest 结尾」的约束）；
- 工具轮次完整性：若保留区首条是带 ToolReturnPart 的 ModelRequest，
  必须连带保留其前一条 ModelResponse（ToolCallPart 源头），
  否则 OpenAI 侧 tool_call/tool 配对断裂直接 400；
- 预算取值见 config.AGENT_HISTORY_CHARS / AGENT_HISTORY_MAX_MESSAGES
  （后者须小于 transport.MAX_MESSAGES，为单步新增消息留头）。
"""
from __future__ import annotations

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ToolReturnPart,
)

from ..config import settings
from ..logging_setup import get_logger

log = get_logger("agent.compress")


def _part_text(part) -> str:
    content = getattr(part, "content", None)
    if isinstance(content, str):
        return content
    args = getattr(part, "args", None)
    if args is not None:
        return str(args)
    return ""


def _msg_chars(m: ModelMessage) -> int:
    return sum(len(_part_text(p)) for p in m.parts)


def _has_tool_returns(m: ModelMessage) -> bool:
    return isinstance(m, ModelRequest) and any(
        isinstance(p, ToolReturnPart) for p in m.parts)


def _fits(messages: list[ModelMessage]) -> bool:
    if len(messages) > settings.AGENT_HISTORY_MAX_MESSAGES:
        return False
    return sum(_msg_chars(m) for m in messages) <= settings.AGENT_HISTORY_CHARS


def compress_history(messages: list[ModelMessage]) -> list[ModelMessage]:
    """history processor：有界化历史（不变式见模块 docstring）。"""
    if _fits(messages) or len(messages) <= 2:
        return messages

    budget = settings.AGENT_HISTORY_CHARS
    cap = settings.AGENT_HISTORY_MAX_MESSAGES

    head = messages[0] if isinstance(messages[0], ModelRequest) else None
    keep: list[ModelMessage] = []
    total = _msg_chars(head) if head is not None else 0
    for m in reversed(messages[1:] if head is not None else messages):
        if len(keep) >= cap - (1 if head is not None else 0):
            break
        c = _msg_chars(m)
        if keep and total + c > budget:
            break
        keep.insert(0, m)
        total += c

    # 工具轮次完整性：保留区首条带 ToolReturnPart → 向前连带其 ToolCallPart 源头
    while keep and _has_tool_returns(keep[0]):
        idx = next(i for i, m in enumerate(messages) if m is keep[0])
        if idx == 0:
            break                      # 源头不在保留区（极端预算），放弃连带
        keep.insert(0, messages[idx - 1])

    out = ([head] if head is not None else []) + keep
    dropped = len(messages) - len(out)
    if dropped > 0:
        log.info("history_compressed",
                 extra={"from": len(messages), "to": len(out),
                        "chars": total})
    return out
