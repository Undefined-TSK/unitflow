/* ============ 沙箱运行时：服务端 Python 执行（P2 · 替代浏览器 Pyodide） ============
   依赖：util（$ / esc / api / authHeaders）。
   运行时：后端 pypedia/seams/python_exec.py（受控子进程 / Docker 隔离）。
   能力：原版 CPython（服务端本机解释器，标准库开箱即用）/ pip 装包（独立包目录，
        不污染系统 site）/ 联网可选（默认隔离，勾选「允许联网」才放开）/ 外部资源
        抓取走 fetch_url 工具经服务端代理（SSRF 已防护）。

   并行 / 取消模型（C1 v2 精神，但后端统一执行）：
     - run(code) → POST /api/sandbox/exec 拿 job_id → 轮询 /api/sandbox/job/{id}
       取增量 stdout/stderr → 完成 resolve {ok, stdout, stderr, returncode, ms, error}；
     - kill() → POST /api/sandbox/cancel/{id} 强杀当前 page 任务（死循环 / 超时兜底）；
     - install(pkgs) → POST /api/sandbox/install（需要网络，故安装不受网络隔离限制）。

   对外 API（window.Sandbox，供沙箱页 / 聊天代码块 / AI 工具层共用）：
     Sandbox.run(code, opts)      → Promise<{ok, stdout, stderr, returncode, ms, error}>
     Sandbox.install(pkgs, opts)  → Promise<{type:'installed'|'install_error', message, installed_packages}>
     Sandbox.runInline(pre, code) → 在代码块下方渲染输出面板（聊天页一键运行）
     Sandbox.kill()               → 终止当前 page 执行任务
     Sandbox.isReady()            → 后端常驻，恒 True
     Sandbox.ensure()             → 无需预热（no-op）
   opts: {origin:'page'|'chat'|'agent', allowNetwork, onStatus, onStdout, onStderr, onDone}
*/
(function () {
  const $ = (s, r = document) => r.querySelector(s);

  let currentPageJobId = null;   // 当前 page 任务（kill 用）

  /* —— 提交执行 + 轮询 —— */
  async function runJob(code, opts) {
    opts = opts || {};
    const body = JSON.stringify({
      code: String(code || ""),
      timeout: opts.timeout || undefined,
      allow_network: !!opts.allowNetwork,   // 默认隔离网络；仅用户显式勾选才放开
    });
    let resp;
    try {
      resp = await api("/api/sandbox/exec", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
      });
    } catch (e) {
      return { ok: false, error: "提交执行失败：" + (e && e.message ? e.message : e), ms: 0 };
    }
    if (!resp.ok) {
      const d = await resp.json().catch(() => ({}));
      return { ok: false, error: d.detail || ("HTTP " + resp.status), ms: 0 };
    }
    const started = await resp.json();
    const jobId = started.job_id;
    if (opts.origin === "page") currentPageJobId = jobId;
    return await pollJob(jobId, opts);
  }

  async function pollJob(jobId, opts) {
    const interval = 250;
    const maxWait = (opts.timeout || 30) + 6;
    const deadline = Date.now() + maxWait * 1000;
    let prevOut = "", prevErr = "";
    while (Date.now() < deadline) {
      let r;
      try {
        r = await api("/api/sandbox/job/" + jobId);
      } catch (e) {
        return { ok: false, error: "轮询失败：" + (e && e.message ? e.message : e), ms: 0 };
      }
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        return { ok: false, error: d.detail || ("HTTP " + r.status), ms: 0 };
      }
      const j = await r.json();
      const newOut = j.stdout.slice(prevOut.length);
      const newErr = j.stderr.slice(prevErr.length);
      prevOut = j.stdout; prevErr = j.stderr;
      if (newOut && opts.onStdout) opts.onStdout(newOut);
      if (newErr && opts.onStderr) opts.onStderr(newErr);
      if (opts.onStatus) opts.onStatus(j.status === "running" ? "运行中…" : "收尾…");
      if (j.status !== "running") {
        const ok = j.status === "done" && j.returncode === 0 && !j.timed_out;
        let error = j.error || "";
        if (!ok && !error) error = (j.stderr || "").slice(-500);
        return {
          ok, stdout: j.stdout, stderr: j.stderr,
          returncode: j.returncode, ms: j.ms, error, timed_out: j.timed_out,
        };
      }
      await new Promise((res) => setTimeout(res, interval));
    }
    return { ok: false, error: "轮询超时（前端侧）", ms: 0 };
  }

  /* —— 装包 —— */
  function install(packages, opts) {
    opts = opts || {};
    const pkgs = (Array.isArray(packages) ? packages : [packages]).filter(Boolean);
    const body = JSON.stringify({
      packages: pkgs.join(" "),
      index_url: opts.indexUrl || "",
    });
    return api("/api/sandbox/install", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    })
      .then((r) => r.json().catch(() => ({})))
      .then((d) => ({
        type: d.ok ? "installed" : "install_error",
        message: d.message || "安装失败",
        installed_packages: d.installed_packages || [],
      }))
      .catch((e) => ({
        type: "install_error",
        message: "安装请求失败：" + (e && e.message ? e.message : e),
      }));
  }

  /* —— 终止当前 page 任务 —— */
  function kill() {
    if (!currentPageJobId) return Promise.resolve(false);
    const id = currentPageJobId;
    currentPageJobId = null;
    return api("/api/sandbox/cancel/" + id, { method: "POST" })
      .then((r) => r.json())
      .then((d) => !!d.ok)
      .catch(() => false);
  }

  /* —— 沙箱页 chrome（元素恒在 DOM，隐藏页也可安全操作） —— */
  function setState(kind, text) {
    const el = $("#sbState");
    if (!el) return;
    el.className = "sb-state st " + kind;
    el.querySelector("span").textContent = text;
  }
  function appendOut(text, cls) {
    const out = $("#sbOut");
    if (!out) return;
    const line = document.createElement("span");
    if (cls) line.className = cls;
    line.textContent = text;
    out.appendChild(line);
    out.scrollTop = out.scrollHeight;
  }
  function clearOut() { const out = $("#sbOut"); if (out) out.textContent = ""; }
  function syncPageButtons() {
    const busy = !!currentPageJobId;
    const r = $("#sbRun"); if (r) r.disabled = busy;
    const i = $("#sbInstall"); if (i) i.disabled = busy;
  }
  const pageInFlight = () => !!currentPageJobId;

  /* —— 本地已装包清单（来自 /api/sandbox/status） —— */
  async function refreshPackages() {
    try {
      const st = await api("/api/sandbox/status").then((r) => r.json());
      const box = $("#sbWheels");
      if (!box) return;
      box.textContent = "";
      const pkgs = st.installed_packages || [];
      if (!pkgs.length) {
        box.innerHTML = '<span class="mini">尚未安装第三方包；在下方输入包名点击「安装」</span>';
        return;
      }
      pkgs.forEach((name) => {
        const b = document.createElement("button");
        b.className = "btn ghost sm";
        b.textContent = name.replace(/-py3-none-any\.whl$/, "").replace(/-cp3\d.*$/, "");
        b.title = "已安装：" + name;
        b.disabled = true;
        box.appendChild(b);
      });
    } catch (e) { /* 状态接口失败不阻塞沙箱使用 */ }
  }

  /* —— 沙箱页示例（服务端 Python：标准库 + 装包 + 联网可选） —— */
  const EXAMPLES = {
    hello: `# 服务端本机 CPython（标准库开箱即用）
import sys, platform
print("Python", sys.version.split()[0], "on", platform.machine())
print("你好，沙箱！这是一次真实的服务端 Python 执行。")
`,
    stdlib: `# 标准库导入：json / collections / dataclasses
import json
from collections import Counter
from dataclasses import dataclass

@dataclass
class Point:
    x: int
    y: int

p = Point(3, 4)
print("距离原点：", round((p.x**2 + p.y**2) ** 0.5, 2))

words = "the quick brown fox the lazy dog the".split()
print("词频：", dict(Counter(words)))

data = json.dumps({"ok": True, "items": [1, 2, 3]}, ensure_ascii=False)
print("JSON：", data)
`,
    numpy: `# 二进制库导入：numpy（先点下方「装 numpy」一键安装到独立包目录）
import numpy as np

a = np.arange(12).reshape(3, 4)
print("矩阵：")
print(a)
print("列和：", a.sum(axis=0).tolist())
print("均值：", round(float(a.mean()), 2))
`,
    net: `# 联网请求（需勾选「允许联网」开关，否则默认隔离网络）
import urllib.request
with urllib.request.urlopen("https://httpbin.org/get", timeout=10) as resp:
    body = resp.read().decode("utf-8")
print("状态码：", resp.status)
print("前 200 字符：", body[:200])
`,
    error: `# 异常与 traceback：错误会完整呈现在右侧输出面板
def divide(a, b):
    return a / b

try:
    print(divide(10, 0))
except ZeroDivisionError as e:
    print("捕获到除零错误：", e)
`,
  };

  function pageRun() {
    if (pageInFlight()) return;
    const code = $("#sbCode").value;
    clearOut();
    $("#sbMs").textContent = "";
    setState("warn", "运行中…");
    const allowNet = $("#sbNet") && $("#sbNet").checked;
    runJob(code, {
      origin: "page",
      allowNetwork: allowNet,
      onStdout: (t) => appendOut(t),
      onStderr: (t) => appendOut(t, "sb-err"),
      onStatus: (t) => setState("warn", "Python · " + t),
      onDone: (m) => {
        if (m.ok) {
          setState("on", "完成 · " + Math.round(m.ms) + "ms");
          $("#sbMs").textContent = "本次运行 " + Math.round(m.ms) + "ms";
        } else {
          setState("off", "出错 · " + Math.round(m.ms) + "ms");
          const tail = (m.error || (m.stderr || "").slice(-300) || "运行出错");
          appendOut("\n✗ " + tail + "\n", "sb-err");
          $("#sbMs").textContent = tail;
        }
        currentPageJobId = null;
        syncPageButtons();
      },
    }).catch((e) => {
      appendOut("沙箱内部错误：" + (e && e.message ? e.message : e) + "\n", "sb-err");
      currentPageJobId = null;
      syncPageButtons();
    });
  }

  function pageInstall() {
    const raw = ($("#sbPkg").value || "").trim();
    if (!raw) { appendOut("请输入包名（多个用空格分隔）\n", "sb-err"); return; }
    const indexUrl = ($("#sbIndex").value || "").trim();
    appendOut("⤓ 安装 " + raw + " …\n", "sb-dim");
    install(raw, { indexUrl }).then((r) => {
      if (r.type === "installed") {
        appendOut("✓ " + r.message + "\n", "sb-ok");
        refreshPackages();
      } else {
        appendOut("✗ " + (r.message || "安装失败") + "\n", "sb-err");
      }
    }).catch((e) => {
      appendOut("沙箱内部错误：" + (e && e.message ? e.message : e) + "\n", "sb-err");
    });
  }

  /* —— 聊天页「▶ 运行」：在代码块下方渲染沙箱输出面板 —— */
  function runInline(pre, codeText) {
    let panel = pre._sbPanel;
    if (!panel) {
      panel = document.createElement("div");
      panel.className = "sb-inline";
      panel.innerHTML =
        '<div class="sb-inline-hd"><span class="sb-inline-t">沙箱输出</span>' +
        '<span class="sb-inline-s"></span></div><pre class="sb-inline-out"></pre>';
      pre.insertAdjacentElement("afterend", panel);
      pre._sbPanel = panel;
    }
    const out = $(".sb-inline-out", panel);
    const st = $(".sb-inline-s", panel);
    out.textContent = "";
    st.textContent = "排队中…";
    st.className = "sb-inline-s run";
    runJob(codeText, {
      origin: "chat",
      onStatus: (t) => { st.textContent = t; },
      onStdout: (t) => appendSpan(out, t, ""),
      onStderr: (t) => appendSpan(out, t, "sb-err"),
      onDone: (m) => {
        st.textContent = m.ok ? ("✓ 完成 · " + Math.round(m.ms) + "ms")
                              : ("✗ " + (m.error || "运行出错"));
        st.className = "sb-inline-s " + (m.ok ? "ok" : "err");
      },
    }).catch((e) => {
      st.textContent = "沙箱内部错误：" + (e && e.message ? e.message : e);
      st.className = "sb-inline-s err";
    });
  }
  function appendSpan(out, text, cls) {
    const line = document.createElement("span");
    if (cls) line.className = cls;
    line.textContent = text;
    out.appendChild(line);
    out.scrollTop = out.scrollHeight;
  }

  /* —— 事件绑定（页面打开时调用一次） —— */
  let bound = false;
  function bind() {
    if (bound) return;
    bound = true;
    $("#sbRun").onclick = pageRun;
    $("#sbStop").onclick = kill;
    $("#sbInstall").onclick = pageInstall;
    $("#sbPkg").onkeydown = (e) => { if (e.key === "Enter") pageInstall(); };
    const code = $("#sbCode");
    code.value = EXAMPLES.hello;
    $("#sbExample").onchange = () => {
      const ex = EXAMPLES[$("#sbExample").value];
      if (ex) code.value = ex;
    };
    code.onkeydown = (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); pageRun(); }
      if (e.key === "Tab") {
        e.preventDefault();
        const s = code.selectionStart, t = code.selectionEnd;
        code.value = code.value.slice(0, s) + "    " + code.value.slice(t);
        code.selectionStart = code.selectionEnd = s + 4;
      }
    };
  }

  /* —— 对外 API —— */
  window.Sandbox = {
    ensure() {},            // 服务端常驻，无需预热
    run: runJob,
    install,
    kill,
    isReady: () => true,
    runInline,
  };

  /* —— 页面入口：app.goPage 调用；懒加载运行时 —— */
  window.loadSandbox = function () {
    bind();
    refreshPackages();
  };
})();
