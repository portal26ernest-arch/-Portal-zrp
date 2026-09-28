// Run with Node.js and Playwright installed. No production API or database is used.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {pathToFileURL} = require('node:url');
const {chromium} = require('playwright');
const assets = path.resolve(__dirname, '../app/src/main/assets');
const metadata = Object.fromEntries(fs.readFileSync(path.resolve(__dirname,'../release.properties'),'utf8').split(/\r?\n/).filter(l=>l&&!l.startsWith('#')).map(l=>{const i=l.indexOf('=');return [l.slice(0,i),l.slice(i+1)];}));
metadata.versionCode=Number(metadata.versionCode);
metadata.applicationId='ru.portal.app';
const context=vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(assets,'core.js'),'utf8'),context);
const core=context.PortalCore;
async function screenshot(page,name){if(process.env.PORTAL_UI_SCREENSHOTS){fs.mkdirSync(process.env.PORTAL_UI_SCREENSHOTS,{recursive:true});await page.screenshot({path:path.join(process.env.PORTAL_UI_SCREENSHOTS,name+'.png'),fullPage:true});}}

test('all shipped JavaScript parses',()=>{
  for(const file of ['core.js','app.js','screens.js','production.js'])new vm.Script(fs.readFileSync(path.join(assets,file),'utf8'),{filename:file});
});
test('role capabilities and employee linkage',()=>{
  const expected={admin:['work','payroll','clients','materials','invoices','users','jobs'],director:['work','payroll','clients','materials','invoices','jobs'],manager:['work','payroll','clients','invoices','jobs'],packer:['work','payroll','jobs'],shift:['work','payroll','clients','materials','jobs'],accountant:['payroll','clients','materials','invoices','jobs']};
  for(const [role,pages] of Object.entries(expected)){
    for(const m of core.modules)assert.equal(core.can(m.id,{role,telegram_id:101},{id:1}),pages.includes(m.id),role+':'+m.id);
    assert.equal(core.can('work',{role}, {id:1}),false);
    assert.equal(core.can('audit',{role},{id:1}),false);
  }
  assert.equal(core.can('dashboard',{role:'platform_owner'},null),false);
  assert.equal(core.can('users',{role:'platform_owner'},{id:2}),true);
  assert.equal(core.can('work',{role:'platform_owner',telegram_id:101},{id:2}),false);
});
test('updates: unconfigured, offline, current, newer and invalid manifests',()=>{
  const manifest={schemaVersion:1,...metadata,publishedAt:metadata.buildDate,changelog:'Исправления',apkUrl:'https://github.com/portal26ernest-arch/-Portal-zrp/releases/download/test/app.apk',sha256:'a'.repeat(64)};
  const state=m=>core.updateState(metadata,{ok:true,configured:true,manifest:m}).state;
  assert.equal(core.updateState(metadata,{ok:true,configured:false}).state,'unconfigured');
  assert.equal(core.updateState(metadata,{ok:false}).state,'error');
  assert.equal(state(manifest),'latest');
  assert.equal(state({...manifest,versionCode:metadata.versionCode+1}),'available');
  for(const patch of [{channel:'other'},{applicationId:'other'},{versionCode:'4'},{publishedAt:'invalid'},{changelog:null},{apkUrl:'http://example.test/app.apk'},{apkUrl:'https://user@example.test/app.apk'},{sha256:'bad'}])assert.equal(state({...manifest,...patch}),'error');
});

