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
  const response=await api('GET','/api/v3/messenger');
  const data=response.data||{accounts:[],conversations:[],adapters:{}};
  const accounts=data.accounts||[];
  paint(heading('Messenger','Личные рабочие аккаунты Telegram и MAX',btn('Добавить аккаунт','addMessengerAccount','','secondary'))+
    `<section class="card"><p class="muted">Подключение выполняется через официальные API адаптеры после настройки серверных секретов. Пароли и токены не вводятся в PORTAL.</p><div class="list">${accounts.map(account=>`<article class="item"><div class="row between"><b>${esc(account.label)}</b><span class="badge amber">Адаптер не настроен</span></div><p class="meta">${account.platform==='telegram'?'Telegram':'MAX'} · Личный рабочий аккаунт</p></article>`).join('')||'<div class="empty">Личные аккаунты ещё не добавлены</div>'}</div></section>`+
    `<section class="card"><h2>Беседы</h2><div class="list">${(data.conversations||[]).map(row=>`<article class="item"><b>${esc(row.title)}</b><p class="meta">${row.platform==='telegram'?'Telegram':'MAX'} · ${esc(row.connection_state)}</p></article>`).join('')||'<div class="empty">Бесед пока нет</div>'}</div></section>`);
};

actions.addMessengerAccount=()=>openSheet('Добавить личный рабочий аккаунт',`${selectField('messengerPlatform','Платформа','<option value="telegram">Telegram</option><option value="max">MAX</option>')}${field('messengerLabel','Название аккаунта','','text','maxlength="80" autocomplete="off"')}${btn('Добавить','createMessengerAccount','','block')}`);
