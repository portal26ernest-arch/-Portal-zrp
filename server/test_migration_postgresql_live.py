"""Opt-in synthetic import check on a dedicated empty PostgreSQL test DB.

Run only as the postgres OS user on the isolated VPS. The test switches to a
non-superuser, non-BYPASSRLS role before importing. It never opens phone data.
"""
import json
import os
import sqlite3
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from migration_context import bind_company
from migration_import import (identity_maxima, open_copy, prepared_source, summary,
                              sync_identity_sequences, transfer, transfer_control)
from migration_validation import TABLES, ValidationError, compare, snapshot
from test_migration_import import SOURCE


DB_NAME = 'portal_migration_synthetic_20260925'
ROLE_NAME = 'portal_migration_synthetic_20260925'


@unittest.skipUnless(os.environ.get('PORTAL_PG_MIGRATION_INTEGRATION') == '1',
                     'requires dedicated empty synthetic PostgreSQL database')
class SyntheticMigrationPostgreSQLTest(unittest.TestCase):
    def test_import_under_forced_rls_and_rollback(self):
        import psycopg

        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / 'synthetic.db'
            with sqlite3.connect(copy) as sqlite:
                sqlite.executescript(SOURCE)
                sqlite.executescript('''
                    ALTER TABLE portal_clients ADD COLUMN created_at TEXT;
                    ALTER TABLE portal_clients ADD COLUMN updated_at TEXT;
                    UPDATE portal_clients SET created_at='2026-09-01',updated_at='2026-09-01';
                    ALTER TABLE portal_client_operations ADD COLUMN created_at TEXT;
                    ALTER TABLE portal_client_operations ADD COLUMN updated_at TEXT;
                    UPDATE portal_client_operations
                        SET created_at='2026-09-01',updated_at='2026-09-01';
                ''')
                sqlite.executescript('''
                    CREATE TABLE portal_production_migrations(
                        company_id INTEGER,version INTEGER,applied_at TEXT);
                    INSERT INTO portal_production_migrations VALUES(1,3,'2026-09-25');
                    CREATE TABLE portal_production(
                        company_id INTEGER,kind TEXT,id TEXT,payload TEXT,created_at TEXT);
                ''')
                facts = (
                    ('batches', 'b1', {'number': 'PRT-2026-SYNTHETIC-1'}),
                    ('tasks', 't1', {'batch_id': 'b1'}),
                    ('tariffs', 'rate1', {'employee_rate': 200, 'client_rate': 500,
                                         'effective_from': '2026-09-01'}),
                    ('works', 'w1', {'batch_id': 'b1', 'task_id': 't1',
                                      'salary': 400, 'revenue': 1000}),
                    ('invoices', 'i1', {'work_ids': ['w1'], 'amount': 1000}),
                    ('payments', 'p1', {'invoice_id': 'i1', 'amount': 300}),
                )
                for kind, identity, fields in facts:
                    payload = json.dumps(dict(fields, id=identity, company_id=1))
                    sqlite.execute('INSERT INTO portal_production VALUES(?,?,?,?,?)',
                                   (1, kind, identity, payload, '2026-09-25'))
            source = open_copy(copy)
            self.addCleanup(source.close)
            expected = summary(source, prepared_source(source, 1), 1)

            with psycopg.connect('dbname=' + DB_NAME + ' user=postgres', autocommit=True) as target:
                target.execute('SET ROLE ' + ROLE_NAME)
                role = target.execute('''SELECT current_user,rolsuper,rolbypassrls
                    FROM pg_roles WHERE rolname=current_user''').fetchone()
                self.assertEqual(role, (ROLE_NAME, False, False))
                self.assertTrue(target.execute(
                    "SELECT row_security_active('portal_production')").fetchone()[0])
                self.assertEqual(target.execute('SELECT count(*) FROM companies').fetchone()[0], 0)

                with target.transaction():
                    transfer_control(None, target)
                    actual = transfer(source, target, 1)
                    self.assertEqual(actual['counts'], expected['counts'])
                    self.assertEqual(actual['money'], expected['money'])
                self.assertEqual(target.execute('SELECT count(*) FROM work_log').fetchone()[0], 0)
                with target.transaction():
                    bind_company(target, 1)
                    self.assertEqual(target.execute('SELECT count(*) FROM work_log').fetchone()[0], 1)
                    row = target.execute("SELECT payload FROM portal_production WHERE kind='works'").fetchone()
                    self.assertEqual(json.loads(row[0])['salary'], 400)
                    self.assertEqual(target.execute('SELECT count(*) FROM portal_production').fetchone()[0], 6)

                # A second company cannot read the first company's imported rows.
                with target.transaction():
                    target.execute('''INSERT INTO companies(id,name,user_limit,created_at,updated_at)
                        VALUES(2,'Synthetic B',15,'2026-09-25','2026-09-25')''')
                    bind_company(target, 2, provision=True)
                    self.assertEqual(target.execute('SELECT count(*) FROM work_log').fetchone()[0], 0)
                    self.assertEqual(target.execute('SELECT count(*) FROM portal_production').fetchone()[0], 0)
                with self.assertRaises(psycopg.Error):
                    with target.transaction():
                        bind_company(target, 2)
                        target.execute('''INSERT INTO work_log(id,company_id,client,operation,
                            quantity,salary) VALUES(99,1,'Cross','Cross',1,1)''')
                with target.transaction():
                    bind_company(target, 1)
                    self.assertEqual(target.execute('SELECT count(*) FROM work_log').fetchone()[0], 1)
                with self.assertRaisesRegex(RuntimeError, 'rollback probe'):
                    with target.transaction():
                        target.execute('''INSERT INTO companies(id,name,user_limit,created_at,updated_at)
                            VALUES(3,'Rollback',15,'2026-09-25','2026-09-25')''')
                        raise RuntimeError('rollback probe')
                self.assertEqual(target.execute('SELECT count(*) FROM companies WHERE id=3').fetchone()[0], 0)

    def test_protected_read_validator_and_mismatch(self):
        """Round-trip synthetic rows through the read-only reconciliation path."""
        import psycopg

        with psycopg.connect('dbname=' + DB_NAME + ' user=postgres', autocommit=True) as target:
            target.execute('SET ROLE ' + ROLE_NAME)
            with target.transaction():
                target.execute('SET TRANSACTION READ ONLY')
                bind_company(target, 1)
                source = sqlite3.connect(':memory:')
                self.addCleanup(source.close)
                for table in TABLES:
                    fields = [row[0] for row in target.execute('''SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema=current_schema() AND table_name=%s
                        ORDER BY ordinal_position''', (table,)).fetchall()]
                    if not fields:
                        continue
                    columns = ','.join('"' + field + '" ' +
                                       ('INTEGER' if field == 'company_id' else 'TEXT')
                                       for field in fields)
                    source.execute('CREATE TABLE "' + table + '"(' + columns + ')')
                    names = ','.join('"' + field + '"' for field in fields)
                    rows = target.execute('SELECT ' + names + ' FROM "' + table +
                                          '" WHERE company_id=%s', (1,)).fetchall()
                    for row in rows:
                        values = tuple(value if field == 'company_id' or value is None
                                       else str(Decimal(str(value)).normalize())
                                       if type(value) in (int, float, Decimal) else value
                                       for field, value in zip(fields, row))
                        source.execute('INSERT INTO "' + table + '" VALUES(' +
                                       ','.join('?' for _ in fields) + ')', values)
                self.assertTrue(compare(snapshot(source, 'sqlite', 1),
                                        snapshot(target, 'postgresql', 1)))
                source.execute("UPDATE work_log SET salary='999' WHERE company_id=1")
                with self.assertRaises(ValidationError):
                    compare(snapshot(source, 'sqlite', 1),
                            snapshot(target, 'postgresql', 1))

    def test_imported_identity_sequences_advance(self):
        import psycopg

        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / 'ids.db'
            with sqlite3.connect(copy) as sqlite:
                sqlite.executescript(SOURCE)
            source = open_copy(copy)
            self.addCleanup(source.close)
            maxima = identity_maxima([(1, source)])
            self.assertEqual(maxima['companies'], 1)
            self.assertEqual(maxima['portal_clients'], 1)
            with psycopg.connect('dbname=' + DB_NAME + ' user=postgres', autocommit=True) as target:
                target.execute('SET ROLE ' + ROLE_NAME)
                with target.transaction():
                    self.assertGreaterEqual(sync_identity_sequences(target, maxima), 4)
                for table in ('companies', 'portal_clients', 'portal_client_operations',
                              'work_log', 'client_invoices'):
                    sequence = target.execute("SELECT pg_get_serial_sequence(%s,'id')",
                                              ('public.' + table,)).fetchone()[0]
                    self.assertGreater(target.execute('SELECT nextval(%s::regclass)',
                                                      (sequence,)).fetchone()[0], maxima[table])


if __name__ == '__main__':
    unittest.main()