// Emulate only the Java bridge transport; run the actual shipped UI and events.
async function fixture(browser,role='manager',viewport={width:390,height:844},stage3=false){
  const page=await browser.newPage({viewport});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(({role,metadata,stage3})=>{
    localStorage.clear();
    const user={id:1,username:role,display_name:'Тестовый пользователь',role,company_id:1,telegram_id:role==='platform_owner'?null:101};
    const client={id:1,name:'Клиент',active:1};
    window.mock={calls:[],offline:false,rejectWrite:false,hold:false,held:[],update:{ok:true,configured:false},timer:null,stage3Today:null,stage3Permissions:null,presenceOnline:true};
    const respond=(id,data)=>setTimeout(()=>window.PortalBridgeResult(id,JSON.stringify(data)),0);
    window.PortalNative={getServerUrl:()=> 'http://127.0.0.1:8765',getAppMetadata:()=>JSON.stringify(metadata),checkUpdates:id=>respond(id,mock.update),requestAsync(id,method,url,payload,token,company){
      mock.calls.push({method,url,body:payload?JSON.parse(payload):null,token,company});
      if(mock.offline)return respond(id,{ok:false,network:true,error:'Нет соединения'});
      if(mock.rejectWrite&&method==='POST')return respond(id,{ok:false,httpStatus:401});
      let data={ok:true};
      if(stage3&&url==='/api/v3/meta')Object.assign(data,{ready:true,heartbeat_seconds:60,permissions:mock.stage3Permissions||['work.write','tasks.read','tasks.manage','batches.receive','finance.read','invoices.read','invoices.create','users.manage','access.history.read','payroll.own'],catalog:[{code:'work.write',group:'Работа',label:'Вносить свою выработку',recommended:['Сборщик']},{code:'access.history.read',group:'Сотрудники',label:'Просматривать историю входов сотрудников',recommended:['Управляющий','Администратор']}]});
      else if(stage3&&url==='/api/v3/today'){const task={id:'task-1',batch_id:'batch-1',client_name:'Клиент',product:'Коробка',batch_number:'PRT-2026-000001',operation_name:'Упаковка',quantity:10,done:2,remaining:8,status:'in_progress',assignees:[1]};data.data=mock.stage3Today||{date:'2026-09-25',mode:role==='admin'?'management':'worker',own_quantity:4,own_salary:500,attention:[],tasks:[task],...(role==='admin'?{today_quantity:17,in_progress:1,ready:1,active_batches:2,finance:{salary:1200,revenue:2500,profit:900},expected_profit:1500,debt:400}:{})};}
      else if(stage3&&url==='/api/v3/tasks')data.data=[{id:'task-1',batch_id:'batch-1',client_name:'Клиент',product:'Коробка',batch_number:'PRT-2026-000001',operation_name:'Упаковка',quantity:10,done:2,remaining:8,status:'in_progress',assignees:[1]}];
      else if(stage3&&url==='/api/v3/timers'&&method==='GET')data.data=mock.timer&&['running','paused'].includes(mock.timer.status)?[mock.timer]:[];
      else if(stage3&&url==='/api/v3/timers'&&method==='POST'){const b=JSON.parse(payload);mock.timer={id:'timer-1',task_id:'task-1',user_id:1,started_at:'2026-09-25T09:12:00',pauses:[],status:({start:'running',pause:'paused',resume:'running',finish:'completed'})[b.event]};data.data=mock.timer;}
      else if(stage3&&url==='/api/v3/batches')data.data=[{id:'batch-1',number:'PRT-2026-000001',client_id:1,client_name:'Клиент',product:'Коробка',received_at:'2026-09-24',quantity:10,done:2,remaining:8,stage:'in_progress',operations:[{operation:'Упаковка',done:2,planned:10}],ready:false}];
      else if(stage3&&url==='/api/v3/catalog')data.data={clients:[{id:1,name:'Клиент'}],operations:[{id:1,client_id:1,name:'Упаковка'}],users:[]};
      else if(stage3&&url==='/api/v3/works')data.data=[{id:'work-free',client_id:1,client_name:'Клиент',operation_name:'Упаковка',quantity:3,salary:300,completed_at:'2026-09-25T09:20:00',without_task:true,batch_id:null}];
      else if(stage3&&url==='/api/v3/work'&&method==='POST')data.data={id:'work-free',salary:300,without_task:true};
      else if(stage3&&url==='/api/v3/presence')data.data=[{user_id:1,online:mock.presenceOnline,last_activity_at:new Date().toISOString(),active_sessions:mock.presenceOnline?1:0}];
      else if(stage3&&url==='/api/v3/activity')data.data=[{event:'login',result:'success',user_id:1,client_type:'Android',at:'2026-09-25T09:12:00'}];
      else if(stage3&&url==='/api/v3/permissions')data.data=[{id:1,display_name:'Тестовый пользователь',role:'admin',permissions:['work.write']}];
      if(url==='/api/ping')data.setup_required=false;
      else if(url.endsWith('/login'))Object.assign(data,{token:'fixture-token',user});
      else if(url==='/api/me')data.user=user;
      else if(url==='/api/company')data.company={id:1,name:'PORTAL'};
      else if(url.startsWith('/api/dashboard'))data.data={quantity:103,salary:206,revenue:515,debt:100,profit:300};
      else if(url==='/api/platform/companies')data.companies=[{id:1,name:'PORTAL',status:'active'},{id:2,name:'Вторая компания',status:'active'}];
      else if(url==='/api/platform/audit')data.rows=[];
      else if(url.endsWith('/operations'))Object.assign(data,{client,operations:[{id:1,name:'Упаковка',employee_rate:2,client_rate:5,active:1}]});
      else if(url==='/api/work')data.work={salary:8,warnings:[]};
      else if(url==='/api/work/mine')data.rows=[];
      else if(url==='/api/payroll/mine')data.data={quantity:4,accrued:8,paid:0,remaining:8};
      else if(url==='/api/jobs')data.jobs=[];
      else if(url==='/api/materials')data.materials=[];
      else if(url==='/api/invoices')data.invoices=[];
      else if(url==='/api/users')Object.assign(data,{users:[user],employees:[{telegram_id:101,full_name:'Сотрудник'}],roles:{admin:'Администратор',manager:'Менеджер',packer:'Сотрудник'}});
      else if(url.endsWith('/clients'))data.clients=[client];
      else if(url==='/api/clients/1')Object.assign(data,{client,stats:{},requisites:{}});
      if(mock.hold&&url.startsWith('/api/dashboard'))mock.held.push(()=>respond(id,data));else respond(id,data);
    }};
  },{role,metadata,stage3});
  await page.goto(pathToFileURL(path.join(assets,'index.html')).href);
  await page.waitForFunction(()=>document.querySelector('#serverState').textContent==='Подключение готово');
  return {page,errors};
}
async function login(page){
  await page.locator('#loginUser').fill('tester');await page.locator('#loginPin').fill('1234');await page.locator('#loginSubmit').click();
  await page.waitForFunction(()=>!document.querySelector('#app').classList.contains('hidden')&&!document.querySelector('.loading'));
}
test('browser UI regression',async t=>{
  const browser=await chromium.launch({headless:true,...(process.env.PORTAL_BROWSER_PATH?{executablePath:process.env.PORTAL_BROWSER_PATH}:{})});
  try{
    await t.test('login at phone/tablet sizes, themes, metadata and update failures',async()=>{
      for(const width of [320,390,768]){
        const {page,errors}=await fixture(browser,'manager',{width,height:844});
        assert.match(await page.locator('#authCredit').innerText(),/Вартанян Эрнест/);
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
        if(width===390)await screenshot(page,'login');
        await login(page);if(width===390)await screenshot(page,'dashboard-manager');await page.evaluate(()=>go('about'));
        assert.match(await page.locator('#content').innerText(),new RegExp(metadata.buildNumber));
        await page.locator('#updateButton').click();await page.waitForSelector('[data-state=unconfigured]');
        await page.evaluate(()=>mock.update={ok:false});await page.locator('#updateButton').click();await page.waitForSelector('[data-state=error]');
        await page.evaluate(metadata=>mock.update={ok:true,configured:true,manifest:{...metadata,schemaVersion:1,publishedAt:metadata.buildDate,changelog:'Исправления',apkUrl:'https://github.com/portal26ernest-arch/-Portal-zrp/releases/download/test/app.apk',sha256:'a'.repeat(64)}},metadata);
        await page.locator('#updateButton').click();await page.waitForSelector('[data-state=latest]');
        await page.evaluate(()=>{mock.update.manifest.versionCode++;mock.update.manifest.versionName='Тестовая следующая сборка';mock.update.manifest.buildNumber='test-next';mock.update.manifest.changelog='<script>bad()</script>';});
        await page.locator('#updateButton').click();await page.waitForSelector('[data-state=available]');
        assert.equal(await page.locator('#updateState script').count(),0);
        await page.evaluate(()=>{mock.update.manifest.changelog='Улучшения интерфейса';});await page.locator('#updateButton').click();await page.waitForSelector('[data-state=available]');
        if(width===390)await screenshot(page,'about-light');
        await page.evaluate(()=>theme('dark'));assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
        if(width===390)await screenshot(page,'about-dark');
        await page.evaluate(()=>theme('system'));await page.emulateMedia({colorScheme:'light'});await page.waitForFunction(()=>document.documentElement.dataset.theme==='light');
        await page.emulateMedia({colorScheme:'dark'});await page.waitForFunction(()=>document.documentElement.dataset.theme==='dark');
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true);
        assert.deepEqual(errors,[]);await page.close();
      }
    });
    await t.test('offline login displays error and preserves unauthenticated state',async()=>{
      const {page,errors}=await fixture(browser);await page.evaluate(()=>mock.offline=true);
      await page.locator('#loginUser').fill('tester');await page.locator('#loginPin').fill('1234');await page.locator('#loginSubmit').click();
      await page.waitForSelector('#loginError:not(.hidden)');assert.equal(await page.locator('#app').isVisible(),false);
      assert.equal(await page.locator('#loginSubmit').isEnabled(),true);assert.deepEqual(errors,[]);await page.close();
    });
    await t.test('each role renders all its allowed screens and hides forbidden tiles',async()=>{
      for(const role of ['admin','director','manager','packer','shift','accountant']){
        const {page,errors}=await fixture(browser,role);await login(page);await page.evaluate(()=>go('sections'));
        const visible=await page.locator('#content [data-page]').evaluateAll(nodes=>nodes.map(n=>n.dataset.page));
        const expected=Array.from(core.modules).filter(m=>!m.future&&core.can(m.id,{role,telegram_id:101},{id:1})).map(m=>m.id);
        assert.deepEqual(visible,expected);
        for(const name of expected){await page.evaluate(name=>go(name),name);assert.doesNotMatch(await page.locator('#content').innerText(),/Не удалось загрузить/);}
        assert.deepEqual(errors,[]);await page.close();
      }
    });
    await t.test('manager records personal work; expired write session returns to login',async()=>{
      const {page,errors}=await fixture(browser);await login(page);await page.evaluate(()=>go('work'));
      await page.locator('#wClient').selectOption('1');await page.waitForFunction(()=>!document.querySelector('#wOp').disabled);
      await page.locator('#wOp').selectOption('1');await page.locator('#wQty').fill('4');await page.locator('#workSubmit').click();
      await page.waitForFunction(()=>document.querySelector('#wQty').value==='');
      const calls=await page.evaluate(()=>mock.calls.filter(c=>c.url==='/api/work'));
      assert.equal(calls.length,1);assert.deepEqual(calls[0].body,{client_id:1,operation_id:1,quantity:4});
      await page.evaluate(()=>mock.rejectWrite=true);await page.locator('#wQty').fill('4');await page.locator('#workSubmit').click();await page.waitForSelector('#auth:not(.hidden)');
      assert.equal(await page.evaluate(()=>localStorage.getItem('portalSession')),null);assert.deepEqual(errors,[]);await page.close();
    });
    await t.test('owner requires company and confirmation, switches scope and rejects stale data',async()=>{
      const {page,errors}=await fixture(browser,'platform_owner');
      await page.locator('#loginCompany').click();await page.locator('#sheetContent [data-action=technicalLogin]').click();
      assert.equal(await page.locator('#passwordLabel').innerText(),'Пароль владельца платформы');await login(page);
      assert.equal(await page.evaluate(()=>mock.calls.some(c=>c.url==='/api/platform/login')),true);
      assert.equal(await page.locator('[data-action=selectCompany]').count(),2);
      assert.equal((await page.evaluate(()=>mock.calls)).some(c=>c.url.startsWith('/api/dashboard')),false);
      await page.locator('[data-action=selectCompany][data-id="2"]').click();await page.locator('[data-action=confirmSheet]').click();
      await page.waitForSelector('#supportStrip:not(.hidden)');assert.match(await page.locator('#supportStrip').innerText(),/Вторая компания/);
      await page.evaluate(()=>go('clients'));await page.locator('[data-action=editClient][data-id="1"]').click();await page.locator('#cName').fill('Новое имя');await page.locator('#clientForm [type=submit]').click();
      assert.match(await page.locator('#sheetContent').innerText(),/Вторая компания/);
      assert.equal((await page.evaluate(()=>mock.calls)).filter(c=>c.method==='POST'&&c.url.startsWith('/api/admin')).length,0);
      await page.locator('[data-action=confirmSheet]').click();await page.waitForFunction(()=>mock.calls.some(c=>c.method==='POST'&&c.url==='/api/admin/clients/1'));
      assert.equal(await page.evaluate(()=>mock.calls.find(c=>c.url==='/api/admin/clients/1').company),'2');
      await page.waitForFunction(()=>S.writes===0);await page.evaluate(()=>{mock.hold=true;void go('dashboard');});
      await page.waitForFunction(()=>mock.held.length===1);await page.locator('#supportStrip [data-action=exitSupport]').click();await page.waitForSelector('[data-action=selectCompany]');
      await page.evaluate(()=>{mock.hold=false;mock.held.splice(0).forEach(f=>f());});
      await page.waitForFunction(()=>pending.size===0);assert.equal(await page.locator('[data-action=selectCompany]').count(),2);
      assert.equal(await page.locator('#supportStrip').isVisible(),false);assert.deepEqual(errors,[]);await page.close();
    });
    await t.test('Stage 3 timer, presence, activity and system information',async()=>{
      const {page,errors}=await fixture(browser,'admin',{width:390,height:844},true);
      await login(page);
      assert.match(await page.locator('#content').innerText(),/PORTAL Сегодня/);
      assert.match(await page.locator('#content').innerText(),/Ожидаемая прибыль/);
      assert.match(await page.locator('#content').innerText(),/Дебиторская задолженность/);
      await page.evaluate(()=>{mock.stage3Today={date:'2026-09-25',mode:'management',today_quantity:17,ready:1,active_batches:2,in_progress:0,tasks:[],attention:[]};void go('dashboard');});
      await page.waitForFunction(()=>document.querySelector('#content').textContent.includes('PORTAL Сегодня')&&!document.querySelector('.loading'));
      assert.doesNotMatch(await page.locator('#content').innerText(),/Ожидаемая прибыль|Выручка|Начислено сотрудникам/);
      await page.evaluate(()=>{mock.stage3Today=null;void go('batches');});
      await page.waitForFunction(()=>S.page==='batches'&&document.querySelector('#content').textContent.includes('Связанные задания'));
      assert.match(await page.locator('#content').innerText(),/PRT-2026-000001/);
      assert.match(await page.locator('#content').innerText(),/Упаковка/);
      await page.evaluate(()=>void go('dashboard'));
      await page.waitForFunction(()=>document.querySelector('[data-action=taskWork]'));
      await page.locator('[data-action=taskWork]').click();
      await page.waitForSelector('#taskWorkForm');
      assert.match(await page.locator('#sheetContent').innerText(),/Накопленное рабочее время/);
      await page.locator('[data-action=timerToggle]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.url==='/api/v3/timers'&&c.body?.event==='pause'));
      await page.waitForFunction(()=>S.currentTimer?.status==='paused');
      await page.locator('[data-action=timerToggle]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.url==='/api/v3/timers'&&c.body?.event==='resume'));
      await page.waitForFunction(()=>S.currentTimer?.status==='running');
      await page.locator('#taskQuantity').fill('5');await page.locator('#taskWorkForm [type=submit]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.url==='/api/v3/timers'&&c.body?.event==='finish'));
      await page.waitForTimeout(300);
      assert.equal(await page.evaluate(()=>S.page),'work',await page.locator('#toast').innerText()+' / '+await page.locator('#content').innerText());
      await page.locator('[data-action=otherWork]').click();
      await page.locator('#freeClient').selectOption('1');
      await page.locator('#freeOperation').selectOption('1');
      await page.locator('#freeQuantity').fill('3');
      await page.locator('#otherWorkForm [type=submit]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.url==='/api/v3/work'&&c.body?.quantity===3));
      const free=await page.evaluate(()=>mock.calls.find(c=>c.url==='/api/v3/work'));
      assert.equal(free.body.client_id,1);assert.equal(free.body.operation_id,1);assert.equal(free.body.batch_id,null);
      assert.equal(Object.hasOwn(free.body,'employee_rate'),false);
      await page.locator('[data-action=productionHistory]').click();
      await page.waitForFunction(()=>document.querySelector('#content').textContent.includes('Без задания'));
      assert.match(await page.locator('#content').innerText(),/Без задания/);
      await page.evaluate(()=>go('users'));
      await page.waitForFunction(()=>S.page==='users'&&!document.querySelector('.loading'));
      assert.match(await page.locator('#content').innerText(),/В сети/);
      await page.locator('[data-action=loginHistory]').click();await page.waitForSelector('#sheetContent');
      assert.match(await page.locator('#sheetContent').innerText(),/Вход · Успешно/);
      await page.evaluate(()=>closeSheet());
      await page.locator('[data-action=employeeActivity]').click();await page.waitForSelector('#sheetContent');
      assert.match(await page.locator('#sheetContent').innerText(),/Активность в системе/);
      assert.match(await page.locator('#sheetContent').innerText(),/История входов/);
      await page.evaluate(()=>{closeSheet();go('about');});
      await page.waitForFunction(()=>document.querySelector('#content').textContent.includes('О системе PORTAL'));
      assert.match(await page.locator('#content').innerText(),/Разработчик и правообладатель — Вартанян Эрнест/);
      assert.deepEqual(errors,[]);await page.close();
    });
    await t.test('individual permissions use Russian labels and hide unauthorized login history',async()=>{
      const {page,errors}=await fixture(browser,'admin',{width:390,height:844},true);
      await page.evaluate(()=>mock.stage3Permissions=['work.write','tasks.read','tasks.manage','batches.receive','users.manage']);
      await login(page);await page.evaluate(()=>go('permissions'));
      await page.waitForFunction(()=>document.querySelector('#content').textContent.includes('Права доступа'));
      await page.locator('[data-action=editPermissions]').click();
      assert.match(await page.locator('#sheetContent').innerText(),/Вносить свою выработку/);
      assert.match(await page.locator('#sheetContent').innerText(),/Сотрудники/);
      assert.match(await page.locator('#sheetContent').innerText(),/рекомендуется: Сборщик/);
      assert.doesNotMatch(await page.locator('#sheetContent').innerText(),/access\.history\.read|Platform Owner/);
      await page.evaluate(()=>{closeSheet();go('users');});
      await page.waitForFunction(()=>S.page==='users'&&document.querySelector('[data-action=employeeActivity]'));
      await page.locator('[data-action=employeeActivity]').click();await page.waitForSelector('#sheetContent');
      assert.match(await page.locator('#sheetContent').innerText(),/Просмотр истории входов недоступен/);
      assert.equal(await page.evaluate(()=>mock.calls.some(c=>c.url==='/api/v3/activity')),false);
      assert.deepEqual(errors,[]);await page.close();
    });
  }finally{await browser.close();}
});

test('new employee creation is independent from existing employees',()=>{
  const source=fs.readFileSync(path.join(assets,'screens.js'),'utf8');
  assert.match(source,/Создать нового сотрудника/);
  assert.match(source,/Выдать доступ существующему/);
  assert.match(source,/existingEmployeeWrap" hidden/);
  assert.match(source,/body\.create_employee=!existing/);
  assert.match(source,/Новый сотрудник получит собственную карточку и уникальный ID/);
});
