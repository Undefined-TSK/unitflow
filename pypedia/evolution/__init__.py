"""自进化模块：Reflexion（反思）+ Voyager（技能库）的统一门面。

遵循「冻结模型权重，只在 prompt / 记忆层面进化」的原则，不微调模型：
- Reflexion：每次问答后由 qwen-plus 生成一句改进点（后台线程，不阻塞）。
- Voyager：把「用户等级偏好 / 高频主题 / 低置信教训」沉淀为可复用 skill（即时）。
- 二者合并为系统提示词片段注入，使同一个模型在后续交互中持续变强。
"""
from __future__ import annotations

import threading

from ..logging_setup import get_logger
from .reflexion import ReflectionLog
from .voyager import SkillLibrary

__all__ = ["ReflectionLog", "SkillLibrary", "Evolution"]

log = get_logger("evolution")


class Evolution:
    """自进化编排：反思 + 技能库 + 提示词注入 + 用户反馈闭环。"""

    def __init__(self) -> None:
        self.reflections = ReflectionLog()
        self.skills = SkillLibrary()
        self._pending: list[dict] = []  # 待反思队列（后台线程消费）

    # —— 每次问答后调用：反思（后台）+ 技能沉淀（即时） —— #
    def observe(self, query: str, answer: str, confidence: float,
                cascade_hit: bool, level: int) -> None:
        # 即时：按会话特征沉淀技能（无 LLM 成本）
        try:
            recent = self.reflections.recent(5)
            low_conf = sum(1 for r in recent if r.get("confidence", 100) < 50)
            topics = [query[:6]]
            self.skills.infer_from_session(level, topics, low_conf)
        except Exception as e:  # noqa: BLE001 —— 旁路能力，不拖垮主流程，但必须留痕
            log.warning("skill_infer_failed", extra={"error": str(e)})
        # 后台：调用 qwen-plus 生成一句改进点并写日志
        threading.Thread(
            target=self._safe_reflect,
            args=(query, answer, confidence, cascade_hit),
            daemon=True,
        ).start()

    def _safe_reflect(self, query, answer, confidence, cascade_hit) -> None:
        try:
            self.reflections.reflect(query, answer, confidence, cascade_hit)
        except Exception as e:  # noqa: BLE001 —— 后台线程，异常无处上抛，必须落日志
            log.warning("background_reflect_failed", extra={"error": str(e)})

    # —— 用户纠正反馈 → 强制反思 + 沉淀技能（察言观色 → 能力进化） —— #
    def feedback(self, query: str, issue: str, lesson: str = "",
                 level: int = 3) -> dict:
        lesson = lesson or issue
        try:
            self.reflections.add({
                "type": "user_feedback",
                "query": query,
                "confidence": 0,
                "note": f"用户反馈：{issue}" + (f" → 教训：{lesson}" if lesson else ""),
            })
            name = f"纠正-{(query or '通用')[:8]}"
            self.skills.add_skill(name, f"当问题涉及「{query[:16]}」时", lesson or issue)
        except Exception as e:  # noqa: BLE001
            # 失败必须如实返回 ok=False：此前恒返回 True，前端明明没沉淀成功却提示"已沉淀成技能"
            log.error("feedback_persist_failed", extra={"error": str(e)})
            return {"ok": False, "query": query, "lesson": lesson, "error": str(e)}
        return {"ok": True, "query": query, "lesson": lesson}

    # —— 供系统提示词注入（即时读取，无 LLM 成本） —— #
    def prompt_injection(self) -> str:
        parts = [self.skills.prompt_injection(), self.reflections.summary(3)]
        return "\n\n".join(p for p in parts if p)

    # —— 前端展示 —— #
    def state(self) -> dict:
        return {
            "skills": self.skills.list_skills(),
            "reflections": self.reflections.recent(6),
        }
