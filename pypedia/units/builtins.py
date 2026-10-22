"""内置 Unit 清单（plugin.json 契约的内存态真值源）。

P1 迁移的核心决策：**23 个内置插件（16 实插件 + 7 空壳入口）的唯一真值源
放在新契约里**——本模块以 Unit manifest 字典（与 ``units/schema/unit.schema.json``
同构）登记全部内置能力；旧 ``pypedia/plugins/manifests.py`` 的 ``BUILTIN_PLUGINS``
（frozen dataclass 元组）退化为**投影视图**，供兼容层与设置页消费。

字段语义（与旧 Plugin 一一对应，多出的是新契约字段）：
- ``form=instance``：内置插件即开箱即用的成品对象；
- ``contributions.agent_tools``：Agent 工具循环的裸可调用入口（module:attr），
  按声明顺序装配——memory(4) → skills(2) → delegate(1)，与插件化前的
  ``BROWSER_TOOLS+SERVER_TOOLS+DELEGATE_TOOLS`` 恒等（11 工具断言是裁判）；
- ``apply``：新契约用 ``immediate``（旧视图归一为 ``instant``，见 manifests 投影）；
- 空壳入口（``switchable=False``）：框架基础设施，恒开、不造假开关。

边界（刻意不登记）：LLM/agent 框架本体（pypedia/agent/{bailian_model,transport}.py、
pypedia/llm/、pypedia/models/）——发动机零件，不是插件。
"""
from __future__ import annotations

from typing import Any

from .manifest import Manifest
from .registry import UnitRegistry

# —— Agent 扩展（Hermes 特性，pypedia/agent/） —— #
_AGENT_MEMORY: dict[str, Any] = {
    "id": "agent-memory",
    "type": "plugin",
    "name": "持久记忆库",
    "version": "1.0.0",
    "description": (
        "MEMORY.md/USER.md 双库 + FTS5 中文检索：AI 跨会话记住项目事实与用户画像，"
        "可按段落精确增删改。"
    ),
    "default_enabled": True,
    "switchable": True,
    "env_gate": "AGENT_MEMORY_ENABLE",
    "apply": "immediate",
    "form": "instance",
    "contributions": {
        "agent_tools": [
            "pypedia.agent.server_tools:memory_search",
            "pypedia.agent.server_tools:memory_add",
            "pypedia.agent.server_tools:memory_patch",
            "pypedia.agent.server_tools:memory_remove",
        ],
    },
}
_AGENT_SKILLS: dict[str, Any] = {
    "id": "agent-skills",
    "type": "plugin",
    "name": "技能库",
    "version": "1.0.0",
    "description": (
        "SKILL.md 三级渐进披露（清单进提示词 / 详情设置页 / 全文按需读）+ "
        "Curator 30 天未用自动归档。"
    ),
    "default_enabled": True,
    "switchable": True,
    "env_gate": "AGENT_SKILLS_ENABLE",
    "apply": "immediate",
    "form": "instance",
    "contributions": {
        "agent_tools": [
            "pypedia.agent.server_tools:skill_list",
            "pypedia.agent.server_tools:skill_view",
        ],
    },
}
_AGENT_CRON: dict[str, Any] = {
    "id": "agent-cron",
    "type": "plugin",
    "name": "定时任务",
    "version": "1.0.0",
    "description": (
        "cron 表达式 / 固定间隔 / 一次性三种触发；内置任务（归档冷技能）与 "
        "Agent 任务（到点跑一轮问答，结果发站内通知）。"
    ),
    "default_enabled": True,
    "switchable": True,
    "env_gate": "AGENT_CRON_ENABLE",
    "apply": "restart",
    "form": "instance",
}
_AGENT_DELEGATE: dict[str, Any] = {
    "id": "agent-delegate",
    "type": "plugin",
    "name": "子代理委派",
    "version": "1.0.0",
    "description": (
        "delegate_task 工具：派上下文隔离的子代理并行干活，限时限流，"
        "失败自动回退主代理自行完成。"
    ),
    "default_enabled": True,
    "switchable": True,
    "env_gate": "AGENT_DELEGATE_ENABLE",
    "apply": "immediate",
    "form": "instance",
    "contributions": {
        "agent_tools": [
            "pypedia.agent.delegate:delegate_task",
        ],
    },
}
_AGENT_REDACT: dict[str, Any] = {
    "id": "agent-redact",
    "type": "plugin",
    "name": "敏感信息脱敏",
    "version": "1.0.0",
    "description": (
        "detect-secrets 24 插件 + 裸令牌检测：记忆写入与工具结果出口双闸门，"
        "密钥/令牌不落盘不进上下文。"
    ),
    "default_enabled": True,
    "switchable": True,
    "env_gate": "AGENT_REDACT_SECRETS",
    "apply": "immediate",
    "form": "instance",
}
_AGENT_COMPRESS: dict[str, Any] = {
    "id": "agent-compress",
    "type": "plugin",
    "name": "历史压缩（入口）",
    "version": "1.0.0",
    "description": (
        "pydantic-ai ProcessHistory：超预算时保留系统提示词与近期对话，"
        "工具调用对完整，防 state 无界增长。当前随 Agent 框架运行，"
        "独立开关开发中。"
    ),
    "default_enabled": True,
    "switchable": False,
    "apply": "immediate",
    "form": "instance",
}
_AGENT_HOOKS: dict[str, Any] = {
    "id": "agent-hooks",
    "type": "plugin",
    "name": "事件钩子（入口）",
    "version": "1.0.0",
    "description": (
        "blinker 7 信号（step 进出/脱敏/记忆写/技能看/委派/定时任务）+ "
        "审计日志接收器。当前随 Agent 框架运行，独立开关开发中。"
    ),
    "default_enabled": True,
    "switchable": False,
    "apply": "immediate",
    "form": "instance",
}

