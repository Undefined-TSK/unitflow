"""知识库模块：对外暴露资料源摄入与向量索引接口。

- 向量召回/混合检索/精排：rag.py（LlamaIndex + 百炼），不自造检索算法。
- 切分：rag.py 内的 LlamaIndex SentenceSplitter（成熟分块器）。
- 网页正文抽取：ingest.html_to_text（trafilatura，成熟库）。
- 离线文档解析：ingest.parse_file（pdfminer / python-docx / ebooklib / trafilatura）。
本包只做统一导出。
"""
from .. import ingest
from ..rag import KnowledgeIndex, get_index

list_sources = ingest.list_sources
delete_source = ingest.delete_source
stats = ingest.stats
ingest_url = ingest.ingest_url
ingest_github = ingest.ingest_github
ingest_file = ingest.ingest_file
ingest_builtin_corpus = ingest.ingest_builtin_corpus
ingest_preset_sources = ingest.ingest_preset_sources
load_preset_sources = ingest.load_preset_sources
supported_exts = ingest.SUPPORTED_EXTS
parse_file = ingest.parse_file
html_to_text = ingest.html_to_text

__all__ = [
    "KnowledgeIndex", "get_index", "list_sources", "delete_source", "stats",
    "ingest_url", "ingest_github", "ingest_file", "ingest_builtin_corpus",
    "ingest_preset_sources", "load_preset_sources",
    "supported_exts", "parse_file", "html_to_text",
]
