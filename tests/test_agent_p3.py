"""P3 测试：敏感脱敏（detect-secrets）/ 历史压缩 / 事件钩子 / 子代理委派 / 传输层集成。

铁律：全部打桩 pypedia.agent.bailian_model.chat_with_tools（或 TestModel），
零真实 LLM 调用、零网络；detect-secrets 探测为纯本地计算。
"""
from __future__ import annotations

import asyncio
import json
import time

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from pypedia import agent
from pypedia.agent import bailian_model
from pypedia.agent import compress as compress_mod
from pypedia.agent import delegate as delegate_mod
from pypedia.agent import hooks as hooks_mod
from pypedia.agent import memory as mem_mod
from pypedia.agent import transport as transport_mod
from pypedia.agent.compress import compress_history
from pypedia.agent.delegate import delegate_task
from pypedia.agent.hooks import (
    agent_step_finished,
    agent_step_started,
    delegate_spawned,
    memory_written,
    secret_redacted,
    skill_viewed,
)
from pypedia.agent.redact import redact_text
from pypedia.agent.transport import load_state
from pypedia.config import settings


# ---------- 打桩：chat_with_tools（脚本化，支持子代理分流） ---------- #
@pytest.fixture()
def fake_chat(monkeypatch):
    """脚本化打桩：script 队列优先（pop）；队列空时走默认委派流程。

    按「系统提示词是否子代理」分流子代理回复；记录全部调用（含子代理），
    断言主代理调用数时须自行剔除子代理调用。
    """
    state = {"calls": [], "sub_calls": 0, "script": []}

    def _fake(messages, tools, **kw):
        state["calls"].append({"messages": messages, "tools": tools, "kw": kw})
        sys_msg = next((m["content"] for m in messages
                        if m.get("role") == "system"), "")
        if sys_msg.startswith("你是子代理"):
            state["sub_calls"] += 1
            return {"role": "assistant",
                    "content": f"子代理结论 v{state['sub_calls']}：查证完成。"}
        if state["script"]:
            item = state["script"].pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        if any(m.get("role") == "tool" for m in messages):
            return _oai_text("已综合子代理结果给出终答。")
        # 默认：主代理请求 delegate_task
        return _oai_tool_calls([{"id": "c1", "name": "delegate_task",
                                 "arguments": {"task": "查证子任务"}}])

    monkeypatch.setattr(bailian_model, "chat_with_tools", _fake)
    return state


def _oai_text(text):
    return {"role": "assistant", "content": text}


def _oai_tool_calls(calls):
    return {"role": "assistant", "content": None,
            "tool_calls": [
                {"id": c["id"], "type": "function",
                 "function": {"name": c["name"],
                              "arguments": json.dumps(c.get("arguments", {}),
                                                      ensure_ascii=False)}}
                for c in calls]}


class _Recorder:
    """blinker 接收器（weak=False，防局部函数被 GC）。"""

    def __init__(self):
        self.events = []

    def __call__(self, sender, **kw):
        self.events.append({"sender": sender, **kw})


@pytest.fixture()
def recorder():
    rec = _Recorder()
    for sig in (agent_step_started, agent_step_finished, secret_redacted,
                memory_written, skill_viewed, delegate_spawned):
        sig.connect(rec, weak=False)
    yield rec
    for sig in (agent_step_started, agent_step_finished, secret_redacted,
                memory_written, skill_viewed, delegate_spawned):
        sig.disconnect(rec)


# ==================== 脱敏（detect-secrets） ==================== #
def test_redact_plain_text_untouched():
    r = redact_text("普通中文内容，没有任何敏感信息。端口 8975。", source="test")
    assert not r.redacted and r.text == "普通中文内容，没有任何敏感信息。端口 8975。"


def test_redact_quoted_assignment():
    """带引号的 key=value（.env/JSON 配置形态）——KeywordDetector 命中。"""
    r = redact_text('password = "p@ssw0rd123456"', source="test")
    assert r.redacted and "p@ssw0rd123456" not in r.text
    assert "«已脱敏»" in r.text and "KeywordDetector" in r.kinds


