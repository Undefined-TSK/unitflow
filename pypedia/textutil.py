"""中文分词统一入口（jieba，成熟库，MIT）。

两处消费：
1. session.py 用户问题主题提取（原手写正则+停用词表 → jieba.analyse TF-IDF）；
2. rag.py BM25 检索器的 tokenizer（原默认 token_pattern 把连续中文串当单一
   token，中文检索实际失效 —— 这是修复项）。
"""
from __future__ import annotations

import re
from functools import lru_cache

import jieba
import jieba.analyse

# Python 领域停用词（问题场景通用词，不承载主题）
STOPWORDS = frozenset({
    "怎么", "如何", "什么", "为什么", "请问", "一下", "一个", "这个", "那个",
    "可以", "能不能", "是否", "python", "用法", "区别", "意思", "作用", "问题",
    "代码", "写法", "实现", "方法", "里面", "以上", "下面", "里面", "时候",
    "报错", "错误", "运行", "执行", "使用", "支持", "包含",
})


def tokens(text: str) -> list[str]:
    """BM25 用：jieba 精确模式分词，中英文数字均保留，去停用词与单噪声字符。"""
    if not text:
        return []
    words = []
    for w in jieba.lcut(text.lower()):
        w = w.strip()
        if not w or w in STOPWORDS:
            continue
        # 纯标点/空白跳过；单字符英文数字跳过（噪声），单汉字保留（中文最小单元）
        if len(w) == 1 and not "\u4e00" <= w <= "\u9fff":
            continue
        words.append(w)
    return words or re.findall(r"[a-zA-Z][a-zA-Z0-9_]+", text.lower())


@lru_cache(maxsize=512)
def keywords(text: str, topk: int = 4) -> tuple[str, ...]:
    """主题提取：jieba TF-IDF（短文本中文主题词，零 LLM 成本，结果确定）。"""
    if not text or not text.strip():
        return ()
    tags = jieba.analyse.extract_tags(
        text, topK=topk, withWeight=False, allowPOS=("n", "nr", "ns", "nt", "v", "vn")
    )
    out = tuple(t for t in tags if t not in STOPWORDS and len(t) > 1)
    if not out:  # 兜底：分词后取前几个实词
        out = tuple(w for w in tokens(text)[:topk])
    return out
