'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const assets=path.join(__dirname,'../app/src/main/assets');
const source=fs.readFileSync(path.join(assets,'preview.js'),'utf8');
const index=fs.readFileSync(path.join(assets,'index.html'),'utf8');
const start=source.indexOf('  screens.dashboard=async()=>{');
const end=source.indexOf('\n  actions.previewFeature=',start);
assert.ok(start>0&&end>start,'management dashboard override found');
const dashboard=source.slice(start,end);

function app(){
  const pending=new Map(),paints=[],calls=[];
  const loader={textContent:'Загружаем показатели за сегодня.'};
  const state={stage3:true,me:{role:'admin',display_name:'TEST'},page:'dashboard',
    view:1,epoch:5,token:'TEST_ONLY',company:{id:1},productionTasks:[],activeTimers:[]};
  const content={querySelector:selector=>selector==='[data-management-loading]'?loader:null};
  const scope={
    screens:{},managementRoles:new Set(['admin','director','platform_owner']),S:state,
    liveDashboard:()=>calls.push('normal-dashboard'),
    quick:(page,icon,title)=>'<button data-page="'+page+'">'+title+'</button>',
    heading:(title,str,action)=>'<h1>'+title+'</h1><p>'+str+'</p>'+action,
    btn:label=>'<button>'+label+'</button>',
    paint:html=>paints.push(String(html)),
    $:()=>content,can:()=>true,allowed:()=>false,currentPayrollBounds:()=>null,
    productionGet:name=>{calls.push(name);return new Promise((resolve,reject)=>pending.set(name,{resolve,reject}));},
    tickElapsed:()=>{},date:v=>String(v||''),num:v=>String(v||0),rub:v=>String(v||0),
    esc:v=>String(v||''),PortalCore:{timeGreeting:()=> 'Добрый вечер'},
    icon:()=>'',attentionHtml:()=>'<p>Нет задач</p>',previewBadge:'<span>Preview</span>',
    taskCards:()=>'',console
  };
  vm.runInNewContext(dashboard,scope);
  return {scope,state,paints,pending,calls,loader};
}

test('the actual last-loaded admin dashboard never waits for network to show navigation',async()=>{
  const a=app();
  await a.scope.screens.dashboard();
  assert.equal(a.paints.length,1);
  assert.match(a.paints[0],/PORTAL Сегодня/);
  assert.match(a.paints[0],/Все разделы/);
  assert.match(a.paints[0],/director-hero/);
  assert.match(a.paints[0],/today-grid/);
  assert.match(a.paints[0],/attention-zone/);
  assert.match(a.paints[0],/money-grid/);
  assert.match(a.paints[0],/dashboard-two/);
  assert.match(a.paints[0],/production-strip/);
  assert.match(a.paints[0],/quick-grid/);
  assert.match(a.paints[0],/Клиенты/);
  assert.match(a.paints[0],/Склад/);
  assert.match(a.paints[0],/Зарплата/);
  assert.ok(a.pending.has('today'));
});
test('today GET failure keeps functional dashboard instead of a global error screen',async()=>{
  const a=app();
  await a.scope.screens.dashboard();
  a.pending.get('today').reject(new Error('DNS: unavailable'));
  await new Promise(setImmediate);
  assert.equal(a.paints.length,1);
  assert.match(a.loader.textContent,/Показатели временно недоступны/);
  assert.match(a.paints[0],/Финансовый радар/);
  assert.match(a.paints[0],/Быстрые действия/);
  assert.doesNotMatch(a.paints[0],/Не удалось загрузить/);
});
test('successful today response renders the real director dashboard instead of a spinner',async()=>{
  const a=app();
  await a.scope.screens.dashboard();
  a.pending.get('today').resolve({date:'2026-10-17',today_quantity:42,attention:[],tasks:[],finance:null});
  await new Promise(setImmediate);
  assert.equal(a.paints.length,2);
  assert.match(a.paints[1],/PORTAL Сегодня/);
  assert.match(a.paints[1],/42/);
  assert.match(a.paints[1],/Быстрые действия/);
});
test('late management response cannot repaint a different page or new user session',async()=>{
  const a=app();
  await a.scope.screens.dashboard();
  a.state.view++;a.state.page='work';
  a.pending.get('today').resolve({today_quantity:12,attention:[],tasks:[]});
  await new Promise(setImmediate);
  assert.equal(a.paints.length,1);
});
test('later preview override is guarded and non-blocking as shipped on Android/Desktop',()=>{
  assert.ok(index.indexOf('production_part3.js')<index.indexOf('preview.js'));
  assert.match(dashboard,/S\.managementDashboardSeq=\(S\.managementDashboardSeq\|\|0\)\+1/);
  assert.match(dashboard,/const renderSummary=\(\)=>\{/);
  assert.match(dashboard,/void productionGet\('today'\)\.then\(data=>/);
  assert.doesNotMatch(dashboard,/await Promise\.all\(/);
  assert.match(dashboard,/if\(!live\(\)\)return;/);
  assert.match(dashboard,/data-management-loading/);
});
