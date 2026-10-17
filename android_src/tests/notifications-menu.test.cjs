'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const all=fs.readFileSync(path.join(__dirname,'../app/src/main/assets/preview.js'),'utf8');
const a=all.indexOf('  screens.notifications=async()=>{');
const b=all.indexOf('\n  screens.clients=async()=>{',a);
assert.ok(a>0&&b>a,'actual notification override found');
const source=all.slice(a,b);

function setup(){
  const updates={events:{innerHTML:'Проверяем события'},channels:{innerHTML:'Загружаем каналы'}};
  let finishToday,failToday,finishUpdates;
  const pendingToday=new Promise((yes,no)=>{finishToday=yes;failToday=no;});
  const pendingUpdates=new Promise(yes=>{finishUpdates=yes;});
  const painted=[];
  const state={page:'notifications',view:5,epoch:3,token:'TEST_ONLY',company:{id:7},stage3:true};
  const scope={screens:{},S:state,
    heading:()=>'<h1>Уведомления</h1>',
    previewCard:()=>'<section>WMS / TalAnt</section>',
    paint:html=>painted.push(html),
    $:id=>({querySelector:selector=>selector==='[data-notification-events]'?updates.events:selector==='[data-notification-channels]'?updates.channels:null}),
    productionGet:pathname=>{assert.equal(pathname,'today');return pendingToday;},
    portalUpdateControlChannel:()=>pendingUpdates,
    attentionHtml:rows=>'<p>Событий: '+rows.length+'</p>',
    controlChannelHtml:item=>'<p>'+item.title+'</p>',
    console
  };
  vm.runInNewContext(source,scope);
  return {scope,state,painted,updates,finishToday,failToday,finishUpdates};
}

test('notifications menu renders the approved sections without waiting for network',async()=>{
  const h=setup();
  await h.scope.screens.notifications();
  assert.equal(h.painted.length,1);
  assert.match(h.painted[0],/Текущие события/);
  assert.match(h.painted[0],/Каналы контроля/);
  assert.match(h.painted[0],/WMS \/ TalAnt/);
  assert.match(h.painted[0],/Загружаем каналы контроля/);
});
test('failed event request never collapses the notifications menu',async()=>{
  const h=setup();
  await h.scope.screens.notifications();
  h.failToday(new Error('DNS timeout'));
  await new Promise(setImmediate);
  assert.match(h.updates.events.innerHTML,/События временно недоступны/);
  assert.equal(h.painted.length,1);
  h.finishUpdates({id:'portal_update',title:'Обновление PORTAL'});
  await new Promise(setImmediate);
  assert.match(h.updates.channels.innerHTML,/Обновление PORTAL/);
});
test('successful reads populate event and control panels without repainting navigation',async()=>{
  const h=setup();
  await h.scope.screens.notifications();
  h.finishUpdates({id:'portal_update',title:'Обновление PORTAL'});
  h.finishToday({attention:[{id:1}],control_channels:[{id:'material_low',title:'Склад'}]});
  await new Promise(setImmediate);
  assert.match(h.updates.events.innerHTML,/Событий: 1/);
  assert.match(h.updates.channels.innerHTML,/Обновление PORTAL/);
  assert.match(h.updates.channels.innerHTML,/Склад/);
  assert.equal(h.painted.length,1);
});
test('delayed responses never modify another screen or company',async()=>{
  const h=setup();
  await h.scope.screens.notifications();
  h.state.page='clients';h.state.view++;
  h.finishToday({attention:[{id:1}],control_channels:[]});
  h.finishUpdates({title:'Do not paint'});
  await new Promise(setImmediate);
  assert.equal(h.updates.events.innerHTML,'Проверяем события');
  assert.equal(h.updates.channels.innerHTML,'Загружаем каналы');
});
test('notifications do not await either remote request to complete the navigation',()=>{
  assert.match(source,/void productionGet\('today'\)\.then\(/);
  assert.match(source,/void portalUpdateControlChannel\(\)\.then\(/);
  assert.doesNotMatch(source,/await productionGet\('today'\)/);
  assert.doesNotMatch(source,/await portalUpdateControlChannel\(\)/);
});
