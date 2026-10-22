"""Reflexion 自反思薄层：每次问答后沉淀「改进点」，形成元认知 buffer。

核心范式（与微调模型严格区分）：
- 模型权重冻结，不训练。
- 进化发生在 prompt / 记忆层面：把「哪里做得不好」「下次怎么不同」写入日志，
  下次以累积反思为条件注入系统提示词，让同一个模型在下一次表现得更好。
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from ..logging_setup import get_logger
from ..models.dashscope import chat

log = get_logger("evolution.reflexion")

DATA_DIR = Path(os.getenv("PYPEDIA_DATA", str(Path.home() / ".pypedia")))


class ReflectionLog:
    """反思日志：持久化到磁盘，跨会话保留最近的反思记录。"""

    def __init__(self) -> None:
        self.path = DATA_DIR / "reflections.json"
        self._ensure()

    def _ensure(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _read(self) -> list[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
            # 静默返回空会让下一次 _write 覆盖损坏文件 → 反思记录永久丢失
            log.error("reflection_file_corrupt",
                      extra={"path": str(self.path), "error": str(e)})
            self._quarantine()
            return []

    def _quarantine(self) -> None:
        """把损坏/不可解析的数据文件改名留存，避免被下一次写入覆盖。"""
        try:
            if self.path.exists():
                self.path.rename(self.path.with_name(
                    f"{self.path.stem}.corrupt-{int(time.time())}{self.path.suffix}"))
        except OSError as e:
            log.warning("reflection_quarantine_failed", extra={"error": str(e)})

    def _write(self, data: list[dict]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add(self, entry: dict) -> None:
        data = self._read()
        data.append(entry)
        self._write(data[-200:])  # 仅保留最近 200 条，避免无限增长

    def recent(self, n: int = 5) -> list[dict]:
        return self._read()[-n:]

    def summary(self, n: int = 5) -> str:
        rs = self.recent(n)
        if not rs:
            return ""
        return "\n".join(f"- {r.get('note', '')}" for r in rs)

    def reflect(self, query: str, answer: str, confidence: float, cascade_hit: bool) -> str:
        """调用 qwen-plus 生成一句改进点并写入日志。失败返回空串并留痕（不抛给主流程）。"""
        prompt = (
            "你是 PyPedia 的自我反思器。基于本次交互，用一句中文指出可改进之处"
            "（例如：证据不足应提示局限、用户可能没懂、应补充可视化示例、术语过多）。\n"
            f"用户问题：{query}\n本轮置信度：{confidence}/100\n主源是否命中：{cascade_hit}\n"
            f"回答前120字：{answer[:120]}\n只输出一句中文改进点，不要解释、不要 markdown。"
        )
        try:
            note = chat([{"role": "user", "content": prompt}], temperature=0.0, max_tokens=60).strip()
            note = note.strip("“”\"'")
            if note:
                self.add({
                    "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "query": query,
                    "confidence": confidence,
                    "note": note,
                })
            return note
        except Exception as e:  # noqa: BLE001 —— 反思属旁路，绝不能拖垮主流程，但必须留痕
            log.warning("reflection_failed", extra={"error": str(e)})
            return ""
