// Regression: sign-out must not await a slow DNS probe or server response.
// Pure JS harness; no production API, PIN, DB or installed Android device.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname,'../app/src/main/assets/app.js'),'utf8');
const begin = source.indexOf('async function revokePortalSession(token)');
const end = source.indexOf('async function checkServer()', begin);
assert.ok(begin > 0 && end > begin, 'sign-out implementation found');

function harness({writes = 0, confirm = true} = {}) {
  const events = [];
  let resolveRemote;
  const state = {token:'old-session', epoch:8, writes};
  const native = {
    requestAsync(id, method, url, body, token, company) {
      events.push({id,method,url,body,token,company});
    }
  };
  const c = {
    actions:{},S:state,window:{PortalNative:native},PortalNative:native,
    canLeave:()=>state.writes===0,confirmSheet:async()=>confirm,
    nativePromise:(start,ms)=>new Promise(resolve=>{
      assert.equal(ms,20000);
      resolveRemote=resolve;start('request-1');
    }),
    logout:(refresh,force)=>{
      assert.equal(refresh,false);assert.equal(force,true);
      state.token='';state.epoch++;events.push({localLogout:true});
    },
    toast:(message,bad)=>events.push({message,bad})
  };
  vm.runInNewContext(source.slice(begin,end),c,{timeout:1000});
  return {state,events,actions:c.actions,resolve:response=>resolveRemote?.(response)};
}

test('sign-out clears UI before remote revocation completes, with old token exactly once',async()=>{
  const h=harness();
  await h.actions.logout();
  assert.equal(h.state.token,'');
  assert.equal(h.state.epoch,9);
  assert.equal(h.events[0].url,'/api/logout');
  assert.equal(h.events[0].method,'POST');
  assert.equal(h.events[0].token,'old-session');
  assert.equal(h.events[0].body,'{}');
  assert.equal(h.events.filter(e=>e.url==='/api/logout').length,1);
  assert.equal(h.events[1].localLogout,true);
  h.resolve({ok:true});
  await Promise.resolve();
  assert.equal(h.events.filter(e=>e.bad).length,0);
});

test('server revocation failure is visible but does not restore local token',async()=>{
  const h=harness();
  await h.actions.logout();
  h.resolve({ok:false,network:true});
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(h.state.token,'');
  assert.equal(h.events.filter(e=>e.bad===true).length,1);
});

test('outstanding write blocks both local logout and token revocation',async()=>{
  const h=harness({writes:1});
  await h.actions.logout();
  assert.equal(h.state.token,'old-session');
  assert.equal(h.events.length,0);
});

test('cancelled confirmation cannot revoke or clear a session',async()=>{
  const h=harness({confirm:false});
  await h.actions.logout();
  assert.equal(h.state.token,'old-session');
  assert.equal(h.events.length,0);
});

test('old revocation result cannot change a new session',async()=>{
  const h=harness();
  await h.actions.logout();
  h.state.token='new-session';h.state.epoch++;
  h.resolve({ok:false,network:true});
  await Promise.resolve();await Promise.resolve();
  assert.equal(h.state.token,'new-session');
  assert.equal(h.events.filter(e=>e.bad===true).length,0);
});

test('native recovery cannot serialize DNS probes or log out an unrelated new session',()=>{
  const main=fs.readFileSync(path.join(__dirname,'../app/src/main/java/ru/portal/app/MainActivity.java'),'utf8');
  assert.doesNotMatch(main,/private synchronized String resolveServerForRequest/);
  assert.match(main,/serverProbeInProgress\.compareAndSet\(false, true\)/);
  assert.match(main,/retryServerProbeAtMs = System\.currentTimeMillis\(\) \+ 8_000L/);
  assert.match(main,/private void notifySessionInvalidated\(String requestToken\)/);
  assert.match(main,/requestToken\.equals\(activeSessionToken\)/);
  assert.match(main,/if \(status == 401\) notifySessionInvalidated\(token\)/);
  assert.match(source,/setActiveSessionToken\?\.\(S\.token\)/);
  assert.match(source,/setActiveSessionToken\?\.\(''\)/);
  assert.match(source,/JSON\.parse\(window\.PortalNative\?\.getAppMetadata\?\.\(\)\|\|'\{\}'\)/);
  assert.doesNotMatch(source,/clearMessengerSession|openMessengerProvider/);
});
