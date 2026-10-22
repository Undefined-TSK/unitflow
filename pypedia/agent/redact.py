"""敏感信息脱敏：工具出口 / 记忆写入 / 用户输入进 LLM 前的统一闸门。

铁律：检测用 detect-secrets（Yelp，MIT，1.5.0）官方插件集，不手写检测规则；
本模块只做「编排 + 替换」，即把各插件 yield 的密文值替换为掩码。

覆盖的探测器（detect_secrets.plugins 全量实例化，均无参构造）：
- KeywordDetector      带引号的 key=value 赋值（.env / JSON 配置片段）
- BasicAuthDetector    URL userinfo（https://user:pass@host）
- PrivateKeyDetector   PEM 私钥块（yield 的是标记串，另行按块整体掩码）
- 其余厂商令牌探测器   OpenAI/GitHub/GitLab/Slack/Stripe/AWS/JWT/SendGrid/
                       Twilio/Telegram/Discord/npm/PyPI/Mailchimp/Artifactory/
                       Azure/Cloudant/IBM/SoftLayer/Square 等专用格式

脱敏策略：
- 密文值（长度 ≥4）按「长者优先」在原文中做精确子串替换，避免短值误伤；
- PEM 块整体替换（标记串本身不含密钥体，只替换标记会漏）；
- 任意插件异常不影响主流程（跳过该插件，记日志）——脱敏是尽力而为的
  保险丝，不是正确性依赖。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from detect_secrets.plugins.base import RegexBasedDetector

from ..config import settings
from ..logging_setup import get_logger
from ..plugins import plugin_registry
from .hooks import secret_redacted

log = get_logger("agent.redact")

REDACTED = "«已脱敏»"
_MIN_VALUE_LEN = 4          # 短于该长度的命中不替换（防误伤）
_PEM_BLOCK_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)

# —— detect-secrets 官方插件全量实例化（探测引擎是现成轮子） —— #
class _BareTokenDetector(RegexBasedDetector):
    """项目自定义 denylist（detect-secrets 官方插件扩展点，非自建检测引擎）。

    动机：官方 OpenAIDetector 只认含 ``T3BlbkFJ`` 字面的真 OpenAI 密钥，
    百炼/DashScope 的 ``sk-`` 裸密钥与 ``Authorization: Bearer`` 头会漏检
    ——这两者正是本项目最可能出现在工具结果/记忆写入里的形态。
    模式无捕获组：analyze_string yield 完整匹配，供整串替换。
    """

    secret_type = "Bare API Token"

    denylist = (
        re.compile(r"sk-[A-Za-z0-9]{20,}"),            # 百炼/DashScope/OpenAI 兼容裸密钥
        re.compile(r"Bearer [A-Za-z0-9._\-]{20,}"),    # Authorization 头
    )


def _load_plugins() -> list:
    from detect_secrets.plugins.base import BasePlugin

    modules = (
        "keyword", "basic_auth", "private_key", "openai", "github_token",
        "gitlab_token", "slack", "stripe", "aws", "azure_storage_key",
        "artifactory", "cloudant", "discord", "ibm_cloud_iam", "ibm_cos_hmac",
        "jwt", "mailchimp", "npm", "pypi_token", "sendgrid", "softlayer",
        "square_oauth", "telegram_token", "twilio",
    )
    plugins: list[BasePlugin] = [_BareTokenDetector()]
    for name in modules:
        try:
            mod = __import__(f"detect_secrets.plugins.{name}", fromlist=["*"])
            for attr in vars(mod).values():
                if (isinstance(attr, type) and issubclass(attr, BasePlugin)
                        and attr is not BasePlugin
                        and attr.__module__ == mod.__name__):
                    plugins.append(attr())
                    break
        except Exception as e:  # noqa: BLE001 —— 单插件加载失败不阻塞其余
            log.warning("redact_plugin_load_failed",
                        extra={"plugin": name, "error": repr(e)[:120]})
    return plugins


_PLUGINS = _load_plugins()
_PEM_PLUGIN = next((p for p in _PLUGINS
                    if type(p).__name__ == "PrivateKeyDetector"), None)


@dataclass
class RedactResult:
    text: str
    redacted: bool = False
    kinds: list[str] = field(default_factory=list)   # 命中的插件类型名（去重）


def _collect_values(text: str) -> list[tuple[str, str]]:
    """各插件扫描 → [(插件类型名, 密文值)]；单插件异常跳过。"""
    hits: list[tuple[str, str]] = []
    for plugin in _PLUGINS:
        try:
            for value in plugin.analyze_string(text):
                if isinstance(value, str) and len(value) >= _MIN_VALUE_LEN:
                    hits.append((type(plugin).__name__, value))
        except Exception as e:  # noqa: BLE001 —— 探测失败不阻塞主流程
            log.warning("redact_plugin_failed",
                        extra={"plugin": type(plugin).__name__,
                               "error": repr(e)[:120]})
    return hits


def redact_text(text: str, *, source: str = "") -> RedactResult:
    """脱敏入口。source 仅用于日志/钩子标注（如 tool_result / memory / query）。"""
    if not text or not plugin_registry.is_enabled("agent-redact"):
        return RedactResult(text=text)
    result = RedactResult(text=text)

    # 1) PEM 私钥块整体掩码（PrivateKeyDetector 只 yield 标记串）
    if _PEM_PLUGIN is not None:
        try:
            if next(iter(_PEM_PLUGIN.analyze_string(text)), None) is not None:
                new_text, n = _PEM_BLOCK_RE.subn(REDACTED, text)
                if n:
                    result.text = new_text
                    result.redacted = True
                    result.kinds.append("PrivateKeyDetector")
        except Exception as e:  # noqa: BLE001
            log.warning("redact_pem_failed", extra={"error": repr(e)[:120]})

    # 2) 密文值精确替换（长者在先，防短值是长值子串时漏替换）
    hits = _collect_values(result.text)
    seen: set[str] = set()
    for kind, value in sorted(hits, key=lambda kv: -len(kv[1])):
        if value in seen:
            continue
        seen.add(value)
        if value in result.text:
            result.text = result.text.replace(value, REDACTED)
            result.redacted = True
            if kind not in result.kinds:
                result.kinds.append(kind)

    if result.redacted:
        log.info("secret_redacted",
                 extra={"source": source, "kinds": ",".join(result.kinds)})
        secret_redacted.send(None, source=source, kinds=result.kinds)
    return result


def redact_or_none(text: str, *, source: str = "") -> str:
    """只要文本的便捷形式（hooks 由 redact_text 内部发）。"""
    return redact_text(text, source=source).text
