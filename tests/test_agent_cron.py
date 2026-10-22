"""P4 cron 定时自动化测试（Hermes 特性：APScheduler + preflight + 通知）。

铁律：零真实 LLM——agent 任务的唯一出口 transport.agent_step 一律打桩；
调度器注入 MemoryJobStore（不碰磁盘），持久化用例单独用 tmp sqlite 文件。
"""
from __future__ import annotations

import time

import pytest
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

from pypedia.agent import cron
from pypedia.agent.cron import CronError_, build_trigger, describe_schedule
from pypedia.config import settings


# ---------- fixtures ---------- #
@pytest.fixture
def cron_env(monkeypatch):
    """内存 jobstore 的调度器 + 干净通知队列；teardown 关调度器。"""
    cron.shutdown()
    cron.clear_notifications()
    cron.start(jobstores={"default": MemoryJobStore()})
    yield
    cron.shutdown()
    cron.clear_notifications()


@pytest.fixture
def recorder():
    """blinker 信号接收器（弱引用防护：强引用持有）。"""
    received: list[dict] = []

    def rec(sender, **kw):
        received.append({"sender": sender, **kw})

    from pypedia.agent.hooks import cron_task_finished

    cron_task_finished.connect(rec, weak=False)
    yield received
    cron_task_finished.disconnect(rec)


