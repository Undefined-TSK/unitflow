"""review 二审测试：六分支全覆盖（LLM 打桩，零真实调用）。"""
import pytest

from pypedia import review
from pypedia.config import settings


@pytest.fixture()
def stub_chat(monkeypatch):
    """打桩 pypedia.models.dashscope.chat（review_answer 函数内 import 的入口）。"""
    import pypedia.models.dashscope as ds

    state = {"reply": "", "raises": False, "calls": 0}

    def _fake(*a, **kw):
        state["calls"] += 1
        if state["raises"]:
            raise RuntimeError("network down")
        return state["reply"]

    monkeypatch.setattr(ds, "chat", _fake)
    return state


class TestReviewBranches:
    def test_disabled_skips(self, monkeypatch, stub_chat):
        monkeypatch.setattr(settings, "REVIEW_ENABLE", False)
        out = review.review_answer("q", "a", ["证据"])
        assert out["verdict"] == "skipped" and out["skipped"] is True
        assert stub_chat["calls"] == 0

    def test_no_evidence_skips(self, stub_chat):
        out = review.review_answer("q", "a", [])
        assert out["skipped"] is True
        assert stub_chat["calls"] == 0  # 无证据不硬审

    def test_empty_answer_skips(self, stub_chat):
        out = review.review_answer("q", "", ["证据"])
        assert out["skipped"] is True

    def test_pass(self, stub_chat):
        stub_chat["reply"] = '{"verdict": "pass", "notes": [], "revised": ""}'
        out = review.review_answer("q", "a", ["证据1", "证据2"])
        assert out["verdict"] == "pass"
        assert out["skipped"] is False
        assert stub_chat["calls"] == 1

    def test_revise_with_notes_and_revision(self, stub_chat):
        stub_chat["reply"] = (
            '{"verdict": "revise", "notes": ["虚构了数据", "引用了不存在的URL"],'
            ' "revised": "修订后的回答"}'
        )
        out = review.review_answer("q", "a", ["证据"])
        assert out["verdict"] == "revise"
        assert out["notes"] == ["虚构了数据", "引用了不存在的URL"]
        assert out["revised"] == "修订后的回答"

    def test_revise_without_revision_degrades_to_pass(self, stub_chat):
        """只有意见没有修订版 → 仅提示不替换。"""
        stub_chat["reply"] = '{"verdict": "revise", "notes": ["有问题"], "revised": ""}'
        out = review.review_answer("q", "a", ["证据"])
        assert out["verdict"] == "pass"
        assert out["notes"] == ["有问题"]

    def test_non_json_reply_skips(self, stub_chat):
        stub_chat["reply"] = "模型今天不想输出 JSON"
        out = review.review_answer("q", "a", ["证据"])
        assert out["skipped"] is True

    def test_exception_skips(self, stub_chat):
        stub_chat["raises"] = True
        out = review.review_answer("q", "a", ["证据"])
        assert out["skipped"] is True  # 审阅失败不影响主流程

    def test_notes_capped(self, stub_chat):
        stub_chat["reply"] = (
            '{"verdict": "revise", "notes": ["n1","n2","n3","n4","n5","n6","n7"],'
            ' "revised": "修订"}'
        )
        out = review.review_answer("q", "a", ["证据"])
        assert len(out["notes"]) <= 5  # 意见条数上限

    def test_revised_capped(self, stub_chat):
        stub_chat["reply"] = (
            '{"verdict": "revise", "notes": ["x"], "revised": "' + "修" * 9000 + '"}'
        )
        out = review.review_answer("q", "a", ["证据"])
        assert len(out["revised"]) <= 4000  # 修订版长度上限
