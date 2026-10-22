"""子代理委派：delegate_task 工具（Hermes 多代理的轻量落地）。

设计（铁律：框架能力用尽，不重造）：
- 子代理 = 同一 BailianModel 通道 + 一个新 Agent 实例（pydantic-ai 原生
  多 agent 组合：工具内 await 另一个 agent.run），上下文与主代理完全隔离
  （子代理的探索过程不进主历史，只有结论回流——上下文隔离正是委派的价值）；
- 子代理工具集 = SERVER_TOOLS（memory/skills 查证），**不含**浏览器外派
  工具与 delegate_task 本身：无嵌套委派 → 扇出有界，无 CallDeferred 跨层
  外派（deferred 外派语义跨 agent 层会破坏主循环的挂起/续跑协议）；
- 并发上限 AGENT_DELEGATE_MAX（默认 3）：单事件循环线程内计数，超限时
  工具返回提示文本让模型改走「自行完成」分支，不抛异常打断主循环；
- 子代理运行有界：UsageLimits 限制请求数 + move_on_after 限时，
  失败/超时返回错误文本（同样不打断主循环）。
"""
from __future__ import annotations

import anyio

from pydantic_ai import Agent
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.tools import DeferredToolRequests
from pydantic_ai.usage import UsageLimits

from ..config import settings
from ..logging_setup import get_logger
from ..plugins import plugin_registry
from .bailian_model import BailianModel
from .compress import compress_history
from .hooks import delegate_spawned

log = get_logger("agent.delegate")

_SUB_TIMEOUT = 180          # 单个子代理运行墙钟上限（秒）
_TASK_PREVIEW = 80          # 钩子/日志里任务摘要长度

# 并发在飞子代理数（工具在父 run 的同一事件循环内串行自增/递减，无需锁）
_inflight = 0

_SUB_SYSTEM_PROMPT = """你是子代理（sub-agent），由主代理委派处理一个独立的子任务。
规则：
· 只聚焦被委派的任务，不展开无关内容，不向用户提问；
· 可用 memory_search 查证既有记忆、skill_list / skill_view 查阅技能指令；
· 不要把未经证实的推测写进记忆；确属稳定事实才 memory_add；
· 完成后直接用 Markdown 给出结论本身，不要复述任务、不要客套。"""


def _build_sub_agent() -> Agent:
    """子代理：服务端工具 + 压缩能力；输出纯文本（无 deferred 外派）。

    工具集走插件注册表且 include_delegate=False：禁嵌套委派保留——
    子代理只拿 memory/skills 查证工具（同样受设置页开关控制）。
    """
    return Agent(
        BailianModel(),
        tools=plugin_registry.enabled_agent_tools(include_delegate=False),
        system_prompt=_SUB_SYSTEM_PROMPT,
        output_type=[str, DeferredToolRequests],  # 工具集不含 deferred 工具时等价 str
        capabilities=[ProcessHistory(compress_history)],
    )


async def delegate_task(task: str, context: str = "") -> str:
    """把子任务委派给一个上下文隔离的子代理，返回其结论文本。

    Args:
        task: 子任务描述（自包含：目标 + 约束 + 期望产出）。
        context: 可选的背景信息（主代理已知的相关事实）。
    """
    global _inflight
    task = (task or "").strip()
    if not task:
        return "参数错误：task 不能为空"
    if not plugin_registry.is_enabled("agent-delegate"):
        return "子代理委派已在配置/设置中关闭（AGENT_DELEGATE_ENABLE=false 或插件面板）"
    if _inflight >= settings.AGENT_DELEGATE_MAX:
        return (f"并发子代理数已达上限（{settings.AGENT_DELEGATE_MAX}），"
                "请在当前上下文内自行完成该子任务。")

    prompt = f"【子任务】{task}"
    if context and context.strip():
        prompt += f"\n\n【背景】{context.strip()[:4000]}"

    _inflight += 1
    delegate_spawned.send(None, task=task[:_TASK_PREVIEW],
                          inflight=_inflight)
    try:
        agent = _build_sub_agent()
        with anyio.move_on_after(_SUB_TIMEOUT) as scope:
            result = await agent.run(
                prompt,
                usage_limits=UsageLimits(
                    request_limit=settings.AGENT_SUB_MAX_REQUESTS),
            )
        if scope.cancelled_caught:
            log.warning("delegate_timeout",
                        extra={"task": task[:_TASK_PREVIEW],
                               "timeout": _SUB_TIMEOUT})
            return f"（子代理执行超时（>{_SUB_TIMEOUT}s），未形成结论；请自行完成或缩小子任务。）"
        out = result.output
        text = out if isinstance(out, str) else str(out)
        return text.strip() or "（子代理未返回内容）"
    except Exception as e:  # noqa: BLE001 —— 子代理失败不打断主循环，回文本让模型续走
        log.warning("delegate_failed",
                    extra={"task": task[:_TASK_PREVIEW],
                           "error": f"{type(e).__name__}: {e}"})
        return f"（子代理执行失败：{type(e).__name__}。请自行完成该子任务。）"
    finally:
        _inflight -= 1


DELEGATE_TOOLS = [delegate_task]
