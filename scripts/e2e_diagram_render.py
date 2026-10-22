#!/usr/bin/env python3
"""P4 diagram-render 浏览器级验收：开启渲染 / 关闭不加载 / 图块降级。

自包含：起临时数据目录的真实 app 进程（随机端口），Playwright 驱动 Chromium：
  1. ON 态：plugins.js 懒加载 mermaid/echarts（网络请求可见）；revealMarkdown
     真实后渲染钩子把 mermaid 块处理成 svg、chart 块初始化 ECharts canvas；
  2. 用户态关闭 + 刷新：DiagramRender.enabled=false、window.mermaid/echarts
     不存在、两个资产零请求；mermaid 块降级为 pre.hljs 普通高亮（源码可读）；
  3. 热切换：不刷新页面，DiagramRender.refresh() 补加载资产并置就绪。

用法：
    python3 scripts/e2e_diagram_render.py
依赖：playwright（python 包）+ Chromium（playwright install chromium）。
退出码：0 = 全部验收通过；1 = 任一断言失败（详见 stdout）。
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MERMAID = "mermaid.min.js"
ECHARTS = "echarts.min.js"
SAMPLE = (
    "# 标题\n\n"
    "```mermaid\nflowchart TD\n  A[开始] --> B[结束]\n```\n\n"
    "```chart\n{\"xAxis\":{\"type\":\"category\",\"data\":[\"a\",\"b\"]},"
    "\"yAxis\":{\"type\":\"value\"},\"series\":[{\"type\":\"bar\",\"data\":[1,2]}]}\n```\n\n"
    "```python\nprint(1)\n```"
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _toggle(base: str, enabled: bool) -> None:
    req = urllib.request.Request(
        f"{base}/api/plugins/diagram-render",
        data=json.dumps({"enabled": enabled}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        assert r.status == 200


def _wait_up(base: str, timeout: float = 60.0) -> None:
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

    tmp = tempfile.mkdtemp(prefix="pypedia-e2e-")
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = dict(os.environ, PYPEDIA_DATA=tmp)
    server = subprocess.Popen(
        [sys.executable, "app.py", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait_up(base)
        with sync_playwright() as pw:
            browser = pw.chromium.launch()

            # —— 1. ON 态：懒加载可见 + 图块真正渲染 —— #
            asked: list[str] = []
            page = browser.new_page()
            page.on("request", lambda r: asked.append(r.url))
            page.goto(base, wait_until="load")
            page.wait_for_function("window.PluginsBoot !== undefined")
            page.wait_for_function(
                "window.DiagramRender && window.DiagramRender.ready === true",
                timeout=20000)
            assert page.evaluate("window.DiagramRender.enabled") is True
            assert page.evaluate("!!window.mermaid") is True
            assert page.evaluate("!!window.echarts") is True
            assert any(MERMAID in u for u in asked), "ON 态未请求 mermaid 资产"
            assert any(ECHARTS in u for u in asked), "ON 态未请求 echarts 资产"
            html = page.evaluate("({src}) => window.md(src)", {"src": SAMPLE})
            assert 'class="mermaid"' in html and 'class="chart"' in html
            # 真实后渲染钩子：mermaid → svg；chart → ECharts canvas
            page.evaluate(
                "src => { const b = document.createElement('div'); b.id = 'e2e-box';"
                " document.body.appendChild(b); revealMarkdown(b, window.md(src)); }",
                SAMPLE)
            page.wait_for_selector("#e2e-box .mermaid[data-processed]", timeout=20000)
            assert page.query_selector("#e2e-box .mermaid svg") is not None, \
                "mermaid 块未被处理为 svg"
            assert page.query_selector("#e2e-box .chart canvas") is not None, \
                "chart 块未被 ECharts 初始化"
            print("ON 态：资产懒加载 ✓ 图块渲染 ✓（mermaid svg + ECharts canvas）")

            # —— 2. 用户态关闭 + 刷新：零下载 + 降级高亮 —— #
            _toggle(base, False)
            asked2: list[str] = []
            page2 = browser.new_page()
            page2.on("request", lambda r: asked2.append(r.url))
            page2.goto(base, wait_until="load")
            page2.wait_for_function("window.PluginsBoot !== undefined")
            page2.wait_for_timeout(2500)
            assert page2.evaluate("window.DiagramRender.enabled") is False
            assert page2.evaluate("!!window.mermaid") is False, "关闭态仍加载了 mermaid"
            assert page2.evaluate("!!window.echarts") is False, "关闭态仍加载了 echarts"
            assert not any(MERMAID in u for u in asked2), "关闭态仍请求了 mermaid 资产"
            assert not any(ECHARTS in u for u in asked2), "关闭态仍请求了 echarts 资产"
            html2 = page2.evaluate("({src}) => window.md(src)", {"src": SAMPLE})
            assert 'class="mermaid"' not in html2 and 'class="chart"' not in html2, \
                "关闭态图块未降级"
            assert 'class="language-mermaid"' in html2, "关闭态 mermaid 源码丢失"
            assert "code-copy" in html2, "关闭态复制按钮丢失"
            print("OFF 态：零下载 ✓ 图块降级普通高亮 ✓（源码可读可复制）")

            # —— 3. 热切换：不刷新重新开启，refresh() 补加载并补画 —— #
            _toggle(base, True)
            page2.evaluate("window.DiagramRender.refresh()")
            page2.wait_for_function(
                "window.DiagramRender && window.DiagramRender.ready === true",
                timeout=20000)
            assert page2.evaluate("window.DiagramRender.enabled") is True
            assert page2.evaluate("!!window.mermaid") is True
            print("热切换：refresh() 不刷新补加载 ✓")

            browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    print("BROWSER E2E OK")
    return 0


if __name__ == "__main__":
    sys.exit(run())
