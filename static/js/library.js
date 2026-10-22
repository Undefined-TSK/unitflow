/* ============ 知识库页 + 离线文档导入 ============
   依赖：util（$/api/esc/CONFIG） */
const ROLE_N={main:"主要源",supplement_a:"补充A",supplement_b:"补充B"};
const KIND_N={url:"网址",github:"GitHub",offline:"离线",builtin:"内置"};
async function loadLibrary(){
  const box=$("#libList"),st=$("#libStats");
  box.innerHTML='<div class="muted">加载中…</div>';
  try{
    const d=await (await api("/api/sources")).json();
    st.innerHTML=`<span class="tag">资料源 ${d.stats.source_count}</span><span class="tag">向量块 ${d.stats.vector_count}</span>`+
      (d.stats.by_role?Object.entries(d.stats.by_role).map(([k,v])=>`<span class="tag">${ROLE_N[k]||k} ${v}</span>`).join(""):"")+
      `<span class="tag">联网抓取 ${CONFIG.web_fetch?"开":"关"}</span>`;
    box.innerHTML=d.sources.length? d.sources.map(s=>`
      <div class="src-item"><span class="tag">${KIND_N[s.kind]||s.kind}</span>
      <div class="grow"><b>${esc(s.title||s.target||s.id)}</b>
      <div class="mini">${ROLE_N[s.role]||s.role} · ${s.status} · ${s.chunk_count||0} 块${s.note?` · ${esc(s.note)}`:""}</div></div>
      <button class="btn ghost sm" data-del="${s.id}">删除</button></div>`).join("")
      :'<div class="muted">还没有资料源，导入一个试试。</div>';
    $$("#libList [data-del]").forEach(b=>b.onclick=async()=>{
      if(!confirm("删除该资料源及其向量块？"))return;
      await api("/api/sources/"+b.dataset.del,{method:"DELETE"});loadLibrary();});
  }catch(e){box.innerHTML='<div style="color:var(--danger)">加载失败：'+esc(e.message)+'</div>';}
}
async function ingest(kind){
  const btn=kind==="url"?$("#libAddUrl"):$("#libAddGh");
  const old=btn.textContent;btn.disabled=true;btn.textContent="导入中…";
  try{
    let r;
    if(kind==="url"){const u=$("#libUrl").value.trim();if(!u)throw new Error("请输入网址");
      r=await api("/api/sources/url",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({url:u,role:$("#libUrlRole").value,max_pages:6})});}
    else{const g=$("#libRepo").value.trim();if(!g)throw new Error("请输入仓库");
      r=await api("/api/sources/github",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({repo:g,role:"supplement_a"})});}
    const d=await r.json();if(!r.ok)throw new Error(d.detail||"导入失败");
    alert(`导入${d.status==="indexed"?"成功":"暂不可用"}：${d.status}，${d.chunks||0} 个分块${d.note?" · "+d.note:""}`);
    loadLibrary();
  }catch(e){alert("导入失败："+e.message);}
  finally{btn.disabled=false;btn.textContent=old;}
}
$("#libAddUrl").onclick=()=>ingest("url");
$("#libAddGh").onclick=()=>ingest("github");

/* —— 预置权威资料源：一键导入（幂等；未开联网时给可操作提示而非静默失败） —— */
$("#libAddPreset").onclick=async()=>{
  const btn=$("#libAddPreset"),msg=$("#presetMsg");
  const old=btn.textContent;btn.disabled=true;btn.textContent="导入中…";
  msg.textContent="正在抓取官方文档 / 仓库 / 论坛，首次较慢…";
  try{
    const r=await api("/api/sources/preset",{method:"POST"});
    const d=await r.json();
    if(!r.ok)throw new Error(d.detail||"导入失败");
    if(d.disabled){
      msg.innerHTML='<span style="color:var(--warn)">'+
        esc(d.note||"预置资料源已关闭（PRESET_SOURCES_ENABLE=false）")+'</span>';
    }else{
      msg.innerHTML=`<span style="color:var(--ok)">清单 ${d.total} 项：入库 ${d.added} · 跳过 ${d.skipped} · 未成功 ${d.failed}</span>`;
      loadLibrary();
    }
  }catch(e){msg.innerHTML='<span style="color:var(--danger)">导入失败：'+esc(e.message)+'</span>';}
  finally{btn.disabled=false;btn.textContent=old;}
};

/* —— 离线文档（前端预检大小，避免无效上传） —— */
$("#docUpload").onclick=async()=>{
  const f=$("#docFile").files[0];if(!f){alert("先选择一个文件");return;}
  const limitMb=(CONFIG.config&&CONFIG.config.upload_limit_mb)||50;
  if(f.size>limitMb*1024*1024){
    $("#docResult").innerHTML=`<span style="color:var(--danger)">文件 ${(f.size/1048576).toFixed(1)}MB 超过上限 ${limitMb}MB，已拒绝</span>`;
    return;
  }
  const fd=new FormData();fd.append("file",f);fd.append("role",$("#docRole").value);
  $("#docUpload").disabled=true;$("#docResult").textContent="解析并入库中…";
  try{
    const r=await api("/api/sources/upload",{method:"POST",body:fd});
    const d=await r.json();if(!r.ok)throw new Error(d.detail||"上传失败");
    $("#docResult").innerHTML=`<span style="color:var(--ok)">已入库：${esc(d.status)}，${d.chunks||0} 个分块</span>`;
  }catch(e){$("#docResult").innerHTML='<span style="color:var(--danger)">失败：'+esc(e.message)+'</span>';}
  finally{$("#docUpload").disabled=false;}
};
