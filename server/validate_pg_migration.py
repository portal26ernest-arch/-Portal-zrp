"""Future read-only cutover gate for an offline SQLite copy and PostgreSQL.

Requires psycopg 3 on the Linux migration host. Does not create or import data.
The PostgreSQL DSN is read only from PORTAL_MIGRATION_DSN, never argv.
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

from migration_validation import (ValidationError, compare, compare_migration_history,
                                  snapshot)
from migration_context import bind_company


def validate(sqlite_copy, company_ids, pg_dsn):
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError('psycopg 3 is required on the migration host') from exc
    source_path = Path(sqlite_copy).resolve(strict=True)
    if not source_path.is_file():
        raise ValidationError('SQLite copy is not a file')
    # mode=ro prevents accidental edits to the source copy. The original phone
    # database is never opened by this tool.
    with sqlite3.connect(source_path.as_uri() + '?mode=ro', uri=True) as source:
        with psycopg.connect(pg_dsn) as target:
            with target.transaction():
                target.execute('SET TRANSACTION READ ONLY')
                for company_id in company_ids:
                    bind_company(target, company_id)
                    source_facts = snapshot(source, 'sqlite', company_id, allow_legacy_primary=True)
                    target_facts = snapshot(target, 'postgresql', company_id,
                                            projection=source_facts)
                    source_tables = {row[0] for row in source.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'")}
                    if 'portal_production_migrations' in source_tables:
                        history_columns = {row[1] for row in source.execute(
                            'PRAGMA table_info(portal_production_migrations)')}
                        if 'company_id' in history_columns:
                            source_history = source.execute(
                                'SELECT version,applied_at FROM portal_production_migrations '
                                'WHERE company_id=? ORDER BY version', (company_id,)).fetchall()
                        elif company_id == 1:
                            source_history = source.execute(
                                'SELECT version,applied_at FROM portal_production_migrations '
                                'ORDER BY version').fetchall()
                        else:
                            raise ValidationError('Missing company_id: portal_production_migrations')
                    else:
                        source_history = []
                    target_history = target.execute(
                        'SELECT version,applied_at FROM portal_production_migrations '
                        'WHERE company_id=%s ORDER BY version', (company_id,)).fetchall()
                    compare_migration_history(source_history, target_history, required_version=6,
                                              additional_required_versions=(7,))
                    source_facts = dict(source_facts)
                    target_facts = dict(target_facts)
                    source_facts.pop('portal_production_migrations', None)
                    target_facts.pop('portal_production_migrations', None)
                    compare(source_facts, target_facts)
                    print('Validated company_id=' + str(company_id))


def main():
    parser = argparse.ArgumentParser(description='Read-only SQLite/PostgreSQL reconciliation')
    parser.add_argument('--sqlite-copy', required=True)
    parser.add_argument('--company-id', type=int, action='append', required=True)
    args = parser.parse_args()
    dsn = os.environ.get('PORTAL_MIGRATION_DSN')
    if not dsn:
        parser.error('PORTAL_MIGRATION_DSN is required')
    try:
        validate(args.sqlite_copy, args.company_id, dsn)
    except (ValidationError, RuntimeError) as exc:
        print('Validation failed: ' + str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        # Driver errors can contain connection details. Never echo their text.
        print('Validation failed: ' + type(exc).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
