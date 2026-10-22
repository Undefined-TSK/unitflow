"""数据备份测试：导出白名单/排除 + 往返恢复 + 防 Zip Slip + API 端点（零真实调用）。"""
import io
import json
import shutil
import zipfile

import pytest

from pypedia import backup
from pypedia.memory_store import DATA_DIR


@pytest.fixture
def fake_data():
    """在隔离数据目录里构造一份假数据（含应被排除的令牌/日志/旧目录）。"""
    (DATA_DIR / "vector_lancedb").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "vector_lancedb" / "index.lance").write_bytes(b"fake-lancedb")
    (DATA_DIR / "mem0_qdrant").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "mem0_qdrant" / "meta.json").write_text('{"n":20}', encoding="utf-8")
    (DATA_DIR / "profile.json").write_text('{"default":{"level":3}}', encoding="utf-8")
    (DATA_DIR / "sources.json").write_text("[]", encoding="utf-8")
    # 应被排除的
    (DATA_DIR / "token").write_text("super-secret-token", encoding="utf-8")
    (DATA_DIR / "logs").mkdir(exist_ok=True)
    (DATA_DIR / "logs" / "pypedia.log").write_text("log line", encoding="utf-8")
    (DATA_DIR / "mem0_chroma").mkdir(exist_ok=True)
    (DATA_DIR / "mem0_chroma" / "old.bin").write_bytes(b"legacy")
    yield DATA_DIR


def _read_manifest(zip_path) -> dict:
    with zipfile.ZipFile(zip_path) as zf:
        return json.loads(zf.read(backup.MANIFEST).decode("utf-8"))


class TestExport:
    def test_whitelist_items_included(self, fake_data, tmp_path):
        r = backup.export(tmp_path / "b.zip")
        assert r["ok"]
        with zipfile.ZipFile(r["path"]) as zf:
            names = set(zf.namelist())
        assert "profile.json" in names
        assert "sources.json" in names
        assert "vector_lancedb/index.lance" in names
        assert "mem0_qdrant/meta.json" in names

    def test_secrets_and_logs_excluded(self, fake_data, tmp_path):
        r = backup.export(tmp_path / "b.zip")
        with zipfile.ZipFile(r["path"]) as zf:
            names = set(zf.namelist())
        assert "token" not in names
        assert not any(n.startswith("logs/") for n in names)
        assert not any("chroma" in n for n in names)

    def test_manifest_contents(self, fake_data, tmp_path):
        r = backup.export(tmp_path / "b.zip")
        m = _read_manifest(r["path"])
        assert m["app"] == "pypedia"
        assert m["schema"] == backup.SCHEMA
        assert "profile.json" in m["items"]
        assert "token" not in m["items"]

    def test_plugins_state_json_included(self, fake_data, tmp_path):
        """插件开关态（plugins/state.json）应进备份包。"""
        (DATA_DIR / "plugins").mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "plugins" / "state.json").write_text(
            '{"agent-memory": false}', encoding="utf-8")
        r = backup.export(tmp_path / "b.zip")
        with zipfile.ZipFile(r["path"]) as zf:
            names = set(zf.namelist())
        assert "plugins/state.json" in names
        assert "plugins/state.json" in _read_manifest(r["path"])["items"]


