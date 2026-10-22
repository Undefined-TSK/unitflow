"""C1 沙箱代理测试：SSRF 防护 + 体积/重定向/错误映射 + HTTP 端点。

铁律合规：全部请求经 mock（FakeResponse / getaddrinfo 打桩），
测试套件零真实网络调用、零百炼额度消耗（本模块本身也不碰 LLM/embedding）。
"""
from __future__ import annotations

import ipaddress
import socket

import pytest

from pypedia import sandbox_proxy as sp
from pypedia.config import settings

PUBLIC_IP = "93.184.216.34"   # example.com 的占位公网 IP（仅测试）


class FakeResponse:
    """requests.Response 的最小替身（status/headers/迭代体/关闭）。"""

    def __init__(self, status_code=200, headers=None, body=b"", location=None):
        self.status_code = status_code
        self.headers = dict(headers or {})
        if location is not None:
            self.headers["Location"] = location
        self._body = body
        self.closed = False

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def is_redirect(self) -> bool:
        return self.status_code in (301, 302, 303, 307, 308)

    def iter_content(self, chunk_size: int = 1):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]

    def close(self) -> None:
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


@pytest.fixture()
def net(monkeypatch):
    """打桩网络层：IP 字面量按字面解析，域名解析为可控公网 IP。

    这样「拦截内网」类测试无需依赖真实 DNS，也验证了校验逻辑对
    IP 字面量（十进制/十六进制/IPv6）同样生效。
    """
    state = {"ip": PUBLIC_IP, "responses": [], "calls": []}

    def fake_getaddrinfo(host, port, proto=socket.IPPROTO_TCP):
        h = (host or "").strip("[]")
        if h == "localhost":
            resolved = "127.0.0.1"
        else:
            try:
                ipaddress.ip_address(h)
                resolved = h          # IP 字面量：按字面量返回（含内网地址）
            except ValueError:
                resolved = state["ip"]  # 域名：返回可控公网 IP
        family = socket.AF_INET6 if ":" in resolved else socket.AF_INET
        return [(family, socket.SOCK_STREAM, proto, "", (resolved, port))]

    def fake_get(url, **kwargs):
        state["calls"].append(url)
        r = state["responses"].pop(0) if state["responses"] else FakeResponse(200, body=b"ok")
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(sp.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(sp.requests, "get", fake_get)
    return state


# ---------- 单元：地址判定 ----------
@pytest.mark.parametrize("ip,public", [
    ("8.8.8.8", True), ("93.184.216.34", True), ("1.1.1.1", True),
    ("127.0.0.1", False), ("10.0.0.1", False), ("192.168.1.5", False),
    ("172.16.0.9", False), ("169.254.169.254", False), ("0.0.0.0", False),
    ("100.64.0.1", False), ("198.18.0.1", False), ("224.0.0.1", False),
    ("240.0.0.1", False),
    ("::1", False), ("fd00::1", False), ("fe80::1", False), ("::", False),
    ("2606:2800:220:1:248:1893:25c8:1946", True),
])
def test_is_public_address_ranges(ip, public):
    assert sp._is_public(ipaddress.ip_address(ip)) is public


@pytest.mark.parametrize("ct,probe,text", [
    ("text/plain", b"", True),
    ("application/json", b"", True),
    ("image/svg+xml", b"", True),
    ("application/octet-stream", b"\x89PNG\r\n\x1a\n", False),
    ("", b"hello world", True),
    ("", b"\x00\x01\x02\x03", False),
    ("text/html; charset=utf-8", b"", True),
])
def test_looks_text_heuristic(ct, probe, text):
    assert sp._looks_text(ct, probe) is text


# ---------- 正常抓取 ----------
def test_fetch_text_success(net):
    net["responses"] = [FakeResponse(200, {"Content-Type": "text/plain"}, b"hello py")]
    r = sp.proxy_fetch("https://example.com/readme")
    assert r["ok"] and r["status"] == 200 and r["is_text"]
    assert r["text"] == "hello py" and r["bytes"] == 8 and not r["truncated"]
    assert r["final_url"] == "https://example.com/readme"
    assert net["calls"] == ["https://example.com/readme"]


def test_fetch_binary_returns_base64(net):
    body = b"\x89PNG\r\n\x1a\n\x00\x01"
    net["responses"] = [FakeResponse(200, {"Content-Type": "image/png"}, body)]
    r = sp.proxy_fetch("https://example.com/a.png")
    assert r["is_text"] is False and "b64" in r and "text" not in r
    assert __import__("base64").b64decode(r["b64"]) == body


# ---------- SSRF 拦截（断言根本不会发出请求） ----------
@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://127.0.0.1:8000/api/status",
    "http://169.254.169.254/latest/meta-data/",
    "http://10.0.0.1/", "http://192.168.1.1/", "http://172.16.0.9/",
    "http://[fd00::1]/", "http://[::1]/", "http://0.0.0.0/",
    "http://100.64.0.1/", "http://localhost/",
])
def test_fetch_blocks_internal(url, net):
    with pytest.raises(sp.ProxyError) as ei:
        sp.proxy_fetch(url)
    assert ei.value.code == "blocked_host"
    assert net["calls"] == [], "SSRF 目标不得发出任何请求"


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "gopher://127.0.0.1:11211/_stats",
    "ftp://ftp.example.com/x", "not-a-url", "http:///path-only",
])
def test_fetch_blocks_bad_scheme_or_url(url, net):
    with pytest.raises(sp.ProxyError) as ei:
        sp.proxy_fetch(url)
    assert ei.value.code == "bad_url"
    assert net["calls"] == []


