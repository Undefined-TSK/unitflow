"""插件系统：manifest 登记 + 注册表（启停态 / 门控 / agent 工具汇总）。

边界（刻意设计）：
- 本包只依赖 config / logging / manifest，**不 import engine/agent**——
  工具列表在 registry.enabled_agent_tools() 内用 importlib 懒加载，
  防 agent/__init__ → build → registry → agent 循环 import；
- LLM/agent 框架本体（pypedia/agent/{bailian_model,transport}.py、pypedia/llm/、
  pypedia/models/）不是插件——发动机零件，见 manifests 模块 docstring。

用法：
    from pypedia.plugins import plugin_registry
    if plugin_registry.is_enabled("agent-memory"):
        ...
"""
from __future__ import annotations

from .manifests import BUILTIN_PLUGINS, Plugin, describe, get_manifest
from .registry import PluginRegistry, plugin_registry

__all__ = [
    "BUILTIN_PLUGINS",
    "Plugin",
    "PluginRegistry",
    "describe",
    "get_manifest",
    "plugin_registry",
]
