"""python-encyclopedia 单 Agent 成品对象：图即引擎的引擎支撑处理器。

本模块把 PyPedia 的**确定性编排管线**拆成图节点可调用的处理器
（与 plugin.json 的 ``node_graph`` 一一对应），让「图就是引擎」真正落地——
管线由图驱动，而不是 ``engine.ask`` 内部黑盒：

    entry → 截断 → 级联检索 → 长上下文压缩 → MCP 分步 → 构造提示词
         → 生成(LLM, model-call) → 置信度 → 二审分支(judge)
         → 记忆沉淀 → 自进化 → 出口

设计要点：
- 每个处理器都是纯函数 ``(payload, data) -> dict``，读取上游节点结果（``data[node_id]``）
  并把自身产物并入返回 dict，下游节点据此取用——单 payload 沿边流动 +
  累积 data 字典（见 pypedia/units/graph.py 说明）；
- 生成这一步是 ``model-call`` 节点（不是这里），本模块的 ``_engine_executor``
  是其生产默认实现：用图里检索到的证据 + ``engine.generate`` 出答案；
- 引擎重型依赖**延迟导入**（函数内），避免模块加载即拉起重型组件；
  测试环境下由 conftest 打桩，导入本模块零副作用。
"""
from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

_HERE = pathlib.Path(__file__).resolve().parent
_MANIFEST = json.loads((_HERE / "plugin.json").read_text(encoding="utf-8"))
NODE_GRAPH = _MANIFEST["node_graph"]


def _cascade_chunks(cascade: Any, n: int = 5) -> list[Any]:
    if cascade is None:
        return []
    return list(getattr(cascade, "all_chunks", []) or [])[:n]


# —— 图节点处理器（引擎支撑） —— #
def retrieve(payload: dict, data: dict) -> dict:
    """级联 RAG 检索：把 query 喂给 CascadeRetriever，产物并入 data。"""
    from pypedia.engine import get_engine
    from pypedia.plugins import plugin_registry

    query = payload["query"] if isinstance(payload, dict) else str(payload)
    level = payload.get("level", 3) if isinstance(payload, dict) else 3
    cascade = get_engine().retriever.retrieve(query, history=[])
    return {
        "query": query, "level": level, "cascade": cascade,
        "review_enabled": plugin_registry.is_enabled("review"),
    }


def compress(payload: dict, data: dict) -> dict:
    """长上下文压缩：Session 挂载 ConversationContext，token 预算内保留/滑窗/摘要。"""
    from pypedia.memory import Session

    level = payload.get("level", 3) if isinstance(payload, dict) else 3
    session = Session(level=level)
    ctx_plan = session.context.plan(session.turns)
    return {**payload, "ctx_plan": ctx_plan}


def reason(payload: dict, data: dict) -> dict:
    """MCP 分步推理：复杂问题拆成有序步骤（失败静默跳过）。"""
    from pypedia.engine import get_engine

    query = payload["query"] if isinstance(payload, dict) else str(payload)
    try:
        plan = get_engine()._reasoning_plan(query)
    except Exception:  # noqa: BLE001 —— 推理是增强项，失败不影响主流程
        plan = ""
    return {**payload, "plan": plan}


def build_prompt(payload: dict, data: dict) -> dict:
    """构造提示词：等级系统提示词 + 检索证据 + 压缩前情 + 分步思路。

    刻意不调用引擎私有 ``_build_prompt``，改用图节点已算出的公开数据自组，
    保证节点间数据契约稳定、可被编辑器可视化。
    """
    query = payload["query"] if isinstance(payload, dict) else str(payload)
    cascade = payload.get("cascade")
    evidence = "\n".join(f"- {getattr(c, 'text', '')}" for c in _cascade_chunks(cascade))
    system = (
        "你是 PyPedia，专业的 Python 百科助手。请严格基于提供的检索证据作答，"
        "不确定的内容明确标注；代码示例用 ```python 代码块，必要时附 mermaid 图 / "
        "表格 / KaTeX 公式，方便前端渲染复核。"
    )
    prompt = (
        f"问题：{query}\n\n"
        f"检索证据：\n{evidence or '（无检索命中，凭模型知识作答并说明局限）'}\n\n"
        "请给出准确、可执行的解答。"
    )
    return {**payload, "system": system, "prompt": prompt}


def confidence(payload: dict, data: dict) -> dict:
    """置信度评估：基于检索证据 + 实际回答，由评估模型打分；并算出是否需二审。"""
    answer = payload.get("answer", "") if isinstance(payload, dict) else ""
    query = (data.get("t") or {}).get("query", "")
    cascade = (data.get("r") or {}).get("cascade")
    evidence = [getattr(c, "text", "") for c in _cascade_chunks(cascade)]
    try:
        from pypedia.models.dashscope import evaluate_confidence

        conf = evaluate_confidence(query, answer, evidence)
    except Exception:  # noqa: BLE001 —— import/评估失败统一降级，与旧架构
        # ``evaluate_confidence`` 内部降级（score=55）同值，保证两条链路
        # 置信度语义一致（真实测试①曾逼出此处 import 路径写错 + 降级分
        # 50≠55 两处偏差）。
        conf = {"score": 55, "level": "低", "reason": "置信度评估跳过"}
    review_enabled = (data.get("r") or {}).get("review_enabled", False)
    needs_review = bool(review_enabled) and conf.get("score", 100) < 0.6
    return {**payload, "conf": conf, "review_enabled": review_enabled,
            "needs_review": needs_review}


