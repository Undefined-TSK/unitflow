"""多轮会话记忆 + 用户画像沉淀。"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from ..textutil import keywords as jieba_keywords


@dataclass
class Turn:
    user: str
    assistant: str
    confidence: float
    primary_title: str = ""


@dataclass
class Session:
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    level: int = 3
    turns: list[Turn] = field(default_factory=list)
    # 用户画像（自进化素材）：高频主题、常卡点、偏好
    profile: dict = field(default_factory=lambda: {
        "topics": {},      # 主题 -> 出现次数
        "weak_spots": {},  # 反复追问的点 -> 次数
        "prefers": [],     # 偏好描述（从反馈沉淀）
    })
    # 长上下文管理（token 预算 + 滑窗 + 滚动摘要），见 conversation.py
    context: object = None  # engine 初始化时注入 ConversationContext

    def __post_init__(self) -> None:
        if self.context is None:
            from ..conversation import ConversationContext

            self.context = ConversationContext(self.session_id)

    def add(self, user: str, assistant: str, confidence: float, primary_title: str = "") -> None:
        self.turns.append(Turn(user, assistant, confidence, primary_title))
        # 主题提取统一走 jieba TF-IDF（成熟中文分词库，见 textutil）
        for kw in jieba_keywords(user):
            self.profile["topics"][kw] = self.profile["topics"].get(kw, 0) + 1

    def recent_context(self, k: int = 3) -> list[str]:
        """返回最近 k 轮用户问题，用于级联检索的查询扩展与多轮指代消解。"""
        return [t.user for t in self.turns[-k:]]

    def feedback(self, good: bool, note: str = "") -> None:
        if good:
            self.profile["prefers"].append(note or "正面反馈")
        else:
            self.profile["weak_spots"][note or "未理解"] = (
                self.profile["weak_spots"].get(note or "未理解", 0) + 1
            )

    def summary(self) -> str:
        topics = sorted(self.profile["topics"].items(), key=lambda x: -x[1])[:4]
        top = "、".join(f"{k}({v})" for k, v in topics) or "—"
        return (
            f"会话 {self.session_id} · 等级 L{self.level} · 已对话 {len(self.turns)} 轮\n"
            f"常问主题：{top}"
        )
