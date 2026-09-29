'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict'),http=require('node:http'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require('playwright');
const assets=path.resolve(__dirname,'../app/src/main/assets');
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.json':'application/json'};
let server,origin;
test.before(async()=>{server=http.createServer((req,res)=>{const name=req.url==='/web/'?'index.html':req.url.startsWith('/web/')?decodeURIComponent(req.url.slice(5)):'';const file=path.resolve(assets,name);if(!name||!file.startsWith(assets+path.sep)||!fs.existsSync(file)){res.writeHead(404).end();return;}res.writeHead(200,{'Content-Type':mime[path.extname(file)]||'application/octet-stream','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"});fs.createReadStream(file).pipe(res);});await new Promise(r=>server.listen(0,'127.0.0.1',r));origin=`http://127.0.0.1:${server.address().port}`;});
test.after(async()=>{server?.close();});
test('same shared Web UI supports role menus, owner company selection, and Documents/Excel screens',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  for(const role of ['director','packer','platform_owner']){
   const context=await browser.newContext(),page=await context.newPage(),errors=[];page.setDefaultTimeout(5000);page.on('pageerror',e=>errors.push(e.message));page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
   await page.route('**/api/**',async route=>{const url=new URL(route.request().url()),body=route.request().postDataJSON?.()||{};let data={ok:true};
    if(url.pathname==='/api/ping')data={ok:true,setup_required:false};
    else if(url.pathname==='/api/login'||url.pathname==='/api/platform/login')data={ok:true,token:'test-token',user:{id:1,username:'tester',display_name:'Tester',role,company_id:1,employee_id:role==='packer'?1:undefined}};
    else if(url.pathname==='/api/company')data={ok:true,company:{id:1,name:'Test company'}};
    else if(url.pathname==='/api/v3/meta')data={ok:true,ready:true,permissions:role==='packer'?['work.write','tasks.read']:['documents.read','documents.manage','users.manage','clients.manage','rates.employee','rates.client','company.settings','imports.manage','work.write','tasks.read'],catalog:[],heartbeat_seconds:600};
    else if(url.pathname==='/api/platform/companies')data={ok:true,companies:[{id:1,name:'Test company',status:'active'}]};
    else if(url.pathname.endsWith('/document-template-info'))data={ok:true,data:{template_version:'v1.0',sheets:[]}};
    else if(url.pathname.includes('/documents'))data={ok:true,data:{items:[],page:1,limit:50,total:0}};
    else if(url.pathname.endsWith('/today'))data={ok:true,data:{tasks:[],mode:'management',attention:[]}};
    else if(url.pathname.endsWith('/timers'))data={ok:true,data:[]};
    await route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(data)});
   });
   await page.goto(origin+'/web/');await page.locator('#loginUser').fill('tester');await page.locator('#loginPin').fill('1234');await page.locator('#loginSubmit').click();
   if(role==='platform_owner'){await page.getByText('Test company').waitFor();assert.equal(await page.locator('[data-action="selectCompany"]').count(),1);assert.equal(await page.locator('[data-action="serverSettings"]').isVisible(),false);}
   else {await page.locator('#nav').waitFor();await page.locator('[data-action="go"][data-page="sections"]').click();if(role==='director'){await page.locator('[data-page="documents"]').waitFor();await page.locator('[data-page="documents"]').click();await page.locator('[data-action="go"][data-page="sections"]').click();await page.locator('[data-page="excelImport"]').waitFor();await page.locator('[data-page="excelImport"]').click();try{await page.locator('input[type=file]').waitFor();}catch{throw new Error('Excel chooser missing; page='+await page.locator('#content').innerText()+'; errors='+errors.join('|'));}}else{assert.equal(await page.locator('[data-page="documents"]').count(),0);}}
   assert.equal(await page.locator('[data-action="installUpdate"]').count(),0);assert.deepEqual(errors,[]);await context.close();
  }
 } finally {await browser.close();}
});
