/* ============ 节点编辑器（P7 · 图即引擎的编排创作面） ============
   零依赖 SVG 画布：节点拖拽 / 点击连线 / 属性编辑 / 校验 / 导出 / 安装。
   后端：GET /api/editor/templates · POST /api/editor/validate
        POST /api/editor/export（zip 下载）· POST /api/editor/install（直装）
   依赖：util（$/$$/api/esc）。 */
const ED_W=1200, ED_H=760;
const ED_TYPE_META={
  "entry":      {label:"入口",     color:"#4ade80", hint:"注入初始 payload"},
  "exit":       {label:"出口",     color:"#f87171", hint:"捕获结果并终止"},
  "process":    {label:"处理",     color:"#60a5fa", hint:"params.expr 表达式或 ref 处理器"},
  "plugin":     {label:"插件",     color:"#c084fc", hint:"params.ref=unit id，method 选工具"},
  "model-call": {label:"模型调用", color:"#fbbf24", hint:"调用 LLM（identity 选人格）"},
  "judge":      {label:"判断",     color:"#fb923c", hint:"按出边 condition 选分支"}
};
const ED={nodes:[],edges:[],sel:null,selEdge:null,seq:1,drag:null,linking:null,dirty:false};

function edEsc(s){return esc(s);}

/* ---------- 序列化：画布态 → node_graph（后端契约） ---------- */
/* 保留节点级键（如规范约定的 ref），只剥画布坐标 x/y——
   直接从模板加载的节点不落 params.ref 也不能丢节点级 ref。 */
function edToGraph(){
  return {
    nodes:ED.nodes.map(n=>{
      const c={...n};delete c.x;delete c.y;
      if(c.params&&Object.keys(c.params).length===0)delete c.params;
      return c;
    }),
    edges:ED.edges.map(e=>{const o={from:e.from,to:e.to};if(e.condition)o.condition=e.condition;return o;})
  };
}
function edFromGraph(g){
  /* 编辑器内部统一用 params.ref；加载时把规范形状（节点级 ref）并入，
     导出时后端 _normalize_graph 再提升回节点级——往返无损。 */
  ED.nodes=(g.nodes||[]).map(n=>{
    const c={...n,params:{...(n.params||{})},x:n.x??80+Math.random()*400,y:n.y??60+Math.random()*400};
    if(n.ref&&!c.params.ref)c.params.ref=n.ref;
    delete c.ref;
    return c;
  });
  ED.edges=(g.edges||[]).map(e=>({...e}));
  ED.sel=null;ED.selEdge=null;ED.dirty=false;
  edRender();
}

