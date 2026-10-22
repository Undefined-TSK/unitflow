"""Hermes 式技能库：SKILL.md 注册/校验 + 三级渐进披露 + Curator 30 天归档。

设计（对应 Hermes 「agentskills」特性，全部本地、零 LLM 调用）：
- 一个技能 = 一个目录 `<skills>/<name>/SKILL.md`，frontmatter 承载元数据，
  markdown 正文是给模型的指令（渐进披露第三级才整体注入上下文）；
- 三级披露（省 context，也对应 Hermes 的 progressive disclosure）：
  L1 list_brief  → name + description      （常驻系统提示词的技能清单）
  L2 list_detail → + when_to_use + tags + 用量（设置页面板 / 技能检索）
  L3 view        → SKILL.md 全文           （模型决定启用某技能时才读取）
- 校验：frontmatter 必填 name/description/when_to_use，且 name 必须与目录名
  一致；非法技能跳过并记日志（不阻塞其余技能加载）；
- Curator：archive_stale(days) 把 last_used 超过 N 天（或从未使用且创建超
  N 天）的技能移入 `<skills>/archived/`，清单默认不含归档区；
  调度触发由 P4 cron 负责，本模块只提供纯函数。

铁律：SKILL.md 解析用 python-frontmatter（PyYAML 封装，MIT），不手写 YAML。
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import threading
import time

import frontmatter

from ..config import settings
from ..logging_setup import get_logger
from .hooks import skill_viewed

log = get_logger("agent.skills")

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_REQUIRED_FIELDS = ("name", "description", "when_to_use")
_MAX_SKILL_CHARS = 20000     # 单个 SKILL.md 全文上限


def _skills_dir() -> str:
    base = os.getenv("PYPEDIA_DATA", os.path.join(os.path.expanduser("~"), ".pypedia"))
    return os.path.join(base, "agent", "skills")


class SkillError_(ValueError):
    """技能操作失败（不存在/校验失败），端点层转 400。"""


class SkillStore:
    """技能注册表 + 使用统计（sqlite）+ 归档（文件移动）。"""

    def __init__(self) -> None:
        self._dir = _skills_dir()
        self._db_path = os.path.join(os.path.dirname(self._dir), "agent_memory.db")
        self._lock = threading.RLock()
        os.makedirs(self._dir, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS skill_usage (
                    name TEXT PRIMARY KEY,
                    count INTEGER NOT NULL DEFAULT 0,
                    last_used REAL
                );
            """)
            self._conn.commit()

    # —— 发现与校验 —— #
    def _skill_path(self, name: str) -> str:
        if not _NAME_RE.match(name or ""):
            raise SkillError_(f"技能名非法：{name!r}（小写字母/数字/连字符，≤64 字符）")
        return os.path.join(self._dir, name, "SKILL.md")

    def _load_one(self, name: str) -> dict | None:
        """加载并校验单个技能；非法返回 None（记日志）。"""
        path = self._skill_path(name)
        try:
            with open(path, encoding="utf-8") as f:
                raw = f.read()
        except FileNotFoundError:
            return None
        if len(raw) > _MAX_SKILL_CHARS:
            log.warning("skill_too_large", extra={"skill": name, "chars": len(raw)})
            return None
        try:
            post = frontmatter.loads(raw)
        except Exception as e:  # noqa: BLE001 —— YAML 畸形：跳过该技能不阻塞其余
            log.warning("skill_frontmatter_invalid", extra={"skill": name, "error": str(e)})
            return None
        meta = dict(post.metadata)
        missing = [k for k in _REQUIRED_FIELDS if not str(meta.get(k, "")).strip()]
        if missing:
            log.warning("skill_missing_fields",
                        extra={"skill": name, "missing": missing})
            return None
        if str(meta["name"]).strip() != name:
            log.warning("skill_name_mismatch",
                        extra={"dir": name, "meta_name": meta["name"]})
            return None
        usage = self._usage(name)
        return {
            "name": name,
            "description": str(meta["description"]).strip(),
            "when_to_use": str(meta["when_to_use"]).strip(),
            "tags": meta.get("tags") or [],
            "version": str(meta.get("version", "")).strip(),
            "body": post.content.strip(),
            "path": path,
            "usage": usage,
        }

    def _discover(self) -> list[str]:
        try:
            entries = sorted(os.listdir(self._dir))
        except FileNotFoundError:
            return []
        return [e for e in entries
                if os.path.isdir(os.path.join(self._dir, e)) and e != "archived"]

    # —— 使用统计 —— #
    def _usage(self, name: str) -> dict:
        row = self._conn.execute(
            "SELECT count, last_used FROM skill_usage WHERE name = ?", (name,)).fetchone()
        return {"count": row["count"] if row else 0,
                "last_used": row["last_used"] if row else None}

    def touch(self, name: str) -> None:
        """记录一次技能查看/使用（Curator 归档判据）。"""
        with self._lock:
            self._conn.execute(
                "INSERT INTO skill_usage(name, count, last_used) VALUES (?, 1, ?) "
                "ON CONFLICT(name) DO UPDATE SET count = count + 1, last_used = ?",
                (name, time.time(), time.time()))
            self._conn.commit()

    # —— 三级披露 —— #
    def list_brief(self) -> list[dict]:
        """L1：name + description（进系统提示词，体积最小）。"""
        out = []
        for name in self._discover():
            skill = self._load_one(name)
            if skill:
                out.append({"name": skill["name"], "description": skill["description"]})
        return out

    def list_detail(self) -> list[dict]:
        """L2：+ when_to_use/tags/version/usage（设置页面板）。"""
        out = []
        for name in self._discover():
            skill = self._load_one(name)
            if skill:
                out.append({k: skill[k] for k in
                            ("name", "description", "when_to_use", "tags",
                             "version", "usage")})
        return out

    def view(self, name: str) -> dict:
        """L3：全文（模型/用户查看单个技能时）。"""
        skill = self._load_one(name)
        if skill is None:
            raise SkillError_(f"技能不存在或校验未通过：{name!r}")
        self.touch(name)
        skill_viewed.send("skills", skill=name)
        return skill

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """L2 级关键词过滤（description/when_to_use/tags 子串命中）。"""
        q = (query or "").strip().lower()
        if not q:
            return self.list_detail()[:limit]
        out = []
        for skill in self.list_detail():
            hay = " ".join([skill["description"], skill["when_to_use"],
                            " ".join(skill["tags"] or [])]).lower()
            if q in hay:
                out.append(skill)
            if len(out) >= limit:
                break
        return out

    # —— Curator：30 天归档 —— #
    def archive_stale(self, days: int | None = None) -> list[str]:
        """把超 N 天未使用的技能移入 archived/；返回被归档的技能名。"""
        days = settings.AGENT_SKILL_ARCHIVE_DAYS if days is None else days
        cutoff = time.time() - days * 86400
        archived: list[str] = []
        for name in self._discover():
            usage = self._usage(name)
            last = usage["last_used"]
            if last is not None and last >= cutoff:
                continue
            if last is None:
                # 从未使用：按创建时间判断（目录 mtime）
                try:
                    born = os.path.getmtime(os.path.join(self._dir, name))
                except OSError:
                    continue
                if born >= cutoff:
                    continue
            dst_dir = os.path.join(self._dir, "archived", name)
            os.makedirs(os.path.dirname(dst_dir), exist_ok=True)
            shutil.move(os.path.join(self._dir, name), dst_dir)
            archived.append(name)
            log.info("skill_archived", extra={"skill": name, "days": days})
        return archived

    def unarchive(self, name: str) -> None:
        src = os.path.join(self._dir, "archived", name)
        if not os.path.isdir(src):
            raise SkillError_(f"归档区没有技能：{name!r}")
        shutil.move(src, os.path.join(self._dir, name))


skill_store = SkillStore()
