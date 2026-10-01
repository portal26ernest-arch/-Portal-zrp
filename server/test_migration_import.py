"""Offline import/preflight tests. Both source and target are temporary SQLite fixtures."""
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from migration_import import ValidationError, open_copy, prepared_source, transfer, transfer_control
from migrate_sqlite_to_pg import run
from portal_config import load_config


SOURCE = '''
CREATE TABLE employees(telegram_id INTEGER PRIMARY KEY,full_name TEXT);
CREATE TABLE portal_clients(id INTEGER PRIMARY KEY,name TEXT);
CREATE TABLE portal_client_operations(id INTEGER PRIMARY KEY,client_id INTEGER,name TEXT,employee_rate REAL,client_rate REAL);
CREATE TABLE work_log(id INTEGER PRIMARY KEY,telegram_id INTEGER,client TEXT,operation TEXT,quantity INTEGER,salary REAL,revenue REAL);
CREATE TABLE client_invoices(id INTEGER PRIMARY KEY,client TEXT,amount_due REAL);
CREATE TABLE client_payments(invoice_id INTEGER,amount REAL);
INSERT INTO employees VALUES(101,'Работник');
INSERT INTO portal_clients VALUES(1,'Старое имя клиента');
INSERT INTO portal_client_operations VALUES(1,1,'Сборка',2.0,5.0);
INSERT INTO work_log VALUES(1,101,'Историческое имя','Сборка',2,4.0,10.0);
INSERT INTO client_invoices VALUES(1,'Историческое имя',10.0);
INSERT INTO client_payments VALUES(1,3.0);
'''

TARGET = '''
CREATE TABLE companies(id INTEGER PRIMARY KEY,name TEXT,created_at TEXT,updated_at TEXT);
CREATE TABLE employees(telegram_id INTEGER PRIMARY KEY,full_name TEXT,company_id INTEGER);
CREATE TABLE portal_clients(id INTEGER PRIMARY KEY,name TEXT,company_id INTEGER);
CREATE TABLE portal_client_operations(id INTEGER PRIMARY KEY,client_id INTEGER,name TEXT,employee_rate REAL,client_rate REAL,company_id INTEGER);
CREATE TABLE work_log(id INTEGER PRIMARY KEY,telegram_id INTEGER,client TEXT,operation TEXT,quantity INTEGER,salary REAL,revenue REAL,company_id INTEGER);
CREATE TABLE client_invoices(id INTEGER PRIMARY KEY,client TEXT,amount_due REAL,company_id INTEGER);
CREATE TABLE client_payments(invoice_id INTEGER,amount REAL,company_id INTEGER);
'''


class MigrationImportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.copy = Path(self.temp.name) / 'copy.db'
        with closing(sqlite3.connect(self.copy)) as conn:
            conn.executescript(SOURCE)

    def target(self):
        conn = sqlite3.connect(':memory:')
        conn.executescript(TARGET)
        self.addCleanup(conn.close)
        return conn

    def test_legacy_company_mapping_preserves_text_money_and_read_only_source(self):
        source = open_copy(self.copy)
        self.addCleanup(source.close)
        self.assertIn('company_id', prepared_source(source, 1)['work_log'])
        target = self.target()
        transfer_control(None, target, 'sqlite')
        result = transfer(source, target, 1, 'sqlite')
        self.assertEqual(result['counts']['work_log'], 1)
        self.assertEqual(result['money']['work_log.salary'], '4')
        self.assertEqual(target.execute('SELECT company_id,client,salary,revenue FROM work_log').fetchone(),
                         (1, 'Историческое имя', 4.0, 10.0))
        self.assertEqual(target.execute('SELECT COUNT(*) FROM companies').fetchone()[0], 1)
        with self.assertRaises(sqlite3.OperationalError):
            source.execute("UPDATE work_log SET salary=0")

    def test_dry_run_and_failed_source_preflight(self):
        result = run([(1, str(self.copy))])
        self.assertEqual(result['status'], 'DRY_RUN')
        self.assertEqual(result['company_count'], 1)
        self.assertEqual(result['companies'][0]['money']['client_payments.amount'], '3')
        with closing(sqlite3.connect(self.copy)) as conn:
            conn.execute('UPDATE portal_client_operations SET client_id=999')
            conn.commit()
        with self.assertRaisesRegex(ValidationError, 'relationship'):
            run([(1, str(self.copy))])

    def test_source_tenant_mismatch_and_target_difference_fail(self):
        source = open_copy(self.copy)
        self.addCleanup(source.close)
        with self.assertRaisesRegex(ValidationError, 'primary company'):
            prepared_source(source, 2)
        target = self.target()
        target.execute('INSERT INTO work_log(id,company_id) VALUES(9,1)')
        with self.assertRaisesRegex(ValidationError, 'not empty'):
            transfer(source, target, 1, 'sqlite')

    def test_missing_required_schema_fails_before_import(self):
        with closing(sqlite3.connect(self.copy)) as conn:
            conn.execute('DROP TABLE employees')
            conn.commit()
        source = open_copy(self.copy)
        self.addCleanup(source.close)
        with self.assertRaisesRegex(ValidationError, 'employees'):
            prepared_source(source, 1)

    def test_mismatch_rolls_back_target_transaction(self):
        source = open_copy(self.copy)
        self.addCleanup(source.close)
        target = self.target()
        target.execute('CREATE TRIGGER corrupt_salary AFTER INSERT ON work_log '
                       'BEGIN UPDATE work_log SET salary=0 WHERE id=NEW.id; END')
        with self.assertRaisesRegex(ValidationError, 'row mismatch'):
            with target:
                transfer(source, target, 1, 'sqlite')
        self.assertEqual(target.execute('SELECT COUNT(*) FROM work_log').fetchone()[0], 0)
        self.assertEqual(target.execute('SELECT COUNT(*) FROM employees').fetchone()[0], 0)

    def test_stage3_ledger_tariff_versions_work_and_invoices_remain_exact(self):
        facts = (
            ('batches', 'b1', {'number': 'PRT-2026-1-b1'}),
            ('tasks', 't1', {'batch_id': 'b1'}),
            ('tariffs', 'rate-old', {'employee_rate': 200, 'client_rate': 500,
                                    'effective_from': '2026-09-01'}),
            ('tariffs', 'rate-new', {'employee_rate': 300, 'client_rate': 600,
                                    'effective_from': '2026-09-25'}),
            ('works', 'w1', {'task_id': 't1', 'batch_id': 'b1', 'salary': 400,
                             'revenue': 1000, 'tariff_id': 'rate-old'}),
            ('invoices', 'i1', {'work_ids': ['w1'], 'amount': 1000}),
            ('payments', 'p1', {'invoice_id': 'i1', 'amount': 300}),
            ('work_timers', 'timer1', {'task_id': 't1', 'batch_id': 'b1', 'net_seconds': 1800}),
            ('access_events', 'login1', {'result': 'success'}),
            ('permissions', 'user1', {'overrides': {'work.write': True}}),
        )
        with closing(sqlite3.connect(self.copy)) as conn:
            conn.execute('CREATE TABLE portal_production(company_id INTEGER,kind TEXT,id TEXT,payload TEXT,created_at TEXT)')
            for kind, identity, fields in facts:
                payload = json.dumps(dict(fields, id=identity, company_id=1))
                conn.execute('INSERT INTO portal_production VALUES(?,?,?,?,?)',
                             (1, kind, identity, payload, '2026-09-25'))
            conn.commit()
        target = self.target()
        target.execute('CREATE TABLE portal_production(company_id INTEGER,kind TEXT,id TEXT,payload TEXT,created_at TEXT)')
        source = open_copy(self.copy)
        self.addCleanup(source.close)
        report = transfer(source, target, 1, 'sqlite')
        self.assertEqual(report['counts']['portal_production/tariffs'], 2)
        self.assertEqual(report['money']['ledger/works.salary'], '400')
        self.assertEqual(report['money']['ledger/invoices.amount'], '1000')
        self.assertEqual(report['money']['ledger/payments.amount'], '300')
        self.assertEqual(target.execute("SELECT COUNT(*) FROM portal_production WHERE kind='work_timers'").fetchone()[0], 1)

    def test_core_schema_contract_covers_tenants_and_history(self):
        sql = (Path(__file__).parent / 'migrations' / 'postgresql_core_stage4b.sql').read_text(encoding='utf-8')
        for table in ('companies', 'platform_owners', 'platform_audit', 'app_users',
                      'app_sessions', 'portal_clients', 'portal_client_operations',
                      'work_log', 'payroll_payments', 'payroll_transactions',
                      'materials', 'material_movements', 'client_invoices',
                      'client_payments', 'audit_log'):
            self.assertIn('CREATE TABLE IF NOT EXISTS ' + table, sql)
        self.assertIn('FORCE ROW LEVEL SECURITY', sql)
        self.assertIn('portal_history_no_delete', sql)

    def test_server_config_and_no_silent_postgresql_cutover(self):
        config = load_config({'PORTAL_ENV': 'test', 'PORTAL_DB_BACKEND': 'postgresql',
                              'PORTAL_DATABASE_URL': 'postgresql://portal@localhost/portal',
                              'PORTAL_CONTROL_DATABASE_URL': 'postgresql://control@localhost/portal',
                              'PORTAL_PUBLIC_API_URL': 'https://portal.example.invalid'})
        self.assertEqual(config.backend, 'postgresql')
        self.assertEqual(config.host, '127.0.0.1')
        self.assertNotIn('postgresql://portal@localhost/portal', repr(config))
        with self.assertRaises(ValueError):
            load_config({'PORTAL_ENV': 'production', 'PORTAL_PUBLIC_API_URL': 'http://example.com'})
        with self.assertRaisesRegex(ValueError, 'explicit PostgreSQL backend'):
            load_config({'PORTAL_ENV': 'production',
                         'PORTAL_PUBLIC_API_URL': 'https://portal.example.invalid'})
        with self.assertRaises(ValueError):
            load_config({'PORTAL_DB_BACKEND': 'postgresql'})
        production={'PORTAL_ENV': 'production', 'PORTAL_DB_BACKEND': 'postgresql',
                    'PORTAL_DATABASE_URL': 'postgresql://tenant@localhost/portal',
                    'PORTAL_CONTROL_DATABASE_URL': 'postgresql://control@localhost/portal',
                    'PORTAL_PUBLIC_API_URL': 'https://portal.example.invalid'}
        with self.assertRaises(ValueError):
            load_config(production)
        production['PORTAL_ENABLE_POSTGRES_PRODUCTION']='true'
        prod_config=load_config(production)
        self.assertEqual(prod_config.environment,'production')
        self.assertEqual(prod_config.host,'127.0.0.1')
        for name in ('PORTAL_DATABASE_URL', 'PORTAL_CONTROL_DATABASE_URL'):
            malformed = dict(production, **{name: 'sqlite:///portal.db'})
            with self.subTest(name=name), self.assertRaises(ValueError):
                load_config(malformed)


if __name__ == '__main__': unittest.main()
