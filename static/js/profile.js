/* ============ 我的画像页 ============
   依赖：util（$/api/esc/SID） */
let _memItems=[];  // 记忆 id 映射，供删除定位
async function loadProfile(){
  const b=$("#profBody");b.innerHTML='<div class="muted">加载中…</div>';
  try{
    const d=await (await api("/api/profile"+(SID?("?session_id="+SID):""))).json();
    _memItems=d.memory_items||[];
    let h=`<div class="card"><h2 style="margin-top:0">我的画像</h2>`+
      `<div class="kv"><span>Python 水平</span><span>${d.level?("L"+d.level):"未知"}</span></div>`+
      `<div class="kv"><span>累计交互</span><span>${d.interactions} 次</span></div>`+
      `<div class="kv"><span>长期记忆</span><span>${_memItems.length} 条</span></div></div>`;
    if(d.pain_points&&d.pain_points.length){
      h+=`<div class="card"><h3 style="margin-top:0">曾经的卡点</h3>`+d.pain_points.map(p=>
        `<div class="refl">${esc(p.q)} <span class="mini">（当时置信度 ${p.conf}）</span></div>`).join("")+`</div>`;
    }
    if(_memItems&&_memItems.length){
      h+=`<div class="card"><div style="display:flex;align-items:center;gap:10px">`+
        `<h3 style="margin-top:0;flex:1">长期记忆（可单条删除 / 导出）</h3>`+
        `<button class="btn ghost sm" id="memExport">导出记忆</button></div>`+
        _memItems.map((m,i)=>`<div class="mem-row" data-i="${i}">`+
          `<span class="grow">${esc(m.text)}</span>`+
          `<button class="btn ghost sm mem-del" data-id="${esc(m.id)}">删除</button></div>`).join("")+`</div>`;
    }
    if(d.session){
      h+=`<div class="card"><h3 style="margin-top:0">当前会话画像（${d.session.turns} 轮）</h3>`;
      if(d.session.topics&&d.session.topics.length)
        h+=`<div class="kv"><span>常问主题</span><span>${d.session.topics.map(t=>
          `<span class="tag">${esc(t.topic)} ×${t.count}</span>`).join("")}</span></div>`;
      if(d.session.weak_spots&&Object.keys(d.session.weak_spots).length)
        h+=`<div class="kv"><span>卡点标记</span><span>${Object.entries(d.session.weak_spots).map(([k,v])=>
          `<span class="tag">${esc(k)} ×${v}</span>`).join("")}</span></div>`;
      if(d.session.prefers&&d.session.prefers.length)
        h+=`<div class="kv"><span>偏好记录</span><span>${d.session.prefers.map(p=>
          `<span class="tag">${esc(p)}</span>`).join("")}</span></div>`;
      h+=`</div>`;
    }
    b.innerHTML=h;
    $$("#memExport",b).forEach(x=>x.onclick=exportMemories);
    $$(".mem-del",b).forEach(x=>x.onclick=()=>deleteMemory(x.dataset.id));
  }catch(e){b.innerHTML='<div style="color:var(--danger)">加载失败：'+esc(e.message)+'</div>';}
}

async function deleteMemory(id){
  if(!confirm("确定删除这条记忆？"))return;
  try{
    const r=await api("/api/memory/"+encodeURIComponent(id),{method:"DELETE"});
    if(!r.ok)throw new Error((await r.json()).detail||"删除失败");
    loadProfile();  // 回执成功后刷新画像
  }catch(e){alert("删除失败："+e.message);}
}

async function exportMemories(){
  try{
    const d=await (await api("/api/memory/export")).json();
    const blob=new Blob([JSON.stringify(d.items,null,2)],{type:"application/json;charset=utf-8"});
    const url=URL.createObjectURL(blob);const a=document.createElement("a");
    a.href=url;a.download="pypedia-记忆.json";a.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }catch(e){alert("导出失败："+e.message);}
}
