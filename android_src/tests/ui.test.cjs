// Run with Node.js and Playwright installed. No production API or database is used.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {pathToFileURL} = require('node:url');
let chromium;
try { ({chromium}=require('playwright')); } catch { chromium=null; }
const assets = path.resolve(__dirname, '../app/src/main/assets');
const metadata = Object.fromEntries(fs.readFileSync(path.resolve(__dirname,'../release.properties'),'utf8').split(/\r?\n/).filter(l=>l&&!l.startsWith('#')).map(l=>{const i=l.indexOf('=');return [l.slice(0,i),l.slice(i+1)];}));
metadata.versionCode=Number(metadata.versionCode);
metadata.applicationId='ru.portal.app';
const context=vm.createContext({});
vm.runInContext(fs.readFileSync(path.join(assets,'core.js'),'utf8'),context);
const core=context.PortalCore;
async function screenshot(page,name){if(process.env.PORTAL_UI_SCREENSHOTS){fs.mkdirSync(process.env.PORTAL_UI_SCREENSHOTS,{recursive:true});await page.screenshot({path:path.join(process.env.PORTAL_UI_SCREENSHOTS,name+'.png'),fullPage:true});}}

test('all shipped JavaScript parses',()=>{
  for(const file of ['core.js','app.js','screens.js','production.js','preview.js','documents_excel.js'])new vm.Script(fs.readFileSync(path.join(assets,file),'utf8'),{filename:file});
});
test('system sticker catalog, rendering and absence notice use structured safe fields',()=>{
  const catalog=JSON.parse(fs.readFileSync(path.join(assets,'stickers/catalog.json'),'utf8'));
  assert.deepEqual(catalog.stickers.map(x=>x.key),['accepted','in_progress','done','help','important','thanks']);
  for(const item of catalog.stickers){assert.match(item.asset,/^[a-z_]+\.svg$/);assert.ok(fs.existsSync(path.join(assets,'stickers',item.asset)));}
  const production=fs.readFileSync(path.join(assets,'production.js'),'utf8');
  assert.match(production,/subtype:'sticker',sticker_key:button\.dataset\.key/);
  assert.match(production,/subtype:'absence_notice',absence_date:/);
  assert.match(production,/esc\(m\.absence_date\)/);
  assert.match(production,/portalStickers\.find\(x=>x\[0\]===m\.sticker_key\)/);
});
test('desktop Organizer exposes director requests in Russian and stays desktop-only',()=>{
  const production=fs.readFileSync(path.join(assets,'production.js'),'utf8');
  const coreSource=fs.readFileSync(path.join(assets,'core.js'),'utf8');
  for(const label of ['Мои запросы','Входящие запросы','Новый запрос директору','Создать задачу из запроса','Закупка материалов'])assert.match(production,new RegExp(label));
  assert.match(production,/organizer-requests\?scope=mine/);
  assert.match(production,/organizer-requests\?scope=incoming/);
  assert.match(production,/organizer-request-events\?organizer_request_id=/);
  assert.match(production,/organizer-request-file\?id=/);
  assert.match(production,/allowed\('organizer\.request\.create'\)/);
  assert.match(production,/canCreateDirectorRequest=\(\)=>allowed\('organizer\.request\.create'\)&&\['manager','admin'\]\.includes\(S\.me\?\.role\)/);
  assert.match(production,/allowed\('organizer\.request\.decide'\)/);
  assert.match(coreSource,/id:'organizer'.*desktopOnly:true/);
  assert.match(coreSource,/page==='organizer' && !globalThis\.__PORTAL_DESKTOP__/);
});

test('marketplace news is live/empty, escaped and links only to official HTTPS hosts',()=>{
  const preview=fs.readFileSync(path.join(assets,'preview.js'),'utf8');
  assert.match(preview,/marketplace-news\?source=/);
  assert.match(preview,/Пока нет опубликованных новостей/);
  assert.match(preview,/esc\(item\.title\)/);assert.match(preview,/esc\(item\.body\)/);
  assert.match(preview,/u\.protocol==='https:'/);
  assert.match(preview,/!u\.port\|\|u\.port==='443'/);
  assert.match(preview,/seller\.ozon\.ru','seller\.wildberries\.ru/);
  assert.match(preview,/href="https:\/\/seller\.ozon\.ru\/"[^>]*>Открыть Ozon Seller/);
  assert.match(preview,/href="https:\/\/seller\.wildberries\.ru\/"[^>]*>Открыть Wildberries Seller/);
  assert.match(preview,/Открыть первоисточник/);
  assert.doesNotMatch(preview,/innerHTML\s*=\s*item\.body/);
});
test('time-based greeting uses local hour boundaries',()=>{
  const cases={0:'Доброй ночи',4:'Доброй ночи',5:'Доброе утро',11:'Доброе утро',12:'Добрый день',17:'Добрый день',18:'Добрый вечер',22:'Добрый вечер',23:'Доброй ночи'};
  for(const [hour,greeting] of Object.entries(cases))assert.equal(core.timeGreeting(Number(hour)),greeting);
  assert.throws(()=>core.timeGreeting(24),/hour must be 0\.\.23/);
});
test('role capabilities and employee linkage',()=>{
  const expected={admin:['work','payroll','clients','materials','invoices','users','jobs','reports','news','wms','notifications'],director:['work','payroll','clients','materials','invoices','users','jobs','reports','news','wms','notifications'],manager:['work','payroll','clients','materials','invoices','jobs','reports','news','wms','notifications'],packer:['work','payroll','materials','jobs'],shift:[],accountant:[]};
  for(const [role,pages] of Object.entries(expected)){
    for(const m of core.modules)assert.equal(core.can(m.id,{role,employee_id:101},{id:1}),pages.includes(m.id),role+':'+m.id);
    assert.equal(core.can('work',{role}, {id:1}),false);
    assert.equal(core.can('audit',{role},{id:1}),false);
  }
  assert.equal(core.can('dashboard',{role:'platform_owner'},null),false);
  assert.equal(core.can('users',{role:'platform_owner'},{id:2}),true);
  assert.equal(core.can('work',{role:'platform_owner',employee_id:101},{id:2}),false);
  const importPermissions=['imports.manage','users.manage','clients.manage','rates.employee','rates.client','company.settings','documents.manage','documents.read'];
  assert.equal(core.can('excelImport',{role:'admin',permissions:importPermissions},{id:1}),true);
  assert.equal(core.can('excelImport',{role:'admin',permissions:['company.settings']},{id:1}),false);
  assert.equal(core.can('excelImport',{role:'platform_owner',permissions:importPermissions},{id:2}),true);
  assert.equal(core.can('work',{role:'manager',employee_id:101},{id:1,module_toggles:{work:false}}),false);
  assert.equal(core.can('work',{role:'manager',employee_id:101},{id:1,module_toggles:{work:true}}),true);
});
test('effective permissions enforce the current company role matrix',()=>{
  const company={id:1};
  const manager=['work.write','tasks.read','tasks.manage','organizer.read','organizer.assign','organizer.request.create','batches.receive','work.link','payroll.own','chat.read','chat.write','chat.moderate','clients.read','rates.client','materials.read','materials.use','invoices.read','invoices.create','invoices.export','finance.read','expenses.read','analytics.read','documents.read'];
  const packer=['tasks.read','work.write','payroll.own','materials.read','materials.use'];
  context.__PORTAL_DESKTOP__=true;
  for(const page of ['work','payroll','clients','materials','invoices','jobs','reports','news','wms','notifications','radar','expenses','analytics','documents','organizer'])
    assert.equal(core.can(page,{role:'manager',employee_id:101,permissions:manager},company),true,'manager:'+page);
  for(const page of ['payrollPeriods','users','permissions','excelImport','control'])
    assert.equal(core.can(page,{role:'manager',employee_id:101,permissions:manager},company),false,'manager forbidden:'+page);
  for(const page of ['work','payroll','materials','jobs'])
    assert.equal(core.can(page,{role:'packer',employee_id:101,permissions:packer},company),true,'packer:'+page);
  for(const page of ['teamChat','clients','invoices','reports','news','wms','notifications','organizer','radar','expenses','analytics','documents','users','permissions'])
    assert.equal(core.can(page,{role:'packer',employee_id:101,permissions:packer},company),false,'packer forbidden:'+page);
  for(const role of ['shift','accountant']){
    for(const m of core.modules)assert.equal(core.can(m.id,{role,employee_id:101,permissions:[]},company),false,role+':'+m.id);
  }
  delete context.__PORTAL_DESKTOP__;
});

