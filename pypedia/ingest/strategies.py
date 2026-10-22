"""摄入策略（对象类思想）：每种资料源 = 一个 Strategy。

将原本挤在 ingest.py 里的 `ingest_url / ingest_file / ingest_github` 三个长函数
重构为 `IngestStrategy` 继承体系：
- 共享逻辑（角色归一、文档组装、清单登记、索引写入与块数回填）上提到基类；
- 各子类只实现「抓什么 / 怎么失败降级」这一差异点；
- 公开函数 `ingest_url / ingest_file / ingest_github` 保留原签名，内部委托策略类，
  所有调用方（app.py / knowledge / cli / 测试）零改动。

`ingest_builtin_corpus` 是批处理（读 corpus.json 后逐条入库），形态不同于单源策略，
保留为独立函数。
"""
from __future__ import annotations

import concurrent.futures
from pathlib import Path

from ..config import settings
from .crawl import _crawl_github, _crawl_site
from .parsers import check_file_safe, parse_file
from .sources import (_patch_chunk_count, add_source_record, index,
                      list_sources)


def _norm_role(role: str) -> str:
    role = (role or "").lower()
    if role in ("main", "primary", "主要"):
        return "main"
    if role in ("supplement_a", "补充a", "github"):
        return "supplement_a"
    return "supplement_b"


def _make_doc(source_id: str, text: str, role: str, source: str,
              title: str, url: str, freshness: float) -> list[dict]:
    """整篇作为一个 Document 交给 rag.add，由 LlamaIndex 分块器切分（不二次切分）。"""
    if not text or not text.strip():
        return []
    return [{
        "src_id": source_id, "text": text, "role": role, "source": source,
        "title": title, "url": url, "freshness": freshness,
    }]


class IngestStrategy:
    """单源摄入策略基类：封装登记、索引、块数回填的共用流程。"""

    kind: str = "url"
    freshness: float = 1.0
    err_note: str = "抓取失败"

    def __init__(self, role: str, title: str | None = None):
        self.role = _norm_role(role)
        self.title = title

    # —— 共用流程 —— #
    def _record(self, *, target: str, title: str, status: str,
                note: str = "", **extra: object) -> str:
        rec = {
            "kind": self.kind, "target": target, "role": self.role,
            "title": title, "status": status, "chunk_count": 0, "chars": 0,
        }
        if note:
            rec["note"] = note
        rec.update(extra)
        return add_source_record(rec)

    def _index_pages(self, sid: str, pages: list[dict]) -> tuple[int, int]:
        docs, chars = [], 0
        for p in pages:
            chars += len(p["text"])
            docs.extend(_make_doc(sid, p["text"], self.role, p["title"],
                                 p["title"], p["url"], self.freshness))
        added = index.add(self.role, docs)
        _patch_chunk_count(sid, added, chars)
        return added, chars

    def _fail(self, target: str, title: str, note: str) -> dict:
        sid = self._record(target=target, title=title, status="pending", note=note)
        return {"source_id": sid, "status": "pending", "pages": 0, "chunks": 0,
                "note": note}

    def run(self, target: str, **kw) -> dict:  # pragma: no cover - 抽象
        raise NotImplementedError


class UrlStrategy(IngestStrategy):
    kind = "url"
    freshness = 1.0

    def run(self, target: str, max_pages: int | None = None) -> dict:
        max_pages = min(max_pages or settings.MAX_PAGES_PER_SITE, 20)
        pages = _crawl_site(target, max_pages)
        if not pages:
            return self._fail(
                target, self.title or target,
                "抓取失败：目标不可达（沙箱网络限制或地址错误）。在本机联网环境可正常抓取。")
        sid = self._record(
            target=target, title=self.title or pages[0]["title"], status="indexed",
            pages=len(pages), freshness=self.freshness)
        added, chars = self._index_pages(sid, pages)
        return {"source_id": sid, "status": "indexed", "pages": len(pages),
                "chunks": added, "chars": chars}


class GithubStrategy(IngestStrategy):
    kind = "github"
    freshness = 0.9

    def run(self, repo: str) -> dict:
        pages = _crawl_github(repo)
        if not pages:
            return self._fail(
                repo, self.title or repo,
                "GitHub 抓取失败：API 不可达（沙箱网络限制）。本机联网可正常抓取 README 与文档。")
        sid = self._record(
            target=repo, title=self.title or pages[0]["title"], status="indexed",
            pages=len(pages), freshness=self.freshness)
        added, chars = self._index_pages(sid, pages)
        return {"source_id": sid, "status": "indexed", "pages": len(pages),
                "chunks": added, "chars": chars}


