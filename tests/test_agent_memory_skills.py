"""Hermes 式记忆库 + 技能库测试：§ 编辑 / FTS5 trigram / 三级披露 / 归档 / 端点。

铁律：全部本地（tmp 目录 + 进程内 store），零 LLM 调用、零网络。
"""
from __future__ import annotations

import asyncio
import os
import time

import pytest

from pypedia.agent import memory as mem_mod
from pypedia.agent import server_tools as st_mod
from pypedia.agent import skills as sk_mod
from pypedia.agent.memory import MemoryError_
from pypedia.agent.skills import SkillError_


@pytest.fixture()
def mem(tmp_path, monkeypatch):
    """隔离的记忆 store（指向 tmp 数据目录；同步 patch server_tools 绑定）。"""
    monkeypatch.setenv("PYPEDIA_DATA", str(tmp_path))
    store = mem_mod.MemoryStore()
    monkeypatch.setattr(mem_mod, "memory_store", store)
    monkeypatch.setattr(st_mod, "memory_store", store)
    return store


@pytest.fixture()
def sk(tmp_path, monkeypatch):
    """隔离的技能 store。"""
    monkeypatch.setenv("PYPEDIA_DATA", str(tmp_path))
    store = sk_mod.SkillStore()
    monkeypatch.setattr(sk_mod, "skill_store", store)
    monkeypatch.setattr(st_mod, "skill_store", store)
    return store


def _write_skill(base: str, name: str, body: str, meta: str = "") -> None:
    d = os.path.join(base, "agent", "skills", name)
    os.makedirs(d, exist_ok=True)
    fm = meta or (f"---\nname: {name}\ndescription: 技能 {name} 的描述\n"
                  f"when_to_use: 需要 {name} 时\n---\n\n")
    with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(fm + body)


# ---------- 记忆：§ 编辑 ---------- #
def test_memory_add_and_render(mem):
    mem.add("memory", "用户偏好先看代码", tag="pref")
    content = mem.render("memory")
    assert "## § " in content and "用户偏好先看代码" in content


def test_memory_add_rejects_empty_and_oversize(mem):
    with pytest.raises(MemoryError_):
        mem.add("memory", "   ")
    big = "x" * (mem_mod.settings.AGENT_MEMORY_MAX_CHARS + 1)
    with pytest.raises(MemoryError_):
        mem.add("memory", big)


def test_memory_unknown_scope(mem):
    with pytest.raises(MemoryError_):
        mem.add("project", "x")


def test_memory_patch_substring(mem):
    mem.add("memory", "讲解顺序：先理论后代码", tag="order")
    header = mem.patch("memory", "先理论后代码", "先代码后理论")
    assert "## §" in header
    assert "先代码后理论" in mem.render("memory")
    assert "先理论后代码" not in mem.render("memory")


def test_memory_patch_requires_unique_hit(mem):
    mem.add("memory", "重复内容甲", tag="a")
    mem.add("memory", "重复内容甲", tag="b")
    with pytest.raises(MemoryError_) as ei:
        mem.patch("memory", "重复内容甲", "替换")
    assert "命中 2 个段落" in str(ei.value)


def test_memory_patch_miss(mem):
    mem.add("memory", "唯一内容", tag="a")
    with pytest.raises(MemoryError_):
        mem.patch("memory", "不存在的子串", "x")


def test_memory_remove(mem):
    mem.add("memory", "要删除的记忆", tag="gone")
    mem.add("memory", "要保留的记忆", tag="keep")
    header = mem.remove("memory", "要删除的记忆")
    assert "gone" in header
    assert "要删除的记忆" not in mem.render("memory")
    assert "要保留的记忆" in mem.render("memory")


def test_memory_remove_last_empties_file(mem):
    mem.add("user", "临时画像", tag="tmp")
    mem.remove("user", "临时画像")
    assert mem.render("user") == ""


# ---------- 记忆：FTS5 trigram 检索 ---------- #
def test_memory_search_chinese_substring(mem):
    mem.add("memory", "用户在做数据分析项目，常用 pandas", tag="proj")
    mem.add("user", "用户是初学者", tag="who")
    hits = mem.search("数据分析")
    assert len(hits) == 1 and hits[0]["scope"] == "memory"
    hits = mem.search("初学者")
    assert len(hits) == 1 and hits[0]["scope"] == "user"


