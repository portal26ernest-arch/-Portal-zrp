const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..', '..');
const ASSETS = path.join(ROOT, 'android_src', 'app', 'src', 'main', 'assets');
const OUT = path.join(ROOT, 'ios_src', 'app_store', 'screenshots', 'ru-RU', '6.9');
fs.mkdirSync(OUT, { recursive: true });

const mime = file => file.endsWith('.html') ? 'text/html; charset=utf-8'
  : file.endsWith('.css') ? 'text/css; charset=utf-8'
  : file.endsWith('.js') ? 'text/javascript; charset=utf-8'
  : file.endsWith('.svg') ? 'image/svg+xml'
  : file.endsWith('.json') ? 'application/json; charset=utf-8'
  : 'application/octet-stream';

const server = http.createServer((req, res) => {
  const target = req.url === '/' ? 'index.html' : decodeURIComponent(req.url.split('?')[0]).replace(/^\//, '');
  const file = path.resolve(ASSETS, target);
  if (!file.startsWith(ASSETS + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    res.writeHead(404); res.end(); return;
  }
  res.writeHead(200, {'Content-Type': mime(file), 'Cache-Control': 'no-store'});
  fs.createReadStream(file).pipe(res);
});

const permissions = [
  'work.write','tasks.read','tasks.manage','batches.receive','finance.read',
  'invoices.read','invoices.create','users.manage','access.history.read',
  'payroll.own','payroll.all','payroll.close','chat.read','clients.read',
  'clients.manage','rates.employee','rates.client','materials.read','materials.use',
  'payments.record','expenses.read','expenses.manage','analytics.read',
  'documents.read','documents.manage','imports.manage','company.settings'
];

function responseFor(url) {
  const u = new URL(url);
  const p = u.pathname;
  if (p === '/api/ping') return {ok:true,setup_required:false};
  if (p === '/api/v3/today') return {ok:true,data:{
    date:'2026-10-03',mode:'management',today_quantity:428,month_quantity:7420,
    active_jobs:7,in_progress:5,ready:2,active_batches:9,
    finance:{salary:184200,revenue:512000,profit:214600},
    today_finance:{revenue:512000,salary:184200},
    month_finance:{revenue:8940000,salary:3210000},
    today_productivity:{units:428,timed_units:390,units_per_hour:58},
    debt:126000,open_invoice_count:3,overdue_invoice_count:1,overdue_debt:42000,
    client_profitability_alerts:0,attention:[],tasks:[]
  }};
  if (p === '/api/v3/catalog') return {ok:true,data:{
    clients:[{id:1,name:'Север',active:true},{id:2,name:'Маяк',active:true},{id:3,name:'Вектор',active:true}],
    operations:[{id:1,client_id:1,name:'Упаковка',employee_rate:600,client_rate:1400},{id:2,client_id:2,name:'Маркировка',employee_rate:300,client_rate:700}],
    products:[],users:[]
  }};

  if (p === '/api/v3/clients') return {ok:true,data:[
    {id:1,name:'Север',active:true},{id:2,name:'Маяк',active:true},{id:3,name:'Вектор',active:true}
  ]};
  if (p.startsWith('/api/v3/documents')) return {ok:true,data:{items:[
    {id:'d1',title:'Расчётный лист',document_type:'payroll_pdf',category:'payroll',document_date:'2026-10-01',created_at:'2026-10-01T09:00:00Z',size_bytes:184320,status:'ready',revision:1},
    {id:'d2',title:'Счёт на оплату',document_type:'invoice_xlsx',category:'invoice',document_date:'2026-10-02',created_at:'2026-10-02T12:00:00Z',size_bytes:92160,status:'ready',revision:2}
  ],total:2,page:1,limit:50}};
  if (p === '/api/v3/documents') return {ok:true,data:[]};
  if (p === '/api/v3/meta') return {ok:true,ready:true,heartbeat_seconds:60,permissions,catalog:[]};
  if (p === '/api/company') return {ok:true,company:{id:1,name:'PORTAL'}};
  if (p === '/api/me') return {ok:true,user:{id:1,username:'demo',display_name:'Анна Смирнова',role:'admin',company_id:1,employee_id:101,permissions}};
  return {ok:true,data:[]};
}

async function shot(page, name) {
  await page.screenshot({path:path.join(OUT, name + '.jpg'), type:'jpeg', quality:94, fullPage:false});
}

(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  const origin = `http://127.0.0.1:${address.port}`;
  const browser = await chromium.launch({headless:true});
  const context = await browser.newContext({
    viewport:{width:430,height:932},
    deviceScaleFactor:3,
    isMobile:true,
    hasTouch:true,
    colorScheme:'light',
    locale:'ru-RU'
  });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', route => {
    const body = JSON.stringify(responseFor(route.request().url()));
    route.fulfill({status:200,contentType:'application/json; charset=utf-8',body});
  });

  await page.goto(origin + '/index.html');
  await page.waitForFunction(() => document.querySelector('#serverState')?.textContent === 'Подключение готово');
  await shot(page, '01-login');

  await page.evaluate(perms => {
    S.token='screenshot-token';
    S.me={id:1,username:'demo',display_name:'Анна Смирнова',role:'admin',company_id:1,employee_id:101,permissions:perms};
    S.company={id:1,name:'PORTAL'};
    S.stage3=true;
    S.permissionCatalog=[];
    document.querySelector('#auth').classList.add('hidden');
    document.querySelector('#app').classList.remove('hidden');
    updateHeader();
  }, permissions);

  await page.evaluate(() => go('dashboard',{fromHistory:true}));
  await page.waitForFunction(() => !document.querySelector('#content .loading'));
  await shot(page, '02-dashboard');

  await page.evaluate(() => go('sections'));
  await page.waitForFunction(() => !document.querySelector('#content .loading'));
  await shot(page, '03-sections');

  await page.evaluate(() => go('documents'));
  await page.waitForFunction(() => !document.querySelector('#content .loading'));
  await shot(page, '04-documents');

  if (errors.length) throw new Error('Browser errors: ' + errors.join(' | '));
  await browser.close();
  server.close();
  console.log('APP STORE SCREENSHOTS OK:', OUT);
})().catch(error => {
  console.error(error);
  server.close();
  process.exitCode=1;
});
