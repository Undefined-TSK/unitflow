"""app 端点测试：TestClient 全端点 + 边界 + 序列化回归（引擎打桩，零真实调用）。

stub_ask / ASK_OK 定义在 conftest（与 test_limiter 共用）。
"""
import io

import pytest


class TestGetEndpoints:
    def test_root(self, client):
        assert client.get("/").status_code == 200

    def test_status(self, client):
        r = client.get("/api/status")
        assert r.status_code == 200
        d = r.json()
        assert "provider" in d and "config" in d

    def test_sources(self, client):
        r = client.get("/api/sources")
        assert r.status_code == 200
        assert "sources" in r.json() and "stats" in r.json()

    def test_profile(self, client):
        r = client.get("/api/profile")
        assert r.status_code == 200
        d = r.json()
        assert "memories" in d

    def test_profile_with_session(self, client, stub_ask):
        r = client.post("/api/ask", json={"query": "第一问", "session_id": "sess-x"})
        sid = r.json()["session"]["session_id"]
        assert sid == "sess-x"
        p = client.get(f"/api/profile?session_id={sid}")
        assert p.status_code == 200
        assert p.json()["session"]["turns"] == 1

    def test_evolution(self, client):
        assert client.get("/api/evolution").status_code == 200

    def test_capabilities(self, client):
        r = client.get("/api/capabilities")
        assert r.status_code == 200
        d = r.json()
        assert len(d["models"]) == 11
        assert len(d["capabilities"]) == 5

    def test_mcp(self, client):
        r = client.get("/api/mcp")
        assert r.status_code == 200
        assert "servers" in r.json()


class TestAskEndpoint:
    def test_ok(self, client, stub_ask):
        r = client.post("/api/ask", json={"query": "什么是装饰器", "level": 3})
        assert r.status_code == 200
        d = r.json()
        assert d["answer"] == "打桩答案"
        assert d["confidence"]["score"] == 72
        # _json_safe：session dataclass 必须可序列化（ConversationContext 回归）
        assert d["session"]["session_id"]
        assert isinstance(d["session"]["turns"], list)

    def test_empty_query_400(self, client, stub_ask):
        assert client.post("/api/ask", json={"query": ""}).status_code == 400
        assert client.post("/api/ask", json={"query": "   "}).status_code == 400

    def test_missing_query_422(self, client, stub_ask):
        assert client.post("/api/ask", json={"level": 3}).status_code == 422

    def test_level_clamped(self, client, stub_ask):
        r = client.post("/api/ask", json={"query": "q", "level": 99})
        assert r.status_code == 200  # 不崩，内部归位到 5

    def test_engine_failure_502(self, client, stub_ask):
        stub_ask["raises"] = True
        r = client.post("/api/ask", json={"query": "q"})
        assert r.status_code == 502
        assert "生成答案" in r.json()["detail"]


class TestUploadEndpoint:
    def test_unsupported_ext_400(self, client):
        f = io.BytesIO(b"data")
        r = client.post("/api/sources/upload",
                        files={"file": ("a.bin", f, "application/octet-stream")},
                        data={"role": "supplement_b"})
        assert r.status_code == 400
        assert "不支持的格式" in r.json()["detail"]

    def test_oversize_413(self, client, monkeypatch):
        from pypedia.config import settings
        monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 0.001)
        f = io.BytesIO(b"x" * 2048)
        r = client.post("/api/sources/upload",
                        files={"file": ("a.md", f, "text/markdown")},
                        data={"role": "supplement_b"})
        assert r.status_code == 413
        assert "超过上限" in r.json()["detail"]


class TestOtherWriteEndpoints:
    def test_url_empty_400(self, client):
        assert client.post("/api/sources/url", json={"url": ""}).status_code == 400

    def test_github_empty_400(self, client):
        assert client.post("/api/sources/github", json={"repo": ""}).status_code == 400

    def test_feedback_empty_issue_400(self, client):
        assert client.post("/api/evolution/feedback",
                           json={"issue": "  "}).status_code == 400

    def test_feedback_ok(self, client):
        r = client.post("/api/evolution/feedback",
                        json={"query": "装饰器", "issue": "答得太简略"})
        assert r.status_code == 200

    def test_feedback_persist_failure_returns_500(self, client, monkeypatch):
        """沉淀失败必须 500：此前恒返回 200 ok=true，前端会误报「已沉淀成技能」。"""
        from app import engine

        def boom(*_a, **_kw):
            raise RuntimeError("disk full")

        monkeypatch.setattr(engine.evolution.skills, "add_skill", boom)
        r = client.post("/api/evolution/feedback",
                        json={"query": "装饰器", "issue": "答得太简略"})
        assert r.status_code == 500
        assert "disk full" in r.json()["detail"]

    def test_delete_missing_source(self, client):
        # 删除不存在的源：不崩（幂等）
        r = client.delete("/api/sources/不存在-id")
        assert r.status_code in (200, 404)
