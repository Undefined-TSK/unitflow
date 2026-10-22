"""记忆层测试：qdrant 本地模式配置契约 + 存储往返 + chroma→qdrant 迁移（零真实调用）。

conftest 已将 PYPEDIA_DATA 隔离到临时目录，qdrant/chroma 数据不会落真实家目录。
"""
import uuid

import pytest

from pypedia.memory_store import _mem0_config
from pypedia import memory_migrate


class TestMem0Config:
    def test_qdrant_local_provider(self):
        """2026-10 架构统一：记忆层向量库必须是 qdrant 本地模式（零服务进程）。"""
        vs = _mem0_config()["vector_store"]
        assert vs["provider"] == "qdrant"
        assert vs["config"]["on_disk"] is True
        assert vs["config"]["embedding_model_dims"] == 1024

    def test_path_under_data_dir(self):
        from pypedia.memory_store import DATA_DIR
        path = _mem0_config()["vector_store"]["config"]["path"]
        assert path == str(DATA_DIR / "mem0_qdrant")

    def test_config_validates_against_mem0_schema(self):
        """配置必须通过 mem0 的 QdrantConfig 校验（无多余字段，本地模式合法）。"""
        from mem0.configs.vector_stores.qdrant import QdrantConfig
        cfg = QdrantConfig(**_mem0_config()["vector_store"]["config"])
        assert cfg.path and cfg.on_disk is True

    def test_llm_and_embedder_use_bailian(self):
        cfg = _mem0_config()
        assert cfg["llm"]["provider"] == "openai"
        assert cfg["embedder"]["config"]["embedding_dims"] == 1024


class TestQdrantLocalStore:
    """mem0 的 qdrant 本地模式存储往返（假向量，零 API 调用）。"""

    def _store(self, tmp_path, name="pypedia_test_mem0"):
        from mem0.vector_stores.qdrant import Qdrant
        return Qdrant(collection_name=name, path=str(tmp_path / "qd"),
                      embedding_model_dims=4, on_disk=True)

    def test_insert_search_delete_roundtrip(self, tmp_path):
        store = self._store(tmp_path)
        mid = str(uuid.uuid4())
        store.insert(
            vectors=[[0.1, 0.2, 0.3, 0.4]],
            payloads=[{"data": "用户是 Python 初学者", "user_id": "default"}],
            ids=[mid],
        )
        res = store.search(query="Python", vectors=[0.1, 0.2, 0.3, 0.4], top_k=1)
        assert res and res[0].payload["data"] == "用户是 Python 初学者"
        store.delete(mid)
        res2 = store.search(query="Python", vectors=[0.1, 0.2, 0.3, 0.4], top_k=1)
        assert not res2

    def test_user_isolation_filter(self, tmp_path):
        store = self._store(tmp_path, name="pypedia_test_iso")
        store.insert(
            vectors=[[0.1, 0.2, 0.3, 0.4], [0.4, 0.3, 0.2, 0.1]],
            payloads=[{"data": "A 的记忆", "user_id": "alice"},
                      {"data": "B 的记忆", "user_id": "bob"}],
            ids=[str(uuid.uuid4()), str(uuid.uuid4())],
        )
        res = store.search(query="x", vectors=[0.1, 0.2, 0.3, 0.4], top_k=5,
                           filters={"user_id": "bob"})
        assert len(res) == 1 and res[0].payload["user_id"] == "bob"

    def test_persist_across_reopen(self, tmp_path):
        """落盘持久化：关闭后重开，数据仍在（跨会话记忆的前提）。"""
        store = self._store(tmp_path, name="pypedia_test_persist")
        store.insert(vectors=[[0.5, 0.5, 0.5, 0.5]],
                     payloads=[{"data": "持久记忆", "user_id": "default"}],
                     ids=[str(uuid.uuid4())])
        del store
        store2 = self._store(tmp_path, name="pypedia_test_persist")
        res = store2.search(query="x", vectors=[0.5, 0.5, 0.5, 0.5], top_k=1)
        assert res and res[0].payload["data"] == "持久记忆"


