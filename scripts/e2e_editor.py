"""P7 节点编辑器 v1 端到端验收（真实子进程，API 级）。

链路：起服务 → 模板（minimal/encyclopedia/node_types）→ 校验（好图/坏图/
内置模板）→ 导出 zip（根 plugin.json）→ 安装（市场同通道）→ /api/units 可见
→ 图上节点图往返无损 → 版本门禁 400 不落盘 → 卸载 → 前端资产在位。
零 LLM 调用（不触发 /api/ask）；执行正确性由单测
``tests/test_p7_editor.py::test_export_install_execute``（execute(21)=42）锁定。

用法：
    python3.11 scripts/e2e_editor.py
退出码 0 = 全过；1 = 有失败项（明细打印到 stdout）。
"""
from __future__ import annotations

import io
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
PORT = 8766
BASE = f"http://127.0.0.1:{PORT}"
RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))


def req(path: str, *, method: str = "GET", body: bytes | None = None,
        ctype: str | None = None) -> tuple[int, object]:
    r = urllib.request.Request(BASE + path, data=body, method=method)
    if ctype:
        r.add_header("Content-Type", ctype)
    try:
        with urllib.request.urlopen(r, timeout=15) as resp:
            raw = resp.read()
            ct = resp.headers.get("Content-Type", "")
            if "application/zip" in ct:
                return resp.status, raw          # 二进制：zip 字节
            if "json" in ct:
                return resp.status, json.loads(raw.decode("utf-8"))
            return resp.status, raw.decode("utf-8", "replace")  # 静态文本
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return e.code, raw


def post_json(path: str, payload: dict) -> tuple[int, object]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return req(path, method="POST", body=body, ctype="application/json")


DOUBLE_GRAPH = {
    "nodes": [
        {"id": "e", "type": "entry"},
        {"id": "p", "type": "process", "params": {"expr": "payload * 2"}},
        {"id": "x", "type": "exit"},
    ],
    "edges": [{"from": "e", "to": "p"}, {"from": "p", "to": "x"}],
}


