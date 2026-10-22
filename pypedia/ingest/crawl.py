"""网页与 GitHub 抓取（成熟库 + 双通路降级）。

- 同域链接发现：trafilatura.spider.focused_crawler（robots.txt + crawl-delay 感知）；
- 抓取：优先 MCP fetch server（独立进程、自带正文转 markdown），不可达降级
  requests + trafilatura（两条通路保证可用性）；
- GitHub：官方 API 读 README（base64 解码）。
本模块只做「URL/Repo → 多页纯文本」这一职责。
"""
from __future__ import annotations

import requests

from ..config import settings
from ..plugins import plugin_registry


def _UA() -> dict:
    return {"User-Agent": "PyPedia/1.0 (+knowledge-ingest)"}


def _page_title(url: str, html: str) -> str:
    from bs4 import BeautifulSoup

    try:
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.get_text(strip=True):
            return soup.title.get_text(strip=True)
    except Exception:
        pass
    return url


def _fetch_via_mcp(url: str) -> str:
    """MCP fetch server 抓取（开关 MCP_FETCH_ENABLE）；未连接/失败返回空串走降级。"""
    if not settings.MCP_FETCH_ENABLE:
        return ""
    try:
        from ..mcp_client import mcp_manager

        md = mcp_manager.call_tool("fetch", "fetch", {"url": url}, timeout=45)
        if md and md.strip() and not md.startswith("["):
            return md
    except Exception:
        pass
    return ""


def _fetch_via_requests(url: str) -> str:
    """requests + trafilatura 兜底抓取。"""
    try:
        r = requests.get(url, timeout=settings.FETCH_TIMEOUT, headers=_UA())
        if r.ok and r.text.strip():
            from .parsers import html_to_text

            return html_to_text(r.text)
    except Exception:
        pass
    return ""


def _crawl_site(target: str, max_pages: int) -> list[dict]:
    if not plugin_registry.is_enabled("web-fetch"):
        return []
    # 1) 同域链接发现（成熟库：robots.txt + crawl-delay + 导航页剪枝）
    urls = [target]
    try:
        from trafilatura.spider import focused_crawler

        todo, _known = focused_crawler(
            homepage=target, max_seen_urls=max_pages, max_known_urls=max_pages * 3
        )
        urls += [u for u in todo if u != target][: max_pages - 1]
    except Exception:
        # 发现失败时至少抓首页
        pass
    # 2) 抓取 + 正文抽取：优先 MCP fetch server，不可达时降级 requests + trafilatura
    pages = []
    for u in urls[:max_pages]:
        text = _fetch_via_mcp(u) or _fetch_via_requests(u)
        if text and text.strip():
            pages.append({"title": _page_title(u, text[:2000]), "url": u, "text": text})
    return pages


def _crawl_github(repo: str) -> list[dict]:
    if not plugin_registry.is_enabled("web-fetch"):
        return []
    # GitHub API 读 README；不可达返回空（上层降级）
    try:
        api = repo if repo.startswith("https://api.github.com") else \
            f"https://api.github.com/repos/{repo.strip('/').replace('https://github.com/', '')}/readme"
        r = requests.get(api, timeout=settings.FETCH_TIMEOUT, headers=_UA())
        if r.ok:
            import base64

            content = base64.b64decode(r.json().get("content", "")).decode("utf-8", "ignore")
            return [{"title": "README", "url": repo, "text": content}]
    except Exception:
        return []
    return []
