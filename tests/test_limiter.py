"""ask 端点配额测试：并发信号量 + 分钟级滑窗限流（假时钟 + TestClient，零真实调用）。"""
import threading
import time

import pytest

from app import AskLimiter, _AskLimited


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, sec):
        self.now += sec


class TestAskLimiterUnit:
    def test_acquire_release_basic(self):
        lim = AskLimiter(max_concurrent=2, per_min=5, queue_timeout=0.1)
        lim.acquire()
        lim.acquire()
        lim.release()
        lim.release()

    def test_rate_limit_raises_with_retry_after(self):
        clock = FakeClock()
        lim = AskLimiter(max_concurrent=5, per_min=2, queue_timeout=0.1, clock=clock)
        lim.acquire()
        lim.acquire()
        with pytest.raises(_AskLimited) as ei:
            lim.acquire()
        assert ei.value.retry_after > 0
        assert "频繁" in str(ei.value)

    def test_sliding_window_expires(self):
        """窗口内最早的请求过期后，配额立即恢复（假时钟推进 61 秒）。"""
        clock = FakeClock()
        lim = AskLimiter(max_concurrent=5, per_min=2, queue_timeout=0.1, clock=clock)
        lim.acquire()
        lim.acquire()
        clock.advance(61)
        lim.acquire()  # 不抛即恢复
        lim.release()
        lim.release()
        lim.release()

    def test_partial_expiry(self):
        """只过期最早的一条：per_min=2 时放出 1 个名额。"""
        clock = FakeClock()
        lim = AskLimiter(max_concurrent=5, per_min=2, queue_timeout=0.1, clock=clock)
        lim.acquire()
        clock.advance(30)
        lim.acquire()
        clock.advance(31)  # 第一条过期（61s 前），第二条仍在窗口内
        lim.acquire()  # 成功
        with pytest.raises(_AskLimited):
            lim.acquire()  # 窗口内又满 2 条

    def test_concurrency_timeout_raises(self):
        """信号量占满且排队超时 → 429 语义异常。"""
        lim = AskLimiter(max_concurrent=1, per_min=10, queue_timeout=0.05)
        lim.acquire()  # 主线程占住唯一执行权

        err = []

        def _worker():
            try:
                lim.acquire()
            except _AskLimited as e:
                err.append(e)

        t = threading.Thread(target=_worker)
        t.start()
        t.join(timeout=2)
        assert err and "排队的问答已满" in str(err[0])
        lim.release()

    def test_release_frees_slot(self):
        lim = AskLimiter(max_concurrent=1, per_min=10, queue_timeout=0.05)
        lim.acquire()
        lim.release()
        lim.acquire()  # 释放后可再获取
        lim.release()

    def test_reset_clears_window(self):
        clock = FakeClock()
        lim = AskLimiter(max_concurrent=5, per_min=1, queue_timeout=0.1, clock=clock)
        lim.acquire()
        lim.release()
        with pytest.raises(_AskLimited):
            lim.acquire()
        lim.reset()
        lim.acquire()  # 重置后恢复
        lim.release()

    def test_invalid_limits_clamped(self):
        """0/负值是配置事故——钳到至少 1，绝不变成 0 并发（全线 429）或负数。"""
        lim = AskLimiter(max_concurrent=0, per_min=0, queue_timeout=0.1)
        lim.acquire()  # max(1,0)=1
        lim.release()
        with pytest.raises(_AskLimited):
            lim.acquire()  # per_min 钳到 1：第二次必超限
            lim.acquire()


class TestAskLimiterEndpoint:
    def test_rate_limited_429_with_retry_after(self, client, stub_ask, monkeypatch):
        import app as app_module
        monkeypatch.setattr(app_module, "ask_limiter",
                            AskLimiter(max_concurrent=2, per_min=1, queue_timeout=0.1))
        r1 = client.post("/api/ask", json={"query": "第一问"})
        assert r1.status_code == 200
        r2 = client.post("/api/ask", json={"query": "第二问"})
        assert r2.status_code == 429
        assert "Retry-After" in r2.headers
        assert int(r2.headers["Retry-After"]) >= 1
        assert "频繁" in r2.json()["detail"]

    def test_concurrency_limited_429(self, client, stub_ask, monkeypatch):
        import app as app_module
        lim = AskLimiter(max_concurrent=1, per_min=10, queue_timeout=0.1)
        monkeypatch.setattr(app_module, "ask_limiter", lim)
        lim.acquire()  # 外部占住唯一执行权（模拟另一个请求正在生成）
        r = client.post("/api/ask", json={"query": "q"})
        assert r.status_code == 429
        assert "排队" in r.json()["detail"]
        lim.release()

    def test_other_endpoints_not_limited(self, client, monkeypatch):
        """配额只闸 ask；status 等廉价端点在任何限额下都可用。"""
        import app as app_module
        monkeypatch.setattr(app_module, "ask_limiter",
                            AskLimiter(max_concurrent=1, per_min=1, queue_timeout=0.1))
        assert client.get("/api/status").status_code == 200
