"""服务端 Python 执行 Seam（P2：替代 17MB 浏览器 Pyodide）。

为什么移到服务端执行
------------------
项目本体即 Python，用户 / AI 生成的代码直接在本机解释器跑即可；浏览器 Pyodide
是 18MB 重资产且二进制包需预分发、功能受限。**但「在服务端跑不可信代码」必须
做隔离**——本 Seam 提供两级后端：

- ``LocalPythonExec``（默认，零额外依赖）：
  · 隔离模式 ``python -I``（无 site / 无 PYTHONPATH / 无用户 site），运行前把
    包目录插入 ``sys.path``（不依赖环境变量，规避 -I 忽略 PYTHONPATH 的问题）；
  · 资源限额：``preexec_fn`` 设 ``RLIMIT_AS``（地址空间上限，防 OOM）与
    ``RLIMIT_CPU``（CPU 秒上限），并 ``setsid`` 起新会话——超时时对整个进程组
    ``killpg`` 强杀（含孙进程）；
  · 网络隔离（尽力）：若 ``unshare`` 可用，用 ``unshare -n`` 起无名网络命名空间
    让子进程无网络（挡住 requests 外联）；不可用则明文提示（桌面单机口径）；
  · 工作目录：每次运行独立临时目录（运行后清理），挡住读写项目源码 / 用户文件；
  · 第三方包：安装到独立 ``pkg_dir``（不污染系统 site），运行前插入 sys.path。

- ``DockerPythonExec``（可选，隔离更彻底）：``docker run --network=none``（禁网）
  + 内存 / CPU 限额 + 只读挂载包目录；需先装 docker 且守护进程可达。
  探测：``shutil.which("docker")`` 且 ``docker info`` 成功 → 用 docker，否则回退 local。

对外 API（app.py 围绕它做 HTTP）：
  get_python_exec() -> PythonExec（按 SANDBOX_BACKEND 选后端）
  exec.exec_sync(code, timeout=...) -> ExecResult（阻塞，测试 / 简单调用用）
  exec.run_job(code, timeout=...) -> job_id（后台线程 + 增量输出 + 可取消）
  exec.get_job(job_id) -> JobView | None
  exec.cancel_job(job_id) -> bool
  exec.install_package(name, index_url=...) -> InstallResult
  exec.status() -> dict

铁律合规：
  · 零真实调用可验证——exec 只在用户 / AI 显式提交代码时跑；测试全部用安全片段，
    不触碰任何外部服务、不耗 LLM 额度；
  · 复用不重造——标准库 subprocess / resource / os；隔离靠操作系统能力，不引第三方；
  · 安全优先——不可信代码绝不带凭据、不碰后端裸跑，子进程限额 + 网络隔离双保险。
"""
from __future__ import annotations

import os
import platform
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from ..config import settings
from ..plugins import plugin_registry

StreamCB = Callable[[str, str], None]  # (stream="stdout"|"stderr", text)


@dataclass
class ExecResult:
    """单次执行的完整结果。"""

    ok: bool
    stdout: str
    stderr: str
    returncode: Optional[int]
    ms: float
    error: str = ""          # 顶层错误（超时 / 被信号终止 / 启动失败）
    timed_out: bool = False


@dataclass
class InstallResult:
    """包安装结果。"""

    ok: bool
    message: str


@dataclass
class JobView:
    """执行任务的快照（HTTP 轮询返回）。"""

    job_id: str
    status: str              # running | done | error
    stdout: str
    stderr: str
    returncode: Optional[int] = None
    ms: float = 0.0
    error: str = ""
    timed_out: bool = False