def test_redact_bare_sk_key():
    """百炼/DashScope 形态的裸 sk- 密钥（官方 OpenAIDetector 不认，靠扩展插件）。"""
    r = redact_text("key=sk-" + "b" * 48, source="test")
    assert r.redacted and "sk-" + "b" * 48 not in r.text


def test_redact_bearer_header():
    r = redact_text("Authorization: Bearer " + "a" * 30, source="test")
    assert r.redacted and "Bearer " + "a" * 30 not in r.text


def test_redact_short_sk_not_matched():
    """短 sk- 串不误伤（<20 位后续）。"""
    r = redact_text("sk-短 and sk-abc", source="test")
    assert not r.redacted


def test_redact_url_userinfo():
    r = redact_text("proxy = https://user:s3cret@example.com/p", source="test")
    assert r.redacted and "s3cret" not in r.text and "example.com" in r.text


def test_redact_pem_block_whole():
    text = ("配置：\n-----BEGIN RSA PRIVATE KEY-----\n"
            "MIIEowIBAAKCAQEAxyz\n-----END RSA PRIVATE KEY-----\n收尾")
    r = redact_text(text, source="test")
    assert r.redacted and "MIIEowIBAAKCAQEA" not in r.text
    assert "PrivateKeyDetector" in r.kinds and "配置" in r.text and "收尾" in r.text


