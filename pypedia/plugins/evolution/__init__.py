"""自进化示范插件：把 pypedia.evolution.Evolution 包装为可开关插件。

第一个「有真封装」的插件——为后续插件（以及未来的第三方插件）立模式：
**子类化既有能力类，在对外方法入口加实时门控**，被关时：
- observe 零副作用：问答链路零反思、零技能沉淀，连后台线程都不起；
- prompt_injection 返回空串：系统提示词无进化段；
- feedback 返回 ok=False（端点已先行 503，这里是纵深防御）；
- state() 附带 enabled 标志：UI/调用方可见启停态。

为什么用子类而不是组合封装：.skills/.reflections 必须是**同一批对象**——
既有测试 monkeypatch `engine.evolution.skills.add_skill` 等方法级路径，
组合封装会让补丁打在包装器上、内层对象不感知（静默失效）。子类化下
属性身份天然保持，166/314 等调用行零改。

门控实时读（plugin_registry.is_enabled → settings.EVOLUTION_ENABLE +
state.json 用户态），不缓存——与插件系统全局语义一致。
"""
from __future__ import annotations

from ...evolution import Evolution
from .. import plugin_registry

_PLUGIN_ID = "evolution"
_OFF_MSG = "自进化插件已在设置/插件面板中关闭"


class EvolutionPlugin(Evolution):
    """自进化插件（Reflexion 反思 + Voyager 技能沉淀 + 启停门控）。"""

    def observe(self, query: str, answer: str, confidence: float,
                cascade_hit: bool, level: int) -> None:
        if not plugin_registry.is_enabled(_PLUGIN_ID):
            return  # 关：零反思零沉淀，后台线程都不起
        super().observe(query, answer, confidence, cascade_hit, level)

    def prompt_injection(self) -> str:
        if not plugin_registry.is_enabled(_PLUGIN_ID):
            return ""
        return super().prompt_injection()

    def feedback(self, query: str, issue: str, lesson: str = "",
                 level: int = 3) -> dict:
        if not plugin_registry.is_enabled(_PLUGIN_ID):
            return {"ok": False, "query": query, "lesson": lesson or issue,
                    "error": _OFF_MSG, "disabled": True}
        return super().feedback(query, issue, lesson, level)

    def state(self) -> dict:
        out = super().state()
        out["enabled"] = plugin_registry.is_enabled(_PLUGIN_ID)
        return out
