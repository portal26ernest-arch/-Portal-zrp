"""Production domain. Integer minor currency units; append-only accounting facts.
No SQLite imports or SQL: the repository is the persistence/legacy boundary.
"""
import base64
import calendar
import hashlib
import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from production_repository import utcnow
from report_xlsx import payroll_xlsx
import production_permissions as rights

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

def employee_id(user):
    return user.get('employee_id',user.get('telegram_id'))

def stamp(value, optional=False):
    if optional and not value: return None
    try:
        dt=datetime.fromisoformat(value)
        if dt.tzinfo: raise ValueError()
        return dt.isoformat(timespec='microseconds')
    except (ValueError,TypeError): raise ValueError('Дата: ISO 8601, UTC без смещения')

class Production:
    def __init__(self, repo, user, clock=utcnow):
        self.r,self.u,self.clock=repo,user,clock
        if user.get('company_id')!=repo.company_id: raise PermissionError('Другая компания')
        self.permissions=rights.effective(repo,user)

    def need(self,p): rights.require(self.r,self.u,p)

    def visible(self,client_id):
        # Assignment scope is independent of individually granted capabilities.
        if self.u['role']!='manager' or self.u.get('technical_owner'): return True
        return any(a['client_id']==client_id and a['active'] and a['telegram_id']==employee_id(self.u) for a in self.r.catalog('assignments'))

    def client(self,identity,active=False):
        c=next((c for c in self.r.catalog('clients') if c['id']==identity and self.visible(identity)),None)
        if not c or (active and not c['active']): raise PermissionError('Клиент недоступен')
        return c

    def entity(self,kind,identity):
        obj=self.r.get(kind,identity)
        if 'client_id' in obj: self.client(obj['client_id'])
        return obj

    def operation(self,client_id,identity):
        self.client(client_id,True)
        op=next((o for o in self.r.catalog('operations') if o['id']==identity and o['client_id']==client_id and o['active']),None)
        if not op: raise ValueError('Выберите существующую активную операцию клиента')
        return op

    def tariff(self,operation_id,at=None):
        versions=[t for t in self.r.list('tariffs') if t['operation_id']==operation_id and t['effective_from']<=(at or self.clock())]
        if not versions: raise ValueError('Для операции требуется действующий тариф')
        versions.sort(key=lambda t:(t['effective_from'],t['created_at'],t['id']))
        current=dict(versions[-1],sources={})
        for key in ('employee_rate','client_rate'):
            source=next(t for t in reversed(versions) if key in t.get('changed_fields',('employee_rate','client_rate')))
            current[key]=source[key];current['sources'][key]=source['id']
        return current

    def create_tariff(self,b):
        op=self.operation(b['client_id'],b['operation_id'])
        old=self.tariff(op['id'])
        values={k:old[k] for k in ('employee_rate','client_rate')}
        changed=False
        for key,permission in [('employee_rate','rates.employee'),('client_rate','rates.client')]:
            if key in b:
                self.need(permission);values[key]=cents(b[key]);changed=True
        if not changed: raise ValueError('Укажите новую ставку или цену')
        effective=stamp(b.get('effective_from') or self.clock())
        if effective<self.clock():
            # A small clock gap is allowed only for immediate server-generated time.
            if b.get('effective_from'): raise ValueError('Тариф нельзя вводить задним числом')
        if any(t['operation_id']==op['id'] and t['effective_from']==effective for t in self.r.list('tariffs')): raise ValueError('Тариф на эту дату уже есть')
        return self.r.insert('tariffs',dict(operation_id=op['id'],client_id=op['client_id'],effective_from=effective,changed_fields=[k for k in values if k in b],**values))

    def batch(self,b):
        self.need('batches.receive'); c=self.client(b['client_id'],True)
        identity=str(uuid.uuid4())
        # Company + UUID is globally unambiguous during file -> central DB migration.
        return self.r.insert('batches',dict(number='PRT-'+self.clock()[:4]+'-'+str(self.r.company_id)+'-'+identity.replace('-',''),
            client_id=c['id'],client_name=c['name'],product=text(b.get('product'),'Товар'),
            received_at=stamp(b.get('received_at') or self.clock()),quantity=qty(b.get('quantity')),
            article=text(b.get('article'),optional=True),gtin=text(b.get('gtin'),optional=True),
            comment=text(b.get('comment'),optional=True),external_number=text(b.get('external_number'),optional=True),
            due_at=stamp(b.get('due_at'),True),direction=b.get('direction','undecided'),status='received'),identity)

    def task(self,b):
        self.need('tasks.manage');batch=self.entity('batches',b['batch_id']);op=self.operation(batch['client_id'],b['operation_id'])
        if batch['status']=='shipped':raise ValueError('Партия уже отгружена')
        target=qty(b['quantity'])
        if target!=batch['quantity']: raise ValueError('План обязательной операции должен покрывать всю партию')
        if any(t['batch_id']==batch['id'] and t['operation_id']==op['id'] for t in self.r.list('tasks')): raise ValueError('Эта операция уже запланирована для партии')
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
        self.r.insert('plans',dict(batch_id=batch['id'],task_id=task['id'],client_id=batch['client_id'],quantity=target,tariff_id=tariff['id'],tariff_sources=tariff['sources'],salary=target*tariff['employee_rate'],revenue=target*tariff['client_rate'],materials=sum(n['cost'] for n in norms),other=cents(b.get('other_cost',0)),norms=norms))
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

    def batch_for_work(self,w):
        links=[l for l in self.r.list('links') if l['work_id']==w['id']]
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
            done=sum(w['quantity'] for w in self.r.list('works') if w.get('task_id')==task['id'])
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
            if any(t['user_id']==self.u['id'] and t['status'] in ('running','paused') for t in self.r.list('work_timers')):
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
        works=[w for w in self.r.list('works') if start<=w['completed_at'][:10]<=end]
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
        return self.r.insert('payroll_periods',dict(period_start=start,period_end=end,status='closed',
            closed_by=self.u['id'],closed_at=self.clock(),snapshot=snapshot))

    def payroll_is_closed(self,at):
        day=at[:10]
        return any(p['status']=='closed' and p['period_start']<=day<=p['period_end'] for p in self.r.list('payroll_periods'))

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
        self.need('chat.write');raw=b.get('text','');attachment=b.get('attachment')
        if not isinstance(raw,str) or len(raw.strip())>4000:raise ValueError('Сообщение: до 4000 символов')
        if not raw.strip() and not attachment:raise ValueError('Введите сообщение или добавьте файл')
        room=self.chat_room(b.get('recipient_user_id'))
        message=self.r.insert('chat_messages',dict(room=room,sender_user_id=self.u['id'],
            sender_name=self.u.get('display_name') or self.u.get('username','Сотрудник'),text=raw.strip()))
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
        cutoff=(datetime.fromisoformat(self.clock())-timedelta(days=14)).isoformat()
        removed=0
        attachments=self.r.list('chat_attachments')
        for message in list(self.r.list('chat_messages')):
            if message['created_at']>=cutoff or bool(latest.get(message['id'],{}).get('pinned')):continue
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
        return result[-200:]

    def chat_file(self,identity):
        self.need('chat.read');attachment=self.entity('chat_attachments',identity)
        if not self.chat_room_allowed(attachment['room']):raise PermissionError('Файл личного чата недоступен')
        return {k:attachment[k] for k in ('id','filename','original_name','mime_type','size_bytes','sha256','file_b64')}

    def document(self,b):
        self.need('documents.manage')
        if b.get('document_type')!='payroll':raise ValueError('Пока поддерживается расчётный документ зарплаты')
        start,end=self.payroll_bounds(b.get('period_start'),b.get('period_end'))
        period=next((p for p in self.r.list('payroll_periods') if p['period_start']==start and p['period_end']==end and p['status']=='closed'),None)
        if not period:raise ValueError('Сначала закройте расчётный период')
        snapshot=period['snapshot'];snapshot_raw=json.dumps(snapshot,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf-8')
        payload=payroll_xlsx(snapshot);title=text(b.get('title') or f'Расчётный период {start} — {end}','Название документа')
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
        self.need('invoices.create');ids=b.get('work_ids')
        if not isinstance(ids,list) or not ids or len(ids)!=len(set(ids)): raise ValueError('Выберите уникальные записи работ')
        billed={wid for i in self.r.list('invoices') for wid in i['work_ids']}
        works=[self.entity('works',wid) for wid in ids]
        if any(w['id'] in billed for w in works): raise ValueError('Работа уже выставлена клиенту')
        if len({w['client_id'] for w in works})!=1: raise ValueError('Счёт может включать работы одного клиента')
        return self.r.insert('invoices',dict(client_id=works[0]['client_id'],work_ids=ids,amount=sum(w['revenue'] for w in works),due_at=stamp(b.get('due_at'),True),lines=[dict(work_id=w['id'],quantity=w['quantity'],client_rate=w['client_rate'],amount=w['revenue'],batch_id=self.batch_for_work(w)) for w in works]))

    def payment(self,b):
        self.need('payments.record');i=self.entity('invoices',b['invoice_id']);amount=cents(b['amount'])
        paid=sum(p['amount'] for p in self.r.list('payments') if p['invoice_id']==i['id'])
        if not 0<amount<=i['amount']-paid: raise ValueError('Оплата должна быть больше нуля и не больше остатка счёта')
        return self.r.insert('payments',dict(invoice_id=i['id'],client_id=i['client_id'],amount=amount,reference=text(b.get('reference'),optional=True)))

    def set_permissions(self,b):
        self.need('users.manage');users={u['id']:u for u in self.r.catalog('users')};target=users.get(b.get('user_id'))
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
        if self.r.get('permissions',old['id'],False): return self.r.update('permissions',old)
        return self.r.insert('permissions',old,old['id'])

    def settings(self,b=None):
        current=self.r.get('settings','control',False) or dict(monday_time='10:00',wednesday_time='10:00',utc_offset_minutes=180,
                                                               presence_heartbeat_seconds=60,presence_timeout_seconds=180)
        current.setdefault('presence_heartbeat_seconds',60)
        current.setdefault('presence_timeout_seconds',180)
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
        return self.r.update('settings',current) if current.get('id') else self.r.insert('settings',current,'control')

    def scoped(self,kind): return [x for x in self.r.list(kind) if 'client_id' not in x or self.visible(x['client_id'])]

    def works(self):
        rows=self.scoped('works')
        if not ({'finance.read','work.link','analytics.read','payroll.all','invoices.create'} & self.permissions): rows=[w for w in rows if w['user_id']==self.u['id']]
        result=[]
        for w in rows:
            w=dict(w,batch_id=self.batch_for_work(w))
            if 'finance.read' not in self.permissions and 'invoices.create' not in self.permissions:
                for k in ('client_rate','revenue'): w.pop(k,None)
            if 'payroll.all' not in self.permissions and not(w['user_id']==self.u['id'] and 'payroll.own' in self.permissions):
                for k in ('salary','employee_rate'):w.pop(k,None)
            result.append(w)
        return result

    def task_rows(self):
        self.need('tasks.read');rows=self.scoped('tasks');works=self.r.list('works')
        if 'tasks.manage' not in self.permissions: rows=[t for t in rows if self.u['id'] in t['assignees']]
        for t in rows:
            t['done']=sum(w['quantity'] for w in works if w.get('task_id')==t['id']);t['remaining']=max(0,t['quantity']-t['done'])
            t['batch_number']=self.r.get('batches',t['batch_id'])['number'];t['client_name']=self.client(t['client_id'])['name']
        return rows

    def progress(self,batch):
        tasks=[t for t in self.r.list('tasks') if t['batch_id']==batch['id']]
        works=[w for w in self.r.list('works') if self.batch_for_work(w)==batch['id']]
        done_by={t['id']:sum(w['quantity'] for w in works if w.get('task_id')==t['id']) for t in tasks}
        # Different operations are NOT summed as finished physical units.
        done=min(done_by.values()) if tasks else 0
        ready=bool(tasks) and all(done_by[t['id']]>=t['quantity'] for t in tasks)
        return dict(batch,done=done,remaining=max(0,batch['quantity']-done),ready=ready,
                    stage='shipped' if batch['status']=='shipped' else 'ready' if ready else 'in_progress' if works else 'received',
                    operations=[dict(operation=t['operation_name'],done=done_by[t['id']],planned=t['quantity']) for t in tasks],
                    performers=sorted({w['user_id'] for w in works}))

    def ship(self,b):
        self.need('batches.receive');batch=self.entity('batches',b['batch_id'])
        if batch['status']=='shipped' or not self.progress(batch)['ready']: raise ValueError('Партия ещё не готова или уже отгружена')
        if b.get('direction') not in ('FBO','FBS','shipment'): raise ValueError('Выберите направление отгрузки')
        batch.update(status='shipped',direction=b['direction']);self.r.update('batches',batch)
        return self.r.insert('shipments',dict(batch_id=batch['id'],client_id=batch['client_id'],direction=b['direction'],quantity=batch['quantity']))

    def economy(self,batch_id):
        self.need('finance.read');batch=self.entity('batches',batch_id)
        works=[w for w in self.scoped('works') if self.batch_for_work(w)==batch_id];ids={w['id'] for w in works}
        plans=[p for p in self.scoped('plans') if p['batch_id']==batch_id]
        plan={k:sum(p[k] for p in plans) for k in ('salary','revenue','materials','other')}
        fact=dict(salary=sum(w['salary'] for w in works),revenue=sum(w['revenue'] for w in works),materials=sum(u['cost'] for u in self.scoped('usage') if u['work_id'] in ids),other=sum(e['amount'] for e in self.scoped('expenses') if e['batch_id']==batch_id))
        for values in (plan,fact):values['profit']=values['revenue']-values['salary']-values['materials']-values['other']
        plan['volume']=sum(p['quantity'] for p in plans);fact['volume']=sum(w['quantity'] for w in works)
        units=self.progress(batch)['done']
        return dict(batch_id=batch_id,plan=plan,fact=fact,deviation={k:fact[k]-plan[k] for k in plan},finished_units=units,
                    cost_per_unit=(fact['salary']+fact['materials']+fact['other'])/units if units else None,profit_per_unit=fact['profit']/units if units else None)

    def finance(self):
        self.need('finance.read');works=self.scoped('works');usage=self.scoped('usage');expenses=self.scoped('expenses')
        clients=[];months={}
        for c in self.r.catalog('clients'):
            if not self.visible(c['id']):continue
            rows=[w for w in works if w['client_id']==c['id']];revenue=sum(w['revenue'] for w in rows)
            salary=sum(w['salary'] for w in rows);material=sum(u['cost'] for u in usage if u['client_id']==c['id']);other=sum(e['amount'] for e in expenses if e.get('client_id')==c['id'])
            profit=revenue-salary-material-other;batches=[b for b in self.scoped('batches') if b['client_id']==c['id']]
            clients.append(dict(client_id=c['id'],client_name=c['name'],revenue=revenue,salary=salary,materials=material,other=other,profit=profit,margin=profit/revenue if revenue else None,average_batch_profit=sum(self.economy(b['id'])['fact']['profit'] for b in batches)/len(batches) if batches else None))
        for w in works:
            month=w['completed_at'][:7];m=months.setdefault(month,dict(revenue=0,salary=0,materials=0,other=0,overhead=0));m['revenue']+=w['revenue'];m['salary']+=w['salary']
        for row in usage:
            month=row['created_at'][:7];m=months.setdefault(month,dict(revenue=0,salary=0,materials=0,other=0,overhead=0));m['materials']+=row['cost']
        for row in expenses:
            month=(row.get('incurred_at') or row['created_at'])[:7];m=months.setdefault(month,dict(revenue=0,salary=0,materials=0,other=0,overhead=0))
            if row.get('client_id') is None:m['overhead']+=row['amount']
            else:m['other']+=row['amount']
        for m in months.values():
            m['profit']=m['revenue']-m['salary']-m['materials']-m['other']-m['overhead']
        overhead=sum(e['amount'] for e in expenses if e.get('client_id') is None)
        client_profit=sum(c['profit'] for c in clients)
        return dict(clients=clients,months=months,company_overhead=overhead,client_profit=client_profit,net_profit=client_profit-overhead,currency='RUB',money_unit='kopeck')

    def invoices(self):
        self.need('invoices.read');rows=self.scoped('invoices');payments=self.scoped('payments')
        for i in rows:
            i['paid']=sum(p['amount'] for p in payments if p['invoice_id']==i['id']);i['remaining']=i['amount']-i['paid']
            i['status']='paid' if not i['remaining'] else 'partial' if i['paid'] else 'unpaid'
        return rows

    def analytics(self):
        all_team='analytics.read' in self.permissions
        if not all_team:self.need('work.write')
        rows=[w for w in self.scoped('works') if all_team or w['user_id']==self.u['id']];groups={}
        for w in rows:
            key=(w['user_id'],w['client_id'],w['product'] or (self.r.get('batches',self.batch_for_work(w))['product'] if self.batch_for_work(w) else ''),w['operation_id'])
            g=groups.setdefault(key,dict(user_id=key[0],client_id=key[1],product=key[2],operation_id=key[3],quantity=0,samples=0,timed_quantity=0,seconds=0,rates=[]))
            g['quantity']+=w['quantity'];g['samples']+=1
            if w['duration_seconds'] and w['duration_seconds']>0:
                g['timed_quantity']+=w['quantity'];g['seconds']+=w['duration_seconds'];g['rates'].append(w['quantity']/w['duration_seconds']*3600)
        for g in groups.values():
            rates=g.pop('rates');g['units_per_hour']=g['timed_quantity']/g['seconds']*3600 if g['seconds'] else None
            mean=sum(rates)/len(rates) if rates else 0
            g['variability']=((sum((v-mean)**2 for v in rates)/len(rates))**.5/mean) if len(rates)>=2 and mean else None
        forecasts=[]
        for t in self.scoped('tasks'):
            if not all_team and self.u['id'] not in t['assignees']:continue
            observations=[w for w in rows if w.get('task_id')==t['id']];done=sum(w['quantity'] for w in observations)
            timed=[w for w in observations if w['started_at']];elapsed=(datetime.fromisoformat(self.clock())-min(datetime.fromisoformat(w['started_at']) for w in timed)).total_seconds() if timed else 0
            pace=done/elapsed if elapsed>0 else 0
            eta=(datetime.fromisoformat(self.clock())+timedelta(seconds=max(0,t['quantity']-done)/pace)).isoformat() if pace else None
            forecasts.append(dict(task_id=t['id'],done=done,remaining=max(0,t['quantity']-done),units_per_hour=pace*3600 if pace else None,estimated_completion=eta,due_at=t['due_at']))
        return dict(groups=list(groups.values()),forecasts=forecasts,ranking=False)

    def today(self):
        settings=self.settings();now=datetime.fromisoformat(self.clock())+timedelta(minutes=settings['utc_offset_minutes']);day=now.date().isoformat()
        works=self.scoped('works');mine=[w for w in works if w['user_id']==self.u['id'] and (datetime.fromisoformat(w['completed_at'])+timedelta(minutes=settings['utc_offset_minutes'])).date().isoformat()==day]
        batches=[self.progress(b) for b in self.scoped('batches')];attention=[]
        manager=bool({'tasks.manage','batches.receive','finance.read'} & self.permissions)
        if manager:
            for b in batches:
                if b['due_at'] and not b['ready'] and b['due_at']<self.clock():attention.append(dict(type='batch_late',label='Партия просрочена',batch_id=b['id'],number=b['number']))
        if 'materials.read' in self.permissions:
            for m in self.r.catalog('materials'):
                if m['active'] and m['stock_qty']<=m['min_stock']:attention.append(dict(type='material_low',label='Критический остаток материала',name=m['name'],quantity=m['stock_qty']))
        unbilled=[]
        if {'invoices.create','invoices.read','finance.read'} & self.permissions:
            billed={wid for i in self.scoped('invoices') for wid in i['work_ids']};unbilled=[w for w in works if w['id'] not in billed]
            if unbilled:attention.append(dict(type='not_invoiced',label='Выполненная работа не выставлена клиенту',amount=sum(w['revenue'] for w in unbilled),clients=[dict(client_id=cid,amount=sum(w['revenue'] for w in unbilled if w['client_id']==cid),work_ids=[w['id'] for w in unbilled if w['client_id']==cid]) for cid in sorted({w['client_id'] for w in unbilled})]))
        invoices=self.invoices() if 'invoices.read' in self.permissions else []
        for i in invoices:
            if i['due_at'] and i['remaining'] and i['due_at']<self.clock():attention.append(dict(type='payment_late',label='Просрочена оплата',invoice_id=i['id'],amount=i['remaining']))
        check='monday' if now.weekday()==0 and now.strftime('%H:%M')>=settings['monday_time'] else 'wednesday' if now.weekday()==2 and now.strftime('%H:%M')>=settings['wednesday_time'] else None
        if check and invoices:attention.append(dict(type='control_'+check,label='Контроль счетов и оплат',paid=sum(i['status']=='paid' for i in invoices),partial=sum(i['status']=='partial' for i in invoices),unpaid=sum(i['status']=='unpaid' for i in invoices),not_invoiced=len(unbilled)))
        result=dict(date=day,mode='management' if manager else 'worker',own_quantity=sum(w['quantity'] for w in mine),attention=attention,tasks=self.task_rows() if 'tasks.read' in self.permissions else [])
        if 'payroll.own' in self.permissions:result['own_salary']=sum(w['salary'] for w in mine)
        if manager:result.update(active_batches=sum(b['stage']!='shipped' for b in batches),in_progress=sum(b['stage']=='in_progress' for b in batches),ready=sum(b['ready'] and b['stage']!='shipped' for b in batches),today_quantity=sum(w['quantity'] for w in works if (datetime.fromisoformat(w['completed_at'])+timedelta(minutes=settings['utc_offset_minutes'])).date().isoformat()==day))
        if 'finance.read' in self.permissions:
            data=self.finance();result['finance']={key:sum(c[key] for c in data['clients']) for key in ('revenue','salary','materials','other')}
            result['finance'].update(company_overhead=data['company_overhead'],profit=data['net_profit'])
            result['expected_profit']=sum(self.economy(b['id'])['plan']['profit'] for b in batches if b['stage']!='shipped')
        if 'invoices.read' in self.permissions:result['debt']=sum(i['remaining'] for i in invoices)
        return result

    def command(self,action,body):
        if 'company_id' in body and body['company_id']!=self.r.company_id:raise PermissionError('Компания определяется сессией')
        methods={'batches':self.batch,'tasks':self.task,'work':self.work,'timers':self.timer,'links':self.link,'tariffs':self.create_tariff,'permissions':self.set_permissions,'usage':self.usage,'expenses':self.expense,'invoices':self.invoice,'payments':self.payment,'settings':self.settings,'shipments':self.ship,'payroll-periods':self.payroll_period,'chat':self.chat_command,'documents':self.document}
        if action not in methods: raise ValueError('Действие не поддерживается')
        authorization={'batches':'batches.receive','tasks':'tasks.manage','work':'work.write','timers':'work.write','links':'work.link','permissions':'users.manage','usage':'materials.use','expenses':'expenses.manage','invoices':'invoices.create','payments':'payments.record','settings':'company.settings','shipments':'batches.receive','payroll-periods':'payroll.close','chat':'chat.write','documents':'documents.manage'}
        if action in authorization:self.need(authorization[action])
        if action=='tariffs':
            for field,key in [('employee_rate','rates.employee'),('client_rate','rates.client')]:
                if field in body:self.need(key)
        key=text(body.get('request_id'),'Идентификатор запроса')
        fingerprint=hashlib.sha256(json.dumps(dict(action=action,body=body,user=self.u['id']),sort_keys=True).encode()).hexdigest()
        old=self.r.get('requests',key,False)
        if old:
            if old['fingerprint']!=fingerprint:raise ValueError('Идентификатор запроса уже использован')
            result=dict(old['result'])
            if action in ('work','tariffs'):
                if not {'finance.read','rates.client','invoices.create'} & self.permissions:
                    result.pop('client_rate',None);result.pop('revenue',None)
                if not {'payroll.own','payroll.all','rates.employee'} & self.permissions:
                    result.pop('employee_rate',None);result.pop('salary',None)
            return result
        result=methods[action](body)
        self.r.audit(self.u,action,result.get('id','control'))
        result=dict(result)
        if action in ('work','tariffs'):
            if not {'finance.read','rates.client','invoices.create'} & self.permissions:
                result.pop('client_rate',None);result.pop('revenue',None)
            if not {'payroll.own','payroll.all','rates.employee'} & self.permissions:
                result.pop('employee_rate',None);result.pop('salary',None)
        self.r.insert('requests',dict(fingerprint=fingerprint,result=result),key)
        return result

    def query(self,action,params):
        if action=='today':return self.today()
        if action=='tasks':return self.task_rows()
        if action=='timers':
            if not {'tasks.read','work.write','tasks.manage'} & self.permissions:raise PermissionError('Нет доступа к работе')
            items=self.scoped('work_timers')
            return [t for t in items if t['status'] in ('running','paused') and ('tasks.manage' in self.permissions or t['user_id']==self.u['id'])]
        if action=='batches':
            if not ({'tasks.read','batches.receive','work.write'}&self.permissions):raise PermissionError('Нет доступа к партиям')
            return [self.progress(b) for b in self.scoped('batches')]
        if action=='works':
            if not {'work.write','payroll.own','work.link','finance.read','analytics.read','payroll.all','invoices.create'} & self.permissions:raise PermissionError('Нет доступа к выработке')
            return self.works()
        if action=='invoices':return self.invoices()
        if action=='expenses':
            self.need('expenses.read');return self.scoped('expenses')
        if action=='finance':return self.finance()
        if action=='economy':return self.economy(params.get('batch_id',[''])[0])
        if action=='analytics':return self.analytics()
        if action=='payroll-periods':
            self.need('payroll.all')
            start=params.get('period_start',[None])[0];end=params.get('period_end',[None])[0]
            return self.payroll_snapshot(start,end) if start or end else self.r.list('payroll_periods')
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
        if action=='settings':self.need('company.settings');return self.settings()
        if action=='permissions':
            self.need('users.manage');return [dict(u,permissions=sorted(rights.effective(self.r,u))) for u in self.r.catalog('users')]
        if action=='catalog':
            operations=[]
            for op in self.r.catalog('operations'):
                if not op['active'] or not self.visible(op['client_id']):continue
                item={k:op[k] for k in ('id','client_id','name')}
                try:t=self.tariff(op['id'])
                except ValueError:t={}
                if {'rates.employee','payroll.own'}&self.permissions:item['employee_rate']=t.get('employee_rate')
                if {'rates.client','finance.read'}&self.permissions:item['client_rate']=t.get('client_rate')
                operations.append(item)
            return dict(clients=[c for c in self.r.catalog('clients') if c['active'] and self.visible(c['id'])],operations=operations,users=self.r.catalog('users') if 'tasks.manage' in self.permissions else [])
        raise ValueError('Раздел не найден')
