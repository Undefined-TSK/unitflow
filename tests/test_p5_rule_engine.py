"""P5 规则引擎测试：确定性路由 + fail-closed + 主动注入（master plan §6/§11）。

验收口径（master plan §11 P5）：
1. manifest 契约：rule-engine（第 23 项内置）过 unit.schema.json 校验；
   default_enabled 与 Settings.RULE_ENGINE_ENABLE 一一对应（防漂移）；
   rules 贡献形状合法（schema 层拦未知条件键）；
2. 内核：九种条件求值（同对象多键 AND）、activate/inject 动作、Decision.matched；
   构造期严格校验（未知键/形状非法/正则不可编译 → RuleError，防静默失效）；
   from_contributions 并集汇总 + 单条坏规则 warning 跳过不阻断；
3. fail-closed：激活集过滤工具可见性与能力规约（L1 收窄、强制子集），
   且经 agent_step → chat_with_tools 真实传导到模型工具 schema；
   必需插件被强制激活的用例（pin-core 自举：rule-engine 自己在激活集内）；
4. 主动注入：规则 inject 命名段落 → 整段进提示词（按 order 排序）+
   隐含激活所属 unit；所属 unit 未启用则跳过（fail-closed 兜底）；
5. 恒等：rule-engine 关闭 → decision=None、路由层旁路，工具集与
   「启用即可见」逐项一致（零回退承诺）；
6. 续轮一致性：state 模式用历史首问重建同一激活集；
7. 端点：/api/plugins 与 /api/units 含 rule-engine，rules 贡献可见。
"""
from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from pypedia import agent
from pypedia.agent import bailian_model, load_state
from pypedia.agent.browser_tools import BROWSER_TOOLS
from pypedia.agent.build import (
    RoutingDecision,
    _rule_decision,
    build_system_prompt,
)
from pypedia.agent.transport import _first_user_content
from pypedia.config import Settings, settings
from pypedia.plugins import BUILTIN_PLUGINS, plugin_registry
from pypedia.rules import Rule, RuleEngine, RuleError
from pypedia.units.builtins import BUILTIN_UNIT_MANIFESTS
from pypedia.units.exceptions import ManifestError
from pypedia.units.manifest import Manifest, validate_raw

ROOT = Path(__file__).resolve().parents[1]
RULE_ID = "rule-engine"

# —— 测试环境基线：4 browser + 7 服务端工具（memory×4 + skills×2 + delegate×1） —— #
ALL_TOOL_NAMES = {t.__name__ for t in BROWSER_TOOLS + plugin_registry.enabled_agent_tools()}
MEMORY_TOOLS = {"memory_search", "memory_add", "memory_patch", "memory_remove"}
SKILL_TOOLS = {"skill_list", "skill_view"}


def _raw_manifest() -> dict:
    for m in BUILTIN_UNIT_MANIFESTS:
        if m["id"] == RULE_ID:
            return m
    raise AssertionError(f"{RULE_ID} 不在内置 Unit manifest 中")


# ---------- 1. manifest 契约 ---------- #
def test_manifest_validates_and_registered():
    """rule-engine manifest 过 schema 校验，且已注册进兼容内核。"""
    raw = _raw_manifest()
    validate_raw(raw)  # 不抛 ManifestError 即过 schema 校验
    assert len(BUILTIN_UNIT_MANIFESTS) == 23  # P5 新增第 23 项
    assert plugin_registry.get_unit(RULE_ID) is not None
    p = next(p for p in BUILTIN_PLUGINS if p.id == RULE_ID)
    assert p.env_gate == "RULE_ENGINE_ENABLE"
    assert p.switchable and p.apply == "instant"
    assert _raw_manifest()["form"] == "instance"


def test_default_enabled_matches_settings():
    """default_enabled 与 Settings.RULE_ENGINE_ENABLE 默认值防漂移。"""
    raw = _raw_manifest()
    field = Settings.model_fields.get("RULE_ENGINE_ENABLE")
    assert field is not None, "RULE_ENGINE_ENABLE 不是 Settings 字段"
    assert raw["default_enabled"] == field.default


