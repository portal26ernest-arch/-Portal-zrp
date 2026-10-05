(()=>{"use strict";
if(window.__PORTAL_DESKTOP__!==true)return;
const KEYS=new Set(["hello","happy","wow","cheer","sad","sleep","shrug","ok"]);
const SAFE=/^[a-z0-9_][a-z0-9_.-]*\.(?:png|webp|gif|svg)$/i;
const reduced=window.matchMedia?window.matchMedia("(prefers-reduced-motion: reduce)"):null;
let items=[],timer=0,active=null;
const state={enabled:false,catalogLoaded:false,lastKey:null,showCount:0};
window.__PORTAL_DESKTOP_MASCOTS__=state;
const disabled=()=>Boolean(reduced&&reduced.matches);
function ready(){
 const app=document.getElementById("app"),sheet=document.getElementById("sheetBackdrop"),focus=document.activeElement;
 const editing=focus&&(/^(INPUT|TEXTAREA|SELECT)$/.test(focus.tagName)||focus.isContentEditable);
 return Boolean(!document.hidden&&!disabled()&&app&&!app.classList.contains("hidden")&&(!sheet||sheet.classList.contains("hidden"))&&!editing&&!active&&items.length);
}
function delay(first){return(first?45000:120000)+Math.floor(Math.random()*(first?75000:180000));}
function schedule(first=false){
 if(timer)window.clearTimeout(timer);
 if(!state.enabled||disabled())return;
 timer=window.setTimeout(()=>{timer=0;if(ready())show();schedule(false);},delay(first));
}
function pick(){
 if(items.length===1)return items[0];
 const pool=state.lastKey?items.filter(x=>x.key!==state.lastKey):items;
 return pool[Math.floor(Math.random()*pool.length)]||items[0];
}
function remove(){if(!active)return;const node=active;active=null;node.remove();}
function show(){
 if(!ready())return;const item=pick();if(!item)return;
 const host=document.createElement("div");
 host.className="portal-desktop-mascot portal-desktop-mascot--"+item.key;
 host.dataset.side=Math.random()<.5?"left":"right";host.setAttribute("aria-hidden","true");
 const img=document.createElement("img");img.src="stickers/"+item.asset;img.alt="";img.draggable=false;img.decoding="async";
 img.addEventListener("error",remove,{once:true});host.addEventListener("animationend",remove,{once:true});
 host.appendChild(img);document.body.appendChild(host);active=host;state.lastKey=item.key;state.showCount+=1;
}
function style(){
 const el=document.createElement("style");el.id="portal-desktop-mascot-style";
 el.textContent=[
 ".portal-desktop-mascot{position:fixed;bottom:22px;width:88px;height:88px;z-index:18;pointer-events:none;user-select:none;opacity:0;display:flex;align-items:flex-end;justify-content:center;animation:portalMascotVisit 6.4s ease-in-out both}",
 ".portal-desktop-mascot[data-side=left]{left:20px}.portal-desktop-mascot[data-side=right]{right:20px}",
 ".portal-desktop-mascot img{display:block;max-width:88px;max-height:88px;object-fit:contain;filter:drop-shadow(0 5px 9px rgba(0,0,0,.16))}",
 ".portal-desktop-mascot--hello img{animation:portalMascotWave 1s ease-in-out 2}",
 ".portal-desktop-mascot--happy img,.portal-desktop-mascot--cheer img{animation:portalMascotJump .8s ease-in-out 3}",
 ".portal-desktop-mascot--wow img{animation:portalMascotPop 1.1s ease-in-out 2}",
 ".portal-desktop-mascot--sad img{animation:portalMascotSad 2.3s ease-in-out 1}",
 ".portal-desktop-mascot--sleep img{animation:portalMascotSleep 2.7s ease-in-out 1}",
 ".portal-desktop-mascot--shrug img{animation:portalMascotShrug 1.5s ease-in-out 2}",
 ".portal-desktop-mascot--ok img{animation:portalMascotOk 1s ease-in-out 2}",
 "@keyframes portalMascotVisit{0%{opacity:0;transform:translateY(24px) scale(.92)}12%,78%{opacity:1;transform:translateY(0) scale(1)}100%{opacity:0;transform:translateY(18px) scale(.96)}}",
 "@keyframes portalMascotWave{0%,100%{transform:rotate(0)}35%{transform:rotate(-8deg)}70%{transform:rotate(8deg)}}",
 "@keyframes portalMascotJump{0%,100%{transform:translateY(0)}45%{transform:translateY(-14px)}}",
 "@keyframes portalMascotPop{0%,100%{transform:scale(1)}45%{transform:scale(1.12)}}",
 "@keyframes portalMascotSad{0%,100%{transform:translateY(0)}50%{transform:translateY(5px) rotate(-3deg)}}",
 "@keyframes portalMascotSleep{0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}",
 "@keyframes portalMascotShrug{0%,100%{transform:translateX(0)}35%{transform:translateX(-5px)}70%{transform:translateX(5px)}}",
 "@keyframes portalMascotOk{0%,100%{transform:rotate(0) scale(1)}50%{transform:rotate(3deg) scale(1.04)}}",
 "@media (prefers-reduced-motion:reduce){.portal-desktop-mascot{display:none!important}}"
 ].join("");document.head.appendChild(el);
}
async function load(){
 try{
  const r=await fetch("stickers/catalog.json",{credentials:"same-origin",cache:"no-cache"});if(!r.ok)return;
  const data=await r.json(),rows=Array.isArray(data&&data.stickers)?data.stickers:[];
  items=rows.filter(x=>x&&x.enabled===true&&KEYS.has(x.key)&&typeof x.asset==="string"&&SAFE.test(x.asset)&&!x.asset.includes("/")&&!x.asset.includes("\\"));
  state.catalogLoaded=true;state.enabled=items.length>0;if(state.enabled)schedule(true);
 }catch(_){}
}
if(reduced&&typeof reduced.addEventListener==="function")reduced.addEventListener("change",()=>{if(disabled()){if(timer)window.clearTimeout(timer);timer=0;remove();}else if(state.enabled)schedule(true);});
document.addEventListener("visibilitychange",()=>{if(document.hidden)remove();else if(state.enabled&&!timer)schedule(true);});
style();load();
})();