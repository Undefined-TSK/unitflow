"""Profile 管理：万物皆 Unit，「对象」即带独立 Profile 的实例。

类/对象思想落地：
- **类（template）**：开发者侧的通用定义（manifest + 节点图），不进市场。
- **对象（instance）**：用户/市场下载后 *new* 出来的运行体，自带一套隔离的
  Profile（配置 / 状态 / 记忆 / 会话 / 凭证）。本模块管「对象」的隔离目录。

每个 Profile 目录结构（懒创建）：
    <home>/<profile_name>/
        config/      # 该对象私有配置（.env / settings.yaml）
        state/       # 运行态（开关、进度）
        memory/      # 记忆存储
        sessions/    # 会话历史
        credentials/ # 凭证（API key 等环境项）

团队本身也是一个对象，额外持有一层 Profile 承载其协作规则。
"""
from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path

from .exceptions import ProfileError

_DEFAULT = "default"

_SUBDIRS = ("config", "state", "memory", "sessions", "credentials")


class ProfileManager:
    """对象实例的隔离 HOME 管理（文件系统级隔离）。"""

    def __init__(self, base: str | Path | None = None) -> None:
        if base is None:
            root = os.getenv("PYPEDIA_DATA", os.path.join(os.path.expanduser("~"), ".pypedia"))
            base = Path(root) / "profiles"
        self.base = Path(base)
        self._lock = threading.RLock()
        self._current = _DEFAULT
        self.base.mkdir(parents=True, exist_ok=True)
        if not (self.base / _DEFAULT).exists():
            self.create_profile(_DEFAULT)

    # —— CRUD —— #
    def create_profile(self, name: str) -> Path:
        if not name or "/" in name or name in (".", ".."):
            raise ProfileError(f"非法 profile 名: {name}")
        path = self.base / name
        if path.exists():
            raise ProfileError(f"profile 已存在: {name}")
        with self._lock:
            path.mkdir(parents=True, exist_ok=True)
            for sub in _SUBDIRS:
                (path / sub).mkdir(exist_ok=True)
        return path

    def delete_profile(self, name: str) -> None:
        if name == _DEFAULT:
            raise ProfileError("默认 profile 不可删除")
        path = self.base / name
        if not path.exists():
            raise ProfileError(f"profile 不存在: {name}")
        with self._lock:
            shutil.rmtree(path, ignore_errors=False)

    def get_profile_path(self, name: str | None = None) -> Path:
        name = name or self._current
        path = self.base / name
        if not path.exists():
            raise ProfileError(f"profile 不存在: {name}")
        return path

    def list_profiles(self) -> list[str]:
        return sorted(
            p.name for p in self.base.iterdir()
            if p.is_dir() and not p.name.startswith(".")
        )

    # —— 切换 —— #
    def switch(self, name: str) -> Path:
        if not (self.base / name).exists():
            raise ProfileError(f"profile 不存在: {name}")
        self._current = name
        return self.get_profile_path(name)

    @property
    def current(self) -> str:
        return self._current

    def config_path(self, name: str | None = None) -> Path:
        return self.get_profile_path(name) / "config"

    def state_path(self, name: str | None = None) -> Path:
        return self.get_profile_path(name) / "state"

    def memory_path(self, name: str | None = None) -> Path:
        return self.get_profile_path(name) / "memory"

    def sessions_path(self, name: str | None = None) -> Path:
        return self.get_profile_path(name) / "sessions"

    def credentials_path(self, name: str | None = None) -> Path:
        return self.get_profile_path(name) / "credentials"