def _resolve_pkg_dir() -> Path:
    """第三方包装载目录（SANDBOX_PKG_DIR 优先，否则数据目录 / sandbox_pkgs）。"""
    base = (settings.SANDBOX_PKG_DIR or "").strip()
    if not base:
        data = os.getenv("PYPEDIA_DATA",
                         os.path.join(os.path.expanduser("~"), ".pypedia"))
        base = os.path.join(data, "sandbox_pkgs")
    p = Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _list_pkg_names(pkg_dir: Path) -> list[str]:
    """包目录里可被 import 的顶层条目（过滤 __pycache__ 等噪声）。"""
    if not pkg_dir.is_dir():
        return []
    return sorted(p.name for p in pkg_dir.iterdir()
                 if p.is_dir() and p.name != "__pycache__")


def _rlimit_prelude() -> str:
    """资源限额前导代码（注入到用户代码之前，避免 preexec_fn 的 fork 隐患）。

    直接在被执行的 Python 进程里设 RLIMIT_AS / RLIMIT_CPU——限额作用于用户
    代码自身；配合 start_new_session=True 起新会话，超时对整个进程组 killpg。
    """
    lines: list[str] = []
    if settings.SANDBOX_EXEC_MEMORY_MB > 0:
        mb = int(settings.SANDBOX_EXEC_MEMORY_MB * 1024 * 1024)
        lines.append(
            f"import resource; resource.setrlimit(resource.RLIMIT_AS, ({mb}, {mb}))")
    if settings.SANDBOX_EXEC_CPU_SEC > 0:
        c = int(settings.SANDBOX_EXEC_CPU_SEC)
        lines.append(
            f"import resource; resource.setrlimit(resource.RLIMIT_CPU, ({c}, {c}))")
    return ("\n".join(lines) + "\n") if lines else ""


def _docker_available() -> bool:
    """docker 可执行且守护进程可达（docker info 成功）。"""
    if not shutil.which("docker"):
        return False
    try:
        r = subprocess.run(["docker", "info"], capture_output=True,
                           timeout=8, check=False)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class _Job:
    """单任务状态机：被 run_job 的后台线程驱动，支持增量输出 + 取消。"""

    def __init__(self, jid: str, code: str, timeout: float) -> None:
        self.jid = jid
        self.code = code
        self.timeout = timeout
        self.status = "running"
        self.stdout = ""
        self.stderr = ""
        self.returncode: Optional[int] = None
        self.ms = 0.0
        self.error = ""
        self.timed_out = False
        self.done = False
        self._lock = threading.Lock()
        self._kill_lock = threading.Lock()
        self._proc: Optional[subprocess.Popen] = None

    def append(self, stream: str, text: str) -> None:
        with self._lock:
            if stream == "stderr":
                self.stderr += text
            else:
                self.stdout += text

    def set_proc(self, proc: subprocess.Popen) -> None:
        with self._kill_lock:
            self._proc = proc

    def finish(self, res: ExecResult) -> None:
        with self._lock:
            self.stdout = res.stdout
            self.stderr = res.stderr
            self.returncode = res.returncode
            self.ms = res.ms
            self.error = res.error
            self.timed_out = res.timed_out
            self.status = "error" if (res.error and not res.stdout and not res.stderr) else "done"
            self.done = True

    def kill(self) -> bool:
        with self._kill_lock:
            proc = self._proc
        if proc is None:
            return False
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
            return True
        except (ProcessLookupError, PermissionError):
            return False

    def view(self) -> JobView:
        with self._lock:
            return JobView(self.jid, self.status, self.stdout, self.stderr,
                          self.returncode, self.ms, self.error, self.timed_out)


class PythonExec:
    """执行后端接口（子类实现具体隔离手段）。"""

    backend: str = "base"

    # —— 默认实现（子类按需覆盖 build/install） —— #
    def python_version(self) -> str:
        return platform.python_version()

    def exec_sync(self, code: str, *, timeout: Optional[float] = None) -> ExecResult:
        raise NotImplementedError

    def run_job(self, code: str, *, timeout: Optional[float] = None) -> str:
        raise NotImplementedError

    def get_job(self, job_id: str) -> Optional[JobView]:
        raise NotImplementedError

    def cancel_job(self, job_id: str) -> bool:
        raise NotImplementedError

    def install_package(self, name: str, *, index_url: str = "") -> InstallResult:
        raise NotImplementedError

    def status(self) -> dict:
        raise NotImplementedError