/* ---------- 画布渲染 ---------- */
function edRender(){
  const svg=$("#edSvg");if(!svg)return;
  let h="";
  // 网格背景
  h+=`<defs><pattern id="edGrid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M 24 0 L 0 0 0 24" fill="none" stroke="rgba(148,163,184,.12)" stroke-width="1"/></pattern>`+
     `<marker id="edArrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 5 z" fill="#94a3b8"/></marker></defs>`;
  h+=`<rect width="${ED_W}" height="${ED_H}" fill="url(#edGrid)"/>`;
  // 边
  for(const e of ED.edges){
    const a=ED.nodes.find(n=>n.id===e.from),b=ED.nodes.find(n=>n.id===e.to);
    if(!a||!b)continue;
    const x1=a.x+150,y1=a.y+34,x2=b.x,y2=b.y+34;
    const mx=(x1+x2)/2;
    const d=`M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`;
    const on=ED.selEdge===e;
    h+=`<path d="${d}" fill="none" stroke="${on?"var(--accent)":"#64748b"}" stroke-width="${on?2.5:1.6}" marker-end="url(#edArrow)" class="ed-edge" data-from="${edEsc(e.from)}" data-to="${edEsc(e.to)}" style="cursor:pointer"/>`;
    if(e.condition){
      h+=`<text x="${mx}" y="${(y1+y2)/2-6}" text-anchor="middle" font-size="11" fill="#fbbf24" style="pointer-events:none">${edEsc(String(e.condition).slice(0,28))}</text>`;
    }
  }
  // 连线预览
  if(ED.linking&&ED.linking.id){
    const a=ED.nodes.find(n=>n.id===ED.linking.id);
    if(a)h+=`<line x1="${a.x+150}" y1="${a.y+34}" x2="${ED.linking.x}" y2="${ED.linking.y}" stroke="var(--accent)" stroke-width="2" stroke-dasharray="6 4"/>`;
  }
  // 节点
  for(const n of ED.nodes){
    const m=ED_TYPE_META[n.type]||{label:n.type,color:"#94a3b8"};
    const on=ED.sel===n.id;
    const px=n.x,py=n.y;
    h+=`<g class="ed-node" data-id="${edEsc(n.id)}" style="cursor:grab">`+
       `<rect x="${px}" y="${py}" width="150" height="68" rx="10" fill="${on?"rgba(56,189,248,.14)":"var(--panel2)"}" stroke="${on?"var(--accent)":m.color}" stroke-width="${on?2.4:1.4}"/>`+
       `<circle cx="${px+14}" cy="${py+16}" r="5" fill="${m.color}"/>`+
       `<text x="${px+26}" y="${py+20}" font-size="12.5" font-weight="600" fill="var(--text)">${edEsc(m.label)}</text>`+
       `<text x="${px+14}" y="${py+40}" font-size="11.5" fill="var(--muted)">${edEsc(n.id)}</text>`+
       `<text x="${px+14}" y="${py+56}" font-size="10.5" fill="var(--muted)">${edEsc(edNodeSummary(n))}</text>`+
       (n.type==="judge"||true?`<circle cx="${px+150}" cy="${py+34}" r="7" fill="var(--accent)" class="ed-linkdot" data-id="${edEsc(n.id)}" style="cursor:crosshair" title="拖到目标节点连线"><title>连线</title></circle>`:"")+
       `</g>`;
  }
  svg.innerHTML=h;
  // 事件：节点拖拽 / 选中 / 连线
  $$("#edSvg .ed-node").forEach(g=>{
    const id=g.dataset.id;
    g.addEventListener("mousedown",ev=>{
      if(ev.target.classList.contains("ed-linkdot"))return;
      ev.preventDefault();
      ED.drag={id,dx:ev.clientX,dy:ev.clientY,moved:false};
    });
    g.addEventListener("click",ev=>{
      if(ev.target.classList.contains("ed-linkdot"))return;
      if(ED.drag&&ED.drag.moved)return;
      if(ED.linking){edFinishLink(id);return;}
      edSelectNode(id);
    });
  });
  $$("#edSvg .ed-linkdot").forEach(dot=>{
    dot.addEventListener("mousedown",ev=>{
      ev.preventDefault();ev.stopPropagation();
      const fromId=dot.dataset.id;
      ED.linking={id:fromId};
      const onMove=e2=>{ED.linking={id:fromId,x:e2.clientX,y:e2.clientY};edRender();};
      /* mouseup 即完成连线：mousedown/mouseup 目标不同时 click 只会派发到
         公共祖先（svg），等 click 建边永远等不到——这里用 elementFromPoint
         直接判定落点节点。 */
      const onUp=e2=>{
        document.removeEventListener("mousemove",onMove);
        document.removeEventListener("mouseup",onUp);
        const el=document.elementFromPoint(e2.clientX,e2.clientY);
        const g=el&&el.closest?el.closest(".ed-node"):null;
        const toId=g?g.dataset.id:null;
        ED.linking=null;
        if(toId&&toId!==fromId&&!ED.edges.some(e=>e.from===fromId&&e.to===toId)){
          ED.edges.push({from:fromId,to:toId});ED.dirty=true;
        }
        edRender();
      };
      document.addEventListener("mousemove",onMove);
      document.addEventListener("mouseup",onUp);
    });
  });
  $$("#edSvg .ed-edge").forEach(p=>{
    p.addEventListener("click",()=>edSelectEdge(p.dataset.from,p.dataset.to));
  });
  edRenderInspector();
}
function edNodeSummary(n){
  const p=n.params||{};
  const ref=n.ref||p.ref;  // 双位置：节点级（规范）或 params（画布直出）
  if(ref&&p.method)return ref+"."+p.method;
  if(ref)return "→ "+ref;
  if(p.expr)return String(p.expr).slice(0,30);
  if(p.identity)return "identity "+p.identity;
  return ED_TYPE_META[n.type]?ED_TYPE_META[n.type].hint.slice(0,26):"";
}

