"""cron 端点测试：/api/agent/cron REST 全流程（引擎 conftest 已 stub，零真实调用）。

调度器由 app 模块导入时启动（PYPEDIA_DATA 已由 conftest 隔离到临时目录，
jobstore 落临时 sqlite）；本文件只管 HTTP 契约：503/400/404/全流程。
"""
from __future__ import annotations

import pytest

from pypedia.config import settings


class TestCronEndpoint:
    def test_get_meta(self, client):
        r = client.get("/api/agent/cron")
        assert r.status_code == 200
        d = r.json()
        assert d["builtin_tasks"][0]["key"] == "archive_stale_skills"
        assert d["max_tasks"] >= 1
        assert isinstance(d["tasks"], list)
        assert isinstance(d["notifications"], list)

    def test_full_flow(self, client, fake_agent_step):
        """建 → 列表 → 暂停 → 恢复 → 立即触发（通知落点）→ 删除 → 再删 404。"""
        r = client.post("/api/agent/cron", json={
            "name": "端点回顾", "kind": "agent", "query": "回顾记忆",
            "schedule": {"type": "interval", "minutes": 30}})
        assert r.status_code == 200
        task = r.json()["task"]
        tid = task["id"]
        assert task["schedule_text"] == "每 30分钟"
        assert task["paused"] is False

        listed = {t["id"]: t for t in client.get("/api/agent/cron").json()["tasks"]}
        assert tid in listed

        r = client.post(f"/api/agent/cron/{tid}/pause")
        assert r.json()["task"]["paused"] is True
        r = client.post(f"/api/agent/cron/{tid}/resume")
        assert r.json()["task"]["paused"] is False

        r = client.post(f"/api/agent/cron/{tid}/run")
        assert r.status_code == 200
        assert fake_agent_step == [{"query": "回顾记忆", "level": 2}]
        notes = client.get("/api/agent/cron").json()["notifications"]
        assert notes and notes[0]["ok"] is True
        assert "【桩】定时总结完成" in notes[0]["body"]

        assert client.delete(f"/api/agent/cron/{tid}").status_code == 200
        assert client.delete(f"/api/agent/cron/{tid}").status_code == 404

    def test_preflight_400(self, client, fake_agent_step):
        """非法定义 400，且不触发 LLM（preflight 失败不发调用）。"""
        bad_specs = [
            {"name": "x", "kind": "agent", "query": "q",
             "schedule": {"type": "cron", "expr": "坏掉的表达式"}},
            {"name": "x", "kind": "builtin", "task": "nope",
             "schedule": {"type": "interval", "minutes": 1}},
            {"name": "x", "kind": "agent", "query": "",
             "schedule": {"type": "interval", "minutes": 1}},
        ]
        for spec in bad_specs:
            r = client.post("/api/agent/cron", json=spec)
            assert r.status_code == 400, spec
            assert r.json()["detail"]
        assert fake_agent_step == []

    def test_action_404_and_bad_action(self, client):
        assert client.post("/api/agent/cron/ghost/pause").status_code == 404
        assert client.post("/api/agent/cron/ghost/run").status_code == 404
        r = client.post("/api/agent/cron/whatever/bogus")
        assert r.status_code == 400

    def test_disabled_503(self, client, monkeypatch):
        monkeypatch.setattr(settings, "AGENT_CRON_ENABLE", False)
        assert client.get("/api/agent/cron").status_code == 503
        assert client.post("/api/agent/cron", json={
            "name": "x", "kind": "builtin", "task": "archive_stale_skills",
            "schedule": {"type": "interval", "minutes": 1}}).status_code == 503
        assert client.delete("/api/agent/cron/x").status_code == 503
        assert client.post("/api/agent/cron/x/pause").status_code == 503
