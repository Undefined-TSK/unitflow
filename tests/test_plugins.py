"""插件系统测试（P6-1）：manifest 完整性 / 门控语义 / 状态持久化 / 工具汇总。

覆盖计划测试项 1-7 + 验收口径：
1. manifest 完整性：23 项唯一/kebab-case；env_gate 全是 Settings 真实字段；
   default_enabled == Settings 字段默认值（防漂移——本测试曾抓到 web-fetch
   manifest=True 与 Settings=False 的漂移，已修）；
2. 引用闭环：代码 is_enabled/set_enabled 字面量 id ⊆ 登记集合（防打字 bug
   静默 fail-open）；_TOOLS_BY_PLUGIN key 同理；
3. state 持久化：写盘/重载保持/原子写无残留；
4. 数据卫生：损坏→隔离+默认值+不崩；未知 id/非 bool 条目忽略；
5. AND 语义矩阵：用户态×部署态四组合 + env_blocked + 无用户态跟随部署态
   （行为零回退：本机 .env 打开过的开关不被静默关掉）；
6. 实时 getattr：monkeypatch settings 后立即跟随（不缓存）；
7. 工具汇总矩阵：11/10/9/7/4 + 顺序恒等 + 子代理工具集。

注意：阶段 1 尚无接线调用点，test_reference_closure 的 referenced 集合为空
（真守卫从阶段 3/5 接线后才开始咬人）。
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from pypedia.config import Settings, settings
from pypedia.plugins import BUILTIN_PLUGINS, PluginRegistry, describe, plugin_registry
from pypedia.plugins.manifests import _TOOLS_BY_PLUGIN  # 同包私有映射，测试需校验其 key

_SHELL_IDS = {
    "agent-compress", "agent-hooks", "backup",
    "embed-cache", "long-context", "ask-quota", "builtin-corpus",
}


# ---------- 1. manifest 完整性 ---------- #
def test_manifest_completeness():
    """23 项登记完整；default_enabled 与 Settings 字段默认值一一对应（防漂移）。"""
    assert len(BUILTIN_PLUGINS) == 23  # 16 实插件 + 7 空壳入口（空壳也留入口）
    ids = [p.id for p in BUILTIN_PLUGINS]
    assert len(set(ids)) == 23, f"重复 id：{sorted(i for i in ids if ids.count(i) > 1)}"
    kebab = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
    ver = re.compile(r"^\d+\.\d+\.\d+$")
    for p in BUILTIN_PLUGINS:
        assert kebab.match(p.id), f"id 不是 kebab-case：{p.id}"
        assert ver.match(p.version), f"version 不是 semver：{p.version}"
        assert p.name and p.description
        assert p.apply in ("instant", "restart")
        if p.switchable:
            assert p.env_gate, f"{p.id} 可开关但无 env_gate"
            field = Settings.model_fields.get(p.env_gate)
            assert field is not None, f"{p.env_gate} 不是 Settings 字段（{p.id}）"
            assert p.default_enabled == field.default, (
                f"{p.id} 的 default_enabled={p.default_enabled} 与 "
                f"Settings.{p.env_gate} 默认值 {field.default} 漂移")
        else:
            assert p.env_gate == "", f"空壳 {p.id} 不应挂部署态开关"
            assert p.apply == "instant"
    assert {p.id for p in BUILTIN_PLUGINS if not p.switchable} == _SHELL_IDS


def test_describe_is_manifest_only():
    """manifests.describe() 只含 manifest 字段（运行时状态在 list_plugins）。"""
    items = describe()
    assert len(items) == 23
    for item in items:
        assert "enabled" not in item and "env_blocked" not in item
        assert set(item) == {"id", "name", "version", "description",
                             "default_enabled", "env_gate", "switchable", "apply"}


# ---------- 2. 引用闭环 ---------- #
def test_reference_closure():
    """代码里 is_enabled/set_enabled 的字面量 id 必须已登记（防静默失效）。"""
    root = Path(__file__).resolve().parents[1]
    pat = re.compile(r"""\.(?:is_enabled|set_enabled)\(\s*['"]([a-z0-9-]+)['"]""")
    referenced: set[str] = set()
    for py in (root / "pypedia").rglob("*.py"):
        referenced |= set(pat.findall(py.read_text(encoding="utf-8")))
    registered = {p.id for p in BUILTIN_PLUGINS}
    assert referenced <= registered, f"未登记的插件 id 引用：{sorted(referenced - registered)}"
    assert set(_TOOLS_BY_PLUGIN) <= registered


# ---------- 3. state 持久化 ---------- #
def test_state_persist_and_reload(tmp_path, monkeypatch):
    """写盘 → 新实例（模拟重启）读回；未写过的项走部署态默认。"""
    monkeypatch.setenv("PYPEDIA_DATA", str(tmp_path))
    reg = PluginRegistry()
    reg.set_enabled("agent-memory", False)
    reg.set_enabled("agent-cron", True)
    fresh = PluginRegistry()
    assert fresh.is_enabled("agent-memory") is False
    assert fresh.is_enabled("agent-cron") is True
    assert fresh.is_enabled("agent-skills") is True


def test_save_atomic_no_tmp_leftovers(tmp_path, monkeypatch):
    """原子写：落盘内容正确且不留 .state-*.tmp 残留。"""
    monkeypatch.setenv("PYPEDIA_DATA", str(tmp_path))
    reg = PluginRegistry()
    reg.set_enabled("agent-memory", False)
    plugins_dir = tmp_path / "plugins"
    assert list(plugins_dir.glob(".state-*")) == []
    assert json.loads((plugins_dir / "state.json").read_text(encoding="utf-8")) \
        == {"agent-memory": False}


def test_set_enabled_rejections(tmp_path, monkeypatch):
    """未知 id → KeyError；非 bool → TypeError；空壳入口 → ValueError。"""
    monkeypatch.setenv("PYPEDIA_DATA", str(tmp_path))
    reg = PluginRegistry()
    with pytest.raises(KeyError):
        reg.set_enabled("no-such-plugin", True)
    with pytest.raises(TypeError):
        reg.set_enabled("agent-memory", "yes")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="暂无独立开关"):
        reg.set_enabled("backup", True)