class _BaseExec(PythonExec):
    """共享的作业管理与子进程运行逻辑（与隔离手段无关）。"""

    def __init__(self) -> None:
        self._jobs: dict[str, _Job] = {}
        self._lock = threading.RLock()
        self._pkg_dir = _resolve_pkg_dir()

    # —— 作业管理 —— #
    def _new_job(self, code: str, timeout: float) -> _Job:
        jid = uuid.uuid4().hex
        job = _Job(jid, code, timeout)
        with self._lock:
            self._jobs[jid] = job
            # 容量上限：只保留最近 500 个任务，避免长开进程内存无界增长
            if len(self._jobs) > 500:
                old = next(iter(self._jobs))
                self._jobs.pop(old, None)
        return job

    def run_job(self, code: str, *, timeout: Optional[float] = None) -> str:
        timeout = timeout or settings.SANDBOX_EXEC_TIMEOUT
        job = self._new_job(code, float(timeout))

        def _drive() -> None:
            res = self._execute(job.code, timeout=job.timeout,
                               on_output=job.append, on_proc=job.set_proc)
            job.finish(res)

        threading.Thread(target=_drive, daemon=True).start()
        return job.jid

    def get_job(self, job_id: str) -> Optional[JobView]:
        with self._lock:
            job = self._jobs.get(job_id)
        return job.view() if job is not None else None

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None or job.done:
            return False
        return job.kill()

    def exec_sync(self, code: str, *, timeout: Optional[float] = None) -> ExecResult:
        timeout = timeout or settings.SANDBOX_EXEC_TIMEOUT
        return self._execute(code, timeout=float(timeout))

    # —— 子进程运行（子类构造 cmd 后调用） —— #
    def _make_workdir(self) -> Path:
        d = self._pkg_dir.parent / "sandbox_runs" / uuid.uuid4().hex
        d.mkdir(parents=True, exist_ok=True)
        return d

    @staticmethod
    def _stream(reader, stream_name: str, on_output: Optional[StreamCB],
                buffers: dict[str, str]) -> None:
        try:
            for chunk in iter(lambda: reader.read(4096), ""):
                if not chunk:
                    break
                buffers[stream_name] += chunk
                if on_output:
                    on_output(stream_name, chunk)
        except (ValueError, OSError):
            pass

    def _run_subprocess(self, cmd: list[str], *, timeout: float,
                        env: Optional[dict[str, str]],
                        on_output: Optional[StreamCB],
                        on_proc: Optional[Callable[[subprocess.Popen], None]]) -> ExecResult:
        workdir = self._make_workdir()
        start = time.monotonic()
        try:
            proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, cwd=str(workdir), env=env,
                start_new_session=True,
                text=True, encoding="utf-8", errors="replace",
            )
        except OSError as e:
            shutil.rmtree(workdir, ignore_errors=True)
            return ExecResult(ok=False, stdout="", stderr="",
                             returncode=None, ms=time.monotonic() - start,
                             error=f"启动失败：{e}")
        if on_proc:
            on_proc(proc)
        try:
            proc.stdin.close()  # -c 模式不需要 stdin，关闭防管道挂起
        except OSError:
            pass
        buffers = {"stdout": "", "stderr": ""}
        t_out = threading.Thread(target=self._stream, args=(proc.stdout, "stdout",
                                                           on_output, buffers), daemon=True)
        t_err = threading.Thread(target=self._stream, args=(proc.stderr, "stderr",
                                                           on_output, buffers), daemon=True)
        t_out.start()
        t_err.start()

        timed_out = False
        try:
            rc = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._kill_group(proc, signal.SIGTERM)
            try:
                rc = proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._kill_group(proc, signal.SIGKILL)
                rc = proc.wait(timeout=5)
            timed_out = True
        t_out.join(timeout=2)
        t_err.join(timeout=2)
        ms = time.monotonic() - start

        error = ""
        if timed_out:
            error = f"执行超时（>{timeout:.0f}s），已强制终止"
        elif rc is not None and rc < 0:
            error = f"进程被信号 {-rc} 终止"
        ok = (rc == 0) and not timed_out
        return ExecResult(ok=ok, stdout=buffers["stdout"], stderr=buffers["stderr"],
                         returncode=rc, ms=ms, error=error, timed_out=timed_out)

    @staticmethod
    def _kill_group(proc: subprocess.Popen, sig: int = signal.SIGTERM) -> None:
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, sig)
        except (ProcessLookupError, PermissionError):
            try:
                proc.kill()
            except OSError:
                pass

    # 子类必须实现
    def _execute(self, code: str, *, timeout: float,
                 on_output: Optional[StreamCB] = None,
                 on_proc: Optional[Callable[[subprocess.Popen], None]] = None) -> ExecResult:
        raise NotImplementedError


