/* ============ Markdown 渲染管道 ============
   marked（解析，含 [main]/[补充] 角色标签扩展）
   → DOMPurify（XSS 消毒，允许有限 HTML 表格/布局标签）
   → 代码块：mermaid → 图解；chart → ECharts；其余 → highlight.js 高亮 + 复制
   → $...$ / $$...$$ → KaTeX 公式（官方 contrib auto-render）
   依赖：vendor/marked、dompurify、katex、katex-auto-render、highlight（先于本文件加载）；
   mermaid / echarts 由 plugins.js 按 diagram-render 门控懒加载（P4），
   插件关闭时 window.mermaid / window.echarts 不存在，图块降级为普通高亮。 */
const SRC_LABEL={main:"主要源",supplement_a:"补充A",supplement_b:"补充B"};
marked.use({gfm:true,breaks:true,extensions:[{
  name:"srcTag",level:"inline",start:s=>s.indexOf("["),
  tokenizer(s){const m=/^\[(main|supplement_a|supplement_b)\]/.exec(s);
    if(m)return{type:"srcTag",raw:m[0],role:m[1]};},
  renderer(t){return `<span class="src">${SRC_LABEL[t.role]}</span>`;}
}]});

/* mermaid 初始化：由 plugins.js 在资产懒加载就绪后调用（diagram-render 门控）。
   插件关闭时 window.mermaid 不存在，本函数空转——顶层不再无条件 initialize。 */
function initMermaid(){
  if(!window.mermaid)return;
  mermaid.initialize({startOnLoad:false,theme:"dark",securityLevel:"strict",
    themeVariables:{background:"#16171B",mainBkg:"#1B1D22",lineColor:"#9AA0AB"},
    htmlLabels:false});  // 不用 foreignObject：消毒后的 SVG 不嵌 HTML，避免渲染失败
}

function md(src){
  const box=document.createElement("div");
  box.innerHTML=DOMPurify.sanitize(marked.parse(src),{ADD_ATTR:["class","target","rel"]});
  box.querySelectorAll("pre").forEach(enhanceCode);
  box.querySelectorAll("a").forEach(a=>{a.target="_blank";a.rel="noopener noreferrer";});
  renderMath(box);
  return box.innerHTML;
}

/* 代码块后处理：mermaid / chart / 高亮；按钮用事件委托绑定（见文件末尾）——
   注意：md() 返回 HTML 字符串，元素级 onclick 会在序列化时丢失，
   因此复制/运行按钮一律经 document 级委托触发（对流式重渲染也天然免疫）。
   diagram-render 门控关闭（或资产尚未就绪）时，mermaid/chart 块走普通
   高亮分支：源码仍可读可复制，由 plugins.js 就绪后的兜底扫描补画。 */
function enhanceCode(pre){
  const code=pre.querySelector("code");if(!code)return;
  const lang=(code.className.match(/language-([\w-]+)/)||[])[1]||"";
  const diagramOn=!!(window.DiagramRender&&window.DiagramRender.enabled);
  if(lang==="mermaid"&&diagramOn){
    const d=document.createElement("div");d.className="mermaid";d.textContent=code.textContent;
    pre.replaceWith(d);return;
  }
  if(lang==="chart"&&diagramOn){
    const d=document.createElement("div");d.className="chart";
    d.setAttribute("data-option",code.textContent);  // 原始 JSON，initCharts 时解析
    pre.replaceWith(d);return;
  }
  if(lang&&window.hljs){
    try{code.innerHTML=hljs.highlight(code.textContent,{language:lang}).value;}catch(e){}
  }
  pre.classList.add("hljs");
  const btn=document.createElement("button");btn.className="code-copy";btn.textContent="复制";
  btn.setAttribute("data-act","copy");
  pre.appendChild(btn);
  // Python 代码块：沙箱一键运行（AI 答案里的代码可直接验证，输出渲染在代码块下方）
  if(lang==="python"||lang==="py"){
    const rb=document.createElement("button");rb.className="code-copy code-run";rb.textContent="▶ 运行";
    rb.setAttribute("data-act","run");
    rb.title="在 PyPedia 沙箱中运行这段代码（原版 Python 3.13）";
    pre.appendChild(rb);
  }
}

