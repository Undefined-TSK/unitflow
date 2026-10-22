/* ============ AI 沙箱工具循环（function calling） ============
   勾选问答页「🧰 沙箱验证」后，AI 回答前可自动调用沙箱工具验证
   （run_python 跑代码 / install_package 装包 / fetch_url 抓公网文本 /
    sandbox_status 查能力），过程以卡片可视化，最终答案照常 Markdown 渲染
   （其中的 python 代码块自带「▶ 运行」按钮，用户可复核）。
   并行规则：一步内多个 tool_calls 且不含 install_package 时并行执行
   （沙箱 Worker 池同步跑）；含 install 的 step 串行（install→run 有顺序依赖）。

   协议（服务端无状态，见 pypedia/agent/transport.py）：
     POST /api/agent/step {query, level}          → {type:"tool_calls", calls, state, max_rounds}
                                                     或 {type:"final", content, state, provider}
     POST /api/agent/step {state, tool_results, level}
                                                    → 同上（state opaque 透传，tool_results=[{id, result}]）
   工具在浏览器沙箱执行（window.Sandbox），服务端不跑任何用户/AI 代码。
   依赖：util（$/esc/api/humanError/BUSY/setBusy）、chat（addMsg）、md（md/revealMarkdown）、
        sandbox（window.Sandbox）。
*/
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const TOOL_LIMIT = 6;                 // 前端兜底轮次上限（服务端 max_rounds 同步约束）
  const OUT_CAP = 4000;                 // 工具结果回喂模型的内容截断（字符）

  const TOOL_LABELS = {
    run_python: "▶ 运行代码",
    install_package: "⤓ 安装包",
    fetch_url: "🌐 抓取网页",
    sandbox_status: "📦 沙箱状态",
  };

  function truncate(s) {
    s = String(s || "");
    return s.length > OUT_CAP ? s.slice(0, OUT_CAP) + "\n…（已截断）" : s;
  }

  async function postStep(body) {
    const r = await api("/api/agent/step", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(d.detail || ("AI 工具步骤失败（HTTP " + r.status + "）"));
    return d;
  }

  /* —— 工具调用轨迹卡片 —— */
  function toolCard(traceEl, call) {
    const args = call.arguments || {};
    const preview = args.code || args.name || args.url || "";
    const card = document.createElement("details");
    card.className = "agent-step";
    card.open = true;
    card.innerHTML =
      '<summary><span class="as-tag"></span><span class="as-arg-preview"></span></summary>' +
      '<div class="as-body"><pre class="as-args"></pre><pre class="as-out"></pre></div>';
    $(".as-tag", card).textContent = TOOL_LABELS[call.name] || call.name;
    $(".as-arg-preview", card).textContent = preview.slice(0, 90);
    $(".as-args", card).textContent = preview || "（无参数）";
    traceEl.appendChild(card);
    const out = $(".as-out", card);
    out.textContent = "执行中…";
    return out;
  }

  /* —— 工具执行：全部在浏览器沙箱 / 同源代理内完成 —— */
  async function execTool(call, outEl) {
    const args = call.arguments || {};
    if (call.name === "run_python") {
      let text = "";
      const r = await window.Sandbox.run(args.code, {
        origin: "agent",
        onStdout: (t) => { text += t; outEl.textContent = truncate(text); },
        onStderr: (t) => { text += t; outEl.textContent = truncate(text); },
        onStatus: () => {},
      });
      if (!r.ok) text += (text ? "\n" : "") + "（未正常结束：" + (r.error || "运行失败") + "）";
      const shown = truncate(text || "（代码执行完毕，无输出）");
      outEl.textContent = shown;   // 失败时也要把结尾信息渲染回卡片
      return shown;
    }
    if (call.name === "install_package") {
      const r = await window.Sandbox.install([args.name], {
        origin: "agent",
        onStatus: (t) => { outEl.textContent = t; },
      });
      const msg = r.type === "installed"
        ? ("安装成功：" + args.name + "，可以 import 了")
        : ("安装失败：" + (r.message || "未知错误"));
      outEl.textContent = msg;   // 安装结果落卡（否则卡片停在"安装中…"）
      return msg;
    }
    if (call.name === "fetch_url") {
      const resp = await api("/api/sandbox/proxy?url=" + encodeURIComponent(args.url));
      const d = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        const fail = "抓取失败（HTTP " + resp.status + "）：" + (d.detail || "未知错误");
        outEl.textContent = fail;
        return fail;
      }
      let text = d.text;
      if (text == null && d.b64) {
        try {
          const bin = Uint8Array.from(atob(d.b64), (c) => c.charCodeAt(0));
          text = new TextDecoder().decode(bin);
        } catch (e) { text = ""; }
      }
      const head = "HTTP " + d.status + " · " + (d.content_type || "") +
                   (d.truncated ? " · 已截断" : "");
      outEl.textContent = head + "\n" + truncate(text || "");
      return truncate(head + "\n" + (text || ""));
    }
    if (call.name === "sandbox_status") {
      const st = await api("/api/sandbox/status").then((r) => r.json());
      const info = "后端：" + (st.backend || "?") +
        " · Python " + (st.python_version || "?") +
        " · 网络隔离：" + (st.network_isolated ? "开" : "关") +
        " · 已装包：" + ((st.installed_packages || []).join("、") || "无") +
        " · 外部资源代理：" + (st.proxy_enabled ? "开" : "关");
      outEl.textContent = info;
      return info;
    }
    return "未知工具：" + call.name;
  }

  /* —— 主入口：问答页勾选「沙箱验证」后由 chat.send 转调 —— */
  window.startAgent = async function (query, level) {
    if (BUSY) return;
    setBusy(true);
    const typing = addMsg("ai", '<div class="typing"><i></i><i></i><i></i></div>');
    const bubble = typing.querySelector(".bubble");
    bubble.innerHTML = '<div class="meta"></div><div class="agent-trace"></div><div class="md"></div>';
    const traceEl = $(".agent-trace", bubble);
    const mdEl = $(".md", bubble);
    try {
      let step = await postStep({ query, level });
      let state = null;
      for (let round = 0; step.type === "tool_calls"; round++) {
        const limit = step.max_rounds || TOOL_LIMIT;
        if (round >= limit) {
          traceEl.insertAdjacentHTML("beforeend",
            '<div class="mini" style="color:var(--danger);padding:4px 2px">' +
            "已达工具调用轮次上限（" + limit + "），停止调用。</div>");
          break;
        }
        state = step.state;
        const toolResults = [];
        // 并行规则（C1 v2）：一步内多个调用且不含 install_package 时并行执行
        //（沙箱 Worker 池同步跑，互不排队）；install 与 run 有顺序依赖，
        // 含 install 的 step 保持串行，避免 import 落到未装完的 worker。
        const execOne = async (call) => {
          const outEl = toolCard(traceEl, call);
          if (call.invalid) {
            const result = "参数错误：" + call.invalid;
            outEl.textContent = result;
            const tag = outEl.closest(".agent-step").querySelector(".as-tag");
            if (tag) tag.classList.add("err");
            return { id: call.id, result: result };
          }
          try {
            const result = await execTool(call, outEl);
            return { id: call.id, result: result };
          } catch (e) {
            const result = "工具执行异常：" + (e && e.message ? e.message : e);
            outEl.textContent = result;
            return { id: call.id, result: result };
          }
        };
        if (step.calls.some((c) => c.name === "install_package")) {
          for (const call of step.calls) toolResults.push(await execOne(call));
        } else {
          // Promise.all 保序：toolResults 与 calls 顺序一致（模型侧按 id 对应）
          for (const m of await Promise.all(step.calls.map(execOne))) toolResults.push(m);
        }
        step = await postStep({ state, tool_results: toolResults, level });
      }
      if (step.type !== "final") {
        // 轮次上限：保留已展示的工具轨迹，给出可操作说明（不擦掉过程、不报红错）
        mdEl.innerHTML = "";
        revealMarkdown(mdEl, md(
          "（AI 工具调用轮次已达上限，未能形成最终答案。请把问题范围缩小，或稍后再试。）"));
        $(".meta", bubble).innerHTML =
          '<span>等级 L' + level + '</span><span class="cf">🧰 沙箱验证 · 轮次上限</span>';
      } else {
        const answer = step.content;
        mdEl.innerHTML = "";
        revealMarkdown(mdEl, md(answer));
        bubble.dataset.md = answer;
        $(".meta", bubble).innerHTML =
          '<span>等级 L' + level + '</span><span>通道 ' + (step.provider || "?") + "</span>" +
          '<span class="cf">🧰 沙箱验证' + (step.degraded ? "（离线演示通道）" : "") + "</span>";
      }
      $("#msgs").scrollTop = $("#msgs").scrollHeight;
    } catch (e) {
      bubble.innerHTML = '<span style="color:var(--danger)">' + esc(humanError(e)) + "</span>";
    } finally {
      setBusy(false);
      const qi = $("#qInput");
      if (qi) qi.focus();
    }
  };
})();
