"""Offline adapter tests; these do not claim a PostgreSQL integration test."""
import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import portal_postgres as pg
from production_repository import Repository


class FakeCursor:
    def __init__(self, rows=(), names=('value',)):
        self.rows = list(rows)
        self.description = [(name,) for name in names]
        self.rowcount = len(self.rows)

    def fetchone(self):
        return self.rows.pop(0) if self.rows else None

    def fetchall(self):
        rows, self.rows = self.rows, []
        return rows

    def close(self):
        pass


class FakeConnection:
    def __init__(self):
        self.calls = []
        self.commits = self.rollbacks = self.closed = 0
        self.result = []

    def execute(self, sql, params=()):
        self.calls.append((sql, params))
        return FakeCursor(self.result)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed += 1


class PostgreSQLAdapterTests(unittest.TestCase):
    def test_row_is_mapping_and_value_sequence(self):
        row = pg.Row((12, 'Тест'), ('id', 'name'))
        self.assertEqual(row[0], row['id'])
        self.assertEqual(tuple(row), (12, 'Тест'))
        self.assertEqual(dict(row), {'id': 12, 'name': 'Тест'})
        self.assertEqual(dict(row, active=1)['active'], 1)
        self.assertEqual(row.keys(), ['id', 'name'])

    def test_placeholders_skip_literals_comments_and_identifiers(self):
        sql = '''SELECT ?, '?%', "odd?%", 'it''s ?', $$?%$$, $body$?%$body$, 5 % 2, %s
        -- ?%
        /* ?% /* nested ? */ */ WHERE name=?'''
        translated = pg.translate_sql(sql)
        self.assertEqual(translated.count('%s'), 3)
        self.assertIn("'?%%'", translated)
        self.assertIn('$$?%%$$', translated)
        self.assertIn('5 %% 2', translated)
        self.assertIn('-- ?%%', translated)
        self.assertIn('/* ?%% /* nested ? */ */', translated)
        self.assertEqual(pg.translate_sql("SELECT E'escaped\\\'?%', ?"), "SELECT E'escaped\\\'?%%', %s")

    def test_existing_nocase_comparisons_and_order(self):
        self.assertEqual(pg.translate_sql('SELECT id FROM portal_clients WHERE name=? COLLATE NOCASE AND id!=?'),
                         'SELECT id FROM portal_clients WHERE lower(name)=lower(%s) AND id!=%s')
        self.assertEqual(pg.translate_sql('SELECT name FROM portal_clients ORDER BY name COLLATE NOCASE'),
                         'SELECT name FROM portal_clients ORDER BY lower(name)')
        self.assertEqual(pg.translate_sql("SELECT 'name=? COLLATE NOCASE'"), "SELECT 'name=? COLLATE NOCASE'")

    def test_context_reapplied_after_commit_and_rollback(self):
        raw = FakeConnection()
        conn = pg.Connection(raw, 42, 'x' * 64)
        conn.execute('SELECT ? AS value', (1,))
        conn.execute('SELECT 2')
        conn.commit()
        conn.execute('SELECT 3')
        conn.rollback()
        conn.execute('SELECT 4')
        contexts = [params for sql, params in raw.calls if 'portal_bind_company' in sql]
        self.assertEqual(contexts, [(42, 'x' * 64)] * 3)

    def test_control_and_tenant_locks_never_share_key(self):
        control, tenant = FakeConnection(), FakeConnection()
        pg.Connection(control).execute('BEGIN IMMEDIATE')
        pg.Connection(tenant, 1, 'x' * 64).execute('BEGIN IMMEDIATE')
        self.assertEqual(control.calls[-1][1], (pg.CONTROL_LOCK,))
        self.assertEqual(tenant.calls[-1][1], (1,))
        self.assertLess(pg.CONTROL_LOCK, 0)
        self.assertEqual(control.calls[0][1], ('',))

    def test_lastrowid_does_not_consume_explicit_returning(self):
        raw = FakeConnection()
        raw.result = [(17,)]
        conn = pg.Connection(raw, 1, 'x' * 64)
        cur = conn.execute('INSERT INTO portal_clients(name) VALUES(?)', ('Тест',))
        self.assertEqual(cur.lastrowid, 17)
        self.assertTrue(raw.calls[-1][0].endswith('RETURNING id'))
        cur = conn.execute('INSERT INTO work_log(company_id) VALUES(?) RETURNING id', (1,))
        self.assertIsNone(cur.lastrowid)
        self.assertEqual(cur.fetchone()[0], 17)
        self.assertEqual(raw.calls[-1][0].count('RETURNING'), 1)
        conn.execute('INSERT INTO portal_production(id) VALUES(?)', ('text-id',))
        self.assertNotIn('RETURNING', raw.calls[-1][0])

    def test_context_manager_closes_success_and_rollback(self):
        raw = FakeConnection()
        with pg.Connection(raw, 1, 'x' * 64):
            pass
        self.assertEqual((raw.commits, raw.rollbacks, raw.closed), (1, 0, 1))
        raw = FakeConnection()
        with self.assertRaisesRegex(ValueError, 'business error'):
            with pg.Connection(raw, 1, 'x' * 64):
                raise ValueError('business error')
        self.assertEqual((raw.commits, raw.rollbacks, raw.closed), (0, 1, 1))

    def test_runtime_validation_rejects_every_privilege(self):
        raw = FakeConnection()
        conn = pg.Connection(raw, 1, 'x' * 64)
        raw.result = [(False,) * 5]
        self.assertTrue(pg.validate_runtime_role(conn))
        for forbidden in range(5):
            raw.result = [tuple(index == forbidden for index in range(5))]
            with self.assertRaises(PermissionError):
                pg.validate_runtime_role(conn)


    def test_repository_list_by_pushes_json_filter_into_postgresql(self):
        raw = FakeConnection()
        raw.result = [(json.dumps({'id':'t1','company_id':1,'operation_id':7}),)]
        repo = Repository(pg.Connection(raw, 1, 'x' * 64), 1)
        rows = repo.list_by('tariffs', operation_id=7)
        self.assertEqual(rows[0]['operation_id'], 7)
        sql, params = raw.calls[-1]
        self.assertIn("payload::jsonb ->> 'operation_id'=%s", sql)
        self.assertEqual(params, (1, 'tariffs', '7'))
        with self.assertRaises(ValueError):
            repo.list_by('tariffs', **{'bad-field': 7})

    def test_bounded_pool_reuses_raw_connection_and_rebinds_tenant(self):
        created = []
        def driver(*args, **kwargs):
            raw = FakeConnection()
            created.append(raw)
            return raw
        pg.close_pools()
        try:
            with patch.dict(sys.modules, {'psycopg': SimpleNamespace(connect=driver)}):
                first = pg.connect_pooled('postgresql://secret@db/portal', 1, 'a' * 64, max_size=2)
                first.execute('SELECT 10')
                first.close()
                second = pg.connect_pooled('postgresql://secret@db/portal', 2, 'b' * 64, max_size=2)
                second.execute('SELECT 20')
                second.close()
            self.assertEqual(len(created), 1)
            contexts = [params for sql, params in created[0].calls if 'portal_bind_company' in sql]
            self.assertEqual(contexts, [(1, 'a' * 64), (2, 'b' * 64)])
            self.assertGreaterEqual(created[0].rollbacks, 4)
            self.assertEqual(created[0].closed, 0)
        finally:
            pg.close_pools()
        self.assertEqual(created[0].closed, 1)

    def test_pool_size_validation(self):
        for invalid in (0, -1, 65, True, '8'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                pg.connect_pooled('unused', max_size=invalid)

    def test_company_validation_and_connection_errors_hide_secrets(self):
        for invalid in (0, -1, True, '1', 2**63):
            with self.assertRaises(PermissionError):
                pg.connect('unused', invalid)
        def failing_driver(*args, **kwargs):
            raise RuntimeError('password=SHOULD_NEVER_APPEAR')
        with patch.dict(sys.modules, {'psycopg': SimpleNamespace(connect=failing_driver)}):
            with self.assertRaises(ConnectionError) as result:
                pg.connect('password=SHOULD_NEVER_APPEAR', 1)
        self.assertNotIn('SHOULD_NEVER_APPEAR', str(result.exception))
        self.assertTrue(result.exception.__suppress_context__)


if __name__ == '__main__':
    unittest.main()
