import unittest
from decimal import Decimal

from money_units import legacy_major_currency
from production_repository import Repository


class LegacyMoneyBoundaryTest(unittest.TestCase):
    def test_postgresql_numeric_binding_is_exact_decimal(self):
        value = legacy_major_currency(1001, 'postgresql')
        self.assertIsInstance(value, Decimal)
        self.assertEqual(value, Decimal('10.01'))

    def test_sqlite_legacy_binding_remains_float_compatible(self):
        value = legacy_major_currency(1001, 'sqlite')
        self.assertIs(type(value), float)
        self.assertEqual(value, 10.01)

    def test_repository_legacy_numeric_writes_use_exact_postgresql_decimal(self):
        class RecordingRepository(Repository):
            def __init__(self):
                self.calls = []
                super().__init__(None, 1, 'postgresql')

            def has_table(self, table):
                return table == 'material_movements'

            def columns(self, table):
                return {'company_id', 'material_id', 'qty_change', 'unit_cost',
                        'movement_type', 'reference_type', 'reference_id', 'note',
                        'created_at', 'created_by'}

            def sql(self, query, args=()):
                self.calls.append((query, args))

        repository = RecordingRepository()
        repository.consume(3, 1.5, 1001, 88, 9)
        movement = repository.calls[-1][1]
        self.assertIn(Decimal('10.01'), movement)
        repository.project_cost(88, 1001)
        self.assertEqual(repository.calls[-1][1][0], Decimal('10.01'))

    def test_rejects_non_integer_minor_units_and_unknown_dialects(self):
        for value, dialect in ((1.01, 'sqlite'), (101, 'mysql')):
            with self.subTest(value=value, dialect=dialect):
                with self.assertRaises(ValueError):
                    legacy_major_currency(value, dialect)


if __name__ == '__main__':
    unittest.main()
