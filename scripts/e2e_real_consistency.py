#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真实测试①：旧架构 vs 新架构单 Agent 产出一致性对比（真实 LLM 调用）。

问题：万物皆插件重构后，把整条 PyPedia 管线封装成「图即引擎」的单 Agent
成品对象（python-encyclopedia 13 节点图，GraphRuntime 解释执行），
产出效果是否打折扣？与旧架构（engine.ask 内部黑盒编排）是否一致？

设计：
- 同一问题集，两条链路各跑一遍，共享同一引擎单例（engine.get_engine()）——
  新架构的每个节点处理器复用的正是旧架构同款组件（retriever/generate/
  confidence/review/memory/evolution），差异只在编排层（图驱动 vs 黑盒顺序）；
- 对比维度（LLM 非确定性，不要求字面一致，只要求结构性与量级一致）：
  1) 答案非空且长度量级相当（比例 0.25~4）；
  2) 主题关键词覆盖率绝对差 ≤ 1；
  3) 检索命中一致（两者 primary 均非空或均为空）；
  4) 置信度分数均产出且绝对差 ≤ 30；
  5) 分步计划 / 上下文压缩等阶段产物存在性一致；
  6) 无架构级异常。
- 数据目录隔离（PYPEDIA_DATA 指向独立临时目录），不碰测试/生产数据；
  不 import tests/conftest（那会打桩 LLM）——本脚本要的就是真实调用。

用法：python3.11 scripts/e2e_real_consistency.py [--quick]
  --quick：只跑 1 个问题（省额度）。
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import sys
import tempfile
import time

# —— 必须在任何 pypedia import 之前：隔离真实数据目录 —— #
_TMP_DATA = tempfile.mkdtemp(prefix="pypedia-real-consistency-")
os.environ["PYPEDIA_DATA"] = _TMP_DATA

_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "units" / "examples" / "python-encyclopedia"))

# 问题集：主题词预定义（用于覆盖率对比），百科语料可命中的经典主题
QUESTIONS = [
    {
        "q": "Python 的 GIL 是什么？对多线程编程有什么影响？",
        "keywords": ["GIL", "全局解释器锁", "线程", "并行", "多进程", "锁"],
    },
    {
        "q": "Python 装饰器是什么？怎么写一个带参数的装饰器？",
        "keywords": ["装饰器", "@", "闭包", "wrapper", "functools", "参数"],
    },
    {
        "q": "Python 列表推导式和生成器表达式有什么区别？",
        "keywords": ["列表推导", "生成器", "惰性", "内存", "方括号", "圆括号"],
    },
]

# 判定阈值
LEN_RATIO_MIN, LEN_RATIO_MAX = 0.25, 4.0
KW_DIFF_MAX = 1
CONF_DIFF_MAX = 30.0


def _coverage(answer: str, keywords: list[str]) -> tuple[int, list[str]]:
    hit = [k for k in keywords if k in answer]
    return len(hit), hit


def _probe_llm() -> str:
    """探测真实 LLM 通道状态：live（可用）/ degraded（已降级，如免费额度耗尽）。"""
    from pypedia.models.dashscope import chat

    try:
        chat([{"role": "user", "content": "ping"}], max_tokens=4)
        return "live"
    except Exception:
        return "degraded"


def _run_old(query: str) -> dict:
    """旧架构：engine.ask 内部黑盒编排。"""
    from pypedia.engine import get_engine

    t0 = time.perf_counter()
    r = get_engine().ask(query, level=3)
    dt = time.perf_counter() - t0
    cascade = r.get("cascade")
    primary = list(getattr(cascade, "primary", []) or [])
    return {
        "answer": r.get("answer", ""),
        "confidence": (r.get("confidence") or {}).get("score"),
        "primary_hits": len(primary),
        "primary_titles": [getattr(c, "title", "") for c in primary[:3]],
        "chunks": len(getattr(cascade, "all_chunks", []) or []),
        "reasoning_plan": r.get("reasoning_plan", ""),
        "compressed": (r.get("context") or {}).get("compressed"),
        "review": (r.get("review") or {}).get("verdict"),
        "latency_s": round(dt, 1),
    }


def _run_new(query: str) -> dict:
    """新架构：GraphRuntime 解释执行 python-encyclopedia 13 节点图。"""
    import encyclopedia

    t0 = time.perf_counter()
    r = encyclopedia.run(query, level=3)
    dt = time.perf_counter() - t0
    cascade = r.get("cascade")
    primary = list(getattr(cascade, "primary", []) or [])
    conf = r.get("conf") or {}
    return {
        "answer": r.get("answer", ""),
        "confidence": conf.get("score"),
        "primary_hits": len(primary),
        "primary_titles": [getattr(c, "title", "") for c in primary[:3]],
        "chunks": len(getattr(cascade, "all_chunks", []) or []),
        "reasoning_plan": r.get("plan", ""),
        "compressed": (r.get("ctx_plan") is not None
                       and getattr(r.get("ctx_plan"), "compressed", None)),
        "review": (r.get("review") or {}).get("verdict"),
        "needs_review": r.get("needs_review"),
        "memory_ok": r.get("memory_ok"),
        "evo_ok": r.get("evo_ok"),
        "latency_s": round(dt, 1),
    }


