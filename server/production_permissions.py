ROLE_NAMES = {'packer':'Упаковщик','loader':'Грузчик','driver':'Водитель','manager':'Менеджер','director':'Директор',
              'admin':'Управляющий','shift':'Старший смены','accountant':'Бухгалтер'}
# code, group, label, legacy recommended roles metadata.
# The authoritative defaults are ROLE_DEFAULTS below.
CATALOG = [
 ('work.write','Работа','Вносить свою выработку','packer manager director admin'),
 ('tasks.read','Работа','Просматривать рабочие задания','packer manager director admin'),
 ('tasks.manage','Работа','Создавать задания сотрудникам','manager director admin'),
 ('organizer.read','Органайзер','Просматривать свои задачи и напоминания','manager director admin'),
 ('organizer.assign','Органайзер','Ставить задачи разрешённым коллегам','manager director admin'),
 ('organizer.manage','Органайзер','Контролировать задачи компании','director admin'),
 ('organizer.request.create','Органайзер','Создавать запросы директору','manager director admin'),
 ('organizer.request.decide','Органайзер','Рассматривать запросы директору','director admin'),
 ('batches.receive','Работа','Принимать поступление товара','manager director admin'),
 ('work.link','Работа','Привязывать работу без задания к партии','manager director admin'),
 ('users.manage','Сотрудники','Управлять сотрудниками и их правами','director admin'),
 ('access.history.read','Сотрудники','Просматривать историю входов сотрудников','director admin'),
 ('payroll.own','Зарплата','Просматривать свою зарплату','packer manager director admin'),
 ('payroll.all','Зарплата','Видеть зарплату других сотрудников','director admin'),
 ('payroll.close','Зарплата','Закрывать расчётные периоды','director admin'),
 ('payroll.settlement.read','Зарплата','Просматривать расчёты и выплаты','director admin'),
 ('payroll.settlement.payout','Зарплата','Регистрировать выплаты зарплаты','director admin'),
 ('payroll.settlement.correct','Зарплата','Регистрировать корректировки и сторно','director admin'),
 ('chat.read','Команда','Читать внутренний чат компании','manager director admin'),
 ('chat.write','Команда','Писать во внутренний чат компании','manager director admin'),
 ('chat.moderate','Команда','Закреплять сообщения внутреннего чата','manager director admin'),
 ('documents.manage','Документы','Формировать и регистрировать документы компании','director admin'),
 ('imports.manage','Документы','Предпросмотр и применение импорта справочников','director admin'),
 ('clients.read','Клиенты','Просматривать карточки клиентов','manager director admin'),
 ('clients.manage','Клиенты','Изменять справочник клиентов и операций','director admin'),
 ('rates.employee','Тарифы','Изменять тарифы сотрудников','director admin'),
 ('rates.client','Тарифы','Изменять цены для клиентов','manager director admin'),
 ('materials.read','Склад','Просматривать остатки материалов','packer manager director admin'),
 ('materials.use','Склад','Учитывать фактический расход материалов','packer manager director admin'),
 ('invoices.read','Счета и оплаты','Просматривать счета и оплаты','manager director admin'),
 ('invoices.create','Счета и оплаты','Создавать счета на оплату','manager director admin'),
 ('invoices.export','Счета и оплаты','Формировать PDF/XLSX счетов','manager director admin'),
 ('payments.record','Счета и оплаты','Отмечать поступление оплаты','director admin'),
 ('finance.read','Отчёты','Просматривать финансовую аналитику клиентов','manager director admin'),
 ('expenses.read','Расходы','Просматривать расходы компании','manager director admin'),
 ('expenses.manage','Расходы','Вносить расходы компании','director admin'),
 ('analytics.read','Отчёты','Просматривать производительность команды','manager director admin'),
 ('documents.read','Документы','Просматривать документы компании','manager director admin'),
 ('company.settings','Настройки компании','Изменять правила контроля компании','director admin'),
]
CODES = {p[0] for p in CATALOG}
ROLE_ORDER=('packer','loader','driver','manager','director','admin','shift','accountant')
MANAGER_DEFAULTS = {
    'work.write','tasks.read','tasks.manage',
    'organizer.read','organizer.assign','organizer.request.create',
    'batches.receive','work.link','payroll.own',
    'chat.read','chat.write','chat.moderate',
    'clients.read','rates.client',
    'materials.read','materials.use',
    'invoices.read','invoices.create','invoices.export',
    'finance.read','expenses.read','analytics.read','documents.read',
}
PACKER_DEFAULTS = {'tasks.read','work.write','payroll.own','materials.read','materials.use'}
ROLE_DEFAULTS = {
    'director': CODES.copy(),
    'admin': CODES.copy(),
    'manager': MANAGER_DEFAULTS,
    'packer': PACKER_DEFAULTS,
    'loader': PACKER_DEFAULTS,
    'driver': PACKER_DEFAULTS,
    'shift': set(),
    'accountant': set(),
}

def defaults(role):
    return set(ROLE_DEFAULTS.get(role,set()))

def effective(repo, user):
    if user.get('technical_owner'):
        return CODES.copy()
    result = defaults(user['role'])
    record = repo.get('permissions', str(user['id']), required=False)
    for key, enabled in (record or {}).get('overrides', {}).items():
        if enabled: result.add(key)
        else: result.discard(key)
    return result

def require(repo, user, permission):
    if user.get('company_id') != repo.company_id:
        raise PermissionError('Доступ к другой компании запрещён')
    if permission not in effective(repo, user):
        raise PermissionError('Недостаточно прав для этого действия')

def public_catalog():
    return [dict(code=c, group=g, label=l,
                 recommended=[ROLE_NAMES[r] for r in ROLE_ORDER if c in ROLE_DEFAULTS[r]])
            for c,g,l,_ in CATALOG]