/* ---------- 交互：增删连选 ---------- */
function edAddNode(type){
  const n={id:type[0]+ED.seq++,type,x:120+((ED.seq*97)%700),y:80+((ED.seq*61)%520),params:{}};
  ED.nodes.push(n);ED.dirty=true;edSelectNode(n.id);edRender();
}
function edFinishLink(toId){
  const from=ED.linking&&ED.linking.id?ED.linking.id:ED.linking;
  ED.linking=null;
  if(from&&from!==toId){
    if(!ED.edges.some(e=>e.from===from&&e.to===toId)){
      ED.edges.push({from,to:toId});ED.dirty=true;
    }
  }
  edRender();
}
function edSelectNode(id){ED.sel=id;ED.selEdge=null;edRender();}
function edSelectEdge(from,to){
  ED.selEdge=ED.edges.find(e=>e.from===from&&e.to===to)||null;
  ED.sel=null;edRender();
}
function edDeleteSelected(){
  if(ED.selEdge){
    ED.edges=ED.edges.filter(e=>e!==ED.selEdge);ED.selEdge=null;
  }else if(ED.sel){
    ED.nodes=ED.nodes.filter(n=>n.id!==ED.sel);
    ED.edges=ED.edges.filter(e=>e.from!==ED.sel&&e.to!==ED.sel);
    ED.sel=null;
  }
  ED.dirty=true;edRender();
}

/* ---------- 右栏：属性检查器 ---------- */
function edRenderInspector(){
  const box=$("#edInspector");if(!box)return;
  const n=ED.nodes.find(x=>x.id===ED.sel);
  const e=ED.selEdge;
  if(!n&&!e){box.innerHTML='<div class="muted">选中节点或连线编辑属性；从左侧托盘添加节点。</div>';return;}
  if(e){
    box.innerHTML=`<b>连线</b> <span class="mini">${edEsc(e.from)} → ${edEsc(e.to)}</span>`+
      `<div class="mini" style="margin-top:8px">condition（judge 分支条件；留空=顺序边/兜底边）</div>`+
      `<input id="edCond" class="inp" style="width:100%" placeholder="(data.get('k') or {}).get('needs_review', False)" value="${edEsc(e.condition||"")}">`+
      `<div style="display:flex;gap:8px;margin-top:8px"><button class="btn" id="edCondSave">保存条件</button>`+
      `<button class="btn" id="edDel" style="color:var(--danger)">删除连线</button></div>`;
    $("#edCondSave").onclick=()=>{e.condition=$("#edCond").value.trim();ED.dirty=true;edRender();};
    $("#edDel").onclick=edDeleteSelected;
    return;
  }
  const m=ED_TYPE_META[n.type]||{label:n.type};
  let fields="";
  if(n.type==="process"){
    fields=`<div class="mini" style="margin-top:8px">expr（表达式，可用 payload/data）</div>`+
      `<textarea id="edExpr" class="inp" style="width:100%;height:64px" placeholder="{'echo': payload}">${edEsc(n.params.expr||"")}</textarea>`+
      `<div class="mini" style="margin-top:6px">或引用 unit 处理器：ref</div>`+
      `<input id="edRef" class="inp" style="width:100%" placeholder="unit id" value="${edEsc(n.params.ref||"")}">`+
      `<input id="edMethod" class="inp" style="width:100%;margin-top:6px" placeholder="method（可选）" value="${edEsc(n.params.method||"")}">`;
  }else if(n.type==="plugin"){
    fields=`<div class="mini" style="margin-top:8px">ref（引用的 unit id，必填）</div>`+
      `<input id="edRef" class="inp" style="width:100%" placeholder="如 python-encyclopedia" value="${edEsc(n.params.ref||"")}">`+
      `<div class="mini" style="margin-top:6px">method（该 unit 的工具名，可选）</div>`+
      `<input id="edMethod" class="inp" style="width:100%" placeholder="retrieve" value="${edEsc(n.params.method||"")}">`;
  }else if(n.type==="model-call"){
    fields=`<div class="mini" style="margin-top:8px">identity（人格标识，可选）</div>`+
      `<input id="edIdentity" class="inp" style="width:100%" placeholder="①" value="${edEsc(n.params.identity||"")}">`;
  }else{
    fields=`<div class="mini" style="margin-top:8px">${edEsc(m.hint||"该类型无可编辑参数")}</div>`;
  }
  box.innerHTML=`<b>${edEsc(m.label)}</b> <span class="mini">${edEsc(n.id)}</span>${fields}`+
    `<div style="display:flex;gap:8px;margin-top:10px"><button class="btn primary" id="edSave">保存参数</button>`+
    `<button class="btn" id="edDel" style="color:var(--danger)">删除节点</button></div>`;
  const save=()=>{
    const p=n.params;
    if(n.type==="process"){
      p.expr=($("#edExpr")?.value||"").trim();
      p.ref=($("#edRef")?.value||"").trim();
      p.method=($("#edMethod")?.value||"").trim();
      if(!p.expr)delete p.expr;
      if(!p.ref)delete p.ref;
      if(!p.method)delete p.method;
    }else if(n.type==="plugin"){
      p.ref=($("#edRef")?.value||"").trim();
      p.method=($("#edMethod")?.value||"").trim();
      if(!p.method)delete p.method;
    }else if(n.type==="model-call"){
      p.identity=($("#edIdentity")?.value||"").trim();
      if(!p.identity)delete p.identity;
    }
    ED.dirty=true;edRender();
  };
  if($("#edSave"))$("#edSave").onclick=save;
  $("#edDel").onclick=edDeleteSelected;
}

