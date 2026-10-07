'use strict';
// Preview-only visual layer. LIVE data remains authoritative; mock-looking values are never presented as real.
(() => {
  const liveDashboard=screens.dashboard;
  const liveClients=screens.clients;
  const liveUsers=screens.users;
  const livePayroll=screens.payroll;
  const liveInvoices=screens.invoices;
  const liveMaterials=screens.materials;
  const liveDocuments=screens.documents;
  const previewBadge='<span class="badge preview">Preview</span>';
  const managementRoles=new Set(['director','admin','platform_owner']);
  const quick=(page,iconName,title,meta='')=>can(page)?`<button class="quick-action" data-action="go" data-page="${page}"><span class="quick-icon">${icon(iconName)}</span><span><b>${esc(title)}</b>${meta?`<small>${esc(meta)}</small>`:''}</span>${icon('chevron')}</button>`:'';
  const previewCard=(title,text)=>`<article class="preview-card"><div class="row between"><b>${esc(title)}</b>${previewBadge}</div><p class="meta">${esc(text)}</p></article>`;
  function attentionHtml(rows){
    if(!rows.length)return '<div class="attention-ok"><span class="status-dot ok"></span><div><b>Всё под контролем</b><p class="meta">Критических событий сейчас нет.</p></div></div>';
    return rows.map(a=>`<article class="attention-card"><span class="status-dot warn"></span><div class="grow"><b>${esc(a.label||'Требует внимания')}</b>${a.number?`<p class="meta batch-number">${esc(a.number)}</p>`:''}${a.name?`<p class="meta">${esc(a.name)} · ${num(a.quantity)} шт.</p>`:''}${a.amount!==undefined?`<strong>${rub(a.amount)}</strong>`:''}</div></article>`).join('');
  }
  function previewSheet(title,body){
    openSheet(title,`<div class="preview-sheet-head">${previewBadge}<p class="muted">Этот экран уже входит в структуру PORTAL. Backend будет подключён на следующем этапе.</p></div>${body}`);
  }
  screens.dashboard=async()=>{
    if(!S.stage3||!managementRoles.has(S.me?.role))return liveDashboard();
    const d=await productionGet('today');
    S.productionTasks=d.tasks||[];
    S.activeTimers=allowed('work.write')||allowed('tasks.read')?await productionGet('timers'):[];
    const inWorkTasks=new Set([...S.productionTasks.filter(t=>t.status==='in_progress').map(t=>t.id),...S.activeTimers.map(t=>t.task_id)]);
    let payroll=null,payrollBounds=null;
    if(allowed('payroll.all')){
      try{payrollBounds=currentPayrollBounds();payroll=await productionGet(`payroll-periods?period_start=${encodeURIComponent(payrollBounds[0])}&period_end=${encodeURIComponent(payrollBounds[1])}`);}catch{}
    }
    const finance=d.finance||null;
    const financeOther=finance?Number(finance.other||0)+Number(finance.company_overhead||0):0;
    const margin=finance&&Number(finance.revenue)?Number(finance.profit||0)/Number(finance.revenue)*100:null;
    const attention=d.attention||[];
    const overdue=attention.filter(a=>a.type==='payment_late').length;
    const status=attention.length?`${attention.length} ${attention.length===1?'пункт требует':'пункта требуют'} внимания`:'Работа идёт штатно';
    const quickActions=[
      quick('clients','clients','Клиенты','Карточки и тарифы'),
      quick('users','users','Сотрудники','Роли и доступ'),
      quick('materials','box','Склад','Остатки и движения'),
      quick('invoices','receipt','Счета','Дебиторка и оплаты'),
      quick('payrollPeriods','wallet','Зарплата','Расчётные периоды'),
      quick('documents','file','Документы','Excel и PDF'),
      quick('reports','grid','Отчёты','Управленческая аналитика'),
      quick('notifications','bell','Контроль','События и предупреждения')
    ].join('');
    paint(
      heading('PORTAL Сегодня',date(d.date),btn('Все разделы','go','data-page="sections"','secondary'))+
      `<section class="director-hero"><div><span class="eyebrow">${esc(S.company?.name||'Компания')}</span><h2>${esc(PortalCore.timeGreeting())}, ${esc(S.me.display_name||S.me.username)}</h2><p class="muted">${esc(status)}</p></div><span class="badge ${attention.length?'amber':'green'}">${attention.length?'Есть задачи':'Всё спокойно'}</span></section>`+
      `<section class="dashboard-section"><div class="section-label"><h2>Сегодня</h2><span class="meta">Живая сводка</span></div><div class="today-grid">
        <div class="today-main"><span class="l">Выработка</span><strong>${num(d.today_quantity||0)}</strong><small>шт. сегодня</small></div>
        <div class="today-kpi"><span>Заданий в работе</span><b>${num(inWorkTasks.size)}</b></div>
        <div class="today-kpi"><span>Готовые партии</span><b>${num(d.ready||0)}</b></div>
        <div class="today-kpi"><span>Активные партии</span><b>${num(d.active_batches||0)}</b></div>
        ${d.active_jobs!==undefined?`<div class="today-kpi"><span>Открытые задания</span><b>${num(d.active_jobs)}</b></div>`:''}
        ${d.today_finance?`<div class="today-kpi"><span>Выручка сегодня</span><b>${rub(d.today_finance.revenue)}</b></div><div class="today-kpi"><span>Начислено сегодня</span><b>${rub(d.today_finance.salary)}</b></div>`:''}
        ${d.today_productivity?`<div class="today-kpi"><span>Скорость команды</span><b>${d.today_productivity.units_per_hour==null?'Нет данных времени':num(d.today_productivity.units_per_hour)+' шт./ч'}</b></div>`:''}
      </div></section>`+
      `<section class="dashboard-section attention-zone"><div class="section-label"><h2>Требует внимания</h2><button class="text-link" data-action="go" data-page="notifications">Все события</button></div><div class="attention-stack">${attentionHtml(attention.slice(0,4))}</div></section>`+
      (finance?`<section class="dashboard-section"><div class="section-label"><h2>Финансовый радар</h2><button class="text-link" data-action="go" data-page="radar">Подробнее</button></div><div class="money-grid">
        <div class="money-card"><span>Выручка</span><strong>${rub(finance.revenue)}</strong></div>
        <div class="money-card"><span>ФОТ</span><strong>${rub(finance.salary)}</strong></div>
        <div class="money-card"><span>Материалы</span><strong>${rub(finance.materials)}</strong></div>
        <div class="money-card"><span>Прочие расходы</span><strong>${rub(financeOther)}</strong></div>
        <div class="money-card emphasis"><span>Чистый результат</span><strong>${rub(finance.profit)}</strong><small>${margin==null?'Маржа не определена':'Маржа '+num(margin)+'%'}</small></div>
        ${d.month_finance?`<div class="money-card"><span>Выручка за месяц</span><strong>${rub(d.month_finance.revenue)}</strong></div><div class="money-card"><span>Начислено за месяц</span><strong>${rub(d.month_finance.salary)}</strong></div>`:''}
        ${(allowed('payroll.settlement.read')||allowed('payroll.all'))&&d.closed_month_payroll!==undefined?`<div class="money-card"><span>Закрытый ФОТ</span><strong>${d.closed_month_payroll?`Начислено ${rub(d.closed_month_payroll.accrued)} · Выплачено ${rub(d.closed_month_payroll.paid)} · Остаток ${rub(d.closed_month_payroll.balance)}`:'Нет закрытого периода'}</strong></div>`:''}
        ${d.expected_profit!==undefined?`<div class="money-card"><span>Плановая прибыль</span><strong>${d.expected_profit==null?'Недоступна':rub(d.expected_profit)}</strong></div>`:''}
      </div></section>`:'')+
      `<div class="dashboard-two"><section class="dashboard-section compact-panel"><div class="section-label"><h2>Зарплата</h2><button class="text-link" data-action="go" data-page="payrollPeriods">Открыть</button></div>
        ${payroll&&payrollBounds?`<p class="meta">${esc(payrollBounds[0])} — ${esc(payrollBounds[1])}</p><div class="large-value">${rub(payroll.total_salary||0)}</div><p>Начислено по данным выработки</p><span class="badge preview">Предпросмотр периода</span>`:`<div class="preview-empty">${previewBadge}<p>Сводка расчётного периода появится после подключения данных.</p></div>`}
      </section><section class="dashboard-section compact-panel"><div class="section-label"><h2>Дебиторка</h2><button class="text-link" data-action="go" data-page="invoices">Счета</button></div>
        ${d.debt!==undefined?`<div class="large-value">${rub(d.debt)}</div><p>Остаток к оплате клиентами</p>${d.open_invoice_count!==undefined?`<p>Открытые счета: ${num(d.open_invoice_count)}</p>`:''}<span class="badge ${(d.overdue_invoice_count||overdue)?'amber':'green'}">${d.overdue_invoice_count?`Просрочено: ${num(d.overdue_invoice_count)} · ${rub(d.overdue_debt)}`:overdue?('Просрочено: '+overdue):'Без просрочек'}</span>`:`<div class="preview-empty">${previewBadge}<p>Данные дебиторки пока недоступны.</p></div>`}
      </section></div>`+
      `<section class="dashboard-section"><div class="section-label"><h2>Производство</h2><button class="text-link" data-action="go" data-page="batches">Партии и задания</button></div><div class="production-strip"><div><span>В работе</span><b>${num(inWorkTasks.size)}</b></div><div><span>Готово</span><b>${num(d.ready||0)}</b></div><div><span>Активно партий</span><b>${num(d.active_batches||0)}</b></div></div>${allowed('tasks.read')&&S.productionTasks.length?`<div class="compact-task-list">${taskCards(S.productionTasks.slice(0,3))}</div>`:''}</section>`+
      `<section class="dashboard-section"><div class="section-label"><h2>Быстрые действия</h2><button class="text-link" data-action="go" data-page="sections">Все разделы</button></div><div class="quick-grid">${quickActions}</div></section>`
    );
    tickElapsed();
  };

  actions.previewFeature=button=>previewSheet(button.dataset.title||'Функция PORTAL',`<div class="preview-flow"><h3>${esc(button.dataset.title||'Будущий модуль')}</h3><p>${esc(button.dataset.text||'Функция включена в утверждённую структуру preview APK.')}</p><div class="notice">В preview-сборке можно оценить расположение, названия и сценарий переходов. Запись в production не выполняется.</div></div>`);
  screens.reports=async()=>{
    const items=[
      ['Производство','Партии, задания, план/факт и выполненный объём'],
      ['Выработка','Сотрудники, клиенты, операции и периоды'],
      ['Зарплата','Начисления, выплаты и расчётные периоды'],
      ['Клиенты','Выручка, тарифы, дебиторка и маржа'],
      ['Склад','Остатки, движения, расход и минимальные запасы'],
      ['Финансы','Расходы, прибыль и динамика'],
      ['Активность','Входы, присутствие и действия сотрудников'],
      ['Документы','XLSX/PDF и история формирования']
    ];
    paint(heading('Отчёты','Единый каталог управленческой отчётности',previewBadge)+
      '<div class="preview-banner"><b>Preview-каталог</b><p>Разделы уже закреплены в интерфейсе. Готовые отчёты будут подключаться постепенно без перестройки меню.</p></div>'+
      `<div class="report-grid">${items.map(([title,text])=>`<button class="report-card" data-action="previewFeature" data-title="${esc(title)}" data-text="${esc(text)}"><span class="tile-icon">${icon('grid')}</span><b>${esc(title)}</b><small>${esc(text)}</small><span class="meta">Открыть макет →</span></button>`).join('')}</div>`);
  };

  let newsFilter='all';
  const safeNewsUrl=value=>{try{const u=new URL(value);return u.protocol==='https:'&&['seller.ozon.ru','seller.wildberries.ru'].includes(u.hostname)&&(!u.port||u.port==='443')&&!u.username&&!u.password?u.href:null;}catch{return null;}};
  async function renderNews(){
    const root=$('content');if(!root)return;
    let items=[],unavailable=false;
    if(S.stage3&&S.company){try{items=await productionGet('marketplace-news?source='+encodeURIComponent(newsFilter)+'&limit=50');}catch{unavailable=true;}}
    const tabs=[['all','Все'],['ozon','Ozon'],['wildberries','Wildberries']].map(([key,label])=>`<button class="${newsFilter===key?'active':''}" type="button" data-action="newsFilter" data-filter="${key}">${label}</button>`).join('');
    const cards=items.map(item=>{const url=safeNewsUrl(item.url);const source=item.source==='ozon'?'Ozon':'Wildberries';const dateText=item.published_at?new Date(item.published_at).toLocaleDateString('ru-RU'):'Дата не указана';return `<article class="news-card"><div class="row between"><span class="market-badge">${esc(source)}</span><span class="meta">${esc(dateText)}</span></div>${item.is_regulation?'<span class="badge">Нормативное</span>':''}<h3>${esc(item.title)}</h3><p>${esc(item.body)}</p>${url?`<a class="btn secondary" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Открыть первоисточник</a>`:'<span class="meta">Ссылка источника недоступна</span>'}</article>`;}).join('');
    const launchers='<div class="mini-actions marketplace-launchers"><a class="btn secondary" href="https://seller.ozon.ru/" target="_blank" rel="noopener noreferrer">Открыть Ozon Seller</a><a class="btn secondary" href="https://seller.wildberries.ru/" target="_blank" rel="noopener noreferrer">Открыть Wildberries Seller</a></div>';
    paint(heading('Новости','Официальные публикации Ozon и Wildberries',items.length?'LIVE':'' )+launchers+`<div class="segmented">${tabs}</div><div class="list">${cards||`<p class="empty">${unavailable?'Новости сейчас недоступны. Попробуйте позже.':'Пока нет опубликованных новостей. Источник ещё не подключён.'}</p>`}</div>`);
  }
  screens.news=renderNews;
  actions.newsFilter=async button=>{newsFilter=button.dataset.filter;await renderNews();};
  screens.excelImport=async()=>{
    const steps=[
      ['1','Получить шаблон','Компания · Сотрудники · Клиенты · Операции/Тарифы'],
      ['2','Заполнить','Файл можно подготовить на телефоне или компьютере'],
      ['3','Загрузить','Выбрать заполненный XLSX'],
      ['4','Предпросмотр','PORTAL покажет все изменения до записи'],
      ['5','Проверка','Валидация, права и защита от дублей'],
      ['6','Подтверждение','Транзакционное применение только к выбранной компании']
    ];
    paint(heading('Импорт / экспорт Excel','Безопасный мастер массовой загрузки',previewBadge)+
      `<div class="step-list">${steps.map(([n,t,d])=>`<div class="step-card"><span class="step-number">${n}</span><div><b>${esc(t)}</b><p class="meta">${esc(d)}</p></div></div>`).join('')}</div>`+
      `<div class="card"><h3>Действия</h3><div class="stack">${btn('Скачать стандартный шаблон','previewFeature','data-title="Шаблон Excel" data-text="Сохранение на устройство, системное меню «Поделиться» и отправка на email."','secondary block')}${btn('Загрузить заполненный XLSX','previewFeature','data-title="Загрузка Excel" data-text="После выбора файла откроется Preview → Validate → Confirm → Commit."','secondary block')}</div></div>`);
  };

  screens.wms=async()=>{
    const flows=['Приёмка','Размещение','Перемещение','Подбор','Сборка','Упаковка','Маркировка','Отгрузка','FBS','FBO','Возвраты','Инвентаризация'];
    paint(heading('WMS / ТСД','PORTAL ↔ TalAnt · складские операции',previewBadge)+
      '<div class="scanner-preview"><span class="scanner-icon">'+icon('box')+'</span><div><span class="eyebrow">ТСД</span><h2>Сканируйте товар</h2><p class="muted">GTIN · штрихкод · DataMatrix / КИЗ</p></div><span class="badge preview">Без записи</span></div>'+
      `<div class="warehouse-grid">${flows.map(name=>`<button class="warehouse-action" data-action="previewFeature" data-title="${esc(name)}" data-text="Сценарий: задание → сканирование → проверка PORTAL → подтверждение TalAnt → следующий товар."><span>${icon('check')}</span><b>${esc(name)}</b></button>`).join('')}</div>`+
      '<div class="notice">TalAnt остаётся WMS-ядром. Preview не обращается напрямую к его базе и не выполняет складские записи.</div>');
  };
  async function portalUpdateControlChannel(){
    const base={id:'portal_update',title:'Обновление PORTAL',description:'Новая APK и описание изменений',page:'about'};
    if(browserClient||typeof window.PortalNative?.checkUpdates!=='function'){
      return {...base,status:'info',count:0,summary:'Проверка версии выполняется в установленном приложении'};
    }
    let state=S.update;
    if(!state||state.state==='checking'){
      try{
        const result=await nativePromise(id=>PortalNative.checkUpdates(id));
        state=PortalCore.updateState(S.metadata||{},result);
        S.update=state;
      }catch{
        state={state:'error',title:'Не удалось проверить обновления',description:'Сервис обновлений недоступен'};
      }
    }
    if(state.state==='available'){
      const version=state.release?.versionName||'новая версия';
      const build=state.release?.buildNumber?` · сборка ${state.release.buildNumber}`:'';
      return {...base,status:'warning',count:1,summary:`Доступна ${version}${build}`};
    }
    if(state.state==='error'||state.state==='unconfigured'){
      return {...base,status:'warning',count:1,summary:state.title||'Проверка обновлений недоступна'};
    }
    if(state.state==='downloading')return {...base,status:'info',count:0,summary:'Обновление загружается'};
    if(state.state==='ready')return {...base,status:'info',count:0,summary:'APK готова к установке'};
    if(state.state==='store')return {...base,status:'ok',count:0,summary:'Обновления управляются App Store'};
    return {...base,status:'ok',count:0,summary:'Установлена последняя версия'};
  }
  function controlChannelHtml(item){
    const labels={ok:'В норме',warning:'Требует внимания',critical:'Ошибка',info:'Инфо'};
    const badge=item.status==='ok'?'green':item.status==='info'?'':'amber';
    const metrics=[];
    if(Number(item.count)>0)metrics.push(`Событий: ${num(item.count)}`);
    if(Number(item.amount)>0)metrics.push(`Сумма: ${rub(item.amount)}`);
    if(item.period_start&&item.period_end)metrics.push(`${date(item.period_start)} — ${date(item.period_end)}`);
    const action=item.page&&can(item.page)?`<button class="btn secondary" data-action="go" data-page="${esc(item.page)}">Открыть</button>`:'';
    return `<article class="item control-channel"><div class="row between"><div class="grow"><b>${esc(item.title||'Канал контроля')}</b><p class="meta">${esc(item.description||'')}</p></div><span class="badge ${badge}">${esc(labels[item.status]||'Статус')}</span></div><p>${esc(item.summary||'')}</p>${metrics.length?`<p class="meta">${metrics.join(' · ')}</p>`:''}${action}</article>`;
  }
  screens.notifications=async()=>{
    let dashboard={attention:[],control_channels:[]};
    if(S.stage3){try{dashboard=await productionGet('today');}catch{}}
    const live=dashboard.attention||[];
    const channels=[...(dashboard.control_channels||[])];
    channels.push(await portalUpdateControlChannel());
    const desired=['material_low','payment_late','not_invoiced','payroll_period','document_error','portal_update'];
    channels.sort((a,b)=>desired.indexOf(a.id)-desired.indexOf(b.id));
    paint(heading('Уведомления','Что требует внимания прямо сейчас','<span class="badge green">LIVE</span>')+
      `<section class="dashboard-section"><div class="section-label"><h2>Текущие события</h2><span class="meta">LIVE</span></div><div class="attention-stack">${attentionHtml(live)}</div></section>`+
      `<section class="dashboard-section"><div class="section-label"><h2>Каналы контроля</h2><span class="meta">LIVE</span></div><div class="list">${channels.map(controlChannelHtml).join('')||'<p class="empty">Нет доступных каналов контроля</p>'}</div></section>`+
      `<section class="dashboard-section"><div class="section-label"><h2>WMS / TalAnt</h2><span class="meta">Preview</span></div>${previewCard('WMS / TalAnt','Ошибки синхронизации и подтверждения')}</section>`);
  };

  screens.clients=async()=>{
    await liveClients();
    if(S.stage3&&allowed('clients.read')){
      const content=$('content'),list=content?.querySelector('.list');
      if(list){
        let history=[],aliasRows=[];
        try{history=await productionGet('client-name-history');}catch{}
        try{aliasRows=await productionGet('client-aliases');}catch{}
        const aliases=new Map(),priorNames=new Map();
        for(const row of history){const values=aliases.get(row.client_id)||[];values.push(row.old_name,row.new_name);aliases.set(row.client_id,values);const prior=priorNames.get(row.client_id)||[];prior.push(row.old_name,row.new_name);priorNames.set(row.client_id,prior);}
        for(const row of aliasRows){const values=aliases.get(row.client_id)||[];values.push(row.alias);aliases.set(row.client_id,values);}
        const rows=[...list.querySelectorAll('.item')].filter(row=>row.querySelector('[data-action="openClient"]'));
        for(const row of rows){
          const id=Number(row.querySelector('[data-action="openClient"]').dataset.id),client=S.clients?.find(item=>item.id===id);
          const names=[client?.name,...(aliases.get(id)||[])].filter(Boolean);
          row.dataset.clientSearch=names.join(' ').toLocaleLowerCase();
          const prior=[...new Set((priorNames.get(id)||[]).filter(name=>name&&name!==client?.name))];
          if(prior.length)row.insertAdjacentHTML('beforeend',`<p class="meta">Ранее: ${prior.map(name=>esc(name)).join(' · ')}</p>`);
        }
        const search=document.createElement('label');search.className='field';search.innerHTML='<span>Клиент или прежнее название</span><input id="clientSearch" type="search" maxlength="200" autocomplete="off">';
        list.before(search);
        const empty=document.createElement('p');empty.className='empty';empty.textContent='Клиенты по этому запросу не найдены';empty.hidden=true;list.after(empty);
        search.querySelector('input').addEventListener('input',()=>{
          const query=search.querySelector('input').value.trim().toLocaleLowerCase();let visible=0;
          for(const row of rows){const match=!query||row.dataset.clientSearch.includes(query);row.hidden=!match;if(match)visible++;}
          empty.hidden=visible>0;
        });
      }
    }
    $('content')?.insertAdjacentHTML('beforeend',`<section class="preview-extension"><div class="section-label"><h2>Client 360°</h2>${previewBadge}</div><div class="mini-actions">
      ${btn('Реквизиты и контакты','previewFeature','data-title="Client 360° · Реквизиты" data-text="ИНН, КПП, БИК, расчётный и корреспондентский счёт, контактное лицо, телефон и email."','secondary')}
      ${btn('Документы','previewFeature','data-title="Client 360° · Документы" data-text="Счета, отчёты и документы клиента с фильтрами и историей."','secondary')}
      ${btn('Финансы','previewFeature','data-title="Client 360° · Финансы" data-text="Выручка, ФОТ, материалы, расходы, прибыль, маржа и дебиторка."','secondary')}
      ${btn('Товары / WMS','previewFeature','data-title="Client 360° · Товары" data-text="Номенклатура, SKU, GTIN, партии и связь с TalAnt."','secondary')}
    </div></section>`);
  };
  screens.users=async()=>{
    await liveUsers();
    $('content')?.insertAdjacentHTML('beforeend',`<section class="preview-extension"><div class="section-label"><h2>Employee 360°</h2>${previewBadge}</div><div class="mini-actions">
      ${btn('Выработка','previewFeature','data-title="Employee 360° · Выработка" data-text="История работы сотрудника по периодам, клиентам и операциям."','secondary')}
      ${btn('Зарплата и выплаты','previewFeature','data-title="Employee 360° · Зарплата" data-text="Начислено, выплачено, остаток, корректировки и сторно."','secondary')}
      ${btn('Задания','previewFeature','data-title="Employee 360° · Задания" data-text="Текущие и завершённые задания, партия и время работы."','secondary')}
      ${btn('Документы','previewFeature','data-title="Employee 360° · Документы" data-text="Расчётные листы и связанные документы сотрудника."','secondary')}
    </div></section>`);
  };

  screens.payroll=async()=>{
    await livePayroll();
    $('content')?.insertAdjacentHTML('beforeend',`<section class="preview-extension"><div class="row between"><div><h2>Расчётный лист A4</h2><p class="meta">Краткая печатная форма без детализации по клиентам и операциям.</p></div>${previewBadge}</div>
      ${btn('Открыть макет расчётного листа','previewFeature','data-title="Расчётный лист A4" data-text="Компания · период · ФИО · итог · дата · подписи: Управляющий компанией → Управляющий подразделением → Сотрудник."','secondary block')}</section>`);
  };

  screens.materials=async()=>{
    await liveMaterials();
    $('content')?.insertAdjacentHTML('beforeend',`<section class="preview-extension"><div class="section-label"><h2>Операции склада</h2>${previewBadge}</div><div class="mini-actions">
      ${btn('Поставка / Приход','previewFeature','data-title="Склад · Приход" data-text="Поставка материала с количеством, ценой и датой."','secondary')}
      ${btn('Взять / Списание','previewFeature','data-title="Склад · Списание" data-text="Сотрудник списывает сам либо менеджер выдаёт материал."','secondary')}
      ${btn('Корректировка','previewFeature','data-title="Склад · Корректировка" data-text="Ручная корректировка остатка с обязательной причиной и аудитом."','secondary')}
      ${btn('История движений','previewFeature','data-title="Склад · История" data-text="Приходы, списания и корректировки по материалу, сотруднику и периоду."','secondary')}
    </div></section>`);
  };

  screens.documents=async()=>{
    await liveDocuments();
    $('content')?.insertAdjacentHTML('beforeend',`<section class="preview-extension"><div class="section-label"><h2>Хранилище документов</h2>${previewBadge}</div><div class="mini-actions">
      ${btn('Папки и фильтры','previewFeature','data-title="Документы · Папки" data-text="Компания → клиент → сотрудник → тип → дата, поиск и права доступа."','secondary')}
      ${btn('PDF','previewFeature','data-title="Документы · PDF" data-text="PDF-счета, расчётные листы и управленческие отчёты."','secondary')}
      ${btn('Поделиться','previewFeature','data-title="Документы · Поделиться" data-text="Сохранить на устройство или открыть системное меню отправки."','secondary')}
      ${btn('Отправить email','previewFeature','data-title="Документы · Email" data-text="Отправка документа на адрес пользователя, директора или указанный email."','secondary')}
    </div></section>`);
  };
})();
