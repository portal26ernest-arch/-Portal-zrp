"""Additive v3 Documents routes, preserving legacy payroll response fields."""
import hashlib
import json
import base64
from document_domain import Documents, decode_file, XLSX_MIME
from report_xlsx import payroll_xlsx
from portal_excel_workbook import deterministic_zip

DOCUMENT_ACTIONS={'documents','document-file','document-metadata','document-upload','document-archive','document-generate'}
TEMPLATE_ACTIONS={'document-template','document-template-blank','document-template-info'}

def require_import(service):
    for permission in ('imports.manage','users.manage','clients.manage','rates.employee','rates.client','company.settings','documents.manage','documents.read'):
        service.need(permission)
    if service.u['role'] not in ('admin','director') and not service.u.get('technical_owner'):
        raise PermissionError('Импорт справочников выполняет директор или администратор компании')

def template_route(service,storage,action,method,values,company):
    from excel_template import SHEETS,TEMPLATE_VERSION,catalog,workbook
    service.need('documents.read')
    if action=='document-template-info':return {'template_version':TEMPLATE_VERSION,'sheets':list(SHEETS),'mapping':{n:[{'key':k,'header':h} for k,h in cols] for n,cols in SHEETS.items()}}
    if action=='document-template':require_import(service)
    data=catalog(service,company) if action=='document-template' else {}
    payload=workbook(data);filename='PORTAL_template_v1.xlsx'
    if method=='POST':
        return Documents(service,storage).register(payload,dict(values,document_type='import_template_xlsx',original_filename=filename,mime_type=XLSX_MIME,
                 title='Стандартный шаблон PORTAL',metadata={'template_version':TEMPLATE_VERSION}),'generated')
    return dict(filename=filename,mime_type=XLSX_MIME,template_version=TEMPLATE_VERSION,file_b64=base64.b64encode(payload).decode())

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
