"""答案交叉审阅：双模型二审（A2A 协议层的轻量替代，2026-10 调研结论）。

调研背景：A2A（Agent2Agent）协议解决的是「跨组织、跨厂商 agent 互相发现与协作」。
PyPedia 是单机桌面应用，没有外部 agent 生态可互操作，引入 A2A 服务端/客户端
是净负担（协议握手、Agent Card、任务生命周期全套开销，换不来实际收益）。

但「多 agent 交叉验证」的思想用更轻的方式落地：出答案的模型不再自我背书，
由一个独立审阅通道（同模型不同系统提示词，或 .env 配置的更强模型）对照证据
审阅，找出事实错误、与证据矛盾、过度断言之处；有实质差异时给出修订版，
前端以「二审提示」形式展示，用户自行取舍。审阅失败（无密钥/网络）只跳过，
绝不影响主答案产出。
"""
from __future__ import annotations

import json
import re

from .config import settings
from .plugins import plugin_registry

REVIEW_SYSTEM = (
    "你是严格的答案审阅员。给定用户问题、参考证据和一份助手回答，"
    "你的职责：找出回答中的事实错误、与证据矛盾之处、无依据的过度断言。"
    "只依据给定证据判断，不引入外部知识。\n"
    "严格只输出 JSON："
    '{"verdict": "pass|revise", "notes": ["问题1", "问题2"], '
    '"revised": "<修订后的完整回答，verdict=pass 时留空>"}'
)


def review_answer(query: str, answer: str, evidence: list[str]) -> dict:
    """对已回答的问题做二审。返回 {verdict, notes, revised, skipped}。

    verdict=pass：无实质问题；verdict=revise：notes 列问题，revised 为修订版。
    skipped=True：审阅未启用或调用失败（不影响主流程）。
    """
    if not plugin_registry.is_enabled("review") or not answer:
        return {"verdict": "skipped", "notes": [], "revised": "", "skipped": True}
    if not evidence:  # 无证据不硬审（避免审阅员凭空挑刺）
        return {"verdict": "skipped", "notes": [], "revised": "", "skipped": True}

    from .models.dashscope import chat as bailian_chat

    ev = "\n---\n".join(f"[{i + 1}] {t[:380]}" for i, t in enumerate(evidence[:5]))
    user = f"用户问题：{query}\n\n参考证据：\n{ev}\n\n待审回答：\n{answer}"

    try:
        txt = bailian_chat(
            [{"role": "system", "content": REVIEW_SYSTEM},
             {"role": "user", "content": user}],
            model=settings.REVIEW_MODEL or None,
            temperature=0.0,
            max_tokens=800,
        )
        m = re.search(r"\{.*\}", txt, re.S)
        if not m:
            return {"verdict": "skipped", "notes": [], "revised": "", "skipped": True}
        obj = json.loads(m.group())
        verdict = "revise" if obj.get("verdict") == "revise" else "pass"
        notes = [str(n)[:120] for n in (obj.get("notes") or [])][:5]
        revised = str(obj.get("revised") or "")[:4000]
        if verdict == "revise" and not revised:
            verdict = "pass"  # 只有意见没有修订版 → 仅提示不替换
        return {"verdict": verdict, "notes": notes, "revised": revised, "skipped": False}
    except Exception:  # noqa: BLE001
        return {"verdict": "skipped", "notes": [], "revised": "", "skipped": True}
