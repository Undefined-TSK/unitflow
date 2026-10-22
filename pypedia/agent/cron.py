"""Hermes 式 cron 定时自动化：APScheduler + SQLAlchemyJobStore + 站内通知。

设计（对应 Hermes「定时任务」特性，全部本地、零外部服务）：
- 调度用 APScheduler 3.x（MIT，Python 生态标准调度库），不自建触发器；
- 任务定义随 job 一起存 SQLAlchemyJobStore（sqlite，数据目录 cron.db）：
  func 恒为本模块的 _execute_task（模块级函数可 pickle），任务细节走
  job.kwargs["task"]（纯 dict），重启后自动恢复、无需双写第二份存储；
- 三类触发：cron（5 段 crontab，本地时区）/ interval（秒/分/时/天）/
  once（ISO 时间，naive 视为本地时区）；
- 两类任务：builtin（调用注册的纯函数，如 Curator 归档冷技能）与
  agent（定时跑一次 agent_step，产出经脱敏后发站内通知）；
- preflight：任务定义先校验后注册（表达式/时间/参数），非法定义直接
  CronError_ 拒绝——不注册、不触发、不发 LLM 调用；
- 站内通知：执行结果进内存通知队列（有界 deque），GET /api/agent/cron
  一并发回，前端设置页面板展示；cron_task_finished 信号供审计。

铁律：调度/持久化/触发全部 APScheduler 现成能力；LLM 出口仍只有
bailian_model（测试可打桩）；通知文本过 redact 闸门。
"""
from __future__ import annotations

import os
import re
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime

from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger
from tzlocal import get_localzone

from ..config import settings
from ..logging_setup import get_logger
from .hooks import cron_task_finished
from .redact import redact_text

log = get_logger("agent.cron")

_TASK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_NAME_MAX = 50
_MISFIRE_GRACE = 300          # 触发后 5 分钟内捡起有效，过期记 missed
_NOTIFY_MAX = 50              # 站内通知保留条数（内存有界）
_RUN_WAIT = 10.0              # run_task 同步等待执行落地的秒数上限
_AGENT_LEVEL_DEFAULT = 2      # cron 的 agent 任务默认等级（与 /api/agent/step 一致）
_CRON_SEGMENTS = 5            # 标准 crontab：分 时 日 月 周

_KINDS = ("builtin", "agent")
_SCHEDULE_TYPES = ("cron", "interval", "once")
_INTERVAL_UNITS = ("seconds", "minutes", "hours", "days")


class CronError_(ValueError):
    """定时任务定义/操作失败（preflight/上限），端点层转 400。"""


class TaskNotFound(CronError_):
    """任务 id 不存在（pause/resume/run/remove），端点层转 404。"""


# ---------- 内置任务（纯函数 runner，执行时惰性 import 避免导入环） ---------- #
def _run_archive_stale_skills() -> dict:
    """Curator：把超 AGENT_SKILL_ARCHIVE_DAYS 天未使用的技能移入归档区。"""
    from . import skills

    archived = skills.skill_store.archive_stale()
    return {"archived": archived}


# key → {"name": 展示名, "runner": () -> dict}
BUILTIN_TASKS = {
    "archive_stale_skills": {
        "name": "归档长期未使用的技能",
        "runner": _run_archive_stale_skills,
    },
}


# ---------- 站内通知（内存有界队列，最新在前） ---------- #
@dataclass
class _Notification:
    ts: float
    title: str
    body: str
    ok: bool

    def to_dict(self) -> dict:
        return {"ts": self.ts, "title": self.title,
                "body": self.body, "ok": self.ok}


_notifications: deque[_Notification] = deque(maxlen=_NOTIFY_MAX)
_notify_lock = threading.Lock()


def _notify(title: str, body: str, ok: bool = True) -> None:
    """追加一条站内通知（线程安全；body 先过脱敏闸门 + 截断）。"""
    safe = redact_text(body or "", source="cron_notify").text
    if len(safe) > 500:
        safe = safe[:497] + "…"
    with _notify_lock:
        _notifications.appendleft(_Notification(time.time(), title, safe, ok))
    log.info("cron_notified", extra={"ok": ok, "title": title[:60]})


def list_notifications() -> list[dict]:
    with _notify_lock:
        return [n.to_dict() for n in _notifications]


def clear_notifications() -> None:
    """清空通知队列（测试/运维用）。"""
    with _notify_lock:
        _notifications.clear()


