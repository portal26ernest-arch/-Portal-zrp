#!/usr/bin/env python3
from __future__ import annotations
import argparse, importlib.util, json, re
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('legacy_runtime_audit',ROOT/'ops/legacy_runtime_audit.py')
legacy=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(legacy)

IMPORT_FILES={'server/excel_apply.py','server/excel_import.py','server/excel_template.py','server/migration_import.py'}
SCHEMA_FILES={'server/production_migrations.py'}
FIXTURE_FILES={'server/web_pg_part10_fixture_host.py'}
COMPATIBILITY_ADAPTERS={'server/employee_identity.py'}
SQL_RUNTIME=re.compile(r'\b(SELECT|WHERE|JOIN|INSERT|UPDATE)\b.*\btelegram_id\b|\btelegram_id\b.*\b(SELECT|WHERE|JOIN|INSERT|UPDATE)\b',re.I)
USER_RUNTIME=re.compile(r'user\.get\([\"\']telegram_id|user\[[\"\']telegram_id|worker_id\s*=.*telegram_id',re.I)

def classify(row):
    path=row['path'];kind=row['kind'];line=row['text']
    if kind=='forbidden_external_runtime':return 'P0_forbidden_external_runtime'
    if kind=='runtime_bridge':return 'P1_explicit_compatibility_bridge'
    if path in FIXTURE_FILES:return 'P2_fixture_support'
    if path in IMPORT_FILES:return 'P1_import_export_boundary'
    if path in SCHEMA_FILES:return 'P1_legacy_schema_boundary'
    if path in COMPATIBILITY_ADAPTERS and kind=='runtime_direct_telegram_id':
        return 'P1_explicit_compatibility_bridge'
    if kind=='runtime_direct_telegram_id' and (SQL_RUNTIME.search(line) or USER_RUNTIME.search(line)):
        return 'P0_runtime_identity_dependency'
    if kind=='runtime_direct_telegram_id':return 'P1_runtime_compatibility_shape'
    return 'P2_history_schema_test'
def advice(path,category):
    if category=='P0_forbidden_external_runtime':return 'Remove Telegram/Termux runtime dependency entirely.'
    if category=='P0_runtime_identity_dependency':
        if path=='server/portal_app_server.py':
            return 'Resolve canonical employee_id before queries/writes; keep telegram_id only behind an explicit legacy adapter.'
        if path in {'server/production_repository.py','server/production_service.py'}:
            return 'Make employee_id the service/repository contract; translate to legacy ids only inside one compatibility boundary.'
        return 'Replace active runtime identity lookup/write with canonical employee_id.'
    if category=='P1_import_export_boundary':
        return 'Keep as temporary migration bridge; exported/API identity should be employee_id and legacy mapping must be explicit.'
    if category=='P1_legacy_schema_boundary':
        return 'Retain historical schema/FK until additive migration and rollback rehearsal prove removal safe.'
    if category=='P1_explicit_compatibility_bridge':
        return 'Allowed temporarily: bridge is explicit and must remain covered by compatibility tests.'
    if category=='P1_runtime_compatibility_shape':
        if path=='server/portal_app_server.py':
            return 'Only the retained legacy column declaration and canonical API-boundary note; request/response identity uses employee_id.'
        return 'Review manually; move this shape behind the canonical employee_id adapter.'
    return 'Historical/test/support evidence; not a runtime cutover blocker by itself.'

def build(root=ROOT):
    source=legacy.scan(root);rows=[]
    for row in source['findings']:
        category=classify(row);rows.append(dict(row,priority=category,action=advice(row['path'],category)))
    counts=Counter(x['priority'] for x in rows);by_file=defaultdict(Counter)
    for x in rows:by_file[x['path']][x['priority']]+=1
    return {'counts':dict(counts),'files':{k:dict(v) for k,v in sorted(by_file.items())},'findings':rows}

