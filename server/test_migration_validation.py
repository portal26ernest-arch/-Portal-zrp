"""Stage 4B offline contract tests. No PostgreSQL or deployment database is used."""
import json
import sqlite3
import unittest
from pathlib import Path

from migration_validation import (ValidationError, compare, snapshot,
                                  validate_postgresql_schema)
from production_repository import Repository


def fixture():
    conn = sqlite3.connect(':memory:')
    conn.executescript('''
        CREATE TABLE portal_production (company_id INTEGER, kind TEXT, id TEXT,
            payload TEXT, created_at TEXT, PRIMARY KEY(company_id,kind,id));
        CREATE TABLE portal_production_migrations (company_id INTEGER, version INTEGER,
            applied_at TEXT, PRIMARY KEY(company_id,version));
        CREATE TABLE app_users (id INTEGER, company_id INTEGER, username TEXT,
            pin_hash TEXT, role TEXT);
        CREATE TABLE portal_clients (id INTEGER, company_id INTEGER, name TEXT);
        CREATE TABLE portal_client_operations (id INTEGER, company_id INTEGER,
            client_id INTEGER, employee_rate REAL, client_rate REAL);
        CREATE TABLE work_log (id INTEGER, company_id INTEGER, quantity INTEGER,
            salary REAL, revenue REAL);
        CREATE TABLE client_invoices (id INTEGER, company_id INTEGER, amount_due REAL);
        CREATE TABLE client_payments (id INTEGER, company_id INTEGER, amount REAL);
    ''')
    for company_id in (1, 2):
        conn.execute('INSERT INTO portal_production_migrations VALUES (?,?,?)',
                     (company_id, 3, '2026-09-25'))
        conn.execute('INSERT INTO app_users VALUES (?,?,?,?,?)',
                     (company_id, company_id, 'worker', 'secret-hash-canary', 'packer'))
        conn.execute('INSERT INTO portal_clients VALUES (?,?,?)',
                     (company_id, company_id, 'Client'))
        conn.execute('INSERT INTO portal_client_operations VALUES (?,?,?,?,?)',
                     (company_id, company_id, company_id, 2.0, 5.0))
        conn.execute('INSERT INTO work_log VALUES (?,?,?,?,?)',
                     (company_id, company_id, 2, 4.0, 10.0))
        conn.execute('INSERT INTO client_invoices VALUES (?,?,?)',
                     (company_id, company_id, 10.0))
        conn.execute('INSERT INTO client_payments VALUES (?,?,?)',
                     (company_id, company_id, 3.0))
        for kind, payload in (
            ('batches', {'number': 'PRT-2026-' + str(company_id)}),
            ('tasks', {'batch_id': 'batch'}),
            ('tariffs', {'employee_rate': 200, 'client_rate': 500, 'effective_from': '2026-09-25'}),
            ('works', {'salary': 400, 'revenue': 1000, 'quantity': 2}),
            ('permissions', {'overrides': {'work.write': True}}),
            ('plans', {'salary': 400, 'revenue': 1000}),
            ('invoices', {'amount': 1000}),
            ('payments', {'amount': 300}),
            ('access_events', {'result': 'success'}),
            ('work_timers', {'net_seconds': 1800}),
        ):
            identity = kind + str(company_id)
            data = dict(payload, id=identity, company_id=company_id)
            conn.execute('INSERT INTO portal_production VALUES (?,?,?,?,?)',
                         (company_id, kind, identity, json.dumps(data), '2026-09-25'))
    conn.commit()
    return conn


