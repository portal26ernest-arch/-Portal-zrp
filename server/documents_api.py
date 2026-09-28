"""Additive v3 Documents routes, preserving legacy payroll response fields."""
import hashlib
import json
from document_domain import Documents, decode_file, XLSX_MIME
from report_xlsx import payroll_xlsx
from portal_excel_workbook import deterministic_zip

DOCUMENT_ACTIONS={'documents','document-file','document-metadata','document-upload','document-archive','document-generate'}

def route(service,storage,action,method,values):
    docs=Documents(service,storage)
    if method=='GET':
        if action=='documents':return docs.rows(values)
        identity=values.get('id',[None])[0]
        if action=='document-file':return docs.download(identity)
        if action=='document-metadata':return docs.public(docs.get(identity))
        raise ValueError('Метод не поддерживается')
    if set(values)-{'request_id','company_id','action','id','document_type','title','original_filename','mime_type',
                    'file_b64','category','client_id','employee_id','invoice_id','payroll_period_id','previous_id',
                    'document_date','metadata','period_start','period_end'}:
        raise ValueError('Неизвестные параметры документа')
    operation=values.get('action') or {'document-upload':'upload','document-archive':'archive'}.get(action,'generate')
    if operation=='archive':return docs.archive(values.get('id'))
    if operation=='upload':return docs.register(decode_file(values),values)
    if operation!='generate' or values.get('document_type') not in ('payroll','payroll_xlsx'):
        raise ValueError('Для генерации поддерживается payroll XLSX; другие типы можно загрузить')
    service.need('documents.manage');service.need('payroll.all')
    start,end=service.payroll_bounds(values.get('period_start'),values.get('period_end'))
    period=next((p for p in service.r.list('payroll_periods') if p['period_start']==start and p['period_end']==end and p['status']=='closed'),None)
    if not period:raise ValueError('Сначала закройте расчётный период')
    snapshot_raw=json.dumps(period['snapshot'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    payload=deterministic_zip(payroll_xlsx(period['snapshot']))
    body=dict(values,document_type='payroll_xlsx',category='payroll',payroll_period_id=period['id'],
              title=values.get('title') or f'Расчётный период {start} — {end}',original_filename=f'PORTAL_payroll_{start}_{end}.xlsx',
              mime_type=XLSX_MIME,metadata=dict(period_start=start,period_end=end,snapshot_sha256=hashlib.sha256(snapshot_raw).hexdigest()))
    return docs.register(payload,body,'generated')
