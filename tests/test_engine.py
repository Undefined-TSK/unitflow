"""engine 全链路测试：LLM/置信度/记忆/MCP 全打桩（零真实调用）。"""
import pytest

from pypedia.config import settings
from pypedia.engine import PyPediaEngine
from pypedia.memory import Session


@pytest.fixture()
def engine():
    """构造引擎。MemoryStore/MCP 已在 conftest 顶层 stub 化。"""
    return PyPediaEngine(provider="mock")


class TestAskHappyPath:
    def test_full_flow(self, engine, fake_chat, fake_confidence, monkeypatch):
        monkeypatch.setattr("pypedia.engine.review_answer",
                            lambda *a, **kw: {"verdict": "pass", "notes": [],
                                              "revised": "", "skipped": False})
        r = engine.ask("什么是装饰器？", level=3)
        # 返回结构齐全
        assert r["query"] == "什么是装饰器？"
        assert r["answer"] and "打桩答案" in r["answer"]
        assert r["provider"] == "mock"
        assert r["level"]["t"] == "进阶"
        assert r["confidence"]["score"] == 72
        assert r["confidence"]["breakdown"]["primary_hit"] == 55
        assert r["review"]["verdict"] == "pass"
        assert r["cascade"] is not None
        assert set(r["context"]) >= {"compressed", "total_tokens", "kept_tokens"}
        assert r["multi_turn"] is False
        assert fake_chat.calls  # 生成确实发生

    def test_multi_turn_flag(self, engine, fake_chat, fake_confidence, monkeypatch):
        monkeypatch.setattr("pypedia.engine.review_answer",
                            lambda *a, **kw: {"verdict": "pass", "notes": [],
                                              "revised": "", "skipped": False})
        sess = Session(level=3)
        engine.ask("第一问", session=sess)
        r = engine.ask("第二问", session=sess)
        assert r["multi_turn"] is True
        assert len(sess.turns) == 2

    def test_review_revise_propagates(self, engine, fake_chat, fake_confidence,
                                      monkeypatch):
        monkeypatch.setattr("pypedia.engine.review_answer",
                            lambda *a, **kw: {"verdict": "revise", "notes": ["问题A"],
                                              "revised": "修订版答案", "skipped": False})
        r = engine.ask("Python 列表和字典的区别是什么？分别用在什么场景？")
        assert r["review"]["verdict"] == "revise"
        assert r["review"]["notes"] == ["问题A"]
        assert r["review"]["revised"] == "修订版答案"


class TestQueryTruncation:
    def test_overlong_query_truncated(self, engine, fake_chat, fake_confidence,
                                      monkeypatch):
        monkeypatch.setattr(settings, "MAX_QUERY_CHARS", 100)
        monkeypatch.setattr("pypedia.engine.review_answer",
                            lambda *a, **kw: {"verdict": "pass", "notes": [],
                                              "revised": "", "skipped": False})
        r = engine.ask("装" * 500)
        assert len(r["query"]) <= 101 + len("…（已截断）")
        assert "已截断" in r["query"]


class TestReasoningPlan:
    def test_complex_query_triggers_plan(self, engine, monkeypatch):
        """复杂问题（问号+对比词）→ 生成分步思路。"""
        calls = {"plan": 0}

        def _fake(messages, **kw):
            if "拆成" in messages[-1]["content"] or "步骤" in messages[0]["content"]:
                calls["plan"] += 1
                return "1. 先看定义\n2. 再对比差异\n3. 最后给场景"
            return "打桩答案"

        monkeypatch.setattr("pypedia.engine.bailian_chat", _fake)
        monkeypatch.setattr("pypedia.engine.evaluate_confidence",
                            lambda *a, **kw: {"score": 60, "level": "中", "level_label": "中",
                                              "reason": "", "breakdown": {}})
        monkeypatch.setattr("pypedia.engine.review_answer",
                            lambda *a, **kw: {"verdict": "pass", "notes": [],
                                              "revised": "", "skipped": False})
        r = engine.ask("列表和字典的区别是什么？分别在什么场景使用？")
        assert r["reasoning_plan"]
        assert "1." in r["reasoning_plan"]

    def test_simple_query_no_plan(self, engine, fake_chat, fake_confidence,
                                  monkeypatch):
        monkeypatch.setattr("pypedia.engine.review_answer",
                            lambda *a, **kw: {"verdict": "pass", "notes": [],
                                              "revised": "", "skipped": False})
        r = engine.ask("你好")
        assert r["reasoning_plan"] == ""  # 短且非复杂问题不触发

    def test_thinking_disabled_no_plan(self, engine, fake_chat, fake_confidence,
                                       monkeypatch):
        monkeypatch.setattr(settings, "MCP_THINKING_ENABLE", False)
        monkeypatch.setattr("pypedia.engine.review_answer",
                            lambda *a, **kw: {"verdict": "pass", "notes": [],
                                              "revised": "", "skipped": False})
        r = engine.ask("列表和字典的区别是什么？分别用在什么场景？")
        assert r["reasoning_plan"] == ""


class TestGenerationFallback:
    def test_llm_failure_degrades_to_mock(self, monkeypatch):
        """百炼调用失败 → Mock 兜底，流程不崩。"""
        eng = PyPediaEngine(provider="bailian")

        def _boom(*a, **kw):
            raise RuntimeError("quota exceeded")

        monkeypatch.setattr("pypedia.engine.bailian_chat", _boom)
        monkeypatch.setattr("pypedia.engine.evaluate_confidence",
                            lambda *a, **kw: {"score": 40, "level": "低", "level_label": "低",
                                              "reason": "", "breakdown": {}})
        monkeypatch.setattr("pypedia.engine.review_answer",
                            lambda *a, **kw: {"verdict": "skipped", "notes": [],
                                              "revised": "", "skipped": True})
        r = eng.ask("测试降级")
        assert "Mock" in r["answer"]  # MockLLM 兜底内容


class TestBuildSystem:
    def test_level_instruction_injected(self, engine):
        s1 = engine._build_system(1, "q")
        s5 = engine._build_system(5, "q")
        assert "L1" in s1 and "L5" in s5
        assert "比喻" in s1 and "CPython" in s5

    def test_visualization_contract_in_system(self, engine):
        """输出契约（mermaid/chart/公式）注入 system。"""
        s = engine._build_system(3, "q")
        assert "mermaid" in s
        assert "chart" in s
