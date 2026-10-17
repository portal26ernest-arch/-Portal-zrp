'use strict';

const centerLabels={TASKS:'Задачи',ORGANIZER:'Органайзер'};
screens.notifications=async()=>{
  const response=await api('GET','/api/v3/notification-centers');
  const centers=response.data||[];
  const cards=centers.filter(center=>center.center==='TASKS'||center.center==='ORGANIZER').map(center=>`<section class="card notification-center" id="center-${center.center}"><div class="row between"><div><span class="eyebrow">Центр уведомлений</span><h2>${centerLabels[center.center]||esc(center.center)}</h2></div><span class="badge ${center.unread_count?'amber':'green'}">${num(center.unread_count)} непрочитано</span></div><div class="list">${center.items.map(item=>`<article class="item"><div class="row between"><b>${esc(item.title)}</b>${item.read?'<span class="badge green">Прочитано</span>':btn('Отметить прочитанным','markNotificationRead',`data-center="${center.center}" data-item-id="${esc(item.id)}"`,'secondary')}</div></article>`).join('')||'<p class="empty">Новых уведомлений нет</p>'}</div></section>`).join('');
  paint(heading('Центры уведомлений','Независимый статус прочтения для каждого пользователя')+`<div class="notification-centers">${cards}</div>`);
  if(S.notificationCenter)document.getElementById(`center-${S.notificationCenter}`)?.scrollIntoView({block:'start',behavior:'smooth'});
};
