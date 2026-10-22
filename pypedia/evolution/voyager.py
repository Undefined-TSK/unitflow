"""Voyager 技能库薄层：把成功的「问答模式 / 用户偏好 / 高频主题」沉淀为可复用 skill，终身复用。

与 Reflexion 互补：Reflexion 记录「不足」，Voyager 记录「成功可复用」。
同样冻结模型权重，进化只体现在 prompt 注入的技能与约束上。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from ..logging_setup import get_logger

log = get_logger("evolution.voyager")

DATA_DIR = Path(os.getenv("PYPEDIA_DATA", str(Path.home() / ".pypedia")))


class SkillLibrary:
    """用户专属技能库：name（技能名）/ trigger（何时触发）/ action（怎么做）。"""

    def __init__(self) -> None:
        self.path = DATA_DIR / "skills.json"
        self._ensure()

    def _ensure(self) -> None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _read(self) -> list[dict]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
            # 静默返回空会导致下一次 _write 直接覆盖损坏文件 → 技能永久丢失。
            # 改为：留痕 + 把损坏原件改名隔离，保证可读回原始数据。
            log.error("skill_file_corrupt",
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
            log.warning("skill_quarantine_failed", extra={"error": str(e)})

    def _write(self, data: list[dict]) -> None:
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_skill(self, name: str, trigger: str, action: str) -> bool:
        """新增或覆盖同名技能。返回是否新增。"""
        data = self._read()
        for s in data:
            if s["name"] == name:
                s.update(trigger=trigger, action=action)
                self._write(data)
                return False
        data.append({"name": name, "trigger": trigger, "action": action,
                     "used": 0})
        self._write(data)
        return True

    def list_skills(self) -> list[dict]:
        return self._read()

    def prompt_injection(self) -> str:
        """把已掌握技能拼成系统提示词片段，注入到每次问答。"""
        data = self._read()
        if not data:
            return ""
        lines = "\n".join(f"- {s['name']}：当「{s['trigger']}」时，{s['action']}" for s in data)
        return "【你已掌握的用户专属技能（务必遵守）】\n" + lines

    def infer_from_session(self, level: int, top_topics: list[str],
                           low_conf_count: int) -> list[str]:
        """根据会话特征自动沉淀技能（Voyager 自动发现）。返回新增技能名。"""
        added: list[str] = []
        if level <= 2:
            if self.add_skill(
                "入门友好", "用户是 L1-L2 入门者",
                "避免 jargon，用比喻+逐行注释的代码，优先给出可运行的最小示例"
            ):
                added.append("入门友好")
        if low_conf_count >= 2:
            if self.add_skill(
                "证据不足时诚实", "近期多次置信度偏低",
                "明确说明不确定性，优先建议用户补充官方文档链接，不要臆测"
            ):
                added.append("证据不足时诚实")
        for t in top_topics[:2]:
            if self.add_skill(
                f"主题-{t}", f"用户频繁问到「{t}」相关",
                f"对「{t}」类问题，主动给出官方文档链接与可视化对比"
            ):
                added.append(f"主题-{t}")
        return added
