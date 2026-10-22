"""P7 节点编辑器 v1 测试：图校验 / 序列化导出 / 安装全链路 / 端点 / 模板
（引擎打桩，零真实调用）。

验收主线（master plan §11(P7)）：**画一张图 → 导出可运行 unit → 装上就能跑**。
- validate：结构 + 表达式语法 + 引用存在性（节点级 ref 与 params.ref
  两种形状都认——与 GraphRuntime 解析顺序一致）；
- export：zip 与市场上传同格式（``parse_upload`` 可直接消费）；
- install：走市场同一通道（schema + 版本门禁 + 账本），装完由
  ``GraphRuntime`` 解释执行（process.expr 图 execute(21)=42，零依赖）；
- 模板：minimal 三节点 / encyclopedia 13 节点 / node_types 六种。

数据隔离：conftest 顶层已把 PYPEDIA_DATA 指到临时目录；装卸都经
``editor_unit`` / ``market_unit`` fixture 保证 teardown 四清
（账本 + 双注册表 + 目录），失败路径（冲突/门禁）同样不留痕。
"""
from __future__ import annotations

import io
import json
import shutil
import zipfile

import pytest

from pypedia.units import (
    EditorError,
    GraphRuntime,
    Manifest,
    export_unit,
    graph_to_manifest,
    manifest_to_zip,
    unit_registry,
    validate_graph,
)
from pypedia.units.editor import NODE_TYPES, encyclopedia_graph, minimal_graph
from pypedia.units.market import MarketError, parse_upload
from pypedia.plugins import plugin_registry


# ---------- 造图 / 造包辅助 ---------- #
def _double_graph() -> dict:
    """最小可执行图：entry → process(payload*2) → exit（execute(21)=42）。"""
    return {
        "nodes": [
            {"id": "e", "type": "entry"},
            {"id": "p", "type": "process", "params": {"expr": "payload * 2"}},
            {"id": "x", "type": "exit"},
        ],
        "edges": [{"from": "e", "to": "p"}, {"from": "p", "to": "x"}],
    }


