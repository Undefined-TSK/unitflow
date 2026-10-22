#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""真实测试②：新架构（万物皆插件内核）全链路真实测试。

与 e2e_editor / e2e_market（零 LLM、TestClient 打桩）的区别：本脚本起**真实
uvicorn 子进程** + **真实 LLM 调用**，验证新架构从「内核视图 → 问答 → 工具
循环 → 图校验/导出/安装 → 市场货架 → 前端资产」的完整生产链路。

链路（每步记录延迟）：
  1) /api/status             provider/模型/配置（真实）
  2) /api/units              内核 23+ 单元可见，python-encyclopedia 13 节点图在列
  3) /api/ask                真实 LLM 问答（旧管线入口仍在，双轨并存）
  4) /api/agent/step         真实 function calling 工具循环（可能多轮）
  5) /api/editor/validate    单 Agent 成品图校验
  6) /api/editor/export      导出 zip（根 plugin.json）
  7) /api/market/upload      同格式安装（版本门禁 + 双注册 + 账本）
  8) /api/market             货架可见已装 unit
  9) /api/units              安装后内核视图可见
 10) /api/market/units/{id}  卸载
 11) GET /                   前端页面 200（含编排 Beta 入口）
 12) /static/js/editor.js    前端资产 200 且含关键函数

用法：python3.11 scripts/e2e_real_fullchain.py [--skip-llm]
  --skip-llm：跳过 3/4 两步真实 LLM 调用（其余不变）。
退出码 0 = 全过；1 = 有失败项。
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 8791
BASE = f"http://127.0.0.1:{PORT}"
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


def req(path: str, *, method: str = "GET", body: bytes | None = None,
        ctype: str | None = None, timeout: int = 120) -> tuple[int, object]:
    r = urllib.request.Request(BASE + path, data=body, method=method)
    if ctype:
        r.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            raw = resp.read()
            ct = resp.headers.get("Content-Type", "")
            if "application/zip" in ct:
                return resp.status, raw
            if "json" in ct:
                return resp.status, json.loads(raw.decode("utf-8"))
            return resp.status, raw.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return e.code, raw


def post_json(path: str, payload: dict, timeout: int = 120) -> tuple[int, object]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return req(path, method="POST", body=body, ctype="application/json",
               timeout=timeout)


def start_server(data_dir: str, log) -> subprocess.Popen:
    env = dict(os.environ, PYPEDIA_DATA=data_dir, PYTHONPATH=str(ROOT))
    p = subprocess.Popen(
        [sys.executable, str(ROOT / "app.py"), "--no-browser",
         "--host", "127.0.0.1", "--port", str(PORT)],
        env=env, stdout=log, stderr=subprocess.STDOUT, cwd=str(ROOT))
    for _ in range(180):
        try:
            s, _ = req("/api/status", timeout=5)
            if s == 200:
                return p
        except Exception:
            pass
        if p.poll() is not None:
            raise RuntimeError(f"服务进程提前退出（code={p.returncode}），见日志")
        time.sleep(0.5)
    raise RuntimeError("服务 90s 内未就绪")


def stop_server(p: subprocess.Popen) -> None:
    p.send_signal(signal.SIGTERM)
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        p.kill()


def timed(fn) -> tuple[object, float]:
    t0 = time.perf_counter()
    r = fn()
    return r, time.perf_counter() - t0


def main() -> int:
    skip_llm = "--skip-llm" in sys.argv
    data_dir = tempfile.mkdtemp(prefix="pypedia-real-fullchain-")
    log_path = ROOT / "scripts" / "e2e_real_fullchain_server.log"
    print(f"== 真实测试②：新架构全链路（真实子进程 + 真实 LLM"
          f"{'，--skip-llm 跳过 LLM 两步' if skip_llm else ''}）==")
    print(f"数据目录：{data_dir}（隔离，不影响测试/生产数据）")
    with open(log_path, "w", encoding="utf-8") as log:
        srv = start_server(data_dir, log)
        try:
            run_checks(skip_llm)
        finally:
            stop_server(srv)
    ok = all(r[1] for r in RESULTS)
    print(f"\n服务日志：{log_path}")
    print(f"\n== 新架构全链路：{sum(1 for r in RESULTS if r[1])}/"
          f"{len(RESULTS)} 通过，整体 {'通过' if ok else '未通过'} ==")
    return 0 if ok else 1