def p0_count(data):return sum(v for k,v in data['counts'].items() if k.startswith('P0_'))
def report(data):
    c=data['counts'];out=['# PORTAL employee identity migration map','',
        'Read-only evidence. Canonical runtime identity target: employee_id.','',
        '## Priority summary','',
        f"- P0 forbidden external runtime: {c.get('P0_forbidden_external_runtime',0)}",
        f"- P0 active runtime identity dependencies: {c.get('P0_runtime_identity_dependency',0)}",
        f"- P1 compatibility/import/schema boundaries: {sum(v for k,v in c.items() if k.startswith('P1_'))}",
        f"- P2 history/test/fixture references: {sum(v for k,v in c.items() if k.startswith('P2_'))}",'',
        'P0 runtime identity dependencies are the actionable blockers for roadmap item 102. P1 bridges may remain temporarily when explicit, tested and isolated.','',
        '## Files requiring action','',
        '| File | P0 | P1 | P2 | Recommended action |','|---|---:|---:|---:|---|']
    for path,kinds in data['files'].items():
        p0=sum(v for k,v in kinds.items() if k.startswith('P0_'));p1=sum(v for k,v in kinds.items() if k.startswith('P1_'));p2=sum(v for k,v in kinds.items() if k.startswith('P2_'))
        if not (p0 or p1):continue
        cats=[x for x in data['findings'] if x['path']==path and (x['priority'].startswith('P0_') or x['priority'].startswith('P1_'))]
        action=cats[0]['action'] if cats else ''
        out.append(f"| {path} | {p0} | {p1} | {p2} | {action.replace('|','/')} |")
    out+=['','## P0 line evidence','', '| File | Line | Evidence |','|---|---:|---|']
    for x in data['findings']:
        if x['priority'].startswith('P0_'):out.append(f"| {x['path']} | {x['line']} | {x['text'].replace('|','/')} |")
    out+=['','## Explicit P1 bridge inventory','',
        'P1 is limited to the single `server/employee_identity.py` compatibility adapter, the read-only migration-source contract, additive retained-schema DDL and the canonical API-boundary note. Spreadsheet template preview/apply now calls the adapter. All service/UI request and response identity fields use `employee_id`; legacy columns remain storage/history keys only. The source lines below are generated by the same read-only scanner.','',
        '| File | Line | Explicit bridge evidence |','|---|---:|---|']
    for x in data['findings']:
        if x['priority'].startswith('P1_'):
            out.append(f"| {x['path']} | {x['line']} | {x['text'].replace('|','/')} |")
    out+=['','### Test coverage for retained bridges','',
        '- `server/test_production.py::test_authenticated_runtime_identity_and_catalog_are_canonical_and_company_scoped` verifies canonical API payloads, legacy-key mapping, and rejection of foreign-company employee IDs.',
        '- `server/test_production.py::test_manager_assignment_catalog_uses_canonical_employee_id` verifies manager assignment projection.',
        '- `server/test_portal_app_server.py` covers account lifecycle, rejection of public `telegram_id` account payloads, invite/account linking and personal work reads.',
        '- `server/test_payroll_settlement.py` covers canonical settlement inputs and legacy immutable snapshot compatibility.',
        '- `server/test_excel_import.py` and `server/test_excel_template.py` cover canonical employee IDs at spreadsheet preview/apply/template boundaries.',
        '- `server/test_documents_postgresql.py::test_employee_identity_api_contract_is_canonical_and_company_scoped` runs duplicate legacy keys across two synthetic companies through real PostgreSQL/RLS and checks cross-company rejection.',
        '- `ops/test_employee_identity_migration_audit.py` fails if active direct runtime references appear outside the declared adapter or external Telegram/Termux runtime is detected.']
    return '\n'.join(out)+'\n'
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',default=str(ROOT))
    ap.add_argument('--markdown');ap.add_argument('--json');ap.add_argument('--fail-on-p0',action='store_true')
    a=ap.parse_args();data=build(Path(a.root).resolve())
    if a.markdown:Path(a.markdown).write_text(report(data),encoding='utf-8')
    if a.json:Path(a.json).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'p0':p0_count(data),'counts':data['counts']},ensure_ascii=False,sort_keys=True))
    return 4 if a.fail_on_p0 and p0_count(data) else 0

if __name__=='__main__':raise SystemExit(main())
