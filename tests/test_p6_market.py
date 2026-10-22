"""P6 市场 v1 测试：版本门禁 / 上传解析（Zip Slip）/ 安装全链路 / 运行可见性 /
卸载护栏 / 重启恢复 / 端点 / form 双形态（引擎打桩，零真实调用）。

数据隔离：conftest 顶层已把 PYPEDIA_DATA 指到临时目录，app 模块级
market_store 的 installed_dir / lock_path 均落在其中；本文件所有装卸
都经 ``market_unit`` fixture 保证 teardown 干净（双注册表 + 账本 + 目录）。
"""
from __future__ import annotations

import io
import json
import logging
import shutil
import zipfile

import pytest

from pypedia.units import UnitLoader, unit_registry
from pypedia.units.market import (
    LOCK_SCHEMA,
    PLATFORM_VERSION,
    MarketError,
    MarketStore,
    check_dependencies,
    check_platform_gate,
    parse_upload,
    parse_version,
    version_ge,
    version_satisfies,
)
from pypedia.units.manifest import Manifest
from pypedia.plugins import plugin_registry


# ---------- 造包辅助 ---------- #
def _manifest_raw(**over) -> dict:
    """最小合法市场 manifest（缺省即「装了就能跑」的成品 plugin）。"""
    raw = {
        "id": "market-demo",
        "type": "plugin",
        "name": "市场演示插件",
        "version": "1.0.0",
        "description": "P6 测试用",
        "min_platform": "0.1.0",
        "dependencies": [],
        "default_enabled": True,
        "switchable": True,
        "env_gate": "",
        "apply": "immediate",
        "form": "instance",
    }
    raw.update(over)
    return raw


def make_zip(manifest: dict, resources: dict | None = None, *,
             nested: bool = False) -> bytes:
    """把 manifest + 资源打成 zip（nested=True 时整包放进一层子目录）。"""
    buf = io.BytesIO()
    prefix = f"{manifest['id']}/" if nested else ""
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(prefix + "plugin.json",
                    json.dumps(manifest, ensure_ascii=False))
        for rel, blob in (resources or {}).items():
            zf.writestr(prefix + rel, blob)
    return buf.getvalue()


@pytest.fixture
def store():
    """app 真单例 market_store（真双注册表；conftest 已隔离数据目录）。"""
    import app as app_module

    return app_module.market_store


@pytest.fixture
def market_unit(store):
    """安装助手：装市场 unit 并保证 teardown 四清（账本/双表/目录）。

    记录「尝试过的 id」（含安装失败的）——失败路径（回滚/冲突）也须
    teardown 干净，否则泄漏到后续用例（计数锁回归）。
    """
    made: list[str] = []

    def _install(manifest: dict, resources: dict | None = None, *,
                 filename: str = "pkg.zip", nested: bool = False) -> str:
        uid = manifest["id"]
        made.append(uid)
        if filename.endswith(".json"):
            data = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
        else:
            data = make_zip(manifest, resources, nested=nested)
        store.install_upload(data, filename)
        return uid

    yield _install
    for uid in made:
        try:
            store.uninstall(uid)
        except MarketError:
            pass
        unit_registry.unregister(uid)   # 双保险：注册表不留痕
        plugin_registry.unregister(uid)
        shutil.rmtree(store.installed_dir / uid, ignore_errors=True)
    store._save_lock([e for e in store.lock_entries()
                      if e.get("id") not in set(made)])


