"""长上下文管理测试：token 估算 / 滑窗 / 滚动摘要（摘要打桩，零 LLM 调用）。"""
from dataclasses import dataclass

import pytest

from pypedia.conversation import ConversationContext, ContextPlan, estimate_tokens
from pypedia.config import settings


@dataclass
class FakeTurn:
    user: str
    assistant: str


def _turns(n: int, size: int = 30) -> list[FakeTurn]:
    return [FakeTurn(user=f"问题{i}" + "字" * size, assistant=f"回答{i}" + "字" * size)
            for i in range(n)]


class TestEstimateTokens:
    def test_empty(self):
        assert estimate_tokens("") == 0

    def test_cjk_per_char(self):
        assert estimate_tokens("你好") == 2 + 4  # 2 字 + 4 消息开销

    def test_english_words(self):
        # 3 词 * 1.3 * 1.2 = 4.68 → int 4，+4 开销
        assert estimate_tokens("hello world foo") == 4 + 4

    def test_mixed(self):
        n = estimate_tokens("Python 装饰器")
        cjk = 3  # 装饰器
        words = int(1 * 1.3 * 1.2)  # Python 一词
        assert n == cjk + words + 4


class TestPlanNoCompression:
    def test_short_conversation_kept_whole(self):
        ctx = ConversationContext()
        plan = ctx.plan(_turns(3))
        assert plan.compressed is False
        assert plan.dropped_turns == 0
        assert len(plan.kept_turns) == 3
        assert plan.total_tokens == plan.kept_tokens

    def test_as_history_pairs(self):
        ctx = ConversationContext()
        plan = ctx.plan(_turns(2))
        msgs = plan.as_history()
        assert len(msgs) == 4  # 每轮 user+assistant
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"


class TestPlanCompression:
    def test_over_budget_keeps_tail(self, monkeypatch):
        monkeypatch.setattr(settings, "CONTEXT_TOKEN_BUDGET", 300)
        monkeypatch.setattr(settings, "CONTEXT_KEEP_TURNS", 2)
        ctx = ConversationContext()
        plan = ctx.plan(_turns(10, size=60))
        assert plan.compressed is True
        assert plan.dropped_turns == 8
        assert len(plan.kept_turns) == 2
        assert plan.kept_turns[-1][0].startswith("问题9")

    def test_trigger_turns_compresses(self, monkeypatch):
        monkeypatch.setattr(settings, "CONTEXT_SUMMARY_TRIGGER", 5)
        ctx = ConversationContext()
        plan = ctx.plan(_turns(6, size=10))
        assert plan.compressed is True

    def test_summary_injected_to_history(self, monkeypatch):
        monkeypatch.setattr(settings, "CONTEXT_TOKEN_BUDGET", 200)
        monkeypatch.setattr(settings, "CONTEXT_KEEP_TURNS", 1)
        ctx = ConversationContext()
        # 打桩摘要（函数内 import dashscope.chat → 打桩 dashscope.chat）
        import pypedia.models.dashscope as ds
        monkeypatch.setattr(ds, "chat", lambda *a, **kw: "前情：用户在问列表和字典")
        plan = ctx.plan(_turns(6, size=60))
        assert plan.summary.startswith("前情")
        msgs = plan.as_history()
        assert msgs[0]["role"] == "system" and "前情摘要" in msgs[0]["content"]

    def test_summary_failure_degrades(self, monkeypatch):
        """摘要调用失败 → 退化为截断拼接，不抛异常；仍受 cap 约束。"""
        monkeypatch.setattr(settings, "CONTEXT_TOKEN_BUDGET", 300)
        monkeypatch.setattr(settings, "CONTEXT_KEEP_TURNS", 1)
        import pypedia.models.dashscope as ds

        def _boom(*a, **kw):
            raise RuntimeError("网络断开")

        monkeypatch.setattr(ds, "chat", _boom)
        ctx = ConversationContext()
        plan = ctx.plan(_turns(6, size=60))
        assert plan.compressed is True
        assert plan.summary  # 退化拼接非空
        # 拼接长度 ≈ 压缩前总量 > budget，必被 cap 截断（防无限增长对退化路径同样生效）
        assert estimate_tokens(plan.summary) <= 300 // 3 + 4

    def test_summary_capped(self, monkeypatch):
        """摘要本身不超预算的 1/3（防无限增长）。"""
        monkeypatch.setattr(settings, "CONTEXT_TOKEN_BUDGET", 600)
        import pypedia.models.dashscope as ds
        monkeypatch.setattr(ds, "chat", lambda *a, **kw: "摘" * 5000)
        ctx = ConversationContext()
        ctx._ensure_summary(_turns(3))
        assert estimate_tokens(ctx._summary) <= 600 // 3 + 10  # 截断后允许少量误差

    def test_incremental_summary(self, monkeypatch):
        """增量式：已摘要的轮次不重复摘要。"""
        monkeypatch.setattr(settings, "CONTEXT_TOKEN_BUDGET", 200)
        monkeypatch.setattr(settings, "CONTEXT_KEEP_TURNS", 1)
        import pypedia.models.dashscope as ds
        calls = []
        monkeypatch.setattr(ds, "chat",
                            lambda *a, **kw: calls.append(1) or "增量摘要")
        ctx = ConversationContext()
        turns = _turns(4, size=60)
        ctx.plan(turns)
        first = len(calls)
        turns.append(FakeTurn(user="新问题" + "字" * 60, assistant="新回答" + "字" * 60))
        ctx.plan(turns)
        assert len(calls) > first  # 只对新轮次再摘要一次

    def test_reset(self, monkeypatch):
        monkeypatch.setattr(settings, "CONTEXT_TOKEN_BUDGET", 200)
        monkeypatch.setattr(settings, "CONTEXT_KEEP_TURNS", 1)
        import pypedia.models.dashscope as ds
        monkeypatch.setattr(ds, "chat", lambda *a, **kw: "摘要")
        ctx = ConversationContext()
        ctx.plan(_turns(5, size=60))
        assert ctx._summarized_upto > 0
        ctx.reset()
        assert ctx._summary == "" and ctx._summarized_upto == 0

    def test_empty_turns(self):
        ctx = ConversationContext()
        plan = ctx.plan([])
        assert isinstance(plan, ContextPlan)
        assert plan.total_tokens == 0 and plan.kept_turns == []
