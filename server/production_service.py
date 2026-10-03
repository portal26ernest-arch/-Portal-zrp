"""Production domain. Integer minor currency units; append-only accounting facts.
No SQLite imports or SQL: the repository is the persistence/legacy boundary.
"""
import base64
import calendar
import copy
import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from production_repository import utcnow
from report_xlsx import payroll_xlsx
import production_permissions as rights

ORGANIZER_ROLE_LABELS={'director':'Директор','admin':'Управляющий','manager':'Менеджер'}
ORGANIZER_ASSIGNABLE={'director':{'admin','manager'},'admin':{'manager'},'manager':{'manager'}}
ORGANIZER_PRIORITIES={'normal','important','urgent'}
ORGANIZER_REPEATS={'none','daily','weekly','monthly'}
ORGANIZER_STATUSES={'new','in_progress','done','cancelled'}
ORGANIZER_REQUEST_TYPES={'materials_purchase','equipment_purchase','repair','expense','tariff_change','hr','other'}
ORGANIZER_REQUEST_STATUSES={'new','review','approved','rejected','needs_info','done'}
ORGANIZER_REQUEST_TRANSITIONS={
    'new':{'review'},
    'review':{'approved','rejected','needs_info'},
    'needs_info':{'review','rejected'},
    'approved':{'review','done'},
    'rejected':{'review'},
    'done':set(),
}

def text(value, name='Название', optional=False):
    if optional and value in (None,''): return ''
    if not isinstance(value,str) or not value.strip() or len(value)>1000: raise ValueError(name+': укажите текст до 1000 символов')
    return value.strip()

def qty(value):
    if type(value) is not int or not 1<=value<=1000000: raise ValueError('Количество: целое число от 1 до 1 000 000')
    return value