# ==================== 版本门禁（纯函数） ==================== #
class TestVersionGate:
    def test_parse_version_ok(self):
        assert parse_version("1.2.3") == (1, 2, 3)
        assert parse_version("0.10.0") == (0, 10, 0)
        assert parse_version("1") == (1,)          # 1-4 段均合法
        assert parse_version("1.2.3.4") == (1, 2, 3, 4)

    @pytest.mark.parametrize("bad", ["", "a.b.c", "1..2", "1.2.3.4.5", "-1.0.0"])
    def test_parse_version_rejects(self, bad):
        with pytest.raises(MarketError):
            parse_version(bad)

    def test_version_ge(self):
        assert version_ge("0.2.0", "0.1.0")
        assert version_ge("0.2.0", "0.2.0")
        assert not version_ge("0.1.0", "0.2.0")

    @pytest.mark.parametrize("spec,have,ok", [
        ("*", "9.9.9", True),
        ("", "0.0.1", True),
        (">=1.0.0", "1.0.0", True),
        (">=1.0.0", "0.9.9", False),
        ("<=1.0.0", "1.0.0", True),
        ("<1.0.0", "1.0.0", False),
        (">1.0.0", "1.0.1", True),
        ("==1.2.3", "1.2.3", True),
        ("==1.2.3", "1.2.4", False),
        ("1.2.3", "1.2.3", True),          # 无比较符 = 精确匹配
        ("1.2.3", "1.2.4", False),
        (">=1.0.0,<2.0.0", "1.5.0", True),  # 逗号分段 AND
        (">=1.0.0,<2.0.0", "2.0.0", False),
    ])
    def test_version_satisfies(self, spec, have, ok):
        assert version_satisfies(have, spec) is ok

    def test_version_satisfies_empty_clause_rejected(self):
        with pytest.raises(MarketError, match="空段"):
            version_satisfies("1.0.0", "1.0.0,")

    def test_platform_gate(self):
        assert check_platform_gate(Manifest.from_dict(_manifest_raw())) is None
        low = Manifest.from_dict(_manifest_raw(min_platform="0.0.1"))
        assert check_platform_gate(low) is None
        high = Manifest.from_dict(_manifest_raw(min_platform="99.0.0"))
        with pytest.raises(MarketError, match="平台版本不满足"):
            check_platform_gate(high)

    def test_dependencies_gate(self, store):
        missing = Manifest.from_dict(
            _manifest_raw(dependencies=[{"id": "no-such-unit", "version": "*"}]))
        with pytest.raises(MarketError, match="未安装"):
            check_dependencies(missing, store.registry)
        low = Manifest.from_dict(
            _manifest_raw(dependencies=[{"id": "agent-memory", "version": "<1.0.0"}]))
        with pytest.raises(MarketError, match="依赖版本不满足"):
            check_dependencies(low, store.registry)
        ok = Manifest.from_dict(
            _manifest_raw(dependencies=[{"id": "agent-memory", "version": ">=1.0.0"}]))
        assert check_dependencies(ok, store.registry) is None


