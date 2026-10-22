"""P3 测试：python-encyclopedia 成品对象 = 图即引擎，零丢失封装 PyPedia。

验证：
1. 真实 manifest 合法且含 node_graph（入口/生成/判断/出口齐备 + 8 个引擎管线方法）；
2. 用与真实 manifest 完全相同的节点图 + mock 处理器 + MockLLM 执行器跑通端到端；
3. judge 分支正确：needs_review=True 走二审、False 跳过二审；
4. 十六项功能零丢失映射（图节点方法 + model-call 工具集 + 能力插件）覆盖全部能力。

不依赖真实引擎/LLM：处理器与执行器全部 mock，证明「图就是引擎」的运行时闭环正确。
"""
from __future__ import annotations

from pathlib import Path

from pypedia.units import GraphRuntime, Manifest, UnitRegistry

EXAMPLE = Path(__file__).resolve().parents[1] / "units" / "examples" / "python-encyclopedia"
MANIFEST_PATH = EXAMPLE / "plugin.json"


# —— 测试可控状态 —— #
_CALLS: list[str] = []
_NEEDS_REVIEW = {"flag": True}


class _MockCascade:
    all_chunks: list = []
    primary: list = []


def _mock_retrieve(payload, data):
    _CALLS.append("retrieve")
    return {"query": payload["query"], "level": payload.get("level", 3),
            "cascade": _MockCascade(), "review_enabled": True}


def _mock_compress(payload, data):
    _CALLS.append("compress")
    return {**payload, "ctx_plan": object()}


def _mock_reason(payload, data):
    _CALLS.append("reason")
    return {**payload, "plan": ""}


def _mock_build_prompt(payload, data):
    _CALLS.append("build_prompt")
    return {**payload, "system": "sys", "prompt": "prompt:" + payload["query"]}


def _mock_confidence(payload, data):
    _CALLS.append("confidence")
    score = 30 if _NEEDS_REVIEW["flag"] else 90
    return {**payload, "conf": {"score": score}, "review_enabled": True,
            "needs_review": bool(_NEEDS_REVIEW["flag"])}


def _mock_review(payload, data):
    _CALLS.append("review")
    return {**payload, "review": {"verdict": "pass"}}


def _mock_remember(payload, data):
    _CALLS.append("remember")
    return {**payload, "memory_ok": True}


def _mock_evolve(payload, data):
    _CALLS.append("evolve")
    return {**payload, "evo_ok": True}


def mock_tools():
    return [
        {"name": "retrieve", "description": "", "handler": _mock_retrieve},
        {"name": "compress", "description": "", "handler": _mock_compress},
        {"name": "reason", "description": "", "handler": _mock_reason},
        {"name": "build_prompt", "description": "", "handler": _mock_build_prompt},
        {"name": "confidence", "description": "", "handler": _mock_confidence},
        {"name": "review", "description": "", "handler": _mock_review},
        {"name": "remember", "description": "", "handler": _mock_remember},
        {"name": "evolve", "description": "", "handler": _mock_evolve},
    ]


def _mock_executor(prompt, data, tools, memory=None, **params):
    _CALLS.append("model-call")
    base = prompt if isinstance(prompt, dict) else {}
    return {**base, "answer": "mock-answer:" + (data.get("t") or {}).get("query", "")}


def _load_graph():
    import json
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["node_graph"]


def _build_mock_registry():
    reg = UnitRegistry(env_resolver=lambda n: True)
    reg.register(Manifest.from_dict({
        "id": "python-encyclopedia", "type": "agent", "name": "mock",
        "version": "1.0.0", "agent_def": {"identity": "①"},
        "contributions": {"tools": ["test_p3_python_encyclopedia:mock_tools"]},
    }))
    return reg


def _run_graph(flag: bool) -> dict:
    _CALLS.clear()
    _NEEDS_REVIEW["flag"] = flag
    reg = _build_mock_registry()
    rt = GraphRuntime(reg, model_executor=_mock_executor)
    res = rt.execute(_load_graph(), input_data={"query": "什么是 GIL？", "level": 3})
    return res["result"]


# —— 1. manifest 合法 + 含图 —— #
def test_manifest_valid_and_has_graph():
    m = Manifest.from_file(MANIFEST_PATH)
    assert m.id == "python-encyclopedia"
    assert m.type == "agent"
    assert m.form == "instance"
    graph = m.node_graph
    assert graph is not None
    types = {n["type"] for n in graph["nodes"]}
    assert {"entry", "model-call", "judge", "exit"}.issubset(types)
    methods = {e.get("params", {}).get("method")
               for e in graph["nodes"] if e["type"] == "plugin"}
    assert methods == {"retrieve", "compress", "reason", "build_prompt",
                       "confidence", "review", "remember", "evolve"}


