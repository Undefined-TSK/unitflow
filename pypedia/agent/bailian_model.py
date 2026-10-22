"""BailianModel：把 pydantic-ai 的模型请求翻译成既有百炼单通道调用。

铁律合规（复用不重造）：
- 唯一的 LLM 出口仍是 models.dashscope.chat_with_tools——tenacity 退避重试、
  模型注册表降级链、密钥管理、配额语义全部原样复用，本类只做协议翻译；
- 不装 openai/anthropic 等 provider extra：项目只有百炼一个通道，
  自定义 Model 子类正是为此场景提供的官方扩展点。

协议翻译要点：
- ModelMessage 列表 → OpenAI 兼容 messages（SystemPromptPart → system 消息，
  ToolReturnPart/RetryPromptPart → role=tool，ToolCallPart → assistant.tool_calls）；
- ModelRequestParameters.function_tools → OpenAI tools schema；
- assistant message dict（content/tool_calls）→ TextPart/ToolCallPart；
- 通道异常向上抛（由 transport 决定降级 Mock），本类不做兜底、不吞异常。
"""
from __future__ import annotations

import json

from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelResponsePart,  # noqa: F401 —— 类型再导出，便于测试构造
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.profiles import ModelProfile
from pydantic_ai.settings import ModelSettings
from pydantic_ai.tools import ToolDefinition

from ..models.dashscope import chat_with_tools
from ..models.registry import registry
from ..logging_setup import get_logger

log = get_logger("agent.model")


def _to_openai_messages(messages: list[ModelMessage]) -> list[dict]:
    """pydantic-ai 消息 → OpenAI 兼容 messages（喂既有 chat_with_tools）。"""
    out: list[dict] = []
    for m in messages:
        if isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, SystemPromptPart):
                    out.append({"role": "system", "content": p.content})
                elif isinstance(p, UserPromptPart):
                    out.append({"role": "user", "content": p.content})
                elif isinstance(p, ToolReturnPart):
                    # pydantic-ai 2.x：content 可能是多模态列表，取文本部分
                    out.append({"role": "tool", "tool_call_id": p.tool_call_id,
                                "content": _flatten_content(p.content)})
                elif isinstance(p, RetryPromptPart):
                    out.append({"role": "tool", "tool_call_id": p.tool_call_id,
                                "content": _flatten_content(p.content)})
        elif isinstance(m, ModelResponse):
            tool_calls = [p for p in m.parts if isinstance(p, ToolCallPart)]
            text = "".join(p.content for p in m.parts if isinstance(p, TextPart))
            if tool_calls:
                out.append({"role": "assistant", "content": text,
                            "tool_calls": [
                                {"id": tc.tool_call_id, "type": "function",
                                 "function": {"name": tc.tool_name,
                                              "arguments": json.dumps(
                                                  tc.args, ensure_ascii=False)}}
                                for tc in tool_calls]})
            elif text:
                out.append({"role": "assistant", "content": text})
    return out


def _flatten_content(content) -> str:
    """ToolReturnPart.content 可能是 str 或多模态 part 列表：统一取文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = [getattr(p, "text", "") for p in content]
        return "\n".join(t for t in texts if t)
    return str(content)


def _to_openai_tools(tools: list[ToolDefinition]) -> list[dict]:
    return [{"type": "function",
             "function": {"name": t.name, "description": t.description,
                          "parameters": t.parameters_json_schema}}
            for t in tools]


def _from_openai_message(msg: dict) -> list:
    """assistant message dict → ModelResponsePart 列表。"""
    parts: list = []
    if msg.get("content"):
        parts.append(TextPart(content=msg["content"]))
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        raw = fn.get("arguments")
        if isinstance(raw, str):
            try:
                args = json.loads(raw or "{}")
            except json.JSONDecodeError:
                args = {}
        elif isinstance(raw, dict):
            args = raw
        else:
            args = {}
        parts.append(ToolCallPart(tool_name=str(fn.get("name") or ""),
                                  args=args, tool_call_id=str(tc.get("id") or "")))
    return parts


class BailianModel(Model):
    """自定义 Model：pydantic-ai ↔ 百炼兼容模式（OpenAI 协议）双向翻译。

    - request() 为唯一入口：同步的 chat_with_tools 经 run_in_executor 下沉，
      不阻塞事件循环（agent 在同步端点内经 run_sync 驱动，本方法仍在
      anyio worker 线程中执行）；
    - supported_tool_deferral_modes 声明 standalone：工具可抛 CallDeferred
      外派到浏览器执行（本项目的核心架构前提）。
    """

    supported_tool_deferral_modes = frozenset({"standalone"})

    def __init__(self, chat_fn=None, model_name: str | None = None) -> None:
        super().__init__(profile=ModelProfile(supports_json_schema_output=True))
        self._chat_fn = chat_fn
        self._model_name = model_name or f"bailian:{registry.name('chat')}"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def system(self) -> str:
        return "bailian"

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        model_settings, model_request_parameters = self.prepare_request(
            model_settings, model_request_parameters)
        chat = self._chat_fn or chat_with_tools  # 模块全局：测试可 monkeypatch
        oai_messages = _to_openai_messages(messages)
        oai_tools = _to_openai_tools(model_request_parameters.function_tools)
        kwargs: dict = {}
        if model_settings is not None:
            if model_settings.get("temperature") is not None:
                kwargs["temperature"] = model_settings["temperature"]
            if model_settings.get("max_tokens") is not None:
                kwargs["max_tokens"] = model_settings["max_tokens"]
        msg = chat(oai_messages, oai_tools, **kwargs)
        parts = _from_openai_message(msg)
        return ModelResponse(parts=parts, model_name=self._model_name)
