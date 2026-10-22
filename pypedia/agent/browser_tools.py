"""沙箱工具（deferred）：函数体只做参数校验 + 外派，执行在服务端沙箱。

架构前提（执行引擎已迁移到服务端 Python Seam，见 pypedia/seams/python_exec.py）：
- 工具函数被模型调用时抛 CallDeferred——pydantic-ai 随即将运行挂起，
  输出 DeferredToolRequests 交给 transport 返回前端；
- 前端把执行请求转发到服务端 /api/sandbox/exec（run/install），fetch/status
  走 /api/sandbox/proxy、/api/sandbox/status，结果经 {state, tool_results}
  回传，transport 用 DeferredToolResults 续跑；
- 参数非法时不外派：直接返回错误文本作为工具结果（内联入历史），
  模型可自行修正重试——与旧协议「invalid 喂回」语义等价且更顺滑。

安全边界（沿用旧 agent.py 白名单思路，LLM 提出的参数同样不可信）：
- 包名仅放行字母数字 . _ -（拒绝版本声明/URL/注入样式）；
- fetch_url 仅 http/https 且限长；
- run_python 代码限长（settings.AGENT_MAX_CODE_CHARS）。
"""
from __future__ import annotations

import re

from pydantic_ai.exceptions import CallDeferred

from ..config import settings

# 安装包名白名单：字母数字 . _ -（连字符/下划线归一化后校验）
_PKG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)
MAX_URL_CHARS = 2048


def _check_code(code: str) -> str | None:
    if not isinstance(code, str) or not code.strip():
        return "参数错误：run_python 需要非空 code 字符串"
    if len(code) > settings.AGENT_MAX_CODE_CHARS:
        return f"参数错误：代码超过上限 {settings.AGENT_MAX_CODE_CHARS} 字符，请精简"
    return None


async def run_python(code: str) -> str:
    """在用户浏览器的 Python 3.13 沙箱中执行代码并返回 stdout/stderr。

    用于验证将要讲给用户的代码确实能跑、实测 API 行为、做计算。
    标准库开箱即用；numpy 等二进制包需先用 install_package 安装。
    代码应是完整可运行的片段（print 输出关键结果）。
    """
    err = _check_code(code)
    if err:
        return err
    raise CallDeferred()


async def install_package(name: str) -> str:
    """在沙箱中安装 Python 包（Pyodide 原生 loadPackage 优先，本地 wheels/PyPI 兜底）。

    仓库已本地分发的 wheel（如 numpy）秒装且离线可用；纯 Python 包从 PyPI
    或镜像安装。安装后的包即可被 run_python import。
    """
    pkg = str(name or "").strip()
    if not _PKG_RE.match(pkg):
        return f"参数错误：包名非法：{pkg!r}（仅允许字母数字 . _ -）"
    raise CallDeferred()


async def fetch_url(url: str) -> str:
    """抓取公网 URL 的文本内容（经服务端代理，仅 http/https，单次上限 8MB）。

    用于查证官方文档页面、API 响应等公开资源。内网/回环/元数据地址会被
    服务端拦截。
    """
    u = str(url or "").strip()
    if not _URL_RE.match(u):
        return "参数错误：fetch_url 仅支持 http/https 网址"
    if len(u) > MAX_URL_CHARS:
        return "参数错误：网址过长"
    raise CallDeferred()


async def sandbox_status() -> str:
    """查询沙箱运行时状态：Python 版本、仓库已本地分发的 wheel 清单、外部资源代理开关。

    无参数。不确定某个包是否已可用时调用。
    """
    raise CallDeferred()


BROWSER_TOOLS = [run_python, install_package, fetch_url, sandbox_status]