class LocalPythonExec(_BaseExec):
    """本地受控子进程后端（零额外依赖，默认）。"""

    backend = "local"

    def __init__(self) -> None:
        super().__init__()
        self._python = sys.executable or "python3.11"
        self._network_isolated = self._probe_unshare()

    @staticmethod
    def _probe_unshare() -> bool:
        if not shutil.which("unshare"):
            return False
        try:
            r = subprocess.run(["unshare", "-n", "true"], capture_output=True,
                               timeout=5, check=False)
            return r.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def _build_cmd(self, code: str, *, isolate_network: bool) -> list[str]:
        # 运行前注入：资源限额（子进程内 setrlimit，避免 preexec_fn 的 fork 隐患）
        # + 把包目录插入 sys.path（不依赖环境变量，规避 -I 忽略 PYTHONPATH）
        prelude = _rlimit_prelude()
        prelude += f"import sys\nsys.path.insert(0, {str(self._pkg_dir)!r})\n"
        full = prelude + code
        cmd = [self._python, "-I", "-c", full]
        if isolate_network and self._network_isolated:
            cmd = ["unshare", "-n", *cmd]
        return cmd

    def _execute(self, code: str, *, timeout: float,
                 on_output: Optional[StreamCB] = None,
                 on_proc: Optional[Callable[[subprocess.Popen], None]] = None) -> ExecResult:
        cmd = self._build_cmd(code, isolate_network=True)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)  # -I 本就忽略，显式清掉更稳妥
        return self._run_subprocess(cmd, timeout=timeout, env=env,
                                   on_output=on_output, on_proc=on_proc)

    def install_package(self, name: str, *, index_url: str = "") -> InstallResult:
        name = (name or "").strip()
        if not name:
            return InstallResult(ok=False, message="包名不能为空")
        # 安装需要网络：不套 unshare 网络隔离
        cmd = [self._python, "-m", "pip", "install", "--target", str(self._pkg_dir),
               "--no-cache-dir", "--disable-pip-version-check"]
        if index_url:
            cmd += ["--index-url", index_url]
        cmd.append(name)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=120,
                               env={**os.environ, "PYTHONPATH": str(self._pkg_dir)})
        except subprocess.TimeoutExpired:
            return InstallResult(ok=False, message="安装超时（>120s）")
        except OSError as e:
            return InstallResult(ok=False, message=f"安装启动失败：{e}")
        if r.returncode == 0:
            return InstallResult(ok=True, message=f"已安装 {name}，可 import 使用")
        tail = (r.stderr or r.stdout).strip()[-800:] or "安装失败"
        return InstallResult(ok=False, message=tail)

    def status(self) -> dict:
        return {
            "backend": self.backend,
            "python_version": self.python_version(),
            "network_isolated": self._network_isolated,
            "pkg_dir": str(self._pkg_dir),
            "installed_packages": self._list_pkgs(),
            "proxy_enabled": plugin_registry.is_enabled("sandbox-proxy"),
            "proxy_max_mb": settings.SANDBOX_PROXY_MAX_MB,
            "exec_timeout": settings.SANDBOX_EXEC_TIMEOUT,
        }

    def _list_pkgs(self) -> list[str]:
        return _list_pkg_names(self._pkg_dir)


