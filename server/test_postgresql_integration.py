"""Opt-in tests against the isolated VPS PostgreSQL API, never production data.

Run as root on the test VPS with PORTAL_PG_INTEGRATION=1. Credentials are read
from the protected test environment file and never included in test output.
"""
import base64
import hashlib
import json
import os
import secrets
import subprocess
import time
import unittest
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from employee_identity import sync_employee_mappings


@unittest.skipUnless(os.environ.get('PORTAL_PG_INTEGRATION') == '1',
                     'requires isolated PostgreSQL test VPS')
class PostgreSQLIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        env_path = Path(os.environ.get('PORTAL_PG_TEST_ENV_FILE', '/etc/portal/pg-test.env'))
        settings = dict(line.split('=', 1) for line in env_path.read_text().splitlines()
                        if line and not line.startswith('#'))
        cls.db_name = urlsplit(settings['PORTAL_DATABASE_URL']).path.lstrip('/')
        cls.api_port = os.environ.get('PORTAL_PG_EXPECTED_APP_PORT', '8766')
        cls.service = os.environ.get('PORTAL_PG_EXPECTED_SERVICE', 'portal-pg-test.service')
        approved_target = (cls.db_name, cls.api_port, cls.service) in {
            ('portal_test_api_20260925', '8766', 'portal-pg-test.service'),
            ('portal_test_stage7_staging', '8770', 'portal-stage7.service'),
        }
        if (settings.get('PORTAL_ENV') != 'test' or
                settings.get('PORTAL_DB_BACKEND') != 'postgresql' or
                not approved_target or
                urlsplit(settings['PORTAL_CONTROL_DATABASE_URL']).path.lstrip('/') != cls.db_name or
                settings.get('PORTAL_APP_HOST') != '127.0.0.1' or
                settings.get('PORTAL_APP_PORT') != cls.api_port):
            raise RuntimeError('Integration target is not the approved isolated test API')
        cls.tenant = psycopg.connect(settings['PORTAL_DATABASE_URL'])
        cls.control = psycopg.connect(settings['PORTAL_CONTROL_DATABASE_URL'])
        cls.company_keys = {}
        cls.base = 'http://127.0.0.1:' + cls.api_port
        cls.slug = secrets.token_hex(5)
        cls.pin = secrets.token_urlsafe(20)
        cls.companies = {}
        now = datetime.now().isoformat(timespec='seconds')
        for label in ('A', 'B'):
            with cls.control.cursor() as cur:
                cur.execute('INSERT INTO companies(name,user_limit,created_at,updated_at) VALUES(%s,15,%s,%s) RETURNING id',
                            ('PORTAL synthetic ' + label + ' ' + cls.slug, now, now))
                company_id = cur.fetchone()[0]
                cur.execute('SELECT portal_provision_company(%s)', (company_id,))
                cur.execute('SELECT secret FROM portal_company_keys WHERE company_id=%s', (company_id,))
                cls.company_keys[company_id] = cur.fetchone()[0]
            cls.control.commit()
            salt = secrets.token_bytes(16)
            salt_text = base64.b64encode(salt).decode()
            digest = base64.b64encode(hashlib.pbkdf2_hmac('sha256', cls.pin.encode(), salt, 180000)).decode()
            cls.scope(company_id)
            user_ids = {}
            for role in ('admin', 'packer'):
                telegram_id = secrets.randbelow(800_000_000) + 100_000_000
                username = 'pg_' + label.lower() + '_' + role + '_' + cls.slug
                cls.tenant.execute('INSERT INTO employees(telegram_id,full_name,username) VALUES(%s,%s,%s)',
                                   (telegram_id, 'Synthetic ' + role, username))
                user_ids[role] = cls.tenant.execute('''INSERT INTO app_users
                    (username,display_name,role,telegram_id,active,pin_salt,pin_hash,created_at,updated_at)
                    VALUES(%s,%s,%s,%s,1,%s,%s,%s,%s) RETURNING id''',
                    (username, 'Synthetic ' + label + ' ' + role, role, telegram_id,
                     salt_text, digest, now, now)).fetchone()[0]
                user_ids[role + '_username'] = username
            # Raw fixture insertion is an explicit legacy-schema bridge. Runtime
            # APIs use canonical employee_id, so materialize the same mapping a
            # migrated company receives before exercising task/work flows.
            sync_employee_mappings(cls.tenant, company_id)
            cls.tenant.commit()
            cls.companies[label] = dict(id=company_id, **user_ids)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'tenant'):
            cls.tenant.close()
        if hasattr(cls, 'control'):
            cls.control.close()

    @classmethod
    def scope(cls, company_id):
        cls.tenant.execute('SELECT portal_bind_company(%s,%s)',
                           (company_id, cls.company_keys[company_id]))

    @classmethod
    def api(cls, method, path, body=None, token=None, headers=None):
        header = {'Content-Type': 'application/json'}
        if token:
            header['Authorization'] = 'Bearer ' + token
        header.update(headers or {})
        request = Request(cls.base + path,
                          data=json.dumps(body).encode() if body is not None else None,
                          headers=header, method=method)
        try:
            with urlopen(request, timeout=8) as result:
                return result.status, json.load(result)
        except HTTPError as error:
            with error:
                return error.code, json.load(error)

    def assert_api(self, method, path, body=None, token=None, status=200, headers=None):
        actual, payload = self.api(method, path, body, token, headers)
        self.assertEqual(actual, status, method + ' ' + path)
        return payload

    def test_live_api_crud_rls_and_restart(self):
        self.assertTrue(self.assert_api('GET', '/api/ping')['ok'])
        users = {}
        for label in ('A', 'B'):
            company = self.companies[label]
            users[label] = {}
            for role in ('admin', 'packer'):
                login = self.assert_api('POST', '/api/login', dict(company_id=company['id'],
                    username=company[role + '_username'], pin=self.pin))
                users[label][role] = login['token']
                self.assertEqual(login['user']['company_id'], company['id'])
                self.assertIsInstance(login['user'].get('employee_id'), int)

        same_name = 'Synthetic client ' + self.slug
        clients = {}
        operations = {}
        batches = {}
        works = {}
        for label in ('A', 'B'):
            company = self.companies[label]
            admin = users[label]['admin']
            worker = users[label]['packer']
            client_id = self.assert_api('POST', '/api/admin/clients',
                                        dict(name=same_name), admin)['id']
            clients[label] = client_id
            listed = self.assert_api('GET', '/api/clients', token=admin)['clients']
            self.assertTrue(any(row['id'] == client_id for row in listed))
            operation_id = self.assert_api('POST', '/api/admin/clients/%s/operations' % client_id,
                                           dict(name='Packing', employee_rate=2, client_rate=5), admin)['id']
            operations[label] = operation_id
            batch = self.assert_api('POST', '/api/v3/batches',
                dict(request_id=secrets.token_hex(12), client_id=client_id, product='Synthetic product', quantity=10), admin)['data']
            batches[label] = batch['id']
            task = self.assert_api('POST', '/api/v3/tasks',
                dict(request_id=secrets.token_hex(12), batch_id=batch['id'], operation_id=operation_id,
                     quantity=10, assignees=[company['packer']]), admin)['data']
            work = self.assert_api('POST', '/api/v3/work',
                dict(request_id=secrets.token_hex(12), task_id=task['id'], quantity=4), worker)['data']
            self.assertEqual(work['salary'], 800)
            full = next(row for row in self.assert_api('GET', '/api/v3/works', token=admin)['data']
                        if row['id'] == work['id'])
            works[label] = full
            self.assertEqual(full['revenue'], 2000)
            own = self.assert_api('GET', '/api/v3/works', token=worker)['data']
            self.assertTrue(any(row['id'] == work['id'] for row in own))
            self.assertTrue(self.assert_api('GET', '/api/v3/batches', token=admin)['data'])

        a, b = self.companies['A']['id'], self.companies['B']['id']
        admin_a, admin_b = users['A']['admin'], users['B']['admin']
        self.assertNotEqual(a, b)
        self.assertNotEqual(clients['A'], clients['B'])
        self.assertEqual(self.api('GET','/api/v3/economy?batch_id=' + batches['B'],token=admin_a)[0], 400)
        self.assertEqual(self.api('GET','/api/v3/economy?batch_id=' + batches['A'],token=admin_b)[0], 400)
        self.assert_api('GET','/api/v3/batches',token=admin_a,status=403,headers={'X-Portal-Company':str(b)})
        self.assert_api('GET','/api/v3/batches?company_id='+str(b),token=admin_a,status=403)
        self.assert_api('POST','/api/admin/clients',dict(company_id=b,name='Forged'),admin_a,status=403)

        # Client and operation updates are live API CRUD; these disposable rows
        # are archived by API. Physical DELETE is tested on another catalog row.
        self.assert_api('POST','/api/admin/clients/'+str(clients['A']),
                        dict(name=same_name+' revised'),admin_a)
        renamed = self.assert_api('GET','/api/admin/clients',token=admin_a)['clients']
        self.assertTrue(any(row['id']==clients['A'] and row['name']==same_name+' revised' for row in renamed))

        old_salary, old_revenue = works['A']['salary'], works['A']['revenue']
        self.assert_api('POST','/api/v3/tariffs',dict(request_id=secrets.token_hex(12),
            client_id=clients['A'],operation_id=operations['A'],employee_rate=3,client_rate=7),admin_a)
        previous = next(row for row in self.assert_api('GET','/api/v3/works',token=admin_a)['data']
                        if row['id']==works['A']['id'])
        self.assertEqual((previous['salary'],previous['revenue']), (old_salary,old_revenue))
        invoice = self.assert_api('POST','/api/v3/invoices',dict(request_id=secrets.token_hex(12),
            work_ids=[works['A']['id']]),admin_a)['data']
        self.assertEqual(invoice['amount'],old_revenue)
        payment = self.assert_api('POST','/api/v3/payments',dict(request_id=secrets.token_hex(12),
            invoice_id=invoice['id'],amount=5),admin_a)['data']
        self.assertEqual(payment['amount'],500)
        self.assert_api('POST','/api/admin/clients/'+str(clients['A']),dict(active=0),admin_a)

        # A raw tenant connection cannot read, change or remove the other
        # company's row while bound to its own transaction context.
        for own, other, other_client in ((a,b,clients['B']),(b,a,clients['A'])):
            self.tenant.commit()
            self.scope(own)
            self.assertEqual(self.tenant.execute('SELECT count(*) FROM portal_clients WHERE company_id=%s',
                                                 (other,)).fetchone()[0],0)
            changed = self.tenant.execute('UPDATE portal_clients SET name=%s WHERE company_id=%s AND id=%s',
                                          ('Forbidden',other,other_client))
            self.assertEqual(changed.rowcount,0)
            removed = self.tenant.execute('DELETE FROM portal_clients WHERE company_id=%s AND id=%s',
                                          (other,other_client))
            self.assertEqual(removed.rowcount,0)
            self.tenant.commit()
            self.scope(own)
            with self.assertRaises(self.psycopg.Error):
                self.tenant.execute('INSERT INTO portal_clients(company_id,name,created_at,updated_at) VALUES(%s,%s,%s,%s)',
                                    (other,'Forged '+self.slug,self.slug,self.slug))
            self.tenant.rollback()

        self.assertEqual(self.tenant.execute('SELECT count(*) FROM portal_clients').fetchone()[0],0)
        self.tenant.rollback()
        # A raw tenant role cannot forge another company's GUC or bind without
        # the control-plane key, even if its connection credential is known.
        self.scope(a)
        self.tenant.execute("SELECT set_config('portal.company_id',%s,true)", (str(b),))
        self.assertEqual(self.tenant.execute('SELECT count(*) FROM portal_clients').fetchone()[0],0)
        self.tenant.rollback()
        with self.assertRaises(self.psycopg.Error):
            self.tenant.execute('SELECT portal_bind_company(%s,%s)', (b, 'wrong'))
        self.tenant.rollback()
        self.scope(a)
        scratch = self.tenant.execute('INSERT INTO portal_clients(name,created_at,updated_at) VALUES(%s,%s,%s) RETURNING id',
                                      ('Disposable '+self.slug,self.slug,self.slug)).fetchone()[0]
        self.assertEqual(self.tenant.execute('SELECT name FROM portal_clients WHERE id=%s',(scratch,)).fetchone()[0],
                         'Disposable '+self.slug)
        self.tenant.execute('UPDATE portal_clients SET name=%s WHERE id=%s',('Updated disposable '+self.slug,scratch))
        self.assertEqual(self.tenant.execute('SELECT name FROM portal_clients WHERE id=%s',(scratch,)).fetchone()[0],
                         'Updated disposable '+self.slug)
        self.tenant.execute('DELETE FROM portal_clients WHERE id=%s',(scratch,))
        self.assertIsNone(self.tenant.execute('SELECT 1 FROM portal_clients WHERE id=%s',(scratch,)).fetchone())
        self.tenant.commit()

        self.scope(a)
        self.tenant.execute('INSERT INTO portal_clients(name,created_at,updated_at) VALUES(%s,%s,%s)',
                            ('Rollback '+self.slug,self.slug,self.slug))
        self.tenant.rollback()
        self.scope(a)
        self.assertEqual(self.tenant.execute('SELECT count(*) FROM portal_clients WHERE name=%s',
                                             ('Rollback '+self.slug,)).fetchone()[0],0)
        self.tenant.commit()
        self.scope(a)
        with self.assertRaises(self.psycopg.Error):
            self.tenant.execute("DELETE FROM portal_production WHERE kind='works' AND id=%s",(works['A']['id'],))
        self.tenant.rollback()

        self.assert_api('POST','/api/logout',{},users['A']['packer'])
        self.assert_api('GET','/api/v3/works',token=users['A']['packer'],status=401)

        subprocess.run(['systemctl','restart',self.service],check=True,stdout=subprocess.DEVNULL)
        for _ in range(20):
            try:
                if self.api('GET','/api/ping')[0]==200:
                    break
            except Exception:
                time.sleep(.5)
        else:
            self.fail('PostgreSQL test service did not restart')
        self.assert_api('GET','/api/ping')
        self.assertEqual(self.assert_api('GET','/api/v3/batches',token=admin_a)['data'][0]['id'],batches['A'])
        self.scope(a)
        self.assertEqual(self.tenant.execute('SELECT count(*) FROM portal_production WHERE kind=%s AND id=%s',
                                             ('works',works['A']['id'])).fetchone()[0],1)
        self.tenant.commit()
        report_path = os.environ.get('PORTAL_PG_TEST_REPORT')
        if report_path:
            Path(report_path).write_text(json.dumps(dict(database=self.db_name,companies={k:v['id'] for k,v in self.companies.items()},
                batches=batches,works={k:v['id'] for k,v in works.items()},restart=True)),encoding='utf-8')


if __name__ == '__main__':
    unittest.main()
