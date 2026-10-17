'use strict';
// No live credentials/production traffic: execute the real request-counting code in a VM.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const app=fs.readFileSync(path.join(__dirname,'../app/src/main/assets/app.js'),'utf8');
const production=fs.readFileSync(path.join(__dirname,'../app/src/main/assets/production.js'),'utf8');
const shard=fs.readFileSync(path.join(__dirname,'../app/src/main/assets/production_part1.js'),'utf8');
const guardSource=app.slice(app.indexOf('function canLeave(){'),app.indexOf('function clearCompanyData(){'));
const apiSource=app.slice(app.indexOf('async function api(method,path,body,options={}){'),app.indexOf('let sheetFocus=null'));
assert.ok(guardSource.includes('function canNavigate'), 'navigation guard found');
assert.ok(apiSource.includes('backgroundWrites'), 'request counters found');

function harness(){
  const calls=[],waiters=[],warnings=[];
  const state={writes:0,backgroundWrites:0,epoch:0,view:0,
    me:{id:4,role:'packer'},company:{id:1},token:'test-not-a-real-token',localDataView:0};
  const native={
    requestAsync(id,method,url,body,token,company){
      calls.push({method,url,body,token,company});
    }
  };
  const context={S:state,window:{PortalNative:native},PortalNative:native,
    isOwner:()=>false,toast:m=>warnings.push(m),markLocalData:()=>{},
    nativePromise:start=>new Promise(resolve=>{start(String(waiters.length+1));waiters.push(resolve);}),
    confirmSheet:()=>Promise.resolve(true),logout:()=>{},console};
  vm.runInNewContext(guardSource+apiSource+';this.api=api;this.canNavigate=canNavigate;this.canLeave=canLeave;',context);
  return {state,warnings,calls,ctx:context,
    finish:(index,result={ok:true})=>waiters[index](result)};
}

test('heartbeat POST cannot block navigation, sheet or logout',async()=>{
  const h=harness();
  const p=h.ctx.api('POST','/api/v3/heartbeat',{}, {global:true,passive:true});
  assert.equal(h.state.writes,0);
  assert.equal(h.ctx.canNavigate(),true);
  assert.equal(h.ctx.canLeave(),true);
  h.finish(0);await p;
  assert.equal(h.state.writes,0);
});
test('a financial POST marked passive still blocks navigation and logout',async()=>{
  const h=harness();
  const p=h.ctx.api('POST','/api/v3/work',{quantity:1}, {global:true,passive:true});
  assert.equal(h.state.writes,1);
  assert.equal(h.ctx.canNavigate(),false);
  assert.equal(h.ctx.canLeave(),false);
  h.finish(0);await p;
  assert.equal(h.state.writes,0);
});
test('background outbox replay allows navigation but blocks logout/company switch',async()=>{
  const h=harness();
  const p=h.ctx.api('POST','/api/v3/work',{request_id:'test-only'}, {global:true,backgroundWrite:true});
  assert.equal(h.state.writes,1);
  assert.equal(h.state.backgroundWrites,1);
  assert.equal(h.ctx.canNavigate(),true);
  assert.equal(h.ctx.canLeave(),false);
  h.state.view++; // The queued write is still valid after navigating to another screen.
  h.finish(0);await p;
  assert.equal(h.state.writes,0);
  assert.equal(h.state.backgroundWrites,0);
  assert.equal(h.ctx.canLeave(),true);
  assert.equal(h.calls.filter(x=>x.method==='POST').length,1);
});
test('a user-initiated write is blocking even during background replay',async()=>{
  const h=harness();
  const queue=h.ctx.api('POST','/api/v3/work',{request_id:'queued'}, {global:true,backgroundWrite:true});
  const user=h.ctx.api('POST','/api/v3/invoices',{quantity:1});
  assert.equal(h.state.writes,2);
  assert.equal(h.state.backgroundWrites,1);
  assert.equal(h.ctx.canNavigate(),false);
  h.finish(1);await user;
  assert.equal(h.ctx.canNavigate(),true);
  assert.equal(h.ctx.canLeave(),false);
  h.finish(0);await queue;
  assert.equal(h.ctx.canLeave(),true);
});
test('network failure cannot leak the write counters',async()=>{
  const h=harness();
  const p=h.ctx.api('POST','/api/v3/work',{request_id:'queued'}, {global:true,backgroundWrite:true});
  h.finish(0,{ok:false,network:true,error:'offline'});
  await assert.rejects(p,/Не удалось подтвердить запись/);
  assert.equal(h.state.writes,0);
  assert.equal(h.state.backgroundWrites,0);
  assert.equal(h.ctx.canNavigate(),true);
});
test('unapproved background write cannot bypass navigation protections',async()=>{
  const h=harness();
  const p=h.ctx.api('POST','/api/v3/invoices',{value:1}, {global:true,backgroundWrite:true});
  assert.equal(h.state.writes,1);
  assert.equal(h.state.backgroundWrites,0);
  assert.equal(h.ctx.canNavigate(),false);
  h.finish(0);await p;
  assert.equal(h.state.writes,0);
});
test('all navigation entry points use the navigation guard, protected exits keep canLeave',()=>{
  assert.match(app,/async function go\(page,options=\{\}\)\{if\(!canNavigate\(\)\)return;/);
  assert.match(app,/window\.portalBack=\(\)=>\{[^;]*;[^;]*;if\(!canNavigate\(\)\)return true;/);
  assert.match(app,/window\.portalHome=\(\)=>\{[^;]*;if\(!canNavigate\(\)\)return true;/);
  assert.match(app,/actions\.logout=async\(\)=>\{\s*if\(!canLeave\(\)\)return;/);
  assert.match(app,/actions\.selectCompany=async button=>\{if\(!canLeave\(\)\)return;/);
  assert.match(production,/api\('POST','\/api\/v3\/heartbeat',\{\}, \{global:true,passive:true\}\)/);
  assert.match(production,/api\('POST',row\.path,row\.body,\{global:true,backgroundWrite:true\}\)/);
  assert.match(shard,/api\('POST','\/api\/v3\/heartbeat',\{\}, \{global:true,passive:true\}\)/);
  assert.match(shard,/api\('POST',row\.path,row\.body,\{global:true,backgroundWrite:true\}\)/);
});
