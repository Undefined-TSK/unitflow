#!/usr/bin/env python3
"""PyPedia 性能基准——零真实 LLM 调用（MockEmbedding + 打桩 chat），可反复跑。

测量四项：
  1. 索引写入吞吐：N 个文档分块写入 LanceDB（MockEmbedding 向量化）
  2. 检索延迟：向量 + BM25(jieba) 混合检索的 P50 / P95 / P99（rerank 自动降级向量分）
  3. Token 吞吐：textutil.tokens 分词 + conversation.estimate_tokens 估算
  4. 打桩 ask 延迟：引擎全链路（检索→提示词→生成→置信度→二审→沉淀）端到端

用法：
    python3 scripts/benchmark.py [--docs 200] [--queries 60] [--ask 20] [--json out.json]
说明：
  · 数据目录用临时目录（不碰真实 ~/.pypedia），跑完自动清理；
  · 结果为量级参考：不同机器（尤其磁盘与 CPU）绝对值会有差异，纵向对比看回归。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import sys
import tempfile
import time
from pathlib import Path

# —— 必须在 import pypedia 之前：隔离数据目录 + 清空密钥（防误调真实 API） —— #
_TMP = tempfile.mkdtemp(prefix="pypedia-bench-")
os.environ["PYPEDIA_DATA"] = _TMP
os.environ["BAILIAN_API_KEY"] = ""
os.environ["DASHSCOPE_API_KEY"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 项目根入路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))  # 共享 stub

import logging  # noqa: E402

import pypedia.rag as rag  # noqa: E402

# 重型依赖桩与 tests/conftest.py 共用单一来源（tests/stubs.py），防止两处定义漂移
from stubs import install_engine_stubs, stub_rag_embeddings  # noqa: E402

stub_rag_embeddings()

# 基准输出保持干净：引擎 INFO 日志（ask_done 等）不进控制台
logging.getLogger("pypedia").setLevel(logging.ERROR)

from pypedia import engine as eng  # noqa: E402
from pypedia.config import settings  # noqa: E402
from pypedia.conversation import ConversationContext  # noqa: E402
from pypedia.engine import PyPediaEngine  # noqa: E402
from pypedia.memory import Session  # noqa: E402
from pypedia.textutil import tokens as zh_tokens  # noqa: E402

BENCH_DIR = Path(_TMP) / "bench_vec"


# —— 工具 —— #
def _pct(vals: list[float], p: float) -> float:
    """最近秩百分位（小样本下比插值法更稳）。"""
    if not vals:
        return 0.0
    s = sorted(vals)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


def _row(name: str, value: str, note: str = "") -> str:
    return f"  {name:<22}{value:>18}   {note}"


# —— 1. 索引写入吞吐 —— #
def bench_index_write(n_docs: int) -> dict:
    idx = rag.KnowledgeIndex(persist_dir=BENCH_DIR)
    # 构造中等长度中文文档（贴近真实知识库语料形状）
    base = ("Python 装饰器本质上是一个接收函数并返回函数的可调用对象，"
            "常用于横切关注点如日志、缓存与权限校验。")
    docs = [{
        "text": base * 3 + f"\n\n第 {i} 段：上下文管理器通过 __enter__/__exit__ 协议管理资源。",
        "source": f"bench://doc-{i}", "title": f"基准文档 {i}",
        "url": "", "freshness": 1.0, "tags": ["bench"],
        "src_id": f"bench-doc-{i}",
    } for i in range(n_docs)]
    t0 = time.perf_counter()
    chunks = idx.add("supplement_b", docs)
    dt = time.perf_counter() - t0
    return {"docs": n_docs, "chunks": chunks, "seconds": round(dt, 3),
            "chunks_per_sec": round(chunks / dt, 1) if dt else 0.0}


# —— 2. 检索延迟 —— #
def bench_search(idx: rag.KnowledgeIndex, n_queries: int) -> dict:
    queries = [f"装饰器 上下文管理器 基准文档 {i}" for i in range(n_queries)]
    # 预热（首查含表加载/BM25 缓存构建）
    idx.search(queries[0], top_k=5)
    lat: list[float] = []
    for q in queries:
        t0 = time.perf_counter()
        idx.search(q, top_k=5)
        lat.append((time.perf_counter() - t0) * 1000)
    return {"queries": n_queries, "p50_ms": round(_pct(lat, 50), 2),
            "p95_ms": round(_pct(lat, 95), 2), "p99_ms": round(_pct(lat, 99), 2),
            "mean_ms": round(statistics.fmean(lat), 2)}


# —— 3. Token 吞吐 —— #
def bench_tokens() -> dict:
    corpus = "装饰器 上下文管理器 生成器 异步 类型标注 " * 400
    t0 = time.perf_counter()
    n = 0
    for _ in range(20):
        n += len(zh_tokens(corpus))
    dt = time.perf_counter() - t0
    toks_per_sec = round(n / dt) if dt else 0

    ctx = ConversationContext(session_id="bench")
    turns = [("装饰器怎么用？", "装饰器是…")] * 200
    t0 = time.perf_counter()
    plan = ctx.plan([type("T", (), {"user": u, "assistant": a})() for u, a in turns])
    dt2 = time.perf_counter() - t0
    return {"tokens_per_sec": toks_per_sec,
            "context_plan_ms": round(dt2 * 1000, 2),
            "context_total_tokens": plan.total_tokens,
            "context_compressed": plan.compressed}


# —— 4. 打桩 ask 全链路 —— #
def _stub_engine_deps() -> None:
    """把引擎的重型依赖换成 no-op（与 tests/conftest 共用 tests/stubs.py，零真实 API）。"""
    # Mem0 / MCP / 自进化反思 / 预置抓取：共享桩（tests/stubs.py）
    install_engine_stubs()
    # 以下为基准特有的确定性回答（保持测量稳定）
    eng.bailian_chat = lambda messages, **kw: "打桩回答：装饰器是接收函数返回函数的可调用对象。[1]"
    eng.evaluate_confidence = lambda *a, **kw: {
        "score": 72, "level": "中", "level_label": "中", "reason": "bench",
        "breakdown": {"primary_hit": 55, "cross_source": 30, "freshness": 12.0}}
    eng.review_answer = lambda *a, **kw: {
        "verdict": "pass", "notes": [], "revised": "", "skipped": True}


def bench_ask(n_ask: int) -> dict:
    _stub_engine_deps()
    engine = PyPediaEngine()
    session = Session(level=3)
    lat: list[float] = []
    for i in range(n_ask):
        q = f"装饰器和上下文管理器有什么区别？第 {i} 次"
        t0 = time.perf_counter()
        engine.ask(q, level=3, session=session)
        lat.append((time.perf_counter() - t0) * 1000)
    return {"asks": n_ask, "p50_ms": round(_pct(lat, 50), 2),
            "p95_ms": round(_pct(lat, 95), 2), "mean_ms": round(statistics.fmean(lat), 2)}


def main() -> None:
    ap = argparse.ArgumentParser(description="PyPedia 性能基准（零真实 LLM 调用）")
    ap.add_argument("--docs", type=int, default=200, help="索引写入文档数")
    ap.add_argument("--queries", type=int, default=60, help="检索测量次数")
    ap.add_argument("--ask", type=int, default=20, help="打桩 ask 测量次数")
    ap.add_argument("--json", type=str, default="", help="结果另存为 JSON 的路径")
    args = ap.parse_args()

    print(f"PyPedia 性能基准（MockEmbedding + 打桩 chat，零真实 LLM 调用）")
    print(f"数据目录：{_TMP}（临时，跑完清理）  LLM_PROVIDER={settings.LLM_PROVIDER}\n")

    w = bench_index_write(args.docs)
    print(f"[1] 索引写入（{w['docs']} 文档 → {w['chunks']} 块）")
    print(_row("总耗时", f"{w['seconds']}s"))
    print(_row("吞吐", f"{w['chunks_per_sec']} 块/s", "MockEmbedding 向量化 + LanceDB 落盘"))

    idx = rag.KnowledgeIndex(persist_dir=BENCH_DIR)
    s = bench_search(idx, args.queries)
    print(f"\n[2] 混合检索延迟（向量 + BM25/jieba，{s['queries']} 次）")
    print(_row("P50", f"{s['p50_ms']}ms"))
    print(_row("P95", f"{s['p95_ms']}ms", "桌面单机可接受 < 500ms"))
    print(_row("P99", f"{s['p99_ms']}ms"))
    print(_row("均值", f"{s['mean_ms']}ms"))

    t = bench_tokens()
    print("\n[3] Token 估算吞吐")
    print(_row("分词", f"{t['tokens_per_sec']} tokens/s", "jieba 中文分词"))
    print(_row("上下文规划", f"{t['context_plan_ms']}ms",
               f"{t['context_total_tokens']} tokens，压缩={t['context_compressed']}"))

    a = bench_ask(args.ask)
    print(f"\n[4] 打桩 ask 全链路（{a['asks']} 次）")
    print(_row("P50", f"{a['p50_ms']}ms", "检索+提示词+生成+置信度+二审+沉淀"))
    print(_row("P95", f"{a['p95_ms']}ms"))
    print(_row("均值", f"{a['mean_ms']}ms", "生成打桩；真实 LLM 延迟另计（数百 ms~数 s）"))

    result = {"write": w, "search": s, "tokens": t, "ask": a,
              "env": {"data_dir": _TMP, "provider": settings.LLM_PROVIDER}}
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
        print(f"\n结果已写入 {args.json}")
    shutil.rmtree(_TMP, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
