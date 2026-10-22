"""P1 Unit 内核测试：契约 / 注册表门控 / Profile / 装载器 / 图即引擎。

验证「万物皆插件·图即引擎」内核可运行、可单测，且不依赖既有 519 测试基线。
"""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path

import pytest

from pypedia.units import (
    GraphRuntime,
    Manifest,
    ProfileManager,
    UnitLoader,
    UnitRegistry,
    unit_registry,
)
from pypedia.units.exceptions import GraphError, RegistryError

EXAMPLES = Path(__file__).resolve().parents[1] / "units" / "examples"


# —— 1. 契约加载 —— #
def test_manifest_hello_world_loads_and_validates():
    m = Manifest.from_file(EXAMPLES / "hello-world" / "plugin.json")
    assert m.id == "hello-world"
    assert m.type == "plugin"
    assert m.form == "instance"
    assert m.contributions["tools"] == ["plugin:list_tools"]


def test_manifest_rejects_team_without_team_def():
    with pytest.raises(Exception):  # ManifestError（schema 条件必填）
        Manifest.from_dict({"id": "t", "type": "team", "name": "T", "version": "1.0.0"})


# —— 2. 注册表门控 —— #
def _resolver(env: dict):
    def r(name: str) -> bool:
        if not name:
            return True
        return bool(env.get(name))

    return r


def test_registry_gate_follows_env_by_default():
    env = {"FLAG_X": False}
    reg = UnitRegistry(env_resolver=_resolver(env))
    m = Manifest.from_dict({
        "id": "p1", "type": "plugin", "name": "P1", "version": "1.0.0",
        "env_gate": "FLAG_X", "default_enabled": True,
    })
    reg.register(m)
    assert reg.is_enabled("p1") is False  # 缺省跟随部署态（env 关）
    env["FLAG_X"] = True
    assert reg.is_enabled("p1") is True


def test_registry_switchable_always_on_and_rejects_set():
    reg = UnitRegistry(env_resolver=_resolver({}))
    m = Manifest.from_dict({
        "id": "shell", "type": "plugin", "name": "Shell", "version": "1.0.0",
        "switchable": False,
    })
    reg.register(m)
    assert reg.is_enabled("shell") is True
    with pytest.raises(RegistryError):
        reg.set_enabled("shell", False)


def test_registry_unknown_id_fail_open():
    reg = UnitRegistry(env_resolver=_resolver({}))
    assert reg.is_enabled("never-registered") is True


def test_registry_user_state_overrides_env():
    env = {"FLAG_Y": True}
    reg = UnitRegistry(env_resolver=_resolver(env))
    m = Manifest.from_dict({
        "id": "p2", "type": "plugin", "name": "P2", "version": "1.0.0",
        "env_gate": "FLAG_Y",
    })
    reg.register(m)
    assert reg.is_enabled("p2") is True  # env 开
    reg.set_enabled("p2", False)
    assert reg.is_enabled("p2") is False  # 用户态覆盖 → 关


# —— 3. Profile 隔离 —— #
def test_profile_create_list_delete_isolation():
    with tempfile.TemporaryDirectory() as tmp:
        pm = ProfileManager(base=Path(tmp) / "profiles")
        assert "default" in pm.list_profiles()
        p = pm.create_profile("agentA")
        for sub in ("config", "state", "memory", "sessions", "credentials"):
            assert (p / sub).is_dir()
        assert "agentA" in pm.list_profiles()
        pm.switch("agentA")
        assert pm.current == "agentA"
        pm.delete_profile("agentA")
        assert "agentA" not in pm.list_profiles()


# —— 4. 装载器扫描 —— #
def test_loader_scans_hello_world_and_registers():
    reg = UnitRegistry(env_resolver=_resolver({}))
    loader = UnitLoader(reg)
    manifests = loader.scan(EXAMPLES / "hello-world")
    assert len(manifests) == 1
    assert reg.get_unit("hello-world") is not None
    tools = reg.enabled_tools()
    assert any(t["source"].startswith("plugin:list_tools") for t in tools)


