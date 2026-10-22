"""Agent 事件钩子（blinker 信号）：Hermes hooks 机制的轻量落地。

铁律：信号机制用 blinker（1.9.0，MIT，Python 生态最常用的信号库），
不自建发布订阅。本模块是叶子模块（不 import 其他 agent 子模块），
供 transport / memory / skills / redact / delegate 发信号。

预置信号（命名对齐 Hermes 概念）：
- agent_step_started / agent_step_finished   单步协议进出
- secret_redacted                           脱敏命中（source/kinds）
- memory_written                            记忆增改删（scope/op/tag）
- skill_viewed                              技能被查看（L3 全文）
- delegate_spawned                          子代理派出（task 摘要）
- cron_task_finished                        定时任务执行/注册事件（task_id/ok/op）

接收方：本模块内置审计日志接收器（import 即连接）；测试/其他模块可
自行 connect 自定义接收器（blinker 弱引用：接收器须被强引用持有）。
"""
from __future__ import annotations

from blinker import signal

from ..logging_setup import get_logger

log = get_logger("agent.hooks")

# —— 信号定义（ sender 约定：发信号的模块名或 None ） —— #
agent_step_started = signal("agent-step-started")
agent_step_finished = signal("agent-step-finished")
secret_redacted = signal("secret-redacted")
memory_written = signal("memory-written")
skill_viewed = signal("skill-viewed")
delegate_spawned = signal("delegate-spawned")
cron_task_finished = signal("cron-task-finished")


# —— 内置审计接收器（结构化日志留痕：关键操作可回溯） —— #
# logging 的 extra 禁止覆盖 LogRecord 保留字段（name/msg/module/process 等），
# 统一消毒：命中保留字的键加 h_ 前缀（python-json-logger 原样并入 JSON）。
_RESERVED_LOG_FIELDS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "asctime", "taskName",
})


def _safe_extra(sender, kw: dict) -> dict:
    extra = {"sender": str(sender) if sender is not None else ""}
    for k, v in kw.items():
        extra[("h_" + k) if k in _RESERVED_LOG_FIELDS else k] = v
    return extra


def _audit_step_started(sender, **kw):
    log.info("hook_agent_step_started", extra=_safe_extra(sender, kw))


def _audit_step_finished(sender, **kw):
    log.info("hook_agent_step_finished", extra=_safe_extra(sender, kw))


def _audit_secret_redacted(sender, **kw):
    log.info("hook_secret_redacted", extra=_safe_extra(sender, kw))


def _audit_memory_written(sender, **kw):
    log.info("hook_memory_written", extra=_safe_extra(sender, kw))


def _audit_skill_viewed(sender, **kw):
    log.info("hook_skill_viewed", extra=_safe_extra(sender, kw))


def _audit_delegate_spawned(sender, **kw):
    log.info("hook_delegate_spawned", extra=_safe_extra(sender, kw))


def _audit_cron_task_finished(sender, **kw):
    log.info("hook_cron_task_finished", extra=_safe_extra(sender, kw))


# import 即连接（模块级函数被本模块持有，弱引用不会失效）
agent_step_started.connect(_audit_step_started)
agent_step_finished.connect(_audit_step_finished)
secret_redacted.connect(_audit_secret_redacted)
memory_written.connect(_audit_memory_written)
skill_viewed.connect(_audit_skill_viewed)
delegate_spawned.connect(_audit_delegate_spawned)
cron_task_finished.connect(_audit_cron_task_finished)
