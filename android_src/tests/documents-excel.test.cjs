'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const assets=path.join(__dirname,'../app/src/main/assets');
const source=fs.readFileSync(path.join(assets,'documents_excel.js'),'utf8');
const html=fs.readFileSync(path.join(assets,'index.html'),'utf8');
const app=fs.readFileSync(path.join(assets,'app.js'),'utf8');
const core=fs.readFileSync(path.join(assets,'core.js'),'utf8');
const shell=fs.readFileSync(path.join(__dirname,'../app/src/main/java/ru/portal/app/MainActivity.java'),'utf8');

test('Documents list has scoped API filters, paging, ready-only download and archive states',()=>{
  for(const value of ['documents?','page: String(state.page)','limit: String(state.limit)','q','document_type','category','date_from','date_to','status','Показать ещё','document-file?id=','document-archive','Документы не найдены','Повторить'])assert.ok(source.includes(value),value);
  assert.match(source,/allowed\('documents\.manage'\)/);
  assert.match(source,/d\.status === 'archived'/);
  assert.match(source,/!archived && d\.status === 'ready'/);
  assert.doesNotMatch(source,/storage_key|fingerprint|request_id/);
});

test('Excel API contract validates files, shows classifications and requires explicit apply',()=>{
  for(const value of ['document-template-info','document-template-blank','document-template','excel-import-preview','excel-import-apply','excel-import-result','file_b64','preview_token','import_id','10 * 1024 * 1024','Компания','Сотрудники','Клиенты','Операции_Тарифы'])assert.ok(source.includes(value),value);
  assert.match(source,/preview\.can_apply && state\.file/);
  assert.match(source,/classification/);
  assert.match(source,/confirmSheet\(/);
  assert.match(source,/state\.busy\) return/);
  assert.match(source,/terminal\?\.status === 'failed'/);
  assert.match(source,/terminal\?\.status === 'applied'/);
  assert.match(source,/Preview устарел или справочники изменились/);
  assert.match(source,/result_document_id/);
  assert.match(source,/validateExcelFile/);
});

test('Downloads use the system picker, private MediaStore save and a strict MIME allowlist',()=>{
  assert.match(source,/new FileReader\(\)/);
  assert.match(source,/saveBase64FileAsync/);
  assert.match(source,/\[XLSX, PDF, JSON_MIME\]/);
  assert.ok(html.indexOf('preview.js')<html.indexOf('documents_excel.js'));
  assert.match(shell,/onShowFileChooser/);
  assert.match(shell,/MediaStore\.Downloads/);
  assert.match(shell,/"application\/json"\.equals\(mimeType\)/);
});

test('Share actions are wired for ready documents, templates and safe import results',()=>{
  assert.match(source,/sharePortalDocument/);
  assert.match(source,/shareExcelTemplate/);
  assert.match(source,/shareImportResult/);
  assert.match(source,/!archived && d\.status === 'ready'.*Поделиться/s);
  assert.match(source,/window\.prompt\('Email получателя \(необязательно\)'/);
  assert.match(shell,/FileProvider\.getUriForFile/);
});

test('Capabilities, owner company context, role visibility and expired-session behavior stay enforced',()=>{
  for(const permission of ['imports.manage','users.manage','clients.manage','rates.employee','rates.client','company.settings','documents.manage','documents.read'])assert.ok(source.includes(permission),permission);
  assert.match(source,/function requireCompany\(\)[\s\S]*isOwner\(\) && !S\.company/);
  assert.match(source,/\['admin', 'director'\]\.includes\(S\.me\?\.role\)/);
  assert.match(core,/id:'excelImport'.*production:true/);
  assert.match(app,/result\.httpStatus===401[\s\S]*logout\(false,true\)/);
  assert.match(app,/isOwner\(\)&&!options\.sessionControl[\s\S]*выберите компанию/);
});

test('PDF generation and ready document sharing are live capability gated actions',()=>{
  const production=fs.readFileSync(path.join(assets,'production.js'),'utf8');
  assert.match(production,/document-generate/);
  assert.match(production,/document_type:'invoice_pdf'/);
  assert.match(production,/document_type:'payroll_slip_pdf'/);
  assert.match(production,/allowed\('invoices\.read'\)/);
  assert.match(production,/allowed\('payroll\.settlement\.read'\)/);
  assert.match(source,/sharePortalDocument/);
  assert.match(source,/shareBase64FileAsync/);
  assert.match(source,/row\.status !== 'ready'/);
});

test('Invoice revisions and XLSX documents are capability gated and tied to the existing workflow',()=>{
  const production=fs.readFileSync(path.join(assets,'production.js'),'utf8');
  for(const label of ['XLSX счёта','Отправить на редактирование','Редактировать счёт','Зафиксирован','На редактировании'])assert.ok(production.includes(label),label);
  assert.match(production,/workflow:'send_to_editing'/);
  assert.match(production,/workflow:'save_revision'/);
  assert.match(production,/document_type:'invoice_xlsx'/);
  assert.match(production,/document_type:'payroll_slip_xlsx'/);
  assert.match(production,/S\.me\.role==='manager'&&i\.state==='editing'/);
  assert.match(production,/data-revision-quantity/);
  assert.match(production,/data-revision-rate/);
  assert.match(production,/client_rate:Math\.round\(Number\(row\.querySelector\('[^']+'\)\.value\)\*100\)/);
  assert.match(production,/\['admin','director'\]\.includes\(S\.me\.role\).*Отправить на редактирование/);
});

test('Payroll settlement UI reads append-only balances and gates payment/reversal actions',()=>{
  const production=fs.readFileSync(path.join(assets,'production.js'),'utf8');
  assert.match(production,/payroll-settlements\?payroll_period_id=/);
  assert.match(production,/Выплачено/);
  assert.match(production,/Остаток/);
  assert.match(production,/allowed\('payroll\.settlement\.read'\).*payrollSettlement/s);
  assert.match(production,/allowed\('payroll\.settlement\.payout'\).*payrollAddPayment/s);
  assert.match(production,/entry_type:'payout'/);
  assert.match(production,/entry_type:'reversal'/);
  assert.match(production,/Исходная запись сохранится в истории/);
  assert.match(production,/productionPost\('payroll-settlements'/);
});