def test_rules_contribution_shape():
    """rules 贡献：三条规则 id 唯一、when/then 合法、pin-core 常驻兜底。"""
    rules = _raw_manifest()["contributions"]["rules"]
    assert len(rules) == 3
    ids = [r["id"] for r in rules]
    assert len(set(ids)) == 3
    for r in rules:  # 逐条过内核构造校验（schema 之外的第二道关）
        Rule.from_dict(r)
    pin = next(r for r in rules if r["id"] == "pin-core")
    assert pin["when"] == {"always": True}
    assert set(pin["then"]["activate"]) == {"agent-memory", "agent-skills", RULE_ID}
    # 等级条件触发：委派/图表只在 L2+ 激活（入门级收窄）
    by_level = {r["id"]: r["when"] for r in rules if "level_gte" in r["when"]}
    assert set(by_level) == {"cap-delegate-by-level", "cap-diagram-by-level"}


def test_schema_validates_rule_structure():
    """schema 层校验规则结构：缺 when/then、规则对象夹带未知键、when 非对象
    一律拒绝；结构合法的规则放行（条件语义交给内核第二道关）。"""
    base = {"id": "r", "when": {"always": True}, "then": {"activate": ["x"]}}

    def _raw(rules):
        return {"id": "rule-test", "type": "plugin", "name": "X", "version": "1.0.0",
                "contributions": {"rules": rules}}

    validate_raw(_raw([base]))  # 合法形状不抛
    with pytest.raises(ManifestError):
        validate_raw(_raw([{k: v for k, v in base.items() if k != "when"}]))   # 缺 when
    with pytest.raises(ManifestError):
        validate_raw(_raw([{k: v for k, v in base.items() if k != "then"}]))   # 缺 then
    with pytest.raises(ManifestError):
        validate_raw(_raw([{**base, "zzz": 1}]))                              # 夹带未知键
    with pytest.raises(ManifestError):
        validate_raw(_raw([{**base, "when": "always"}]))                      # when 非对象


def test_kernel_rejects_unknown_condition_key():
    """纵深防御：未知条件键能过 schema（when 是自由对象），
    但内核 Rule.from_dict 拒绝——防打字 bug 静默失效。"""
    typo = {"id": "r-typo", "when": {"level_gteee": 2},
            "then": {"activate": ["x"]}}
    validate_raw({"id": "rule-test", "type": "plugin", "name": "X",
                  "version": "1.0.0",
                  "contributions": {"rules": [typo]}})  # schema 层放行
    with pytest.raises(RuleError):
        Rule.from_dict(typo)  # 内核层拦截


# ---------- 2. 内核：条件求值 ---------- #
def _engine(*rules) -> RuleEngine:
    return RuleEngine(list(rules))


def test_condition_always():
    e = _engine({"id": "r", "when": {"always": True},
                 "then": {"activate": ["a"]}})
    assert e.evaluate(level=1).active == frozenset({"a"})
    # always: False 恒不命中（构造期允许布尔假值——规则可整体停用某条）
    e2 = _engine({"id": "r", "when": {"always": False},
                  "then": {"activate": ["a"]}})
    assert e2.evaluate(level=3).active == frozenset()
    assert e2.evaluate(level=3).matched == ()


def test_condition_level_gte_and_lte():
    rules = [{"id": "gte", "when": {"level_gte": 3}, "then": {"activate": ["hi"]}},
             {"id": "lte", "when": {"level_lte": 2}, "then": {"activate": ["lo"]}}]
    e = _engine(*rules)
    assert e.evaluate(level=1).active == frozenset({"lo"})
    assert e.evaluate(level=2).active == frozenset({"lo"})
    assert e.evaluate(level=3).active == frozenset({"hi"})
    assert e.evaluate(level=5).active == frozenset({"hi"})


def test_condition_query_contains_and_matches():
    rules = [
        {"id": "kw", "when": {"query_contains": ["报错", "ERROR"]},
         "then": {"activate": ["debug"]}},
        {"id": "rx", "when": {"query_matches": r"画.*图"},
         "then": {"activate": ["chart"]}},
    ]
    e = _engine(*rules)
    d = e.evaluate(level=3, query="这段代码报错了")
    assert d.active == frozenset({"debug"}) and d.matched == ("kw",)
    # query_contains 大小写不敏感；query_matches 走 IGNORECASE 正则
    d2 = e.evaluate(level=3, query="error trace here")
    assert d2.active == frozenset({"debug"})
    d3 = e.evaluate(level=3, query="帮我画一个架构图")
    assert d3.active == frozenset({"chart"})


