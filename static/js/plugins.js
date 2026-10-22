/* ============ 前端插件资产加载器（万物皆插件 · ui_panels 懒加载） ============
   读 /api/units 拿各 unit 的 ui_panels 贡献与门控态（已合并 /api/plugins 视图）：
   - enabled → 动态按序加载 assets（<script>），全部就绪后调 initMermaid() 并
     对 boot 期间已渲染的图块兜底扫描（自愈，防流式答案早于资产就绪）；
   - 关闭 / .env 拦截 → 一个字节都不下载；md.js 的 mermaid/chart 块随后续
     渲染自动降级为普通代码高亮（源码仍可读、可复制）。

   依赖：util（$/$$/api）。端点不可用（旧后端/分享页无后端）时静默降级。
   导出：window.DiagramRender{enabled,ready,assets,refresh}
        window.PluginsBoot（boot Promise，分享页渲染前可 await） */
(function(){
"use strict";
const state={enabled:false,ready:false,assets:[],loaded:new Set()};

function loadScript(src){
  return new Promise((res,rej)=>{
    const s=document.createElement("script");
    s.src=src;s.async=false;  // 保序：mermaid 先于依赖它的逻辑就绪
    s.onload=()=>{state.loaded.add(src);res();};
    s.onerror=()=>rej(new Error("资产加载失败:"+src));
    document.head.appendChild(s);
  });
}

/* 就绪兜底：boot 期间渲染出来的图块补跑（mermaid.run 自带 data-processed 去重） */
function sweepPending(){
  if(window.mermaid){
    const pending=$$(".mermaid").filter(el=>!el.hasAttribute("data-processed"));
    if(pending.length)mermaid.run({nodes:pending,suppressErrors:true}).catch(()=>{});
  }
  if(window.echarts&&typeof initCharts==="function")initCharts(document);
}

async function boot(){
  let units=[];
  try{
    const r=await api("/api/units");
    if(!r.ok)return state;  // 端点不可用（旧后端/无权限）：保持 disabled，渲染走降级分支
    const d=await r.json();
    units=(d&&d.units)||[];
  }catch(e){return state;}  // 网络异常等：静默降级
  const assets=[];
  for(const u of units){
    if(!u.enabled)continue;  // 门控关（用户态或 .env）→ 不加载
    const panels=(u.contributions&&u.contributions.ui_panels)||[];
    for(const p of panels){
      if(p.lazy===false)continue;  // 非 lazy 面板由页面静态引入，loader 不管
      (p.assets||[]).forEach(a=>{if(!assets.includes(a))assets.push(a);});
    }
  }
  state.assets=assets;
  if(!assets.length){state.enabled=false;return state;}
  state.enabled=true;
  for(const src of assets){
    if(state.loaded.has(src))continue;  // refresh 时跳过已加载资产
    try{await loadScript(src);}
    catch(e){console.warn("[plugins]",e.message);}  // 单点失败不阻塞其余资产
  }
  state.ready=true;
  if(typeof initMermaid==="function")initMermaid();
  sweepPending();
  document.dispatchEvent(new CustomEvent("diagram-render:ready",
    {detail:{ready:true}}));
  return state;
}

state.refresh=function(){return boot();};  // 设置页切换开关后重新拉取态并按需加载
window.DiagramRender=state;
window.PluginsBoot=boot();
})();
