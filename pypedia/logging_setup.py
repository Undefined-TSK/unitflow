"""结构化日志：stdlib logging + JSON 行 + RotatingFileHandler。

- 日志目录：settings.LOG_DIR，缺省 <数据目录>/logs（桌面即 ~/.pypedia/logs）；
- 文件单条 5MB × 3 轮转，JSON 行格式便于 grep / jq / 后期接入采集；
- 控制台同步人可读格式（桌面用户直接看终端）；
- 任意模块 `from .logging_setup import get_logger; log = get_logger("engine")`
  即用；首次调用自动完成初始化（幂等）。

JSON 序列化交给 python-json-logger（成熟库）：extra 字段自动并入、不可序列化值
走 json_default=str、保留字段自动排除，本项目只保留一层字段契约预设。
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

from pythonjsonlogger.json import JsonFormatter as _BaseJsonFormatter

from .config import settings

# 数据目录解析与 ingest/rag 等模块保持一致（import 时求值，测试靠 conftest 预设隔离）
DATA_DIR = Path(os.getenv("PYPEDIA_DATA", str(Path.home() / ".pypedia")))
LOG_DIR = Path(settings.LOG_DIR) if settings.LOG_DIR else DATA_DIR / "logs"

# 项目统一字段契约：ts / level / logger / msg（+ 任意 extra 上下文字段）
_FIELD_RENAMES = {
    "asctime": "ts",
    "levelname": "level",
    "name": "logger",
    "message": "msg",
    "exc_info": "exc",
}


class JsonFormatter(_BaseJsonFormatter):
    """单行 JSON 格式化器：预设项目字段契约，仍可按需覆盖任意参数。"""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("fmt", "%(asctime)s %(levelname)s %(name)s %(message)s")
        kwargs.setdefault("datefmt", "%Y-%m-%dT%H:%M:%S%z")
        kwargs.setdefault("rename_fields", dict(_FIELD_RENAMES))
        kwargs.setdefault("json_default", str)
        kwargs.setdefault("json_ensure_ascii", False)
        super().__init__(*args, **kwargs)


_initialized = False


def setup_logging(level: str | None = None) -> logging.Logger:
    """初始化 pypedia 日志体系（幂等）：文件 JSON + 控制台人可读。"""
    global _initialized
    root = logging.getLogger("pypedia")
    if _initialized:
        return root
    _initialized = True
    root.setLevel(getattr(logging, (level or settings.LOG_LEVEL).upper(), logging.INFO))
    # 文件句柄：日志目录不可写时静默退化为仅控制台（桌面环境偶发只读挂载）
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            LOG_DIR / "pypedia.log",
            maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
        )
        fh.setFormatter(JsonFormatter())
        root.addHandler(fh)
    except OSError:
        pass
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%H:%M:%S"))
    root.addHandler(sh)
    return root


def get_logger(name: str) -> logging.Logger:
    """取子 logger（如 get_logger("engine") → pypedia.engine），首次调用即初始化。"""
    setup_logging()
    return logging.getLogger(name if name.startswith("pypedia") else f"pypedia.{name}")
