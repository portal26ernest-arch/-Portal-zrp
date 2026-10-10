'use strict';
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const root=path.join(__dirname,'../app/src/main/assets');
const adapter=fs.readFileSync(path.join(root,'web_adapter.js'),'utf8');
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
const app=fs.readFileSync(path.join(root,'app.js'),'utf8');
const css=fs.readFileSync(path.join(root,'ui.css'),'utf8');

test('browser uses shared shell, same-origin API and session scoped token storage',()=>{
  assert.ok(html.includes('build_meta.js'));
  assert.ok(html.includes('web_adapter.js'));
  assert.ok(adapter.includes('getAppMetadata: appMetadata'));
  assert.ok(adapter.includes('__PORTAL_BUILD_METADATA__'));
  assert.ok(html.includes("connect-src 'self'"));
  assert.ok(adapter.includes('new URL(value, location.origin)'));
  assert.ok(adapter.includes('url.origin !== location.origin'));
  assert.ok(adapter.includes("!['GET','POST'].includes(verb)"));
  assert.ok(adapter.includes("headers.Authorization = 'Bearer ' + token"));
  assert.ok(adapter.includes("headers['X-Portal-Company']"));
  assert.ok(adapter.includes("credentials:'same-origin'"));
  assert.ok(adapter.includes("redirect:'error'"));assert.ok(!adapter.includes('httpStatus:response.status, data'));
  assert.ok(!/[?&]token=/i.test(adapter));
  assert.ok(app.includes('sessionScopedStorage=browserClient&&!window.__PORTAL_DESKTOP__'));
  assert.ok(app.includes('sessionScopedStorage?sessionStorage:localStorage'));
  assert.ok(app.includes("return PORTAL_AUTOMATIC_SERVERS.has(a)&&PORTAL_AUTOMATIC_SERVERS.has(b)"));
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

test('Desktop cache is company + user + permission scoped, encrypted and fail-safe',()=>{
  for(const value of ['portalDesktopCache','setCacheCompany','setCacheIdentity','cacheCompany','cacheIdentity','cacheScope','CACHEABLE','cacheRead','cacheWrite','ClearCompany','MarkStale','invalidationKeys','30 * 24 * 60 * 60 * 1000','queueMutation','pendingMutations','removeMutation']) assert.ok(adapter.includes(value),value);
  assert.ok(app.includes("PortalNative.setCacheCompany(String(S.company?.id||S.me.company_id||''))"));
  assert.ok(app.includes("PortalNative.setCacheCompany(String(c.id))"));
  assert.ok(adapter.includes("user + '|' + safeRole + '|' + signature"));
  assert.ok(adapter.includes("verb === 'GET' && !!token && !!cacheScope()"));
  assert.ok(adapter.includes("cached:true,stale:cached.stale,cached_at"));
  assert.ok(adapter.includes('FETCH_TIMEOUT_MS = 20 * 1000'));
  assert.ok(adapter.includes('new AbortController()'));
  assert.ok(adapter.includes('signal:controller.signal'));
  for(const endpoint of ['dashboard','payroll\\/mine','work\\/mine','notification-centers','organizer-bootstrap','organizer-requests','payroll-settlements','expenses','presence']) assert.ok(adapter.includes(endpoint),endpoint);
  for(const forbidden of ['/api/login','/api/me','/api/platform','messenger-relay-ticket','code-interpreter']) assert.equal(adapter.includes("CACHEABLE = ['"+forbidden),false,forbidden);
  assert.ok(adapter.includes("invalidationKeys(target).length"));
  assert.ok(app.includes("setCacheIdentity?.('','','[]')"));
  assert.ok(app.includes("setCacheIdentity?.('','')"));
});

test('meta and Organizer stay in the local-first cache contract',()=>{
  assert.match(adapter,/organizer-users\|meta/);
  assert.ok(adapter.includes('/api/v3/organizer-bootstrap'));
  assert.ok(adapter.includes('/api/v3/meta'));
});

test('local-first performance contract uses long cache, 10-minute sync, bulk tariffs and parallel dashboard',()=>{
  const production=fs.readFileSync(path.join(root,'production.js'),'utf8');
  assert.match(adapter,/CACHE_MAX_AGE_MS = 30 \* 24 \* 60 \* 60 \* 1000/);
  assert.match(production,/LOCAL_SYNC_INTERVAL_MS=10\*60\*1000/);
  assert.match(production,/productionGet\('tariff-history'\)/);
  assert.doesNotMatch(production,/c\.operations\.map\(async o=>\[o\.id,await productionGet\('tariff-history\?operation_id='/);
  assert.match(production,/const \[d,organizerRows,organizerRequestIncoming,organizerRequestMine,timers\]=await Promise\.all/);
  assert.match(production,/queueLocalMutation\(path,payload,requestId\)/);
  assert.match(production,/api\('GET','\/api\/v3\/meta'/);
  assert.match(production,/applyProductionMeta\(meta\)/);
  assert.match(production,/setCacheIdentity\?\.\(String\(S\.me\?\.id\|\|''\),String\(S\.me\?\.role\|\|''\),JSON\.stringify\(S\.me\.permissions\)\)/);
  assert.match(app,/LOCAL_PREWARM/);
  assert.match(app,/item\.pages\.some\(page=>can\(page\)\)/);
  assert.match(app,/Локальные данные/);
  assert.match(app,/Связь с сервером временно недоступна\. Работаем с локальными данными\./);
  assert.match(app,/isTransientNetworkError\(e\)&&previousHtml/);
  assert.match(app,/error\.network=true;error\.timeout=true/);
  assert.match(production,/S\.company=\{\.\.\.S\.company,\.\.\.r\.company\}/);
  for(const action of ['work','links','batches','tasks','shipments','returns']) assert.ok(production.includes(`'${action}'`),action);
  assert.doesNotMatch(production,/LOCAL_OUTBOX_PATHS[^\n]*(?:timers|payments|invoices|permissions|settings|tariffs|payroll)/);
  for(const pathName of ['/api/v3/work','/api/v3/links','/api/v3/batches','/api/v3/tasks','/api/v3/shipments','/api/v3/returns']) assert.ok(adapter.includes(`'${pathName}'`),pathName);
  assert.match(production,/if\(error\?\.network\)\{queueError='Нет соединения с сервером';break;\}/);
  assert.match(production,/queueError=error\?\.message\|\|'Одна из локальных записей требует проверки';\s*continue;/);
});
