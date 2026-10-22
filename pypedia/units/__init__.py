"""Unit 内核：万物皆插件 / 万物皆对象 的统一底座。

对外暴露：
- :class:`Manifest`            ：契约（plugin.json）解析
- :class:`UnitRegistry`        ：启停态 + 门控 + 工具汇总（单例 ``unit_registry``）
- :class:`ProfileManager`      ：对象实例隔离 HOME
- :class:`UnitLoader`          ：扫描 / 安装 / 卸载
- :class:`GraphRuntime`        ：图即引擎（节点图直接执行）
"""
from __future__ import annotations

from .exceptions import (
    EditorError,
    GraphError,
    LoaderError,
    ManifestError,
    ProfileError,
    RegistryError,
    UnitError,
)
from .manifest import Manifest
from .registry import UnitRegistry, unit_registry
from .profile import ProfileManager
from .loader import UnitLoader
from .graph import GraphRuntime
from .editor import (
    export_unit,
    graph_to_manifest,
    manifest_to_zip,
    validate_graph,
)

__all__ = [
    "Manifest", "UnitRegistry", "unit_registry", "ProfileManager",
    "UnitLoader", "GraphRuntime",
    "UnitError", "ManifestError", "RegistryError",
    "ProfileError", "LoaderError", "GraphError", "EditorError",
    "validate_graph", "graph_to_manifest", "manifest_to_zip", "export_unit",
]
