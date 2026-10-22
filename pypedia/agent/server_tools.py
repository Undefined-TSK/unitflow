"""服务端内联工具：记忆库 + 技能库（结果直接入历史，不经前端）。

与 browser_tools 的分工：
- browser_tools 抛 CallDeferred：执行在用户浏览器沙箱（run_python 等）；
- 本模块工具在服务端 run 内同步执行完（本地 sqlite/文件，零网络零 LLM），
  返回值作为 ToolReturnPart 直接进历史——模型一次请求即可拿到结果。
- 参数/操作失败同样返回错误文本（不抛），模型可自行修正重试。

P2 范围：memory_search/add/patch/remove + skill_list/view/search。
P3+ 追加：rag_search（级联检索）/ session_search / cron_manage /
delegate_task / mcp_* —— 届时在同一 SERVER_TOOLS 列表扩充，签名风格保持一致。
"""
from __future__ import annotations

from ..plugins import plugin_registry
from .memory import MemoryError_, SCOPES, memory_store
from .skills import SkillError_, skill_store


def _guard_enabled(flag: bool, what: str) -> str | None:
    if not flag:
        return (f"{what}已在配置/设置中关闭（.env 的 AGENT_MEMORY_ENABLE / "
                f"AGENT_SKILLS_ENABLE，或设置页「插件管理」面板）")
    return None


# ---------- 记忆工具 ---------- #
async def memory_search(query: str, scope: str = "") -> str:
    """检索持久记忆库（MEMORY.md 项目记忆 / USER.md 用户画像，FTS5 中文子串命中）。

    记不起用户偏好、过往结论、项目事实时先用它查，再决定是否补写。
    scope 可传 "memory"/"user" 限定范围，留空表示两个都查。
    """
    off = _guard_enabled(plugin_registry.is_enabled("agent-memory"), "记忆库")
    if off:
        return off
    q = (query or "").strip()
    if not q:
        return "参数错误：memory_search 需要非空 query"
    if scope and scope not in SCOPES:
        return f"参数错误：scope 只能是 {'/'.join(SCOPES)} 之一"
    hits = memory_store.search(q, scope=scope or None)
    if not hits:
        return f"没有命中：{q!r} 在记忆中不存在。可换关键词重试，或确认是否需要新记录。"
    lines = [f"· [{h['scope']}] {h['header'][5:]} —— {h['body'][:120]}"
             for h in hits]
    return f"记忆命中 {len(hits)} 条：\n" + "\n".join(lines)


async def memory_add(scope: str, text: str, tag: str = "") -> str:
    """向持久记忆库追加一条记忆（memory=项目事实/结论，user=用户偏好与画像）。

    值得记的：用户明确表达的偏好、稳定的项目约束、重要结论与纠错。
    不要记：一次性中间结果、可从代码/文档直接查到的事实。
    """
    off = _guard_enabled(plugin_registry.is_enabled("agent-memory"), "记忆库")
    if off:
        return off
    try:
        header = memory_store.add(scope, text, tag)
    except MemoryError_ as e:
        return f"参数错误：{e}"
    return f"已记录到 {scope}：{header[5:]}"


async def memory_patch(scope: str, old: str, new: str) -> str:
    """修正记忆库中某条内容（old 子串必须唯一命中一个段落）。

    记忆过期/记错时用；先用 memory_search 确认原文，再给出足够长的唯一 old。
    """
    off = _guard_enabled(plugin_registry.is_enabled("agent-memory"), "记忆库")
    if off:
        return off
    try:
        header = memory_store.patch(scope, old, new)
    except MemoryError_ as e:
        return f"参数错误：{e}"
    return f"已更新 {scope} 中的段落：{header[5:]}"


async def memory_remove(scope: str, needle: str) -> str:
    """删除记忆库中某条内容（needle 子串必须唯一命中一个段落）。"""
    off = _guard_enabled(plugin_registry.is_enabled("agent-memory"), "记忆库")
    if off:
        return off
    try:
        header = memory_store.remove(scope, needle)
    except MemoryError_ as e:
        return f"参数错误：{e}"
    return f"已从 {scope} 删除段落：{header[5:]}"


# ---------- 技能工具 ---------- #
def _render_skill_brief(items: list[dict]) -> str:
    if not items:
        return "（技能库为空）"
    return "\n".join(f"· {s['name']}：{s['description']}" for s in items)


def _render_skill_detail(items: list[dict]) -> str:
    if not items:
        return "（没有匹配的技能）"
    lines = []
    for s in items:
        usage = s.get("usage") or {}
        used = f"{usage.get('count', 0)} 次" + (
            f"，最近 {time_str(usage.get('last_used'))}" if usage.get("last_used") else "，从未使用")
        lines.append(f"· {s['name']}（v{s.get('version') or '-'}，{used}）\n"
                     f"  描述：{s['description']}\n  何时用：{s['when_to_use']}")
    return "\n".join(lines)


def time_str(ts: float | None) -> str:
    import time as _t
    if not ts:
        return "从未"
    return _t.strftime("%Y-%m-%d", _t.localtime(ts))


async def skill_list(query: str = "") -> str:
    """列出可用技能（SKILL.md 技能库，渐进披露第一/二级）。

    需要专门方法完成特定任务（如生成图表、写测试、重构）时先查这里；
    命中后用 skill_view 看完整指令再照做。
    """
    off = _guard_enabled(plugin_registry.is_enabled("agent-skills"), "技能库")
    if off:
        return off
    if query and query.strip():
        return _render_skill_detail(skill_store.search(query))
    return _render_skill_brief(skill_store.list_brief())


async def skill_view(name: str) -> str:
    """查看单个技能的完整指令（渐进披露第三级：SKILL.md 全文）。"""
    off = _guard_enabled(plugin_registry.is_enabled("agent-skills"), "技能库")
    if off:
        return off
    try:
        skill = skill_store.view(name)
    except SkillError_ as e:
        return f"参数错误：{e}"
    return (f"# 技能：{skill['name']}\n\n{skill['description']}\n\n"
            f"## 何时使用\n{skill['when_to_use']}\n\n## 指令\n{skill['body']}")


SERVER_TOOLS = [
    memory_search, memory_add, memory_patch, memory_remove,
    skill_list, skill_view,
]
"""服务端工具集（与 BROWSER_TOOLS 一起注册进 Agent；P3/P4 继续扩充）。"""