# ---------- preflight：任务定义校验与规范化 ---------- #
def build_trigger(schedule: dict) -> BaseTrigger:
    """schedule 定义 → APScheduler 触发器；非法抛 CronError_（400）。

    支持：cron（expr 5 段 crontab）/ interval（seconds/minutes/hours/days
    至少一个正数）/ once（at ISO 8601，naive 按本地时区）。
    """
    if not isinstance(schedule, dict):
        raise CronError_("schedule 必须是对象")
    t = str(schedule.get("type", "")).strip()
    if t not in _SCHEDULE_TYPES:
        raise CronError_(f"不支持的调度类型：{t!r}（可用：{'/'.join(_SCHEDULE_TYPES)}）")
    tz = get_localzone()
    if t == "cron":
        expr = str(schedule.get("expr", "")).strip()
        if not expr:
            raise CronError_("cron 调度缺少 expr（5 段 crontab，如 '0 3 * * *'）")
        if len(expr.split()) != _CRON_SEGMENTS:
            raise CronError_(f"cron expr 需为 {_CRON_SEGMENTS} 段：'{expr}'")
        try:
            return CronTrigger.from_crontab(expr, timezone=tz)
        except ValueError as e:
            raise CronError_(f"cron 表达式非法：{expr!r}（{e}）") from e
    if t == "interval":
        fields = {}
        for unit in _INTERVAL_UNITS:
            raw = schedule.get(unit)
            if raw is None:
                continue
            try:
                val = int(raw)
            except (TypeError, ValueError) as e:
                raise CronError_(f"interval.{unit} 必须是整数：{raw!r}") from e
            if val <= 0:
                raise CronError_(f"interval.{unit} 必须为正数：{val}")
            fields[unit] = val
        if not fields:
            raise CronError_("interval 调度至少需要一个正数单位"
                             f"（{'/'.join(_INTERVAL_UNITS)}）")
        return IntervalTrigger(**fields, timezone=tz)
    # once
    at = str(schedule.get("at", "")).strip()
    if not at:
        raise CronError_("once 调度缺少 at（ISO 8601 时间，如 '2026-10-21 09:00'）")
    try:
        run_date = datetime.fromisoformat(at)
    except ValueError as e:
        raise CronError_(f"once.at 不是合法 ISO 时间：{at!r}") from e
    if run_date.tzinfo is None:
        run_date = run_date.replace(tzinfo=tz)   # naive 视为本地时区
    return DateTrigger(run_date=run_date, timezone=tz)


def preflight(spec: dict) -> dict:
    """校验并规范化任务定义（spec 来自 POST body）；非法抛 CronError_。

    规范化输出：{id, name, kind, task, query, level, schedule}，全基本类型
    （可直接随 job.kwargs 持久化）。agent 任务的 query 上限复用
    MAX_QUERY_CHARS；builtin 任务的 task 必须在 BUILTIN_TASKS 注册表内。
    """
    if not isinstance(spec, dict):
        raise CronError_("任务定义必须是对象")
    name = str(spec.get("name", "")).strip()
    if not name:
        raise CronError_("任务缺少 name（展示名）")
    if len(name) > _NAME_MAX:
        raise CronError_(f"name 超过 {_NAME_MAX} 字符")
    kind = str(spec.get("kind", "")).strip()
    if kind not in _KINDS:
        raise CronError_(f"不支持的 kind：{kind!r}（可用：{'/'.join(_KINDS)}）")

    task_key = str(spec.get("task", "")).strip()
    query = str(spec.get("query", "")).strip()
    if kind == "builtin":
        if task_key not in BUILTIN_TASKS:
            raise CronError_(f"未知内置任务：{task_key!r}（可用："
                             f"{'/'.join(sorted(BUILTIN_TASKS))}）")
        query = ""
    else:
        if not query:
            raise CronError_("agent 任务缺少 query（要模型执行的指令）")
        if len(query) > settings.MAX_QUERY_CHARS:
            raise CronError_(f"query 超过上限 {settings.MAX_QUERY_CHARS} 字符")
        task_key = ""
    raw_level = spec.get("level")
    if raw_level is None:
        level = _AGENT_LEVEL_DEFAULT
    else:
        try:
            level = max(1, min(5, int(raw_level)))
        except (TypeError, ValueError) as e:
            raise CronError_(f"level 必须是 1-5 的整数：{raw_level!r}") from e

    task_id = str(spec.get("id", "")).strip()
    if task_id and not _TASK_ID_RE.match(task_id):
        raise CronError_(f"任务 id 非法：{task_id!r}"
                         "（小写字母/数字/连字符，≤64 字符）")
    task_id = task_id or f"cron_{uuid.uuid4().hex[:8]}"

    schedule = dict(spec.get("schedule") or {})
    build_trigger(schedule)   # 提前失败：触发器不可构建 = 定义非法

    return {"id": task_id, "name": name, "kind": kind, "task": task_key,
            "query": query, "level": level, "schedule": schedule}


