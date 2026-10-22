"""agent 组装：BailianModel + 浏览器外派工具 + 服务端工具 + 输出联合类型。

设计要点：
- output_type=[str, DeferredToolRequests]：模型不外派工具时输出正文（str），
  外派时输出 DeferredToolRequests（transport 转成前端的 tool_calls）——框架
  原生联合类型，无需手写分支；
- 系统提示词不挂在 Agent.instructions 上：首轮由 transport 作为
  SystemPromptPart 冻结进历史，随 state 原样往返（实测 instructions 在
  续跑时不会自动恢复，见 transport 模块注释）；
- usage_limits 在 transport 按次运行设置（见 PER_STEP_REQUEST_LIMIT）；
- P5 规则引擎：LLM 调用前经 :func:`_rule_decision` 求值本轮激活集
  （deterministic-routing），工具可见性与能力规约据此 fail-closed 过滤；
  规则引擎关闭时 decision=None，行为与插件化前恒等。
"""
from __future__ import annotations

from dataclasses import dataclass

from pydantic_ai import Agent
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.tools import DeferredToolRequests

from ..logging_setup import get_logger
from ..plugins import plugin_registry
from ..rules import RuleEngine
from .bailian_model import BailianModel
from .browser_tools import BROWSER_TOOLS
from .compress import compress_history
from .memory import memory_store

log = get_logger("agent.build")

# 注入系统提示词的工具使用规约（挂在等级提示词之后；文案与旧 agent.py 一致）
TOOL_ADDENDUM = """

【沙箱工具使用规约（你拥有一座真实可运行的服务端 Python 沙箱）】
· 工具：run_python（执行代码看真实输出）/ install_package（装包）/
  fetch_url（抓公网文本）/ sandbox_status（查沙箱能力与已分发 wheel）。
· 将要讲给用户的代码，先用 run_python 实跑验证再写进答案；实测输出
  与文档不符时，以实测为准并说明。
· 纯概念/语法解释类问题不要调用工具，直接回答；
  涉及"这段代码能跑吗/结果是多少/这个 API 怎么用"的问题再调用。
· 工具调用要节俭：单个问题最多几轮；拿不到所需资源就基于已知知识
  作答并说明局限，不要反复重试。
· 最终答案仍按既有规范输出（Markdown / ```python 代码块 / mermaid /
  chart / KaTeX），代码块会被用户一键运行复核。"""

# 记忆库使用规约（Hermes「持久记忆」：先查后写，防重复与过期）
MEMORY_ADDENDUM = """

【持久记忆库使用规约（MEMORY.md 项目记忆 / USER.md 用户画像）】
· 回答涉及用户偏好、历史结论、项目约束前，先用 memory_search 查证，
  不要凭印象假设；查不到再按需 memory_add 补记（给 tag 便于日后检索）。
· 记忆过期或记错时用 memory_patch 修正、memory_remove 删除；
  old/needle 子串必须唯一命中一个段落，先用 memory_search 确认原文。
· 只记稳定事实与明确偏好；一次性中间结果、可随时查到的信息不要记。"""

# 技能库使用规约（Hermes「agentskills」：三级渐进披露）
SKILLS_ADDENDUM = """

【技能库使用规约（SKILL.md，渐进披露）】
· 遇到有专门方法的任务（生成图表/写测试/重构/格式化输出等），先用
  skill_list 查可用技能；命中后 skill_view 读取完整指令并严格照做。
· 技能指令与通用规范冲突时，以技能指令为准（它更具体）。"""

# 子代理委派规约（Hermes 多代理的轻量版：上下文隔离 + 并发有界）
DELEGATE_ADDENDUM = """

【子代理委派规约（delegate_task）】
· 把一个自包含的子任务交给 delegate_task：子代理在隔离上下文里工作，
  只有结论回流，主历史不被探索过程污染——适合「查证/试错/整块起草」。
· 任务描述必须自包含（目标+约束+期望产出），必要时用 context 传背景；
· 并发上限 3：超限时工具会提示你自行完成，不要反复重试；
· 子代理没有沙箱/浏览器工具，涉及跑代码/抓网页的环节仍由你亲自调用。"""

_MEMORY_SNAPSHOT_LIMIT = 3     # 系统提示词里展示的最近记忆条数
_SNAPSHOT_CHARS = 120          # 每条快照正文字符上限


