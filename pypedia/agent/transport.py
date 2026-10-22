"""无状态单步传输协议：state 序列化 + deferred 外派 + 回填补跑。

协议（POST /api/agent/step）：
  首轮   {query, level}        → {type:"tool_calls", calls, state, max_rounds}
                                 或 {type:"final", content, state, provider}
  续轮   {state, tool_results, level}
         tool_results=[{id, result}]（前端执行完浏览器工具的结果）
                              → 同上两种

设计（均经 spike 实证）：
- state = ModelMessagesTypeAdapter 序列化的完整会话（含首轮冻结的
  SystemPromptPart 系统提示词）——前端 opaque 透传，不再手搓 role=tool 消息；
- 系统提示词首轮作为 SystemPromptPart 进历史：实测 Agent.instructions 在
  续跑时不会被序列化恢复（instructions=None 时 instruction_parts 为空），
  放进历史才能随 state 自然往返且内容冻结；
- deferred：浏览器工具抛 CallDeferred → 运行挂起输出 DeferredToolRequests →
  transport 转 {type:"tool_calls", calls}；前端执行后用 DeferredToolResults
  回填续跑，框架负责把结果注入历史并再次请求模型；
- 轮次护栏：历史中累计的 ToolCallPart 轮数达到 MAX_TOOL_ROUNDS 时不再
  请求 LLM，直接给出上限提示（前端同步强制执行，双保险防失控循环）；
- 通道异常（无密钥/网络断）：降级 Mock 直答，provider=mock、degraded=True
  （与旧协议一致，不假装调过工具）。
"""
from __future__ import annotations

import json