# —— 沙箱与代码执行（C1） —— #
_SANDBOX: dict[str, Any] = {
    "id": "sandbox",
    "type": "plugin",
    "name": "AI 沙箱工具层",
    "version": "1.0.0",
    "description": (
        "run_python / install_package / fetch_url / sandbox_status 四个工具："
        "AI 在服务端 Python 沙箱（受控子进程 / Docker 隔离）里真跑代码验证答案。"
    ),
    "default_enabled": True,
    "switchable": True,
    "env_gate": "AGENT_ENABLE",
    "apply": "immediate",
    "form": "instance",
}
_SANDBOX_PROXY: dict[str, Any] = {
    "id": "sandbox-proxy",
    "type": "plugin",
    "name": "沙箱外部资源代理",
    "version": "1.0.0",
    "description": (
        "沙箱内 pyfetch 的同源代理：scheme 白名单 + 私网 IP 拦截 + "
        "逐跳重定向校验（SSRF 防护）。"
    ),
    "default_enabled": True,
    "switchable": True,
    "env_gate": "SANDBOX_PROXY_ENABLE",
    "apply": "immediate",
    "form": "instance",
}

# —— 协议层与增强 —— #
_MCP: dict[str, Any] = {
    "id": "mcp",
    "type": "plugin",
    "name": "MCP 协议层",
    "version": "1.0.0",
    "description": (
        "官方 MCP server 接入（网页抓取 / 文件系统 / 分步推理）；子开关 "
        "MCP_FETCH_ENABLE / MCP_THINKING_ENABLE 在 .env 单独控制。"
    ),
    "default_enabled": True,
    "switchable": True,
    "env_gate": "MCP_ENABLE",
    "apply": "restart",
    "form": "instance",
}
_REVIEW: dict[str, Any] = {
    "id": "review",
    "type": "plugin",
    "name": "答案交叉审阅",
    "version": "1.0.0",
    "description": "双模型二审：第二模型（temperature=0）对照检索证据审阅答案，降低幻觉。",
    "default_enabled": True,
    "switchable": True,
    "env_gate": "REVIEW_ENABLE",
    "apply": "immediate",
    "form": "instance",
}
_WEB_FETCH: dict[str, Any] = {
    "id": "web-fetch",
    "type": "plugin",
    "name": "联网抓取",
    "version": "1.0.0",
    "description": (
        "提问时抓取官方文档/GitHub/论坛页面正文（trafilatura 抽取），"
        "不可达自动降级本地语料。"
    ),
    "default_enabled": False,
    "switchable": True,
    "env_gate": "ENABLE_WEB_FETCH",
    "apply": "immediate",
    "form": "instance",
}
_PRESET_SOURCES: dict[str, Any] = {
    "id": "preset-sources",
    "type": "plugin",
    "name": "预置权威资料源",
    "version": "1.0.0",
    "description": (
        "Python 官方文档 / CPython / 官方论坛自动登记入库（关闭联网时"
        "仍登记为 pending 并附开启指引）。"
    ),
    "default_enabled": True,
    "switchable": True,
    "env_gate": "PRESET_SOURCES_ENABLE",
    "apply": "restart",
    "form": "instance",
}
_LOCAL_RERANK: dict[str, Any] = {
    "id": "local-rerank",
    "type": "plugin",
    "name": "本地重排",
    "version": "1.0.0",
    "description": (
        "bge-reranker 精排（首次自动下载）：向量+关键词混合检索后相关性"
        "重排，提升答案依据质量。"
    ),
    "default_enabled": True,
    "switchable": True,
    "env_gate": "RERANK_LOCAL_ENABLE",
    "apply": "immediate",
    "form": "instance",
}