class TestImport:
    def _make_backup(self, fake_data, tmp_path):
        r = backup.export(tmp_path / "b.zip")
        # 清空白名单数据模拟"数据丢失"（备份语义只覆盖 BACKUP_ITEMS）。
        # 注意：不能整个数据目录乱删——agent/agent_memory.db 等运行期单例
        # 持有的文件被删后，进程内 sqlite 连接再写即
        # "attempt to write a readonly database"，会污染后续所有测试。
        for name in backup.BACKUP_ITEMS:
            p = fake_data / name
            if p.is_dir():
                shutil.rmtree(p)
            elif p.exists():
                p.unlink()
        return r["path"]

    def test_roundtrip_restores(self, fake_data, tmp_path):
        zip_path = self._make_backup(fake_data, tmp_path)
        r = backup.import_backup(zip_path)
        assert r["ok"]
        assert (DATA_DIR / "profile.json").read_text(encoding="utf-8") == '{"default":{"level":3}}'
        assert (DATA_DIR / "vector_lancedb" / "index.lance").read_bytes() == b"fake-lancedb"
        assert (DATA_DIR / "mem0_qdrant" / "meta.json").exists()
        # 快照目录生成（可回滚）
        assert "rollback-" in r["rollback"]

    def test_plugins_state_json_roundtrip(self, fake_data, tmp_path):
        """插件开关态备份→清空→恢复：state.json 内容完整还原。"""
        (DATA_DIR / "plugins").mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "plugins" / "state.json").write_text(
            '{"agent-memory": false, "web-fetch": true}', encoding="utf-8")
        zip_path = self._make_backup(fake_data, tmp_path)
        r = backup.import_backup(zip_path)
        assert r["ok"]
        restored = (DATA_DIR / "plugins" / "state.json").read_text(encoding="utf-8")
        assert json.loads(restored) == {"agent-memory": False, "web-fetch": True}

    def test_rejects_foreign_manifest(self, tmp_path):
        bad = tmp_path / "foreign.zip"
        with zipfile.ZipFile(bad, "w") as zf:
            zf.writestr(backup.MANIFEST, json.dumps({"app": "other-app", "schema": 1}))
        r = backup.import_backup(bad)
        assert not r["ok"]
        assert "不是 pypedia" in r["error"]

    def test_rejects_newer_schema(self, tmp_path):
        future = tmp_path / "future.zip"
        with zipfile.ZipFile(future, "w") as zf:
            zf.writestr(backup.MANIFEST,
                        json.dumps({"app": "pypedia", "schema": backup.SCHEMA + 99}))
        r = backup.import_backup(future)
        assert not r["ok"]
        assert "过新" in r["error"]

    def test_rejects_missing_manifest(self, tmp_path):
        no = tmp_path / "no.zip"
        with zipfile.ZipFile(no, "w") as zf:
            zf.writestr("profile.json", "{}")
        r = backup.import_backup(no)
        assert not r["ok"]
        assert "manifest" in r["error"]

    def test_rejects_zip_slip(self, tmp_path):
        """恶意备份含 ../ 越界路径——必须拒绝且不写出数据目录。"""
        evil = tmp_path / "evil.zip"
        outside = tmp_path / "evil-escape.txt"
        with zipfile.ZipFile(evil, "w") as zf:
            zf.writestr(backup.MANIFEST, json.dumps({"app": "pypedia", "schema": 1}))
            zf.writestr("../evil-escape.txt", "pwned")
        r = backup.import_backup(evil)
        assert not r["ok"]
        assert "越界" in r["error"]
        assert not outside.exists()

    def test_bad_zip_file(self, tmp_path):
        bad = tmp_path / "bad.zip"
        bad.write_bytes(b"not a zip at all")
        r = backup.import_backup(bad)
        assert not r["ok"]
        assert "zip" in r["error"]

    def test_missing_file(self, tmp_path):
        r = backup.import_backup(tmp_path / "nonexistent.zip")
        assert not r["ok"]
        assert "不存在" in r["error"]


class TestBackupApi:
    def test_export_endpoint(self, client, fake_data, tmp_path, monkeypatch):
        r = client.post("/api/backup/export")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        # 响应体确实是 zip（含 manifest）
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            assert backup.MANIFEST in zf.namelist()

    def test_import_endpoint_roundtrip(self, client, fake_data, tmp_path):
        r = backup.export(tmp_path / "b.zip")
        with open(r["path"], "rb") as f:
            data = f.read()
        # 先删掉再恢复
        (DATA_DIR / "profile.json").unlink()
        resp = client.post("/api/backup/import",
                           files={"file": ("b.zip", io.BytesIO(data), "application/zip")})
        assert resp.status_code == 200
        d = resp.json()
        assert d["ok"] and d["restored"] > 0
        assert (DATA_DIR / "profile.json").exists()

    def test_import_endpoint_rejects_garbage(self, client):
        resp = client.post("/api/backup/import",
                           files={"file": ("x.zip", io.BytesIO(b"garbage"), "application/zip")})
        assert resp.status_code == 400
