"""本地 Bearer Token 鉴权（默认关闭；面向暴露到局域网/公网场景的一次性开关）。

设计约束：
- 桌面单机为主，默认不鉴权（AUTH_ENABLE=false）——开启零负担，关闭零影响；
- 令牌来源优先级：.env 的 AUTH_TOKEN > 数据目录 token 文件 > 首次启用时生成落盘；
- 令牌文件权限 600（仅所有者可读写），先落盘再限权，杜绝窗口期；
- 常量时间比较（secrets.compare_digest），防时序侧信道；
- 放行清单：/、/static（前端资产）、/api/status（健康检查，不含密钥明文）。
"""
from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path

from .config import settings
from .plugins import plugin_registry

DATA_DIR = Path(os.getenv("PYPEDIA_DATA", str(Path.home() / ".pypedia")))
TOKEN_FILE = DATA_DIR / "token"

# 中间件放行前缀（鉴权开启时也不需要令牌的路径）
PUBLIC_PREFIXES = ("/static",)
PUBLIC_EXACT = {"/", "/api/status"}

# 启动时解析的进程内令牌（ensure_token 填充；见 app.py）
_current = ""


def generate_token() -> str:
    """256bit 随机数的 URL 安全表示（43 字符）。"""
    return secrets.token_urlsafe(32)


def save_token(token: str) -> Path:
    """令牌写入数据目录并限权 600。"""
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(token, encoding="utf-8")
    TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    return TOKEN_FILE


def ensure_token() -> str:
    """启动时调用：启用鉴权则确保有可用令牌并缓存；未启用返回空串。"""
    global _current
    if not plugin_registry.is_enabled("auth"):
        _current = ""
        return ""
    if settings.AUTH_TOKEN:
        _current = settings.AUTH_TOKEN
    elif TOKEN_FILE.exists():
        _current = TOKEN_FILE.read_text(encoding="utf-8").strip()
    else:
        token = generate_token()
        save_token(token)
        _current = token
    return _current


def current_token() -> str:
    return _current


def is_public(path: str) -> bool:
    if path in PUBLIC_EXACT:
        return True
    return any(path == p or path.startswith(p + "/") for p in PUBLIC_PREFIXES)


def check_header(authorization: str | None) -> bool:
    """校验 Authorization 头。未启用鉴权时恒真（放行）。"""
    if not plugin_registry.is_enabled("auth"):
        return True
    if not authorization or not _current:
        return False
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return False
    return secrets.compare_digest(parts[1].strip(), _current)
