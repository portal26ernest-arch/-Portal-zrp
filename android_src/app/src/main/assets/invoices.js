'use strict';

(() => {
  const XLSX='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
  const PDF='application/pdf';
  const legacyNewInvoice=actions.newInvoice;
  const legacyInvoices=screens.invoices;
  const invoiceStatus={paid:'Оплачен',partial:'Частично оплачен',unpaid:'Не оплачен'};
  const stateLabel={editing:'На редактировании',finalized:'Зафиксирован'};

  const clientName=(catalog,id)=>catalog.clients.find(row=>row.id===id)?.name||('Клиент #'+id);
  const invoiceNumber=invoice=>invoice.number||('Счёт от '+date(invoice.created_at));
  const lineTotal=line=>Number(line.quantity||0)*Number(line.client_rate||0);

  async function saveInvoicePayload(file,share=false){
    const bridge=share?'shareBase64FileAsync':'saveBase64FileAsync';
    if(typeof window.PortalNative?.[bridge]!=='function')throw new Error('Сохранение файла недоступно');
    const result=await nativePromise(id=>share
      ? PortalNative.shareBase64FileAsync(id,file.filename,file.mime_type,file.file_b64,'','Счёт на оплату','')
      : PortalNative.saveBase64FileAsync(id,file.filename,file.mime_type,file.file_b64));
    if(!result.ok)throw new Error(result.error||'Не удалось подготовить файл');
    if(!share)toast('Файл сохранён · '+result.location);
  }

  async function buildInvoiceDocument(invoiceId,type,share=false){
    const doc=await productionPost('document-generate',{document_type:type,invoice_id:invoiceId});
    const file=await productionGet('document-file?id='+encodeURIComponent(doc.id));
    await saveInvoicePayload(file,share);
  }
  function invoiceCard(invoice,catalog){
    const client=clientName(catalog,invoice.client_id);
    const status=invoiceStatus[invoice.status]||invoice.status||'Не определён';
    const state=stateLabel[invoice.state]||'Зафиксирован';
    return `<article class="item invoice-card">
      <div class="row between invoice-card-head">
        <div><span class="eyebrow">${esc(client)}</span><h3>${esc(invoiceNumber(invoice))}</h3></div>
        <span class="badge ${invoice.status==='paid'?'green':invoice.status==='partial'?'amber':''}">${esc(status)}</span>
      </div>
      <div class="invoice-card-money"><strong>${rub(invoice.amount)}</strong><span>Остаток ${rub(invoice.remaining)}</span></div>
      <p class="meta">${esc(state)} · версия ${num(invoice.revision||1)} · ${date(invoice.created_at)}${invoice.due_at?' · оплатить до '+date(invoice.due_at):''}</p>
      <div class="item-actions">
        ${invoice.remaining&&allowed('payments.record')?btn('Внести оплату','recordPayment',`data-id="${esc(invoice.id)}"`,'secondary'):''}
        ${allowed('invoices.export')?btn('PDF','invoiceDownloadPdf',`data-id="${esc(invoice.id)}"`,'secondary')+btn('Отправить PDF','invoiceSharePdf',`data-id="${esc(invoice.id)}"`,'secondary')+btn('Excel','invoiceDownloadXlsx',`data-id="${esc(invoice.id)}"`,'text'):''}
        ${['admin','director'].includes(S.me.role)&&invoice.state!=='editing'?btn('Отправить на редактирование','sendInvoiceEditing',`data-id="${esc(invoice.id)}"`,'text'):''}
        ${S.me.role==='manager'&&invoice.state==='editing'?btn('Редактировать','editInvoice',`data-id="${esc(invoice.id)}"`,'secondary'):''}
      </div>
    </article>`;
  }

  screens.invoices=async()=>{
    if(!S.stage3)return legacyInvoices();
    const [rows,catalog]=await Promise.all([productionGet('invoices'),productionCatalog()]);
    S.productionInvoices=rows;S.invoiceCatalog=catalog;
    const outstanding=rows.reduce((sum,row)=>sum+Number(row.remaining||0),0);
    const unpaid=rows.filter(row=>row.remaining>0).length;
    const paid=rows.filter(row=>row.status==='paid').length;
    const toolbar=allowed('invoices.create')||allowed('invoices.read')?
      `<div class="invoice-toolbar">
        ${allowed('invoices.create')?btn('Новый счёт','invoiceNew','','block'):''}
        ${allowed('invoices.create')?btn('Из выработки','invoiceFromWork','','secondary'):''}
        ${allowed('invoices.read')?btn('Дебиторка','viewReceivables','','secondary'):''}
      </div>`:'';
    paint(heading('Счета на оплату','Создание, PDF, Excel и контроль оплаты')+
      `<div class="metrics">${metric('К получению',rub(outstanding))}${metric('Не оплачено',num(unpaid))}${metric('Оплачено',num(paid))}</div>`+
      toolbar+
      `<div class="section-label"><h2>Счета · ${num(rows.length)}</h2></div>
       <div class="list">${rows.slice().reverse().map(row=>invoiceCard(row,catalog)).join('')||'<p class="empty">Счетов пока нет. Создайте первый счёт на оплату.</p>'}</div>`);
  };

  function operationsForClient(clientId){
    return (S.invoiceCatalog?.operations||[]).filter(op=>op.client_id===Number(clientId));
  }

  function defaultRate(operation){
    return operation?.client_rate==null?'':(Number(operation.client_rate)/100).toFixed(2);
  }

  function newDraftLine(operationId){
    const operations=operationsForClient(S.invoiceDraft.client_id);
    const operation=operations.find(op=>op.id===Number(operationId))||operations[0];
    return {key:crypto.randomUUID(),operation_id:operation?.id||'',quantity:1,rate:defaultRate(operation)};
  }

  function draftTotal(){
    return (S.invoiceDraft?.lines||[]).reduce((sum,line)=>sum+
      Math.round((Number(line.quantity)||0)*(Number(line.rate)||0)*100),0);
  }

  function renderDraftLines(){
    const container=$('invoiceDraftLines');if(!container)return;
    const operations=operationsForClient(S.invoiceDraft.client_id);
    container.innerHTML=S.invoiceDraft.lines.map((line,index)=>{
      const operationOptions=operations.map(op=>`<option value="${op.id}" ${Number(line.operation_id)===op.id?'selected':''}>${esc(op.name)}</option>`).join('');
      return `<div class="invoice-line" data-invoice-line="${esc(line.key)}">
        <span class="invoice-line-number">${index+1}</span>
        <label><span>Услуга</span><select data-invoice-operation>${operationOptions}</select></label>
        <label><span>Кол-во</span><input data-invoice-quantity type="number" min="1" step="1" value="${esc(line.quantity)}"></label>
        <label><span>Цена, ₽</span><input data-invoice-rate type="number" min="0" step="0.01" value="${esc(line.rate)}"></label>
        <strong data-invoice-line-total>${rub(Math.round(Number(line.quantity||0)*Number(line.rate||0)*100))}</strong>
        <button type="button" class="btn text invoice-remove" data-action="invoiceRemoveLine" data-key="${esc(line.key)}">Удалить</button>
      </div>`;
    }).join('')||'<p class="empty">Добавьте хотя бы одну строку счёта.</p>';
    const total=$('invoiceDraftTotal');if(total)total.textContent=rub(draftTotal());
    for(const row of container.querySelectorAll('[data-invoice-line]')){
      const key=row.dataset.invoiceLine;
      const line=S.invoiceDraft.lines.find(item=>item.key===key);
      const op=row.querySelector('[data-invoice-operation]');
      const qty=row.querySelector('[data-invoice-quantity]');
      const rate=row.querySelector('[data-invoice-rate]');
      op?.addEventListener('change',()=>{line.operation_id=Number(op.value);line.rate=defaultRate(operations.find(item=>item.id===line.operation_id));renderDraftLines();});
      const recalc=()=>{line.quantity=qty.value;line.rate=rate.value;row.querySelector('[data-invoice-line-total]').textContent=rub(Math.round((Number(qty.value)||0)*(Number(rate.value)||0)*100));$('invoiceDraftTotal').textContent=rub(draftTotal());};
      qty?.addEventListener('input',recalc);rate?.addEventListener('input',recalc);
    }
  }

  async function refreshInvoiceRequisites(){
    const box=$('invoiceRequisitesNotice');if(!box)return;
    try{
      const req=await productionGet('client-requisites?client_id='+encodeURIComponent(S.invoiceDraft.client_id));
      const missing=[];if(!req?.legal_name)missing.push('название');if(!req?.inn)missing.push('ИНН');
      box.className=missing.length?'notice warning':'notice';
      box.textContent=missing.length?'Для PDF не заполнены реквизиты клиента: '+missing.join(', ')+'. Их может дополнить директор или администратор.':'Реквизиты клиента готовы для печати счёта.';
    }catch{box.className='notice warning';box.textContent='Не удалось проверить реквизиты клиента.';}
  }

  function renderInvoiceDraft(){
    const catalog=S.invoiceCatalog||{clients:[]};
    const clientOptions=catalog.clients.map(client=>`<option value="${client.id}" ${client.id===S.invoiceDraft.client_id?'selected':''}>${esc(client.name)}</option>`).join('');
    openSheet('Новый счёт на оплату',`<form id="invoiceManualForm" class="invoice-editor">
      <div class="invoice-editor-top">
        <label class="field"><span>Клиент</span><select id="invoiceClient" required>${clientOptions}</select></label>
        ${field('invoiceDue','Оплатить до','','date')}
      </div>
      <div class="invoice-editor-tools">
        ${btn('Добавить строку','invoiceAddLine','','secondary')}
        ${btn('Скачать Excel-шаблон','invoiceTemplate','','text')}
        <label class="btn text invoice-file-button">Загрузить Excel<input id="invoiceExcelFile" type="file" accept=".xlsx,${XLSX}" hidden></label>
      </div>
      <p class="meta">Цена подставляется из тарифа клиента. Изменение цены здесь действует только для этого счёта.</p>
      <div id="invoiceRequisitesNotice" class="notice">Проверяем реквизиты клиента…</div>
      <div class="invoice-lines-head"><span>№</span><span>Услуга</span><span>Количество</span><span>Цена</span><span>Сумма</span><span></span></div>
      <div id="invoiceDraftLines" class="invoice-lines"></div>
      <div class="invoice-total"><span>Итого</span><strong id="invoiceDraftTotal">0 ₽</strong></div>
      <button class="btn block" type="submit">Зафиксировать счёт</button>
      <p class="meta">После сохранения счёт блокируется. Директор или администратор может отправить его менеджеру на редактирование.</p>
    </form>`);
    $('invoiceClient').addEventListener('change',()=>{
      S.invoiceDraft.client_id=Number($('invoiceClient').value);
      const operations=operationsForClient(S.invoiceDraft.client_id);
      S.invoiceDraft.lines=operations.length?[newDraftLine(operations[0].id)]:[];
      renderDraftLines();void refreshInvoiceRequisites();
    });
    $('invoiceExcelFile').addEventListener('change',event=>void importInvoiceExcel(event.target.files?.[0]));
    renderDraftLines();void refreshInvoiceRequisites();
  }

  actions.invoiceNew=async()=>{
    const catalog=await productionCatalog();
    if(!catalog.clients.length)throw new Error('Нет доступных активных клиентов');
    S.invoiceDraft={client_id:catalog.clients[0].id,lines:[]};
    const operations=operationsForClient(S.invoiceDraft.client_id);
    if(operations.length)S.invoiceDraft.lines=[newDraftLine(operations[0].id)];
    renderInvoiceDraft();
  };
  actions.invoiceFromWork=()=>legacyNewInvoice();
  actions.invoiceAddLine=()=>{
    const operations=operationsForClient(S.invoiceDraft.client_id);
    if(!operations.length)return toast('У клиента нет активных операций',true);
    const used=new Set(S.invoiceDraft.lines.map(line=>Number(line.operation_id)));
    const operation=operations.find(op=>!used.has(op.id));
    if(!operation)return toast('Все операции клиента уже добавлены в счёт',true);
    S.invoiceDraft.lines.push(newDraftLine(operation.id));renderDraftLines();
  };
  actions.invoiceRemoveLine=button=>{
    S.invoiceDraft.lines=S.invoiceDraft.lines.filter(line=>line.key!==button.dataset.key);renderDraftLines();
  };

  async function fileBase64(file){
    if(!file)throw new Error('Выберите XLSX-файл');
    if(!file.name.toLowerCase().endsWith('.xlsx'))throw new Error('Нужен файл .xlsx');
    if(file.size>5*1024*1024)throw new Error('Файл больше 5 МБ');
    return new Promise((resolve,reject)=>{
      const reader=new FileReader();
      reader.onerror=()=>reject(new Error('Не удалось прочитать файл'));
      reader.onload=()=>{const value=String(reader.result||'');resolve(value.slice(value.indexOf(',')+1));};
      reader.readAsDataURL(file);
    });
  }

  async function importInvoiceExcel(file){
    try{
      const file_b64=await fileBase64(file);
      const result=await productionPost('invoice-import-preview',{client_id:S.invoiceDraft.client_id,file_b64});
      S.invoiceDraft.lines=result.lines.map(line=>({key:crypto.randomUUID(),operation_id:line.operation_id,quantity:line.quantity,rate:(line.client_rate/100).toFixed(2)}));
      renderDraftLines();toast('Excel загружен · проверьте строки и итог');
    }catch(error){handleError(error);}
    finally{if($('invoiceExcelFile'))$('invoiceExcelFile').value='';}
  }

  actions.invoiceTemplate=async()=>{
    const file=await productionGet('invoice-template?client_id='+encodeURIComponent(S.invoiceDraft.client_id));
    await saveInvoicePayload(file,false);
  };

  forms.invoiceManualForm=async form=>{
    const lines=Array.from(form.querySelectorAll('[data-invoice-line]'),row=>({
      operation_id:Number(row.querySelector('[data-invoice-operation]').value),
      quantity:Number(row.querySelector('[data-invoice-quantity]').value),
      client_rate:Math.round(Number(row.querySelector('[data-invoice-rate]').value)*100)
    }));
    if(!lines.length)throw new Error('Добавьте хотя бы одну строку счёта');
    const invoice=await productionPost('invoices',{
      mode:'manual',
      client_id:Number($('invoiceClient').value),
      lines,
      due_at:$('invoiceDue').value?utc($('invoiceDue').value):null
    },form);
    closeSheet();toast('Счёт '+invoiceNumber(invoice)+' зафиксирован');await go('invoices');
  };

  actions.invoiceDownloadPdf=button=>buildInvoiceDocument(button.dataset.id,'invoice_pdf',false);
  actions.invoiceSharePdf=button=>buildInvoiceDocument(button.dataset.id,'invoice_pdf',true);
  actions.invoiceDownloadXlsx=button=>buildInvoiceDocument(button.dataset.id,'invoice_xlsx',false);
})();