def describe_schedule(schedule: dict) -> str:
    """schedule 定义 → 人类可读文本（列表展示）。"""
    t = str((schedule or {}).get("type", ""))
    if t == "cron":
        return f"cron：{str(schedule.get('expr', '')).strip() or '?'}"
    if t == "interval":
        parts = [f"{int(schedule[u])}{_UNIT_CN[u]}"
                 for u in ("days", "hours", "minutes", "seconds")
                 if schedule.get(u)]
        return "每 " + " ".join(parts) if parts else "interval：?"
    if t == "once":
        return f"一次性：{str(schedule.get('at', '')).strip() or '?'}"
    return "?"


_UNIT_CN = {"seconds": "秒", "minutes": "分钟", "hours": "小时", "days": "天"}


# ---------- 执行（模块级函数：随 job 持久化可 pickle） ---------- #
def _execute_task(task: dict) -> None:
    """APScheduler 触发入口：按 kind 分发，结果发通知 + cron_task_finished 信号。

    异常不外抛（APScheduler 会记 missed）：失败转通知 ok=False，调度循环
    继续跑后续任务。
    """
    task_id = str(task.get("id", "?"))
    name = str(task.get("name", task_id))
    started = time.time()
    try:
        if task.get("kind") == "builtin":
            runner = BUILTIN_TASKS[task["task"]]["runner"]
            detail = runner()
            _notify(f"定时任务完成：{name}", _fmt_builtin(detail), ok=True)
        else:
            _run_agent_task(task, name)
        cron_task_finished.send("cron", task_id=task_id, ok=True,
                                ms=int((time.time() - started) * 1000))
    except Exception as e:  # noqa: BLE001 —— 单任务失败不拖垮调度循环
        log.exception("cron_task_failed", extra={"task_id": task_id})
        _notify(f"定时任务失败：{name}",
                f"{type(e).__name__}: {e}", ok=False)
        cron_task_finished.send("cron", task_id=task_id, ok=False,
                                error=type(e).__name__)


def _fmt_builtin(detail: dict) -> str:
    archived = detail.get("archived") or []
    if not archived:
        return "没有需要归档的技能"
    return f"已归档 {len(archived)} 个技能：{'、'.join(archived)}"


def _run_agent_task(task: dict, name: str) -> None:
    """agent 任务：跑一次无状态 agent_step，产出脱敏后通知。"""
    from .transport import agent_step  # 惰性 import：避免 cron→transport→build 链在导入期全量拉起

    level = int(task.get("level") or _AGENT_LEVEL_DEFAULT)
    result = agent_step(query=task["query"], level=level)
    content = str(result.get("content") or "").strip() or "（无文本产出）"
    _notify(f"定时任务完成：{name}", content, ok=True)


# ---------- 调度器单例 ---------- #
_scheduler: BackgroundScheduler | None = None


def _default_sqlite_url() -> str:
    """任务存储落数据目录 <PYPEDIA_DATA>/agent/cron.db（与记忆/技能同目录）。"""
    base = os.getenv("PYPEDIA_DATA", os.path.join(os.path.expanduser("~"), ".pypedia"))
    path = os.path.join(base, "agent", "cron.db")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return f"sqlite:///{path.replace(os.sep, '/')}"


def build_scheduler(jobstores: dict | None = None) -> BackgroundScheduler:
    """构造 BackgroundScheduler（未 start）；jobstores 可注入（测试用 memory）。"""
    if jobstores is None:
        jobstores = {"default": SQLAlchemyJobStore(url=_default_sqlite_url())}
    return BackgroundScheduler(
        jobstores=jobstores,
        timezone=get_localzone(),
        executors={"default": {"type": "threadpool", "max_workers": 2}},
        job_defaults={
            "coalesce": True,            # 积压触发合并为一次
            "max_instances": 1,          # 同任务不并发
            "misfire_grace_time": _MISFIRE_GRACE,
        },
    )