def test_redact_disabled_by_settings(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_REDACT_SECRETS", False)
    r = redact_text('api_key = "sk-abc123def456ghi789jkl012"', source="test")
    assert not r.redacted and "sk-abc123def456" in r.text


def test_redact_emits_hook(recorder):
    redact_text('password = "p@ssw0rd123456"', source="unit")
    ev = [e for e in recorder.events if "kinds" in e]
    assert ev and ev[0]["source"] == "unit"


def test_redact_long_text_fast():
    """长文本（工具结果量级）不炸且耗时有限（本地正则，无网络）。"""
    text = ("正常内容行，包含一些中文与代码片段 print(1)。\n" * 400)
    t0 = time.perf_counter()
    r = redact_text(text, source="perf")
    assert not r.redacted
    assert time.perf_counter() - t0 < 5.0


# ==================== 历史压缩 ==================== #
def _hist(n_rounds=4, filler="回答"):
    """首条(sys+user) + n 轮 (user, assistant)。"""
    out = [ModelRequest(parts=[UserPromptPart(content="首轮问题")])]
    for i in range(n_rounds):
        out.append(ModelRequest(parts=[UserPromptPart(content=f"问题{i}" + "x" * 50)]))
        out.append(ModelResponse(parts=[TextPart(content=f"{filler}{i}" + "y" * 50)]))
    return out


def test_compress_identity_within_budget(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_HISTORY_CHARS", 100000)
    monkeypatch.setattr(settings, "AGENT_HISTORY_MAX_MESSAGES", 24)
    hist = _hist(3)
    assert compress_history(hist) is hist


def test_compress_truncates_over_budget(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_HISTORY_CHARS", 300)
    monkeypatch.setattr(settings, "AGENT_HISTORY_MAX_MESSAGES", 24)
    hist = _hist(6)
    out = compress_history(hist)
    assert len(out) < len(hist)
    assert "首轮问题" in out[0].parts[0].content          # 首条恒保留
    assert "回答5" in out[-1].parts[0].content             # 尾部恒保留
    assert sum(len(p.content) for m in out for p in m.parts) <= 300 + 120


def test_compress_message_count_cap(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_HISTORY_CHARS", 100000)
    monkeypatch.setattr(settings, "AGENT_HISTORY_MAX_MESSAGES", 5)
    hist = _hist(6)
    out = compress_history(hist)
    assert len(out) <= 5


def test_compress_preserves_tool_pair(monkeypatch):
    """保留区首条带 ToolReturnPart 时，必须连带保留 ToolCallPart 源头。"""
    monkeypatch.setattr(settings, "AGENT_HISTORY_CHARS", 100000)
    monkeypatch.setattr(settings, "AGENT_HISTORY_MAX_MESSAGES", 3)
    hist = [
        ModelRequest(parts=[UserPromptPart(content="q0" + "z" * 80)]),
        ModelResponse(parts=[ToolCallPart(tool_name="t", args={"a": "x" * 80},
                                          tool_call_id="c1")]),
        ModelRequest(parts=[ToolReturnPart(tool_name="t", content="r" * 200,
                                           tool_call_id="c1")]),
        ModelRequest(parts=[UserPromptPart(content="后续问题" + "w" * 60)]),
    ]
    out = compress_history(hist)
    names = [type(p).__name__ for m in out for p in m.parts]
    assert "ToolCallPart" in names and "ToolReturnPart" in names
    assert names.index("ToolCallPart") < names.index("ToolReturnPart")


def test_compress_tiny_history_untouched():
    assert compress_history([]) == []
    one = [ModelRequest(parts=[UserPromptPart(content="x")])]
    assert compress_history(one) is one


def test_compress_via_agent_capability():
    """集成：Agent(capabilities=[ProcessHistory]) 跑一轮，all_messages 被有界化。"""
    from pydantic_ai import Agent
    from pydantic_ai.capabilities import ProcessHistory
    from pydantic_ai.models.test import TestModel

    old_chars = settings.AGENT_HISTORY_CHARS
    settings.AGENT_HISTORY_CHARS = 200
    try:
        seen = {}

        def proc(messages):
            seen["n"] = len(messages)
            return compress_history(messages)

        a = Agent(TestModel(), capabilities=[ProcessHistory(proc)])
        r = a.run_sync("新问题", message_history=_hist(6, filler="长回答"))
        assert seen["n"] == 13                    # 7 条历史 + 新 prompt
        assert len(r.all_messages()) < 14         # 压缩生效（含 TestModel 自动回复）
    finally:
        settings.AGENT_HISTORY_CHARS = old_chars


# ==================== 事件钩子 ==================== #
def test_hook_signals_exist():
    for sig in (agent_step_started, agent_step_finished, secret_redacted,
                memory_written, skill_viewed, delegate_spawned):
        assert sig is not None


def test_hook_reserved_field_sanitized(recorder, caplog):
    """send(name=...) 曾撞 LogRecord 保留字段；消毒后不抛且日志有记录。"""
    with caplog.at_level("INFO"):
        skill_viewed.send("skills", name="demo")   # name 是保留字段
    ev = [e for e in recorder.events if e.get("h_name") == "demo"
          or e.get("name") == "demo"]
    assert ev


def test_memory_hook_on_write(tmp_path, monkeypatch, recorder):
    monkeypatch.setenv("PYPEDIA_DATA", str(tmp_path))
    store = mem_mod.MemoryStore()
    monkeypatch.setattr(mem_mod, "memory_store", store)
    store.add("memory", "钩子测试记忆", tag="hook")
    ev = [e for e in recorder.events if e.get("op") == "add"]
    assert ev and ev[0]["scope"] == "memory"


# ==================== 子代理委派 ==================== #
def test_delegate_end_to_end(fake_chat, recorder):
    r = agent.agent_step(query="帮确认服务端口", level=3)
    assert r["type"] == "final"
    assert "已综合子代理结果" in r["content"]
    msgs = load_state(r["state"])
    names = [type(p).__name__ for m in msgs for p in m.parts]
    assert "ToolCallPart" in names and "ToolReturnPart" in names
    # 子代理结论回流主历史（ToolReturnPart content）
    tr = [p for m in msgs for p in m.parts if isinstance(p, ToolReturnPart)][0]
    assert "子代理结论" in str(tr.content)
    # 子代理的探索过程不进主 state：主代理 LLM 只被调用 2 次（工具请求 + 终答）
    main_calls = [c for c in fake_chat["calls"]
                  if not any(m.get("role") == "system"
                             and str(m.get("content", "")).startswith("你是子代理")
                             for m in c["messages"])]
    assert len(main_calls) == 2
    assert fake_chat["sub_calls"] == 1
    # 钩子：委派派出
    ev = [e for e in recorder.events if "inflight" in e]
    assert ev and ev[0]["task"] == "查证子任务"


def test_delegate_subagent_has_no_delegate_tool(fake_chat):
    agent.agent_step(query="x", level=3)
    sub_msgs = [c for c in fake_chat["calls"]
                if any(m.get("role") == "system"
                       and str(m.get("content", "")).startswith("你是子代理")
                       for m in c["messages"])]
    assert sub_msgs
    sub_tools = {t["function"]["name"] for t in sub_msgs[0]["tools"]}
    assert "delegate_task" not in sub_tools
    assert "run_python" not in sub_tools          # 无浏览器外派工具
    assert "memory_search" in sub_tools           # 有服务端工具


def test_delegate_empty_task():
    out = asyncio.run(delegate_task(""))
    assert "参数错误" in out


def test_delegate_disabled(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_DELEGATE_ENABLE", False)
    out = asyncio.run(delegate_task("查点什么"))
    assert "AGENT_DELEGATE_ENABLE" in out


def test_delegate_concurrency_cap(monkeypatch):
    monkeypatch.setattr(settings, "AGENT_DELEGATE_MAX", 0)
    out = asyncio.run(delegate_task("查点什么"))
    assert "上限" in out


def test_delegate_subagent_failure_returns_text(monkeypatch):
    """子代理运行抛异常 → 错误文本回流，不打断主循环。"""

    def boom(messages, tools, **kw):
        sys_msg = next((m["content"] for m in messages
                        if m.get("role") == "system"), "")
        if sys_msg.startswith("你是子代理"):
            raise RuntimeError("sub boom")
        return _oai_text("主代理自行完成。")

    monkeypatch.setattr(bailian_model, "chat_with_tools", boom)
    out = asyncio.run(delegate_task("查证"))
    assert "子代理执行失败" in out and "RuntimeError" in out


def test_delegate_inflight_restored_after_failure(monkeypatch):
    def boom(messages, tools, **kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(bailian_model, "chat_with_tools", boom)
    before = delegate_mod._inflight
    asyncio.run(delegate_task("查证"))
    assert delegate_mod._inflight == before        # finally 递减，无泄漏


# ==================== 传输层集成（脱敏闸门 + 步级钩子） ==================== #
def test_query_redacted_before_llm(fake_chat):
    fake_chat["script"] = [_oai_text("收到。")]
    r = agent.agent_step(query="我的密钥是 sk-" + "k" * 40, level=3)
    assert r["type"] == "final"
    sent = fake_chat["calls"][0]["messages"]
    joined = json.dumps(sent, ensure_ascii=False)
    assert "sk-" + "k" * 40 not in joined
    assert "«已脱敏»" in joined


def test_tool_result_redacted_before_llm(fake_chat):
    fake_chat["script"] = [
        _oai_tool_calls([{"id": "c1", "name": "run_python",
                          "arguments": {"code": "print(1)"}}]),
        _oai_text("好。"),
    ]
    r1 = agent.agent_step(query="跑一下", level=3)
    assert r1["type"] == "tool_calls"

    secret = 'config = {"token": "sk-' + "z" * 40 + '"}'
    r2 = agent.agent_step(state=r1["state"], level=3,
                          tool_results=[{"id": "c1", "result": secret}])
    assert r2["type"] == "final"
    sent = fake_chat["calls"][-1]["messages"]
    tool_msgs = [m for m in sent if m["role"] == "tool"]
    assert tool_msgs and "sk-" + "z" * 40 not in tool_msgs[0]["content"]
    assert "«已脱敏»" in tool_msgs[0]["content"]


def test_step_hooks_fire(fake_chat, recorder):
    fake_chat["script"] = [_oai_text("答案")]
    agent.agent_step(query="你好", level=3)
    started = [e for e in recorder.events if e.get("mode") == "query"
               and "level" in e]
    finished = [e for e in recorder.events if e.get("type") == "final"
                and "degraded" in e]
    assert started and finished


def test_step_hook_on_bad_state(recorder):
    with pytest.raises(ValueError):
        agent.agent_step(state="{bad json", level=3)
    ev = [e for e in recorder.events if e.get("ok") is False]
    assert ev