class MigrationValidationTest(unittest.TestCase):
    def test_postgresql_sql_adapter_contract_without_server(self):
        class Rows:
            def __init__(self, rows):
                self.rows = rows

            def fetchall(self):
                return self.rows

        class PostgreSQLShape:
            def __init__(self, sqlite_connection):
                self.sqlite_connection = sqlite_connection
                self.queries = []

            def execute(self, query, args=()):
                self.queries.append((query, args))
                if query.startswith('SELECT set_config'):
                    return Rows([])
                if 'information_schema.columns' in query:
                    table = args[0]
                    return Rows([(r[1],) for r in self.sqlite_connection.execute(
                        'PRAGMA table_info(' + table + ')')])
                return self.sqlite_connection.execute(query.replace('%s', '?'), args)

        conn = fixture()
        try:
            shaped = PostgreSQLShape(conn)
            repo = Repository(shaped, 1, 'postgresql')
            self.assertEqual(repo.get('works', 'works1')['salary'], 400)
            self.assertTrue(compare(snapshot(conn, 'sqlite', 1),
                                    snapshot(shaped, 'postgresql', 1)))
            self.assertTrue(any('company_id=%s' in query for query, _ in shaped.queries))
            self.assertEqual(shaped.queries[0][1], ('1',))
        finally:
            conn.close()

    def test_schema_contract_and_company_scoped_snapshot(self):
        sql = (Path(__file__).parent / 'migrations' / 'postgresql_stage3.sql').read_text(encoding='utf-8')
        self.assertTrue(validate_postgresql_schema(sql))
        conn = fixture()
        try:
            one, two = snapshot(conn, 'sqlite', 1), snapshot(conn, 'sqlite', 2)
            self.assertEqual(one['portal_production']['count'], 10)
            self.assertNotEqual(one['portal_production']['sha256'], two['portal_production']['sha256'])
            self.assertTrue(compare(one, snapshot(conn, 'sqlite', 1)))
            self.assertNotIn('secret-hash-canary', json.dumps(one))
        finally:
            conn.close()

    def test_historical_and_control_changes_fail_validation(self):
        changes = (
            "UPDATE portal_production SET payload=replace(payload,'400','401') WHERE kind='works' AND company_id=1",
            "UPDATE portal_production SET payload=replace(payload,'200','201') WHERE kind='tariffs' AND company_id=1",
            "UPDATE portal_production SET payload=replace(payload,'1800','1801') WHERE kind='work_timers' AND company_id=1",
            "UPDATE portal_production SET payload=replace(payload,'true','false') WHERE kind='permissions' AND company_id=1",
            "UPDATE portal_production SET payload=replace(payload,'1000','1001') WHERE kind='plans' AND company_id=1",
            "UPDATE portal_production SET payload=replace(payload,'1000','1001') WHERE kind='invoices' AND company_id=1",
            "UPDATE portal_production SET payload=replace(payload,'300','301') WHERE kind='payments' AND company_id=1",
            'UPDATE work_log SET salary=4.01 WHERE company_id=1',
            'UPDATE client_payments SET amount=3.01 WHERE company_id=1',
            'DELETE FROM portal_production WHERE kind=\'tasks\' AND company_id=1',
        )
        for change in changes:
            with self.subTest(change=change):
                conn = fixture()
                try:
                    before = snapshot(conn, 'sqlite', 1)
                    conn.execute(change)
                    with self.assertRaises(ValidationError):
                        compare(before, snapshot(conn, 'sqlite', 1))
                finally:
                    conn.close()

    def test_missing_company_id_and_ledger_identity_are_rejected(self):
        conn = fixture()
        try:
            conn.execute("UPDATE portal_production SET payload='{}' WHERE company_id=1 AND kind='batches'")
            with self.assertRaisesRegex(ValidationError, 'Ledger identity'):
                snapshot(conn, 'sqlite', 1)
        finally:
            conn.close()
        conn = fixture()
        try:
            conn.execute('ALTER TABLE work_log RENAME TO old_work_log')
            conn.execute('CREATE TABLE work_log (id INTEGER, salary REAL)')
            with self.assertRaisesRegex(ValidationError, 'company_id'):
                snapshot(conn, 'sqlite', 1)
        finally:
            conn.close()

    def test_missing_table_or_schema_difference_fails_closed(self):
        conn = fixture()
        try:
            expected = snapshot(conn, 'sqlite', 1)
            conn.execute('DROP TABLE client_payments')
            with self.assertRaises(ValidationError):
                compare(expected, snapshot(conn, 'sqlite', 1))
        finally:
            conn.close()


if __name__ == '__main__':
    unittest.main()
