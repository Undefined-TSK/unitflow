"""PyPedia 桌面 MVP 后端：封装核心引擎，提供 REST API + 静态前端托管。

启动：
    python3.11 app.py            # 自动开浏览器（桌面）
    python3.11 app.py --no-browser
默认走 .env 里的 LLM_PROVIDER（已设为 bailian）。
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import sys
import threading
import time
import uuid
import webbrowser
from collections import deque
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pypedia.config import settings
from pypedia.engine import get_engine
from pypedia.llm import provider_name
from pypedia.logging_setup import get_logger, setup_logging
from pypedia.memory import Session
from pypedia.plugins import get_manifest, plugin_registry
from pypedia.units import RegistryError, UnitLoader, unit_registry
from pypedia.units.builtins import register_builtins
from pypedia.units.editor import EditorError, export_unit, validate_graph
from pypedia.units.market import (
    PLATFORM_VERSION,
    MarketError,
    MarketStore,
    default_paths as market_default_paths,
)
from pypedia import auth, knowledge

setup_logging()  # 模块导入即初始化（uvicorn app:app 方式启动同样生效）
http_log = get_logger("http")

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
SESSIONS: dict[str, Session] = {}

app = FastAPI(title="PyPedia", version=PLATFORM_VERSION)
engine = get_engine()  # 进程内共享单例（agent 沙箱工具层共用同一实例，不重复建检索器/记忆）

# ---------- Unit 内核（万物皆插件·图即引擎）---------- #
# P1 收尾：plugin_registry（兼容层）与 unit_registry（内核）共享同一份 manifest
# 真值源（pypedia/units/builtins.py）。内置插件的用户启停态仍走
# plugins/state.json（既有部署零迁移）；unit_registry 的 units/state.json
# 承载后续市场 unit 态。示例 unit（hello-world / python-encyclopedia）装入
# 共享内核：/api/units 可见、GraphRuntime 可解释执行其 node_graph。
register_builtins(unit_registry)  # 23 个内置插件（幂等）
_unit_loader = UnitLoader(unit_registry)
for _manifest_path in sorted((ROOT / "units" / "examples").rglob("plugin.json")):
    try:
        _unit_loader.install(_manifest_path.parent)
    except RegistryError:
        pass  # 已注册（重复导入/热重载），幂等跳过

# ---------- 市场 v1（P6：三类货架 + 模板/成品双形态 + 上传导入）---------- #
# 安装目录与账本位于数据目录（market/installed/ + units.lock）；重启时扫描
# 已安装目录恢复注册（幂等；单个坏包 warning 跳过，不阻断启动）。
# 双注册：市场 unit 除内核主表（unit_registry）外同步进 plugin_registry——
# agent 工具循环 / 提示词规约 / is_enabled 的消费方全走后者，只装主表会
# 「装得上但看不见」；门控查询（enabled/env_blocked）亦以 plugin_registry 为准。
_market_installed_dir, _market_lock_path = market_default_paths()
market_store = MarketStore(unit_registry, _unit_loader,
                           runtime_registry=plugin_registry,
                           installed_dir=_market_installed_dir,
                           lock_path=_market_lock_path)
try:
    for _uid in market_store.restore_installed():
        print(f"[PyPedia] 市场 unit 已恢复：{_uid}")
except MarketError as _exc:  # 账本损坏不阻断启动（市场功能不可用，其余正常）
    print(f"[PyPedia] 市场账本读取失败（{_exc}），本次运行跳过市场恢复")

# 定时任务调度器（AGENT_CRON_ENABLE 开启时随进程启动；任务持久化于数据目录
# agent/cron.db，重启后自动恢复——uvicorn app:app 方式导入同样生效）
if plugin_registry.is_enabled("agent-cron"):
    from pypedia.agent import cron as _agent_cron

    _agent_cron.start()

# 鉴权令牌启动时解析（启用且无既有令牌时生成落盘，权限 600）
_auth_token = auth.ensure_token()
if _auth_token:
    src = "（.env AUTH_TOKEN）" if settings.AUTH_TOKEN else f"（已保存至 {auth.TOKEN_FILE}，权限 600）"
    print(f"[PyPedia] 鉴权已开启，访问令牌 {src}")


class _AskLimited(Exception):
    """ask 配额超限（429）。retry_after 秒后重试。"""

    def __init__(self, detail: str, retry_after: float):
        super().__init__(detail)
        self.retry_after = retry_after


class AskLimiter:
    """ask 端点配额：并发上限 + 每分钟速率（线程安全；端点在线程池执行，须用 threading 原语）。

    - 并发：BoundedSemaphore，排队超过 queue_timeout 秒 → 429；
    - 速率：60 秒滑窗计数，窗口内请求数达 per_min → 429；
    - clock 可注入（测试用假时钟验证滑窗过期，无需真等 60 秒）。
    """

    def __init__(self, max_concurrent: int = 2, per_min: int = 10,
                 queue_timeout: float = 30.0, clock=time.monotonic):
        self._sem = threading.BoundedSemaphore(max(1, max_concurrent))
        self._per_min = max(1, per_min)
        self._queue_timeout = queue_timeout
        self._clock = clock
        self._lock = threading.Lock()
        self._calls: deque[float] = deque()

    def _window_wait(self) -> float:
        """当前若触发速率上限，返回需等待的秒数；否则 0。"""
        now = self._clock()
        with self._lock:
            while self._calls and now - self._calls[0] >= 60:
                self._calls.popleft()
            if len(self._calls) >= self._per_min:
                return max(1.0, 60 - (now - self._calls[0]))
        return 0.0

    def acquire(self) -> None:
        wait = self._window_wait()
        if wait > 0:
            raise _AskLimited("提问太频繁，请稍后再试", wait)
        if not self._sem.acquire(timeout=self._queue_timeout):
            raise _AskLimited("当前排队的问答已满，请稍后再试", 5.0)
        # 排队期间窗口可能已满：拿到执行权后复核一次，超限则退还执行权
        wait = self._window_wait()
        if wait > 0:
            self._sem.release()
            raise _AskLimited("提问太频繁，请稍后再试", wait)
        with self._lock:
            self._calls.append(self._clock())

    def release(self) -> None:
        self._sem.release()

    def reset(self) -> None:
        """清空速率窗口（测试/运维重置用；不触碰信号量）。"""
        with self._lock:
            self._calls.clear()


ask_limiter = AskLimiter(
    max_concurrent=settings.MAX_CONCURRENT_ASK,
    per_min=settings.ASK_RATE_PER_MIN,
    queue_timeout=settings.ASK_QUEUE_TIMEOUT,
)


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    """Bearer Token 鉴权（AUTH_ENABLE 开启时生效；放行 /、/static、/api/status）。

    位于 request_log 内层：401 拒绝也会被外层请求日志记录（安全审计可见）。
    """
    if auth.check_header(request.headers.get("Authorization")) or auth.is_public(request.url.path):
        return await call_next(request)
    return JSONResponse(
        status_code=401,
        content={"detail": "未授权：请在请求头携带 Authorization: Bearer <令牌>"},
        headers={"WWW-Authenticate": "Bearer"},
    )


@app.middleware("http")
async def request_log(request: Request, call_next):
    """请求中间件：记录 method/path/status/duration_ms/request_id（JSON 行落盘）。

    复用客户端 X-Request-ID（无则生成），回写响应头便于前后端对账；
    uvicorn access_log 已关闭——这里的结构化记录是唯一访问日志来源。
    """
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as e:  # noqa: BLE001 —— 未捕获异常也留痕后再抛给上层
        http_log.error(
            "http_request",
            extra={"request_id": request_id, "method": request.method,
                   "path": request.url.path, "status": 500,
                   "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                   "error": f"{type(e).__name__}: {e}"},
            exc_info=True,
        )
        raise
    response.headers["X-Request-ID"] = request_id
    http_log.info(
        "http_request",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "duration_ms": round((time.perf_counter() - start) * 1000, 1),
        },
    )
    return response


class AskReq(BaseModel):
    query: str
    level: int = 3
    session_id: str | None = None


class AgentStepReq(BaseModel):
    """AI 沙箱工具层单步请求：首轮传 query，后续轮传 state + tool_results。

    工具在服务端 Python 沙箱执行（pypedia.seams.python_exec，受控子进程 /
    Docker 隔离），服务端只做 LLM 编排，因此本端点无状态：会话历史由
    pydantic-ai 序列化为 opaque state 字符串，前端原样带回。
    """
    query: str | None = None
    state: str | None = None
    tool_results: list[dict] | None = None
    level: int = 3


class SandboxExecReq(BaseModel):
    """服务端 Python 执行请求（替代浏览器 Pyodide）。

    返回 job_id 后由客户端轮询 /api/sandbox/job/{id} 取增量输出，
    或调 /api/sandbox/cancel/{id} 强杀（见 pypedia/seams/python_exec.py）。
    """
    code: str
    timeout: float | None = None


class SandboxInstallReq(BaseModel):
    """服务端装包请求：packages 可为空格/逗号分隔的多个包名。"""

    packages: str
    index_url: str = ""


def _json_safe(result: dict) -> dict:
    """把引擎返回中的 dataclass（cascade / session）转为可序列化 dict。"""
    r = dict(result)
    if r.get("cascade") is not None:
        r["cascade"] = r["cascade"].to_dict()
    if r.get("session") is not None:
        s = r["session"]
        r["session"] = {
            "session_id": s.session_id,
            "level": s.level,
            "turns": [
                {"user": t.user, "assistant": t.assistant,
                 "confidence": t.confidence, "primary_title": t.primary_title}
                for t in s.turns[-10:]
            ],
            "profile": s.profile,
        }
    return r


def _get_session(session_id: str | None, level: int) -> Session:
    if session_id:
        s = SESSIONS.get(session_id)
        if s is None:
            s = Session(level=level, session_id=session_id)
            SESSIONS[session_id] = s
        return s
    s = Session(level=level)
    SESSIONS[s.session_id] = s  # 注册，供 /api/profile 等端点按 id 检索
    # 简单上限：超过 100 个会话淘汰最旧的（桌面单用户场景足够）
    if len(SESSIONS) > 100:
        for k in list(SESSIONS)[: len(SESSIONS) - 100]:
            SESSIONS.pop(k, None)
    return s


@app.get("/api/status")
def api_status():
    from pypedia.mcp_client import mcp_manager

    provider = provider_name()
    return {
        "provider": provider,
        "model": settings.BAILIAN_MODEL if provider == "bailian" else settings.OLLAMA_MODEL,
        "web_fetch": plugin_registry.is_enabled("web-fetch"),
        "config": settings.describe(),
        "mcp": mcp_manager.status(),
    }


@app.post("/api/ask")
def api_ask(req: AskReq):
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")
    level = max(1, min(5, int(req.level)))
    session = _get_session(req.session_id, level)
    try:
        ask_limiter.acquire()
    except _AskLimited as e:
        raise HTTPException(status_code=429, detail=str(e),
                            headers={"Retry-After": str(math.ceil(e.retry_after))})
    try:
        result = engine.ask(req.query, level=level, session=session)
    except Exception as e:  # noqa: BLE001 —— 原始异常已由 request_log 中间件落日志
        raise HTTPException(status_code=502, detail="暂时没能生成答案，请稍后再试一次")
    finally:
        ask_limiter.release()
    # 脱敏：不回传密钥
    return JSONResponse(content=_json_safe(result))


@app.post("/api/ask/stream")
def api_ask_stream(req: AskReq):
    """SSE 流式问答：meta → chunk* → done（事件协议见 engine.ask_stream）。

    与 /api/ask 同一套校验与配额（并发/速率/限流）。检索完成后立即回 meta，
    正文逐字到达；流已开始后的引擎异常以 error 事件收尾，不崩连接。
    """
    if not req.query or not req.query.strip():
        raise HTTPException(status_code=400, detail="query 不能为空")
    level = max(1, min(5, int(req.level)))
    session = _get_session(req.session_id, level)
    try:
        ask_limiter.acquire()
    except _AskLimited as e:
        raise HTTPException(status_code=429, detail=str(e),
                            headers={"Retry-After": str(math.ceil(e.retry_after))})

    def _gen():
        try:
            for event, payload in engine.ask_stream(req.query, level=level, session=session):
                data = _json_safe(payload) if event == "done" else payload
                yield (f"event: {event}\n"
                       f"data: {json.dumps(data, ensure_ascii=False, default=str)}\n\n")
        except Exception as e:  # noqa: BLE001 —— 流已开始：以 error 事件收尾，不丢连接（原始异常已由中间件落日志）
            yield (f"event: error\ndata: "
                   f"{json.dumps({'detail': '暂时没能生成答案，请稍后再试一次'}, ensure_ascii=False)}\n\n")
        finally:
            ask_limiter.release()

    return StreamingResponse(
        _gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                 "Connection": "keep-alive"},
    )


# ---------- 知识库 / 离线文档 / 画像 / 自进化 ----------
class UrlReq(BaseModel):
    url: str
    role: str = "main"
    title: str | None = None
    max_pages: int = 6


class GithubReq(BaseModel):
    repo: str
    role: str = "supplement_a"
    title: str | None = None


class FeedbackReq(BaseModel):
    query: str = ""
    issue: str
    lesson: str = ""
    level: int = 3


@app.get("/api/sources")
def api_sources():
    return {"sources": knowledge.list_sources(), "stats": knowledge.stats(),
            "supported_exts": knowledge.supported_exts}


@app.post("/api/sources/url")
def api_sources_url(req: UrlReq):
    if not req.url.strip():
        raise HTTPException(status_code=400, detail="url 不能为空")
    return knowledge.ingest_url(req.url, req.role, req.title, req.max_pages)


@app.post("/api/sources/github")
def api_sources_github(req: GithubReq):
    if not req.repo.strip():
        raise HTTPException(status_code=400, detail="repo 不能为空")
    return knowledge.ingest_github(req.repo, req.role, req.title)


@app.post("/api/sources/upload")
async def api_sources_upload(file: UploadFile = File(...),
                             role: str = Form("supplement_b")):
    import tempfile
    from pathlib import Path

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in knowledge.supported_exts:
        raise HTTPException(status_code=400,
                            detail=f"不支持的格式 {suffix}，支持：{knowledge.supported_exts}")
    # 流式写入 + 大小上限检查（不把超大文件整个读进内存）
    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        written = 0
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > limit:
                tmp.close()
                Path(tmp.name).unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"文件超过上限 {settings.MAX_UPLOAD_MB:.0f}MB，已拒绝",
                )
            tmp.write(chunk)
        tmp_path = tmp.name
    try:
        return knowledge.ingest_file(tmp_path, role, file.filename, file.filename)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.delete("/api/sources/{source_id}")
def api_sources_delete(source_id: str):
    ok = knowledge.delete_source(source_id)
    return {"ok": ok}


@app.get("/api/profile")
def api_profile(session_id: str | None = None):
    """跨会话画像（Mem0）+ 当前会话画像（主题/卡点/偏好）。"""
    out = engine.memory.get_profile()
    if session_id:
        s = SESSIONS.get(session_id)
        if s is not None:
            topics = sorted(s.profile["topics"].items(), key=lambda x: -x[1])[:8]
            out["session"] = {
                "session_id": s.session_id,
                "turns": len(s.turns),
                "topics": [{"topic": k, "count": v} for k, v in topics],
                "weak_spots": s.profile["weak_spots"],
                "prefers": s.profile["prefers"][-5:],
            }
    return out


@app.get("/api/memory/export")
def api_memory_export():
    """导出长期记忆（id+文本）为 JSON，供前端下载 / 备份。"""
    items = engine.memory.get_profile().get("memory_items", [])
    return {"items": items, "count": len(items)}


@app.delete("/api/memory/{mem_id}")
def api_memory_delete(mem_id: str):
    """删除单条长期记忆（Mem0 真实 id 或本地 cache:<index>）。"""
    ok = engine.memory.delete_memory(mem_id)
    if not ok:
        raise HTTPException(status_code=404, detail="未找到该记忆或删除失败")
    return {"ok": True, "deleted": mem_id}


@app.get("/api/evolution")
def api_evolution():
    if not plugin_registry.is_enabled("evolution"):
        raise HTTPException(status_code=503, detail="自进化插件已在设置中关闭")
    return engine.evolution.state()


@app.get("/api/capabilities")
def api_capabilities():
    """预留入口面板：百炼模型能力（含未开通占位）+ 协议层能力（MCP/A2A/子代理/Skill/Ollama）。"""
    from pypedia.models.dashscope import capability_report
    from pypedia.capabilities import capabilities

    return {"models": capability_report(), "capabilities": capabilities.describe()}


@app.get("/api/mcp")
def api_mcp():
    """MCP 协议层真实连接状态（后台线程长连接，供能力面板展示）。"""
    from pypedia.mcp_client import mcp_manager

    return {"servers": mcp_manager.status()}


@app.get("/api/cost")
def api_cost():
    """成本 / token 面板数据：嵌入缓存统计（零触网）+ 当前模型通道。

    estimated_saved_tokens 为粗估：每条落盘向量 = 一次本需重算的百炼嵌入调用。
    """
    from pypedia.embed_cache import global_stats
    from pypedia.models.registry import registry

    return {
        "provider": settings.LLM_PROVIDER,
        "models": {
            "chat": registry.name("chat"),
            "embed": registry.name("embed"),
            "embed_v4": registry.name("embed_v4"),
        },
        "embed_cache": global_stats(),
    }


@app.post("/api/sources/preset")
def api_sources_preset(force: bool = False):
    """一键导入预置权威资料源（Python 官方文档 / CPython / 官方论坛）。幂等。

    未开启联网抓取时返回 disabled + 可操作提示（不写任何资料源记录，避免知识库页
    凭空多出一片 pending），前端据此提示用户如何开启。
    """
    from pypedia.ingest import ingest_preset_sources

    r = ingest_preset_sources(force=force)
    return {"ok": not r.get("disabled"), **r}


@app.post("/api/evolution/feedback")
def api_evolution_feedback(req: FeedbackReq):
    if not plugin_registry.is_enabled("evolution"):
        raise HTTPException(status_code=503, detail="自进化插件已在设置中关闭")
    if not req.issue.strip():
        raise HTTPException(status_code=400, detail="issue 不能为空")
    r = engine.evolution.feedback(req.query, req.issue, req.lesson, req.level)
    # 沉淀失败如实返回 500：否则前端会照常提示"已沉淀成技能"，与真实结果不符
    if not r.get("ok"):
        raise HTTPException(status_code=500, detail=r.get("error", "反馈沉淀失败"))
    return r


# ---------- 服务端 Python 沙箱（P2：替代浏览器 Pyodide 微缩运行器） ----------
_exec_backend = None


def _get_exec():
    """懒加载执行后端单例（按 SANDBOX_BACKEND 选 local / docker）。"""
    global _exec_backend
    if _exec_backend is None:
        from pypedia.seams import python_exec as _pe

        _exec_backend = _pe.get_python_exec()
    return _exec_backend


@app.get("/api/sandbox/status")
def api_sandbox_status():
    """沙箱可用性自检：服务端执行后端 + 代理开关（前端沙箱页加载时调用）。

    不触网、不耗额度：返回后端类型 / Python 版本 / 网络隔离与否 /
    已装包清单 / 代理开关，供前端展示。
    """
    return _get_exec().status()


@app.post("/api/sandbox/exec")
def api_sandbox_exec(req: SandboxExecReq):
    """提交一段 Python 代码到服务端沙箱执行，返回 job_id（异步 + 可取消）。

    客户端轮询 /api/sandbox/job/{id} 取增量输出；中途可 POST
    /api/sandbox/cancel/{id} 强杀。代码限长沿用 AGENT_MAX_CODE_CHARS。
    """
    if not plugin_registry.is_enabled("sandbox"):
        raise HTTPException(status_code=503,
                            detail="AI 沙箱工具层已在设置中关闭")
    code = req.code or ""
    if not code.strip():
        raise HTTPException(status_code=400, detail="代码不能为空")
    if len(code) > settings.AGENT_MAX_CODE_CHARS:
        raise HTTPException(status_code=400,
                            detail=f"代码超过上限 {settings.AGENT_MAX_CODE_CHARS} 字符")
    job_id = _get_exec().run_job(code, timeout=req.timeout)
    return {"job_id": job_id, "status": "running"}


@app.get("/api/sandbox/job/{job_id}")
def api_sandbox_job(job_id: str):
    """轮询执行任务：返回 {status, stdout, stderr, returncode, ms, error, timed_out}。"""
    job = _get_exec().get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    return job


@app.post("/api/sandbox/cancel/{job_id}")
def api_sandbox_cancel(job_id: str):
    """强杀一个正在运行的执行任务（超时 / 死循环兜底）。"""
    ok = _get_exec().cancel_job(job_id)
    return {"ok": ok}


@app.post("/api/sandbox/install")
def api_sandbox_install(req: SandboxInstallReq):
    """在服务端沙箱装包（纯 Python 包走 PyPI/镜像；二进制包受运行环境限制）。"""
    if not plugin_registry.is_enabled("sandbox"):
        raise HTTPException(status_code=503,
                            detail="AI 沙箱工具层已在设置中关闭")
    pkgs = [p for p in req.packages.replace(",", " ").split() if p]
    if not pkgs:
        raise HTTPException(status_code=400, detail="包名不能为空")
    # 逐个安装，合并结果（避免一个失败丢全部信息）
    results = [_get_exec().install_package(p, index_url=req.index_url) for p in pkgs]
    ok = all(r.ok for r in results)
    message = "；".join((("✓ " if r.ok else "✗ ") + r.message) for r in results)
    return {"ok": ok, "message": message,
            "installed_packages": _get_exec().status()["installed_packages"]}


@app.get("/api/sandbox/proxy")
def api_sandbox_proxy(url: str):
    """沙箱外部资源代理：fetch_url 工具 / 沙箱页抓取公网资源的服务端腿。

    SSRF 防护（私网/回环/元数据地址拦截、逐跳重定向校验、体积上限）见
    pypedia.sandbox_proxy.proxy_fetch；错误码 → HTTP 状态映射如下。
    """
    from pypedia.sandbox_proxy import ProxyError, proxy_fetch

    _PROXY_STATUS = {"bad_url": 400, "blocked_host": 403, "host_not_allowed": 403,
                     "too_large": 413, "timeout": 504, "disabled": 503}
    try:
        return proxy_fetch(url)
    except ProxyError as e:
        raise HTTPException(status_code=_PROXY_STATUS.get(e.code, 502),
                            detail=e.message) from e


@app.post("/api/agent/step")
def api_agent_step(req: AgentStepReq):
    """AI 沙箱工具层（function calling）单步：见 pypedia/agent/transport.py 模块 docstring。

    协议：
      请求 {query, level}            → 首轮：服务端构建 system 并冻结进 state，返回
                                       {type:"tool_calls", calls, state, max_rounds}
                                       或 {type:"final", content, state, provider}；
      请求 {state, tool_results, level} → 续轮：前端带回 state 与服务端沙箱工具
                                       执行结果 [{id, result}]，返回同上两种。
    前端按 type 分流：执行工具后再 POST（max_rounds 轮上限），或渲染最终答案。
    与 ask 同一套配额（每次 LLM 调用计一次）；LLM 通道不可用时降级 Mock 直答。
    """
    if not plugin_registry.is_enabled("sandbox"):
        raise HTTPException(status_code=503, detail="AI 沙箱工具层已在配置中关闭")
    # query 与 state 必须且只能提供一个（以 None 判定，空串/空列表同样算"提供了"，
    # 交由 agent_step 的形状校验给出具体错误）
    if (req.query is None) == (req.state is None):
        raise HTTPException(status_code=400, detail="query 与 state 必须且只能提供一个")
    try:
        ask_limiter.acquire()
    except _AskLimited as e:
        raise HTTPException(status_code=429, detail=str(e),
                            headers={"Retry-After": str(math.ceil(e.retry_after))})
    try:
        from pypedia import agent

        return agent.agent_step(query=req.query, state=req.state,
                                tool_results=req.tool_results,
                                level=max(1, min(5, int(req.level))))
    except ValueError as e:
        # 消息形状/参数非法：客户端问题，明确 400（不消耗重试）
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001 —— 编排异常如实 502（原始异常已由中间件落日志）
        raise HTTPException(status_code=502, detail="AI 工具步骤执行失败，请稍后再试")
    finally:
        ask_limiter.release()


# ---------- agent 记忆 / 技能（Hermes 扩展：设置页只读面板 + 技能管理） ---------- #
@app.get("/api/agent/memory")
def api_agent_memory():
    """持久记忆库只读查看（MEMORY.md 项目记忆 + USER.md 用户画像全文）。"""
    if not plugin_registry.is_enabled("agent-memory"):
        raise HTTPException(status_code=503,
                            detail="持久记忆库已在配置/设置中关闭（插件面板可开关）")
    from pypedia.agent import memory as agent_memory_mod

    store = agent_memory_mod.memory_store
    return {
        "memory": store.render("memory"),
        "user": store.render("user"),
        "sections": {
            "memory": [s.header[5:] for s in store.list_sections("memory")],
            "user": [s.header[5:] for s in store.list_sections("user")],
        },
    }


@app.get("/api/agent/skills")
def api_agent_skills(query: str = ""):
    """技能库列表（L2：含何时用/标签/用量；query 非空时关键词过滤）。"""
    if not plugin_registry.is_enabled("agent-skills"):
        raise HTTPException(status_code=503,
                            detail="技能库已在配置/设置中关闭（插件面板可开关）")
    from pypedia.agent import skills as agent_skills_mod

    store = agent_skills_mod.skill_store
    items = store.search(query) if query.strip() else store.list_detail()
    return {"skills": items, "archived": _archived_skill_names()}


def _archived_skill_names() -> list[str]:
    import os

    from pypedia.agent.skills import _skills_dir

    archived = os.path.join(_skills_dir(), "archived")
    try:
        return sorted(os.listdir(archived))
    except OSError:
        return []


@app.get("/api/agent/skills/{name}")
def api_agent_skill_detail(name: str):
    """单个技能全文（L3：SKILL.md 指令正文；查看即计入用量）。"""
    if not plugin_registry.is_enabled("agent-skills"):
        raise HTTPException(status_code=503,
                            detail="技能库已在配置/设置中关闭（插件面板可开关）")
    from pypedia.agent import skills as agent_skills_mod
    from pypedia.agent.skills import SkillError_

    try:
        skill = agent_skills_mod.skill_store.view(name)
    except SkillError_ as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {k: skill[k] for k in
            ("name", "description", "when_to_use", "tags", "version", "body", "usage")}


# ---------- 插件管理（万物皆插件：设置页开关） ---------- #
class PluginToggleReq(BaseModel):
    """用户态开关单个插件（缺省跟随 .env 部署态）。"""

    enabled: bool


@app.get("/api/plugins")
def api_plugins():
    """列出全部插件 + 汇总（enabled / env_blocked 实时读 settings）。"""
    return {"plugins": plugin_registry.list_plugins(), "summary": plugin_registry.summary()}


@app.post("/api/plugins/{pid}")
def api_plugin_toggle(pid: str, req: PluginToggleReq):
    """用户态开关单个插件。

    - 未知 id → 404；
    - 空壳入口（switchable=False，框架基础设施预留）→ 400（不造假开关）；
    - .env 部署态关闭（env_blocked）时仍允许写入——用户先打开，部署态恢复即生效。
    """
    manifest = get_manifest(pid)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"未知插件：{pid}")
    if not manifest.switchable:
        raise HTTPException(
            status_code=400,
            detail=f"「{manifest.name}」为框架基础设施入口，暂无独立开关（switchable=False）")
    plugin_registry.set_enabled(pid, req.enabled)
    return {"ok": True, "plugin": plugin_registry.describe(pid)}


# ---------- Unit 内核视图（万物皆插件：新契约清单，市场/编辑器消费） ---------- #
@app.get("/api/units")
def api_units():
    """全部 unit（新契约视图：type/form/contributions/node_graph 等）。

    内置插件与市场 unit 的 enabled/env_blocked 均与设置页（/api/plugins）
    合并为同一门控来源（plugins/state.json + plugin_registry），防止两个
    视图对同一开关各说各话；示例 unit 不在 plugin_registry，沿用内核门控。
    """
    units = unit_registry.list_units()
    for u in units:
        if get_manifest(u["id"]) is not None or \
                plugin_registry.get_unit(u["id"]) is not None:  # 内置 + 市场 unit
            u["enabled"] = plugin_registry.is_enabled(u["id"])
            u["env_blocked"] = plugin_registry.env_blocked(u["id"])
    return {
        "units": units,
        "summary": {
            "total": len(units),
            "enabled": sum(1 for u in units if u["enabled"]),
            "env_blocked": sum(1 for u in units if u["env_blocked"]),
            "by_type": {
                t: sum(1 for u in units if u["type"] == t)
                for t in ("plugin", "agent", "team")
            },
        },
    }


@app.get("/api/units/{unit_id}")
def api_unit_detail(unit_id: str):
    """单 unit 详情（含 contributions / dependencies / node_graph——图即引擎可执行）。"""
    info = unit_registry.describe(unit_id)
    if info is None:
        raise HTTPException(status_code=404, detail=f"未知 unit：{unit_id}")
    if get_manifest(unit_id) is not None or \
            plugin_registry.get_unit(unit_id) is not None:  # 内置 + 市场 unit
        info["enabled"] = plugin_registry.is_enabled(unit_id)
        info["env_blocked"] = plugin_registry.env_blocked(unit_id)
    return {"unit": info}


# ---------- 市场 v1（P6：三类货架 + 模板/成品双形态 + 上传导入 + 版本门禁） ---------- #
@app.get("/api/market")
def api_market():
    """市场货架视图：已安装 unit 账本 + 注册态 + 平台版本（门禁基准）。"""
    return {
        "platform_version": PLATFORM_VERSION,
        "installed_dir": str(market_store.installed_dir),
        "lock_path": str(market_store.lock_path),
        "shelves": {
            t: [u for u in market_store.list_installed() if u.get("type") == t]
            for t in ("plugin", "agent", "team")
        },
    }


@app.post("/api/market/upload")
async def api_market_upload(file: UploadFile = File(...)):
    """上传导入 unit 包（plugin.json 裸文件或 zip 资源包）。

    全链路：解析 → schema 校验 → 版本门禁（min_platform/dependencies）→
    落盘装载 → 写 units.lock。任何一步失败都不落盘（4xx + 原因）。
    """
    try:
        data = await file.read()
    except Exception as exc:  # noqa: BLE001 —— 读取失败转 400，不裸抛 500
        raise HTTPException(status_code=400, detail=f"读取上传文件失败：{exc}") from exc
    try:
        result = market_store.install_upload(data, file.filename or "")
    except MarketError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "installed": {
        "id": result.unit_id, "name": result.name, "version": result.version,
        "type": result.type, "form": result.form, "path": result.path,
    }}


@app.delete("/api/market/units/{unit_id}")
def api_market_uninstall(unit_id: str):
    """卸载市场安装的 unit（仅 units.lock 账本内；内置/示例拒卸）。"""
    try:
        market_store.uninstall(unit_id)
    except MarketError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "uninstalled": unit_id}


# ---------- 节点编辑器（P7：图即引擎的编排创作面） ---------- #
class EditorReq(BaseModel):
    """画布提交体：graph（节点图）+ meta（导出元信息）。"""

    graph: dict = {}
    meta: dict = {}


@app.get("/api/editor/templates")
def api_editor_templates():
    """编辑器模板：最小可运行链 + 单 Agent 成品图（python-encyclopedia）。"""
    from pypedia.units.editor import encyclopedia_graph, minimal_graph

    return {
        "minimal": minimal_graph(),
        "encyclopedia": encyclopedia_graph(),
        "node_types": [
            {"type": "entry", "label": "入口", "hint": "注入初始 payload"},
            {"type": "exit", "label": "出口", "hint": "捕获结果并终止"},
            {"type": "process", "label": "处理",
             "hint": "params.expr 表达式或 params.ref 引用 unit 处理器"},
            {"type": "plugin", "label": "插件",
             "hint": "params.ref=unit id，params.method 选工具"},
            {"type": "model-call", "label": "模型调用",
             "hint": "调用 LLM（params.identity 选人格），注入可见工具"},
            {"type": "judge", "label": "判断",
             "hint": "按出边 condition 选分支（控制流）"},
        ],
    }


@app.post("/api/editor/validate")
def api_editor_validate(req: EditorReq):
    """校验画布图（结构 + 表达式语法 + registry 引用存在性）。

    引用检查走 ``unit_registry``（内核超集：内置 + 示例 + 市场）——
    GraphRuntime 解析 ref 的真值源；只查 plugin_registry 会漏报
    python-encyclopedia 这类仅在内核注册的引用。
    """
    errors = validate_graph(req.graph, registry=unit_registry)
    return {"ok": not errors, "errors": errors}


@app.post("/api/editor/export")
def api_editor_export(req: EditorReq):
    """导出可运行 unit 包（zip，与市场上传同格式——可再上传/分享）。"""
    try:
        blob, filename = export_unit(req.graph, req.meta)
    except EditorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StreamingResponse(
        io.BytesIO(blob), media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.post("/api/editor/install")
def api_editor_install(req: EditorReq):
    """画一张图直接装成可运行 unit（走市场同一通道：schema+门禁+账本）。"""
    try:
        blob, _name = export_unit(req.graph, req.meta)
    except EditorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        result = market_store.install_upload(blob, _name)
    except MarketError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "installed": {
        "id": result.unit_id, "name": result.name, "version": result.version,
        "type": result.type, "form": result.form, "path": result.path,
    }}


# ---------- agent cron 定时任务（Hermes 扩展：APScheduler + 站内通知） ---------- #
class CronTaskReq(BaseModel):
    """新建/更新定时任务；schedule 形状见 pypedia/agent/cron.preflight。"""

    id: str = ""
    name: str = ""
    kind: str = ""
    task: str = ""
    query: str = ""
    level: int | None = None
    schedule: dict = {}


@app.get("/api/agent/cron")
def api_agent_cron():
    """定时任务列表（含暂停态/下次运行）+ 最近站内通知 + 内置任务清单。"""
    if not plugin_registry.is_enabled("agent-cron"):
        raise HTTPException(status_code=503, detail="定时任务已在配置中关闭")
    from pypedia.agent import cron as agent_cron

    return {
        "tasks": agent_cron.list_tasks(),
        "notifications": agent_cron.list_notifications(),
        "max_tasks": settings.AGENT_CRON_MAX_TASKS,
        "builtin_tasks": [
            {"key": k, "name": v["name"]}
            for k, v in sorted(agent_cron.BUILTIN_TASKS.items())
        ],
    }


@app.post("/api/agent/cron")
def api_agent_cron_add(req: CronTaskReq):
    """新建定时任务（preflight 校验；同 id 覆盖更新）。"""
    if not plugin_registry.is_enabled("agent-cron"):
        raise HTTPException(status_code=503, detail="定时任务已在配置中关闭")
    from pypedia.agent import cron as agent_cron

    try:
        view = agent_cron.add_task(req.model_dump())
    except agent_cron.CronError_ as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "task": view}


@app.delete("/api/agent/cron/{task_id}")
def api_agent_cron_remove(task_id: str):
    if not plugin_registry.is_enabled("agent-cron"):
        raise HTTPException(status_code=503, detail="定时任务已在配置中关闭")
    from pypedia.agent import cron as agent_cron

    try:
        agent_cron.remove_task(task_id)
    except agent_cron.TaskNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return {"ok": True}


@app.post("/api/agent/cron/{task_id}/{action}")
def api_agent_cron_action(task_id: str, action: str):
    """任务操作：pause（暂停）/ resume（恢复）/ run（立即触发一次）。"""
    if not plugin_registry.is_enabled("agent-cron"):
        raise HTTPException(status_code=503, detail="定时任务已在配置中关闭")
    from pypedia.agent import cron as agent_cron

    ops = {"pause": agent_cron.pause_task,
           "resume": agent_cron.resume_task,
           "run": agent_cron.run_task}
    if action not in ops:
        raise HTTPException(status_code=400,
                            detail=f"未知操作：{action!r}（可用：{'/'.join(ops)}）")
    try:
        view = ops[action](task_id)
    except agent_cron.TaskNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except agent_cron.CronError_ as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "task": view}


# ---------- 数据备份 / 恢复 ----------
@app.post("/api/backup/export")
def api_backup_export():
    """导出数据备份 zip（不含令牌/日志）。"""
    from pypedia.backup import export

    r = export()
    if not r.get("ok"):
        raise HTTPException(status_code=500, detail=r.get("error", "导出失败"))
    return FileResponse(r["path"], filename=Path(r["path"]).name,
                        media_type="application/zip")


@app.post("/api/backup/import")
async def api_backup_import(file: UploadFile = File(...)):
    """上传备份 zip 恢复数据（替换语义；恢复前自动快照可回滚）。"""
    import tempfile

    from pypedia.backup import import_backup

    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        written = 0
        while chunk := await file.read(1024 * 1024):
            written += len(chunk)
            if written > limit:
                tmp.close()
                Path(tmp.name).unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=f"备份超过上限 {settings.MAX_UPLOAD_MB:.0f}MB，已拒绝",
                )
            tmp.write(chunk)
        tmp_path = tmp.name
    try:
        r = import_backup(tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("error", "恢复失败"))
    return JSONResponse(content={
        "ok": True, "restored": r["restored"], "items": r["items"],
        "rollback": r["rollback"],
        "note": "恢复完成，建议重启服务使向量索引生效",
    })


# ---------- 静态前端 ----------
if STATIC.exists():
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")


def main() -> None:
    import uvicorn

    p = argparse.ArgumentParser()
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--no-browser", action="store_true")
    args = p.parse_args()

    url = f"http://{args.host}:{args.port}/"
    if not args.no_browser:
        # 桌面环境自动开浏览器；无显示环境（如沙箱）则忽略
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001
            pass

    print(f"[PyPedia] 正在启动 → {url}  （LLM: {settings.LLM_PROVIDER}）")
    # access_log=False：访问日志由 request_log 中间件以结构化 JSON 记录（见上）
    uvicorn.run(app, host=args.host, port=args.port, log_level="info", access_log=False)


if __name__ == "__main__":
    main()