def _wait(predicate, timeout: float = 5.0):
    """轮询等待条件成立（调度器 tick 级延迟）；超时断言失败。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


# ---------- preflight：合法定义 ---------- #
def test_preflight_builtin_normalized():
    task = cron.preflight({
        "name": "每天归档冷技能", "kind": "builtin",
        "task": "archive_stale_skills",
        "schedule": {"type": "cron", "expr": "0 3 * * *"},
    })
    assert task["kind"] == "builtin"
    assert task["task"] == "archive_stale_skills"
    assert task["query"] == ""          # builtin 忽略 query
    assert task["level"] == 2
    assert task["id"].startswith("cron_")
    assert task["schedule"]["expr"] == "0 3 * * *"


def test_preflight_agent_normalized():
    task = cron.preflight({
        "id": "my-job", "name": "早间回顾", "kind": "agent",
        "query": "回顾最近三天的记忆", "level": 3,
        "schedule": {"type": "interval", "minutes": 30},
    })
    assert task["id"] == "my-job"
    assert task["kind"] == "agent"
    assert task["query"] == "回顾最近三天的记忆"
    assert task["level"] == 3
    assert task["task"] == ""           # agent 忽略内置 task key


def test_preflight_once_naive_treated_local():
    task = cron.preflight({
        "name": "一次性", "kind": "builtin", "task": "archive_stale_skills",
        "schedule": {"type": "once", "at": "2026-10-21 09:00"},
    })
    trigger = build_trigger(task["schedule"])
    # naive 时间被附上本地时区（而非 naive/UTC）
    assert trigger.run_date.tzinfo is not None


def test_preflight_level_clamped():
    """level 越界钳制到 1-5（与 /api/agent/step 同语义），不拒绝。"""
    assert cron.preflight({"name": "x", "kind": "agent", "query": "q", "level": 9,
                           "schedule": {"type": "interval", "minutes": 1}
                           })["level"] == 5
    assert cron.preflight({"name": "x", "kind": "agent", "query": "q", "level": 0,
                           "schedule": {"type": "interval", "minutes": 1}
                           })["level"] == 1


@pytest.mark.parametrize("spec,reason", [
    ({"name": "x", "kind": "builtin", "task": "nope",
      "schedule": {"type": "interval", "minutes": 1}}, "未知内置任务"),
    ({"name": "x", "kind": "builtin", "task": "archive_stale_skills",
      "schedule": {"type": "cron", "expr": "0 3 * *"}}, "crontab 段数不足"),
    ({"name": "x", "kind": "builtin", "task": "archive_stale_skills",
      "schedule": {"type": "cron", "expr": "99 3 * * *"}}, "crontab 值非法"),
    ({"name": "x", "kind": "builtin", "task": "archive_stale_skills",
      "schedule": {"type": "interval"}}, "interval 无单位"),
    ({"name": "x", "kind": "builtin", "task": "archive_stale_skills",
      "schedule": {"type": "interval", "minutes": 0}}, "interval 非正数"),
    ({"name": "x", "kind": "builtin", "task": "archive_stale_skills",
      "schedule": {"type": "once", "at": "not-a-time"}}, "ISO 时间非法"),
    ({"name": "x", "kind": "builtin", "task": "archive_stale_skills",
      "schedule": {"type": "weekly"}}, "调度类型不支持"),
    ({"name": "x", "kind": "agent", "schedule": {"type": "interval", "minutes": 1}},
     "agent 缺 query"),
    ({"name": "x", "kind": "agent", "query": "q" * (settings.MAX_QUERY_CHARS + 1),
      "schedule": {"type": "interval", "minutes": 1}}, "query 超长"),
    ({"name": "x", "kind": "other", "schedule": {"type": "interval", "minutes": 1}},
     "kind 不支持"),
    ({"name": "", "kind": "agent", "query": "q",
      "schedule": {"type": "interval", "minutes": 1}}, "缺 name"),
    ({"name": "x", "kind": "agent", "query": "q", "level": "abc",
      "schedule": {"type": "interval", "minutes": 1}}, "level 非整数"),
    ({"name": "x", "kind": "agent", "query": "q", "id": "Bad_ID",
      "schedule": {"type": "interval", "minutes": 1}}, "id 非法"),
    ({"name": "x", "kind": "builtin", "task": "archive_stale_skills",
      "schedule": None}, "schedule 缺失"),
])
def test_preflight_rejects_invalid(spec, reason, fake_agent_step):
    """preflight 失败直接拒绝：不注册、不触发、不发 LLM 调用（验收项）。"""
    with pytest.raises(CronError_):
        cron.preflight(spec)
    assert fake_agent_step == [], f"{reason}：preflight 失败却触发了 LLM 调用"


# ---------- 触发器 / 描述 ---------- #
def test_build_trigger_types():
    assert type(build_trigger({"type": "cron", "expr": "*/5 * * * *"})).__name__ \
        == "CronTrigger"
    assert type(build_trigger({"type": "interval", "seconds": 30})).__name__ \
        == "IntervalTrigger"
    assert type(build_trigger({"type": "once", "at": "2026-10-21 09:00"})).__name__ \
        == "DateTrigger"


def test_describe_schedule_text():
    assert describe_schedule({"type": "cron", "expr": "0 3 * * *"}) == "cron：0 3 * * *"
    assert describe_schedule({"type": "interval", "minutes": 30}) == "每 30分钟"
    assert describe_schedule({"type": "interval", "hours": 2, "minutes": 5}) == "每 2小时 5分钟"
    assert describe_schedule({"type": "once", "at": "2026-10-21 09:00"}) \
        == "一次性：2026-10-21 09:00"


# ---------- CRUD（内存 jobstore） ---------- #
def test_add_and_list(cron_env, fake_agent_step):
    view = cron.add_task({"name": "早间回顾", "kind": "agent", "query": "回顾记忆",
                          "schedule": {"type": "interval", "minutes": 30}})
    tasks = cron.list_tasks()
    assert len(tasks) == 1
    t = tasks[0]
    assert t["id"] == view["id"]
    assert t["name"] == "早间回顾"
    assert t["kind"] == "agent"
    assert t["schedule_text"] == "每 30分钟"
    assert t["paused"] is False
    assert t["next_run_time"]              # 已排下一次
    assert fake_agent_step == []           # 仅注册，未执行


def test_add_overwrite_same_id(cron_env):
    spec = {"id": "job-1", "name": "归档", "kind": "builtin",
            "task": "archive_stale_skills", "schedule": {"type": "interval", "hours": 1}}
    cron.add_task(dict(spec))
    cron.add_task({**spec, "schedule": {"type": "interval", "hours": 2}})
    tasks = cron.list_tasks()
    assert len(tasks) == 1
    assert tasks[0]["schedule_text"] == "每 2小时"


def test_remove_task(cron_env):
    cron.add_task({"name": "归档", "kind": "builtin", "task": "archive_stale_skills",
                   "schedule": {"type": "interval", "hours": 1}})
    cron.remove_task(cron.list_tasks()[0]["id"])
    assert cron.list_tasks() == []
    with pytest.raises(CronError_):
        cron.remove_task("no-such-job")


def test_pause_resume(cron_env):
    cron.add_task({"id": "p1", "name": "归档", "kind": "builtin",
                   "task": "archive_stale_skills",
                   "schedule": {"type": "interval", "hours": 1}})
    paused = cron.pause_task("p1")
    assert paused["paused"] is True
    assert paused["next_run_time"] == ""
    assert cron.list_tasks()[0]["paused"] is True
    resumed = cron.resume_task("p1")
    assert resumed["paused"] is False
    assert resumed["next_run_time"]
    with pytest.raises(CronError_):
        cron.pause_task("ghost")


def test_max_tasks_limit(cron_env, monkeypatch):
    monkeypatch.setattr(settings, "AGENT_CRON_MAX_TASKS", 2)
    for i in range(2):
        cron.add_task({"name": f"任务{i}", "kind": "builtin",
                       "task": "archive_stale_skills",
                       "schedule": {"type": "interval", "hours": 1}})
    with pytest.raises(CronError_):
        cron.add_task({"name": "任务3", "kind": "builtin",
                       "task": "archive_stale_skills",
                       "schedule": {"type": "interval", "hours": 1}})
    assert len(cron.list_tasks()) == 2


def test_sqlite_jobstore_persist_and_restart(tmp_path, monkeypatch):
    """SQLAlchemyJobStore：任务定义随 job 落 sqlite，重启调度器后恢复。"""
    monkeypatch.delenv("PYPEDIA_DATA", raising=False)
    url = f"sqlite:///{(tmp_path / 'cron.db').as_posix()}"
    try:
        cron.shutdown()
        cron.start(jobstores={"default": SQLAlchemyJobStore(url=url)})
        cron.add_task({"id": "persist-1", "name": "每日归档", "kind": "builtin",
                       "task": "archive_stale_skills",
                       "schedule": {"type": "cron", "expr": "0 3 * * *"}})
        cron.shutdown()

        cron.start(jobstores={"default": SQLAlchemyJobStore(url=url)})
        tasks = cron.list_tasks()
        assert len(tasks) == 1
        assert tasks[0]["id"] == "persist-1"
        assert tasks[0]["name"] == "每日归档"
        assert tasks[0]["schedule_text"] == "cron：0 3 * * *"
        assert tasks[0]["paused"] is False
    finally:
        cron.shutdown()


# ---------- 触发执行 ---------- #
def test_run_task_fires_agent(cron_env, fake_agent_step):
    cron.add_task({"name": "早间回顾", "kind": "agent", "query": "回顾最近三天的记忆",
                   "schedule": {"type": "interval", "minutes": 30}})
    view = cron.run_task(cron.list_tasks()[0]["id"])
    assert view["paused"] is False
    assert fake_agent_step == [{"query": "回顾最近三天的记忆", "level": 2}]
    notes = cron.list_notifications()
    assert notes[0]["ok"] is True
    assert "【桩】定时总结完成" in notes[0]["body"]
    assert "早间回顾" in notes[0]["title"]


def test_run_task_builtin_archive(cron_env, monkeypatch):
    from pypedia.agent import skills as skills_mod

    monkeypatch.setattr(skills_mod.skill_store, "archive_stale",
                        lambda days=None: ["cold-a", "cold-b"])
    cron.add_task({"name": "冷技能归档", "kind": "builtin",
                   "task": "archive_stale_skills",
                   "schedule": {"type": "interval", "hours": 24}})
    cron.run_task(cron.list_tasks()[0]["id"])
    notes = cron.list_notifications()
    assert notes[0]["ok"] is True
    assert "已归档 2 个技能" in notes[0]["body"]
    assert "cold-a" in notes[0]["body"]


def test_run_task_failure_notifies_and_scheduler_survives(cron_env, monkeypatch):
    """单任务失败 → 通知 ok=False，调度循环继续（后续任务照常跑）。"""
    from pypedia.agent import skills as skills_mod

    def boom(days=None):
        raise RuntimeError("磁盘满了")

    monkeypatch.setattr(skills_mod.skill_store, "archive_stale", boom)
    cron.add_task({"id": "bad", "name": "坏任务", "kind": "builtin",
                   "task": "archive_stale_skills",
                   "schedule": {"type": "interval", "hours": 1}})
    cron.run_task("bad")
    notes = cron.list_notifications()
    assert notes[0]["ok"] is False
    assert "RuntimeError" in notes[0]["body"]
    # 调度器仍存活：再注册一个任务能立即执行
    monkeypatch.undo()
    monkeypatch.setattr(skills_mod.skill_store, "archive_stale",
                        lambda days=None: [])
    cron.add_task({"id": "good", "name": "好任务", "kind": "builtin",
                   "task": "archive_stale_skills",
                   "schedule": {"type": "interval", "hours": 1}})
    cron.run_task("good")
    assert cron.list_notifications()[0]["ok"] is True


def test_once_task_not_rescheduled_after_fire(cron_env, fake_agent_step):
    """once 任务触发后自动移除，不再排下一次。"""
    from datetime import datetime, timedelta

    from tzlocal import get_localzone

    at = datetime.now(get_localzone()) + timedelta(seconds=2)
    cron.add_task({"id": "once-1", "name": "一次性回顾", "kind": "agent",
                   "query": "临时任务",
                   "schedule": {"type": "once", "at": at.isoformat()}})
    assert _wait(lambda: fake_agent_step, timeout=6), "once 任务未被触发"
    job = cron.get_scheduler().get_job("once-1")
    assert job is None or job.next_run_time is None


def test_paused_task_not_fired_until_resume(cron_env, fake_agent_step):
    """暂停态不触发；恢复后按周期触发（暂停语义验收）。"""
    cron.add_task({"id": "p2", "name": "周期回顾", "kind": "agent",
                   "query": "周期任务",
                   "schedule": {"type": "interval", "seconds": 1}})
    cron.pause_task("p2")
    time.sleep(1.6)
    assert fake_agent_step == [], "暂停态任务被触发"
    cron.resume_task("p2")
    assert _wait(lambda: fake_agent_step, timeout=5), "恢复后任务未被触发"


def test_agent_notification_redacted(cron_env, monkeypatch):
    """通知文本过脱敏闸门：密钥/令牌不进入站内通知。"""
    def leak_step(*, query, level=2, state=None, tool_results=None):
        return {"type": "final",
                "content": "配置已就绪，密钥 sk-abcdefghijklmnopqrstuvwxyz123456 请妥善保管",
                "provider": "mock"}

    monkeypatch.setattr("pypedia.agent.transport.agent_step", leak_step)
    cron.add_task({"name": "汇报", "kind": "agent", "query": "汇报进度",
                   "schedule": {"type": "interval", "minutes": 30}})
    cron.run_task(cron.list_tasks()[0]["id"])
    body = cron.list_notifications()[0]["body"]
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in body
    assert "«已脱敏»" in body


def test_notifications_bounded():
    """通知队列有界（_NOTIFY_MAX），不随执行次数无界增长。"""
    cron.clear_notifications()
    for i in range(cron._NOTIFY_MAX + 20):
        cron._notify(f"t{i}", "b", ok=True)
    notes = cron.list_notifications()
    assert len(notes) == cron._NOTIFY_MAX
    assert notes[0]["title"] == f"t{cron._NOTIFY_MAX + 19}"   # 最新在前
    cron.clear_notifications()


# ---------- hooks ---------- #
def test_cron_task_finished_signal(cron_env, fake_agent_step, recorder):
    """注册与执行都发 cron_task_finished（审计留痕）。"""
    cron.add_task({"id": "sig-1", "name": "信号任务", "kind": "agent",
                   "query": "跑一下", "schedule": {"type": "interval", "minutes": 30}})
    cron.run_task("sig-1")
    ops = [r.get("op", "") for r in recorder]
    assert "added" in ops
    done = [r for r in recorder if r.get("task_id") == "sig-1" and "op" not in r]
    assert done and done[-1]["ok"] is True