def test_memory_search_scope_filter(mem):
    mem.add("memory", "共同关键词 here", tag="a")
    mem.add("user", "共同关键词 here", tag="b")
    assert len(mem.search("共同关键词")) == 2
    assert len(mem.search("共同关键词", scope="user")) == 1


def test_memory_search_short_query_like_fallback(mem):
    mem.add("memory", "短查询两个", tag="s")
    assert len(mem.search("两个")) == 1   # <3 字符退化 LIKE


def test_memory_search_injection_safe(mem):
    mem.add("memory", "安全内容", tag="safe")
    # FTS 查询语法注入不应报错，只应无命中
    assert mem.search('内容" OR "1"="1') == []


def test_memory_search_reflects_patch(mem):
    mem.add("memory", "旧关键词记忆", tag="t")
    mem.patch("memory", "旧关键词", "新关键词")
    assert mem.search("新关键词")
    assert not mem.search("旧关键词")


# ---------- 记忆：nudge ---------- #
def test_memory_nudge_every_n_steps(mem, monkeypatch):
    monkeypatch.setattr(mem_mod.settings, "AGENT_NUDGE_EVERY", 3)
    assert mem.bump_step() is None      # 1
    assert mem.bump_step() is None      # 2
    assert "整理" in mem.bump_step()    # 3
    assert mem.bump_step() is None      # 4


# ---------- 技能：注册/校验/三级披露 ---------- #
def test_skills_three_levels(sk, tmp_path):
    _write_skill(str(tmp_path), "chart-gen", "# 图表指令\n按协议输出 chart 块。")
    _write_skill(str(tmp_path), "pytest-gen", "# 测试指令\n先正常后边界。")

    brief = sk.list_brief()
    assert {s["name"] for s in brief} == {"chart-gen", "pytest-gen"}
    assert all(set(s) == {"name", "description"} for s in brief)   # L1 最小

    detail = sk.list_detail()
    by_name = {s["name"]: s for s in detail}
    assert by_name["chart-gen"]["when_to_use"] == "需要 chart-gen 时"    # L2 增量
    assert by_name["chart-gen"]["usage"] == {"count": 0, "last_used": None}

    full = sk.view("chart-gen")
    assert "图表指令" in full["body"]                       # L3 全文
    assert sk._usage("chart-gen")["count"] == 1             # view 即用量


def test_skills_validation_skips_bad(sk, tmp_path):
    _write_skill(str(tmp_path), "good", "# ok\n")
    _write_skill(str(tmp_path), "bad", "坏", meta="---\nname: bad\ndescription: 缺字段\n---\n\n")
    _write_skill(str(tmp_path), "mismatch", "坏", meta="---\nname: other\ndescription: d\nwhen_to_use: w\n---\n\n")
    with open(os.path.join(str(tmp_path), "agent", "skills", "bad.md"), "w") as f:
        f.write("not a skill")
    assert {s["name"] for s in sk.list_brief()} == {"good"}


def test_skills_view_missing(sk):
    with pytest.raises(SkillError_):
        sk.view("nonexistent")


def test_skills_search(sk, tmp_path):
    _write_skill(str(tmp_path), "viz-chart", "# c\n", meta=(
        "---\nname: viz-chart\ndescription: 把数据画成图表\nwhen_to_use: 需要可视化时\ntags: [echarts]\n---\n\n"))
    assert [s["name"] for s in sk.search("图表")] == ["viz-chart"]
    assert [s["name"] for s in sk.search("echarts")] == ["viz-chart"]
    assert sk.search("不存在的词") == []


def test_skills_illegal_name(sk):
    with pytest.raises(SkillError_):
        sk.view("../escape")


# ---------- 技能：Curator 30 天归档 ---------- #
def test_skills_archive_stale(sk, tmp_path):
    _write_skill(str(tmp_path), "fresh", "# f\n")
    _write_skill(str(tmp_path), "stale", "# s\n")
    old = time.time() - 40 * 86400
    os.utime(os.path.join(str(tmp_path), "agent", "skills", "stale"), (old, old))
    archived = sk.archive_stale()
    assert archived == ["stale"]
    assert os.path.isdir(os.path.join(str(tmp_path), "agent", "skills", "archived", "stale"))
    assert {s["name"] for s in sk.list_brief()} == {"fresh"}
    sk.unarchive("stale")
    assert {s["name"] for s in sk.list_brief()} == {"fresh", "stale"}