def test_condition_plugin_enabled():
    e = _engine({"id": "pe", "when": {"plugin_enabled": "sandbox"},
                 "then": {"activate": ["cap-sandbox"]}})
    assert e.evaluate(level=3, enabled=lambda pid: pid == "sandbox").active \
        == frozenset({"cap-sandbox"})
    assert e.evaluate(level=3, enabled=lambda pid: False).active == frozenset()
    # enabled 缺省视为全部启用（仅供内核单测）
    assert e.evaluate(level=3).active == frozenset({"cap-sandbox"})


def test_condition_composition_all_any_not():
    rules = [
        {"id": "and", "when": {"all": [{"level_gte": 2}, {"query_contains": ["图"]}]},
         "then": {"activate": ["and-cap"]}},
        {"id": "or", "when": {"any": [{"level_gte": 5}, {"query_contains": ["紧急"]}]},
         "then": {"activate": ["or-cap"]}},
        {"id": "neg", "when": {"not": {"query_contains": ["简单"]}},
         "then": {"activate": ["neg-cap"]}},
    ]
    e = _engine(*rules)
    # AND：两条件都满足才命中
    assert e.evaluate(level=2, query="画个图").active == frozenset({"and-cap", "neg-cap"})
    assert e.evaluate(level=1, query="画个图").active == frozenset({"neg-cap"})
    # ANY：任一满足即命中（neg 规则同样命中——"紧急修复"不含"简单"）
    assert e.evaluate(level=3, query="紧急修复").active == frozenset({"or-cap", "neg-cap"})
    # NOT：取反（含"简单"→不命中 neg）
    assert e.evaluate(level=3, query="简单问题").active == frozenset()


def test_condition_same_object_multi_key_is_and():
    """同一 when 对象内多键为 AND（全部满足才命中）。"""
    e = _engine({"id": "multi", "when": {"level_gte": 2, "query_contains": ["部署"]},
                 "then": {"activate": ["ops"]}})
    assert e.evaluate(level=3, query="如何部署").active == frozenset({"ops"})
    assert e.evaluate(level=1, query="如何部署").active == frozenset()
    assert e.evaluate(level=3, query="随便问问").active == frozenset()


# ---------- 3. 动作与 Decision ---------- #
def test_actions_activate_union_and_inject_names():
    e = _engine(
        {"id": "r1", "when": {"always": True}, "then": {"activate": ["a", "b"]}},
        {"id": "r2", "when": {"level_gte": 2}, "then": {"activate": ["b", "c"]}},
        {"id": "r3", "when": {"query_contains": ["图"]},
         "then": {"inject": ["x:guide", "y:mode"]}},
    )
    d = e.evaluate(level=2, query="画图")
    assert d.active == frozenset({"a", "b", "c"})
    assert d.injected == ("x:guide", "y:mode")   # 段落名按规则顺序、去重
    assert d.matched == ("r1", "r2", "r3")
    # Decision 是冻结数据类（路由结果不可变、可跨轮比较）
    with pytest.raises(Exception):
        d.active = frozenset()  # type: ignore[misc]


def test_evaluate_is_deterministic_and_replayable():
    """同一份规则 + 同一 (level, query) → 同一 Decision（可重放、可缓存）。"""
    e = _engine({"id": "r", "when": {"level_gte": 2},
                 "then": {"activate": ["a"], "inject": ["s:1"]}})
    assert e.evaluate(level=2, query="q") == e.evaluate(level=2, query="q")
    assert e.evaluate(level=1, query="q") != e.evaluate(level=2, query="q")


# ---------- 4. 构造期校验（防打字 bug 静默失效） ---------- #
@pytest.mark.parametrize("bad", [
    {"id": "", "when": {"always": True}, "then": {"activate": ["a"]}},        # 空 id
    {"when": {"always": True}, "then": {"activate": ["a"]}},                  # 缺 id
    {"id": "r", "when": {}, "then": {"activate": ["a"]}},                     # 空 when
    {"id": "r", "when": {"always": True}, "then": {}},                        # 空 then
    {"id": "r", "when": {"always": True}, "then": {"drop": ["a"]}},           # 无已知动作
    {"id": "r", "when": {"always": True}, "then": {"activate": []}},          # 空激活数组
    {"id": "r", "when": {"always": True}, "then": {"activate": "a"}},         # 激活非数组
    {"id": "r", "when": {"typo_key": True}, "then": {"activate": ["a"]}},     # 未知条件键
    {"id": "r", "when": {"level_gte": "2"}, "then": {"activate": ["a"]}},     # 等级非整数
    {"id": "r", "when": {"query_contains": "图"}, "then": {"activate": ["a"]}},  # 非数组
    {"id": "r", "when": {"query_matches": "("}, "then": {"activate": ["a"]}},  # 正则非法
    {"id": "r", "when": {"not": []}, "then": {"activate": ["a"]}},            # not 非对象
    {"id": "r", "when": {"all": [{"nope": 1}]}, "then": {"activate": ["a"]}},  # 子条件未知键
    {"id": "r", "when": {"always": True}, "then": {"activate": ["a"], "x": 1}},  # then 未知键
    "not-a-dict",
])
def test_invalid_rule_raises_rule_error(bad):
    with pytest.raises(RuleError):
        Rule.from_dict(bad)


