"""AI 沙箱工具层（pydantic-ai 版）：让大模型完整使用浏览器沙箱（C1）。

架构（服务端 LLM + 浏览器工具执行的 agent 循环）：
    1. 前端 POST /api/agent/step（query 或 state+tool_results）；
    2. 服务端经 BailianModel（百炼单通道）请求模型；模型要调工具 →
       工具函数抛 CallDeferred → 返回 {type:"tool_calls", calls, state}；
    3. 前端在 Pyodide 沙箱执行（run_python / install_package / fetch_url /
       sandbox_status），结果经 {state, tool_results} 回传；
    4. transport 用 DeferredToolResults 回填补跑；模型不再调工具 →
       {type:"final", content, state}，前端按 Markdown 渲染。

铁律合规：
    · 零真实调用可验证——BailianModel 唯一的 LLM 出口是
      models.dashscope.chat_with_tools（测试可打桩），工具执行全在前端；
    · 复用不重造——agent 循环/工具调度/消息序列化/用量限制全部由
      pydantic-ai 框架提供；LLM 通道 / 配额 / 等级提示词复用既有组件；
    · 额度纪律——每步 LLM 调用走 ask_limiter；轮次上限前后端双保险。

包结构：
    bailian_model.py  百炼单通道 ↔ pydantic-ai 协议翻译（自定义 Model）
    build.py          agent 组装 + 系统提示词（复用 engine._build_system）
    browser_tools.py  4 个浏览器外派工具（CallDeferred）
    server_tools.py   服务端内联工具（记忆库 memory_* / 技能库 skill_*）
    transport.py      无状态单步协议（state 序列化 / deferred 往返 / 降级）
    memory.py         持久记忆库（MEMORY.md/USER.md + FTS5 trigram + nudge）
    skills.py         技能库（SKILL.md 三级披露 + Curator 归档）
    redact.py         敏感信息脱敏（detect-secrets 插件集，写前/出口闸门）
    compress.py       历史压缩（ProcessHistory capability，有界化 state）
    hooks.py          事件钩子（blinker 信号 + 审计日志接收器）
    delegate.py       子代理委派（delegate_task 工具，上下文隔离 + 并发有界）
    cron.py           定时自动化（APScheduler + SQLAlchemyJobStore + 站内通知）
"""
from __future__ import annotations

from .build import TOOL_ADDENDUM, build_agent, build_system_prompt
from .browser_tools import BROWSER_TOOLS
from .cron import CronError_, add_task, list_notifications, list_tasks
from .delegate import DELEGATE_TOOLS, delegate_task
from .memory import MemoryError_, memory_store
from .server_tools import SERVER_TOOLS
from .skills import SkillError_, skill_store
from .transport import (
    MAX_CONTENT_CHARS,
    MAX_MESSAGES,
    MAX_TOOL_RESULT_CHARS,
    MAX_TOOL_ROUNDS,
    PER_STEP_REQUEST_LIMIT,
    agent_step,
    dump_state,
    load_state,
)

__all__ = [
    "agent_step", "build_agent", "build_system_prompt", "TOOL_ADDENDUM",
    "BROWSER_TOOLS", "SERVER_TOOLS", "DELEGATE_TOOLS", "delegate_task",
    "dump_state", "load_state",
    "memory_store", "skill_store", "MemoryError_", "SkillError_",
    "CronError_", "add_task", "list_tasks", "list_notifications",
    "MAX_MESSAGES", "MAX_CONTENT_CHARS", "MAX_TOOL_ROUNDS",
    "MAX_TOOL_RESULT_CHARS", "PER_STEP_REQUEST_LIMIT",
]