from pydantic_ai import AgentRunResult
from pydantic_ai.messages import (
    ModelMessage,
    ModelMessagesTypeAdapter,
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.tools import DeferredToolRequests, DeferredToolResults
from pydantic_ai.usage import UsageLimits
from pydantic_core import ValidationError as PydanticValidationError

from ..config import settings
from ..plugins import plugin_registry
from ..llm.mock import MockLLM
from ..logging_setup import get_logger
from .build import RoutingDecision, _rule_decision, build_agent, build_system_prompt
from .hooks import agent_step_finished, agent_step_started
from .memory import memory_store
from .redact import redact_text

log = get_logger("agent.transport")

# —— 与旧协议一致的上限（state 模式由服务端强制；query 截断上限同 settings） —— #
MAX_MESSAGES = 40            # 序列化状态里的消息条数上限
MAX_CONTENT_CHARS = 20000    # 单条消息内容上限（字符）
MAX_TOOL_ROUNDS = 6          # 浏览器工具执行轮次上限（前后端双保险）
MAX_TOOL_RESULT_CHARS = 4000  # 单个工具结果回喂上限（与前端 OUT_CAP 一致）
PER_STEP_REQUEST_LIMIT = 4   # 单次 HTTP step 内 LLM 调用硬上限（防内联重试失控）


def _clamp_level(level) -> int:
    return max(1, min(5, int(level)))


def dump_state(messages: list[ModelMessage]) -> str:
    """会话状态 → 前端 opaque 字符串。"""
    return ModelMessagesTypeAdapter.dump_json(messages).decode("utf-8")


def load_state(state: str) -> list[ModelMessage]:
    """前端 state → 会话状态；形状/规模非法抛 ValueError（端点转 400）。"""
    if not isinstance(state, str) or not state:
        raise ValueError("state 不能为空")
    try:
        messages = ModelMessagesTypeAdapter.validate_json(state)
    except PydanticValidationError as e:
        raise ValueError(f"state 不是合法的会话序列化数据：{e.errors()[0].get('msg', e)}") from e
    if not isinstance(messages, list) or not messages:
        raise ValueError("state 会话不能为空")
    if len(messages) > MAX_MESSAGES:
        raise ValueError(f"state 消息条数超过上限 {MAX_MESSAGES}")
    for i, m in enumerate(messages):
        if isinstance(m, ModelRequest):
            for p in m.parts:
                text = getattr(p, "content", None)
                if isinstance(text, str) and len(text) > MAX_CONTENT_CHARS:
                    raise ValueError(f"state 第 {i} 条消息超过 {MAX_CONTENT_CHARS} 字符上限")
    return messages


def _count_tool_rounds(messages: list[ModelMessage]) -> int:
    """历史中模型请求工具执行的轮数（每个含 ToolCallPart 的响应算一轮）。"""
    return sum(1 for m in messages if isinstance(m, ModelResponse)
               and any(isinstance(p, ToolCallPart) for p in m.parts))


def _last_user_content(messages: list[ModelMessage]) -> str:
    for m in reversed(messages):
        if isinstance(m, ModelRequest):
            for p in reversed(m.parts):
                if isinstance(p, UserPromptPart) and isinstance(p.content, str):
                    return p.content
    return ""


def _first_user_content(messages: list[ModelMessage]) -> str:
    """历史里的首条用户提问（P5 续轮路由上下文：规则是 (level, query) 的
    确定性函数，用首问重建即得与首轮同一激活集，跨轮工具可见性不漂移）。"""
    for m in messages:
        if isinstance(m, ModelRequest):
            for p in m.parts:
                if isinstance(p, UserPromptPart) and isinstance(p.content, str):
                    return p.content
    return ""


def _pending_call_ids(messages: list[ModelMessage]) -> set[str]:
    """历史中尚未被工具结果回答的 tool_call_id（最后一个模型响应的调用）。"""
    for m in reversed(messages):
        if isinstance(m, ModelResponse):
            return {p.tool_call_id for p in m.parts if isinstance(p, ToolCallPart)}
        if isinstance(m, ModelRequest) and any(
                isinstance(p, ToolReturnPart) for p in m.parts):
            break
    return set()


def _build_deferred_results(tool_results: list, messages: list[ModelMessage]) -> DeferredToolResults:
    """前端回传的 [{id, result}] → DeferredToolResults（id 必须对得上待答调用）。"""
    if not isinstance(tool_results, list) or not tool_results:
        raise ValueError("tool_results 必须是非空列表")
    pending = _pending_call_ids(messages)
    calls: dict[str, str] = {}
    for i, tr in enumerate(tool_results):
        if not isinstance(tr, dict):
            raise ValueError(f"tool_results[{i}] 不是对象")
        cid = tr.get("id")
        result = tr.get("result")
        if not isinstance(cid, str) or not cid:
            raise ValueError(f"tool_results[{i}] 缺少 id")
        if not isinstance(result, str):
            raise ValueError(f"tool_results[{i}].result 必须是字符串")
        if pending and cid not in pending:
            raise ValueError(f"tool_results[{i}].id 与待执行的工具调用不匹配")
        # 脱敏闸门：浏览器工具结果（抓取正文/代码输出）进 LLM 前先过 detect-secrets
        result = redact_text(result, source="tool_result").text
        if len(result) > MAX_TOOL_RESULT_CHARS:
            result = result[:MAX_TOOL_RESULT_CHARS] + "\n…（已截断）"
        calls[cid] = result
    return DeferredToolResults(calls=calls)


def _wrap(result: AgentRunResult, level: int) -> dict:
    """AgentRunResult → 前端协议（tool_calls / final 二式，恒带 state）。"""
    messages = result.all_messages()
    state = dump_state(messages)
    out = result.output
    if isinstance(out, DeferredToolRequests):
        return {
            "type": "tool_calls",
            "calls": [{"id": c.tool_call_id, "name": c.tool_name, "arguments": c.args}
                      for c in out.calls],
            "state": state,
            "max_rounds": MAX_TOOL_ROUNDS,
        }
    content = out if isinstance(out, str) else str(out)
    if not content.strip():
        content = "（模型没有返回内容，请换个问法再试一次。）"
    return {"type": "final", "content": content, "state": state,
            "provider": settings.LLM_PROVIDER}


def _degraded_final(messages: list[ModelMessage]) -> dict:
    """通道不可用：Mock 直答（复用 MockLLM，与旧协议同一兜底）。"""
    text = MockLLM().complete(_last_user_content(messages)[:2000])
    return {"type": "final",
            "content": text + "\n\n（当前为离线演示通道，沙箱工具不可用；"
                    "配置百炼 API Key 后 AI 即可自动运行/装包/抓取。）",
            "provider": "mock", "degraded": True,
            "state": dump_state(messages)}


def _run(history: list[ModelMessage], *, deferred_tool_results=None,
         decision: RoutingDecision | None = None) -> AgentRunResult:
    agent = build_agent(decision=decision)
    return agent.run_sync(
        message_history=history,
        deferred_tool_results=deferred_tool_results,
        usage_limits=UsageLimits(request_limit=PER_STEP_REQUEST_LIMIT),
    )


def agent_step(*, query: str | None = None, state: str | None = None,
               tool_results: list | None = None, level: int = 3) -> dict:
    """单步 agent（协议见模块 docstring）。

    - query 模式（首轮）：服务端构建系统提示词并冻结进历史；
    - state + tool_results 模式（续轮）：反序列化状态、回填工具结果续跑。

    钩子：agent_step_started / agent_step_finished（blinker，audit 接收器留痕）。
    """
    level = _clamp_level(level)
    mode = "query" if query is not None else "state"
    agent_step_started.send("transport", mode=mode, level=level)
    try:
        result = _agent_step_impl(query=query, state=state,
                                  tool_results=tool_results, level=level)
    except Exception:
        agent_step_finished.send("transport", mode=mode, ok=False)
        raise
    agent_step_finished.send("transport", mode=mode, ok=True,
                             type=result.get("type"),
                             degraded=bool(result.get("degraded")))
    return result


def _agent_step_impl(*, query: str | None = None, state: str | None = None,
                     tool_results: list | None = None, level: int = 3) -> dict:
    if (query is None) == (state is None):
        raise ValueError("query 与 state 必须且只能提供一个")

    if query is not None:
        if not query.strip():
            raise ValueError("query 不能为空")
        # 脱敏闸门：用户粘贴的密钥/令牌不进 LLM 上下文（先脱敏后截断）
        query = redact_text(query, source="query").text
        if len(query) > settings.MAX_QUERY_CHARS:
            query = query[: settings.MAX_QUERY_CHARS] + "…（已截断）"
        # nudge：步数计数到期时在系统提示词尾部附记忆整理提醒（P2 记忆库）
        # 门控走插件注册表：.env 部署态 AND 设置页用户态（实时读）
        nudge = memory_store.bump_step() if plugin_registry.is_enabled("agent-memory") else None
        # P5 规则引擎：LLM 调用前解析本轮激活集（deterministic-routing）；
        # 规则引擎关闭时 decision=None，工具/规约回到「启用即可见」（恒等）
        decision = _rule_decision(level, query)
        system = build_system_prompt(level, query, nudge=nudge, decision=decision)
        history: list[ModelMessage] = [
            ModelRequest(parts=[SystemPromptPart(content=system),
                                UserPromptPart(content=query)])]
        deferred = None
    else:
        history = load_state(state)
        if tool_results is None:
            raise ValueError("state 模式必须提供 tool_results")
        if _count_tool_rounds(history) >= MAX_TOOL_ROUNDS:
            # 轮次护栏：不再请求 LLM（前端同步强制执行，此处防 API 直调失控）
            return {"type": "final",
                    "content": "（AI 工具调用轮次已达上限，未能形成最终答案。"
                               "请把问题范围缩小，或稍后再试。）",
                    "state": dump_state(history),
                    "provider": settings.LLM_PROVIDER}
        deferred = _build_deferred_results(tool_results, history)
        # 续轮路由：用历史首问 + 当前等级重建同一激活集（确定性 → 不漂移）
        decision = _rule_decision(level, _first_user_content(history))

    try:
        result = _run(history, deferred_tool_results=deferred, decision=decision)
    except Exception as e:  # noqa: BLE001 —— 通道不可用：降级 Mock 直答（不假装调过工具）
        log.warning("agent_step_fallback_mock",
                    extra={"error": f"{type(e).__name__}: {e}"})
        return _degraded_final(history)
    return _wrap(result, level)
