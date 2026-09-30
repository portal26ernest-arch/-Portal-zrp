"""Exact integer-minor-unit conversion at legacy major-unit DB boundaries."""

from decimal import Decimal


def legacy_major_currency(amount_minor, dialect):
    """Project integer minor units into a legacy numeric column representation.

    PostgreSQL NUMERIC receives Decimal, avoiding binary float conversion.
    SQLite legacy NUMERIC/REAL schemas require a float-compatible binding; the
    canonical integer value remains authoritative and reconciliation detects drift.
    """
    if type(amount_minor) is not int:
        raise ValueError('Money must be an integer number of minor units')
    amount = Decimal(amount_minor).scaleb(-2)
    if dialect == 'postgresql':
        return amount
    if dialect == 'sqlite':
        return float(amount)
    raise ValueError('Unsupported database dialect')
