"""Hermes 式持久记忆库：MEMORY.md / USER.md + FTS5 trigram 检索 + § 子串编辑 + nudge。

设计（对应 Hermes「持久记忆库」特性，全部本地、零 LLM 调用）：
- 双作用域：MEMORY.md（项目/事实记忆）与 USER.md（用户画像记忆），均为
  markdown 文件，§ 段落为最小单元（`## § 时间 · 标签` 头 + 正文）；
- 文件是唯一真相（source of truth）：用户可手工编辑，add/patch/remove 全部
  落到文件；SQLite FTS5（trigram 分词，中文子串可命中）只是检索索引，
  每次写操作同事务重建对应行，不依赖触发器（避免外部编辑不同步）；
- 编辑语义：add 追加新 §；patch/remove 按子串定位目标 §（子串必须唯一命中，
  否则报错带候选列表，避免误改）；
- 字符上限：单文件超 settings.AGENT_MEMORY_MAX_CHARS 时拒绝 add 并提示整理；
- nudge：每 AGENT_NUDGE_EVERY 次 agent_step 由 transport 调一次计数器，
  到期返回整理提醒文本（由调用方决定是否注入系统提示词）。

铁律：纯本地 sqlite3 + 文件 IO，无第三方服务、无网络、零 LLM 调用。
"""
from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from dataclasses import dataclass

from ..config import settings
from ..logging_setup import get_logger
from .hooks import memory_written
from .redact import redact_text

log = get_logger("agent.memory")

SCOPES = ("memory", "user")
_FILES = {"memory": "MEMORY.md", "user": "USER.md"}
_SECTION_RE = re.compile(r"^## § ", re.MULTILINE)
_MAX_PATCH_CANDIDATES = 5


def _data_dir() -> str:
    base = os.getenv("PYPEDIA_DATA", os.path.join(os.path.expanduser("~"), ".pypedia"))
    return os.path.join(base, "agent", "memories")


class MemoryError_(ValueError):
    """记忆操作失败（作用域/子串/上限问题），端点层转 400。"""


@dataclass
class Section:
    index: int          # 在文件中的序号（0 起）
    header: str         # `## § ...` 整行
    body: str           # 正文（不含头）

    @property
    def text(self) -> str:
        return f"{self.header}\n{self.body}".rstrip()


def _split_sections(content: str) -> list[Section]:
    """按 `## § ` 切分段落；头部之前的游离内容归入 index=0 的 pseudo 段。"""
    parts = _SECTION_RE.split(content)
    if not parts:
        return []
    sections: list[Section] = []
    preamble = parts[0]
    if preamble.strip():
        sections.append(Section(0, "## § （无序前言）", preamble.strip()))
    for i, body in enumerate(parts[1:], start=1):
        lines = body.split("\n", 1)
        header = "## § " + lines[0]
        sections.append(Section(i, header, (lines[1] if len(lines) > 1 else "").strip()))
    return sections


