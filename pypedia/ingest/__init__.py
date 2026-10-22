"""知识摄入层：用户资料源（URL / GitHub / 离线文档）的抓取、解析、入库。

包结构（按职责 + 对象类思想拆分，逻辑零改动）：
- parsers.py  ：单文件 → 纯文本（trafilatura / pypdfium2 / mammoth / ... + ZIP 炸弹防护）
- sources.py  ：sources.json 清单管理（filelock + 原子替换）+ 统计
- crawl.py    ：网页/GitHub 抓取（focused_crawler + 双通路降级）
- strategies.py：摄入策略类（UrlStrategy / GithubStrategy / FileStrategy）+ 内置语料批处理
- preset.py   ：预置权威资料源（Python 官方文档 / CPython / 官方论坛）

本 __init__ 重新导出旧 ingest.py 的全部公开名，所有调用方（engine / app / cli /
knowledge / tests）零改动。
"""
from __future__ import annotations

# —— 配置（旧 ingest.py 曾直接暴露 settings，测试依赖 ing.settings） —— #
from ..config import settings

# —— 子模块公开 API 聚合 —— #
from .crawl import (_crawl_github, _crawl_site, _fetch_via_mcp,
                   _fetch_via_requests, _page_title, _UA)
from .parsers import (SUPPORTED_EXTS, _check_zip_safe, check_file_safe,
                      html_to_text, parse_file)
from .preset import (PRESET_PATH, ingest_preset_sources, load_preset_sources)
from .sources import (DATA_DIR, _LOCK_PATH, _now, _ensure, _read, _write,
                      add_source_record, delete_source, index, list_sources,
                      stats, _patch_chunk_count)
from .strategies import (GithubStrategy, FileStrategy, IngestStrategy,
                         UrlStrategy, _make_doc, _norm_role, ingest_builtin_corpus,
                         ingest_file, ingest_github, ingest_url)

__all__ = [
    # 来源策略
    "ingest_url", "ingest_github", "ingest_file", "ingest_builtin_corpus",
    "IngestStrategy", "UrlStrategy", "GithubStrategy", "FileStrategy",
    # 预置源
    "load_preset_sources", "ingest_preset_sources", "PRESET_PATH",
    # 清单管理
    "list_sources", "add_source_record", "delete_source", "stats",
    "DATA_DIR", "index",
    # 解析
    "SUPPORTED_EXTS", "parse_file", "check_file_safe", "html_to_text",
    "_check_zip_safe",
    # 配置（测试依赖 ing.settings）
    "settings",
    # 内部工具（测试/调用方仍可能引用）
    "_norm_role", "_make_doc", "_patch_chunk_count", "_read", "_write",
]
