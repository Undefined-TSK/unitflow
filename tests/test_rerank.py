"""rerank 测试：响应解析双路径 + 三级链降级（requests 打桩，零真实调用）。"""
import pytest

from pypedia.models import dashscope


class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.text = str(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class TestRerankRawParsing:
    def test_output_results_path(self, monkeypatch):
        """百炼实际结构：output.results（2026-10 实测修复项）。"""
        monkeypatch.setattr(dashscope.requests, "post", lambda *a, **kw: _FakeResp({
            "output": {"results": [
                {"index": 1, "relevance_score": 0.9},
                {"index": 0, "relevance_score": 0.2},
            ]}
        }))
        res = dashscope._rerank_raw("q", ["a", "b"], 2, "qwen3-rerank")
        assert res[0]["index"] == 1  # 已按分数降序
        assert res[0]["relevance_score"] > res[1]["relevance_score"]

    def test_data_rerank_legacy_path(self, monkeypatch):
        """兼容旧文档结构：data.rerank。"""
        monkeypatch.setattr(dashscope.requests, "post", lambda *a, **kw: _FakeResp({
            "data": {"rerank": [{"index": 0, "relevance_score": 0.5}]}
        }))
        res = dashscope._rerank_raw("q", ["a"], 1, "gte-rerank")
        assert res[0]["relevance_score"] == 0.5

    def test_bad_structure_raises(self, monkeypatch):
        monkeypatch.setattr(dashscope.requests, "post", lambda *a, **kw: _FakeResp({"foo": 1}))
        with pytest.raises(RuntimeError, match="结构异常"):
            dashscope._rerank_raw("q", ["a"], 1, "m")

    def test_http_error_propagates(self, monkeypatch):
        monkeypatch.setattr(dashscope.requests, "post",
                            lambda *a, **kw: _FakeResp({"error": "no permission"}, status=403))
        with pytest.raises(Exception):
            dashscope._rerank_raw("q", ["a"], 1, "m")


class TestRerankChain:
    def _active(self, monkeypatch):
        monkeypatch.setattr(dashscope, "_has_key", lambda: True)
        monkeypatch.setattr(dashscope.registry, "status", lambda k: "active")

    def test_cloud_first(self, monkeypatch):
        self._active(monkeypatch)
        monkeypatch.setattr(dashscope, "_rerank_raw",
                            lambda *a, **kw: [{"index": 0, "relevance_score": 0.9}])
        from pypedia import rerank_local
        called = []
        monkeypatch.setattr(rerank_local.reranker, "rank",
                            lambda *a, **kw: called.append(1) or [{"index": 0, "relevance_score": 0.1}])
        res = dashscope.rerank("q", ["a"])
        assert res[0]["relevance_score"] == 0.9
        assert not called  # 云端成功不走本地

    def test_cloud_fail_falls_local(self, monkeypatch):
        self._active(monkeypatch)

        def _boom(*a, **kw):
            raise RuntimeError("403")

        monkeypatch.setattr(dashscope, "_rerank_raw", _boom)
        from pypedia import rerank_local
        monkeypatch.setattr(rerank_local.reranker, "rank",
                            lambda *a, **kw: [{"index": 1, "relevance_score": 0.7}])
        res = dashscope.rerank("q", ["a", "b"])
        assert res[0]["index"] == 1

    def test_all_unavailable_raises(self, monkeypatch):
        """有 key 但云端未开通 + 本地模型未就绪 → 三级链耗尽抛错。"""
        monkeypatch.setattr(dashscope, "_has_key", lambda: True)
        monkeypatch.setattr(dashscope.registry, "status", lambda k: "pending")
        from pypedia import rerank_local
        monkeypatch.setattr(rerank_local.reranker, "rank", lambda *a, **kw: None)
        with pytest.raises(RuntimeError, match="重排不可用"):
            dashscope.rerank("q", ["a"])

    def test_no_key_raises_early(self, monkeypatch):
        monkeypatch.setattr(dashscope, "_has_key", lambda: False)
        with pytest.raises(RuntimeError, match="API Key"):
            dashscope.rerank("q", ["a"])
