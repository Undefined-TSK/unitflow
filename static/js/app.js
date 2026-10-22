/* ============ 应用外壳：等级选择 / 引导页 / 页面导航 ============
   依赖：util（LEVEL/SID/CONFIG 状态）、md、chat（renderCascade）、
        library（loadLibrary）、profile（loadProfile）、evolve（loadEvolve/loadTrain）、
        settings（loadSettings）——须最后一个加载，本文件的导航绑定才能引用到全部 loadXxx。 */
const LV=[
  {n:1,t:"零基础",d:"刚接触编程"},{n:2,t:"入门",d:"懂基础语法"},
  {n:3,t:"进阶",d:"能写小脚本"},{n:4,t:"熟练",d:"做过项目"},{n:5,t:"专家",d:"精通底层"}
];

/* 等级选择 + 三步引导 */
const lvGrid=$("#lvGrid");
LV.forEach(l=>{const b=document.createElement("button");b.className="lv";b.innerHTML=
  `<div class="lv-n">L${l.n}</div><div class="lv-t">${l.t}</div><div class="lv-d">${l.d}</div>`;
  b.onclick=()=>{$$(".lv").forEach(x=>x.classList.remove("on"));b.classList.add("on");
    LEVEL=l.n;$("#lvChip").textContent="等级 L"+l.n;
    const n=$("#obNext1");if(n)n.disabled=false;};
  lvGrid.appendChild(b);});

function obStep(n){
  $$(".ob-step").forEach(s=>s.classList.toggle("on",+s.dataset.step===n));
  $$(".ob-dot").forEach(d=>d.classList.toggle("on",+d.dataset.s<=n));
}
const obQ=$("#obQ");
function obFinish(){
  if(!LEVEL){alert("请先选择你的 Python 水平");return;}
  const q=(obQ&&obQ.value||"").trim();
  localStorage.setItem("pyp_level",LEVEL);
  $("#onboarding").style.display="none";$("#app").classList.add("on");
  loadSettings();
  if(q&&typeof send==="function"&&typeof qInput!=="undefined"){
    qInput.value=q;send();  // 首问自动发送
  }
}
const obN1=$("#obNext1");if(obN1)obN1.onclick=()=>obStep(2);
const obN2=$("#obNext2");if(obN2)obN2.onclick=()=>obStep(3);
const obP2=$("#obPrev2");if(obP2)obP2.onclick=()=>obStep(1);
const obP3=$("#obPrev3");if(obP3)obP3.onclick=()=>obStep(2);
const obGo=$("#obGo");if(obGo)obGo.onclick=obFinish;
if(obQ)obQ.onkeydown=e=>{if(e.key==="Enter"&&obGo)obFinish();};

(function(){const s=+localStorage.getItem("pyp_level");if(s>0){LEVEL=s;
  const el=$$(".lv")[s-1];el&&el.click();
  // 已选过等级：引导跳到第三步，让用户直接问首问
  obStep(3);}})();

/* 启动：若以只读分享链接打开，则渲染分享对话（无后端）。
   等 plugins.js 的资产 boot 完成再渲染：图块在正确的门控态下走渲染/降级分支。 */
if(location.hash.startsWith("#share=")&&window.renderShared){
  (window.PluginsBoot||Promise.resolve()).then(()=>window.renderShared());}

/* 导航 */
const TITLES={chat:"智能问答",retrieval:"检索过程",library:"知识库",profile:"我的画像",
  evolve:"自进化",docs:"离线文档",sandbox:"沙箱",train:"能力进化",editor:"节点编排",settings:"设置"};
function goPage(p){
  $$(".nav-b").forEach(x=>x.classList.remove("on"));
  const b=$$(".nav-b").find(x=>x.dataset.p===p);
  if(b)b.classList.add("on");
  $$(".page").forEach(x=>x.classList.remove("on"));
  $("#p-"+p).classList.add("on");
  $("#topT").textContent=TITLES[p]||p;
  if(p==="retrieval")renderCascade();
  if(p==="library")loadLibrary();
  if(p==="profile")loadProfile();
  if(p==="evolve")loadEvolve();
  if(p==="train")loadTrain();
  if(p==="settings")loadSettings();
  if(p==="sandbox"&&typeof loadSandbox==="function")loadSandbox();
  if(p==="editor"&&typeof loadEditor==="function")loadEditor();
}
$$(".nav-b").forEach(b=>b.onclick=()=>goPage(b.dataset.p));
function setLevel(n){const el=$$(".lv")[n-1];el&&el.click();}  // 复用等级卡选择逻辑
