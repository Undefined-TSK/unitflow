"""AI 沙箱工具层（pydantic-ai 版）测试：工具白名单 / deferred 往返 / state 协议 / 端点。

铁律：全部打桩 pypedia.agent.bailian_model.chat_with_tools，零真实 LLM 调用；
工具执行在前端（浏览器沙箱），本层只验证编排与协议。
"""
from __future__ import annotations

import asyncio
import json

import pytest
from pydantic_ai.exceptions import CallDeferred
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    SystemPromptPart,
    ToolCallPart,
    UserPromptPart,
)

from pypedia import agent
from pypedia.agent import (
    MAX_TOOL_ROUNDS,
    browser_tools,
    build_system_prompt,
    dump_state,
    load_state,
)
from pypedia.agent import bailian_model
from pypedia.config import settings
from pypedia.agent.browser_tools import (
    MAX_URL_CHARS,
    install_package,
    run_python,
    sandbox_status,
)


# ---------- 打桩：chat_with_tools 脚本化返回 ---------- #
@pytest.fixture()
def fake_chat(monkeypatch):
    """打桩 pypedia.agent.bailian_model.chat_with_tools（BailianModel 唯一 LLM 出口）。

    按脚本队列返回 OpenAI 兼容消息；记录每次调用的 messages/tools 供断言。
    """
    state = {"script": [], "calls": []}

    def _fake(messages, tools, **kw):
        state["calls"].append({"messages": messages, "tools": tools, "kw": kw})
        item = state["script"].pop(0) if len(state["script"]) > 1 else state["script"][0]
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(bailian_model, "chat_with_tools", _fake)
    return state


def _oai_tool_calls(calls):
    """OpenAI assistant 消息（tool_calls）。"""
    return {"role": "assistant", "content": None,
            "tool_calls": [
                {"id": c["id"], "type": "function",
                 "function": {"name": c["name"],
                              "arguments": json.dumps(c.get("arguments", {}),
                                                      ensure_ascii=False)}}
                for c in calls]}


def _oai_text(text):
    return {"role": "assistant", "content": text}


# ---------- 工具白名单（参数非法内联喂回，不外派） ---------- #
def test_four_browser_tools():
    names = {t.__name__ for t in agent.BROWSER_TOOLS}
    assert names == {"run_python", "install_package", "fetch_url", "sandbox_status"}


@pytest.mark.parametrize("name,args,needle", [
    ("run_python", {"code": None}, "参数错误"),
    ("run_python", {"code": "   "}, "参数错误"),
    ("run_python", {"code": 123}, "参数错误"),
    ("install_package", {"name": "x; rm -rf /"}, "包名非法"),
    ("install_package", {"name": "numpy>=1.0"}, "包名非法"),
    ("install_package", {"name": "https://evil/x.whl"}, "包名非法"),
    ("install_package", {"name": None}, "包名非法"),
    ("fetch_url", {"url": "ftp://x"}, "仅支持 http/https"),
    ("fetch_url", {"url": "file:///etc/passwd"}, "仅支持 http/https"),
    ("fetch_url", {"url": "https://a.com/" + "x" * MAX_URL_CHARS}, "网址过长"),
    ("fetch_url", {"url": None}, "仅支持 http/https"),
])
def test_tool_invalid_params_return_error_text(name, args, needle):
    """参数非法：返回错误文本（作为工具结果内联喂回模型自修正），不外派。"""
    fn = {t.__name__: t for t in agent.BROWSER_TOOLS}[name]
    out = asyncio.run(fn(**args))
    assert isinstance(out, str) and needle in out


@pytest.mark.parametrize("name,args", [
    ("run_python", {"code": "print(1)"}),
    ("install_package", {"name": "charset_normalizer"}),
    ("fetch_url", {"url": "https://docs.python.org/3/"}),
])
def test_tool_valid_params_raise_call_deferred(name, args):
    """参数合法：抛 CallDeferred（运行挂起，外派浏览器执行）。"""
    fn = {t.__name__: t for t in agent.BROWSER_TOOLS}[name]
    with pytest.raises(CallDeferred):
        asyncio.run(fn(**args))


def test_sandbox_status_defers():
    with pytest.raises(CallDeferred):
        asyncio.run(sandbox_status())


