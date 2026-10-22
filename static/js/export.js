/* ============ 导出 / 分享：Markdown / 自包含 HTML / PNG / 复制 / 只读分享链接 ============
   依赖：util（esc）、md（md）。纯前端，零后端依赖；对话原文存于消息元素 dataset。
   只读分享：把对话 JSON 编码进 location.hash（#share=），打开该链接即只读渲染，无需后端。 */
(function(){
  const SHARE_KEY="pyp_share";

  // 收集 #msgs 中的对话为结构化数组
  function collect(){
    return $$("#msgs .msg").map(m=>({
      role:m.classList.contains("user")?"user":"ai",
      text:m.classList.contains("user")?(m.dataset.q||m.textContent.trim())
                                        :(m.dataset.md||($(".md",m)?.textContent||"")),
      md:m.dataset.md||"",
    }));
  }

  function download(filename,content,mime){
    const blob=new Blob([content],{type:mime+";charset=utf-8"});
    const url=URL.createObjectURL(blob);
    const a=document.createElement("a");a.href=url;a.download=filename;
    document.body.appendChild(a);a.click();a.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
  }

  function toMarkdown(){
    const msgs=collect();if(!msgs.length)return "";
    return "# PyPedia 对话导出\n\n"+
      msgs.map(m=>m.role==="user"?"> **你**："+m.text
                                  :"**PyPedia**：\n\n"+(m.md||m.text)).join("\n\n")+"\n";
  }

  function toHTML(){
    const msgs=collect();if(!msgs.length)return "";
    const body=msgs.map(m=>{
      const cls=m.role==="user"?"u":"a";
      const inner=m.role==="user"?esc(m.text):(m.md?md(m.md):esc(m.text));
      return `<div class="m ${cls}"><div class="who">${m.role==="user"?"你":"PyPedia"}</div><div class="b">${inner}</div></div>`;
    }).join("\n");
    return `<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PyPedia 对话导出</title><style>
body{background:#0A0A0B;color:#D9D9DA;font-family:system-ui,-apple-system,"PingFang SC",sans-serif;
  max-width:820px;margin:0 auto;padding:28px;line-height:1.65}
h1{font-size:20px}.m{margin:18px 0;display:flex;gap:12px}.who{font-weight:700;flex:none;color:#2E90FF}
.u .who{color:#2E90FF}.a .who{color:#4ADE80}.b{flex:1}
.b pre{background:#07080A;border:1px solid rgba(255,255,255,.1);border-radius:9px;padding:12px;overflow:auto}
.b code{background:#1B1D22;padding:1px 5px;border-radius:5px;font-family:monospace}
.b table{border-collapse:collapse;width:100%}.b th,.b td{border:1px solid rgba(255,255,255,.12);padding:6px 10px}
.b a{color:#2E90FF}.b img{max-width:100%}
</style></head><body><h1>PyPedia 对话导出</h1>\n${body}\n</body></html>`;
  }

  function exportMarkdown(){const md=toMarkdown();if(!md)return alert("还没有对话可导出");
    download("pypedia-对话.md",md,"text/markdown");}
  function exportHTML(){const h=toHTML();if(!h)return alert("还没有对话可导出");
    download("pypedia-对话.html",h,"text/html");}
  async function copyMarkdown(){const md=toMarkdown();if(!md)return alert("还没有对话可导出");
    try{await navigator.clipboard.writeText(md);flash("已复制 Markdown 到剪贴板");}
    catch(e){alert("复制失败："+e.message);}}

  // 无依赖 PNG 导出：SVG <foreignObject> 包裹 HTML → 绘到 canvas → 下载
  function exportPNG(){
    const src=$("#msgs");if(!src||!$$("#msgs .msg").length)return alert("还没有对话可导出");
    const w=820,padding=24;
    const clone=src.cloneNode(true);
    clone.querySelectorAll(".typing").forEach(e=>e.remove());
    clone.style.cssText="background:#0A0A0B;color:#D9D9DA;padding:"+padding+"px;"+
      "font-family:system-ui,sans-serif;width:"+w+"px;box-sizing:border-box";
    const xml='<svg xmlns="http://www.w3.org/2000/svg" width="'+(w+padding*2)+
      '" height="'+(src.scrollHeight+padding*2)+'"><foreignObject width="100%" height="100%">'+
      '<div xmlns="http://www.w3.org/1999/xhtml">'+clone.outerHTML+'</div></foreignObject></svg>';
    const img=new Image();
    const svgUrl="data:image/svg+xml;charset=utf-8,"+encodeURIComponent(xml);
    img.onload=()=>{
      const cv=document.createElement("canvas");
      const scale=2;cv.width=(w+padding*2)*scale;cv.height=(src.scrollHeight+padding*2)*scale;
      const ctx=cv.getContext("2d");ctx.scale(scale,scale);ctx.drawImage(img,0,0);
      try{cv.toBlob(b=>{const url=URL.createObjectURL(b);const a=document.createElement("a");
        a.href=url;a.download="pypedia-对话.png";a.click();
        setTimeout(()=>URL.revokeObjectURL(url),1000);});}
      catch(e){alert("PNG 导出失败（可能含外部图片触发安全限制）："+e.message);}
    };
    img.onerror=()=>alert("PNG 导出失败：渲染节点不支持");
    img.src=svgUrl;
  }

  // 只读分享链接：对话 JSON 编码进 hash，打开即只读渲染（无后端）
  function shareLink(){
    const msgs=collect();if(!msgs.length)return alert("还没有对话可分享");
    localStorage.setItem(SHARE_KEY,JSON.stringify(msgs));
    const id="t"+Date.now();
    localStorage.setItem(SHARE_KEY+"_"+id,JSON.stringify(msgs));
    const link=location.origin+location.pathname+"#share="+id;
    navigator.clipboard.writeText(link).then(()=>flash("只读分享链接已复制："+link),
      ()=>prompt("复制此只读链接：",link));
    return link;
  }
  window.shareCurrent=shareLink;

  // 渲染只读分享页（app.js 在启动时调用）
  function renderShared(){
    const m=/#share=([^&]+)/.exec(location.hash);
    if(!m)return false;
    const raw=localStorage.getItem(SHARE_KEY+"_"+m[1]);
    if(!raw)return false;
    let msgs=[];try{msgs=JSON.parse(raw);}catch(e){return false;}
    const box=$("#msgs");if(box){box.innerHTML="";
      msgs.forEach(x=>{const el=document.createElement("div");el.className="msg "+(x.role==="user"?"user":"ai");
        el.innerHTML=`<div class="av">${x.role==="user"?"你":"P"}</div><div class="bubble">${
          x.role==="user"?esc(x.text):(x.md?md(x.md):esc(x.text))}</div>`;});}
    document.querySelectorAll(".composer").forEach(c=>c.style.display="none");
    const t=$("#topT");if(t)t.textContent="分享的对话（只读）";
    const sub=document.createElement("div");sub.className="muted";sub.style.textAlign="center";
    sub.style.margin="10px";sub.textContent="这是他人分享的只读对话，无法继续提问。";
    $("#msgs")?.parentElement?.insertBefore(sub,$("#msgs"));
    // 跳过启动引导，直接展示应用壳（分享场景无需选等级）
    const ob=$("#onboarding"),app=$("#app");
    if(ob)ob.style.display="none";
    if(app)app.classList.add("on");
    return true;
  }
  window.renderShared=renderShared;

  function flash(msg){const t=document.createElement("div");t.className="pk-hint";
    t.textContent=msg;document.body.appendChild(t);setTimeout(()=>t.remove(),1800);}

  // 暴露给命令面板 / 工具栏
  window.exportChat=exportMarkdown;  // 命令面板「导出当前对话」默认导出 MD
  window.exportMarkdown=exportMarkdown;
  window.exportHTML=exportHTML;
  window.exportPNG=exportPNG;
  window.copyMarkdown=copyMarkdown;

  // 工具栏按钮（若 index.html 提供挂载点则渲染）
  function buildToolbar(){
    const host=$("#exportBar");
    if(!host)return;
    const btns=[["导出MD",exportMarkdown],["导出HTML",exportHTML],["导出PNG",exportPNG],
      ["复制MD",copyMarkdown],["分享链接",shareLink]];
    host.innerHTML=btns.map(([t])=>`<button class="btn ghost sm" data-t="${t}">${t}</button>`).join("");
    $$("button",host).forEach(b=>b.onclick=()=>{
      const fn=btns.find(x=>x[0]===b.dataset.t)[1];fn();});
  }
  if(document.readyState!=="loading")buildToolbar();
  else document.addEventListener("DOMContentLoaded",buildToolbar);
})();
