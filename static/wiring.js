(() => {
  "use strict";

  const KEY="lokivelli.repoBountyHunter.v0.1";
  const $=s=>document.querySelector(s);
  const $$=s=>[...document.querySelectorAll(s)];

  function state(){
    try{return JSON.parse(localStorage.getItem(KEY)||"{}")}
    catch{return {}}
  }

  function saveState(s){
    localStorage.setItem(KEY,JSON.stringify(s));
  }

  function base(){
    const input=$("#backendUrl")?.value?.trim();
    const saved=state().backend||"";
    return (input||saved).replace(/\/$/,"");
  }

  function api(path){
    return base()+path;
  }

  async function request(path,opts={}){
    const headers={"Accept":"application/json",...(opts.headers||{})};
    if(opts.body && !headers["Content-Type"]) headers["Content-Type"]="application/json";
    const r=await fetch(api(path),{...opts,headers});
    const text=await r.text();
    let data={};
    try{data=JSON.parse(text)}catch{data={raw:text}};
    if(!r.ok || data.status==="HOLD" || data.status==="FAILED"){
      throw new Error(data.error||data.detail||`${r.status} ${r.statusText}`);
    }
    return data;
  }

  function log(msg){
    const el=$("#log");
    if(!el)return;
    el.textContent+=`[${new Date().toLocaleTimeString()}] ${msg}\n`;
    el.scrollTop=el.scrollHeight;
  }

  function toast(msg){
    const el=$("#toast");
    if(!el)return;
    el.textContent=msg;
    el.classList.add("on");
    clearTimeout(toast._rbhTimer);
    toast._rbhTimer=setTimeout(()=>el.classList.remove("on"),2600);
  }

  function receipt(operation,status,payload={}){
    const s=state();
    const list=Array.isArray(s.receipts)?s.receipts:[];
    list.push({
      receipt_id:`adapter-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,8)}`,
      operation,
      timestamp:new Date().toISOString(),
      status,
      payload
    });
    s.receipts=list.slice(-500);
    saveState(s);
  }

  function download(url,name=""){
    const a=document.createElement("a");
    a.href=url;
    if(name)a.download=name;
    a.style.display="none";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  function fallbackClick(el){
    el.dataset.rbhFallback="1";
    el.click();
  }

  function ensureDrawer(){
    let d=$("#rbhBackendDrawer");
    if(d)return d;
    d=document.createElement("div");
    d.id="rbhBackendDrawer";
    d.className="drawer";
    d.innerHTML=`
      <div class="drawer-card">
        <div class="drawer-head">
          <div><div class="kicker">Backend evidence</div><h2 id="rbhBackendTitle">Result</h2></div>
          <button class="btn ghost" id="rbhBackendClose">✕</button>
        </div>
        <pre id="rbhBackendBody" class="log" style="max-height:70vh;white-space:pre-wrap;overflow:auto"></pre>
      </div>`;
    document.body.appendChild(d);
    $("#rbhBackendClose").onclick=()=>d.classList.remove("open");
    d.addEventListener("click",e=>{if(e.target===d)d.classList.remove("open")});
    return d;
  }

  function showData(title,data){
    const d=ensureDrawer();
    $("#rbhBackendTitle").textContent=title;
    $("#rbhBackendBody").textContent=typeof data==="string"?data:JSON.stringify(data,null,2);
    d.classList.add("open");
  }

  function languageObjects(){
    const lines=($("#languageRoster")?.value||"")
      .split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
    return lines.map((name,i)=>({
      name,
      slug:name.toLowerCase(),
      enabled:true,
      pinned:i<4,
      order:i+1,
      polling:i<4?"daily":"weekly"
    }));
  }

  function rootList(){
    return ($("#rootRoster")?.value||"")
      .split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
  }

  function wireSaveSettings(){
    const btn=$("#saveSettingsBtn");
    if(!btn||btn.dataset.rbhWired)return;
    btn.dataset.rbhWired="1";
    const original=btn.onclick;
    btn.onclick=async e=>{
      if(original)original.call(btn,e);
      try{
        await request("/api/config/languages",{
          method:"POST",
          body:JSON.stringify({languages:languageObjects()})
        });
        await request("/api/config/runtime-roots",{
          method:"POST",
          body:JSON.stringify({roots:rootList()})
        });
        receipt("config.backend.sync","LIVE",{languages:languageObjects().length,roots:rootList().length});
        log("Backend configuration synchronized with GUI language roster and Termux roots");
      }catch(err){
        receipt("config.backend.sync","HOLD",{error:String(err.message||err)});
        log(`HOLD: backend settings sync failed · ${err.message||err}`);
      }
    };
  }

  function wireRefreshEverything(){
    const btn=$("#refreshAllBtn");
    if(!btn||btn.dataset.rbhWired)return;
    btn.dataset.rbhWired="1";
    const original=btn.onclick;
    btn.onclick=async e=>{
      const old=btn.textContent;
      btn.disabled=true;
      btn.textContent="↻ REFRESHING EVERYTHING…";
      log("REFRESH EVERYTHING: backend full-language, all-period evidence sweep started");
      try{
        const data=await request("/api/refresh",{
          method:"POST",
          body:JSON.stringify({full_languages:true})
        });
        receipt("refresh.everything.backend","LIVE",{
          status:data.status,
          trending_lanes:data.results?.trending?.length
        });
        log(`REFRESH EVERYTHING backend sweep ended · ${data.results?.trending?.length||0} Trending lanes`);
      }catch(err){
        receipt("refresh.everything.backend","HOLD",{error:String(err.message||err)});
        log(`HOLD: backend full refresh failed · ${err.message||err}`);
      }finally{
        btn.disabled=false;
        btn.textContent=old;
        if(original)await original.call(btn,e);
      }
    };
  }

  function wireExportEverything(){
    const btn=$("#exportBtn");
    if(!btn||btn.dataset.rbhWired)return;
    btn.dataset.rbhWired="1";
    const original=btn.onclick;
    btn.onclick=async e=>{
      const old=btn.textContent;
      btn.disabled=true;
      btn.textContent="⇩ EXPORTING…";
      try{
        const data=await request("/api/export/all",{method:"POST",body:"{}"});
        if(!data.download_url)throw new Error("backend export returned no download_url");
        download(api(data.download_url));
        receipt("manual.export.everything","LIVE",{format:"zip",sha256:data.sha256,download_url:data.download_url});
        log(`EXPORT EVERYTHING LIVE · ${data.download_url} · ${data.sha256||"no hash"}`);
        toast("Evidence ZIP exported");
      }catch(err){
        receipt("manual.export.everything","HOLD",{error:String(err.message||err),fallback:"browser-json"});
        log(`HOLD: backend ZIP export failed · ${err.message||err} · using browser JSON fallback`);
        if(original)original.call(btn,e);
      }finally{
        btn.disabled=false;
        btn.textContent=old;
      }
    };
  }

  function wireManualButtons(){
    document.addEventListener("click",async e=>{
      const el=e.target.closest("[data-export-manual],[data-export-json]");
      if(!el)return;
      if(el.dataset.rbhFallback==="1"){
        delete el.dataset.rbhFallback;
        return;
      }
      e.preventDefault();
      e.stopImmediatePropagation();
      const key=el.dataset.exportManual||el.dataset.exportJson;
      const format=el.dataset.exportManual?"html":"json";
      try{
        await request("/api/manuals",{method:"POST",body:"{}"});
        download(api(`/api/manual/current?key=${encodeURIComponent(key)}&format=${format}`));
        receipt("manual.backend.download","LIVE",{key,format});
        log(`Manual backend download LIVE · ${key} · ${format}`);
      }catch(err){
        receipt("manual.backend.download","HOLD",{key,format,error:String(err.message||err),fallback:"browser"});
        log(`HOLD: backend manual download failed · ${err.message||err} · using browser fallback`);
        fallbackClick(el);
      }
    },true);
  }

  let searchTimer=null;
  function ensureSearchResults(){
    const host=$(".search-wrap");
    if(!host)return null;
    host.style.position="relative";
    let box=$("#rbhSearchResults");
    if(box)return box;
    box=document.createElement("div");
    box.id="rbhSearchResults";
    box.style.cssText="display:none;position:absolute;z-index:50;top:calc(100% + 6px);left:0;right:0;max-height:55vh;overflow:auto;background:#0b090d;border:1px solid #493047;border-radius:12px;padding:8px;box-shadow:0 18px 50px #000c";
    host.appendChild(box);
    return box;
  }

  function searchLabel(r){
    return r.full_name||r.object_key||r.path||r.manual_key||r.receipt_id||r.name||r.operation||"result";
  }

  function wireBackendSearch(){
    const input=$("#globalSearch");
    const box=ensureSearchResults();
    if(!input||!box)return;
    input.addEventListener("input",()=>{
      clearTimeout(searchTimer);
      const q=input.value.trim();
      if(!q){box.style.display="none";box.innerHTML="";return}
      searchTimer=setTimeout(async()=>{
        try{
          const data=await request(`/api/search?q=${encodeURIComponent(q)}`);
          const rows=Array.isArray(data.results)?data.results:[];
          box.innerHTML=rows.length?rows.slice(0,40).map((r,i)=>
            `<button class="mini" data-rbh-search-index="${i}" style="display:block;width:100%;text-align:left;margin:4px 0;height:auto;min-height:38px"><b>${String(r.kind||"result").toUpperCase()}</b> · ${escapeHtml(searchLabel(r))}</button>`
          ).join(""):`<div class="empty"><b>No backend evidence matches.</b>Local card filtering is still active.</div>`;
          box._rbhRows=rows;
          box.style.display="block";
        }catch(err){
          box.innerHTML=`<div class="empty"><b>Backend search HOLD.</b>${escapeHtml(String(err.message||err))}</div>`;
          box.style.display="block";
        }
      },250);
    });
    box.addEventListener("click",e=>{
      const b=e.target.closest("[data-rbh-search-index]");
      if(!b)return;
      const row=box._rbhRows?.[Number(b.dataset.rbhSearchIndex)];
      if(row)showData(`Search · ${row.kind||"result"}`,row);
    });
  }

  function escapeHtml(v){
    return String(v??"").replace(/[&<>"']/g,m=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
  }

  function repoName(card){
    return card.querySelector(".repo-name")?.textContent?.trim()||"";
  }

  function decorateRepoActions(){
    $$(".repo").forEach(card=>{
      if(card.dataset.rbhWired)return;
      const name=repoName(card);
      const actions=card.querySelector(".repo-actions");
      if(!name||!actions)return;
      card.dataset.rbhWired="1";
      const starred=(card.querySelector(".repo-meta")?.textContent||"").includes("STARRED");
      const buttons=[
        [starred?"unstar":"star",starred?"UNSTAR":"STAR"],
        ["review","ADD TO REVIEW"],
        ["compare","COMPARE"],
        ["history","VIEW HISTORY"],
        ["readme","VIEW README"],
        ["card","VIEW MANUAL CARD"],
      ];
      for(const [action,label] of buttons){
        const b=document.createElement("button");
        b.className="mini";
        if(action==="star"||action==="unstar")b.classList.add("star");
        b.dataset.rbhAction=action;
        b.dataset.rbhRepo=name;
        b.textContent=label;
        actions.appendChild(b);
      }
    });
  }

  async function repoAction(button){
    const action=button.dataset.rbhAction;
    const full_name=button.dataset.rbhRepo;
    if(!action||!full_name)return;
    try{
      if(action==="star"||action==="unstar"){
        const data=await request(action==="star"?"/api/star":"/api/unstar",{
          method:"POST",
          body:JSON.stringify({full_name})
        });
        button.dataset.rbhAction=action==="star"?"unstar":"star";
        button.textContent=action==="star"?"UNSTAR":"STAR";
        receipt(`repo.${action}`,"LIVE",{full_name});
        showData(`${full_name} · ${action.toUpperCase()}`,data);
        return;
      }
      if(action==="review"){
        const data=await request("/api/note",{
          method:"POST",
          body:JSON.stringify({namespace:"review",object_key:full_name,note:"REVIEW_QUEUE"})
        });
        receipt("repo.review.add","LIVE",{full_name});
        showData(`${full_name} · ADD TO REVIEW`,data);
        return;
      }
      if(action==="compare"){
        return showData(`${full_name} · COMPARE`,await request(`/api/compare?full_name=${encodeURIComponent(full_name)}`));
      }
      if(action==="history"){
        return showData(`${full_name} · HISTORY`,await request(`/api/history?full_name=${encodeURIComponent(full_name)}`));
      }
      if(action==="card"){
        return showData(`${full_name} · MANUAL CARD`,await request(`/api/manual-card?full_name=${encodeURIComponent(full_name)}`));
      }
      if(action==="readme"){
        return showData(`${full_name} · README AUDIT`,await request("/api/readme",{
          method:"POST",
          body:JSON.stringify({full_name})
        }));
      }
    }catch(err){
      receipt(`repo.${action}`,"HOLD",{full_name,error:String(err.message||err)});
      showData(`${full_name} · HOLD`,{status:"HOLD",action,error:String(err.message||err)});
    }
  }

  function wireRepoActions(){
    document.addEventListener("click",e=>{
      const b=e.target.closest("[data-rbh-action]");
      if(!b)return;
      e.preventDefault();
      e.stopImmediatePropagation();
      repoAction(b);
    },true);
    decorateRepoActions();
    new MutationObserver(decorateRepoActions).observe(document.body,{childList:true,subtree:true});
  }

  setTimeout(()=>{
    wireSaveSettings();
    wireRefreshEverything();
    wireExportEverything();
    wireManualButtons();
    wireBackendSearch();
    wireRepoActions();
    log("Canonical GUI backend adapter wired: full refresh, ZIP export, manuals, search, repo actions, runtime/config bridge");
  },0);
})();
