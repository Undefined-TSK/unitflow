/* ============ 问答页 + 检索过程面板 ============
   依赖：util（$/api/LEVEL/BUSY）、md（md/revealMarkdown） */
const qInput=$("#qInput"),qSend=$("#qSend");
function setBusy(b){BUSY=b;qSend.disabled=b;qInput.disabled=b;}
qInput.oninput=()=>qSend.disabled=!qInput.value.trim()||BUSY;
qInput.onkeydown=e=>{if(e.key==="Enter"&&!qSend.disabled)send();};
qSend.onclick=send;

function addMsg(role,html,meta){
  const m=document.createElement("div");m.className="msg "+role;
  m.innerHTML=`<div class="av">${role==="user"?"你":"P"}</div><div class="bubble">${meta?`<div class="meta">${meta}</div>`:""}${html}</div>`;
  $("#msgs").appendChild(m);$("#msgs").scrollTop=$("#msgs").scrollHeight;return m;
}

async function send(){
  const q=qInput.value.trim();if(!q||BUSY)return;
  // 「🧰 沙箱验证」勾选：转 AI 工具循环（function calling，见 agent.js）
  const agentOn=$("#qAgent")&&$("#qAgent").checked;
  if(agentOn&&typeof startAgent==="function"){
    qInput.value="";qSend.disabled=true;
    return startAgent(q,LEVEL);
  }
  SID=SID||(localStorage.getItem("pyp_sid")||null);
  const userMsg=addMsg("user",esc(q));userMsg.dataset.q=q;
  qInput.value="";qSend.disabled=true;
  const typing=addMsg("ai",'<div class="typing"><i></i><i></i><i></i></div>');
  setBusy(true);
  const bubble=typing.querySelector(".bubble");
  bubble.innerHTML='<div class="meta"></div><div class="md"></div>';
  const mdEl=$(".md",bubble);
  let ansText="",done=null,errMsg="",lastRender=0;
  try{
    const resp=await api("/api/ask/stream",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({query:q,level:LEVEL,session_id:SID})});
    if(!resp.ok){const d=await resp.json().catch(()=>({}));throw new Error(d.detail||"请求失败");}
    if(!resp.body)throw new Error("当前浏览器不支持流式输出");
    // 逐帧读取 SSE：meta → chunk* → done（或 error）
    const reader=resp.body.getReader(),dec=new TextDecoder();let buf="";
    for(;;){
      const {value,done:fin}=await reader.read();if(fin)break;
      buf+=dec.decode(value,{stream:true});
      let i;while((i=buf.indexOf("\n\n"))>=0){
        const frame=buf.slice(0,i);buf=buf.slice(i+2);
        const ev=/^event:\s*(.+)$/m.exec(frame),da=/^data:\s*(.+)$/m.exec(frame);
        if(!ev||!da)continue;
        const d=JSON.parse(da[1]);
        if(ev[1]==="meta"){
          SID=d.session_id;if(SID)localStorage.setItem("pyp_sid",SID);
          $(".meta",bubble).innerHTML=`<span>等级 L${d.level.n}</span><span>通道 ${d.provider}</span>`;
        }else if(ev[1]==="chunk"){
          ansText+=d.text;
          const now=Date.now();
          if(now-lastRender>50||d.text.includes("\n")){  // 节流：避免长答案每帧全量重渲
            mdEl.innerHTML=md(ansText);lastRender=now;
          }
        }else if(ev[1]==="done"){done=d;LAST_CASCADE=d.cascade;}
        else if(ev[1]==="error"){errMsg=d.detail||"流式输出中断";}
      }
    }
    if(errMsg)throw new Error(errMsg);
    if(!done)throw new Error("流式输出未完成");
    // —— done 收尾：置信度元信息 + 最终渲染（mermaid/chart/高亮）+ 分步/二审面板 —— //
    const c=done.confidence,lvl=c.level_label||"";LAST_CONF=c;
    let meta=`<span class="cf">置信度 <b>${c.score}</b>/100 · ${lvl}</span><span>等级 L${LEVEL}</span><span>通道 ${done.provider}</span>`;
    if(done.context&&done.context.compressed)
      meta+=`<span class="cf soft" title="更早的对话已折叠为滚动摘要">已折叠 ${done.context.dropped_turns} 轮旧对话</span>`;
    if(done.review&&done.review.verdict==="revise")
      meta+=`<span class="cf warn">二审发现 ${done.review.notes.length} 处问题</span>`;
    $(".meta",bubble).innerHTML=meta;
    const answerHtml=md(done.answer);
    mdEl.innerHTML="";revealMarkdown(mdEl,answerHtml);  // 末帧精渲染（mermaid/chart 在此生效）
    bubble.dataset.md=done.answer;  // 留存原始 Markdown，供导出/分享
    if(done.reasoning_plan){
      bubble.insertAdjacentHTML("beforeend",
        `<details class="panel"><summary>分步解答思路（MCP 分步推理）</summary>
         <div class="p-body">${esc(done.reasoning_plan).replace(/\n/g,"<br>")}</div></details>`);
    }
    if(done.review&&done.review.verdict==="revise"){
      const p=document.createElement("details");p.className="panel";p.open=true;
      p.innerHTML=`<summary class="rvw-h">二审意见 · 独立通道对照证据审阅</summary>
        <div class="p-body"><ul class="rvw-n">${done.review.notes.map(n=>`<li>${esc(n)}</li>`).join("")}</ul>
        <div class="rvw-act">
          <button class="btn sm" data-act="revised">查看修订版</button>
          <button class="btn ghost sm" data-act="original" hidden>看原答案</button>
        </div></div>`;
      bubble.appendChild(p);
      p.querySelector('[data-act="revised"]').onclick=()=>{
        mdEl.innerHTML="";revealMarkdown(mdEl,md(done.review.revised));
        p.querySelector('[data-act="revised"]').hidden=true;p.querySelector('[data-act="original"]').hidden=false;
      };
      p.querySelector('[data-act="original"]').onclick=()=>{
        mdEl.innerHTML="";revealMarkdown(mdEl,answerHtml);
        p.querySelector('[data-act="revised"]').hidden=false;p.querySelector('[data-act="original"]').hidden=true;
      };
    }
  addCitations(bubble,d.cascade);  // 引用溯源：答案下方可点击跳转原文
  }catch(e){
    bubble.innerHTML='<span style="color:var(--danger)">'+esc(humanError(e))+'</span>';
  }finally{setBusy(false);qInput.focus();}
}