test('updates: unconfigured, offline, current, newer and invalid manifests',()=>{
  const manifest={schemaVersion:1,...metadata,publishedAt:metadata.buildDate+'T12:00:00Z',changelog:'Исправления',apkUrl:`https://github.com/portal26ernest-arch/-Portal-zrp/releases/download/portal-android-v${metadata.versionName}/PORTAL_Android_${metadata.versionName}_release.apk`,sha256:'a'.repeat(64)};
  const state=m=>core.updateState(metadata,{ok:true,configured:true,manifest:m}).state;
  assert.equal(core.updateState(metadata,{ok:true,configured:false}).state,'unconfigured');
  assert.equal(core.updateState(metadata,{ok:true,configured:false,storeManaged:true}).state,'store');
  assert.equal(core.updateState(metadata,{ok:false}).state,'error');
  assert.equal(state(manifest),'latest');
  assert.equal(state({...manifest,versionCode:metadata.versionCode+1}),'available');
  const wrongVersionUrl=manifest.apkUrl.replace('portal-android-v'+metadata.versionName,'portal-android-v'+metadata.versionName+'-wrong');
  for(const patch of [{channel:'other'},{applicationId:'other'},{versionCode:'4'},{publishedAt:'invalid'},{changelog:null},{apkUrl:'http://example.test/app.apk'},{apkUrl:'https://user@example.test/app.apk'},{apkUrl:wrongVersionUrl},{sha256:'bad'}])assert.equal(state({...manifest,...patch}),'error');
});
test('login screen exposes update check before authentication and uses blue PORTAL accent',()=>{
  const index=fs.readFileSync(path.join(assets,'index.html'),'utf8');
  const app=fs.readFileSync(path.join(assets,'app.js'),'utf8');
  const css=fs.readFileSync(path.join(assets,'ui.css'),'utf8');
  assert.match(index,/id="authUpdateButton"[^>]+data-action="checkUpdates"/);
  assert.match(index,/id="authUpdateState"/);
  assert.match(app,/\['updateState','authUpdateState'\]/);
  assert.match(app,/Вход в аккаунт для обновления не требуется/);
  assert.match(css,/--accent:#0b5ed7/);
  assert.doesNotMatch(css,/--accent:#23695d/);
});

test('update install action is available only for verified available state and renders progress',()=>{
  const app=fs.readFileSync(path.join(assets,'app.js'),'utf8');
  assert.match(app,/u\.state==='available'\?btn\('Скачать и установить','installUpdate'/);
  assert.match(app,/state:'downloading',title:'Загружаем и проверяем…'/);
  assert.match(app,/state:'ready',title:'Готово к установке'/);
  assert.match(app,/void autoCheckUpdates\(\);await checkServer\(\)/);
  assert.match(app,/S\.update\?\.state!=='available'\|\|!S\.update\.release/);
});
test('desktop web branding uses the PORTAL blue shell',()=>{
  const css=fs.readFileSync(path.join(assets,'ui.css'),'utf8');
  assert.match(css,/--portal-blue:#0b5ed7/);
  assert.match(css,/\.web-client \.nav::before\{content:"PORTAL"/);
  assert.match(css,/\.web-client \.top\{background:var\(--portal-blue\)/);
  assert.match(css,/@media\(min-width:900px\)/);
});
test('modal sheets do not dismiss on backdrop, Escape or Back',()=>{
  const index=fs.readFileSync(path.join(assets,'index.html'),'utf8');
  const app=fs.readFileSync(path.join(assets,'app.js'),'utf8');
  assert.match(index,/id="sheetBackdrop"[\s\S]*data-action="closeSheet"[^>]*aria-label="Закрыть"/);
  assert.match(app,/window\.portalBack=\(\)=>\{if\(!\$\('sheetBackdrop'\)\.classList\.contains\('hidden'\)\)return true;/);
  assert.match(app,/function guardModalDismiss\(event\)/);
  assert.match(app,/document\.addEventListener\('pointerdown',guardModalDismiss,true\)/);
  assert.match(app,/document\.addEventListener\('click',guardModalDismiss,true\)/);
  assert.match(app,/if\(event\.key==='Escape'\)\{event\.preventDefault\(\);event\.stopPropagation\(\);event\.stopImmediatePropagation\(\);return;\}/);
  assert.doesNotMatch(app,/sheetBackdrop'\)\.addEventListener\('click'/);
});

// Emulate only the Java bridge transport; run the actual shipped UI and events.
async function fixture(browser,role='manager',viewport={width:390,height:844},stage3=false,web=false){
  const page=await browser.newPage({viewport});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.addInitScript(({role,metadata,stage3,web})=>{
    localStorage.clear();
    if(web)window.__PORTAL_WEB__=true;
    const user={id:1,username:role,display_name:'Тестовый пользователь',role,company_id:1,employee_id:role==='platform_owner'?null:101};
    const client={id:1,name:'Клиент',active:1};
    window.mock={calls:[],offline:false,rejectWrite:false,failUrls:[],hold:false,held:[],update:{ok:true,configured:false},timer:null,stage3Today:null,stage3Batches:null,stage3Shipments:null,stage3Tasks:null,stage3Economy:null,stage3Finance:null,stage3Permissions:null,stage3Invoices:null,stage3Users:null,clientNameHistory:[],clientAliases:[],clientRequisites:{legal_name:'ООО Тест',inn:'TEST-INN-001'},tariffHistory:[],presenceOnline:true,saved:null,previewMode:'ok',applyMode:'ok',payrollPaid:2000,invites:[],products:[]};
    const respond=(id,data)=>setTimeout(()=>window.PortalBridgeResult(id,JSON.stringify(data)),0);
    window.PortalNative={getServerUrl:()=> 'http://127.0.0.1:8765',getAppMetadata:()=>JSON.stringify(metadata),checkUpdates:id=>respond(id,mock.update),saveBase64FileAsync(id,filename,mime,file_b64){mock.saved={filename,mime,file_b64};respond(id,{ok:true,location:'Downloads/PORTAL/'+filename});},requestAsync(id,method,url,payload,token,company){
      mock.calls.push({method,url,body:payload?JSON.parse(payload):null,token,company});
      if(mock.offline)return respond(id,{ok:false,network:true,error:'Нет соединения'});
      if(mock.rejectWrite&&method==='POST')return respond(id,{ok:false,httpStatus:401});
      if(mock.failUrls.includes(url))return respond(id,{ok:false,httpStatus:503,error:'Синтетическая ошибка источника'});
      let data={ok:true};
      if(stage3&&url==='/api/v3/meta')Object.assign(data,{ready:true,heartbeat_seconds:60,permissions:mock.stage3Permissions||['work.write','tasks.read','tasks.manage','batches.receive','finance.read','invoices.read','invoices.create','users.manage','access.history.read','payroll.own'],catalog:[{code:'work.write',group:'Работа',label:'Вносить свою выработку',recommended:['Сборщик']},{code:'access.history.read',group:'Сотрудники',label:'Просматривать историю входов сотрудников',recommended:['Управляющий','Администратор']}]});
      else if(stage3&&url.startsWith('/api/v3/documents?'))data.data={items:[{id:'doc-ready',title:'Готовый документ',document_type:'report_xlsx',category:'report',document_date:'2026-09-29',created_at:'2026-09-29T00:00:00Z',client_id:1,size_bytes:2048,status:'ready',revision:1},{id:'doc-archived',title:'Архивный документ',document_type:'report_pdf',category:'report',document_date:'2026-09-28',created_at:'2026-09-28T00:00:00Z',size_bytes:1024,status:'archived',revision:1}],total:2,page:1,limit:50};
      else if(stage3&&url.startsWith('/api/v3/document-history?'))data.data=[{id:'doc-older',title:'Старая версия',created_at:'2026-09-28T00:00:00Z',status:'archived',revision:1},{id:'doc-ready',title:'Готовый документ',created_at:'2026-09-29T00:00:00Z',status:'ready',revision:2}];
      else if(stage3&&url.startsWith('/api/v3/document-file?id=')){const result=url.includes('result-');data.data=result?{filename:'PORTAL_import_result.json',mime_type:'application/json',file_b64:'e30='}:{filename:'PORTAL_report.xlsx',mime_type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',file_b64:'UEs='};}
      else if(stage3&&url==='/api/v3/document-archive'&&method==='POST')data.data={id:'doc-ready',status:'archived'};
      else if(stage3&&url==='/api/v3/document-template-info')data.data={template_version:'1.1',sheets:['Компания','Сотрудники','Клиенты','Операции_Тарифы']};
      else if(stage3&&(url==='/api/v3/document-template-blank'||url==='/api/v3/document-template'))data.data={filename:'PORTAL_template_v1.1.xlsx',mime_type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',file_b64:'UEs='};
      else if(stage3&&url==='/api/v3/excel-import-preview'&&method==='POST'){const conflict=mock.previewMode==='conflict';data.data={import_id:'import-1',preview_token:'token-1',template_version:'1.1',can_apply:!conflict,summary:{new:conflict?0:1,update:0,unchanged:0,conflict:conflict?1:0,invalid:0},rows:[{sheet:'Клиенты',row:4,classification:conflict?'conflict':'new',errors:conflict?[{code:'duplicate_client'}]:[],changes:conflict?{}:{name:{before:null,after:'Новый клиент'}}}]};}
      else if(stage3&&url==='/api/v3/excel-import-apply'&&method==='POST'){if(mock.applyMode==='failed')return respond(id,{ok:false,httpStatus:409,error:'Импорт отменён полностью',data:{status:'failed',result_document_id:'result-failed',error_report:[{code:'apply_failed'}]}});if(mock.applyMode==='stale')return respond(id,{ok:false,httpStatus:400,error:'Справочники изменились; повторите preview'});data.data={status:'applied',result_counts:{new:1,updated:0,unchanged:0},result_document_id:'result-ok'};}
      else if(stage3&&url.startsWith('/api/v3/excel-import-result?id=')){if(mock.applyMode==='failed')data.data={status:'failed',result_document_id:'result-failed',error_report:[{code:'apply_failed'}]};else if(mock.applyMode==='ok')data.data={status:'applied',result_document_id:'result-ok',result_counts:{new:1,updated:0,unchanged:0}};else return respond(id,{ok:false,httpStatus:404,error:'Импорт не найден'});}
      else if(stage3&&url==='/api/v3/today'){const task={id:'task-1',batch_id:'batch-1',client_name:'Клиент',product:'Коробка',batch_number:'PRT-2026-000001',operation_name:'Упаковка',quantity:10,done:2,remaining:8,status:'in_progress',assignees:[1]};data.data=mock.stage3Today||{date:'2026-09-25',mode:role==='admin'?'management':'worker',own_quantity:4,own_salary:500,attention:[],tasks:[task],...(role==='admin'?{today_quantity:17,month_quantity:27,active_jobs:1,in_progress:1,ready:1,active_batches:2,finance:{salary:1200,revenue:2500,profit:900},today_finance:{revenue:1000,salary:400},month_finance:{revenue:5000,salary:2000},today_productivity:{units:17,timed_units:10,units_per_hour:5},closed_month_payroll:null,expected_profit:null,debt:400,open_invoice_count:2,overdue_invoice_count:1,overdue_debt:400,client_profitability_alerts:1}:{})};}
      else if(stage3&&url==='/api/v3/tasks')data.data=mock.stage3Tasks||[{id:'task-1',batch_id:'batch-1',client_name:'Клиент',product:'Коробка',batch_number:'PRT-2026-000001',operation_name:'Упаковка',quantity:10,done:2,remaining:8,status:'in_progress',assignees:[1]}];
      else if(stage3&&url==='/api/v3/timers'&&method==='GET')data.data=mock.timer&&['running','paused'].includes(mock.timer.status)?[mock.timer]:[];
      else if(stage3&&url==='/api/v3/timers'&&method==='POST'){const b=JSON.parse(payload);mock.timer={id:'timer-1',task_id:'task-1',user_id:1,started_at:'2026-09-25T09:12:00',pauses:[],status:({start:'running',pause:'paused',resume:'running',finish:'completed'})[b.event]};data.data=mock.timer;}
      else if(stage3&&url==='/api/v3/batches')data.data=mock.stage3Batches||[{id:'batch-1',number:'PRT-2026-000001',client_id:1,client_name:'Клиент',product:'Коробка',received_at:'2026-09-24',quantity:10,done:2,remaining:8,stage:'in_progress',operations:[{operation:'Упаковка',done:2,planned:10}],ready:false}];
      else if(stage3&&url==='/api/v3/shipments')data.data=mock.stage3Shipments||[];
      else if(stage3&&url.startsWith('/api/v3/economy?'))data.data=mock.stage3Economy||{plan:{salary:null,revenue:null,materials:null,other:null,profit:null,volume:null},fact:{salary:0,revenue:0,materials:0,other:0,profit:0,volume:0},deviation:{salary:null,revenue:null,materials:null,other:null,profit:null,volume:null},margin_bps:{plan:null,fact:null,deviation:null},finished_units:0,cost_per_unit:null,profit_per_unit:null};
      else if(stage3&&url==='/api/v3/invoices')data.data=mock.stage3Invoices||[];
      else if(stage3&&url==='/api/v3/documents')data.data=[{id:'doc-client',title:'Документ клиента',client_id:1,document_type:'invoice_pdf',status:'ready'}];
      else if(stage3&&url==='/api/v3/finance')data.data=mock.stage3Finance||{clients:[],months:{},client_profit:0,company_overhead:0,net_profit:0};
      else if(stage3&&url.startsWith('/api/v3/receivables'))data.data={as_of:'2026-09-30',money_unit:'kopeck',outstanding:12500,overdue:4000,total:2,page:1,limit:50,buckets:{current:{count:1,amount:8500},days_1_7:{count:1,amount:4000},days_8_30:{count:0,amount:0},days_31_60:{count:0,amount:0},days_61_plus:{count:0,amount:0},undated:{count:0,amount:0}},clients:[{client_id:1,name:'Клиент',outstanding:12500}],items:[{invoice_id:1,client_id:1,amount:8500,paid:0,outstanding:8500,due_at:'2026-09-30',overdue_days:0,bucket:'current'},{invoice_id:2,client_id:1,amount:6000,paid:2000,outstanding:4000,due_at:'2026-09-29',overdue_days:1,bucket:'days_1_7'}]};
      else if(stage3&&url==='/api/v3/payroll-periods')data.data=[{id:'period-1',period_start:'2026-09-01',period_end:'2026-09-15',closed_at:'2026-09-16',snapshot:{total_quantity:10,total_salary:10000,employees:[{employee_id:1,display_name:'Тестовый сотрудник',salary:10000}]}}];
      else if(stage3&&url.startsWith('/api/v3/payroll-settlements?'))data.data={period_id:'period-1',period_start:'2026-09-01',period_end:'2026-09-15',status:'закрыт',money_unit:'kopeck',employees:[{employee_id:1,display_name:'Тестовый сотрудник',accrued:10000,adjustment:0,paid:mock.payrollPaid,balance:10000-mock.payrollPaid}],totals:{accrued:10000,adjustment:0,paid:mock.payrollPaid,balance:10000-mock.payrollPaid},entries:[{id:'payment-1',employee_id:1,entry_type:'payout',effect:'payment',amount:2000,occurred_at:'2026-09-20',reason:'Первая выплата',reference:'Платёж 1'}]};
      else if(stage3&&url.startsWith('/api/v3/analytics'))data.data={groups:[{user_id:1,user_name:'Анна Сборщик',client_id:1,client_name:'Клиент',product:'Товар',operation_id:1,operation_name:'Упаковка',quantity:12,samples:3,timed_quantity:10,seconds:6000,units_per_hour:6,variability:0.25}],batch_groups:[{batch_id:'batch-1',batch_number:'PRT-2026-000001',client_id:1,client_name:'Клиент',product:'Товар',operation_id:1,operation_name:'Упаковка',quantity:8,samples:2,timed_quantity:8,seconds:4800,units_per_hour:6,variability:0.1}],quality:{available:false,recorded_units:0,defects:null},forecasts:[],comparison:url.includes('from=')?{period_start:'2026-09-10',period_end:'2026-09-16',previous_start:'2026-09-03',previous_end:'2026-09-09',current:{units:12,units_per_hour:6},previous:{units:8,units_per_hour:4},units_delta:4,units_percent_delta:50,units_per_hour_delta:2}:undefined};
      else if(stage3&&url==='/api/v3/payroll-settlements'&&method==='POST'){mock.payrollPaid+=Math.round(Number(JSON.parse(payload).amount)*100);data.data={id:'payment-2',entry_type:'payout'};}
      else if(stage3&&url==='/api/v3/catalog')data.data={clients:[{id:1,name:'Клиент'}],operations:[{id:1,client_id:1,name:'Упаковка'}],products:mock.products.filter(p=>p.active),users:mock.stage3Users||[]};
      else if(stage3&&url.startsWith('/api/v3/client-name-history'))data.data=mock.clientNameHistory;
      else if(stage3&&url.startsWith('/api/v3/client-aliases'))data.data=mock.clientAliases;
      else if(stage3&&url.startsWith('/api/v3/client-requisites?'))data.data=mock.clientRequisites;
      else if(stage3&&url==='/api/v3/client-requisites'&&method==='POST'){mock.clientRequisites={...mock.clientRequisites,...JSON.parse(payload)};data.data=mock.clientRequisites;}
      else if(stage3&&url.startsWith('/api/v3/tariff-history?operation_id='))data.data=mock.tariffHistory;
      else if(stage3&&url==='/api/v3/products'&&method==='POST'){const body=JSON.parse(payload);let product;if(body.action==='create'){product={id:'product-1',company_id:1,client_id:body.client_id,name:body.name,active:true};mock.products.push(product);}else{product=mock.products.find(p=>p.id===body.product_id);if(product){if(body.action==='archive')product.active=false;else product.name=body.name;}}data.data=product;}
      else if(stage3&&url==='/api/v3/products')data.data=mock.products;
      else if(stage3&&url==='/api/v3/works')data.data=[{id:'work-free',client_id:1,client_name:'Клиент',operation_name:'Упаковка',quantity:3,salary:300,completed_at:'2026-09-25T09:20:00',without_task:true,batch_id:null}];
      else if(stage3&&url==='/api/v3/work'&&method==='POST')data.data={id:'work-free',salary:300,without_task:true};
      else if(stage3&&url==='/api/v3/presence')data.data=[{user_id:1,online:mock.presenceOnline,last_activity_at:new Date().toISOString(),active_sessions:mock.presenceOnline?1:0}];
      else if(stage3&&url==='/api/v3/activity')data.data=[{event:'login',result:'success',user_id:1,client_type:'Android',at:'2026-09-25T09:12:00'}];
      else if(stage3&&url==='/api/v3/invitations'&&method==='POST'){const action=JSON.parse(payload);if(action.action==='create'){const invite={id:'invite-1',status:'pending',display_name:action.display_name,username:action.username,role:action.role,expires_at:'2026-10-07'};mock.invites.unshift(invite);data.data={invite,token:'1.abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_',replay:false};}else{const invite=mock.invites.find(item=>item.id===action.invite_id);if(invite)invite.status=action.action==='approve'?'approved':action.action==='revoke'?'revoked':'rejected';data.data={invite};}}
      else if(stage3&&url.startsWith('/api/v3/invitations'))data.data={items:mock.invites.slice(),page:1,limit:50,total:mock.invites.length};
      else if(url==='/api/access-invites/accept')data.data={status:'pending_approval'};
      else if(stage3&&url==='/api/v3/company-access')data.data={active_users:1,user_limit:null,unlimited:true};
      else if(stage3&&url==='/api/v3/settings')data.data={monday_time:'10:00',wednesday_time:'11:00',utc_offset_minutes:180,presence_heartbeat_seconds:60,presence_timeout_seconds:180,reminder_enabled:false,reminder_cadence:'daily'};
      else if(stage3&&url.startsWith('/api/v3/audit'))data.data={items:[],page:1,limit:50,total:0};
      else if(stage3&&url==='/api/v3/permissions')data.data=[{id:1,display_name:'Тестовый пользователь',role:'admin',permissions:['work.write']}];
      if(url==='/api/ping')data.setup_required=false;
      else if(url.endsWith('/login'))Object.assign(data,{token:'fixture-token',user});
      else if(url==='/api/me')data.user=user;
      else if(url==='/api/company')data.company={id:1,name:'PORTAL'};
      else if(url.startsWith('/api/dashboard'))data.data={quantity:103,salary:206,revenue:515,debt:100,profit:300};
      else if(url==='/api/platform/companies')data.companies=[{id:1,name:'PORTAL',status:'active',service_status:'active',monthly_price:0,demo_enabled:0,user_limit:null,module_toggles:{}},{id:2,name:'Вторая компания',status:'active',service_status:'active',monthly_price:0,demo_enabled:0,user_limit:15,module_toggles:{}}];
      else if(url.startsWith('/api/platform/audit'))Object.assign(data,{rows:[],page:1,limit:50,total:0});
      else if(url.endsWith('/operations'))Object.assign(data,{client,operations:[{id:1,name:'Упаковка',employee_rate:2,client_rate:5,active:1}]});
      else if(url==='/api/work')data.work={salary:8,warnings:[]};
      else if(url==='/api/work/mine')data.rows=[];
      else if(url==='/api/payroll/mine')data.data={quantity:4,accrued:8,paid:0,remaining:8};
      else if(url==='/api/jobs')data.jobs=[];
      else if(url==='/api/materials')data.materials=[];
      else if(url==='/api/invoices')data.invoices=[];
      else if(url==='/api/users')Object.assign(data,{users:[user],employees:[{employee_id:101,full_name:'Сотрудник'}],roles:{admin:'Администратор',manager:'Менеджер',packer:'Сотрудник'}});
      else if(url.endsWith('/clients'))data.clients=[{...client,name:mock.clientNameOverride||client.name}];
      else if(url==='/api/clients/1')Object.assign(data,{client,stats:{},requisites:{}});
      if(mock.hold&&url.startsWith('/api/dashboard'))mock.held.push(()=>respond(id,data));else respond(id,data);
    }};
  },{role,metadata,stage3,web});
  await page.goto(pathToFileURL(path.join(assets,'index.html')).href);
  await page.waitForFunction(()=>document.querySelector('#serverState').textContent==='Подключение готово');
  return {page,errors};
}
async function login(page){
  await page.locator('#loginUser').fill('tester');await page.locator('#loginPin').fill('1234');await page.locator('#loginSubmit').click();
  await page.waitForFunction(()=>!document.querySelector('#app').classList.contains('hidden')&&!document.querySelector('.loading'));
}
test('browser UI regression',async t=>{
  if(!chromium){t.skip('Playwright is not installed in this environment');return;}
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
        await page.evaluate(metadata=>mock.update={ok:true,configured:true,manifest:{...metadata,schemaVersion:1,publishedAt:metadata.buildDate+'T12:00:00Z',changelog:'Исправления',apkUrl:`https://github.com/portal26ernest-arch/-Portal-zrp/releases/download/portal-android-v${metadata.versionName}/PORTAL_Android_${metadata.versionName}_release.apk`,sha256:'a'.repeat(64)}},metadata);
        await page.locator('#updateButton').click();await page.waitForSelector('[data-state=latest]');
        await page.evaluate(()=>{mock.update.manifest.versionCode++;mock.update.manifest.versionName='test-next';mock.update.manifest.apkUrl='https://github.com/portal26ernest-arch/-Portal-zrp/releases/download/portal-android-vtest-next/PORTAL_Android_test-next_release.apk';mock.update.manifest.buildNumber='test-next';mock.update.manifest.changelog='<script>bad()</script>';});
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
    await t.test('modal stays open on backdrop click, Escape and Back until explicit close',async()=>{
      const {page,errors}=await fixture(browser,'manager',{width:1280,height:900},true,true);await login(page);
      await page.evaluate(()=>openSheet('Проверка окна','<button id="modalInside">Внутри</button>'));
      await page.waitForSelector('#sheetBackdrop:not(.hidden)');
      await page.locator('#sheetBackdrop').click({position:{x:8,y:8}});
      assert.equal(await page.locator('#sheetBackdrop').isVisible(),true);
      await page.keyboard.press('Escape');assert.equal(await page.locator('#sheetBackdrop').isVisible(),true);
      assert.equal(await page.evaluate(()=>window.portalBack()),true);assert.equal(await page.locator('#sheetBackdrop').isVisible(),true);
      await page.locator('#sheet .sheet-header [data-action=closeSheet]').click();
      await page.waitForFunction(()=>document.querySelector('#sheetBackdrop').classList.contains('hidden'));assert.equal(await page.locator('#sheetBackdrop').isVisible(),false);
      assert.deepEqual(errors,[]);await page.close();
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
        const expected=Array.from(core.modules).filter(m=>!m.future&&core.can(m.id,{role,employee_id:101},{id:1})).map(m=>m.id);
        assert.deepEqual(visible,expected);
        assert.doesNotMatch(await page.locator('body').innerText(),/\bGod\b|Технический вход|Platform Owner|Владелец платформы/);
        for(const name of expected){await page.evaluate(name=>go(name),name);assert.doesNotMatch(await page.locator('#content').innerText(),/Не удалось загрузить/);}
        assert.deepEqual(errors,[]);await page.close();
      }
    });
    await t.test('desktop menu follows effective permissions and PORTAL branding',async()=>{
      const director=await fixture(browser,'director',{width:1280,height:900},true,true);
      await director.page.evaluate(()=>{mock.stage3Permissions=['work.write','tasks.read','tasks.manage','batches.receive','users.manage','access.history.read','payroll.own','payroll.all','payroll.close','chat.read','clients.read','clients.manage','rates.employee','rates.client','materials.read','materials.use','invoices.read','invoices.create','payments.record','finance.read','expenses.read','expenses.manage','analytics.read','documents.read','documents.manage','imports.manage','company.settings'];document.documentElement.classList.add('web-client');});
      await login(director.page);const directorPages=await director.page.locator('#nav [data-page]').evaluateAll(nodes=>nodes.map(n=>n.dataset.page));
      for(const pageName of ['dashboard','users','materials','payrollPeriods','expenses','excelImport'])assert.ok(directorPages.includes(pageName),pageName);
      assert.equal(await director.page.evaluate(()=>getComputedStyle(document.querySelector('.top')).backgroundColor),'rgb(11, 94, 215)');
      assert.deepEqual(director.errors,[]);await director.page.close();
      const manager=await fixture(browser,'manager',{width:1280,height:900},true,true);
      await manager.page.evaluate(()=>{mock.stage3Permissions=['work.write','tasks.read','tasks.manage','batches.receive','payroll.own','chat.read','clients.read','rates.client','invoices.read','invoices.create','analytics.read','documents.read'];document.documentElement.classList.add('web-client');});
      await login(manager.page);const managerPages=await manager.page.locator('#nav [data-page]').evaluateAll(nodes=>nodes.map(n=>n.dataset.page));
      for(const pageName of ['dashboard','work','clients','invoices','analytics','documents'])assert.ok(managerPages.includes(pageName),pageName);
      for(const pageName of ['users','materials','payrollPeriods','expenses','excelImport'])assert.equal(managerPages.includes(pageName),false,pageName);
      assert.deepEqual(manager.errors,[]);await manager.page.close();
    });
    await t.test('Documents and Excel live flow downloads, archives, previews, applies and rolls back',async()=>{
      const {page,errors}=await fixture(browser,'admin',{width:390,height:844},true);
      const full=['imports.manage','users.manage','clients.manage','rates.employee','rates.client','company.settings','documents.manage','documents.read','payroll.all','payroll.close'];
      await page.evaluate(full=>mock.stage3Permissions=full,full);await login(page);

      await page.evaluate(()=>go('documents'));await page.waitForFunction(()=>document.querySelector('#content').innerText.includes('Готовый документ'));
      assert.equal(await page.locator('#content [data-document-folder]').count(),2);
      assert.match(await page.locator('#content').innerText(),/текущая версия/);
      assert.match(await page.locator('#content').innerText(),/архивная запись/);
      assert.equal(await page.locator('[data-action=downloadPortalDocument]').count(),1);
      await page.locator('[data-action=showPortalDocumentHistory]').first().click();
      await page.waitForSelector('#sheetContent');
      assert.equal(await page.locator('#sheetTitle').innerText(),'История версий документа');
      assert.match(await page.locator('#sheetContent').innerText(),/Старая версия/);
      assert.ok(await page.evaluate(()=>mock.calls.some(c=>c.url==='/api/v3/document-history?id=doc-ready')));
      await page.locator('[data-action=closeSheet]').click();
      await page.locator('[data-action=downloadPortalDocument]').click();await page.waitForFunction(()=>mock.saved?.filename==='PORTAL_report.xlsx');
      await page.locator('[data-action=archivePortalDocument]').click();await page.locator('[data-action=confirmSheet]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.method==='POST'&&c.url==='/api/v3/document-archive'));
      await page.waitForFunction(()=>mock.calls.filter(c=>c.url.startsWith('/api/v3/documents?')).length>=2);
      await page.locator('#docQuery').fill('акт');await page.locator('#documentsFilters').evaluate(form=>form.requestSubmit());
      await page.waitForFunction(()=>mock.calls.some(c=>c.url.includes('/api/v3/documents?')&&c.url.includes('q=%D0%B0%D0%BA%D1%82')));
      assert.equal(await page.locator('#docClient').count(),1);assert.equal(await page.locator('#docEmployee').count(),1);
      await page.locator('#docClient').fill('1');await page.locator('#docEmployee').fill('101');await page.locator('#documentsFilters').evaluate(form=>form.requestSubmit());
      await page.waitForFunction(()=>mock.calls.some(c=>c.url.includes('/api/v3/documents?')&&c.url.includes('client_id=1')&&c.url.includes('employee_id=101')));
      const restricted=await fixture(browser,'packer',{width:390,height:844},true);
      await restricted.page.evaluate(()=>mock.stage3Permissions=['documents.read']);await login(restricted.page);await restricted.page.evaluate(()=>go('documents'));
      await restricted.page.waitForFunction(()=>document.querySelector('#content').innerText.includes('Готовый документ'));
      assert.equal(await restricted.page.locator('#docClient').count(),0);assert.equal(await restricted.page.locator('#docEmployee').count(),0);
      assert.equal(await restricted.page.locator('[data-action=showPortalDocumentHistory]').count(),2);
      assert.equal(await restricted.page.locator('[data-action=archivePortalDocument]').count(),0);
      await restricted.page.locator('[data-action=showPortalDocumentHistory]').first().click();
      await restricted.page.waitForSelector('#sheetContent');
      const readonlyHistory=await restricted.page.locator('#sheetContent').innerText();
      assert.ok(readonlyHistory.indexOf('Версия 1')<readonlyHistory.indexOf('Версия 2'));
      assert.match(readonlyHistory,/Старая версия[\s\S]*В архиве/);
      assert.match(readonlyHistory,/Готовый документ[\s\S]*выбранная версия/);
      assert.ok(await restricted.page.evaluate(()=>mock.calls.some(c=>c.url==='/api/v3/document-history?id=doc-ready')));
      await restricted.page.locator('[data-action=closeSheet]').click();
      assert.deepEqual(restricted.errors,[]);await restricted.page.close();

      const denied=await fixture(browser,'packer',{width:390,height:844},true);
      await denied.page.evaluate(()=>mock.stage3Permissions=[]);await login(denied.page);
      const deniedHistory=await denied.page.evaluate(async()=>{try{await actions.showPortalDocumentHistory({dataset:{id:'doc-ready'}});return '';}catch(error){return error.message;}});
      assert.match(deniedHistory,/Нет права на просмотр документов/);
      assert.equal((await denied.page.evaluate(()=>mock.calls.filter(c=>c.url.startsWith('/api/v3/document-history?')).length)),0);
      await denied.page.close();

      const file={name:'PORTAL_test.xlsx',mimeType:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',buffer:Buffer.from('PK-test')};
      await page.evaluate(()=>go('excelImport'));await page.waitForFunction(()=>document.querySelector('#content').innerText.includes('Шаблон PORTAL 1.1'));
      await page.locator('[data-action=downloadExcelTemplate][data-kind=blank]').click();await page.waitForFunction(()=>mock.saved?.filename==='PORTAL_template_v1.1.xlsx');
      await page.locator('#excelFile').setInputFiles(file);await page.locator('[data-action=previewExcelImport]').click();
      await page.waitForFunction(()=>document.querySelector('#content').innerText.includes('Проверка завершена'));
      assert.equal(await page.locator('[data-action=applyExcelImport]').innerText(),'Применить изменения');
      await page.locator('[data-action=applyExcelImport]').click();await page.evaluate(()=>actions.applyExcelImport());await page.locator('[data-action=confirmSheet]').click();
      await page.waitForFunction(()=>document.querySelector('#content').innerText.includes('Импорт применён'));
      assert.equal((await page.evaluate(()=>mock.calls.filter(c=>c.url==='/api/v3/excel-import-apply').length)),1);
      await page.locator('[data-action=downloadImportResult]').click();await page.waitForFunction(()=>mock.saved?.mime==='application/json');

      await page.evaluate(()=>{mock.previewMode='conflict';mock.applyMode='ok';return go('excelImport');});await page.locator('#excelFile').setInputFiles(file);await page.locator('[data-action=previewExcelImport]').click();
      await page.waitForFunction(()=>document.querySelector('#content').innerText.includes('Конфликты'));
      assert.equal(await page.locator('[data-action=applyExcelImport]').count(),0);

      await page.evaluate(()=>{mock.previewMode='ok';mock.applyMode='failed';return go('excelImport');});await page.locator('#excelFile').setInputFiles(file);await page.locator('[data-action=previewExcelImport]').click();await page.waitForSelector('[data-action=applyExcelImport]');
      await page.locator('[data-action=applyExcelImport]').click();await page.locator('[data-action=confirmSheet]').click();
      await page.waitForFunction(()=>document.querySelector('#content').innerText.includes('Импорт полностью отменён'));
      assert.match(await page.locator('#content').innerText(),/Сервер сохранил безопасный отчёт/);

      await page.evaluate(()=>{mock.previewMode='ok';mock.applyMode='stale';return go('excelImport');});await page.locator('#excelFile').setInputFiles(file);await page.locator('[data-action=previewExcelImport]').click();await page.waitForSelector('[data-action=applyExcelImport]');
      await page.locator('[data-action=applyExcelImport]').click();await page.locator('[data-action=confirmSheet]').click();
      await page.waitForFunction(()=>document.querySelector('#content').innerText.includes('Результат предварительной проверки устарел'));
      assert.deepEqual(errors,[]);await page.close();
    });
    await t.test('receivables screen renders cents-backed aging and applies client and bucket filters',async()=>{
      const {page,errors}=await fixture(browser,'admin',{width:390,height:844},true);
      await page.evaluate(()=>mock.stage3Permissions=['invoices.read']);await login(page);
      await page.evaluate(()=>go('invoices'));await page.locator('[data-action=viewReceivables]').click();
      await page.waitForFunction(()=>document.querySelector('#content').textContent.includes('Дебиторская задолженность'));
      assert.match(await page.locator('#content').innerText(),/125 ₽/);
      assert.match(await page.locator('#content').innerText(),/40 ₽/);
      assert.equal(await page.locator('#content .item').count(),2);
      await page.locator('#receivablesBucket').selectOption('days_1_7');
      await page.waitForFunction(()=>document.querySelectorAll('#content .item').length===1);
      await page.locator('#receivablesClient').selectOption('1');
      await page.waitForFunction(()=>mock.calls.some(c=>c.url.includes('/api/v3/receivables?')&&c.url.includes('client_id=1')));
      assert.deepEqual(errors,[]);await page.close();
    });
    await t.test('payroll settlement role flow records a payment and refreshes append-only balance',async()=>{
      const {page,errors}=await fixture(browser,'admin',{width:390,height:844},true);
      await page.evaluate(()=>mock.stage3Permissions=['payroll.all','payroll.settlement.read','payroll.settlement.payout']);await login(page);
      await page.evaluate(()=>go('payrollPeriods'));await page.locator('[data-action=payrollSettlement]').click();await page.waitForSelector('#sheetContent');
      assert.match(await page.locator('#sheetContent').innerText(),/Выплачено 20 ₽/);assert.match(await page.locator('#sheetContent').innerText(),/Остаток 80 ₽/);
      await page.locator('[data-action=payrollAddPayment]').click();await page.locator('#payrollPaymentAmount').fill('10');
      await page.locator('#payrollPaymentForm [type=submit]').click();await page.waitForFunction(()=>document.querySelector('#sheetContent').textContent.includes('Остаток 70 ₽'));
      const payout=await page.evaluate(()=>mock.calls.find(c=>c.method==='POST'&&c.url==='/api/v3/payroll-settlements'));
      assert.equal(payout.body.entry_type,'payout');assert.equal(payout.body.amount,'10');assert.equal(payout.body.employee_id,1);assert.equal(payout.body.payroll_period_id,'period-1');
      assert.match(await page.locator('#sheetContent').innerText(),/Первая выплата/);assert.deepEqual(errors,[]);await page.close();
      const accountant=await fixture(browser,'accountant',{width:390,height:844},true);
      await accountant.page.evaluate(()=>mock.stage3Permissions=['payroll.all','payroll.settlement.read','payroll.settlement.payout']);await login(accountant.page);
      await accountant.page.evaluate(()=>go('payrollPeriods'));await accountant.page.locator('[data-action=payrollSettlement]').click();await accountant.page.waitForSelector('#sheetContent');
      assert.equal(await accountant.page.locator('[data-action=payrollAddPayment]').count(),1);
      await accountant.page.locator('[data-action=payrollAddPayment]').click();await accountant.page.locator('#payrollPaymentAmount').fill('5');
      await accountant.page.locator('#payrollPaymentForm [type=submit]').click();await accountant.page.waitForFunction(()=>mock.calls.some(c=>c.method==='POST'&&c.url==='/api/v3/payroll-settlements'));
      const accountantPayout=await accountant.page.evaluate(()=>mock.calls.find(c=>c.method==='POST'&&c.url==='/api/v3/payroll-settlements'));
      assert.equal(accountantPayout.body.entry_type,'payout');assert.equal(accountantPayout.body.amount,'5');assert.deepEqual(accountant.errors,[]);await accountant.page.close();
      const manager=await fixture(browser,'manager',{width:390,height:844},true);
      await manager.page.evaluate(()=>mock.stage3Permissions=['payroll.all','payroll.settlement.read']);await login(manager.page);await manager.page.evaluate(()=>go('payrollPeriods'));
      await manager.page.locator('[data-action=payrollSettlement]').click();await manager.page.waitForSelector('#sheetContent');
      assert.equal(await manager.page.locator('[data-action=payrollAddPayment]').count(),0);
      assert.equal((await manager.page.evaluate(()=>mock.calls)).some(c=>c.method==='POST'&&c.url==='/api/v3/payroll-settlements'),false);
      assert.deepEqual(manager.errors,[]);await manager.page.close();
    });
    await t.test('company settings are discoverable only to company.settings capability',async()=>{
      const director=await fixture(browser,'director',{width:390,height:844},true);
      await director.page.evaluate(()=>mock.stage3Permissions=['company.settings']);await login(director.page);
      await director.page.evaluate(()=>go('settings'));
      assert.equal(await director.page.locator('[data-page="control"]').count(),1);
      await director.page.locator('[data-page="control"]').click();
      await director.page.waitForFunction(()=>document.querySelector('#content').textContent.includes('Правила сохранены')||document.querySelector('#content').textContent.includes('Понедельник'));
      assert.equal(await director.page.locator('#controlMonday').inputValue(),'10:00');
      assert.equal(await director.page.locator('#controlWednesday').inputValue(),'11:00');
      assert.equal(await director.page.locator('#reminderEnabled').inputValue(),'false');
      assert.equal(await director.page.locator('#reminderCadence').inputValue(),'daily');
      await director.page.locator('#controlMonday').fill('09:30');await director.page.locator('#controlForm [type=submit]').click();
      await director.page.waitForFunction(()=>mock.calls.some(c=>c.method==='POST'&&c.url==='/api/v3/settings'));
      const saved=await director.page.evaluate(()=>mock.calls.find(c=>c.method==='POST'&&c.url==='/api/v3/settings'));
      assert.equal(saved.body.monday_time,'09:30');assert.equal(saved.body.utc_offset_minutes,180);assert.equal(Object.hasOwn(saved.body,'company_id'),false);
      await director.page.locator('#reminderEnabled').selectOption('true');await director.page.locator('#reminderCadence').selectOption('weekly');
      await director.page.locator('#controlForm [type=submit]').click();await director.page.waitForFunction(()=>mock.calls.filter(c=>c.method==='POST'&&c.url==='/api/v3/settings').length===2);
      const reminders=await director.page.evaluate(()=>mock.calls.filter(c=>c.method==='POST'&&c.url==='/api/v3/settings').at(-1).body);
      assert.equal(reminders.reminder_enabled,true);assert.equal(reminders.reminder_cadence,'weekly');
      assert.deepEqual(director.errors,[]);await director.page.close();
      const manager=await fixture(browser,'manager',{width:390,height:844},true);
      await manager.page.evaluate(()=>mock.stage3Permissions=['work.write','tasks.read']);await login(manager.page);
      await manager.page.evaluate(()=>go('settings'));
      assert.equal(await manager.page.locator('[data-page="control"]').count(),0);
      assert.deepEqual(manager.errors,[]);await manager.page.close();
    });
    await t.test('admin invite flow displays one-time token only after create; manager cannot open users',async()=>{
      const {page,errors}=await fixture(browser,'admin',{width:390,height:844},true);
      await page.evaluate(()=>mock.stage3Permissions=['users.manage']);await login(page);
      await page.evaluate(()=>go('users'));await page.locator('[data-action=createAccessInvite]').click();
      await page.locator('#inviteName').fill('Новый сотрудник');await page.locator('#inviteUsername').fill('new-staff');
      await page.locator('#accessInviteForm [type=submit]').click();await page.waitForSelector('#oneTimeInviteToken');
      const token=await page.locator('#oneTimeInviteToken').inputValue();assert.ok(token.length>=40);
      const calls=await page.evaluate(()=>mock.calls);const create=calls.find(c=>c.method==='POST'&&c.url==='/api/v3/invitations');
      assert.equal(create.body.action,'create');assert.equal(Object.hasOwn(create.body,'pin'),false);
      assert.equal(calls.some(c=>c.url.includes(encodeURIComponent(token))||c.url.includes('pin=')),false);
      await page.close();
      const manager=await fixture(browser,'manager',{width:390,height:844},true);await manager.page.evaluate(()=>mock.stage3Permissions=['work.write','tasks.read','finance.read','invoices.read','payroll.own']);await login(manager.page);
      await manager.page.evaluate(()=>go('users'));await manager.page.waitForTimeout(100);
      assert.equal(await manager.page.locator('[data-action=createAccessInvite]').count(),0);
      assert.equal((await manager.page.evaluate(()=>mock.calls)).some(c=>c.url.startsWith('/api/v3/invitations')),false);
      assert.deepEqual(manager.errors,[]);await manager.page.close();
    });
    await t.test('invitee submits one-time code and private PIN only in the accept request body',async()=>{
      const {page,errors}=await fixture(browser,'admin',{width:390,height:844},true);
      await page.locator('[data-action=acceptInvite]').click();await page.waitForSelector('#acceptInviteForm');
      const token='1.synthetic-invitation-code';const pin='9876';
      await page.locator('#acceptInviteToken').fill(token);await page.locator('#acceptInvitePin').fill(pin);
      await page.locator('#acceptInviteForm [type=submit]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.method==='POST'&&c.url==='/api/access-invites/accept'));
      const request=await page.evaluate(()=>mock.calls.find(c=>c.method==='POST'&&c.url==='/api/access-invites/accept'));
      assert.deepEqual(request.body,{token,pin});
      assert.equal(new URL(request.url,'https://portal.example').search,'');
      assert.doesNotMatch(page.url(),/9876|synthetic-invitation-code/);
      await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('Запрос отправлен'));
      assert.equal(await page.locator('#acceptInviteForm').count(),0);
      assert.deepEqual(errors,[]);await page.close();
    });
    await t.test('director approves access requests and packer cannot decide invitations',async()=>{
      const {page,errors}=await fixture(browser,'director',{width:390,height:844},true);
      await page.evaluate(()=>{mock.stage3Permissions=['users.manage'];mock.invites=[
        {id:'access-request-1',status:'accepted',display_name:'Новый запрос',username:'requester',role:'packer',expires_at:'2026-10-07'},
        {id:'invite-pending-1',status:'pending',display_name:'Приглашённый',username:'invitee',role:'manager',expires_at:'2026-10-07'}
      ];});await login(page);await page.evaluate(()=>go('users'));
      await page.waitForFunction(()=>document.querySelector('#content').textContent.includes('Новый запрос'));
      assert.ok(await page.locator('[data-action=decideAccessInvite][data-id=access-request-1][data-decision=approve]').count());
      await page.locator('[data-action=decideAccessInvite][data-id=access-request-1][data-decision=approve]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.method==='POST'&&c.url==='/api/v3/invitations'&&c.body?.action==='approve'));
      await page.waitForFunction(()=>document.querySelector('#content').textContent.includes('approved'));
      assert.equal((await page.evaluate(()=>mock.invites.find(i=>i.id==='access-request-1').status)),'approved');
      await page.locator('[data-action=decideAccessInvite][data-id=invite-pending-1][data-decision=revoke]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.method==='POST'&&c.url==='/api/v3/invitations'&&c.body?.action==='revoke'));
      await page.waitForFunction(()=>document.querySelector('#content').textContent.includes('revoked'));
      assert.equal((await page.evaluate(()=>mock.invites.find(i=>i.id==='invite-pending-1').status)),'revoked');
      assert.equal(await page.locator('[data-action=decideAccessInvite][data-id=access-request-1]').count(),0);
      assert.equal(await page.locator('[data-action=decideAccessInvite][data-id=invite-pending-1]').count(),0);
      await page.locator('[data-action=createAccessInvite]').click();
      await page.locator('#inviteName').fill('Новое приглашение директора');await page.locator('#inviteUsername').fill('director-invitee');
      await page.locator('#accessInviteForm [type=submit]').click();await page.waitForSelector('#oneTimeInviteToken');
      const directorCreate=(await page.evaluate(()=>mock.calls)).find(c=>c.method==='POST'&&c.url==='/api/v3/invitations'&&c.body?.username==='director-invitee');
      assert.equal(directorCreate.body.action,'create');assert.equal(Object.hasOwn(directorCreate.body,'pin'),false);
      await page.evaluate(()=>closeSheet());await page.locator('[data-action=companyAudit]').click();await page.waitForSelector('#auditEntity');
      await page.locator('#auditAction').fill('access_invite.created');await page.locator('#auditFilterForm [type=submit]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.url.startsWith('/api/v3/audit?')&&c.url.includes('action=access_invite.created')));
      assert.equal((await page.evaluate(()=>mock.calls)).some(c=>c.url.startsWith('/api/platform/audit?')),false);
      assert.deepEqual(errors,[]);await page.close();
      const packer=await fixture(browser,'packer',{width:390,height:844},true);
      await packer.page.evaluate(()=>{mock.stage3Permissions=['work.write','tasks.read'];mock.invites=[
        {id:'access-request-foreign-role',status:'accepted',display_name:'Запрос',username:'requester',role:'packer',expires_at:'2026-10-07'}
      ];});await login(packer.page);await packer.page.evaluate(()=>go('users'));
      await packer.page.waitForFunction(()=>!document.querySelector('.loading'));
      assert.equal(await packer.page.locator('[data-action=decideAccessInvite]').count(),0);
      assert.equal((await packer.page.evaluate(()=>mock.calls)).some(c=>c.url.startsWith('/api/v3/invitations')),false);
      assert.deepEqual(packer.errors,[]);await packer.page.close();
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
    await t.test('God requires company and confirmation, switches scope and rejects stale data',async()=>{
      const {page,errors}=await fixture(browser,'platform_owner');
      assert.equal(await page.locator('[data-action=technicalLogin]').count(),0);
      assert.equal((await page.locator('#auth').innerText()).includes('God'),false);
      await login(page);
      assert.equal(await page.evaluate(()=>mock.calls.some(c=>c.url==='/api/login')),true);
      assert.equal(await page.locator('#companyName').innerText(),'God');
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
    await t.test('God invitation writes require selected company confirmation and stay in support audit',async()=>{
      const {page,errors}=await fixture(browser,'platform_owner',{width:390,height:844},true);
      await login(page);
      await page.locator('[data-action=selectCompany][data-id="2"]').click();await page.locator('[data-action=confirmSheet]').click();
      await page.waitForSelector('#supportStrip:not(.hidden)');await page.waitForFunction(()=>S.page==='dashboard'&&!document.querySelector('.loading')&&S.writes===0);
      const support=await page.evaluate(async()=>{await go('users');return {page:S.page,company:S.company?.id,stage3:S.stage3};});
      assert.equal(support.page,'users',JSON.stringify(support));await page.locator('[data-action=createAccessInvite]').click();
      await page.locator('#inviteName').fill('Сотрудник второй компании');await page.locator('#inviteUsername').fill('second-company-staff');
      await page.locator('#accessInviteForm [type=submit]').click();
      await page.waitForFunction(()=>document.querySelector('#sheetContent').textContent.includes('Компания: Вторая компания · #2'));
      assert.equal((await page.evaluate(()=>mock.calls)).some(c=>c.method==='POST'&&c.url==='/api/v3/invitations'),false);
      await page.locator('[data-action=confirmSheet]').click();await page.waitForSelector('#oneTimeInviteToken');
      const calls=await page.evaluate(()=>mock.calls),create=calls.find(c=>c.method==='POST'&&c.url==='/api/v3/invitations');
      assert.equal(create.company,'2');assert.equal(create.body.action,'create');assert.equal(Object.hasOwn(create.body,'pin'),false);
      assert.ok((await page.locator('#oneTimeInviteToken').inputValue()).length>=40);
      await page.evaluate(()=>{closeSheet();actions.exitSupport();});await page.waitForSelector('[data-action=selectCompany]');
      assert.equal(await page.locator('#oneTimeInviteToken').count(),0);assert.equal(await page.locator('#supportStrip').isVisible(),false);
      await page.locator('[data-action=audit]').click();await page.waitForSelector('#ownerAuditCompany');
      await page.locator('#ownerAuditCompany').fill('2');await page.locator('#ownerAuditEvent').fill('god_access');
      await page.locator('#ownerAuditFilterForm [type=submit]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.url.startsWith('/api/platform/audit?')&&c.url.includes('company_id=2')&&c.url.includes('event=god_access')));
      assert.deepEqual(errors,[]);await page.close();
    });
    await t.test('God audit is separate and filters are sent only from God surface',async()=>{
      const {page,errors}=await fixture(browser,'platform_owner');
      await login(page);
      await page.locator('[data-action=audit]').click();await page.waitForSelector('#ownerAuditCompany');
      assert.match(await page.locator('#sheetContent').innerText(),/Только действия God и системные события/);
      await page.locator('#ownerAuditCompany').fill('2');await page.locator('#ownerAuditActor').fill('1');
      await page.locator('#ownerAuditEvent').fill('god_access');await page.locator('#ownerAuditFrom').fill('2026-09-01');await page.locator('#ownerAuditTo').fill('2026-09-30');
      await page.locator('#ownerAuditFilterForm [type=submit]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.url.startsWith('/api/platform/audit?')&&c.url.includes('company_id=2')));
      const url=await page.evaluate(()=>mock.calls.filter(c=>c.url.startsWith('/api/platform/audit?')).at(-1).url);
      assert.match(url,/actor_id=1/);assert.match(url,/event=god_access/);assert.match(url,/from=2026-09-01/);assert.match(url,/to=2026-09-30/);
      assert.match(await page.locator('#sheetContent').innerText(),/Запросы и секреты в журнал не включаются/);
      assert.deepEqual(errors,[]);await page.close();
    });
    await t.test('God module switches are explicit and submitted with company scope',async()=>{
      const {page,errors}=await fixture(browser,'platform_owner');
      await login(page);
      await page.locator('[data-action=editPlatformCompany][data-id="2"]').click();
      assert.equal(await page.locator('[data-platform-module]').count(),23);
      await page.locator('#module-toggle-work').uncheck();
      await page.locator('#platformCompanyForm [type=submit]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.method==='POST'&&c.url==='/api/platform/companies/2'));
      const saved=await page.evaluate(()=>mock.calls.findLast(c=>c.method==='POST'&&c.url==='/api/platform/companies/2'));
      assert.equal(saved.body.module_toggles.work,false);assert.equal(saved.company,'');
      assert.deepEqual(errors,[]);await page.close();
    });
    await t.test('God saves company subscription state and override while PORTAL stays unlimited',async()=>{
      const {page,errors}=await fixture(browser,'platform_owner');
      await login(page);
      await page.locator('[data-action=editPlatformCompany][data-id="2"]').click();
      assert.equal(await page.locator('#platformCompanyLimit').inputValue(),'15');
      await page.locator('#platformCompanyLimit').fill('16');await page.locator('#platformCompanyFee').fill('123.45');
      await page.selectOption('#platformCompanyStatus','suspended');await page.selectOption('#platformServiceStatus','expired');
      await page.locator('#platformDemoEnabled').check();await page.locator('#platformDemoStart').fill('2026-09-01T09:00');await page.locator('#platformDemoEnd').fill('2026-10-01T18:00');
      await page.locator('#module-toggle-work').uncheck();await page.locator('#platformCompanyForm [type=submit]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.method==='POST'&&c.url==='/api/platform/companies/2'));
      const saved=await page.evaluate(()=>mock.calls.findLast(c=>c.method==='POST'&&c.url==='/api/platform/companies/2'));
      assert.equal(saved.body.user_limit,16);assert.equal(saved.body.monthly_price,12345);assert.equal(saved.body.status,'suspended');assert.equal(saved.body.service_status,'expired');
      assert.equal(saved.body.demo_enabled,1);assert.equal(saved.body.demo_start,'2026-09-01T09:00:00');assert.equal(saved.body.demo_end,'2026-10-01T18:00:00');assert.equal(saved.body.module_toggles.work,false);
      await page.waitForSelector('[data-action=editPlatformCompany][data-id="1"]');await page.locator('[data-action=editPlatformCompany][data-id="1"]').click();
      assert.equal(await page.locator('#platformCompanyLimit').isDisabled(),true);
      await page.locator('#platformCompanyForm [type=submit]').click();await page.waitForFunction(()=>mock.calls.filter(c=>c.method==='POST'&&c.url==='/api/platform/companies/1').length===1);
      const portalSave=await page.evaluate(()=>mock.calls.find(c=>c.method==='POST'&&c.url==='/api/platform/companies/1'));
      assert.equal(Object.hasOwn(portalSave.body,'user_limit'),false);assert.deepEqual(errors,[]);await page.close();
    });
    await t.test('analytics compares company-local periods and labels missing timing honestly',async()=>{
      const {page,errors}=await fixture(browser,'admin',{width:390,height:844},true);
      await page.evaluate(()=>mock.stage3Permissions=['analytics.read']);await login(page);await page.evaluate(()=>go('analytics'));
      await page.locator('#analyticsFrom').fill('2026-09-10');await page.locator('#analyticsTo').fill('2026-09-16');
      await page.locator('#analyticsFilterForm [type=submit]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.url==='/api/v3/analytics?from=2026-09-10&to=2026-09-16'));
      await page.waitForFunction(()=>document.querySelector('#content').innerText.includes('Объём за период'));
      assert.match(await page.locator('#content').innerText(),/10\.09\.2026–16\.09\.2026 · сравнение с 03\.09\.2026–09\.09\.2026/);
      assert.match(await page.locator('#content').innerText(),/Объём за период\s+12 шт\./);
      assert.match(await page.locator('#content').innerText(),/Изменение объёма\s+4 шт\. · 50%/);
      assert.match(await page.locator('#content').innerText(),/Изменение темпа\s+2 шт\.\/ч/);
      assert.match(await page.locator('#content').innerText(),/Анна Сборщик[\s\S]*Клиент · Упаковка[\s\S]*разброс темпа 25%/);
      assert.match(await page.locator('#content').innerText(),/PRT-2026-000001 · Упаковка[\s\S]*разброс темпа 10%/);
      assert.match(await page.locator('#content').innerText(),/Источник данных о дефектах пока не заполнен/);
      assert.deepEqual(errors,[]);await page.close();
    });
    await t.test('client product catalog supports stable-ID create, rename and archive',async()=>{
      const {page,errors}=await fixture(browser,'admin',{width:390,height:844},true);await page.evaluate(()=>mock.stage3Permissions=['work.write','tasks.read','tasks.manage','batches.receive','finance.read','invoices.read','invoices.create','users.manage','clients.read','clients.manage','documents.read','access.history.read','payroll.own','rates.employee','rates.client']);await login(page);
      await page.evaluate(async()=>{mock.clientNameOverride='Борискин';mock.clientAliases=[{client_id:1,alias:'Борисенко',source:'knowledge'}];mock.stage3Invoices=[{id:1,client_id:1,remaining:12500}];mock.stage3Shipments=[{id:'ship-client',batch_id:'batch-1',client_id:1,direction:'FBS',quantity:10},{id:'return-client',type:'return',batch_id:'batch-1',client_id:1,direction:'FBS',quantity:2,condition:'damaged'},{id:'ship-other',batch_id:'batch-other',client_id:2,direction:'FBO',quantity:99}];mock.stage3Tasks=[{id:'task-client',batch_id:'batch-1',batch_number:'PRT-2026-000001',operation_name:'Упаковка клиента',quantity:10,done:2,remaining:8},{id:'task-other',batch_id:'batch-other',batch_number:'PRT-OTHER',operation_name:'Чужая партия',quantity:1,done:0,remaining:1}];mock.clientNameHistory=[{client_id:1,old_name:'Старое название',new_name:'Новое <имя>',occurred_at:'2026-09-30T10:00:00'}];mock.tariffHistory=[{operation_id:1,effective_from:'2026-01-01T00:00:00',employee_rate:200,client_rate:500},{operation_id:1,effective_from:'2099-01-01T00:00:00',employee_rate:300,client_rate:700}];await go('clients');});await page.waitForSelector('#clientSearch');
      await page.locator('#clientSearch').fill('Старое название');assert.equal(await page.locator('#content [data-action=openClient]').isVisible(),true);
      await page.locator('#clientSearch').fill('Борисенко');assert.equal(await page.locator('#content [data-action=openClient]').isVisible(),true);
      assert.equal(await page.evaluate(()=>mock.calls.some(c=>c.url.startsWith('/api/v3/client-aliases'))),true);
      assert.match(await page.locator('#content').innerText(),/Ранее: Старое название/);
      await page.locator('#clientSearch').fill('несуществующий клиент');assert.equal(await page.locator('#content [data-action=openClient]').isVisible(),false);
      assert.equal(await page.locator('#content .empty').filter({hasText:'Клиенты по этому запросу не найдены'}).isVisible(),true);
      const shipmentProbe=await page.evaluate(async()=>{const raw=await productionGet('shipments'),batches=await productionGet('batches'),ids=new Set(batches.filter(b=>b.client_id===1).map(b=>String(b.id)));return {allowed:allowed('batches.receive'),raw,filtered:raw.filter(s=>s.client_id===1&&ids.has(String(s.batch_id)))};});
      assert.equal(shipmentProbe.allowed,true,JSON.stringify(shipmentProbe));assert.equal(shipmentProbe.raw.length,3,JSON.stringify(shipmentProbe));assert.equal(shipmentProbe.filtered.length,2,JSON.stringify(shipmentProbe));
      await page.locator('#clientSearch').fill('');await page.locator('#content [data-action=openClient]').click();
      await page.waitForFunction(()=>document.querySelector('#sheetContent')?.textContent.includes('Реквизиты и контакты'));
      assert.match(await page.locator('#sheetContent').innerText(),/Задания по партиям клиента[\s\S]*Упаковка клиента · PRT-2026-000001[\s\S]*2 \/ 10 · осталось 8/);
      assert.doesNotMatch(await page.locator('#sheetContent').innerText(),/Чужая партия|PRT-OTHER/);
      assert.equal(await page.evaluate(()=>mock.calls.some(c=>c.url==='/api/v3/tasks')),true);
      assert.equal(await page.evaluate(()=>mock.calls.some(c=>c.url==='/api/v3/shipments')),true);
      assert.match(await page.locator('#sheetContent').innerText(),/Отгрузки и возвраты[\s\S]*Возврат · FBS[\s\S]*2 шт\. · Повреждённый[\s\S]*Отгрузка · FBS[\s\S]*10 шт\./);
      assert.doesNotMatch(await page.locator('#sheetContent').innerText(),/99 шт\.|FBO/);
      assert.match(await page.locator('#sheetContent').innerText(),/Старое название → Новое <имя>/);
      assert.match(await page.locator('#sheetContent').innerText(),/TEST-INN-001/);
      await page.locator('[data-action=editClientRequisites]').click();await page.locator('#clientReqInn').fill('TEST-INN-002');
      await page.locator('#clientRequisitesForm [type=submit]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.method==='POST'&&c.url==='/api/v3/client-requisites'));
      const requisites=await page.evaluate(()=>mock.calls.find(c=>c.method==='POST'&&c.url==='/api/v3/client-requisites'));
      assert.equal(requisites.body.client_id,1);assert.equal(requisites.body.inn,'TEST-INN-002');assert.equal('company_id' in requisites.body,false);
      await page.waitForFunction(()=>document.querySelector('#sheetContent')?.textContent.includes('TEST-INN-002'));
      assert.match(await page.locator('#sheetContent').innerText(),/История ставок · 2/);
      await page.locator('#sheetContent details summary').click();
      assert.match(await page.locator('#sheetContent').innerText(),/Действует сейчас/);
      assert.match(await page.locator('#sheetContent').innerText(),/Будущая версия/);
      assert.equal(await page.locator('[data-action=newTariff][data-return-to-client="true"]').count(),1);
      assert.equal(await page.locator('[data-action=clientOperations]').count(),1);
      await page.locator('[data-action=newTariff][data-return-to-client="true"]').click();await page.waitForSelector('#tariffForm');
      await page.locator('#tariffEmployee').fill('2.50');await page.locator('#tariffClient').fill('5.50');
      await page.locator('#tariffForm [type=submit]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.method==='POST'&&c.url==='/api/v3/tariffs'));
      const tariffWrite=await page.evaluate(()=>mock.calls.find(c=>c.method==='POST'&&c.url==='/api/v3/tariffs'));
      assert.equal(tariffWrite.body.client_id,1);assert.equal(tariffWrite.body.operation_id,1);assert.equal(tariffWrite.body.employee_rate,'2.50');assert.equal(tariffWrite.body.client_rate,'5.50');
      await page.waitForFunction(()=>document.querySelector('#sheetContent')?.textContent.includes('Реквизиты и контакты'));
      await page.locator('[data-action=clientOperations]').click();await page.waitForFunction(()=>document.querySelector('#content')?.textContent.includes('Операции клиента'));
      assert.equal(await page.locator('#content [data-action=editOperation]').count()>0,true);
      assert.equal(await page.evaluate(()=>mock.calls.some(c=>c.url==='/api/admin/clients/1/operations')),true);
      await page.evaluate(()=>actions.openClient({dataset:{id:'1'}}));await page.waitForSelector('[data-action=manageClientProducts]');
      await page.locator('[data-action=manageClientProducts]').click();await page.locator('[data-action=newCatalogProduct]').click();
      await page.locator('#catalogProductName').fill('Коробка');await page.locator('#catalogProductForm [type=submit]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.method==='POST'&&c.url==='/api/v3/products'&&c.body?.action==='create'));
      const create=await page.evaluate(()=>mock.calls.find(c=>c.method==='POST'&&c.url==='/api/v3/products'&&c.body?.action==='create'));
      assert.equal(create.body.client_id,1);assert.equal(create.body.name,'Коробка');
      await page.locator('#productSearch').fill('missing');assert.equal(await page.locator('#clientProductRows [data-product-name]').isVisible(),false);
      await page.locator('#productSearch').fill('короб');assert.equal(await page.locator('#clientProductRows [data-product-name]').isVisible(),true);
      await page.locator('[data-action=editCatalogProduct]').click();await page.waitForSelector('#catalogProductForm');await page.locator('#catalogProductName').fill('Коробка новая');await page.locator('#catalogProductForm [type=submit]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.method==='POST'&&c.url==='/api/v3/products'&&c.body?.action==='update'));
      await page.locator('[data-action=archiveCatalogProduct]').click();await page.waitForFunction(()=>mock.calls.some(c=>c.method==='POST'&&c.url==='/api/v3/products'&&c.body?.action==='archive'));
      await page.evaluate(()=>actions.openClient({dataset:{id:'1'}}));await page.waitForSelector('[data-action=openClientDocuments]');
      await page.locator('[data-action=openClientDocuments]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.url.startsWith('/api/v3/documents?')&&c.url.includes('client_id=1')));
      assert.equal(await page.locator('#docClient').inputValue(),'1');
      await page.evaluate(()=>actions.openClient({dataset:{id:'1'}}));await page.waitForSelector('[data-action=openClientReceivables]');
      assert.equal(await page.locator('[data-action=openClientReceivables]').count(),1);
      await page.locator('[data-action=openClientReceivables]').last().click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.url.startsWith('/api/v3/receivables?')&&c.url.includes('client_id=1')));
      assert.equal(await page.locator('#receivablesClient').inputValue(),'1');
      assert.deepEqual(errors,[]);await page.close();
      const restricted=await fixture(browser,'manager',{width:390,height:844},true);
      await restricted.page.evaluate(()=>mock.stage3Permissions=['clients.read']);await login(restricted.page);await restricted.page.evaluate(()=>go('clients'));
      await restricted.page.waitForSelector('#clientSearch');await restricted.page.locator('#content [data-action=openClient]').click();
      await restricted.page.waitForFunction(()=>document.querySelector('#sheetContent')?.textContent.includes('Реквизиты и контакты'));
      assert.equal(await restricted.page.locator('[data-action=editClientRequisites]').count(),0);
      assert.equal(await restricted.page.locator('[data-action=clientOperations]').count(),0);
      assert.equal(await restricted.page.locator('[data-action=newTariff]').count(),0);
      assert.equal(await restricted.page.evaluate(()=>mock.calls.some(c=>c.url==='/api/v3/tasks')),false);
      assert.equal(await restricted.page.evaluate(()=>actions.openClientReceivables({dataset:{id:'1'}}).then(()=>false).catch(error=>error.message==='Недостаточно прав для просмотра дебиторки')),true);
      assert.deepEqual(restricted.errors,[]);await restricted.page.close();
    });
    await t.test('batch economics labels an absent plan as unavailable',async()=>{
      const {page,errors}=await fixture(browser,'admin',{width:390,height:844},true);await login(page);await page.evaluate(()=>go('batches'));
      await page.waitForSelector('[data-action=batchEconomy]');await page.locator('[data-action=batchEconomy]').click();await page.waitForSelector('#sheetContent');
      assert.match(await page.locator('#sheetContent').innerText(),/Недоступно/);
      assert.deepEqual(errors,[]);await page.close();
    });
    await t.test('Client 360 identifies a failed source instead of silently presenting a complete card',async()=>{
      const {page,errors}=await fixture(browser,'admin',{width:390,height:844},true);
      await page.evaluate(()=>{mock.stage3Permissions=['clients.read','batches.receive','clients.manage'];mock.failUrls=['/api/v3/shipments'];});
      await login(page);await page.evaluate(()=>actions.openClient({dataset:{id:'1'}}));await page.waitForSelector('#sheetContent');
      const rendered=await page.locator('#sheetContent').innerText();
      assert.match(rendered,/Карточка загружена частично/);assert.match(rendered,/Не удалось загрузить: Отгрузки и возвраты/);
      assert.match(rendered,/Реквизиты и контакты/);assert.deepEqual(errors,[]);await page.close();
    });
    await t.test('finance radar combines source-backed profitability, receivables and financial attention with capability gating',async()=>{
      const {page,errors}=await fixture(browser,'admin',{width:390,height:844},true);
      await page.evaluate(()=>{mock.stage3Permissions=['finance.read','invoices.read'];mock.stage3Finance={clients:[{client_id:1,client_name:'Клиент прибыль',revenue:10000,salary:3000,materials:1000,other:500,profit:5500,margin:0.55,margin_bps:5500,average_batch_profit:2750},{client_id:2,client_name:'Клиент убыток',revenue:2000,salary:1800,materials:500,other:200,profit:-500,margin_bps:-2500,average_batch_profit:-500}],months:{'2026-08':{revenue:8000,salary:3000,materials:1000,other:500,overhead:2000,profit:1500,margin_bps:1875},'2026-09':{revenue:10000,salary:4000,materials:1200,other:700,overhead:2500,profit:1600,margin_bps:1600}},totals:{revenue:12000,salary:4800,materials:1500,other:700},client_profit:5000,client_margin_bps:4167,company_overhead:1000,net_profit:4000,net_margin_bps:3333};mock.stage3Today={date:'2026-09-30',mode:'management',tasks:[],attention:[{type:'payment_late',label:'Просрочен платёж',amount:4000},{type:'batch_late',label:'Просрочена партия'}]};});
      await login(page);await page.evaluate(()=>go('radar'));await page.waitForSelector('#content h2');
      let rendered=await page.locator('#content').innerText();
      for(const label of ['Прибыль клиентов','Общие расходы','Чистая прибыль','Убыточные клиенты','Открытая дебиторка','Просрочено','Открытые счета','Требует внимания','Просрочен платёж','Динамика по месяцам','ФОТ','Материалы','Расходы по клиентам','Прибыль'])assert.ok(rendered.includes(label),`missing ${label}`);
      assert.match(rendered,/Убыточные клиенты\s+1/);assert.match(rendered,/Открытая дебиторка\s+125/);assert.match(rendered,/Просрочено\s+40/);
      assert.doesNotMatch(rendered,/Просрочена партия/);assert.ok(rendered.indexOf('2026-09')<rendered.indexOf('2026-08'));
      assert.equal(await page.evaluate(()=>mock.calls.some(c=>c.url.startsWith('/api/v3/receivables?'))),true);
      await page.evaluate(()=>{S.me.permissions=S.me.permissions.filter(p=>p!=='invoices.read');mock.calls=[];mock.stage3Today={date:'2026-09-30',mode:'management',tasks:[],attention:[]};void go('radar');});
      await page.waitForFunction(()=>document.querySelector('#content').textContent.includes('Финансовый радар')&&!document.querySelector('.loading'));
      rendered=await page.locator('#content').innerText();
      assert.doesNotMatch(rendered,/Открытая дебиторка|Просрочено|Открытые счета/);
      assert.equal(await page.evaluate(()=>mock.calls.some(c=>c.url.startsWith('/api/v3/receivables?'))),false);
      assert.deepEqual(errors,[]);await page.close();
    });
    await t.test('batch economics shows basis-point margins and per-unit profit without inventing zero',async()=>{
      const {page,errors}=await fixture(browser,'admin',{width:390,height:844},true);
      await page.evaluate(()=>{mock.stage3Economy={plan:{salary:400,revenue:1000,materials:0,other:100,profit:500,volume:2},fact:{salary:200,revenue:500,materials:0,other:25,profit:275,volume:1},deviation:{salary:-200,revenue:-500,materials:0,other:-75,profit:-225,volume:-1},margin_bps:{plan:5050,fact:null,deviation:null},finished_units:1,cost_per_unit:225,profit_per_unit:275};});
      await login(page);await page.evaluate(()=>go('batches'));await page.locator('[data-action=batchEconomy]').click();await page.waitForSelector('#sheetContent');
      const rendered=await page.locator('#sheetContent').innerText();
      assert.match(rendered,/Маржа[\s\S]*50,5% → Недоступно/);assert.match(rendered,/Себестоимость единицы: 2,25/);assert.match(rendered,/Прибыль на единицу: 2,75/);
      assert.deepEqual(errors,[]);await page.close();
    });
    await t.test('planned batch overhead is submitted only with finance capability',async()=>{
      const batch={id:'batch-plan-role',number:'PRT-PLAN-ROLE',client_id:1,client_name:'Клиент',product:'Коробка',received_at:'2026-09-24',quantity:2,done:0,remaining:2,stage:'in_progress',ready:false};
      const users=[{id:2,display_name:'Исполнитель',employee_id:102,active:true}];
      for(const [role,permissions,expectCost] of [['admin',['tasks.manage','batches.receive','finance.read'],'1.25'],['manager',['tasks.manage','batches.receive'],null]]){
        const {page,errors}=await fixture(browser,role,{width:390,height:844},true);
        await page.evaluate(({permissions,batch,users})=>{mock.stage3Permissions=permissions;mock.stage3Batches=[batch];mock.stage3Users=users;},{permissions,batch,users});
        await login(page);await page.evaluate(()=>go('batches'));await page.locator('[data-action=createTask]').click();await page.waitForSelector('#taskOperation');
        assert.equal(await page.locator('#taskOther').count(),expectCost?1:0);
        await page.selectOption('#taskOperation','1');await page.selectOption('#taskAssignees','2');
        if(expectCost)await page.locator('#taskOther').fill(expectCost);
        await page.locator('#createTaskForm [type=submit]').click();
        await page.waitForFunction(()=>mock.calls.some(c=>c.method==='POST'&&c.url==='/api/v3/tasks'));
        const created=await page.evaluate(()=>mock.calls.find(c=>c.method==='POST'&&c.url==='/api/v3/tasks'));
        if(expectCost)assert.equal(created.body.other_cost,expectCost);else assert.equal(Object.hasOwn(created.body,'other_cost'),false);
        assert.deepEqual(errors,[]);await page.close();
      }
    });
    await t.test('shipped batch return flow is visible, permission aware and submits quantity/result',async()=>{
      const {page,errors}=await fixture(browser,'admin',{width:390,height:844},true);
      await page.evaluate(()=>{mock.stage3Batches=[{id:'batch-return',number:'PRT-RETURN',client_id:1,client_name:'Клиент',product:'Коробка',received_at:'2026-09-24',quantity:10,done:10,remaining:0,stage:'partially_returned',returned_quantity:2,returnable_quantity:8,ready:true}];});
      await login(page);await page.evaluate(()=>go('batches'));await page.waitForSelector('[data-action=returnBatch]');
      assert.match(await page.locator('#content').innerText(),/Частично возвращена/);
      await page.locator('[data-action=returnBatch]').click();await page.locator('#returnQuantity').fill('3');await page.selectOption('#returnCondition','damaged');await page.locator('#returnComment').fill('Повреждение');await page.locator('#returnForm [type=submit]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.method==='POST'&&c.url==='/api/v3/returns'));
      const saved=await page.evaluate(()=>mock.calls.find(c=>c.method==='POST'&&c.url==='/api/v3/returns'));
      assert.deepEqual({batch_id:saved.body.batch_id,quantity:saved.body.quantity,condition:saved.body.condition,comment:saved.body.comment},{batch_id:'batch-return',quantity:3,condition:'damaged',comment:'Повреждение'});
      assert.deepEqual(errors,[]);await page.close();
      const worker=await fixture(browser,'packer',{width:390,height:844},true);await login(worker.page);await worker.page.evaluate(()=>go('batches'));
      await worker.page.waitForFunction(()=>S.page==='batches'&&!document.querySelector('.loading'));
      assert.equal(await worker.page.locator('[data-action=returnBatch]').count(),0);assert.deepEqual(worker.errors,[]);await worker.page.close();
    });
    await t.test('ready batch shipment flow records the selected FBO/FBS direction',async()=>{
      const {page,errors}=await fixture(browser,'admin',{width:390,height:844},true);
      await page.evaluate(()=>{mock.stage3Batches=[{id:'batch-ready',number:'PRT-READY',client_id:1,client_name:'Клиент',product:'Коробка',received_at:'2026-09-24',quantity:4,done:4,remaining:0,stage:'ready',returned_quantity:0,returnable_quantity:0,ready:true}];});
      await login(page);await page.evaluate(()=>go('batches'));await page.waitForSelector('[data-action=shipBatch]');
      await page.locator('[data-action=shipBatch]').click();await page.selectOption('#shipDirection','FBO');await page.locator('#shipForm [type=submit]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.method==='POST'&&c.url==='/api/v3/shipments'));
      const saved=await page.evaluate(()=>mock.calls.find(c=>c.method==='POST'&&c.url==='/api/v3/shipments'));
      assert.deepEqual({batch_id:saved.body.batch_id,direction:saved.body.direction},{batch_id:'batch-ready',direction:'FBO'});
      assert.equal(typeof saved.body.request_id,'string');assert.ok(saved.body.request_id.length>0);
      assert.deepEqual(errors,[]);await page.close();
    });
    await t.test('Stage 3 timer, presence, activity and system information',async()=>{
      const {page,errors}=await fixture(browser,'admin',{width:390,height:844},true);
      await page.evaluate(()=>mock.stage3Permissions=['work.write','tasks.read','tasks.manage','batches.receive','finance.read','invoices.read','invoices.create','users.manage','clients.read','clients.manage','access.history.read','payroll.own','payroll.settlement.read']);
      await login(page);
      assert.match(await page.locator('#content').innerText(),/PORTAL Сегодня/);
      assert.match(await page.locator('#content').innerText(),/Финансовый радар/);
      assert.match(await page.locator('#content').innerText(),/Дебиторка/);
      assert.match(await page.locator('#content').innerText(),/Выручка сегодня/);
      assert.match(await page.locator('#content').innerText(),/Выручка за месяц/);
      assert.match(await page.locator('#content').innerText(),/Открытые счета: 2/);
      assert.match(await page.locator('#content').innerText(),/Плановая прибыль\s+Недоступна/);
      assert.match(await page.locator('#content').innerText(),/Закрытый ФОТ\s+Нет закрытого периода/);
      assert.match(await page.locator('#content').innerText(),/Скорость команды\s+5 шт\./);
      await page.evaluate(async()=>{mock.stage3Today={date:'2026-09-25',mode:'management',today_quantity:17,month_quantity:27,tasks:[],finance:{revenue:2500,salary:1200,materials:0,other:0,company_overhead:0,profit:900},closed_month_payroll:{accrued:10000,paid:4000,balance:6000}};await go('dashboard');});
      await page.waitForFunction(()=>document.querySelector('#content').textContent.includes('Начислено 100')&&!document.querySelector('.loading'));
      assert.match(await page.locator('#content').innerText(),/Закрытый ФОТ\s+Начислено 100 ₽ · Выплачено 40 ₽ · Остаток 60 ₽/);
      await page.evaluate(async()=>{S.me.permissions=S.me.permissions.filter(p=>p!=='payroll.settlement.read'&&p!=='payroll.all');await go('dashboard');});
      await page.waitForFunction(()=>!document.querySelector('#content').textContent.includes('Закрытый ФОТ')&&!document.querySelector('.loading'));
      assert.doesNotMatch(await page.locator('#content').innerText(),/Закрытый ФОТ|Начислено 100|Выплачено 40|Остаток 60/);
      await page.evaluate(async()=>{mock.stage3Today={date:'2026-09-26',mode:'management',today_quantity:17,ready:1,active_batches:2,in_progress:0,tasks:[],attention:[]};await go('dashboard');});
      await page.waitForFunction(()=>document.querySelector('#content').textContent.includes('26.09.2026')&&!document.querySelector('.loading'));
      assert.doesNotMatch(await page.locator('#content').innerText(),/Плановая прибыль|Выручка|Начислено|Закрытый ФОТ/);
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
      await page.evaluate(()=>closeSheet());
      await page.locator('[data-action=companyAudit]').click();await page.waitForSelector('#auditEntity');
      await page.locator('#auditActor').fill('7');await page.locator('#auditAction').fill('access_invite.created');await page.locator('#auditEntity').fill('invite-42');await page.locator('#auditFrom').fill('2026-09-01');await page.locator('#auditTo').fill('2026-09-30');
      await page.locator('#auditFilterForm [type=submit]').click();
      await page.waitForFunction(()=>mock.calls.some(c=>c.url.startsWith('/api/v3/audit?')&&c.url.includes('entity_id=invite-42')));
      const auditCall=await page.evaluate(()=>mock.calls.filter(c=>c.url.startsWith('/api/v3/audit?')).at(-1).url);
      assert.match(auditCall,/actor_id=7/);assert.match(auditCall,/action=access_invite\.created/);assert.match(auditCall,/entity_id=invite-42/);assert.match(auditCall,/from=2026-09-01/);assert.match(auditCall,/to=2026-09-30/);
      await page.evaluate(()=>{closeSheet();go('clients');});
      await page.waitForSelector('#content [data-action=openClient]');
      await page.locator('[data-action=openClient]').click();await page.waitForSelector('#sheetContent');
      assert.match(await page.locator('#sheetContent').innerText(),/Реквизиты и контакты/);
      assert.match(await page.locator('#sheetContent').innerText(),/Сводка экономики недоступна/);
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

test('self-service PIN change settings flow is masked, validates mismatch and hides for God',async t=>{
  if(!chromium){t.skip('Playwright is not installed in this environment');return;}
  const browser=await chromium.launch({headless:true,...(process.env.PORTAL_BROWSER_PATH?{executablePath:process.env.PORTAL_BROWSER_PATH}:{})});
  try{
    const {page,errors}=await fixture(browser,'packer');await login(page);await page.evaluate(()=>go('settings'));
    await page.waitForFunction(()=>document.querySelector('#content [data-action=changePin]'));
    await page.locator('[data-action=changePin]').click();await page.waitForSelector('#changePinForm');
    for(const id of ['currentPin','newPin','confirmPin'])assert.equal(await page.locator('#'+id).getAttribute('type'),'password');
    await page.locator('#currentPin').fill('fixture-current');await page.locator('#newPin').fill('fixture-new');await page.locator('#confirmPin').fill('mismatch');await page.locator('#changePinForm [type=submit]').click();
    await page.waitForFunction(()=>document.querySelector('#toast')?.textContent.includes('PIN'));
    assert.equal(await page.evaluate(()=>mock.calls.some(c=>c.url==='/api/me/pin')),false);
    await page.locator('#confirmPin').fill('fixture-new');await page.locator('#changePinForm [type=submit]').click();
    await page.waitForFunction(()=>mock.calls.some(c=>c.url==='/api/me/pin'));
    assert.deepEqual(await page.evaluate(()=>mock.calls.find(c=>c.url==='/api/me/pin').body),{current_pin:'fixture-current',new_pin:'fixture-new'});
    await page.evaluate(()=>{S.me.role='platform_owner';screens.settings();});
    assert.equal(await page.locator('[data-action=changePin]').count(),0);assert.deepEqual(errors,[]);await page.close();
  }finally{await browser.close();}
});
