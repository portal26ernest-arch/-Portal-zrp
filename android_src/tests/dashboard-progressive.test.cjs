'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const prod=fs.readFileSync(path.join(__dirname,'../app/src/main/assets/production.js'),'utf8');
const start=prod.indexOf('screens.dashboard=async()=>{');
const end=prod.indexOf('\nscreens.work=async()=>{',start);
assert.ok(start>0&&end>start,'real production dashboard source found');
const actualDashboard=prod.slice(start,end);
function harness(){
  const paints=[],requests=[],waits=new Map();
  const state={stage3:true,view:7,epoch:2,token:'TEST_TOKEN',page:'dashboard',
    company:{id:12},me:{role:'admin'},productionTasks:[],activeTimers:[]};
  const content={querySelector:()=>null};
  const scope={
    screens:{},previous:{dashboard:()=>{}},S:state,
    $:()=>content,paint:html=>paints.push(String(html)),
    heading:(title,subtitle,action='')=>'<h1>'+title+'</h1><p>'+subtitle+'</p>'+action,
    btn:(title,action)=>'<button>'+title+'</button>',
    can:page=>page==='work'||page==='organizer',
    allowed:()=>false,canCreateDirectorRequest:()=>false,
    productionGet:name=>{requests.push(name);return new Promise((yes,no)=>{waits.set(name,{yes,no});});},
    num:String,rub:String,date:String,esc:String,metric:()=>'',taskCards:()=>'',icon:()=>'',tickElapsed:()=>{},
    console
  };
  vm.runInNewContext(actualDashboard,scope);
  return {scope,state,paints,requests,waits,resolve:(name,v)=>waits.get(name).yes(v)};
}
test('dashboard shows usable navigation without waiting for today or organizer responses',async()=>{
  const h=harness();
  const pending=h.scope.screens.dashboard();
  assert.equal(h.paints.length,1);
  assert.match(h.paints[0],/Рабочее место готово/);
  assert.match(h.paints[0],/Перейти к работе/);
  assert.match(h.paints[0],/Все разделы/);
  assert.ok(h.requests.includes('today'));
  assert.ok(h.requests.includes('organizer?scope=incoming'));
  h.resolve('today',{date:'2026-10-17',mode:'worker',own_quantity:7,own_salary:250,tasks:[]});
  await pending;
  assert.ok(h.paints.length>=2);
  assert.match(h.paints.at(-1),/Мой рабочий день/);
  assert.match(h.paints.at(-1),/7/);
  h.resolve('organizer?scope=incoming',[]);
  await Promise.resolve();
});
test('late dashboard results cannot repaint a different screen or a new account session',async()=>{
  const h=harness();
  const pending=h.scope.screens.dashboard();
  h.state.page='work';
  h.state.view++;
  h.resolve('today',{date:'2026-10-17',mode:'worker',own_quantity:200,tasks:[]});
  await pending;
  assert.equal(h.paints.length,1);
  h.resolve('organizer?scope=incoming',[{title:'old task',due_at:'2026-10-18'}]);
  await Promise.resolve();
  assert.equal(h.paints.length,1);
});
test('optional organizer failure does not block today, work or navigation',async()=>{
  const h=harness();
  const pending=h.scope.screens.dashboard();
  h.resolve('today',{date:'2026-10-17',mode:'worker',own_quantity:2,tasks:[]});
  await pending;
  const painted=h.paints.length;
  h.waits.get('organizer?scope=incoming').no(new Error('VPN offline'));
  await Promise.resolve();
  await Promise.resolve();
  assert.equal(h.paints.length,painted);
});
test('dashboard renderer has a one-way latest-request guard and independent optional reads',()=>{
  assert.match(actualDashboard,/S\.dashboardLoadSeq=\(S\.dashboardLoadSeq\|\|0\)\+1/);
  assert.match(actualDashboard,/const live=\(\)=>S\.page==='dashboard'&&S\.view===view&&S\.epoch===epoch/);
  assert.match(actualDashboard,/Promise\.allSettled\(\[/);
  assert.match(actualDashboard,/todayData=await productionGet\('today'\)/);
  assert.match(actualDashboard,/if\(!todayData\|\|!live\(\)\)return/);
  assert.match(actualDashboard,/if\(todayData&&auxiliary\.some\(rows=>rows\.length\)\)render\(\)/);
});
