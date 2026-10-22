"""编排引擎：等级适配 → RAG(LanceDB + 百炼) → 长上下文压缩 → 生成 → 二审 → 记忆沉淀。

设计：检索/向量化/重排/生成/记忆/协议层全部复用成熟组件（见 rag.py / models/ /
memory_store.py / conversation.py / review.py / mcp_client.py），本模块只负责
业务编排与产品逻辑（等级适配、级联主/辅判定、提示词构造、极端场景兜底）。

2026-10 升级要点：
- 长上下文：Session 挂载 ConversationContext（token 预算 + 滑窗 + 滚动摘要）；
- Agent 协议层：MCPManager（filesystem/fetch/sequential-thinking），失败自动降级；
- 答案质量：双模型二审（review.py，A2A 轻量替代），差异大时给修订版；
- 记忆注入：按当前 query 语义检索历史记忆（search_memory），不全量倾倒；
- 可视化输出：系统提示词约束模型产出 mermaid/图表/表格/代码（前端对应渲染）。
"""
from __future__ import annotations

import re
import sys
import threading
import time

from .config import settings
from .levels import ensure_level, level_prompt, level_meta
from .llm.mock import MockLLM
from .logging_setup import get_logger
from .memory import Session
from .memory_store import MemoryStore
from .plugins.evolution import EvolutionPlugin
from .retrieval import CascadeRetriever
from .retrieval.sources import ROLE_LABEL
from .models.dashscope import chat as bailian_chat, chat_stream as bailian_chat_stream, evaluate_confidence
from .knowledge import ingest_builtin_corpus, ingest_preset_sources
from .mcp_client import mcp_manager
from .review import review_answer

log = get_logger("engine")

# 复杂问题启发式：多分句 / 多问号 / 多并列项 → 借 MCP 分步推理便笺拆解
_COMPLEX = re.compile(r"[?？。；;]|并且|以及|同时|分别|对比|区别|步骤|流程|原理")

_singleton: "PyPediaEngine | None" = None


def get_engine() -> "PyPediaEngine":
    """进程内共享引擎单例：app.py 与 agent.py（沙箱工具层）共用同一实例，
    避免双份检索器 / 记忆 / 自进化状态。测试环境下 conftest 已在 import 时
    完成重型依赖打桩，此处延迟实例化正好落在打桩之后。"""
    global _singleton
    if _singleton is None:
        _singleton = PyPediaEngine()
    return _singleton


