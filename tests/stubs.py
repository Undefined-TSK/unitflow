"""测试与性能基准共用的重型依赖桩（tests/conftest.py 与 scripts/benchmark.py 的唯一来源）。

铁律背景：桩定义曾在两处各写一份（benchmark.py docstring 自认重复），
任何一侧漏同步都会让「零真实 LLM 调用」承诺出现缺口——合并为单一模块。

约束：本模块 import 时不 import pypedia（调用方需先设好 PYPEDIA_DATA 等
环境变量），所有 pypedia import 延迟到 install_* 函数内，避免 import
顺序耦合。
"""
from __future__ import annotations


class StubMCP:
    """MCP 管理器 stub：不起子进程、不调工具。"""

    def start(self) -> None:
        pass

    def status(self) -> list[dict]:
        return []

    def call_tool(self, key, tool, args, timeout=30.0):
        raise RuntimeError("stub mcp")

    def close(self) -> None:
        pass


class StubMemory:
    """Mem0 stub：不初始化 chroma、不调百炼。"""

    def __init__(self):
        self._caches: list[str] = []

    def observe(self, *a, **kw) -> None:
        pass

    def search_memory(self, query="", user_id="default", n=4) -> list[str]:
        return []

    def profile_prompt(self, query="", user_id="default") -> str:
        return ""

    def get_profile(self, user_id="default") -> dict:
        return {"level": None, "interactions": 0, "memories": list(self._caches),
                "pain_points": [],
                "memory_items": [{"id": f"cache:{i}", "text": t}
                                 for i, t in enumerate(self._caches)]}

    def delete_memory(self, mem_id: str, user_id="default") -> bool:
        if mem_id.startswith("cache:"):
            try:
                idx = int(mem_id.split(":", 1)[1])
            except (ValueError, IndexError):
                return False
            if 0 <= idx < len(self._caches):
                self._caches.pop(idx)
                return True
        return False


def stub_rag_embeddings() -> None:
    """rag 的嵌入器替换为 LlamaIndex MockEmbedding（确定性假向量，零真实端点）。"""
    from llama_index.core.embeddings import MockEmbedding

    import pypedia.rag as rag

    rag.DashScopeEmbedding = lambda **kwargs: MockEmbedding(embed_dim=64)
    # rag.py 现通过 CachedDashScopeEmbedding 建嵌入器（磁盘缓存包裹真实
    # DashScopeEmbedding）；同步桩掉，缓存包装在桩下不触网。
    rag.CachedDashScopeEmbedding = lambda **kwargs: MockEmbedding(embed_dim=64)


def install_engine_stubs() -> None:
    """引擎重型依赖打桩：Mem0 / MCP / 自进化反思 / 预置抓取全部 no-op（零真实 API）。

    · MemoryStore / mcp_manager：见 StubMemory / StubMCP；
    · reflexion.chat：自进化后台反思会调真实百炼 chat（Evolution.observe 每次
      问答后起守护线程调用它），模块级替换避免后台线程在 teardown 后仍触网，
      返回值固定为一句中文改进点；
    · PRESET_SOURCES_ENABLE：测试/基准环境绝不联网抓取预置资料源。
    """
    import pypedia.config as cfg
    import pypedia.engine as engine
    import pypedia.evolution.reflexion as reflexion

    engine.MemoryStore = StubMemory
    engine.mcp_manager = StubMCP()
    reflexion.chat = lambda *a, **kw: "（测试桩）建议补充一个可运行示例。"
    cfg.settings.PRESET_SOURCES_ENABLE = False