def _memory_snapshot() -> str:
    """最近几条记忆的摘要头（只读预览；全文走 memory_search）。"""
    try:
        rows = []
        for scope in ("memory", "user"):
            for s in memory_store.list_sections(scope)[-_MEMORY_SNAPSHOT_LIMIT:]:
                rows.append(f"· [{scope}] {s.header[5:]} —— {s.body[:_SNAPSHOT_CHARS]}")
        if not rows:
            return ""
        return "\n\n【记忆快照（最近 " + str(len(rows)) + " 条，全文用 memory_search 查）】\n" + "\n".join(rows)
    except Exception:  # noqa: BLE001 —— 快照失败不阻塞主流程（提示词退化）
        return ""


def _skills_snapshot() -> str:
    """技能清单第一级（name + description 常驻提示词；全文走 skill_view）。"""
    try:
        items = skill_store.list_brief()
    except Exception:  # noqa: BLE001 —— 同上：快照失败不阻塞
        return ""
    if not items:
        return ""
    lines = "\n".join(f"· {s['name']}：{s['description']}" for s in items)
    return "\n\n【可用技能（第一级清单；完整指令用 skill_view 读取）】\n" + lines


def _diagram_addendum() -> str:
    """图表渲染规约：从 diagram-render 的 system_prompt_sections 贡献读取。

    单一真值源在 unit manifest（units/builtins.py）；本函数只做「按名取值」，
    贡献缺失时返回空串（不注入）。
    """
    unit = plugin_registry.get_unit("diagram-render")
    if unit is None:
        return ""
    for section in unit.contributions.get("system_prompt_sections", []):
        if section.get("name") == "diagram-render:guide":
            return "\n\n" + section.get("text", "")
    return ""


# ---------- P5 规则引擎：确定性路由（master plan §6） ---------- #
@dataclass(frozen=True, slots=True)
class RoutingDecision:
    """求值并解析后的路由结果（active 已含 inject 的隐含激活）。

    - ``active``：本轮可见的能力 unit id 集（fail-closed：不在此集的能力
      工具不可见、规约不注入；用户/部署态门控仍另行 AND——规则只做收窄，
      不覆盖用户显式关闭）；
    - ``injected``：按 order 排序的待注入段落（主动注入，active-injection）；
    - ``matched``：命中的规则 id（可观测/审计）。
    """

    active: frozenset[str]
    injected: tuple[dict, ...]
    matched: tuple[str, ...]


def _rule_decision(level: int, query: str = "") -> RoutingDecision | None:
    """规则引擎开启 → 求值本轮激活集；关闭 → None（路由层旁路，行为恒等）。

    规则来源：各 unit 的 ``contributions.rules`` 并集（第三方插件可自声明
    触发条件）；求值是 (level, query) 的确定性函数——续轮用历史首问重建
    同一上下文，得到同一激活集（跨轮工具可见性不漂移）。
    """
    if not plugin_registry.is_enabled("rule-engine"):
        return None
    decision = RuleEngine.from_contributions(
        plugin_registry.all_units()).evaluate(
            level=level, query=query, enabled=plugin_registry.is_enabled)
    # inject 段落名 → (unit, section)：注入即隐含激活该 unit；
    # fail-closed：段落所属 unit 未启用（用户/部署态）则跳过不注入。
    active = set(decision.active)
    injected: list[dict] = []
    if decision.injected:
        by_name: dict[str, tuple[str, dict]] = {}
        for unit in plugin_registry.all_units():
            if not plugin_registry.is_enabled(unit.id):
                continue
            for sec in unit.contributions.get("system_prompt_sections", []):
                by_name[sec.get("name")] = (unit.id, sec)
        for name in decision.injected:
            hit = by_name.get(name)
            if hit is None:
                log.debug("规则注入段落未找到或所属 unit 未启用：%s", name)
                continue
            uid, sec = hit
            active.add(uid)
            injected.append({"name": name, "order": sec.get("order", 0),
                             "text": sec.get("text", ""), "unit": uid})
    injected.sort(key=lambda s: s["order"])
    return RoutingDecision(active=frozenset(active),
                           injected=tuple(injected), matched=decision.matched)


def build_system_prompt(level: int, query: str = "", *, nudge: str | None = None,
                        decision: RoutingDecision | None = None) -> str:
    """等级适配系统提示词 + 工具规约 + 记忆/技能快照（复用既有组件，不重造）。

    多处能力门控走插件注册表（用户态 AND .env 部署态，实时读）——
    历史上是裸 settings.AGENT_*_ENABLE，现在统一由插件面板可关。
    P5：``decision`` 非 None 时叠加激活集过滤（fail-closed）——能力须
    「已启用 AND 本轮已激活」才注入规约；decision=None（规则引擎关闭）
    时仅按启用态门控，与插件化前恒等。
    """
    from ..engine import get_engine  # 延迟导入：engine 不依赖本模块，避免循环

    def _cap(pid: str) -> bool:
        if not plugin_registry.is_enabled(pid):
            return False
        return decision is None or pid in decision.active

    parts = [get_engine()._build_system(level, query), TOOL_ADDENDUM]
    if _cap("agent-memory"):
        parts.append(MEMORY_ADDENDUM)
        parts.append(_memory_snapshot())
    if _cap("agent-skills"):
        parts.append(SKILLS_ADDENDUM)
        parts.append(_skills_snapshot())
    if _cap("agent-delegate"):
        parts.append(DELEGATE_ADDENDUM)
    if _cap("diagram-render"):
        parts.append(_diagram_addendum())
    if _cap("rule-engine"):
        parts.append(_rule_engine_addendum())
    if decision is not None:
        parts.extend(_injected_sections(decision))
    parts.extend(_third_party_sections(decision))
    if nudge:
        parts.append("\n\n" + nudge)
    return "".join(p for p in parts if p)


