"""Pytest 全局配置：数据目录隔离 + LLM 全打桩（测试零真实 API 调用）。

关键约束：测试套件**不允许**消耗任何百炼/Ollama/HF 配额——
  · PYPEDIA_DATA 在任何 pypedia import 之前指向临时目录（模块级 Path(os.getenv) 在
    import 时求值，晚于 import 设置无效）
  · pypedia.rag.DashScopeEmbedding 替换为 LlamaIndex MockEmbedding（确定性假向量）
  · pypedia.engine.MemoryStore / mcp_manager 替换为 no-op stub
  · 各测试按需 monkeypatch pypedia.engine.bailian_chat / evaluate_confidence

重型依赖桩统一定义在 tests/stubs.py（scripts/benchmark.py 共用同一来源，
防止两处定义漂移破坏「零真实调用」承诺）。

真实 API 调用的测试用 @pytest.mark.network 标记，默认不跑：pytest -m "not network"。
"""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile

# —— 必须在 import pypedia 之前：隔离数据目录 —— #
_TMP_DATA = tempfile.mkdtemp(prefix="pypedia-test-")
os.environ["PYPEDIA_DATA"] = _TMP_DATA
atexit.register(shutil.rmtree, _TMP_DATA, ignore_errors=True)

import pytest  # noqa: E402

# —— 重型依赖打桩（与 scripts/benchmark.py 共用 tests/stubs.py 单一来源） —— #
from stubs import StubMCP, install_engine_stubs, stub_rag_embeddings  # noqa: E402

stub_rag_embeddings()
# import pypedia.engine 后立即替换重型依赖（app.py 模块级 PyPediaEngine() 也受益）
install_engine_stubs()

import pypedia.engine as _engine  # noqa: E402,F401 —— fixtures 的 monkeypatch 目标


# —— fixtures —— #
# ask 端点打桩返回值（engine.ask 的完整结构，含 cascade/session 序列化形状）
ASK_OK = {
    "query": "q", "level": {"n": "L3", "t": "进阶", "d": ""},
    "confidence": {"score": 72, "level": "中", "level_label": "中",
                   "reason": "打桩", "breakdown": {"primary_hit": 55}},
    "cascade": None, "answer": "打桩答案", "provider": "mock",
    "session": None, "multi_turn": False,
    "context": {"compressed": False, "total_tokens": 10, "kept_tokens": 10,
                "dropped_turns": 0, "summary": ""},
    "review": {"verdict": "pass", "notes": [], "revised": "", "skipped": False},
    "reasoning_plan": "",
}


@pytest.fixture()
def stub_mcp():
    """供测试断言 MCP 调用行为的可操控 stub（替换 _engine.mcp_manager）。"""
    calls: list[tuple] = []

    class Recording(StubMCP):
        def call_tool(self, key, tool, args, timeout=30.0):
            calls.append((key, tool, args))
            return {"ok": True}

    m = Recording()
    import pypedia.engine as eng
    orig = eng.mcp_manager
    eng.mcp_manager = m
    yield m
    eng.mcp_manager = orig


@pytest.fixture()
def fake_chat(monkeypatch):
    """打桩 pypedia.engine.bailian_chat：按 prompt 内容分派返回值，记录调用。"""
    calls: list[list[dict]] = []
    replies: dict[str, str] = {}  # prompt 子串 → 回复

    def _fake(messages, **kwargs):
        calls.append(messages)
        prompt = messages[-1]["content"] if messages else ""
        for needle, reply in replies.items():
            if needle in prompt:
                return reply
        return "这是打桩答案：列表有序、字典按键寻址。[1]"

    monkeypatch.setattr(_engine, "bailian_chat", _fake)
    return Simple(calls=calls, replies=replies)


class Simple:
    def __init__(self, **kw):
        self.__dict__.update(kw)


@pytest.fixture()
def fake_confidence(monkeypatch):
    """打桩 pypedia.engine.evaluate_confidence：返回可配置的置信度结果。"""
    result = {
        "score": 72, "level": "中",
        "level_label": "中",
        "reason": "打桩置信度",
        "breakdown": {"primary_hit": 55, "cross_source": 30, "freshness": 12.8},
    }

    def _fake(*a, **kw):
        return dict(result)

    monkeypatch.setattr(_engine, "evaluate_confidence", _fake)
    return result


@pytest.fixture()
def fake_agent_step(monkeypatch):
    """打桩 pypedia.agent.transport.agent_step（cron 的 agent 任务唯一 LLM 出口）。

    记录 {query, level}；测试据此断言「preflight 失败不发 LLM 调用」等。
    """
    calls: list[dict] = []

    def fake_step(*, query, level=2, state=None, tool_results=None):
        calls.append({"query": query, "level": level})
        return {"type": "final", "content": "【桩】定时总结完成",
                "provider": "mock", "state": state}

    monkeypatch.setattr("pypedia.agent.transport.agent_step", fake_step)
    return calls


@pytest.fixture()
def stub_ask(monkeypatch):
    """打桩 app.engine.ask（单例已在 conftest 顶层 stub 化重型依赖）。"""
    import app as app_module

    state = {"raises": False}

    def _fake(query, level=3, session=None):
        if state["raises"]:
            raise RuntimeError("engine boom")
        out = dict(ASK_OK)
        out["query"] = query
        out["session"] = session
        if session is not None:
            session.add(query, "打桩答案", 72, "")  # 模拟真实 ask 的轮次记录
        return out

    monkeypatch.setattr(app_module.engine, "ask", _fake)
    return state


@pytest.fixture(autouse=True)
def reset_plugin_state():
    """插件状态跨测试隔离：快照/还原注册表内存态 + state.json 字节。

    set_enabled 会同时改内存态并原子落盘——不还原会污染后续用例
    （test_plugins 与 test_agent / test_app 之间的顺序依赖陷阱）。

    关键：saved_state 必须**深拷贝**后还原——set_enabled 是「原地改字典」
    （state[pid]=val），若保存同一引用，teardown 再把同一引用赋回去等于
    没还原，泄漏会串到后续用例（is_enabled 读到上一条用例写的值）。
    注意：导入 pypedia.plugins 零副作用（数据目录与 state.json 均懒加载）。
    """
    from pypedia.plugins.registry import plugin_registry

    path = plugin_registry._state_path()
    saved_state = dict(plugin_registry._state) if plugin_registry._state is not None else None
    saved_bytes = path.read_bytes() if path.exists() else None
    yield
    plugin_registry._state = dict(saved_state) if saved_state is not None else None
    if saved_bytes is None:
        path.unlink(missing_ok=True)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(saved_bytes)


@pytest.fixture()
def client():
    """FastAPI TestClient。app 模块级 engine 已在 conftest 顶部完成 stub 化。"""
    from fastapi.testclient import TestClient

    import app as app_module

    app_module.SESSIONS.clear()
    app_module.ask_limiter.reset()  # 配额窗口跨测试隔离，避免滑窗计数互相污染
    return TestClient(app_module.app)
