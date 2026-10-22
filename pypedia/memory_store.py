"""长期记忆与用户画像（基于 Mem0，百炼 DashScope 已支持）。

- 用 Mem0（2.2.x）这一成熟记忆层，通过 OpenAI 兼容接口走百炼：
  · llm: qwen-plus（记忆抽取/合并/冲突解决）
  · embedder: text-embedding-v4（1024 维）
  · vector_store: qdrant 本地模式（path= 嵌入式存储，零服务进程）
- Mem0 自动完成记忆抽取、去重、更新与冲突解决；用户画像由记忆 + 轻量 JSON 聚合而来。
- 无百炼密钥时优雅降级为「无记忆」模式（不崩溃，仅少个性化）。

2026-10 架构统一：向量库全家桶改为「零服务嵌入式」——
RAG 用 LanceDB，记忆层用 qdrant 本地模式（mem0ai 硬依赖自带 qdrant-client，
不新增依赖）；原 chroma 版记忆数据由 memory_migrate 一次性迁移（见该模块）。
"""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

from .config import settings

DATA_DIR = Path(os.getenv("PYPEDIA_DATA", str(Path.home() / ".pypedia")))
DEFAULT_USER = "default"
COLLECTION = "pypedia_mem0"


def _llm_config() -> dict:
    """Mem0 的 openai provider 走环境变量读取 base_url / key（此处显式传入更稳）。"""
    return {
        "provider": "openai",
        "config": {
            "model": settings.BAILIAN_MODEL,
            "temperature": 0.2,
            "max_tokens": 2000,
            "api_key": settings.BAILIAN_API_KEY,
            "openai_base_url": settings.BAILIAN_BASE_URL,
        },
    }


def _embedder_config() -> dict:
    return {
        "provider": "openai",
        "config": {
            "model": settings.BAILIAN_EMBED_MODEL,
            "embedding_dims": int(os.getenv("BAILIAN_EMBED_DIMS", "1024")),
            "api_key": settings.BAILIAN_API_KEY,
            "openai_base_url": settings.BAILIAN_BASE_URL,
        },
    }


def _mem0_config() -> dict:
    """完整 Mem0 配置（qdrant 本地模式向量库）。迁移模块复用同一 llm/embedder 块。"""
    return {
        "version": "v1.1",
        "llm": _llm_config(),
        "embedder": _embedder_config(),
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "collection_name": COLLECTION,
                "path": str(DATA_DIR / "mem0_qdrant"),
                "embedding_model_dims": int(os.getenv("BAILIAN_EMBED_DIMS", "1024")),
                "on_disk": True,
            },
        },
    }


