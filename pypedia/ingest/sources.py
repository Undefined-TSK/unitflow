"""资料源清单管理（filelock + 原子替换，防并发写撕裂）。

本模块只负责 sources.json 的 CRUD 与统计，不含抓取与解析逻辑。
索引写入/删除仍委托 rag.py 的 KnowledgeIndex。
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from filelock import FileLock

from ..config import settings
from ..logging_setup import get_logger
from ..rag import get_index

log = get_logger("ingest")

DATA_DIR = Path(os.getenv("PYPEDIA_DATA", str(Path.home() / ".pypedia")))
_LOCK_PATH = DATA_DIR / ".pypedia.lock"

# 对外暴露的向量索引句柄（供 strategies / 测试按需引用）
index = get_index()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    p = DATA_DIR / "sources.json"
    if not p.exists():
        p.write_text("[]", encoding="utf-8")


def _read() -> list[dict]:
    with FileLock(_LOCK_PATH):
        _ensure()
        try:
            return json.loads((DATA_DIR / "sources.json").read_text(encoding="utf-8"))
        except Exception:
            return []


def _write(sources: list[dict]) -> None:
    with FileLock(_LOCK_PATH):
        _ensure()
        tmp = DATA_DIR / "sources.json.tmp"
        tmp.write_text(json.dumps(sources, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, DATA_DIR / "sources.json")  # 原子替换，读者永不见半写文件


def list_sources() -> list[dict]:
    return _read()


def add_source_record(rec: dict) -> str:
    sources = _read()
    sid = rec.get("id") or uuid.uuid4().hex[:10]
    rec["id"] = sid
    rec.setdefault("added_at", _now())
    sources.append(rec)
    _write(sources)
    return sid


def delete_source(source_id: str) -> bool:
    sources = _read()
    before = len(sources)
    target = next((s for s in sources if s.get("id") == source_id), None)
    sources = [s for s in sources if s.get("id") != source_id]
    _write(sources)
    if target:
        index.delete_source(target.get("role", "supplement_b"), source_id)
    return len(sources) != before


def stats() -> dict:
    sources = _read()
    by_role: dict[str, int] = {}
    for s in sources:
        by_role[s.get("role", "?")] = by_role.get(s.get("role", "?"), 0) + 1
    ok = sum(1 for s in sources if s.get("status") == "indexed")
    return {
        "source_count": len(sources),
        "vector_count": index.count(),
        "indexed": ok,
        "pending": len(sources) - ok,
        "by_role": by_role,
    }


def _patch_chunk_count(source_id: str, count: int, chars: int) -> None:
    """回填某资料源的块数与字符数（幂等；内置语料用本条目实际新增块数）。"""
    sources = _read()
    for s in sources:
        if s.get("id") == source_id:
            s["chunk_count"] = count
            s["chars"] = chars
    _write(sources)