# ---------- 4. 数据卫生 ---------- #
def test_corrupt_state_quarantined(tmp_path, monkeypatch, caplog):
    """state.json 损坏 → 隔离改名 + 默认值 + 不崩（复刻 evolution 数据损坏教训）。"""
    monkeypatch.setenv("PYPEDIA_DATA", str(tmp_path))
    state_file = tmp_path / "plugins" / "state.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text("{不是合法 JSON", encoding="utf-8")
    with caplog.at_level(logging.ERROR, logger="pypedia"):
        reg = PluginRegistry()
        assert reg.is_enabled("agent-memory") is True  # 损坏不崩，回落部署态默认
    assert list(state_file.parent.glob("state.corrupt-*.json")), "损坏原件应被隔离保留"
    assert not state_file.exists()
    assert "plugin_state_corrupt" in caplog.text


def test_state_entries_hygiene(tmp_path, monkeypatch):
    """加载时忽略未登记 id 与非 bool 条目（防手改文件把状态带歪）。"""
    monkeypatch.setenv("PYPEDIA_DATA", str(tmp_path))
    state_file = tmp_path / "plugins" / "state.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text(json.dumps({
        "agent-memory": False,      # 正常项
        "ghost-plugin": True,       # 未登记 id → 忽略
        "agent-skills": "on",       # 非 bool → 忽略
    }), encoding="utf-8")
    reg = PluginRegistry()
    assert reg.is_enabled("agent-memory") is False
    assert reg.is_enabled("agent-skills") is True


# ---------- 5. AND 语义矩阵 ---------- #
def test_and_semantics_matrix(tmp_path, monkeypatch):
    """用户态 × 部署态四组合；env_blocked 只归因部署态。"""
    monkeypatch.setenv("PYPEDIA_DATA", str(tmp_path))
    reg = PluginRegistry()
    monkeypatch.setattr(settings, "AGENT_SKILLS_ENABLE", True)
    reg.set_enabled("agent-skills", True)
    assert reg.is_enabled("agent-skills") is True
    assert reg.env_blocked("agent-skills") is False
    # 部署态关 → 整体关（用户态救不回），且如实标记 env_blocked
    monkeypatch.setattr(settings, "AGENT_SKILLS_ENABLE", False)
    assert reg.is_enabled("agent-skills") is False
    assert reg.env_blocked("agent-skills") is True
    # 用户态关 + 部署态开 → 关（用户级子开关说了算），不记 env_blocked
    reg.set_enabled("agent-skills", False)
    monkeypatch.setattr(settings, "AGENT_SKILLS_ENABLE", True)
    assert reg.is_enabled("agent-skills") is False
    assert reg.env_blocked("agent-skills") is False
    # 双关 → 关
    monkeypatch.setattr(settings, "AGENT_SKILLS_ENABLE", False)
    assert reg.is_enabled("agent-skills") is False