def test_rule_engine_ctor_validates_all_rules():
    """构造期逐条校验——一条坏规则让整体 fail-fast（不带着暗病上路）。"""
    with pytest.raises(RuleError):
        RuleEngine([{"id": "ok", "when": {"always": True},
                     "then": {"activate": ["a"]}},
                    {"id": "bad", "when": {"level_gte": 1.5},
                     "then": {"activate": ["b"]}}])


# ---------- 5. from_contributions：并集汇总 + 坏规则容错 ---------- #
def test_from_contributions_union():
    """各 unit 的 contributions.rules 并集汇总（第三方可自声明触发条件）。"""
    units = [
        SimpleNamespace(id="u1", contributions={"rules": [
            {"id": "r1", "when": {"always": True}, "then": {"activate": ["a"]}}]}),
        SimpleNamespace(id="u2", contributions={"rules": [
            {"id": "r2", "when": {"level_gte": 2}, "then": {"activate": ["b"]}}]}),
        SimpleNamespace(id="u3", contributions=None),  # 无贡献不阻断
    ]
    e = RuleEngine.from_contributions(units)
    assert [r.id for r in e.rules] == ["r1", "r2"]
    assert e.evaluate(level=2).active == frozenset({"a", "b"})


def test_from_contributions_skips_bad_rule_with_warning(caplog):
    """单条坏规则 warning 跳过、不阻断整体（平台不因一个插件罢工而瘫痪）。"""
    units = [
        SimpleNamespace(id="evil", contributions={"rules": [
            {"id": "bad", "when": {"typo": True}, "then": {"activate": ["x"]}},
            {"id": "good", "when": {"always": True}, "then": {"activate": ["y"]}},
        ]}),
    ]
    with caplog.at_level(logging.WARNING, logger="pypedia.rules.engine"):
        e = RuleEngine.from_contributions(units)
    assert [r.id for r in e.rules] == ["good"]
    assert "忽略非法规则" in caplog.text and "unit=evil" in caplog.text


def test_from_contributions_real_registry():
    """真实 registry：规则来自各 unit 贡献并集（内置默认规则在 L3 全命中）。"""
    e = RuleEngine.from_contributions(plugin_registry.all_units())
    d = e.evaluate(level=3, query="什么是装饰器",
                   enabled=plugin_registry.is_enabled)
    assert d.matched == ("pin-core", "cap-delegate-by-level", "cap-diagram-by-level")
    assert d.active == frozenset({"agent-memory", "agent-skills", RULE_ID,
                                  "agent-delegate", "diagram-render"})


# ---------- 6. fail-closed：确定性路由 ---------- #
def test_l3_default_routing_is_p4_identical():
    """L3（默认等级）激活集复现现行行为：11 工具在位、六规约齐全（零回归）。"""
    d = _rule_decision(3, "什么是装饰器")
    assert d is not None
    names = {t.__name__ for t in BROWSER_TOOLS + plugin_registry.enabled_agent_tools(
        active_only=d.active)}
    assert names == ALL_TOOL_NAMES  # 与无路由时的全量工具逐项一致
    sp = build_system_prompt(3, "什么是装饰器", decision=d)
    for needle in ("沙箱工具使用规约", "持久记忆库使用规约", "技能库使用规约",
                   "子代理委派规约", "图表渲染规约", "能力激活规约"):
        assert needle in sp, f"L3 缺规约：{needle}"