/* 检索过程渲染（置信度拆解用后端真实 breakdown） */
let LAST_CASCADE=null,LAST_CONF=null;
function renderCascade(){
  const box=$("#cascade");
  if(!LAST_CASCADE){box.innerHTML='<div class="muted" style="text-align:center;margin-top:30px">先去「智能问答」提一个问题，这里会展示三级级联检索过程与置信度拆解。</div>';return;}
  const c=LAST_CASCADE;const rl={main:"主要",supplement_a:"补充A",supplement_b:"补充B"};
  const conf=LAST_CONF?LAST_CONF.score:(c.primary&&c.primary.length?98:42);
  const bd=(LAST_CONF&&LAST_CONF.breakdown)||{};
  box.innerHTML='<div class="card" style="padding:14px 18px"><b>置信度拆解</b>'+
    '<div class="cf-bar"><i id="cfFill"></i></div>'+
    '<div class="muted" id="cfTxt"></div></div>'+
    c.stages.map((s,idx)=>`<div class="stage" data-i="${idx}"><div class="hd">${esc(s.name)}`+
      `<span class="r ${s.role}">${rl[s.role]||s.role}</span></div>`+
      `<div class="chunks">${s.chunks.length? s.chunks.map(ch=>`<div class="chunk"><span class="sc">${ch.score}</span><div class="ct"><b>${esc(ch.title)}</b> · ${esc((ch.text||"").slice(0,90))}</div></div>`).join(""):'<div class="muted">本阶段暂无命中（已回退本地语料）</div>'}</div></div>`).join("");
  const stages=$$(".stage",box);
  stages.forEach((st,k)=>setTimeout(()=>st.classList.add("lit"),300+k*500));
  const fill=$("#cfFill");setTimeout(()=>{fill.style.width=conf+"%";
    $("#cfTxt").textContent=`主源命中 ${bd.primary_hit||0} + 跨源一致 ${bd.cross_source||0} + 新鲜度 ${bd.freshness||0} = ${conf}/100`;},300+stages.length*500);
}

/* 引用溯源：把答案依据的来源（去重）渲染为可点击跳转原文档的面板 */
const _ROLE_SHORT={main:"主要源",supplement_a:"补充A",supplement_b:"补充B"};
function addCitations(bubble,cascade){
  if(!cascade||!cascade.stages)return;
  const seen={},items=[];
  cascade.stages.forEach(s=>{
    const rl=_ROLE_SHORT[s.role]||s.role_label||s.role;
    (s.chunks||[]).forEach(c=>{
      if(!c.url||seen[c.url])return;seen[c.url]=1;
      items.push({url:c.url,title:c.title||c.source||c.url,role:rl});
    });
  });
  if(!items.length)return;
  const p=document.createElement("details");p.className="panel";
  p.innerHTML=`<summary class="rvw-h">引用来源（${items.length}）· 点击跳转到原文</summary>`+
    `<div class="p-body">`+items.map(it=>
      `<div class="src-row"><span class="src">${esc(it.role)}</span>`+
      `<a href="${esc(it.url)}" target="_blank" rel="noopener noreferrer">${esc(it.title)} ↗</a></div>`).join("")+`</div>`;
  bubble.appendChild(p);
}
