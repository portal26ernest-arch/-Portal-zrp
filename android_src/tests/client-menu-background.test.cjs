'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const source=fs.readFileSync(path.join(__dirname,'../app/src/main/assets/preview.js'),'utf8');
const first=source.indexOf('  screens.clients=async()=>{');
const last=source.indexOf('\n  screens.users=async()=>{',first);
assert.ok(first>=0&&last>first,'actual preview client override');
const actual=source.slice(first,last);

function harness(){
  const outstanding=new Map(),inserted=[],events={};
  const clientButton={dataset:{id:'1'}};
  const row={dataset:{},hidden:false,prior:'',
    querySelector:selector=>selector==='[data-action="openClient"]'?clientButton:null,
    insertAdjacentHTML:(pos,html)=>{row.prior+=html;}
  };
  const searchInput={value:'',addEventListener:(name,fn)=>{events[name]=fn;}};
  const search={className:'',innerHTML:'',querySelector:selector=>selector==='input'?searchInput:null};
  const empty={className:'',textContent:'',hidden:true};
  const list={isConnected:true,querySelectorAll:selector=>selector==='.item'?[row]:[],
    before:obj=>{assert.equal(obj,search);},after:obj=>{assert.equal(obj,empty);}};
  const content={querySelector:selector=>selector==='.list'?list:null,insertAdjacentHTML:(position,html)=>inserted.push(html)};
  const S={stage3:true,me:{role:'admin'},page:'clients',view:2,epoch:3,token:'TEMP_TEST_TOKEN',
    company:{id:1},clients:[{id:1,name:'Борискин'}]};
  const scope={S,screens:{},
    liveClients:async()=>{},allowed:permission=>permission==='clients.read',
    $:()=>content,
    document:{createElement:tag=>tag==='label'?search:empty},
    productionGet:pathname=>new Promise((resolve,reject)=>outstanding.set(pathname,{resolve,reject})),
    btn:label=>'<button>'+label+'</button>',
    previewBadge:'<span>Preview</span>',esc:v=>String(v),console};
  vm.runInNewContext(actual,scope);
  return {scope,S,inserted,events,searchInput,row,empty,outstanding};
}

test('client menu returns without waiting for optional historical names',async()=>{
  const a=harness();
  await a.scope.screens.clients();
  assert.ok(a.inserted.length>0,'original client preview actions already present');
  assert.equal(a.row.dataset.clientSearch,'борискин');
  assert.equal(a.row.hidden,false);
  assert.ok(a.outstanding.has('client-name-history'));
  assert.ok(a.outstanding.has('client-aliases'));
  a.searchInput.value='борис';
  a.events.input();
  assert.equal(a.row.hidden,false);
});

test('historical and alias names enrich search when available without changing the screen',async()=>{
  const a=harness();
  await a.scope.screens.clients();
  a.outstanding.get('client-name-history').resolve([{client_id:1,old_name:'Старое название',new_name:'Борискин'}]);
  a.outstanding.get('client-aliases').resolve([{client_id:1,alias:'Борисенко'}]);
  await new Promise(setImmediate);
  assert.match(a.row.dataset.clientSearch,/старое название/);
  assert.match(a.row.dataset.clientSearch,/борисенко/);
  assert.match(a.row.prior,/Ранее: Старое название/);
  a.searchInput.value='борисенко';
  a.events.input();
  assert.equal(a.row.hidden,false);
});

test('late alias replies never edit another page or a changed session',async()=>{
  const a=harness();
  await a.scope.screens.clients();
  a.S.page='dashboard';a.S.view++;
  a.outstanding.get('client-name-history').resolve([{client_id:1,old_name:'Other company'}]);
  a.outstanding.get('client-aliases').resolve([]);
  await new Promise(setImmediate);
  assert.equal(a.row.dataset.clientSearch,'борискин');
  assert.equal(a.row.prior,'');
});

test('nonessential client enrichment must not be awaited before navigation completes',()=>{
  assert.match(actual,/void Promise\.allSettled\(\[/);
  assert.match(actual,/await liveClients\(\)/);
  assert.doesNotMatch(actual,/await productionGet\('client-name-history'\)/);
  assert.doesNotMatch(actual,/await productionGet\('client-aliases'\)/);
});
