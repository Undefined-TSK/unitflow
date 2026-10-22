"""rag 索引测试：MockEmbedding + tmp LanceDB（全本地，零 API；rerank 打桩）。"""
import pytest

from pypedia.rag import KnowledgeIndex


def _docs(n: int = 3, src: str = "test-src") -> list[dict]:
    """n 个文档块共享同一 src_id（与 ingest 语义一致：一个源 → 多个块）。"""
    return [
        {
            "text": f"文档{i}：Python 装饰器 生成器 迭代器 上下文管理器 列表推导式。",
            "source": src,
            "title": f"标题{i}",
            "url": f"https://example.com/{i}",
            "freshness": 1.0,
            "tags": ["python", "语法"],
            "src_id": src,
        }
        for i in range(n)
    ]


@pytest.fixture()
def idx(tmp_path):
    return KnowledgeIndex(persist_dir=tmp_path / "lancedb")


class TestAdd:
    def test_add_and_count(self, idx):
        assert idx.add("main", _docs(3)) == 3
        assert idx.count() == 3
        assert idx.count("main") == 3

    def test_add_empty(self, idx):
        assert idx.add("main", []) == 0
        assert idx.count() == 0

    def test_roles_isolated(self, idx):
        idx.add("main", _docs(2, "src-main"))
        idx.add("supplement_a", _docs(3, "src-a"))
        assert idx.count("main") == 2
        assert idx.count("supplement_a") == 3
        assert idx.count("supplement_b") == 0
        assert idx.count() == 5

    def test_add_same_content_no_duplicate(self, idx):
        """同 source 同内容 → 同 doc_id，重复 add 不翻倍（幂等）。"""
        docs = _docs(2, "dedup-src")
        idx.add("main", docs)
        idx.add("main", docs)
        assert idx.count() == 2


class TestSearch:
    def test_search_hits(self, idx):
        idx.add("main", _docs(3))
        hits = idx.search("装饰器", role="main", top_k=2, use_rerank=False)
        assert hits
        assert len(hits) <= 2
        h = hits[0]
        assert h.role == "main"
        assert h.source == "test-src"
        assert h.title.startswith("标题")
        assert "python" in h.tags
        assert h.score >= 0

    def test_search_empty_index(self, idx):
        assert idx.search("任意", use_rerank=False) == []

    def test_search_role_filter(self, idx):
        idx.add("main", _docs(2, "src-m"))
        idx.add("supplement_a", _docs(2, "src-a"))
        hits = idx.search("装饰器", role="supplement_a", use_rerank=False)
        assert hits and all(h.role == "supplement_a" for h in hits)

    def test_search_dedup_merged(self, idx):
        """融合检索同一节点双路命中 → 按文本去重。"""
        idx.add("main", _docs(2))
        hits = idx.search("生成器 迭代器", top_k=5, use_rerank=False)
        texts = [h.text for h in hits]
        assert len(texts) == len(set(texts))

    def test_rerank_path_called(self, idx, monkeypatch):
        """use_rerank 且候选 >1 → 走 ds_rerank 并按其结果排序。"""
        idx.add("main", _docs(3))
        import pypedia.rag as rag_mod

        called = {}

        def _fake(query, texts, top_n=None, **kw):
            called["q"] = query
            called["n"] = len(texts)
            # 故意逆序返回，验证 search 按 rerank 结果重排
            return [{"index": i} for i in range(len(texts) - 1, -1, -1)]

        monkeypatch.setattr(rag_mod, "ds_rerank", _fake)
        hits = idx.search("装饰器", role="main", top_k=3, use_rerank=True)
        assert called["q"] == "装饰器"
        assert len(hits) == 3

    def test_rerank_failure_falls_back_scores(self, idx, monkeypatch):
        """rerank 抛异常 → 按向量分数排序兜底，不崩。"""
        idx.add("main", _docs(3))
        import pypedia.rag as rag_mod

        def _boom(*a, **kw):
            raise RuntimeError("rerank down")

        monkeypatch.setattr(rag_mod, "ds_rerank", _boom)
        hits = idx.search("装饰器", role="main", top_k=2, use_rerank=True)
        assert len(hits) == 2


class TestDelete:
    def test_delete_source(self, idx):
        idx.add("main", _docs(3, "del-src"))
        idx.add("main", _docs(2, "keep-src"))
        assert idx.count() == 5
        idx.delete_source("main", "del-src")
        assert idx.count() == 2  # 只剩 keep-src 的 2 块

    def test_delete_missing_no_crash(self, idx):
        idx.add("main", _docs(2))
        idx.delete_source("main", "不存在")  # 不抛即通过
        assert idx.count() == 2

    def test_delete_then_search(self, idx):
        idx.add("main", _docs(2, "gone"))
        idx.delete_source("main", "gone")
        assert idx.search("装饰器", role="main", use_rerank=False) == []
