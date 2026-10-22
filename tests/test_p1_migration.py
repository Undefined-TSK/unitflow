"""P1 收尾测试：内置插件迁移到 Unit 新契约 + app.py 接入口。

验收口径（master plan §11 P1：现有测试不回归；单 Agent 图可跑）：
1. 23 项内置 manifest 全部通过 unit.schema.json 校验并可注册（契约迁移零丢失）；
2. plugin_registry 即 UnitRegistry 子类——内核接管，门控/工具汇总单一实现；
3. 单一真值源：BUILTIN_PLUGINS 投影逐字段等于 BUILTIN_UNIT_MANIFESTS；
4. agent_tools 贡献可解析为裸 callable，顺序与插件化前恒等（11 工具裁判）；
5. app.py 接入口：/api/units 视图含 23 内置 + 示例 unit，
   内置 id 的门控与 /api/plugins 合并一致（两视图不漂移）。
"""
from __future__ import annotations

from pypedia.plugins import BUILTIN_PLUGINS, plugin_registry
from pypedia.plugins.manifests import _TOOLS_BY_PLUGIN
from pypedia.units import UnitRegistry
from pypedia.units.builtins import BUILTIN_UNIT_MANIFESTS, register_builtins


# ---------- 1. 契约迁移完整性 ---------- #
def test_builtin_manifests_all_validate_and_register():
    """23 项 manifest 全部过 schema 校验，并可注册进全新 registry。"""
    assert len(BUILTIN_UNIT_MANIFESTS) == 23
    reg = UnitRegistry(env_resolver=lambda name: True)
    assert register_builtins(reg) == 23
    assert register_builtins(reg) == 0  # 幂等：重复注册跳过
    assert len(reg.all_units()) == 23
    assert {m.id for m in reg.all_units()} == {p.id for p in BUILTIN_PLUGINS}


# ---------- 2. 单一真值源（投影不漂移） ---------- #
def test_plugin_projection_matches_manifests():
    """旧 Plugin 视图逐字段投影自 Unit manifest（apply 归一 instant/restart）。"""
    by_id = {m["id"]: m for m in BUILTIN_UNIT_MANIFESTS}
    for p in BUILTIN_PLUGINS:
        raw = by_id[p.id]
        assert p.name == raw["name"] and p.version == raw["version"]
        assert p.description == raw["description"]
        assert p.default_enabled == raw["default_enabled"]
        assert p.env_gate == raw.get("env_gate", "")
        assert p.switchable == raw["switchable"]
        assert raw["type"] == "plugin" and raw["form"] == "instance"
        assert raw["apply"] in ("immediate", "restart")
        assert p.apply == {"immediate": "instant", "restart": "restart"}[raw["apply"]]


def test_tools_by_plugin_projection():
    """_TOOLS_BY_PLUGIN 从 agent_tools 贡献投影：分组、顺序、内容恒等。"""
    assert _TOOLS_BY_PLUGIN == {
        "agent-memory": ("pypedia.agent.server_tools",
                         ("memory_search", "memory_add", "memory_patch", "memory_remove")),
        "agent-skills": ("pypedia.agent.server_tools", ("skill_list", "skill_view")),
        "agent-delegate": ("pypedia.agent.delegate", ("delegate_task",)),
    }


# ---------- 3. 内核接管 ---------- #
def test_registry_is_kernel_subclass():
    """plugin_registry 是 UnitRegistry 实例——门控/工具汇总由内核单一实现。"""
    assert isinstance(plugin_registry, UnitRegistry)
    assert plugin_registry.get_unit("agent-memory") is not None
    assert plugin_registry.state_dir == "plugins"  # 旧 state.json 路径不漂移
    assert plugin_registry.is_enabled("agent-memory") is True
    # 旧异常契约仍在（未知 id / 空壳 / 非 bool）
    try:
        plugin_registry.set_enabled("ghost", True)
    except KeyError:
        pass
    else:
        raise AssertionError("未知 id 应抛 KeyError")
    try:
        plugin_registry.set_enabled("backup", True)
    except ValueError:
        pass
    else:
        raise AssertionError("空壳入口应抛 ValueError")


# ---------- 4. agent_tools 贡献解析与顺序恒等 ---------- #
def test_agent_tools_entries_resolve_and_order():
    """agent_tools 入口可解析为裸 callable；默认顺序与历史恒等（对象身份）。"""
    from pypedia.agent.browser_tools import BROWSER_TOOLS
    from pypedia.agent.delegate import DELEGATE_TOOLS
    from pypedia.agent.server_tools import SERVER_TOOLS

    reg = UnitRegistry(env_resolver=lambda name: True)
    register_builtins(reg)
    tools = reg.enabled_agent_tools()
    assert [t.__name__ for t in tools] == [
        "memory_search", "memory_add", "memory_patch", "memory_remove",
        "skill_list", "skill_view", "delegate_task",
    ]
    assert BROWSER_TOOLS + tools == BROWSER_TOOLS + SERVER_TOOLS + DELEGATE_TOOLS
    # 子代理：排除 delegate（禁嵌套委派）
    sub = reg.enabled_agent_tools(exclude_unit_ids={"agent-delegate"})
    assert [t.__name__ for t in sub] == [
        "memory_search", "memory_add", "memory_patch", "memory_remove",
        "skill_list", "skill_view",
    ]


# ---------- 5. app.py 接入口：/api/units ---------- #
class TestUnitsEndpoints:
    def test_units_view_contains_builtins_and_examples(self, client):
        """内核视图含 23 内置 + 示例 unit（hello-world / python-encyclopedia）。"""
        r = client.get("/api/units")
        assert r.status_code == 200
        d = r.json()
        ids = {u["id"] for u in d["units"]}
        assert {p.id for p in BUILTIN_PLUGINS} <= ids
        assert {"hello-world", "python-encyclopedia"} <= ids
        assert set(d["summary"]) == {"total", "enabled", "env_blocked", "by_type"}
        assert d["summary"]["total"] == len(d["units"])
        assert d["summary"]["by_type"]["plugin"] == 24  # 23 内置 + hello-world
        assert d["summary"]["by_type"]["agent"] == 1    # python-encyclopedia

    def test_units_gate_view_matches_plugins(self, client):
        """合并视图：内置 unit 的 enabled/env_blocked 与 /api/plugins 逐条一致。"""
        plugins = {p["id"]: p for p in client.get("/api/plugins").json()["plugins"]}
        units = {u["id"]: u for u in client.get("/api/units").json()["units"]}
        for pid, p in plugins.items():
            u = units[pid]
            assert u["enabled"] == p["enabled"], pid
            assert u["env_blocked"] == p["env_blocked"], pid

    def test_unit_detail_has_node_graph(self, client):
        """python-encyclopedia 成品对象：详情含 node_graph（图即引擎可执行）。"""
        r = client.get("/api/units/python-encyclopedia")
        assert r.status_code == 200
        u = r.json()["unit"]
        assert u["type"] == "agent" and u["form"] == "instance"
        assert u["agent_def"]["identity"] == "①"
        graph = u["node_graph"]
        assert len(graph["nodes"]) == 13 and len(graph["edges"]) == 13
        types = {n["type"] for n in graph["nodes"]}
        assert {"entry", "process", "model-call", "judge", "exit"} <= types

    def test_unit_detail_unknown_404(self, client):
        r = client.get("/api/units/no-such-unit")
        assert r.status_code == 404
