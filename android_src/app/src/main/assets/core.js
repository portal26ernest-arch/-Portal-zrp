'use strict';
// Presentation capabilities; the server remains the security authority.
globalThis.PortalCore = (() => {
  const roles = {admin:'Администратор',director:'Директор',manager:'Менеджер',packer:'Сотрудник',shift:'Старший смены',accountant:'Бухгалтер',platform_owner:'God'};
  const modules = [
    {id:'work',title:'Выработка',icon:'plus',description:'Записать работу'},
    {id:'payroll',title:'Зарплата',icon:'wallet',description:'Начисления и выплаты'},
    {id:'payrollPeriods',title:'Расчётные периоды',icon:'wallet',description:'Предпросмотр и закрытие зарплаты',production:true},
    {id:'teamChat',title:'Команда',icon:'users',description:'Внутренний чат сотрудников',production:true},
    {id:'clients',title:'Клиенты',icon:'clients',description:'Клиенты и операции'},
    {id:'materials',title:'Склад',icon:'box',description:'Материалы и остатки'},
    {id:'invoices',title:'Счета и оплаты',icon:'receipt',description:'Оплаты и задолженность'},
    {id:'users',title:'Сотрудники',icon:'users',description:'Роли и доступ'},
    {id:'jobs',title:'Задания',icon:'check',description:'Ход производства'},
    {id:'batches',title:'Партии и задания',icon:'box',description:'Приёмка и ход работ',production:true},
    {id:'permissions',title:'Права сотрудников',icon:'shield',description:'Индивидуальные разрешения',production:true},
    {id:'tariffs',title:'Тарифы',icon:'receipt',description:'Две цены и история',production:true},
    {id:'radar',title:'Финансы',icon:'wallet',description:'Финансовый радар и себестоимость',production:true},
    {id:'expenses',title:'Расходы',icon:'receipt',description:'Аренда, логистика и прочие расходы',production:true},
    {id:'analytics',title:'PORTAL Аналитика',icon:'grid',description:'Темп и динамика',production:true},
    {id:'control',title:'Контроль PORTAL',icon:'bell',description:'Правила счетов и оплат',production:true},
    {id:'documents',title:'Документы',icon:'file',description:'Документы компании',production:true},
    {id:'reports',title:'Отчёты',icon:'grid',description:'Каталог управленческих отчётов',preview:true},
    {id:'news',title:'Новости',icon:'bell',description:'Ozon и Wildberries',preview:true},
    {id:'excelImport',title:'Импорт Excel',icon:'file',description:'Шаблон, проверка и загрузка',production:true},
    {id:'wms',title:'WMS / ТСД',icon:'box',description:'Сканирование и складские операции',preview:true},
    {id:'notifications',title:'Уведомления',icon:'bell',description:'Что требует внимания',preview:true}
  ];
  function can(page,user,company) {
    if (['about','settings'].includes(page)) return true;
    if (company?.module_toggles?.[page] === false) return false;
    if (!user || !roles[user.role]) return false;
    if (Array.isArray(user.permissions) && (user.role!=='platform_owner'||company)) {
      if(page==='excelImport'){
        const needed=['imports.manage','users.manage','clients.manage','rates.employee','rates.client','company.settings','documents.manage','documents.read'];
        return ['admin','director','platform_owner'].includes(user.role)&&needed.every(p=>user.permissions.includes(p));
      }
      const map={work:['work.write','tasks.read'],payroll:['payroll.own'],payrollPeriods:['payroll.all','payroll.close'],teamChat:['chat.read'],clients:['clients.read'],catalogue:['clients.manage'],materials:['materials.read'],invoices:['invoices.read'],users:['users.manage'],jobs:['tasks.read'],batches:['batches.receive','tasks.read','work.write'],permissions:['users.manage'],tariffs:['rates.employee','rates.client'],radar:['finance.read'],expenses:['expenses.read','expenses.manage'],analytics:['analytics.read','work.write'],documents:['documents.read','documents.manage'],reports:['finance.read','analytics.read'],control:['company.settings'],news:['chat.read','clients.read','tasks.read'],wms:['tasks.read','batches.receive','work.write'],notifications:['tasks.read','invoices.read','materials.read','payroll.own']};
      if(map[page])return map[page].some(p=>user.permissions.includes(p));
      if(['dashboard','sections'].includes(page))return true;
    }
    if(['batches','permissions','tariffs','radar','expenses','analytics','control','payrollPeriods','teamChat','documents'].includes(page))return false;
    if(page==='catalogue')return ['admin','director'].includes(user.role)||user.role==='platform_owner'&&!!company;
    if (user.role==='platform_owner') {
      if (['companies','audit'].includes(page)) return true;
      return !!company && ['dashboard','sections','clients','materials','invoices','users','jobs','reports','news','excelImport','wms','notifications'].includes(page);
    }
    if (['dashboard','sections','jobs','news','notifications'].includes(page)) return true;
    if (page==='work') return !!user.employee_id && ['admin','director','manager','packer','shift'].includes(user.role);
    if (page==='payroll') return !!user.employee_id;
    if (page==='clients') return user.role!=='packer';
    if (page==='materials') return ['admin','director','accountant','shift'].includes(user.role);
    if (page==='invoices') return ['admin','director','manager','accountant'].includes(user.role);
    if (page==='reports') return ['admin','director','manager','accountant','shift'].includes(user.role);
    if (page==='excelImport') return false;
    if (page==='wms') return ['admin','director','manager','packer','shift'].includes(user.role);
    return page==='users' && ['admin','director'].includes(user.role);
  }
  function timeGreeting(value=new Date()) {
    const hour=value instanceof Date?value.getHours():Number(value);
    if(!Number.isInteger(hour)||hour<0||hour>23)throw new RangeError('hour must be 0..23');
    if(hour>=5&&hour<12)return 'Доброе утро';
    if(hour>=12&&hour<18)return 'Добрый день';
    if(hour>=18&&hour<23)return 'Добрый вечер';
    return 'Доброй ночи';
  }
  function updateState(current,result) {
    if (!result || !result.ok) return {state:'error',title:'Не удалось проверить обновления',description:'Сервис обновлений недоступен. Попробуйте позже.'};
    if (!result.configured) return {state:'unconfigured',title:'Проверка пока недоступна',description:'Официальный источник обновлений ещё не подключён.'};
    const m=result.manifest;
    const versionOk=m && typeof m.versionName==='string' && /^[A-Za-z0-9._-]{1,80}$/.test(m.versionName);
    const expectedApkUrl=versionOk?'https://github.com/portal26ernest-arch/-Portal-zrp/releases/download/portal-android-v'+m.versionName+'/PORTAL_Android_'+m.versionName+'_release.apk':'';
    const valid=m && m.schemaVersion===1 && m.applicationId===current.applicationId && m.channel===current.channel
      && Number.isSafeInteger(m.versionCode) && m.versionCode>0 && versionOk
      && typeof m.buildNumber==='string' && /^[A-Za-z0-9._-]{1,40}$/.test(m.buildNumber) && typeof m.publishedAt==='string'
      && m.publishedAt.length<=40 && /^\d{4}-\d{2}-\d{2}T.*Z$/.test(m.publishedAt) && Number.isFinite(Date.parse(m.publishedAt))
      && typeof m.changelog==='string' && m.changelog.length<=4000
      && typeof m.apkUrl==='string' && m.apkUrl===expectedApkUrl
      && typeof m.sha256==='string' && /^[0-9a-f]{64}$/i.test(m.sha256);
    if (!valid || !Number.isSafeInteger(current.versionCode)) return {state:'error',title:'Не удалось проверить обновления',description:'Источник вернул неподходящие данные.'};
    if (m.versionCode<=current.versionCode) return {state:'latest',title:'Установлена последняя версия',description:'Для вашего канала обновлений новых сборок нет.'};
    return {state:'available',title:'Доступна новая версия',description:'Установка будет доступна через официальный канал распространения.',release:m};
  }
  return Object.freeze({roles,modules,can,timeGreeting,updateState});
})();
