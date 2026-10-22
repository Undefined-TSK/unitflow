"""C1 浏览器沙箱的外部资源代理：Pyodide 内 `pyfetch(url)` 的服务端腿。

背景：Pyodide 把 `urllib.request` 桥到浏览器 JS fetch，受同源/CORS 限制，
且 jsdelivr/unpkg 等 CDN 在国内不可达。本模块让浏览器里的 Python 代码
经同源后端 `/api/sandbox/proxy` 抓取外部资源，绕过 CORS 并统一管控。

安全模型（SSRF 防护，桌面单机工具的务实口径）：
- scheme 白名单：仅 http/https（挡 file://、gopher://、ftp:// 等）；
- 主机解析：`getaddrinfo` 后**逐 IP** 校验，私网/回环/链路本地/保留/组播/
  未指定地址一律拒绝（挡 127.0.0.1、10.x、192.168.x、169.254.169.254 元数据等）；
- 重定向：关闭 requests 自动跟随，手动逐跳，每跳重新做 scheme + IP 校验；
- 体积：先看 Content-Length 预拒，再流式读取硬截断（默认 8MB）；
- 超时：复用 settings.FETCH_TIMEOUT（连接/读取同值）；
- 域名白名单：SANDBOX_PROXY_ALLOW_HOSTS（逗号分隔，后缀匹配），留空=放行公网。

已知限制（如实声明，不假装完美）：DNS 重绑定（TOCTOU）——校验与连接分两次
解析，理论上存在窗口；桌面单机工具不做连接级 IP 固定。需要更强保证的场景应
在前置网关做 egress 过滤。

铁律合规：
- 零真实调用可验证：模块本身不发起任何非用户显式指定的请求；测试全 mock；
- 复用不重造：requests（既有依赖）、settings.FETCH_TIMEOUT、UA 约定与
  ingest.crawl 一致；
- 额度纪律：本模块不触碰 LLM / embedding，零百炼额度消耗。
"""
from __future__ import annotations

import base64
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import requests

from .config import settings
from .plugins import plugin_registry

_UA = {"User-Agent": "PyPedia/1.0 (+sandbox-proxy)"}

# 显式特殊用途段（Python 3.11 的 is_global 不覆盖 CGNAT/基准测试段，宁严勿宽）
_EXTRA_BLOCKED_V4 = [
    ipaddress.ip_network("100.64.0.0/10"),    # CGNAT 共享地址空间
    ipaddress.ip_network("198.18.0.0/15"),    # 网络设备基准测试
    ipaddress.ip_network("192.0.0.0/24"),     # IETF 协议分配
    ipaddress.ip_network("192.0.2.0/24"),     # TEST-NET-1（文档示例）
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),   # TEST-NET-3
]

# 视为「文本」的 content-type 主类型/子类型（其余按二进制 base64 回传）
_TEXT_TYPES = {
    "text/plain", "text/html", "text/css", "text/csv", "text/markdown",
    "text/xml", "text/javascript",
    "application/json", "application/xml", "application/javascript",
    "application/x-javascript", "application/xhtml+xml",
    "image/svg+xml",
}


