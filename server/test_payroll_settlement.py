"""Payroll settlement ledger tests against isolated temporary SQLite tenants."""
import copy
import hashlib
import http.client
import json
import sqlite3
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import test_portal_app_server as legacy
import test_portal_tenancy as isolation
from production_migrations import migrate
from production_repository import Repository

portal=legacy.portal


class PayrollSettlementTest(unittest.TestCase):
    request=legacy.PortalAPITest.request
    tearDown=legacy.PortalAPITest.tearDown
    role_token=isolation.CompanyIsolationTest.role_token

    def setUp(self):
        isolation.CompanyIsolationTest.setUp(self)
        for cid in (1,self.other):
            with portal.tenants.company_scope(cid),portal.db() as conn:migrate(conn,cid)
        self.legacy_employee_id=self.request('/api/me',self.worker)['user']['employee_id']
        with portal.db() as conn:
            self.employee_id=Repository(conn,1).payroll_employee(self.legacy_employee_id,legacy=True)['employee_id']

    def post(self,action,body,token=None,status=200):
        payload=dict(body)
        payload.setdefault('request_id',str(uuid.uuid4()))
        return self.request('/api/v3/'+action,token or self.admin,payload,status=status)

    def get(self,action,token=None,status=200):
        return self.request('/api/v3/'+action,token or self.admin,status=status)

    def closed_period(self):
        current=self.post('work',dict(client_id=1,operation_id=1,quantity=2),self.worker)['data']
        today=datetime.now(timezone.utc).date()
        if today.day>15:start=today.replace(day=1).isoformat();end=today.replace(day=15).isoformat()
        else:
            previous=today.replace(day=1)-timedelta(days=1);start=previous.replace(day=16).isoformat();end=previous.isoformat()
        with portal.db() as conn:
            repo=Repository(conn,1)
            old=dict(current,completed_at=end+'T12:00:00.000000',created_at=end+'T12:00:00.000000')
            for key in ('id','company_id'):old.pop(key,None)
            repo.insert('works',old);conn.commit()
        return self.post('payroll-periods',dict(period_start=start,period_end=end))['data']

    def settlement(self,period,entry_type='payout',amount=1,**extra):
        body=dict(payroll_period_id=period['id'],employee_id=self.employee_id,
                  entry_type=entry_type,reason='Проверка расчёта',amount=amount,**extra)
        return self.post('payroll-settlements',body)['data']

    def test_closed_period_payout_retry_and_multiple_partial_totals(self):
        period=self.closed_period();snapshot=copy.deepcopy(period['snapshot'])
        body=dict(payroll_period_id=period['id'],employee_id=self.employee_id,entry_type='payout',
                  amount='2.50',reason='Первая часть',reference='Ведомость 1',request_id='payroll-retry')
        first=self.post('payroll-settlements',body)['data']
        retry=self.post('payroll-settlements',body)['data']
        self.assertEqual(first['id'],retry['id'])
        self.settlement(period,amount='1.50')
        result=self.get('payroll-settlements?payroll_period_id='+period['id'])['data']
        self.assertEqual(len(result['entries']),2)
        self.assertEqual(result['totals'],{'accrued':400,'adjustment':0,'paid':400,'balance':0})
        with portal.db() as conn:
            self.assertEqual(conn.execute('SELECT COUNT(*),SUM(amount_minor),typeof(amount_minor) FROM payroll_settlement_entries').fetchone()[:],(2,400,'integer'))
            stored=Repository(conn,1).get('payroll_periods',period['id'])
        self.assertEqual(stored['snapshot'],snapshot)
        self.post('payroll-settlements',dict(payroll_period_id=period['id'],employee_id=self.employee_id,
            entry_type='payout',amount='.01',reason='Переплата'),status=400)

    def test_adjustment_and_reversal_are_append_only(self):
        period=self.closed_period()
        adjustment=self.settlement(period,'adjustment','1.25')
        after=self.get('payroll-settlements?payroll_period_id='+period['id'])['data']
        self.assertEqual(after['totals'],{'accrued':400,'adjustment':125,'paid':0,'balance':525})
        reversal=self.post('payroll-settlements',dict(entry_type='reversal',reversal_of=adjustment['id'],
            reason='Отмена ошибочной корректировки'))['data']
        self.assertEqual((reversal['amount'],reversal['effect'],reversal['employee_id']),(-125,'entitlement',self.employee_id))
        final=self.get('payroll-settlements?payroll_period_id='+period['id'])['data']
        self.assertEqual(final['totals'],{'accrued':400,'adjustment':0,'paid':0,'balance':400})
        self.post('payroll-settlements',dict(entry_type='reversal',reversal_of=adjustment['id'],reason='Ещё раз'),status=400)
        with portal.db() as conn:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE payroll_settlement_entries SET reason='Изменено'")
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute('DELETE FROM payroll_settlement_entries')

    def test_non_closed_period_and_employee_outside_snapshot_rejected(self):
        period=self.closed_period()
        with portal.db() as conn:
            repo=Repository(conn,1)
            opened=repo.insert('payroll_periods',dict(period_start='2020-01-01',period_end='2020-01-15',status='open',snapshot={'employees':[]}))
            conn.commit()
        with portal.db() as conn:
            reviewed=Repository(conn,1).insert('payroll_periods',dict(period_start='2020-02-01',period_end='2020-02-15',status='review',snapshot={'employees':[]}))
        for period_id in (opened['id'],reviewed['id'],'missing-period'):
            self.post('payroll-settlements',dict(payroll_period_id=period_id,employee_id=self.employee_id,
                entry_type='payout',amount=1,reason='Недопустимый период'),status=400)
        self.post('payroll-settlements',dict(payroll_period_id=period['id'],employee_id=999999,
            entry_type='payout',amount=1,reason='Другой сотрудник'),status=400)

    def test_employee_id_is_canonical_and_telegram_id_is_compatibility_only(self):
        period=self.closed_period()
        entry=self.post('payroll-settlements',dict(payroll_period_id=period['id'],telegram_id=self.legacy_employee_id,
            entry_type='payout',amount=1,reason='Совместимый запрос'))['data']
        self.assertEqual(entry['employee_id'],self.employee_id);self.assertNotIn('telegram_id',entry)
        self.post('payroll-settlements',dict(payroll_period_id=period['id'],employee_id=self.employee_id,
            telegram_id=202,entry_type='payout',amount=1,reason='Конфликт'),status=400)
        self.assertNotEqual(self.employee_id,self.legacy_employee_id)
        self.post('payroll-settlements',dict(payroll_period_id=period['id'],employee_id=self.legacy_employee_id,
            entry_type='payout',amount=1,reason='Старый идентификатор не канонический'),status=400)
        matching=self.post('payroll-settlements',dict(payroll_period_id=period['id'],employee_id=self.employee_id,
            telegram_id=self.legacy_employee_id,entry_type='payout',amount=1,reason='Совпадение через связь'))['data']
        self.assertEqual(matching['employee_id'],self.employee_id)
        with portal.db() as conn:
            columns={row[1] for row in conn.execute('PRAGMA table_info(payroll_settlement_entries)')}
        self.assertIn('employee_id',columns);self.assertNotIn('telegram_id',columns)

    def test_company_isolation_and_capabilities(self):
        period=self.closed_period()
        self.post('payroll-periods',dict(period_start='2019-01-01',period_end='2019-01-15'),self.worker,status=403)
        self.get('payroll-settlements?payroll_period_id='+period['id'],self.worker,status=403)
        self.post('payroll-settlements',dict(payroll_period_id=period['id'],employee_id=self.employee_id,
            entry_type='payout',amount=1,reason='Нет прав'),self.worker,status=403)
        self.post('permissions',dict(user_id=self.worker_id,permissions={
            'payroll.settlement.read':True,'payroll.settlement.payout':True}))
        self.get('payroll-settlements?payroll_period_id='+period['id'],self.worker)
        retry_body=dict(payroll_period_id=period['id'],employee_id=self.employee_id,
            entry_type='payout',amount=1,reason='Повтор с проверкой права',request_id='permission-retry')
        self.post('payroll-settlements',retry_body,self.worker)
        self.post('permissions',dict(user_id=self.worker_id,permissions={'payroll.settlement.payout':False}))
        self.post('payroll-settlements',retry_body,self.worker,status=403)
        self.post('payroll-settlements',dict(payroll_period_id=period['id'],employee_id=self.employee_id,
            entry_type='adjustment',amount=1,reason='Нет права корректировки'),self.worker,status=403)
        foreign=self.post('work',dict(client_id=1,operation_id=1,quantity=2),self.other_worker)['data']
        self.assertIsNotNone(foreign)
        self.request('/api/v3/payroll-settlements?payroll_period_id='+period['id'],self.other_admin,status=400)
        self.post('payroll-settlements',dict(payroll_period_id=period['id'],employee_id=self.employee_id,
            entry_type='payout',amount=1,reason='Чужой период'),self.other_admin,status=400)
        self.request('/api/v3/payroll-settlements',self.admin,dict(payroll_period_id=period['id'],
            employee_id=self.employee_id,entry_type='payout',amount=1,reason='Чужая компания',request_id='foreign-company',company_id=self.other),status=403)

    def test_audit_is_complete_and_migration_is_repeatable(self):
        period=self.closed_period();entry=self.settlement(period,amount='1.00',reference='Платёж 7')
        self.assertEqual((entry['actor_id'],entry['reason'],entry['reference']),
                         (self.admin_id,'Проверка расчёта','Платёж 7'))
        self.assertTrue(entry['occurred_at'])
        with portal.db() as conn:
            repo=Repository(conn,1)
            audit=next(row for row in repo.list('audit') if row['entity_id']==entry['id'])
            self.assertEqual({key:audit[key] for key in ('actor_id','entry_type','employee_id','payroll_period_id','amount','request_id')},
                {'actor_id':self.admin_id,'entry_type':'payout','employee_id':self.employee_id,
                 'payroll_period_id':period['id'],'amount':100,'request_id':entry['request_id']})
            self.assertTrue(audit['created_at'])
            self.assertEqual(audit['reason'],'Выплата зарплаты')
            self.assertEqual(audit['reason_sha256'],hashlib.sha256(entry['reason'].encode()).hexdigest())
            self.assertNotIn('reference',audit)
            migrate(conn,1);conn.commit();migrate(conn,1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM portal_production_migrations WHERE company_id=1 AND version=6').fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM payroll_settlement_entries').fetchone()[0],1)

    def raw_post(self,body):
        payload=body if isinstance(body,bytes) else json.dumps(body).encode()
        path='/api/v3/payroll-settlements'
        headers={'Authorization':'Bearer '+self.admin,'Content-Type':'application/json'}
        if self.http:
            conn=http.client.HTTPConnection('127.0.0.1',self.http.server_port,timeout=15)
            try:
                conn.request('POST',path,payload,headers)
                response=conn.getresponse()
                return response.status,json.loads(response.read())
            finally:conn.close()
        raw=f'POST {path} HTTP/1.0\r\nHost: localhost\r\nContent-Length: {len(payload)}\r\n'
        raw+=''.join(f'{key}: {value}\r\n' for key,value in headers.items())+'\r\n'
        sock=legacy.MemorySocket(raw.encode()+payload)
        legacy.QuietHandler(sock,('127.0.0.1',12345),None)
        head,content=bytes(sock.output).split(b'\r\n\r\n',1)
        return int(head.split()[1]),json.loads(content)

    def payout_body(self,period,**extra):
        return dict(payroll_period_id=period['id'],employee_id=self.employee_id,entry_type='payout',
                    amount='1.00',reason='Часть выплаты',request_id=str(uuid.uuid4()),**extra)

    def test_duplicate_payload_actor_and_action_mismatch_does_not_write(self):
        period=self.closed_period();body=self.payout_body(period)
        original=self.post('payroll-settlements',body)['data']
        for key,value in [('amount','2.00'),('reason','Другая причина'),('reference','Другое основание'),('entry_type','adjustment')]:
            self.post('payroll-settlements',dict(body,**{key:value}),status=400)
        accountant=self.role_token('accountant')
        self.post('payroll-settlements',body,accountant,status=400)
        self.post('payroll-periods',dict(period_start='2018-01-01',period_end='2018-01-15',request_id=body['request_id']),status=400)
        with portal.db() as conn:
            repo=Repository(conn,1)
            self.assertEqual(len(repo.payroll_settlements()),1)
            self.assertEqual(sum(row['entity_id']==original['id'] for row in repo.list('audit')),1)

    def test_reversal_retry_exact_payout_compensation_and_snapshot_bytes(self):
        period=self.closed_period()
        with portal.db() as conn:
            before=conn.execute("SELECT payload FROM portal_production WHERE kind='payroll_periods' AND id=?",(period['id'],)).fetchone()[0]
        payout=self.settlement(period,amount='2.00')
        body=dict(entry_type='reversal',reversal_of=payout['id'],reason='Исправление ошибочной выплаты',request_id='reversal-retry')
        reversal=self.post('payroll-settlements',body)['data']
        self.assertEqual(self.post('payroll-settlements',body)['data'],reversal)
        self.assertEqual((reversal['amount'],reversal['effect']),(-200,'payment'))
        self.assertEqual(self.get('payroll-settlements?payroll_period_id='+period['id'])['data']['totals']['paid'],0)
        self.post('payroll-settlements',dict(entry_type='reversal',reversal_of=reversal['id'],reason='Сторно сторно'),status=400)
        with portal.db() as conn:
            after=conn.execute("SELECT payload FROM portal_production WHERE kind='payroll_periods' AND id=?",(period['id'],)).fetchone()[0]
            self.assertEqual(before,after)
            self.assertEqual(Repository(conn,1).payroll_settlement(payout['id'])['amount_minor'],200)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM payroll_settlement_entries').fetchone()[0],2)

    def test_negative_correction_is_separate_from_paid(self):
        period=self.closed_period();entry=self.settlement(period,'adjustment','-1.25')
        totals=self.get('payroll-settlements?payroll_period_id='+period['id'])['data']['totals']
        self.assertEqual(totals,{'accrued':400,'adjustment':-125,'paid':0,'balance':275})
        self.post('payroll-settlements',dict(entry_type='reversal',reversal_of=entry['id'],reason='Отмена корректировки'))
        self.assertEqual(self.get('payroll-settlements?payroll_period_id='+period['id'])['data']['totals']['adjustment'],0)

    def test_invalid_amount_type_reference_and_identity_fail_without_writes(self):
        period=self.closed_period();body=self.payout_body(period)
        for amount in (None,True,False,[],{},0,-1,'NaN','Infinity','1e2','0.001','0.00',' 1.00','1.000','1000000000.01'):
            self.post('payroll-settlements',dict(body,amount=amount),status=400)
        for identity in (True,False,1.5,{},[],str(self.employee_id)+'.0'):
            self.post('payroll-settlements',dict(body,employee_id=identity),status=400)
        for key,value in [('entry_type','bad'),('entry_type',[]),('reason',''),('reference',{}),('reference','a'*1001),
                          ('reversal_of','anything'),('request_id',''),('request_id','a'*129),('request_id','bad\nkey')]:
            self.post('payroll-settlements',dict(body,**{key:value}),status=400)
        with portal.db() as conn:self.assertEqual(conn.execute('SELECT COUNT(*) FROM payroll_settlement_entries').fetchone()[0],0)

    def test_json_decimal_and_storage_are_exact_and_direct_float_is_rejected(self):
        period=self.closed_period();body=self.payout_body(period)
        payload=json.dumps(dict(body,amount=0.29)).encode()
        status,data=self.raw_post(payload)
        self.assertEqual(status,200);self.assertEqual(data['data']['amount'],29)
        with portal.db() as conn:
            amount,kind=conn.execute('SELECT amount_minor,typeof(amount_minor) FROM payroll_settlement_entries').fetchone()
            self.assertEqual((amount,kind),(29,'integer'))
        from production_service import settlement_cents
        with self.assertRaises(ValueError):settlement_cents(0.29)
        for payload in (b'{',b'{"amount":NaN}',b'[]'):
            status,data=self.raw_post(payload);self.assertEqual(status,400)
            self.assertRegex(data['error'],r'[А-Яа-я]')

    def test_actor_time_and_auth_field_spoofing_are_rejected(self):
        period=self.closed_period();body=self.payout_body(period)
        for key,value in [('actor_id',999),('actor_kind','platform_owner'),('occurred_at','2000-01-01'),
                          ('token','synthetic-token'),('pin','synthetic-pin'),('amount_minor',1),('effect','entitlement')]:
            self.post('payroll-settlements',dict(body,**{key:value}),status=400)
        entry=self.post('payroll-settlements',body)['data']
        self.assertEqual((entry['actor_id'],entry['actor_kind']),(self.admin_id,'user'))
        with portal.db() as conn:
            audit=next(r for r in Repository(conn,1).list('audit') if r['entity_id']==entry['id'])
        encoded=json.dumps(audit)
        self.assertTrue(self.admin not in encoded and 'synthetic-token' not in encoded and 'synthetic-pin' not in encoded)
        self.assertEqual(audit['company_id'],1)
        self.assertNotIn('pin',entry);self.assertNotIn('token',entry)

    def test_audit_failure_rolls_back_entry_and_request_then_retry_succeeds(self):
        period=self.closed_period();body=self.payout_body(period)
        with patch.object(Repository,'audit',side_effect=RuntimeError('Ошибка синтетического аудита')):
            self.post('payroll-settlements',body,status=500)
        with portal.db() as conn:
            repo=Repository(conn,1)
            self.assertEqual(len(repo.payroll_settlements()),0)
            self.assertIsNone(repo.get('requests',body['request_id'],False))
        self.post('payroll-settlements',body)

    def race(self,bodies):
        barrier=threading.Barrier(len(bodies))
        def send(body):
            barrier.wait(timeout=10)
            return self.raw_post(body)
        with ThreadPoolExecutor(max_workers=len(bodies)) as pool:return list(pool.map(send,bodies))

    def test_concurrent_duplicate_is_one_payout_and_one_audit(self):
        period=self.closed_period();body=self.payout_body(period)
        results=self.race([body,body])
        self.assertEqual([status for status,data in results],[200,200])
        self.assertEqual(results[0][1]['data']['id'],results[1][1]['data']['id'])
        with portal.db() as conn:
            repo=Repository(conn,1)
            self.assertEqual(len(repo.payroll_settlements()),1)
            self.assertEqual(sum(a['entity_id']==results[0][1]['data']['id'] for a in repo.list('audit')),1)

    def test_concurrent_distinct_requests_cannot_overpay(self):
        period=self.closed_period()
        bodies=[dict(self.payout_body(period),amount='3.00') for _ in range(2)]
        results=self.race(bodies)
        self.assertEqual(sorted(status for status,data in results),[200,400])
        totals=self.get('payroll-settlements?payroll_period_id='+period['id'])['data']['totals']
        self.assertEqual((totals['paid'],totals['balance']),(300,100))

    def test_concurrent_reversals_compensate_once(self):
        period=self.closed_period();entry=self.settlement(period,amount='1.00')
        bodies=[dict(entry_type='reversal',reversal_of=entry['id'],reason='Отмена',request_id=str(uuid.uuid4())) for _ in range(2)]
        self.assertEqual(sorted(status for status,data in self.race(bodies)),[200,400])
        with portal.db() as conn:self.assertEqual(conn.execute('SELECT COUNT(*),SUM(amount_minor) FROM payroll_settlement_entries').fetchone()[:],(2,0))

    def test_database_constraints_block_invalid_period_employee_and_reversal(self):
        period=self.closed_period();entry=self.settlement(period,amount='1.00')
        with portal.db() as conn:
            repo=Repository(conn,1);source=repo.payroll_settlement(entry['id'])
            for changes in ({'company_id':self.other},{'employee_id':999},{'payroll_period_id':'missing'},
                            {'effect':'entitlement'},{'amount_minor':1000},{'amount_minor':1.5},
                            {'entry_type':'reversal','reversal_of':entry['id'],'amount_minor':-99}):
                data=dict(source,**changes,id=str(uuid.uuid4()),request_id=str(uuid.uuid4()))
                cols=tuple(data)
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute('INSERT INTO payroll_settlement_entries('+','.join(cols)+') VALUES('+','.join('?' for _ in cols)+')',tuple(data.values()))
            for sql in ('UPDATE payroll_employee_identities SET legacy_employee_id=999','DELETE FROM payroll_employee_identities'):
                with self.assertRaises(sqlite3.IntegrityError):conn.execute(sql)
        reversal=self.post('payroll-settlements',dict(entry_type='reversal',reversal_of=entry['id'],reason='Отмена'))['data']
        with portal.db() as conn:
            data=Repository(conn,1).payroll_settlement(reversal['id']);data.update(id=str(uuid.uuid4()),request_id=str(uuid.uuid4()))
            with self.assertRaises(sqlite3.IntegrityError):Repository(conn,1).insert_payroll_settlement(data)

    def test_historical_payments_block_until_reconciled_without_rewriting_history(self):
        period=self.closed_period()
        with portal.db() as conn:
            conn.execute('INSERT INTO payroll_transactions(telegram_id,period_start,period_end,amount) VALUES(?,?,?,?)',
                         (self.legacy_employee_id,period['period_start'],period['period_end'],2))
        self.post('payroll-settlements',self.payout_body(period),status=400)
        self.get('payroll-settlements?payroll_period_id='+period['id'],status=400)
        with portal.db() as conn:
            self.assertEqual(conn.execute('SELECT amount FROM payroll_transactions').fetchone()[0],2)
            self.assertEqual(len(Repository(conn,1).payroll_settlements()),0)

    def test_same_period_employee_request_ids_are_scoped_and_foreign_reversal_is_denied(self):
        period=self.closed_period();body=self.payout_body(period);entry=self.post('payroll-settlements',body)['data']
        with portal.tenants.company_scope(self.other),portal.db() as conn:
            repo=Repository(conn,self.other)
            other_employee=repo.payroll_employee(self.legacy_employee_id,legacy=True)['employee_id']
            self.assertEqual(other_employee,self.employee_id)
            data=dict(period)
            for key in ('id','company_id'):data.pop(key,None)
            repo.insert('payroll_periods',data,period['id'])
        second=self.post('payroll-settlements',body,self.other_admin)['data']
        self.assertEqual(second['company_id'],self.other);self.assertNotEqual(entry['id'],second['id'])
        a=self.get('payroll-settlements?payroll_period_id='+period['id'])['data']['entries']
        b=self.get('payroll-settlements?payroll_period_id='+period['id'],self.other_admin)['data']['entries']
        self.assertEqual([x['id'] for x in a],[entry['id']]);self.assertEqual([x['id'] for x in b],[second['id']])
        self.post('payroll-settlements',dict(entry_type='reversal',reversal_of=entry['id'],reason='Чужая запись'),self.other_admin,status=400)

    def test_default_roles_granted_capability_and_owner_scope(self):
        period=self.closed_period()
        for role in ('manager','packer','shift'):
            token=self.role_token(role)
            self.post('payroll-settlements',self.payout_body(period),token,status=403)
        for role in ('director','accountant'):
            self.post('payroll-settlements',self.payout_body(period),self.role_token(role))
        self.request('/api/v3/payroll-settlements',self.owner,self.payout_body(period),status=403)
        owner_entry=self.request('/api/v3/payroll-settlements',self.owner,self.payout_body(period),
            extra_headers={'X-Portal-Company':'1'})['data']
        self.assertEqual(owner_entry['actor_kind'],'platform_owner')
        self.assertEqual(owner_entry['actor_id'],self.owner_id)

    def test_new_employee_gets_mapping_without_deriving_id_and_clone_is_scoped(self):
        # Provision after Stage 6 is installed: schema-only clone must not copy A's guard.
        third=self.request('/api/platform/companies',self.owner,{'name':'Третья компания'})['id']
        with portal.tenants.company_scope(third):
            uid=portal.save_user(dict(username='new-worker',display_name='Новый сотрудник',role='packer',pin='4321',create_employee=True))
            with portal.db() as conn:
                migrate(conn,third)
                legacy_id=conn.execute('SELECT telegram_id FROM app_users WHERE id=?',(uid,)).fetchone()[0]
                canonical=Repository(conn,third).payroll_employee(legacy_id,legacy=True)['employee_id']
                self.assertLess(legacy_id,0);self.assertGreater(canonical,0)
                with self.assertRaises(sqlite3.IntegrityError):
                    conn.execute('INSERT INTO payroll_employee_identities(company_id,legacy_employee_id) VALUES(1,202)')

    def test_two_accounts_for_one_employee_aggregate_without_changing_snapshot(self):
        period=self.closed_period()
        with portal.db() as conn:
            repo=Repository(conn,1);data=copy.deepcopy(period)
            data['snapshot']['employees'].append(dict(data['snapshot']['employees'][0],user_id=999))
            for key in ('id','company_id'):data.pop(key,None)
            combined=repo.insert('payroll_periods',data)
        summary=self.get('payroll-settlements?payroll_period_id='+combined['id'])['data']
        self.assertEqual(len(summary['employees']),1);self.assertEqual(summary['totals']['accrued'],800)

    def test_synthetic_import_preserves_identity_settlement_and_snapshot(self):
        from migration_import import transfer
        period=self.closed_period();payout=self.settlement(period,amount='1.00')
        adjustment=self.settlement(period,'adjustment','.25')
        self.post('payroll-settlements',dict(entry_type='reversal',reversal_of=adjustment['id'],reason='Отмена'))
        with portal.db() as source,sqlite3.connect(':memory:') as target:
            target.execute('PRAGMA foreign_keys=ON')
            schema=source.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY CASE type WHEN 'table' THEN 0 WHEN 'index' THEN 1 ELSE 2 END").fetchall()
            for row in schema:target.execute(row[0])
            target.execute('INSERT INTO portal_tenant_identity VALUES(1,1)')
            report=transfer(source,target,1,dialect='sqlite')
            self.assertEqual(report['money']['payroll_settlement_entries.amount_minor'],'100')
            self.assertEqual(Repository(source,1).payroll_settlements(),Repository(target,1).payroll_settlements())
            self.assertEqual(Repository(source,1).get('payroll_periods',period['id']),Repository(target,1).get('payroll_periods',period['id']))
            self.assertEqual(Repository(target,1).payroll_settlement(payout['id'])['employee_id'],self.employee_id)

    def test_imported_surrogate_sequence_is_advanced_on_employee_id_column(self):
        from migration_import import identity_maxima,sync_identity_sequences
        with portal.db() as source:
            maxima=identity_maxima([(1,source)])
            expected_max=source.execute('SELECT MAX(employee_id) FROM payroll_employee_identities').fetchone()[0]
            self.assertEqual(maxima['payroll_employee_identities'],expected_max)
        class Target:
            def __init__(self):self.calls=[]
            def execute(self,query,args):
                self.calls.append((query,args))
                return self
            def fetchone(self):return ('synthetic_employee_sequence',)
        target=Target()
        self.assertEqual(sync_identity_sequences(target,{'payroll_employee_identities':2}),1)
        self.assertIn("'employee_id'",target.calls[0][0])
        self.assertEqual(target.calls[1][1],('synthetic_employee_sequence',2,'synthetic_employee_sequence'))


if __name__=='__main__':unittest.main()
