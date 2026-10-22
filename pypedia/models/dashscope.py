"""百炼（DashScope）现成模型能力封装：embedding / rerank / chat / 置信度评估。

全部走官方 API，密钥只来自环境变量（settings），不硬编码。
对应架构拼图：向量模型、重排模型、通义千问大模型——均为百炼平台成熟服务，直接复用，不自造。
"""
from __future__ import annotations

import json
import re
import time

import requests
from tenacity import (RetryError, Retrying, retry_if_exception, retry_if_result,
                      stop_after_attempt, wait_exponential)

from ..config import settings
from .registry import registry

API_KEY = settings.BAILIAN_API_KEY
# 模型名统一走注册表：.env 覆盖位 + 未开通占位 + 自动降级链
EMBED_MODEL = registry.name("embed")
CHAT_MODEL = registry.name(registry.resolve("chat"))

COMPAT_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
RERANK_URL = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"

# 值得重试的瞬时状态码：限流 + 网关/服务端错误（4xx 业务错误重试无意义，直接抛）
_RETRY_STATUS = frozenset({429, 500, 502, 503, 504})

# 退避睡眠入口（独立符号便于测试注入 fake，避免测试真睡）
_sleep = time.sleep


def _is_transient(exc: BaseException) -> bool:
    """仅网络层瞬时错误值得重试。HTTPError 由 raise_for_status 抛出，不在重试范围。"""
    return isinstance(exc, (requests.exceptions.ConnectionError,
                            requests.exceptions.Timeout))


def _tenacity_sleep(state) -> None:
    """tenacity 回调给的是 DoSleep（含 .seconds），转成秒数交给可注入的 _sleep。"""
    _sleep(getattr(state, "seconds", state))


def _request_with_retry(url: str, *, headers: dict, json: dict, timeout: float = 30,
                        max_retries: int | None = None,
                        backoff: float | None = None) -> requests.Response:
    """统一 HTTP POST：网络错误 / 429 / 5xx 指数退避重试，其余立即抛错。

    重试策略交给 tenacity（llama-index-core 的传递依赖 → 零新增依赖），语义与自写版一致：
    - max_retries：总尝试次数（含首次），默认取 settings.LLM_MAX_RETRIES；
    - backoff：首次退避秒数，之后 ×2 递增，默认取 settings.LLM_RETRY_BACKOFF；
    - 只重试 ConnectionError / Timeout 与 429 / 5xx——4xx 业务错误（参数非法等）
      立即抛，反复重试只会浪费配额；
    - sleep 走 _sleep 包装，保留测试注入假时钟的能力（测试不真睡）。
    """
    if max_retries is None:
        max_retries = settings.LLM_MAX_RETRIES
    if backoff is None:
        backoff = settings.LLM_RETRY_BACKOFF
    attempts = max(1, max_retries)

    def _post() -> requests.Response:
        r = requests.post(url, headers=headers, json=json, timeout=timeout)
        if r.status_code in _RETRY_STATUS:
            return r  # 交给 retry_if_result 决定是否重试
        r.raise_for_status()  # 4xx 等立即抛，不进重试
        return r

    retryer = Retrying(
        stop=stop_after_attempt(attempts),
        wait=wait_exponential(multiplier=backoff, exp_base=2),
        retry=(retry_if_exception(_is_transient)
               | retry_if_result(lambda r: getattr(r, "status_code", 0) in _RETRY_STATUS)),
        sleep=_tenacity_sleep,
        reraise=True,
    )
    try:
        r = retryer(_post)
    except RetryError as e:
        # 按返回值重试（429/5xx）耗尽时 tenacity 抛 RetryError 而非返回最后结果，
        # 这里取出最后一次响应，统一交给 raise_for_status → 抛 HTTPError
        r = e.last_attempt.result()
    r.raise_for_status()
    return r


def _headers() -> dict:
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}


def _has_key() -> bool:
    return bool(API_KEY)


# —————————————————————————————————————————————— #
# Embedding（OpenAI 兼容模式；百炼要求分批 ≤ 10）
# —————————————————————————————————————————————— #
def embed_texts(texts: list[str], model: str = EMBED_MODEL, batch: int = 10) -> list[list[float]]:
    """批量生成向量。无密钥时抛错（由上层降级到 Mock）。"""
    if not _has_key():
        raise RuntimeError("未配置百炼 API Key，无法生成 embedding")
    if not texts:
        return []
    out: list[list[float]] = []
    for i in range(0, len(texts), batch):
        chunk = texts[i : i + batch]
        r = _request_with_retry(
            f"{COMPAT_BASE}/embeddings",
            headers=_headers(),
            json={"model": model, "input": chunk},
            timeout=30,
        )
        data = r.json().get("data", [])
        data.sort(key=lambda x: x.get("index", 0))
        out.extend(d["embedding"] for d in data)
    return out


def embed_one(text: str) -> list[float]:
    return embed_texts([text])[0]


