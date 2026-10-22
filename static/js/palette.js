/* ============ 命令面板 Cmd/Ctrl+K：全局搜索 / 跳转 / 执行 ============
   依赖：app（goPage / setLevel / LEVEL）、util（esc）、md（md）、chat（send）。
   零后端依赖：纯前端命令表，动作直接调用已存在的导航/等级函数。 */
(function(){
  const PAGES=[
    {p:"chat",t:"智能问答"},{p:"retrieval",t:"检索过程"},{p:"library",t:"知识库"},
    {p:"profile",t:"我的画像"},{p:"evolve",t:"自进化"},{p:"docs",t:"离线文档"},
    {p:"train",t:"能力进化"},{p:"settings",t:"设置"}
  ];
  // 静态命令表：分类 + 标题 + 动作（动作引用全局 goPage/setLevel）
  const COMMANDS=[
    ...PAGES.map(c=>({cat:"跳转",title:"打开 "+c.t,kw:c.t,run:()=>goPage(c.p)})),
    {cat:"操作",title:"新建对话",kw:"新对话 提问 q",run:()=>{goPage("chat");
      const i=$("#qInput");if(i){i.value="";i.focus();}}},
    ...[1,2,3,4,5].map(n=>({cat:"等级",title:"切换为 L"+n+" "+LV[n-1].t,kw:"等级 level",
      run:()=>setLevel(n)})),
    {cat:"操作",title:"导出当前对话",kw:"导出 分享 export",run:()=>{
      if(typeof window.exportChat==="function")window.exportChat();
      else flashHint("导出功能即将上线（F3）");}},
  ];

  let root=null,inputEl=null,listEl=null,sel=0,items=[];
  function ensure(){
    if(root)return;
    root=document.createElement("div");root.id="palette";
    root.style.cssText="position:fixed;inset:0;z-index:60;display:none;"+
      "align-items:flex-start;justify-content:center;background:rgba(0,0,0,.5)";
    root.innerHTML=`<div class="pk-box"><input class="pk-in" placeholder="搜索页面或操作…（↑↓ 选择，Enter 执行，Esc 关闭）">
      <div class="pk-list"></div><div class="pk-foot">PyPedia 命令面板</div></div>`;
    document.body.appendChild(root);
    inputEl=$(".pk-in",root);listEl=$(".pk-list",root);
    inputEl.oninput=()=>{sel=0;render();};
    inputEl.onkeydown=e=>{
      if(e.key==="ArrowDown"){e.preventDefault();sel=Math.min(sel+1,items.length-1);render();}
      else if(e.key==="ArrowUp"){e.preventDefault();sel=Math.max(sel-1,0);render();}
      else if(e.key==="Enter"){e.preventDefault();exec();}
      else if(e.key==="Escape"){e.preventDefault();close();}
    };
    root.onclick=e=>{if(e.target===root)close();};
  }
  function render(){
    const q=inputEl.value.trim().toLowerCase();items=COMMANDS.filter(c=>(c.title+c.kw).toLowerCase().includes(q));
    listEl.innerHTML=items.map((c,i)=>`<div class="pk-i ${i===sel?"on":""}" data-i="${i}">
      <span class="pk-cat">${c.cat}</span><span class="pk-t">${esc(c.title)}</span></div>`).join("")
      ||'<div class="pk-i muted">无匹配命令</div>';
    $$(".pk-i[data-i]",listEl).forEach(el=>el.onclick=()=>{sel=+el.dataset.i;exec();});
  }
  function exec(){const c=items[sel];if(!c)return;close();c.run();}
  function open(){ensure();root.style.display="flex";inputEl.value="";sel=0;render();
    setTimeout(()=>inputEl.focus(),10);}
  function close(){if(root)root.style.display="none";}
  function flashHint(msg){const t=document.createElement("div");t.className="pk-hint";
    t.textContent=msg;document.body.appendChild(t);setTimeout(()=>t.remove(),1600);}

  document.addEventListener("keydown",e=>{
    if((e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==="k"){e.preventDefault();open();}
  });
  // 顶栏 ⌘K 提示按钮（由 index.html 提供，存在则绑定）
  const hintBtn=$("#cmdkHint");
  if(hintBtn)hintBtn.onclick=open;

  window.openPalette=open;  // 供其他模块唤起
})();
