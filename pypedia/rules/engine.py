"""P5 规则引擎：能力激活的确定性路由（master plan §6）。

四类激活策略（数据化规则，非硬编码分支）：
- always-on / pinned：核心能力常驻（显式 allow-list 兜底）；
- rule / condition-triggered：满足条件才激活（等级切换、查询意图、MCP 按需）；
- deterministic-routing：LLM 调用前解析 active set，工具可见性据此过滤（fail-closed）；
- active-injection：规则动作把命名提示词段落整段注入（hermes:mode 式注入点）。

fail-closed 原则：规则引擎开启时，未进入 active set 的能力**不可见且不可调用**；
规则引擎关闭时路由层整体旁路（行为与插件化前恒等，零回退）。

规则即数据：来源于各 unit 的 ``contributions.rules`` 贡献（含第三方插件自声明
触发条件），可整体替换——本模块不 import 任何具体插件。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable

log = logging.getLogger("pypedia.rules.engine")

__all__ = ["Decision", "Rule", "RuleEngine", "RuleError"]


class RuleError(ValueError):
    """规则数据非法（形状错误/条件键未知/正则编译失败）。"""


@dataclass(frozen=True, slots=True)
class Rule:
    """一条激活规则：``when`` 条件满足时执行 ``then`` 动作。"""

    id: str
    when: dict[str, Any]
    then: dict[str, Any]

    @classmethod
    def from_dict(cls, data: Any) -> "Rule":
        if not isinstance(data, dict):
            raise RuleError(f"规则必须是对象：{data!r}")
        rid = data.get("id")
        if not isinstance(rid, str) or not rid:
            raise RuleError(f"规则缺少非空 id：{data!r}")
        when = data.get("when")
        if not isinstance(when, dict) or not when:
            raise RuleError(f"规则 {rid} 的 when 必须是非空对象")
        then = data.get("then")
        if not isinstance(then, dict) or not then:
            raise RuleError(f"规则 {rid} 的 then 必须是非空对象")
        _validate_when(rid, when)
        actions = {"activate", "inject"} & set(then)
        if not actions:
            raise RuleError(f"规则 {rid} 的 then 必须含 activate 或 inject 动作")
        for key in ("activate", "inject"):
            if key in then:
                vals = then[key]
                if (not isinstance(vals, list) or not vals
                        or not all(isinstance(v, str) and v for v in vals)):
                    raise RuleError(
                        f"规则 {rid} 的 {key} 必须是非空字符串数组：{vals!r}")
        unknown = set(then) - {"activate", "inject"}
        if unknown:
            raise RuleError(f"规则 {rid} 的 then 含未知动作键：{sorted(unknown)}")
        return cls(id=rid, when=when, then=then)


@dataclass(frozen=True, slots=True)
class Decision:
    """一次求值结果：本轮激活的能力集 + 主动注入的段落名 + 命中规则（可观测）。"""

    active: frozenset[str]
    injected: tuple[str, ...]
    matched: tuple[str, ...]


# —— 构造期校验：每个条件键一个校验器（形状非法在注册/构造时就炸） —— #
def _v_always(rid: str, key: str, val: Any) -> None:
    if not isinstance(val, bool):
        raise RuleError(f"规则 {rid} 的 always 必须是布尔值")


def _v_level(rid: str, key: str, val: Any) -> None:
    if not isinstance(val, int):
        raise RuleError(f"规则 {rid} 的 {key} 必须是整数")


def _v_str_list(rid: str, key: str, val: Any) -> None:
    if (not isinstance(val, list) or not val
            or not all(isinstance(v, str) and v for v in val)):
        raise RuleError(f"规则 {rid} 的 {key} 必须是非空字符串数组")


def _v_regex(rid: str, key: str, val: Any) -> None:
    if not isinstance(val, str) or not val:
        raise RuleError(f"规则 {rid} 的 query_matches 必须是非空正则字符串")
    try:
        re.compile(val)
    except re.error as exc:
        raise RuleError(f"规则 {rid} 的 query_matches 正则非法：{exc}") from exc


def _v_plugin(rid: str, key: str, val: Any) -> None:
    if not isinstance(val, str) or not val:
        raise RuleError(f"规则 {rid} 的 plugin_enabled 必须是非空字符串")


def _v_cond_list(rid: str, key: str, val: Any) -> None:
    if not isinstance(val, list) or not val:
        raise RuleError(f"规则 {rid} 的 {key} 必须是非空条件数组")
    for sub in val:
        if not isinstance(sub, dict) or not sub:
            raise RuleError(f"规则 {rid} 的 {key} 含非法子条件：{sub!r}")
        _validate_when(rid, sub)


def _v_cond(rid: str, key: str, val: Any) -> None:
    if not isinstance(val, dict) or not val:
        raise RuleError(f"规则 {rid} 的 not 必须是非空条件对象")
    _validate_when(rid, val)


_VALIDATORS: dict[str, Callable[[str, str, Any], None]] = {
    "always": _v_always,
    "level_gte": _v_level,
    "level_lte": _v_level,
    "query_contains": _v_str_list,
    "query_matches": _v_regex,
    "plugin_enabled": _v_plugin,
    "all": _v_cond_list,
    "any": _v_cond_list,
    "not": _v_cond,
}


def _validate_when(rid: str, when: dict[str, Any]) -> None:
    """构造期校验条件形状（键名/类型/正则可编译）——防打字 bug 静默失效。"""
    for key, val in when.items():
        validator = _VALIDATORS.get(key)
        if validator is None:
            raise RuleError(f"规则 {rid} 的 when 含未知条件键：{key}")
        validator(rid, key, val)


# —— 条件求值：每个条件键一个谓词（同对象多键为 AND） —— #
def _p_always(val: Any, *, level: int, query: str, enabled: Any) -> bool:
    return bool(val)


def _p_level_gte(val: int, *, level: int, query: str, enabled: Any) -> bool:
    return level >= val


def _p_level_lte(val: int, *, level: int, query: str, enabled: Any) -> bool:
    return level <= val


def _p_query_contains(val: list[str], *, level: int, query: str,
                      enabled: Any) -> bool:
    q = query.lower()
    return any(kw.lower() in q for kw in val)


def _p_query_matches(val: str, *, level: int, query: str, enabled: Any) -> bool:
    return re.search(val, query, re.IGNORECASE) is not None


def _p_plugin_enabled(val: str, *, level: int, query: str,
                      enabled: Any) -> bool:
    return enabled is None or bool(enabled(val))


def _p_all(val: list[dict], *, level: int, query: str, enabled: Any) -> bool:
    return all(_match_when(sub, level=level, query=query, enabled=enabled)
               for sub in val)


def _p_any(val: list[dict], *, level: int, query: str, enabled: Any) -> bool:
    return any(_match_when(sub, level=level, query=query, enabled=enabled)
               for sub in val)


def _p_not(val: dict, *, level: int, query: str, enabled: Any) -> bool:
    return not _match_when(val, level=level, query=query, enabled=enabled)


_PREDICATES: dict[str, Callable[..., bool]] = {
    "always": _p_always,
    "level_gte": _p_level_gte,
    "level_lte": _p_level_lte,
    "query_contains": _p_query_contains,
    "query_matches": _p_query_matches,
    "plugin_enabled": _p_plugin_enabled,
    "all": _p_all,
    "any": _p_any,
    "not": _p_not,
}


def _match_when(when: dict[str, Any], *, level: int, query: str,
                enabled: Callable[[str], bool] | None) -> bool:
    """条件对象求值（递归；未知键已在构造期拦截）。"""
    for key, val in when.items():
        if not _PREDICATES[key](val, level=level, query=query, enabled=enabled):
            return False
    return True


class RuleEngine:
    """规则求值器：同一份规则数据 → 确定性的 Decision（无状态、可重放）。"""

    def __init__(self, rules: Iterable[Any] = ()) -> None:
        self._rules: tuple[Rule, ...] = tuple(
            r if isinstance(r, Rule) else Rule.from_dict(r) for r in rules)

    @property
    def rules(self) -> tuple[Rule, ...]:
        return self._rules

    @classmethod
    def from_contributions(
        cls, units: Iterable[Any], *, rules_key: str = "rules"
    ) -> "RuleEngine":
        """汇总各 unit 的 ``contributions[rules_key]``（并集语义：可叠加不可删）。

        ``units``：含 ``id`` 与 ``contributions`` 属性的对象（Manifest 或其替身）。
        第三方插件可自声明触发条件（condition-triggered 的落点）。
        """
        rules: list[Any] = []
        for u in units:
            for raw in (u.contributions or {}).get(rules_key, []) or []:
                try:
                    rules.append(raw if isinstance(raw, Rule) else Rule.from_dict(raw))
                except RuleError as exc:
                    # 单条坏规则不阻断整体（warning 留痕，该条不参与路由）
                    log.warning("忽略非法规则（unit=%s）：%s", getattr(u, "id", "?"), exc)
        return cls(rules)

    def evaluate(
        self,
        *,
        level: int,
        query: str = "",
        enabled: Callable[[str], bool] | None = None,
    ) -> Decision:
        """求值：按规则顺序匹配，汇总 activate/inject 动作。

        ``enabled``：部署态/用户态门控查询（缺省视为全部启用——仅供内核单测）。
        激活集 = 各规则 activate 并集 + inject 隐含激活（注入段落所属 unit）；
        门控不过的能力即使被 activate 也进不了最终 active（fail-closed 兜底，
        由调用方依 is_enabled 再过滤，本函数只做规则演绎）。
        """
        active: set[str] = set()
        injected: list[str] = []
        matched: list[str] = []
        for rule in self._rules:
            if not _match_when(rule.when, level=level, query=query, enabled=enabled):
                continue
            matched.append(rule.id)
            active.update(rule.then.get("activate", ()))
            for name in rule.then.get("inject", ()):
                if name not in injected:
                    injected.append(name)
        if matched:
            log.debug("规则求值：matched=%s active=%s injected=%s",
                      matched, sorted(active), injected)
        return Decision(active=frozenset(active),
                        injected=tuple(injected), matched=tuple(matched))
