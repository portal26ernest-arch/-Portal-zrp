'use strict';
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');

const repo=path.join(__dirname,'../..');
const invoice=fs.readFileSync(path.join(repo,'android_src/app/src/main/assets/invoices.js'),'utf8');
const preview=fs.readFileSync(path.join(repo,'android_src/app/src/main/assets/preview.js'),'utf8');
const index=fs.readFileSync(path.join(repo,'android_src/app/src/main/assets/index.html'),'utf8');
const permissions=fs.readFileSync(path.join(repo,'server/production_permissions.py'),'utf8');

test('invoice workspace is live, compact and manager-oriented',()=>{
  for(const value of ['Новый счёт','Из выработки','Скачать Excel-шаблон','Загрузить Excel','Зафиксировать счёт','Отправить PDF','Дебиторка'])assert.ok(invoice.includes(value),value);
  assert.match(invoice,/screens\.invoices=async/);
  assert.match(invoice,/mode:'manual'/);
  assert.match(invoice,/operation_id:Number/);
  assert.match(invoice,/client_rate:Math\.round/);
  assert.match(invoice,/invoice-import-preview/);
  assert.match(invoice,/invoice-template\?client_id=/);
  assert.doesNotMatch(preview,/actions\.previewInvoice/);
  assert.doesNotMatch(preview,/Открыть макет счёта/);
});

test('manager can export invoice documents without full document-management rights',()=>{
  assert.match(permissions,/\('invoices\.export'.*'manager director admin'\)/);
  assert.match(invoice,/allowed\('invoices\.export'\)/);
  assert.match(invoice,/document_type:type/);
  assert.match(invoice,/shareBase64FileAsync/);
});

test('invoice module is loaded after preview so live workspace wins',()=>{
  assert.ok(index.indexOf('preview.js')<index.indexOf('invoices.js'));
  assert.ok(index.indexOf('invoices.js')<index.indexOf('documents_excel.js'));
});
