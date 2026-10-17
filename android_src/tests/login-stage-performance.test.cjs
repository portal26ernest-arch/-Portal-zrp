'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const source=fs.readFileSync(path.join(__dirname,'../app/src/main/assets/app.js'),'utf8');
const native=fs.readFileSync(path.join(__dirname,'../app/src/main/java/ru/portal/app/MainActivity.java'),'utf8');
const start=source.indexOf('async function enterApp(){');
const end=source.indexOf('\nfunction logout(',start);
assert.ok(start>=0&&end>start,'enterApp found');

test('authenticated shell opens before slow dashboard loads',async()=>{
  let resolveDashboard;
  const dashboard=new Promise(resolve=>{resolveDashboard=resolve;});
  const calls=[];
  const classes=[];
  const state={me:{role:'packer',company_id:1},token:'TEST_ONLY',company:null,stage3:false};
  const nativeBridge={setCacheCompany:()=>true};
  const elements={auth:{classList:{add:()=>classes.push('auth-hidden'),remove:()=>classes.push('auth-visible')}},app:{classList:{add:()=>classes.push('app-hidden'),remove:()=>classes.push('app-visible')}},nav:{classList:{remove:()=>{}}}};
  const scope={
    S:state,
    PortalCore:{roles:{packer:true}},
    PortalNative:nativeBridge,window:{PortalNative:nativeBridge},
    isOwner:()=>false,
    api:async(method,p)=>{calls.push(p);return p==='/api/v3/meta'?{ready:false,company:{id:1,name:'TEST'}}:{company:{id:1,name:'TEST'}};},
    configureProduction:async()=>{},
    reportStageTime:(name)=>calls.push('stage:'+name),
    bootstrapRetryTimer:null,clearTimeout:()=>{},
    savePortalSession:()=>{},
    updateHeader:()=>{},
    $:id=>elements[id],
    go:()=>{calls.push('dashboard-started');return dashboard;},
    handleError:()=>{},setTimeout:()=>{},
    logout:()=>{},Error,Date
  };
  vm.runInNewContext(source.slice(start,end)+';this.enterApp=enterApp;',scope);
  await scope.enterApp();
  assert.deepEqual(classes,['auth-hidden','app-visible']);
  assert.ok(calls.includes('dashboard-started'));
  assert.equal(calls.filter(x=>x==='/api/v3/meta').length,1);
  assert.ok(!calls.includes('/api/company'),'company details are not part of the critical path');
  assert.equal(state.company.name,'TEST');
  assert.ok(calls.includes('stage:company'));
  assert.ok(!calls.includes('dashboard-resolved'));
  resolveDashboard();await Promise.resolve();await Promise.resolve();
});
test('startup does not crowd dashboard with redundant meta refreshes',()=>{
  const production=fs.readFileSync(path.join(__dirname,'../app/src/main/assets/production_part1.js'),'utf8');
  const bundled=fs.readFileSync(path.join(__dirname,'../app/src/main/assets/production.js'),'utf8');
  for(const code of [production,bundled]){
    assert.match(code,/refreshLocalPendingCount\(\)\.then\(count=>\{/);
    assert.match(code,/if\(count>0\)void syncLocalOutbox\(\)/);
    assert.doesNotMatch(code,/void refreshLocalPendingCount\(\);void syncLocalOutbox\(\)/);
  }
  assert.match(source,/prewarmLocalData\(\);\},45000\)/);
});

test('performance markers are constrained to staging and fixed event names',()=>{
  assert.match(native,/if \(!BuildConfig\.APPLICATION_ID\.endsWith\("\.staging"\)\) return;/);
  assert.match(native,/"auth"\.equals\(stage\)/);
  assert.match(native,/"company"\.equals\(stage\)/);
  assert.match(native,/"dashboard"\.equals\(stage\)/);
  assert.match(native,/"PortalTiming"/);
  assert.match(source,/reportStageTime\('auth',authStart\)/);
  assert.match(source,/reportStageTime\('company',companyStart\)/);
  assert.match(source,/reportStageTime\('dashboard',dashboardStart\)/);
});
