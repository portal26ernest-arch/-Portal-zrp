function currentPayrollBounds(){
  const d=new Date(),pad=n=>String(n).padStart(2,'0');
  if(d.getDate()>15){const y=d.getFullYear(),m=d.getMonth();return [`${y}-${pad(m+1)}-01`,`${y}-${pad(m+1)}-15`];}
  const prev=new Date(d.getFullYear(),d.getMonth(),0),y=prev.getFullYear(),m=prev.getMonth(),last=prev.getDate();
  return [`${y}-${pad(m+1)}-16`,`${y}-${pad(m+1)}-${pad(last)}`];
}
screens.payrollPeriods=async()=>{
  const rows=await productionGet('payroll-periods'),[start,end]=currentPayrollBounds();S.payrollPeriods=rows;
  paint(heading('Расчётные периоды','Предпросмотр → закрытие → неизменяемый снимок')+
    (allowed('payroll.close')?`<form id="payrollPreviewForm" class="card">${field('payrollStart','Начало',start,'date','required')}${field('payrollEnd','Конец',end,'date','required')}<button class="btn block" type="submit">Предпросмотр периода</button></form>`:'')+
    `<div class="list">${rows.slice().reverse().map(p=>`<article class="item"><b>${esc(p.period_start)} — ${esc(p.period_end)}</b><p class="meta">Закрыт ${esc(date(p.closed_at))}</p><p>Выработка ${num(p.snapshot.total_quantity)} шт. · Зарплата ${rub(p.snapshot.total_salary)}</p><span class="badge green">Закрыт</span>${allowed('payroll.settlement.read')?btn('Выплаты и остатки','payrollSettlement',`data-period="${esc(p.id)}"`,'secondary block'):''}${allowed('payroll.all')&&allowed('payroll.settlement.read')&&allowed('documents.manage')?`<div class="item-actions">${(p.snapshot.employees||[]).filter(e=>Number.isInteger(e.employee_id)&&e.employee_id>0).map(e=>btn('PDF · '+esc(e.display_name),'generatePayrollSlip',`data-period="${esc(p.id)}" data-employee="${esc(e.employee_id)}"`,'secondary')+btn('XLSX · '+esc(e.display_name),'generatePayrollSlipXlsx',`data-period="${esc(p.id)}" data-employee="${esc(e.employee_id)}"`,'secondary')).join('')}</div>`:''}</article>`).join('')||'<p class="empty">Закрытых периодов пока нет</p>'}</div>`);
};
actions.payrollSettlement=async button=>{
  const period=S.payrollPeriods.find(p=>p.id===button.dataset.period);if(!period)throw new Error('Расчётный период недоступен');
  const data=await productionGet('payroll-settlements?payroll_period_id='+encodeURIComponent(period.id));S.payrollSettlement=data;
  const employees=new Map(data.employees.map(e=>[e.employee_id,e]));
  const summary=data.employees.map(e=>`<article class="item"><b>${esc(e.display_name)}</b><p>Начислено ${rub(e.accrued)} · Выплачено ${rub(e.paid)} · Остаток <strong>${rub(e.balance)}</strong></p>${allowed('payroll.settlement.payout')&&e.balance>0?btn('Добавить выплату','payrollAddPayment',`data-employee="${e.employee_id}"`,'secondary'):''}</article>`).join('')||'<p class="empty">В закрытом снимке нет сотрудников с employee ID.</p>';
  const entries=data.entries.slice().reverse().map(e=>`<article class="item"><b>${esc(employees.get(e.employee_id)?.display_name||'Сотрудник')}</b><p>${e.effect==='payment'?'Выплата':'Корректировка'} · ${rub(Math.abs(e.amount))} · ${esc(date(e.occurred_at))}</p><p class="meta">${esc(e.reason)}${e.reference?' · '+esc(e.reference):''}${e.reversal_of?' · сторно':''}</p>${e.entry_type!=='reversal'&&allowed('payroll.settlement.correct')?btn('Сторнировать запись','payrollReverse',`data-entry="${esc(e.id)}"`,'text'):''}</article>`).join('')||'<p class="empty">Записей выплат пока нет.</p>';
  openSheet('Выплаты и остатки',`<p class="meta">${esc(data.period_start)} — ${esc(data.period_end)} · закрытый снимок не изменяется выплатами</p><div class="metrics">${metric('Начислено',rub(data.totals.accrued))}${metric('Выплачено',rub(data.totals.paid))}${metric('Остаток',rub(data.totals.balance))}</div><h3>Сотрудники</h3><div class="list">${summary}</div><h3>История записей</h3><div class="list">${entries}</div>`);
};
actions.payrollAddPayment=button=>{
  const employee=S.payrollSettlement?.employees.find(e=>e.employee_id===Number(button.dataset.employee));if(!employee||employee.balance<=0)throw new Error('Остаток для выплаты недоступен');
  S.payrollPaymentEmployee=employee;
  openSheet('Добавить выплату',`<p>${esc(employee.display_name)} · доступный остаток ${rub(employee.balance)}</p><form id="payrollPaymentForm">${field('payrollPaymentAmount','Сумма, ₽','','number','required min="0.01" max="'+(employee.balance/100).toFixed(2)+'" step="0.01"')}${field('payrollPaymentReason','Основание','Выплата зарплаты','text','required maxlength="1000"')}${field('payrollPaymentReference','Комментарий','','text','maxlength="1000"')}<p class="meta">Дата и автор фиксируются сервером. Выплата добавляется отдельной записью; удалить её нельзя.</p><button class="btn block" type="submit">Записать выплату</button></form>`);
};
forms.payrollPaymentForm=async form=>{
  const employee=S.payrollPaymentEmployee,period=S.payrollSettlement;if(!employee||!period)throw new Error('Данные выплаты устарели');
  await productionPost('payroll-settlements',{entry_type:'payout',payroll_period_id:period.period_id,employee_id:employee.employee_id,amount:$('payrollPaymentAmount').value,reason:$('payrollPaymentReason').value,reference:$('payrollPaymentReference').value},form);
  closeSheet();toast('Выплата записана');await actions.payrollSettlement({dataset:{period:period.period_id}});
};
actions.payrollReverse=async button=>{
  const entry=S.payrollSettlement?.entries.find(e=>e.id===button.dataset.entry);if(!entry||entry.entry_type==='reversal')throw new Error('Запись для сторно недоступна');
  if(!await confirmSheet('Сторно выплаты','Будет добавлено отдельное обратное событие. Исходная запись сохранится в истории.','Добавить сторно'))return;
  await productionPost('payroll-settlements',{entry_type:'reversal',reversal_of:entry.id,reason:'Сторно записи: '+entry.reason});
  toast('Сторно записано');await actions.payrollSettlement({dataset:{period:S.payrollSettlement.period_id}});
};
forms.payrollPreviewForm=async form=>{
  const start=$('payrollStart').value,end=$('payrollEnd').value,d=await productionGet(`payroll-periods?period_start=${encodeURIComponent(start)}&period_end=${encodeURIComponent(end)}`);S.payrollPreview=d;
  openSheet('Предпросмотр зарплаты',`<div class="metrics">${metric('Выработка',num(d.total_quantity)+' шт.')}${metric('Начислено',rub(d.total_salary))}${metric('Записей',num(d.work_rows))}</div><div class="list">${d.employees.map(x=>`<div class="item"><b>${esc(x.display_name)}</b><p>${num(x.quantity)} шт. · ${rub(x.salary)}</p></div>`).join('')||'<p class="empty">В периоде нет выработки</p>'}</div>${allowed('payroll.close')?btn('Закрыть период','closePayrollPeriod','','block'):''}`);
};
actions.closePayrollPeriod=async()=>{const d=S.payrollPreview;if(!d)return;await productionPost('payroll-periods',{period_start:d.period_start,period_end:d.period_end});closeSheet();toast('Расчётный период закрыт');await go('payrollPeriods');};
screens.documents=async()=>{
  const docs=await productionGet('documents');S.documents=docs;
  paint(heading('Документы','Закрытые расчётные периоды · готовые Excel',allowed('documents.manage')?btn('Создать расчётный документ','newPayrollDocument'):'')+
    `<div class="list">${docs.slice().reverse().map(d=>`<article class="item"><b>${esc(d.title)}</b><p class="meta">${esc(d.period_start)} — ${esc(d.period_end)} · ${esc(d.filename||d.document_type)}</p><p>Начислено ${rub(d.snapshot?.total_salary||0)} · ${num(d.snapshot?.total_quantity||0)} шт.</p><p class="meta">SHA-256 ${esc((d.sha256||'').slice(0,16))}… · ${num((d.size_bytes||0)/1024)} КБ</p><div class="item-actions"><span class="badge green">Файл Excel готов</span>${window.PortalNative?.saveBase64FileAsync?btn('Сохранить XLSX','saveDocument',`data-id="${esc(d.id)}"`,'secondary'):''}</div></article>`).join('')||'<p class="empty">Документы ещё не сформированы</p>'}</div>`);
};
actions.newPayrollDocument=async()=>{
  const periods=await productionGet('payroll-periods');if(!periods.length)return toast('Сначала закройте расчётный период',true);
  S.documentPeriods=periods;
  openSheet('Расчётный документ',`<form id="documentForm">${selectField('documentPeriod','Закрытый период',periods.slice().reverse().map(p=>`<option value="${esc(p.id)}">${esc(p.period_start)} — ${esc(p.period_end)} · ${rub(p.snapshot.total_salary)}</option>`).join(''))}${field('documentTitle','Название — необязательно','','text','maxlength="200"')}<p class="meta">PORTAL зафиксирует неизменяемый снимок. Общий XLSX строится из него; PDF расчётного листа создаётся отдельно для сотрудника из закрытого периода.</p><button class="btn block" type="submit">Создать снимок</button></form>`);
};
forms.documentForm=async form=>{const p=S.documentPeriods.find(x=>x.id===$('documentPeriod').value);if(!p)throw new Error('Выберите период');await productionPost('documents',{document_type:'payroll',period_start:p.period_start,period_end:p.period_end,title:$('documentTitle').value.trim()||undefined},form);closeSheet();toast('Документ зафиксирован');await go('documents');};
actions.saveDocument=async button=>{if(typeof window.PortalNative?.saveBase64FileAsync!=='function')throw new Error('Сохранение доступно в мобильном приложении');const file=await productionGet('document-file?id='+encodeURIComponent(button.dataset.id));const result=await nativePromise(id=>PortalNative.saveBase64FileAsync(id,file.filename,file.mime_type,file.file_b64));if(!result.ok)throw new Error(result.error||'Не удалось сохранить документ');toast('Сохранено · '+result.location);};
async function createAndSavePdf(body){
  const doc=await productionPost('document-generate',body);
  if(typeof window.PortalNative?.saveBase64FileAsync!=='function'){toast('PDF создан в разделе «Документы»');return;}
  const file=await productionGet('document-file?id='+encodeURIComponent(doc.id));
  const result=await nativePromise(id=>PortalNative.saveBase64FileAsync(id,file.filename,file.mime_type,file.file_b64));
  if(!result.ok)throw new Error(result.error||'PDF создан, но сохранить его не удалось');
  toast('PDF создан и сохранён · '+result.location);
};
actions.generateInvoicePdf=async button=>{
  if(!allowed('documents.manage')||!allowed('invoices.read'))throw new Error('Недостаточно прав для генерации счёта');
  await createAndSavePdf({document_type:'invoice_pdf',invoice_id:button.dataset.id});
};
actions.generateInvoiceXlsx=async button=>{
  if(!allowed('documents.manage')||!allowed('invoices.read'))throw new Error('Недостаточно прав для генерации счёта');
  await createAndSaveDocument({document_type:'invoice_xlsx',invoice_id:button.dataset.id},'XLSX');
};
actions.generatePayrollSlip=async button=>{
  if(!allowed('documents.manage')||!allowed('payroll.all')||!allowed('payroll.settlement.read'))throw new Error('Недостаточно прав для расчётного листа');
  await createAndSavePdf({document_type:'payroll_slip_pdf',payroll_period_id:button.dataset.period,employee_id:Number(button.dataset.employee)});
};
actions.generatePayrollSlipXlsx=async button=>{
  if(!allowed('documents.manage')||!allowed('payroll.all')||!allowed('payroll.settlement.read'))throw new Error('Недостаточно прав для расчётного листа');
  await createAndSaveDocument({document_type:'payroll_slip_xlsx',payroll_period_id:button.dataset.period,employee_id:Number(button.dataset.employee)},'XLSX');
};
async function createAndSaveDocument(body,label){
  const doc=await productionPost('document-generate',body);
  if(typeof window.PortalNative?.saveBase64FileAsync!=='function'){toast(`${label} создан в разделе «Документы»`);return;}
  const file=await productionGet('document-file?id='+encodeURIComponent(doc.id));
  const result=await nativePromise(id=>PortalNative.saveBase64FileAsync(id,file.filename,file.mime_type,file.file_b64));
  if(!result.ok)throw new Error(result.error||`${label} создан, но сохранить его не удалось`);
  toast(`${label} создан и сохранён · ${result.location}`);
};
function chatAttachment(file){
  if(!file)return Promise.resolve(null);
  const allowedTypes=new Set(['image/jpeg','image/png','image/webp','application/pdf','text/plain']);
  if(!allowedTypes.has(file.type))return Promise.reject(new Error('Поддерживаются JPG, PNG, WebP, PDF и TXT'));
  if(file.size<=0||file.size>2*1024*1024)return Promise.reject(new Error('Файл должен быть не больше 2 МБ'));
  return new Promise((resolve,reject)=>{
    const reader=new FileReader();
    reader.onerror=()=>reject(new Error('Не удалось прочитать файл'));
    reader.onload=()=>{
      const raw=String(reader.result||''),comma=raw.indexOf(',');
      if(comma<0)return reject(new Error('Не удалось прочитать файл'));
      resolve({name:file.name,mime_type:file.type,file_b64:raw.slice(comma+1)});
    };
    reader.readAsDataURL(file);
  });
}
function chatAttachmentHtml(m){
  const a=m.attachment;if(!a)return '';
  const save=window.PortalNative?.saveBase64FileAsync?btn('Сохранить файл','saveChatAttachment','data-id="'+esc(a.id)+'"','text'):'';
  return '<div class="notice"><b>'+esc(a.original_name)+'</b><span class="meta"> · '+num(a.size_bytes/1024)+' КБ</span>'+save+'</div>';
}
function chatSystemHtml(m){
  if(m.message_type==='sticker'){const s=(S.chatStickerCatalog||[]).find(x=>x.key===m.sticker_key);return s?`<div class="chat-sticker"><img width="54" height="54" src="stickers/${esc(s.asset)}" alt="${esc(s.label)}"><b>${esc(s.label)}</b></div>`:'<p class="meta">Системный стикер недоступен</p>';}
  if(m.message_type==='absence_notice')return `<div class="notice"><b>Сообщил(а) о невыходе · ${esc(m.sender_name)}</b><p>Дата невыхода: <strong>${esc(m.absence_date)}</strong></p>${m.comment?`<p>${esc(m.comment)}</p>`:''}</div>`;
  return m.text?'<p>'+esc(m.text)+'</p>':'';
}
async function refreshTeamChat(){
  const recipient=S.chatRecipient||'',rows=await productionGet('chat'+(recipient?'?recipient_user_id='+encodeURIComponent(recipient):''));S.chatRows=rows;
  if(!$('chatList'))return;
  $('chatList').innerHTML=rows.map(m=>`<article class="item"><div class="row between"><b>${esc(m.sender_name)}</b>${m.pinned?'<span class="badge green">Закреплено</span>':''}</div>${chatSystemHtml(m)}${chatAttachmentHtml(m)}<p class="meta">${esc(portalDate(m.created_at).toLocaleString('ru-RU'))}</p>${allowed('chat.moderate')?btn(m.pinned?'Открепить':'Закрепить','pinChat',`data-id="${esc(m.id)}" data-pinned="${m.pinned?'1':'0'}"`,'text'):''}</article>`).join('')||'<p class="empty">Сообщений пока нет</p>';
}
screens.teamChat=async()=>{
  S.chatUsers=await productionGet('chat-users');S.chatStickerCatalog=await productionGet('chat-sticker-catalog');S.chatRecipient='';
  const roomOptions='<option value="">Общий чат</option>'+S.chatUsers.map(u=>`<option value="${u.id}">Лично · ${esc(u.display_name)}</option>`).join('');
  paint(heading('Команда','Внутреннее общение внутри PORTAL')+selectField('chatRecipient','Комната',roomOptions)+'<div id="chatList" class="list"></div>'+
    (allowed('chat.write')?`<form id="chatForm" class="card">${field('chatText','Сообщение','','text','maxlength="4000" autocomplete="off"')}<label class="field"><span>Вложение — необязательно, до 2 МБ</span><input id="chatFile" type="file" accept="image/jpeg,image/png,image/webp,application/pdf,text/plain"></label><button class="btn secondary block" type="button" data-action="chooseChatSticker">Стикеры PORTAL</button><button class="btn secondary block" type="button" data-action="newAbsenceNotice">Сообщить о невыходе</button><button class="btn block" type="submit">Отправить</button><p class="meta">В каждой комнате хранятся последние 1000 обычных сообщений. Закреплённые сообщения не входят в лимит и сохраняются до открепления.</p></form>`:''));
  $('chatRecipient').addEventListener('change',async()=>{S.chatRecipient=$('chatRecipient').value;await refreshTeamChat();});await refreshTeamChat();
};
actions.chooseChatSticker=()=>{if(S.chatRecipient)throw new Error('Стикеры доступны в общем чате');openSheet('Стикеры PORTAL',`<div class="mini-actions">${(S.chatStickerCatalog||[]).map(s=>`<button class="item" type="button" data-action="sendChatSticker" data-key="${esc(s.key)}"><img width="48" height="48" src="stickers/${esc(s.asset)}" alt=""><b>${esc(s.label)}</b></button>`).join('')}</div>`);};
actions.sendChatSticker=async button=>{await productionPost('chat',{subtype:'sticker',sticker_key:button.dataset.key},null);closeSheet();await refreshTeamChat();};
actions.newAbsenceNotice=()=>{if(S.chatRecipient)throw new Error('Сообщить о невыходе можно только в общем чате');openSheet('Сообщить о невыходе',`<form id="absenceForm">${field('absenceDate','Дата смены / дня',new Date().toISOString().slice(0,10),'date','required')}${field('absenceComment','Комментарий или причина — необязательно','','text','maxlength="300"')}<button class="btn block" type="submit">Отправить сообщение</button></form>`);};
forms.absenceForm=async form=>{await productionPost('chat',{subtype:'absence_notice',absence_date:$('absenceDate').value,comment:$('absenceComment').value},form);closeSheet();await refreshTeamChat();};
forms.chatForm=async form=>{const value=$('chatText').value.trim(),attachment=await chatAttachment($('chatFile')?.files?.[0]);if(!value&&!attachment)throw new Error('Введите сообщение или добавьте файл');await productionPost('chat',{text:value,attachment,recipient_user_id:S.chatRecipient?Number(S.chatRecipient):null},form);$('chatText').value='';if($('chatFile'))$('chatFile').value='';delete form.dataset.requestId;await refreshTeamChat();};
actions.pinChat=async button=>{await productionPost('chat',{mode:'pin',message_id:button.dataset.id,pinned:button.dataset.pinned!=='1'});await refreshTeamChat();};
actions.saveChatAttachment=async button=>{if(typeof window.PortalNative?.saveBase64FileAsync!=='function')throw new Error('Сохранение доступно в мобильном приложении');const file=await productionGet('chat-file?id='+encodeURIComponent(button.dataset.id));const result=await nativePromise(id=>PortalNative.saveBase64FileAsync(id,file.filename,file.mime_type,file.file_b64));if(!result.ok)throw new Error(result.error||'Не удалось сохранить файл');toast('Сохранено · '+result.location);};
