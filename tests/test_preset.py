"""预置权威资料源测试：清单完整性 + 幂等 + 绝不污染知识库（零真实联网）。"""
from __future__ import annotations

from pypedia import ingest
from pypedia.ingest import sources as src_mod
from pypedia.ingest import strategies as strat_mod


class TestPresetManifest:
    def test_manifest_covers_three_roles(self):
        srcs = ingest.load_preset_sources()
        assert len(srcs) >= 6, "预置清单过少，失去预装意义"
        roles = {s["role"] for s in srcs}
        assert roles == {"main", "supplement_a", "supplement_b"}, roles

    def test_manifest_has_official_python_sources(self):
        """用户诉求：Python 官方文档 + 官方 GitHub + 权威论坛三类都要有。"""
        srcs = ingest.load_preset_sources()
        assert any("docs.python.org" in s["target"] for s in srcs), "缺官方文档"
        assert any(s["kind"] == "github" and "cpython" in s["target"]
                   for s in srcs), "缺 CPython 仓库"
        assert any("discuss.python.org" in s["target"]
                   or "stackoverflow.com" in s["target"] for s in srcs), "缺权威论坛"

    def test_manifest_fields_valid(self):
        for s in ingest.load_preset_sources():
            assert s["kind"] in ("url", "github")
            assert s["role"] in ("main", "supplement_a", "supplement_b")
            assert s["target"].startswith(("http", "python/"))


class TestPresetIngest:
    def test_switch_off_returns_disabled(self, monkeypatch):
        monkeypatch.setattr(ingest.settings, "PRESET_SOURCES_ENABLE", False)
        assert ingest.ingest_preset_sources()["disabled"] is True

    def test_no_records_when_web_fetch_off(self, monkeypatch):
        """未开联网抓取时一条都不登记：否则知识库页会凭空多出一片 pending。"""
        monkeypatch.setattr(ingest.settings, "PRESET_SOURCES_ENABLE", True)
        monkeypatch.setattr(ingest.settings, "ENABLE_WEB_FETCH", False)
        before = len(ingest.list_sources())
        r = ingest.ingest_preset_sources()
        assert r["disabled"] is True and r["web_fetch"] is False
        assert len(ingest.list_sources()) == before, "离线状态不应写入任何资料源记录"

    def test_idempotent_skip_existing(self, monkeypatch):
        """已存在同 target 的记录应跳过，重复启动不重复抓取。"""
        monkeypatch.setattr(ingest.settings, "PRESET_SOURCES_ENABLE", True)
        monkeypatch.setattr(ingest.settings, "ENABLE_WEB_FETCH", True)
        calls: list[str] = []

        def fake_url(target, role, title=None, max_pages=None):
            calls.append(target)
            return {"status": "indexed", "chunks": 1}

        def fake_gh(repo, role, title=None):
            calls.append(repo)
            return {"status": "indexed", "chunks": 1}

        monkeypatch.setattr(strat_mod, "ingest_url", fake_url)
        monkeypatch.setattr(strat_mod, "ingest_github", fake_gh)
        monkeypatch.setattr(src_mod, "list_sources",
                            lambda: [{"target": t} for t in calls])

        r1 = ingest.ingest_preset_sources()
        assert r1["added"] == len(calls) > 0
        n = len(calls)
        r2 = ingest.ingest_preset_sources()
        assert r2["skipped"] == n and r2["added"] == 0, "第二次应全部跳过"
        assert len(calls) == n, "跳过的源不应重复抓取"

    def test_single_source_failure_does_not_abort(self, monkeypatch):
        """单源抛异常只记 failed，其余源继续（绝不中断整批）。"""
        monkeypatch.setattr(ingest.settings, "PRESET_SOURCES_ENABLE", True)
        monkeypatch.setattr(ingest.settings, "ENABLE_WEB_FETCH", True)
        monkeypatch.setattr(src_mod, "list_sources", lambda: [])

        def flaky_url(target, role, title=None, max_pages=None):
            if "datamodel" in target:
                raise RuntimeError("network boom")
            return {"status": "indexed", "chunks": 1}

        monkeypatch.setattr(strat_mod, "ingest_url", flaky_url)
        monkeypatch.setattr(strat_mod, "ingest_github",
                            lambda *a, **k: {"status": "indexed", "chunks": 1})
        r = ingest.ingest_preset_sources()
        assert r["failed"] == 1
        assert r["added"] >= 1, "其余源应继续入库"
