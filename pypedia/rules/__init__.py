"""P5 规则引擎包：能力激活的确定性路由（master plan §6）。

公开面：
- :class:`RuleEngine` —— 规则求值器（无状态、可重放、可第三方替换）；
- :class:`Rule` / :class:`Decision` —— 规则与求值结果的数据形状；
- :class:`RuleError` —— 规则数据非法（构造期校验，防静默失效）。
"""
from .engine import Decision, Rule, RuleEngine, RuleError

__all__ = ["Decision", "Rule", "RuleEngine", "RuleError"]