def test_absent_state_follows_deployment(tmp_path, monkeypatch):
    """无显式用户态时跟随部署态——.env 打开过的开关不被静默关掉（行为零回退）。"""
    monkeypatch.setenv("PYPEDIA_DATA", str(tmp_path))
    reg = PluginRegistry()
    monkeypatch.setattr(settings, "ENABLE_WEB_FETCH", True)
    assert reg.is_enabled("web-fetch") is True
    assert reg.env_blocked("web-fetch") is False
    monkeypatch.setattr(settings, "ENABLE_WEB_FETCH", False)
    assert reg.is_enabled("web-fetch") is False
    assert reg.env_blocked("web-fetch") is True
    # 用户显式关闭后，即使部署态开着也不生效
    monkeypatch.setattr(settings, "ENABLE_WEB_FETCH", True)
    reg.set_enabled("web-fetch", False)
    assert reg.is_enabled("web-fetch") is False


# ---------- 6. 实时 getattr ---------- #
def test_env_gate_realtime(tmp_path, monkeypatch):
    """env 门控实时读 settings（不缓存）：monkeypatch 后立即跟随。"""
    monkeypatch.setenv("PYPEDIA_DATA", str(tmp_path))
    reg = PluginRegistry()
    monkeypatch.setattr(settings, "REVIEW_ENABLE", True)
    assert reg.is_enabled("review") is True
    monkeypatch.setattr(settings, "REVIEW_ENABLE", False)  # 不重载不重启
    assert reg.is_enabled("review") is False
    assert reg.env_blocked("review") is True
    monkeypatch.setattr(settings, "REVIEW_ENABLE", True)
    assert reg.is_enabled("review") is True


# ---------- 未知 id 与空壳 ---------- #
def test_unknown_id_fail_open(tmp_path, monkeypatch, caplog):
    """未知 id fail-open（行为不退回到插件化之前）+ warning 留痕。"""
    monkeypatch.setenv("PYPEDIA_DATA", str(tmp_path))
    reg = PluginRegistry()
    with caplog.at_level(logging.WARNING, logger="pypedia"):
        assert reg.is_enabled("ghost-plugin") is True
    assert reg.env_blocked("ghost-plugin") is False
    assert "plugin_unknown_id" in caplog.text


def test_shell_plugins_always_enabled(tmp_path, monkeypatch):
    """7 个空壳入口：is_enabled 恒 True，与 settings 改动无关。"""
    monkeypatch.setenv("PYPEDIA_DATA", str(tmp_path))
    reg = PluginRegistry()
    for pid in _SHELL_IDS:
        assert reg.is_enabled(pid) is True
        assert reg.env_blocked(pid) is False


