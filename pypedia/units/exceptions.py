"""Unit 内核统一异常。

所有内核抛出的错误都继承自 :class:`UnitError`，便于调用方统一捕获。
设计原则：不吞异常、不静默失败；具体异常类型让调用方精确处理。
"""
from __future__ import annotations


class UnitError(Exception):
    """Unit 内核所有错误的基类。"""


class ManifestError(UnitError):
    """manifest（plugin.json）解析/校验失败。"""


class RegistryError(UnitError):
    """注册表操作失败（重复注册、未知 id、空壳拒绝等）。"""


class ProfileError(UnitError):
    """Profile（对象实例隔离目录）操作失败。"""


class LoaderError(UnitError):
    """Unit 装载 / 安装 / 卸载失败。"""


class GraphError(UnitError):
    """节点图执行（图即引擎）失败：入口缺失、环未终止、节点执行异常等。"""


class EditorError(UnitError):
    """节点编辑器（P7）导出失败：图校验未过、meta 非法、manifest 不达契约。"""
