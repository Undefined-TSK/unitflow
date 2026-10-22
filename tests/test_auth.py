"""本地 Bearer Token 鉴权测试：令牌生命周期 + 中间件放行/拒绝（零真实调用）。"""
import os
import stat

import pytest

from pypedia import auth
from pypedia.config import settings


@pytest.fixture
def auth_on(monkeypatch):
    """开启鉴权并固定已知令牌；teardown 自动复原。"""
    monkeypatch.setattr(settings, "AUTH_ENABLE", True)
    monkeypatch.setattr(settings, "AUTH_TOKEN", "test-token-123")
    monkeypatch.setattr(auth, "_current", "")
    auth.ensure_token()
    yield "test-token-123"


@pytest.fixture
def auth_off(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_ENABLE", False)
    monkeypatch.setattr(settings, "AUTH_TOKEN", "")
    monkeypatch.setattr(auth, "_current", "")
    auth.ensure_token()


class TestTokenLifecycle:
    def test_disabled_no_token(self, auth_off):
        assert auth.current_token() == ""

    def test_explicit_token_from_env(self, auth_on):
        assert auth.current_token() == "test-token-123"

    def test_generate_and_persist(self, monkeypatch, auth_off):
        """无显式令牌时生成并落盘，权限 600。"""
        monkeypatch.setattr(settings, "AUTH_ENABLE", True)
        monkeypatch.setattr(settings, "AUTH_TOKEN", "")
        auth.TOKEN_FILE.unlink(missing_ok=True)
        token = auth.ensure_token()
        assert token and len(token) >= 32
        assert auth.TOKEN_FILE.exists()
        mode = stat.S_IMODE(auth.TOKEN_FILE.stat().st_mode)
        assert mode == 0o600
        # 二次调用复用同一令牌（不重复生成）
        assert auth.ensure_token() == token

    def test_read_existing_file(self, monkeypatch, auth_off):
        """令牌文件已存在时直接复用（重启不翻转令牌）。"""
        auth.TOKEN_FILE.write_text("file-token-xyz", encoding="utf-8")
        monkeypatch.setattr(settings, "AUTH_ENABLE", True)
        monkeypatch.setattr(settings, "AUTH_TOKEN", "")
        assert auth.ensure_token() == "file-token-xyz"

    def test_env_token_beats_file(self, monkeypatch, auth_off):
        auth.TOKEN_FILE.write_text("file-token-xyz", encoding="utf-8")
        monkeypatch.setattr(settings, "AUTH_ENABLE", True)
        monkeypatch.setattr(settings, "AUTH_TOKEN", "env-token-abc")
        assert auth.ensure_token() == "env-token-abc"


class TestCheckHeader:
    def test_disabled_always_passes(self, auth_off):
        assert auth.check_header(None)
        assert auth.check_header("Bearer whatever")
        assert auth.check_header("garbage")

    def test_correct_token(self, auth_on):
        assert auth.check_header("Bearer test-token-123")

    def test_scheme_case_insensitive(self, auth_on):
        assert auth.check_header("bearer test-token-123")
        assert auth.check_header("BEARER test-token-123")

    def test_wrong_token_rejected(self, auth_on):
        assert not auth.check_header("Bearer wrong-token")

    def test_missing_header_rejected(self, auth_on):
        assert not auth.check_header(None)
        assert not auth.check_header("")

    def test_non_bearer_scheme_rejected(self, auth_on):
        assert not auth.check_header("Basic dXNlcjpwYXNz")
        assert not auth.check_header("Token test-token-123")

    def test_extra_whitespace_tolerated(self, auth_on):
        assert auth.check_header("Bearer   test-token-123  ")

    def test_empty_process_token_rejects_all(self, monkeypatch):
        """令牌未初始化（如忘记 ensure_token）时拒绝一切，绝不裸放行。"""
        monkeypatch.setattr(settings, "AUTH_ENABLE", True)
        monkeypatch.setattr(auth, "_current", "")
        assert not auth.check_header("Bearer anything")


class TestPublicPaths:
    def test_public_exact(self):
        assert auth.is_public("/")
        assert auth.is_public("/api/status")

    def test_public_prefix(self):
        assert auth.is_public("/static/index.html")
        assert auth.is_public("/static/vendor/marked.min.js")

    def test_protected_paths(self):
        for p in ("/api/ask", "/api/sources", "/api/profile",
                  "/api/evolution", "/api/capabilities", "/api/mcp"):
            assert not auth.is_public(p), p


class TestAuthMiddleware:
    def test_disabled_by_default(self, client):
        """默认不鉴权：所有端点直接可用。"""
        assert client.get("/api/sources").status_code == 200
        assert client.get("/api/status").status_code == 200
        assert client.get("/").status_code == 200

    def test_protected_401_without_token(self, client, auth_on):
        r = client.get("/api/sources")
        assert r.status_code == 401
        assert r.headers["WWW-Authenticate"] == "Bearer"
        assert "Bearer" in r.json()["detail"]

    def test_public_paths_pass(self, client, auth_on):
        assert client.get("/").status_code == 200
        assert client.get("/api/status").status_code == 200
        assert client.get("/static/index.html").status_code == 200

    def test_protected_200_with_token(self, client, auth_on):
        r = client.get("/api/sources",
                       headers={"Authorization": f"Bearer {auth_on}"})
        assert r.status_code == 200

    def test_wrong_token_401(self, client, auth_on):
        r = client.get("/api/sources", headers={"Authorization": "Bearer nope"})
        assert r.status_code == 401

    def test_ask_requires_token(self, client, auth_on, stub_ask):
        r = client.post("/api/ask", json={"query": "q"})
        assert r.status_code == 401  # 令牌闸在引擎之前

    def test_401_is_logged(self, client, auth_on, caplog):
        """401 拒绝也必须留痕（安全审计）——验证中间件嵌套顺序。"""
        import logging
        with caplog.at_level(logging.INFO, logger="pypedia"):
            client.get("/api/sources")
        recs = [x for x in caplog.records
                if x.name == "pypedia.http" and getattr(x, "status", None) == 401]
        assert recs, "401 未被请求日志记录（中间件顺序错误）"
