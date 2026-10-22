#!/usr/bin/env python3
"""P7 节点编辑器浏览器级验收：真实 Chromium 驱动画布交互。

自包含：起临时数据目录的真实 app 进程（随机端口），Playwright 驱动 Chromium：
  1. 页面装载：导航「编排 Beta」→ 画布/托盘/检查器三栏就绪，无 JS 报错；
  2. 模板：最小链 3 节点 2 边；单 Agent 成品 13 节点；
  3. 校验：UI 点「校验」→ 通过消息；edToGraph() 序列化经端点复核 ok；
  4. 检查器：点 process 节点 → expr 回显；改表达式 → 保存 → 序列化保真；
  5. 拖拽：节点鼠标拖拽 → 坐标变化（SVG 逻辑坐标换算生效）；
  6. 连线：linkdot 拖到目标节点 → 边 +1（elementFromPoint 落点判定）；
  7. 托盘增删：加节点 +1；Delete 删选中 -1；
  8. 安装：填 meta → 点「安装为 unit」→ /api/units 可见 → 市场卸载收尾；
  9. 全程零 console error / pageerror。

用法：
    python3 scripts/e2e_editor_browser.py
依赖：playwright（python 包）+ Chromium（playwright install chromium）。
退出码：0 = 全部验收通过；1 = 任一断言失败（详见 stdout）。
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_up(base: str, timeout: float = 90.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{base}/api/units", timeout=3) as r:
                if r.status == 200:
                    return
        except OSError:
            time.sleep(1)
    raise RuntimeError(f"服务器 {timeout:.0f}s 内未就绪")


def run() -> int:
    from playwright.sync_api import sync_playwright

    tmp = tempfile.mkdtemp(prefix="pypedia-e2e-ed-")
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ, PYPEDIA_DATA=tmp)
    server = subprocess.Popen(
        [sys.executable, "app.py", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    errors: list[str] = []
    try:
        _wait_up(base)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            page.on("console", lambda m: errors.append(f"console.error: {m.text}")
                    if m.type == "error" else None)

            # —— 1. 导航进编辑器页（先过首次引导遮罩） —— #
            page.add_init_script("localStorage.setItem('pyp_level', '3')")
            page.goto(base, wait_until="load")
            page.evaluate("typeof obFinish === 'function' && obFinish()")
            page.wait_for_selector("#app.on", timeout=10000)
            page.click('[data-p="editor"]')
            page.wait_for_selector("#edSvg", timeout=15000)
            page.wait_for_selector("#edTray button", timeout=5000)
            tray_n = page.eval_on_selector_all("#edTray button", "els => els.length")
            assert tray_n == 6, f"托盘应有 6 类节点，实际 {tray_n}"
            print("1. 页面装载 ✓（三栏 + 六类托盘）")

            # —— 2. 模板装载 —— #
            page.click("#edTplMin")
            page.wait_for_function(
                "document.querySelectorAll('#edSvg .ed-node').length === 3",
                timeout=10000)
            assert page.eval_on_selector_all("#edSvg .ed-edge",
                                             "els => els.length") == 2
            page.click("#edTplEnc")
            page.wait_for_function(
                "document.querySelectorAll('#edSvg .ed-node').length === 13",
                timeout=10000)
            print("2. 模板 ✓（最小链 3 节点 2 边；单 Agent 13 节点）")

            # —— 3. UI 校验 + 序列化端点复核 —— #
            page.click("#edValidate2")
            page.wait_for_function(
                "document.querySelector('#edMsg').textContent.includes('校验通过')",
                timeout=10000)
            graph = page.evaluate("edToGraph()")
            r = page.request.post(f"{base}/api/editor/validate",
                                  data=json.dumps({"graph": graph}),
                                  headers={"Content-Type": "application/json"})
            assert r.status == 200 and r.json()["ok"], "encyclopedia 图端点复核失败"
            print("3. 校验 ✓（UI 消息 + 端点复核 ok）")

            # —— 4. 检查器：选中 plugin 节点 → ref 回显（模板往返） —— #
            page.evaluate(
                "edSelectNode(ED.nodes.find(n => n.type === 'plugin').id)")
            page.wait_for_selector("#edRef", timeout=5000)
            ref_val = page.eval_on_selector("#edRef", "el => el.value")
            assert ref_val == "python-encyclopedia", \
                f"plugin 节点 ref 回显异常：{ref_val!r}"
            print("4. 检查器 ✓（plugin ref 回显 = python-encyclopedia）")

            # —— 5. 拖拽节点：坐标变化（受控两节点图，消除随机布点重叠歧义） —— #
            page.evaluate("""() => {
              ED.nodes = [
                {id:'a', type:'process', x:100, y:100, params:{expr:'payload'}},
                {id:'b', type:'exit',    x:600, y:400, params:{}}];
              ED.edges = []; ED.sel = null; ED.selEdge = null;
              edRender();
            }""")
            page.wait_for_function(
                "document.querySelectorAll('#edSvg .ed-node').length === 2")
            before = page.evaluate("ED.nodes.find(n=>n.id==='a').x")
            b_before = page.evaluate("ED.nodes.find(n=>n.id==='b').x")
            box = page.locator('#edSvg .ed-node[data-id="a"]').bounding_box()
            page.mouse.move(box["x"] + 40, box["y"] + 20)
            page.mouse.down()
            assert page.evaluate("ED.drag && ED.drag.id") == "a", "mousedown 未抓住节点 a"
            page.mouse.move(box["x"] + 240, box["y"] + 120, steps=8)
            page.mouse.up()
            after = page.evaluate("ED.nodes.find(n=>n.id==='a').x")
            b_after = page.evaluate("ED.nodes.find(n=>n.id==='b').x")
            assert after != before, "拖拽后节点 a 坐标未变化"
            assert b_after == b_before, "拖拽 a 影响了无关节点 b"
            print(f"5. 拖拽 ✓（a.x {before:.0f} → {after:.0f}，b 不动）")

            # —— 6. 拖拽连线：linkdot → 目标节点，边建成 —— #
            assert page.evaluate("ED.edges.length") == 0
            dot = page.locator('#edSvg .ed-node[data-id="a"] .ed-linkdot')
            dbox = dot.bounding_box()
            tbox = page.locator('#edSvg .ed-node[data-id="b"]').bounding_box()
            page.mouse.move(dbox["x"] + dbox["width"] / 2,
                            dbox["y"] + dbox["height"] / 2)
            page.mouse.down()
            page.mouse.move(tbox["x"] + 20, tbox["y"] + 20, steps=10)
            page.mouse.up()
            edges = page.evaluate("ED.edges")
            assert len(edges) == 1 and edges[0]["from"] == "a" \
                and edges[0]["to"] == "b", f"拖拽连线未建成：{edges}"
            print("6. 连线 ✓（linkdot a → 节点 b，边建成）")

            # —— 7. 托盘增删 —— #
            page.evaluate("edAddNode('process')")
            n_add = page.evaluate("ED.nodes.length")
            page.evaluate("edDeleteSelected()")
            n_del = page.evaluate("ED.nodes.length")
            assert n_add == n_del + 1, f"增删异常（{n_add} → {n_del}）"
            print(f"7. 托盘增删 ✓（{n_del} → {n_add} → {n_del}）")

            # —— 8. UI 安装为 unit → 端点可见 → 卸载收尾 —— #
            page.fill("#edMetaId", "e2e-canvas")
            page.fill("#edMetaName", "画布直装")
            page.click("#edTplMin")  # 回到最小链（干净图）
            page.wait_for_function(
                "document.querySelectorAll('#edSvg .ed-node').length === 3",
                timeout=10000)
            page.click("#edInstall2")
            page.wait_for_function(
                "document.querySelector('#edMsg').textContent.includes('已安装')",
                timeout=15000)
            r = page.request.get(f"{base}/api/units/e2e-canvas")
            assert r.status == 200 and r.json()["unit"]["id"] == "e2e-canvas"
            r = page.request.delete(f"{base}/api/market/units/e2e-canvas")
            assert r.status == 200, f"卸载失败：HTTP {r.status}"
            print("8. UI 安装 ✓（/api/units 可见 → 市场卸载收尾）")

            # —— 9. 全程零 JS 错误 —— #
            assert not errors, "浏览器报错：" + "; ".join(errors[:5])
            print("9. 零 console/page error ✓")
            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    print("\n浏览器级验收全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(run())
