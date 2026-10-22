"""LLM 调用重试测试：指数退避 + 状态码分流（requests 打桩，零真实调用）。

验证 _request_with_retry 契约：
- 网络错误（ConnectionError/Timeout）与 429/5xx：指数退避重试；
- 4xx 业务错误：立即抛，绝不重试（避免浪费配额）；
- chat / embed_texts / _rerank_raw 三条真实通路均走该封装。
"""
import pytest
import requests

from pypedia.models import dashscope


class _FakeResp:
    """最小 Response 替身：只暴露重试封装用到的接口。"""

    def __init__(self, payload=None, status=200):
        self._payload = payload if payload is not None else {"ok": True}
        self.status_code = status
        self.text = str(self._payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class _Counter:
    """记录调用次数 + 可按序列返回响应/抛异常。"""

    def __init__(self, script):
        self.script = list(script)  # 元素：_FakeResp 或 Exception 实例
        self.calls = 0

    def __call__(self, *a, **kw):
        item = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def no_sleep(monkeypatch):
    """拦截退避睡眠并记录序列——测试不真睡。"""
    seq = []
    monkeypatch.setattr(dashscope, "_sleep", lambda s: seq.append(s))
    return seq


def _post(monkeypatch, counter):
    monkeypatch.setattr(dashscope.requests, "post", counter)
    return counter


class TestRetryPolicy:
    def test_success_first_try(self, monkeypatch, no_sleep):
        c = _Counter([_FakeResp()])
        _post(monkeypatch, c)
        r = dashscope._request_with_retry("http://x", headers={}, json={})
        assert r.status_code == 200
        assert c.calls == 1
        assert no_sleep == []  # 成功不睡

    def test_network_error_retries_then_succeeds(self, monkeypatch, no_sleep):
        c = _Counter([requests.exceptions.ConnectionError("boom"),
                      requests.exceptions.ConnectionError("boom"),
                      _FakeResp()])
        _post(monkeypatch, c)
        r = dashscope._request_with_retry("http://x", headers={}, json={}, max_retries=3)
        assert c.calls == 3
        assert no_sleep == [1.0, 2.0]  # 指数退避序列

    def test_network_error_exhausted_raises(self, monkeypatch, no_sleep):
        c = _Counter([requests.exceptions.ConnectionError("boom")])
        _post(monkeypatch, c)
        with pytest.raises(requests.exceptions.ConnectionError):
            dashscope._request_with_retry("http://x", headers={}, json={}, max_retries=3)
        assert c.calls == 3
        assert no_sleep == [1.0, 2.0]  # 最后一次失败不再睡

    def test_timeout_is_retried(self, monkeypatch, no_sleep):
        c = _Counter([requests.exceptions.Timeout("slow"), _FakeResp()])
        _post(monkeypatch, c)
        r = dashscope._request_with_retry("http://x", headers={}, json={}, max_retries=2)
        assert c.calls == 2
        assert no_sleep == [1.0]

    def test_429_retried_then_succeeds(self, monkeypatch, no_sleep):
        c = _Counter([_FakeResp(status=429), _FakeResp(status=429), _FakeResp()])
        _post(monkeypatch, c)
        dashscope._request_with_retry("http://x", headers={}, json={}, max_retries=3)
        assert c.calls == 3
        assert no_sleep == [1.0, 2.0]

    @pytest.mark.parametrize("status", [500, 502, 503, 504])
    def test_5xx_retried(self, monkeypatch, no_sleep, status):
        c = _Counter([_FakeResp(status=status), _FakeResp()])
        _post(monkeypatch, c)
        dashscope._request_with_retry("http://x", headers={}, json={}, max_retries=2)
        assert c.calls == 2

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
    def test_4xx_not_retried(self, monkeypatch, no_sleep, status):
        """4xx 是业务错误（参数非法/无权限），重试无意义——立即抛。"""
        c = _Counter([_FakeResp(status=status)])
        _post(monkeypatch, c)
        with pytest.raises(requests.exceptions.HTTPError):
            dashscope._request_with_retry("http://x", headers={}, json={}, max_retries=3)
        assert c.calls == 1
        assert no_sleep == []

    def test_5xx_on_last_attempt_raises(self, monkeypatch, no_sleep):
        c = _Counter([_FakeResp(status=503)])
        _post(monkeypatch, c)
        with pytest.raises(requests.exceptions.HTTPError):
            dashscope._request_with_retry("http://x", headers={}, json={}, max_retries=3)
        assert c.calls == 3

    def test_max_retries_one_no_retry(self, monkeypatch, no_sleep):
        c = _Counter([_FakeResp(status=503)])
        _post(monkeypatch, c)
        with pytest.raises(requests.exceptions.HTTPError):
            dashscope._request_with_retry("http://x", headers={}, json={}, max_retries=1)
        assert c.calls == 1
        assert no_sleep == []

    def test_backoff_configurable(self, monkeypatch, no_sleep):
        c = _Counter([requests.exceptions.ConnectionError("x")] * 4 + [_FakeResp()])
        _post(monkeypatch, c)
        dashscope._request_with_retry("http://x", headers={}, json={},
                                      max_retries=5, backoff=0.5)
        assert no_sleep == [0.5, 1.0, 2.0, 4.0]

    def test_defaults_from_settings(self, monkeypatch, no_sleep):
        """不传参时用 settings.LLM_MAX_RETRIES（默认 3：2 次重试 + 1 次成功）。"""
        c = _Counter([_FakeResp(status=503), _FakeResp(status=503), _FakeResp()])
        _post(monkeypatch, c)
        r = dashscope._request_with_retry("http://x", headers={}, json={})
        assert c.calls == 3
        assert r.status_code == 200

    def test_zero_retries_clamped(self, monkeypatch, no_sleep):
        """max_retries=0 是非法值——钳到至少 1 次尝试，不死循环也不零调用。"""
        c = _Counter([_FakeResp()])
        _post(monkeypatch, c)
        dashscope._request_with_retry("http://x", headers={}, json={}, max_retries=0)
        assert c.calls == 1


class TestChatRetry:
    def test_chat_retries_on_503(self, monkeypatch, no_sleep):
        monkeypatch.setattr(dashscope, "_has_key", lambda: True)
        c = _Counter([_FakeResp(status=503),
                      _FakeResp({"choices": [{"message": {"content": "你好"}}]})])
        _post(monkeypatch, c)
        out = dashscope.chat([{"role": "user", "content": "hi"}])
        assert out == "你好"
        assert c.calls == 2

    def test_chat_no_retry_on_400(self, monkeypatch, no_sleep):
        monkeypatch.setattr(dashscope, "_has_key", lambda: True)
        c = _Counter([_FakeResp(status=400)])
        _post(monkeypatch, c)
        with pytest.raises(requests.exceptions.HTTPError):
            dashscope.chat([{"role": "user", "content": "hi"}])
        assert c.calls == 1


class TestEmbedRetry:
    def test_embed_retries_on_connection_error(self, monkeypatch, no_sleep):
        monkeypatch.setattr(dashscope, "_has_key", lambda: True)
        c = _Counter([requests.exceptions.ConnectionError("net"),
                      _FakeResp({"data": [{"index": 0, "embedding": [0.1, 0.2]}]})])
        _post(monkeypatch, c)
        out = dashscope.embed_texts(["a"])
        assert out == [[0.1, 0.2]]
        assert c.calls == 2

    def test_embed_batch_each_retried(self, monkeypatch, no_sleep):
        """分批（每批 ≤10）时每一批独立走重试。"""
        monkeypatch.setattr(dashscope, "_has_key", lambda: True)
        # 第一批 503 后成功，第二批直接成功
        seq = [_FakeResp(status=503),
               _FakeResp({"data": [{"index": 0, "embedding": [1.0]}]}),
               _FakeResp({"data": [{"index": 0, "embedding": [2.0]}]})]
        c = _Counter(seq)
        _post(monkeypatch, c)
        out = dashscope.embed_texts(["a", "b"], batch=1)
        assert out == [[1.0], [2.0]]
        assert c.calls == 3


class TestRerankRetry:
    def test_rerank_raw_retries_on_429(self, monkeypatch, no_sleep):
        monkeypatch.setattr(dashscope, "_has_key", lambda: True)
        c = _Counter([_FakeResp(status=429),
                      _FakeResp({"output": {"results": [
                          {"index": 0, "relevance_score": 0.9}]}})])
        _post(monkeypatch, c)
        res = dashscope._rerank_raw("q", ["a"], 1, "qwen3-rerank")
        assert res[0]["relevance_score"] == 0.9
        assert c.calls == 2
