"""GraphRuntime：图即引擎（图本身就是运行时，不编译成别的配置）。

节点类型（与 units/schema/unit.schema.json 的 ``node_graph`` 及说明书 §5.13 对齐）：
- ``input`` / ``entry``  ：入口，注入初始数据（payload）
- ``output`` / ``exit``   ：出口，捕获结果并终止
- ``plugin``             ：引用一个 unit（ref=unit id），调用其主工具（可用 params.method 指定具体工具）
- ``model-call`` / ``llm``：调用 LLM（model_executor），注入当前可见工具
- ``judge``              ：不改数据，仅按出边 ``condition`` 选择分支（控制流）
- ``process``            ：纯处理节点，执行 ``params.expr``（受限求值）或 ``ref``+``method`` 处理器

边（edges）：``from -> to``；judge 节点的出边带 ``condition``（Python 布尔表达式，
命名空间含 ``payload`` 与 ``data``）。顺序边忽略 condition。规范 §6 的 ``kind/data/
control`` + 类型化插座是 P7 的完整表达，本运行时（P3）采用**单 payload 沿边流动 +
累积 data 字典**的简化但等价的模型（judge 分支 + 边回指实现循环）——这是「图就是
引擎、引擎就是图」的可执行最小闭环。

安全边界：condition / process.expr 由开发者编写（与插件代码同信任级），内核用
受限 ``__builtins__`` 求值，不接受不可信外部输入。
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable

from .exceptions import GraphError
from .registry import UnitRegistry

# 节点类型别名：规范用语 → 内核用语（保持 P1 旧图 ``input`` 等仍可跑）
_NODE_ALIASES = {
    "entry": "input",
    "exit": "output",
    "llm": "model-call",
}


def _norm_type(ntype: str) -> str:
    return _NODE_ALIASES.get(ntype, ntype)


# 受限求值命名空间：仅暴露无害的内置（绝不含 eval/exec/open/__import__ 等），
# 供 judge.condition 与 process.expr 编写表达式——开发者信任级，不接受外部不可信输入。
_SAFE_BUILTINS = {
    "isinstance": isinstance, "len": len, "str": str, "int": int, "float": float,
    "bool": bool, "dict": dict, "list": list, "tuple": tuple, "set": set,
    "getattr": getattr, "hasattr": hasattr, "min": min, "max": max,
    "any": any, "all": all, "abs": abs, "sum": sum, "sorted": sorted,
    "enumerate": enumerate, "zip": zip, "range": range,
}


class GraphRuntime:
    """解释执行节点图（图即引擎）。"""

    def __init__(
        self,
        registry: UnitRegistry,
        model_executor: Callable[..., Any] | None = None,
        memory: Any | None = None,
    ) -> None:
        self.registry = registry
        self.model_executor = model_executor
        self.memory = memory

    # —— 主入口 —— #
    def execute(
        self,
        graph: dict[str, Any],
        input_data: Any = None,
        max_steps: int = 1000,
    ) -> dict[str, Any]:
        nodes = {n["id"]: n for n in graph.get("nodes", [])}
        edges = graph.get("edges", [])
        if not nodes:
            raise GraphError("图没有任何节点")

        outgoing: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for e in edges:
            outgoing[e["from"]].append(e)

        entry = next((n for n in graph["nodes"] if _norm_type(n["type"]) == "input"), None)
        if entry is None:
            raise GraphError("图缺少 input/entry 入口节点")

        data: dict[str, Any] = {}
        payload = input_data
        current = entry["id"]
        steps = 0
        final: Any = None
        outputs: dict[str, Any] = {}

        while True:
            steps += 1
            if steps > max_steps:
                raise GraphError("超出最大步数，疑似未终止环")
            node = nodes.get(current)
            if node is None:
                raise GraphError(f"节点不存在: {current}")

            ntype = _norm_type(node["type"])
            if ntype == "input":
                out = payload
            elif ntype == "output":
                outputs[current] = payload
                final = payload
                break
            elif ntype == "plugin":
                out = self._run_plugin(node, payload, data)
            elif ntype == "model-call":
                out = self._run_model(node, payload, data)
            elif ntype == "process":
                out = self._run_process(node, payload, data)
            elif ntype == "judge":
                out = payload  # judge 只选边，不改数据
            else:
                raise GraphError(f"未知节点类型: {ntype}")

            data[current] = out
            payload = out

            edges_out = outgoing.get(current, [])
            if not edges_out:
                if ntype != "output":
                    final = payload
                break
            nxt = self._select_edge(ntype, edges_out, payload, data)
            if nxt is None:
                final = payload
                break
            current = nxt

        return {"result": final, "outputs": outputs, "data": data}

    # —— 边选择 —— #
    def _select_edge(
        self,
        ntype: str,
        edges_out: list[dict[str, Any]],
        payload: Any,
        data: dict[str, Any],
    ) -> str | None:
        if ntype == "judge":  # 控制流：按 condition 选分支
            matched: list[dict[str, Any]] = []
            fallback: dict[str, Any] | None = None
            for e in edges_out:
                cond = e.get("condition")
                if not cond:
                    fallback = e
                    continue
                if self._eval_condition(cond, payload, data):
                    matched.append(e)
            if matched:
                return matched[0]["to"]
            if fallback is not None:
                return fallback["to"]
            return edges_out[0]["to"]  # 兜底：第一条
        # 顺序边：取第一条
        return edges_out[0]["to"]

    @staticmethod
    def _eval_condition(cond: str, payload: Any, data: dict[str, Any]) -> bool:
        if not cond:
            return True
        namespace = {"payload": payload, "data": data}
        try:
            return bool(eval(cond, {"__builtins__": _SAFE_BUILTINS}, namespace))  # noqa: S307
        except Exception as exc:
            raise GraphError(f"condition 求值失败 ({cond}): {exc}") from exc

    # —— 节点执行 —— #
    @staticmethod
    def _call_handler(handler: Callable, payload: Any, data: dict[str, Any],
                      params: dict[str, Any]) -> Any:
        """以「最兼容」方式调用节点处理器：优先带 data，逐级退化到旧签名。

        兼容三层：``handler(payload, data=..., **params)`` →
        ``handler(payload, **params)`` → ``handler(payload)``，覆盖 P1 简单处理器
        与需要读取上游累积 data 的管线处理器。
        """
        try:
            return handler(payload, data=data, **params)
        except TypeError:
            try:
                return handler(payload, **params)
            except TypeError:
                return handler(payload)

    def _resolve_unit_tools(self, ref: str) -> list[Any]:
        """取该 unit 声明的**全部工具描述符**（打平成一级列表）。"""
        unit = self.registry.get_unit(ref)
        if unit is None:
            raise GraphError(f"plugin 节点引用的 unit 未注册: {ref}")
        tools_entries = unit.contributions.get("tools", [])
        if not tools_entries:
            raise GraphError(f"unit {ref} 未声明 tools 贡献点")
        flat: list[Any] = []
        for entry in tools_entries:
            resolved = self.registry._resolve_tool_entry(entry)
            flat.extend(resolved.get("tools", []))
        return flat

    @staticmethod
    def _pick_tool(flat_tools: list[Any], method: str | None) -> Any:
        """按 params.method 选具体工具描述符（按 name 匹配），未命中回退首个。"""
        if method:
            for t in flat_tools:
                name = getattr(t, "__name__", None) or getattr(t, "func_name", None) \
                    or (t.get("name") if isinstance(t, dict) else None)
                if name == method:
                    return t
        return flat_tools[0]

    def _run_plugin(self, node: dict[str, Any], payload: Any, data: dict[str, Any]) -> Any:
        # ref 兼容两个位置：节点级（规范约定，示例图/导出图用）或 params.ref
        # （画布直出形状）——以节点级优先，两者缺一才报错。
        ref = node.get("ref") or (node.get("params") or {}).get("ref")
        if not ref:
            raise GraphError(f"plugin 节点缺少 ref: {node.get('id')}")
        flat = self._resolve_unit_tools(ref)
        tool = self._pick_tool(flat, node.get("params", {}).get("method"))
        # 工具描述符可能是字典（{"name","handler"}）或裸可调用对象
        handler = tool.get("handler") if isinstance(tool, dict) else tool
        if not callable(handler):
            raise GraphError(f"tool 缺少可调用 handler: {ref}")
        # method 是运行时选择器、ref 是引用键，均不作为处理器参数传入
        params = {k: v for k, v in (node.get("params") or {}).items()
                  if k not in ("method", "ref")}
        return self._call_handler(handler, payload, data, params)

    def _run_process(self, node: dict[str, Any], payload: Any, data: dict[str, Any]) -> Any:
        params = node.get("params") or {}
        ref = node.get("ref") or params.get("ref")
        if ref:  # process 也可引用 unit 处理器（与 plugin 等价，仅语义不同）
            return self._run_plugin(node, payload, data)
        expr = params.get("expr")
        if not expr:
            raise GraphError(f"process 节点缺少 expr 或 ref: {node.get('id')}")
        namespace: dict[str, Any] = {"payload": payload, "data": data}
        try:
            return eval(expr, {"__builtins__": _SAFE_BUILTINS}, namespace)  # noqa: S307
        except Exception as exc:
            raise GraphError(f"process.expr 求值失败 ({expr}): {exc}") from exc

    def _run_model(self, node: dict[str, Any], payload: Any, data: dict[str, Any]) -> Any:
        if self.model_executor is None:
            raise GraphError("图含 model-call/llm 节点，但未注入 model_executor")
        visible_tools = self.registry.enabled_tools()
        params = node.get("params") or {}
        try:
            return self.model_executor(
                prompt=payload, data=data, tools=visible_tools,
                memory=self.memory, **params,
            )
        except TypeError:
            # 兼容极简 executor(prompt, **kw)
            return self.model_executor(prompt=payload, tools=visible_tools, **params)
