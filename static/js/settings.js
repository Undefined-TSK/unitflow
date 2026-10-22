/* ============ 设置页：状态 + MCP 面板 + 能力面板 + 鉴权/备份卡片 ============
   依赖：util（$/api/esc/getToken/setToken/CONFIG） */
async function loadSettings(){
  const b=$("#settingsBody");b.innerHTML='<div class="muted">加载中…</div>';
  try{
    const r=await api("/api/status");const d=await r.json();
    CONFIG=d;
    $("#navProv").textContent=d.provider;
    b.innerHTML=`<div class="kv"><span>模型通道</span><span style="color:var(--accent)">${d.provider}</span></div>`+
      `<div class="kv"><span>模型</span><span>${d.model}</span></div>`+
      `<div class="kv"><span>联网抓取</span><span>${d.web_fetch?"已开启":"关闭（用本地语料兜底）"}</span></div>`+
      `<div class="kv"><span>百炼密钥</span><span>${d.config.bailian_key}</span></div>`+
      `<div class="kv"><span>百炼模型</span><span>${d.config.bailian_model}</span></div>`+
      `<div class="kv"><span>Ollama 地址</span><span>${d.config.ollama_host}</span></div>`+
      `<div class="kv"><span>上传上限</span><span>${d.config.upload_limit_mb}MB / 文件</span></div>`+
      `<div class="kv"><span>上下文预算</span><span>${d.config.context_budget} tokens（超了滑窗+滚动摘要）</span></div>`+
      `<div class="kv"><span>本地重排</span><span>${d.config.rerank_local}</span></div>`+
      `<div class="kv"><span>答案二审</span><span>${d.config.review?"已开启（双模型）":"关闭"}</span></div>`+
      `<div class="card" style="margin-top:14px"><h3 style="margin-top:0">访问鉴权</h3>`+
      `<div class="kv"><span>服务端鉴权</span><span style="color:${d.config.auth?"var(--ok)":"var(--warn)"}">${d.config.auth?"已开启（Bearer Token）":"关闭（仅本机访问时无需开启）"}</span></div>`+
      `<div class="kv"><span>本地令牌</span><span id="authState">${getToken()?"已保存（浏览器本地存储）":"未设置"}</span></div>`+
      `<input id="authInput" class="inp" placeholder="粘贴令牌后保存" style="width:100%;margin-top:8px" value="${esc(getToken())}">`+
      `<div style="display:flex;gap:8px;margin-top:8px">`+
      `<button class="btn primary" id="authSave">保存令牌</button>`+
      `<button class="btn" id="authClear">清除令牌</button></div>`+
      `<div class="mini" style="margin-top:6px">开启方式：.env 设 AUTH_ENABLE=true 并重启；令牌自动生成于数据目录 token 文件（权限 600），也可在 .env 用 AUTH_TOKEN 指定。放行：/、/static、/api/status。</div>`+
      `</div>`+
      `<div class="card" style="margin-top:14px"><h3 style="margin-top:0">数据备份</h3>`+
      `<div class="mini">打包知识库索引、长期记忆、用户画像与自进化数据为 zip（不含访问令牌与日志）。恢复为替换语义，恢复前自动快照可回滚。</div>`+
      `<div style="display:flex;gap:8px;margin-top:8px">`+
      `<button class="btn primary" id="bkExport">导出备份</button>`+
      `<label class="btn" for="bkImportFile">导入恢复</label>`+
      `<input id="bkImportFile" type="file" accept=".zip" style="display:none">`+
      `</div><div id="bkMsg" class="mini" style="margin-top:6px"></div></div>`+
      `<div class="card" style="margin-top:14px"><h3 style="margin-top:0">成本 / Token 面板</h3>`+
      `<div id="costPanel"><div class="muted">统计中…</div></div>`+
      `<div class="mini" style="margin-top:6px">嵌入向量落盘缓存命中即省一次百炼嵌入调用；"估算节省"为粗估（按 ~150 token/片段）。</div></div>`+
      `<div id="capPanel"></div><div id="mcpPanel"></div>`+
      `<div id="agentMemPanel"></div><div id="agentSkillPanel"></div>`+
      `<div id="agentCronPanel"></div><div id="pluginPanel"></div>`+
      `<div id="marketPanel"></div>`;
    loadCapabilities();loadMcp();loadCost();loadAgentMemory();loadAgentSkills();loadAgentCron();loadPlugins();loadMarket();
    $("#authSave").onclick=()=>{setToken($("#authInput").value.trim());
      $("#authState").textContent=getToken()?"已保存（浏览器本地存储）":"未设置";};
    $("#authClear").onclick=()=>{setToken("");$("#authInput").value="";
      $("#authState").textContent="未设置";};
    $("#bkExport").onclick=async()=>{
      const r=await api("/api/backup/export",{method:"POST"});
      if(!r.ok){$("#bkMsg").innerHTML='<span style="color:var(--danger)">导出失败</span>';return;}
      const blob=await r.blob();
      const a=document.createElement("a");
      a.href=URL.createObjectURL(blob);
      a.download="pypedia-backup.zip";a.click();
      URL.revokeObjectURL(a.href);
      $("#bkMsg").innerHTML='<span style="color:var(--ok)">已开始下载</span>';};
    $("#bkImportFile").onchange=async()=>{
      const f=$("#bkImportFile").files[0];if(!f)return;
      const fd=new FormData();fd.append("file",f);
      $("#bkMsg").textContent="恢复中…";
      try{
        const r=await api("/api/backup/import",{method:"POST",body:fd});
        const d=await r.json();
        $("#bkMsg").innerHTML=r.ok
          ?'<span style="color:var(--ok)">'+esc(d.note||"恢复完成")+'</span>'
          :'<span style="color:var(--danger)">'+esc(d.detail||"恢复失败")+'</span>';
      }catch(e){$("#bkMsg").innerHTML='<span style="color:var(--danger)">'+esc(e.message)+'</span>';}
    };
  }catch(e){b.innerHTML='<div style="color:var(--danger)">状态获取失败：'+esc(e.message)+'</div>';}
}
async function loadCost(){
  const box=$("#costPanel");if(!box)return;
  try{
    const d=await (await api("/api/cost")).json();
    const c=d.embed_cache||{};
    const rows=c.rows||0;
    const saved=c.estimated_saved_tokens||0;
    const byModel=c.by_model||{};
    const modelLines=Object.entries(byModel).map(([m,n])=>
      `<span class="tag">${esc(m)} ×${n}</span>`).join("")||'<span class="muted">暂无</span>';
    box.innerHTML=
      `<div class="kv"><span>嵌入缓存向量数</span><span style="color:var(--accent)">${rows}</span></div>`+
      `<div class="kv"><span>估算节省嵌入 token</span><span>${saved.toLocaleString()}</span></div>`+
      `<div class="kv"><span>当前模型通道</span><span>${esc(d.provider)}</span></div>`+
      `<div class="kv"><span>对话模型</span><span>${esc(d.models.chat)}</span></div>`+
      `<div class="kv"><span>嵌入模型</span><span>${esc(d.models.embed)} / ${esc(d.models.embed_v4)}</span></div>`+
      `<div style="margin-top:8px"><div class="mini">按模型分布：</div>${modelLines}</div>`;
  }catch(e){box.innerHTML='<div style="color:var(--danger)">成本统计失败：'+esc(e.message)+'</div>';}
}
async function loadMcp(){
  const box=$("#mcpPanel");if(!box)return;
  box.innerHTML='<h3 style="margin:16px 0 0">MCP 协议层（真实连接）</h3><div class="muted">探测中…</div>';
  try{
    const d=await (await api("/api/mcp")).json();
    let h=`<h3 style="margin:16px 0 0">MCP 协议层 · 官方参考 server</h3>`;
    h+=d.servers.map(s=>{
      const cls=s.connected?"on":"off";
      return `<div class="skill"><span class="st ${cls}"><i></i>${esc(s.name)} · ${s.connected?"已连接":"未连接"}</span>`+
        `<div class="mini">${esc(s.detail)}</div>`+
        (s.tools&&s.tools.length?`<div style="margin-top:4px">${s.tools.map(t=>
          `<span class="tool-chip" title="${esc(t.description||"")}">${esc(t.name)}</span>`).join("")}</div>`:"")+
        `</div>`;
    }).join("");
    box.innerHTML=h;
  }catch(e){box.innerHTML='<div style="color:var(--danger)">MCP 状态获取失败：'+esc(e.message)+'</div>';}
}
/* ============ 设置页：Agent 持久记忆（只读） + 技能库（三级渐进披露）面板 ============
   依赖：util（$/api/esc） */