# ---------- 7. 工具汇总矩阵 ---------- #
def test_tool_aggregation_matrix(tmp_path, monkeypatch):
    """11/10/9/7/4 矩阵 + 顺序恒等 + 子代理工具集（test_agent.py 的 11 断言是裁判）。"""
    from pypedia.agent.browser_tools import BROWSER_TOOLS
    from pypedia.agent.delegate import DELEGATE_TOOLS
    from pypedia.agent.server_tools import SERVER_TOOLS

    monkeypatch.setenv("PYPEDIA_DATA", str(tmp_path))
    reg = PluginRegistry()
    for gate in ("AGENT_MEMORY_ENABLE", "AGENT_SKILLS_ENABLE", "AGENT_DELEGATE_ENABLE"):
        monkeypatch.setattr(settings, gate, True)
    historical = BROWSER_TOOLS + SERVER_TOOLS + DELEGATE_TOOLS  # 插件化前的恒等式

    # 默认全开：11 工具，顺序与对象身份双重恒等
    assert BROWSER_TOOLS + reg.enabled_agent_tools() == historical
    assert len(BROWSER_TOOLS + reg.enabled_agent_tools()) == 11

    # delegate off → 10
    reg.set_enabled("agent-delegate", False)
    assert len(BROWSER_TOOLS + reg.enabled_agent_tools()) == 10
    reg.set_enabled("agent-delegate", True)

    # memory off → 7，且 skill 工具不受误伤（按 id 分组而非 provider key 的意义所在）
    reg.set_enabled("agent-memory", False)
    names = [t.__name__ for t in reg.enabled_agent_tools()]
    assert names == ["skill_list", "skill_view", "delegate_task"]
    assert len(BROWSER_TOOLS + reg.enabled_agent_tools()) == 7
    reg.set_enabled("agent-memory", True)

    # skills off → 9
    reg.set_enabled("agent-skills", False)
    names = [t.__name__ for t in reg.enabled_agent_tools()]
    assert names == ["memory_search", "memory_add", "memory_patch",
                     "memory_remove", "delegate_task"]
    assert len(BROWSER_TOOLS + reg.enabled_agent_tools()) == 9
    reg.set_enabled("agent-skills", True)

    # 全 off → 仅 browser 4 个
    for pid in ("agent-memory", "agent-skills", "agent-delegate"):
        reg.set_enabled(pid, False)
    assert reg.enabled_agent_tools() == []
    assert BROWSER_TOOLS + reg.enabled_agent_tools() == BROWSER_TOOLS

    # 子代理工具集：禁嵌套委派（默认 = SERVER_TOOLS，无 delegate_task）
    for pid in ("agent-memory", "agent-skills", "agent-delegate"):
        reg.set_enabled(pid, True)
    sub = reg.enabled_agent_tools(include_delegate=False)
    assert sub == SERVER_TOOLS
    assert all(t.__name__ != "delegate_task" for t in sub)
    # 子代理集同样受门控：memory off → 只剩 2 个 skill 工具
    reg.set_enabled("agent-memory", False)
    assert [t.__name__ for t in reg.enabled_agent_tools(include_delegate=False)] \
        == ["skill_list", "skill_view"]


# ---------- 全量视图 ---------- #
def test_list_plugins_shape_and_summary(tmp_path, monkeypatch):
    """list_plugins 形状 + summary 汇总（固定部署态，摆脱环境/.env/stub 干扰）。

    注意：测试环境 stubs 会把 PRESET_SOURCES_ENABLE 置 False（绝不联网抓取），
    故三个可能随环境漂移的门控在此显式固定。
    """
    monkeypatch.setenv("PYPEDIA_DATA", str(tmp_path))
    reg = PluginRegistry()
    monkeypatch.setattr(settings, "AUTH_ENABLE", False)
    monkeypatch.setattr(settings, "ENABLE_WEB_FETCH", False)
    monkeypatch.setattr(settings, "PRESET_SOURCES_ENABLE", True)
    items = reg.list_plugins()
    assert len(items) == 23
    assert {i["id"] for i in items} == {p.id for p in BUILTIN_PLUGINS}
    expect_keys = {"id", "name", "version", "description", "default_enabled",
                   "env_gate", "switchable", "apply", "enabled", "env_blocked"}
    for item in items:
        assert set(item) == expect_keys
        # 聚合结果与单点查询一致（汇总不走样）
        assert item["enabled"] == reg.is_enabled(item["id"])
        assert item["env_blocked"] == reg.env_blocked(item["id"])
    # auth 与 web-fetch 部署态关闭 → env_blocked=2、enabled=21
    assert reg.summary() == {"total": 23, "enabled": 21, "env_blocked": 2}
    # 部署态全开 → 23 全启用、零拦截
    monkeypatch.setattr(settings, "AUTH_ENABLE", True)
    monkeypatch.setattr(settings, "ENABLE_WEB_FETCH", True)
    assert reg.summary() == {"total": 23, "enabled": 23, "env_blocked": 0}