/* ---------- 顶栏动作 ---------- */
async function edLoadTemplate(which){
  const d=await (await api("/api/editor/templates")).json();
  const g=which==="encyclopedia"?d.encyclopedia:d.minimal;
  if(!g){alert("模板不可用（python-encyclopedia 未注册）");return;}
  edFromGraph(g);
  edMsg(`已加载模板：${which==="encyclopedia"?"单 Agent 成品（13 节点）":"最小可运行链"}`,true);
}
function edNew(){
  ED.nodes=[];ED.edges=[];ED.sel=null;ED.selEdge=null;ED.seq=1;ED.dirty=false;
  edRender();edMsg("新画布（从左侧托盘添加节点）",true);
}
async function edValidate(){
  const r=await api("/api/editor/validate",{method:"POST",
    headers:{"Content-Type":"application/json"},body:JSON.stringify({graph:edToGraph()})});
  const d=await r.json().catch(()=>({errors:["响应解析失败"]}));
  if(d.ok){edMsg("校验通过：图结构合法，可导出/安装。",true);}
  else{edMsg("校验未通过：<br>"+(d.errors||[]).map(e=>"· "+edEsc(e)).join("<br>"),false);}
}
async function edExport(){
  const meta=edMeta();
  if(!meta)return;
  const r=await api("/api/editor/export",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({graph:edToGraph(),meta})});
  if(!r.ok){const d=await r.json().catch(()=>({}));
    edMsg("导出失败："+edEsc(d.detail||("HTTP "+r.status)),false);return;}
  const blob=await r.blob();
  const a=document.createElement("a");
  a.href=URL.createObjectURL(blob);
  a.download=(meta.id||"unit")+".zip";a.click();
  URL.revokeObjectURL(a.href);
  edMsg(`已导出 ${edEsc(meta.id)}.zip（与市场上传同格式，可分享/再上传）`,true);
}
async function edInstall(){
  const meta=edMeta();
  if(!meta)return;
  const r=await api("/api/editor/install",{method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({graph:edToGraph(),meta})});
  const d=await r.json().catch(()=>({}));
  if(r.ok){edMsg(`已安装为可运行 unit：${edEsc(d.installed.name||d.installed.id)}`+
    `（${edEsc(d.installed.type)} · v${edEsc(d.installed.version)}）——「单元」页可见，重启后自动恢复`,true);}
  else{edMsg("安装失败："+edEsc(d.detail||("HTTP "+r.status)),false);}
}
function edMeta(){
  const id=($("#edMetaId")?.value||"").trim();
  const name=($("#edMetaName")?.value||"").trim();
  const type=$("#edMetaType")?.value||"agent";
  if(!id){edMsg("请先填 unit id（安装/导出的主键）",false);$("#edMetaId")?.focus();return null;}
  if(!/^[a-z0-9][a-z0-9-]*$/.test(id)){
    edMsg("unit id 只能用小写字母/数字/连字符（如 my-agent）",false);return null;}
  return {id,name:name||id,type,form:$("#edMetaForm")?.value||"instance"};
}
function edMsg(html,ok){
  const m=$("#edMsg");if(!m)return;
  m.innerHTML=ok?`<span style="color:var(--ok)">${html}</span>`
    :`<span style="color:var(--danger)">${html}</span>`;
}

