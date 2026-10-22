"""F4 记忆查看/删除/导出：零真实调用测试（Mem0 由 conftest stub 替代）。"""
import pytest


class TestMemoryEndpoints:
    def test_profile_has_memory_items(self, client):
        r = client.get("/api/profile")
        assert r.status_code == 200
        d = r.json()
        assert "memory_items" in d  # 删除/导出依赖的带 id 结构
        assert isinstance(d["memory_items"], list)

    def test_export_returns_items(self, client):
        r = client.get("/api/memory/export")
        assert r.status_code == 200
        assert "items" in r.json()
        assert r.json()["count"] == len(r.json()["items"])

    def test_delete_cache_memory(self, client):
        # conftest stub 的 cache: 删除：先确认无则 404，这里直接打删除接口验证路径
        r = client.delete("/api/memory/cache:999")
        assert r.status_code == 404  # 越界索引删除失败 → 404

    def test_delete_unknown_returns_404(self, client):
        r = client.delete("/api/memory/not-a-real-id")
        assert r.status_code in (404,)  # stub 仅支持 cache: 前缀，其余 404

    def test_delete_real_id_path(self, client, monkeypatch):
        import app as app_module

        calls = {}

        def _fake_delete(mem_id, user_id="default"):
            calls["id"] = mem_id
            return True

        monkeypatch.setattr(app_module.engine.memory, "delete_memory", _fake_delete)
        r = client.delete("/api/memory/" + "abc-123")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert calls["id"] == "abc-123"
