"""F1 SSE 流式输出：零真实调用测试。

覆盖三层：dashscope.chat_stream 的 SSE 帧解析、engine.ask_stream 事件协议、
app /api/ask/stream 端到端（真实引擎 + 网络函数打桩）。
"""
import json
import re

import pytest


# —————————————————————————————————————————————— #
# 1) dashscope.chat_stream：SSE 帧解析（心跳/空 delta/结束帧）
# —————————————————————————————————————————————— #
class TestChatStreamParse:
    def test_parses_deltas_and_skips_noise(self, monkeypatch):
        sse_lines = [
            ": keep-alive",                                   # 注释行跳过
            'data: {"choices":[{"delta":{"content":"你好"}}]}',
            'data: {"choices":[{"delta":{"content":""}}]}',   # 空 delta 跳过
            'data: {"choices":[{"delta":{"content":"世界"}}]}',
            'data: [DONE]',
        ]

        class _FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def raise_for_status(self):
                return None

            def iter_lines(self, decode_unicode=False):
                return iter(sse_lines)

        import pypedia.models.dashscope as ds

        monkeypatch.setattr(ds.requests, "post", lambda *a, **k: _FakeResp())
        out = "".join(ds.chat_stream([{"role": "user", "content": "hi"}]))
        assert out == "你好世界"


# —————————————————————————————————————————————— #
# 2) engine.ask_stream：事件协议 meta → chunk* → done（记忆/置信度/二审仍执行）
# —————————————————————————————————————————————— #
class TestEngineAskStream:
    def test_event_sequence_and_join(self, monkeypatch):
        import pypedia.engine as eng

        def _fake_stream(messages, **kw):
            yield "甲"
            yield "乙"
            yield "丙"

        monkeypatch.setattr(eng, "bailian_chat_stream", _fake_stream)
        monkeypatch.setattr(eng, "bailian_chat", lambda *a, **k: "x")  # 分步思路兜底
        monkeypatch.setattr(eng, "evaluate_confidence",
                            lambda *a, **k: {"score": 60, "level": "中",
                                             "level_label": "中", "reason": "",
                                             "breakdown": {}})
        monkeypatch.setattr(eng, "review_answer",
                            lambda *a, **k: {"verdict": "pass", "notes": [],
                                             "revised": "", "skipped": False})
        e = eng.PyPediaEngine(provider="mock")
        evs = list(e.ask_stream("什么是装饰器？", level=3))
        kinds = [k for k, _ in evs]
        assert kinds[0] == "meta"
        assert kinds[-1] == "done"
        chunks = [p["text"] for k, p in evs if k == "chunk"]
        assert "".join(chunks) == "甲乙丙"
        done = [p for k, p in evs if k == "done"][0]
        assert done["answer"] == "甲乙丙"
        assert done["confidence"]["score"] == 60
        assert done["review"]["verdict"] == "pass"

    def test_partial_failure_propagates(self, monkeypatch):
        """已吐出部分答案后失败 → 必须抛（半截答案降级会留拼接痕迹）。"""
        import pypedia.engine as eng

        def _fake_stream(messages, **kw):
            yield "甲"
            raise RuntimeError("stream died")

        monkeypatch.setattr(eng, "bailian_chat_stream", _fake_stream)
        monkeypatch.setattr(eng, "evaluate_confidence",
                            lambda *a, **k: {"score": 50, "level": "低",
                                             "level_label": "低", "reason": "",
                                             "breakdown": {}})
        monkeypatch.setattr(eng, "review_answer",
                            lambda *a, **k: {"verdict": "skipped", "notes": [],
                                             "revised": "", "skipped": True})
        e = eng.PyPediaEngine(provider="mock")
        with pytest.raises(RuntimeError):
            list(e.ask_stream("q", level=3))


# —————————————————————————————————————————————— #
# 3) app /api/ask/stream：端到端（真实引擎 + 网络函数打桩，零额度消耗）
# —————————————————————————————————————————————— #
class TestAppStreamEndpoint:
    def test_stream_end_to_end(self, client, monkeypatch):
        import pypedia.engine as eng

        monkeypatch.setattr(eng, "bailian_chat_stream",
                            lambda *a, **k: iter(["逐", "字", "到", "达"]))
        monkeypatch.setattr(eng, "bailian_chat", lambda *a, **k: "x")
        monkeypatch.setattr(eng, "evaluate_confidence",
                            lambda *a, **k: {"score": 61, "level": "中",
                                             "level_label": "中", "reason": "",
                                             "breakdown": {}})
        monkeypatch.setattr(eng, "review_answer",
                            lambda *a, **k: {"verdict": "pass", "notes": [],
                                             "revised": "", "skipped": False})
        r = client.post("/api/ask/stream", json={"query": "q", "level": 3})
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        body = r.text
        assert "event: meta" in body and "event: chunk" in body and "event: done" in body
        texts = re.findall(r'event: chunk\ndata: (\{.*\})', body)
        assert "".join(json.loads(t)["text"] for t in texts) == "逐字到达"
        done = re.search(r'event: done\ndata: (\{.*\})', body)
        assert done and json.loads(done.group(1))["confidence"]["score"] == 61

    def test_done_cascade_keeps_chunk_url(self, client, monkeypatch):
        """F5 引用溯源数据通路：done.cascade 的 chunk 必须带 url，前端才能跳转原文。"""
        import pypedia.engine as eng

        monkeypatch.setattr(eng, "bailian_chat_stream", lambda *a, **k: iter(["a"]))
        monkeypatch.setattr(eng, "bailian_chat", lambda *a, **k: "x")
        monkeypatch.setattr(eng, "evaluate_confidence",
                            lambda *a, **k: {"score": 60, "level": "中",
                                             "level_label": "中", "reason": "",
                                             "breakdown": {}})
        monkeypatch.setattr(eng, "review_answer",
                            lambda *a, **k: {"verdict": "pass", "notes": [],
                                             "revised": "", "skipped": False})
        r = client.post("/api/ask/stream", json={"query": "装饰器", "level": 3})
        done = re.search(r'event: done\ndata: (\{.*\})', r.text)
        cascade = json.loads(done.group(1))["cascade"]
        urls = [c["url"] for s in cascade["stages"] for c in s["chunks"] if c.get("url")]
        assert urls, "done.cascade 至少应含一个带 url 的 chunk（引用溯源依赖）"

    def test_empty_query_400(self, client):
        assert client.post("/api/ask/stream", json={"query": ""}).status_code == 400

    def test_engine_error_ends_as_event(self, client, monkeypatch):
        """流已开始后的引擎异常 → error 事件收尾，HTTP 不崩。"""
        import app as app_module
        import pypedia.engine as eng

        def _boom(query, level=3, session=None):
            yield "meta", {"session_id": "s", "level": {"n": "L3"}, "provider": "mock"}
            raise RuntimeError("engine boom")

        monkeypatch.setattr(eng, "bailian_chat_stream", lambda *a, **k: iter([]))
        monkeypatch.setattr(eng, "evaluate_confidence",
                            lambda *a, **k: {"score": 50, "level": "低",
                                             "level_label": "低", "reason": "",
                                             "breakdown": {}})
        monkeypatch.setattr(eng, "review_answer",
                            lambda *a, **k: {"verdict": "skipped", "notes": [],
                                             "revised": "", "skipped": True})
        app_module.engine.ask_stream = _boom  # 实例属性替换（无需 self）
        r = client.post("/api/ask/stream", json={"query": "q"})
        assert r.status_code == 200
        assert "event: error" in r.text
        assert "生成答案" in r.text
