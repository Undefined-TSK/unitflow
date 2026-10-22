"""配置：pydantic-settings 类型化配置 + python-dotenv 载入 .env。

约定：所有密钥只来自环境 / .env，绝不硬编码。
load_dotenv 同时把 .env 写入 os.environ——models.registry（模型预留入口开关）、
capabilities（协议层开关）等模块直接读环境变量，依赖这一步。
"""
from pathlib import Path

from dotenv import load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# override=False：已存在的环境变量优先，与 .env 缺省值互不覆盖
load_dotenv(_ENV_FILE, override=False)


class Settings(BaseSettings):
    """集中管理可配置项。pydantic-settings 自动从环境变量读取同名项并做类型校验。"""

    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    # LLM 通道：bailian | mock。默认百炼（用户已配密钥）；缺密钥时自动降级 mock。
    LLM_PROVIDER: str = "bailian"

    # 百炼 / DashScope（兼容两种环境变量名）
    BAILIAN_API_KEY: str = Field(
        default="", validation_alias=AliasChoices("BAILIAN_API_KEY", "DASHSCOPE_API_KEY")
    )
    BAILIAN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    BAILIAN_MODEL: str = "qwen-plus"

    # 百炼 embedding 模型（text-embedding-v3 免费额度已耗尽 → 默认切 v4；dim=1024 与 v3 相同）
    BAILIAN_EMBED_MODEL: str = "text-embedding-v4"      # Mem0 / 非 RAG 路径（registry.embed）
    BAILIAN_EMBED_V4_MODEL: str = "text-embedding-v4"   # RAG 主力向量（registry.embed_v4 → rag.py）

    # 百炼文本生成参数
    BAILIAN_TEMPERATURE: float = 0.3
    BAILIAN_MAX_TOKENS: int = 1500

    # —— LLM 调用重试（网络错误 / 429 / 5xx 指数退避；4xx 不重试） —— #
    LLM_MAX_RETRIES: int = 3        # 最大尝试次数（含首次），即最多重试 2 次
    LLM_RETRY_BACKOFF: float = 1.0  # 首次退避秒数，之后按 2 的幂倍增

    # —— 结构化日志（JSON 行 + 轮转，目录缺省 <数据目录>/logs） —— #
    LOG_LEVEL: str = "INFO"   # DEBUG | INFO | WARNING | ERROR
    LOG_DIR: str = ""         # 自定义日志目录；留空=数据目录下 logs/

    # —— ask 端点配额（桌面单机防费用失控 / 服务雪堆） —— #
    MAX_CONCURRENT_ASK: int = 2      # 同时处理的 ask 请求上限（其余排队）
    ASK_RATE_PER_MIN: int = 10       # 每分钟 ask 请求上限（60 秒滑窗）
    ASK_QUEUE_TIMEOUT: float = 30.0  # 排队等待执行权的最长秒数，超时 429

    # —— 本地 Bearer Token 鉴权（默认关；暴露到局域网时开启） —— #
    AUTH_ENABLE: bool = False   # true=除 /、/static、/api/status 外全部需令牌
    AUTH_TOKEN: str = ""        # 显式令牌；留空则用数据目录 token 文件（首次启用自动生成，权限 600）

    # 本地 Ollama
    OLLAMA_HOST: str = "http://127.0.0.1:11434"
    OLLAMA_MODEL: str = "qwen2.5-coder:7b"

    # 检索
    TOP_K_PER_STAGE: int = 3
    # 网络抓取超时（秒）。不可达时自动降级到本地语料。
    FETCH_TIMEOUT: float = 6.0
    # 知识来源总开关（演示用，真实部署按需开启）
    ENABLE_WEB_FETCH: bool = False
    # 预置权威资料源（Python 官方文档 / CPython / 官方论坛）自动入库开关。
    # 关闭联网抓取时清单仍会被登记为 pending 并附开启指引，不影响离线语料兜底。
    PRESET_SOURCES_ENABLE: bool = True

    # —— 嵌入向量落盘缓存（额度保护核心，D3：模型切换前必落） —— #
    # 相同文本（按 模型+text 哈希）不重复调用百炼，防重复摄入/重建把新额度烧光。
    # 留空=数据目录下 embed_cache/；切 embedding 模型（v3→v4）后必须清空该目录重建。
    EMBED_CACHE_DIR: str = ""

    # —— 沙箱外部资源代理（C1：fetch_url 工具 / pyfetch 的服务端腿） —— #
    # 抓取公网 URL 经同源后端 /api/sandbox/proxy（绕过 CORS），SSRF 防护见
    # pypedia/sandbox_proxy.py（scheme 白名单 + 私网 IP 拦截 + 逐跳重定向校验）。
    SANDBOX_PROXY_ENABLE: bool = True      # 代理总开关
    SANDBOX_PROXY_MAX_MB: float = 8.0      # 单次代理响应体上限（MB）
    SANDBOX_PROXY_MAX_REDIRECTS: int = 5   # 重定向最多跟随跳数（每跳重新校验）
    SANDBOX_PROXY_ALLOW_HOSTS: str = ""    # 域名白名单（逗号分隔，后缀匹配）；空=放行公网

    # —— 服务端 Python 执行沙箱（P2：替代浏览器 Pyodide 17MB 重资产） —— #
    # 用户 / AI 生成的代码直接在本机 Python 解释器跑（项目本体即 Python），
    # 但必须隔离：受控子进程（默认）或 Docker。隔离细节见 pypedia/seams/python_exec.py。
    SANDBOX_BACKEND: str = "local"         # local（默认，零依赖）| docker（更强隔离）| auto（docker 可达则用）
    SANDBOX_EXEC_TIMEOUT: float = 30.0     # 单次执行墙钟上限（秒），超时强杀整个进程组
    SANDBOX_EXEC_MEMORY_MB: float = 512.0  # RLIMIT_AS 地址空间上限（防 OOM）
    SANDBOX_EXEC_CPU_SEC: int = 15         # RLIMIT_CPU CPU 时间上限（秒，防死循环烧 CPU）
    SANDBOX_PKG_DIR: str = ""              # 第三方包装载目录；空=数据目录/sandbox_pkgs

    # —— AI 沙箱工具层（function calling：AI 调 run_python/install_package/fetch_url） —— #
    # LLM 在服务端（百炼），工具执行在服务端 Python 沙箱（P2 起不再是浏览器 Pyodide）；
    # 循环轮次 / 代码长度上限防费用失控。执行后端见 pypedia/seams/python_exec.py。
    AGENT_ENABLE: bool = True           # 问答页「沙箱验证」勾选是否可用
    AGENT_MAX_ROUNDS: int = 6           # 单问最大工具调用轮数（前端强制执行）
    AGENT_MAX_CODE_CHARS: int = 20000   # AI 提议的单次 run_python 代码上限

    # —— 极端场景防护（桌面单机，宁严勿崩） —— #
    MAX_UPLOAD_MB: float = 50.0        # 单文件上传上限（MB）
    MAX_QUERY_CHARS: int = 4000        # 单次提问长度上限（字符）
    PARSE_TIMEOUT: float = 120.0       # 离线文档解析超时（秒）
    MAX_PAGES_PER_SITE: int = 6        # 单站抓取页数上限

    # —— 长上下文管理（多轮对话 token 预算） —— #
    CONTEXT_TOKEN_BUDGET: int = 6000   # 会话上下文 token 预算（中英文混合粗估）
    CONTEXT_KEEP_TURNS: int = 4        # 超预算时始终完整保留的最近轮数
    CONTEXT_SUMMARY_TRIGGER: int = 8   # 超过 N 轮触发滚动摘要

    # —— 本地重排模型（bge-reranker，首次使用自动下载） —— #
    RERANK_LOCAL_MODEL: str = "BAAI/bge-reranker-base"  # 1.1GB；要更高质量可换 v2-m3(2.2GB)
    RERANK_LOCAL_ENABLE: bool = True   # 关闭后只用向量分数排序
    HF_ENDPOINT: str = "https://hf-mirror.com"  # HuggingFace 国内镜像（模型下载）

    # —— MCP 协议层（真实接入，stdio） —— #
    MCP_ENABLE: bool = True            # 总开关；Node 不可用时自动降级
    MCP_FS_DIR: str = ""               # MCP filesystem 授权目录（缺省为数据目录）
    MCP_FETCH_ENABLE: bool = True      # MCP fetch server（网页正文）
    MCP_THINKING_ENABLE: bool = True   # MCP sequential-thinking（复杂问题分步推理）

    # —— 答案交叉审阅（A2A 轻量替代：双模型二审） —— #
    REVIEW_ENABLE: bool = True
    REVIEW_MODEL: str = ""             # 缺省用 BAILIAN_MODEL；可设 qwen-max 增强

    # —— 图表渲染（P4 diagram-render 插件：mermaid/echarts 前端资产懒加载） —— #
    # 关闭后前端不下载 mermaid/echarts vendor（省 ~4.7MB 首屏），答案中的
    # mermaid/chart 代码块降级为普通代码高亮；系统提示词不再注入图表规约。
    DIAGRAM_RENDER_ENABLE: bool = True

    # —— 规则引擎（P5 rule-engine 插件：能力激活的确定性路由） —— #
    # 开启后 LLM 调用前按规则求值 active set：未激活的能力不可见（fail-closed），
    # 核心能力 pinned 常驻，等级/查询意图条件触发；关闭后路由层整体旁路，
    # 工具可见性与提示词规约回到「插件启用即可见」（与插件化前恒等）。
    RULE_ENGINE_ENABLE: bool = True

    # —— 自进化（Reflexion 反思 + Voyager 技能沉淀；P6 示范插件） —— #
    # 同一模型越用越强（不微调权重，只在 prompt/记忆层进化）。关闭后问答链路
    # 零反思/零沉淀，/api/evolve 等端点返回 503（设置页也可关，见插件系统）。
    EVOLUTION_ENABLE: bool = True

    # —— Hermes 式 agent 扩展（记忆/技能/cron/hooks/委派，全本地） —— #
    AGENT_MEMORY_ENABLE: bool = True       # 持久记忆库（MEMORY.md/USER.md + FTS5）
    AGENT_SKILLS_ENABLE: bool = True       # 技能库（SKILL.md 三级披露 + Curator）
    AGENT_CRON_ENABLE: bool = True         # 定时任务（P4）
    AGENT_REDACT_SECRETS: bool = True      # 工具出口/记忆写入脱敏（P3，detect-secrets）
    AGENT_MEMORY_MAX_CHARS: int = 20000    # 单个记忆 md 文件字符上限
    AGENT_NUDGE_EVERY: int = 10            # 每 N 步 agent_step 提醒一次记忆整理
    AGENT_SKILL_ARCHIVE_DAYS: int = 30     # 技能 N 天未使用进归档区
    AGENT_DELEGATE_MAX: int = 3            # delegate_task 最大并发子 agent 数
    AGENT_DELEGATE_ENABLE: bool = True     # 是否向模型开放 delegate_task 工具
    AGENT_CRON_MAX_TASKS: int = 20         # 定时任务数上限（防雪堆）
    AGENT_SUB_MAX_REQUESTS: int = 6        # 单个子代理运行的 LLM 请求数上限
    AGENT_HISTORY_CHARS: int = 24000       # 历史压缩字符预算（ProcessHistory）
    AGENT_HISTORY_MAX_MESSAGES: int = 24   # 历史压缩条数预算（< transport.MAX_MESSAGES）

    def describe(self) -> dict:
        masked = (self.BAILIAN_API_KEY[:6] + "…") if self.BAILIAN_API_KEY else "（未配置）"
        return {
            "provider": self.LLM_PROVIDER,
            "bailian_key": masked,
            "bailian_model": self.BAILIAN_MODEL,
            "ollama_host": self.OLLAMA_HOST,
            "ollama_model": self.OLLAMA_MODEL,
            "web_fetch": self.ENABLE_WEB_FETCH,
            "upload_limit_mb": self.MAX_UPLOAD_MB,
            "sandbox_proxy": self.SANDBOX_PROXY_ENABLE,
            "agent_tools": self.AGENT_ENABLE,
            "context_budget": self.CONTEXT_TOKEN_BUDGET,
            "rerank_local": self.RERANK_LOCAL_MODEL if self.RERANK_LOCAL_ENABLE else "关闭",
            "mcp": self.MCP_ENABLE,
            "review": self.REVIEW_ENABLE,
            "diagram_render": self.DIAGRAM_RENDER_ENABLE,
            "rule_engine": self.RULE_ENGINE_ENABLE,
            "evolution": self.EVOLUTION_ENABLE,
            "auth": self.AUTH_ENABLE,
            "agent_memory": self.AGENT_MEMORY_ENABLE,
            "agent_skills": self.AGENT_SKILLS_ENABLE,
            "agent_delegate": self.AGENT_DELEGATE_ENABLE,
            "agent_cron": self.AGENT_CRON_ENABLE,
        }


settings = Settings()