# —————————————————————————————————————————————— #
# Rerank（百炼 gte-rerank 专用端点）
# —————————————————————————————————————————————— #
def _rerank_raw(query: str, documents: list[str], top_n: int,
                model: str) -> list[dict]:
    """调用百炼 rerank 专用端点，失败抛异常（由上层决定降级）。"""
    r = _request_with_retry(
        RERANK_URL,
        headers=_headers(),
        json={
            "model": model,
            "input": {"query": query, "documents": documents},
            "parameters": {"return_documents": False, "top_n": top_n},
        },
        timeout=30,
    )
    # 百炼 rerank 实际返回结构：{"output": {"results": [{"index":…, "relevance_score":…}]}}
    # （早期文档曾写作 data.rerank，2026-10 实测以 output.results 为准，双路径兼容）
    payload = r.json()
    results = payload.get("output", {}).get("results")
    if results is None:
        results = payload.get("data", {}).get("rerank")
    if results is None:
        raise RuntimeError(f"rerank 响应结构异常：{r.text[:200]}")
    results.sort(key=lambda x: -x["relevance_score"])
    return results


def rerank(query: str, documents: list[str], top_n: int | None = None,
           return_documents: bool = False) -> list[dict]:
    """返回按相关性降序的列表：[{'index': int, 'relevance_score': float}]。

    三级精排链（2026-10 调研结论）：
    1) 百炼 qwen3-rerank（云端，gte-rerank 已官方下线，qwen3-rerank 为继任者；
       账号未开通时自动跳过）；
    2) 本地 bge-reranker（sentence-transformers CrossEncoder，离线可用，
       首次使用自动下载模型）；
    3) 调用方按向量分数排序兜底（返回空列表由上层处理）。
    """
    if not _has_key():
        raise RuntimeError("未配置百炼 API Key，无法 rerank")
    if not documents:
        return []
    if top_n is None:
        top_n = len(documents)

    # 1) 云端 qwen3-rerank（未开通/失败则静默跳过，进入本地链）
    try:
        if registry.status("rerank") == "active":
            return _rerank_raw(query, documents, top_n, registry.name("rerank"))
    except Exception:
        pass

    # 2) 本地 bge-reranker（模型未就绪返回 None → 上层兜底）
    try:
        from ..rerank_local import reranker

        local = reranker.rank(query, documents)
    except Exception:  # noqa: BLE001 —— 本地链自身故障也绝不被拖垮主流程
        local = None
    if local is not None:
        return local[:top_n]

    # 3) 无可用重排：抛错让上层按向量分数排序
    raise RuntimeError("重排不可用（云端未开通且本地模型未就绪）")


# —————————————————————————————————————————————— #
# Chat（OpenAI 兼容；通义千问 qwen 系列）
# —————————————————————————————————————————————— #
def chat(messages: list[dict], model: str | None = None, temperature: float | None = None,
         max_tokens: int | None = None) -> str:
    """统一的对话补全。失败时由调用方处理降级。"""
    model = model or CHAT_MODEL
    if temperature is None:
        temperature = settings.BAILIAN_TEMPERATURE
    if max_tokens is None:
        max_tokens = settings.BAILIAN_MAX_TOKENS
    r = _request_with_retry(
        f"{COMPAT_BASE}/chat/completions",
        headers=_headers(),
        json={
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
        },
        timeout=120,
    )
    return r.json()["choices"][0]["message"]["content"]


def chat_stream(messages: list[dict], model: str | None = None,
                temperature: float | None = None,
                max_tokens: int | None = None):
    """流式对话补全：生成器逐段产出文本增量（SSE data 帧）。

    DashScope 兼容模式协议：每行 `data: {json}`，`choices[0].delta.content`
    为增量文本，结束帧为 `data: [DONE]`；中间可能夹杂心跳/注释行（非 JSON 直接跳过）。

    流式请求**不做重试**：连接中断即抛错，由上层（engine._complete_stream）
    决定降级——重放会导致重复计费与半截答案拼接，语义不安全。
    """
    model = model or CHAT_MODEL
    if temperature is None:
        temperature = settings.BAILIAN_TEMPERATURE
    if max_tokens is None:
        max_tokens = settings.BAILIAN_MAX_TOKENS
    with requests.post(
        f"{COMPAT_BASE}/chat/completions",
        headers=_headers(),
        json={
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
            "stream": True,
        },
        stream=True,
        timeout=120,
    ) as r:
        r.raise_for_status()
        for line in r.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0].get("delta", {}).get("content")
            except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                continue  # 心跳/注释行等非内容帧
            if delta:
                yield delta