# ==================== 上传包解析 ==================== #
class TestUploadParse:
    def test_bare_json(self):
        data = json.dumps(_manifest_raw()).encode("utf-8")
        pkg = parse_upload(data, "plugin.json")
        assert pkg.unit_id == "market-demo" and pkg.resources == {}

    def test_zip_flat(self):
        pkg = parse_upload(make_zip(_manifest_raw(), {"tool.py": "x = 1"}))
        assert pkg.resources == {"tool.py": b"x = 1"}

    def test_zip_nested_strips_prefix(self):
        pkg = parse_upload(make_zip(_manifest_raw(), {"tool.py": "x = 1"},
                                    nested=True))
        assert pkg.resources == {"tool.py": b"x = 1"}  # 顶层目录已剥掉

    def test_zip_slip_rejected(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("plugin.json", json.dumps(_manifest_raw()))
            zf.writestr("../evil.json", "{}")
        with pytest.raises(MarketError, match="越界路径"):
            parse_upload(buf.getvalue())

    def test_absolute_path_rejected(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("plugin.json", json.dumps(_manifest_raw()))
            zf.writestr("/etc/evil.json", "{}")
        with pytest.raises(MarketError, match="越界路径"):
            parse_upload(buf.getvalue())

    def test_multiple_manifests_rejected(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("a/plugin.json", json.dumps(_manifest_raw()))
            zf.writestr("b/plugin.json", json.dumps(_manifest_raw(id="other")))
        with pytest.raises(MarketError, match="多个"):
            parse_upload(buf.getvalue())

    def test_no_manifest_rejected(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("readme.txt", "hi")
        with pytest.raises(MarketError, match="未找到"):
            parse_upload(buf.getvalue())

    def test_empty_upload_rejected(self):
        with pytest.raises(MarketError, match="为空"):
            parse_upload(b"")

    def test_oversize_rejected(self, monkeypatch):
        import pypedia.units.market as market

        monkeypatch.setattr(market, "MAX_UPLOAD_BYTES", 100)
        data = json.dumps(_manifest_raw()).encode("utf-8")
        with pytest.raises(MarketError, match="体积上限"):
            parse_upload(data, "plugin.json")

    def test_too_many_files_rejected(self, monkeypatch):
        import pypedia.units.market as market

        monkeypatch.setattr(market, "MAX_UPLOAD_FILES", 2)
        with pytest.raises(MarketError, match="文件数超限"):
            parse_upload(make_zip(_manifest_raw(),
                                  {"a.py": "", "b.py": "", "c.py": ""}))

    def test_sniff_by_content(self):
        # 扩展名缺失/不认识：zip 魔数与 JSON 内容嗅探
        assert parse_upload(make_zip(_manifest_raw()), "blob").unit_id == "market-demo"
        data = json.dumps(_manifest_raw()).encode("utf-8")
        assert parse_upload(data, "blob").unit_id == "market-demo"

    def test_unsupported_format_rejected(self):
        with pytest.raises(MarketError, match="不支持的上传格式"):
            parse_upload(b"\x00\x01\x02randombytes", "blob.bin")

    def test_manifest_top_level_not_object(self):
        with pytest.raises(MarketError, match="顶层必须是对象"):
            parse_upload(b"[1,2,3]", "plugin.json")

    def test_zip_corrupt_entry_rejected(self):
        """条目级 CRC 损坏（改数据区字节）→ MarketError，不裸奔成 500。"""
        raw = bytearray(make_zip(_manifest_raw(), {"tool.py": "x = 1"}))
        hit = bytes(raw).find(b"x = 1")
        assert hit > 0
        raw[hit] = ord("y")  # 内容变了，中央目录 CRC 不符
        with pytest.raises(MarketError, match="读取失败"):
            parse_upload(bytes(raw))


# ==================== 安装 / 卸载全链路 ==================== #
class TestInstallLifecycle:
    def test_install_full_chain(self, store, market_unit):
        uid = market_unit(_manifest_raw())
        # 双注册：内核主表 + 运行态门控表都能看到
        assert store.registry.get_unit(uid) is not None
        assert plugin_registry.get_unit(uid) is not None
        # 账本 + 落盘
        entries = {e["id"]: e for e in store.lock_entries()}
        assert uid in entries and entries[uid]["version"] == "1.0.0"
        assert (store.installed_dir / uid / "plugin.json").exists()
        # 货架视图：注册态 + 门控（运行态表为真值源）
        rows = {r["id"]: r for r in store.list_installed()}
        assert rows[uid]["registered"] is True and rows[uid]["enabled"] is True

    def test_install_with_resources(self, store, market_unit):
        uid = market_unit(_manifest_raw(), {"demo_tool.py": "def f():\n    return 1\n"})
        assert (store.installed_dir / uid / "demo_tool.py").exists()

    def test_install_bare_json(self, store, market_unit):
        uid = market_unit(_manifest_raw(), filename="plugin.json")
        assert store.registry.get_unit(uid) is not None
        assert (store.installed_dir / uid / "plugin.json").exists()

    def test_duplicate_in_registry_rejected(self, store, market_unit):
        uid = market_unit(_manifest_raw())
        with pytest.raises(MarketError, match="已在注册表"):
            store.install_upload(make_zip(_manifest_raw()), "pkg.zip")
        assert uid in {e["id"] for e in store.lock_entries()}  # 原装不受影响

    def test_duplicate_in_lock_rejected(self, store):
        store._save_lock([{"id": "market-demo", "version": "1.0.0",
                           "type": "plugin", "form": "instance",
                           "name": "幽灵条目"}])
        with pytest.raises(MarketError, match="账本中但未注册"):
            store.install_upload(make_zip(_manifest_raw()), "pkg.zip")
        assert store.registry.get_unit("market-demo") is None  # 没落注册表
        store._save_lock([])  # 清理幽灵条目

    def test_invalid_manifest_rejected(self, store, market_unit):
        bad = _manifest_raw()
        del bad["name"]  # required 缺失
        with pytest.raises(MarketError, match="不满足契约"):
            store.install_upload(make_zip(bad), "pkg.zip")
        assert store.registry.get_unit("market-demo") is None
        assert not (store.installed_dir / "market-demo").exists()

    def test_platform_gate_blocks_install(self, store, market_unit):
        with pytest.raises(MarketError, match="平台版本不满足"):
            store.install_upload(
                make_zip(_manifest_raw(min_platform="99.0.0")), "pkg.zip")
        assert not (store.installed_dir / "market-demo").exists()
        assert store.lock_entries() == []

    def test_dependency_gate_blocks_install(self, store, market_unit):
        with pytest.raises(MarketError, match="未安装"):
            store.install_upload(
                make_zip(_manifest_raw(
                    dependencies=[{"id": "ghost-dep", "version": "*"}])), "pkg.zip")
        assert not (store.installed_dir / "market-demo").exists()

    def test_reinstall_after_uninstall(self, store, market_unit):
        market_unit(_manifest_raw())
        store.uninstall("market-demo")
        market_unit(_manifest_raw(version="2.0.0"))  # 卸后可重装（含新版本）
        rows = {r["id"]: r for r in store.list_installed()}
        assert rows["market-demo"]["version"] == "2.0.0"

    def test_install_rollback_on_lock_failure(self, store, market_unit,
                                              monkeypatch):
        """记账失败 → 整体回滚：双表注销 + 目录删除，不留残迹。"""
        def boom(entries):
            raise OSError("disk full")

        monkeypatch.setattr(store, "_save_lock", boom)
        with pytest.raises(MarketError, match="账本写入失败"):
            store.install_upload(make_zip(_manifest_raw()), "pkg.zip")
        assert store.registry.get_unit("market-demo") is None
        assert plugin_registry.get_unit("market-demo") is None
        assert not (store.installed_dir / "market-demo").exists()

    def test_uninstall_full_chain(self, store, market_unit):
        market_unit(_manifest_raw())
        store.uninstall("market-demo")
        assert store.registry.get_unit("market-demo") is None
        assert plugin_registry.get_unit("market-demo") is None
        assert not (store.installed_dir / "market-demo").exists()
        assert store.lock_entries() == []

    def test_uninstall_builtin_rejected(self, store):
        with pytest.raises(MarketError, match="不是市场安装的"):
            store.uninstall("agent-memory")
        assert store.registry.get_unit("agent-memory") is not None  # 内置无损

    def test_uninstall_unknown_rejected(self, store):
        with pytest.raises(MarketError, match="不是市场安装的"):
            store.uninstall("never-installed")


# ==================== 重启恢复 / 账本卫生 ==================== #
class TestRestoreAndLock:
    def test_restore_after_restart(self, store, market_unit):
        """模拟进程重启：内存注销（账本/目录保留）→ restore 双表恢复。"""
        market_unit(_manifest_raw())
        unit_registry.unregister("market-demo")
        plugin_registry.unregister("market-demo")
        store2 = MarketStore(store.registry, UnitLoader(store.registry),
                             runtime_registry=plugin_registry,
                             installed_dir=store.installed_dir,
                             lock_path=store.lock_path)
        assert "market-demo" in store2.restore_installed()
        assert store.registry.get_unit("market-demo") is not None
        assert plugin_registry.get_unit("market-demo") is not None

    def test_restore_skips_bad_package(self, store, market_unit, caplog):
        market_unit(_manifest_raw())
        bad_dir = store.installed_dir / "bad-pkg"
        bad_dir.mkdir(parents=True, exist_ok=True)
        (bad_dir / "plugin.json").write_text('{"id": "bad-pkg"}', encoding="utf-8")
        try:
            unit_registry.unregister("market-demo")
            plugin_registry.unregister("market-demo")
            store2 = MarketStore(store.registry, UnitLoader(store.registry),
                                 runtime_registry=plugin_registry,
                                 installed_dir=store.installed_dir,
                                 lock_path=store.lock_path)
            with caplog.at_level(logging.WARNING, logger="pypedia.units.market"):
                restored = store2.restore_installed()
            assert "market-demo" in restored and "bad-pkg" not in restored
            assert "跳过无法恢复" in caplog.text
            assert store.registry.get_unit("market-demo") is not None
        finally:
            shutil.rmtree(bad_dir, ignore_errors=True)

    def test_corrupt_lock_rejected(self, store):
        store.lock_path.write_text("{broken json", encoding="utf-8")
        with pytest.raises(MarketError, match="损坏"):
            store.load_lock()
        store.lock_path.unlink(missing_ok=True)

    def test_lock_schema_incompatible(self, store):
        store.lock_path.write_text(
            json.dumps({"schema": LOCK_SCHEMA + 99, "units": []}), encoding="utf-8")
        with pytest.raises(MarketError, match="结构版本不兼容"):
            store.load_lock()
        store.lock_path.unlink(missing_ok=True)

    def test_lock_roundtrip(self, store):
        store._save_lock([{"id": "x", "version": "1.0.0"}])
        assert store.lock_entries() == [{"id": "x", "version": "1.0.0"}]
        store._save_lock([])


# ==================== 运行可见性（装上即可用） ==================== #
TOOL_SRC = (
    "def market_demo_tool_fn():\n"
    "    return {'name': 'market_demo_tool', 'description': '演示', 'parameters': {}}\n"
)
SECTION = {"name": "market-demo:guide", "order": 50, "text": "P6 冒烟规约：请用表格回答。"}
ALWAYS_RULE = [{"id": "market-demo:always", "when": {"always": True},
                "then": {"activate": ["market-demo"]}}]


class TestRuntimeVisibility:
    def _contrib(self, **extra) -> dict:
        c = {"agent_tools": ["demo_tool:market_demo_tool_fn"],
             "system_prompt_sections": [SECTION]}
        c.update(extra)
        return c

    def test_agent_tool_visible(self, store, market_unit):
        market_unit(_manifest_raw(contributions=self._contrib()),
                    {"demo_tool.py": TOOL_SRC})
        from pypedia.agent.build import build_system_prompt  # noqa: F401

        names = [getattr(t, "__name__", "") for t in
                 plugin_registry.enabled_agent_tools()]
        assert "market_demo_tool_fn" in names
        store.uninstall("market-demo")
        names = [getattr(t, "__name__", "") for t in
                 plugin_registry.enabled_agent_tools()]
        assert "market_demo_tool_fn" not in names

    def test_prompt_section_visible_without_rules(self, store, market_unit):
        from pypedia.agent.build import build_system_prompt

        market_unit(_manifest_raw(contributions=self._contrib()),
                    {"demo_tool.py": TOOL_SRC})
        assert "P6 冒烟规约" in build_system_prompt(3, "你好")

    def test_prompt_section_fail_closed_then_activated(self, store, market_unit):
        """规则引擎开启：未激活 → 规约不可见；自声明 always 规则 → 可见。"""
        from pypedia.agent.build import _rule_decision, build_system_prompt

        market_unit(_manifest_raw(contributions=self._contrib()),
                    {"demo_tool.py": TOOL_SRC})
        decision = _rule_decision(3, "你好")
        assert "market-demo" not in decision.active  # 无规则 → 不进激活集
        assert "P6 冒烟规约" not in build_system_prompt(3, "你好", decision=decision)
        # 卸载后改装「自声明 always 规则」的版本
        store.uninstall("market-demo")
        market_unit(_manifest_raw(contributions=self._contrib(rules=ALWAYS_RULE)),
                    {"demo_tool.py": TOOL_SRC})
        decision = _rule_decision(3, "你好")
        assert "market-demo" in decision.active
        assert "P6 冒烟规约" in build_system_prompt(3, "你好", decision=decision)

    def test_env_gate_blocks_runtime(self, store, market_unit, monkeypatch):
        from pypedia.agent.build import build_system_prompt
        from pypedia.config import settings

        market_unit(_manifest_raw(
            env_gate="EVOLUTION_ENABLE",
            contributions=self._contrib()), {"demo_tool.py": TOOL_SRC})
        assert "market_demo_tool_fn" in [
            getattr(t, "__name__", "") for t in plugin_registry.enabled_agent_tools()]
        monkeypatch.setattr(settings, "EVOLUTION_ENABLE", False)
        assert not plugin_registry.is_enabled("market-demo")
        assert "market_demo_tool_fn" not in [
            getattr(t, "__name__", "") for t in plugin_registry.enabled_agent_tools()]
        assert "P6 冒烟规约" not in build_system_prompt(3, "你好")


# ==================== form 双形态 ==================== #
class TestForm:
    def test_template_form(self, store, market_unit):
        market_unit(_manifest_raw(id="market-tpl", form="template",
                                  name="模板类插件"))
        rows = {r["id"]: r for r in store.list_installed()}
        assert rows["market-tpl"]["form"] == "template"
        assert store.registry.get_unit("market-tpl").form == "template"

    def test_invalid_form_rejected(self, store):
        with pytest.raises(MarketError, match="不满足契约"):
            store.install_upload(
                make_zip(_manifest_raw(id="market-bad", form="widget")), "pkg.zip")
        assert store.registry.get_unit("market-bad") is None


# ==================== 端点 ==================== #
class TestMarketEndpoints:
    def test_market_view(self, client):
        r = client.get("/api/market")
        assert r.status_code == 200
        d = r.json()
        assert d["platform_version"] == PLATFORM_VERSION
        assert set(d["shelves"]) == {"plugin", "agent", "team"}

    def test_upload_endpoint(self, client, store, market_unit):
        r = client.post("/api/market/upload",
                        files={"file": ("pkg.zip", make_zip(_manifest_raw()),
                                        "application/zip")})
        assert r.status_code == 200, r.text
        inst = r.json()["installed"]
        assert inst["id"] == "market-demo" and inst["type"] == "plugin"
        assert store.registry.get_unit("market-demo") is not None
        assert plugin_registry.get_unit("market-demo") is not None
        # 端点直装不走 fixture 记录：显式卸载，防止污染后续用例
        store.uninstall("market-demo")
        assert plugin_registry.get_unit("market-demo") is None

    def test_upload_bad_package_400(self, client, store):
        r = client.post("/api/market/upload",
                        files={"file": ("pkg.zip", b"not a zip at all",
                                        "application/zip")})
        assert r.status_code == 400
        assert "detail" in r.json()

    def test_uninstall_endpoint(self, client, market_unit):
        market_unit(_manifest_raw())
        r = client.delete("/api/market/units/market-demo")
        assert r.status_code == 200
        assert plugin_registry.get_unit("market-demo") is None

    def test_uninstall_builtin_400(self, client):
        r = client.delete("/api/market/units/agent-memory")
        assert r.status_code == 400

    def test_units_view_contains_market_unit(self, client, market_unit):
        """/api/units 对市场 unit 的门控合并到 plugin_registry（同一真值源）。"""
        market_unit(_manifest_raw())  # 无贡献：不影响工具恒等
        d = client.get("/api/units").json()
        row = next((u for u in d["units"] if u["id"] == "market-demo"), None)
        assert row is not None and row["enabled"] is True
        detail = client.get("/api/units/market-demo")
        assert detail.status_code == 200
        assert detail.json()["unit"]["id"] == "market-demo"

    def test_units_view_market_unit_env_blocked(self, client, market_unit,
                                                monkeypatch):
        from pypedia.config import settings

        market_unit(_manifest_raw(env_gate="EVOLUTION_ENABLE"))
        monkeypatch.setattr(settings, "EVOLUTION_ENABLE", False)
        d = client.get("/api/units").json()
        row = next(u for u in d["units"] if u["id"] == "market-demo")
        assert row["enabled"] is False and row["env_blocked"] is True