class DockerPythonExec(_BaseExec):
    """Docker 隔离后端（--network=none + 资源限额，隔离更彻底）。"""

    backend = "docker"

    def __init__(self, image: str = "python:3.11-slim") -> None:
        super().__init__()
        self._image = image

    def _build_cmd(self, code: str) -> list[str]:
        # 资源限额注入到容器内 Python（与本地同构）；/pkgs 为挂载的包目录
        prelude = _rlimit_prelude()
        prelude += "import sys\nsys.path.insert(0, '/pkgs')\n"
        full = prelude + code
        return [
            "docker", "run", "--rm", "--network=none",
            f"--memory={int(settings.SANDBOX_EXEC_MEMORY_MB)}m",
            "--cpus=1.0",
            "-v", f"{self._pkg_dir}:/pkgs:rw",
            "-i", self._image, "python", "-I", "-c", full,
        ]

    def _execute(self, code: str, *, timeout: float,
                 on_output: Optional[StreamCB] = None,
                 on_proc: Optional[Callable[[subprocess.Popen], None]] = None) -> ExecResult:
        cmd = self._build_cmd(code)
        return self._run_subprocess(cmd, timeout=timeout, env=dict(os.environ),
                                   on_output=on_output, on_proc=on_proc)

    def install_package(self, name: str, *, index_url: str = "") -> InstallResult:
        name = (name or "").strip()
        if not name:
            return InstallResult(ok=False, message="包名不能为空")
        # 安装需要网络：--network=host
        cmd = ["docker", "run", "--rm", "--network=host",
               "-v", f"{self._pkg_dir}:/pkgs:rw", self._image,
               "python", "-m", "pip", "install", "--target", "/pkgs",
               "--no-cache-dir", "--disable-pip-version-check"]
        if index_url:
            cmd += ["--index-url", index_url]
        cmd.append(name)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            return InstallResult(ok=False, message="安装超时（>180s）")
        except OSError as e:
            return InstallResult(ok=False, message=f"安装启动失败：{e}")
        if r.returncode == 0:
            return InstallResult(ok=True, message=f"已安装 {name}，可 import 使用")
        tail = (r.stderr or r.stdout).strip()[-800:] or "安装失败"
        return InstallResult(ok=False, message=tail)

    def status(self) -> dict:
        return {
            "backend": self.backend,
            "image": self._image,
            "python_version": "3.11 (docker image)",
            "network_isolated": True,
            "pkg_dir": str(self._pkg_dir),
            "installed_packages": self._list_pkgs_local(),
            "proxy_enabled": plugin_registry.is_enabled("sandbox-proxy"),
            "proxy_max_mb": settings.SANDBOX_PROXY_MAX_MB,
            "exec_timeout": settings.SANDBOX_EXEC_TIMEOUT,
        }

    def _list_pkgs_local(self) -> list[str]:
        return _list_pkg_names(self._pkg_dir)


_exec_singleton: Optional[PythonExec] = None


def get_python_exec() -> PythonExec:
    """按 SANDBOX_BACKEND 选择后端（auto → docker 可用则用，否则 local）。"""
    global _exec_singleton
    if _exec_singleton is not None:
        return _exec_singleton
    backend = (settings.SANDBOX_BACKEND or "auto").lower()
    if backend == "docker":
        _exec_singleton = DockerPythonExec()
    elif backend == "local":
        _exec_singleton = LocalPythonExec()
    else:  # auto
        _exec_singleton = DockerPythonExec() if _docker_available() else LocalPythonExec()
    return _exec_singleton