def test_system_prompt_contains_tool_rules():
    sp = build_system_prompt(3, "什么是装饰器")
    assert "沙箱工具使用规约" in sp
    assert "run_python" in sp and "PyPedia" in sp


# ---------- agent_step：首轮 tool_calls + state ---------- #
def test_agent_step_first_round_tool_calls_with_state(fake_chat):
    fake_chat["script"] = [_oai_tool_calls([
        {"id": "c1", "name": "run_python", "arguments": {"code": "print(1+1)"}},
        {"id": "c2", "name": "sandbox_status", "arguments": {}},
    ])]
    r = agent.agent_step(query="帮我算 1+1", level=3)
    assert r["type"] == "tool_calls"
    assert r["max_rounds"] == MAX_TOOL_ROUNDS
    assert r["calls"] == [
        {"id": "c1", "name": "run_python", "arguments": {"code": "print(1+1)"}},
        {"id": "c2", "name": "sandbox_status", "arguments": {}},
    ]
    # state 可反序列化，且首轮系统提示词已冻结进历史
    msgs = load_state(r["state"])
    assert msgs[0].parts[0].content.find("沙箱工具使用规约") >= 0
    assert msgs[0].parts[1].content == "帮我算 1+1"
    assert msgs[-1].parts[0].tool_name == "run_python"
    # 请求确实带了全部工具 schema：4 个浏览器外派 + 6 个服务端内联 + 1 委派
    tool_names = {t["function"]["name"] for t in fake_chat["calls"][0]["tools"]}
    assert tool_names == {"run_python", "install_package", "fetch_url", "sandbox_status",
                          "memory_search", "memory_add", "memory_patch",
                          "memory_remove", "skill_list", "skill_view",
                          "delegate_task"}


def test_agent_step_deferred_roundtrip_final(fake_chat):
    """deferred 往返：首轮外派 → 回填工具结果 → 续跑出最终答案。"""
    fake_chat["script"] = [_oai_tool_calls(
        [{"id": "c1", "name": "run_python", "arguments": {"code": "print(42)"}}])]
    r1 = agent.agent_step(query="算一下", level=3)
    assert r1["type"] == "tool_calls"

    fake_chat["script"] = [_oai_text("跑过了，42 没错。")]
    r2 = agent.agent_step(state=r1["state"], level=3,
                          tool_results=[{"id": "c1", "result": "42\n"}])
    assert r2["type"] == "final"
    assert r2["content"] == "跑过了，42 没错。"
    assert r2["provider"] == settings.LLM_PROVIDER
    # 第二次请求的历史里工具结果以 role=tool 正确注入（id 对得上）
    sent = fake_chat["calls"][1]["messages"]
    tool_msgs = [m for m in sent if m["role"] == "tool"]
    assert tool_msgs and tool_msgs[0]["tool_call_id"] == "c1"
    assert tool_msgs[0]["content"] == "42\n"
    # 续轮 state 仍可再序列化往返（前端继续 opaque 透传）
    assert load_state(r2["state"])


def test_agent_step_round_guard_stops_before_llm(fake_chat):
    """轮次护栏：历史已达 MAX_TOOL_ROUNDS 轮工具调用时不再请求 LLM。"""
    messages = [ModelRequest(parts=[SystemPromptPart(content="s"),
                                    UserPromptPart(content="q")])]
    for i in range(MAX_TOOL_ROUNDS):
        messages.append(ModelResponse(parts=[
            ToolCallPart(tool_name="run_python", args={"code": "x"},
                         tool_call_id=f"c{i}")]))
    r = agent.agent_step(state=dump_state(messages), level=3,
                         tool_results=[{"id": f"c{MAX_TOOL_ROUNDS - 1}", "result": "ok"}])
    assert r["type"] == "final" and "轮次" in r["content"]
    assert fake_chat["calls"] == []          # 零 LLM 调用
    assert load_state(r["state"])            # state 原样带回


