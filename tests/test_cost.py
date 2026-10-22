"""F7 成本/token 面板：零真实调用测试（只读缓存文件 + 注册表，不触网）。"""
import pytest


class TestCostEndpoint:
    def test_cost_endpoint_shape(self, client, monkeypatch):
        import pypedia.embed_cache as ec

        monkeypatch.setattr(ec, "global_stats", lambda: {
            "rows": 12, "by_model": {"text-embedding-v4": 12},
            "estimated_saved_tokens": 1800, "cache_dir": "/tmp/x",
        })
        r = client.get("/api/cost")
        assert r.status_code == 200
        d = r.json()
        assert "embed_cache" in d and "models" in d and "provider" in d
        assert d["embed_cache"]["rows"] == 12
        assert d["models"]["chat"] and d["models"]["embed_v4"]

    def test_global_stats_no_db_returns_zero(self, monkeypatch):
        import pypedia.embed_cache as ec

        # 指向不存在的目录，应安全返回零值而非抛错
        monkeypatch.setenv("EMBED_CACHE_DIR", "/nonexistent_pypedia_cache_xyz")
        stats = ec.global_stats()
        assert stats["rows"] == 0
        assert stats["estimated_saved_tokens"] == 0
        assert isinstance(stats["by_model"], dict)