def _manifest_raw(**over) -> dict:
    """最小合法市场 manifest（被 editor 图引用的靶子 unit 用）。"""
    raw = {
        "id": "p7-target",
        "type": "plugin",
        "name": "P7 靶子插件",
        "version": "1.0.0",
        "description": "P7 测试用",
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


# 带 tools 贡献点的靶子（GraphRuntime._run_plugin 经 contributions.tools 解析）
DOUBLE_TOOL_SRC = (
    "def p7_double_tools():\n"
    "    def double(payload, data=None):\n"
    "        return payload * 2\n"
    "    return {'name': 'double', 'description': 'P7 翻倍工具', 'handler': double}\n"
)


@pytest.fixture
def store():
    """app 真单例 market_store（真双注册表；conftest 已隔离数据目录）。"""
    import app as app_module

    return app_module.market_store


@pytest.fixture
def market_unit(store):
    """市场安装助手（同 P6 模式）：teardown 四清（账本/双表/目录）。"""
    made: list[str] = []

    def _install(manifest: dict, resources: dict | None = None) -> str:
        uid = manifest["id"]
        made.append(uid)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("plugin.json", json.dumps(manifest, ensure_ascii=False))
            for rel, blob in (resources or {}).items():
                zf.writestr(rel, blob)
        store.install_upload(buf.getvalue(), "pkg.zip")
        return uid

    yield _install
    for uid in made:
        try:
            store.uninstall(uid)
        except MarketError:
            pass
        unit_registry.unregister(uid)
        plugin_registry.unregister(uid)
        shutil.rmtree(store.installed_dir / uid, ignore_errors=True)
    store._save_lock([e for e in store.lock_entries()
                      if e.get("id") not in set(made)])


@pytest.fixture
def editor_unit(store):
    """编辑器安装助手：export_unit 产包 → 市场安装；teardown 四清。"""
    made: list[str] = []

    def _install(graph: dict, meta: dict) -> str:
        uid = str(meta["id"])
        made.append(uid)
        blob, name = export_unit(graph, meta)
        store.install_upload(blob, name)
        return uid

    yield _install
    for uid in made:
        try:
            store.uninstall(uid)
        except MarketError:
            pass
        unit_registry.unregister(uid)
        plugin_registry.unregister(uid)
        shutil.rmtree(store.installed_dir / uid, ignore_errors=True)
    store._save_lock([e for e in store.lock_entries()
                      if e.get("id") not in set(made)])


# ==================== 图校验（纯函数，不执行） ==================== #
class TestValidateGraph:
    def test_non_dict_rejected(self):
        assert validate_graph("nope") == ["图必须是对象（含 nodes/edges）"]

    def test_empty_graph_rejected(self):
        errs = validate_graph({})
        assert any("nodes 必须是非空数组" in e for e in errs)
        assert any("缺少 entry" in e for e in errs)

    def test_node_not_object(self):
        errs = validate_graph({"nodes": ["x"], "edges": []})
        assert any("nodes[0] 必须是对象" in e for e in errs)

    def test_missing_node_id(self):
        errs = validate_graph({"nodes": [{"type": "entry"}], "edges": []})
        assert any("缺少字符串 id" in e for e in errs)

    def test_duplicate_node_id(self):
        g = {"nodes": [{"id": "a", "type": "entry"}, {"id": "a", "type": "exit"}],
             "edges": []}
        assert any("id 重复" in e for e in validate_graph(g))

    def test_unknown_node_type(self):
        g = {"nodes": [{"id": "a", "type": "entry"}, {"id": "b", "type": "widget"}],
             "edges": []}
        assert any("类型非法" in e for e in validate_graph(g))

    def test_missing_entry(self):
        g = {"nodes": [{"id": "p", "type": "process",
                        "params": {"expr": "1"}},
                       {"id": "x", "type": "exit"}],
             "edges": [{"from": "p", "to": "x"}]}
        assert any("缺少 entry" in e for e in validate_graph(g))

    def test_missing_exit_warns(self):
        """缺 exit 是「建议级」提示：进 errors 引导用户补出口（图以末节点终止）。"""
        g = {"nodes": [{"id": "e", "type": "entry"},
                       {"id": "p", "type": "process", "params": {"expr": "1"}}],
             "edges": [{"from": "e", "to": "p"}]}
        assert any("建议包含 exit" in e for e in validate_graph(g))

    def test_edge_from_missing(self):
        g = {"nodes": [{"id": "e", "type": "entry"}, {"id": "x", "type": "exit"}],
             "edges": [{"from": "ghost", "to": "x"}]}
        assert any("from 不存在" in e for e in validate_graph(g))

    def test_edge_to_missing(self):
        g = {"nodes": [{"id": "e", "type": "entry"}, {"id": "x", "type": "exit"}],
             "edges": [{"from": "e", "to": "ghost"}]}
        assert any("to 不存在" in e for e in validate_graph(g))

    def test_self_loop(self):
        g = {"nodes": [{"id": "e", "type": "entry"}, {"id": "x", "type": "exit"}],
             "edges": [{"from": "e", "to": "e"}]}
        assert any("自环" in e for e in validate_graph(g))

    def test_condition_syntax_error(self):
        g = {"nodes": [{"id": "e", "type": "entry"}, {"id": "x", "type": "exit"}],
             "edges": [{"from": "e", "to": "x", "condition": "payload >"}]}
        errs = validate_graph(g)
        assert any("condition 不是合法 Python 表达式" in e for e in errs)

    def test_expr_syntax_error(self):
        g = {"nodes": [{"id": "e", "type": "entry"},
                       {"id": "p", "type": "process",
                        "params": {"expr": "payload +"}},
                       {"id": "x", "type": "exit"}],
             "edges": [{"from": "e", "to": "p"}, {"from": "p", "to": "x"}]}
        assert any("expr 不是合法 Python 表达式" in e
                   for e in validate_graph(g))

    def test_plugin_missing_ref(self):
        g = {"nodes": [{"id": "e", "type": "entry"},
                       {"id": "k", "type": "plugin"},
                       {"id": "x", "type": "exit"}],
             "edges": [{"from": "e", "to": "k"}, {"from": "k", "to": "x"}]}
        assert any("plugin 节点 k 缺少 ref" in e for e in validate_graph(g))

    def test_plugin_ref_unregistered(self, store):
        g = {"nodes": [{"id": "e", "type": "entry"},
                       {"id": "k", "type": "plugin",
                        "params": {"ref": "ghost-unit"}},
                       {"id": "x", "type": "exit"}],
             "edges": [{"from": "e", "to": "k"}, {"from": "k", "to": "x"}]}
        errs = validate_graph(g, registry=unit_registry)
        assert any("引用的 unit 未注册：ghost-unit" in e for e in errs)

    def test_process_needs_expr_or_ref(self):
        g = {"nodes": [{"id": "e", "type": "entry"},
                       {"id": "p", "type": "process"},
                       {"id": "x", "type": "exit"}],
             "edges": [{"from": "e", "to": "p"}, {"from": "p", "to": "x"}]}
        assert any("需要 params.expr 或 ref" in e for e in validate_graph(g))

    def test_multiple_errors_reported_together(self):
        """一张图同时踩三个坑：重复 id / expr 语法 / 边引用——全部报出。"""
        g = {"nodes": [{"id": "a", "type": "entry"},
                       {"id": "a", "type": "process",
                        "params": {"expr": "1 +"}},
                       {"id": "x", "type": "exit"}],
             "edges": [{"from": "a", "to": "x"}, {"from": "ghost", "to": "x"}]}
        errs = validate_graph(g)
        assert any("id 重复" in e for e in errs)
        assert any("不是合法 Python 表达式" in e for e in errs)
        assert any("from 不存在" in e for e in errs)

    def test_minimal_template_passes(self):
        assert validate_graph(minimal_graph()) == []

    def test_encyclopedia_template_passes(self, store):
        """内置单 Agent 成品图（节点级 ref 规范形状）校验零错误。"""
        assert validate_graph(encyclopedia_graph(),
                              registry=unit_registry) == []

    def test_params_ref_shape_accepted(self, store):
        """画布直出形状（params.ref）同样通过——运行时双位置容错。"""
        g = {"nodes": [{"id": "e", "type": "entry"},
                       {"id": "k", "type": "plugin",
                        "params": {"ref": "agent-memory", "method": "x"}},
                       {"id": "x", "type": "exit"}],
             "edges": [{"from": "e", "to": "k"}, {"from": "k", "to": "x"}]}
        assert validate_graph(g, registry=unit_registry) == []


# ==================== 画布 → manifest 序列化 ==================== #
class TestGraphToManifest:
    def test_missing_id_raises(self):
        with pytest.raises(EditorError, match="unit id 不能为空"):
            graph_to_manifest(minimal_graph(), {})

    def test_invalid_type_raises(self):
        with pytest.raises(EditorError, match="type 非法"):
            graph_to_manifest(minimal_graph(), {"id": "x", "type": "widget"})

    def test_defaults(self):
        m = graph_to_manifest(minimal_graph(), {"id": "ser-defaults"})
        assert m["id"] == "ser-defaults" and m["name"] == "ser-defaults"
        assert m["version"] == "0.1.0"
        assert m["min_platform"] == "0.2.0"   # 编辑器产物跟随当前平台线
        assert m["type"] == "agent" and m["form"] == "instance"
        assert m["default_enabled"] is True and m["env_gate"] == ""
        assert m["node_graph"]["nodes"]       # 图随身

    def test_agent_def_attached(self):
        m = graph_to_manifest(minimal_graph(), {"id": "ser-agent"})
        assert m["agent_def"] == {"identity": "①"}

    def test_team_def_attached(self):
        m = graph_to_manifest(minimal_graph(), {"id": "ser-team", "type": "team"})
        assert m["team_def"]["graph"]["nodes"]   # team 的图在 team_def.graph

    def test_meta_overrides(self):
        m = graph_to_manifest(minimal_graph(), {
            "id": "ser-over", "name": "自定义名", "version": "2.3.4",
            "description": "描述", "form": "template", "min_platform": "0.3.0"})
        assert m["name"] == "自定义名" and m["version"] == "2.3.4"
        assert m["form"] == "template" and m["min_platform"] == "0.3.0"

    def test_normalize_hoists_ref_and_strips_xy(self):
        """导出前归一：params.ref → 节点级 ref（规范形状），画布坐标剥掉。"""
        g = {"nodes": [
            {"id": "e", "type": "entry", "x": 1, "y": 2},
            {"id": "k", "type": "plugin", "x": 3, "y": 4,
             "params": {"ref": "agent-memory", "method": "remember"}},
            {"id": "x", "type": "exit"}],
            "edges": [{"from": "e", "to": "k"}, {"from": "k", "to": "x"}]}
        m = graph_to_manifest(g, {"id": "ser-norm"})
        node = {n["id"]: n for n in m["node_graph"]["nodes"]}["k"]
        assert node["ref"] == "agent-memory"            # 提升为节点级
        assert "ref" not in node["params"]              # params 不再背 ref
        assert node["params"]["method"] == "remember"   # method 留 params
        assert "x" not in node and "y" not in node      # 坐标剥掉

    def test_normalize_idempotent(self):
        g = minimal_graph()
        m1 = graph_to_manifest(g, {"id": "ser-idem"})
        m2 = graph_to_manifest(m1["node_graph"], {"id": "ser-idem"})
        assert m1["node_graph"] == m2["node_graph"]


# ==================== 导出 roundtrip（与市场同格式） ==================== #
class TestExportRoundtrip:
    def test_export_zip_parsable_by_market(self):
        blob, name = export_unit(_double_graph(), {"id": "rt-demo"})
        assert name == "rt-demo.zip"
        pkg = parse_upload(blob, name)   # 与市场上传同一裁判
        assert pkg.unit_id == "rt-demo" and pkg.resources == {}
        Manifest.from_dict(pkg.manifest_raw)  # schema 复检

    def test_export_with_resources(self):
        blob, _ = export_unit(_double_graph(), {"id": "rt-res"},
                              resources={"README.md": "hi"})
        pkg = parse_upload(blob, "rt-res.zip")
        assert pkg.resources == {"README.md": b"hi"}

    def test_export_bad_graph_raises(self):
        with pytest.raises(EditorError, match="图校验未通过"):
            export_unit({}, {"id": "rt-bad"})

    def test_export_missing_meta_id_raises(self):
        with pytest.raises(EditorError, match="unit id 不能为空"):
            export_unit(minimal_graph(), {})

    def test_export_bad_meta_type_raises(self):
        with pytest.raises(EditorError, match="type 非法"):
            export_unit(minimal_graph(), {"id": "rt-x", "type": "widget"})

    def test_manifest_to_zip_root_manifest(self):
        blob = manifest_to_zip({"id": "z", "name": "z"}, {"a.py": "x = 1"})
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            assert "plugin.json" in zf.namelist()
            assert zf.read("a.py") == b"x = 1"


# ==================== 安装全链路（装上就能跑） ==================== #
class TestEditorInstallLifecycle:
    def test_export_install_execute(self, store, editor_unit):
        """P7 验收主线：export → 市场安装 → GraphRuntime execute(21)=42。"""
        uid = editor_unit(_double_graph(),
                          {"id": "chain-demo", "type": "agent", "name": "链路演示"})
        # 双注册：内核主表 + 运行态门控表
        assert store.registry.get_unit(uid) is not None
        assert plugin_registry.get_unit(uid) is not None
        # 账本 + 落盘
        entries = {e["id"]: e for e in store.lock_entries()}
        assert uid in entries and entries[uid]["version"] == "0.1.0"
        assert (store.installed_dir / uid / "plugin.json").exists()
        # 从安装后的 unit 取回图执行（证明 zip→manifest→node_graph 往返无损）
        res = GraphRuntime(store.registry).execute(
            store.registry.get_unit(uid).node_graph, 21)
        assert res["result"] == 42 and res["outputs"]["x"] == 42

    def test_judge_condition_graph_executes(self, store, editor_unit):
        """judge 控制流：按 condition 选分支（编辑器画的判断图真能跑）。"""
        graph = {"nodes": [
            {"id": "e", "type": "entry"},
            {"id": "j", "type": "judge"},
            {"id": "big", "type": "process", "params": {"expr": "'big'"}},
            {"id": "small", "type": "process", "params": {"expr": "'small'"}},
            {"id": "x", "type": "exit"}],
            "edges": [
                {"from": "e", "to": "j"},
                {"from": "j", "to": "big", "condition": "payload > 10"},
                {"from": "j", "to": "small", "condition": "payload <= 10"},
                {"from": "big", "to": "x"}, {"from": "small", "to": "x"}]}
        uid = editor_unit(graph, {"id": "chain-judge"})
        node_graph = store.registry.get_unit(uid).node_graph
        rt = GraphRuntime(store.registry)
        assert rt.execute(node_graph, 21)["result"] == "big"
        assert rt.execute(node_graph, 5)["result"] == "small"

    def test_plugin_node_graph_executes(self, store, market_unit, editor_unit):
        """plugin 节点引用市场 unit 的 tools 贡献点（画布形状 params.ref）。"""
        market_unit(_manifest_raw(id="chain-target", contributions={
            "tools": ["p7_double_tools:p7_double_tools"]}),
            {"p7_double_tools.py": DOUBLE_TOOL_SRC})
        graph = {"nodes": [
            {"id": "e", "type": "entry"},
            {"id": "k", "type": "plugin",
             "params": {"ref": "chain-target", "method": "double"}},
            {"id": "x", "type": "exit"}],
            "edges": [{"from": "e", "to": "k"}, {"from": "k", "to": "x"}]}
        uid = editor_unit(graph, {"id": "chain-plugin"})
        # 归一后节点级 ref 落进 manifest（市场安装同通道）
        node = {n["id"]: n for n in
                store.registry.get_unit(uid).node_graph["nodes"]}["k"]
        assert node["ref"] == "chain-target"
        res = GraphRuntime(store.registry).execute(
            store.registry.get_unit(uid).node_graph, 21)
        assert res["result"] == 42

    def test_team_type_install(self, store, editor_unit):
        """team 类型图：team_def.graph 随身，安装后同样可执行。"""
        uid = editor_unit(_double_graph(), {"id": "chain-team", "type": "team"})
        unit = store.registry.get_unit(uid)
        assert unit.type == "team"
        assert unit.team_def["graph"]["nodes"]
        assert GraphRuntime(store.registry).execute(unit.node_graph, 21)["result"] == 42

    def test_duplicate_install_rejected(self, store, editor_unit):
        editor_unit(_double_graph(), {"id": "chain-dup"})
        blob, name = export_unit(_double_graph(), {"id": "chain-dup"})
        with pytest.raises(MarketError, match="已在注册表"):
            store.install_upload(blob, name)

    def test_uninstall_full_chain(self, store, editor_unit):
        editor_unit(_double_graph(), {"id": "chain-uninstall"})
        store.uninstall("chain-uninstall")
        assert store.registry.get_unit("chain-uninstall") is None
        assert plugin_registry.get_unit("chain-uninstall") is None
        assert not (store.installed_dir / "chain-uninstall").exists()
        assert "chain-uninstall" not in {e["id"] for e in store.lock_entries()}


# ==================== 端点 ==================== #
class TestEditorEndpoints:
    def test_templates(self, client):
        d = client.get("/api/editor/templates").json()
        assert len(d["minimal"]["nodes"]) == 3     # entry/process/exit
        assert len(d["encyclopedia"]["nodes"]) == 13  # 单 Agent 成品图
        assert {t["type"] for t in d["node_types"]} == set(NODE_TYPES)
        assert all(t.get("label") and t.get("hint") for t in d["node_types"])

    def test_validate_endpoint_ok(self, client):
        r = client.post("/api/editor/validate", json={"graph": minimal_graph()})
        assert r.status_code == 200
        assert r.json() == {"ok": True, "errors": []}

    def test_validate_endpoint_errors(self, client):
        bad = {"nodes": [{"id": "a", "type": "entry"}, {"id": "a", "type": "exit"}],
               "edges": []}
        d = client.post("/api/editor/validate", json={"graph": bad}).json()
        assert d["ok"] is False and any("id 重复" in e for e in d["errors"])

    def test_validate_endpoint_encyclopedia_template(self, client):
        """内置模板经端点校验零错误（引用检查走 unit_registry 超集）。"""
        g = client.get("/api/editor/templates").json()["encyclopedia"]
        d = client.post("/api/editor/validate", json={"graph": g}).json()
        assert d == {"ok": True, "errors": []}

    def test_export_endpoint_zip(self, client):
        r = client.post("/api/editor/export",
                        json={"graph": minimal_graph(), "meta": {"id": "ep-export"}})
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/zip"
        pkg = parse_upload(r.content, "ep-export.zip")
        assert pkg.unit_id == "ep-export"

    def test_export_endpoint_bad_graph_400(self, client):
        r = client.post("/api/editor/export",
                        json={"graph": {}, "meta": {"id": "ep-bad"}})
        assert r.status_code == 400 and "detail" in r.json()

    def test_install_endpoint_full_chain(self, client, store):
        r = client.post("/api/editor/install",
                        json={"graph": _double_graph(),
                              "meta": {"id": "ep-install"}})
        assert r.status_code == 200, r.text
        assert r.json()["installed"]["id"] == "ep-install"
        assert store.registry.get_unit("ep-install") is not None
        res = GraphRuntime(store.registry).execute(
            store.registry.get_unit("ep-install").node_graph, 21)
        assert res["result"] == 42
        store.uninstall("ep-install")  # 端点直装：显式卸，防污染后续用例

    def test_install_endpoint_bad_graph_400(self, client, store):
        r = client.post("/api/editor/install",
                        json={"graph": {"nodes": [{"id": "a", "type": "widget"}],
                                        "edges": []},
                              "meta": {"id": "ep-bad-graph"}})
        assert r.status_code == 400
        assert store.registry.get_unit("ep-bad-graph") is None

    def test_install_endpoint_meta_missing_id_400(self, client):
        r = client.post("/api/editor/install",
                        json={"graph": minimal_graph(), "meta": {}})
        assert r.status_code == 400 and "unit id" in r.json()["detail"]

    def test_install_endpoint_meta_bad_type_400(self, client):
        r = client.post("/api/editor/install",
                        json={"graph": minimal_graph(),
                              "meta": {"id": "ep-x", "type": "widget"}})
        assert r.status_code == 400 and "type 非法" in r.json()["detail"]

    def test_install_endpoint_platform_gate_400(self, client, store):
        """meta.min_platform 走市场版本门禁：99.0.0 → 400 且不落盘。"""
        r = client.post("/api/editor/install",
                        json={"graph": minimal_graph(),
                              "meta": {"id": "ep-gate", "min_platform": "99.0.0"}})
        assert r.status_code == 400 and "平台版本不满足" in r.json()["detail"]
        assert store.registry.get_unit("ep-gate") is None
        assert not (store.installed_dir / "ep-gate").exists()

    def test_exported_zip_uploads_via_market_endpoint(self, client, store):
        """编辑器导出的 zip 与市场上传同格式：/api/market/upload 直接吃。"""
        blob, name = export_unit(_double_graph(), {"id": "ep-interop"})
        r = client.post("/api/market/upload",
                        files={"file": (name, blob, "application/zip")})
        assert r.status_code == 200, r.text
        assert r.json()["installed"]["id"] == "ep-interop"
        store.uninstall("ep-interop")
