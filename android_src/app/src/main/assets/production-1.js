'use strict';
// Progressive activation: companies without the explicit migration keep Stage 2.
const LOCAL_SYNC_INTERVAL_MS=10*60*1000;
let localSyncBusy=false;
function applyProductionMeta(r){
  S.stage3=!!r.ready;
  if(!S.stage3)return;
  S.me.permissions=Array.isArray(r.permissions)?r.permissions:[];
  S.permissionCatalog=Array.isArray(r.catalog)?r.catalog:[];
  S.heartbeatSeconds=r.heartbeat_seconds||60;
  if(r.company&&S.company&&Number(r.company.id)===Number(S.company.id)){
    S.company={...S.company,...r.company};
    updateHeader();
    if(typeof buildNav==='function')buildNav();
  }
}
async function configureProduction(){
  const r=await api('GET','/api/v3/meta',undefined,{global:true});
  applyProductionMeta(r);
  if(S.stage3){clearInterval(S.heartbeatTimer);S.heartbeatTimer=setInterval(()=>{if(S.token&&!document.hidden)api('POST','/api/v3/heartbeat',{}, {global:true}).catch(()=>{});},S.heartbeatSeconds*1000);startOrganizerReminderWatch();startLocalSyncWatch();}
}
const allowed=permission=>S.me?.permissions?.includes(permission);
const rub=cents=>money(Number(cents||0)/100);
const utc=value=>value?new Date(value).toISOString().slice(0,-1):null;
const productionGet=async path=>(await api('GET','/api/v3/'+path)).data;
const LOCAL_OUTBOX_PATHS=new Set(['work','links','batches','tasks','shipments','returns']);
function canUseLocalOutbox(){return !isOwner()&&S.company&&typeof window.PortalNative?.queueMutation==='function'&&typeof window.PortalNative?.pendingMutations==='function'&&typeof window.PortalNative?.removeMutation==='function';}
function canQueueLocalMutation(path){return LOCAL_OUTBOX_PATHS.has(path);}
async function nativeOutboxCall(name,...args){try{return await Promise.resolve(PortalNative[name](...args));}catch{return null;}}
async function refreshLocalPendingCount(){
  if(!canUseLocalOutbox()){S.localPendingCount=0;return 0;}
  const value=Number(await nativeOutboxCall('pendingMutationCount')||0);S.localPendingCount=Number.isFinite(value)?value:0;return S.localPendingCount;
}
async function queueLocalMutation(path,body,requestId){
  if(!canUseLocalOutbox()||!canQueueLocalMutation(path))return false;
  const row={v:1,method:'POST',path:'/api/v3/'+path,request_id:requestId,queued_at:new Date().toISOString(),body};
  const stored=!!(await nativeOutboxCall('queueMutation',JSON.stringify(row)));if(stored)await refreshLocalPendingCount();return stored;
}
async function syncLocalOutbox(){
  if(localSyncBusy||!S.token||isOwner()||!S.company||navigator.onLine===false)return;
  localSyncBusy=true;
  let queueError='';
  try{
    if(canUseLocalOutbox()){
      let raw=[];try{raw=JSON.parse(String(await nativeOutboxCall('pendingMutations')||'[]'));}catch{raw=[];}
      if(Array.isArray(raw)){
        for(const value of raw){
          let row=value;try{if(typeof row==='string')row=JSON.parse(row);}catch{continue;}
          const action=typeof row?.path==='string'&&row.path.startsWith('/api/v3/')?row.path.slice(8):'';
          if(!row||row.method!=='POST'||!canQueueLocalMutation(action)||!row.body||row.body.request_id!==row.request_id)continue;
          try{
            await api('POST',row.path,row.body,{global:true});
            await nativeOutboxCall('removeMutation',String(row.request_id));
            await refreshLocalPendingCount();
          }catch(error){
            if(error?.network){queueError='Нет соединения с сервером';break;}
            queueError=error?.message||'Одна из локальных записей требует проверки';
            continue;
          }
        }
      }
    }
    try{
      const meta=await api('GET','/api/v3/meta',undefined,{global:true});
      applyProductionMeta(meta);
      S.lastLocalSync=Date.now();
      S.localSyncError=queueError;
    }catch(error){
      S.localSyncError=queueError||(!error?.network?(error?.message||'Не удалось получить обновления с сервера'):'Нет соединения с сервером');
    }
  }finally{await refreshLocalPendingCount();localSyncBusy=false;}
}
function startLocalSyncWatch(){
  clearInterval(S.localSyncTimer);
  if(isOwner()||!S.company)return;
  S.localSyncTimer=setInterval(()=>{if(!document.hidden)void syncLocalOutbox();},LOCAL_SYNC_INTERVAL_MS);
  setTimeout(()=>{void refreshLocalPendingCount();void syncLocalOutbox();},1200);
  if(!globalThis.__portalLocalSyncOnline){globalThis.__portalLocalSyncOnline=true;addEventListener('online',()=>void syncLocalOutbox());}
}
async function productionPost(path,body,form){
  const requestId=form?(form.dataset.requestId||(form.dataset.requestId=crypto.randomUUID())):crypto.randomUUID();
  const payload={...body,request_id:requestId};
  const journaled=canQueueLocalMutation(path)&&await queueLocalMutation(path,payload,requestId);
  try{
    const result=(await api('POST','/api/v3/'+path,payload)).data;
    if(journaled){await nativeOutboxCall('removeMutation',String(requestId));await refreshLocalPendingCount();}
    return result;
  }catch(error){
    if(error?.network&&journaled)return {queued:true,request_id:requestId,path};
    if(journaled){await nativeOutboxCall('removeMutation',String(requestId));await refreshLocalPendingCount();}
    throw error;
  }
}
const options=(items,label='name')=>items.map(i=>`<option value="${esc(i.id)}">${esc(i[label])}</option>`).join('');
async function productionCatalog(){return S.productionCatalog=await productionGet('catalog');}
const previous={dashboard:screens.dashboard,work:screens.work,jobs:screens.jobs,invoices:screens.invoices,settings:screens.settings,users:screens.users,openClient:actions.openClient};
const activeTimer=task=>S.activeTimers?.find(t=>t.task_id===task.id&&t.user_id===S.me.id);
const taskCards=tasks=>tasks.filter(t=>t.remaining>0).map(t=>{const timer=S.activeTimers?.find(x=>x.task_id===t.id),own=activeTimer(t);return `<article class="item task-card"><span class="eyebrow">${esc(t.client_name||'')}</span><h3>${esc(t.product)}</h3><p class="meta batch-number">${esc(t.batch_number)}</p><b>${esc(t.operation_name)}</b><p>Нужно ${num(t.quantity)} · Сделано ${num(t.done)} · Осталось <strong>${num(t.remaining)}</strong></p>${timer?`<div class="timer-summary"><b>${timer.status==='running'?'В работе':'На паузе'} с ${esc(timeOfDay(timer.started_at))}</b><span class="meta">Накоплено <span data-timer-elapsed="${esc(timer.id)}">${esc(durationLabel(timerElapsed(timer)))}</span></span></div>`:''}${allowed('work.write')&&t.assignees.includes(S.me.id)?btn(own?'Открыть работу':'Начать','taskWork',`data-id="${esc(t.id)}"`):''}</article>`;}).join('')||'<p class="empty">Текущих заданий нет. Можно начать другую работу.</p>';
function portalDate(value){return new Date(typeof value==='string'&&!/(Z|[+-]\d\d:\d\d)$/i.test(value)?value+'Z':value);}
function timeOfDay(value){return value?portalDate(value).toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'}):'—';}
function durationLabel(seconds){const total=Math.max(0,Math.floor(seconds||0)),h=Math.floor(total/3600),m=Math.floor(total%3600/60),s=total%60;return h?`${h} ч ${String(m).padStart(2,'0')} мин`:`${m} мин ${String(s).padStart(2,'0')} с`;}
function timerElapsed(timer,now=Date.now()){
  const start=portalDate(timer.started_at).getTime();if(!Number.isFinite(start))return 0;
  const end=timer.status==='running'?now:portalDate(timer.pauses?.at(-1)?.start).getTime()||now;
  let elapsed=Math.max(0,(end-start)/1000);
  for(const pause of timer.pauses||[]){const a=portalDate(pause.start).getTime(),b=pause.end?portalDate(pause.end).getTime():timer.status==='running'?now:NaN;if(Number.isFinite(a)&&Number.isFinite(b))elapsed-=Math.max(0,(b-a)/1000);}
  return Math.max(0,elapsed);
}
function tickElapsed(){clearInterval(S.timerTicker);S.timerTicker=setInterval(()=>{for(const el of document.querySelectorAll('[data-timer-elapsed]')){const id=el.dataset.timerElapsed,timer=S.activeTimers?.find(x=>x.id===id)||(S.currentTimer?.id===id?S.currentTimer:null);if(timer)el.textContent=durationLabel(timerElapsed(timer));}const current=$('timerElapsed');if(current&&S.currentTimer)current.textContent=durationLabel(timerElapsed(S.currentTimer));},1000);}
const statusLabel={received:'Принята',in_progress:'В работе',ready:'Готова',shipped:'Отгружена',partially_returned:'Частично возвращена',returned:'Возвращена'};
function taskStatusLabel(task){return task.status==='done'?'Завершено':task.status==='in_progress'?'В работе':'Ожидает начала';}
screens.dashboard=async()=>{
  if(!S.stage3)return previous.dashboard();
  const [d,organizerRows,organizerRequestIncoming,organizerRequestMine,timers]=await Promise.all([
    productionGet('today'),
    can('organizer')?productionGet('organizer?scope=incoming'):Promise.resolve([]),
    can('organizer')&&allowed('organizer.request.decide')?productionGet('organizer-requests?scope=incoming'):Promise.resolve([]),
    canCreateDirectorRequest()?productionGet('organizer-requests?scope=mine'):Promise.resolve([]),
    allowed('work.write')||allowed('tasks.read')?productionGet('timers'):Promise.resolve([])
  ]);
  S.productionTasks=d.tasks||[];S.activeTimers=timers;
  const management=d.mode==='management';
  const inWorkTasks=new Set([...S.productionTasks.filter(t=>t.status==='in_progress').map(t=>t.id),...S.activeTimers.map(t=>t.task_id)]);
  const taskMetrics=allowed('tasks.read')?metric('Задания в работе',num(inWorkTasks.size)):'';
  const attention=d.attention||[];
  const workerActions=allowed('work.write')?`${btn(icon('plus')+' Начать работу','go','data-page="work"','block')}${btn('Другая работа','otherWork','','secondary block')}`:'';
  paint(heading(management?'PORTAL Сегодня':'Мой рабочий день',date(d.date),btn('Меню','go','data-page="sections"','secondary'))+
    (management?`<div class="metrics">${d.today_quantity!==undefined?metric('Работа сегодня',num(d.today_quantity)+' шт.'):''}${d.month_quantity!==undefined?metric('Работа за месяц',num(d.month_quantity)+' шт.'):''}${taskMetrics}${d.ready!==undefined?metric('Готовые партии',num(d.ready)):''}${d.active_batches!==undefined?metric('Активные партии',num(d.active_batches)):''}${d.active_jobs!==undefined?metric('Открытые задания',num(d.active_jobs)):''}${d.today_productivity?metric('Скорость команды',d.today_productivity.units_per_hour==null?'Нет данных времени':num(d.today_productivity.units_per_hour)+' шт./ч'):''}</div>${d.today_finance?`<div class="metrics">${metric('Выручка сегодня',rub(d.today_finance.revenue))}${metric('Начислено сегодня',rub(d.today_finance.salary))}</div><div class="metrics">${metric('Выручка за месяц',rub(d.month_finance.revenue))}${metric('Начислено за месяц',rub(d.month_finance.salary))}${d.expected_profit!==undefined?metric('Плановая прибыль',d.expected_profit==null?'Недоступна':rub(d.expected_profit)):''}</div>`:''}${(allowed('payroll.settlement.read')||allowed('payroll.all'))&&d.closed_month_payroll!==undefined?metric('Закрытый ФОТ',d.closed_month_payroll==null?'Нет закрытого периода':`Начислено ${rub(d.closed_month_payroll.accrued)} · Выплачено ${rub(d.closed_month_payroll.paid)} · Остаток ${rub(d.closed_month_payroll.balance)}`):''}${d.debt!==undefined?metric('Дебиторская задолженность',rub(d.debt)):''}${d.open_invoice_count!==undefined?metric('Открытые счета',num(d.open_invoice_count)):''}${d.overdue_invoice_count?metric('Просроченные счета',num(d.overdue_invoice_count)+' · '+rub(d.overdue_debt)):''}${d.client_profitability_alerts?metric('Клиенты с отрицательной прибылью',num(d.client_profitability_alerts)):''}`:
      `<div class="hero"><span>Моя выработка сегодня</span><div class="hero-value">${num(d.own_quantity)} шт.</div>${d.own_salary!==undefined?`<strong>Заработано ${rub(d.own_salary)}</strong>`:''}</div>${workerActions}`)+
    (attention.length?`<section class="attention-section"><h2>Требует внимания</h2><div class="list attention">${attention.map(a=>`<div class="notice warning"><b>${esc(a.label)}</b>${a.number?`<p class="batch-number">${esc(a.number)}</p>`:''}${a.name?`<p>${esc(a.name)} · ${num(a.quantity)}</p>`:''}${a.amount!==undefined?`<p>${rub(a.amount)}</p>`:''}${a.type==='not_invoiced'&&allowed('invoices.create')?btn('Подготовить счёт','go','data-page="invoices"','secondary'):''}</div>`).join('')}</div></section>`:'')+
    `${!management&&S.productionTasks.length?`<h2 class="compact-heading">Мои задания</h2><div class="list">${taskCards(S.productionTasks)}</div>`:''}${management&&allowed('tasks.read')?`<h2 class="compact-heading">Задания в работе</h2><div class="list">${taskCards(S.productionTasks.filter(t=>t.status==='in_progress'||S.activeTimers.some(timer=>timer.task_id===t.id)))}</div>`:''}`);
  if(organizerRows.length){const active=organizerRows.filter(t=>organizerActive(t)),late=active.filter(t=>new Date(t.due_at)<new Date());const box=document.createElement('section');box.className='card';box.innerHTML='<div class="row between"><div><span class="eyebrow">Органайзер</span><h2>Мои задачи</h2></div>'+btn('Открыть органайзер','go','data-page="organizer"','secondary')+'</div><p>'+active.length+' активных задач'+(late.length?' · <b>'+late.length+' просрочено</b>':'')+'</p>'+(active[0]?'<p class="meta">Ближайшая: '+esc(active[0].title)+' · '+esc(organizerMoment(active[0].due_at))+'</p>':'');$('content').querySelector('.page-heading')?.after(box);}
  if(organizerRequestIncoming.length||organizerRequestMine.length){const directorAttention=organizerRequestIncoming.filter(r=>['new','review'].includes(r.status)).length,authorAttention=organizerRequestMine.filter(r=>r.status==='needs_info').length;const box=document.createElement('section');box.className='card';box.innerHTML='<div class="row between"><div><span class="eyebrow">Органайзер</span><h2>Запросы директору</h2></div>'+btn('Открыть органайзер','go','data-page="organizer"','secondary')+'</div>'+(directorAttention?'<p><b>'+directorAttention+'</b> запросов требуют решения директора</p>':'')+(authorAttention?'<p><b>'+authorAttention+'</b> запросов ждут уточнения от вас</p>':'')+(!directorAttention&&!authorAttention?'<p class="meta">Активные запросы доступны в Органайзере</p>':'');$('content').querySelector('.page-heading')?.after(box);}
  tickElapsed();
};
screens.work=async()=>{
  if(!S.stage3)return previous.work();
  [S.productionTasks,S.activeTimers]=await Promise.all([allowed('tasks.read')?productionGet('tasks'):Promise.resolve([]),productionGet('timers')]);
  paint(heading('Мои задания','Клиент → товар и партия → операция')+`<div class="list">${taskCards(S.productionTasks)}</div>${allowed('work.write')?btn('Другая работа','otherWork','','secondary block'):''}${allowed('work.write')||allowed('payroll.own')?btn('История выработки','productionHistory','','text block'):''}`);tickElapsed();
};
screens.jobs=async()=>S.stage3?screens.work():previous.jobs();
function activityTime(value){if(!value)return null;const d=portalDate(value),today=new Date();if(d.toDateString()===today.toDateString())return 'сегодня в '+timeOfDay(value);return d.toLocaleString('ru-RU',{day:'numeric',month:'long',hour:'2-digit',minute:'2-digit'});}
screens.users=async()=>{
  if(!S.stage3)return previous.users();
  permission('users');
  const [r,p,invites,access]=await Promise.all([api('GET','/api/users'),productionGet('presence'),productionGet('invitations?status=all&page=1&limit=50'),productionGet('company-access')]);S.userData=r;S.accessInvites=invites.items;
  const presence=new Map(p.map(x=>[x.user_id,x]));
  paint(heading('Сотрудники',`Доступ и активность · ${num(access.active_users)} активных / ${access.unlimited?'без лимита':num(access.user_limit)+' максимум'}`,btn('Добавить сотрудника','editUser','','secondary'))+`<div class="list">${r.users.map(u=>{const state=presence.get(u.id),last=activityTime(state?.last_activity_at);return `<article class="item employee-card"><div class="row"><div class="grow"><b><span class="presence-dot ${state?.online?'online':'offline'}" aria-label="${state?.online?'Online':'Offline'}"></span>${esc(u.display_name)}</b><div class="meta">${esc(r.roles[u.role]||u.role)} · ${esc(u.username)}</div><div class="meta">${state?.online?'В сети':last?'Не в сети · Был в PORTAL '+esc(last):'Не в сети · Активность пока не записана'}</div></div><span class="badge ${u.active?'green':''}">${u.active?'Активен':'Отключён'}</span></div><div class="item-actions">${btn('Активность в системе','employeeActivity',`data-id="${u.id}"`,'text')}${btn('Изменить доступ','editUser',`data-id="${u.id}"`,'secondary')}</div></article>`;}).join('')}</div><h2>Дополнительный способ: приглашения</h2>${btn('Создать приглашение','createAccessInvite','','text block')}<div class="list">${invites.items.map(i=>`<article class="item"><b>${esc(i.display_name)} · ${esc(r.roles[i.role]||i.role)}</b><p class="meta">${esc(i.username)} · ${esc(i.status)} · истекает ${esc(i.expires_at)}</p>${i.status==='accepted'?btn('Подтвердить доступ','decideAccessInvite',`data-id="${esc(i.id)}" data-decision="approve"`,'secondary'):''}${['pending','accepted'].includes(i.status)?btn('Отозвать','decideAccessInvite',`data-id="${esc(i.id)}" data-decision="revoke"`,'text'):''}</article>`).join('')||'<p class="empty">Активных приглашений и запросов нет</p>'}</div>${btn('Административный аудит','companyAudit','','secondary block')}${allowed('access.history.read')?btn('История входов сотрудников','loginHistory','','secondary block'):''}`);
};
actions.companyAudit=async()=>{const data=await productionGet('audit?page=1&limit=50');S.auditPage=1;S.auditFilter={};showCompanyAudit(data);};
function showCompanyAudit(data){const rows=data.items.map(row=>`<article class="item"><b>${esc(row.summary)}</b><p class="meta">${esc(row.actor_name)} · ${esc(row.at)} · ${esc(row.action)} · запись ${esc(row.entity_id)}</p></article>`).join('')||'<p class="empty">По выбранным фильтрам записей нет</p>';openSheet('Аудит компании',`<form id="auditFilterForm">${field('auditActor','ID пользователя',S.auditFilter?.actor_id||'','number','min="1" step="1"')}${field('auditAction','Код действия',S.auditFilter?.action||'','text','maxlength="80"')}${field('auditEntity','ID записи',S.auditFilter?.entity_id||'','text','maxlength="100"')}${field('auditFrom','С даты',S.auditFilter?.from||'','date')}${field('auditTo','По дату',S.auditFilter?.to||'','date')}<button class="btn block" type="submit">Применить фильтры</button></form><p class="meta">Страница ${num(data.page)} · Всего ${num(data.total)}. Секреты и содержимое запросов в сводке не показываются.</p><div class="list">${rows}</div>${data.page>1?btn('Предыдущая','auditPage','data-step="-1"','secondary'):''}${data.page*data.limit<data.total?btn('Следующая','auditPage','data-step="1"','secondary'):''}`);}
forms.auditFilterForm=async form=>{S.auditFilter={actor_id:$('auditActor').value,action:$('auditAction').value,entity_id:$('auditEntity').value,from:$('auditFrom').value,to:$('auditTo').value};S.auditPage=1;await loadCompanyAudit();};
actions.auditPage=async button=>{S.auditPage=Math.max(1,S.auditPage+Number(button.dataset.step));await loadCompanyAudit();};
async function loadCompanyAudit(){const q=new URLSearchParams({page:String(S.auditPage),limit:'50',...Object.fromEntries(Object.entries(S.auditFilter||{}).filter(([,v])=>v))});showCompanyAudit(await productionGet('audit?'+q));}
actions.createAccessInvite=()=>openSheet('Приглашение сотрудника',`<p class="meta">Одноразовый код действует 7 дней. PIN задаёт сам сотрудник при принятии.</p><form id="accessInviteForm">${field('inviteName','Имя сотрудника','','text','required maxlength="100"')}${field('inviteUsername','Логин','','text','required maxlength="100" autocapitalize="none"')}<label class="field"><span>Карточка сотрудника</span><select id="inviteEmployee"><option value="">Создать новую карточку</option>${(S.userData.employees||[]).map(e=>`<option value="${e.employee_id}">${esc(e.full_name)} · ${e.employee_id}</option>`).join('')}</select></label>${selectField('inviteRole','Роль','<option value="packer">Упаковщик</option><option value="loader">Грузчик</option><option value="driver">Водитель</option><option value="shift">Старший смены</option><option value="manager">Менеджер</option><option value="accountant">Бухгалтер</option>')}<button class="btn block" type="submit">Создать одноразовый код</button></form>`);
forms.accessInviteForm=async form=>{const selected=$('inviteEmployee').value;const result=await productionPost('invitations',{action:'create',role:$('inviteRole').value,username:$('inviteUsername').value,display_name:$('inviteName').value,employee_id:selected?Number(selected):null},form);closeSheet();if(result.token){openSheet('Передайте код сотруднику',`<p class="meta">Код показывается один раз. Не отправляйте вместе с ним пароль или PIN.</p><label class="field"><span>Одноразовый код</span><textarea id="oneTimeInviteToken" readonly rows="3">${esc(result.token)}</textarea></label>${btn('Скопировать код','copyAccessInvite','','secondary block')}${typeof navigator.share==='function'?btn('Поделиться…','shareAccessInvite','','secondary block'):''}`);}else{toast('Приглашение уже создано; одноразовый код повторно не показывается');await go('users');}};
actions.copyAccessInvite=async()=>{const value=$('oneTimeInviteToken')?.value;if(!value)return;try{await navigator.clipboard.writeText(value);toast('Код скопирован');}catch{const input=$('oneTimeInviteToken');input?.focus();input?.select();toast('Выделите код и скопируйте его');}};
actions.shareAccessInvite=async()=>{const value=$('oneTimeInviteToken')?.value;if(!value)return;if(typeof navigator.share!=='function'){await actions.copyAccessInvite();return;}try{await navigator.share({title:'Приглашение в PORTAL',text:value});}catch(error){if(error?.name==='AbortError')return;await actions.copyAccessInvite();}};
actions.decideAccessInvite=async button=>{await productionPost('invitations',{action:button.dataset.decision,invite_id:button.dataset.id});toast(button.dataset.decision==='approve'?'Доступ подтверждён':'Приглашение отозвано');await go('users');};
actions.openClient=async button=>{
  if(!S.stage3)return previous.openClient(button);
  const id=Number(button.dataset.id),base=await api('GET',`/api/clients/${id}`),c=base.client;
  const allowedQueries=[];
  if(allowed('work.write')||allowed('payroll.own')||allowed('finance.read')||allowed('invoices.create'))allowedQueries.push(['works',()=>productionGet('works')]);
  if(allowed('tasks.read')||allowed('batches.receive')||allowed('work.write'))allowedQueries.push(['batches',()=>productionGet('batches')]);
  if(allowed('batches.receive'))allowedQueries.push(['shipments',()=>productionGet('shipments')]);
  if(allowed('tasks.read'))allowedQueries.push(['tasks',()=>productionGet('tasks')]);
  if(allowed('invoices.read'))allowedQueries.push(['invoices',()=>productionGet('invoices')]);
  if(allowed('documents.read'))allowedQueries.push(['documents',()=>productionGet('documents')]);
  if(allowed('finance.read'))allowedQueries.push(['finance',()=>productionGet('finance')]);
  if(allowed('clients.read')||allowed('clients.manage'))allowedQueries.push(['products',()=>productionGet('products')]);
  if(allowed('clients.read')||allowed('clients.manage'))allowedQueries.push(['requisites',()=>productionGet('client-requisites?client_id='+encodeURIComponent(id))]);
  if(allowed('clients.read'))allowedQueries.push(['nameHistory',()=>productionGet('client-name-history?client_id='+encodeURIComponent(id))]);
  const values=await Promise.all(allowedQueries.map(([,load])=>load().catch(()=>null))),data=Object.fromEntries(allowedQueries.map(([key],index)=>[key,values[index]]));
  const sectionLabels={works:'Выработка',batches:'Партии',shipments:'Отгрузки и возвраты',tasks:'Задания',invoices:'Счета',documents:'Документы',finance:'Экономика',products:'Товары',requisites:'Реквизиты',nameHistory:'История названий'};
  const failedSections=allowedQueries.filter((entry,index)=>values[index]===null).map(([key])=>sectionLabels[key]||key);
  const partialDataNotice=failedSections.length?`<p class="meta" role="status">Карточка загружена частично. Не удалось загрузить: ${failedSections.map(esc).join(', ')}. Проверьте подключение и откройте карточку повторно.</p>`:'';
  const works=(data.works||[]).filter(w=>w.client_id===id),batches=(data.batches||[]).filter(b=>b.client_id===id),clientBatchIds=new Set(batches.map(b=>String(b.id))),tasks=(data.tasks||[]).filter(t=>clientBatchIds.has(String(t.batch_id))),shipments=(data.shipments||[]).filter(s=>s.client_id===id&&clientBatchIds.has(String(s.batch_id))),invoices=(data.invoices||[]).filter(i=>i.client_id===id),docs=(data.documents||[]).filter(d=>d.client_id===id),economy=(data.finance?.clients||[]).find(x=>x.client_id===id),ops=(S.productionCatalog||await productionCatalog()).operations.filter(o=>o.client_id===id);
  const tariffHistory=new Map(await Promise.all((['rates.employee','rates.client','finance.read','payroll.own'].some(allowed)?ops:[]).map(async o=>[o.id,await productionGet('tariff-history?operation_id='+encodeURIComponent(o.id)).catch(()=>[])])));
  const tariffTime=value=>{const raw=String(value||'');return Date.parse(/(?:Z|[+-]\d{2}:\d{2})$/i.test(raw)?raw:raw+'Z');};
  const requisites=data.requisites||base.requisites||{};S.client360Id=id;S.client360Requisites=requisites;
  const products=(data.products||[]).filter(p=>p.client_id===id);
  const outstanding=invoices.reduce((sum,i)=>sum+Number(i.remaining||0),0);
  const names=data.nameHistory||[],canManageOperations=can('catalogue'),canManageTariffs=allowed('rates.employee')||allowed('rates.client');
  openSheet(c.name,`${partialDataNotice}<div class="row between"><span class="badge ${c.active?'green':''}">${c.active?'Активен':'Архив'}</span>${can('catalogue')?btn('Изменить карточку','editClient',`data-id="${id}"`,'secondary'):''}</div>${names.length?`<h3>История названий</h3><div class="list">${names.slice().reverse().map(row=>`<div class="item"><b>${esc(row.old_name)} → ${esc(row.new_name)}</b><p class="meta">${esc(date(row.occurred_at))}</p></div>`).join('')}</div>`:''}<h3>Реквизиты и контакты</h3><p>${esc(requisites.legal_name||'Не заполнены')}</p><p class="meta">ИНН ${esc(requisites.inn||'—')} · КПП ${esc(requisites.kpp||'—')} · ОГРН ${esc(requisites.ogrn||'—')}<br>${esc(requisites.contact_person||'')} · ${esc(requisites.phone||'')} · ${esc(requisites.email||'')}<br>${esc(requisites.legal_address||'')}<br>${requisites.bank_name?esc(requisites.bank_name)+' · ':''}${esc(requisites.bik||'')} · ${esc(requisites.settlement_account||'')} · ${esc(requisites.correspondent_account||'')}</p>${allowed('clients.manage')?btn('Изменить реквизиты','editClientRequisites','','secondary block'):''}${ops.length||canManageOperations?`<h3>Операции и действующие тарифы</h3><div class="list">${ops.map(o=>{const versions=tariffHistory.get(o.id)||[],active=versions.find(v=>tariffTime(v.effective_from)<=Date.now());return `<div class="item"><b>${esc(o.name)}</b><p class="meta">${o.employee_rate===undefined?'':'Сотруднику '+rub(o.employee_rate)} ${o.client_rate===undefined?'':'· Клиенту '+rub(o.client_rate)}</p>${versions.length?`<details><summary>История ставок · ${versions.length}</summary><div class="list">${versions.map(v=>`<div class="item"><b>${tariffTime(v.effective_from)<=Date.now()?(v===active?'Действует сейчас':'Историческая версия'):'Будущая версия'}</b><p class="meta">С ${esc(date(v.effective_from))}</p><p>${v.employee_rate===undefined?'':'Сотруднику '+rub(v.employee_rate)} ${v.client_rate===undefined?'':'· Клиенту '+rub(v.client_rate)}</p></div>`).join('')}</div><p class="meta">Новая ставка не пересчитывает ранее выполненную работу.</p></details>`:''}${canManageTariffs?btn('Новая ставка','newTariff',`data-id="${o.id}" data-return-to-client="true"`,'secondary'):''}</div>`;}).join('')||'<p class="empty">Операций пока нет</p>'}</div>${canManageOperations?btn('Управлять операциями','clientOperations',`data-id="${id}"`,'secondary block'):''}`:''}<h3>Каталог товаров</h3>${products.length?`<div class="list">${products.map(p=>`<div class="item"><b>${esc(p.name)}</b><p class="meta">${p.sku?`Артикул ${esc(p.sku)}`:''}${p.barcode?` · Штрихкод ${esc(p.barcode)}`:''}</p></div>`).join('')}</div>`:'<p class="empty">Активных товаров пока нет</p>'}${allowed('clients.manage')?btn('Управлять товарами','manageClientProducts',`data-id="${id}"`,'secondary block'):''}${batches.length?`<h3>Текущие партии и работа</h3><div class="list">${batches.map(b=>`<div class="item"><b>${esc(b.product)} · ${esc(b.number)}</b><p>${num(b.done)} / ${num(b.quantity)} · ${esc(statusLabel[b.stage]||b.stage)}</p>${allowed('finance.read')?btn('Экономика партии','batchEconomy',`data-id="${esc(b.id)}"`,'text'):''}</div>`).join('')}</div>`:''}${shipments.length?`<h3>Отгрузки и возвраты</h3><div class="list">${shipments.slice().reverse().map(s=>`<div class="item"><b>${s.type==='return'?'Возврат':'Отгрузка'} · ${esc(s.direction||'')}</b><p>${num(s.quantity)} шт.${s.type==='return'&&s.condition?` · ${esc(s.condition==='resalable'?'Годный':s.condition==='damaged'?'Повреждённый':'Состояние не указано')}`:''}</p></div>`).join('')}</div>`:''}${tasks.length?`<h3>Задания по партиям клиента</h3><div class="list">${tasks.slice(-5).reverse().map(t=>`<div class="item"><b>${esc(t.operation_name||'Операция')} · ${esc(t.batch_number||'')}</b><p>${num(t.done)} / ${num(t.quantity)} · осталось ${num(t.remaining)}</p></div>`).join('')}</div>`:''}${docs.length?`<h3>Документы</h3><p>${num(docs.length)} документа в общей папке компании</p>${btn('Открыть документы клиента','openClientDocuments','','secondary')}`:''}${invoices.length?`<h3>Счета и дебиторка</h3><p>${num(invoices.length)} счетов · открытый остаток ${rub(outstanding)}</p>${allowed('invoices.read')?btn('Открыть дебиторку клиента','openClientReceivables',`data-id="${id}"`,'secondary'):''}`:''}${economy?`<h3>Экономика по подтверждённым данным</h3><p>Выручка ${rub(economy.revenue)} · зарплата ${rub(economy.salary)} · материалы ${rub(economy.materials)} · прямые расходы ${rub(economy.other)}</p><p>Прибыль ${rub(economy.profit)} · маржа ${economy.margin_bps==null?(economy.margin==null?'недоступна':num(economy.margin*100)+'%'):num(economy.margin_bps/100)+'%'}</p>`:'<p class="meta">Сводка экономики недоступна по текущим правам или источникам.</p>'}${works.length?`<h3>Последние работы</h3><div class="list">${works.slice(-5).reverse().map(w=>`<div class="item"><b>${esc(w.operation_name)}</b><p>${num(w.quantity)} шт. · ${esc(date(w.completed_at))}</p></div>`).join('')}</div>`:''}${can('work')&&c.active?btn('Записать работу','clientWork',`data-id="${id}"`,'block'):''}`);
};
actions.clientOperations=button=>{if(!can('catalogue'))throw new Error('Нет права управлять операциями клиента');const id=Number(button?.dataset?.id||S.client360Id);if(!Number.isSafeInteger(id)||id<1)throw new Error('Некорректный клиент');closeSheet();return actions.operations({dataset:{id:String(id)}});};
actions.editClientRequisites=()=>{
  if(!allowed('clients.manage'))throw new Error('Нет права изменять реквизиты клиента');
  const r=S.client360Requisites||{},input=(id,label,key)=>field(id,label,r[key]||'','text','maxlength="500"');
  openSheet('Реквизиты и контакты',`<form id="clientRequisitesForm">${input('clientReqLegalName','Юридическое наименование','legal_name')}${input('clientReqInn','ИНН','inn')}${input('clientReqKpp','КПП','kpp')}${input('clientReqOgrn','ОГРН','ogrn')}<label class="field"><span>Юридический адрес</span><textarea id="clientReqAddress" maxlength="500">${esc(r.legal_address||'')}</textarea></label>${input('clientReqBank','Банк','bank_name')}${input('clientReqBik','БИК','bik')}${input('clientReqAccount','Расчётный счёт','settlement_account')}${input('clientReqCorrespondent','Корреспондентский счёт','correspondent_account')}${input('clientReqContact','Контактное лицо','contact_person')}${input('clientReqPhone','Телефон','phone')}${input('clientReqEmail','Email','email')}<label class="field"><span>Дополнительная налоговая информация</span><textarea id="clientReqTaxInfo" maxlength="500">${esc(r.tax_info||'')}</textarea></label><button class="btn block" type="submit">Сохранить реквизиты</button></form><p class="meta">Изменения записываются в журнал без сохранения банковских данных в тексте события.</p>`);
};
actions.changePin=()=>openSheet('\u0421\u043c\u0435\u043d\u0430 PIN',`<form id="changePinForm">${field('currentPin','\u0422\u0435\u043a\u0443\u0449\u0438\u0439 PIN','','password','required minlength="4" maxlength="128" autocomplete="current-password"')}${field('newPin','\u041d\u043e\u0432\u044b\u0439 PIN','','password','required minlength="4" maxlength="128" autocomplete="new-password"')}${field('confirmPin','\u041f\u043e\u0432\u0442\u043e\u0440\u0438\u0442\u0435 \u043d\u043e\u0432\u044b\u0439 PIN','','password','required minlength="4" maxlength="128" autocomplete="new-password"')}<button class="btn block" type="submit">\u0421\u043c\u0435\u043d\u0438\u0442\u044c PIN</button></form>`);
forms.changePinForm=async()=>{const current_pin=$('currentPin').value,new_pin=$('newPin').value,confirmation=$('confirmPin').value;if(new_pin!==confirmation)throw new Error('\u041d\u043e\u0432\u044b\u0435 PIN \u043d\u0435 \u0441\u043e\u0432\u043f\u0430\u0434\u0430\u044e\u0442');if(new_pin===current_pin)throw new Error('\u041d\u043e\u0432\u044b\u0439 PIN \u0434\u043e\u043b\u0436\u0435\u043d \u043e\u0442\u043b\u0438\u0447\u0430\u0442\u044c\u0441\u044f');if(new_pin.length<4||new_pin.length>128)throw new Error('PIN: 4\u2013128 \u0441\u0438\u043c\u0432\u043e\u043b\u043e\u0432');await api('POST','/api/me/pin',{current_pin,new_pin});closeSheet();toast('\u0421\u0435\u0430\u043d\u0441 \u0441\u043e\u0445\u0440\u0430\u043d\u0451\u043d');};
actions.openClientDocuments=async()=>{
  if(!allowed('documents.read')||(!allowed('clients.read')&&!allowed('clients.manage')))throw new Error('Нет права просматривать документы клиента');
  if(!S.client360Id||typeof window.PortalDocuments?.openForClient!=='function')throw new Error('Документы клиента пока недоступны');
  return window.PortalDocuments.openForClient(S.client360Id);
};
actions.openClientReceivables=async button=>{
  if(!allowed('invoices.read'))throw new Error('Недостаточно прав для просмотра дебиторки');
  const id=Number(button?.dataset?.id||S.client360Id);
  if(!Number.isSafeInteger(id)||id<1)throw new Error('Некорректный клиент');
  S.receivablesClient=String(id);S.receivablesPage=1;S.receivablesBucket='';closeSheet();
  return actions.viewReceivables();
};
forms.clientRequisitesForm=async form=>{
  const body={client_id:S.client360Id,legal_name:$('clientReqLegalName').value,inn:$('clientReqInn').value,kpp:$('clientReqKpp').value,ogrn:$('clientReqOgrn').value,legal_address:$('clientReqAddress').value,bank_name:$('clientReqBank').value,bik:$('clientReqBik').value,settlement_account:$('clientReqAccount').value,correspondent_account:$('clientReqCorrespondent').value,contact_person:$('clientReqContact').value,phone:$('clientReqPhone').value,email:$('clientReqEmail').value,tax_info:$('clientReqTaxInfo').value};
  S.client360Requisites=await productionPost('client-requisites',body,form);closeSheet();toast('Реквизиты клиента сохранены');await actions.openClient({dataset:{id:String(S.client360Id)}});
};
actions.manageClientProducts=async button=>{S.productClientId=Number(button.dataset.id);const products=(await productionGet('products')).filter(p=>p.client_id===S.productClientId&&p.active);openSheet('Товары клиента',`${field('productSearch','Поиск по названию','','search','maxlength="200"')}<div class="list" id="clientProductRows">${products.map(p=>`<article class="item" data-product-name="${esc(p.name.toLocaleLowerCase())}"><b>${esc(p.name)}</b><div class="row">${btn('Изменить','editCatalogProduct',`data-id="${esc(p.id)}"`,'secondary')}${btn('Архивировать','archiveCatalogProduct',`data-id="${esc(p.id)}"`,'text')}</div></article>`).join('')||'<p class="empty">Активных товаров пока нет</p>'}</div>${btn('Добавить товар','newCatalogProduct','','block')}`);$('productSearch').addEventListener('input',()=>{const q=$('productSearch').value.trim().toLocaleLowerCase();for(const row of document.querySelectorAll('#clientProductRows [data-product-name]'))row.classList.toggle('hidden',!row.dataset.productName.includes(q));});};
actions.newCatalogProduct=()=>{S.productEdit=null;openCatalogProductForm();};
actions.editCatalogProduct=button=>{S.productEdit=(S.productionCatalog?.products||[]).find(p=>p.id===button.dataset.id)||null;if(!S.productEdit)productionGet('products').then(rows=>{S.productEdit=rows.find(p=>p.id===button.dataset.id)||null;openCatalogProductForm();});else openCatalogProductForm();};