def test_l1_narrows_capabilities():
    """L1 收窄：委派/图表掉出激活集——master plan 点名的「等级切换」用例。"""
    d = _rule_decision(1, "什么是装饰器")
    assert d.matched == ("pin-core",)
    names = {t.__name__ for t in BROWSER_TOOLS + plugin_registry.enabled_agent_tools(
        active_only=d.active)}
    assert names == ALL_TOOL_NAMES - {"delegate_task"}  # 11 → 10
    sp = build_system_prompt(1, "什么是装饰器", decision=d)
    assert "子代理委派规约" not in sp and "图表渲染规约" not in sp
    assert "持久记忆库使用规约" in sp and "能力激活规约" in sp


def test_fail_closed_subset_forces_minimal_tools():
    """fail-closed：激活集只有 agent-memory → 仅 browser + 4 memory 工具，
    技能规约消失——未进激活集的能力不可见且不可调用。"""
    forced = RoutingDecision(active=frozenset({"agent-memory"}), injected=(), matched=())
    names = {t.__name__ for t in BROWSER_TOOLS + plugin_registry.enabled_agent_tools(
        active_only=forced.active)}
    assert names == {t.__name__ for t in BROWSER_TOOLS} | MEMORY_TOOLS
    assert not (names & SKILL_TOOLS)
    sp = build_system_prompt(3, "帮我记一下", decision=forced)
    assert "持久记忆库使用规约" in sp
    assert "技能库使用规约" not in sp and "子代理委派规约" not in sp


def test_required_plugins_pinned_by_force_activation():
    """必需插件被强制激活的用例（master plan §11 P5 验收口径）：
    rule-engine 通过 pin-core 把自己放进激活集——规则引擎自举，
    其路由规约与插件自身始终可见，不依赖任何等级/查询条件。"""
    d = _rule_decision(1, "任意问题")
    assert RULE_ID in d.active
    sp = build_system_prompt(1, "任意问题", decision=d)
    assert "能力激活规约" in sp  # rule-engine 规约在最低等级也在位
    # 核心能力（记忆/技能）同为 pinned：L1 也在激活集
    assert {"agent-memory", "agent-skills"} <= d.active


def test_user_disable_overrides_rule_activation():
    """规则只做收窄、不覆盖用户显式关闭：memory 被用户关掉后，
    即使 pin-core 激活它，工具与规约也不可见（is_enabled 另行 AND）。"""
    plugin_registry.set_enabled("agent-memory", False)
    try:
        d = _rule_decision(3, "帮我记一下")
        assert "agent-memory" in d.active  # 规则侧仍激活（规则不知道用户关了）
        names = {t.__name__ for t in BROWSER_TOOLS + plugin_registry.enabled_agent_tools(
            active_only=d.active)}
        assert not (names & MEMORY_TOOLS)  # 门控侧 AND 掉
        sp = build_system_prompt(3, "帮我记一下", decision=d)
        assert "持久记忆库使用规约" not in sp
    finally:
        plugin_registry.set_enabled("agent-memory", True)


@pytest.fixture()
def fake_chat(monkeypatch):
    """打桩 pypedia.agent.bailian_model.chat_with_tools（BailianModel 唯一 LLM 出口）。

    按脚本队列返回 OpenAI 兼容消息；记录每次调用的 messages/tools 供断言
    （本文件专用，与 tests/test_agent.py 的同名 fixture 同源同口径）。
    """
    state = {"script": [], "calls": []}

    def _fake(messages, tools, **kw):
        state["calls"].append({"messages": messages, "tools": tools, "kw": kw})
        item = state["script"].pop(0) if len(state["script"]) > 1 else state["script"][0]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(bailian_model, "chat_with_tools", _fake)
    return state


def _oai_text(text):
    return {"role": "assistant", "content": text}


def test_agent_step_l1_narrowing_reaches_llm(fake_chat):
    """端到端：L1 求值 → 激活集收窄 → 模型请求的工具 schema 里
    delegate_task 不可见（证明 fail-closed 真实传导，不停在注册表层）。"""
    fake_chat["script"] = [_oai_text("入门级回答")]
    r = agent.agent_step(query="什么是装饰器", level=1)
    assert r["type"] == "final"
    tool_names = {t["function"]["name"] for t in fake_chat["calls"][0]["tools"]}
    assert "delegate_task" not in tool_names          # L1 收窄生效
    assert "memory_search" in tool_names              # pinned 核心能力仍在
    sp = load_state(r["state"])[0].parts[0].content
    assert "子代理委派规约" not in sp                 # 提示词侧同步收窄
    assert "能力激活规约" in sp