def cents(value):
    try:
        if isinstance(value,bool): raise ValueError()
        n=Decimal(str(value))
        if not n.is_finite() or n<0 or n>Decimal('1000000000'): raise ValueError()
        return int((n*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
    except (ValueError,InvalidOperation): raise ValueError('Цена должна быть неотрицательным числом')

def settlement_cents(value, signed=False):
    """Exact rubles at the API boundary; no float conversion or silent rounding."""
    if type(value) is int:
        value=str(value)
    if not isinstance(value,str) or not re.fullmatch(r'-?(?:[0-9]+(?:\.[0-9]{1,2})?|\.[0-9]{1,2})',value) or len(value)>32:
        raise ValueError('Сумма: число в рублях с точностью до двух знаков после точки')
    amount=Decimal(value)*100
    if amount==0 or abs(amount)>100_000_000_000 or (not signed and amount<0):
        raise ValueError('Сумма должна быть ненулевой, не более 1 000 000 000 рублей; выплата — положительной')
    return int(amount)

def margin_basis_points(profit, revenue):
    """Return a rounded integer percent in basis points; missing/zero revenue is unavailable."""
    if profit is None or revenue is None or revenue <= 0:
        return None
    sign=-1 if profit<0 else 1
    numerator=abs(profit)*10000
    return sign*((numerator*2+revenue)//(2*revenue))

def request_identity(value):
    if not isinstance(value,str) or not 1<=len(value)<=128 or value.strip()!=value:
        raise ValueError('Идентификатор запроса: от 1 до 128 символов без пробелов по краям')
    return value

def employee_id(user):
    # Runtime identity is supplied by the authenticated, tenant-scoped adapter.
    # A missing canonical ID fails closed; historical IDs never cross this layer.
    return user.get('employee_id')

def stamp(value, optional=False):
    if optional and not value: return None
    try:
        dt=datetime.fromisoformat(value)
        if dt.tzinfo: raise ValueError()
        return dt.isoformat(timespec='microseconds')
    except (ValueError,TypeError): raise ValueError('Дата: ISO 8601, UTC без смещения')

def company_date(value, utc_offset_minutes):
    """Interpret a stored UTC/date value in the company's configured timezone."""
    if not isinstance(value,str) or not value:
        raise ValueError('Некорректная дата')
    parsed=datetime.fromisoformat(value)
    if len(value)==10 and parsed.tzinfo is None:return parsed.date()
    zone=timezone(timedelta(minutes=utc_offset_minutes))
    return parsed.astimezone(zone).date() if parsed.tzinfo else (parsed+timedelta(minutes=utc_offset_minutes)).date()

class Production:
    def __init__(self, repo, user, clock=utcnow):
        self.r,self.u,self.clock=repo,user,clock
        if user.get('company_id')!=repo.company_id: raise PermissionError('Другая компания')
        self.permissions=rights.effective(repo,user)

    def need(self,p): rights.require(self.r,self.u,p)

    def need_management_role(self):
        if not self.u.get('technical_owner') and self.u.get('role') not in {'director','admin'}:
            raise PermissionError('Управленческие настройки доступны только директору или управляющему')

    def visible(self,client_id):
        # Assignment scope is independent of individually granted capabilities.
        if self.u['role']!='manager' or self.u.get('technical_owner'): return True
        return any(a['client_id']==client_id and a['active'] and a['employee_id']==employee_id(self.u) for a in self.r.catalog('assignments'))

    def client(self,identity,active=False):
        c=next((c for c in self.r.catalog('clients') if c['id']==identity and self.visible(identity)),None)
        if not c or (active and not c['active']): raise PermissionError('Клиент недоступен')
        return c

    CLIENT_REQUISITE_FIELDS=('legal_name','inn','kpp','ogrn','legal_address','settlement_account',
        'bank_name','bik','correspondent_account','phone','email','contact_person','tax_info')

    def _client_requisites(self,client_id):
        self.client(client_id)
        if not self.r.has_table('portal_client_requisites'):return {}
        fields=(*self.CLIENT_REQUISITE_FIELDS,'updated_at')
        row=self.r.sql('SELECT '+','.join(fields)+' FROM portal_client_requisites WHERE company_id=? AND client_id=?',
                       (self.r.company_id,client_id)).fetchone()
        return dict(zip(fields,row)) if row else {}

    def client_requisites(self,params):
        self.need('clients.read')
        raw=params.get('client_id',[None])[0]
        try:client_id=int(raw)
        except (TypeError,ValueError):raise ValueError('Укажите корректного клиента')
        return self._client_requisites(client_id)

    def save_client_requisites(self,b):
        self.need('clients.manage')
        if set(b)-{'company_id','client_id','request_id',*self.CLIENT_REQUISITE_FIELDS}:
            raise ValueError('Неизвестные поля реквизитов клиента')
        identity=b.get('client_id')
        if type(identity) is not int or identity<1:raise ValueError('Укажите корректного клиента')
        self.client(identity)
        if not self.r.has_table('portal_client_requisites'):
            raise ValueError('Сначала примените миграцию реквизитов клиентов')
        old=self._client_requisites(identity)
        values=dict(old)
        for key in self.CLIENT_REQUISITE_FIELDS:
            if key not in b:continue
            value=b[key]
            if value is None:value=''
            if not isinstance(value,str):raise ValueError('Реквизиты должны быть текстом')
            values[key]=text(value,key,optional=True)
        if not any(key in b for key in self.CLIENT_REQUISITE_FIELDS):
            raise ValueError('Укажите данные для изменения')
        columns=('company_id','client_id',*self.CLIENT_REQUISITE_FIELDS,'updated_at','updated_by')
        updates=','.join(key+'=excluded.'+key for key in (*self.CLIENT_REQUISITE_FIELDS,'updated_at','updated_by'))
        self.r.sql('INSERT INTO portal_client_requisites('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+') '
                   'ON CONFLICT(company_id,client_id) DO UPDATE SET '+updates,
                   (self.r.company_id,identity,*(values.get(key,'') for key in self.CLIENT_REQUISITE_FIELDS),self.clock(),self.u['id']))
        return dict(client_id=identity,**{key:values.get(key,'') for key in self.CLIENT_REQUISITE_FIELDS})

    def entity(self,kind,identity):
        obj=self.r.get(kind,identity)
        if 'client_id' in obj: self.client(obj['client_id'])
        return obj

    def invoice_current(self,identity):
        invoice=self.entity('invoices',identity)
        revisions=sorted(self.r.list_by('invoice_revisions',invoice_id=invoice['id']),key=lambda r:r['revision'])
        history=[dict(revision=1,state='finalized',snapshot={k:invoice[k] for k in ('work_ids','lines','amount','due_at')})]
        history.extend(dict(revision=r['revision'],state=r['state'],snapshot=r['snapshot']) for r in revisions if r['state']=='finalized')
        if revisions:
            latest=revisions[-1]
            historical=history if latest['state']=='editing' else history[:-1]
            invoice.update(latest['snapshot'],snapshot=latest['snapshot'],state=latest['state'],revision=latest['revision'],history=historical,revision_history=historical)
        else:invoice.setdefault('state','finalized');invoice.setdefault('revision',1);invoice['history']=[];invoice['revision_history']=history
        return invoice

    def billed_work_ids(self):
        billed={wid for item in self.r.list('invoices') for wid in item['work_ids']}
        billed.update(wid for item in self.r.list('invoice_revisions') for wid in item['snapshot'].get('work_ids',[]))
        return billed

    def operation(self,client_id,identity):
        self.client(client_id,True)
        op=next((o for o in self.r.catalog('operations') if o['id']==identity and o['client_id']==client_id and o['active']),None)
        if not op: raise ValueError('Выберите существующую активную операцию клиента')
        return op

    def tariff(self,operation_id,at=None,tariff_rows=None):
        source_rows=self.r.list_by('tariffs',operation_id=operation_id) if tariff_rows is None else tariff_rows
        versions=[t for t in source_rows if t['operation_id']==operation_id and t['effective_from']<=(at or self.clock())]
        if not versions: raise ValueError('Для операции требуется действующий тариф')
        versions.sort(key=lambda t:(t['effective_from'],t['created_at'],t['id']))
        current=dict(versions[-1],sources={})
        for key in ('employee_rate','client_rate'):
            source=next(t for t in reversed(versions) if key in t.get('changed_fields',('employee_rate','client_rate')))
            current[key]=source[key];current['sources'][key]=source['id']
        return current

    def create_tariff(self,b):
        op=self.operation(b['client_id'],b['operation_id'])
        now=self.clock()
        versions=[t for t in self.r.list_by('tariffs',operation_id=op['id']) if t['effective_from']<=now]
        old=self.tariff(op['id'],now) if versions else None
        values={k:(old[k] if old else None) for k in ('employee_rate','client_rate')}
        changed=False
        for key,permission in [('employee_rate','rates.employee'),('client_rate','rates.client')]:
            if key in b:
                self.need(permission);values[key]=cents(b[key]);changed=True
        if not changed: raise ValueError('Укажите новую ставку или цену')
        if old is None and any(values[k] is None for k in ('employee_rate','client_rate')):
            raise ValueError('Для первого тарифа укажите ставку сотруднику и цену клиенту')
        effective=stamp(b.get('effective_from') or now)
        if effective<self.clock():
            # A small clock gap is allowed only for immediate server-generated time.
            if b.get('effective_from'): raise ValueError('Тариф нельзя вводить задним числом')
        if self.r.list_by('tariffs',operation_id=op['id'],effective_from=effective): raise ValueError('Тариф на эту дату уже есть')
        return self.r.insert('tariffs',dict(operation_id=op['id'],client_id=op['client_id'],effective_from=effective,changed_fields=[k for k in values if k in b],**values))

    def batch(self,b):
        self.need('batches.receive'); c=self.client(b['client_id'],True)
        identity=str(uuid.uuid4())
        product_id=b.get('product_id')
        product=next((item for item in self.r.list_by('products',id=str(product_id))
                      if item['client_id']==c['id'] and item['active']),None) if product_id else None
        if product_id and not product: raise ValueError('Выберите активный товар этого клиента')
        # Company + UUID is globally unambiguous during file -> central DB migration.
        return self.r.insert('batches',dict(number='PRT-'+self.clock()[:4]+'-'+str(self.r.company_id)+'-'+identity.replace('-',''),
            client_id=c['id'],client_name=c['name'],product_id=product['id'] if product else None,
            product=product['name'] if product else text(b.get('product'),'Товар'),
            received_at=stamp(b.get('received_at') or self.clock()),quantity=qty(b.get('quantity')),
            article=text(b.get('article'),optional=True),gtin=text(b.get('gtin'),optional=True),
            comment=text(b.get('comment'),optional=True),external_number=text(b.get('external_number'),optional=True),
            due_at=stamp(b.get('due_at'),True),direction=b.get('direction','undecided'),status='received'),identity)

    def product(self,b):
        action=b.get('action','create')
        if action=='create':
            client=self.client(b.get('client_id'),True)
            name=text(b.get('name'),'Товар')
            if any(p['name'].casefold()==name.casefold() for p in self.r.list_by('products',client_id=client['id'],active=True)):
                raise ValueError('Активный товар с таким названием уже есть у клиента')
            return self.r.insert('products',dict(client_id=client['id'],name=name,active=True))
        product=self.entity('products',b.get('product_id'))
        self.client(product['client_id'],True)
        if action=='archive': product['active']=False
        elif action=='update':
            name=text(b.get('name',product['name']),'Товар')
            if any(p['id']!=product['id'] and p['name'].casefold()==name.casefold() for p in self.r.list_by('products',client_id=product['client_id'],active=True)):
                raise ValueError('Активный товар с таким названием уже есть у клиента')
            product['name']=name
        else: raise ValueError('Неизвестное действие товара')
        return self.r.update('products',product)

    def task(self,b):
        self.need('tasks.manage');batch=self.entity('batches',b['batch_id']);op=self.operation(batch['client_id'],b['operation_id'])
        if batch['status']=='shipped':raise ValueError('Партия уже отгружена')
        target=qty(b['quantity'])
        planned_other=cents(b.get('other_cost',0))
        if planned_other:self.need('finance.read')
        if target!=batch['quantity']: raise ValueError('План обязательной операции должен покрывать всю партию')
        if self.r.list_by('tasks',batch_id=batch['id'],operation_id=op['id']): raise ValueError('Эта операция уже запланирована для партии')
        assignees=b.get('assignees',[])
        if not isinstance(assignees,list) or not assignees or len(assignees)!=len(set(assignees)): raise ValueError('Выберите исполнителей')
        users={u['id']:u for u in self.r.catalog('users')}
        for uid in assignees:
            u=users.get(uid)
            if not u or not u['active'] or not employee_id(u) or 'work.write' not in rights.effective(self.r,u): raise ValueError('Исполнитель не может вносить работу')
            if not Production(self.r,u).visible(batch['client_id']): raise ValueError('Клиент недоступен исполнителю')
        tariff=self.tariff(op['id']);self.valid_rates(tariff)
        norms=self.norms(op['id'],target)
        task=self.r.insert('tasks',dict(batch_id=batch['id'],client_id=batch['client_id'],product=batch['product'],operation_id=op['id'],operation_name=op['name'],quantity=target,assignees=assignees,due_at=stamp(b.get('due_at') or batch['due_at'],True),status='open'))
        self.r.insert('plans',dict(batch_id=batch['id'],task_id=task['id'],client_id=batch['client_id'],quantity=target,tariff_id=tariff['id'],tariff_sources=tariff['sources'],salary=target*tariff['employee_rate'],revenue=target*tariff['client_rate'],materials=sum(n['cost'] for n in norms),other=planned_other,norms=norms))
        return task

    def valid_rates(self,t):
        if t['employee_rate'] is None or t['client_rate'] is None: raise ValueError('Администратор должен задать обе цены операции')

    def norms(self,op_id,quantity):
        materials={m['id']:m for m in self.r.catalog('materials') if m['active']}
        result=[]
        for n in self.r.catalog('norms'):
            if n['operation_id']!=op_id or not n['active']: continue
            m=materials.get(n['material_id'])
            if not m: raise ValueError('Материал норматива недоступен')
            amount=Decimal(str(n['qty_per_unit']))*quantity
            if not amount.is_finite() or amount<0: raise ValueError('Некорректный норматив')
            cost=int((amount*cents(m['unit_cost'] or 0)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
            result.append(dict(material_id=m['id'],quantity=str(amount),norm=str(n['qty_per_unit']),unit_cost=cents(m['unit_cost'] or 0),cost=cost))
        return result

    def batch_for_work(self,w,link_rows=None):
        source=self.r.list_by('links',work_id=w['id']) if link_rows is None else link_rows
        links=[l for l in source if l['work_id']==w['id']]
        return links[-1]['batch_id'] if links else w.get('batch_id')

    def work(self,b):
        self.need('work.write')
        if not employee_id(self.u): raise ValueError('Доступ не связан с сотрудником')
        task=self.entity('tasks',b['task_id']) if b.get('task_id') else None
        if task:
            if self.u['id'] not in task['assignees']: raise PermissionError('Задание назначено другому сотруднику')
            if task['status']=='done': raise ValueError('Задание завершено')
            client_id,op_id,batch_id=task['client_id'],task['operation_id'],task['batch_id']
        else: client_id,op_id,batch_id=b['client_id'],b['operation_id'],b.get('batch_id')
        client=self.client(client_id,True);op=self.operation(client_id,op_id);quantity=qty(b['quantity'])
        batch=self.entity('batches',batch_id) if batch_id else None
        if batch and (batch['client_id']!=client_id or batch['status']=='shipped'): raise ValueError('Партия недоступна для этой работы')
        if task:
            done=sum(w['quantity'] for w in self.r.list_by('works',task_id=task['id']))
            if done+quantity>task['quantity']: raise ValueError('Количество превышает остаток задания')
        tariff=self.tariff(op_id);self.valid_rates(tariff);now=self.clock()
        if self.payroll_is_closed(now):raise ValueError('Расчётный период уже закрыт')
        started=stamp(b.get('started_at'),True)
        if started and started>now: raise ValueError('Начало работы в будущем')
        duration=(datetime.fromisoformat(now)-datetime.fromisoformat(started)).total_seconds() if started else None
        calendar_seconds=duration
        pauses=[]
        timing_id=b.get('timing_session_id')
        if timing_id:
            timer=self.entity('work_timers',timing_id)
            if timer['status']!='finishing' or timer['user_id']!=self.u['id'] or timer['task_id']!=(task['id'] if task else None):
                raise PermissionError('Таймер работы недоступен')
            started=timer['started_at'];calendar_seconds=timer['calendar_seconds'];duration=timer['net_seconds'];pauses=timer['pauses']
        legacy_id=self.r.legacy_work(self.u,client,op,quantity,tariff['employee_rate'],tariff['client_rate'],now)
        work=self.r.insert('works',dict(client_id=client_id,client_name=client['name'],operation_id=op_id,operation_name=op['name'],batch_id=batch_id,
            product=batch['product'] if batch else text(b.get('product'),optional=True),task_id=task['id'] if task else None,without_task=not bool(task),
            user_id=self.u['id'],employee_id=employee_id(self.u),quantity=quantity,tariff_id=tariff['id'],tariff_sources=tariff['sources'],employee_rate=tariff['employee_rate'],client_rate=tariff['client_rate'],
            salary=quantity*tariff['employee_rate'],revenue=quantity*tariff['client_rate'],legacy_id=legacy_id,started_at=started,completed_at=now,duration_seconds=duration,
            calendar_seconds=calendar_seconds,net_seconds=duration,pauses=pauses,timing_session_id=timing_id,
            units_per_hour=quantity/duration*3600 if duration and duration>0 else None,quality={'defects':None,'correction_of':None}))
        consumption=self.norms(op_id,quantity)
        for item in consumption:
            self.r.consume(item['material_id'],float(item['quantity']),item['unit_cost'],legacy_id,employee_id(self.u))
            self.r.insert('usage',dict(item,work_id=work['id'],batch_id=batch_id,operation_id=op_id,client_id=client_id,source='norm'))
        self.r.project_cost(legacy_id,sum(n['cost'] for n in consumption))
        if task:
            task['status']='done' if done+quantity==task['quantity'] else 'in_progress';self.r.update('tasks',task)
        return work

    def timer(self,b):
        self.need('work.write')
        action=b.get('event');now=self.clock()
        if action=='start':
            if not employee_id(self.u):raise PermissionError('Свяжите доступ с сотрудником перед началом работы')
            task=self.entity('tasks',b['task_id'])
            if self.u['id'] not in task['assignees'] or task['status']=='done':raise PermissionError('Задание недоступно')
            if any(t['status'] in ('running','paused') for t in self.r.list_by('work_timers',user_id=self.u['id'])):
                raise ValueError('Сначала завершите текущую работу')
            timer=self.r.insert('work_timers',dict(task_id=task['id'],batch_id=task['batch_id'],client_id=task['client_id'],product=task['product'],
                operation_id=task['operation_id'],user_id=self.u['id'],employee_id=employee_id(self.u),started_at=now,
                running_from=now,pauses=[],status='running',net_seconds=None,calendar_seconds=None,quantity=None,work_id=None))
        else:
            timer=self.entity('work_timers',b['session_id'])
            if timer['user_id']!=self.u['id']:raise PermissionError('Таймер другого сотрудника')
            if action=='pause':
                if timer['status']!='running':raise ValueError('Работа сейчас не выполняется')
                timer['pauses'].append(dict(start=now,end=None));timer['status']='paused';timer['running_from']=None
            elif action=='resume':
                if timer['status']!='paused':raise ValueError('Работа не на паузе')
                timer['pauses'][-1]['end']=now;timer['status']='running';timer['running_from']=now
            elif action=='finish':
                if timer['status'] not in ('running','paused'):raise ValueError('Работа уже завершена')
                quantity=qty(b.get('quantity'))
                if timer['status']=='paused':timer['pauses'][-1]['end']=now
                calendar=(datetime.fromisoformat(now)-datetime.fromisoformat(timer['started_at'])).total_seconds()
                paused=sum((datetime.fromisoformat(p['end'])-datetime.fromisoformat(p['start'])).total_seconds() for p in timer['pauses'])
                if calendar<0 or paused<0 or paused>calendar:raise ValueError('Часы сервера изменились; проверьте время')
                timer.update(status='finishing',calendar_seconds=calendar,net_seconds=calendar-paused,quantity=quantity,running_from=None)
                self.r.update('work_timers',timer)
                work=self.work(dict(task_id=timer['task_id'],quantity=quantity,timing_session_id=timer['id']))
                timer.update(status='completed',completed_at=now,work_id=work['id'])
            else:raise ValueError('Неизвестное событие таймера')
            self.r.update('work_timers',timer)
        self.r.insert('timer_events',dict(session_id=timer['id'],user_id=self.u['id'],task_id=timer['task_id'],event=action,at=now,
                                          quantity=timer.get('quantity') if action=='finish' else None))
        return timer

    def link(self,b):
        self.need('work.link');work=self.entity('works',b['work_id']);batch=self.entity('batches',b['batch_id'])
        if not work['without_task'] or self.batch_for_work(work): raise ValueError('Работа уже привязана')
        if batch['client_id']!=work['client_id'] or (work['product'] and work['product']!=batch['product']): raise ValueError('Клиент или товар не совпадает')
        return self.r.insert('links',dict(work_id=work['id'],batch_id=batch['id'],client_id=work['client_id'],actor_id=self.u['id']))

    def usage(self,b):
        self.need('materials.use');w=self.entity('works',b['work_id'])
        m=next((m for m in self.r.catalog('materials') if m['id']==b['material_id'] and m['active']),None)
        if not m: raise ValueError('Материал недоступен')
        amount=Decimal(str(b['quantity']))
        if not amount.is_finite() or amount<=0 or amount>1000000: raise ValueError('Некорректный расход')
        unit=cents(m['unit_cost'] or 0);cost=int((amount*unit).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
        self.r.consume(m['id'],float(amount),unit,w['legacy_id'],employee_id(self.u))
        item=self.r.insert('usage',dict(work_id=w['id'],batch_id=self.batch_for_work(w),operation_id=w['operation_id'],client_id=w['client_id'],material_id=m['id'],quantity=str(amount),unit_cost=unit,cost=cost,source='additional_actual'))
        # The legacy projection retains the original cost snapshot; late facts belong to the ledger.
        return item

    def payroll_bounds(self,start,end):
        try:
            s=datetime.strptime(start,'%Y-%m-%d').date();e=datetime.strptime(end,'%Y-%m-%d').date()
        except (TypeError,ValueError):
            raise ValueError('Период зарплаты: даты ГГГГ-ММ-ДД')
        if (s.year,s.month)!=(e.year,e.month):
            raise ValueError('Расчётный период должен быть внутри одного месяца')
        last=calendar.monthrange(s.year,s.month)[1]
        if not ((s.day==1 and e.day==15) or (s.day==16 and e.day==last)):
            raise ValueError('Допустимы периоды 1–15 или 16–последний день месяца')
        return s.isoformat(),e.isoformat()

    def payroll_snapshot(self,start,end):
        self.need('payroll.all');start,end=self.payroll_bounds(start,end)
        users={u['id']:u for u in self.r.catalog('users')};groups={}
        end_exclusive=(datetime.strptime(end,'%Y-%m-%d').date()+timedelta(days=1)).isoformat()+'T00:00:00';works=self.r.list_range('works','completed_at',start+'T00:00:00',end_exclusive)
        for w in works:
            g=groups.setdefault(w['user_id'],dict(user_id=w['user_id'],employee_id=w.get('employee_id'),
                display_name=users.get(w['user_id'],{}).get('display_name','Сотрудник'),quantity=0,salary=0,work_rows=0))
            g['quantity']+=w['quantity'];g['salary']+=w['salary'];g['work_rows']+=1
        rows=sorted(groups.values(),key=lambda x:(x['display_name'].casefold(),x['user_id']))
        details=[dict(work_id=w['id'],user_id=w['user_id'],employee_id=w.get('employee_id'),
                      display_name=users.get(w['user_id'],{}).get('display_name','Сотрудник'),
                      client_name=w['client_name'],operation_name=w['operation_name'],quantity=w['quantity'],
                      employee_rate=w['employee_rate'],salary=w['salary'],completed_at=w['completed_at'])
                 for w in sorted(works,key=lambda x:(x['completed_at'],x['user_id'],x['id']))]
        return dict(period_start=start,period_end=end,employees=rows,details=details,total_quantity=sum(x['quantity'] for x in rows),
                    total_salary=sum(x['salary'] for x in rows),work_rows=sum(x['work_rows'] for x in rows),
                    currency='RUB',money_unit='kopeck')

    def payroll_period(self,b):
        self.need('payroll.close');start,end=self.payroll_bounds(b.get('period_start'),b.get('period_end'))
        local_today=(datetime.fromisoformat(self.clock())+timedelta(minutes=self.settings()['utc_offset_minutes'])).date().isoformat()
        if end>=local_today:raise ValueError('Закрывать можно только завершившийся расчётный период')
        for p in self.r.list('payroll_periods'):
            if not (end<p['period_start'] or start>p['period_end']):
                raise ValueError('Этот расчётный период уже закрыт или пересекается с закрытым')
        snapshot=self.payroll_snapshot(start,end)
        stored_snapshot=copy.deepcopy(snapshot)
        for row in stored_snapshot['employees']:
            identity=row.get('employee_id')
            row['employee_id']=self.r.legacy_identity_for_employee(identity) if identity is not None else None
        period=self.r.insert('payroll_periods',dict(period_start=start,period_end=end,status='closed',
            closed_by=self.u['id'],closed_at=self.clock(),snapshot=stored_snapshot))
        return self.public_payroll_period(period)

    def public_payroll_period(self,period):
        """Translate retained snapshot keys to employee_id in API responses only."""
        result=copy.deepcopy(period)
        for row in result.get('snapshot',{}).get('employees',[]):
            legacy=row.get('employee_id')
            if legacy is not None:
                row['employee_id']=self.r.payroll_employee(legacy,legacy=True)['employee_id']
        return result

    def payroll_is_closed(self,at):
        day=at[:10]
        return any(p['period_start']<=day<=p['period_end'] for p in self.r.list_by('payroll_periods',status='closed'))

    def payroll_employee_id(self,b,required=True):
        canonical=b.get('employee_id')
        def normalized(value):
            if type(value) is int:return value
            if isinstance(value,str) and re.fullmatch(r'-?[0-9]{1,19}',value):return int(value)
            raise ValueError('Некорректный идентификатор сотрудника')
        resolved=self.r.payroll_employee(normalized(canonical))['employee_id'] if canonical is not None else None
        value=resolved
        if value is None and not required:return None
        if value is None:raise ValueError('Укажите сотрудника')
        return value

    def settlement_employees(self,period):
        # Closed v3 snapshots retain their historical compatibility IDs unchanged.
        result=[]
        for row in period['snapshot']['employees']:
            legacy=row.get('employee_id')
            if legacy is None:continue
            if type(legacy) is not int or type(row.get('salary')) is not int:
                raise ValueError('Закрытый снимок требует проверки идентификаторов и денежных сумм')
            identity=self.r.payroll_employee(legacy,legacy=True)['employee_id']
            if self.r.has_legacy_payroll(period,legacy):
                raise ValueError('В периоде есть исторические расчёты зарплаты; требуется сверка до новых выплат')
            result.append(dict(row,employee_id=identity))
        return result

    def closed_payroll_period(self,identity):
        period=self.r.get('payroll_periods',text(identity,'Расчётный период'))
        if period.get('status')!='closed':raise ValueError('Расчёты разрешены только для закрытого расчётного периода')
        return period

    def settlement_entry(self,row):
        result=dict(row,amount=row['amount_minor'],money_unit='kopeck',currency='RUB')
        result.pop('amount_minor',None)
        if result.get('actor_kind')=='platform_owner' and not self.u.get('technical_owner'):
            result.pop('actor_id',None);result['actor_kind']='system'
        return result

    def settlement_summary(self,period,entries,employee=None):
        employees={}
        for row in self.settlement_employees(period):
            identity=row.get('employee_id')
            if identity is None:continue
            item=employees.setdefault(identity,dict(employee_id=identity,
                display_name=row.get('display_name','Сотрудник'),accrued=0,adjustment=0,paid=0,balance=0))
            item['accrued']+=row['salary'];item['balance']+=row['salary']
        for entry in entries:
            item=employees.get(entry['employee_id'])
            if item is None:continue
            if entry['effect']=='payment':item['paid']+=entry['amount_minor']
            else:item['adjustment']+=entry['amount_minor']
            item['balance']=item['accrued']+item['adjustment']-item['paid']
        rows=sorted((item for item in employees.values() if employee is None or item['employee_id']==employee),
                    key=lambda item:(item['display_name'].casefold(),item['employee_id']))
        totals={key:sum(item[key] for item in rows) for key in ('accrued','adjustment','paid','balance')}
        return dict(period_id=period['id'],period_start=period['period_start'],period_end=period['period_end'],
                    status='закрыт',money_unit='kopeck',currency='RUB',employees=rows,totals=totals,
                    entries=[self.settlement_entry(row) for row in entries if employee is None or row['employee_id']==employee])

    def payroll_settlement(self,b):
        entry_type=b.get('entry_type')
        if entry_type not in ('payout','adjustment','reversal'):
            raise ValueError('Тип записи: выплата, корректировка или сторно')
        self.need('payroll.settlement.payout' if entry_type=='payout' else 'payroll.settlement.correct')
        reason=text(b.get('reason'),'Причина')
        reference=text(b.get('reference'),'Ссылка или основание',optional=True) or None
        request_id=request_identity(b.get('request_id'))
        reversal_of=None
        if entry_type=='reversal':
            if 'amount' in b:raise ValueError('Сумма сторно определяется исходной записью')
            target=self.r.payroll_settlement(text(b.get('reversal_of'),'Исходная запись'))
            if target['entry_type']=='reversal':raise ValueError('Сторно нельзя сторнировать повторно')
            if any(row['reversal_of']==target['id'] for row in self.r.payroll_settlements(target['payroll_period_id'])):
                raise ValueError('Исходная запись уже сторнирована')
            period=self.closed_payroll_period(target['payroll_period_id'])
            employee=target['employee_id'];amount=-target['amount_minor'];effect=target['effect'];reversal_of=target['id']
            self.settlement_employees(period)
            supplied=self.payroll_employee_id(b,False)
            if supplied is not None and supplied!=employee:raise ValueError('Сотрудник не совпадает с исходной записью')
            if b.get('payroll_period_id') not in (None,period['id']):raise ValueError('Расчётный период не совпадает с исходной записью')
        else:
            period=self.closed_payroll_period(b.get('payroll_period_id'))
            employee=self.payroll_employee_id(b)
            if employee not in {row['employee_id'] for row in self.settlement_employees(period)}:
                raise ValueError('Сотрудник отсутствует в закрытом снимке расчётного периода')
            amount=settlement_cents(b.get('amount'),signed=entry_type=='adjustment')
            if amount==0:raise ValueError('Сумма записи после округления не может быть нулевой')
            effect='payment' if entry_type=='payout' else 'entitlement'
            if entry_type=='payout':
                current=self.settlement_summary(period,self.r.payroll_settlements(period['id']),employee)['employees'][0]
                if amount>current['balance']:raise ValueError('Сумма выплаты превышает остаток по закрытому периоду')
        item=self.r.insert_payroll_settlement(dict(employee_id=employee,payroll_period_id=period['id'],
            amount_minor=amount,entry_type=entry_type,effect=effect,actor_id=self.u['id'],
            occurred_at=self.clock(),reason=reason,reference=reference,request_id=request_id,reversal_of=reversal_of,
            actor_kind='platform_owner' if self.u.get('technical_owner') else 'user'))
        return self.settlement_entry(item)

    def payroll_settlement_rows(self,params):
        self.need('payroll.settlement.read')
        period_id=params.get('payroll_period_id',[None])[0]
        if not period_id:raise ValueError('Укажите закрытый расчётный период')
        period=self.closed_payroll_period(period_id)
        values={key:params[key][0] for key in ('employee_id',) if key in params}
        employee=self.payroll_employee_id(values,False)
        if employee is not None and employee not in {row['employee_id'] for row in self.settlement_employees(period)}:
            raise ValueError('Сотрудник отсутствует в закрытом снимке расчётного периода')
        return self.settlement_summary(period,self.r.payroll_settlements(period['id'],employee),employee)

    def chat_room(self,recipient=None):
        if recipient in (None,''):return 'general'
        try:target=int(recipient)
        except (TypeError,ValueError):raise ValueError('Сотрудник для личного чата не найден')
        users={u['id']:u for u in self.r.catalog('users')}
        if target==self.u['id'] or target not in users or not users[target]['active']:
            raise ValueError('Сотрудник для личного чата не найден')
        a,b=sorted((self.u['id'],target));return f'dm:{a}:{b}'

    def chat_room_allowed(self,room):
        if room=='general':return True
        parts=str(room).split(':')
        return len(parts)==3 and parts[0]=='dm' and str(self.u['id']) in parts[1:]

    def chat_command(self,b):
        mode=b.get('mode','message')
        if mode=='pin':
            self.need('chat.moderate');message=self.entity('chat_messages',text(b.get('message_id'),'Сообщение'))
            if not self.chat_room_allowed(message['room']):raise PermissionError('Личная переписка доступна только её участникам')
            pinned=b.get('pinned',True)
            if type(pinned) is not bool:raise ValueError('Некорректный статус закрепления')
            return self.r.insert('chat_pins',dict(message_id=message['id'],room=message['room'],pinned=pinned,actor_id=self.u['id']))
        self.need('chat.write')
        subtype=b.get('subtype','text')
        request_id=b.get('request_id')
        if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',request_id):
            raise ValueError('Некорректный request id')
        previous=next(iter(self.r.list_by('chat_messages',request_id=request_id,sender_user_id=self.u['id'])),None)
        if previous:return previous
        if subtype=='sticker':
            key=b.get('sticker_key')
            if key not in {'accepted','in_progress','done','help','important','thanks'}:raise ValueError('Неизвестный системный стикер')
            if b.get('recipient_user_id') not in (None,''):raise ValueError('Стикеры доступны только в общем чате')
            return self.r.insert('chat_messages',dict(room='general',sender_user_id=self.u['id'],sender_name=self.u.get('display_name') or self.u.get('username','Сотрудник'),message_type='sticker',sticker_key=key,text='',request_id=request_id))
        if subtype=='absence_notice':
            day=b.get('absence_date');comment=b.get('comment','')
            try:
                parsed=datetime.strptime(day,'%Y-%m-%d')
                if parsed.date().isoformat()!=day:raise ValueError()
            except (TypeError,ValueError):raise ValueError('Укажите корректную дату дня невыхода')
            if not isinstance(comment,str) or len(comment.strip())>300:raise ValueError('Комментарий должен содержать не более 300 символов')
            if b.get('recipient_user_id') not in (None,''):raise ValueError('Сообщение о невыходе доступно только в общем чате')
            return self.r.insert('chat_messages',dict(room='general',sender_user_id=self.u['id'],sender_name=self.u.get('display_name') or self.u.get('username','Сотрудник'),message_type='absence_notice',absence_date=day,comment=comment.strip(),text='',request_id=request_id))
        raw=b.get('text','');attachment=b.get('attachment')
        if not isinstance(raw,str) or len(raw.strip())>4000:raise ValueError('Сообщение: до 4000 символов')
        if not raw.strip() and not attachment:raise ValueError('Введите сообщение или добавьте файл')
        room=self.chat_room(b.get('recipient_user_id'))
        message=self.r.insert('chat_messages',dict(room=room,sender_user_id=self.u['id'],
            sender_name=self.u.get('display_name') or self.u.get('username','Сотрудник'),text=raw.strip(),request_id=request_id))
        if attachment:
            if not isinstance(attachment,dict):raise ValueError('Некорректное вложение')
            original=attachment.get('name');mime=attachment.get('mime_type');encoded=attachment.get('file_b64')
            if not isinstance(original,str) or not original.strip() or len(original.strip())>120:raise ValueError('Имя файла: до 120 символов')
            types={'image/jpeg':'jpg','image/png':'png','image/webp':'webp','application/pdf':'pdf','text/plain':'txt'}
            if mime not in types:raise ValueError('Этот тип файла пока не поддерживается')
            if not isinstance(encoded,str) or len(encoded)>3*1024*1024:raise ValueError('Файл слишком большой')
            try:data=base64.b64decode(encoded,validate=True)
            except Exception:raise ValueError('Некорректное содержимое файла')
            if not data or len(data)>2*1024*1024:raise ValueError('Файл должен быть не больше 2 МБ')
            saved=self.r.insert('chat_attachments',dict(message_id=message['id'],room=room,original_name=original.strip(),
                filename=f"PORTAL_chat_{uuid.uuid4().hex[:16]}.{types[mime]}",mime_type=mime,size_bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest(),file_b64=base64.b64encode(data).decode('ascii')))
            message=dict(message,attachment={k:saved[k] for k in ('id','original_name','mime_type','size_bytes','sha256')})
        return message

    def chat_cleanup(self):
        self.need('chat.read');pins=self.r.list('chat_pins');latest={}
        for event in pins:latest[event['message_id']]=event
        removed=0;attachments=self.r.list('chat_attachments')
        messages=list(self.r.list('chat_messages'))
        rooms={message['room'] for message in messages}
        remove_ids=set()
        for room in rooms:
            ordinary=[message for message in messages
                      if message['room']==room and not bool(latest.get(message['id'],{}).get('pinned'))]
            ordinary.sort(key=lambda message:(message.get('created_at',''),str(message['id'])))
            remove_ids.update(message['id'] for message in ordinary[:-1000])
        for message in messages:
            if message['id'] not in remove_ids:continue
            for attachment in [a for a in attachments if a['message_id']==message['id']]:self.r.delete('chat_attachments',attachment['id'])
            for event in [p for p in pins if p['message_id']==message['id']]:self.r.delete('chat_pins',event['id'])
            self.r.delete('chat_messages',message['id']);removed+=1
        return removed

    def chat_rows(self,recipient=None):
        self.need('chat.read');self.chat_cleanup();room=self.chat_room(recipient);latest={}
        for event in self.r.list('chat_pins'):
            if event['room']==room:latest[event['message_id']]=event
        attachments={}
        for item in self.r.list('chat_attachments'):
            if item['room']==room:
                attachments[item['message_id']]={k:item[k] for k in ('id','original_name','mime_type','size_bytes','sha256')}
        result=[]
        for message in self.r.list('chat_messages'):
            if message['room']!=room:continue
            result.append(dict(message,pinned=bool(latest.get(message['id'],{}).get('pinned')),attachment=attachments.get(message['id'])))
        return result

    def chat_file(self,identity):
        self.need('chat.read');attachment=self.entity('chat_attachments',identity)
        if not self.chat_room_allowed(attachment['room']):raise PermissionError('Файл личного чата недоступен')
        return {k:attachment[k] for k in ('id','filename','original_name','mime_type','size_bytes','sha256','file_b64')}

    def document(self,b):
        self.need('documents.manage')
        if b.get('document_type')!='payroll':raise ValueError('Пока поддерживается расчётный документ зарплаты')
        start,end=self.payroll_bounds(b.get('period_start'),b.get('period_end'))
        period=next(iter(self.r.list_by('payroll_periods',period_start=start,period_end=end,status='closed')),None)
        if not period:raise ValueError('Сначала закройте расчётный период')
        snapshot=period['snapshot'];snapshot_raw=json.dumps(snapshot,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
        settlements=self.settlement_summary(period,self.r.payroll_settlements(period['id']))
        payload=payroll_xlsx(snapshot,settlements);title=text(b.get('title') or f'Расчётный период {start} — {end}','Название документа')
        filename=f'PORTAL_payroll_{start}_{end}.xlsx'
        return self.r.insert('documents',dict(document_type='payroll',title=title,
            period_id=period['id'],period_start=start,period_end=end,status='ready',
            snapshot_sha256=hashlib.sha256(snapshot_raw).hexdigest(),sha256=hashlib.sha256(payload).hexdigest(),
            filename=filename,mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            size_bytes=len(payload),file_b64=base64.b64encode(payload).decode('ascii'),
            created_by=self.u['id'],generated_format='xlsx',future_formats=['pdf'],snapshot=snapshot))

    def expense(self,b):
        self.need('expenses.manage')
        categories={'rent':'Аренда','logistics':'Логистика','carrier_pickup':'Забор из ТК',
                    'marketplace_delivery':'Доставка на маркетплейс','utilities':'Коммунальные расходы',
                    'waste':'Вывоз мусора','management':'Управленческие расходы','other':'Прочее'}
        code=b.get('category_code')
        if code is None and b.get('category'):
            code='other';label=text(b.get('category'),'Статья расхода')
        else:
            if code not in categories:raise ValueError('Выберите категорию расхода')
            label=categories[code]
        amount=cents(b.get('amount'))
        if amount<=0:raise ValueError('Сумма расхода должна быть больше нуля')
        batch=self.entity('batches',b['batch_id']) if b.get('batch_id') else None
        client_id=batch['client_id'] if batch else b.get('client_id')
        if client_id is not None:
            try:client_id=int(client_id)
            except (TypeError,ValueError):raise ValueError('Клиент расхода не найден')
            self.client(client_id)
        if batch and b.get('client_id') not in (None,batch['client_id']):raise ValueError('Клиент не совпадает с партией')
        return self.r.insert('expenses',dict(batch_id=batch['id'] if batch else None,client_id=client_id,
            amount=amount,category_code=code,category=label,incurred_at=stamp(b.get('incurred_at') or self.clock()),
            note=text(b.get('note'),optional=True),created_by=self.u['id']))

    def invoice(self,b):
        workflow=b.get('workflow')
        if workflow in ('send_to_editing','save_revision'):
            if not self.r.sql('SELECT 1 FROM portal_production_migrations WHERE company_id=? AND version=9',(self.r.company_id,)).fetchone():
                raise ValueError('Invoice revision migration 9 must be applied before changing invoice state')
            self.need('invoices.read')
            original=self.entity('invoices',b.get('invoice_id'))
            history=sorted(self.r.list_by('invoice_revisions',invoice_id=original['id']),key=lambda r:r['revision'])
            current=self.invoice_current(original['id'])
            invoice=current
            if self.u.get('role') not in ('admin','director'):
                if workflow=='send_to_editing':raise PermissionError('Только администратор или директор может отправить счёт на редактирование')
                if self.u.get('role')!='manager':raise PermissionError('Нет права изменять счёт')
            payments=self.r.list_by('payments',invoice_id=invoice['id'])
            if workflow=='send_to_editing':
                if invoice.get('state','finalized')=='editing':return invoice
                if invoice.get('state','finalized')!='finalized':raise ValueError('Недопустимое состояние счёта')
                snapshot={k:invoice[k] for k in ('work_ids','lines','amount','due_at')}
                row=self.r.insert('invoice_revisions',dict(invoice_id=invoice['id'],revision=invoice.get('revision',1),state='editing',snapshot=snapshot))
                return dict(invoice,state='editing',revision=row['revision'])
            if invoice.get('state')!='editing':raise ValueError('Счёт не находится на редактировании')
            submitted=b.get('lines')
            if submitted is None:
                ids=b.get('work_ids',invoice['work_ids'])
                if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)):raise ValueError('Выберите уникальные записи работ')
                if any(work_id not in invoice['work_ids'] for work_id in ids):raise ValueError('В новую редакцию можно включать только исходные строки счёта')
                works=[self.entity('works',wid) for wid in ids]
                if len({w['client_id'] for w in works})!=1 or works[0]['client_id']!=invoice['client_id']:
                    raise ValueError('Счёт может включать работы только исходного клиента')
                lines=[dict(work_id=w['id'],operation_id=w['operation_id'],operation_name=w['operation_name'],quantity=w['quantity'],client_rate=w['client_rate'],amount=w['revenue'],batch_id=self.batch_for_work(w)) for w in works]
            else:
                if not isinstance(submitted,list) or not submitted:raise ValueError('Добавьте хотя бы одну строку счёта')
                old_by_work={line['work_id']:line for line in invoice['lines']}
                lines=[]
                for item in submitted:
                    if not isinstance(item,dict) or set(item)!={'work_id','quantity','client_rate'} or item['work_id'] not in old_by_work:
                        raise ValueError('Новая редакция может содержать только исходные строки счёта')
                    if any(line['work_id']==item['work_id'] for line in lines):raise ValueError('Строки счёта должны быть уникальными')
                    quantity=qty(item['quantity']);rate=item['client_rate']
                    if type(rate) is not int or not 0<=rate<=100_000_000_000:raise ValueError('Цена строки указана неверно')
                    lines.append(dict(old_by_work[item['work_id']],quantity=quantity,client_rate=rate,amount=quantity*rate))
                ids=[line['work_id'] for line in lines]
            amount=sum(line['amount'] for line in lines)
            old_lines=invoice['lines']
            financial=lambda rows:[{k:line.get(k) for k in ('work_id','quantity','client_rate','amount')} for line in rows]
            if payments and (amount!=invoice['amount'] or financial(lines)!=financial(old_lines)):
                raise ValueError('Нельзя менять сумму или строки счёта с зарегистрированными оплатами')
            previous=dict(revision=invoice.get('revision',1),**{k:invoice[k] for k in ('work_ids','lines','amount','due_at')})
            due=stamp(b.get('due_at',invoice.get('due_at')),True)
            snapshot=dict(work_ids=ids,lines=lines,amount=amount,due_at=due)
            revision=invoice.get('revision',1)+1
            self.r.insert('invoice_revisions',dict(invoice_id=invoice['id'],revision=revision,state='finalized',snapshot=snapshot,previous_snapshot=previous,finalized_at=self.clock()))
            return dict(invoice,**snapshot,revision=revision,state='finalized',history=list(invoice.get('history',[]))+[dict(revision=invoice.get('revision',1),snapshot=previous)],finalized_at=self.clock())
        self.need('invoices.create')
        if b.get('mode')=='manual':
            client_id=b.get('client_id')
            if type(client_id) is not int: raise ValueError('Выберите клиента')
            self.client(client_id,True)
            submitted=b.get('lines')
            if not isinstance(submitted,list) or not 1<=len(submitted)<=200:
                raise ValueError('Добавьте от 1 до 200 строк счёта')
            lines=[];seen=set()
            for item in submitted:
                if not isinstance(item,dict) or set(item)!={'operation_id','quantity','client_rate'}:
                    raise ValueError('Некорректная строка счёта')
                operation_id=item['operation_id']
                if type(operation_id) is not int or operation_id in seen:
                    raise ValueError('Операции в счёте должны быть уникальными')
                seen.add(operation_id)
                op=self.operation(client_id,operation_id)
                quantity=qty(item['quantity']);rate=item['client_rate']
                if type(rate) is not int or not 0<=rate<=100_000_000_000:
                    raise ValueError('Цена строки указана неверно')
                line_id='manual:'+str(uuid.uuid4())
                lines.append(dict(work_id=line_id,operation_id=op['id'],operation_name=op['name'],
                    quantity=quantity,client_rate=rate,amount=quantity*rate,batch_id=None,source_kind='manual'))
            amount=sum(line['amount'] for line in lines);due=stamp(b.get('due_at'),True)
            identity=str(uuid.uuid4())
            day=self.clock()[:10].replace('-','')
            number=f'PRT-{day}-{identity[:6].upper()}'
            ids=[line['work_id'] for line in lines]
            snapshot=dict(work_ids=ids,lines=lines,amount=amount,due_at=due)
            return self.r.insert('invoices',dict(number=number,client_id=client_id,work_ids=ids,amount=amount,due_at=due,
                lines=lines,source_kind='manual',state='finalized',revision=1,finalized_at=self.clock(),history=[],snapshot=snapshot),identity)
        ids=b.get('work_ids')
        if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)): raise ValueError('Выберите уникальные записи работ')
        billed=self.billed_work_ids()
        works=[self.entity('works',wid) for wid in ids]
        if any(w['id'] in billed for w in works): raise ValueError('Работа уже выставлена клиенту')
        if len({w['client_id'] for w in works})!=1: raise ValueError('Счёт может включать работы одного клиента')
        lines=[dict(work_id=w['id'],operation_id=w['operation_id'],operation_name=w['operation_name'],quantity=w['quantity'],client_rate=w['client_rate'],amount=w['revenue'],batch_id=self.batch_for_work(w)) for w in works]
        amount=sum(w['revenue'] for w in works);due=stamp(b.get('due_at'),True)
        identity=str(uuid.uuid4());day=self.clock()[:10].replace('-','');number=f'PRT-{day}-{identity[:6].upper()}'
        return self.r.insert('invoices',dict(number=number,client_id=works[0]['client_id'],work_ids=ids,amount=amount,due_at=due,lines=lines,
            state='finalized',revision=1,finalized_at=self.clock(),history=[],snapshot=dict(work_ids=ids,lines=lines,amount=amount,due_at=due)),identity)

    def payment(self,b):
        self.need('payments.record');i=self.entity('invoices',b['invoice_id'])
        history=sorted(self.r.list_by('invoice_revisions',invoice_id=i['id']),key=lambda r:r['revision'])
        if history:i=dict(i,**history[-1]['snapshot'],state=history[-1]['state'])
        if i.get('state')=='editing':raise ValueError('Счёт на редактировании; приём оплаты временно недоступен')
        amount=cents(b['amount'])
        paid=sum(p['amount'] for p in self.r.list_by('payments',invoice_id=i['id']))
        if not 0<amount<=i['amount']-paid: raise ValueError('Оплата должна быть больше нуля и не больше остатка счёта')
        return self.r.insert('payments',dict(invoice_id=i['id'],client_id=i['client_id'],amount=amount,reference=text(b.get('reference'),optional=True)))

    def set_permissions(self,b):
        self.need('users.manage');self.need_management_role()
        users={u['id']:u for u in self.r.catalog('users')};target=users.get(b.get('user_id'))
        if not target: raise ValueError('Сотрудник не найден')
        old=self.r.get('permissions',str(target['id']),False) or dict(id=str(target['id']),overrides={})
        mode=b.get('mode','custom')
        if mode in ('recommended','reset'): desired=rights.defaults(target['role'])
        elif mode=='copy':
            source=users.get(b.get('source_id'))
            if not source: raise ValueError('Источник прав недоступен')
            desired=rights.effective(self.r,source)
        elif mode=='custom':
            values=b.get('permissions')
            if not isinstance(values,dict) or any(k not in rights.CODES or type(v) is not bool for k,v in values.items()): raise ValueError('Недопустимые права')
            desired=rights.effective(self.r,target)
            for key,on in values.items():
                if on: desired.add(key)
                else: desired.discard(key)
        else: raise ValueError('Неизвестное действие')
        before=rights.effective(self.r,target)
        if (before^desired)-self.permissions: raise PermissionError('Можно изменять только собственные бизнес-права')
        if target['role']=='admin' and 'users.manage' not in desired:
            if not any(u['active'] and u['id']!=target['id'] and u['role']=='admin' and 'users.manage' in rights.effective(self.r,u) for u in users.values()): raise ValueError('Нельзя лишить прав последнего администратора')
        defaults=rights.defaults(target['role']);old['overrides']={k:k in desired for k in rights.CODES if (k in defaults)!=(k in desired)}
        changed=sorted(before^desired)
        if self.r.get('permissions',old['id'],False): result=self.r.update('permissions',old)
        else: result=self.r.insert('permissions',old,old['id'])
        if changed:self.r.audit(self.u,'user.permissions.updated',target['id'],fields=changed)
        return result

    def settings(self,b=None):
        current=self.r.get('settings','control',False) or dict(monday_time='10:00',wednesday_time='10:00',utc_offset_minutes=180,
                                                               presence_heartbeat_seconds=60,presence_timeout_seconds=180,
                                                               reminder_enabled=False,reminder_cadence='daily')
        current.setdefault('presence_heartbeat_seconds',60)
        current.setdefault('presence_timeout_seconds',180)
        current.setdefault('reminder_enabled',False)
        current.setdefault('reminder_cadence','daily')
        if b is None: return current
        self.need('company.settings')
        for field in ('monday_time','wednesday_time'):
            value=b.get(field,current[field])
            try: datetime.strptime(value,'%H:%M')
            except (ValueError,TypeError): raise ValueError('Укажите время ЧЧ:ММ')
            if len(value)!=5: raise ValueError('Укажите время ЧЧ:ММ')
            current[field]=value
        offset=b.get('utc_offset_minutes',current['utc_offset_minutes'])
        if type(offset) is not int or not -720<=offset<=840: raise ValueError('Некорректное смещение часового пояса')
        current['utc_offset_minutes']=offset
        heartbeat=b.get('presence_heartbeat_seconds',current['presence_heartbeat_seconds'])
        timeout=b.get('presence_timeout_seconds',current['presence_timeout_seconds'])
        if type(heartbeat) is not int or not 15<=heartbeat<=300 or type(timeout) is not int or not 2*heartbeat<=timeout<=3600:
            raise ValueError('Интервал активности должен быть 15–300 с, таймаут — не меньше двух интервалов и до 3600 с')
        current['presence_heartbeat_seconds']=heartbeat
        current['presence_timeout_seconds']=timeout
        reminder_enabled=b.get('reminder_enabled',current['reminder_enabled'])
        reminder_cadence=b.get('reminder_cadence',current['reminder_cadence'])
        if type(reminder_enabled) is not bool: raise ValueError('Включение напоминаний должно быть явным значением да/нет')
        if reminder_cadence not in ('daily','weekly'): raise ValueError('Допустимая периодичность напоминаний: daily или weekly')
        current['reminder_enabled']=reminder_enabled
        current['reminder_cadence']=reminder_cadence
        previous=self.r.get('settings','control',False) or dict(monday_time='10:00',wednesday_time='10:00',utc_offset_minutes=180,
            presence_heartbeat_seconds=60,presence_timeout_seconds=180,reminder_enabled=False,reminder_cadence='daily')
        previous.setdefault('reminder_enabled',False)
        previous.setdefault('reminder_cadence','daily')
        changed=sorted(key for key in ('monday_time','wednesday_time','utc_offset_minutes','presence_heartbeat_seconds','presence_timeout_seconds','reminder_enabled','reminder_cadence')
            if current.get(key)!=previous.get(key))
        result=self.r.update('settings',current) if current.get('id') else self.r.insert('settings',current,'control')
        if changed:self.r.audit(self.u,'company.settings.updated','control',fields=changed)
        return result

    def organizer_users(self):
        self.need('organizer.read')
        users=[u for u in self.r.catalog('users') if u.get('active')]
        allowed={'director','admin','manager'} if self.u.get('technical_owner') else ORGANIZER_ASSIGNABLE.get(self.u.get('role'),set())
        rows=[]
        for u in users:
            if u['id']!=self.u['id'] and u.get('role') not in allowed:continue
            rows.append(dict(id=u['id'],display_name=u.get('display_name') or u.get('username') or 'Сотрудник',
                role=u.get('role'),role_label=ORGANIZER_ROLE_LABELS.get(u.get('role'),'Сотрудник'),self=u['id']==self.u['id']))
        return sorted(rows,key=lambda x:(not x['self'],x['role_label'],x['display_name'].casefold()))

    def organizer_moment(self,value,label,optional=False):
        if optional and value in (None,''):return None
        if not isinstance(value,str):raise ValueError(label+': укажите дату и время')
        try:parsed=datetime.fromisoformat(value)
        except ValueError:raise ValueError(label+': укажите корректную дату и время')
        if parsed.tzinfo is not None:raise ValueError(label+': часовой пояс определяется компанией')
        return parsed.isoformat(timespec='minutes')

    def organizer_visible(self,task):
        return 'organizer.manage' in self.permissions or task.get('assignee_user_id')==self.u['id'] or task.get('created_by')==self.u['id']

    def organizer_can_edit(self,task):
        if self.u.get('technical_owner') or task.get('created_by')==self.u['id']:return True
        if self.u.get('role')=='director':return True
        if self.u.get('role')=='admin':
            users={u['id']:u for u in self.r.catalog('users')};creator=users.get(task.get('created_by'),{})
            return creator.get('role') in {'admin','manager'} and task.get('assignee_role')=='manager'
        return False

    def organizer_public(self,task):
        users={u['id']:u for u in self.r.catalog('users')}
        creator=users.get(task.get('created_by'),{});assignee=users.get(task.get('assignee_user_id'),{})
        item=dict(task,created_by_name=creator.get('display_name') or task.get('created_by_name') or 'Сотрудник',
            assignee_name=assignee.get('display_name') or task.get('assignee_name') or 'Сотрудник',
            assignee_role_label=ORGANIZER_ROLE_LABELS.get(assignee.get('role') or task.get('assignee_role'),'Сотрудник'))
        item['can_edit']=self.organizer_can_edit(task)
        item['can_change_status']=item['can_edit'] or task.get('assignee_user_id')==self.u['id']
        return item

    def organizer_event(self,task,event,detail=''):
        self.r.insert('organizer_events',dict(task_id=task['id'],event=event,actor_id=self.u['id'],
            actor_name=self.u.get('display_name') or self.u.get('username') or 'Сотрудник',detail=detail,occurred_at=self.clock()))

    def organizer_next_due(self,value,repeat_rule):
        due=datetime.fromisoformat(value)
        if repeat_rule=='daily':return (due+timedelta(days=1)).isoformat(timespec='minutes')
        if repeat_rule=='weekly':return (due+timedelta(days=7)).isoformat(timespec='minutes')
        if repeat_rule=='monthly':
            year=due.year+(1 if due.month==12 else 0);month=1 if due.month==12 else due.month+1
            return due.replace(year=year,month=month,day=min(due.day,calendar.monthrange(year,month)[1])).isoformat(timespec='minutes')
        return None

    def organizer_create(self,b,recurrence_of=None,allowed_assignees=None):
        self.need('organizer.assign');allowed=allowed_assignees or {u['id']:u for u in self.organizer_users()}
        assignee=b.get('assignee_user_id',self.u['id'])
        if type(assignee) is not int or assignee not in allowed:raise PermissionError('Нельзя поставить задачу этому сотруднику')
        title=text(b.get('title'),'Название задачи')
        if len(title)>200:raise ValueError('Название задачи: до 200 символов')
        description=b.get('description','')
        if not isinstance(description,str) or len(description.strip())>4000:raise ValueError('Описание: до 4000 символов')
        due=self.organizer_moment(b.get('due_at'),'Срок');remind=self.organizer_moment(b.get('remind_at'),'Напоминание',True)
        if remind and remind>due:raise ValueError('Напоминание должно быть не позже срока задачи')
        priority=b.get('priority','normal');repeat=b.get('repeat_rule','none')
        if priority not in ORGANIZER_PRIORITIES:raise ValueError('Неизвестный приоритет задачи')
        if repeat not in ORGANIZER_REPEATS:raise ValueError('Неизвестное правило повтора')
        linked_type=b.get('linked_type') or '';linked_id=str(b.get('linked_id') or '').strip()
        if linked_type not in {'','client','invoice','document','request'} or linked_type and not linked_id:raise ValueError('Проверьте связь задачи')
        target=allowed[assignee]
        task=self.r.insert('organizer_tasks',dict(title=title,description=description.strip(),assignee_user_id=assignee,
            assignee_name=target['display_name'],assignee_role=target['role'],created_by=self.u['id'],
            created_by_name=self.u.get('display_name') or self.u.get('username') or 'Сотрудник',due_at=due,remind_at=remind,
            priority=priority,repeat_rule=repeat,linked_type=linked_type,linked_id=linked_id,status='new',
            completed_at=None,recurrence_of=recurrence_of,next_task_id=None))
        self.organizer_event(task,'created','Задача создана');return task

    def organizer(self,b):
        mode=b.get('mode','create')
        if mode=='create':return self.organizer_create(b)
        self.need('organizer.read');task=self.r.get('organizer_tasks',str(b.get('task_id') or ''))
        if not self.organizer_visible(task):raise PermissionError('Задача недоступна')
        can_edit=self.organizer_can_edit(task)
        can_status=can_edit or task.get('assignee_user_id')==self.u['id']
        if mode=='status':
            if not can_status:raise PermissionError('Нельзя изменить статус этой задачи')
            status=b.get('status')
            if status not in ORGANIZER_STATUSES:raise ValueError('Неизвестный статус задачи')
            if status=='cancelled' and not can_edit:raise PermissionError('Отменить задачу может постановщик или руководитель')
            previous=task.get('status','new');task['status']=status;task['completed_at']=self.clock() if status=='done' else None
            self.r.update('organizer_tasks',task);self.organizer_event(task,'status',previous+' → '+status)
            if status=='done' and task.get('repeat_rule') in ORGANIZER_REPEATS-{'none'} and not task.get('next_task_id'):
                next_due=self.organizer_next_due(task['due_at'],task['repeat_rule'])
                follow=dict(title=task['title'],description=task.get('description',''),assignee_user_id=task['assignee_user_id'],
                    due_at=next_due,priority=task.get('priority','normal'),repeat_rule=task['repeat_rule'],
                    linked_type=task.get('linked_type',''),linked_id=task.get('linked_id',''))
                if task.get('remind_at'):
                    delta=datetime.fromisoformat(task['due_at'])-datetime.fromisoformat(task['remind_at'])
                    follow['remind_at']=(datetime.fromisoformat(next_due)-delta).isoformat(timespec='minutes')
                created=self.r.insert('organizer_tasks',dict(title=task['title'],description=task.get('description',''),
                    assignee_user_id=task['assignee_user_id'],assignee_name=task.get('assignee_name','Сотрудник'),
                    assignee_role=task.get('assignee_role'),created_by=task['created_by'],created_by_name=task.get('created_by_name','Сотрудник'),
                    due_at=follow['due_at'],remind_at=follow.get('remind_at'),priority=task.get('priority','normal'),
                    repeat_rule=task['repeat_rule'],linked_type=task.get('linked_type',''),linked_id=task.get('linked_id',''),
                    status='new',completed_at=None,recurrence_of=task['id'],next_task_id=None))
                self.organizer_event(created,'created','Следующая повторяющаяся задача создана автоматически')
                task['next_task_id']=created['id'];self.r.update('organizer_tasks',task)
            return task
        if mode=='reschedule':
            if not can_edit:raise PermissionError('Изменить срок может постановщик или руководитель')
            old=task['due_at'];task['due_at']=self.organizer_moment(b.get('due_at'),'Срок')
            task['remind_at']=self.organizer_moment(b.get('remind_at'),'Напоминание',True)
            if task['remind_at'] and task['remind_at']>task['due_at']:raise ValueError('Напоминание должно быть не позже срока задачи')
            self.r.update('organizer_tasks',task);self.organizer_event(task,'rescheduled',old+' → '+task['due_at']);return task
        if mode=='edit':
            if not can_edit:raise PermissionError('Изменить задачу может постановщик или руководитель')
            if 'title' in b:
                task['title']=text(b.get('title'),'Название задачи')
                if len(task['title'])>200:raise ValueError('Название задачи: до 200 символов')
            if 'description' in b:
                if not isinstance(b['description'],str) or len(b['description'].strip())>4000:raise ValueError('Описание: до 4000 символов')
                task['description']=b['description'].strip()
            if 'priority' in b:
                if b['priority'] not in ORGANIZER_PRIORITIES:raise ValueError('Неизвестный приоритет задачи')
                task['priority']=b['priority']
            self.r.update('organizer_tasks',task);self.organizer_event(task,'edited','Задача изменена');return task
        raise ValueError('Неизвестное действие органайзера')

    def organizer_rows(self,params):
        self.need('organizer.read');scope=(params.get('scope',['mine'])[0] or 'mine')
        if scope not in {'mine','incoming','assigned_by_me','company'}:raise ValueError('Неизвестный режим просмотра органайзера')
        if scope=='company' and 'organizer.manage' not in self.permissions:raise PermissionError('Общий список доступен руководителю')
        rows=[self.organizer_public(t) for t in self.r.list('organizer_tasks') if self.organizer_visible(t)]
        if scope=='incoming':rows=[t for t in rows if t['assignee_user_id']==self.u['id']]
        elif scope=='assigned_by_me':rows=[t for t in rows if t['created_by']==self.u['id']]
        elif scope=='mine' and 'organizer.manage' in self.permissions:
            rows=[t for t in rows if t['assignee_user_id']==self.u['id'] or t['created_by']==self.u['id']]
        return sorted(rows,key=lambda t:(t.get('status') in {'done','cancelled'},t.get('due_at') or '9999',t.get('created_at') or ''))

    def organizer_events(self,params):
        self.need('organizer.read');identity=str(params.get('task_id',[''])[0] or '')
        task=self.r.get('organizer_tasks',identity)
        if not self.organizer_visible(task):raise PermissionError('Задача недоступна')
        return self.r.list_by('organizer_events',task_id=identity)

    def organizer_directors(self):
        self.need('organizer.read')
        if not ({'organizer.request.create','organizer.request.decide'} & self.permissions):
            raise PermissionError('Нет доступа к запросам директору')
        rows=[]
        for user in self.r.catalog('users'):
            if user.get('active') and user.get('role')=='director':
                rows.append(dict(id=user['id'],display_name=user.get('display_name') or user.get('username') or 'Директор'))
        return sorted(rows,key=lambda row:row['display_name'].casefold())

    def organizer_request_responsibles(self):
        self.need('organizer.assign')
        if not self.u.get('technical_owner') and self.u.get('role') not in {'director','admin'}:
            raise PermissionError('Назначать ответственного по запросу может директор или управляющий')
        rows=[]
        for user in self.r.catalog('users'):
            if user.get('active') and user.get('role') in {'director','admin','manager'}:
                rows.append(dict(id=user['id'],display_name=user.get('display_name') or user.get('username') or 'Сотрудник',
                    role=user['role'],role_label=ORGANIZER_ROLE_LABELS[user['role']]))
        return sorted(rows,key=lambda row:(row['role_label'],row['display_name'].casefold()))

    def organizer_request_visible(self,request):
        return bool(self.u.get('technical_owner') or request.get('created_by')==self.u['id'] or request.get('director_user_id')==self.u['id'])

    def organizer_request_event(self,request,event,detail='',comment=''):
        self.r.insert('organizer_request_events',dict(organizer_request_id=request['id'],event=event,
            actor_id=self.u['id'],actor_name=self.u.get('display_name') or self.u.get('username') or 'Сотрудник',
            detail=detail,comment=comment,occurred_at=self.clock()))

    def organizer_request_attachment_payload(self,attachment):
        if not isinstance(attachment,dict):raise ValueError('Некорректное вложение')
        original=attachment.get('name');mime=attachment.get('mime_type');encoded=attachment.get('file_b64')
        if not isinstance(original,str) or not original.strip() or len(original.strip())>120:
            raise ValueError('Имя файла: до 120 символов')
        original=original.strip()
        if any(char in original for char in ('/','\\','\x00')) or re.search(r'\.(?:exe|com|bat|cmd|ps1|vbs|js|msi|scr|dll|jar|apk|sh)$',original,re.I):
            raise ValueError('Небезопасное имя или тип файла')
        types={'image/jpeg':'jpg','image/png':'png','image/webp':'webp','application/pdf':'pdf','text/plain':'txt'}
        if mime not in types:raise ValueError('Этот тип файла пока не поддерживается')
        if not isinstance(encoded,str) or len(encoded)>3*1024*1024:raise ValueError('Файл слишком большой')
        try:data=base64.b64decode(encoded,validate=True)
        except Exception:raise ValueError('Некорректное содержимое файла')
        if not data or len(data)>2*1024*1024:raise ValueError('Файл должен быть не больше 2 МБ')
        return dict(original_name=original,filename=f"PORTAL_request_{uuid.uuid4().hex[:16]}.{types[mime]}",
            mime_type=mime,size_bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
            file_b64=base64.b64encode(data).decode('ascii'))

    def organizer_request_public(self,request):
        users={u['id']:u for u in self.r.catalog('users')}
        creator=users.get(request.get('created_by'),{});director=users.get(request.get('director_user_id'),{})
        responsible=users.get(request.get('responsible_user_id'),{}) if request.get('responsible_user_id') else {}
        item=dict(request,
            created_by_name=creator.get('display_name') or request.get('created_by_name') or 'Сотрудник',
            director_name=director.get('display_name') or request.get('director_name') or 'Директор',
            responsible_name=(responsible.get('display_name') or responsible.get('username')) if responsible else None)
        attachments=[]
        for row in self.r.list_by('organizer_request_attachments',organizer_request_id=request['id']):
            if row.get('organizer_request_id')==request['id']:
                attachments.append({k:row[k] for k in ('id','original_name','mime_type','size_bytes','sha256')})
        item['attachments']=attachments
        item['can_decide']='organizer.request.decide' in self.permissions and (self.u.get('technical_owner') or request.get('director_user_id')==self.u['id'])
        item['can_comment']=self.organizer_request_visible(request)
        item['can_create_task']=bool(request.get('status')=='approved' and not request.get('task_id') and
            ('organizer.assign' in self.permissions) and (self.u.get('technical_owner') or self.u.get('role') in {'director','admin'}))
        return item

    def organizer_request_create(self,b):
        self.need('organizer.request.create')
        if not self.u.get('technical_owner') and self.u.get('role') not in {'manager','admin'}:
            raise PermissionError('Создавать запрос директору может управляющий или менеджер')
        director_id=b.get('director_user_id')
        if type(director_id) is not int:raise ValueError('Выберите директора')
        directors={row['id']:row for row in self.organizer_directors()}
        if director_id not in directors:raise PermissionError('Директор другой компании или недоступен')
        request_type=b.get('request_type')
        if request_type not in ORGANIZER_REQUEST_TYPES:raise ValueError('Неизвестный тип запроса')
        title=text(b.get('title'),'Тема запроса')
        if len(title)>200:raise ValueError('Тема запроса: до 200 символов')
        description=b.get('description','')
        if not isinstance(description,str) or len(description.strip())>4000:raise ValueError('Описание: до 4000 символов')
        priority=b.get('priority','normal')
        if priority not in ORGANIZER_PRIORITIES:raise ValueError('Неизвестный приоритет запроса')
        due=self.organizer_moment(b.get('requested_due_at'),'Желаемый срок',True)
        amount=None if b.get('amount') in (None,'') else settlement_cents(b.get('amount'))
        item_name=b.get('item_name','');unit=b.get('unit','');initial_comment=b.get('initial_comment','')
        if not isinstance(item_name,str) or len(item_name.strip())>200:raise ValueError('Материал или товар: до 200 символов')
        if not isinstance(unit,str) or len(unit.strip())>50:raise ValueError('Единица измерения: до 50 символов')
        if not isinstance(initial_comment,str) or len(initial_comment.strip())>2000:raise ValueError('Комментарий: до 2000 символов')
        quantity=b.get('quantity')
        if quantity in (None,''):quantity=None
        else:
            raw=str(quantity)
            if not re.fullmatch(r'[0-9]+(?:\.[0-9]{1,3})?',raw) or Decimal(raw)<=0 or Decimal(raw)>Decimal('1000000000'):
                raise ValueError('Количество: положительное число, до трёх знаков после точки')
            quantity=format(Decimal(raw).normalize(),'f')
        attachment_payload=self.organizer_request_attachment_payload(b['attachment']) if b.get('attachment') else None
        request=self.r.insert('organizer_requests',dict(request_type=request_type,title=title,
            description=description.strip(),priority=priority,requested_due_at=due,amount=amount,
            item_name=item_name.strip(),quantity=quantity,unit=unit.strip(),status='new',
            created_by=self.u['id'],created_by_name=self.u.get('display_name') or self.u.get('username') or 'Сотрудник',
            director_user_id=director_id,director_name=directors[director_id]['display_name'],
            responsible_user_id=None,task_id=None,decided_at=None,completed_at=None,updated_at=self.clock()))
        self.organizer_request_event(request,'created','Запрос создан',initial_comment.strip())
        if attachment_payload:
            self.r.insert('organizer_request_attachments',dict(attachment_payload,
                organizer_request_id=request['id'],uploaded_by=self.u['id']))
        return self.organizer_request_public(request)

    def organizer_request(self,b):
        mode=b.get('mode','create')
        if mode=='create':return self.organizer_request_create(b)
        self.need('organizer.read')
        identity=str(b.get('organizer_request_id') or '')
        request=self.r.get('organizer_requests',identity)
        if not self.organizer_request_visible(request):raise PermissionError('Запрос недоступен')
        if mode=='comment':
            comment=b.get('comment','')
            if not isinstance(comment,str) or not comment.strip() or len(comment.strip())>2000:
                raise ValueError('Комментарий: от 1 до 2000 символов')
            self.organizer_request_event(request,'comment','Комментарий',comment.strip())
            if request.get('status')=='needs_info' and request.get('created_by')==self.u['id']:
                old=request['status'];request['status']='review';request['updated_at']=self.clock()
                self.r.update('organizer_requests',request)
                self.organizer_request_event(request,'status',old+' → review','Информация предоставлена')
            return self.organizer_request_public(request)
        if mode=='decide':
            self.need('organizer.request.decide')
            if not self.u.get('technical_owner') and request.get('director_user_id')!=self.u['id']:
                raise PermissionError('Рассматривать запрос может назначенный директор')
            status=b.get('status')
            if status not in ORGANIZER_REQUEST_STATUSES:raise ValueError('Неизвестный статус запроса')
            current=request.get('status','new')
            if status not in ORGANIZER_REQUEST_TRANSITIONS.get(current,set()):
                raise ValueError('Недопустимый переход статуса запроса')
            responsible=b.get('responsible_user_id',request.get('responsible_user_id'))
            if responsible not in (None,''):
                if type(responsible) is not int:raise ValueError('Некорректный ответственный')
                user=next((u for u in self.r.catalog('users') if u.get('active') and u['id']==responsible and u.get('role') in {'director','admin','manager'}),None)
                if not user:raise PermissionError('Ответственный другой компании или недоступен')
                request['responsible_user_id']=responsible
            comment=b.get('comment','')
            if not isinstance(comment,str) or len(comment.strip())>2000:raise ValueError('Комментарий: до 2000 символов')
            request['status']=status;request['updated_at']=self.clock()
            if status in {'approved','rejected'}:request['decided_at']=self.clock()
            if status=='done':request['completed_at']=self.clock()
            self.r.update('organizer_requests',request)
            self.organizer_request_event(request,'status',current+' → '+status,comment.strip())
            return self.organizer_request_public(request)
        if mode=='create_task':
            if 'organizer.assign' not in self.permissions or (not self.u.get('technical_owner') and self.u.get('role') not in {'director','admin'}):
                raise PermissionError('Создать задачу из запроса может директор или управляющий')
            if request.get('status')!='approved':raise ValueError('Задачу можно создать только по одобренному запросу')
            if request.get('task_id'):return self.organizer_public(self.r.get('organizer_tasks',request['task_id']))
            responsible=b.get('responsible_user_id',request.get('responsible_user_id'))
            if type(responsible) is not int:raise ValueError('Назначьте ответственного')
            allowed={u['id']:u for u in self.r.catalog('users')
                     if u.get('active') and u.get('role') in {'director','admin','manager'}}
            if responsible not in allowed:raise PermissionError('Ответственный другой компании или неактивен')
            due=request.get('requested_due_at')
            if not due:
                base=datetime.fromisoformat(self.clock()).replace(second=0,microsecond=0)
                due=(base+timedelta(days=1)).isoformat(timespec='minutes')
            task=self.organizer_create(dict(assignee_user_id=responsible,title='Запрос: '+request['title'],
                description=request.get('description',''),due_at=due,priority=request.get('priority','normal'),
                repeat_rule='none',linked_type='request',linked_id=request['id']),allowed_assignees=allowed)
            request['responsible_user_id']=responsible;request['task_id']=task['id'];request['updated_at']=self.clock()
            self.r.update('organizer_requests',request)
            self.organizer_request_event(request,'task_created',task['id'],'Создана связанная задача')
            return self.organizer_public(task)
        raise ValueError('Неизвестное действие запроса директору')

    def organizer_request_rows(self,params):
        self.need('organizer.read');scope=(params.get('scope',['mine'])[0] or 'mine')
        if scope not in {'mine','incoming'}:raise ValueError('Неизвестный режим запросов')
        rows=self.r.list('organizer_requests')
        if scope=='mine':
            if 'organizer.request.create' not in self.permissions:raise PermissionError('Нет доступа к своим запросам')
            rows=[row for row in rows if row.get('created_by')==self.u['id']]
        else:
            self.need('organizer.request.decide')
            if not self.u.get('technical_owner'):rows=[row for row in rows if row.get('director_user_id')==self.u['id']]
        return [self.organizer_request_public(row) for row in sorted(rows,key=lambda row:(row.get('status') in {'done','rejected'},row.get('created_at') or ''),reverse=True)]

    def organizer_request_events(self,params):
        self.need('organizer.read');identity=str(params.get('organizer_request_id',[''])[0] or '')
        request=self.r.get('organizer_requests',identity)
        if not self.organizer_request_visible(request):raise PermissionError('Запрос недоступен')
        return self.r.list_by('organizer_request_events',organizer_request_id=identity)

    def organizer_request_file(self,identity):
        self.need('organizer.read');attachment=self.r.get('organizer_request_attachments',str(identity or ''))
        request=self.r.get('organizer_requests',attachment.get('organizer_request_id'))
        if not self.organizer_request_visible(request):raise PermissionError('Файл запроса недоступен')
        return {k:attachment[k] for k in ('id','filename','original_name','mime_type','size_bytes','sha256','file_b64')}

    def scoped(self,kind): return [x for x in self.r.list(kind) if 'client_id' not in x or self.visible(x['client_id'])]

    def works(self):
        rows=self.scoped('works')
        if not ({'finance.read','work.link','analytics.read','payroll.all','invoices.create'} & self.permissions): rows=[w for w in rows if w['user_id']==self.u['id']]
        link_rows=self.r.list('links')
        result=[]
        for w in rows:
            w=dict(w,batch_id=self.batch_for_work(w,link_rows))
            if 'finance.read' not in self.permissions and 'invoices.create' not in self.permissions:
                for k in ('client_rate','revenue'): w.pop(k,None)
            if 'payroll.all' not in self.permissions and not(w['user_id']==self.u['id'] and 'payroll.own' in self.permissions):
                for k in ('salary','employee_rate'):w.pop(k,None)
            result.append(w)
        return result

    def task_rows(self,task_rows=None,work_rows=None,batch_rows=None,client_rows=None):
        self.need('tasks.read')
        rows=self.scoped('tasks') if task_rows is None else [dict(t) for t in task_rows if self.visible(t['client_id'])]
        works=self.r.list('works') if work_rows is None else work_rows
        batches={b['id']:b for b in (self.r.list('batches') if batch_rows is None else batch_rows)}
        clients={c['id']:c for c in (self.r.catalog('clients') if client_rows is None else client_rows)}
        if 'tasks.manage' not in self.permissions: rows=[t for t in rows if self.u['id'] in t['assignees']]
        for t in rows:
            t['done']=sum(w['quantity'] for w in works if w.get('task_id')==t['id']);t['remaining']=max(0,t['quantity']-t['done'])
            batch=batches.get(t['batch_id']);client=clients.get(t['client_id'])
            if not batch or not client:raise ValueError('Задание связано с недоступной партией или клиентом')
            t['batch_number']=batch['number'];t['client_name']=client['name']
        return rows

    def progress(self,batch,task_rows=None,work_rows=None,shipment_rows=None,link_rows=None):
        task_source=self.r.list('tasks') if task_rows is None else task_rows
        work_source=self.r.list('works') if work_rows is None else work_rows
        shipment_source=self.r.list('shipments') if shipment_rows is None else shipment_rows
        link_source=self.r.list('links') if link_rows is None else link_rows
        tasks=[t for t in task_source if t['batch_id']==batch['id']]
        works=[w for w in work_source if self.batch_for_work(w,link_source)==batch['id']]
        shipment=next((item for item in shipment_source if item['batch_id']==batch['id'] and item.get('type')!='return'),None)
        returned=sum(item.get('quantity',0) for item in shipment_source if item['batch_id']==batch['id'] and item.get('type')=='return')
        done_by={t['id']:sum(w['quantity'] for w in works if w.get('task_id')==t['id']) for t in tasks}
        # Different operations are NOT summed as finished physical units.
        done=min(done_by.values()) if tasks else 0
        ready=bool(tasks) and all(done_by[t['id']]>=t['quantity'] for t in tasks)
        return dict(batch,done=done,remaining=max(0,batch['quantity']-done),ready=ready,
                    stage='returned' if batch['status']=='returned' else 'partially_returned' if batch['status']=='partially_returned' else 'shipped' if batch['status']=='shipped' else 'ready' if ready else 'in_progress' if works else 'received',
                    operations=[dict(operation=t['operation_name'],done=done_by[t['id']],planned=t['quantity']) for t in tasks],
                    performers=sorted({w['user_id'] for w in works}),returned_quantity=returned,
                    returnable_quantity=max(0,(shipment or {}).get('quantity',0)-returned))

    def ship(self,b):
        self.need('batches.receive');batch=self.entity('batches',b['batch_id'])
        if batch['status'] in ('shipped','partially_returned','returned') or not self.progress(batch)['ready']: raise ValueError('Партия ещё не готова или уже отгружена')
        if b.get('direction') not in ('FBO','FBS','shipment'): raise ValueError('Выберите направление отгрузки')
        batch.update(status='shipped',direction=b['direction']);self.r.update('batches',batch)
        return self.r.insert('shipments',dict(batch_id=batch['id'],client_id=batch['client_id'],direction=b['direction'],quantity=batch['quantity']))

    def return_batch(self,b):
        self.need('batches.receive')
        batch=self.entity('batches',b['batch_id'])
        if batch['status'] not in ('shipped','partially_returned'):
            raise ValueError('Возврат разрешён только для отгруженной партии')
        quantity=qty(b.get('quantity'))
        condition=b.get('condition','unknown')
        if condition not in ('resalable','damaged','unknown'):
            raise ValueError('Укажите состояние возвращённого товара')
        shipment_rows=self.r.list_by('shipments',batch_id=batch['id'])
        shipment=next((item for item in shipment_rows if item.get('type')!='return'),None)
        if shipment is None:raise ValueError('Исходная отгрузка не найдена')
        returned=sum(item.get('quantity',0) for item in shipment_rows if item.get('type')=='return')
        remaining=shipment['quantity']-returned
        if quantity>remaining:raise ValueError('Возвращаемое количество превышает остаток отгрузки')
        item=self.r.insert('shipments',dict(type='return',batch_id=batch['id'],client_id=batch['client_id'],
            direction=shipment['direction'],quantity=quantity,condition=condition,
            comment=text(b.get('comment'),optional=True),recorded_by=self.u['id']))
        new_returned=returned+quantity
        batch['status']='returned' if new_returned==shipment['quantity'] else 'partially_returned'
        self.r.update('batches',batch)
        return dict(item,returned_quantity=new_returned,returnable_quantity=shipment['quantity']-new_returned)

    def economy(self,batch_id):
        self.need('finance.read');batch=self.entity('batches',batch_id)
        works=[w for w in self.scoped('works') if self.batch_for_work(w)==batch_id];ids={w['id'] for w in works}
        plans=[p for p in self.scoped('plans') if p['batch_id']==batch_id]
        # No plan rows means "unavailable", not a confirmed zero-cost/zero-revenue plan.
        plan={k:(sum(p[k] for p in plans) if plans else None) for k in ('salary','revenue','materials','other')}
        fact=dict(salary=sum(w['salary'] for w in works),revenue=sum(w['revenue'] for w in works),materials=sum(u['cost'] for u in self.scoped('usage') if u['work_id'] in ids),other=sum(e['amount'] for e in self.scoped('expenses') if e['batch_id']==batch_id))
        fact['profit']=fact['revenue']-fact['salary']-fact['materials']-fact['other']
        plan['profit']=(plan['revenue']-plan['salary']-plan['materials']-plan['other']) if plans else None
        plan['volume']=sum(p['quantity'] for p in plans) if plans else None;fact['volume']=sum(w['quantity'] for w in works)
        margins={key:margin_basis_points(values['profit'],values['revenue']) for key,values in (('plan',plan),('fact',fact))}
        margins['deviation']=(margins['fact']-margins['plan']
                              if margins['fact'] is not None and margins['plan'] is not None else None)
        units=self.progress(batch)['done']
        deviation={k:(fact[k]-plan[k] if plan[k] is not None else None) for k in plan}
        def per_unit_kopecks(amount):
            if not units:return None
            sign=-1 if amount<0 else 1
            return sign*((abs(amount)+units//2)//units)
        return dict(batch_id=batch_id,plan=plan,fact=fact,deviation=deviation,margin_bps=margins,finished_units=units,
                    cost_per_unit=per_unit_kopecks(fact['salary']+fact['materials']+fact['other']),
                    profit_per_unit=per_unit_kopecks(fact['profit']))

    def finance(self):
        self.need('finance.read');works=self.scoped('works');usage=self.scoped('usage');expenses=self.scoped('expenses')
        offset=self.settings()['utc_offset_minutes']
        clients=[];months={}
        for c in self.r.catalog('clients'):
            if not self.visible(c['id']):continue
            rows=[w for w in works if w['client_id']==c['id']];revenue=sum(w['revenue'] for w in rows)
            salary=sum(w['salary'] for w in rows);material=sum(u['cost'] for u in usage if u['client_id']==c['id']);other=sum(e['amount'] for e in expenses if e.get('client_id')==c['id'])
            profit=revenue-salary-material-other;batches=[b for b in self.scoped('batches') if b['client_id']==c['id']]
            clients.append(dict(client_id=c['id'],client_name=c['name'],revenue=revenue,salary=salary,materials=material,other=other,
                profit=profit,margin=profit/revenue if revenue else None,margin_bps=margin_basis_points(profit,revenue),
                average_batch_profit=sum(self.economy(b['id'])['fact']['profit'] for b in batches)/len(batches) if batches else None))
        for w in works:
            month=company_date(w['completed_at'],offset).strftime('%Y-%m');m=months.setdefault(month,dict(revenue=0,salary=0,materials=0,other=0,overhead=0));m['revenue']+=w['revenue'];m['salary']+=w['salary']
        for row in usage:
            month=company_date(row['created_at'],offset).strftime('%Y-%m');m=months.setdefault(month,dict(revenue=0,salary=0,materials=0,other=0,overhead=0));m['materials']+=row['cost']
        for row in expenses:
            month=company_date(row.get('incurred_at') or row['created_at'],offset).strftime('%Y-%m');m=months.setdefault(month,dict(revenue=0,salary=0,materials=0,other=0,overhead=0))
            if row.get('client_id') is None:m['overhead']+=row['amount']
            else:m['other']+=row['amount']
        for m in months.values():
            m['profit']=m['revenue']-m['salary']-m['materials']-m['other']-m['overhead']
            m['margin_bps']=margin_basis_points(m['profit'],m['revenue'])
        overhead=sum(e['amount'] for e in expenses if e.get('client_id') is None)
        total_revenue=sum(c['revenue'] for c in clients)
        totals={key:sum(c[key] for c in clients) for key in ('revenue','salary','materials','other')}
        client_profit=sum(c['profit'] for c in clients)
        net_profit=client_profit-overhead
        return dict(clients=clients,months=months,totals=totals,company_overhead=overhead,client_profit=client_profit,
                    client_margin_bps=margin_basis_points(client_profit,total_revenue),net_profit=net_profit,
                    net_margin_bps=margin_basis_points(net_profit,total_revenue),currency='RUB',money_unit='kopeck')

    def invoices(self):
        self.need('invoices.read');rows=self.scoped('invoices');payments=self.scoped('payments')
        for i in rows:
            revisions=sorted(self.r.list_by('invoice_revisions',invoice_id=i['id']),key=lambda r:r['revision'])
            if revisions:
                latest=revisions[-1]
                i.update(latest['snapshot'],state=latest['state'],revision=latest['revision'],
                    revision_history=[r.get('previous_snapshot',r['snapshot']) for r in revisions if r['state']=='finalized'])
            else:
                i.setdefault('state','finalized');i.setdefault('revision',1);i.setdefault('revision_history',[])
            i['paid']=sum(p['amount'] for p in payments if p['invoice_id']==i['id']);i['remaining']=i['amount']-i['paid']
            i['status']='paid' if not i['remaining'] else 'partial' if i['paid'] else 'unpaid'
        return rows

    def receivables(self,params):
        self.need('invoices.read')
        client_filter=params.get('client_id',[None])[0]
        if client_filter not in (None,''):
            try:client_filter=int(client_filter)
            except (TypeError,ValueError):raise ValueError('Некорректный клиент')
            self.client(client_filter)
        settings=self.settings()
        local_today=(datetime.fromisoformat(self.clock())+timedelta(minutes=settings['utc_offset_minutes'])).date()
        buckets={key:dict(count=0,amount=0) for key in ('current','days_1_7','days_8_30','days_31_60','days_61_plus','undated')}
        clients={};items=[];overdue_total=0;outstanding_total=0
        for invoice in self.invoices():
            remaining=invoice['remaining']
            # Legacy/non-client invoice rows can remain in the shared invoice
            # ledger (for example imported documents without a client link).
            # Aging is a client receivables report, so do not invent a client
            # association for those rows or let them break the whole report.
            invoice_client_id=invoice.get('client_id')
            if remaining<=0 or invoice_client_id is None:continue
            if client_filter is not None and invoice_client_id!=client_filter:continue
            due_text=invoice.get('due_at');overdue=0
            if not due_text:bucket='undated'
            else:
                try:due_date=company_date(due_text,settings['utc_offset_minutes'])
                except (TypeError,ValueError):raise ValueError('В счёте сохранена некорректная дата оплаты')
                overdue=max(0,(local_today-due_date).days)
                bucket='current' if overdue==0 else 'days_1_7' if overdue<=7 else 'days_8_30' if overdue<=30 else 'days_31_60' if overdue<=60 else 'days_61_plus'
            item=dict(invoice_id=invoice['id'],client_id=invoice_client_id,amount=invoice['amount'],paid=invoice['paid'],outstanding=remaining,due_at=due_text,overdue_days=overdue,bucket=bucket,status=invoice['status'])
            items.append(item);outstanding_total+=remaining;buckets[bucket]['count']+=1;buckets[bucket]['amount']+=remaining
            if overdue:overdue_total+=remaining
            total=clients.setdefault(invoice_client_id,dict(client_id=invoice_client_id,name=invoice.get('client_name') or next((c['name'] for c in self.r.catalog('clients') if c['id']==invoice_client_id),''),outstanding=0,overdue=0,invoice_count=0))
            total['outstanding']+=remaining;total['invoice_count']+=1
            if overdue:total['overdue']+=remaining
        items.sort(key=lambda row:(row['due_at'] or '9999-12-31',row['invoice_id']))
        try:page=max(1,int(params.get('page',['1'])[0] or 1));limit=min(100,max(1,int(params.get('limit',['50'])[0] or 50)))
        except (TypeError,ValueError):raise ValueError('Некорректная страница дебиторки')
        total=len(items);items=items[(page-1)*limit:page*limit]
        return dict(as_of=local_today.isoformat(),currency='RUB',money_unit='kopeck',outstanding=outstanding_total,overdue=overdue_total,
                    buckets=buckets,clients=sorted(clients.values(),key=lambda row:(row['name'].casefold(),row['client_id'])),items=items,page=page,limit=limit,total=total)

    def analytics(self,params=None):
        params=params or {}
        all_team='analytics.read' in self.permissions
        if not all_team:self.need('work.write')
        rows=[w for w in self.scoped('works') if all_team or w['user_id']==self.u['id']];groups={};batch_groups={}
        users={u['id']:u.get('display_name') or u.get('username') or str(u['id']) for u in self.r.catalog('users')}
        clients={c['id']:c['name'] for c in self.r.catalog('clients')}
        operations={o['id']:o['name'] for o in self.r.catalog('operations')}
        batches={b['id']:b for b in self.scoped('batches')}
        start_text=params.get('from',[''])[0];end_text=params.get('to',[''])[0]
        if bool(start_text)!=bool(end_text):raise ValueError('Укажите обе даты периода')
        comparison=None
        if start_text:
            try:
                start=datetime.strptime(start_text,'%Y-%m-%d').date();end=datetime.strptime(end_text,'%Y-%m-%d').date()
            except (TypeError,ValueError):raise ValueError('Период аналитики должен быть задан датами YYYY-MM-DD')
            if start.isoformat()!=start_text or end.isoformat()!=end_text or end<start or (end-start).days>365:
                raise ValueError('Период аналитики должен быть от 1 до 366 дней')
            offset=self.settings()['utc_offset_minutes']
            all_rows=rows
            previous_end=start-timedelta(days=1);previous_start=previous_end-timedelta(days=(end-start).days)
            rows=[w for w in all_rows if start<=company_date(w['completed_at'],offset)<=end]
            previous=[w for w in all_rows if previous_start<=company_date(w['completed_at'],offset)<=previous_end]
            def measure(items):
                timed=[w for w in items if w.get('duration_seconds') and w['duration_seconds']>0]
                timed_units=sum(w['quantity'] for w in timed);seconds=sum(w['duration_seconds'] for w in timed)
                return dict(units=sum(w['quantity'] for w in items),timed_units=timed_units,seconds=seconds,
                            units_per_hour=timed_units/(seconds/3600) if seconds else None)
            current_measure=measure(rows);previous_measure=measure(previous)
            comparison=dict(period_start=start.isoformat(),period_end=end.isoformat(),
                previous_start=previous_start.isoformat(),previous_end=previous_end.isoformat(),
                current=current_measure,previous=previous_measure,
                units_delta=current_measure['units']-previous_measure['units'],
                units_percent_delta=((current_measure['units']-previous_measure['units'])/previous_measure['units']*100) if previous_measure['units'] else None,
                units_per_hour_delta=(current_measure['units_per_hour']-previous_measure['units_per_hour'])
                    if current_measure['units_per_hour'] is not None and previous_measure['units_per_hour'] is not None else None)
        else:all_rows=rows
        def add_sample(group,work):
            group['quantity']+=work['quantity'];group['samples']+=1
            if work.get('duration_seconds') and work['duration_seconds']>0:
                group['timed_quantity']+=work['quantity'];group['seconds']+=work['duration_seconds']
                group['rates'].append(work['quantity']/work['duration_seconds']*3600)
        def finish_group(group):
            rates=group.pop('rates');group['units_per_hour']=group['timed_quantity']/group['seconds']*3600 if group['seconds'] else None
            mean=sum(rates)/len(rates) if rates else 0
            group['variability']=((sum((v-mean)**2 for v in rates)/len(rates))**.5/mean) if len(rates)>=2 and mean else None
        for w in rows:
            batch_id=w.get('batch_id') or self.batch_for_work(w)
            batch=batches.get(batch_id) if batch_id else None
            product=w.get('product') or (batch or {}).get('product','')
            key=(w['user_id'],w['client_id'],product,w['operation_id'])
            g=groups.setdefault(key,dict(user_id=key[0],user_name=users.get(key[0],str(key[0])),
                client_id=key[1],client_name=clients.get(key[1],str(key[1])),product=key[2],operation_id=key[3],
                operation_name=operations.get(key[3],str(key[3])),quantity=0,samples=0,timed_quantity=0,seconds=0,rates=[]))
            add_sample(g,w)
            if batch_id:
                bkey=(batch_id,w['operation_id'])
                bg=batch_groups.setdefault(bkey,dict(batch_id=batch_id,batch_number=(batch or {}).get('number',str(batch_id)),
                    client_id=w['client_id'],client_name=clients.get(w['client_id'],str(w['client_id'])),
                    product=product,operation_id=w['operation_id'],operation_name=operations.get(w['operation_id'],str(w['operation_id'])),
                    quantity=0,samples=0,timed_quantity=0,seconds=0,rates=[]))
                add_sample(bg,w)
        for group in groups.values():finish_group(group)
        for group in batch_groups.values():finish_group(group)
        quality_samples=[]
        for work in rows:
            q=work.get('quality') if isinstance(work.get('quality'),dict) else {}
            defects=q.get('defects')
            if isinstance(defects,(int,float)) and not isinstance(defects,bool) and defects>=0:
                quality_samples.append((work,defects))
        quality=(dict(available=True,recorded_units=sum(w['quantity'] for w,_ in quality_samples),defects=sum(v for _,v in quality_samples))
                 if quality_samples else dict(available=False,recorded_units=0,defects=None))
        forecasts=[]
        for t in self.scoped('tasks'):
            if not all_team and self.u['id'] not in t['assignees']:continue
            observations=[w for w in all_rows if w.get('task_id')==t['id']];done=sum(w['quantity'] for w in observations)
            timed=[w for w in observations if w['started_at']];elapsed=(datetime.fromisoformat(self.clock())-min(datetime.fromisoformat(w['started_at']) for w in timed)).total_seconds() if timed else 0
            pace=done/elapsed if elapsed>0 else 0
            eta=(datetime.fromisoformat(self.clock())+timedelta(seconds=max(0,t['quantity']-done)/pace)).isoformat() if pace else None
            forecasts.append(dict(task_id=t['id'],done=done,remaining=max(0,t['quantity']-done),units_per_hour=pace*3600 if pace else None,estimated_completion=eta,due_at=t['due_at']))
        result=dict(groups=list(groups.values()),batch_groups=list(batch_groups.values()),forecasts=forecasts,quality=quality,ranking=False)
        if comparison is not None:result['comparison']=comparison
        return result

    def today(self):
        settings=self.settings();now=datetime.fromisoformat(self.clock())+timedelta(minutes=settings['utc_offset_minutes']);day=now.date().isoformat()
        works=self.scoped('works');local_dates={w['id']:company_date(w['completed_at'],settings['utc_offset_minutes']) for w in works}
        today_works=[w for w in works if local_dates[w['id']].isoformat()==day]
        month_works=[w for w in works if local_dates[w['id']].year==now.year and local_dates[w['id']].month==now.month]
        mine=[w for w in today_works if w['user_id']==self.u['id']]
        batch_rows=self.scoped('batches');task_source=self.r.list('tasks');shipment_rows=self.r.list('shipments');link_rows=self.r.list('links')
        batches=[self.progress(b,task_source,works,shipment_rows,link_rows) for b in batch_rows];attention=[]
        manager=bool({'tasks.manage','batches.receive','finance.read'} & self.permissions)
        if manager:
            for b in batches:
                if b['due_at'] and not b['ready'] and b['due_at']<self.clock():attention.append(dict(type='batch_late',label='Партия просрочена',batch_id=b['id'],number=b['number']))
        if 'materials.read' in self.permissions:
            for m in self.r.catalog('materials'):
                if m['active'] and m['stock_qty']<=m['min_stock']:attention.append(dict(type='material_low',label='Критический остаток материала',name=m['name'],quantity=m['stock_qty']))
        unbilled=[]
        if {'invoices.create','invoices.read','finance.read'} & self.permissions:
            billed=self.billed_work_ids();unbilled=[w for w in works if w['id'] not in billed]
            if unbilled:attention.append(dict(type='not_invoiced',label='Выполненная работа не выставлена клиенту',amount=sum(w['revenue'] for w in unbilled),clients=[dict(client_id=cid,amount=sum(w['revenue'] for w in unbilled if w['client_id']==cid),work_ids=[w['id'] for w in unbilled if w['client_id']==cid]) for cid in sorted({w['client_id'] for w in unbilled})]))
        invoices=self.invoices() if 'invoices.read' in self.permissions else []
        for i in invoices:
            if i['due_at'] and i['remaining'] and company_date(i['due_at'],settings['utc_offset_minutes']).isoformat()<day:attention.append(dict(type='payment_late',label='Просрочена оплата',invoice_id=i['id'],amount=i['remaining']))
        if {'invoices.read','finance.read'} & self.permissions:
            notices=self.r.list_recent('notifications',20,'occurred_at')
            attention.extend(dict(type='reminder',label=item['title'],entity_id=item['entity_id'],notification_id=item['id']) for item in notices)
        check='monday' if now.weekday()==0 and now.strftime('%H:%M')>=settings['monday_time'] else 'wednesday' if now.weekday()==2 and now.strftime('%H:%M')>=settings['wednesday_time'] else None
        if check and invoices:attention.append(dict(type='control_'+check,label='Контроль счетов и оплат',paid=sum(i['status']=='paid' for i in invoices),partial=sum(i['status']=='partial' for i in invoices),unpaid=sum(i['status']=='unpaid' for i in invoices),not_invoiced=len(unbilled)))
        tasks=self.task_rows(task_source,works,batch_rows,self.r.catalog('clients')) if 'tasks.read' in self.permissions else []
        result=dict(date=day,mode='management' if manager else 'worker',own_quantity=sum(w['quantity'] for w in mine),attention=attention,tasks=tasks)
        if 'payroll.own' in self.permissions:result['own_salary']=sum(w['salary'] for w in mine)
        if manager:
            result.update(active_batches=sum(b['stage'] not in ('shipped','returned') for b in batches),
                in_progress=sum(b['stage']=='in_progress' for b in batches),
                ready=sum(b['ready'] and b['stage'] not in ('shipped','returned') for b in batches),
                active_jobs=sum(t['remaining']>0 for t in tasks),today_quantity=sum(w['quantity'] for w in today_works),
                month_quantity=sum(w['quantity'] for w in month_works))
        if 'finance.read' in self.permissions:
            data=self.finance();result['finance']={key:sum(c[key] for c in data['clients']) for key in ('revenue','salary','materials','other')}
            result['finance'].update(company_overhead=data['company_overhead'],profit=data['net_profit'])
            result['today_finance']=dict(revenue=sum(w['revenue'] for w in today_works),salary=sum(w['salary'] for w in today_works))
            result['month_finance']=dict(revenue=sum(w['revenue'] for w in month_works),salary=sum(w['salary'] for w in month_works),
                                         direct_payroll=sum(w['salary'] for w in month_works))
            plan_profits=[self.economy(b['id'])['plan']['profit'] for b in batches if b['stage'] not in ('shipped','returned')]
            result['expected_profit']=None if not plan_profits or any(value is None for value in plan_profits) else sum(plan_profits)
            result['client_profitability_alerts']=sum(client['profit']<0 for client in data['clients'])
        if {'payroll.all','payroll.settlement.read'} & self.permissions:
            closed=[period for period in self.r.list_by('payroll_periods',status='closed')
                    if period['period_start'][:7]==day[:7] and period['period_end']<=day]
            settled=None
            if closed and self.r.has_table('payroll_settlement_entries'):
                accrued=sum(employee['salary'] for period in closed
                            for employee in period['snapshot'].get('employees',[]))
                entries=[entry for period in closed for entry in self.r.payroll_settlements(period['id'])]
                paid=sum(entry['amount_minor'] for entry in entries if entry['effect']=='payment')
                adjustments=sum(entry['amount_minor'] for entry in entries if entry['effect']!='payment')
                settled=dict(period_count=len(closed),accrued=accrued,paid=paid,balance=accrued+adjustments-paid,
                             money_unit='kopeck',currency='RUB')
            result['closed_month_payroll']=settled
        if 'invoices.read' in self.permissions:result['debt']=sum(i['remaining'] for i in invoices)
        if 'invoices.read' in self.permissions:
            open_invoices=[i for i in invoices if i['remaining']>0]
            overdue_invoices=[i for i in open_invoices if i.get('due_at') and company_date(i['due_at'],settings['utc_offset_minutes']).isoformat()<day]
            result['open_invoice_count']=len(open_invoices)
            result['overdue_invoice_count']=len(overdue_invoices)
            result['overdue_debt']=sum(i['remaining'] for i in overdue_invoices)
        if 'analytics.read' in self.permissions:
            groups=self.analytics()['groups'];timed_units=sum(g['timed_quantity'] for g in groups);seconds=sum(g['seconds'] for g in groups)
            result['productivity']=dict(units=sum(g['quantity'] for g in groups),timed_units=timed_units,
                                        units_per_hour=timed_units/(seconds/3600) if seconds>0 else None)
            timed_today=[w for w in today_works if w.get('duration_seconds') and w['duration_seconds']>0]
            today_seconds=sum(w['duration_seconds'] for w in timed_today)
            result['today_productivity']=dict(units=sum(w['quantity'] for w in today_works),
                timed_units=sum(w['quantity'] for w in timed_today),
                units_per_hour=sum(w['quantity'] for w in timed_today)/(today_seconds/3600) if today_seconds>0 else None)
        return result

    def command(self,action,body):
        if 'company_id' in body and (type(body['company_id']) is not int or body['company_id']!=self.r.company_id):raise PermissionError('Компания определяется сессией')
        methods={'batches':self.batch,'products':self.product,'client-requisites':self.save_client_requisites,'tasks':self.task,'work':self.work,'timers':self.timer,'links':self.link,'tariffs':self.create_tariff,'permissions':self.set_permissions,'usage':self.usage,'expenses':self.expense,'invoices':self.invoice,'payments':self.payment,'settings':self.settings,'shipments':self.ship,'returns':self.return_batch,'payroll-periods':self.payroll_period,'payroll-settlements':self.payroll_settlement,'chat':self.chat_command,'documents':self.document,'organizer':self.organizer,'organizer-requests':self.organizer_request}
        if action not in methods: raise ValueError('Действие не поддерживается')
        authorization={'batches':'batches.receive','products':'clients.manage','client-requisites':'clients.manage','tasks':'tasks.manage','work':'work.write','timers':'work.write','links':'work.link','permissions':'users.manage','usage':'materials.use','expenses':'expenses.manage','invoices':'invoices.create','payments':'payments.record','settings':'company.settings','shipments':'batches.receive','returns':'batches.receive','payroll-periods':'payroll.close','chat':'chat.write','documents':'documents.manage'}
        if action in authorization:self.need(authorization[action])
        if action=='settings':self.need_management_role()
        if action=='payroll-settlements':
            entry_type=body.get('entry_type')
            if entry_type not in ('payout','adjustment','reversal'):
                raise ValueError('Тип записи: выплата, корректировка или сторно')
            self.need('payroll.settlement.payout' if entry_type=='payout' else 'payroll.settlement.correct')
            if set(body)-{'company_id','employee_id','payroll_period_id','entry_type',
                          'amount','reason','reference','request_id','reversal_of'}:
                raise ValueError('Неизвестные параметры расчёта; автора и время определяет сервер')
            if entry_type!='reversal' and body.get('reversal_of') is not None:
                raise ValueError('Исходная запись указывается только для сторно')
            if not isinstance(body.get('request_id'),str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',body['request_id']):
                raise ValueError('Идентификатор запроса: латинские буквы, цифры, точка, дефис, двоеточие или подчёркивание')
        if action=='tariffs':
            for field,key in [('employee_rate','rates.employee'),('client_rate','rates.client')]:
                if field in body:self.need(key)
        key=request_identity(body.get('request_id'))
        fingerprint=hashlib.sha256(json.dumps(dict(action=action,body=body,user=self.u['id']),sort_keys=True).encode()).hexdigest()
        old=self.r.get('requests',key,False)
        if old:
            if old['fingerprint']!=fingerprint:raise ValueError('Идентификатор запроса уже использован')
            result=dict(old['result'])
            if action=='work':
                if not {'finance.read','rates.client','invoices.create'} & self.permissions:
                    result.pop('client_rate',None);result.pop('revenue',None)
                if not {'payroll.own','payroll.all','rates.employee'} & self.permissions:
                    result.pop('employee_rate',None);result.pop('salary',None)
            elif action=='tariffs':
                if 'rates.client' not in self.permissions:result.pop('client_rate',None)
                if 'rates.employee' not in self.permissions:result.pop('employee_rate',None)
            return result
        result=methods[action](body)
        if action=='payroll-settlements':
            self.r.audit(self.u,'payroll_settlement.recorded',result['id'],entry_type=result['entry_type'],
                employee_id=result['employee_id'],payroll_period_id=result['payroll_period_id'],
                amount=result['amount'],request_id=result['request_id'],actor_kind=result['actor_kind'],
                reason={'payout':'Выплата зарплаты','adjustment':'Корректировка начисления','reversal':'Сторно записи'}[result['entry_type']],
                reason_sha256=hashlib.sha256(result['reason'].encode('utf-8')).hexdigest())
        else:self.r.audit(self.u,'client.requisites.updated' if action=='client-requisites' else action,
                          result.get('client_id',result.get('id','control')) if action=='client-requisites' else result.get('id','control'))
        result=dict(result)
        if action=='work':
            if not {'finance.read','rates.client','invoices.create'} & self.permissions:
                result.pop('client_rate',None);result.pop('revenue',None)
            if not {'payroll.own','payroll.all','rates.employee'} & self.permissions:
                result.pop('employee_rate',None);result.pop('salary',None)
        elif action=='tariffs':
            if 'rates.client' not in self.permissions:result.pop('client_rate',None)
            if 'rates.employee' not in self.permissions:result.pop('employee_rate',None)
        self.r.insert('requests',dict(fingerprint=fingerprint,result=result),key)
        return result

    def query(self,action,params):
        if action=='today':return self.today()
        if action=='organizer':return self.organizer_rows(params)
        if action=='organizer-users':return self.organizer_users()
        if action=='organizer-events':return self.organizer_events(params)
        if action=='organizer-directors':return self.organizer_directors()
        if action=='organizer-request-responsibles':return self.organizer_request_responsibles()
        if action=='organizer-requests':return self.organizer_request_rows(params)
        if action=='organizer-request-events':return self.organizer_request_events(params)
        if action=='organizer-request-file':return self.organizer_request_file(params.get('id',[None])[0])
        if action=='client-requisites':return self.client_requisites(params)
        if action=='client-name-history':
            self.need('clients.read')
            raw_client_id=params.get('client_id',[None])[0]
            if raw_client_id not in (None,''):
                try:client_id=int(raw_client_id)
                except (TypeError,ValueError):raise ValueError('Некорректный клиент')
                self.client(client_id)
                visible_ids={client_id}
            else:
                visible_ids={client['id'] for client in self.r.catalog('clients') if self.visible(client['id'])}
            rows=self.r.list_by('client_name_history',client_id=client_id) if raw_client_id not in (None,'') else self.r.list('client_name_history')
            return [row for row in rows if row['client_id'] in visible_ids]
        if action=='client-aliases':
            self.need('clients.read')
            raw_client_id=params.get('client_id',[None])[0]
            if raw_client_id not in (None,''):
                try:client_id=int(raw_client_id)
                except (TypeError,ValueError):raise ValueError('Некорректный клиент')
                self.client(client_id)
                visible_ids={client_id}
            else:
                visible_ids={client['id'] for client in self.r.catalog('clients') if self.visible(client['id'])}
            rows=self.r.list_by('client_aliases',client_id=client_id) if raw_client_id not in (None,'') else self.r.list('client_aliases')
            return [row for row in rows if row['client_id'] in visible_ids]
        if action in ('employee-name-history','employee-aliases'):
            self.need('users.manage')
            employee_ids={employee['employee_id'] for employee in self.r.employee_catalog()}
            raw_employee_id=params.get('employee_id',[None])[0]
            if raw_employee_id not in (None,''):
                try:employee_id=int(raw_employee_id)
                except (TypeError,ValueError):raise ValueError('Некорректный сотрудник')
                if employee_id not in employee_ids:raise ValueError('Сотрудник не найден в этой компании')
                employee_ids={employee_id}
            kind='employee_name_history' if action=='employee-name-history' else 'employee_aliases'
            rows=self.r.list_by(kind,employee_id=employee_id) if raw_employee_id not in (None,'') else self.r.list(kind)
            return [row for row in rows if row['employee_id'] in employee_ids]
        if action=='tasks':return self.task_rows()
        if action=='timers':
            if not {'tasks.read','work.write','tasks.manage'} & self.permissions:raise PermissionError('Нет доступа к работе')
            items=self.scoped('work_timers')
            return [t for t in items if t['status'] in ('running','paused') and ('tasks.manage' in self.permissions or t['user_id']==self.u['id'])]
        if action=='batches':
            if not ({'tasks.read','batches.receive','work.write'}&self.permissions):raise PermissionError('Нет доступа к партиям')
            batches=self.scoped('batches');tasks=self.r.list('tasks');works=self.r.list('works');shipments=self.r.list('shipments');links=self.r.list('links')
            return [self.progress(b,tasks,works,shipments,links) for b in batches]
        if action=='shipments':
            self.need('batches.receive');return self.scoped('shipments')
        if action=='works':
            if not {'work.write','payroll.own','work.link','finance.read','analytics.read','payroll.all','invoices.create'} & self.permissions:raise PermissionError('Нет доступа к выработке')
            return self.works()
        if action=='invoices':return self.invoices()
        if action=='receivables':return self.receivables(params)
        if action=='expenses':
            self.need('expenses.read');return self.scoped('expenses')
        if action=='finance':return self.finance()
        if action=='economy':return self.economy(params.get('batch_id',[''])[0])
        if action=='analytics':return self.analytics(params)
        if action=='payroll-periods':
            self.need('payroll.all')
            start=params.get('period_start',[None])[0];end=params.get('period_end',[None])[0]
            return self.payroll_snapshot(start,end) if start or end else [self.public_payroll_period(row) for row in self.r.list('payroll_periods')]
        if action=='payroll-settlements':return self.payroll_settlement_rows(params)
        if action=='chat':return self.chat_rows(params.get('recipient_user_id',[None])[0])
        if action=='chat-users':
            self.need('chat.read')
            return [dict(id=u['id'],display_name=u['display_name']) for u in self.r.catalog('users') if u['active'] and u['id']!=self.u['id']]
        if action=='chat-file':
            return self.chat_file(params.get('id',[None])[0])
        if action=='documents':
            self.need('documents.read');rows=[]
            for document in self.r.list('documents'):
                item=dict(document);item.pop('file_b64',None)
                if 'snapshot' in item:
                    snap=dict(item['snapshot']);snap.pop('details',None);item['snapshot']=snap
                rows.append(item)
            return rows
        if action=='document-file':
            self.need('documents.read');identity=params.get('id',[None])[0]
            document=self.entity('documents',identity)
            return {k:document[k] for k in ('id','filename','mime_type','size_bytes','sha256','file_b64')}
        if action=='settings':
            self.need('company.settings');self.need_management_role()
            return self.settings()
        if action=='permissions':
            self.need('users.manage');self.need_management_role()
            return [dict(u,permissions=sorted(rights.effective(self.r,u))) for u in self.r.catalog('users')]
        if action=='catalog':
            operations=[]
            tariff_rows=self.r.list('tariffs')
            tariff_at=self.clock()
            for op in self.r.catalog('operations'):
                if not op['active'] or not self.visible(op['client_id']):continue
                item={k:op[k] for k in ('id','client_id','name')}
                try:t=self.tariff(op['id'],tariff_at,tariff_rows)
                except ValueError:t={}
                if {'rates.employee','payroll.own'}&self.permissions:item['employee_rate']=t.get('employee_rate')
                if {'rates.client','finance.read'}&self.permissions:item['client_rate']=t.get('client_rate')
                operations.append(item)
            clients=[c for c in self.r.catalog('clients') if c['active'] and self.visible(c['id'])]
            client_ids={c['id'] for c in clients}
            products=[p for p in self.r.list_by('products',active=True) if p['client_id'] in client_ids]
            return dict(clients=clients,operations=operations,products=products,users=self.r.catalog('users') if 'tasks.manage' in self.permissions else [])
        if action=='products':
            if not ({'clients.read','clients.manage'}&self.permissions): raise PermissionError('Нет доступа к товарам')
            return [p for p in self.r.list('products') if self.visible(p['client_id'])]
        if action=='tariff-history':
            if not ({'rates.employee','rates.client','finance.read','payroll.own'}&self.permissions):raise PermissionError('Нет доступа к истории тарифов')
            raw=params.get('operation_id',[''])[0]
            catalog=self.r.catalog('operations')
            if raw not in ('',None):
                try:operation_id=int(raw)
                except (TypeError,ValueError):raise ValueError('Укажите операцию тарифа')
                op=next((item for item in catalog if item['id']==operation_id),None)
                if not op:raise ValueError('Операция не найдена')
                self.client(op['client_id'])
                visible_operations={operation_id}
            else:
                visible_operations={item['id'] for item in catalog if item.get('active') and self.visible(item['client_id'])}
            tariff_rows=self.r.list_by('tariffs',operation_id=operation_id) if raw not in ('',None) else self.r.list('tariffs')
            rows=sorted((dict(t) for t in tariff_rows if t['operation_id'] in visible_operations),key=lambda t:(t['effective_from'],t['created_at'],t['id']),reverse=True)
            for row in rows:
                if 'rates.employee' not in self.permissions:row.pop('employee_rate',None)
                if 'rates.client' not in self.permissions:row.pop('client_rate',None)
            return rows
        raise ValueError('Раздел не найден')