class ProxyError(Exception):
    """代理抓取失败。code 供上层映射 HTTP 状态码，message 面向用户。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _check_scheme(url: str) -> tuple[str, str]:
    """校验 scheme 并拆出 (scheme, host)。拒绝非 http(s)。"""
    try:
        parts = urlsplit(url)
    except ValueError as e:
        raise ProxyError("bad_url", f"URL 无法解析：{e}") from e
    scheme = (parts.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise ProxyError("bad_url", f"仅支持 http/https，收到：{scheme or '（空）'}")
    host = parts.hostname
    if not host:
        raise ProxyError("bad_url", "URL 缺少主机名")
    return scheme, host


def _assert_public_host(host: str, port: int) -> None:
    """DNS 解析后逐 IP 校验：任何非公网地址即拒（SSRF 核心防线）。"""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise ProxyError("bad_url", f"域名解析失败：{host}（{e}）") from e
    if not infos:
        raise ProxyError("bad_url", f"域名解析无结果：{host}")
    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str.split("%", 1)[0])  # 去 IPv6 zone
        except ValueError as e:
            raise ProxyError("blocked_host", f"无法识别的地址：{ip_str}") from e
        if not _is_public(ip):
            raise ProxyError(
                "blocked_host",
                f"已拦截对内网/保留地址的访问（{host} → {ip_str}）：沙箱只访问公网资源",
            )


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """公网判定：白名单口径（显式拒绝各类特殊用途段），宁严勿宽。"""
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        return False
    if ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        return False
    if ip.version == 4 and any(ip in net for net in _EXTRA_BLOCKED_V4):
        return False
    # IPv4-mapped / 6to4 / Teredo 等内嵌 v4 的地址，解出来再查一次
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None and not _is_public(mapped):
        return False
    sixtofour = getattr(ip, "sixtofour", None)
    if sixtofour is not None and not _is_public(sixtofour):
        return False
    teredo = getattr(ip, "teredo", None)
    if teredo is not None:
        server, client = teredo
        if not _is_public(server) or not _is_public(client):
            return False
    return bool(ip.is_global)


def _assert_host_allowed(host: str) -> None:
    """可选域名白名单（后缀匹配：example.com 覆盖 a.example.com）。"""
    raw = (settings.SANDBOX_PROXY_ALLOW_HOSTS or "").strip()
    if not raw:
        return
    host_l = host.lower().rstrip(".")
    for entry in raw.split(","):
        e = entry.strip().lower().rstrip(".")
        if not e:
            continue
        if host_l == e or host_l.endswith("." + e):
            return
    raise ProxyError("host_not_allowed", f"主机不在沙箱白名单内：{host}")


def _looks_text(content_type: str, probe: bytes) -> bool:
    """content-type 判定 + 对无类型/类型模糊的响应做字节嗅探。"""
    ct = (content_type or "").split(";", 1)[0].strip().lower()
    if ct in _TEXT_TYPES:
        return True
    if ct:
        return ct.startswith("text/") or ct.endswith("+json") or ct.endswith("+xml")
    if not probe:
        return True
    if b"\x00" in probe:
        return False
    sample = probe[:1024]
    nontext = sum(1 for b in sample if b < 9 or (13 < b < 32))
    return nontext / max(1, len(sample)) < 0.10


def proxy_fetch(url: str, *, max_bytes: int | None = None,
                timeout: float | None = None) -> dict:
    """抓取单个 URL（SSRF 防护 + 体积/超时上限），返回前端可直接用的 dict。

    返回结构：{ok, status, final_url, content_type, headers, is_text,
               text|b64, bytes, truncated}
    失败抛 ProxyError（code ∈ bad_url/blocked_host/host_not_allowed/
    too_large/timeout/upstream_error）。
    """
    if not plugin_registry.is_enabled("sandbox-proxy"):
        raise ProxyError("disabled", "沙箱代理未启用（SANDBOX_PROXY_ENABLE=false 或插件面板关闭）")
    if max_bytes is None:
        max_bytes = int(settings.SANDBOX_PROXY_MAX_MB * 1024 * 1024)
    if timeout is None:
        timeout = settings.FETCH_TIMEOUT
    if max_bytes <= 0:
        raise ProxyError("too_large", "体积上限配置非法")

    scheme, host = _check_scheme(url)
    port = urlsplit(url).port or (443 if scheme == "https" else 80)
    _assert_host_allowed(host)
    _assert_public_host(host, port)

    hops = 0
    current = url
    try:
        while True:
            # 关键：不自动跟随重定向——每跳都要重新校验，否则 302 到内网即失守
            r = requests.get(current, timeout=timeout, headers=_UA,
                             stream=True, allow_redirects=False)
            if r.is_redirect or r.status_code in (301, 302, 303, 307, 308):
                loc = r.headers.get("Location", "")
                r.close()
                if not loc:
                    raise ProxyError("upstream_error", "重定向缺少 Location 头")
                hops += 1
                if hops > settings.SANDBOX_PROXY_MAX_REDIRECTS:
                    raise ProxyError("upstream_error",
                                     f"重定向超过 {settings.SANDBOX_PROXY_MAX_REDIRECTS} 跳，已放弃")
                current = urljoin(current, loc)
                scheme, host = _check_scheme(current)
                port = urlsplit(current).port or (443 if scheme == "https" else 80)
                _assert_host_allowed(host)
                _assert_public_host(host, port)
                continue
            if not r.ok:
                r.close()
                raise ProxyError("upstream_error",
                                 f"上游返回 {r.status_code}（{current}）")
            break
    except ProxyError:
        raise
    except requests.Timeout as e:
        raise ProxyError("timeout", f"抓取超时（{timeout:.0f}s）：{current}") from e
    except requests.RequestException as e:
        raise ProxyError("upstream_error", f"抓取失败：{e}") from e

    with r:
        content_type = r.headers.get("Content-Type", "")
        declared = r.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise ProxyError("too_large",
                             f"响应体 {int(declared) / 1e6:.1f}MB 超过上限 "
                             f"{settings.SANDBOX_PROXY_MAX_MB:.0f}MB")
        chunks: list[bytes] = []
        total = 0
        truncated = False
        for chunk in r.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            chunks.append(chunk)
            total += len(chunk)
            if total >= max_bytes:
                truncated = True
                break
        body = b"".join(chunks)
        if truncated:
            body = body[:max_bytes]

    is_text = _looks_text(content_type, body[:2048])
    out: dict = {
        "ok": True,
        "status": r.status_code,
        "final_url": current,
        "content_type": content_type or "application/octet-stream",
        "is_text": is_text,
        "bytes": len(body),
        "truncated": truncated,
        "headers": {
            "content-type": content_type,
            "last-modified": r.headers.get("Last-Modified", ""),
            "etag": r.headers.get("ETag", ""),
        },
    }
    if is_text:
        out["text"] = body.decode("utf-8", errors="replace")
    else:
        out["b64"] = base64.b64encode(body).decode("ascii")
    return out