class FileStrategy(IngestStrategy):
    kind = "offline"
    freshness = 0.6

    def run(self, path: str, filename: str | None = None) -> dict:
        role = self.role
        name = filename or Path(path).name
        # 桌面安全防护先行：大小 / ZIP 炸弹
        reject = check_file_safe(path)
        if reject:
            sid = self._record(target=name, title=self.title or name,
                              status="error", note=reject)
            return {"source_id": sid, "status": "error", "chunks": 0, "note": reject}
        # 解析放线程池 + 超时墙（防病态文件拖死服务）
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(parse_file, path, filename)
                text = future.result(timeout=settings.PARSE_TIMEOUT)
        except concurrent.futures.TimeoutError:
            note = f"解析超时（>{settings.PARSE_TIMEOUT:.0f}s），文件可能过于复杂或损坏"
            sid = self._record(target=name, title=self.title or name,
                              status="error", note=note)
            return {"source_id": sid, "status": "error", "chunks": 0, "note": note}
        if text.startswith("[解析失败]") or text.startswith("[不支持"):
            sid = self._record(target=name, title=self.title or name,
                              status="error", note=text)
            return {"source_id": sid, "status": "error", "chunks": 0, "note": text}
        sid = self._record(target=name, title=self.title or name, status="indexed",
                          chars=len(text), freshness=self.freshness)
        docs = _make_doc(sid, text, role, name, self.title or name,
                        f"file://{path}", self.freshness)
        added = index.add(role, docs)
        _patch_chunk_count(sid, added, len(text))
        return {"source_id": sid, "status": "indexed", "chunks": added,
                "chars": len(text), "format": Path(path).suffix.lower()}


# —— 公开函数（保持原签名，委托策略类；调用方零改动） —— #
def ingest_url(target: str, role: str, title: str | None = None,
               max_pages: int | None = None) -> dict:
    return UrlStrategy(role, title).run(target, max_pages=max_pages)


def ingest_github(repo: str, role: str, title: str | None = None) -> dict:
    return GithubStrategy(role, title).run(repo)


def ingest_file(path: str, role: str, filename: str | None = None,
                title: str | None = None) -> dict:
    return FileStrategy(role, title).run(path, filename)


def ingest_builtin_corpus() -> int:
    """把内置示例语料（corpus.json）导入向量索引，统一走 LlamaIndex 检索。幂等。

    幂等条件同时看 sources.json 与向量库：向量库为空（如迁移失败/用户清库）时
    强制重新摄入，避免「清单说已索引、检索却零命中」的口径不一致。
    """
    corpus_path = Path(__file__).resolve().parent.parent / "data" / "corpus.json"
    if not corpus_path.exists():
        return 0
    import json

    data = json.loads(corpus_path.read_text(encoding="utf-8"))
    entries = data.get("entries", []) if isinstance(data, dict) else data
    existing = {s.get("target") for s in list_sources() if s.get("kind") == "builtin"}
    if index.count() == 0:
        # 向量库空了：清掉 builtin 旧记录强制重摄（非 builtin 记录不动）
        from .sources import _read, _write

        _write([s for s in _read() if s.get("kind") != "builtin"])
        existing = set()
    added = 0
    for e in entries:
        key = f"builtin:{e['title']}"
        if key in existing:
            continue
        role = e.get("role", "main")
        sid = add_source_record({
            "kind": "builtin", "target": key, "role": role, "title": e["title"],
            "status": "indexed", "chunk_count": 0, "chars": len(e.get("body", "")),
            "freshness": float(e.get("freshness", 1.0)),
        })
        docs = _make_doc(sid, e.get("body", ""), role, e.get("source", ""),
                         e["title"], e.get("url", ""), float(e.get("freshness", 1.0)))
        n = index.add(role, docs)
        added += n
        # 记本条目实际写入的块数：此前误传 index.count(role)（该角色的累计总数），
        # 会导致每个内置条目的 chunk_count 都显示成全角色总数并随导入顺序虚高
        _patch_chunk_count(sid, n, len(e.get("body", "")))
    return added