def test_fetch_dns_failure(net, monkeypatch):
    def boom(host, port, proto=socket.IPPROTO_TCP):
        raise socket.gaierror("Name or service not known")

    monkeypatch.setattr(sp.socket, "getaddrinfo", boom)
    with pytest.raises(sp.ProxyError) as ei:
        sp.proxy_fetch("https://no-such-host.invalid/")
    assert ei.value.code == "bad_url"


# ---------- 重定向：逐跳复校验 ----------
def test_fetch_redirect_to_internal_blocked(net):
    net["responses"] = [FakeResponse(302, location="http://127.0.0.1/secret")]
    with pytest.raises(sp.ProxyError) as ei:
        sp.proxy_fetch("https://example.com/redir")
    assert ei.value.code == "blocked_host"
    assert net["calls"] == ["https://example.com/redir"], "第二跳不得发出"


def test_fetch_follows_public_redirect(net):
    net["responses"] = [
        FakeResponse(301, location="https://cdn.example.com/final"),
        FakeResponse(200, {"Content-Type": "text/plain"}, b"final"),
    ]
    r = sp.proxy_fetch("https://example.com/redir")
    assert r["text"] == "final" and r["final_url"] == "https://cdn.example.com/final"
    assert len(net["calls"]) == 2


def test_fetch_redirect_hops_exhausted(net, monkeypatch):
    monkeypatch.setattr(settings, "SANDBOX_PROXY_MAX_REDIRECTS", 3)
    net["responses"] = [FakeResponse(302, location=f"https://example.com/hop{i}")
                        for i in range(10)]
    with pytest.raises(sp.ProxyError) as ei:
        sp.proxy_fetch("https://example.com/loop")
    assert ei.value.code == "upstream_error"
    assert len(net["calls"]) == 4, "3 跳上限 = 首发 + 3 次重定向请求"


# ---------- 体积 / 上游错误 / 超时 ----------
def test_fetch_rejects_by_content_length(net):
    net["responses"] = [FakeResponse(200, {"Content-Length": str(999 * 1024 * 1024)}, b"x")]
    with pytest.raises(sp.ProxyError) as ei:
        sp.proxy_fetch("https://example.com/huge")
    assert ei.value.code == "too_large"


def test_fetch_truncates_oversized_body(net):
    net["responses"] = [FakeResponse(200, {"Content-Type": "text/plain"}, b"A" * 5000)]
    r = sp.proxy_fetch("https://example.com/big", max_bytes=1000)
    assert r["truncated"] and r["bytes"] == 1000 and len(r["text"]) == 1000


def test_fetch_upstream_error(net):
    net["responses"] = [FakeResponse(503, body=b"unavailable")]
    with pytest.raises(sp.ProxyError) as ei:
        sp.proxy_fetch("https://example.com/down")
    assert ei.value.code == "upstream_error"


def test_fetch_timeout(net):
    import requests

    net["responses"] = [requests.Timeout("read timeout")]
    with pytest.raises(sp.ProxyError) as ei:
        sp.proxy_fetch("https://example.com/slow")
    assert ei.value.code == "timeout"


def test_fetch_disabled(monkeypatch):
    monkeypatch.setattr(settings, "SANDBOX_PROXY_ENABLE", False)
    with pytest.raises(sp.ProxyError) as ei:
        sp.proxy_fetch("https://example.com/")
    assert ei.value.code == "disabled"


# ---------- 域名白名单 ----------
def test_fetch_host_allowlist(net, monkeypatch):
    monkeypatch.setattr(settings, "SANDBOX_PROXY_ALLOW_HOSTS", "example.com, docs.python.org")
    net["responses"] = [FakeResponse(200, {"Content-Type": "text/plain"}, b"ok")]
    # 精确命中 + 子域命中
    assert sp.proxy_fetch("https://example.com/a")["text"] == "ok"
    assert sp.proxy_fetch("https://api.example.com/b")["text"] == "ok"
    # 不在名单
    with pytest.raises(sp.ProxyError) as ei:
        sp.proxy_fetch("https://evil.example.net/")
    assert ei.value.code == "host_not_allowed"


# ---------- 状态自检（P2：服务端执行后端，替代 Pyodide 资产检查） ----------
def test_sandbox_status_reports_backend():
    from pypedia.seams import get_python_exec

    st = get_python_exec().status()
    assert st["backend"] in ("local", "docker")
    assert isinstance(st["python_version"], str) and st["python_version"]
    assert isinstance(st["installed_packages"], list)
    assert st["proxy_enabled"] in (True, False)


# ---------- HTTP 端点 ----------
def test_api_status(client):
    r = client.get("/api/sandbox/status")
    assert r.status_code == 200
    body = r.json()
    assert body["backend"] in ("local", "docker")
    assert isinstance(body["python_version"], str) and body["python_version"]


def test_api_proxy_blocked_internal(client):
    r = client.get("/api/sandbox/proxy", params={"url": "http://169.254.169.254/latest/"})
    assert r.status_code == 403
    assert "拦截" in r.json()["detail"]


def test_api_proxy_bad_scheme(client):
    r = client.get("/api/sandbox/proxy", params={"url": "file:///etc/passwd"})
    assert r.status_code == 400


def test_api_proxy_success(client, net):
    net["responses"] = [FakeResponse(200, {"Content-Type": "application/json"}, b'{"a":1}')]
    r = client.get("/api/sandbox/proxy", params={"url": "https://example.com/data.json"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["text"] == '{"a":1}'


def test_api_proxy_missing_url(client):
    r = client.get("/api/sandbox/proxy")
    assert r.status_code == 422
