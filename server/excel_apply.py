"""Transactional catalog adapter. No work/payroll/invoice fact updates."""
import uuid
from decimal import Decimal
from document_domain import Documents,decode_file,validate_upload,XLSX_MIME
from documents_api import require_import
from excel_template import REQUISITES,TEMPLATE_VERSION
from excel_import import canonical,digest,LOG
from portal_excel_workbook import parse_template
from production_repository import utcnow
from employee_identity import create_employee_card,hash_access_pin,update_employee_card,write_user_account
from employee_names import persist_employee_rename,persist_known_employee_aliases

JOB_COLUMNS=('company_id','import_id','template_version','checksum','actor_id','actor_kind','created_at','status',
             'preview_summary','applied_at','result_counts','error_report','result_document_id')

def job(importer,identity):
    import json
    row=importer.r.sql('SELECT '+','.join(JOB_COLUMNS)+' FROM portal_excel_imports WHERE company_id=? AND import_id=?',(importer.r.company_id,str(identity))).fetchone()
    if not row:return None
    value=dict(zip(JOB_COLUMNS,row))
    for key in ('preview_summary','result_counts','error_report'):
        if isinstance(value[key],str):value[key]=json.loads(value[key])
    return value

def public_job(value):
    return {key:value[key] for key in ('company_id','import_id','template_version','checksum','status','created_at','applied_at','result_counts','error_report','result_document_id')}

def import_result(importer,identity):
    require_import(importer.s)
    value=job(importer,identity)
    if not value:raise ValueError('Импорт не найден')
    return public_job(value)

def _requisites(importer,table,key,identity,values,extra):
    r=importer.r;fields=REQUISITES+(extra,);supported=set(r.columns(table))
    if any(values.get(field) and field not in supported for field in fields):raise ValueError('Unsupported requisite field')
    record={field:values.get(field) or None for field in fields if field in supported}
    existing=r.sql('SELECT 1 FROM '+table+' WHERE company_id=? AND '+key+'=?',(r.company_id,identity)).fetchone()
    if not existing and not any(record.values()):return
    record.update(updated_at=utcnow(),updated_by=importer.u['id'])
    record={k:v for k,v in record.items() if k in supported}
    if existing:
        r.sql('UPDATE '+table+' SET '+','.join(k+'=?' for k in record)+' WHERE company_id=? AND '+key+'=?',tuple(record.values())+(r.company_id,identity))
    else:
        record.update(company_id=r.company_id,**{key:identity})
        r.sql('INSERT INTO '+table+'('+','.join(record)+') VALUES('+','.join('?' for _ in record)+')',tuple(record.values()))

def _apply_row(importer,row,refs):
    r=importer.r;value=row['normalized'];sheet=row['sheet'];now=utcnow()
    if row['classification']=='unchanged':
        if sheet=='Клиенты':refs[value['client_ref']]=value['client_id']
        return None
    if sheet=='Компания':
        _requisites(importer,'portal_company_requisites','id',1,value,'director');return 1
    if sheet=='Клиенты':
        identity=value['client_id']
        if identity is None:
            identity=r.sql('INSERT INTO portal_clients(company_id,name,active,created_at,updated_at) VALUES(?,?,?,?,?) RETURNING id',
                           (r.company_id,value['name'],value['active'],now,now)).fetchone()[0]
        else:
            r.sql('UPDATE portal_clients SET name=?,active=?,updated_at=? WHERE company_id=? AND id=?',
                  (value['name'],value['active'],now,r.company_id,identity))
        refs[value['client_ref']]=identity
        _requisites(importer,'portal_client_requisites','client_id',identity,value,'contact_person')
        return identity
    if sheet=='Сотрудники':
        identity=value['employee_id']
        if identity is None:
            identity=create_employee_card(r.conn,r.company_id,value['full_name'],value['profile_username'])
            persist_known_employee_aliases(r,identity,value['full_name'])
        else:
            before_employee=next((employee for employee in r.employee_catalog() if employee['employee_id']==identity),None)
            if before_employee is None:raise ValueError('employee_id не найден в этой компании')
            update_employee_card(r.conn,r.company_id,identity,value['full_name'],value['profile_username'])
            persist_employee_rename(r,identity,before_employee['full_name'],value['full_name'])
        if value['user_id']:
            old=r.sql('SELECT role,active FROM app_users WHERE company_id=? AND id=?',(r.company_id,value['user_id'])).fetchone()
            if (old[0],old[1])!=(value['role'],value['active']):
                r.sql('UPDATE app_users SET role=?,active=?,updated_at=? WHERE company_id=? AND id=?',
                      (value['role'],value['active'],now,r.company_id,value['user_id']))
                r.sql('DELETE FROM app_sessions WHERE company_id=? AND user_id=?',(r.company_id,value['user_id']))
        elif value.get('create_access'):
            salt,pin_hash=hash_access_pin(value['initial_pin'])
            account=dict(username=value['profile_username'],display_name=value['full_name'],role=value['role'],
                         active=value['active'],employee_id=identity)
            write_user_account(r.conn,r.company_id,None,account,salt,pin_hash,now)
        return identity
    cid=refs.get(value['client_ref'],value['client_id'])
    if type(cid) is not int:raise ValueError('Client mapping missing')
    identity=value['operation_id']
    if identity is None:
        # Catalog baseline applies only to this new operation, not existing rates.
        rate=format(Decimal(value['employee_rate'])/100,'.2f')
        price=None if value['client_rate'] is None else format(Decimal(value['client_rate'])/100,'.2f')
        identity=r.sql('''INSERT INTO portal_client_operations(company_id,client_id,name,active,employee_rate,client_rate,sort_order,created_at,updated_at)
             VALUES(?,?,?,?,?,?,0,?,?) RETURNING id''',(r.company_id,cid,value['name'],value['active'],rate,price,now,now)).fetchone()[0]
    else:
        # Existing physical catalog rates and every historical snapshot stay intact.
        r.sql('UPDATE portal_client_operations SET name=?,active=?,updated_at=? WHERE company_id=? AND id=? AND client_id=?',
              (value['name'],value['active'],now,r.company_id,identity,cid))
    if value['append_tariff']:
        r.insert('tariffs',dict(operation_id=identity,client_id=cid,effective_from=value['effective_from'] or now,
                              employee_rate=value['employee_rate'],client_rate=value['client_rate'],changed_fields=['employee_rate','client_rate']))
    return identity