class TestChromaMigration:
    def _fake_memory(self, monkeypatch, old_items, new_items):
        """桩 mem0.Memory：记录 from_config 调用与 add 调用。"""
        calls = {"old_cfg": None, "new_cfg": None, "adds": []}
        instances = []

        class _Mem:
            def __init__(self, cfg):
                instances.append(cfg)
                calls["old_cfg" if cfg["vector_store"]["provider"] == "chroma" else "new_cfg"] = cfg
                self._which = cfg["vector_store"]["provider"]

            @staticmethod
            def from_config(cfg):
                return _Mem(cfg)

            def get_all(self, filters=None, **kw):
                return {"results": old_items if self._which == "chroma" else new_items}

            def add(self, messages=None, user_id=None, infer=True, **kw):
                calls["adds"].append({"text": messages[0]["content"],
                                      "user_id": user_id, "infer": infer})

        import pypedia.memory_migrate as mm
        monkeypatch.setattr(mm, "Memory", _Mem)
        return calls

    def test_no_chroma_dir_skips(self, monkeypatch, tmp_path):
        monkeypatch.setattr(memory_migrate, "CHROMA_DIR", tmp_path / "nonexistent")
        r = memory_migrate.migrate()
        assert r["status"] == "skipped"
        assert "无需迁移" in r["detail"]

    def test_no_api_key_errors(self, monkeypatch, tmp_path):
        from pypedia.config import settings
        monkeypatch.setattr(settings, "BAILIAN_API_KEY", "")
        chroma_dir = tmp_path / "mem0_chroma"
        chroma_dir.mkdir()
        monkeypatch.setattr(memory_migrate, "CHROMA_DIR", chroma_dir)
        r = memory_migrate.migrate()
        assert r["status"] == "error"
        assert "API Key" in r["detail"]

    def test_full_migration_infer_false(self, monkeypatch, tmp_path):
        from pypedia.config import settings
        monkeypatch.setattr(settings, "BAILIAN_API_KEY", "test-key-for-ci")
        monkeypatch.setattr(memory_migrate, "CHROMA_DIR", tmp_path / "mem0_chroma")
        (tmp_path / "mem0_chroma").mkdir()
        calls = self._fake_memory(monkeypatch,
                                  old_items=[{"memory": "用户学过 Java"},
                                             {"memory": "对装饰器有卡点"}],
                                  new_items=[])
        r = memory_migrate.migrate()
        assert r["status"] == "ok"
        assert r["migrated"] == 2 and r["total"] == 2
        # 原文直存：infer=False（不再走 LLM 抽取）
        assert [c["text"] for c in calls["adds"]] == ["用户学过 Java", "对装饰器有卡点"]
        assert all(c["infer"] is False for c in calls["adds"])
        # 旧配置读 chroma、新配置写 qdrant
        assert calls["old_cfg"]["vector_store"]["provider"] == "chroma"
        assert calls["new_cfg"]["vector_store"]["provider"] == "qdrant"

    def test_already_migrated_skips(self, monkeypatch, tmp_path):
        from pypedia.config import settings
        monkeypatch.setattr(settings, "BAILIAN_API_KEY", "test-key-for-ci")
        monkeypatch.setattr(memory_migrate, "CHROMA_DIR", tmp_path / "mem0_chroma")
        (tmp_path / "mem0_chroma").mkdir()
        self._fake_memory(monkeypatch, old_items=[{"memory": "x"}],
                          new_items=[{"memory": "已存在"}])
        r = memory_migrate.migrate()
        assert r["status"] == "skipped"
        assert "已迁移" in r["detail"]

    def test_chromadb_missing_gives_hint(self, monkeypatch, tmp_path):
        """chromadb 未装时给出可操作提示而非堆栈。"""
        from pypedia.config import settings
        monkeypatch.setattr(settings, "BAILIAN_API_KEY", "test-key-for-ci")
        monkeypatch.setattr(memory_migrate, "CHROMA_DIR", tmp_path / "mem0_chroma")
        (tmp_path / "mem0_chroma").mkdir()

        def _boom(cfg):
            raise ImportError("No module named 'chromadb'")

        import pypedia.memory_migrate as mm

        class _MemFactory:
            @staticmethod
            def from_config(cfg):
                _boom(cfg)

        monkeypatch.setattr(mm, "Memory", _MemFactory)
        r = memory_migrate.migrate()
        assert r["status"] == "error"
        assert "chromadb 未安装" in r["detail"]


class TestMemoryStoreDegraded:
    def test_no_key_degrades_gracefully(self, monkeypatch):
        """无密钥：降级为无记忆模式，所有方法不崩。"""
        from pypedia.config import settings
        from pypedia.memory_store import MemoryStore
        monkeypatch.setattr(settings, "BAILIAN_API_KEY", "")
        ms = MemoryStore()
        assert ms._ready is False
        ms.observe("什么是装饰器", 3, 80.0, "装饰器是…")  # 不崩、不起线程
        assert ms.search_memory("装饰器") == []
        prof = ms.get_profile()
        assert prof["interactions"] == 1  # JSON 画像仍可用
        assert prof["memories"] == []