class MemoryStore:
    """双 md 文件 + FTS5 索引的记忆库（线程安全，进程内单例）。"""

    def __init__(self) -> None:
        self._dir = _data_dir()
        # 与 SkillStore 共用同一个库文件（agent/agent_memory.db）：记忆 § 索引
        # 与技能用量统计分表存放，一处初始化、互不干扰。
        self._db_path = os.path.join(os.path.dirname(self._dir), "agent_memory.db")
        self._lock = threading.RLock()
        os.makedirs(self._dir, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    # —— 基础设施 —— #
    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS sections (
                    scope TEXT NOT NULL,
                    idx INTEGER NOT NULL,
                    header TEXT NOT NULL,
                    body TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (scope, idx)
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS sections_fts USING fts5(
                    header, body, content='sections', content_rowid='rowid',
                    tokenize='trigram'
                );
                CREATE TRIGGER IF NOT EXISTS sections_ai AFTER INSERT ON sections BEGIN
                    INSERT INTO sections_fts(rowid, header, body)
                    VALUES (new.rowid, new.header, new.body);
                END;
                CREATE TRIGGER IF NOT EXISTS sections_ad AFTER DELETE ON sections BEGIN
                    INSERT INTO sections_fts(sections_fts, rowid, header, body)
                    VALUES ('delete', old.rowid, old.header, old.body);
                END;
                CREATE TRIGGER IF NOT EXISTS sections_au AFTER UPDATE ON sections BEGIN
                    INSERT INTO sections_fts(sections_fts, rowid, header, body)
                    VALUES ('delete', old.rowid, old.header, old.body);
                    INSERT INTO sections_fts(rowid, header, body)
                    VALUES (new.rowid, new.header, new.body);
                END;
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY, value INTEGER NOT NULL
                );
            """)
            self._conn.commit()

    def _path(self, scope: str) -> str:
        if scope not in SCOPES:
            raise MemoryError_(f"未知记忆作用域：{scope!r}（可用：{'/'.join(SCOPES)}）")
        return os.path.join(self._dir, _FILES[scope])

    def _read(self, scope: str) -> str:
        try:
            with open(self._path(scope), encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def _write(self, scope: str, content: str) -> None:
        if len(content) > settings.AGENT_MEMORY_MAX_CHARS:
            raise MemoryError_(
                f"{_FILES[scope]} 将达到 {len(content)} 字符，超过上限 "
                f"{settings.AGENT_MEMORY_MAX_CHARS}：请先 patch/remove 清理旧记忆")
        tmp = self._path(scope) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, self._path(scope))   # 原子替换，避免写一半损坏

    # —— FTS 同步（与文件写同事务） —— #
    def _reindex_scope(self, scope: str, sections: list[Section]) -> None:
        self._conn.execute("DELETE FROM sections WHERE scope = ?", (scope,))
        self._conn.executemany(
            "INSERT INTO sections(scope, idx, header, body, updated_at) VALUES (?,?,?,?,?)",
            [(scope, s.index, s.header, s.body, time.time()) for s in sections])

    def _flush(self, scope: str, content: str) -> list[Section]:
        sections = _split_sections(content)
        with self._lock:
            self._write(scope, content)
            self._reindex_scope(scope, sections)
            self._conn.commit()
        return sections

    # —— 读 —— #
    def render(self, scope: str) -> str:
        """全文（设置页只读查看用）。"""
        return self._read(scope)

    def list_sections(self, scope: str) -> list[Section]:
        return _split_sections(self._read(scope))

    def search(self, query: str, scope: str | None = None,
               limit: int = 10) -> list[dict]:
        """FTS5 trigram 检索（中文子串可命中；查询词 <3 字符退化为 LIKE）。"""
        query = (query or "").strip()
        if not query:
            return []
        if len(query) < 3:
            return self._search_like(query, scope, limit)
        return self._search_fts(query, scope, limit)

    def _search_fts(self, query: str, scope: str | None, limit: int) -> list[dict]:
        # 双引号包裹 = FTS5 字符串字面量，避免查询语法注入（AND/OR/NEAR/- 等）
        expr = '"' + query.replace('"', '""') + '"'
        sql = ("SELECT scope, idx, header, body FROM sections_fts "
               "WHERE sections_fts MATCH ?")
        args: list = [expr]
        if scope:
            sql += " AND scope = ?"
            args.append(scope)
        sql += " ORDER BY rank LIMIT ?"
        args.append(limit)
        try:
            with self._lock:
                rows = self._conn.execute(sql, args).fetchall()
        except sqlite3.OperationalError:
            # 极端查询形态（如纯符号）trigram 解析失败时退化为 LIKE
            return self._search_like(query, scope, limit)
        return [dict(r) for r in rows]

    def _search_like(self, query: str, scope: str | None, limit: int) -> list[dict]:
        sql = "SELECT scope, idx, header, body FROM sections WHERE body LIKE ?"
        args: list = [f"%{query}%"]
        if scope:
            sql += " AND scope = ?"
            args.append(scope)
        sql += " ORDER BY updated_at DESC LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [dict(r) for r in rows]

    # —— 写 —— #
    def add(self, scope: str, text: str, tag: str = "") -> str:
        """追加新 §；返回 § 头（便于调用方确认落点）。"""
        text = (text or "").strip()
        if not text:
            raise MemoryError_("记忆内容不能为空")
        if len(text) > settings.AGENT_MEMORY_MAX_CHARS:
            raise MemoryError_(f"单条记忆 {len(text)} 字符超过上限 "
                               f"{settings.AGENT_MEMORY_MAX_CHARS}")
        # 脱敏闸门：密钥/令牌不落记忆文件（写了就会永久留在上下文里）
        text = redact_text(text, source="memory_add").text
        stamp = time.strftime("%Y-%m-%d %H:%M")
        header = f"## § {stamp}" + (f" · {tag.strip()}" if tag.strip() else "")
        content = self._read(scope)
        if content and not content.endswith("\n"):
            content += "\n"
        content += f"\n{header}\n{text}\n"
        self._flush(scope, content)
        log.info("memory_added", extra={"scope": scope, "chars": len(text)})
        memory_written.send("memory", op="add", scope=scope, chars=len(text))
        return header

    def _locate(self, scope: str, needle: str) -> tuple[list[Section], list[Section]]:
        sections = self.list_sections(scope)
        hits = [s for s in sections if needle in s.text]
        if not hits:
            raise MemoryError_(
                f"在 {_FILES[scope]} 中找不到包含 {needle!r} 的段落；"
                f"可用 patch/remove 前先 memory_search 确认原文")
        if len(hits) > 1:
            preview = "；".join(s.header[5:40] for s in hits[:_MAX_PATCH_CANDIDATES])
            raise MemoryError_(
                f"子串 {needle!r} 命中 {len(hits)} 个段落（{preview}…），"
                f"请提供更长的唯一子串")
        return sections, hits

    def patch(self, scope: str, old: str, new: str) -> str:
        """子串替换（定位到唯一 § 后整段替换正文）。返回新 § 头。"""
        old, new = (old or "").strip(), (new or "").strip()
        if not old or not new:
            raise MemoryError_("patch 需要非空的 old 与 new")
        # 脱敏闸门：新正文同样不过密钥（old 是定位子串，不脱敏）
        new = redact_text(new, source="memory_patch").text
        sections, (hit,) = self._locate(scope, old)
        body = hit.text.replace(old, new)
        lines = body.split("\n", 1)
        new_section = Section(hit.index, lines[0], lines[1] if len(lines) > 1 else "")
        out = []
        replaced = False
        for s in sections:
            out.append(new_section.text if s.index == hit.index and not replaced
                       else s.text)
            replaced = replaced or s.index == hit.index
        self._flush(scope, "\n\n".join(out) + "\n")
        memory_written.send("memory", op="patch", scope=scope, chars=len(new))
        return new_section.header

    def remove(self, scope: str, needle: str) -> str:
        """删除唯一命中的 §；返回被删 § 头。"""
        sections, (hit,) = self._locate(scope, needle)
        rest = [s.text for s in sections if s.index != hit.index]
        self._flush(scope, ("\n\n".join(rest) + "\n") if rest else "")
        memory_written.send("memory", op="remove", scope=scope,
                            header=hit.header[5:60])
        return hit.header

    # —— nudge（步数计数） —— #
    def bump_step(self) -> str | None:
        """agent_step 计数 +1；每到 AGENT_NUDGE_EVERY 的倍数返回整理提醒。"""
        with self._lock:
            row = self._conn.execute(
                "INSERT INTO meta(key, value) VALUES('steps', 1) "
                "ON CONFLICT(key) DO UPDATE SET value = value + 1 "
                "RETURNING value").fetchone()
            self._conn.commit()
            steps = row[0] if row else 0
        if steps and steps % max(1, settings.AGENT_NUDGE_EVERY) == 0:
            return (f"（记忆整理提醒：已进行 {steps} 步对话。可用 memory_search "
                    f"回顾既有记忆，避免重复记录；必要时 patch/remove 清理过期内容。）")
        return None


memory_store = MemoryStore()
