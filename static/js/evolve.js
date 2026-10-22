/* ============ 自进化页 + 能力进化页 ============
   依赖：util（$/api/esc/LEVEL） */
/* 自进化插件被关闭时（设置 → 插件管理）的统一提示 */
const EVO_OFF_HTML='<div class="muted">自进化插件已在设置中关闭——到「设置 → 插件管理」重新开启后，这里会继续积累技能与反思。</div>';
/* —— 自进化 —— */
async function loadEvolve(){
  const b=$("#evoBody");b.innerHTML='<div class="muted">加载中…</div>';
  try{
    const r=await api("/api/evolution");
    if(r.status===503){b.innerHTML=EVO_OFF_HTML;return;}
    const d=await r.json();
    let h=`<h3 style="margin:12px 0 0">已沉淀技能（${d.skills.length}）</h3>`;
    h+=d.skills.length? d.skills.map(s=>`<div class="skill"><b>${esc(s.name)}</b> · 当「${esc(s.trigger)}」时，${esc(s.action)}</div>`).join("")
      :'<div class="muted">还没有技能，多问几个问题或提交反馈后会自动沉淀。</div>';
    h+=`<h3 style="margin:16px 0 0">最近反思（${d.reflections.length}）</h3>`;
    h+=d.reflections.length? d.reflections.map(r=>`<div class="refl">${esc(r.note)} <span class="mini">${r.ts||""}</span></div>`).join("")
      :'<div class="muted">暂无反思记录。</div>';
    b.innerHTML=h;
  }catch(e){b.innerHTML='<div style="color:var(--danger)">加载失败：'+esc(e.message)+'</div>';}
}
$("#fbSend").onclick=async()=>{
  const q=$("#fbQuery").value.trim(),iss=$("#fbIssue").value.trim();
  if(!iss){alert("说说哪里没答好");return;}
  $("#fbSend").disabled=true;
  try{
    const r=await api("/api/evolution/feedback",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({query:q,issue:iss,level:LEVEL})});
    const d=await r.json();
    if(r.status===503)throw new Error("自进化插件已在设置中关闭，请到「设置 → 插件管理」开启");
    if(!r.ok)throw new Error(d.detail||"提交失败");
    $("#fbResult").innerHTML='<span style="color:var(--ok)">已沉淀成技能，谢谢！下次遇到同类问题会自动改进。</span>';
    $("#fbIssue").value="";$("#fbQuery").value="";loadEvolve();
  }catch(e){$("#fbResult").innerHTML='<span style="color:var(--danger)">'+esc(e.message)+'</span>';}
  finally{$("#fbSend").disabled=false;}
};

/* —— 能力进化（原微调训练页） —— */
async function loadTrain(){
  const b=$("#trainBody");b.innerHTML='<div class="muted">加载中…</div>';
  try{
    const r=await api("/api/evolution");
    if(r.status===503){b.innerHTML=EVO_OFF_HTML;return;}
    const d=await r.json();
    let h=`<div class="kv"><span>模型权重</span><span>冻结（不微调）</span></div>`+
      `<div class="kv"><span>专属技能</span><span>${d.skills.length} 条</span></div>`+
      `<div class="kv"><span>反思记录</span><span>${d.reflections.length} 条</span></div>`;
    if(d.skills.length){
      h+=`<h3 style="margin:14px 0 0">已注入系统提示词的技能</h3>`+
        d.skills.map(s=>`<div class="skill"><b>${esc(s.name)}</b>：${esc(s.action)}</div>`).join("");
    }
    b.innerHTML=h;
  }catch(e){b.innerHTML='<div style="color:var(--danger)">加载失败：'+esc(e.message)+'</div>';}
}