/* 代码块按钮事件委托（document 级：innerHTML 重渲染 / 流式刷新均不丢 Handler） */
document.addEventListener("click",(e)=>{
  const btn=e.target.closest("button.code-copy");
  if(!btn)return;
  const pre=btn.closest("pre");
  const code=pre&&pre.querySelector("code");
  if(!code)return;
  if(btn.getAttribute("data-act")==="run"){
    if(!window.Sandbox){alert("沙箱运行时尚未加载，请先打开「沙箱」页一次");return;}
    const orig=btn.textContent;
    btn.textContent="…运行中";btn.disabled=true;
    const restore=()=>{btn.textContent=orig;btn.disabled=false;};
    try{window.Sandbox.runInline(pre,code.textContent);setTimeout(restore,400);}
    catch(err){restore();alert("沙箱运行失败："+(err&&err.message?err.message:err));}
    return;
  }
  // 复制
  const done=()=>{btn.textContent="已复制 ✓";setTimeout(()=>btn.textContent="复制",1500);};
  if(navigator.clipboard&&navigator.clipboard.writeText){
    navigator.clipboard.writeText(code.textContent).then(done,()=>{});
  }
});

/* KaTeX：$...$ 行内 / $$...$$ 独立公式——用官方 contrib auto-render
   （vendor/katex-auto-render.min.js，与 katex.min.js 同版本 0.19.0），
   不再手写 TreeWalker+正则（那正是 auto-render 的内部实现）。
   ignoredTags 跳过代码块；ignoredClasses 跳过 mermaid/chart 与已渲染部分。 */
function renderMath(root){
  if(!window.renderMathInElement)return;
  try{
    renderMathInElement(root,{
      delimiters:[
        {left:"$$",right:"$$",display:true},
        {left:"\\[",right:"\\]",display:true},
        {left:"\\(",right:"\\)",display:false},
        {left:"$",right:"$",display:false}
      ],
      ignoredTags:["script","noscript","style","textarea","pre","code"],
      ignoredClasses:["mermaid","chart","katex"],
      throwOnError:false,
      strict:false
    });
  }catch(e){/* 公式渲染失败不阻塞答案展示 */}
}

/* ECharts：chart 块 option JSON → 交互图表（剥离 formatter 字符串防 HTML 注入） */
function initCharts(root){
  if(!window.echarts)return;
  root.querySelectorAll(".chart").forEach(el=>{
    if(el._ec)return;
    let opt=null;
    try{opt=JSON.parse(el.getAttribute("data-option")||"null");}catch(e){}
    if(!opt||typeof opt!=="object"){
      el.textContent="（图表数据缺失或解析失败）";el._ec=true;return;
    }
    try{
      const ch=echarts.init(el,null,{renderer:"canvas"});
      ch.setOption(sanitizeChartOption(opt));
      el._ec=ch;
      window.addEventListener("resize",()=>ch.resize());
    }catch(e){el.textContent="（图表渲染失败）";el._ec=true;}
  });
}
function sanitizeChartOption(o){
  if(Array.isArray(o))return o.map(sanitizeChartOption);
  if(o&&typeof o==="object"){
    const out={};
    for(const k in o){
      let v=o[k];
      if(k==="formatter"&&typeof v==="string")v=v.replace(/<[^>]*>/g,"");  // tooltip HTML 注入面
      else v=sanitizeChartOption(v);
      out[k]=v;
    }
    return out;
  }
  return o;
}

/* 逐块淡入，模拟流式生成；末尾渲染 mermaid / 图表 */
function revealMarkdown(el,html){
  const tmp=document.createElement("div");tmp.innerHTML=html;
  const nodes=[...tmp.childNodes];let delay=0;
  nodes.forEach(n=>{const w=document.createElement("div");w.className="reveal";
    w.style.animationDelay=delay+"ms";w.appendChild(n.cloneNode(true));el.appendChild(w);delay+=55;});
  $("#msgs").scrollTop=$("#msgs").scrollHeight;
  const mm=$$(".mermaid",el);
  if(mm.length&&window.mermaid)mermaid.run({nodes:mm,suppressErrors:true}).catch(()=>{});
  initCharts(el);
}