def start_server(data_dir: str, log) -> subprocess.Popen:
    env = dict(os.environ, PYPEDIA_DATA=data_dir, PYTHONPATH=str(ROOT))
    p = subprocess.Popen(
        [sys.executable, str(ROOT / "app.py"), "--no-browser",
         "--host", "127.0.0.1", "--port", str(PORT)],
        env=env, stdout=log, stderr=subprocess.STDOUT, cwd=str(ROOT))
    # 首次启动含示例语料导入/MCP 连接，放宽到 90s（0.5s 轮询）
    for _ in range(180):
        try:
            s, _ = req("/api/status")
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


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="pypedia-e2e-editor-")
    log = open(Path(tmp) / "server.log", "w", encoding="utf-8")
    p = None
    try:
        p = start_server(tmp, log)

        # 1. 模板
        s, d = req("/api/editor/templates")
        check("GET /api/editor/templates", s == 200 and
              len(d["minimal"]["nodes"]) == 3 and
              len(d["encyclopedia"]["nodes"]) == 13 and
              len(d["node_types"]) == 6,
              f"minimal={len(d.get('minimal', {}).get('nodes', []))} "
              f"encyclopedia={len(d.get('encyclopedia', {}).get('nodes', []))}")

        # 2. 校验：好图 / 坏图（三类错误一次报全）/ 内置成品模板
        s, d = post_json("/api/editor/validate",
                         {"graph": d["minimal"] if s == 200 else DOUBLE_GRAPH})
        check("校验好图 → ok", s == 200 and d["ok"] and d["errors"] == [])

        bad = {"nodes": [{"id": "a", "type": "entry"},
                         {"id": "a", "type": "process",
                          "params": {"expr": "1 +"}},
                         {"id": "x", "type": "exit"}],
               "edges": [{"from": "a", "to": "x"},
                         {"from": "ghost", "to": "x"}]}
        s, d = post_json("/api/editor/validate", {"graph": bad})
        check("校验坏图 → 三类错误（重复 id/语法/边引用）",
              s == 200 and not d["ok"] and len(d["errors"]) >= 3,
              f"{len(d.get('errors', []))} 个错误")

        s, d = req("/api/editor/templates")
        s2, d2 = post_json("/api/editor/validate", {"graph": d["encyclopedia"]})
        check("内置 encyclopedia 模板校验通过", s2 == 200 and d2["ok"],
              "; ".join(d2.get("errors", [])[:2]))

        # 3. 导出：zip + 根 plugin.json + 图随身
        s, blob = post_json("/api/editor/export",
                            {"graph": DOUBLE_GRAPH,
                             "meta": {"id": "e2e-editor-export"}})
        zip_ok = False
        graph_nodes = 0
        if s == 200 and isinstance(blob, bytes):
            with zipfile.ZipFile(io.BytesIO(blob)) as zf:
                m = json.loads(zf.read("plugin.json").decode("utf-8"))
                zip_ok = m["id"] == "e2e-editor-export"
                graph_nodes = len(m["node_graph"]["nodes"])
        check("POST /api/editor/export → zip（根 plugin.json + node_graph）",
              s == 200 and zip_ok and graph_nodes == 3,
              f"status={s} nodes={graph_nodes}")

        # 4. 安装（市场同一通道）→ /api/units 可见 → 图上节点图往返无损
        s, d = post_json("/api/editor/install",
                         {"graph": DOUBLE_GRAPH,
                          "meta": {"id": "e2e-editor-install",
                                   "name": "编辑器直装"}})
        check("POST /api/editor/install → 200", s == 200 and
              d["installed"]["id"] == "e2e-editor-install", d.get("detail", ""))

        s, d = req("/api/units")
        row = next((u for u in d["units"]
                    if u["id"] == "e2e-editor-install"), None)
        check("/api/units 含编辑器安装的 unit 且 enabled", row is not None
              and row["enabled"])

        s, d = req("/api/units/e2e-editor-install")
        ng = (d.get("unit") or {}).get("node_graph") or {}
        exprs = [n.get("params", {}).get("expr")
                 for n in ng.get("nodes", []) if n["type"] == "process"]
        check("安装后 node_graph 往返无损（expr 保真）",
              s == 200 and len(ng.get("nodes", [])) == 3
              and exprs == ["payload * 2"], f"exprs={exprs}")

        # 5. 元信息 / 版本门禁
        s, d = post_json("/api/editor/install",
                         {"graph": DOUBLE_GRAPH, "meta": {}})
        check("meta 缺 id → 400", s == 400 and "unit id" in d.get("detail", ""))

        s, d = post_json("/api/editor/install",
                         {"graph": DOUBLE_GRAPH,
                          "meta": {"id": "e2e-editor-gate",
                                   "min_platform": "99.0.0"}})
        check("版本门禁 → 400 且不落盘",
              s == 400 and "平台版本不满足" in d.get("detail", ""))
        s, d = req("/api/units")
        gate_gone = not any(u["id"] == "e2e-editor-gate" for u in d["units"])
        check("门禁不过不落盘", gate_gone)

        # 6. 导出的 zip 走市场端点上架（同格式互通）
        s, blob = post_json("/api/editor/export",
                            {"graph": DOUBLE_GRAPH,
                             "meta": {"id": "e2e-editor-interop"}})
        b = "----pypedia-e2e-editor"
        body = (f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; "
                f"filename=\"e2e-editor-interop.zip\"\r\n"
                f"Content-Type: application/zip\r\n\r\n").encode() + blob + \
            f"\r\n--{b}--\r\n".encode()
        s, d = req("/api/market/upload", method="POST", body=body,
                   ctype=f"multipart/form-data; boundary={b}")
        check("导出 zip → /api/market/upload 互通", s == 200 and
              d["installed"]["id"] == "e2e-editor-interop", d.get("detail", ""))

        # 7. 前端资产在位（画布线）
        s, raw = req("/static/js/editor.js")
        check("GET /static/js/editor.js", s == 200 and
              isinstance(raw, str) and "edToGraph" in raw)
        s, raw = req("/static/index.html")
        check("GET /static/index.html 含编辑器页", s == 200 and
              isinstance(raw, str) and 'id="p-editor"' in raw)

        # 8. 卸载收尾
        for uid in ("e2e-editor-install", "e2e-editor-interop"):
            s, d = req(f"/api/market/units/{uid}", method="DELETE")
            check(f"卸载 {uid}", s == 200, d.get("detail", ""))
        s, d = req("/api/market")
        check("货架最终为空", all(not v for v in d["shelves"].values()))
    finally:
        if p is not None:
            stop_server(p)
        log.close()

    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
