"""Canonical employee identity rules on synthetic, company-scoped legacy rows."""
import sqlite3
import unittest

from employee_identity import (canonical_employee_id, employee_catalog,
                               employee_id_for_user, legacy_employee_id, user_catalog)


class EmployeeIdentityBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.conn=sqlite3.connect(':memory:')
        self.conn.execute('CREATE TABLE employees(company_id INTEGER NOT NULL, telegram_id INTEGER NOT NULL, full_name TEXT, username TEXT, PRIMARY KEY(company_id,telegram_id))')
        self.conn.execute('CREATE TABLE app_users(id INTEGER PRIMARY KEY,company_id INTEGER,telegram_id INTEGER,display_name TEXT,role TEXT,active INTEGER)')
        self.conn.executemany('INSERT INTO employees VALUES(?,?,?,?)',[(1,101,'A','a'),(1,202,'B','b'),(2,101,'C','c')])

    def tearDown(self):
        self.conn.close()

    def test_unmigrated_legacy_number_is_never_exposed_as_employee_id(self):
        self.assertIsNone(canonical_employee_id(self.conn,1,101))
        self.assertIsNone(legacy_employee_id(self.conn,1,101))
        self.assertIsNone(employee_id_for_user(self.conn,1,{'telegram_id':101}))
        with self.assertRaises(RuntimeError):employee_catalog(self.conn,1)
        with self.assertRaises(RuntimeError):user_catalog(self.conn,1)

    def test_mapping_is_tenant_scoped_and_user_link_must_match(self):
        self.conn.execute('CREATE TABLE payroll_employee_identities(company_id INTEGER NOT NULL,employee_id INTEGER NOT NULL,legacy_employee_id INTEGER NOT NULL,PRIMARY KEY(company_id,employee_id),UNIQUE(company_id,legacy_employee_id))')
        self.conn.executemany('INSERT INTO payroll_employee_identities VALUES(?,?,?)',[(1,7,101),(1,8,202),(2,9,101)])
        self.assertEqual(canonical_employee_id(self.conn,1,101),7)
        self.assertEqual(canonical_employee_id(self.conn,2,101),9)
        self.assertIsNone(legacy_employee_id(self.conn,1,9))
        self.assertIsNone(employee_id_for_user(self.conn,1,{'employee_id':9,'telegram_id':101}))
        self.assertIsNone(employee_id_for_user(self.conn,1,{'employee_id':7,'telegram_id':202}))
        self.assertEqual(employee_id_for_user(self.conn,1,{'employee_id':7,'telegram_id':101}),7)
        self.assertIsNone(canonical_employee_id(self.conn,1,101.5))
        self.assertIsNone(legacy_employee_id(self.conn,1,7.5))
        self.assertIsNone(legacy_employee_id(self.conn,1,True))


if __name__ == '__main__':unittest.main()
