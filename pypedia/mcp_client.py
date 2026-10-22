"""MCP 客户端（官方 modelcontextprotocol/python-sdk，stdio 传输）。

选型说明（2026-10 调研 + 实测）：
- 官方 Python SDK 2.x 系列：stdio_client + ClientSession 经典 API（2026-10-19
  起 2.x 成为 fetch server 的硬要求，见下）；
- 官方 fetch server（mcp-server-fetch 2026.10.19）Requires-Dist: mcp<3,>=2.3，
  与 SDK 2.3.0 组合实测可用；旧版 fetch server（≤2026.10.10）只 import
  McpError（1.x 名称，2.x 已改名 MCPError），与 2.x SDK 不兼容；
- filesystem / sequential-thinking 走 npm（npx），与 SDK 版本解耦。

设计（桌面场景）：
- 真实接入 3 个无密钥官方参考 server：filesystem / fetch / sequential-thinking；
- 同步/异步桥用 anyio 的 BlockingPortal（anyio.from_thread.start_blocking_portal）：
  portal 在新线程中跑专用事件循环，stdio 长连接常驻该 loop；
  同步调用方经 portal.call(...) 提交协程并阻塞等结果（带超时），
  不再手写「后台线程 + run_coroutine_threadsafe」桥（铁律：复用现成组件）；
- 任何 server 起不来（无 Node/网络/缺依赖）都只降级该项，不影响主流程；
- 上层消费：
  · fetch            → ingest._crawl_site 抓取正文（开关 MCP_FETCH_ENABLE）
  · sequential-thinking → engine 复杂问题分步推理（开关 MCP_THINKING_ENABLE）
  · filesystem       → 能力面板展示状态 + 预留本地目录读取
"""
from __future__ import annotations

import asyncio
import os
import shutil
import threading
from dataclasses import dataclass, field

import anyio
from anyio.from_thread import BlockingPortal, start_blocking_portal

from .config import settings
from .plugins import plugin_registry

DATA_DIR = os.getenv("PYPEDIA_DATA", os.path.join(os.path.expanduser("~"), ".pypedia"))


@dataclass
class ServerSpec:
    key: str
    name: str
    command: str          # npx | python
    args: list[str]
    needs_node: bool = False
    enabled: bool = True
    env_extra: dict = field(default_factory=dict)


def _specs() -> list[ServerSpec]:
    fs_dir = settings.MCP_FS_DIR or DATA_DIR
    return [
        ServerSpec("filesystem", "MCP 文件系统", "npx",
                   ["-y", "@modelcontextprotocol/server-filesystem", fs_dir],
                   needs_node=True, enabled=True),
        ServerSpec("fetch", "MCP 网页抓取", "python",
                   ["-m", "mcp_server_fetch"], needs_node=False,
                   enabled=settings.MCP_FETCH_ENABLE),
        ServerSpec("thinking", "MCP 分步推理", "npx",
                   ["-y", "@modelcontextprotocol/server-sequential-thinking"],
                   needs_node=True, enabled=settings.MCP_THINKING_ENABLE),
    ]


