"""textutil / levels 纯函数测试（零外部依赖）。"""
from pypedia.levels import ensure_level, level_meta, level_prompt
from pypedia.textutil import STOPWORDS, keywords, tokens


class TestTokens:
    def test_chinese_segmentation(self):
        ws = tokens("Python 装饰器的用法")
        # jieba 精确模式切分：「装饰器」切为 装饰/器；python/用法 是领域停用词被剔除；
        # 「的」为中文单字，按最小单元规则保留
        assert ws == ["装饰", "器", "的"]

    def test_english_words(self):
        ws = tokens("how to use asyncio event loop")
        assert "asyncio" in ws and "event" in ws and "loop" in ws

    def test_stopwords_removed(self):
        ws = tokens("这个怎么用 是什么 区别")
        for w in ws:
            assert w not in STOPWORDS

    def test_single_ascii_noise_dropped(self):
        ws = tokens("a b c 装饰器")
        assert "a" not in ws and "b" not in ws
        assert "装饰" in ws  # 中文按最小单元保留

    def test_empty(self):
        assert tokens("") == []

    def test_never_empty_for_real_text(self):
        # 兜底：纯停用词输入时也应尽量给出词（findall 分支）
        assert tokens("装饰器")  # 非空


class TestKeywords:
    def test_topk_respected(self):
        ks = keywords("Python 列表推导式 生成器 迭代器 装饰器 上下文管理器", topk=2)
        assert len(ks) <= 2

    def test_no_stopwords(self):
        ks = keywords("这个装饰器是什么意思怎么用")
        for k in ks:
            assert k not in STOPWORDS

    def test_empty(self):
        assert keywords("") == ()
        assert keywords("   ") == ()


class TestLevels:
    def test_clamp(self):
        assert ensure_level(0) == 1
        assert ensure_level(9) == 5
        assert ensure_level(-3) == 1

    def test_coerce(self):
        assert ensure_level("3") == 3
        assert ensure_level("abc") == 3
        assert ensure_level(None) == 3

    def test_prompt_differs_by_level(self):
        p1, p5 = level_prompt(1), level_prompt(5)
        assert p1 != p5
        assert "L1" in p1 and "L5" in p5
        assert "比喻" in p1 and "CPython" in p5

    def test_meta(self):
        assert level_meta(3)["t"] == "进阶"
        assert level_meta(99)["n"] == "L5"  # 越界也归位
