'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.join(__dirname,'../app/src/main/assets');
const adapter=fs.readFileSync(path.join(root,'web_adapter.js'),'utf8');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const app=fs.readFileSync(path.join(root,'app.js'),'utf8');
const css=fs.readFileSync(path.join(root,'ui.css'),'utf8');

test('browser uses shared shell, same-origin API and session scoped token storage',()=>{
  assert.ok(html.includes('web_adapter.js'));
  assert.ok(html.includes("connect-src 'self'"));
  assert.ok(adapter.includes('new URL(value, location.origin)'));
  assert.ok(adapter.includes('url.origin !== location.origin'));
  assert.ok(adapter.includes("!['GET','POST'].includes(verb)"));
  assert.ok(adapter.includes("headers.Authorization = 'Bearer ' + token"));
  assert.ok(adapter.includes("headers['X-Portal-Company']"));
  assert.ok(adapter.includes("credentials:'same-origin'"));
  assert.ok(adapter.includes("redirect:'error'"));assert.ok(!adapter.includes('httpStatus:response.status, data'));
  assert.ok(!/[?&]token=/i.test(adapter));
  assert.ok(app.includes('browserClient?sessionStorage:localStorage'));
  assert.ok(app.includes('sessionStorage.clear()'));
});

test('browser adapter bounds file data and matches filename extension to MIME',()=>{
  for(const value of ['MAX_BYTES = 20 * 1024 * 1024','MAX_BASE64','validFile','URL.createObjectURL','URL.revokeObjectURL']) assert.ok(adapter.includes(value),value);
  for(const value of ['application/pdf','.pdf','application/vnd.openxmlformats-officedocument.spreadsheetml.sheet','.xlsx','application/json','.json','image/webp','.webp','text/plain','.txt']) assert.ok(adapter.includes(value),value);
});

test('Web Share cancellation is explicit and native-only controls are hidden',()=>{
  assert.ok(adapter.includes("error.name === 'AbortError'"));
  assert.ok(adapter.includes("cancelled:error && error.name === 'AbortError'"));
  assert.ok(!adapter.includes('.catch(()=>result(id,download'));
  assert.ok(css.includes('[data-action="serverSettings"]'));
  assert.ok(css.includes('[data-action="checkUpdates"]'));
  assert.ok(css.includes('Web-клиент обновляется автоматически'));
  assert.ok(adapter.includes("document.documentElement.classList.add('web-client')"));
});

test('Desktop cache is company-scoped, encrypted by native bridge and never used for auth',()=>{
  for(const value of ['portalDesktopCache','setCacheCompany','cacheCompany','CACHEABLE','cacheRead','cacheWrite','ClearCompany','30 * 24 * 60 * 60 * 1000','queueMutation','pendingMutations','removeMutation']) assert.ok(adapter.includes(value),value);
  assert.ok(app.includes("PortalNative.setCacheCompany(String(S.company?.id||S.me.company_id||''))"));
  assert.ok(app.includes("PortalNative.setCacheCompany(String(c.id))"));
  assert.ok(!adapter.includes("CACHEABLE = [/^\\/api\\/(?:login|me|platform)"));
  assert.ok(adapter.includes("verb === 'GET' && !!token && !!cacheCompany"));
  assert.ok(adapter.includes("INVALIDATES_CACHE.test(target)"));
});

test('local-first performance contract uses long cache, 10-minute sync, bulk tariffs and parallel dashboard',()=>{
  const production=fs.readFileSync(path.join(root,'production.js'),'utf8');
  assert.match(adapter,/CACHE_MAX_AGE_MS = 30 \* 24 \* 60 \* 60 \* 1000/);
  assert.match(production,/LOCAL_SYNC_INTERVAL_MS=10\*60\*1000/);
  assert.match(production,/productionGet\('tariff-history'\)/);
  assert.doesNotMatch(production,/c\.operations\.map\(async o=>\[o\.id,await productionGet\('tariff-history\?operation_id='/);
  assert.match(production,/const \[d,organizerRows,organizerRequestIncoming,organizerRequestMine,timers\]=await Promise\.all/);
  assert.match(production,/queueLocalWork\(payload,requestId\)/);
});
