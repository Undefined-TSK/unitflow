"""P7 节点编辑器 v1：图校验 + 序列化导出（「画一张图 → 可运行 unit」）。

定位（master plan §11(P7) / D1）：编辑器是「图即引擎」的**编排创作面**——
用户在画布上编排节点图，导出为标准 unit 包（与市场上传同格式），经市场
安装后由 ``GraphRuntime`` 解释执行。本模块是画布的后端支柱：

- :func:`validate_graph`：结构校验（不执行）——节点/边形状、类型别名、
  entry/exit 约束、边引用完整性、judge condition 与 process expr 的
  **语法可编译**（防打字 bug 画出一张跑不起来的图）；
- :func:`graph_to_manifest`：画布数据 + 元信息 → 完整 unit manifest 字典；
- :func:`manifest_to_zip`：打成可被 ``MarketStore.parse_upload`` 直接
  消费的 zip（plugin.json + 资源），「导出即上架格式」。

安全边界：condition / expr 是**开发者编写**的表达式（与插件代码同信任级，
见 graph.py 模块注释）；本模块只做语法级校验（compile），不执行、
不求值。安装走市场同一通道（schema + 版本门禁 + 落盘前校验）。
"""
from __future__ import annotations

import io
import json
import zipfile
from typing import Any

from .exceptions import EditorError
from .graph import _norm_type
from .manifest import Manifest

# 画布可见节点类型（规范用语；内核别名在 graph.py 归一）
NODE_TYPES: tuple[str, ...] = (
    "entry", "exit", "process", "plugin", "model-call", "judge",
)
# 每种节点在画布上的可编辑参数键（editor.js 属性面板同源）
NODE_PARAM_HINTS: dict[str, tuple[str, ...]] = {
    "entry": (),
    "exit": (),
    "process": ("expr", "ref", "method"),
    "plugin": ("ref", "method"),
    "model-call": ("identity",),
    "judge": (),
}


def validate_graph(graph: Any, *, registry: Any | None = None) -> list[str]:
    """校验节点图结构，返回错误列表（空 = 通过；不执行、不求值）。"""
    errors: list[str] = []
    if not isinstance(graph, dict):
        return ["图必须是对象（含 nodes/edges）"]
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not nodes:
        errors.append("nodes 必须是非空数组")
        nodes = []
    if edges is None:
        edges = []
    if not isinstance(edges, list):
        errors.append("edges 必须是数组")
        edges = []

    seen: set[str] = set()
    has_entry = False
    has_exit = False
    for i, n in enumerate(nodes):
        if not isinstance(n, dict):
            errors.append(f"nodes[{i}] 必须是对象")
            continue
        nid = n.get("id")
        if not nid or not isinstance(nid, str):
            errors.append(f"nodes[{i}] 缺少字符串 id")
            continue
        if nid in seen:
            errors.append(f"节点 id 重复：{nid}")
        seen.add(nid)
        ntype = n.get("type")
        if ntype not in NODE_TYPES:
            errors.append(
                f"节点 {nid} 类型非法：{ntype!r}（可选 {list(NODE_TYPES)}）")
            continue
        if _norm_type(ntype) == "input":
            has_entry = True
        if _norm_type(ntype) == "output":
            has_exit = True
        errors.extend(_validate_node_params(nid, n, registry))
    if not has_entry:
        errors.append("图缺少 entry 入口节点")
    if not has_exit:
        errors.append("图建议包含 exit 出口节点（否则以末节点结果终止）")

    for i, e in enumerate(edges):
        if not isinstance(e, dict):
            errors.append(f"edges[{i}] 必须是对象")
            continue
        src, dst = e.get("from"), e.get("to")
        if src not in seen:
            errors.append(f"edges[{i}] 的 from 不存在：{src!r}")
        if dst not in seen:
            errors.append(f"edges[{i}] 的 to 不存在：{dst!r}")
        if src == dst and src in seen:
            errors.append(f"edges[{i}] 是自环：{src}")
        cond = e.get("condition")
        if cond:
            if not isinstance(cond, str):
                errors.append(f"edges[{i}] 的 condition 必须是字符串")
            else:
                errors.extend(_check_expr(cond, f"边 {src}->{dst} 的 condition"))
    return errors


def _validate_node_params(nid: str, node: dict[str, Any],
                          registry: Any | None) -> list[str]:
    """按类型校验参数：plugin 必须有 ref（registry 给了还查存在性）；
    process 必须有 expr 或 ref；表达式类字段做语法编译检查。

    ref 兼容两个位置：节点级 ``ref``（规范约定，示例图/导出图用）或
    ``params.ref``（画布直出形状）——与 GraphRuntime 的解析顺序一致。
    """
    errors: list[str] = []
    params = node.get("params") or {}
    if not isinstance(params, dict):
        return [f"节点 {nid} 的 params 必须是对象"]
    ntype = _norm_type(node["type"])
    ref = node.get("ref") or params.get("ref")
    if ntype == "plugin":
        if not ref:
            errors.append(
                f"plugin 节点 {nid} 缺少 ref（节点级或 params.ref：引用的 unit id）")
        elif registry is not None and registry.get_unit(ref) is None:
            errors.append(f"plugin 节点 {nid} 引用的 unit 未注册：{ref}")
    if ntype == "process" and not params.get("expr") and not ref:
        errors.append(f"process 节点 {nid} 需要 params.expr 或 ref")
    expr = params.get("expr")
    if expr:
        if not isinstance(expr, str):
            errors.append(f"节点 {nid} 的 params.expr 必须是字符串")
        else:
            errors.extend(_check_expr(expr, f"节点 {nid} 的 expr"))
    return errors


