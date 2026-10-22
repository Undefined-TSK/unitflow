"""Unit 装载器：扫描 / 安装 / 卸载。

职责：
- ``scan``    ：在目录树中递归发现 ``plugin.json``，校验后注册进 UnitRegistry；
- ``install`` ：把一个 unit 目录复制进「已安装目录」并注册（市场下载即此路径）；
- ``uninstall``：移除已安装目录并注销（卸载一个 unit 的全链路）。

与既有 ``plugins/registry.py`` 的关系：本装载器是「发现/安装」层，注册表是
「门控/查询」层；二者解耦，P3 再把 10 个既有插件迁移到本契约。
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Iterable

from .exceptions import LoaderError
from .manifest import Manifest
from .registry import UnitRegistry


def _add_to_sys_path(directory: Path) -> None:
    """把 unit 目录加入 sys.path 前端，使其 ``module:attr`` 入口可被 import。

    注意：top-level 模块名（如 ``plugin``）可能撞名，v1 接受此简化，
    后续可改为 importlib.util 按绝对路径加载（TODO）。
    """
    s = str(directory.resolve())
    if s not in sys.path:
        sys.path.insert(0, s)


class UnitLoader:
    """扫描与装卸 unit。"""

    def __init__(self, registry: UnitRegistry, installed_dir: str | Path | None = None) -> None:
        self.registry = registry
        self.installed_dir = Path(installed_dir) if installed_dir else None
        if self.installed_dir is not None:
            self.installed_dir.mkdir(parents=True, exist_ok=True)

    # —— 扫描 —— #
    def scan(self, directory: str | Path) -> list[Manifest]:
        """递归发现并注册目录下所有 plugin.json（按 id 去重）。"""
        root = Path(directory)
        if not root.exists():
            raise LoaderError(f"目录不存在: {root}")
        manifests: list[Manifest] = []
        for path in sorted(root.rglob("plugin.json")):
            try:
                manifest = Manifest.from_file(path)
            except LoaderError:
                raise
            except Exception as exc:  # 单个坏清单不应阻断整批扫描
                from .exceptions import ManifestError

                if isinstance(exc, ManifestError):
                    raise
                continue
            _add_to_sys_path(path.parent)
            self.registry.register(manifest)
            manifests.append(manifest)
        return manifests

    # —— 安装 / 卸载 —— #
    def install(self, unit_dir: str | Path) -> Manifest:
        """安装一个 unit 目录到已安装目录并注册。"""
        src = Path(unit_dir)
        manifest = Manifest.from_file(src / "plugin.json")
        if self.installed_dir is None:
            # 未配置已安装目录：仅注册（内存态），不做复制
            _add_to_sys_path(src)
            self.registry.register(manifest)
            return manifest
        dest = self.installed_dir / manifest.id
        if dest.exists():
            raise LoaderError(f"已安装目录已存在: {dest}")
        shutil.copytree(src, dest)
        _add_to_sys_path(dest)
        installed = Manifest.from_file(dest / "plugin.json")
        self.registry.register(installed)
        return installed

    def uninstall(self, unit_id: str) -> None:
        """卸载：删除已安装目录 + 注销。"""
        if self.installed_dir is not None:
            dest = self.installed_dir / unit_id
            if dest.exists():
                shutil.rmtree(dest, ignore_errors=False)
        self.registry.unregister(unit_id)

    # —— 依赖解析（安装前门禁）—— #
    def resolve_dependencies(self, manifest: Manifest, available: Iterable[str]) -> list[str]:
        """返回未满足的依赖 id 列表（空 = 满足）。"""
        available = set(available)
        missing: list[str] = []
        for dep in manifest.dependencies:
            dep_id = dep.get("id")
            if dep_id and dep_id not in available:
                missing.append(dep_id)
        return missing
