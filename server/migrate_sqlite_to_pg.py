"""Explicit offline migration of SQLite backups to a prepared PostgreSQL DB.

Default dry-run reads copies only. --apply imports atomically and verifies every
copied table. The running server and phone database are never addressed here.
"""
import argparse
import json
import os
import sys
from contextlib import ExitStack, closing
from pathlib import Path

from migration_import import (ValidationError, open_copy, prepared_source,
                              summary, transfer, transfer_control,
                              identity_maxima, sync_identity_sequences)
from migration_context import bind_company
from production_migrations import migrate_payroll_settlement
from production_repository import Repository


def parse_tenant(spec):
    number, separator, path = spec.partition(':')
    if not separator or not number.isdecimal() or int(number) < 1 or not path:
        raise argparse.ArgumentTypeError('Use COMPANY_ID:PATH_TO_SQLITE_COPY')
    return int(number), path


def run(tenant_specs, platform_path=None, apply=False, dsn=None):
    if len({company_id for company_id, _ in tenant_specs}) != len(tenant_specs):
        raise ValidationError('Duplicate company_id')
    if not platform_path and set(company_id for company_id, _ in tenant_specs) != {1}:
        raise ValidationError('Platform copy required for multiple companies')
    with ExitStack() as stack:
        tenants = [(cid, stack.enter_context(closing(open_copy(path)))) for cid, path in tenant_specs]
        control = stack.enter_context(closing(open_copy(platform_path))) if platform_path else None
        if control and 'companies' not in [row[0] for row in control.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")]:
            raise ValidationError('Platform copy lacks companies')
        if control:
            source_ids = {row[0] for row in control.execute('SELECT id FROM companies')}
            if source_ids != {cid for cid, _ in tenants}:
                raise ValidationError('Company count/IDs differ from tenant copies')
        report = {'status': 'DRY_RUN', 'company_count': len(tenants), 'companies': []}
        for cid, source in tenants:
            columns = prepared_source(source, cid)
            facts = summary(source, columns, cid)
            report['companies'].append({'company_id': cid, 'counts': facts['counts'],
                                        'money': facts['money']})
        if not apply:
            return report
        if not dsn:
            raise ValidationError('PORTAL_MIGRATION_DSN is required for --apply')
        try:
            import psycopg
        except ImportError as exc:
            raise RuntimeError('psycopg 3 is required on migration host') from exc
        with psycopg.connect(dsn) as target:
            with target.transaction():
                report['control'] = transfer_control(control, target)
                for cid, source in tenants:
                    transferred = transfer(source, target, cid)
                    before = next(x for x in report['companies'] if x['company_id'] == cid)
                    if transferred['counts'] != before['counts'] or transferred['money'] != before['money']:
                        raise ValidationError('Migration FAILED: company reconciliation')
                # The source can legitimately predate Stage 6. Finalize each imported
                # company inside this same atomic cutover transaction before the API
                # is ever allowed to start.
                for cid, _source in tenants:
                    bind_company(target, cid)
                    migrate_payroll_settlement(Repository(target, cid, dialect='postgresql'))
                report['identity_sequences_checked'] = sync_identity_sequences(
                    target, identity_maxima(tenants, control))
        report['status'] = 'IMPORTED_AND_VERIFIED'
        return report


def main():
    parser = argparse.ArgumentParser(description='SQLite backup copy -> PostgreSQL')
    parser.add_argument('--tenant-copy', action='append', type=parse_tenant, required=True,
                        help='COMPANY_ID:PATH; repeat for every company')
    parser.add_argument('--platform-copy', help='Read-only copy of portal.db.platform.db')
    parser.add_argument('--apply', action='store_true', help='Explicitly import into empty prepared PostgreSQL')
    parser.add_argument('--report', required=True, help='JSON report path outside the application repo')
    args = parser.parse_args()
    report = {'status': 'FAILED'}
    try:
        report = run(args.tenant_copy, args.platform_copy, args.apply,
                     os.environ.get('PORTAL_MIGRATION_DSN'))
    except (ValidationError, RuntimeError) as exc:
        report['reason'] = str(exc)
    except Exception as exc:
        # DB driver exceptions may contain a DSN or sensitive row values.
        report['reason'] = type(exc).__name__
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(report['status'] + ': report written to ' + str(report_path))
    return 0 if report['status'] != 'FAILED' else 1


if __name__ == '__main__':
    sys.exit(main())
