/* ============ 基础工具 / 访问令牌 / 统一 API 入口 ============
   依赖：无（须第一个加载）。被 md/chat/library/profile/evolve/settings/app 共用。 */
const $=(s,r=document)=>r.querySelector(s);
const $$=(s,r=document)=>[...r.querySelectorAll(s)];
function esc(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}

/* —— 访问令牌（服务端 AUTH_ENABLE 开启时所有 /api 请求自动带头） —— */
const TOKEN_KEY="pypedia_token";
const getToken=()=>localStorage.getItem(TOKEN_KEY)||"";
const setToken=t=>{if(t)localStorage.setItem(TOKEN_KEY,t);else localStorage.removeItem(TOKEN_KEY);};
function authHeaders(){const t=getToken();return t?{Authorization:"Bearer "+t}:{};}
/* 统一 API 入口：自动注入令牌；401 时弹令牌输入框（FormData 不强行设 JSON 头） */
const api=(u,o={})=>{
  const h={...authHeaders(),...(o.headers||{})};
  if(!(o.body instanceof FormData)&&!h["Content-Type"])h["Content-Type"]="application/json";
  return fetch(u,{...o,headers:h}).then(r=>{
    if(r.status===401)showAuthPrompt();
    return r;
  });
};
/* 错误人话化：把技术错误翻译成用户能懂的中文提示 */
function humanError(e){
  const m=(e&&e.message)||String(e||"");
  if(/Failed to fetch|NetworkError|网络/.test(m))return "网络好像断了，请检查连接后重试";
  if(/timeout|超时|timed out/i.test(m))return "请求超时了，模型服务可能正忙，请稍后再试";
  if(/429|太频繁|频繁/.test(m))return "提问太频繁，稍等几秒再试";
  if(/502|引擎调用失败|生成答案/.test(m))return "暂时没能生成答案，请稍后再试一次";
  if(/500/.test(m))return "服务出了点小问题，请重试";
  if(/401|未授权|令牌/.test(m))return "访问被拒绝，请检查本地访问令牌";
  if(/400|不能为空/.test(m))return "问题不能为空，请先输入你的问题";
  return "出错了："+m;
}

function showAuthPrompt(){  if($("#authMask"))return;
  const m=document.createElement("div");m.id="authMask";
  m.style.cssText="position:fixed;inset:0;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center;z-index:99";
  m.innerHTML=`<div class="card" style="max-width:400px;width:90%">
    <h3 style="margin-top:0">需要访问令牌</h3>
    <p class="mini">服务端开启了鉴权。请输入本地令牌：数据目录下的 <code>token</code> 文件内容（或 .env 的 AUTH_TOKEN）。</p>
    <input id="authTok" class="inp" placeholder="Bearer Token" style="width:100%">
    <div style="display:flex;gap:8px;margin-top:10px">
      <button class="btn primary" id="authOk">保存并继续</button>
      <button class="btn" id="authCancel">取消</button>
    </div></div>`;
  document.body.appendChild(m);
  $("#authOk").onclick=()=>{setToken($("#authTok").value.trim());m.remove();location.reload();};
  $("#authCancel").onclick=()=>m.remove();
  $("#authTok").focus();
}

/* —— 跨模块共享状态（chat/settings 等读写） —— */
let LEVEL=3, SID=null, BUSY=false, CONFIG={};
