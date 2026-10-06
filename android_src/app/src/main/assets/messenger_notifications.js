'use strict';

const centerLabels={TASKS:'Задачи',MESSENGER:'Messenger',ORGANIZER:'Органайзер'};
screens.notifications=async()=>{
  const response=await api('GET','/api/v3/notification-centers');
  const centers=response.data||[];
  const cards=centers.map(center=>`<section class="card notification-center" id="center-${center.center}"><div class="row between"><div><span class="eyebrow">Центр уведомлений</span><h2>${centerLabels[center.center]||esc(center.center)}</h2></div><span class="badge ${center.unread_count?'amber':'green'}">${num(center.unread_count)} непрочитано</span></div><div class="list">${center.items.map(item=>`<article class="item"><div class="row between"><b>${esc(item.title)}</b>${item.read?'<span class="badge green">Прочитано</span>':btn('Отметить прочитанным','markNotificationRead',`data-center="${center.center}" data-item-id="${esc(item.id)}"`,'secondary')}</div></article>`).join('')||'<p class="empty">Новых уведомлений нет</p>'}</div></section>`).join('');
  paint(heading('Центры уведомлений','Независимый статус прочтения для каждого пользователя')+`<div class="notification-centers">${cards}</div>`);
  if(S.notificationCenter)document.getElementById(`center-${S.notificationCenter}`)?.scrollIntoView({block:'start',behavior:'smooth'});
};

screens.messenger=async()=>{
  let data={accounts:[],conversations:[],adapters:{telegram:'unconfigured',max:'unconfigured'}};
  let serverMessengerAvailable=false;
  try{const response=await api('GET','/api/v3/messenger');data=response.data||data;serverMessengerAvailable=true;}catch{}
  const accounts=data.accounts||[];
  const serverControls=serverMessengerAvailable
    ? `<section class="card"><div class="row between"><div><span class="eyebrow">Серверный Messenger</span><h2>Метаданные рабочих аккаунтов</h2></div>${btn('Добавить аккаунт','addMessengerAccount','','secondary')}</div><p class="muted">Этот контур хранит только разрешённые metadata. Пароли, коды, cookies и web-сессии Telegram/MAX сюда не передаются.</p><div class="list">${accounts.map(account=>`<article class="item"><div class="row between"><b>${esc(account.label)}</b><span class="badge amber">${esc(((data.adapters||{})[account.platform]==='unconfigured'||!(data.adapters||{})[account.platform])?'Адаптер не настроен':'Адаптер подключён')}</span></div><p class="meta">${account.platform==='telegram'?'Telegram':'MAX'} · Личный рабочий аккаунт</p></article>`).join('')||'<div class="empty">Личные аккаунты ещё не добавлены</div>'}</div></section>`+
      `<section class="card"><h2>Беседы</h2><div class="list">${(data.conversations||[]).map(row=>`<article class="item"><b>${esc(row.title)}</b><p class="meta">${row.platform==='telegram'?'Telegram':'MAX'} · ${esc(row.connection_state)}</p></article>`).join('')||'<div class="empty">Бесед пока нет</div>'}</div></section>`
    : `<section class="card"><span class="badge amber">Серверная синхронизация ещё не активирована</span><p class="muted" style="margin-top:10px">Это не мешает пользоваться Telegram и MAX внутри PORTAL. Вход выполняется кнопками выше напрямую в официальных клиентах. Кнопка добавления server-metadata скрыта, пока production backend не поддерживает Messenger API.</p></section>`;
  paint(heading('Messenger','Telegram + MAX · личные рабочие аккаунты')+
    `<section class="card"><div class="row between"><div><span class="eyebrow">Официальные клиенты</span><h2>Telegram + MAX</h2></div></div><p class="muted">Вход выполняется только внутри официальных веб-клиентов. PORTAL не запрашивает и не передаёт пароли, коды, cookies или provider-сессии на сервер.</p><div class="mini-actions">${btn('Открыть Telegram','openMessengerProvider','data-provider="telegram"')}${btn('Открыть MAX','openMessengerProvider','data-provider="max"','secondary')}</div></section>`+serverControls);
};

actions.addMessengerAccount=()=>openSheet('Добавить личный рабочий аккаунт',`${selectField('messengerPlatform','Платформа','<option value="telegram">Telegram</option><option value="max">MAX</option>')}${field('messengerLabel','Название аккаунта','','text','maxlength="80" autocomplete="off"')}${btn('Добавить','createMessengerAccount','','block')}`);