def start(jobstores: dict | None = None) -> BackgroundScheduler:
    """启动（幂等）并返回进程内调度器单例。"""
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    _scheduler = build_scheduler(jobstores)
    _scheduler.start()
    restored = len(_scheduler.get_jobs())
    log.info("cron_scheduler_started", extra={"restored_jobs": restored})
    return _scheduler


def shutdown() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def get_scheduler() -> BackgroundScheduler:
    """取调度器（未启动则启动）——所有任务操作的入口。"""
    if _scheduler is None:
        return start()
    return _scheduler


# ---------- 任务 CRUD ---------- #
def _task_view(job, task_fallback: dict | None = None) -> dict:
    task = ((job.kwargs or {}).get("task") if job is not None else None) \
        or task_fallback or {}
    next_run = job.next_run_time if job is not None else None
    return {
        "id": job.id,
        "name": str(task.get("name") or job.name or job.id),
        "kind": task.get("kind", ""),
        "task": task.get("task", ""),
        "query": task.get("query", ""),
        "level": task.get("level", _AGENT_LEVEL_DEFAULT),
        "schedule": task.get("schedule", {}),
        "schedule_text": describe_schedule(task.get("schedule", {})),
        "paused": next_run is None,
        "next_run_time": next_run.isoformat() if next_run else "",
    }


def add_task(spec: dict) -> dict:
    """preflight → 注册（同 id 覆盖更新）；返回任务视图。"""
    task = preflight(spec)
    sch = get_scheduler()
    if sch.get_job(task["id"]) is None:
        max_tasks = max(1, settings.AGENT_CRON_MAX_TASKS)
        if len(sch.get_jobs()) >= max_tasks:
            raise CronError_(f"任务数已达上限 {max_tasks}，请先删除旧任务")
    sch.add_job(
        _execute_task,
        build_trigger(task["schedule"]),
        kwargs={"task": task},
        id=task["id"],
        name=task["name"],
        replace_existing=True,
    )
    log.info("cron_task_added", extra={"task_id": task["id"], "kind": task["kind"]})
    cron_task_finished.send("cron", task_id=task["id"], ok=True, op="added")
    # once 且 at 已过：APScheduler 可能瞬间触发完并移除 job，get_job 为 None，
    # 此时用任务定义兜底渲染视图（不再伪装 next_run_time）
    return _task_view(sch.get_job(task["id"]), task_fallback=task)


def list_tasks() -> list[dict]:
    """全部任务（含暂停态），按创建顺序稳定返回。"""
    sch = get_scheduler()
    return [_task_view(j) for j in sch.get_jobs()]


def remove_task(task_id: str) -> None:
    sch = get_scheduler()
    if sch.get_job(task_id) is None:
        raise TaskNotFound(f"任务不存在：{task_id!r}")
    sch.remove_job(task_id)
    log.info("cron_task_removed", extra={"task_id": task_id})


def pause_task(task_id: str) -> dict:
    sch = get_scheduler()
    if sch.get_job(task_id) is None:
        raise TaskNotFound(f"任务不存在：{task_id!r}")
    sch.pause_job(task_id)
    return _task_view(sch.get_job(task_id))


def resume_task(task_id: str) -> dict:
    sch = get_scheduler()
    if sch.get_job(task_id) is None:
        raise TaskNotFound(f"任务不存在：{task_id!r}")
    sch.resume_job(task_id)
    return _task_view(sch.get_job(task_id))


def run_task(task_id: str) -> dict:
    """立即触发一次（不改周期）：把 next_run_time 拨到当下。

    同步等待最多 _RUN_WAIT 秒让执行落地（桌面端点可接受），超时也返回
    （执行仍在后台继续，结果以通知形式到达）。
    """
    sch = get_scheduler()
    job = sch.get_job(task_id)
    if job is None:
        raise TaskNotFound(f"任务不存在：{task_id!r}")
    if job.next_run_time is None:
        sch.resume_job(task_id)      # 暂停态先恢复，否则 modify 不生效
    sch.modify_job(task_id, next_run_time=datetime.now(get_localzone()))
    deadline = time.monotonic() + _RUN_WAIT
    before = list_notifications()
    while time.monotonic() < deadline:
        time.sleep(0.05)
        now = list_notifications()
        if now and (not before or now[0] != before[0]):
            break
    return _task_view(sch.get_job(task_id) or job)