# ---------- 7. 主动注入（active-injection） ---------- #
def test_active_injection_resolves_named_sections():
    """第三方 unit 声明 inject 段落：段落整段进提示词 + 隐含激活所属 unit。"""
    temp = {
        "id": "p5-inject-demo", "type": "plugin", "name": "注入示范",
        "version": "1.0.0", "default_enabled": True,
        "contributions": {
            "system_prompt_sections": [
                {"name": "p5-inject-demo:mode", "order": 90,
                 "text": "【注入示范段（v1）】"}],
            "rules": [
                {"id": "inject-on-query",
                 "when": {"query_contains": ["注入"]},
                 "then": {"inject": ["p5-inject-demo:mode"]}},
            ],
        },
    }
    plugin_registry.register(Manifest.from_dict(temp))
    try:
        d = _rule_decision(3, "请注入示范")
        assert d.matched == ("pin-core", "cap-delegate-by-level",
                             "cap-diagram-by-level", "inject-on-query")
        # 注入段落按 order 解析，且隐含激活所属 unit
        assert [s["name"] for s in d.injected] == ["p5-inject-demo:mode"]
        assert "p5-inject-demo" in d.active
        sp = build_system_prompt(3, "请注入示范", decision=d)
        assert "【注入示范段（v1）】" in sp
        # 查询不含触发词 → 不注入、不激活（规则收窄的另外一半）
        d2 = _rule_decision(3, "随便问问")
        assert d2.injected == () and "p5-inject-demo" not in d2.active
        assert "【注入示范段" not in build_system_prompt(3, "随便问问", decision=d2)
    finally:
        plugin_registry.unregister("p5-inject-demo")


def test_injection_skips_disabled_unit():
    """inject 的段落所属 unit 被用户关掉 → 跳过不注入（fail-closed 兜底）。"""
    temp = {
        "id": "p5-inject-off", "type": "plugin", "name": "注入关闭",
        "version": "1.0.0", "default_enabled": True,
        "contributions": {
            "system_prompt_sections": [
                {"name": "p5-inject-off:mode", "order": 90,
                 "text": "【关闭注入段】"}],
            "rules": [
                {"id": "inject-always", "when": {"always": True},
                 "then": {"inject": ["p5-inject-off:mode"]}},
            ],
        },
    }
    plugin_registry.register(Manifest.from_dict(temp))
    try:
        plugin_registry.set_enabled("p5-inject-off", False)
        d = _rule_decision(3, "q")
        assert "p5-inject-off:mode" not in [s["name"] for s in d.injected]
        assert "p5-inject-off" not in d.active
        assert "【关闭注入段】" not in build_system_prompt(3, "q", decision=d)
    finally:
        plugin_registry.set_enabled("p5-inject-off", True)
        plugin_registry.unregister("p5-inject-off")


def test_injection_sections_sorted_by_order():
    """多段落注入按 order 排序（提示词组装顺序确定，可复现）。"""
    temps = []
    for i, order in enumerate((50, 10, 30), start=1):
        uid = f"p5-order-{i}"
        temps.append(uid)
        plugin_registry.register(Manifest.from_dict({
            "id": uid, "type": "plugin", "name": f"顺序{i}",
            "version": "1.0.0", "default_enabled": True,
            "contributions": {
                "system_prompt_sections": [
                    {"name": f"{uid}:sec", "order": order,
                     "text": f"【顺序段 order={order}】"}],
                "rules": [
                    {"id": f"{uid}-inject", "when": {"always": True},
                     "then": {"inject": [f"{uid}:sec"]}},
                ],
            },
        }))
    try:
        d = _rule_decision(3, "q")
        assert [s["name"] for s in d.injected] == [
            "p5-order-2:sec", "p5-order-3:sec", "p5-order-1:sec"]  # order 10/30/50
        sp = build_system_prompt(3, "q", decision=d)
        assert sp.index("order=10") < sp.index("order=30") < sp.index("order=50")
    finally:
        for uid in temps:
            plugin_registry.unregister(uid)