# —— 5. 图即引擎：插件链 —— #
def _build_engine():
    reg = UnitRegistry(env_resolver=_resolver({}))
    loader = UnitLoader(reg)
    loader.scan(EXAMPLES / "hello-world")
    return reg, GraphRuntime(reg)


def test_graph_plugin_chain_executes():
    reg, rt = _build_engine()
    graph = {
        "nodes": [
            {"id": "in", "type": "input"},
            {"id": "p", "type": "plugin", "ref": "hello-world"},
            {"id": "out", "type": "output"},
        ],
        "edges": [
            {"from": "in", "to": "p"},
            {"from": "p", "to": "out"},
        ],
    }
    res = rt.execute(graph, input_data="PyPedia")
    assert res["result"] == "Hello, PyPedia! 来自 hello-world 插件。"
    assert "out" in res["outputs"]


# —— 6. 图即引擎：judge 分支 —— #
def _engine_with_demo():
    reg = UnitRegistry(env_resolver=_resolver({}))
    for uid, entry in (("echo", "echo_entry"), ("dec", "dec_entry")):
        reg.register(Manifest.from_dict({
            "id": uid, "type": "plugin", "name": uid, "version": "1.0.0",
            "contributions": {"tools": [f"pypedia.units._demo_plugins:{entry}"]},
        }))
    return reg, GraphRuntime(reg)


def test_graph_judge_branch_selects_true_path():
    reg, rt = _engine_with_demo()
    graph = {
        "nodes": [
            {"id": "in", "type": "input"},
            {"id": "j", "type": "judge"},
            {"id": "e", "type": "plugin", "ref": "echo"},
            {"id": "out", "type": "output"},
        ],
        "edges": [
            {"from": "in", "to": "j"},
            {"from": "j", "to": "e", "condition": "payload == 'go'"},
            {"from": "j", "to": "out", "condition": ""},  # fallback
        ],
    }
    res = rt.execute(graph, input_data="go")
    assert res["result"] == "echo:go"
    # 反向分支
    res2 = rt.execute(graph, input_data="stop")
    assert res2["result"] == "stop"


# —— 7. 图即引擎：循环（judge 回指）终止 —— #
def test_graph_loop_terminates_via_judge():
    reg, rt = _engine_with_demo()
    graph = {
        "nodes": [
            {"id": "in", "type": "input"},
            {"id": "j", "type": "judge"},
            {"id": "d", "type": "plugin", "ref": "dec"},
            {"id": "out", "type": "output"},
        ],
        "edges": [
            {"from": "in", "to": "j"},
            {"from": "j", "to": "d", "condition": "payload > 0"},
            {"from": "d", "to": "j"},
            {"from": "j", "to": "out", "condition": ""},
        ],
    }
    res = rt.execute(graph, input_data=3)
    assert res["result"] == 0  # 3→2→1→0 后退出循环


# —— 8. 图即引擎：model-call —— #
def test_graph_model_call_uses_executor():
    reg, _ = _engine_with_demo()
    rt = GraphRuntime(reg, model_executor=lambda prompt, **kw: f"model:{prompt}")
    graph = {
        "nodes": [
            {"id": "in", "type": "input"},
            {"id": "m", "type": "model-call"},
            {"id": "out", "type": "output"},
        ],
        "edges": [
            {"from": "in", "to": "m"},
            {"from": "m", "to": "out"},
        ],
    }
    res = rt.execute(graph, input_data="hi")
    assert res["result"] == "model:hi"


def test_graph_requires_input_node():
    reg, rt = _engine_with_demo()
    with pytest.raises(GraphError):
        rt.execute({"nodes": [{"id": "x", "type": "output"}], "edges": []})


def test_graph_missing_input_node_errors():
    reg, rt = _engine_with_demo()
    with pytest.raises(GraphError):
        rt.execute({"nodes": [{"id": "o", "type": "output"}], "edges": []})