async function loadAgentMemory(){
  const box=$("#agentMemPanel");if(!box)return;
  box.innerHTML='<h3 style="margin:16px 0 0">🧠 持久记忆（只读）</h3><div class="muted">加载中…</div>';
  try{
    const r=await api("/api/agent/memory");
    if(!r.ok){const d=await r.json().catch(()=>({}));
      throw new Error(d.detail||("HTTP "+r.status));}
    const d=await r.json();
    const sec=(scope,label,note)=>{
      const list=(d.sections&&d.sections[scope])||[];
      const chips=list.length
        ? list.map(h=>`<span class="tag">${esc(h)}</span>`).join("")
        : '<span class="muted">暂无段落</span>';
      return `<div class="skill"><b>${label}</b>`+
        `<div class="mini">${note}</div>`+
        `<div style="margin-top:6px">${chips}</div>`+
        (d[scope]?`<pre class="mem-full">${esc(d[scope])}</pre>`:'')+
        `</div>`;
    };
    box.innerHTML='<h3 style="margin:16px 0 0">🧠 持久记忆（只读）</h3>'+
      `<div class="mini">Agent 通过 memory_add / memory_patch / memory_remove 工具自主维护；此处仅供查看，不提供编辑入口。</div>`+
      sec("memory","MEMORY.md · 项目记忆","稳定的项目事实（配置偏好、结论、坑），§ 段落可被精确增删改。")+
      sec("user","USER.md · 用户画像","用户身份、偏好与协作习惯，跨会话保留。");
  }catch(e){
    box.innerHTML='<h3 style="margin:16px 0 0">🧠 持久记忆（只读）</h3>'+
      `<div style="color:var(--danger)">加载失败：${esc(e.message)}（可能已在配置中关闭：AGENT_MEMORY_ENABLE=false）</div>`;
  }
}
async function loadAgentSkills(){
  const box=$("#agentSkillPanel");if(!box)return;
  box.innerHTML='<h3 style="margin:16px 0 0">🛠 技能库</h3>'+
    `<div class="mini">三级渐进披露：L1 名称+描述进系统提示词；L2 补充何时用/标签/用量；点击「查看全文」看 L3（SKILL.md 指令正文，查看即计入用量）。</div>`+
    `<input id="skillQ" class="inp" placeholder="按关键词过滤（描述 / 何时用 / 标签）" style="width:100%;margin:8px 0">`+
    `<div id="skillList"><div class="muted">加载中…</div></div>`;
  const renderList=d=>{
    const fmtTs=ts=>{try{return new Date(ts*1000).toLocaleString("zh-CN",{hour12:false});}catch(e){return "";}};
    let h=(d.skills||[]).map(s=>{
      const tags=(s.tags||[]).map(t=>`<span class="tag">${esc(t)}</span>`).join("");
      const u=s.usage||{};
      const usage=`用量 ${u.count??0}`+(u.last_used?` · 最近 ${esc(fmtTs(u.last_used))}`:"");
      return `<div class="skill"><b>${esc(s.name)}</b>`+
        ` <span class="mini">v${esc(s.version||"1")} · ${usage}</span>`+
        `<div class="mini">${esc(s.description)}</div>`+
        `<div class="mini">何时用：${esc(s.when_to_use)}</div>`+
        (tags?`<div style="margin-top:4px">${tags}</div>`:"")+
        `<div style="margin-top:6px"><button class="btn" data-skill="${esc(s.name)}">查看全文</button></div>`+
        `<div id="skillFull-${esc(s.name)}"></div></div>`;
    }).join("")||'<div class="muted">未命中技能</div>';
    if((d.archived||[]).length)
      h+=`<div class="mini" style="margin-top:10px">已归档（超期未用）：`+
        d.archived.map(a=>`<span class="tag">${esc(a)}</span>`).join("")+`</div>`;
    $("#skillList").innerHTML=h;
    $$("#skillList button[data-skill]").forEach(btn=>{
      btn.onclick=()=>viewSkillFull(btn.dataset.skill,btn);
    });
  };
  const load=async q=>{
    try{
      const r=await api("/api/agent/skills"+(q?"?query="+encodeURIComponent(q):""));
      if(!r.ok){const d=await r.json().catch(()=>({}));
        throw new Error(d.detail||("HTTP "+r.status));}
      renderList(await r.json());
    }catch(e){
      $("#skillList").innerHTML=`<div style="color:var(--danger)">加载失败：${esc(e.message)}</div>`;
    }
  };
  $("#skillQ").oninput=()=>load($("#skillQ").value.trim());
  await load("");
}
async function viewSkillFull(name,btn){
  const box=document.getElementById("skillFull-"+name);
  if(!box)return;
  if(box.dataset.loaded==="1"){ // 再点一次收起
    box.dataset.loaded="";box.innerHTML="";btn.textContent="查看全文";return;
  }
  box.innerHTML='<div class="muted">加载中…</div>';
  try{
    const r=await api("/api/agent/skills/"+encodeURIComponent(name));
    if(!r.ok){const d=await r.json().catch(()=>({}));
      throw new Error(d.detail||("HTTP "+r.status));}
    const d=await r.json();
    box.innerHTML=`<pre class="mem-full">${esc(d.body||"（无正文）")}</pre>`;
    box.dataset.loaded="1";btn.textContent="收起";
  }catch(e){
    box.innerHTML=`<div style="color:var(--danger)">加载失败：${esc(e.message)}</div>`;
  }
}
/* ============ 设置页：Agent 定时任务（cron）面板 ============
   依赖：util（$/$$/api/esc）。后端：GET/POST/DELETE /api/agent/cron + {id}/{action} */