def _rule_engine_addendum() -> str:
    """规则引擎规约：从 rule-engine 的 system_prompt_sections 贡献按名取值。"""
    unit = plugin_registry.get_unit("rule-engine")
    if unit is None:
        return ""
    for section in unit.contributions.get("system_prompt_sections", []):
        if section.get("name") == "rule-engine:routing":
            return "\n\n" + section.get("text", "")
    return ""


def _injected_sections(decision: RoutingDecision) -> list[str]:
    """主动注入（active-injection）：规则命中的命名段落整段进提示词。

    段落在 :func:`_rule_decision` 已解析（按 order 排序、所属 unit 启用），
    此处只做「已注入名去重」——四个能力规约有各自的 manifest 名/常量，
    规则重复注入同名段落不叠加。
    """
    return ["\n\n" + s["text"] for s in decision.injected if s.get("text")]


def _third_party_sections(decision: RoutingDecision | None) -> list[str]:
    """第三方（市场安装）unit 的系统提示词规约：按 order 注入（P6）。

    贡献点即合约：unit manifest 声明 ``system_prompt_sections`` 就应生效，
    与 ``agent_tools`` 的可见性对称——否则市场插件「工具有了、规约没了」。
    内置 23 个走上方硬编码路径（MEMORY/SKILLS/DELEGATE/DIAGRAM/RULE_ENGINE
    五段，行为与插件化前恒等），此处只注入**非内置** unit 的段落，避免重复。

    门控与四大能力规约一致：``is_enabled`` AND（规则引擎关闭时直接放行；
    开启时 unit 须在本轮激活集内——fail-closed，与工具可见性同一判据）。
    与规则 inject 的同名段落去重（规则优先，不叠加）。
    """
    from ..units.builtins import BUILTIN_UNIT_MANIFESTS

    builtin_ids = {raw["id"] for raw in BUILTIN_UNIT_MANIFESTS}
    injected_names = {s["name"] for s in (decision.injected if decision else ())}
    secs: list[tuple[int, str]] = []
    for unit in plugin_registry.all_units():
        if unit.id in builtin_ids:
            continue  # 内置规约走硬编码路径，此处不重复注入
        if not plugin_registry.is_enabled(unit.id):
            continue
        if decision is not None and unit.id not in decision.active:
            continue  # fail-closed：未激活 → 规约不可见（与工具同一判据）
        for sec in unit.contributions.get("system_prompt_sections", []):
            name = sec.get("name", "")
            if name in injected_names:
                continue  # 规则 inject 已注入同名段落，不叠加
            secs.append((sec.get("order", 0), sec.get("text", "")))
    secs.sort(key=lambda t: t[0])
    return ["\n\n" + text for _order, text in secs if text]


def build_agent(tools: list | None = None, *, chat_fn=None,
                decision: RoutingDecision | None = None) -> Agent:
    """组装 agent：百炼单通道模型 + 工具集（浏览器外派 + 服务端内联）。

    工具列表由插件注册表按 id 汇总（memory → skills → delegate）：
    默认全开时与历史 BROWSER_TOOLS+SERVER_TOOLS+DELEGATE_TOOLS 恒等；
    显式传入 tools 时尊重调用方（测试/特殊装配绕过门控）。
    P5：``decision`` 非 None 时仅激活集内的插件贡献工具（fail-closed）；
    None 时全部已启用插件可见（规则引擎关闭的兼容路径）。
    """
    if tools is None:
        active_only = None if decision is None else decision.active
        tools = BROWSER_TOOLS + plugin_registry.enabled_agent_tools(
            active_only=active_only)
    return Agent(
        BailianModel(chat_fn=chat_fn),
        tools=tools,
        output_type=[str, DeferredToolRequests],
        # 历史压缩：模型请求前有界化历史；压缩后历史经 all_messages() 落回 state
        capabilities=[ProcessHistory(compress_history)],
    )
