"""EMBED_CACHE_DIR 落盘缓存的零网络回归测试（不烧任何额度）。

覆盖 EmbedCache（sqlite 落盘/统计/清空）与 CachedDashScopeEmbedding
（命中不触网、miss 才走 super、query 路由复用缓存）。
网络调用一律 mock 父类私有 worker，绝不请求百炼。
"""
from __future__ import annotations

import tempfile
import unittest
from unittest import mock

from pypedia.embed_cache import CachedDashScopeEmbedding, EmbedCache


class TestEmbedCache(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.c = EmbedCache(self.tmp)

    def test_set_get_stats(self):
        self.assertIsNone(self.c.get("m1", "hello"))
        self.c.mset("m1", [("hello", [0.1, 0.2])])
        self.assertEqual(self.c.get("m1", "hello"), [0.1, 0.2])
        self.assertIsNone(self.c.get("m2", "hello"))  # 按模型隔离
        self.c.mset("m2", [("hello", [9.9])])
        self.assertEqual(self.c.get("m2", "hello"), [9.9])
        s = self.c.stats()
        self.assertEqual(s["hits"], 2)
        self.assertEqual(s["misses"], 2)
        self.assertEqual(s["rows"], 2)

    def test_clear(self):
        self.c.mset("m1", [("a", [1.0]), ("b", [2.0])])
        self.assertEqual(self.c.clear(), 2)
        self.assertEqual(self.c.stats()["rows"], 0)
        self.assertIsNone(self.c.get("m1", "a"))


class TestCachedWrapper(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.net_calls = 0
        parent = CachedDashScopeEmbedding.__bases__[0]
        self._patchers = [
            mock.patch.object(parent, "_get_text_embeddings",
                              side_effect=self._fake_batch),
            mock.patch.object(parent, "_get_text_embedding",
                              side_effect=self._fake_single),
            mock.patch.object(parent, "_get_query_embedding",
                              side_effect=self._fake_single),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in self._patchers:
            p.stop()

    def _fake_batch(self, texts):
        self.net_calls += 1
        return [[float(i)] for i in range(len(texts))]

    def _fake_single(self, text):
        self.net_calls += 1
        return [1.0]

    def _make(self):
        inst = CachedDashScopeEmbedding(
            model_name="fake-model", api_key=None, embed_batch_size=10,
            cache=EmbedCache(self.tmp),
        )
        inst.model_name = "fake-model"
        return inst

    def test_hit_no_network(self):
        inst = self._make()
        out1 = inst._get_text_embeddings(["a", "b", "c"])
        self.assertEqual(self.net_calls, 1)   # 首次全 miss → 1 次批量触网
        out2 = inst._get_text_embeddings(["a", "b", "c"])
        self.assertEqual(self.net_calls, 1)   # 全部命中，不再触网
        self.assertEqual(out1, out2)

    def test_partial_miss(self):
        inst = self._make()
        inst._get_text_embeddings(["x", "y"])
        self.assertEqual(self.net_calls, 1)
        inst._get_text_embeddings(["x", "z"])  # x 命中，z miss
        self.assertEqual(self.net_calls, 2)
        inst._get_text_embeddings(["z"])
        self.assertEqual(self.net_calls, 2)

    def test_query_routes_cache(self):
        inst = self._make()
        inst._get_text_embeddings(["q"])
        self.assertEqual(self.net_calls, 1)
        self.assertEqual(inst._get_query_embedding("q"), [0.0])  # 命中，0 次触网
        self.assertEqual(self.net_calls, 1)


if __name__ == "__main__":
    unittest.main()
