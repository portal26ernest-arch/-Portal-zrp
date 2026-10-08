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
const expenseCategories={rent:'Аренда',logistics:'Логистика',carrier_pickup:'Забор из ТК',marketplace_delivery:'Доставка на маркетплейс',utilities:'Коммунальные расходы',waste:'Вывоз мусора',management:'Управленческие расходы',other:'Прочее'};
screens.expenses=async()=>{
  const [rows,catalog]=await Promise.all([productionGet('expenses'),productionCatalog()]);S.expenseRows=rows;S.expenseCatalog=catalog;
  paint(heading('Расходы','Общие расходы компании и затраты по клиентам',allowed('expenses.manage')?btn('Добавить расход','newExpense'):'')+
    `<div class="list">${rows.slice().reverse().map(e=>`<article class="item"><div class="row between"><b>${esc(e.category)}</b><strong>${rub(e.amount)}</strong></div><p class="meta">${e.client_id?'Клиент · '+esc(catalog.clients.find(c=>c.id===e.client_id)?.name||('#'+e.client_id)):'Общекомпанейский расход'} · ${esc(date(e.incurred_at||e.created_at))}</p>${e.note?`<p>${esc(e.note)}</p>`:''}</article>`).join('')||'<p class="empty">Расходов пока нет</p>'}</div>`);
};
actions.newExpense=()=>{const clients=S.expenseCatalog?.clients||[];openSheet('Новый расход',`<form id="expenseForm">${selectField('expenseCategory','Категория',Object.entries(expenseCategories).map(([k,v])=>`<option value="${k}">${esc(v)}</option>`).join(''))}${field('expenseAmount','Сумма, ₽','','number','required min="0.01" step="0.01"')}${selectField('expenseClient','Клиент — необязательно','<option value="">Вся компания</option>'+options(clients))}${field('expenseDate','Дата',new Date().toISOString().slice(0,10),'date','required')}${field('expenseNote','Комментарий','','text','maxlength="1000"')}<button class="btn block" type="submit">Записать расход</button></form>`);};
forms.expenseForm=async form=>{await productionPost('expenses',{category_code:$('expenseCategory').value,amount:$('expenseAmount').value,client_id:$('expenseClient').value?Number($('expenseClient').value):null,incurred_at:$('expenseDate').value,note:$('expenseNote').value},form);closeSheet();toast('Расход записан');await go('expenses');};

