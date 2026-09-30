"""Company-scoped document ledger with portable SQL storage.

Domain code uses get/list/insert/update and catalog ports, never sqlite APIs.
JSON is canonical TEXT (portable to PostgreSQL, optionally JSONB after migration).
All writes require one company transaction. Immutable facts have no update API.
"""
import json
import uuid
from datetime import datetime, timezone

KINDS = {'batches','tasks','works','tariffs','permissions','plans','usage','expenses',
         'invoices','payments','settings','audit','links','requests','shipments',
         'access_events','access_sessions','work_timers','timer_events',
         'payroll_periods','invoice_revisions','documents','products','chat_messages','chat_pins','chat_attachments'}
MUTABLE = {'batches','tasks','permissions','settings','access_sessions','work_timers','products'}
DELETABLE = {'chat_messages','chat_pins','chat_attachments'}

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec='microseconds')

class Repository:
    def __init__(self, connection, company_id, dialect=None):
        self.conn, self.company_id = connection, company_id
        self.dialect = dialect or getattr(connection, 'dialect', 'sqlite')
        if type(company_id) is not int or company_id < 1: raise PermissionError('Некорректная компания')
        if self.dialect=='postgresql' and getattr(connection,'dialect',None)!='postgresql':
            # Offline DB-API fakes predate the verified connection adapter.
            self.sql("SELECT set_config('portal.company_id',?,true)",(str(company_id),))

    def sql(self, query, args=()):
        if self.dialect == 'postgresql' and getattr(self.conn, 'dialect', None) != 'postgresql':
            # Legacy schema tests supply a lightweight DB-API fake.
            return self.conn.execute(query.replace('?', '%s'), args)
        return self.conn.execute(query, args)

    def lock(self):
        if self.dialect=='postgresql':
            self.sql('SELECT pg_advisory_xact_lock(?)', (self.company_id,))
        else:
            self.sql('BEGIN IMMEDIATE')

    def get(self, kind, identity, required=True):
        if kind not in KINDS: raise ValueError('Неизвестная сущность')
        row = self.sql('SELECT payload FROM portal_production WHERE company_id=? AND kind=? AND id=?',
                       (self.company_id, kind, str(identity))).fetchone()
        if row: return json.loads(row[0])
        if required: raise ValueError('Запись не найдена в этой компании')

    def list(self, kind):
        if kind not in KINDS: raise ValueError('Неизвестная сущность')
        return [json.loads(r[0]) for r in self.sql('SELECT payload FROM portal_production WHERE company_id=? AND kind=? ORDER BY created_at,id', (self.company_id,kind)).fetchall()]

    def insert(self, kind, data, identity=None):
        if kind not in KINDS: raise ValueError('Неизвестная сущность')
        value = dict(data, id=str(identity or uuid.uuid4()), company_id=self.company_id)
        value.setdefault('created_at',utcnow())
        self.sql('INSERT INTO portal_production(company_id,kind,id,payload,created_at) VALUES(?,?,?,?,?)',
                 (self.company_id,kind,value['id'],json.dumps(value,ensure_ascii=False,sort_keys=True),value['created_at']))
        return value

    def update(self, kind, value):
        if kind not in MUTABLE: raise ValueError('История неизменяема')
        self.get(kind,value['id'])
        value = dict(value,company_id=self.company_id)
        self.sql('UPDATE portal_production SET payload=? WHERE company_id=? AND kind=? AND id=?',
                 (json.dumps(value,ensure_ascii=False,sort_keys=True),self.company_id,kind,value['id']))
        return value

    def delete(self, kind, identity):
        if kind not in DELETABLE: raise ValueError('Эту историю удалять нельзя')
        self.sql('DELETE FROM portal_production WHERE company_id=? AND kind=? AND id=?',
                 (self.company_id,kind,str(identity)))

    def audit(self, user, event, entity_id, **details):
        # Deliberately no request body, credentials, exception text or names.
        allowed = {key: details[key] for key in (
            'entry_type','employee_id','payroll_period_id','amount','request_id',
            'actor_kind','reason','reason_sha256'
        ) if key in details}
        self.insert('audit',dict(actor_id=(user or {}).get('id'),event=event,entity_id=str(entity_id),**allowed))

    def sync_payroll_employees(self):
        """Assign surrogate payroll IDs; never derive a financial key from Telegram."""
        self.sql('''INSERT INTO payroll_employee_identities(company_id,legacy_employee_id)
                    SELECT e.company_id,e.telegram_id FROM employees e
                    WHERE e.company_id=? AND NOT EXISTS (
                        SELECT 1 FROM payroll_employee_identities i
                        WHERE i.company_id=e.company_id AND i.legacy_employee_id=e.telegram_id)
                    ORDER BY e.telegram_id''', (self.company_id,))

    def payroll_employee(self, identity, legacy=False):
        # Column names are constants, and both lookup paths verify an existing card.
        column='legacy_employee_id' if legacy else 'employee_id'
        row=self.sql('''SELECT i.employee_id,i.legacy_employee_id
                        FROM payroll_employee_identities i JOIN employees e
                          ON e.company_id=i.company_id AND e.telegram_id=i.legacy_employee_id
                        WHERE i.company_id=? AND i.'''+column+'=?',
                     (self.company_id,identity)).fetchone()
        if row is None:raise ValueError('Сотрудник не найден в этой компании')
        return dict(employee_id=row[0],legacy_employee_id=row[1])

    def has_legacy_payroll(self, period, legacy_employee):
        # Historical payout semantics have not been reconciled into this ledger.
        # Presence alone blocks a second payout; no old amount is reinterpreted.
        for table in ('payroll_transactions','payroll_payments'):
            if self.has_table(table) and self.sql(
                'SELECT 1 FROM '+table+' WHERE company_id=? AND telegram_id=? '
                'AND substr(period_start,1,10)<=? AND substr(period_end,1,10)>=? LIMIT 1',
                (self.company_id,legacy_employee,period['period_end'],period['period_start'])).fetchone():
                return True
        return False

    def payroll_settlement(self, identity, required=True):
        row=self.sql('''SELECT id,company_id,employee_id,payroll_period_id,amount_minor,
                               entry_type,effect,actor_id,occurred_at,reason,reference,
                               request_id,reversal_of,actor_kind
                        FROM payroll_settlement_entries
                        WHERE company_id=? AND id=?''',(self.company_id,str(identity))).fetchone()
        if row:
            keys=('id','company_id','employee_id','payroll_period_id','amount_minor','entry_type',
                  'effect','actor_id','occurred_at','reason','reference','request_id','reversal_of','actor_kind')
            return dict(zip(keys,row))
        if required:raise ValueError('Запись расчёта зарплаты не найдена в этой компании')

    def payroll_settlements(self, period_id=None, employee=None):
        conditions=['company_id=?'];args=[self.company_id]
        if period_id is not None:conditions.append('payroll_period_id=?');args.append(str(period_id))
        if employee is not None:conditions.append('employee_id=?');args.append(employee)
        cursor=self.sql('''SELECT id,company_id,employee_id,payroll_period_id,amount_minor,
                                  entry_type,effect,actor_id,occurred_at,reason,reference,
                                  request_id,reversal_of,actor_kind
                           FROM payroll_settlement_entries WHERE '''+' AND '.join(conditions)+
                        ' ORDER BY occurred_at,id',tuple(args))
        keys=('id','company_id','employee_id','payroll_period_id','amount_minor','entry_type',
              'effect','actor_id','occurred_at','reason','reference','request_id','reversal_of','actor_kind')
        return [dict(zip(keys,row)) for row in cursor.fetchall()]

    def insert_payroll_settlement(self, data):
        value=dict(data,id=str(data.get('id') or uuid.uuid4()),company_id=self.company_id)
        columns=('id','company_id','employee_id','payroll_period_id','amount_minor','entry_type',
                 'effect','actor_id','occurred_at','reason','reference','request_id','reversal_of','actor_kind')
        self.sql('INSERT INTO payroll_settlement_entries('+','.join(columns)+') VALUES('+
                 ','.join('?' for _ in columns)+')',tuple(value.get(key) for key in columns))
        return value

    def catalog(self, name):
        tables={'clients':'portal_clients','operations':'portal_client_operations','users':'app_users',
                'assignments':'manager_client_assignments','materials':'materials','norms':'operation_material_norms'}
        table=tables[name]
        if not self.has_table(table): return []
        fields={'users':'id,display_name,role,telegram_id,active,company_id'}.get(name,'*')
        cursor=self.sql(f'SELECT {fields} FROM {table} WHERE company_id=?',(self.company_id,))
        names=[c[0] for c in cursor.description]
        rows=[dict(zip(names,r)) for r in cursor.fetchall()]
        if name=='users':
            for row in rows:row['employee_id']=row.get('telegram_id')
        return rows

    def has_table(self, table):
        if self.dialect=='postgresql':
            return bool(self.sql('SELECT 1 FROM information_schema.tables WHERE table_schema=current_schema() AND table_name=?',(table,)).fetchone())
        return bool(self.sql("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone())

    def ready(self):
        return self.has_table('portal_production_migrations') and bool(self.sql('SELECT 1 FROM portal_production_migrations WHERE company_id=? AND version=3',(self.company_id,)).fetchone())

    def columns(self, table):
        if self.dialect=='postgresql':
            return [r[0] for r in self.sql('SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=?',(table,)).fetchall()]
        return [r[1] for r in self.sql('PRAGMA table_info('+table+')').fetchall()]

    def legacy_work(self, user, client, operation, quantity, employee_rate, client_rate, created):
        """Compatibility projection, in the SAME transaction as the new ledger."""
        employee=user.get('employee_id',user.get('telegram_id'))
        if employee is None: raise ValueError('Доступ не связан с сотрудником')
        if self.has_table('payroll_payments'):
            paid=self.sql("SELECT 1 FROM payroll_payments WHERE company_id=? AND telegram_id=? AND period_start<=? AND period_end>=? AND status='paid'",(self.company_id,employee,created.replace('T',' ')[:19],created.replace('T',' ')[:19])).fetchone()
            if paid: raise ValueError('Расчётный период уже закрыт')
        values=dict(company_id=self.company_id,telegram_id=employee,username=user.get('username',''),first_name=user.get('display_name',''),client=client['name'],operation=operation['name'],quantity=quantity,rate=employee_rate/100,salary=quantity*employee_rate/100,client_rate=client_rate/100,revenue=quantity*client_rate/100,direct_cost=0,created_at=created.replace('T',' ')[:19])
        values={k:v for k,v in values.items() if k in self.columns('work_log')}
        cur=self.sql('INSERT INTO work_log('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')'+(' RETURNING id' if self.dialect=='postgresql' else ''),tuple(values.values()))
        return cur.fetchone()[0] if self.dialect=='postgresql' else cur.lastrowid

    def consume(self, material_id, quantity, unit_cost, legacy_id, actor):
        self.sql('UPDATE materials SET stock_qty=stock_qty-? WHERE company_id=? AND id=?',(quantity,self.company_id,material_id))
        if self.has_table('material_movements'):
            values=dict(company_id=self.company_id,material_id=material_id,qty_change=-quantity,unit_cost=unit_cost/100,movement_type='work',reference_type='work_log',reference_id=str(legacy_id),note='PORTAL: расход по выработке',created_at=utcnow(),created_by=actor)
            values={k:v for k,v in values.items() if k in self.columns('material_movements')}
            self.sql('INSERT INTO material_movements('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',tuple(values.values()))

    def project_cost(self, legacy_id, cost):
        self.sql('UPDATE work_log SET direct_cost=? WHERE company_id=? AND id=?',(cost/100,self.company_id,legacy_id))
