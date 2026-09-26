"""Protected-context migration contract; uses no deployment database."""
import unittest

from migration_context import bind_company
from migration_validation import ValidationError


class Cursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class Target:
    def __init__(self, available=True):
        self.available = available
        self.calls = []

    def execute(self, sql, args):
        self.calls.append((sql, args))
        return Cursor(() if 'INSERT INTO' in sql else (() if self.available else None))


class MigrationContextTest(unittest.TestCase):
    def test_import_provisions_only_key_then_binds_without_returning_secret(self):
        target = Target()
        bind_company(target, 7, provision=True)
        self.assertEqual(len(target.calls), 2)
        self.assertIn('ON CONFLICT(company_id) DO NOTHING', target.calls[0][0])
        self.assertIn('portal_bind_company(%s,secret)', target.calls[1][0])
        self.assertEqual(target.calls[0][1], (7,))
        self.assertEqual(target.calls[1][1], (7, 7))
        self.assertFalse(any('set_config' in sql for sql, _ in target.calls))

    def test_validator_requires_existing_key_and_rejects_invalid_company(self):
        target = Target(available=False)
        with self.assertRaisesRegex(ValidationError, 'unavailable'):
            bind_company(target, 3)
        self.assertEqual(len(target.calls), 1)
        with self.assertRaisesRegex(ValidationError, 'Invalid company_id'):
            bind_company(target, 0, provision=True)
        self.assertEqual(len(target.calls), 1)


if __name__ == '__main__':
    unittest.main()
