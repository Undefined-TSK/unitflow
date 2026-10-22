"""用户等级（精通 Python 的程度）：决定解释深度、术语密度与示例风格。"""

# 等级定义：n 档 -> 名称、画像、给模型的风格指令
LEVELS = {
    1: {
        "n": "L1", "t": "零基础", "d": "刚接触 Python，需要最通俗的比喻和完整前置",
        "style": "用生活中的比喻解释，避免术语；每一步都写清；先给能直接抄的运行示例，再说原理。",
    },
    2: {
        "n": "L2", "t": "入门", "d": "会写简单脚本，见过基础语法但不系统",
        "style": "用少量术语但立刻解释；示例短小可直接运行；点明常见坑。",
    },
    3: {
        "n": "L3", "t": "进阶", "d": "能独立开发，想理解机制与最佳实践",
        "style": "直接讲原理与权衡，适度使用术语；给出可运行示例 + 何时该用/不该用。",
    },
    4: {
        "n": "L4", "t": "熟练", "d": "熟悉生态，关注性能、边界与底层实现",
        "style": "聚焦机制、性能与边界情况；可用专业术语；对比不同实现的开销。",
    },
    5: {
        "n": "L5", "t": "专家", "d": "深入 CPython / 标准库实现层面",
        "style": "直击实现细节、CPython 行为与设计取舍；示例可含底层/源码级讨论，不啰嗦。",
    },
}


def ensure_level(level) -> int:
    try:
        level = int(level)
    except (TypeError, ValueError):
        level = 3
    return max(1, min(5, level))


def level_prompt(level) -> str:
    lv = LEVELS[ensure_level(level)]
    return (
        f"用户 Python 熟练度等级：{lv['n']}（{lv['t']}）。\n"
        f"解释风格要求：{lv['style']}"
    )


def level_meta(level) -> dict:
    lv = LEVELS[ensure_level(level)]
    return {"n": lv["n"], "t": lv["t"], "d": lv["d"]}
