'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const source=fs.readFileSync(path.join(__dirname,'../app/src/main/assets/app.js'),'utf8');
const start=source.indexOf('let bootstrapRetryTimer=null;');
const end=source.indexOf('async function loginRequest(',start);
assert.ok(start>0&&end>start,'post-login recovery code exists');
const recovery=source.slice(start,end);

function context(enterApp=async()=>{}){
  const state={token:'TEST_TOKEN',me:{id:8,role:'admin',company_id:1,permissions:['payroll.all','users.manage']},
    stage3:true,company:{id:1,name:'PORTAL'},page:'dashboard',view:2,bootstrapPending:false};
  const classes=[],painted=[],delayed=[],loginError={textContent:'',classList:{remove:()=>classes.push('error-shown')}};
  const elements={
    auth:{classList:{add:()=>classes.push('auth-hidden')}},
    app:{classList:{remove:()=>classes.push('app-visible')}},
    nav:{classList:{add:()=>classes.push('nav-hidden')}},
    supportStrip:{classList:{add:()=>{}}},
    content:{querySelector:()=>null},
    companyName:{textContent:''},
    loginError
  };
  const stateCall=[];
  const scope={
    S:state,actions:{},$:(id)=>elements[id],
    heading:(title)=>'<h1>'+title+'</h1>',
    btn:(label,action)=>'<button data-action="'+action+'">'+label+'</button>',
    paint:html=>painted.push(html),
    clearTimeout:()=>{},setTimeout:(fn,ms)=>{delayed.push({fn,ms});return 99;},
    document:{hidden:false},
    isTransientNetworkError:error=>!!error.network,
    enterApp:async()=>{stateCall.push('enterApp');return enterApp(state);},
    logout:(refresh,force)=>stateCall.push('logout'),
    console
  };
  vm.runInNewContext(recovery,scope);
  return {scope,state,classes,painted,delayed,stateCall,elements};
}

test('confirmed login survives a meta timeout and never re-requests the PIN',()=>{
  const h=context();
  assert.equal(h.scope.showBootstrapPending({network:true}),true);
  assert.equal(h.state.token,'TEST_TOKEN');
  assert.equal(h.state.me.id,8);
  assert.equal(h.state.me.permissions.length,0);
  assert.equal(h.state.stage3,false);
  assert.equal(h.state.company,null);
  assert.equal(h.state.bootstrapPending,true);
  assert.ok(h.classes.includes('nav-hidden'));
  assert.match(h.painted[0],/Вход подтверждён/);
  assert.match(h.painted[0],/Повторить загрузку/);
  assert.match(h.painted[0],/Повторно вводить PIN не нужно/);
  assert.equal(h.stateCall.length,0,'no POST or logout');
  assert.equal(h.delayed.length,1);
});
test('a manual retry uses the existing session, without POST or credentials',async()=>{
  const h=context(async state=>{state.bootstrapPending=false;});
  h.scope.showBootstrapPending({network:true});
  await h.scope.retryBootstrap();
  assert.deepEqual(h.stateCall,['enterApp']);
  assert.equal(h.state.token,'TEST_TOKEN');
  assert.equal(h.state.bootstrapPending,false);
});
test('a second temporary failure remains in recoverable pending state',async()=>{
  const h=context(async()=>{throw Object.assign(new Error('offline'),{network:true});});
  h.scope.showBootstrapPending({network:true});
  await h.scope.retryBootstrap();
  assert.equal(h.state.bootstrapPending,true);
  assert.equal(h.state.bootstrapAttempts,2);
  assert.equal(h.state.token,'TEST_TOKEN');
  assert.equal(h.stateCall.includes('logout'),false);
});
test('a permanent authorization error leaves the user logged out',async()=>{
  const h=context(async()=>{throw new Error('403');});
  h.scope.showBootstrapPending({network:true});
  await h.scope.retryBootstrap();
  assert.ok(h.stateCall.includes('logout'));
  assert.ok(h.classes.includes('error-shown'));
});
test('bootstrap recovery is guarded across cold restarts and cannot open protected menus',()=>{
  assert.match(source,/if\(isTransientNetworkError\(error\)&&S\.token&&S\.me\)\{showBootstrapPending\(error\);return;\}/);
  assert.match(source,/if\(S\.bootstrapPending\)return;if\(!canNavigate\(\)\)return;/);
  assert.match(source,/S\.bootstrapPending=false;S\.bootstrapAttempts=0/);
  assert.match(source,/if\(!company\|\|Number\(company\.id\)!==Number\(S\.me\.company_id\)\)/);
  assert.match(source,/const metaResult=await api\('GET','\/api\/v3\/meta'/);
  assert.doesNotMatch(source.slice(source.indexOf('async function enterApp(){'),source.indexOf('\nfunction logout(')),
    /await Promise\.all\(\[\s*api\('GET','\/api\/company'/);
});