# —— 图表渲染（P4 diagram-render：mermaid/echarts 前端资产懒加载） —— #
_DIAGRAM_RENDER: dict[str, Any] = {
    "id": "diagram-render",
    "type": "plugin",
    "name": "图表渲染",
    "version": "1.0.0",
    "description": (
        "mermaid 图解 + ECharts 图表：答案中的 ```mermaid / ```chart 代码块"
        "渲染为交互图形。前端资产按门控懒加载——关闭时不下载 ~4.7MB vendor，"
        "代码块降级为普通高亮。"
    ),
    "default_enabled": True,
    "switchable": True,
    "env_gate": "DIAGRAM_RENDER_ENABLE",
    "apply": "immediate",
    "form": "instance",
    "contributions": {
        "ui_panels": [
            {
                "slot": "render.hook",
                "entry": "diagram-render:frontend",
                "assets": [
                    "/static/vendor/mermaid.min.js",
                    "/static/vendor/echarts.min.js",
                ],
                "lazy": True,
            }
        ],
        "system_prompt_sections": [
            {
                "name": "diagram-render:guide",
                "order": 80,
                "text": (
                    "【图表渲染规约（diagram-render）】\n"
                    "· 适合可视化的内容优先给图，别用大段文字堆结构：\n"
                    "· 流程/状态机/层次/依赖关系 → ```mermaid 代码块"
                    "（flowchart TD / stateDiagram-v2 / classDiagram 等）；\n"
                    "· 数据对比/分布/趋势 → ```chart 代码块，内容为 ECharts option 的"
                    " JSON（含 series 与 xAxis/yAxis）；\n"
                    "· mermaid 只用安全子集：不引外部 CSS/JS、不用 click 回调；"
                    "chart 的 formatter 不要含 HTML 标签；\n"
                    "· 每张图配一句话解读，别只甩图不解释。"
                ),
            }
        ],
    },
}

# —— 规则引擎（P5 rule-engine：能力激活的确定性路由，master plan §6） —— #
# 四类策略数据化：pin-core（核心能力常驻）/ 等级条件触发（委派、图表）/
# 确定性路由（求值结果过滤工具可见性，fail-closed）/ 主动注入（命名段落）。
# 规则本身也是数据：第三方插件可在自己的 contributions.rules 自声明触发条件，
# 由 RuleEngine.from_contributions 并集汇总；本插件可整体关闭（路由层旁路，
# 行为回到「插件启用即可见」——与插件化前恒等）。
_RULE_ENGINE: dict[str, Any] = {
    "id": "rule-engine",
    "type": "plugin",
    "name": "规则引擎",
    "version": "1.0.0",
    "description": (
        "能力激活的确定性路由：LLM 调用前按规则求值 active set——核心能力"
        "（记忆/技能）pinned 常驻，委派/图表按等级条件触发，查询意图可附加"
        "激活；未进激活集的能力不可见（fail-closed），不用每轮 @引用。"
    ),
    "default_enabled": True,
    "switchable": True,
    "env_gate": "RULE_ENGINE_ENABLE",
    "apply": "immediate",
    "form": "instance",
    "contributions": {
        "rules": [
            {
                # always-on / pinned：核心能力显式 allow-list 兜底
                "id": "pin-core",
                "when": {"always": True},
                "then": {"activate": ["agent-memory", "agent-skills",
                                      "rule-engine"]},
            },
            {
                # condition-triggered（等级切换）：入门级不走委派/不引导出图
                "id": "cap-delegate-by-level",
                "when": {"level_gte": 2},
                "then": {"activate": ["agent-delegate"]},
            },
            {
                "id": "cap-diagram-by-level",
                "when": {"level_gte": 2},
                "then": {"activate": ["diagram-render"]},
            },
        ],
        "system_prompt_sections": [
            {
                "name": "rule-engine:routing",
                "order": 85,
                "text": (
                    "【能力激活规约（rule-engine）】\n"
                    "· 本轮可用能力由确定性规则路由决定：只有出现在工具列表与"
                    "对应规约中的能力本轮可调用；未出现的能力本轮不可用。\n"
                    "· 用户明确要求某项能力而它未出现时，直接说明该能力本轮未"
                    "启用（可能因等级/查询意图未命中其激活条件），不要假装调用"
                    "或编造执行结果。"
                ),
            }
        ],
    },
}

# —— 自进化（示范插件：第一个有真封装的插件） —— #
_EVOLUTION: dict[str, Any] = {
    "id": "evolution",
    "type": "plugin",
    "name": "自进化",
    "version": "1.0.0",
    "description": (
        "Reflexion 反思 + Voyager 技能沉淀：每次问答后生成改进点并积累，"
        "同一模型越用越强（不微调权重，只在 prompt/记忆层进化）。"
    ),
    "default_enabled": True,
    "switchable": True,
    "env_gate": "EVOLUTION_ENABLE",
    "apply": "immediate",
    "form": "instance",
}

