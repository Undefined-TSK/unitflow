"""结构化日志测试：JsonFormatter 字段契约 + 请求中间件（零真实调用）。

conftest 已在 import 前把 PYPEDIA_DATA 指向临时目录，日志文件不会落真实家目录。
"""
import json
import logging

import pytest

from pypedia.logging_setup import JsonFormatter, get_logger, setup_logging


def _record(msg="hello", **extra):
    rec = logging.LogRecord("pypedia.test", logging.INFO, __file__, 1, msg, (), None)
    for k, v in extra.items():
        setattr(rec, k, v)
    return rec


class TestJsonFormatter:
    def test_basic_fields(self):
        line = JsonFormatter().format(_record("hello"))
        obj = json.loads(line)  # 必须是合法单行 JSON
        assert obj["msg"] == "hello"
        assert obj["level"] == "INFO"
        assert obj["logger"] == "pypedia.test"
        assert "ts" in obj

    def test_extra_fields_merged(self):
        rec = _record("http_request", request_id="abc123", method="GET",
                      path="/api/status", status=200, duration_ms=12.3)
        obj = json.loads(JsonFormatter().format(rec))
        assert obj["request_id"] == "abc123"
        assert obj["status"] == 200
        assert obj["duration_ms"] == 12.3

    def test_reserved_fields_not_merged_as_extra(self):
        """标准 LogRecord 属性（lineno 等）不得再作为 extra 键重复出现在 JSON 里。"""
        rec = _record("x")
        rec.lineno = 999  # 保留字段被污染时应被跳过
        obj = json.loads(JsonFormatter().format(rec))
        assert "lineno" not in obj

    def test_non_serializable_extra_stringified(self):
        obj = json.loads(JsonFormatter().format(_record("x", obj=object())))
        assert isinstance(obj["obj"], str)

    def test_exc_info_included(self):
        import sys
        try:
            raise ValueError("boom")
        except ValueError:
            rec = logging.LogRecord("pypedia.test", logging.ERROR, __file__, 1,
                                    "failed", (), sys.exc_info())
        obj = json.loads(JsonFormatter().format(rec))
        assert "ValueError: boom" in obj["exc"]

    def test_unicode_not_escaped(self):
        line = JsonFormatter().format(_record("中文消息"))
        assert "中文消息" in line  # ensure_ascii=False


class TestSetupLogging:
    def test_idempotent(self):
        a = setup_logging()
        b = setup_logging()
        assert a is b
        # 重复初始化不叠加句柄（否则日志翻倍）
        assert len(a.handlers) == len(b.handlers)

    def test_log_dir_created(self, tmp_path, monkeypatch):
        """日志目录不存在时自动创建（PYPEDIA_DATA 已被 conftest 隔离到 tmp）。"""
        from pypedia import logging_setup
        target = tmp_path / "custom_logs"
        monkeypatch.setattr(logging_setup, "LOG_DIR", target)
        # 重置初始化状态并清空既有句柄，触发新一轮 mkdir + 句柄创建
        root = logging.getLogger("pypedia")
        root.handlers.clear()
        monkeypatch.setattr(logging_setup, "_initialized", False)
        root = logging_setup.setup_logging()
        assert target.is_dir()
        # 落盘一条，验证文件句柄真的写进了这个目录
        get_logger("setup_test").info("probe")
        for h in root.handlers:
            h.flush()
        assert (target / "pypedia.log").exists()

    def test_get_logger_namespaced(self):
        assert get_logger("engine").name == "pypedia.engine"
        assert get_logger("pypedia.http").name == "pypedia.http"


class TestRequestMiddleware:
    def test_request_logged_with_fields(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="pypedia"):
            r = client.get("/api/status")
        assert r.status_code == 200
        recs = [x for x in caplog.records
                if x.name == "pypedia.http" and getattr(x, "path", None) == "/api/status"]
        assert recs, "中间件未记录 http_request"
        rec = recs[-1]
        assert rec.request_id
        assert rec.method == "GET"
        assert rec.status == 200
        assert rec.duration_ms >= 0

    def test_request_id_header_echoed(self, client):
        r = client.get("/api/status", headers={"X-Request-ID": "client-trace-1"})
        assert r.headers["X-Request-ID"] == "client-trace-1"

    def test_request_id_generated_when_absent(self, client):
        r = client.get("/api/status")
        assert r.headers["X-Request-ID"]  # 12 位 hex

    def test_404_also_logged(self, client, caplog):
        with caplog.at_level(logging.INFO, logger="pypedia"):
            r = client.get("/api/nonexistent")
        assert r.status_code == 404
        recs = [x for x in caplog.records
                if x.name == "pypedia.http" and getattr(x, "status", None) == 404]
        assert recs
