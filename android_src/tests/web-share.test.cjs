const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const adapter = fs.readFileSync(path.join(__dirname, '../app/src/main/assets/web_adapter.js'), 'utf8');
function browser({share, canShare} = {}) {
  const results = new Map(), timers = [], counters = {created:0,revoked:0,clicked:0};
  const URLApi = class extends URL {};
  URLApi.createObjectURL = () => { counters.created++; return 'blob:portal-file'; };
  URLApi.revokeObjectURL = value => { assert.equal(value,'blob:portal-file'); counters.revoked++; };
  class File { constructor(parts,name,options){this.parts=parts;this.name=name;this.type=options.type;} }
  const context = {
    window:{PortalBridgeResult:(id,value)=>results.set(String(id),JSON.parse(value))},
    location:{protocol:'https:',origin:'https://portal.test'},
    navigator:{share,canShare},URL:URLApi,File,Blob,atob,
    setTimeout:callback=>{timers.push(callback);return timers.length;},
    document:{documentElement:{classList:{add(){}}},body:{append(){}},createElement(){return {click(){counters.clicked++;},remove(){}};}},
    fetch:async()=>{throw new Error('unexpected fetch');}
  };
  vm.runInNewContext(adapter,context,{filename:'web_adapter.js'});
  return {api:context.window.PortalNative,results,timers,counters};
}
const fileArgs=['report.pdf','application/pdf',Buffer.from('%PDF-1.4').toString('base64')];

test('Web Share cancellation reports cancel without forcing a download',async()=>{
  const env=browser({share:()=>Promise.reject(Object.assign(new Error('cancel'),{name:'AbortError'})),canShare:()=>true});
  env.api.shareBase64FileAsync('share-1',...fileArgs);
  await new Promise(resolve=>setImmediate(resolve));
  assert.deepEqual(env.results.get('share-1'),{ok:false,cancelled:true,error:'Отправка отменена'});
  assert.deepEqual(env.counters,{created:0,revoked:0,clicked:0});
});

test('Web Share sends the selected allowlisted file and metadata without creating a download URL',async()=>{
  let sent;
  const env=browser({share:payload=>{sent=payload;return Promise.resolve();},canShare:({files})=>files[0].name==='report.pdf'});
  env.api.shareBase64FileAsync('share-ok',...fileArgs,'finance@example.test','Invoice report','Please review this report');
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(env.results.get('share-ok').shared,true);
  assert.equal(sent.files[0].name,'report.pdf');assert.equal(sent.files[0].type,'application/pdf');
  assert.equal(sent.title,'Invoice report');assert.equal(sent.text,'Please review this report');
  assert.deepEqual(env.counters,{created:0,revoked:0,clicked:0});
});

test('unsupported Web Share safely downloads allowlisted files and revokes object URLs',()=>{
  const env=browser();
  env.api.shareBase64FileAsync('share-2',...fileArgs);
  assert.equal(env.results.get('share-2').ok,true);
  assert.equal(env.counters.created,1);assert.equal(env.counters.clicked,1);assert.equal(env.counters.revoked,0);
  env.timers[0]();assert.equal(env.counters.revoked,1);
});

test('browser without file sharing capability falls back to the safe download path',()=>{
  const env=browser({share:()=>{throw new Error('must not call share');},canShare:()=>false});
  env.api.shareBase64FileAsync('share-fallback',...fileArgs);
  assert.equal(env.results.get('share-fallback').ok,true);
  assert.equal(env.counters.created,1);assert.equal(env.counters.clicked,1);assert.equal(env.counters.revoked,0);
  env.timers[0]();assert.equal(env.counters.revoked,1);
});

test('Web file share rejects mismatched filename and MIME before sharing or downloading',()=>{
  const env=browser({share:()=>Promise.resolve(),canShare:()=>true});
  env.api.shareBase64FileAsync('share-3','report.exe','application/pdf',fileArgs[2]);
  assert.equal(env.results.get('share-3').ok,false);
  assert.deepEqual(env.counters,{created:0,revoked:0,clicked:0});
});