class MCPManager:
    """MCP server 连接管理器：anyio BlockingPortal + 长连接 + 状态可查。"""

    def __init__(self) -> None:
        self._portal: BlockingPortal | None = None
        self._thread: threading.Thread | None = None
        # anyio.Event 必须在 portal loop 上 wait/set（见 _serve/_request_stop）
        self._stop_async: anyio.Event | None = None
        self._clients: dict = {}           # key -> (stdio_cm, session)
        self._tools: dict[str, list] = {}  # key -> 工具列表
        self._status: dict[str, dict] = {}  # key -> {connected, detail}
        self._started = False

    # —— 生命周期 —— #
    def start(self) -> None:
        if not plugin_registry.is_enabled("mcp") or self._started:
            return
        self._started = True
        self._thread = threading.Thread(target=self._run_worker, daemon=True,
                                        name="mcp-portal-host")
        self._thread.start()

    def _run_worker(self) -> None:
        # anyio 的 blocking portal 自行在新线程跑事件循环并常驻；本宿主线程
        # 只持有 with 作用域。_serve 在同一个 portal task 里完成
        # 「连接 → 保活 → 关闭」全生命周期：
        # anyio 的 cancel scope 要求进入与退出在同一 task 且退出时为 innermost，
        # 因此 stdio/session 的 __aenter__/__aexit__ 绝不能分散到多次 portal.call
        # （跨 task 退出必抛 "cancel scope in a different task"），也不能包在
        # move_on_after/wait_for 里（加的 scope 会破坏 innermost 检查）。
        with start_blocking_portal() as portal:
            self._portal = portal
            try:
                portal.call(self._serve)
            except Exception as e:  # noqa: BLE001 —— 保活/关闭失败不拖垮宿主线程
                print(f"[MCP] 后台任务退出：{type(e).__name__}: {e}")

    async def _serve(self) -> None:
        self._stop_async = anyio.Event()
        try:
            await self._connect_all()
        except Exception as e:  # noqa: BLE001 —— 连接失败不拖垮保活与关闭
            print(f"[MCP] 初始化失败：{type(e).__name__}: {e}")
        await self._stop_async.wait()   # close() 经 portal 置位后进入关闭
        await self._shutdown_async()

    async def _connect_all(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        for spec in _specs():
            if not spec.enabled:
                self._status[spec.key] = {"connected": False, "detail": "已在配置中关闭"}
                continue
            if spec.needs_node and not shutil.which("npx") and not shutil.which("npx.cmd"):
                self._status[spec.key] = {"connected": False, "detail": "未检测到 Node.js（npx），跳过"}
                continue
            command = spec.command
            if spec.needs_node and not shutil.which("npx") and shutil.which("npx.cmd"):
                command = "npx.cmd"  # Windows
            stdio = None
            session = None
            stdio_entered = False
            try:
                params = StdioServerParameters(
                    command=command, args=spec.args, env=self._child_env(spec)
                )
                # 手动进入两个上下文并保持长连接（async with 退出即杀子进程）
                stdio = stdio_client(params)
                read, write = await stdio.__aenter__()
                stdio_entered = True
                session = ClientSession(read, write)
                await session.__aenter__()
                await session.initialize()
                tools = await session.list_tools()
                self._clients[spec.key] = (stdio, session)
                self._tools[spec.key] = [
                    {"name": t.name, "description": (t.description or "")[:80]}
                    for t in tools.tools
                ]
                self._status[spec.key] = {
                    "connected": True,
                    "detail": f"{len(tools.tools)} 个工具",
                }
                print(f"[MCP] {spec.name} 已连接（{len(tools.tools)} 工具）")
            except BaseException as e:  # noqa: BLE001 —— 单 server 失败只降级该项：
                # 子进程起即崩（如版本不兼容）时，stdio_client 的任务组会抛
                # BaseExceptionGroup 或 CancelledError——3.11 起二者都是
                # BaseException 子类，except Exception 兜不住，会冲垮整个
                # _connect_all 使后续 server 连不上。连接是一次性启动动作，
                # 此处捕获即「该 server 不可用」，继续连下一个。
                await self._cleanup_partial(session, stdio, stdio_entered, e)
                self._status[spec.key] = {"connected": False, "detail": f"{type(e).__name__}: {e}"[:100]}

    @staticmethod
    async def _cleanup_partial(session, stdio, stdio_entered: bool, exc: BaseException) -> None:
        """尽力退出连接失败路径上已进入的上下文（杀子进程、收任务组）。

        不退出会让 stdio_client 的子进程与任务组泄漏到 portal 停止时才取消，
        触发 anyio「Attempted to exit a cancel scope in a different task」
        竞态噪音。硬性约束：
        - 只对确认 `__aenter__` 成功返回的 stdio generator 调 `__aexit__`；
          对未启动的 async generator 调 `asend` 会真的把它跑起来（起子进程），
          而 `athrow`（传异常路径）只会把异常扔回调用方，不会执行生成器体。
        - session 是普通对象的 async 方法，未进入也无副作用。
        - **不能**用 move_on_after/wait_for/timeout 包裹 `__aexit__`：这些会
          新起 Task 或加一层 cancel scope，而 anyio 要求 scope 退出时必须是
          当前 task 的 innermost（同 task、同嵌套层级），否则必抛
          "cancel scope in a different task"。stdio 的 shutdown 内部所有
          wait 本身有界（见 mcp stdio_client 源码注释），直接 await 不会挂死。
        - 每个退出都兜底：清理是尽力而为，不能再拖垮降级路径。
        """
        exc_info = (type(exc), exc, exc.__traceback__)
        for ctx, entered in ((session, True), (stdio, stdio_entered)):
            if ctx is None or not entered:
                continue
            try:
                await ctx.__aexit__(*exc_info)
            except BaseException:  # noqa: BLE001 —— 清理失败只吞不冒
                pass

    @staticmethod
    def _child_env(spec: ServerSpec) -> dict:
        # 子进程不继承主环境（MCP 安全模型），显式传 PATH 与必要变量
        env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
        env.update(spec.env_extra)
        return env

    # —— 工具调用（同步等结果，带超时） —— #
    def call_tool(self, key: str, tool: str, args: dict, timeout: float = 30.0):
        """调用指定 server 的工具；未连接/失败返回 None（上层降级）。"""
        client = self._clients.get(key)
        portal = self._portal
        if client is None or portal is None:
            return None
        try:
            # wait_for 提供超时（portal.call 本身无超时语义）；超时/未连接均降级 None
            return portal.call(self._call_tool_async, key, tool, args, timeout)
        except Exception:  # noqa: BLE001 —— 未连接/超时/调用失败统一降级
            return None

    async def _call_tool_async(self, key: str, tool: str, args: dict, timeout: float):
        _stdio, session = self._clients[key]
        result = await asyncio.wait_for(session.call_tool(tool, args), timeout=timeout)
        if getattr(result, "isError", False):
            return None
        texts = [getattr(c, "text", "") for c in getattr(result, "content", [])]
        return "\n".join(t for t in texts if t)

    # —— 状态（能力面板） —— #
    def status(self) -> list[dict]:
        out = []
        for spec in _specs():
            st = self._status.get(spec.key) or {"connected": False, "detail": "未启动"}
            out.append({
                "key": spec.key, "name": spec.name,
                "connected": st.get("connected", False),
                "detail": st.get("detail", ""),
                "tools": self._tools.get(spec.key, []),
            })
        return out

    # —— 优雅关闭（退出时释放子进程） —— #
    def close(self) -> None:
        portal = self._portal
        if portal is None:
            return
        try:
            # 经 portal 在 loop 上置位 stop 事件：_serve 随后在同一 task 内
            # 执行 _shutdown_async（stdio/session 的 __aexit__ 与 __aenter__
            # 同 task 同层级，满足 anyio cancel scope 约束）。
            portal.call(self._request_stop_async)
        except BaseException:  # noqa: BLE001 —— 关闭尽力而为：
            # portal 停止时遗留任务组可能抛 BaseExceptionGroup，不应冒到 atexit
            pass
        if self._thread is not None:
            self._thread.join(timeout=15)
        self._portal = None

    async def _request_stop_async(self) -> None:
        if self._stop_async is not None:
            self._stop_async.set()

    async def _shutdown_async(self) -> None:
        # 必须逆序关闭（后进先出）：anyio 的 cancel scope 退出时必须是
        # 当前 task 的 innermost——后连接的 server 的 scope 在栈顶，先退。
        # 每个 server 内 session 的 tg 后进先退，stdio 的 tg 最后退。
        for stdio, session in reversed(list(self._clients.values())):
            for ctx in (session, stdio):
                if ctx is None:
                    continue
                try:
                    await ctx.__aexit__(None, None, None)
                except BaseException:  # noqa: BLE001 —— 关闭是尽力而为：
                    # 子进程已死时任务组可能抛 CancelledError/BaseExceptionGroup
                    pass
        self._clients.clear()


mcp_manager = MCPManager()

# 进程退出时释放 MCP 子进程，避免孤儿进程
import atexit  # noqa: E402

atexit.register(mcp_manager.close)