def test_agent_step_invalid_args_inline_feedback(fake_chat):
    """模型给了非法参数：工具返回错误文本内联入历史，模型自修正后继续（同一步内）。"""
    fake_chat["script"] = [
        _oai_tool_calls([{"id": "c1", "name": "install_package",
                          "arguments": {"name": "x; rm -rf /"}}]),
        _oai_text("包名参数有问题，我直接基于已知知识回答。"),
    ]
    r = agent.agent_step(query="装个包", level=3)
    assert r["type"] == "final"
    # 同一步内发生了两次模型请求：坏调用 + 自修正后的最终答复
    assert len(fake_chat["calls"]) == 2
    sent = fake_chat["calls"][1]["messages"]
    tool_msgs = [m for m in sent if m["role"] == "tool"]
    assert tool_msgs and "包名非法" in tool_msgs[0]["content"]


def test_agent_step_degraded_when_channel_down(fake_chat):
    """通道不可用（无密钥/网络断）：降级 Mock 直答，不假装调过工具。"""
    fake_chat["script"] = [RuntimeError("no api key")]
    r = agent.agent_step(query="什么是装饰器")
    assert r["type"] == "final"
    assert r["provider"] == "mock" and r["degraded"] is True
    assert "离线演示" in r["content"]


def test_agent_step_empty_content_placeholder(fake_chat):
    fake_chat["script"] = [_oai_text("  ")]
    r = agent.agent_step(query="q")
    assert r["type"] == "final" and "没有返回内容" in r["content"]


# ---------- agent_step：入参校验 ---------- #
@pytest.mark.parametrize("kwargs", [
    {"query": "   "},                       # 空 query
    {},                                      # 两个都不给
    {"query": "q", "state": "{}"},           # 都给
    {"state": "[]"},                         # state 模式缺 tool_results
])
def test_agent_step_rejects_bad_inputs(kwargs):
    with pytest.raises(ValueError):
        agent.agent_step(**kwargs)


@pytest.mark.parametrize("bad_state", [
    "not-json",
    "[]",
    '{"x": 1}',
    "null",
])
def test_agent_step_rejects_bad_state(bad_state):
    with pytest.raises(ValueError):
        agent.agent_step(state=bad_state, tool_results=[{"id": "c1", "result": "x"}])


def test_agent_step_rejects_mismatched_tool_result_id():
    msgs = [ModelRequest(parts=[SystemPromptPart(content="s"), UserPromptPart(content="q")]),
            ModelResponse(parts=[ToolCallPart(tool_name="run_python", args={"code": "x"},
                                              tool_call_id="c1")])]
    with pytest.raises(ValueError):
        agent.agent_step(state=dump_state(msgs),
                         tool_results=[{"id": "cX", "result": "x"}])


def test_agent_step_truncates_long_tool_result(fake_chat):
    """单个工具结果超长：截断到 MAX_TOOL_RESULT_CHARS 后再喂模型。"""
    fake_chat["script"] = [_oai_tool_calls(
        [{"id": "c1", "name": "run_python", "arguments": {"code": "print(42)"}}])]
    r1 = agent.agent_step(query="算一下", level=3)
    fake_chat["script"] = [_oai_text("ok")]
    big = "x" * (agent.MAX_TOOL_RESULT_CHARS + 500)
    agent.agent_step(state=r1["state"], level=3,
                     tool_results=[{"id": "c1", "result": big}])
    sent = fake_chat["calls"][1]["messages"]
    tool_msg = next(m for m in sent if m["role"] == "tool")
    assert len(tool_msg["content"]) < len(big)
    assert "已截断" in tool_msg["content"]


def test_agent_step_truncates_long_query(fake_chat):
    fake_chat["script"] = [_oai_text("ok")]
    long_q = "啊" * 5000
    agent.agent_step(query=long_q)
    sent_user = fake_chat["calls"][0]["messages"][1]["content"]
    assert len(sent_user) < 5000 and sent_user.endswith("…（已截断）")


# ---------- 端点 ---------- #
def test_agent_endpoint_query_mode(client, monkeypatch):
    """首轮：query → tool_calls + state（打桩 chat_with_tools，零真实调用）。"""
    monkeypatch.setattr(bailian_model, "chat_with_tools",
                        lambda m, t, **kw: _oai_tool_calls(
                            [{"id": "c1", "name": "run_python",
                              "arguments": {"code": "print(42)"}}]))
    r = client.post("/api/agent/step", json={"query": "帮我算", "level": 3})
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "tool_calls"
    assert body["calls"][0]["arguments"] == {"code": "print(42)"}
    assert load_state(body["state"])          # state 形状合法
    assert body["max_rounds"] == MAX_TOOL_ROUNDS


