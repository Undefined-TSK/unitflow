"""MCPManager 生命周期测试：anyio BlockingPortal 桥（零真实调用、零子进程）。

覆盖 B3 铁律整改（手写线程桥 → anyio start_blocking_portal）：
- portal 起停闭环：start → call/status → close 不挂死、线程可 join；
- 调用经 portal.call 真正落在 portal loop 上执行（不是静默失败）；
- 超时与未连接统一降级 None（上层 ingest/engine 依赖该契约）。
"""
from __future__ import annotations

import asyncio
import time

import pytest

from pypedia import mcp_client
from pypedia.config import settings


class _FakeContent:
    def __init__(self, text: str):
        self.text = text


class _FakeResult:
    def __init__(self, text: str, is_error: bool = False):
        self.isError = is_error
        self.content = [_FakeContent(text)]


class _FakeStdio:
    """假 stdio 上下文管理器：记录 __aexit__ 是否被调用。"""

    def __init__(self):
        self.exited = False

    async def __aexit__(self, *exc):
        self.exited = True


def _fake_session(text="hello mcp", delay: float = 0.0, boom: bool = False):
    class _Session:
        async def call_tool(self, tool, args):
            if delay:
                await asyncio.sleep(delay)
            if boom:
                raise RuntimeError("session boom")
            return _FakeResult(f"{text}:{tool}")

    return _Session()


def _wait_portal(mgr: mcp_client.MCPManager, timeout: float = 3.0) -> None:
    """等宿主线程把 portal 挂上（_run_worker 首行）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if mgr._portal is not None:
            return
        time.sleep(0.01)
    raise AssertionError("portal 未在超时内就绪")


@pytest.fixture()
def mgr(monkeypatch):
    """空 spec 的 MCPManager：不 spawn 任何真实 server 子进程。"""
    monkeypatch.setattr(settings, "MCP_ENABLE", True)
    monkeypatch.setattr(mcp_client, "_specs", lambda: [])
    m = mcp_client.MCPManager()
    yield m
    m.close()


class TestPortalLifecycle:
    def test_start_call_status_close(self, mgr):
        mgr.start()
        _wait_portal(mgr)
        # 无 server 时：调用降级 None，状态为空列表（接口契约不变）
        assert mgr.call_tool("fetch", "fetch", {"url": "x"}) is None
        assert mgr.status() == []
        mgr.close()
        assert mgr._portal is None
        assert mgr._thread is not None and not mgr._thread.is_alive()

    def test_close_without_start_is_noop(self, monkeypatch):
        monkeypatch.setattr(settings, "MCP_ENABLE", False)
        m = mcp_client.MCPManager()
        m.close()  # 不得抛异常
        assert m._portal is None

    def test_call_runs_on_portal_loop(self, mgr):
        """注册假 session 后，call_tool 必须经 portal 真正执行并回传文本。"""
        mgr.start()
        _wait_portal(mgr)
        stdio = _FakeStdio()
        mgr._clients["fetch"] = (stdio, _fake_session(text="ok"))
        out = mgr.call_tool("fetch", "fetch", {"url": "https://example.com"})
        assert out == "ok:fetch", "portal.call 未在 portal loop 上执行协程"
        mgr.close()
        assert stdio.exited, "close 未退出 stdio 上下文（子进程会泄漏）"

    def test_call_timeout_degrades_to_none(self, mgr):
        mgr.start()
        _wait_portal(mgr)
        mgr._clients["fetch"] = (_FakeStdio(), _fake_session(delay=5.0))
        t0 = time.monotonic()
        assert mgr.call_tool("fetch", "fetch", {}, timeout=0.2) is None
        assert time.monotonic() - t0 < 2.0, "超时未生效（wait_for 未包住调用）"

    def test_call_error_degrades_to_none(self, mgr):
        mgr.start()
        _wait_portal(mgr)
        mgr._clients["fetch"] = (_FakeStdio(), _fake_session(boom=True))
        assert mgr.call_tool("fetch", "fetch", {}) is None

    def test_call_after_close_degrades_to_none(self, mgr):
        mgr.start()
        _wait_portal(mgr)
        mgr._clients["fetch"] = (_FakeStdio(), _fake_session())
        mgr.close()
        assert mgr.call_tool("fetch", "fetch", {}) is None
