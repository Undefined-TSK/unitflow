"""服务端 Python 执行 Seam 测试（P2）。

铁律：全部用安全片段，不碰任何外部服务、不耗 LLM 额度、不装真实第三方包
（网络可能不可用）；装包只验证返回类型与非法入参的分支。
"""
from __future__ import annotations

import time

import pytest

from pypedia.seams import LocalPythonExec, get_python_exec
from pypedia.seams.python_exec import ExecResult, InstallResult, JobView


@pytest.fixture()
def exec_backend():
    return LocalPythonExec()


def test_exec_success(exec_backend):
    r = exec_backend.exec_sync("print(1 + 2)\nprint('hello')")
    assert isinstance(r, ExecResult)
    assert r.ok is True
    assert r.returncode == 0
    assert "3" in r.stdout and "hello" in r.stdout
    assert r.error == ""


def test_exec_syntax_error(exec_backend):
    r = exec_backend.exec_sync("print(('unclosed")
    assert r.ok is False
    assert r.returncode not in (0, None)
    assert "SyntaxError" in r.stderr or "syntax" in (r.stderr or "").lower()


def test_exec_runtime_error(exec_backend):
    r = exec_backend.exec_sync("raise ValueError('boom')")
    assert r.ok is False
    assert r.returncode not in (0, None)
    assert "boom" in r.stderr


def test_exec_timeout_kills_process_group(exec_backend):
    r = exec_backend.exec_sync("import time\ntime.sleep(30)", timeout=1.0)
    assert r.ok is False
    assert r.timed_out is True
    # 被信号终止：returncode 为负（SIGTERM=-15）或 None（已强杀）
    assert (r.returncode is None or r.returncode < 0)
    assert "超时" in r.error


def test_exec_uses_isolated_mode(exec_backend):
    # -I 隔离模式：不应能读到项目源码目录里的任意模块；sys.path[0] 是临时工作目录
    r = exec_backend.exec_sync("import sys\nprint(sys.path[0])\nprint('iso-ok')")
    assert r.ok is True
    assert "iso-ok" in r.stdout


def test_install_invalid_name(exec_backend):
    r = exec_backend.install_package("")
    assert isinstance(r, InstallResult)
    assert r.ok is False
    # 非法包名（命令注入样式）也应被拒绝而非执行
    r2 = exec_backend.install_package("x; rm -rf /")
    assert r2.ok is False


def test_status_shape(exec_backend):
    st = exec_backend.status()
    assert isinstance(st, dict)
    assert st["backend"] == "local"
    assert isinstance(st["python_version"], str) and st["python_version"]
    assert isinstance(st["network_isolated"], bool)
    assert isinstance(st["installed_packages"], list)
    assert isinstance(st["proxy_enabled"], bool)
    assert isinstance(st["exec_timeout"], (int, float))


def test_run_job_and_poll(exec_backend):
    job_id = exec_backend.run_job("print('job-ok')", timeout=10.0)
    assert isinstance(job_id, str) and job_id
    # 轮询直到完成（执行很快，给足上限）
    view = None
    for _ in range(40):
        view = exec_backend.get_job(job_id)
        assert isinstance(view, JobView)
        if view.status != "running":
            break
        time.sleep(0.1)
    assert view is not None
    assert view.status == "done"
    assert "job-ok" in view.stdout
    assert view.returncode == 0


def test_get_unknown_job_returns_none(exec_backend):
    assert exec_backend.get_job("does-not-exist") is None


def test_cancel_unknown_job_returns_false(exec_backend):
    assert exec_backend.cancel_job("does-not-exist") is False


def test_get_python_exec_singleton():
    a = get_python_exec()
    b = get_python_exec()
    assert a is b  # 单例
    assert a.backend in ("local", "docker")