def test_skills_archive_keeps_recently_used(sk, tmp_path):
    _write_skill(str(tmp_path), "used", "# u\n")
    old = time.time() - 40 * 86400
    os.utime(os.path.join(str(tmp_path), "agent", "skills", "used"), (old, old))
    sk.touch("used")                      # 最近用过 → 不归档
    assert sk.archive_stale() == []


# ---------- server_tools（agent 可调用的服务端工具） ---------- #
def test_server_tool_memory_roundtrip(mem):
    r = asyncio.run(st_mod.memory_add("memory", "工具写入的记忆", tag="tool"))
    assert "已记录" in r
    r = asyncio.run(st_mod.memory_search("工具写入"))
    assert "工具写入的记忆" in r
    r = asyncio.run(st_mod.memory_patch("memory", "工具写入的记忆", "工具改写的记忆"))
    assert "已更新" in r
    r = asyncio.run(st_mod.memory_remove("memory", "工具改写的记忆"))
    assert "已从 memory 删除段落" in r
    assert mem.render("memory") == ""


def test_server_tool_memory_error_text_not_raise(mem):
    """操作失败返回错误文本（模型可自修正），不抛异常打断 run。"""
    r = asyncio.run(st_mod.memory_patch("memory", "不存在", "x"))
    assert "参数错误" in r
    r = asyncio.run(st_mod.memory_add("bad-scope", "x"))
    assert "参数错误" in r


def test_server_tool_memory_disabled(mem, monkeypatch):
    """.env 关 → guard 拦（文案指引 .env 与插件面板两处）。"""
    monkeypatch.setattr(mem_mod.settings, "AGENT_MEMORY_ENABLE", False)
    r = asyncio.run(st_mod.memory_search("x"))
    assert "已在配置/设置中关闭" in r


def test_server_tool_memory_disabled_via_plugin_panel(mem, monkeypatch, tmp_path):
    """设置页插件面板关（用户态）→ guard 同样拦：执行层 honoring 完整门控。"""
    from pypedia.plugins import plugin_registry

    monkeypatch.setenv("PYPEDIA_DATA", str(tmp_path))
    plugin_registry.set_enabled("agent-memory", False)
    r = asyncio.run(st_mod.memory_search("x"))
    assert "已在配置/设置中关闭" in r
    assert "插件管理" in r


def test_server_tool_skill_list_and_view(sk, tmp_path):
    _write_skill(str(tmp_path), "demo", "# demo 指令\n做演示。")
    r = asyncio.run(st_mod.skill_list())
    assert "demo" in r
    r = asyncio.run(st_mod.skill_view("demo"))
    assert "demo 指令" in r and "做演示" in r
    r = asyncio.run(st_mod.skill_view("missing"))
    assert "参数错误" in r


def test_server_tools_registered():
    names = {t.__name__ for t in st_mod.SERVER_TOOLS}
    assert names == {"memory_search", "memory_add", "memory_patch",
                     "memory_remove", "skill_list", "skill_view"}


# ---------- 端点 ---------- #
def test_memory_endpoint_readonly_view(client, mem):
    mem.add("memory", "端点可见的记忆", tag="ep")
    r = client.get("/api/agent/memory")
    assert r.status_code == 200
    body = r.json()
    assert "端点可见的记忆" in body["memory"]
    assert any("ep" in h for h in body["sections"]["memory"])


def test_memory_endpoint_disabled(client, monkeypatch):
    monkeypatch.setattr(mem_mod.settings, "AGENT_MEMORY_ENABLE", False)
    assert client.get("/api/agent/memory").status_code == 503


def test_skills_endpoint_list_and_detail(client, sk, tmp_path):
    _write_skill(str(tmp_path), "ep-skill", "# ep\n")
    r = client.get("/api/agent/skills")
    assert r.status_code == 200
    names = [s["name"] for s in r.json()["skills"]]
    assert "ep-skill" in names
    r = client.get("/api/agent/skills/ep-skill")
    assert r.status_code == 200 and r.json()["body"] == "# ep"
    assert client.get("/api/agent/skills/ep-skill").json()["usage"]["count"] >= 1


def test_skills_endpoint_404(client, sk):
    assert client.get("/api/agent/skills/nope").status_code == 404


def test_skills_endpoint_disabled(client, monkeypatch):
    monkeypatch.setattr(sk_mod.settings, "AGENT_SKILLS_ENABLE", False)
    assert client.get("/api/agent/skills").status_code == 503
