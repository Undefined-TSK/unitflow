"""capabilities 测试：settings 开关回归（os.getenv bug 不复弹）+ 无占位虚条目。"""
import pytest

from pypedia.capabilities import CAPABILITIES, capabilities
from pypedia.config import settings


class TestProtocolCapabilities:
    def test_exactly_five_real_entries(self):
        """协议层只登记有真实代码路径的能力（无占位虚条目）。"""
        keys = {c.key for c in CAPABILITIES}
        assert keys == {"mcp_fetch", "mcp_filesystem", "mcp_thinking",
                        "answer_review", "ollama_local"}

    def test_review_follows_settings_not_getenv(self, monkeypatch):
        """回归：REVIEW_ENABLE 必须走 settings——.env 未显式写时 os.getenv 返回 None
        会被误判为关闭（2026-10 真实 bug）。"""
        monkeypatch.setattr(settings, "REVIEW_ENABLE", True)
        assert capabilities.enabled("answer_review") is True
        monkeypatch.setattr(settings, "REVIEW_ENABLE", False)
        assert capabilities.enabled("answer_review") is False

    def test_ollama_follows_provider(self, monkeypatch):
        """回归：Ollama 通道开关是 LLM_PROVIDER，不是死环境变量 PYPEDIA_OLLAMA。"""
        monkeypatch.setattr(settings, "LLM_PROVIDER", "bailian")
        assert capabilities.enabled("ollama_local") is False
        monkeypatch.setattr(settings, "LLM_PROVIDER", "ollama")
        assert capabilities.enabled("ollama_local") is True

    def test_mcp_items_check_real_connection(self, monkeypatch):
        """MCP 项查真实连接状态，不是读开关了事。"""
        import pypedia.capabilities as cap_mod

        monkeypatch.setattr(cap_mod, "_mcp_status",
                            lambda: {"fetch": {"connected": True}})
        assert capabilities.enabled("mcp_fetch") is True
        assert capabilities.enabled("mcp_filesystem") is False  # 未连接

    def test_describe_shape(self):
        out = capabilities.describe()
        assert len(out) == 5
        for item in out:
            assert {"key", "name", "layer", "enabled", "env", "how", "fallback"} <= set(item)
            if item["key"].startswith("mcp_"):
                assert "mcp" in item  # MCP 项附带真实状态

    def test_describe_has_no_fake_names(self):
        """描述文本不得再出现已删除的占位名。"""
        blob = str(capabilities.describe())
        for fake in ("A2A", "子代理", "Skill 注册", "PYPEDIA_"):
            assert fake not in blob


class TestModelRegistry:
    def test_name_env_override(self, monkeypatch):
        from pypedia.models.registry import registry
        monkeypatch.setenv("BAILIAN_MODEL", "qwen-max")
        assert registry.name("chat") == "qwen-max"

    def test_name_default_without_env(self, monkeypatch):
        from pypedia.models.registry import registry
        monkeypatch.delenv("BAILIAN_MODEL", raising=False)
        assert registry.name("chat") == "qwen-plus"

    def test_describe_lists_eleven(self):
        from pypedia.models.registry import registry
        out = registry.describe()
        assert len(out) == 11
        keys = {m["key"] for m in out}
        assert {"embed", "chat", "rerank", "decision", "code", "math",
                "vision", "t2i", "tts", "asr", "embed_v4"} == keys

    def test_resolve_fallback_chain(self, monkeypatch):
        from pypedia.models.registry import registry
        # decision 未开通 → 沿 fallback 链落到 chat
        monkeypatch.setattr(registry, "status", lambda k: "active" if k == "chat" else "pending")
        assert registry.resolve("decision") == "chat"

    def test_resolve_active_direct(self, monkeypatch):
        from pypedia.models.registry import registry
        monkeypatch.setattr(registry, "status", lambda k: "active")
        assert registry.resolve("rerank") == "rerank"

    def test_unknown_key_raises(self):
        from pypedia.models.registry import registry
        with pytest.raises(KeyError):
            registry.name("不存在的能力")
