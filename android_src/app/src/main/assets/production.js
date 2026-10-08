'use strict';
// Progressive activation: companies without the explicit migration keep Stage 2.
const LOCAL_SYNC_INTERVAL_MS=10*60*1000;
let localSyncBusy=false;
function applyProductionMeta(r){
  S.stage3=!!r.ready;
  if(!S.stage3)return;
  S.me.permissions=Array.isArray(r.permissions)?r.permissions:[];
  S.permissionCatalog=Array.isArray(r.catalog)?r.catalog:[];
  try{window.PortalNative?.setCacheIdentity?.(String(S.me?.id||''),String(S.me?.role||''),JSON.stringify(S.me.permissions));}catch{}
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
  if(!canUseLocalOutbox()){S.localPendingCount=0;S.localLegacyPendingCount=0;return 0;}
  const [value,legacy]=await Promise.all([
    nativeOutboxCall('pendingMutationCount'),
    typeof window.PortalNative?.legacyPendingMutationCount==='function'?nativeOutboxCall('legacyPendingMutationCount'):Promise.resolve(0)
  ]);
  const current=Number(value||0),legacyCount=Number(legacy||0);
  S.localPendingCount=Number.isFinite(current)?current:0;
  S.localLegacyPendingCount=Number.isFinite(legacyCount)?legacyCount:0;
  return S.localPendingCount;
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
function openCatalogProductForm(){const p=S.productEdit||{};openSheet(p.id?'Изменить товар':'Новый товар',`<form id="catalogProductForm">${field('catalogProductName','Название',p.name||'','text','required maxlength="200"')}<p class="meta">Переименование не меняет названия товара в ранее созданных партиях.</p><button class="btn block" type="submit">Сохранить</button></form>`);}
forms.catalogProductForm=async form=>{const p=S.productEdit,body={action:p?'update':'create',client_id:S.productClientId,product_id:p?.id,name:$('catalogProductName').value};await productionPost('products',body,form);closeSheet();toast('Каталог обновлён');await actions.manageClientProducts({dataset:{id:String(S.productClientId)}});};
actions.archiveCatalogProduct=async button=>{await productionPost('products',{action:'archive',product_id:button.dataset.id});toast('Товар перемещён в архив');await actions.manageClientProducts({dataset:{id:String(S.productClientId)}});};
actions.employeeActivity=async button=>{const u=S.userData.users.find(x=>x.id===Number(button.dataset.id)),p=(await productionGet('presence')).find(x=>x.user_id===u.id),last=activityTime(p?.last_activity_at);let history='';if(allowed('access.history.read')){const events=await productionGet('activity');history=events.filter(e=>e.user_id===u.id).slice(-12).reverse().map(e=>`<div class="item"><b>${e.event==='login'?'Вход':'Выход'} · ${e.result==='success'?'Успешно':'Отказано'}</b><p class="meta">${esc(e.client_type)} · ${esc(portalDate(e.at).toLocaleString('ru-RU'))}</p></div>`).join('')||'<p class="empty">История входов пока пуста</p>';}
  openSheet(u.display_name,`<section class="card activity-card"><h3>Активность в системе</h3><p><span class="presence-dot ${p?.online?'online':'offline'}"></span>${p?.online?'В сети':'Не в сети'}</p>${!p?.online&&last?`<p class="meta">Был в PORTAL ${esc(last)}</p>`:''}${p?.online?`<p class="meta">Активных устройств: ${num(p.active_sessions)}</p>`:''}</section>${allowed('access.history.read')?`<h3>История входов</h3><div class="list">${history}</div>`:'<p class="meta">Просмотр истории входов недоступен по вашим правам.</p>'}`);
};
actions.loginHistory=async()=>{const events=await productionGet('activity');openSheet('История входов сотрудников',`<div class="list">${events.map(e=>{const user=S.userData?.users.find(u=>u.id===e.user_id);return `<div class="item"><b>${e.event==='login'?'Вход':'Выход'} · ${e.result==='success'?'Успешно':'Отказано'}</b><p class="meta">${esc(user?.display_name||'Сотрудник не определён')} · ${esc(e.client_type)} · ${esc(portalDate(e.at).toLocaleString('ru-RU'))}</p></div>`;}).join('')||'<p class="empty">Записей пока нет</p>'}</div>`);};
actions.taskWork=async button=>{const task=S.productionTasks.find(t=>t.id===button.dataset.id);if(!task)return;S.activeTask=task;let timer=activeTimer(task);if(!timer)timer=await productionPost('timers',{event:'start',task_id:task.id});S.currentTimer=timer;showTimer();};
function showTimer(){const t=S.currentTimer,task=S.activeTask;openSheet('Работа по заданию',`<p>${esc(task.client_name)} · ${esc(task.product)}</p><p><b>${esc(task.operation_name)}</b> · Осталось ${num(task.remaining)}</p><p class="notice"><b>${t.status==='running'?'В работе':'На паузе'} с ${esc(timeOfDay(t.started_at))}</b><br><span class="meta">Накопленное рабочее время: <strong id="timerElapsed">${esc(durationLabel(timerElapsed(t)))}</strong></span></p>${btn(t.status==='running'?'Пауза':'Продолжить','timerToggle','','secondary block')}<form id="taskWorkForm">${field('taskQuantity','Выполненное количество','','number',`required min="1" max="${task.remaining}" step="1"`)}<button class="btn block" type="submit">Завершить работу</button></form>`);tickElapsed();}
actions.timerToggle=async()=>{S.currentTimer=await productionPost('timers',{event:S.currentTimer.status==='running'?'pause':'resume',session_id:S.currentTimer.id});showTimer();};
forms.taskWorkForm=async form=>{await productionPost('timers',{event:'finish',session_id:S.currentTimer.id,quantity:Number($('taskQuantity').value)},form);closeSheet();toast('Работа завершена, сдельная зарплата начислена');await go('work');};
actions.otherWork=async()=>{
  const c=await productionCatalog();
  openSheet('Другая работа',`<p class="meta">Без задания — зарплата начисляется сразу. Новые операции создаёт руководитель.</p><form id="otherWorkForm">${selectField('freeClient','Клиент','<option value="">Выберите клиента</option>'+options(c.clients))}${selectField('freeOperation','Операция','<option value="">Выберите клиента</option>')}${field('freeQuantity','Количество','','number','required min="1" max="1000000" step="1"')}<button class="btn block" type="submit">Внести работу</button></form>`);
  $('freeClient').addEventListener('change',()=>{const id=Number($('freeClient').value);$('freeOperation').innerHTML='<option value="">Выберите операцию</option>'+options(c.operations.filter(o=>o.client_id===id));});
};
forms.otherWorkForm=async form=>{const w=await productionPost('work',{client_id:Number($('freeClient').value),operation_id:Number($('freeOperation').value),quantity:Number($('freeQuantity').value)},form);closeSheet();toast(w.queued?'Сохранено на устройстве · отправим на сервер автоматически':w.salary===undefined?'Выполнено без задания':'Выполнено без задания · '+rub(w.salary));await go('work');};
actions.productionHistory=async()=>{
  const rows=await productionGet('works');S.productionWorks=rows;
  paint(heading('Выработка','История записей сохраняется')+`<div class="list">${rows.map(w=>`<div class="item"><b>${esc(w.client_name)} · ${esc(w.operation_name)}</b><p>${num(w.quantity)} шт. ${w.salary===undefined?'':'· '+rub(w.salary)}</p><p class="meta">${date(w.completed_at)}${w.without_task?' · ':''}${w.without_task?'<span class="badge">Без задания</span>':''}</p>${!w.batch_id&&allowed('work.link')?btn('Привязать к партии','linkWork',`data-id="${w.id}"`,'secondary'):''}</div>`).join('')||'<p class="empty">Записей ещё нет</p>'}</div>`);
};
actions.linkWork=async button=>{const w=S.productionWorks.find(w=>w.id===button.dataset.id),batches=await productionGet('batches');S.linkWorkId=w.id;openSheet('Привязать работу',`<p class="meta">Начисленная зарплата и цена клиенту не изменятся.</p><form id="linkWorkForm">${selectField('linkBatch','Партия',options(batches.filter(b=>b.client_id===w.client_id),'product'))}<button class="btn block" type="submit">Привязать</button></form>`);};
forms.linkWorkForm=async form=>{const result=await productionPost('links',{work_id:S.linkWorkId,batch_id:$('linkBatch').value},form);closeSheet();toast(result.queued?'Привязка сохранена на устройстве · отправим на сервер автоматически':'Работа привязана к партии');await actions.productionHistory();};
screens.batches=async()=>{const [batches,tasks]=await Promise.all([productionGet('batches'),allowed('tasks.read')?productionGet('tasks'):Promise.resolve([])]);S.productionBatches=batches;const grouped=new Map();for(const t of tasks){const list=grouped.get(t.batch_id)||[];list.push(t);grouped.set(t.batch_id,list);}
  paint(heading('Партии и задания','Поступление и ход работ',allowed('batches.receive')?btn('Принять товар','receiveBatch'):'')+`<div class="list">${batches.map(b=>{const related=grouped.get(b.id)||[];return `<article class="item batch-card"><span class="eyebrow">${esc(b.client_name)}</span><h3>${esc(b.product)}</h3><p class="meta batch-number">${esc(b.number)}</p><p class="meta">Поступила ${esc(date(b.received_at))}</p><p>Принято ${num(b.quantity)} · Выполнено ${num(b.done)} · Осталось <strong>${num(b.remaining)}</strong></p>${b.returned_quantity?`<p class="meta">Возвращено ${num(b.returned_quantity)} · Можно принять ещё ${num(b.returnable_quantity)}</p>`:''}<span class="badge ${b.stage==='ready'?'green':''}">${esc(statusLabel[b.stage]||'Статус не указан')}</span>${related.length?`<section class="related-tasks"><h4>Связанные задания</h4><div class="list">${related.map(t=>`<div class="related-task"><b>${esc(t.operation_name)}</b><span class="meta">${num(t.done)} / ${num(t.quantity)} · ${taskStatusLabel(t)}</span></div>`).join('')}</div></section>`:b.operations?.length?`<section class="related-tasks"><h4>Операции партии</h4>${b.operations.map(o=>`<div class="related-task"><b>${esc(o.operation)}</b><span class="meta">${num(o.done)} / ${num(o.planned)}</span></div>`).join('')}</section>`:''}<div class="item-actions">${allowed('tasks.manage')&&!['shipped','partially_returned','returned'].includes(b.stage)?btn('Создать задание','createTask',`data-id="${b.id}"`,'secondary'):''}${allowed('finance.read')?btn('План / факт','batchEconomy',`data-id="${b.id}"`,'text'):''}${b.ready&&b.stage!=='shipped'&&allowed('batches.receive')?btn('Отгрузить','shipBatch',`data-id="${b.id}"`,'secondary'):''}${b.returnable_quantity>0&&['shipped','partially_returned'].includes(b.stage)&&allowed('batches.receive')?btn('Оформить возврат','returnBatch',`data-id="${b.id}"`,'secondary'):''}</div></article>`;}).join('')||'<p class="empty">Пока нет партий</p>'}</div>`);};
actions.receiveBatch=async()=>{const c=await productionCatalog(),productOptions=clientId=>'<option value="">Свободное название / исторический товар</option>'+options((c.products||[]).filter(p=>p.client_id===clientId),'name');openSheet('Поступление товара',`<form id="batchForm">${selectField('batchClient','Клиент',options(c.clients))}${selectField('batchProductId','Товар из каталога',productOptions(c.clients[0]?.id))}${field('batchProduct','Название товара','','text','required maxlength="200"')}<p class="meta">При выборе каталожного товара партия сохранит его стабильный ID и снимок названия.</p>${field('batchQty','Принятое количество','','number','required min="1" step="1"')}${field('batchDate','Дата поступления',new Date().toISOString().slice(0,10),'date','required')}${field('batchExternal','Номер документа клиента — необязательно')}${field('batchDue','Срок готовности','','datetime-local')}${field('batchComment','Комментарий')}<p class="meta">Внутренний номер присвоит PORTAL.</p><button class="btn block" type="submit">Принять товар</button></form>`);$('batchClient').addEventListener('change',()=>{$('batchProductId').innerHTML=productOptions(Number($('batchClient').value));});$('batchProductId').addEventListener('change',()=>{const p=(c.products||[]).find(row=>row.id===$('batchProductId').value);if(p)$('batchProduct').value=p.name;});};
forms.batchForm=async form=>{const result=await productionPost('batches',{client_id:Number($('batchClient').value),product_id:$('batchProductId').value||null,product:$('batchProduct').value,quantity:Number($('batchQty').value),received_at:$('batchDate').value,external_number:$('batchExternal').value,due_at:utc($('batchDue').value),comment:$('batchComment').value},form);closeSheet();toast(result.queued?'Поступление сохранено на устройстве · отправим на сервер автоматически':'Поступление сохранено');await go('batches');};
actions.createTask=async button=>{const b=S.productionBatches.find(b=>b.id===button.dataset.id),c=await productionCatalog();S.taskBatch=b;openSheet('Новое задание',`<p>${esc(b.product)} · ${num(b.quantity)} шт.</p><form id="createTaskForm">${selectField('taskOperation','Операция',options(c.operations.filter(o=>o.client_id===b.client_id)))}<label class="field"><span>Исполнители — можно выбрать нескольких</span><select id="taskAssignees" multiple required>${options(c.users.filter(u=>u.active&&employeeId(u)),'display_name')}</select></label>${field('taskDue','Срок','','datetime-local')}${allowed('finance.read')?field('taskOther','План других расходов, ₽',0,'number','min="0" step="0.01"'):''}<button class="btn block" type="submit">Создать задание</button></form>`);};
forms.createTaskForm=async form=>{const body={batch_id:S.taskBatch.id,operation_id:Number($('taskOperation').value),quantity:S.taskBatch.quantity,assignees:Array.from($('taskAssignees').selectedOptions,o=>Number(o.value)),due_at:utc($('taskDue').value),...($('taskOther')?{other_cost:$('taskOther').value}:{})};const result=await productionPost('tasks',body,form);closeSheet();toast(result.queued?'Задание сохранено на устройстве · отправим на сервер автоматически':'Задание создано');await go('batches');};
actions.batchEconomy=async button=>{const d=await productionGet('economy?batch_id='+encodeURIComponent(button.dataset.id)),money=value=>value==null?'Недоступно':rub(value),volume=value=>value==null?'Недоступно':num(value),rate=value=>value==null?'Недоступно':num(value/100)+'%';openSheet('План / Факт / Отклонение',`<div class="list">${[['revenue','Выручка'],['salary','Зарплата'],['materials','Материалы'],['other','Другие расходы'],['profit','Прибыль']].map(([k,l])=>`<div class="item"><b>${l}</b><p>${money(d.plan[k])} → ${money(d.fact[k])}</p><span class="meta">Отклонение ${money(d.deviation[k])}</span></div>`).join('')}<div class="item"><b>Маржа</b><p>${rate(d.margin_bps?.plan)} → ${rate(d.margin_bps?.fact)}</p><span class="meta">Отклонение ${rate(d.margin_bps?.deviation)}</span></div></div><p class="meta">Объём операций: ${volume(d.plan.volume)} → ${volume(d.fact.volume)}. Готовых единиц: ${num(d.finished_units)} · Себестоимость единицы: ${money(d.cost_per_unit)} · Прибыль на единицу: ${money(d.profit_per_unit)}.</p>`);};
actions.shipBatch=button=>{S.shipBatch=button.dataset.id;openSheet('Направление отгрузки',`<form id="shipForm">${selectField('shipDirection','Направление','<option value="FBO">FBO</option><option value="FBS">FBS</option><option value="shipment">Другая отгрузка</option>')}<button class="btn block" type="submit">Подтвердить отгрузку</button></form>`);};
forms.shipForm=async form=>{const result=await productionPost('shipments',{batch_id:S.shipBatch,direction:$('shipDirection').value},form);closeSheet();toast(result.queued?'Отгрузка сохранена на устройстве · отправим на сервер автоматически':'Отгрузка сохранена');await go('batches');};
actions.returnBatch=button=>{const batch=S.productionBatches?.find(item=>item.id===button.dataset.id);if(!batch)return;S.returnBatch=batch;openSheet('Возврат товара',`<p>Доступно к возврату: ${num(batch.returnable_quantity)} шт.</p><form id="returnForm">${field('returnQuantity','Количество','','number',`required min="1" max="${batch.returnable_quantity}" step="1"`)}${selectField('returnCondition','Состояние','<option value="unknown">Не определено</option><option value="resalable">Можно использовать</option><option value="damaged">Повреждено</option>')}${field('returnComment','Комментарий','','text','maxlength="1000"')}<button class="btn block" type="submit">Зафиксировать возврат</button></form>`);};
forms.returnForm=async form=>{const result=await productionPost('returns',{batch_id:S.returnBatch.id,quantity:Number($('returnQuantity').value),condition:$('returnCondition').value,comment:$('returnComment').value},form);closeSheet();toast(result.queued?'Возврат сохранён на устройстве · отправим на сервер автоматически':'Возврат сохранён');await go('batches');};
screens.permissions=async()=>{
  S.permissionUsers=await productionGet('permissions');paint(heading('Права доступа','Роль задаёт рекомендации, индивидуальные права — доступ')+`<div class="list">${S.permissionUsers.map(u=>`<button class="choice" data-action="editPermissions" data-id="${u.id}"><span><b>${esc(u.display_name)}</b><span class="meta">${esc(PortalCore.roles[u.role])}</span></span></button>`).join('')}</div>`);
};
actions.editPermissions=button=>{
  const u=S.permissionUsers.find(u=>u.id===Number(button.dataset.id));S.permissionTarget=u;
  const groups=[...new Set(S.permissionCatalog.map(p=>p.group))];
  openSheet('Права · '+u.display_name,`<form id="permissionsForm">${groups.map(g=>`<h3>${esc(g)}</h3>${S.permissionCatalog.filter(p=>p.group===g).map(p=>`<label class="permission-row"><input type="checkbox" data-permission="${p.code}" ${u.permissions.includes(p.code)?'checked':''} ${allowed(p.code)?'':'disabled'}><span>${esc(p.label)}<small class="meta">(рекомендуется: ${p.recommended.map(esc).join(', ')})</small></span></label>`).join('')}`).join('')}<button class="btn block" type="submit">Сохранить права</button></form><hr class="line">${btn('Применить рекомендуемые','resetPermissions','data-mode="recommended"','secondary block')}${btn('Сбросить к стандартным','resetPermissions','data-mode="reset"','text block')}<form id="copyPermissionsForm">${selectField('copyUser','Скопировать права сотрудника',options(S.permissionUsers.filter(x=>x.id!==u.id),'display_name'))}<button class="btn secondary block" type="submit">Скопировать права сотрудника</button></form>`);
};
forms.permissionsForm=async form=>{const permissions=Object.fromEntries(Array.from(form.querySelectorAll('[data-permission]:not(:disabled)'),i=>[i.dataset.permission,i.checked]));await productionPost('permissions',{user_id:S.permissionTarget.id,permissions},form);closeSheet();await configureProduction();await go('permissions');};
actions.resetPermissions=async button=>{await productionPost('permissions',{user_id:S.permissionTarget.id,mode:button.dataset.mode});closeSheet();await configureProduction();await go('permissions');};
forms.copyPermissionsForm=async form=>{await productionPost('permissions',{user_id:S.permissionTarget.id,mode:'copy',source_id:Number($('copyUser').value)},form);closeSheet();await configureProduction();await go('permissions');};
screens.tariffs=async()=>{const [c,historyRows]=await Promise.all([productionCatalog(),productionGet('tariff-history')]),history=new Map();for(const row of historyRows){const key=Number(row.operation_id),items=history.get(key)||[];items.push(row);history.set(key,items);}paint(heading('Тарифы','Новая версия не пересчитывает прошлые работы')+`<div class="list">${c.operations.map(o=>`<article class="item"><h3>${esc(o.name)}</h3><p class="meta">${esc(c.clients.find(c=>c.id===o.client_id)?.name)}</p><p>${o.employee_rate===undefined?'':'Сотруднику '+rub(o.employee_rate)} ${o.client_rate===undefined?'':'· Клиенту '+rub(o.client_rate)}</p><details><summary>История ставок · ${(history.get(o.id)||[]).length}</summary><div class="list">${(history.get(o.id)||[]).map((v,index)=>`<div class="item"><b>${index===0?'Текущая версия':'Историческая версия'}</b><p class="meta">Действует с ${esc(v.effective_from)}</p><p>${v.employee_rate===undefined?'':'Сотруднику '+rub(v.employee_rate)} ${v.client_rate===undefined?'':'· Клиенту '+rub(v.client_rate)}</p></div>`).join('')||'<p class="empty">Истории ставок нет</p>'}</div></details>${allowed('rates.employee')||allowed('rates.client')?btn('Новая версия','newTariff',`data-id="${o.id}"`,'secondary'):''}</article>`).join('')||'<p class="empty">Доступных тарифов нет</p>'}</div>`);};
actions.newTariff=button=>{const o=S.productionCatalog.operations.find(o=>o.id===Number(button.dataset.id));S.tariffOperation=o;S.tariffReturnToClient=button.dataset.returnToClient==='true'?o.client_id:null;openSheet('Новая версия тарифа',`<form id="tariffForm">${allowed('rates.employee')?field('tariffEmployee','Ставка сотруднику, ₽',(o.employee_rate||0)/100,'number','min="0" step="0.01" required'):''}${allowed('rates.client')?field('tariffClient','Цена клиенту, ₽',(o.client_rate||0)/100,'number','min="0" step="0.01" required'):''}${field('tariffFrom','Начало действия — пусто означает сейчас','','datetime-local')}<button class="btn block" type="submit">Сохранить новую версию</button></form>`);};
forms.tariffForm=async form=>{const o=S.tariffOperation,b={client_id:o.client_id,operation_id:o.id};if($('tariffEmployee'))b.employee_rate=$('tariffEmployee').value;if($('tariffClient'))b.client_rate=$('tariffClient').value;if($('tariffFrom').value)b.effective_from=utc($('tariffFrom').value);await productionPost('tariffs',b,form);closeSheet();const clientId=S.tariffReturnToClient;S.tariffReturnToClient=null;if(clientId)return actions.openClient({dataset:{id:String(clientId)}});await go('tariffs');};
screens.invoices=async()=>{
  if(!S.stage3)return previous.invoices();
  const rows=await productionGet('invoices');S.productionInvoices=rows;
  paint(heading('Счета и оплаты','Начисления из выработки',allowed('invoices.create')?btn('Подготовить счёт','newInvoice'):'')+`${allowed('invoices.read')?btn('Открыть дебиторку','viewReceivables','','secondary block'):''}<div class="list">${rows.map(i=>`<div class="item"><b>Счёт · ${date(i.created_at)}</b><p>${rub(i.amount)} · Остаток ${rub(i.remaining)}</p><p class="meta">${i.state==='editing'?'На редактировании':'Зафиксирован'} · версия ${num(i.revision||1)}</p><span class="badge">${({paid:'Оплачен',partial:'Частично оплачен',unpaid:'Не оплачен'})[i.status]}</span>${i.remaining&&allowed('payments.record')?btn('Внести оплату','recordPayment',`data-id="${i.id}"`,'secondary'):''}${allowed('documents.manage')&&allowed('invoices.read')?btn('PDF счёта','generateInvoicePdf',`data-id="${esc(i.id)}"`,'secondary')+btn('XLSX счёта','generateInvoiceXlsx',`data-id="${esc(i.id)}"`,'secondary'):''}${['admin','director'].includes(S.me.role)&&i.state!=='editing'?btn('Отправить на редактирование','sendInvoiceEditing',`data-id="${esc(i.id)}"`,'secondary'):''}${S.me.role==='manager'&&i.state==='editing'?btn('Редактировать счёт','editInvoice',`data-id="${esc(i.id)}"`,'secondary'):''}</div>`).join('')||'<p class="empty">Новых счетов нет</p>'}</div>${btn('Ранее созданные счета','legacyInvoices','','text block')}`);
};
actions.viewReceivables=async()=>{
  if(!allowed('invoices.read'))throw new Error('Недостаточно прав для просмотра дебиторки');
  const query=new URLSearchParams({page:String(S.receivablesPage||1),limit:'50'});if(S.receivablesClient)query.set('client_id',S.receivablesClient);
  const d=await productionGet('receivables?'+query.toString()),b=d.buckets||{},rows=d.items||[];S.receivablesData=d;
  paint(heading('Дебиторская задолженность',`На ${date(d.as_of)} · остатки в копейках на сервере`)+btn('К счетам','go','data-page="invoices"','text block')+`<div class="metrics">${metric('Открытый остаток',rub(d.outstanding))}${metric('Просрочено',rub(d.overdue))}${metric('Счетов',num(d.total))}</div><div class="card"><h3>Срок оплаты</h3><div class="metrics">${[['current','В срок'],['days_1_7','1–7 дней'],['days_8_30','8–30 дней'],['days_31_60','31–60 дней'],['days_61_plus','Свыше 60'],['undated','Без срока']].map(([key,label])=>metric(label,`${num(b[key]?.count||0)} · ${rub(b[key]?.amount||0)}`)).join('')}</div><label class="field"><span>Клиент</span><select id="receivablesClient"><option value="">Все клиенты</option>${(d.clients||[]).map(c=>`<option value="${c.client_id}" ${String(S.receivablesClient||'')===String(c.client_id)?'selected':''}>${esc(c.name)} · ${rub(c.outstanding)}</option>`).join('')}</select></label><label class="field"><span>Период просрочки</span><select id="receivablesBucket"><option value="">Все периоды</option><option value="current">В срок</option><option value="days_1_7">1–7 дней</option><option value="days_8_30">8–30 дней</option><option value="days_31_60">31–60 дней</option><option value="days_61_plus">Свыше 60 дней</option><option value="undated">Без срока</option></select></label></div><div class="list">${rows.filter(i=>!S.receivablesBucket||i.bucket===S.receivablesBucket).map(i=>`<article class="item"><b>Счёт #${esc(i.invoice_id)} · клиент #${esc(i.client_id)}</b><p>Остаток ${rub(i.outstanding)} · оплачено ${rub(i.paid)}</p><p class="meta">${i.due_at?`Срок ${esc(date(i.due_at))} · просрочка ${num(i.overdue_days)} дн.`:'Срок оплаты не указан'}</p><span class="badge">${esc(i.bucket)}</span></article>`).join('')||'<p class="empty">Открытых счетов в этом фильтре нет</p>'}</div><div class="row between">${btn('Назад','receivablesPage',`data-page="${Math.max(1,(d.page||1)-1)}"`,'secondary')}${btn(`Страница ${num(d.page||1)} · ${num(d.total||0)} счетов`,'noop','','text')}${btn('Далее','receivablesPage',`data-page="${(d.page||1)+1}"`,'secondary')}</div>`);
  const client=$('receivablesClient');client?.addEventListener('change',()=>{S.receivablesClient=client.value;S.receivablesPage=1;void actions.viewReceivables();});
  const bucket=$('receivablesBucket');if(bucket){bucket.value=S.receivablesBucket||'';bucket.addEventListener('change',()=>{S.receivablesBucket=bucket.value;void actions.viewReceivables();});}
};
actions.receivablesPage=button=>{S.receivablesPage=Math.max(1,Number(button.dataset.page)||1);void actions.viewReceivables();};
actions.noop=()=>{};
actions.legacyInvoices=()=>previous.invoices();
actions.sendInvoiceEditing=async button=>{await productionPost('invoices',{workflow:'send_to_editing',invoice_id:button.dataset.id});toast('Счёт отправлен на редактирование');await go('invoices');};
actions.editInvoice=button=>{const invoice=S.productionInvoices.find(i=>String(i.id)===button.dataset.id);if(!invoice||invoice.state!=='editing')throw new Error('\u0421\u0447\u0451\u0442 \u0431\u043e\u043b\u044c\u0448\u0435 \u043d\u0435 \u043d\u0430\u0445\u043e\u0434\u0438\u0442\u0441\u044f \u043d\u0430 \u0440\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0438');S.editingInvoice=invoice;openSheet('\u0420\u0435\u0434\u0430\u043a\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 \u0441\u0447\u0451\u0442\u0430',`<p class="meta">\u0422\u0435\u043a\u0443\u0449\u0430\u044f \u0432\u0435\u0440\u0441\u0438\u044f ${num(invoice.revision||1)}. \u0421\u0443\u043c\u043c\u0430 \u0438 \u0441\u0442\u0440\u043e\u043a\u0438 \u0441\u043e\u0445\u0440\u0430\u043d\u044f\u044e\u0442\u0441\u044f \u043d\u043e\u0432\u043e\u0439 \u0440\u0435\u0432\u0438\u0437\u0438\u0435\u0439.</p><form id="invoiceRevisionForm">${(invoice.lines||[]).map(line=>`<div class="permission-row" data-revision-line="${esc(line.work_id)}"><label><input type="checkbox" data-revision-work="${esc(line.work_id)}" checked> ${esc(line.operation_name)}</label><label>\u041a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e<input type="number" data-revision-quantity value="${num(line.quantity)}" min="1" step="1" required></label><label>\u0426\u0435\u043d\u0430, \u20bd<input type="number" data-revision-rate value="${(line.client_rate/100).toFixed(2)}" min="0" step="0.01" required></label></div>`).join('')}${field('invoiceRevisionDue','\u041e\u043f\u043b\u0430\u0442\u0438\u0442\u044c \u0434\u043e',invoice.due_at||'','datetime-local')}<button class="btn block" type="submit">\u0421\u043e\u0445\u0440\u0430\u043d\u0438\u0442\u044c \u043d\u043e\u0432\u0443\u044e \u0432\u0435\u0440\u0441\u0438\u044e</button></form>`);};
forms.invoiceRevisionForm=async form=>{const lines=Array.from(form.querySelectorAll('[data-revision-work]:checked'),input=>{const row=input.closest('[data-revision-line]');return {work_id:input.dataset.revisionWork,quantity:Number(row.querySelector('[data-revision-quantity]').value),client_rate:Math.round(Number(row.querySelector('[data-revision-rate]').value)*100)};});if(!lines.length)throw new Error('\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u0445\u043e\u0442\u044f \u0431\u044b \u043e\u0434\u043d\u0443 \u0441\u0442\u0440\u043e\u043a\u0443');await productionPost('invoices',{workflow:'save_revision',invoice_id:S.editingInvoice.id,lines,due_at:utc($('invoiceRevisionDue').value)},form);closeSheet();toast('\u041d\u043e\u0432\u0430\u044f \u0432\u0435\u0440\u0441\u0438\u044f \u0441\u0447\u0451\u0442\u0430 \u0441\u043e\u0445\u0440\u0430\u043d\u0435\u043d\u0430');await go('invoices');};
actions.newInvoice=async()=>{const [rows,invoices]=await Promise.all([productionGet('works'),productionGet('invoices')]);const billed=new Set(invoices.flatMap(i=>i.work_ids));S.unbilledWorks=rows.filter(w=>!billed.has(w.id));openSheet('Выставить выполненную работу',`<p class="meta">Выберите работы одного клиента. Повторное начисление исключено.</p><form id="invoiceForm">${S.unbilledWorks.map(w=>`<label class="permission-row"><input type="checkbox" data-work="${w.id}"><span>${esc(w.client_name)} · ${esc(w.operation_name)}<small>${num(w.quantity)} шт. · ${rub(w.revenue)}</small></span></label>`).join('')||'<p>Невыставленных работ нет</p>'}${field('invoiceDue','Оплатить до','','datetime-local')}<button class="btn block" type="submit">Создать счёт</button></form>`);};
forms.invoiceForm=async form=>{await productionPost('invoices',{work_ids:Array.from(form.querySelectorAll('[data-work]:checked'),i=>i.dataset.work),due_at:utc($('invoiceDue').value)},form);closeSheet();await go('invoices');};
actions.recordPayment=button=>{S.paymentInvoice=button.dataset.id;openSheet('Поступление оплаты',`<form id="paymentForm">${field('paymentAmount','Сумма, ₽','','number','required min="0.01" step="0.01"')}${field('paymentReference','Номер платёжного документа')}<button class="btn block" type="submit">Записать оплату</button></form>`);};
forms.paymentForm=async form=>{await productionPost('payments',{invoice_id:S.paymentInvoice,amount:$('paymentAmount').value,reference:$('paymentReference').value},form);closeSheet();await go('invoices');};
screens.radar=async()=>{
  const [d,receivables,today]=await Promise.all([
    productionGet('finance'),
    allowed('invoices.read')?productionGet('receivables?page=1&limit=1').catch(()=>null):Promise.resolve(null),
    productionGet('today').catch(()=>null)
  ]);
  const margin=value=>value==null?'—':num(value/100)+'%';
  const totals=d.totals||{revenue:d.clients.reduce((sum,c)=>sum+c.revenue,0),salary:d.clients.reduce((sum,c)=>sum+c.salary,0),materials:d.clients.reduce((sum,c)=>sum+c.materials,0),other:d.clients.reduce((sum,c)=>sum+c.other,0)};
  const lossCount=d.clients.filter(c=>c.profit<0).length;
  const financialTypes=new Set(['not_invoiced','payment_late','reminder','control_monday','control_wednesday']);
  const attention=(today?.attention||[]).filter(item=>financialTypes.has(item.type)).slice(0,8);
  const debtBlock=receivables?`<div class="metrics">${metric('Открытая дебиторка',rub(receivables.outstanding))}${metric('Просрочено',rub(receivables.overdue))}${metric('Открытые счета',num(receivables.total))}</div>`:allowed('invoices.read')?'<div class="notice warning"><b>Дебиторка временно недоступна</b><p>Основные показатели прибыли показаны из доступных источников.</p></div>':'';
  const attentionBlock=attention.length?`<h2>Требует внимания</h2><div class="list">${attention.map(item=>`<article class="item"><b>${esc(item.label||'Финансовое событие')}</b>${item.amount!==undefined?`<p>${rub(item.amount)}</p>`:''}</article>`).join('')}</div>`:'';
  paint(heading('Финансовый радар','Выручка − зарплата − материалы − расходы')+
    `<div class="metrics">${metric('Выручка',rub(totals.revenue))}${metric('Прибыль клиентов',rub(d.client_profit))}${metric('Маржа клиентов',margin(d.client_margin_bps))}${metric('Общие расходы',rub(d.company_overhead))}${metric('Чистая прибыль',rub(d.net_profit))}${metric('Чистая маржа',margin(d.net_margin_bps))}${metric('Убыточные клиенты',num(lossCount))}</div>${debtBlock}${attentionBlock}<div class="list">${d.clients.map(c=>`<article class="card"><h3>${esc(c.client_name)}</h3><div class="hero-value">${rub(c.profit)}</div><p class="meta">Выручка ${rub(c.revenue)} · зарплата ${rub(c.salary)}<br>Материалы ${rub(c.materials)} · расходы клиента ${rub(c.other)}</p><p>Маржинальность ${c.margin_bps==null?(c.margin==null?'—':num(c.margin*100)+'%'):margin(c.margin_bps)}</p><p class="meta">Средняя прибыль партии ${c.average_batch_profit==null?'—':rub(c.average_batch_profit)}</p></article>`).join('')}</div><h2>Динамика по месяцам</h2>${Object.entries(d.months||{}).sort(([a],[b])=>b.localeCompare(a)).map(([m,v])=>`<article class="item"><h3>${esc(m)}</h3><p>Выручка ${rub(v.revenue)} · ФОТ ${rub(v.salary)}</p><p class="meta">Материалы ${rub(v.materials)} · Расходы по клиентам ${rub(v.other)} · Общие расходы ${rub(v.overhead)}</p><b>Прибыль ${rub(v.profit)} · маржа ${margin(v.margin_bps)}</b></article>`).join('')||'<p class="empty">Нет подтверждённых фактов для помесячной сводки</p>'}`);
};
screens.analytics=async()=>{
  const range=S.analyticsRange||{},query=range.from&&range.to?'?from='+encodeURIComponent(range.from)+'&to='+encodeURIComponent(range.to):'',d=await productionGet('analytics'+query),c=d.comparison;
  const pace=value=>value==null?'нет подтверждённого времени':num(value)+' шт./ч';
  const consistency=value=>value==null?'недостаточно timed samples':'разброс темпа '+num(value*100)+'%';
  const groups=(d.groups||[]).map(g=>`<article class="item"><h3>${esc(g.product||g.operation_name||'Без товара')}</h3><p class="meta">${esc(g.user_name||('Сотрудник #'+g.user_id))} · ${esc(g.client_name||('Клиент #'+g.client_id))} · ${esc(g.operation_name||('Операция #'+g.operation_id))}</p><p>${num(g.quantity)} шт. · ${pace(g.units_per_hour)}</p><p class="meta">По времени учтено ${num(g.timed_quantity||0)} шт. · ${consistency(g.variability)}</p></article>`).join('')||'<p class="empty">Нет подтверждённых данных</p>';
  const batchGroups=(d.batch_groups||[]).map(g=>`<article class="item"><h3>${esc(g.batch_number||g.batch_id)} · ${esc(g.operation_name||('Операция #'+g.operation_id))}</h3><p class="meta">${esc(g.client_name||('Клиент #'+g.client_id))} · ${esc(g.product||'Без товара')}</p><p>${num(g.quantity)} шт. · ${pace(g.units_per_hour)}</p><p class="meta">${consistency(g.variability)}</p></article>`).join('')||'<p class="empty">Нет выработки, связанной с партиями</p>';
  const quality=d.quality?.available?`<div class="notice"><b>Качество по зафиксированным данным</b><p>Записано ${num(d.quality.defects)} дефектов на ${num(d.quality.recorded_units)} учтённых единиц.</p></div>`:'<div class="notice"><b>Качество</b><p>Источник данных о дефектах пока не заполнен. Оценка качества не рассчитывается.</p></div>';
  const aiAllowed=isOwner()||['admin','director'].includes(S.me?.role);
  let aiStatus=null;
  if(aiAllowed){try{aiStatus=await productionGet('code-interpreter');}catch{}}
  const aiReady=aiStatus?.enabled&&aiStatus?.configured;
  const aiBlock=!aiAllowed?'':`<h2>AI-аналитик (Python)</h2><div class="card"><p class="meta">Code Interpreter работает в изолированном Python-контейнере OpenAI без сетевого доступа. В OpenAI API отправляется только текст, который вы сами введёте в поле ниже; данные PORTAL автоматически не передаются.</p>${aiReady?`<form id="codeInterpreterForm"><label class="field"><span>Что проанализировать</span><textarea id="codeInterpreterPrompt" maxlength="12000" rows="5" required placeholder="Например: рассчитай среднюю производительность по этим данным: ..."></textarea></label><button class="btn block" type="submit">Запустить Python-анализ</button></form><div id="codeInterpreterResult"></div><p class="meta">Модель: ${esc(aiStatus.model)} · память ${esc(aiStatus.memory_limit)} · сохранение response отключено.</p>`:`<div class="notice warning"><b>AI-аналитик пока не активирован</b><p>${aiStatus?.enabled?'На сервере не настроен OPENAI_API_KEY.':'Функция отключена оператором PORTAL.'}</p></div>`}</div>`;
  paint(heading('PORTAL Аналитика','Производительность по сотруднику, клиенту, товару, операции и партии')+aiBlock+
    `<form id="analyticsFilterForm">${field('analyticsFrom','С даты',range.from||'','date','required')}${field('analyticsTo','По дату',range.to||'','date','required')}<button class="btn secondary block" type="submit">Сравнить периоды</button></form><p class="meta">Прогнозы ориентировочные. Темп считается только по работам с зафиксированным временем.</p>`+
    (c?`<h2>${esc(date(c.period_start))}–${esc(date(c.period_end))} · сравнение с ${esc(date(c.previous_start))}–${esc(date(c.previous_end))}</h2><div class="metrics">${metric('Объём за период',num(c.current.units)+' шт.')}${metric('Предыдущий период',num(c.previous.units)+' шт.')}${metric('Изменение объёма',c.previous.units?num(c.units_delta)+' шт. · '+num(c.units_percent_delta)+'%':num(c.units_delta)+' шт. · нет базы для процента')}${metric('Темп за период',pace(c.current.units_per_hour))}${metric('Темп ранее',pace(c.previous.units_per_hour))}${metric('Изменение темпа',c.units_per_hour_delta==null?'недостаточно данных времени для сравнения':num(c.units_per_hour_delta)+' шт./ч')}</div>`:'')+
    `<h2>Сотрудники, клиенты и операции</h2><div class="list">${groups}</div><h2>Партии по операциям</h2><div class="list">${batchGroups}</div>${quality}<h2>Прогноз заданий</h2>${(d.forecasts||[]).map(f=>`<div class="item">Осталось ${num(f.remaining)} · ${f.estimated_completion?date(f.estimated_completion):'срок пока не определён'}</div>`).join('')||'<p class="empty">Нет активных прогнозов</p>'}`);
};
forms.analyticsFilterForm=async form=>{const from=$('analyticsFrom').value,to=$('analyticsTo').value;if(!from||!to)throw new Error('Укажите обе даты периода');S.analyticsRange={from,to};await go('analytics');};
forms.codeInterpreterForm=async()=>{const prompt=$('codeInterpreterPrompt')?.value.trim();if(!prompt)throw new Error('Введите запрос для AI-аналитика');const result=(await api('POST','/api/v3/code-interpreter',{prompt})).data,node=$('codeInterpreterResult');if(node)node.innerHTML=`<div class="notice"><b>Результат Python-анализа</b><p>${esc(result.text).replace(/\n/g,'<br>')}</p><p class="meta">${esc(result.model||'OpenAI')} · sandbox без сети</p></div>`;};
screens.control=async()=>{const s=await productionGet('settings');paint(heading('Контроль PORTAL','Понедельник — счета; среда — проверка оплат')+`<form id="controlForm" class="card">${field('controlMonday','Проверка в понедельник',s.monday_time,'time','required')}${field('controlWednesday','Проверка в среду',s.wednesday_time,'time','required')}${field('controlOffset','Смещение от UTC, минут',s.utc_offset_minutes,'number','min="-720" max="840" step="1" required')}${field('presenceHeartbeat','Интервал проверки связи, секунд',s.presence_heartbeat_seconds,'number','min="15" max="300" step="1" required')}${field('presenceTimeout','Порог отсутствия связи, секунд',s.presence_timeout_seconds,'number','min="30" max="3600" step="1" required')}<label class="field"><span>Внутренние напоминания</span><select id="reminderEnabled"><option value="false" ${s.reminder_enabled?'':'selected'}>Выключены</option><option value="true" ${s.reminder_enabled?'selected':''}>Включены</option></select></label><label class="field"><span>Периодичность напоминаний</span><select id="reminderCadence"><option value="daily" ${s.reminder_cadence==='weekly'?'':'selected'}>Ежедневно</option><option value="weekly" ${s.reminder_cadence==='weekly'?'selected':''}>Еженедельно</option></select></label><p class="meta">Напоминания попадают во внутреннюю ленту внимания. Автоматический запуск требует отдельного настроенного оператора и по умолчанию выключен.</p><p class="meta">Проверки выполняются при открытии PORTAL Сегодня. Внешние уведомления не отправляются.</p><button class="btn block" type="submit">Сохранить правила</button></form>`);};
forms.controlForm=async form=>{await productionPost('settings',{monday_time:$('controlMonday').value,wednesday_time:$('controlWednesday').value,utc_offset_minutes:Number($('controlOffset').value),presence_heartbeat_seconds:Number($('presenceHeartbeat').value),presence_timeout_seconds:Number($('presenceTimeout').value),reminder_enabled:$('reminderEnabled').value==='true',reminder_cadence:$('reminderCadence').value},form);await configureProduction();toast('Правила сохранены');delete form.dataset.requestId;};
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
function organizerCounts(rows){
  const now=new Date(),today=organizerDay(now);
  return {
    today:organizerTodayRows(rows,now).length,
    upcoming:rows.filter(t=>organizerActive(t)&&new Date(t.due_at)>=now&&organizerDay(t.due_at)!==today).length,
    overdue:rows.filter(t=>organizerActive(t)&&new Date(t.due_at)<now).length,
    incoming:rows.filter(t=>t.assignee_user_id===S.me.id).length,
    assigned:rows.filter(t=>t.created_by===S.me.id).length,
    all:rows.length
  };
}
function organizerRenderTabs(){
  const box=$('organizerTabs');if(!box)return;
  const counts=organizerCounts(S.organizerRows||[]);
  const tabs=[['today','Сегодня'],['upcoming','Предстоящие'],['overdue','Просроченные'],['incoming','Назначенные мне'],['assigned','Поставленные мной'],['calendar','Календарь'],['all','Все задачи']];
  box.innerHTML=tabs.map(([key,label])=>btn(label+(key==='calendar'?'':' <span class="organizer-tab-count">'+num(counts[key]||0)+'</span>'),'organizerView','data-view="'+key+'"',S.organizerView===key?'':'secondary')).join('');
}
function organizerRenderBody(){
  const body=$('organizerBody');if(!body)return;
  if(!S.organizerLoaded){body.innerHTML='<div class="loading organizer-loading"><span class="spinner"></span><p>Загружаем задачи…</p></div>';return;}
  const view=S.organizerView||'today';
  if(view==='calendar'){
    S.organizerMonth=S.organizerMonth||new Date(new Date().getFullYear(),new Date().getMonth(),1);
    body.innerHTML=organizerCalendar(S.organizerRows||[],S.organizerMonth);return;
  }
  const rows=organizerFiltered(S.organizerRows||[],view);
  body.innerHTML='<div class="list">'+(rows.map(organizerTaskCard).join('')||'<p class="empty organizer-empty">Задач в этом разделе нет</p>')+'</div>';
}
function organizerRenderSync(){
  const box=$('organizerSync');if(!box)return;
  const sync=S.organizerSync||{};
  if(sync.loading&&!S.organizerLoaded){box.innerHTML='<div class="organizer-sync"><span class="spinner"></span><span>Получаем актуальные данные…</span></div>';return;}
  if(!sync.loadedAt&&!sync.error){box.innerHTML='';return;}
  let text='',klass='';
  if(sync.cached){
    klass=' cached';const at=sync.cachedAt?organizerMoment(new Date(sync.cachedAt).toISOString()):'ранее';
    text='Локальные данные · синхронизация '+at;
  }else if(sync.error){klass=' warning';text='Часть данных временно недоступна · показано последнее доступное состояние';}
  else{text='Синхронизировано · '+organizerMoment(new Date(sync.loadedAt).toISOString());}
  box.innerHTML='<div class="organizer-sync'+klass+'"><span>'+esc(text)+'</span>'+btn('Обновить','organizerRefresh','','text')+'</div>';
}
function organizerRenderRequests(){
  const box=$('organizerRequestsPanel');if(!box)return;
  const canMine=canCreateDirectorRequest(),canIncoming=allowed('organizer.request.decide');
  if(!canMine&&!canIncoming){box.innerHTML='';return;}
  const mine=S.organizerMineRequests||[],incoming=S.organizerIncomingRequests||[];
  const total=mine.length+incoming.length,attention=incoming.filter(r=>['new','review'].includes(r.status)).length+mine.filter(r=>r.status==='needs_info').length;
  let groups='';
  if(mine.length)groups+='<div class="organizer-request-group"><h3>Мои запросы</h3><div class="list">'+mine.map(organizerRequestCard).join('')+'</div></div>';
  if(incoming.length)groups+='<div class="organizer-request-group"><h3>Входящие запросы</h3><div class="list">'+incoming.map(organizerRequestCard).join('')+'</div></div>';
  if(!total)groups+='<p class="meta organizer-request-empty">Активных запросов нет.</p>';
  const create=canMine?btn(icon('plus')+' Новый запрос','organizerRequestNew','','secondary'):'';
  box.innerHTML='<details class="organizer-requests card"'+(attention?' open':'')+'><summary><span><b>Запросы директору</b><small>'+(attention?attention+' требуют внимания':total?total+' всего':'нет активных')+'</small></span><span class="badge'+(attention?' amber':'')+'">'+num(total)+'</span></summary><div class="organizer-request-content">'+(create?'<div class="organizer-request-toolbar">'+create+'</div>':'')+groups+'</div></details>';
}
function organizerRenderWorkspace(){organizerRenderSync();organizerRenderTabs();organizerRenderBody();organizerRenderRequests();}
async function organizerFetch(path,fresh=false){return api('GET','/api/v3/'+path,undefined,fresh?{fresh:true}:{});}
async function organizerLoadWorkspace(fresh=false){
  const scope=allowed('organizer.manage')?'company':'mine';
  S.organizerSync={...(S.organizerSync||{}),loading:true};organizerRenderSync();
  const specs=[['tasks','organizer?scope='+scope]];
  if(canCreateDirectorRequest())specs.push(['mine','organizer-requests?scope=mine']);
  if(allowed('organizer.request.decide'))specs.push(['incoming','organizer-requests?scope=incoming']);
  const settled=await Promise.allSettled(specs.map(([,path])=>organizerFetch(path,fresh)));
  let tasksOk=false,firstError=null;const successful=[];
  settled.forEach((entry,index)=>{
    const key=specs[index][0];
    if(entry.status==='fulfilled'){
      successful.push(entry.value);const rows=Array.isArray(entry.value.data)?entry.value.data:[];
      if(key==='tasks'){S.organizerRows=rows;S.organizerLoaded=true;tasksOk=true;}
      else if(key==='mine')S.organizerMineRequests=rows;
      else if(key==='incoming')S.organizerIncomingRequests=rows;
    }else if(!firstError)firstError=entry.reason;
  });
  S.organizerMineRequests=S.organizerMineRequests||[];S.organizerIncomingRequests=S.organizerIncomingRequests||[];
  S.organizerRequestRows=[...S.organizerMineRequests,...S.organizerIncomingRequests.filter(x=>!S.organizerMineRequests.some(m=>m.id===x.id))];
  if(!tasksOk&&!S.organizerLoaded)throw firstError||new Error('Не удалось загрузить задачи');
  const cached=successful.some(result=>result?.cached);
  const cachedTimes=successful.map(organizerCachedAt).filter(Boolean);
  S.organizerSync={loading:false,cached,cachedAt:cachedTimes.length?Math.min(...cachedTimes):0,loadedAt:Date.now(),error:firstError?String(firstError.message||firstError):''};
  organizerRenderWorkspace();return cached;
}
async function organizerFreshReload(view,epoch){
  try{await organizerLoadWorkspace(true);}
  catch(error){if(S.page==='organizer'&&S.view===view&&S.epoch===epoch){S.organizerSync={...(S.organizerSync||{}),loading:false,error:String(error.message||error)};organizerRenderSync();}}
}
async function refreshOrganizer(){
  const scope=allowed('organizer.manage')?'company':'mine',result=await organizerFetch('organizer?scope='+scope,true);
  S.organizerRows=Array.isArray(result.data)?result.data:[];S.organizerLoaded=true;
  S.organizerSync={loading:false,cached:false,cachedAt:0,loadedAt:Date.now(),error:''};organizerRenderWorkspace();
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
async function refreshOrganizerRequests(){
  const specs=[];
  if(canCreateDirectorRequest())specs.push(['mine','organizer-requests?scope=mine']);
  if(allowed('organizer.request.decide'))specs.push(['incoming','organizer-requests?scope=incoming']);
  const results=await Promise.all(specs.map(async([key,path])=>[key,await organizerFetch(path,true)]));
  for(const [key,result] of results){const rows=Array.isArray(result.data)?result.data:[];if(key==='mine')S.organizerMineRequests=rows;else S.organizerIncomingRequests=rows;}
  S.organizerMineRequests=S.organizerMineRequests||[];S.organizerIncomingRequests=S.organizerIncomingRequests||[];
  S.organizerRequestRows=[...S.organizerMineRequests,...S.organizerIncomingRequests.filter(x=>!S.organizerMineRequests.some(m=>m.id===x.id))];
  organizerRenderRequests();
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
screens.organizer=async()=>{
  if(!can('organizer'))throw new Error('Нет доступа к органайзеру');
  const companyKey=String(S.company?.id||'');
  if(S.organizerCompanyKey!==companyKey){
    S.organizerCompanyKey=companyKey;S.organizerRows=[];S.organizerMineRequests=[];S.organizerIncomingRequests=[];S.organizerRequestRows=[];
    S.organizerUsers=null;S.organizerDirectors=null;S.organizerRequestUsers=null;S.organizerLoaded=false;S.organizerSync=null;
  }
  S.organizerView=S.organizerView||'today';
  paint(heading('Органайзер','Задачи и сроки',allowed('organizer.assign')?btn(icon('plus')+' Новая','organizerNew','','secondary'):'')+
    '<div id="organizerSync"></div><div id="organizerTabs" class="organizer-tabs"></div><div id="organizerBody"></div><div id="organizerRequestsPanel"></div>');
  organizerRenderWorkspace();
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
actions.organizerView=button=>{S.organizerView=button.dataset.view;organizerRenderTabs();organizerRenderBody();};
actions.organizerMonth=button=>{const m=S.organizerMonth||new Date();S.organizerMonth=new Date(m.getFullYear(),m.getMonth()+Number(button.dataset.shift),1);organizerRenderBody();};
actions.organizerRefresh=async button=>{button.disabled=true;try{await organizerLoadWorkspace(true);}finally{button.disabled=false;}};
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