# ---------- 8. 恒等（规则引擎关闭 → 路由层旁路） ---------- #
def test_rule_engine_off_is_identity():
    """rule-engine 关闭：decision=None + 工具/规约回到「启用即可见」，
    与插件化前恒等（零回退承诺）。"""
    plugin_registry.set_enabled(RULE_ID, False)
    try:
        assert _rule_decision(3, "什么是装饰器") is None
        # 工具：无路由时全量可见（含 delegate——L1 也看得见）
        names = {t.__name__ for t in BROWSER_TOOLS + plugin_registry.enabled_agent_tools()}
        assert names == ALL_TOOL_NAMES
        # 提示词：不注入规则引擎规约；decision=None 时与显式传 None 恒等
        sp = build_system_prompt(1, "什么是装饰器")
        assert "能力激活规约" not in sp
        assert "子代理委派规约" in sp  # 无等级收窄
        assert sp == build_system_prompt(1, "什么是装饰器", decision=None)
    finally:
        plugin_registry.set_enabled(RULE_ID, True)


def test_env_blocked_rule_engine_is_identity(monkeypatch):
    """部署态（.env）关闭 rule-engine → 同样旁路（is_enabled 双层门控）。"""
    monkeypatch.setattr(settings, "RULE_ENGINE_ENABLE", False)
    assert _rule_decision(3, "q") is None
    assert "能力激活规约" not in build_system_prompt(3, "q")


# ---------- 9. 续轮路由一致性 ---------- #
def test_continuation_reuses_first_query():
    """state 模式用历史首问重建激活集：跨轮工具可见性不漂移。"""
    from pydantic_ai.messages import (
        ModelMessage,
        ModelRequest,
        ModelResponse,
        SystemPromptPart,
        ToolCallPart,
        UserPromptPart,
    )

    history: list[ModelMessage] = [
        ModelRequest(parts=[SystemPromptPart(content="sys"),
                            UserPromptPart(content="画个架构图")]),
        ModelResponse(parts=[ToolCallPart(tool_name="browser_open",
                                          args={"url": "x"}, tool_call_id="c1")]),
        ModelRequest(parts=[UserPromptPart(content="（续轮追问，与首问不同）")]),
    ]
    assert _first_user_content(history) == "画个架构图"
    # 首问重建 → 与首轮同一激活集（query_contains 类规则跨轮不漂移）
    d_first = _rule_decision(3, "画个架构图")
    d_again = _rule_decision(3, _first_user_content(history))
    assert d_first == d_again


def test_first_user_content_empty_when_no_user_message():
    """历史无用户消息（异常输入）→ 空串，规则按 query="" 求值不炸。"""
    from pydantic_ai.messages import ModelRequest, SystemPromptPart

    assert _first_user_content(
        [ModelRequest(parts=[SystemPromptPart(content="s")])]) == ""
    d = _rule_decision(3, "")
    assert d is not None and RULE_ID in d.active


# ---------- 10. 端点 ---------- #
class TestRuleEngineEndpoints:
    def test_plugins_and_units_views_carry_rule_engine(self, client):
        """/api/plugins 与 /api/units 均含 rule-engine，rules 贡献可见。"""
        p = next(p for p in client.get("/api/plugins").json()["plugins"]
                 if p["id"] == RULE_ID)
        assert p["env_gate"] == "RULE_ENGINE_ENABLE"
        assert p["switchable"] is True
        u = next(u for u in client.get("/api/units").json()["units"]
                 if u["id"] == RULE_ID)
        assert u["enabled"] is True and u["env_blocked"] is False
        rules = u["contributions"]["rules"]
        assert [r["id"] for r in rules] == ["pin-core", "cap-delegate-by-level",
                                            "cap-diagram-by-level"]

    def test_toggle_rule_engine_roundtrip(self, client):
        """toggle 回写带 contributions（前端热刷新依据）；两视图门控一致。"""
        r = client.post(f"/api/plugins/{RULE_ID}", json={"enabled": False})
        assert r.status_code == 200
        dd = r.json()["plugin"]
        assert dd["enabled"] is False
        assert dd["contributions"]["rules"][0]["id"] == "pin-core"
        u = next(u for u in client.get("/api/units").json()["units"]
                 if u["id"] == RULE_ID)
        assert u["enabled"] is False
        r2 = client.post(f"/api/plugins/{RULE_ID}", json={"enabled": True})
        assert r2.json()["plugin"]["enabled"] is True


# ---------- 11. describe() 同步（部署态开关清单） ---------- #
def test_describe_contains_rule_engine_flag():
    """settings.describe() 暴露 rule_engine（前端部署态展示单一真值源）。"""
    d = settings.describe()
    assert d.get("rule_engine") == settings.RULE_ENGINE_ENABLE
