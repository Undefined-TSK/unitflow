"""hello-world 示例插件：演示 Unit 契约的最小可运行实现。

契约（P0 冻结，详见 docs/UNIT_SCHEMA.md）：
- ``load(ctx)``           : 注册贡献点（tools / sections / ui ...）
- ``unload()``            : 清理
- ``contributions.tools`` 指向的入口返回 ``(tools, disposer)``，disposer 在卸载时逆序执行

本文件自带一个极简 ``ctx`` 桩，可直接 ``python plugin.py`` 跑通演示，
不依赖平台内核（内核在 P1 才接入）。真实装载时 ctx 由 UnitLoader 注入。
"""
from __future__ import annotations

import sys
from typing import Callable


# ---- 极简 ctx 桩（仅示例用；真实环境由 UnitLoader 提供）----
class _DemoCtx:
    """示例上下文：真实平台的 UnitLoader 会提供功能更完整的等价接口。"""

    def __init__(self) -> None:
        self.tools: dict[str, Callable] = {}
        self.sections: list[dict] = []

    def register_tool(self, name: str, handler: Callable, description: str) -> None:
        self.tools[name] = handler
        print(f"[ctx] 注册工具: {name} - {description}")

    def register_section(self, name: str, order: int, text: str) -> None:
        self.sections.append({"name": name, "order": order, "text": text})
        print(f"[ctx] 注册提示词段: {name} (order={order})")


def _hello_world(name: str = "world") -> str:
    """向用户问好（示例工具）。"""
    return f"Hello, {name}! 来自 hello-world 插件。"


def _tool_specs() -> list[dict]:
    """工具描述符（无 ctx，供内核/图引擎解析 handler）。"""
    return [{"name": "hello_world", "description": "示例：向用户问好", "handler": _hello_world}]


def list_tools() -> list[dict]:
    """contributions.tools 入口：返回工具清单，无需运行时 ctx。"""
    return _tool_specs()


def register_tools(ctx) -> tuple[list, Callable]:
    """生命周期入口：把工具注册进实时 ctx，返回 ``(工具清单, disposer)``。"""
    for spec in _tool_specs():
        ctx.register_tool(spec["name"], spec["handler"], spec["description"])
    tools = _tool_specs()

    def disposer() -> None:
        ctx.tools.pop("hello_world", None)
        print("[disposer] 已移除 hello_world 工具")

    return tools, disposer


def load(ctx) -> None:
    """生命周期：注册贡献点。"""
    register_tools(ctx)
    ctx.register_section(
        "hello-world:guide", 90, "你可以用 hello_world 工具向用户问好。"
    )


def unload() -> None:
    """生命周期：清理（disposer 由 UnitLoader 逆序调用）。"""
    print("[unload] hello-world 已卸载")


if __name__ == "__main__":
    ctx = _DemoCtx()
    load(ctx)
    print("调用工具:", _hello_world("PyPedia"))
    unload()