let CRON_META={builtin_tasks:[],max_tasks:20};   // 内置任务清单 / 上限（GET 时刷新）
async function loadAgentCron(){
  const box=$("#agentCronPanel");if(!box)return;
  box.innerHTML='<h3 style="margin:16px 0 0">⏰ 定时任务</h3><div class="muted">加载中…</div>';
  let d;
  try{
    const r=await api("/api/agent/cron");
    if(!r.ok){const e=await r.json().catch(()=>({}));
      throw new Error(e.detail||("HTTP "+r.status));}
    d=await r.json();
  }catch(e){
    box.innerHTML='<h3 style="margin:16px 0 0">⏰ 定时任务</h3>'+
      `<div style="color:var(--danger)">加载失败：${esc(e.message)}（可能已在配置中关闭：AGENT_CRON_ENABLE=false）</div>`;
    return;
  }
  CRON_META={builtin_tasks:d.builtin_tasks||[],max_tasks:d.max_tasks||20};
  const fmtTs=ts=>{try{return new Date(ts*1000).toLocaleString("zh-CN",{hour12:false});}catch(e){return "";}};
  box.innerHTML='<h3 style="margin:16px 0 0">⏰ 定时任务</h3>'+
    `<div class="mini">三类触发：cron 表达式 / 固定间隔 / 一次性时间点。内置任务为纯函数（不调模型）；Agent 任务到点跑一轮问答，结果以站内通知返回。上限 ${CRON_META.max_tasks} 个。</div>`+
    `<div id="cronList"></div>`+
    `<div class="card" style="margin-top:12px"><h3 style="margin-top:0">新建任务</h3><div id="cronForm"></div></div>`+
    `<h3 style="margin:16px 0 0">最近通知</h3><div id="cronNotes"></div>`;
  renderCronList(d.tasks||[]);
  renderCronForm();
  renderCronNotes(d.notifications||[],fmtTs);
}
function renderCronList(tasks){
  const box=$("#cronList");if(!box)return;
  if(!tasks.length){box.innerHTML='<div class="muted">暂无任务</div>';return;}
  box.innerHTML=tasks.map(t=>{
    const kindTag=t.kind==="agent"?"Agent 任务":"内置任务";
    const state=t.paused
      ?'<span style="color:var(--warn)">已暂停</span>'
      :'<span style="color:var(--ok)">运行中</span>';
    const next=t.next_run_time?esc(t.next_run_time.replace("T"," ").slice(0,16)):"—";
    return `<div class="skill"><b>${esc(t.name)}</b> <span class="mini">${kindTag} · ${esc(t.schedule_text)} · ${state}</span>`+
      `<div class="mini">下次运行：${next}</div>`+
      (t.query?`<div class="mini">指令：${esc(t.query)}</div>`:"")+
      `<div style="margin-top:6px;display:flex;gap:8px;flex-wrap:wrap">`+
      `<button class="btn primary" data-cron-run="${esc(t.id)}">立即执行</button>`+
      (t.paused
        ?`<button class="btn" data-cron-resume="${esc(t.id)}">恢复</button>`
        :`<button class="btn" data-cron-pause="${esc(t.id)}">暂停</button>`)+
      `<button class="btn" data-cron-del="${esc(t.id)}">删除</button>`+
      `</div></div>`;
  }).join("");
  $$("#cronList button[data-cron-run]").forEach(b=>b.onclick=()=>cronAction(b.dataset.cronRun,"run","已触发，结果见通知"));
  $$("#cronList button[data-cron-pause]").forEach(b=>b.onclick=()=>cronAction(b.dataset.cronPause,"pause","已暂停"));
  $$("#cronList button[data-cron-resume]").forEach(b=>b.onclick=()=>cronAction(b.dataset.cronResume,"resume","已恢复"));
  $$("#cronList button[data-cron-del]").forEach(b=>b.onclick=async()=>{
    if(!confirm("删除定时任务「"+b.dataset.cronDel+"」？"))return;
    try{
      const r=await api("/api/agent/cron/"+encodeURIComponent(b.dataset.cronDel),{method:"DELETE"});
      if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(e.detail||("HTTP "+r.status));}
      await loadAgentCron();
    }catch(e){alert("删除失败："+e.message);}
  });
}
async function cronAction(id,action,okMsg){
  try{
    const r=await api("/api/agent/cron/"+encodeURIComponent(id)+"/"+action,{method:"POST"});
    const d=await r.json().catch(()=>({}));
    if(!r.ok)throw new Error(d.detail||("HTTP "+r.status));
    if(action==="run")alert(okMsg+"（后台执行中）");
    await loadAgentCron();
  }catch(e){alert("操作失败："+e.message);}
}
function renderCronNotes(notes,fmtTs){
  const box=$("#cronNotes");if(!box)return;
  if(!notes.length){box.innerHTML='<div class="muted">暂无通知</div>';return;}
  box.innerHTML=notes.map(n=>
    `<div class="skill"><span style="color:${n.ok?"var(--ok)":"var(--danger)"}">${n.ok?"✓":"✗"}</span> `+
    `<b>${esc(n.title)}</b> <span class="mini">${esc(fmtTs(n.ts))}</span>`+
    `<div class="mini" style="white-space:pre-wrap">${esc(n.body)}</div></div>`).join("");
}
/* —— 新建任务表单（kind / schedule 类型联动切换，切换时保留已填值） —— */
function renderCronForm(){
  const box=$("#cronForm");if(!box)return;
  const kind=$("#cronKind")?$("#cronKind").value:"builtin";
  const stype=$("#cronSType")?$("#cronSType").value:"cron";
  const builtinOpts=CRON_META.builtin_tasks.map(t=>
    `<option value="${esc(t.key)}">${esc(t.name)}</option>`).join("");
  const schedFields=
    stype==="cron"
      ?`<input id="cronExpr" class="inp" placeholder="0 3 * * *（分 时 日 月 周）" style="width:100%" value="${esc($("#cronExpr")?$("#cronExpr").value:"")}">`
      :stype==="interval"
      ?`<div style="display:flex;gap:8px"><input id="cronEvery" class="inp" type="number" min="1" value="${esc($("#cronEvery")?$("#cronEvery").value:"30")}" style="flex:1">`+
       `<select id="cronUnit" class="inp" style="width:90px">${["seconds","minutes","hours","days"].map(u=>
         `<option value="${u}"${($("#cronUnit")?$("#cronUnit").value:"minutes")===u?" selected":""}>${{seconds:"秒",minutes:"分钟",hours:"小时",days:"天"}[u]}</option>`).join("")}</select></div>`
      :`<input id="cronAt" class="inp" type="datetime-local" style="width:100%" value="${esc($("#cronAt")?$("#cronAt").value:"")}">`;
  box.innerHTML=
    `<div style="display:flex;gap:8px;flex-wrap:wrap">`+
    `<input id="cronName" class="inp" placeholder="任务名称" style="flex:1;min-width:140px" value="${esc($("#cronName")?$("#cronName").value:"")}">`+
    `<select id="cronKind" class="inp" style="width:130px">`+
    `<option value="builtin"${kind==="builtin"?" selected":""}>内置任务</option>`+
    `<option value="agent"${kind==="agent"?" selected":""}>Agent 任务</option></select></div>`+
    (kind==="builtin"
      ?`<select id="cronBuiltin" class="inp" style="width:100%;margin-top:8px">${builtinOpts}</select>`
      :`<textarea id="cronQuery" class="inp" rows="2" placeholder="到点要让 Agent 执行的指令（如：回顾最近三天的记忆并给出整理建议）" style="width:100%;margin-top:8px">${esc($("#cronQuery")?$("#cronQuery").value:"")}</textarea>`+
       `<select id="cronLevel" class="inp" style="margin-top:8px">${[1,2,3,4,5].map(l=>
         `<option value="${l}"${(($("#cronLevel")?Number($("#cronLevel").value):2))===l?" selected":""}>等级 L${l}</option>`).join("")}</select>`)+
    `<div style="display:flex;gap:8px;margin-top:8px;align-items:center">`+
    `<select id="cronSType" class="inp" style="width:110px">`+
    `<option value="cron"${stype==="cron"?" selected":""}>cron 表达式</option>`+
    `<option value="interval"${stype==="interval"?" selected":""}>固定间隔</option>`+
    `<option value="once"${stype==="once"?" selected":""}>一次性</option></select>`+
    schedFields+`</div>`+
    `<div style="margin-top:8px"><button class="btn primary" id="cronCreate">创建任务</button></div>`+
    `<div id="cronFormMsg" class="mini" style="margin-top:6px"></div>`;
  $("#cronKind").onchange=renderCronForm;
  $("#cronSType").onchange=renderCronForm;
  $("#cronCreate").onclick=createCronTask;
}
async function createCronTask(){
  const kind=$("#cronKind").value;
  const stype=$("#cronSType").value;
  const body={name:$("#cronName").value.trim(),kind,schedule:{type:stype}};
  if(kind==="builtin")body.task=$("#cronBuiltin").value;
  else{body.query=$("#cronQuery").value.trim();body.level=Number($("#cronLevel").value);}
  if(stype==="cron")body.schedule.expr=$("#cronExpr").value.trim();
  else if(stype==="interval"){
    const unit=$("#cronUnit").value;
    body.schedule[unit]=Number($("#cronEvery").value);
  }else{
    const v=$("#cronAt").value;   // datetime-local → ISO 本地时间
    if(!v){cronFormMsg("请选择执行时间","var(--danger)");return;}
    body.schedule.at=new Date(v).toISOString().slice(0,19);
  }
  try{
    const r=await api("/api/agent/cron",{method:"POST",
      headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    const d=await r.json().catch(()=>({}));
    if(!r.ok)throw new Error(d.detail||("HTTP "+r.status));
    await loadAgentCron();
  }catch(e){cronFormMsg("创建失败："+e.message,"var(--danger)");}
}
function cronFormMsg(msg,color){
  const el=$("#cronFormMsg");if(el)el.innerHTML=`<span style="color:${color}">${esc(msg)}</span>`;
}
async function loadCapabilities(){
  const box=$("#capPanel");if(!box)return;
  box.innerHTML='<h3 style="margin:16px 0 0">预留入口（百炼模型）</h3><div class="muted">探测中…</div>';
  try{
    const d=await (await api("/api/capabilities")).json();
    const ST={active:["已开通","var(--ok)"],pending:["占位待开通","var(--warn)"],unavailable:["不可用","var(--danger)"]};
    let h=`<h3 style="margin:16px 0 0">预留入口 · 百炼模型能力</h3>`;
    h+=d.models.map(m=>{const[s,col]=ST[m.status]||["未知","var(--text-dim)"];
      return `<div class="skill"><b>${esc(m.note.split("（")[0])}</b> <span style="color:${col}">· ${s}</span>`+
        `<div class="mini">模型 ${esc(m.model)} · 开关 ${esc(m.env)}`+
        (m.fallback?` · 未开通时降级到 ${esc(m.resolves_to||m.fallback)}`:"")+`</div></div>`;}).join("");
    h+=`<h3 style="margin:16px 0 0">协议层能力（MCP / 审阅 / Ollama）</h3>`;
    h+=d.capabilities.map(c=>{
      let detail="";
      if(c.mcp) detail=`<div class="mini">真实状态：${c.mcp.connected?"已连接":"未连接"} · ${esc(c.mcp.detail)}`+
        (c.mcp.tools&&c.mcp.tools.length?` · 工具 ${c.mcp.tools.length} 个`:"")+`</div>`;
      return `<div class="skill"><b>${esc(c.name)}</b> <span style="color:${c.enabled?"var(--ok)":"var(--warn)"}">· ${c.enabled?"已接入":"未接入（走降级）"}</span>`+
        detail+
        `<div class="mini">接入：${esc(c.how)}</div>`+
        `<div class="mini">未接入时降级：${esc(c.fallback)}（当前：${esc(c.builtin_alt)}）</div>`+
        `<div class="mini">开关：${esc(c.env)}</div></div>`;}).join("");
    box.innerHTML=h;
  }catch(e){box.innerHTML='<div style="color:var(--danger)">能力探测失败：'+esc(e.message)+'</div>';}
}

/* ============ 设置页：插件管理（万物皆插件 · 开关面板） ============
   依赖：util（$/$$/api/esc）。后端：GET /api/plugins + POST /api/plugins/{id} */
async function loadPlugins(){
  const box=$("#pluginPanel");if(!box)return;
  box.innerHTML='<h3 style="margin:16px 0 0">🔌 插件管理</h3><div class="muted">加载中…</div>';
  let d;
  try{
    const r=await api("/api/plugins");
    if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(e.detail||("HTTP "+r.status));}
    d=await r.json();
  }catch(e){
    box.innerHTML='<h3 style="margin:16px 0 0">🔌 插件管理</h3>'+
      `<div style="color:var(--danger)">加载失败：${esc(e.message)}</div>`;
    return;
  }
  const s=d.summary||{};
  const summary=`共 ${s.total??0} 个 · 启用 ${s.enabled??0} · 受 .env 拦截 ${s.env_blocked??0}`;
  box.innerHTML=
    `<h3 style="margin:16px 0 0">🔌 插件管理（万物皆插件）</h3>`+
    `<div class="mini">除 Agent 框架本体外的所有能力都可在此开关。开关 = 用户态 AND .env 部署态；`+
    `.env 关闭的项此处置灰，需改 .env 后重启才能生效。</div>`+
    `<div class="mini" style="margin-top:4px;color:var(--accent)">${summary}</div>`+
    `<div id="pluginList"></div>`;
  renderPluginList(d.plugins||[]);
}
function renderPluginList(plugins){
  const box=$("#pluginList");if(!box)return;
  if(!plugins.length){box.innerHTML='<div class="muted">暂无插件</div>';return;}
  box.innerHTML=plugins.map(p=>{
    const applyBadge=p.apply==="restart"
      ?'<span class="tag" title="改动需重启服务生效">重启生效</span>'
      :'<span class="tag" title="改动即时生效">即时生效</span>';
    let ctrl;
    if(!p.switchable){
      ctrl='<span class="mini" title="框架基础设施入口，当前无独立开关">入口预留</span>';
    }else if(p.env_blocked){
      ctrl=`<span class="mini" style="color:var(--warn)" title="${esc(p.env_gate)} 在 .env 关闭">.env 已关</span>`+
        `<input type="checkbox" class="plugin-switch" data-plugin="${esc(p.id)}" ${p.enabled?"checked":""} disabled>`;
    }else{
      ctrl=`<input type="checkbox" class="plugin-switch" data-plugin="${esc(p.id)}" ${p.enabled?"checked":""}>`;
    }
    return `<div class="skill"><div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">`+
      `<div style="flex:1;min-width:0"><b>${esc(p.name)}</b> <span class="mini">v${esc(p.version)} · ${esc(p.id)}</span> ${applyBadge}`+
      `<div class="mini">${esc(p.description)}</div></div>`+
      `<div style="flex-shrink:0;display:flex;align-items:center;gap:6px">${ctrl}</div></div></div>`;
  }).join("");
  $$("#pluginList input[data-plugin]").forEach(cb=>{
    cb.onchange=async()=>{
      const id=cb.dataset.plugin;
      try{
        const r=await api("/api/plugins/"+encodeURIComponent(id),{method:"POST",
          headers:{"Content-Type":"application/json"},body:JSON.stringify({enabled:cb.checked})});
        const dd=await r.json().catch(()=>({}));
        if(!r.ok)throw new Error(dd.detail||("HTTP "+r.status));
        await loadPlugins();   // 即时刷新（env_blocked 等态可能变化）
        // 带 ui_panels 资产贡献的插件（如图表渲染）：开关后重跑前端资产加载器
        const panels=(dd.plugin&&dd.plugin.contributions&&dd.plugin.contributions.ui_panels)||[];
        if(panels.length&&window.DiagramRender&&window.DiagramRender.refresh){
          window.DiagramRender.refresh();
        }
      }catch(e){alert("开关失败："+e.message);await loadPlugins();}
    };
  });
}

/* ============ 设置页：插件市场（P6 · 本地上传导入） ============
   依赖：util（$/$$/api/esc）。后端：GET /api/market + POST /api/market/upload
   + DELETE /api/market/units/{id}。三类货架（插件/Agent/团队）+ 模板/成品
   双形态；上传 plugin.json 或 zip 包即装即用（无需联网/中心注册表）。 */
async function loadMarket(){
  const box=$("#marketPanel");if(!box)return;
  box.innerHTML='<h3 style="margin:16px 0 0">🛒 插件市场（本地上传导入）</h3><div class="muted">加载中…</div>';
  let d;
  try{
    const r=await api("/api/market");
    if(!r.ok){const e=await r.json().catch(()=>({}));throw new Error(e.detail||("HTTP "+r.status));}
    d=await r.json();
  }catch(e){
    box.innerHTML='<h3 style="margin:16px 0 0">🛒 插件市场（本地上传导入）</h3>'+
      `<div style="color:var(--danger)">加载失败：${esc(e.message)}</div>`;
    return;
  }
  box.innerHTML=
    `<h3 style="margin:16px 0 0">🛒 插件市场（本地上传导入）</h3>`+
    `<div class="mini">三类货架：插件 / Agent / 团队；模板（待定制）与成品（开箱即用）双形态。`+
    `上传 <code>plugin.json</code> 或含该清单的 <code>.zip</code> 包即装即用——`+
    `不联网、无中心注册表。仅「市场安装」的 unit 可卸载，内置与示例不受影响。</div>`+
    `<div class="mini" style="margin-top:4px;color:var(--accent)">平台版本 v${esc(d.platform_version||"?")}</div>`+
    `<div class="card" style="margin-top:10px"><b>上传导入</b>`+
    `<div style="display:flex;gap:8px;margin-top:8px;align-items:center;flex-wrap:wrap">`+
    `<input id="mkFile" class="inp" type="file" accept=".zip,.json" style="flex:1;min-width:220px">`+
    `<button class="btn primary" id="mkUpload">上传并安装</button></div>`+
    `<div id="mkMsg" class="mini" style="margin-top:6px"></div>`+
    `<div class="mini" style="margin-top:4px">安装前校验：清单契约（schema）→ 平台版本（min_platform）→ 依赖（dependencies），任一不过即拒收、不落盘。</div>`+
    `</div>`+
    `<div id="mkShelves"></div>`;
  renderMarketShelves(d.shelves||{});
  $("#mkUpload").onclick=uploadMarketUnit;
  $("#mkFile").onchange=()=>{$("#mkMsg").textContent="";};
}
function renderMarketShelves(shelves){
  const box=$("#mkShelves");if(!box)return;
  const labels={plugin:"🔌 插件",agent:"🤖 Agent",team:"👥 团队"};
  const forms={template:"模板",instance:"成品"};
  let html="";
  for(const type of ["plugin","agent","team"]){
    const list=(shelves&&shelves[type])||[];
    html+=`<h3 style="margin:16px 0 0">${labels[type]}</h3>`;
    if(!list.length){html+='<div class="muted">暂无（上传一个试试）</div>';continue;}
    html+=list.map(u=>{
      const state=!u.registered?"warn":(u.enabled?"on":"off");
      const note=!u.registered?'<span style="color:var(--danger)">未注册（目录残留或坏包，建议卸载重装）</span>'
        :(u.env_blocked?'<span style="color:var(--warn)">.env 部署态已关</span>':"已启用");
      return `<div class="skill"><div style="display:flex;justify-content:space-between;align-items:flex-start;gap:10px">`+
        `<div style="flex:1;min-width:0"><b>${esc(u.name||u.id)}</b> `+
        `<span class="mini">v${esc(u.version||"?")} · ${esc(u.id)}</span> `+
        `<span class="tag">${esc(forms[u.form]||u.form||"成品")}</span>`+
        `<div class="mini">${note}${u.source?` · 来源 ${esc(u.source)}`:""}</div></div>`+
        `<div style="flex-shrink:0"><button class="btn" data-mk-uninstall="${esc(u.id)}">卸载</button></div>`+
        `</div></div>`;
    }).join("");
  }
  box.innerHTML=html;
  $$("#mkShelves button[data-mk-uninstall]").forEach(btn=>{
    btn.onclick=()=>uninstallMarketUnit(btn.dataset.mkUninstall);
  });
}
async function uploadMarketUnit(){
  const input=$("#mkFile");const msg=$("#mkMsg");
  const f=input&&input.files&&input.files[0];
  if(!f){msg.innerHTML='<span style="color:var(--warn)">先选择 .zip 或 .json 文件</span>';return;}
  msg.textContent="上传安装中…";
  try{
    const fd=new FormData();fd.append("file",f);
    const r=await api("/api/market/upload",{method:"POST",body:fd});
    const d=await r.json().catch(()=>({}));
    if(!r.ok)throw new Error(d.detail||("HTTP "+r.status));
    msg.innerHTML=`<span style="color:var(--ok)">已安装：${esc(d.installed.name||d.installed.id)}`+
      `（${esc(d.installed.type)} · ${esc(d.installed.form==="template"?"模板":"成品")} · v${esc(d.installed.version)}）</span>`;
    input.value="";
    await loadMarket();   // 刷新货架（含启用态/部署态）
  }catch(e){
    msg.innerHTML='<span style="color:var(--danger)">安装失败：'+esc(e.message)+'</span>';
  }
}
async function uninstallMarketUnit(id){
  const msg=$("#mkMsg");
  if(!confirm(`确定卸载「${id}」？\n仅市场安装的 unit 可卸载；卸载后其工具/规约立即不可用。`))return;
  msg.textContent="卸载中…";
  try{
    const r=await api("/api/market/units/"+encodeURIComponent(id),{method:"DELETE"});
    const d=await r.json().catch(()=>({}));
    if(!r.ok)throw new Error(d.detail||("HTTP "+r.status));
    msg.innerHTML='<span style="color:var(--ok)">已卸载 '+esc(id)+'</span>';
    await loadMarket();
  }catch(e){
    msg.innerHTML='<span style="color:var(--danger)">卸载失败：'+esc(e.message)+'</span>';
  }
}