# —————————————————————————————————————————————— #
# Chat with Tools（OpenAI 兼容 function calling；agent 沙箱工具层用）
# —————————————————————————————————————————————— #
def chat_with_tools(messages: list[dict], tools: list[dict], model: str | None = None,
                    temperature: float | None = None, max_tokens: int | None = None,
                    tool_choice: str = "auto") -> dict:
    """带工具列表的对话补全：返回 assistant message dict（content / tool_calls）。

    百炼兼容模式（OpenAI 协议）：`choices[0].message.tool_calls[i].function.arguments`
    为 JSON 字符串，需调用方解析。模型不调工具时 tool_calls 为空、content 为正文。
    网络错误 / 429 / 5xx 走统一退避重试；4xx 立即抛（由上层 agent 降级 Mock）。
    """
    model = model or CHAT_MODEL
    if temperature is None:
        temperature = settings.BAILIAN_TEMPERATURE
    if max_tokens is None:
        max_tokens = settings.BAILIAN_MAX_TOKENS
    r = _request_with_retry(
        f"{COMPAT_BASE}/chat/completions",
        headers=_headers(),
        json={
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
        },
        timeout=120,
    )
    try:
        return r.json()["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"chat_with_tools 响应结构异常：{r.text[:200]}") from e


# —————————————————————————————————————————————— #
# 置信度评估（decision-model 预览版无权限 → 用 qwen-plus 强模型评估替代）
# —————————————————————————————————————————————— #
def evaluate_confidence(question: str, answer: str, evidence_texts: list[str]) -> dict:
    """用大模型评估回答置信度，返回 {score:0-100, level, reason}。"""
    ev = "\n---\n".join(f"[{i + 1}] {t[:380]}" for i, t in enumerate(evidence_texts[:6]))
    prompt = (
        "你是严谨的答案质量评审员，只依据给定证据评估置信度。\n"
        f"用户问题：{question}\n\n参考证据：\n{ev}\n\n模型回答：\n{answer}\n\n"
        "请评估该回答的置信度（证据充分且正确=高，部分充分=中，证据缺失或可能错误=低）。\n"
        '严格只输出一个 JSON：{"score": <0-100整数>, "level": "高/中/低", "reason": "<一句中文理由>"}'
    )
    try:
        txt = chat([{"role": "user", "content": prompt}], temperature=0.0)
        m = re.search(r"\{.*\}", txt, re.S)
        if m:
            obj = json.loads(m.group())
            obj["score"] = int(max(0, min(100, float(obj.get("score", 60)))))
            obj.setdefault("level", "中")
            obj.setdefault("reason", "")
            return obj
    except Exception as e:  # noqa: BLE001
        return {"score": 55, "level": "低", "reason": f"置信度评估失败：{e}"}
    return {"score": 55, "level": "低", "reason": "置信度评估未返回有效结果"}


# —————————————————————————————————————————————— #
# 预留入口：百炼多模态能力（视觉 / 文生图 / 语音合成 / 语音识别 / 代码 / 数学）
# 这些能力已登记进 registry（见 models/registry.py）。当前账号未开通时，
# 调用会抛出带指引的 RuntimeError；在百炼控制台开通对应模型后「零改代码」即生效。
# —————————————————————————————————————————————— #
class ModelNotEnabled(RuntimeError):
    """能力已占位但尚未在百炼开通。"""


def _require(key: str) -> str:
    st = registry.status(key)
    if st != "active":
        s = registry.spec(key)
        raise ModelNotEnabled(
            f"百炼能力「{s.key}」（模型 {s.name}）尚未开通。"
            f"开通方式：百炼控制台启用该模型，或在 .env 设置 {s.env}。"
            f"当前降级到：{registry.resolve(key)}"
        )
    return registry.name(key)


def describe_image(image_url: str, prompt: str = "请描述这张图片的关键信息") -> str:
    """视觉理解（qwen-vl）：读截图/图表 → 支撑可视化讲解。【预留入口】"""
    model = _require("vision")
    r = _request_with_retry(
        f"{COMPAT_BASE}/chat/completions",
        headers=_headers(),
        json={"model": model, "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_url}},
        ]}]},
        timeout=90,
    )
    return r.json()["choices"][0]["message"]["content"]


def generate_image(prompt: str, size: str = "1024*1024") -> str:
    """文生图（wanx）：为知识点生成示意图/插图，返回图片 URL。【预留入口】"""
    model = _require("t2i")
    r = _request_with_retry(
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis",
        headers={**_headers(), "X-DashScope-Async": "enable"},
        json={"model": model, "input": {"prompt": prompt},
              "parameters": {"size": size, "n": 1}},
        timeout=30,
    )
    return r.json()["output"]["task_id"]  # 异步任务，后续轮询取图


def synthesize_speech(text: str, voice: str = "Cherry") -> str:
    """语音合成（qwen-tts）：把答案转为语音播报。【预留入口】"""
    model = _require("tts")
    r = _request_with_retry(
        f"{COMPAT_BASE}/audio/speech",
        headers=_headers(),
        json={"model": model, "input": {"text": text}, "voice": voice},
        timeout=60,
    )
    return r.content  # 音频字节


def code_complete(prompt: str) -> str:
    """代码专用模型（qwen3-coder）：Python 代码生成/解释，比通用模型更强。【预留入口】"""
    model = _require("code")
    r = _request_with_retry(
        f"{COMPAT_BASE}/chat/completions",
        headers=_headers(),
        json={"model": model, "messages": [{"role": "user", "content": prompt}]},
        timeout=120,
    )
    return r.json()["choices"][0]["message"]["content"]


def capability_report() -> list[dict]:
    """供设置页展示「预留入口」面板：每项能力的状态/降级目标/开通方式。"""
    registry.probe_all()
    return registry.describe()
