"""P6 市场 v1 端到端验收（真实子进程，API 级）。

链路：起服务 → 货架空 → 上传 zip（含工具/规约/自声明规则）→ /api/units 可见
→ 详情 → 卸内置 400 → 卸载 → 货架空 → 重启（同数据目录）→ 保留包仍在 →
清理。零 LLM 调用（不触发 /api/ask）。

用法：
    python3.11 scripts/e2e_market.py
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
PORT = 8765
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
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode("utf-8"))


def multipart(field: str, filename: str, blob: bytes) -> tuple[bytes, str]:
    b = "----pypedia-e2e"
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"{field}\"; "
            f"filename=\"{filename}\"\r\nContent-Type: application/zip\r\n\r\n"
            ).encode() + blob + f"\r\n--{b}--\r\n".encode()
    return body, f"multipart/form-data; boundary={b}"


def make_pkg(uid: str, *, min_platform: str = "0.1.0") -> bytes:
    manifest = {
        "id": uid, "type": "plugin", "name": f"E2E {uid}",
        "version": "1.0.0", "description": "e2e_market 冒烟包",
        "min_platform": min_platform, "dependencies": [],
        "default_enabled": True, "switchable": True, "env_gate": "",
        "apply": "immediate",
        "contributions": {
            "system_prompt_sections": [
                {"name": f"{uid}:guide", "order": 40, "text": f"{uid} 规约。"}],
            "rules": [{"id": f"{uid}:always", "when": {"always": True},
                       "then": {"activate": [uid]}}],
        },
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{uid}/plugin.json", json.dumps(manifest, ensure_ascii=False))
        zf.writestr(f"{uid}/README.md", f"# {uid}\n")
    return buf.getvalue()


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
    tmp = tempfile.mkdtemp(prefix="pypedia-e2e-market-")
    log = open(Path(tmp) / "server.log", "w", encoding="utf-8")
    p = None
    try:
        p = start_server(tmp, log)

        s, d = req("/api/market")
        check("GET /api/market 空货架", s == 200 and
              all(not v for v in d["shelves"].values()) and
              d["platform_version"], f"v{d.get('platform_version')}")

        body, ctype = multipart("file", "e2e-smoke.zip", make_pkg("e2e-smoke"))
        s, d = req("/api/market/upload", method="POST", body=body, ctype=ctype)
        check("POST /api/market/upload", s == 200 and
              d["installed"]["id"] == "e2e-smoke", d.get("detail", ""))

        s, d = req("/api/units")
        row = next((u for u in d["units"] if u["id"] == "e2e-smoke"), None)
        check("/api/units 含新装 unit 且 enabled", row is not None and row["enabled"])

        s, d = req("/api/units/e2e-smoke")
        check("GET /api/units/{id} 详情", s == 200 and
              d["unit"]["contributions"].get("system_prompt_sections"))

        s, d = req("/api/market")
        shelf = d["shelves"]["plugin"]
        check("货架出现 e2e-smoke（成品态）",
              len(shelf) == 1 and shelf[0]["form"] == "instance" and
              shelf[0]["enabled"])

        s, d = req("/api/market/units/agent-memory", method="DELETE")
        check("卸内置被拒（400）", s == 400 and "不是市场安装的" in d.get("detail", ""))

        # 版本门禁：坏平台版本 → 400 不落盘
        body, ctype = multipart("file", "e2e-gate.zip",
                                make_pkg("e2e-gate", min_platform="99.0.0"))
        s, d = req("/api/market/upload", method="POST", body=body, ctype=ctype)
        check("版本门禁拒收（400）", s == 400 and "平台版本不满足" in d.get("detail", ""))
        s, d = req("/api/units")
        check("门禁不过不落盘", not any(u["id"] == "e2e-gate" for u in d["units"]))

        # 重启恢复：装保留包 → 重启 → 仍在 → 卸载冒烟包 → 货架空
        body, ctype = multipart("file", "e2e-keep.zip", make_pkg("e2e-keep"))
        s, _ = req("/api/market/upload", method="POST", body=body, ctype=ctype)
        check("安装保留包 e2e-keep", s == 200)

        stop_server(p)
        p = start_server(tmp, log)
        s, d = req("/api/units")
        row = next((u for u in d["units"] if u["id"] == "e2e-keep"), None)
        check("重启后 e2e-keep 恢复注册", row is not None and row["enabled"])

        s, d = req("/api/market/units/e2e-smoke", method="DELETE")
        check("卸载 e2e-smoke", s == 200)
        s, d = req("/api/units")
        check("卸载后 /api/units 不可见",
              not any(u["id"] == "e2e-smoke" for u in d["units"]))
        s, d = req("/api/market/units/e2e-keep", method="DELETE")
        check("卸载 e2e-keep", s == 200)
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
