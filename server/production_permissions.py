"""Business capabilities. No platform authority can be delegated here."""
ROLE_NAMES = {'packer':'Сборщик','manager':'Менеджер','director':'Директор',
              'admin':'Администратор','shift':'Старший смены','accountant':'Бухгалтер'}
# code, group, label, recommended roles
CATALOG = [
 ('work.write','Работа','Вносить свою выработку','packer manager director admin shift'),
 ('tasks.read','Работа','Просматривать рабочие задания','packer manager director admin shift'),
 ('tasks.manage','Работа','Создавать задания сотрудникам','manager director admin shift'),
 ('batches.receive','Работа','Принимать поступление товара','manager director admin'),
 ('work.link','Работа','Привязывать работу без задания к партии','manager director admin'),
 ('users.manage','Сотрудники','Управлять сотрудниками и их правами','director admin'),
 ('access.history.read','Сотрудники','Просматривать историю входов сотрудников','director admin'),
 ('payroll.own','Зарплата','Просматривать свою зарплату','packer manager director admin shift accountant'),
 ('payroll.all','Зарплата','Видеть зарплату других сотрудников','director admin accountant'),
 ('clients.read','Клиенты','Просматривать карточки клиентов','manager director admin accountant shift'),
 ('clients.manage','Клиенты','Изменять справочник клиентов и операций','director admin'),
 ('rates.employee','Тарифы','Изменять тарифы сотрудников','director admin'),
 ('rates.client','Тарифы','Изменять цены для клиентов','manager director admin'),
 ('materials.read','Склад','Просматривать остатки материалов','director admin shift accountant'),
 ('materials.use','Склад','Учитывать фактический расход материалов','director admin shift'),
 ('invoices.read','Счета и оплаты','Просматривать счета и оплаты','manager director admin accountant'),
 ('invoices.create','Счета и оплаты','Создавать счета на оплату','manager director admin accountant'),
 ('payments.record','Счета и оплаты','Отмечать поступление оплаты','director admin accountant'),
 ('finance.read','Отчёты','Просматривать финансовую аналитику клиентов','director admin accountant'),
 ('analytics.read','Отчёты','Просматривать производительность команды','manager director admin'),
 ('documents.read','Документы','Просматривать документы компании','manager director admin accountant'),
 ('company.settings','Настройки компании','Изменять правила контроля компании','director admin'),
]
CODES = {p[0] for p in CATALOG}

def defaults(role):
    return {code for code, _, _, roles in CATALOG if role in roles.split()}

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
    return [dict(code=c, group=g, label=l, recommended=[ROLE_NAMES[r] for r in roles.split()])
            for c,g,l,roles in CATALOG]
