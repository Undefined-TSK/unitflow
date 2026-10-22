"""内核测试用的演示插件（非发布件）：提供 echo / dec 两个纯函数工具。

仅用于 ``tests/test_units_kernel.py`` 验证图引擎的 plugin 节点与分支/循环逻辑，
不进入市场、不随分发。
"""
from __future__ import annotations


def echo(x: str) -> str:
    return f"echo:{x}"


def dec(x: int) -> int:
    return x - 1 if isinstance(x, int) else x


def echo_entry() -> list[dict]:
    return [{"name": "echo", "description": "回显输入", "handler": echo}]


def dec_entry() -> list[dict]:
    return [{"name": "dec", "description": "整数减一", "handler": dec}]