# —— 2. 端到端：needs_review=True 走二审 —— #
def test_graph_runs_end_to_end_with_review():
    result = _run_graph(flag=True)
    assert result["answer"].startswith("mock-answer:")
    assert result["memory_ok"] is True
    assert result["evo_ok"] is True
    assert "review" in _CALLS          # 二审分支被执行
    assert "model-call" in _CALLS
    # 流水线顺序：入口→截断→检索→压缩→分步→提示词→生成→置信度→二审→记忆→自进化
    assert _CALLS.index("retrieve") < _CALLS.index("build_prompt") \
        < _CALLS.index("model-call") < _CALLS.index("confidence") \
        < _CALLS.index("review") < _CALLS.index("remember") < _CALLS.index("evolve")


# —— 3. judge 分支：needs_review=False 跳过二审 —— #
def test_graph_skips_review_when_not_needed():
    result = _run_graph(flag=False)
    assert result["memory_ok"] is True
    assert result["evo_ok"] is True
    assert "review" not in _CALLS      # 二审节点未执行（judge 走了 fallback 边）
    assert "model-call" in _CALLS


# —— 4. 十六项功能零丢失映射 —— #
def test_all_features_zero_loss():
    graph = _load_graph()
    methods = {e.get("params", {}).get("method")
               for e in graph["nodes"] if e["type"] == "plugin"}
    has_model_call = any(n["type"] == "model-call" for n in graph["nodes"])
    # 八大引擎管线步骤都在图节点里
    engine_steps = {"retrieve", "compress", "reason", "build_prompt",
                    "confidence", "review", "remember", "evolve"}
    assert engine_steps.issubset(methods)
    # 生成（LLM）节点存在：其工具集承载 agent 能力（沙箱/记忆/技能/委派/...）
    assert has_model_call

    # 能力插件全部登记在册（model-call 节点经 registry.enabled_tools() 即可获得）
    from pypedia.plugins.manifests import BUILTIN_PLUGINS
    ids = {p.id for p in BUILTIN_PLUGINS}
    for cap in ("sandbox", "agent-memory", "agent-skills", "agent-delegate",
                "agent-redact", "mcp", "review", "web-fetch", "preset-sources",
                "local-rerank", "evolution"):
        assert cap in ids, f"能力插件缺失：{cap}"

    # 十六项能力清单（功能维度）必须被「图节点方法 ∪ model-call 工具集 ∪ 能力插件」覆盖
    feature_coverage = methods | ({"model-call-tools"} if has_model_call else set()) | ids
    required = {
        "retrieve", "compress", "reason", "build_prompt", "confidence",
        "review", "remember", "evolve",          # 图节点
        "model-call-tools",                       # LLM 节点携带的 agent 工具集
        "sandbox", "agent-memory", "agent-skills", "agent-delegate",
        "agent-redact", "mcp", "web-fetch", "preset-sources",
        "local-rerank", "evolution",              # 能力插件
    }
    missing = required - feature_coverage
    assert not missing, f"以下功能未映射到图/工具/插件：{missing}"


# —— 5. confidence 真实处理器的 import 路径与降级语义 —— #
# 背景：真实测试①曾逼出此处 import 路径写错（pypedia.engine.models → pypedia.models）
# 且降级分 50≠旧架构 55——因为既有测试整体 mock 了 confidence handler，错误 import
# 从未被执行。本组测试刻意**不打桩 handler 本身**，只打桩被 import 的
# evaluate_confidence，锁定「import 可解析 + 打桩值透传 + 异常降级 55」三条契约。
def _import_real_encyclopedia():
    import importlib
    import sys

    if str(EXAMPLE) not in sys.path:
        sys.path.insert(0, str(EXAMPLE))
    module = importlib.import_module("encyclopedia")
    importlib.reload(module)  # 确保打到本进程的最新源码
    return module


def test_confidence_handler_real_import_path(monkeypatch):
    enc = _import_real_encyclopedia()
    # 真实 import 语句指向的模块必须可解析（不炸 ImportError）
    from pypedia.models import dashscope  # noqa: F401 —— 路径存在性

    calls: list[tuple] = []

    def fake_eval(question, answer, evidence_texts):
        calls.append((question, answer, evidence_texts))
        return {"score": 88, "level": "高", "reason": "打桩"}

    monkeypatch.setattr(dashscope, "evaluate_confidence", fake_eval)
    data = {"t": {"query": "q", "level": 3},
            "r": {"cascade": None, "review_enabled": False}}
    out = enc.confidence({"answer": "a"}, data)
    assert out["conf"] == {"score": 88, "level": "高", "reason": "打桩"}
    assert calls == [("q", "a", [])]          # 三参调用，与旧架构 engine._confidence 一致
    assert out["needs_review"] is False


def test_confidence_handler_fallback_matches_legacy(monkeypatch):
    enc = _import_real_encyclopedia()
    from pypedia.models import dashscope

    def boom(*args, **kwargs):
        raise RuntimeError("评估通道不可用")

    monkeypatch.setattr(dashscope, "evaluate_confidence", boom)
    data = {"t": {"query": "q", "level": 3},
            "r": {"cascade": None, "review_enabled": False}}
    out = enc.confidence({"answer": "a"}, data)
    # 降级分必须与旧架构 evaluate_confidence 内部降级（score=55）同值
    assert out["conf"]["score"] == 55
    assert out["conf"]["level"] == "低"