def review(payload: dict, data: dict) -> dict:
    """答案二审（双模型交叉审阅，A2A 轻量替代；跳过不影响主流程）。"""
    from pypedia.review import review_answer

    answer = payload.get("answer", "") if isinstance(payload, dict) else ""
    query = (data.get("t") or {}).get("query", "")
    cascade = (data.get("r") or {}).get("cascade")
    evidence = [getattr(c, "text", "") for c in _cascade_chunks(cascade)]
    try:
        verdict = review_answer(query, answer, evidence)
    except Exception:  # noqa: BLE001
        verdict = {"verdict": "pass", "notes": ["二审跳过"], "revised": "", "skipped": True}
    return {**payload, "review": verdict}


def remember(payload: dict, data: dict) -> dict:
    """记忆沉淀：会话内多轮 + 跨会话画像（Mem0）。"""
    from pypedia.engine import get_engine
    from pypedia.memory import Session

    answer = payload.get("answer", "") if isinstance(payload, dict) else ""
    t = data.get("t") or {}
    query = t.get("query", "")
    level = t.get("level", 3)
    conf = (data.get("k") or {}).get("conf", {})
    cascade = (data.get("r") or {}).get("cascade")
    primary_title = ""
    if cascade is not None:
        primary = getattr(cascade, "primary", []) or []
        primary_title = primary[0].title if primary else ""
    session = Session(level=level)
    try:
        session.add(query, answer, conf.get("score", 0), primary_title)
        get_engine().memory.observe(query, level, conf.get("score", 0), answer)
    except Exception:  # noqa: BLE001 —— 记忆失败不影响答案返回
        pass
    return {**payload, "memory_ok": True}


def evolve(payload: dict, data: dict) -> dict:
    """自进化：反思 + 技能沉淀（冻结权重，只进化 prompt/记忆层）。"""
    from pypedia.engine import get_engine

    answer = payload.get("answer", "") if isinstance(payload, dict) else ""
    t = data.get("t") or {}
    query = t.get("query", "")
    level = t.get("level", 3)
    conf = (data.get("k") or {}).get("conf", {})
    cascade = (data.get("r") or {}).get("cascade")
    has_primary = bool(cascade and getattr(cascade, "primary", []))
    try:
        get_engine().evolution.observe(query, answer, conf.get("score", 0),
                                       has_primary, level)
    except Exception:  # noqa: BLE001
        pass
    return {**payload, "evo_ok": True}


# —— 贡献点入口（供内核 / 图引擎解析 handler） —— #
def list_tools() -> list[dict]:
    return [
        {"name": "retrieve", "description": "级联 RAG 检索", "handler": retrieve},
        {"name": "compress", "description": "长上下文压缩", "handler": compress},
        {"name": "reason", "description": "MCP 分步推理", "handler": reason},
        {"name": "build_prompt", "description": "构造提示词", "handler": build_prompt},
        {"name": "confidence", "description": "置信度评估", "handler": confidence},
        {"name": "review", "description": "答案二审", "handler": review},
        {"name": "remember", "description": "记忆沉淀", "handler": remember},
        {"name": "evolve", "description": "自进化", "handler": evolve},
    ]


# —— 生产默认 model-call 执行器：用图里检索到的证据 + 引擎生成 —— #
def _engine_executor(prompt: Any, data: dict, tools: list, memory: Any = None,
                     **params: Any) -> dict:
    from pypedia.engine import get_engine

    b = data.get("b") or {}
    system = b.get("system")
    user_prompt = b.get("prompt") or (prompt if isinstance(prompt, str) else str(prompt))
    level = b.get("level", 3)
    answer = get_engine().generate(user_prompt, system=system, level=level)
    base = prompt if isinstance(prompt, dict) else {}
    return {**base, "answer": answer}


def run(query: str, level: int = 3, model_executor: Any = None,
        env_resolver: Any = None) -> dict:
    """图即引擎入口：用 GraphRuntime 执行本成品对象的 node_graph。

    - ``model_executor`` 不传时默认为 ``_engine_executor``（生产：引擎生成）；
      测试 / 特殊装配可传入 mock executor（如 MockLLM）绕过真实 LLM。
    - 返回图的 ``result``（出口节点捕获的 dict）。
    """
    if str(_HERE) not in sys.path:
        sys.path.insert(0, str(_HERE))
    from pypedia.units import GraphRuntime, Manifest, UnitRegistry

    reg = UnitRegistry(env_resolver=env_resolver)
    reg.register(Manifest.from_dict(_MANIFEST))
    rt = GraphRuntime(reg, model_executor=model_executor or _engine_executor)
    res = rt.execute(NODE_GRAPH, input_data={"query": query, "level": level})
    return res["result"]