# ---------- import 纯度（验收口径） ---------- #
def test_read_queries_never_write(tmp_path, monkeypatch):
    """只读查询（is_enabled）不建目录、不写 state.json。"""
    monkeypatch.setenv("PYPEDIA_DATA", str(tmp_path))
    reg = PluginRegistry()
    assert reg.is_enabled("agent-memory") is True  # 触发懒加载（只读）
    assert not (tmp_path / "plugins").exists()


def test_import_has_no_file_side_effects(tmp_path):
    """子进程 import pypedia.plugins：不产生 plugins/ 目录与 state.json。

    （logs/ 日志目录的创建是全项目既有行为——get_logger 首次调用即初始化，
    非本模块副作用，故不断言。）
    """
    data = tmp_path / "data"
    data.mkdir()
    env = dict(os.environ, PYPEDIA_DATA=str(data))
    proc = subprocess.run(
        [sys.executable, "-c", "import pypedia.plugins as p; assert p.plugin_registry"],
        capture_output=True, text=True, env=env,
        cwd=str(Path(__file__).resolve().parents[1]), timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert not (data / "plugins").exists()


def test_import_does_not_touch_home(tmp_path):
    """PYPEDIA_DATA 未设时 import 也不在 HOME 下造 plugins/ 目录。"""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    env = {k: v for k, v in os.environ.items() if k != "PYPEDIA_DATA"}
    env["HOME"] = str(fake_home)
    proc = subprocess.run(
        [sys.executable, "-c", "import pypedia.plugins as p; assert p.plugin_registry"],
        capture_output=True, text=True, env=env,
        cwd=str(Path(__file__).resolve().parents[1]), timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert not (fake_home / ".pypedia" / "plugins").exists()


# ---------- 8. evolution 示范插件（阶段 2） ---------- #
@pytest.fixture
def evo_dir(tmp_path, monkeypatch):
    """隔离 evolution 数据目录。

    reflexion/voyager 的 DATA_DIR 是 **import 时求值**的模块级常量，
    monkeypatch.setenv("PYPEDIA_DATA") 重定向不了它——直接 patch 两个模块的
    DATA_DIR，其后构造的 ReflectionLog/SkillLibrary 实例即写临时目录。
    """
    from pypedia.evolution import reflexion, voyager

    d = tmp_path / "evo"
    d.mkdir()
    monkeypatch.setattr(reflexion, "DATA_DIR", d)
    monkeypatch.setattr(voyager, "DATA_DIR", d)
    return d


def _make_evolution_plugin():
    from pypedia.plugins.evolution import EvolutionPlugin

    return EvolutionPlugin()


def test_evolution_plugin_disabled_zero_observe(evo_dir, monkeypatch):
    """禁用时 observe 零反思零沉淀：基类零触达、无后台线程、无数据落盘。"""
    monkeypatch.setattr(settings, "EVOLUTION_ENABLE", False)
    from pypedia.evolution import Evolution

    seen: list[tuple] = []
    monkeypatch.setattr(Evolution, "observe", lambda self, *a: seen.append(a))
    plugin = _make_evolution_plugin()
    plugin.observe("q", "a", 90.0, True, 3)
    assert seen == []                                  # 基类零触达
    assert plugin.reflections.recent(6) == []          # 零反思
    assert plugin.skills.list_skills() == []           # 零技能沉淀


def test_evolution_plugin_enabled_delegates(evo_dir, monkeypatch):
    """启用时原样委派基类（参数逐一透传）。"""
    monkeypatch.setattr(settings, "EVOLUTION_ENABLE", True)
    from pypedia.evolution import Evolution

    seen: list[tuple] = []
    monkeypatch.setattr(Evolution, "observe", lambda self, *a: seen.append(a))
    plugin = _make_evolution_plugin()
    plugin.observe("q", "a", 90.0, True, 3)
    assert seen == [("q", "a", 90.0, True, 3)]


def test_evolution_plugin_prompt_injection_gate(evo_dir, monkeypatch):
    """禁用时提示词注入空串（系统提示词无进化段）；启用时恢复。"""
    plugin = _make_evolution_plugin()
    plugin.skills.add_skill("图表技能", "当要画图时", "用 mermaid 画")
    monkeypatch.setattr(settings, "EVOLUTION_ENABLE", False)
    assert plugin.prompt_injection() == ""
    monkeypatch.setattr(settings, "EVOLUTION_ENABLE", True)
    assert "图表技能" in plugin.prompt_injection()


def test_evolution_plugin_feedback_gate(evo_dir, monkeypatch):
    """feedback：禁用 → ok=False+disabled 标志且不落盘；启用 → 正常沉淀。"""
    plugin = _make_evolution_plugin()
    monkeypatch.setattr(settings, "EVOLUTION_ENABLE", False)
    r = plugin.feedback("装饰器", "答得太简略")
    assert r["ok"] is False and r["disabled"] is True
    assert plugin.reflections.recent(6) == []
    monkeypatch.setattr(settings, "EVOLUTION_ENABLE", True)
    r = plugin.feedback("装饰器", "答得太简略")
    assert r["ok"] is True
    assert plugin.reflections.recent(6)


def test_evolution_plugin_state_enabled_flag(evo_dir, monkeypatch):
    """state() 附带 enabled 标志（关时仍可看存量数据）。"""
    plugin = _make_evolution_plugin()
    monkeypatch.setattr(settings, "EVOLUTION_ENABLE", True)
    assert plugin.state()["enabled"] is True
    monkeypatch.setattr(settings, "EVOLUTION_ENABLE", False)
    st = plugin.state()
    assert st["enabled"] is False
    assert set(st) >= {"skills", "reflections", "enabled"}


def test_evolution_plugin_exception_passthrough(evo_dir, monkeypatch):
    """插件包装不吞异常：内层抛 → 原样穿透（与基类语义一致）。"""
    plugin = _make_evolution_plugin()

    def boom():
        raise RuntimeError("inner boom")

    monkeypatch.setattr(plugin.skills, "prompt_injection", boom)
    with pytest.raises(RuntimeError, match="inner boom"):
        plugin.prompt_injection()


def test_evolution_endpoints_503_when_disabled(client, monkeypatch):
    """两端点在插件关闭时 503（文案指引设置页）。"""
    monkeypatch.setattr(settings, "EVOLUTION_ENABLE", False)
    r = client.get("/api/evolution")
    assert r.status_code == 503
    assert "自进化插件" in r.json()["detail"]
    r2 = client.post("/api/evolution/feedback",
                     json={"query": "装饰器", "issue": "答得太简略"})
    assert r2.status_code == 503


def test_evolution_endpoint_reports_enabled(client, monkeypatch):
    """开启时 200 且 payload 带 enabled 标志（前端可展示启停态）。"""
    monkeypatch.setattr(settings, "EVOLUTION_ENABLE", True)
    r = client.get("/api/evolution")
    assert r.status_code == 200
    d = r.json()
    assert d["enabled"] is True
    assert set(d) >= {"skills", "reflections", "enabled"}


def test_engine_evolution_is_plugin_instance():
    """engine.evolution 是 EvolutionPlugin 且仍是 Evolution——monkeypatch 路径不变。"""
    from app import engine
    from pypedia.evolution import Evolution
    from pypedia.plugins.evolution import EvolutionPlugin

    assert isinstance(engine.evolution, EvolutionPlugin)
    assert isinstance(engine.evolution, Evolution)


class TestEvolutionPluginEngineWiring:
    """engine 接线：禁用时 ask 全链路零反思、系统提示词无进化段。"""

    def _engine(self, evo_dir):
        from pypedia.engine import PyPediaEngine

        return PyPediaEngine(provider="mock")

    def test_ask_zero_evolution_when_disabled(self, evo_dir, monkeypatch,
                                              fake_chat, fake_confidence):
        monkeypatch.setattr("pypedia.engine.review_answer",
                            lambda *a, **kw: {"verdict": "pass", "notes": [],
                                              "revised": "", "skipped": False})
        eng = self._engine(evo_dir)
        from pypedia.evolution import Evolution

        seen: list[tuple] = []
        monkeypatch.setattr(Evolution, "observe", lambda self, *a: seen.append(a))
        monkeypatch.setattr(settings, "EVOLUTION_ENABLE", False)
        eng.ask("什么是装饰器？", level=3)
        assert seen == []
        assert eng.evolution.reflections.recent(6) == []

    def test_prompt_has_no_evolution_section_when_disabled(self, evo_dir, monkeypatch):
        eng = self._engine(evo_dir)
        eng.evolution.skills.add_skill("图表技能", "当要画图时", "用 mermaid 画")
        monkeypatch.setattr(settings, "EVOLUTION_ENABLE", False)
        assert "图表技能" not in eng._build_system(3, "q")
        monkeypatch.setattr(settings, "EVOLUTION_ENABLE", True)
        assert "图表技能" in eng._build_system(3, "q")


# ---------- 阶段 3：agent 工具层接线（memory/skills/delegate 门控） ---------- #
def test_enabled_agent_tools_all_open():
    """默认全开：memory(4)+skills(2)+delegate(1)=7（不含 browser 4）。"""
    names = {t.__name__ for t in plugin_registry.enabled_agent_tools()}
    assert names == {"memory_search", "memory_add", "memory_patch", "memory_remove",
                     "skill_list", "skill_view", "delegate_task"}


def test_enabled_agent_tools_memory_off(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_MEMORY_ENABLE", False)
    names = {t.__name__ for t in plugin_registry.enabled_agent_tools()}
    assert "memory_search" not in names
    assert {"skill_list", "skill_view", "delegate_task"} <= names


def test_enabled_agent_tools_skills_off(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_SKILLS_ENABLE", False)
    names = {t.__name__ for t in plugin_registry.enabled_agent_tools()}
    assert "skill_list" not in names and "skill_view" not in names
    assert {"memory_search", "memory_add", "memory_patch", "memory_remove",
            "delegate_task"} <= names


def test_enabled_agent_tools_delegate_off(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_DELEGATE_ENABLE", False)
    names = {t.__name__ for t in plugin_registry.enabled_agent_tools()}
    assert "delegate_task" not in names
    assert {"memory_search", "memory_add", "memory_patch", "memory_remove",
            "skill_list", "skill_view"} <= names


def test_enabled_agent_tools_exclude_delegate(monkeypatch):
    """子代理专用：禁嵌套委派，只拿 memory/skills（与 delegate 开关无关）。"""
    monkeypatch.setattr(settings, "AGENT_DELEGATE_ENABLE", False)
    names = {t.__name__ for t in plugin_registry.enabled_agent_tools(include_delegate=False)}
    assert "delegate_task" not in names
    assert {"memory_search", "memory_add", "memory_patch", "memory_remove",
            "skill_list", "skill_view"} <= names


def _sp_addendums(level=3, query="q"):
    from pypedia.agent.build import build_system_prompt

    sp = build_system_prompt(level, query)
    return {
        "tool": "沙箱工具使用规约" in sp,
        "memory": "持久记忆库使用规约" in sp,
        "skills": "技能库使用规约" in sp,
        "delegate": "子代理委派规约" in sp,
    }


def test_build_system_prompt_addendums_gated(monkeypatch):
    """三处能力规约随插件开关增减；browser 规约永远在（工具不门控防幻觉）。"""
    assert _sp_addendums() == {"tool": True, "memory": True, "skills": True, "delegate": True}
    monkeypatch.setattr(settings, "AGENT_MEMORY_ENABLE", False)
    a = _sp_addendums()
    assert a == {"tool": True, "memory": False, "skills": True, "delegate": True}
    monkeypatch.setattr(settings, "AGENT_SKILLS_ENABLE", False)
    monkeypatch.setattr(settings, "AGENT_DELEGATE_ENABLE", False)
    b = _sp_addendums()
    assert b == {"tool": True, "memory": False, "skills": False, "delegate": False}


# ---------- 阶段 4：插件管理端点契约（计划测试项 9） ---------- #
class TestPluginEndpoints:
    def test_get_plugins_shape(self, client):
        r = client.get("/api/plugins")
        assert r.status_code == 200
        d = r.json()
        assert set(d) == {"plugins", "summary"}
        assert len(d["plugins"]) == 23
        assert set(d["summary"]) == {"total", "enabled", "env_blocked"}
        assert d["summary"]["total"] == 23
        keys = {"id", "name", "version", "description", "default_enabled",
                "env_gate", "switchable", "apply", "enabled", "env_blocked"}
        for p in d["plugins"]:
            assert set(p) == keys

    def test_toggle_unknown_id_404(self, client):
        r = client.post("/api/plugins/nope", json={"enabled": True})
        assert r.status_code == 404

    def test_toggle_shell_entry_400(self, client):
        # backup 是空壳入口（switchable=False）→ 不造假开关
        r = client.post("/api/plugins/backup", json={"enabled": True})
        assert r.status_code == 400
        assert "switchable" in r.json()["detail"]

    def test_toggle_real_plugin_roundtrip(self, client, monkeypatch):
        monkeypatch.setattr(settings, "AGENT_MEMORY_ENABLE", True)
        # 关 → 开 → 关 往返，状态落盘且 summary 计数跟随
        r1 = client.post("/api/plugins/agent-memory", json={"enabled": False})
        assert r1.status_code == 200
        assert r1.json()["plugin"]["enabled"] is False
        r2 = client.post("/api/plugins/agent-memory", json={"enabled": True})
        assert r2.json()["plugin"]["enabled"] is True
        # 重新 GET 验证持久化
        r3 = client.get("/api/plugins")
        mem = next(p for p in r3.json()["plugins"] if p["id"] == "agent-memory")
        assert mem["enabled"] is True

    def test_toggle_env_blocked_allowed(self, client, monkeypatch):
        # .env 关了 → 仍允许写回用户态（部署态恢复即生效），返回 env_blocked=True
        monkeypatch.setattr(settings, "AGENT_SKILLS_ENABLE", False)
        r = client.post("/api/plugins/agent-skills", json={"enabled": True})
        assert r.status_code == 200
        body = r.json()
        assert body["plugin"]["env_blocked"] is True
        assert body["plugin"]["enabled"] is False  # 仍被 .env 拦截

    def test_toggle_bad_body_422(self, client):
        # 缺 required 字段（enabled）→ FastAPI 422（pydantic v2 对 "yes" 等会宽松转 bool，故用缺字段）
        r = client.post("/api/plugins/agent-memory", json={})
        assert r.status_code == 422


# ---------- 阶段 5：其余 10 插件门控接线（set_enabled 与 monkeypatch env 行为等价） ---------- #
@pytest.mark.parametrize("pid,gate", [
    (p.id, p.env_gate) for p in BUILTIN_PLUGINS
    if p.switchable and p.env_gate
])
def test_plugin_gate_equivalence(pid, gate, monkeypatch):
    """每插件：monkeypatch env 关 与 set_enabled(False) 都让 is_enabled 落到 False。

    证明「设置页开关」与「.env 部署态」是同一道闸的两个输入源，
    不会因走哪条路径而行为分裂（计划阶段 5 核心验收）。
    """
    monkeypatch.setattr(settings, gate, True)           # 先确保部署态开
    assert plugin_registry.is_enabled(pid) is True       # 无用户态 → 跟随部署态 → 开
    monkeypatch.setattr(settings, gate, False)           # 路径 A：部署态关
    assert plugin_registry.is_enabled(pid) is False
    monkeypatch.setattr(settings, gate, True)            # 路径 B：部署态恢复 + 用户态关
    plugin_registry.set_enabled(pid, False)
    assert plugin_registry.is_enabled(pid) is False
    plugin_registry.set_enabled(pid, True)               # 用户态恢复开
    assert plugin_registry.is_enabled(pid) is True


def test_redact_functional_respects_gate(monkeypatch):
    """agent-redact 接线实证：关（env 或 用户态）时 redact_text 不脱敏，开时脱敏。"""
    from pypedia.agent.redact import redact_text

    secret = "api_key = sk-abcdefghijklmnopqrstuvwx"  # sk- 后 ≥20 位才命中 BareTokenDetector
    monkeypatch.setattr(settings, "AGENT_REDACT_SECRETS", True)
    assert redact_text(secret).text != secret                  # 开：真脱敏
    monkeypatch.setattr(settings, "AGENT_REDACT_SECRETS", False)
    assert redact_text(secret).text == secret                  # env 关：不脱敏
    monkeypatch.setattr(settings, "AGENT_REDACT_SECRETS", True)
    plugin_registry.set_enabled("agent-redact", False)
    assert redact_text(secret).text == secret                  # 用户态关：不脱敏
    plugin_registry.set_enabled("agent-redact", True)
    assert redact_text(secret).text != secret                  # 恢复：再脱敏