const organizerStatus={new:'Новая',in_progress:'В работе',done:'Выполнена',cancelled:'Отменена'};
const organizerPriority={normal:'Обычная',important:'Важная',urgent:'Срочная'};
const organizerRepeat={none:'Не повторять',daily:'Каждый день',weekly:'Каждую неделю',monthly:'Каждый месяц'};
const organizerLink={client:'Клиент',invoice:'Счёт',document:'Документ',request:'Запрос директору'};
function organizerMoment(value){if(!value)return '—';const d=new Date(value);return Number.isFinite(d.getTime())?d.toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}):'—';}
function organizerDay(value){const d=new Date(value);return Number.isFinite(d.getTime())?d.toLocaleDateString('sv-SE'):'0000-00-00';}
function organizerActive(t){return !['done','cancelled'].includes(t.status);}
function organizerCalendarDayNumber(value){const d=value instanceof Date?value:new Date(value);return Number.isFinite(d.getTime())?Math.floor(Date.UTC(d.getFullYear(),d.getMonth(),d.getDate())/86400000):null;}
function organizerOverdueDays(value,now=new Date()){const dueDay=organizerCalendarDayNumber(value),nowDay=organizerCalendarDayNumber(now);return dueDay==null||nowDay==null?0:Math.max(0,nowDay-dueDay);}
function organizerDayWord(days){const mod100=days%100,mod10=days%10;if(mod100>=11&&mod100<=14)return 'дней';if(mod10===1)return 'день';if(mod10>=2&&mod10<=4)return 'дня';return 'дней';}
function organizerOverdueLabel(value,now=new Date()){const days=organizerOverdueDays(value,now);return days>0?'Просрочено '+days+' '+organizerDayWord(days):'Просрочено';}
function organizerTodayRows(rows,now=new Date()){
  const today=organizerDay(now),nowTime=now.getTime();
  return rows.filter(t=>organizerActive(t)&&organizerDay(t.due_at)<=today).sort((a,b)=>{
    const aTime=new Date(a.due_at).getTime(),bTime=new Date(b.due_at).getTime();
    const aLate=Number.isFinite(aTime)&&aTime<nowTime,bLate=Number.isFinite(bTime)&&bTime<nowTime;
    if(aLate!==bLate)return aLate?-1:1;
    return (Number.isFinite(aTime)?aTime:Number.MAX_SAFE_INTEGER)-(Number.isFinite(bTime)?bTime:Number.MAX_SAFE_INTEGER);
  });
}
function organizerTaskCard(t){
  const now=new Date(),due=new Date(t.due_at),late=organizerActive(t)&&Number.isFinite(due.getTime())&&due<now;
  const completed=t.status==='done',badge=completed?'✓ Выполнена':late?'🔴 '+organizerOverdueLabel(t.due_at,now):organizerStatus[t.status]||'Задача';
  const link=t.linked_type?'<p class="meta">'+esc(organizerLink[t.linked_type]||'Связь')+' · '+esc(t.linked_id)+'</p>':'';
  let buttons=btn('История','organizerHistory','data-id="'+esc(t.id)+'"','text');
  if(t.can_change_status&&t.status==='new')buttons+=btn('В работу','organizerStatus','data-id="'+esc(t.id)+'" data-status="in_progress"','secondary');
  if(t.can_comment&&t.status!=='cancelled')buttons+=btn('Комментарий','organizerComment','data-id="'+esc(t.id)+'"','secondary');
  if(t.can_change_status&&t.status==='in_progress')buttons+=btn('✓ Выполнить','organizerComplete','data-id="'+esc(t.id)+'"');
  if(t.can_edit&&organizerActive(t))buttons+=btn('Перенести','organizerReschedule','data-id="'+esc(t.id)+'"','secondary');
  if(t.can_edit&&organizerActive(t))buttons+=btn('Отменить','organizerStatus','data-id="'+esc(t.id)+'" data-status="cancelled"','text');
  return '<article class="item"><div class="row between"><div><span class="eyebrow">'+esc(organizerPriority[t.priority]||'Обычная')+'</span><h3>'+esc(t.title)+'</h3></div><span class="badge '+(completed?'green':late?'warning':'')+'">'+esc(badge)+'</span></div>'+
    (t.description?'<p>'+esc(t.description)+'</p>':'')+
    '<p><b>Срок:</b> '+esc(organizerMoment(t.due_at))+(t.remind_at?' · <b>Напомнить:</b> '+esc(organizerMoment(t.remind_at)):'')+'</p>'+
    '<p class="meta">Исполнитель: '+esc(t.assignee_name)+' · '+esc(t.assignee_role_label||'Сотрудник')+'<br>Поставил: '+esc(t.created_by_name)+(t.repeat_rule&&t.repeat_rule!=='none'?' · '+esc(organizerRepeat[t.repeat_rule]):'')+'</p>'+link+
    '<div class="item-actions">'+buttons+'</div></article>';
}
function organizerCalendar(rows,month){
  const first=new Date(month.getFullYear(),month.getMonth(),1),last=new Date(month.getFullYear(),month.getMonth()+1,0);
  const start=(first.getDay()+6)%7,cells=[],names=['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];
  for(let i=0;i<start;i++)cells.push('<div class="card" style="min-height:92px;opacity:.35"></div>');
  for(let day=1;day<=last.getDate();day++){
    const key=[month.getFullYear(),String(month.getMonth()+1).padStart(2,'0'),String(day).padStart(2,'0')].join('-');
    const dayRows=rows.filter(t=>organizerDay(t.due_at)===key);
    cells.push('<div class="card" style="min-height:92px;padding:10px"><b>'+day+'</b>'+dayRows.slice(0,4).map(t=>'<button type="button" class="btn text block" data-action="organizerHistory" data-id="'+esc(t.id)+'" style="text-align:left;padding:4px 0">'+esc(t.title)+'</button>').join('')+(dayRows.length>4?'<span class="meta">Ещё '+(dayRows.length-4)+'</span>':'')+'</div>');
  }
  return '<div class="row between"><button class="btn secondary" data-action="organizerMonth" data-shift="-1">← Предыдущий</button><h2>'+esc(month.toLocaleDateString('ru-RU',{month:'long',year:'numeric'}))+'</h2><button class="btn secondary" data-action="organizerMonth" data-shift="1">Следующий →</button></div>'+
    '<div class="organizer-calendar-scroll"><div class="organizer-calendar-grid">'+names.map(x=>'<div class="meta organizer-calendar-weekday"><b>'+x+'</b></div>').join('')+cells.join('')+'</div></div>';
}
function organizerFiltered(rows,view){
  const now=new Date(),today=organizerDay(now);
  if(view==='today')return organizerTodayRows(rows,now);
  if(view==='upcoming')return rows.filter(t=>organizerActive(t)&&new Date(t.due_at)>=now&&organizerDay(t.due_at)!==today);
  if(view==='overdue')return rows.filter(t=>organizerActive(t)&&new Date(t.due_at)<now);
  if(view==='incoming')return rows.filter(t=>t.assignee_user_id===S.me.id);
  if(view==='assigned')return rows.filter(t=>t.created_by===S.me.id);
  return rows;
}
function organizerCachedAt(result){
  const millis=Number(result?.cached_at_ms||0);if(Number.isFinite(millis)&&millis>0)return millis;
  const parsed=Date.parse(result?.cached_at||'');return Number.isFinite(parsed)?parsed:0;
}
function organizerSyncTime(value){
  const d=new Date(Number(value)||0);return Number.isFinite(d.getTime())?d.toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'}):'—';
}
function organizerCounts(rows){
  return {today:organizerFiltered(rows,'today').length,upcoming:organizerFiltered(rows,'upcoming').length,overdue:organizerFiltered(rows,'overdue').length,incoming:organizerFiltered(rows,'incoming').length,assigned:organizerFiltered(rows,'assigned').length,all:rows.length};
}
function renderOrganizerTabs(){
  const box=$('organizerTabs');if(!box)return;
  const counts=organizerCounts(S.organizerRows||[]);
  const tabs=[['today','Сегодня'],['upcoming','Предстоящие'],['overdue','Просроченные'],['incoming','Назначенные мне'],['assigned','Поставленные мной'],['calendar','Календарь'],['all','Все задачи']];
  box.innerHTML=tabs.map(([key,label])=>btn(label+(key==='calendar'?'':' <span class="organizer-tab-count">'+num(counts[key]||0)+'</span>'),'organizerView','data-view="'+key+'"',S.organizerView===key?'':'secondary')).join('');
}
function renderOrganizerBody(){
  if(!$('organizerBody'))return;
  if(!S.organizerLoaded){$('organizerBody').innerHTML='<div class="loading compact"><span class="spinner"></span><p>Загружаем задачи…</p></div>';return;}
  const view=S.organizerView||'today',rows=S.organizerRows||[];
  if(view==='calendar'){
    S.organizerMonth=S.organizerMonth||new Date(new Date().getFullYear(),new Date().getMonth(),1);
    $('organizerBody').innerHTML=organizerCalendar(rows,S.organizerMonth);return;
  }
  const filtered=organizerFiltered(rows,view);
  const empty=S.organizerLoadError&&!rows.length
    ?'<div class="notice warning"><b>Не удалось обновить задачи</b><p>Показывать пока нечего. Проверьте связь и нажмите «Обновить».</p>'+btn('Обновить','organizerRetry','','secondary')+'</div>'
    :'<p class="empty organizer-empty">Задач в этом разделе нет</p>';
  $('organizerBody').innerHTML='<div class="list">'+(filtered.map(organizerTaskCard).join('')||empty)+'</div>';
}
function renderOrganizerSync(){
  const box=$('organizerSync');if(!box)return;
  const sync=S.organizerSync||{};
  if(sync.loading&&!S.organizerLoaded){box.innerHTML='<div class="organizer-sync"><span class="spinner"></span><span>Получаем актуальные задачи…</span></div>';return;}
  if(!sync.loadedAt&&!sync.cached&&!sync.error){box.innerHTML='';return;}
  let text='',klass='';
  if(sync.cached){klass=' cached';text='Локальные данные'+(sync.cachedAt?' · синхронизация '+organizerSyncTime(sync.cachedAt):'');}
  else if(sync.error){klass=' warning';text='Сервер временно недоступен · показано последнее доступное состояние';}
  else{text='Синхронизировано · '+organizerSyncTime(sync.loadedAt);}
  box.innerHTML='<div class="organizer-sync'+klass+'"><span>'+esc(text)+'</span>'+btn('Обновить','organizerRetry','','text')+'</div>';
}
function refreshOrganizerViewButtons(){renderOrganizerTabs();}
async function organizerFetch(path,fresh=false){return api('GET','/api/v3/'+path,undefined,fresh?{fresh:true}:{});}
async function refreshOrganizer(fresh=true){
  const scope=allowed('organizer.manage')?'company':'mine';
  try{
    const result=await organizerFetch('organizer?scope='+scope,fresh);
    S.organizerRows=Array.isArray(result.data)?result.data:[];S.organizerLoaded=true;S.organizerLoadError=null;
    S.organizerSync={loading:false,cached:!!result.cached,cachedAt:organizerCachedAt(result),loadedAt:Date.now(),error:''};
  }catch(error){
    S.organizerLoadError=error;if(!Array.isArray(S.organizerRows))S.organizerRows=[];
    S.organizerSync={...(S.organizerSync||{}),loading:false,error:String(error.message||error)};
  }
  renderOrganizerSync();renderOrganizerTabs();renderOrganizerBody();
}

const organizerRequestType={materials_purchase:'Закупка материалов',equipment_purchase:'Закупка оборудования',repair:'Ремонт',expense:'Расходы',tariff_change:'Изменение условий/тарифов',hr:'Кадровый вопрос',other:'Другое'};
const organizerRequestStatus={new:'Новый',review:'На рассмотрении',approved:'Одобрен',rejected:'Отклонён',needs_info:'Нужна информация',done:'Выполнен'};
const canCreateDirectorRequest=()=>can('organizer')&&allowed('organizer.request.create')&&['manager','admin'].includes(S.me?.role);
function organizerRequestCard(r){
  let details='<p class="meta">Автор: '+esc(r.created_by_name)+' · Директор: '+esc(r.director_name||'—')+(r.responsible_name?' · Ответственный: '+esc(r.responsible_name):'')+'</p>';
  if(r.requested_due_at)details+='<p><b>Желаемый срок:</b> '+esc(organizerMoment(r.requested_due_at))+'</p>';
  if(r.amount!=null)details+='<p><b>Сумма:</b> '+esc(rub(r.amount))+'</p>';
  if(r.item_name)details+='<p><b>Материал / товар:</b> '+esc(r.item_name)+(r.quantity?' · '+esc(r.quantity)+' '+esc(r.unit||''):'')+'</p>';
  if(r.task_id)details+='<p class="meta">Связанная задача: '+esc(r.task_id)+'</p>';
  let buttons=btn('История','organizerRequestHistory','data-id="'+esc(r.id)+'"','text')+btn('Комментарий','organizerRequestComment','data-id="'+esc(r.id)+'"','secondary');
  if(r.can_decide&&r.status==='new')buttons+=btn('Взять на рассмотрение','organizerRequestQuickStatus','data-id="'+esc(r.id)+'" data-status="review"','secondary');
  if(r.can_decide&&r.status==='review'){buttons+=btn('Одобрить','organizerRequestDecision','data-id="'+esc(r.id)+'" data-status="approved"');buttons+=btn('Нужна информация','organizerRequestDecision','data-id="'+esc(r.id)+'" data-status="needs_info"','secondary');buttons+=btn('Отклонить','organizerRequestDecision','data-id="'+esc(r.id)+'" data-status="rejected"','text');}
  if(r.can_decide&&['needs_info','rejected','approved'].includes(r.status))buttons+=btn('Вернуть на рассмотрение','organizerRequestQuickStatus','data-id="'+esc(r.id)+'" data-status="review"','secondary');
  if(r.can_decide&&r.status==='approved')buttons+=btn('Выполнено','organizerRequestQuickStatus','data-id="'+esc(r.id)+'" data-status="done"');
  if(r.can_create_task)buttons+=btn('Создать задачу из запроса','organizerRequestCreateTask','data-id="'+esc(r.id)+'"','secondary');
  const files=(r.attachments||[]).map(a=>btn('Файл: '+esc(a.original_name),'organizerRequestFile','data-id="'+esc(a.id)+'"','text')).join('');
  return '<article class="item"><div class="row between"><div><span class="eyebrow">'+esc(organizerRequestType[r.request_type]||'Запрос')+' · '+esc(organizerPriority[r.priority]||'Обычная')+'</span><h3>'+esc(r.title)+'</h3></div><span class="badge '+(r.status==='needs_info'?'warning':'')+'">'+esc(organizerRequestStatus[r.status]||r.status)+'</span></div>'+(r.description?'<p>'+esc(r.description)+'</p>':'')+details+(files?'<div class="item-actions">'+files+'</div>':'')+'<div class="item-actions">'+buttons+'</div></article>';
}
function renderOrganizerRequestsPanel(){
  const box=$('organizerRequestsPanel');if(!box)return;
  const canMine=canCreateDirectorRequest(),canIncoming=allowed('organizer.request.decide');
  if(!canMine&&!canIncoming){box.innerHTML='';return;}
  const mine=S.organizerMineRequests||[],incoming=S.organizerIncomingRequests||[];
  const total=mine.length+incoming.length;
  const attention=incoming.filter(r=>['new','review'].includes(r.status)).length+mine.filter(r=>r.status==='needs_info').length;
  let content='';
  if(mine.length)content+='<div class="organizer-request-group"><h3>Мои запросы</h3><div class="list">'+mine.map(organizerRequestCard).join('')+'</div></div>';
  if(incoming.length)content+='<div class="organizer-request-group"><h3>Входящие запросы</h3><div class="list">'+incoming.map(organizerRequestCard).join('')+'</div></div>';
  if(!total)content+='<p class="meta organizer-request-empty">Активных запросов нет.</p>';
  if(canMine)content='<div class="organizer-request-toolbar">'+btn(icon('plus')+' Новый запрос','organizerRequestNew','','secondary')+'</div>'+content;
  box.innerHTML='<details class="organizer-requests card"'+(attention?' open':'')+'><summary><span><b>Запросы директору</b><small>'+(attention?attention+' требуют внимания':total?total+' всего':'нет активных')+'</small></span><span class="badge">'+num(total)+'</span></summary><div class="organizer-request-content">'+content+'</div></details>';
}
async function refreshOrganizerRequests(fresh=true){
  const specs=[];
  if(canCreateDirectorRequest())specs.push(['mine','organizer-requests?scope=mine']);
  if(allowed('organizer.request.decide'))specs.push(['incoming','organizer-requests?scope=incoming']);
  const settled=await Promise.allSettled(specs.map(([,path])=>organizerFetch(path,fresh)));
  for(let i=0;i<settled.length;i++){
    const entry=settled[i],key=specs[i][0];
    if(entry.status!=='fulfilled')continue;
    const rows=Array.isArray(entry.value.data)?entry.value.data:[];
    if(key==='mine')S.organizerMineRequests=rows;else S.organizerIncomingRequests=rows;
  }
  S.organizerMineRequests=S.organizerMineRequests||[];S.organizerIncomingRequests=S.organizerIncomingRequests||[];
  S.organizerRequestRows=[...S.organizerMineRequests,...S.organizerIncomingRequests.filter(x=>!S.organizerMineRequests.some(m=>m.id===x.id))];
  renderOrganizerRequestsPanel();
}
async function organizerEnsureUsers(){
  if(!Array.isArray(S.organizerUsers)||!S.organizerUsers.length){const result=await organizerFetch('organizer-users',true);S.organizerUsers=Array.isArray(result.data)?result.data:[];}
  return S.organizerUsers;
}
async function organizerEnsureDirectors(){
  if(!Array.isArray(S.organizerDirectors)||!S.organizerDirectors.length){const result=await organizerFetch('organizer-directors',true);S.organizerDirectors=Array.isArray(result.data)?result.data:[];}
  return S.organizerDirectors;
}
async function organizerEnsureRequestUsers(){
  if(!Array.isArray(S.organizerRequestUsers)||!S.organizerRequestUsers.length){const result=await organizerFetch('organizer-request-responsibles',true);S.organizerRequestUsers=Array.isArray(result.data)?result.data:[];}
  return S.organizerRequestUsers;
}
async function organizerLoadWorkspace(fresh=false){
  const scope=allowed('organizer.manage')?'company':'mine',specs=[['tasks','organizer?scope='+scope]];
  if(canCreateDirectorRequest())specs.push(['mine','organizer-requests?scope=mine']);
  if(allowed('organizer.request.decide'))specs.push(['incoming','organizer-requests?scope=incoming']);
  S.organizerSync={...(S.organizerSync||{}),loading:true};renderOrganizerSync();
  const settled=await Promise.allSettled(specs.map(([,path])=>organizerFetch(path,fresh)));
  let firstError=null,tasksOk=false;const successes=[];
  settled.forEach((entry,index)=>{
    const key=specs[index][0];
    if(entry.status==='fulfilled'){
      successes.push(entry.value);const rows=Array.isArray(entry.value.data)?entry.value.data:[];
      if(key==='tasks'){S.organizerRows=rows;S.organizerLoaded=true;S.organizerLoadError=null;tasksOk=true;}
      else if(key==='mine')S.organizerMineRequests=rows;
      else if(key==='incoming')S.organizerIncomingRequests=rows;
    }else{firstError=firstError||entry.reason;if(key==='tasks')S.organizerLoadError=entry.reason;}
  });
  if(!tasksOk&&!S.organizerLoaded)throw firstError||new Error('Не удалось загрузить задачи');
  S.organizerMineRequests=S.organizerMineRequests||[];S.organizerIncomingRequests=S.organizerIncomingRequests||[];
  S.organizerRequestRows=[...S.organizerMineRequests,...S.organizerIncomingRequests.filter(x=>!S.organizerMineRequests.some(m=>m.id===x.id))];
  const cached=successes.some(result=>result?.cached),times=successes.map(organizerCachedAt).filter(Boolean);
  S.organizerSync={loading:false,cached,cachedAt:times.length?Math.min(...times):0,loadedAt:Date.now(),error:firstError?String(firstError.message||firstError):''};
  renderOrganizerSync();renderOrganizerTabs();renderOrganizerBody();renderOrganizerRequestsPanel();
  return cached;
}
async function organizerFreshReload(view,epoch){
  try{await organizerLoadWorkspace(true);}
  catch(error){if(S.page==='organizer'&&S.view===view&&S.epoch===epoch){S.organizerSync={...(S.organizerSync||{}),loading:false,error:String(error.message||error)};renderOrganizerSync();}}
}
screens.organizer=async()=>{
  if(!can('organizer'))throw new Error('Нет доступа к Органайзеру');
  const companyKey=String(S.company?.id||S.me?.company_id||'');
  if(S.organizerCompanyKey!==companyKey){
    S.organizerCompanyKey=companyKey;S.organizerRows=[];S.organizerMineRequests=[];S.organizerIncomingRequests=[];S.organizerRequestRows=[];
    S.organizerUsers=null;S.organizerDirectors=null;S.organizerRequestUsers=null;S.organizerLoaded=false;S.organizerSync=null;S.organizerLoadError=null;
  }
  S.organizerView=S.organizerView||'today';
  paint(heading('Органайзер','Задачи и сроки',allowed('organizer.assign')?btn(icon('plus')+' Новая','organizerNew','','secondary'):'')+
    '<div id="organizerSync"></div><div id="organizerTabs" class="organizer-tabs"></div><div id="organizerBody"></div><div id="organizerRequestsPanel"></div>');
  renderOrganizerSync();renderOrganizerTabs();renderOrganizerBody();renderOrganizerRequestsPanel();
  const view=S.view,epoch=S.epoch,cached=await organizerLoadWorkspace(false);
  if(cached&&S.page==='organizer'&&S.view===view&&S.epoch===epoch)void organizerFreshReload(view,epoch);
};

actions.organizerRequestNew=async()=>{
  if(!canCreateDirectorRequest())throw new Error('Создавать запросы директору может управляющий или менеджер');
  const directors=await organizerEnsureDirectors();if(!directors.length)throw new Error('В компании нет активного директора');
  const types=Object.entries(organizerRequestType).map(([key,label])=>'<option value="'+key+'">'+esc(label)+'</option>').join('');
  const directorOptions=directors.map(u=>'<option value="'+u.id+'">'+esc(u.display_name)+'</option>').join('');
  openSheet('Новый запрос директору','<form id="organizerRequestForm">'+
    selectField('organizerRequestType','Тип запроса',types)+
    selectField('organizerRequestDirector','Директор',directorOptions)+
    field('organizerRequestTitle','Тема запроса','','text','required maxlength="200" placeholder="Например: закупить упаковочные материалы"')+
    '<label class="field"><span>Описание</span><textarea id="organizerRequestDescription" maxlength="4000" rows="4" placeholder="Что требуется и зачем"></textarea></label>'+
    selectField('organizerRequestPriority','Приоритет','<option value="normal">Обычный</option><option value="important">Важный</option><option value="urgent">Срочный</option>')+
    field('organizerRequestDue','Желаемый срок','','datetime-local')+
    field('organizerRequestAmount','Сумма, ₽ — необязательно','','number','min="0.01" step="0.01"')+
    field('organizerRequestItem','Материал / товар — необязательно','','text','maxlength="200"')+
    field('organizerRequestQuantity','Количество — необязательно','','number','min="0.001" step="0.001"')+
    field('organizerRequestUnit','Единица — необязательно','','text','maxlength="50" placeholder="шт., уп., рул."')+
    '<label class="field"><span>Комментарий — необязательно</span><textarea id="organizerRequestInitialComment" maxlength="2000" rows="3"></textarea></label>'+
    '<label class="field"><span>Фото или файл — необязательно</span><input id="organizerRequestAttachment" type="file" accept=".jpg,.jpeg,.png,.webp,.pdf,.txt,image/jpeg,image/png,image/webp,application/pdf,text/plain"></label>'+
    '<button class="btn block" type="submit">Отправить запрос директору</button></form>');
};
forms.organizerRequestForm=async form=>{
  const attachment=await chatAttachment($('organizerRequestAttachment').files?.[0]);
  await productionPost('organizer-requests',{mode:'create',request_type:$('organizerRequestType').value,
    director_user_id:Number($('organizerRequestDirector').value),title:$('organizerRequestTitle').value.trim(),
    description:$('organizerRequestDescription').value.trim(),priority:$('organizerRequestPriority').value,
    requested_due_at:$('organizerRequestDue').value||null,amount:$('organizerRequestAmount').value||null,
    item_name:$('organizerRequestItem').value.trim(),quantity:$('organizerRequestQuantity').value||null,
    unit:$('organizerRequestUnit').value.trim(),initial_comment:$('organizerRequestInitialComment').value.trim(),attachment},form);
  closeSheet();toast('Запрос отправлен директору');await refreshOrganizerRequests();
};
actions.organizerRequestQuickStatus=async button=>{
  await productionPost('organizer-requests',{mode:'decide',organizer_request_id:button.dataset.id,status:button.dataset.status});
  toast('Статус запроса изменён');await refreshOrganizerRequests();
};
actions.organizerRequestDecision=async button=>{
  const r=(S.organizerRequestRows||[]).find(x=>x.id===button.dataset.id);if(!r)throw new Error('Запрос не найден');
  const responsible=(await organizerEnsureRequestUsers()).map(u=>'<option value="'+u.id+'" '+(r.responsible_user_id===u.id?'selected':'')+'>'+esc(u.display_name)+' · '+esc(u.role_label)+'</option>').join('');
  openSheet(organizerRequestStatus[button.dataset.status]||'Решение по запросу','<form id="organizerRequestDecisionForm" data-id="'+esc(r.id)+'" data-status="'+esc(button.dataset.status)+'">'+
    selectField('organizerRequestResponsible','Ответственный — необязательно','<option value="">Не назначать</option>'+responsible)+
    '<label class="field"><span>Комментарий — необязательно</span><textarea id="organizerRequestDecisionComment" maxlength="2000" rows="3"></textarea></label>'+
    '<button class="btn block" type="submit">Сохранить решение</button></form>');
};
forms.organizerRequestDecisionForm=async form=>{
  const responsible=$('organizerRequestResponsible').value;
  await productionPost('organizer-requests',{mode:'decide',organizer_request_id:form.dataset.id,status:form.dataset.status,
    responsible_user_id:responsible?Number(responsible):null,comment:$('organizerRequestDecisionComment').value.trim()},form);
  closeSheet();toast('Решение сохранено');await refreshOrganizerRequests();
};
actions.organizerRequestComment=button=>{
  const r=(S.organizerRequestRows||[]).find(x=>x.id===button.dataset.id);if(!r)throw new Error('Запрос не найден');
  openSheet('Комментарий к запросу','<form id="organizerRequestCommentForm" data-id="'+esc(r.id)+'"><p><b>'+esc(r.title)+'</b></p>'+
    '<label class="field"><span>Комментарий</span><textarea id="organizerRequestCommentText" maxlength="2000" rows="4" required></textarea></label>'+
    '<button class="btn block" type="submit">Отправить комментарий</button></form>');
};
forms.organizerRequestCommentForm=async form=>{
  await productionPost('organizer-requests',{mode:'comment',organizer_request_id:form.dataset.id,comment:$('organizerRequestCommentText').value.trim()},form);
  closeSheet();toast('Комментарий отправлен');await refreshOrganizerRequests();
};
function organizerRequestEventDetail(value){
  const raw=String(value||'');const parts=raw.split(' → ');
  return parts.length===2?(organizerRequestStatus[parts[0]]||parts[0])+' → '+(organizerRequestStatus[parts[1]]||parts[1]):raw;
}
actions.organizerRequestHistory=async button=>{
  const r=(S.organizerRequestRows||[]).find(x=>x.id===button.dataset.id);if(!r)throw new Error('Запрос не найден');
  const events=await productionGet('organizer-request-events?organizer_request_id='+encodeURIComponent(r.id));
  const names={created:'Запрос создан',comment:'Комментарий',status:'Изменён статус',task_created:'Создана связанная задача'};
  openSheet(r.title,'<p><b>Статус:</b> '+esc(organizerRequestStatus[r.status]||r.status)+'</p><h3>История</h3><div class="list">'+
    (events.slice().reverse().map(e=>'<div class="item"><b>'+esc(names[e.event]||'Изменение')+'</b><p class="meta">'+esc(e.actor_name)+' · '+esc(organizerMoment(e.occurred_at))+'</p>'+
    (e.detail?'<p>'+esc(organizerRequestEventDetail(e.detail))+'</p>':'')+(e.comment?'<p>'+esc(e.comment)+'</p>':'')+'</div>').join('')||'<p class="empty">История пока пуста</p>')+'</div>');
};
actions.organizerRequestCreateTask=async button=>{
  const r=(S.organizerRequestRows||[]).find(x=>x.id===button.dataset.id);if(!r)throw new Error('Запрос не найден');
  const users=await organizerEnsureRequestUsers();const opts=users.map(u=>'<option value="'+u.id+'" '+(r.responsible_user_id===u.id?'selected':'')+'>'+esc(u.display_name)+' · '+esc(u.role_label)+'</option>').join('');
  openSheet('Создать задачу из запроса','<form id="organizerRequestTaskForm" data-id="'+esc(r.id)+'">'+selectField('organizerRequestTaskAssignee','Ответственный',opts)+
    '<button class="btn block" type="submit">Создать связанную задачу</button><p class="meta">Повторное нажатие не создаст дубль.</p></form>');
};
forms.organizerRequestTaskForm=async form=>{
  await productionPost('organizer-requests',{mode:'create_task',organizer_request_id:form.dataset.id,responsible_user_id:Number($('organizerRequestTaskAssignee').value)},form);
  closeSheet();toast('Задача создана и связана с запросом');await refreshOrganizerRequests();await refreshOrganizer();
};
actions.organizerRequestFile=async button=>{
  const f=await productionGet('organizer-request-file?id='+encodeURIComponent(button.dataset.id));
  const raw=atob(f.file_b64),bytes=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)bytes[i]=raw.charCodeAt(i);
  const url=URL.createObjectURL(new Blob([bytes],{type:f.mime_type||'application/octet-stream'})),a=document.createElement('a');
  a.href=url;a.download=f.original_name||f.filename||'PORTAL-request-file';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
actions.organizerView=button=>{S.organizerView=button.dataset.view;renderOrganizerTabs();renderOrganizerBody();};
actions.organizerMonth=button=>{const m=S.organizerMonth||new Date();S.organizerMonth=new Date(m.getFullYear(),m.getMonth()+Number(button.dataset.shift),1);renderOrganizerBody();};
actions.organizerRetry=async button=>{if(button)button.disabled=true;try{await organizerLoadWorkspace(true);}finally{if(button)button.disabled=false;}};
actions.organizerNew=async()=>{
  if(!allowed('organizer.assign'))throw new Error('Нет права ставить задачи');
  const users=await organizerEnsureUsers(),tomorrow=new Date(Date.now()+86400000);tomorrow.setHours(10,0,0,0);
  const local=tomorrow.getFullYear()+'-'+String(tomorrow.getMonth()+1).padStart(2,'0')+'-'+String(tomorrow.getDate()).padStart(2,'0')+'T'+String(tomorrow.getHours()).padStart(2,'0')+':00';
  openSheet('Новая задача','<form id="organizerForm">'+
    selectField('organizerAssignee','Исполнитель',users.map(u=>'<option value="'+u.id+'">'+esc(u.display_name)+' · '+esc(u.role_label)+(u.self?' · Я':'')+'</option>').join(''))+
    field('organizerTitle','Название задачи','','text','required maxlength="200" placeholder="Например: проверить оплату счёта"')+
    '<label class="field"><span>Описание — необязательно</span><textarea id="organizerDescription" maxlength="4000" rows="4" placeholder="Что именно нужно сделать"></textarea></label>'+
    field('organizerDue','Срок',local,'datetime-local','required')+
    selectField('organizerReminder','Напомнить','<option value="none">Не напоминать заранее</option><option value="15m">За 15 минут</option><option value="1h">За 1 час</option><option value="2h">За 2 часа</option><option value="1d">За 1 день</option><option value="custom">Своё время</option>')+
    field('organizerReminderCustom','Своя дата напоминания — если выбрано «Своё время»','','datetime-local')+
    selectField('organizerPriority','Приоритет','<option value="normal">Обычная</option><option value="important">Важная</option><option value="urgent">Срочная</option>')+
    selectField('organizerRepeat','Повтор','<option value="none">Не повторять</option><option value="daily">Каждый день</option><option value="weekly">Каждую неделю</option><option value="monthly">Каждый месяц</option>')+
    selectField('organizerLinkType','Связать с','<option value="">Без связи</option><option value="client">Клиент</option><option value="invoice">Счёт</option><option value="document">Документ</option>')+
    field('organizerLinkId','Номер / идентификатор связанной записи','','text','maxlength="200"')+
    '<button class="btn block" type="submit">Поставить задачу</button><p class="meta">Постановщик и история изменений фиксируются автоматически.</p></form>');
};
forms.organizerForm=async form=>{
  const due=$('organizerDue').value,choice=$('organizerReminder').value;let remind_at=null;
  if(choice==='custom')remind_at=$('organizerReminderCustom').value||null;
  else if(choice!=='none'){const mins={ '15m':15,'1h':60,'2h':120,'1d':1440 }[choice],d=new Date(due);remind_at=new Date(d.getTime()-mins*60000).toLocaleString('sv-SE').replace(' ','T').slice(0,16);}
  const linked_type=$('organizerLinkType').value,linked_id=$('organizerLinkId').value.trim();
  await productionPost('organizer',{mode:'create',assignee_user_id:Number($('organizerAssignee').value),title:$('organizerTitle').value.trim(),
    description:$('organizerDescription').value.trim(),due_at:due,remind_at,priority:$('organizerPriority').value,repeat_rule:$('organizerRepeat').value,
    linked_type,linked_id:linked_type?linked_id:''},form);
  closeSheet();toast('Задача поставлена');await refreshOrganizer();
};
actions.organizerStatus=async button=>{await productionPost('organizer',{mode:'status',task_id:button.dataset.id,status:button.dataset.status});toast(button.dataset.status==='done'?'Задача выполнена':button.dataset.status==='in_progress'?'Задача взята в работу':'Задача отменена');await refreshOrganizer();};
actions.organizerComplete=button=>{
  const t=(S.organizerRows||[]).find(x=>x.id===button.dataset.id);if(!t)throw new Error('Задача не найдена');
  openSheet('Завершить задачу','<form id="organizerCompleteForm" data-task="'+esc(t.id)+'"><p><b>'+esc(t.title)+'</b></p>'+
    '<label class="field"><span>Комментарий о результате — необязательно</span><textarea id="organizerCompleteComment" maxlength="2000" rows="4" placeholder="Что сделано, результат или важное пояснение"></textarea></label>'+
    '<button class="btn block" type="submit">✓ Отметить выполненной</button></form>');
};
forms.organizerCompleteForm=async form=>{
  await productionPost('organizer',{mode:'status',task_id:form.dataset.task,status:'done',comment:$('organizerCompleteComment').value.trim()},form);
  closeSheet();toast('✓ Задача выполнена');await refreshOrganizer();
};
actions.organizerComment=button=>{
  const t=(S.organizerRows||[]).find(x=>x.id===button.dataset.id);if(!t)throw new Error('Задача не найдена');
  openSheet('Комментарий к задаче','<form id="organizerCommentForm" data-task="'+esc(t.id)+'"><p><b>'+esc(t.title)+'</b></p>'+
    '<label class="field"><span>Комментарий исполнителя</span><textarea id="organizerCommentText" maxlength="2000" rows="4" required placeholder="Например: что уже сделано, что мешает или почему задача пока не выполнена"></textarea></label>'+
    '<button class="btn block" type="submit">Добавить комментарий</button></form>');
};
forms.organizerCommentForm=async form=>{
  await productionPost('organizer',{mode:'comment',task_id:form.dataset.task,comment:$('organizerCommentText').value.trim()},form);
  closeSheet();toast('Комментарий добавлен');await refreshOrganizer();
};
actions.organizerReschedule=button=>{
  const t=(S.organizerRows||[]).find(x=>x.id===button.dataset.id);if(!t)throw new Error('Задача не найдена');
  openSheet('Перенести задачу','<form id="organizerRescheduleForm" data-task="'+esc(t.id)+'">'+field('organizerNewDue','Новый срок',String(t.due_at||'').slice(0,16),'datetime-local','required')+field('organizerNewReminder','Напомнить в',String(t.remind_at||'').slice(0,16),'datetime-local')+'<button class="btn block" type="submit">Сохранить новый срок</button></form>');
};
forms.organizerRescheduleForm=async form=>{await productionPost('organizer',{mode:'reschedule',task_id:form.dataset.task,due_at:$('organizerNewDue').value,remind_at:$('organizerNewReminder').value||null},form);closeSheet();toast('Срок изменён');await refreshOrganizer();};
actions.organizerHistory=async button=>{
  const t=(S.organizerRows||[]).find(x=>x.id===button.dataset.id);if(!t)throw new Error('Задача не найдена');
  const events=await productionGet('organizer-events?task_id='+encodeURIComponent(t.id));
  const eventNames={created:'Создана задача',status:'Изменён статус',comment:'Комментарий исполнителя',rescheduled:'Изменён срок',edited:'Изменена задача'};
  openSheet(t.title,'<p><b>Исполнитель:</b> '+esc(t.assignee_name)+'</p><p><b>Срок:</b> '+esc(organizerMoment(t.due_at))+'</p><h3>История</h3><div class="list">'+events.slice().reverse().map(e=>'<div class="item"><b>'+esc(eventNames[e.event]||'Изменение')+'</b><p class="meta">'+esc(e.actor_name)+' · '+esc(organizerMoment(e.occurred_at))+'</p>'+(e.detail?'<p>'+esc(e.detail)+'</p>':'')+'</div>').join('')+'</div>');
};
async function organizerReminderCheck(){
  if(!S.token||!can('organizer'))return;
  try{
    const rows=await productionGet('organizer?scope=incoming'),now=Date.now();
    if(globalThis.__PORTAL_ANDROID__||globalThis.__PORTAL_IOS__){
      const reminders=rows.filter(organizerActive).map(t=>({id:String(t.id),title:String(t.title||'Задача'),at:String(t.remind_at||t.due_at||'')})).filter(t=>Number.isFinite(Date.parse(t.at))&&Date.parse(t.at)>now&&Date.parse(t.at)<now+30*86400000);
      try{globalThis.PortalNative?.scheduleOrganizerReminders?.(JSON.stringify(reminders));}catch{}
      return;
    }
    if(!globalThis.__PORTAL_DESKTOP__)return;
    S.organizerReminderSeen=S.organizerReminderSeen||new Set();
    for(const t of rows){
      if(!organizerActive(t))continue;
      const remind=t.remind_at?new Date(t.remind_at).getTime():null,due=new Date(t.due_at).getTime();
      if((remind!==null&&remind<=now&&due>=now)||(remind===null&&due<=now)){
        const key=t.id+':'+(t.remind_at||t.due_at);if(S.organizerReminderSeen.has(key))continue;
        S.organizerReminderSeen.add(key);toast('Напоминание: '+t.title+(due<now?' · срок уже наступил':''),due<now);
      }
    }
  }catch{}
}
function startOrganizerReminderWatch(){clearInterval(S.organizerReminderTimer);if(!S.token||!can('organizer')){if(globalThis.__PORTAL_ANDROID__||globalThis.__PORTAL_IOS__)try{globalThis.PortalNative?.scheduleOrganizerReminders?.('[]');}catch{}return;}organizerReminderCheck();S.organizerReminderTimer=setInterval(organizerReminderCheck,60000);}