def _check_expr(expr: str, where: str) -> list[str]:
    """表达式语法编译检查（不执行）——防画出一张跑不起来的图。"""
    try:
        compile(expr, "<editor>", "eval")
    except SyntaxError as exc:
        return [f"{where} 不是合法 Python 表达式：{exc.msg}（{expr!r}）"]
    return []


def _normalize_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """导出前归一（幂等）：把 ``params.ref`` 提升为节点级 ``ref``（运行时
    规范约定），并剥掉画布坐标 ``x/y``（纯编辑器状态，非图语义）。

    两种 ref 形状运行时都认（见 graph.py），但导出的 zip 只保留规范
    形状——人读、版本 diff、再导入编辑器都不迷路。
    """
    nodes: list[dict[str, Any]] = []
    for n in graph.get("nodes", []):
        if not isinstance(n, dict):
            nodes.append(n)
            continue
        n = {k: v for k, v in n.items() if k not in ("x", "y")}
        params = dict(n.get("params") or {})
        ref = params.pop("ref", None)
        if ref and not n.get("ref"):
            n["ref"] = ref
        if params:
            n["params"] = params
        else:
            n.pop("params", None)
        nodes.append(n)
    out = dict(graph)
    out["nodes"] = nodes
    return out


def graph_to_manifest(graph: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    """画布图 + 元信息 → unit manifest 字典（随后可 schema 校验 / 打包）。

    ``meta``：id / name / type / form / version / description 等
    （缺省给保守默认值；id 必填——它是安装与引用的主键）。
    """
    uid = str(meta.get("id") or "").strip()
    if not uid:
        raise EditorError("导出失败：unit id 不能为空")
    utype = meta.get("type") or "agent"
    if utype not in ("plugin", "agent", "team"):
        raise EditorError(f"导出失败：type 非法：{utype!r}")
    graph = _normalize_graph(graph)
    manifest: dict[str, Any] = {
        "id": uid,
        "type": utype,
        "name": str(meta.get("name") or uid),
        "version": str(meta.get("version") or "0.1.0"),
        "description": str(meta.get("description") or "由节点编辑器导出"),
        "min_platform": str(meta.get("min_platform") or "0.2.0"),
        "dependencies": meta.get("dependencies") or [],
        "default_enabled": True,
        "switchable": True,
        "env_gate": "",
        "apply": "immediate",
        "form": meta.get("form") or "instance",
        "node_graph": graph,
    }
    if utype == "agent":
        manifest["agent_def"] = meta.get("agent_def") or {"identity": "①"}
    if utype == "team":
        # schema 要求 members + graph（members 引用的 agent id 列表，
        # 画布上先给空表，用户在 meta.team_def 里补真实成员）
        manifest["team_def"] = meta.get("team_def") or {
            "members": [], "graph": graph}
    return manifest


def manifest_to_zip(manifest: dict[str, Any],
                    resources: dict[str, str] | None = None) -> bytes:
    """manifest + 资源 → zip 字节（与市场上传格式一致：根 plugin.json）。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("plugin.json",
                    json.dumps(manifest, ensure_ascii=False, indent=2))
        for rel, text in (resources or {}).items():
            zf.writestr(rel, text)
    return buf.getvalue()


def export_unit(graph: dict[str, Any], meta: dict[str, Any],
                *, resources: dict[str, str] | None = None) -> tuple[bytes, str]:
    """校验 → 组 manifest → schema 复检 → 打 zip。返回 (zip 字节, 建议文件名)。"""
    errors = validate_graph(graph)
    if errors:
        raise EditorError("图校验未通过：" + "；".join(errors))
    manifest = graph_to_manifest(graph, meta)
    try:
        Manifest.from_dict(manifest)  # schema 复检：与市场安装同一裁判
    except Exception as exc:  # ManifestError 及其包装
        raise EditorError(f"导出的 manifest 不满足契约：{exc}") from exc
    return manifest_to_zip(manifest, resources), f"{manifest['id']}.zip"


def minimal_graph() -> dict[str, Any]:
    """最小可运行模板：entry → process(表达式) → exit（编辑器「新建」用）。"""
    return {
        "nodes": [
            {"id": "e", "type": "entry"},
            {"id": "p", "type": "process",
             "params": {"expr": "{'echo': payload}"}},
            {"id": "x", "type": "exit"},
        ],
        "edges": [{"from": "e", "to": "p"}, {"from": "p", "to": "x"}],
    }


def encyclopedia_graph() -> dict[str, Any] | None:
    """单 Agent 成品模板：python-encyclopedia 的 13 节点图（装了才有）。"""
    from .registry import unit_registry

    unit = unit_registry.get_unit("python-encyclopedia")
    return dict(unit.node_graph) if unit and unit.node_graph else None