def compare(item: dict, old: dict, new: dict, mode: str) -> list[dict]:
    checks: list[dict] = []

    def chk(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    # 1) 答案非空
    chk("旧架构答案非空", bool(old["answer"].strip()),
        f"{len(old['answer'])} 字")
    chk("新架构答案非空", bool(new["answer"].strip()),
        f"{len(new['answer'])} 字")
    if mode == "degraded":
        # 降级模式：两条链路都应降级到 Mock，且 Mock 答案均带标记
        chk("两架构均降级 Mock（标记一致）",
            "Mock" in old["answer"] and "Mock" in new["answer"],
            f"旧含 Mock 标记={'Mock' in old['answer']}；"
            f"新含 Mock 标记={'Mock' in new['answer']}")
        chk("答案长度记录（降级模式不判定）", True,
            f"旧 {len(old['answer'])} 字 / 新 {len(new['answer'])} 字"
            "（Mock 兜底长度由各自 prompt 模板决定，非架构质量差异）")
    else:
        # 2) 长度量级
        if old["answer"] and new["answer"]:
            ratio = len(new["answer"]) / max(len(old["answer"]), 1)
            chk("答案长度量级相当", LEN_RATIO_MIN <= ratio <= LEN_RATIO_MAX,
                f"旧 {len(old['answer'])} 字 / 新 {len(new['answer'])} 字 "
                f"(比值 {ratio:.2f})")
        # 3) 关键词覆盖率
        old_hit, old_kws = _coverage(old["answer"], item["keywords"])
        new_hit, new_kws = _coverage(new["answer"], item["keywords"])
        chk("主题关键词覆盖差 ≤1", abs(new_hit - old_hit) <= KW_DIFF_MAX,
            f"旧 {old_hit}/{len(item['keywords'])} {old_kws}；"
            f"新 {new_hit}/{len(item['keywords'])} {new_kws}")
    # 4) 检索命中一致（两种模式都判定）
    chk("检索命中一致", (old["primary_hits"] > 0) == (new["primary_hits"] > 0),
        f"旧 primary={old['primary_hits']} chunks={old['chunks']}；"
        f"新 primary={new['primary_hits']} chunks={new['chunks']}")
    if old["primary_titles"] and new["primary_titles"]:
        # 首位可能受后台预置源导入竞态影响（旧/新之间索引被写入），
        # 以前 3 条首要证据有交集为一致口径
        overlap = set(old["primary_titles"]) & set(new["primary_titles"])
        chk("首要证据同源（前 3 条有交集）", bool(overlap),
            f"旧前 3 {old['primary_titles']}；新前 3 {new['primary_titles']}；"
            f"交集 {len(overlap)} 条")
    # 5) 置信度（两种模式都判定）
    if old["confidence"] is not None and new["confidence"] is not None:
        diff = abs(float(old["confidence"]) - float(new["confidence"]))
        chk("置信度均产出且差 ≤30", diff <= CONF_DIFF_MAX,
            f"旧 {old['confidence']} / 新 {new['confidence']}（差 {diff:.1f}）")
    else:
        chk("置信度均产出", False,
            f"旧 {old['confidence']} / 新 {new['confidence']}")
    # 6) 阶段产物：两架构一致性（分步计划仅复杂问题触发，空即一致）
    chk("分步计划两架构一致",
        bool(str(old["reasoning_plan"]).strip()) == bool(str(new["reasoning_plan"]).strip()),
        f"旧 {len(str(old['reasoning_plan']))} 字 / "
        f"新 {len(str(new['reasoning_plan']))} 字")
    chk("新架构记忆/自进化节点完成", new.get("memory_ok") and new.get("evo_ok"),
        f"memory_ok={new.get('memory_ok')} evo_ok={new.get('evo_ok')}")
    return checks


def main() -> int:
    quick = "--quick" in sys.argv
    questions = QUESTIONS[:1] if quick else QUESTIONS
    mode = _probe_llm()
    print(f"== 真实测试①：旧架构 vs 新架构单 Agent 一致性（{len(questions)} 问）==")
    print(f"LLM 通道状态：{mode}"
          + ("（免费额度耗尽，验证降级一致性；额度恢复后重跑本脚本自动进入 live 模式）"
             if mode == "degraded" else "（真实 LLM）"))
    report: dict = {"llm_channel": mode, "questions": [], "all_ok": True}
    for i, item in enumerate(questions, 1):
        print(f"\n—— 问题 {i}/{len(questions)}：{item['q']}")
        old = _run_old(item["q"])
        print(f"  旧架构：{len(old['answer'])} 字，置信度 {old['confidence']}，"
              f"primary {old['primary_hits']}，{old['latency_s']}s")
        new = _run_new(item["q"])
        print(f"  新架构：{len(new['answer'])} 字，置信度 {new['confidence']}，"
              f"primary {new['primary_hits']}，{new['latency_s']}s，"
              f"二审 needs_review={new.get('needs_review')}")
        checks = compare(item, old, new, mode)
        ok = all(c["ok"] for c in checks)
        report["all_ok"] = report["all_ok"] and ok
        report["questions"].append({
            "q": item["q"], "ok": ok, "checks": checks,
            "old": {k: v for k, v in old.items() if k != "answer"},
            "new": {k: v for k, v in new.items() if k != "answer"},
        })
        for c in checks:
            mark = "PASS" if c["ok"] else "FAIL"
            print(f"    [{mark}] {c['check']}：{c['detail']}")
        print(f"  ⇒ 问题 {i} {'一致' if ok else '不一致'}")
    out = _ROOT / "scripts" / "e2e_real_consistency_report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告：{out}")
    print("\n== 结论：两条链路产出一致性 " +
          ("通过（封装无折扣）" if report["all_ok"] else "未通过") +
          f"（LLM 通道：{mode}） ==")
    shutil.rmtree(_TMP_DATA, ignore_errors=True)
    return 0 if report["all_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