class MemoryStore:
    """跨会话沉淀用户画像与记忆；单用户桌面场景默认 user_id='default'。

    底层为 Mem0（百炼 DashScope）。无密钥或初始化失败时降级为无操作，保证可用。
    """

    def __init__(self) -> None:
        self._ready = False
        self._mem_cache: list[str] = []
        self._profile_path = DATA_DIR / "profile.json"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not self._profile_path.exists():
            self._profile_path.write_text("{}", encoding="utf-8")
        try:
            self._init_mem0()
            self._ready = True
            print("[PyPedia] 记忆层：Mem0（百炼 DashScope）已就绪")
        except Exception as e:  # noqa: BLE001
            print(f"[PyPedia] 记忆层降级为无记忆模式：{e}", file=sys.stderr)

    def _init_mem0(self) -> None:
        if not settings.BAILIAN_API_KEY:
            raise RuntimeError("未配置百炼 API Key，记忆层不可用")
        from mem0 import Memory

        # Mem0 的 openai provider 走环境变量读取 base_url / key
        os.environ.setdefault("OPENAI_API_KEY", settings.BAILIAN_API_KEY)
        os.environ.setdefault("OPENAI_BASE_URL", settings.BAILIAN_BASE_URL)

        self._m = Memory.from_config(_mem0_config())

    # —— 观测一次交互 —— #
    def observe(self, query: str, level: int, confidence: float, answer: str,
                user_id: str = DEFAULT_USER) -> None:
        # 结构化等级/交互次数/卡点立即存 JSON（轻量、零额外 LLM 成本，同步完成）
        self._bump_profile(user_id, level, confidence, query)
        if not self._ready:
            return
        # 长期记忆抽取交给 Mem0（含 LLM 抽取 + 百炼向量化），放后台线程，
        # 不阻塞用户拿答案；完成后刷新记忆缓存供后续提示词注入。
        def _worker() -> None:
            try:
                self._m.add(
                    messages=[{
                        "role": "user",
                        "content": (
                            f"[PyPedia 交互记录] 用户 Python 水平约为 L{level}，"
                            f"提问：{query}\n助手回答（置信度 {confidence}）：{answer}"
                        ),
                    }],
                    user_id=user_id,
                    metadata={"level": level, "confidence": confidence},
                )
                try:
                    mem = self._m.get_all(filters={"user_id": user_id}) or {}
                    items = mem.get("results", []) if isinstance(mem, dict) else mem
                    self._mem_cache = [x.get("memory", "") for x in items[:12]]
                except Exception:
                    pass
            except Exception as e:  # noqa: BLE001
                print(f"[PyPedia] Mem0 写入失败：{e}", file=sys.stderr)

        threading.Thread(target=_worker, daemon=True).start()

    # —— 轻量画像（JSON） —— #
    def _read_profile(self) -> dict:
        try:
            return json.loads(self._profile_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_profile(self, data: dict) -> None:
        self._profile_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _bump_profile(self, user_id: str, level: int, confidence: float, query: str) -> None:
        prof = self._read_profile()
        p = prof.get(user_id, {"level": level, "interactions": 0, "pain_points": []})
        p["level"] = level
        p["interactions"] = p.get("interactions", 0) + 1
        if confidence < 50:
            pp = p.setdefault("pain_points", [])
            if len(pp) < 20:
                pp.append({"q": query, "conf": confidence})
        prof[user_id] = p
        self._write_profile(prof)

    def get_profile(self, user_id: str = DEFAULT_USER) -> dict:
        p = self._read_profile().get(user_id, {})
        out = {
            "level": p.get("level"),
            "interactions": p.get("interactions", 0),
            "pain_points": p.get("pain_points", [])[:5],
            "memories": list(self._mem_cache),
        }
        if self._ready:
            try:
                mem = self._m.get_all(filters={"user_id": user_id}) or {}
                items = mem.get("results", []) if isinstance(mem, dict) else mem
                out["memories"] = [x.get("memory", "") for x in items[:8]]
            except Exception:
                pass
        # memory_items：带 id 的结构，前端删除/导出依赖；id 为 Mem0 真实 id，
        # 无 Mem0 时退化为 cache:<index>（仅本地快照，删除只清缓存）。
        out["memory_items"] = self._mem_items(user_id)
        return out

    def _mem_items(self, user_id: str = DEFAULT_USER) -> list[dict]:
        """（id, text）记忆列表，供前端删除/导出。"""
        if self._ready:
            try:
                mem = self._m.get_all(filters={"user_id": user_id}) or {}
                items = mem.get("results", []) if isinstance(mem, dict) else mem
                return [{"id": x.get("id", ""), "text": x.get("memory", "")}
                        for x in items if x.get("memory")]
            except Exception:
                return []
        return [{"id": f"cache:{i}", "text": t} for i, t in enumerate(self._mem_cache)]

    def delete_memory(self, mem_id: str, user_id: str = DEFAULT_USER) -> bool:
        """删除单条记忆。Mem0 真实 id 走底层删除；cache: 前缀为本地快照，仅清缓存。

        返回是否真有删除动作发生（供端点回执）。
        """
        if mem_id.startswith("cache:"):
            try:
                idx = int(mem_id.split(":", 1)[1])
            except (ValueError, IndexError):
                return False
            if 0 <= idx < len(self._mem_cache):
                self._mem_cache.pop(idx)
                return True
            return False
        if not self._ready:
            return False
        try:
            self._m.delete(mem_id)
            try:
                mem = self._m.get_all(filters={"user_id": user_id}) or {}
                items = mem.get("results", []) if isinstance(mem, dict) else mem
                self._mem_cache = [x.get("memory", "") for x in items[:12]]
            except Exception:
                pass
            return True
        except Exception as e:  # noqa: BLE001
            print(f"[PyPedia] Mem0 删除失败：{e}", file=sys.stderr)
            return False

    # —— 记忆语义检索 —— #
    def search_memory(self, query: str, user_id: str = DEFAULT_USER, n: int = 4) -> list[str]:
        if not self._ready:
            return []
        try:
            # mem0 2.2.1：实体参数走 filters（顶层 user_id 已被禁用，且 limit 更名 top_k）
            res = self._m.search(query, top_k=n, filters={"user_id": user_id}) or {}
            items = res.get("results", []) if isinstance(res, dict) else res
            return [x.get("memory", "") for x in items if x.get("memory")]
        except Exception:
            return []

    def profile_prompt(self, query: str = "", user_id: str = DEFAULT_USER) -> str:
        """把用户画像与记忆拼成系统提示词片段，注入到每次问答。

        记忆注入走语义检索（search_memory，按当前 query 找最相关的历史记忆），
        而不是全量倾倒——全量既稀释注意力又浪费 token。
        """
        p = self.get_profile(user_id)
        if p["interactions"] == 0 and not p["memories"]:
            return ""
        lines = []
        if p.get("level"):
            lines.append(f"【用户画像】该用户 Python 水平约 L{p['level']}，已交互 {p['interactions']} 次。")
        if p["pain_points"]:
            qs = "；".join(x["q"] for x in p["pain_points"][:3])
            lines.append(f"曾在这些问题上置信度偏低（可能没讲清）：{qs}。")
        relevant = self.search_memory(query, user_id) if query else []
        if relevant:
            lines.append("相关历史记忆：" + " | ".join(m[:80] for m in relevant[:4]))
        return "\n".join(lines)
