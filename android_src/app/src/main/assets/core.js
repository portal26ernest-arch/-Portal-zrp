'use strict';
// Presentation capabilities; the server remains the security authority.
globalThis.PortalCore = (() => {
  const roles = {admin:'Администратор',director:'Директор',manager:'Менеджер',packer:'Сотрудник',shift:'Старший смены',accountant:'Бухгалтер',platform_owner:'Platform Owner'};
  const modules = [
    {id:'work',title:'Выработка',icon:'plus',description:'Записать работу'},
    {id:'payroll',title:'Зарплата',icon:'wallet',description:'Начисления и выплаты'},
    {id:'clients',title:'Клиенты',icon:'clients',description:'Клиенты и операции'},
    {id:'materials',title:'Склад',icon:'box',description:'Материалы и остатки'},
    {id:'invoices',title:'Счета',icon:'receipt',description:'Оплаты и задолженность'},
    {id:'users',title:'Сотрудники',icon:'users',description:'Роли и доступ'},
    {id:'jobs',title:'Задания',icon:'check',description:'Ход производства'},
    {id:'batches',title:'Партии / задания',icon:'box',description:'Приёмка и готовность',production:true},
    {id:'permissions',title:'Права сотрудников',icon:'shield',description:'Индивидуальные разрешения',production:true},
    {id:'tariffs',title:'Тарифы',icon:'receipt',description:'Две цены и история',production:true},
    {id:'radar',title:'Финансовый радар',icon:'wallet',description:'Себестоимость и прибыль',production:true},
    {id:'analytics',title:'PORTAL Аналитика',icon:'grid',description:'Темп и динамика',production:true},
    {id:'control',title:'Контроль PORTAL',icon:'bell',description:'Правила счетов и оплат',production:true},
    {id:'documents',title:'Документы',icon:'file',future:true},
    {id:'news',title:'Новости',icon:'bell',future:true}
  ];
  function can(page,user,company) {
    if (['about','settings'].includes(page)) return true;
    if (!user || !roles[user.role]) return false;
    if (Array.isArray(user.permissions) && (user.role!=='platform_owner'||company)) {
      const map={work:['work.write','tasks.read'],payroll:['payroll.own'],clients:['clients.read'],catalogue:['clients.manage'],materials:['materials.read'],invoices:['invoices.read'],users:['users.manage'],jobs:['tasks.read'],batches:['batches.receive','tasks.read','work.write'],permissions:['users.manage'],tariffs:['rates.employee','rates.client'],radar:['finance.read'],analytics:['analytics.read','work.write'],control:['company.settings']};
      if(map[page])return map[page].some(p=>user.permissions.includes(p));
      if(['dashboard','sections'].includes(page))return true;
    }
    if(['batches','permissions','tariffs','radar','analytics','control'].includes(page))return false;
    if(page==='catalogue')return user.role==='admin'||user.role==='platform_owner'&&!!company;
    if (user.role==='platform_owner') {
      if (['companies','audit'].includes(page)) return true;
      return !!company && ['dashboard','sections','clients','materials','invoices','users','jobs'].includes(page);
    }
    if (['dashboard','sections','jobs'].includes(page)) return true;
    if (page==='work') return !!user.telegram_id && ['admin','director','manager','packer','shift'].includes(user.role);
    if (page==='payroll') return !!user.telegram_id;
    if (page==='clients') return user.role!=='packer';
    if (page==='materials') return ['admin','director','accountant','shift'].includes(user.role);
    if (page==='invoices') return ['admin','director','manager','accountant'].includes(user.role);
    return page==='users' && user.role==='admin';
  }
  function updateState(current,result) {
    if (!result || !result.ok) return {state:'error',title:'Не удалось проверить обновления',description:'Сервис обновлений недоступен. Попробуйте позже.'};
    if (!result.configured) return {state:'unconfigured',title:'Проверка пока недоступна',description:'Официальный источник обновлений ещё не подключён.'};
    const m=result.manifest;
    const valid=m && m.schemaVersion===1 && m.applicationId===current.applicationId && m.channel===current.channel
      && Number.isSafeInteger(m.versionCode) && m.versionCode>0 && typeof m.versionName==='string' && m.versionName.length<=80
      && typeof m.buildNumber==='string' && m.buildNumber.length<=40 && typeof m.publishedAt==='string'
      && /^\d{4}-\d{2}-\d{2}(?:T.*)?$/.test(m.publishedAt) && Number.isFinite(Date.parse(m.publishedAt))
      && typeof m.changelog==='string' && m.changelog.length<=4000;
    if (!valid || !Number.isSafeInteger(current.versionCode)) return {state:'error',title:'Не удалось проверить обновления',description:'Источник вернул неподходящие данные.'};
    if (m.versionCode<=current.versionCode) return {state:'latest',title:'Установлена последняя версия',description:'Для вашего канала обновлений новых сборок нет.'};
    return {state:'available',title:'Доступна новая версия',description:'Установка будет доступна через официальный канал распространения.',release:m};
  }
  return Object.freeze({roles,modules,can,updateState});
})();
