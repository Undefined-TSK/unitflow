"""长上下文管理：token 估算 + 滑窗 + 滚动摘要（2026-10 调研选型落地）。

背景：多轮对话无限增长会把提示词撑爆、成本线性上升。桌面单机场景的成熟解法是
「滑窗 + 滚动摘要」——
- 估算：中英文混合粗估（中文 1 字 ≈ 1 token，英文 1 词 ≈ 1.3 token），不引重依赖；
- 超预算（CONTEXT_TOKEN_BUDGET）：最近 CONTEXT_KEEP_TURNS 轮完整保留，
  更早的轮次交给百炼 qwen 压缩成一段滚动摘要（注入系统提示词）；
- 触发滚动摘要（CONTEXT_SUMMARY_TRIGGER 轮）后，每轮增量式更新摘要，
  避免全量重算；
- 摘要生成失败（无密钥/网络）时退化为截断拼接，保证主流程永不阻塞。

qwen-long 百万上下文仅作旁路参考：本机向量库检索才是知识主通道，
上下文压缩解决的是会话历史，两者互补不冲突。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import settings


# —— token 粗估 —— #
_CJK = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")
_WORD = re.compile(r"[a-zA-Z0-9_]+")


def estimate_tokens(text: str) -> int:
    """中英文混合 token 粗估：CJK 逐字计 1，英文数字按词计 1.3（含 20% 冗余）。"""
    if not text:
        return 0
    cjk = len(_CJK.findall(text))
    words = len(_WORD.findall(text))
    return cjk + int(words * 1.3 * 1.2) + 4  # +4 角色消息固定开销


@dataclass
class ContextPlan:
    """压缩后的上下文装配结果。"""
    summary: str = ""                    # 滚动摘要（更早轮次的压缩）
    kept_turns: list = field(default_factory=list)   # 完整保留的最近轮次 [(user, assistant)]
    dropped_turns: int = 0               # 被折叠进摘要的轮数
    total_tokens: int = 0                # 压缩前总 token
    kept_tokens: int = 0                 # 压缩后 token（kept + summary）
    compressed: bool = False             # 是否发生了压缩

    def as_history(self) -> list[dict]:
        """转成 chat messages 格式（供 LLM 通道复用）。"""
        msgs: list[dict] = []
        if self.summary:
            msgs.append({"role": "system", "content": f"【前情摘要】\n{self.summary}"})
        for user, assistant in self.kept_turns:
            msgs.append({"role": "user", "content": user})
            if assistant:
                msgs.append({"role": "assistant", "content": assistant})
        return msgs


class ConversationContext:
    """会话级上下文管理器：挂在一个 Session 上，随轮次增量更新。"""

    def __init__(self, session_id: str = ""):
        self.session_id = session_id
        self._summary = ""            # 滚动摘要文本
        self._summarized_upto = 0     # 已被摘要覆盖的轮数（索引上界）

    # —— 主入口：根据全部轮次生成装配方案 —— #
    def plan(self, turns: list) -> ContextPlan:
        """turns: 内存 Session.turns（每轮有 .user/.assistant）。"""
        total = sum(estimate_tokens(t.user) + estimate_tokens(t.assistant)
                    for t in turns)
        budget = settings.CONTEXT_TOKEN_BUDGET
        keep = max(1, settings.CONTEXT_KEEP_TURNS)
        trigger = max(keep + 1, settings.CONTEXT_SUMMARY_TRIGGER)

        # 未超预算且未到摘要触发轮数：原样保留
        if total <= budget and len(turns) < trigger:
            return ContextPlan(
                kept_turns=[(t.user, t.assistant) for t in turns],
                total_tokens=total, kept_tokens=total, compressed=False,
            )

        # 超预算：末尾 keep 轮完整保留，其余折叠摘要
        cut = max(self._summarized_upto, len(turns) - keep)
        head, tail = turns[:cut], turns[cut:]
        summary = self._ensure_summary(head)
        kept_tokens = (estimate_tokens(summary)
                       + sum(estimate_tokens(t.user) + estimate_tokens(t.assistant)
                             for t in tail))
        return ContextPlan(
            summary=summary,
            kept_turns=[(t.user, t.assistant) for t in tail],
            dropped_turns=len(head),
            total_tokens=total, kept_tokens=kept_tokens, compressed=True,
        )

    # —— 滚动摘要（增量式：只对新覆盖的轮次增量压缩） —— #
    def _ensure_summary(self, head: list) -> str:
        if not head:
            return self._summary
        fresh = head[self._summarized_upto:]
        if not fresh:
            return self._summary
        text = self._summarize(fresh)
        self._summarized_upto = len(head)
        if not text:  # 摘要失败：退化为截断拼接
            text = "\n".join(
                f"- 用户：{t.user[:60]}｜助手：{(t.assistant or '')[:60]}" for t in fresh
            )
        self._summary = (self._summary + "\n" + text).strip() if self._summary else text
        # 摘要本身也要设上限，防止无限增长（按 token 预算截断，中文 1 字≈1 token）
        cap = settings.CONTEXT_TOKEN_BUDGET // 3
        if estimate_tokens(self._summary) > cap:
            self._summary = self._summary[-cap:]
        return self._summary

    def _summarize(self, turns: list) -> str:
        """百炼 qwen 增量摘要；失败返回空串（上层退化）。"""
        from .models.dashscope import chat as bailian_chat
        convo = "\n".join(
            f"用户：{t.user}\n助手：{(t.assistant or '')[:300]}" for t in turns
        )
        try:
            return bailian_chat([
                {"role": "system", "content": (
                    "把以下多轮对话压缩成一段不超过 150 字的中文前情摘要，"
                    "保留：用户关注的主题、已得到的结论、未解决的问题。不要添加原对话没有的信息。"
                )},
                {"role": "user", "content": convo},
            ], model=settings.BAILIAN_MODEL, max_tokens=300).strip()
        except Exception:  # noqa: BLE001
            return ""

    def reset(self) -> None:
        self._summary = ""
        self._summarized_upto = 0