def test_agent_endpoint_state_mode_final(client, monkeypatch):
    """续轮：state + tool_results → final（端点内两跳完整往返）。"""
    monkeypatch.setattr(bailian_model, "chat_with_tools",
                        lambda m, t, **kw: _oai_tool_calls(
                            [{"id": "c1", "name": "run_python",
                              "arguments": {"code": "print(42)"}}]))
    r1 = client.post("/api/agent/step", json={"query": "帮我算", "level": 3})
    state = r1.json()["state"]

    monkeypatch.setattr(bailian_model, "chat_with_tools",
                        lambda m, t, **kw: _oai_text("跑过了，没问题"))
    r2 = client.post("/api/agent/step", json={
        "state": state, "level": 3,
        "tool_results": [{"id": "c1", "result": "42\n"}]})
    assert r2.status_code == 200
    assert r2.json()["type"] == "final"
    assert r2.json()["content"] == "跑过了，没问题"


def test_agent_endpoint_bad_request_shapes(client):
    assert client.post("/api/agent/step", json={}).status_code == 400                    # 都不给
    assert client.post("/api/agent/step",
                       json={"query": "q", "state": "[]"}).status_code == 400           # 都给
    assert client.post("/api/agent/step", json={"query": "  "}).status_code == 400       # 空 query
    assert client.post("/api/agent/step",
                       json={"state": "not-json",
                             "tool_results": [{"id": "c1", "result": "x"}]}).status_code == 400  # 坏 state
    assert client.post("/api/agent/step",
                       json={"state": "[]",
                             "tool_results": [{"id": "c1", "result": "x"}]}).status_code == 400  # state 缺 tool_results


def test_agent_endpoint_disabled(client, monkeypatch):
    monkeypatch.setattr(settings, "AGENT_ENABLE", False)
    assert client.post("/api/agent/step", json={"query": "q"}).status_code == 503


def test_agent_endpoint_degraded_without_key(client, monkeypatch):
    """无密钥路径：chat_with_tools 抛错 → 200 + 降级标注（不 502）。"""
    def boom(m, t, **kw):
        raise RuntimeError("未配置百炼 API Key")

    monkeypatch.setattr(bailian_model, "chat_with_tools", boom)
    r = client.post("/api/agent/step", json={"query": "什么是 GIL"})
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "final" and body["degraded"] is True


def test_agent_endpoint_level_clamped(client, monkeypatch):
    """level 越界钳制到 1-5（不 422）。"""
    monkeypatch.setattr(bailian_model, "chat_with_tools",
                        lambda m, t, **kw: _oai_text("ok"))
    assert client.post("/api/agent/step",
                       json={"query": "q", "level": 99}).status_code == 200
    assert client.post("/api/agent/step",
                       json={"query": "q", "level": -5}).status_code == 200


def test_agent_step_respects_memory_gate(fake_chat, monkeypatch):
    """关闭记忆插件：LLM 请求不再携带 memory_* 工具，系统提示词无记忆段。

    与 test_agent_step_first_round_tool_calls_with_state（全开 11 工具）互为对照，
    证明插件门控经 build_agent → BailianModel.request 真实传导到模型工具 schema。
    """
    monkeypatch.setattr(settings, "AGENT_MEMORY_ENABLE", False)
    fake_chat["script"] = [_oai_tool_calls([
        {"id": "c1", "name": "run_python", "arguments": {"code": "print(1)"}}])]
    r = agent.agent_step(query="算一下", level=3)
    assert r["type"] == "tool_calls"
    tool_names = {t["function"]["name"] for t in fake_chat["calls"][0]["tools"]}
    assert "memory_search" not in tool_names          # 记忆工具已摘
    assert "delegate_task" in tool_names              # 其他插件不受影响
    sp = load_state(r["state"])[0].parts[0].content
    assert "持久记忆库使用规约" not in sp             # 系统提示词无记忆段
    assert "技能库使用规约" in sp                     # 技能段仍在
