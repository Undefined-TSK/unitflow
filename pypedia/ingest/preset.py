"""预置权威资料源（Python 官方文档 / CPython / 官方论坛）。

清单放在可编辑的 JSON（data/preset_sources.json）而非代码里：新增/删除资料源
无需改代码，用户也可自行编辑。首次启动（联网抓取开启时）后台真实抓取入库。
"""
from __future__ import annotations

import json
from pathlib import Path

from ..config import settings
from ..logging_setup import get_logger
from ..plugins import plugin_registry
from . import sources, strategies

log = get_logger("ingest")

# data/ 在 pypedia/ 下，preset.py 在 pypedia/ingest/ 下，需上溯两级
PRESET_PATH = Path(__file__).resolve().parent.parent / "data" / "preset_sources.json"


def load_preset_sources() -> list[dict]:
    """读取预置权威资料源清单（data/preset_sources.json）。"""
    if not PRESET_PATH.exists():
        return []
    try:
        data = json.loads(PRESET_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
        log.error("preset_sources_unreadable",
                  extra={"path": str(PRESET_PATH), "error": str(e)})
        return []
    return [s for s in data.get("sources", []) if s.get("target") and s.get("kind")]


def ingest_preset_sources(force: bool = False) -> dict:
    """把预置权威资料源导入索引（幂等；单源失败不影响其余源，绝不阻塞启动）。

    - force=False：已存在同 target 的记录直接跳过（重复启动不会重复抓取）；
    - 抓取受 settings.ENABLE_WEB_FETCH 控制；关闭时源会被记为 pending 并附开启指引，
      已有的内置语料（corpus.json）仍作为离线兜底正常可用。
    """
    presets = load_preset_sources()
    if not plugin_registry.is_enabled("preset-sources"):
        return {"total": len(presets), "added": 0, "skipped": 0, "failed": 0,
                "disabled": True, "web_fetch": plugin_registry.is_enabled("web-fetch")}
    # 未开启联网抓取时一条都不登记：否则知识库页会凭空多出一片「抓取失败」的
    # pending 条目（用户并未主动导入）。开启 ENABLE_WEB_FETCH 后自动生效。
    if not plugin_registry.is_enabled("web-fetch"):
        return {"total": len(presets), "added": 0, "skipped": 0, "failed": 0,
                "disabled": True, "web_fetch": False,
                "note": "未开启联网抓取：.env 设 ENABLE_WEB_FETCH=true 后启动即自动导入"}
    existing = {s.get("target") for s in sources.list_sources()}
    added = skipped = failed = 0
    for p in presets:
        target, kind = p["target"], p["kind"]
        if not force and target in existing:
            skipped += 1
            continue
        try:
            if kind == "github":
                r = strategies.ingest_github(target, p.get("role", "supplement_a"), p.get("title"))
            else:
                r = strategies.ingest_url(target, p.get("role", "main"), p.get("title"),
                                         p.get("max_pages"))
            if r.get("status") == "indexed":
                added += 1
                log.info("preset_source_indexed",
                         extra={"target": target, "chunks": r.get("chunks", 0)})
            else:
                failed += 1
                log.warning("preset_source_pending",
                            extra={"target": target, "status": r.get("status"),
                                   "note": r.get("note", "")})
        except Exception as e:  # noqa: BLE001 —— 单源失败不得中断其余源与启动流程
            failed += 1
            log.warning("preset_source_failed",
                        extra={"target": target, "error": str(e)})
    return {"total": len(presets), "added": added, "skipped": skipped,
            "failed": failed, "disabled": False,
            "web_fetch": plugin_registry.is_enabled("web-fetch")}