def _save_outcome(importer,claims,plan,status,counts,errors,old=None):
    r=importer.r;identity=claims['import_id'];now=utcnow()
    report=dict(import_id=identity,company_id=r.company_id,template_version=TEMPLATE_VERSION,checksum=claims['checksum'],
                status=status,summary=plan['summary'],result_counts=counts,errors=errors)
    request_id=identity+':result:'+status+(':'+uuid.uuid4().hex if status=='failed' else '')
    document=Documents(importer.s,importer.storage).register(canonical(report).encode(),
        dict(document_type='import_result',original_filename='PORTAL_import_'+identity+'.json',mime_type='application/json',
             title='Результат импорта PORTAL',request_id=request_id,category='imports',metadata=dict(import_id=identity,result=status,template_version=TEMPLATE_VERSION)),
        'imported')
    record=dict(company_id=r.company_id,import_id=identity,template_version=TEMPLATE_VERSION,checksum=claims['checksum'],
                actor_id=importer.u['id'],actor_kind=importer.actor_kind(),created_at=old['created_at'] if old else now,status=status,
                preview_summary=canonical(plan['summary']),applied_at=now if status=='applied' else None,
                result_counts=canonical(counts),error_report=canonical(errors),result_document_id=document['id'])
    if old:
        fields=[k for k in JOB_COLUMNS if k not in ('company_id','import_id','checksum','template_version')]
        r.sql('UPDATE portal_excel_imports SET '+','.join(k+'=?' for k in fields)+' WHERE company_id=? AND import_id=?',
              tuple(record[k] for k in fields)+(r.company_id,identity))
    else:
        r.sql('INSERT INTO portal_excel_imports('+','.join(JOB_COLUMNS)+') VALUES('+','.join('?' for _ in JOB_COLUMNS)+')',tuple(record[k] for k in JOB_COLUMNS))
    # Persist preview provenance with the first write, without writing at preview.
    r.audit(importer.u,'import_preview_created',identity,actor_kind=importer.actor_kind())
    r.audit(importer.u,'import_applied' if status=='applied' else 'import_failed',identity,actor_kind=importer.actor_kind())
    return import_result(importer,identity)

def apply_import(importer,body):
    require_import(importer.s)
    if set(body)-{'company_id','import_id','preview_token','file_b64','original_filename','mime_type','request_id'}:raise ValueError('Неизвестные параметры apply')
    claims=importer.verify(body.get('preview_token'));payload=decode_file(body)
    validate_upload(body.get('original_filename','PORTAL_template.xlsx'),body.get('mime_type',XLSX_MIME),payload,'import_template_xlsx')
    parsed=parse_template(payload)
    if body.get('import_id')!=claims['import_id'] or parsed['checksum_sha256']!=claims['checksum']:raise ValueError('Файл/ID не соответствует preview')
    old=job(importer,claims['import_id'])
    if old and old['status']=='applied':return public_job(old)
    plan=importer.plan(parsed,importer.state())
    if claims['snapshot']!=plan['snapshot_sha256'] or claims['plan']!=digest(plan):raise ValueError('Справочники изменились; повторите preview')
    if not plan['can_apply']:
        errors=[dict(sheet=row['sheet'],row=row['row'],codes=row['errors']) for row in plan['rows'] if row['errors']]
        return _save_outcome(importer,claims,plan,'failed',dict(new=0,updated=0,unchanged=0,rows=[]),errors,old)
    importer.r.sql('SAVEPOINT portal_excel_apply')
    try:
        mappings=[];refs={}
        for row in plan['rows']:
            identity=_apply_row(importer,row,refs)
            if identity is not None:mappings.append(dict(sheet=row['sheet'],row=row['row'],id=identity))
        counts=dict(new=plan['summary']['new'],updated=plan['summary']['update'],unchanged=plan['summary']['unchanged'],rows=mappings)
        result=_save_outcome(importer,claims,plan,'applied',counts,[],old)
        importer.r.sql('RELEASE SAVEPOINT portal_excel_apply')
        return result
    except Exception:
        importer.r.sql('ROLLBACK TO SAVEPOINT portal_excel_apply');importer.r.sql('RELEASE SAVEPOINT portal_excel_apply')
        LOG.info(canonical(dict(event='import_failed',company_id=importer.r.company_id,actor_id=importer.u['id'],import_id=claims['import_id'],code='apply_failed')))
        # Record the failure only after all catalog mutations have been rolled back.
        return _save_outcome(importer,claims,plan,'failed',dict(new=0,updated=0,unchanged=0,rows=[]),[dict(code='apply_failed')],old)