def run_checks(skip_llm: bool) -> None:
    # 1) 状态
    (s, st), dt = timed(lambda: req("/api/status"))
    check("GET /api/status", s == 200 and "provider" in st,
          f"provider={st.get('provider')} model={st.get('model')} {dt:.1f}s")

    # 2) 单元列表 + 单 Agent 成品图
    (s, units), dt = timed(lambda: req("/api/units"))
    unit_list = units.get("units", []) if isinstance(units, dict) else []
    ids = [u.get("id") for u in unit_list]
    check("GET /api/units 内核单元可见", s == 200 and "python-encyclopedia" in ids,
          f"{len(ids)} 个单元，含 python-encyclopedia，{dt:.1f}s")
    (s, enc), _ = timed(lambda: req("/api/units/python-encyclopedia"))
    graph = ((enc.get("unit") or {}).get("node_graph") or {}) \
        if isinstance(enc, dict) else {}
    check("python-encyclopedia 13 节点图在列",
          len(graph.get("nodes", [])) == 13 and len(graph.get("edges", [])) == 13,
          f"nodes={len(graph.get('nodes', []))} edges={len(graph.get('edges', []))}")

    # 3) 真实问答（旧管线仍在，双轨并存）
    if skip_llm:
        check("POST /api/ask（--skip-llm 跳过）", True, "按参数跳过")
    else:
        (s, ask_r), dt = timed(lambda: post_json(
            "/api/ask", {"query": "Python 的 GIL 是什么？", "level": 3}))
        answer = ask_r.get("answer", "") if isinstance(ask_r, dict) else ""
        check("POST /api/ask 真实 LLM 问答",
              s == 200 and len(answer) > 50 and "confidence" in ask_r,
              f"{len(answer)} 字，置信度 "
              f"{(ask_r.get('confidence') or {}).get('score')}，{dt:.1f}s")

    # 4) 真实工具循环（function calling）
    if skip_llm:
        check("POST /api/agent/step（--skip-llm 跳过）", True, "按参数跳过")
    else:
        (s, step_r), dt = timed(lambda: post_json(
            "/api/agent/step", {"query": "帮我算 2 的 10 次方", "level": 3}))
        ok4 = s == 200 and step_r.get("type") in ("tool_calls", "final")
        detail4 = f"type={step_r.get('type')}，{dt:.1f}s"
        # 工具循环可能多轮：按协议续跑（上限 5 轮防失控）
        rounds = 0
        while (ok4 and s == 200 and step_r.get("type") == "tool_calls"
               and rounds < 5):
            rounds += 1
            results = [{"id": c.get("id"), "result": "1024"}
                       for c in step_r.get("calls", [])]
            (s, step_r), dt2 = timed(lambda: post_json(
                "/api/agent/step", {"state": step_r.get("state"),
                                    "tool_results": results, "level": 3}))
            ok4 = s == 200 and step_r.get("type") in ("tool_calls", "final")
            detail4 = (f"{rounds} 轮工具循环后 type={step_r.get('type')}，"
                       f"累计 {dt + dt2:.1f}s")
        check("POST /api/agent/step 真实工具循环", ok4, detail4)

    # 5) 图校验（编辑器端点，用内置单 Agent 成品图）
    (s, tpl), _ = timed(lambda: req("/api/editor/templates"))
    enc_graph = (tpl.get("encyclopedia") if isinstance(tpl, dict) else None) or {}
    (s, val), dt = timed(lambda: post_json(
        "/api/editor/validate", {"graph": enc_graph}))
    check("POST /api/editor/validate 成品图校验",
          s == 200 and val.get("ok") and not val.get("errors"),
          f"errors={val.get('errors')} {dt:.1f}s")

    # 6) 导出 zip
    (s, zbytes), dt = timed(lambda: req(
        "/api/editor/export", method="POST",
        body=json.dumps({"meta": {"id": "e2e-real-export",
                                  "type": "agent", "name": "真实测试导出"},
                         "graph": enc_graph}).encode("utf-8"),
        ctype="application/json"))
    with zipfile.ZipFile(__import__("io").BytesIO(zbytes)) as zf:
        names = zf.namelist()
        root_ok = "plugin.json" in names
    check("POST /api/editor/export 导出 zip",
          s == 200 and root_ok and isinstance(zbytes, bytes),
          f"zip {len(zbytes)} 字节，根 plugin.json={root_ok}，{dt:.1f}s")

    # 7) 市场安装（同格式互通，multipart/form-data —— UploadFile 契约）
    b = "----pypedia-e2e-real-boundary"
    mbody = (f"--{b}\r\n"
             f'Content-Disposition: form-data; name="file"; '
             f'filename="e2e-real-export.zip"\r\n'
             f"Content-Type: application/zip\r\n\r\n").encode("utf-8") \
        + zbytes + f"\r\n--{b}--\r\n".encode("utf-8")
    (s, inst), dt = timed(lambda: req(
        "/api/market/upload", method="POST", body=mbody,
        ctype=f"multipart/form-data; boundary={b}", timeout=60))
    check("POST /api/market/upload 安装导出包",
          s == 200 and (inst.get("id") == "e2e-real-export"
                        or "e2e-real-export" in json.dumps(inst, ensure_ascii=False)),
          f"{json.dumps(inst, ensure_ascii=False)[:120]} {dt:.1f}s")

    # 8) 货架可见
    (s, market), _ = timed(lambda: req("/api/market"))
    shelves = market.get("shelves", {}) if isinstance(market, dict) else {}
    shelf_ids = [u.get("id") for us in shelves.values() for u in us]
    check("GET /api/market 货架可见", "e2e-real-export" in shelf_ids,
          f"货架 {len(shelf_ids)} 项")

    # 9) 安装后内核视图可见
    (s, units2), _ = timed(lambda: req("/api/units"))
    ids2 = [u.get("id") for u in (units2.get("units", [])
                                  if isinstance(units2, dict) else [])]
    check("GET /api/units 安装后可见", "e2e-real-export" in ids2,
          f"{len(ids2)} 个单元")

    # 10) 卸载
    (s, del_r), dt = timed(lambda: req(
        "/api/market/units/e2e-real-export", method="DELETE"))
    check("DELETE /api/market/units/{id} 卸载", s == 200,
          f"{json.dumps(del_r, ensure_ascii=False)[:80]} {dt:.1f}s")
    (s, market2), _ = timed(lambda: req("/api/market"))
    shelves2 = market2.get("shelves", {}) if isinstance(market2, dict) else {}
    shelf2 = [u.get("id") for us in shelves2.values() for u in us]
    check("卸载后货架干净", "e2e-real-export" not in shelf2,
          f"货架剩 {len(shelf2)} 项")

    # 11) 前端页面
    (s, html), dt = timed(lambda: req("/"))
    check("GET / 前端页面", s == 200 and "p-editor" in html,
          f"{len(html)} 字节，含编排入口，{dt:.1f}s")

    # 12) 前端资产
    (s, js), _ = timed(lambda: req("/static/js/editor.js"))
    check("GET /static/js/editor.js", s == 200 and "edToGraph" in js,
          f"{len(js)} 字节，含 edToGraph")


if __name__ == "__main__":
    sys.exit(main())