class PyPediaEngine:
    def __init__(self, provider: str | None = None):
        self.provider = provider or settings.LLM_PROVIDER
        self.retriever = CascadeRetriever(top_k=settings.TOP_K_PER_STAGE)
        # 幂等预导入内置示例语料（统一走向量索引）
        try:
            ingest_builtin_corpus()
        except Exception as e:  # noqa: BLE001
            print(f"[PyPedia] 内置语料导入跳过：{e}", file=sys.stderr)
        # 长期记忆/用户画像层（Mem0 + 百炼），无密钥时自动降级
        self.memory = MemoryStore()
        # 自进化层（Reflexion 反思 + Voyager 技能库），冻结权重、只进化 prompt。
        # 插件化：换为 EvolutionPlugin（同一对象，门控实时读，关时全链路零反思）
        self.evolution = EvolutionPlugin()
        # MCP 协议层（真实接入 3 个官方参考 server，后台线程长连接）
        try:
            mcp_manager.start()
        except Exception as e:  # noqa: BLE001
            print(f"[PyPedia] MCP 启动跳过：{e}", file=sys.stderr)
        # 预置权威资料源（Python 官方文档 / CPython / 官方论坛）：后台线程入库，
        # 抓取耗时几十秒，绝不能阻塞服务启动；失败降级为 pending，离线语料仍可兜底
        threading.Thread(target=self._ingest_preset, daemon=True).start()

    def _ingest_preset(self) -> None:
        """后台导入预置资料源（daemon 线程，异常不得影响服务）。"""
        try:
            r = ingest_preset_sources()
            log.info("preset_sources_done", extra={k: v for k, v in r.items()
                                                   if isinstance(v, (int, float, bool, str))})
        except Exception as e:  # noqa: BLE001
            log.warning("preset_sources_failed", extra={"error": str(e)})

    def ask(self, query: str, level: int = 3, session: Session | None = None) -> dict:
        """一次性问答：prepare → 整段生成 → finalize（返回完整结果 dict）。"""
        level = ensure_level(level)
        session = session or Session(level=level)
        started = time.perf_counter()
        p = self._prepare(query, level, session)
        answer = self._complete(p["prompt"], p["system"])
        return self._finalize(query=p["query"], answer=answer, cascade=p["cascade"],
                              ctx_plan=p["ctx_plan"], plan=p["plan"], session=session,
                              level=level, started=started)

    def ask_stream(self, query: str, level: int = 3, session: Session | None = None):
        """流式问答：产出 (event, payload) 序列，事件协议：

        - ("meta",  {session_id, level, provider})  —— 检索完成后立即回吐（首帧 <1s）；
        - ("chunk", {"text": 增量})                  —— 逐段答案，可多次；
        - ("done",  结果 dict)                       —— 与 ask() 返回同构（未 _json_safe）。

        与 ask() 共用 _prepare/_finalize：检索/压缩/分步/置信度/二审/记忆/自进化
        逻辑完全一致，仅生成通道为逐段增量。半截答案中断时不降级（避免拼接痕迹）。
        """
        level = ensure_level(level)
        session = session or Session(level=level)
        started = time.perf_counter()
        p = self._prepare(query, level, session)
        yield "meta", {
            "session_id": session.session_id,
            "level": level_meta(level),
            "provider": self.provider,
        }
        parts: list[str] = []
        try:
            for delta in self._complete_stream(p["prompt"], p["system"]):
                parts.append(delta)
                yield "chunk", {"text": delta}
        except Exception as e:  # noqa: BLE001 —— 已吐出部分答案则如实中断（上层发 error 事件）
            if parts:
                raise
            # 首段即失败（无密钥/网络不通）：Mock 流兜底，流程与 ask() 的降级语义一致
            log.warning("bailian_stream_fallback_mock",
                        extra={"error": f"{type(e).__name__}: {e}"})
            for delta in MockLLM().stream(p["prompt"], system=p["system"]):
                parts.append(delta)
                yield "chunk", {"text": delta}
        answer = "".join(parts)
        yield "done", self._finalize(query=p["query"], answer=answer,
                                     cascade=p["cascade"], ctx_plan=p["ctx_plan"],
                                     plan=p["plan"], session=session, level=level,
                                     started=started)

    # —— ask / ask_stream 共用前置：截断防护 → 级联检索 → 上下文压缩 → 分步思路 → 提示词 —— #
    def _prepare(self, query: str, level: int, session: Session) -> dict:
        # 0) 极端输入防护：超长提问截断（防提示词膨胀与费用失控）
        if len(query) > settings.MAX_QUERY_CHARS:
            query = query[: settings.MAX_QUERY_CHARS] + "…（已截断）"
        # 1) 级联检索（带多轮上下文扩展），明确标注主要/补充
        cascade = self.retriever.retrieve(query, history=session.recent_context())
        # 2) 长上下文压缩：token 预算内全保留，超预算滑窗 + 滚动摘要
        ctx_plan = session.context.plan(session.turns)
        # 3) 复杂问题分步拆解（MCP sequential-thinking 便笺，失败静默跳过）
        plan = self._reasoning_plan(query)
        # 4) 构造提示词：等级适配 + 角色约定 + 证据 + 压缩后前情 + 分步思路
        system = self._build_system(level, query)
        prompt = self._build_prompt(query, cascade, ctx_plan, plan)
        return {"query": query, "cascade": cascade, "ctx_plan": ctx_plan,
                "plan": plan, "system": system, "prompt": prompt}

    # —— ask / ask_stream 共用后置：置信度 → 二审 → 记忆沉淀 → 自进化 → 结果 dict —— #
    def _finalize(self, *, query: str, answer: str, cascade, ctx_plan, plan: str,
                  session: Session, level: int, started: float) -> dict:
        # 5) 置信度：基于检索证据 + 实际回答，由百炼 qwen 评估
        evidence = [c.text for c in cascade.all_chunks[:5]]
        conf = self._confidence(query, answer, evidence, cascade)

        # 6) 答案二审（双模型交叉审阅，A2A 轻量替代；跳过不影响主流程）
        review = review_answer(query, answer, evidence)

        # 7) 沉淀记忆：会话内多轮 + 跨会话画像（Mem0，后台线程不阻塞）
        primary_title = cascade.primary[0].title if cascade.primary else ""
        session.add(query, answer, conf["score"], primary_title)
        self.memory.observe(query, level, conf["score"], answer)
        # 8) 自进化：反思（后台）+ 技能沉淀（即时），下次问答以累积技能/反思注入
        self.evolution.observe(query, answer, conf["score"], bool(cascade.primary), level)

        log.info(
            "ask_done",
            extra={
                "level": level,
                "query_len": len(query),
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "confidence": conf["score"],
                "primary": primary_title or None,
                "chunks": len(cascade.all_chunks),
                "compressed": ctx_plan.compressed,
                "multi_turn": len(session.turns) > 1,
            },
        )

        return {
            "query": query,
            "level": level_meta(level),
            "confidence": conf,
            "cascade": cascade,
            "answer": answer,
            "provider": self.provider,
            "session": session,
            "multi_turn": len(session.turns) > 1,
            "context": {
                "compressed": ctx_plan.compressed,
                "total_tokens": ctx_plan.total_tokens,
                "kept_tokens": ctx_plan.kept_tokens,
                "dropped_turns": ctx_plan.dropped_turns,
                "summary": ctx_plan.summary[:200],
            },
            "review": review,
            "reasoning_plan": plan,
        }

    # —— 生成（真实通道失败降级 Mock） —— #
    def _complete(self, prompt: str, system: str) -> str:
        try:
            return bailian_chat([
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ])
        except Exception as e:  # noqa: BLE001
            log.warning("bailian_fallback_mock", extra={"error": f"{type(e).__name__}: {e}"})
            return MockLLM().complete(prompt, system=system)

    # —— 公开生成入口：供「图即引擎」的 model-call 节点调用 —— #
    def generate(self, prompt: str, system: str | None = None, level: int = 3) -> str:
        """图节点（model-call）出答案的公开薄封装：复用 _complete，失败降级 Mock。

        与 ``ask`` 的区别：``ask`` 自带检索/压缩/二审/记忆全链路；本方法只做
        「给定提示词 → 出答案」，让节点图自己掌控检索证据、二审与记忆的编排
        （即「图就是引擎」——管线由图驱动，而非 ask 内部黑盒）。
        """
        system = system or self._build_system(level, prompt)
        return self._complete(prompt, system)

    # —— 流式生成（真实 SSE 通道；首段即失败才降级 Mock 流） —— #
    def _complete_stream(self, prompt: str, system: str):
        """逐段产出答案增量。已吐出部分内容后失败 → 直接抛（半截答案降级会留下拼接痕迹）。"""
        emitted = False
        try:
            for delta in bailian_chat_stream([
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ]):
                emitted = True
                yield delta
        except Exception as e:  # noqa: BLE001
            if emitted:
                raise
            log.warning("bailian_stream_fallback_mock",
                        extra={"error": f"{type(e).__name__}: {e}"})
            yield from MockLLM().stream(prompt, system=system)

    # —— 复杂问题分步拆解（MCP sequential-thinking） —— #
    def _reasoning_plan(self, query: str) -> str:
        """复杂问题（多分句/多问号/流程对比类）生成结构化分步思路。

        推理由百炼 qwen 完成；MCP sequential-thinking server 作为持久化
        「思路便笺」承接每一步（真实 MCP 工具调用，可通过协议检视/导出）。
        server 未连接或调用失败时静默跳过，不影响主流程。
        """
        if not settings.MCP_THINKING_ENABLE:
            return ""
        if len(query) < 12 or not _COMPLEX.search(query):
            return ""
        try:
            plan = bailian_chat(
                [{"role": "system", "content": (
                    "把下面的 Python 问题拆成 2-4 个有序的解答步骤，每步一行，"
                    "只输出步骤清单，不要展开内容。"
                )},
                 {"role": "user", "content": query}],
                temperature=0.2, max_tokens=200,
            ).strip()
            if not plan:
                return ""
            # 写入 MCP 思路便笺（便笺只是可检视产物，失败绝不影响 plan 返回）
            try:
                mcp_manager.call_tool(
                    "thinking", "sequentialthinking",
                    {"thought": f"问题：{query}\n分步思路：\n{plan}",
                     "thoughtNumber": 1, "totalThoughts": 1, "nextThoughtNeeded": False},
                    timeout=10,
                )
            except Exception:  # noqa: BLE001
                pass
            return plan
        except Exception:  # noqa: BLE001
            return ""

    # —— 置信度（模型评估 + 证据维度拆解） —— #
    def _confidence(self, query: str, answer: str, evidence: list[str],
                   cascade) -> dict:
        raw = evaluate_confidence(query, answer, evidence)
        primary_hit = bool(cascade.primary)
        cross = bool(cascade.supplements)
        fresh = (sum(c.freshness for c in cascade.all_chunks) /
                 max(1, len(cascade.all_chunks)))
        raw["breakdown"] = {
            "primary_hit": 55 if primary_hit else 0,
            "cross_source": 30 if cross else 0,
            "freshness": round(fresh * 15, 1),
        }
        raw["level_label"] = raw.get("level", "中")
        return raw

    # —— 提示词构造 —— #
    def _build_system(self, level: int, query: str = "") -> str:
        base = (
            "你是「PyPedia」，一位只精通 Python 的百科全书式助手。"
            "你的回答应当：通俗易懂、偏好可视化与代码框、必要时用 Markdown 表格/图示；"
            "不直接长篇大论，能用图/表/代码表达的就别用纯文字。\n\n"
            + level_prompt(level)
            + "\n\n【角色与主要/补充】\n"
            "· 主要源 = 用户指定库的官方主站文档，权威性最高，答案以其为准。\n"
            "· 补充A = GitHub 源码与文档，用于确认 API 实际行为与实现细节。\n"
            "· 补充B = 离线文档与权威论坛，用于边界场景与社区经验。\n"
            "当主要源命中强时直接采信；主要源缺失时明确告知不确定性并谨慎作答。\n\n"
            "【可视化输出规范（前端已具备渲染能力，请按需使用）】\n"
            "· 标准 Markdown（GFM）：标题/列表/表格/引用/链接；\n"
            "· 代码块必须带语言标注（```python 等），前端会做语法高亮；\n"
            "· 需要表达流程/结构/关系时，用 ```mermaid 代码块（graph TD / sequenceDiagram / "
            "classDiagram / erDiagram 等），不要用 ASCII 画图；\n"
            "· 需要表达数据对比/统计时，用 ```chart 代码块，内容为标准 ECharts option JSON"
            "（如 {\"xAxis\":{\"type\":\"category\",\"data\":[...]},\"yAxis\":{\"type\":\"value\"},"
            "\"series\":[{\"type\":\"bar\",\"data\":[...]}]}），前端会渲染成交互图表；\n"
            "· 行内公式用 $...$、独立公式用 $$...$$（KaTeX 语法）；\n"
            "· 允许有限 HTML（表格/布局标签），但禁止 script/iframe/事件属性。"
        )
        # 注入跨会话用户画像与历史记忆（Mem0 语义检索，无记忆时为空串）
        try:
            profile = self.memory.profile_prompt(query)
        except Exception:
            profile = ""
        # 注入自进化：已掌握技能 + 累积反思（无内容时为空串）
        try:
            evolution = self.evolution.prompt_injection()
        except Exception:
            evolution = ""
        extras = "\n\n".join(p for p in (profile, evolution) if p)
        return base + (("\n\n" + extras) if extras else "")

    def _build_prompt(self, query: str, cascade, ctx_plan, plan: str = "") -> str:
        lines = [f"用户问题：{query}", ""]
        # 多轮前情：优先用压缩后的方案（滑窗保留 + 滚动摘要）
        if ctx_plan.summary:
            lines.append("【前情摘要（更早的对话已折叠）】")
            lines.append(ctx_plan.summary)
            lines.append("")
        kept = ctx_plan.kept_turns
        if kept:
            lines.append("【多轮前情】")
            for user, _assistant in kept[-3:]:
                lines.append(f"- 用户曾问：{user}")
            lines.append("")
        if plan:
            lines.append("【分步解答思路】")
            lines.append(plan)
            lines.append("")
        lines.append("【证据（按角色标注）】")
        used = cascade.all_chunks[:6]
        if not used:
            lines.append("证据：（未检索到相关片段，请基于通用 Python 知识谨慎作答并说明局限）")
        for c in used:
            snippet = c.text[:180].replace("\n", " ")
            lines.append(f"证据：[{ROLE_LABEL.get(c.role, c.role)}] {c.title} — {snippet}")
        lines.append("")
        lines.append(
            "请综合上述证据作答，并标明哪些结论来自主要源、哪些来自补充源。"
        )
        return "\n".join(lines)
