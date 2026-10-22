"""外部能力接入层（协议层）：MCP（已真实接入）/ 答案审阅 / Ollama。

原则：项目不重复实现这些协议层能力，而是「优先接现成 server，接不上才降级」——
每项能力在此登记：
  · 是否已接入（enabled，MCP 项查真实连接状态，其余查真实配置）
  · 接入方式（how）：一旦配置好对应 server / 通道，自动启用，无需改业务代码
  · 降级行为（fallback）：未接入时项目仍可用，只是少对应增强

本表只登记**有真实代码路径**的能力（2026-10 整改）：纯占位条目
（MCP 联网搜索 / 子代理 / Skill 注册机制）已移除——前端不展示代码中不存在的功能。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Capability:
    key: str
    name: str
    layer: str            # mcp | review | local
    env_enable: str       # 启用开关的环境变量
    how: str              # 接入方式说明
    fallback: str         # 未接入时的降级行为
    builtin_alt: str = "" # 当前用的内置/替代实现
    mcp_key: str = ""     # 已真实接入的 MCP server key（空 = 未接入）


CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        "mcp_fetch", "MCP 网页抓取", "mcp", "MCP_FETCH_ENABLE",
        how="接入 MCP fetch server（python -m mcp_server_fetch，正文转 markdown）",
        fallback="用 requests + trafilatura 抓正文（成熟库）",
        builtin_alt="trafilatura",
        mcp_key="fetch",
    ),
    Capability(
        "mcp_filesystem", "MCP 文件系统", "mcp", "MCP_ENABLE",
        how="接入 MCP filesystem server（npx @modelcontextprotocol/server-filesystem）",
        fallback="直接读上传的临时文件",
        builtin_alt="本地文件 IO",
        mcp_key="filesystem",
    ),
    Capability(
        "mcp_thinking", "MCP 分步推理", "mcp", "MCP_THINKING_ENABLE",
        how="接入 MCP sequential-thinking server，复杂问题拆解为持久化思路便笺",
        fallback="单次生成（提示词内联要求分步）",
        builtin_alt="单次生成",
        mcp_key="thinking",
    ),
    Capability(
        "answer_review", "答案交叉审阅", "review", "REVIEW_ENABLE",
        how="review.py：独立审阅通道（第二模型，temperature=0）对照检索证据审阅答案",
        fallback="仅输出置信度（models/dashscope.evaluate_confidence）",
        builtin_alt="双模型二审",
    ),
    Capability(
        "ollama_local", "本地 Ollama 通道", "local", "LLM_PROVIDER",
        how="本机安装 Ollama 并拉取 qwen2.5-coder 后，在 .env 设 LLM_PROVIDER=ollama",
        fallback="百炼 API（默认 LLM_PROVIDER=bailian）",
        builtin_alt="百炼 qwen-plus",
    ),
)

_BY_KEY = {c.key: c for c in CAPABILITIES}


def _mcp_status() -> dict[str, dict]:
    """真实 MCP 连接状态（manager 未启动时返回空 dict）。"""
    try:
        from ..mcp_client import mcp_manager

        return {s["key"]: s for s in mcp_manager.status()}
    except Exception:
        return {}


@dataclass
class CapabilityRegistry:
    _status: dict[str, bool] = field(default_factory=dict)

    def enabled(self, key: str) -> bool:
        c = _BY_KEY[key]
        if c.mcp_key:  # 已接入的 MCP server：查真实连接状态
            return _mcp_status().get(c.mcp_key, {}).get("connected", False)
        # 其余开关一律走 settings（类型化配置，默认值生效）——
        # 不能 os.getenv：.env 未显式写的键不会进 os.environ，默认值会被误判为关闭
        from ..config import settings

        if key == "ollama_local":  # 本地通道：看真实 provider 配置
            return settings.LLM_PROVIDER == "ollama"
        return bool(getattr(settings, c.env_enable, False))

    def probe_all(self) -> dict[str, bool]:
        for c in CAPABILITIES:
            self._status[c.key] = self.enabled(c.key)
        return dict(self._status)

    def describe(self) -> list[dict]:
        mcp = _mcp_status()
        self.probe_all()
        out = []
        for c in CAPABILITIES:
            item = {
                "key": c.key,
                "name": c.name,
                "layer": c.layer,
                "enabled": self.enabled(c.key),
                "env": c.env_enable,
                "how": c.how,
                "fallback": c.fallback,
                "builtin_alt": c.builtin_alt,
            }
            if c.mcp_key:  # 附带真实连接细节（工具数/失败原因）
                st = mcp.get(c.mcp_key, {})
                item["mcp"] = {
                    "connected": st.get("connected", False),
                    "detail": st.get("detail", "未启动"),
                    "tools": st.get("tools", []),
                }
            out.append(item)
        return out


capabilities = CapabilityRegistry()