# —— 系统能力 —— #
_AUTH: dict[str, Any] = {
    "id": "auth",
    "type": "plugin",
    "name": "访问鉴权",
    "version": "1.0.0",
    "description": "Bearer Token 鉴权：暴露到局域网时开启，令牌存数据目录（权限 600）。",
    "default_enabled": False,
    "switchable": True,
    "env_gate": "AUTH_ENABLE",
    "apply": "immediate",
    "form": "instance",
}
_BACKUP: dict[str, Any] = {
    "id": "backup",
    "type": "plugin",
    "name": "数据备份/恢复",
    "version": "1.0.0",
    "description": (
        "知识库索引 / 记忆 / 画像 / 自进化 / 插件开关状态打包 zip，"
        "恢复前自动快照可回滚。当前无独立开关（端点随时可用），预留入口。"
    ),
    "default_enabled": True,
    "switchable": False,
    "apply": "immediate",
    "form": "instance",
}

# —— 引擎基础设施（空壳入口：随引擎运行，独立开关开发中） —— #
_EMBED_CACHE: dict[str, Any] = {
    "id": "embed-cache",
    "type": "plugin",
    "name": "嵌入向量缓存（入口）",
    "version": "1.0.0",
    "description": (
        "相同文本（模型+内容哈希）不重复调用嵌入 API，防重复摄入烧额度。"
        "当前随引擎运行，独立开关开发中。"
    ),
    "default_enabled": True,
    "switchable": False,
    "apply": "immediate",
    "form": "instance",
}
_LONG_CONTEXT: dict[str, Any] = {
    "id": "long-context",
    "type": "plugin",
    "name": "长上下文管理（入口）",
    "version": "1.0.0",
    "description": (
        "多轮对话 token 预算：滑窗保留 + 滚动摘要，超预算自动压缩历史。"
        "当前随引擎运行，独立开关开发中。"
    ),
    "default_enabled": True,
    "switchable": False,
    "apply": "immediate",
    "form": "instance",
}
_ASK_QUOTA: dict[str, Any] = {
    "id": "ask-quota",
    "type": "plugin",
    "name": "问答配额（入口）",
    "version": "1.0.0",
    "description": (
        "并发上限 + 每分钟速率 + 排队超时：防费用失控与服务雪堆。"
        "当前随引擎运行，参数在 .env 调整（MAX_CONCURRENT_ASK 等）。"
    ),
    "default_enabled": True,
    "switchable": False,
    "apply": "immediate",
    "form": "instance",
}
_BUILTIN_CORPUS: dict[str, Any] = {
    "id": "builtin-corpus",
    "type": "plugin",
    "name": "内置示例语料（入口）",
    "version": "1.0.0",
    "description": (
        "首次启动导入的示例知识语料，保证空库也有可检索内容。"
        "当前随引擎运行，独立开关开发中。"
    ),
    "default_enabled": True,
    "switchable": False,
    "apply": "immediate",
    "form": "instance",
}

#: 23 项内置 unit 的 manifest 字典（顺序即 agent_tools 装配顺序：
#: agent-memory → agent-skills → agent-delegate，与插件化前恒等；
#: rule-engine 不贡献 agent_tools，位置仅影响清单展示序）。
BUILTIN_UNIT_MANIFESTS: tuple[dict[str, Any], ...] = (
    _AGENT_MEMORY,
    _AGENT_SKILLS,
    _AGENT_CRON,
    _AGENT_DELEGATE,
    _AGENT_REDACT,
    _AGENT_COMPRESS,
    _AGENT_HOOKS,
    _SANDBOX,
    _SANDBOX_PROXY,
    _MCP,
    _REVIEW,
    _WEB_FETCH,
    _PRESET_SOURCES,
    _LOCAL_RERANK,
    _DIAGRAM_RENDER,
    _RULE_ENGINE,
    _EVOLUTION,
    _AUTH,
    _BACKUP,
    _EMBED_CACHE,
    _LONG_CONTEXT,
    _ASK_QUOTA,
    _BUILTIN_CORPUS,
)


def register_builtins(registry: UnitRegistry, *, quiet: bool = True) -> int:
    """把 23 个内置 unit 注册进 registry（幂等：已存在 id 跳过）。

    ``quiet=True``：批量注册走 debug 日志，避免 import 期 23 条 info 刷屏。
    返回新注册数量（重复调用返回 0）。
    """
    registered = 0
    for raw in BUILTIN_UNIT_MANIFESTS:
        if registry.get_unit(raw["id"]) is not None:
            continue
        registry.register(Manifest.from_dict(raw), quiet=quiet)
        registered += 1
    return registered