/* ---------- 页面装载 ---------- */
async function loadEditor(){
  const page=$("#p-editor");if(!page)return;
  if(page.dataset.built){edRender();return;}
  page.dataset.built="1";
  page.innerHTML=`
    <div class="card" style="margin-bottom:10px">
      <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center">
        <b style="font-size:15px">🧩 节点编辑器</b>
        <span class="mini">画一张图 → 导出 / 安装为可运行 unit（图即引擎）</span>
        <span style="flex:1"></span>
        <button class="btn" id="edNew2">新建</button>
        <button class="btn" id="edTplMin">模板：最小链</button>
        <button class="btn" id="edTplEnc">模板：单 Agent</button>
        <button class="btn primary" id="edValidate2">校验</button>
        <button class="btn" id="edExport2">导出 zip</button>
        <button class="btn" id="edInstall2">安装为 unit</button>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:10px">
        <span class="mini">unit id</span><input id="edMetaId" class="inp" style="width:170px" placeholder="my-agent">
        <span class="mini">名称</span><input id="edMetaName" class="inp" style="width:150px" placeholder="我的图">
        <span class="mini">类型</span><select id="edMetaType" style="max-width:110px"><option value="agent">agent</option><option value="plugin">plugin</option><option value="team">team</option></select>
        <span class="mini">形态</span><select id="edMetaForm" style="max-width:110px"><option value="instance">成品</option><option value="template">模板</option></select>
        <span class="mini" style="margin-left:8px">连线：点节点右侧圆点 → 点目标节点；Delete 删除选中</span>
      </div>
      <div id="edMsg" class="mini" style="margin-top:8px"></div>
    </div>
    <div style="display:grid;grid-template-columns:150px 1fr 300px;gap:10px;align-items:start">
      <div class="card" style="padding:10px;margin:0"><b class="mini">节点托盘</b><div id="edTray" style="margin-top:8px"></div></div>
      <div class="card" style="padding:6px;overflow:hidden;margin:0;width:100%"><svg id="edSvg" width="100%" viewBox="0 0 ${ED_W} ${ED_H}" style="display:block;background:var(--panel2);border-radius:8px"></svg></div>
      <div class="card" style="padding:12px;margin:0"><b class="mini">属性</b><div id="edInspector" style="margin-top:8px"></div></div>
    </div>`;
  // 托盘
  const tray=$("#edTray");
  for(const t of ["entry","exit","process","plugin","model-call","judge"]){
    const m=ED_TYPE_META[t];
    const b=document.createElement("button");
    b.className="btn";b.style.cssText="display:block;width:100%;margin-bottom:6px;text-align:left;border-left:3px solid "+m.color;
    b.innerHTML=`<b>${m.label}</b><div class="mini" style="white-space:normal">${m.hint}</div>`;
    b.title=m.hint;
    b.onclick=()=>edAddNode(t);
    tray.appendChild(b);
  }
  // 顶栏按钮
  $("#edNew2").onclick=edNew;
  $("#edTplMin").onclick=()=>edLoadTemplate("minimal");
  $("#edTplEnc").onclick=()=>edLoadTemplate("encyclopedia");
  $("#edValidate2").onclick=edValidate;
  $("#edExport2").onclick=edExport;
  $("#edInstall2").onclick=edInstall;
  // 节点拖拽（SVG 逻辑坐标换算）
  const svg=$("#edSvg");
  document.addEventListener("mousemove",ev=>{
    if(!ED.drag)return;
    const pt=svg.createSVGPoint();pt.x=ev.clientX;pt.y=ev.clientY;
    const loc=pt.matrixTransform(svg.getScreenCTM().inverse());
    const n=ED.nodes.find(x=>x.id===ED.drag.id);
    if(!n)return;
    if(Math.abs(ev.clientX-ED.drag.dx)>3||Math.abs(ev.clientY-ED.drag.dy)>3)ED.drag.moved=true;
    n.x=Math.max(0,Math.min(ED_W-160,loc.x-75));
    n.y=Math.max(0,Math.min(ED_H-80,loc.y-34));
    edRender();
  });
  document.addEventListener("mouseup",()=>{if(ED.drag){setTimeout(()=>ED.drag=null,0);}});
  document.addEventListener("keydown",ev=>{
    if(!$("#p-editor").classList.contains("on"))return;
    if((ev.key==="Delete"||ev.key==="Backspace")&&(ED.sel||ED.selEdge)&&
       !["INPUT","TEXTAREA","SELECT"].includes(document.activeElement?.tagName)){
      ev.preventDefault();edDeleteSelected();
    }
  });
  edNew();
}
