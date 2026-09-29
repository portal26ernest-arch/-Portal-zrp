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

def route(service,storage,action,method,values,company=None):
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
    if operation!='generate': raise ValueError('Неизвестное действие с документом')
    service.need('documents.manage')
    if values.get('document_type')=='invoice_pdf':
        service.need('invoices.read')
        invoice=service.entity('invoices',values.get('invoice_id'))
        from excel_template import catalog, SHEETS
        catalogs=catalog(service,company)
        company_sheet,_,clients_sheet,_=SHEETS.keys()
        client=next((row for row in catalogs[clients_sheet] if row['id']==invoice['client_id']),None)
        if client is None: raise PermissionError('Клиент недоступен')
        company_profile=catalogs[company_sheet][0]
        operations={o['id']:o['name'] for o in service.r.catalog('operations')}
        work_by_id={w['id']:w for w in service.r.list('works')}
        invoice=dict(invoice,lines=[dict(line,operation_id=work_by_id.get(line.get('work_id'),{}).get('operation_id'),
            operation_name=work_by_id.get(line.get('work_id'),{}).get('operation_name')) for line in invoice.get('lines',[])])
        if not invoice['lines'] or any(line.get('operation_name') is None or
            any(line.get(key) is None for key in ('quantity','client_rate','amount')) for line in invoice['lines']):
            raise ValueError('Для счёта отсутствуют подтверждённые строки операции')
        operations.update({line.get('operation_id'):line.get('operation_name') for line in invoice['lines'] if line.get('operation_id')})
        from pdf_documents import invoice_pdf
        payload=invoice_pdf(company_profile,client,invoice,operations)
        identity=str(invoice['id'])
        body=dict(values,document_type='invoice_pdf',category='invoice',invoice_id=identity,
            client_id=invoice['client_id'],title=f"Счёт на оплату · {client.get('name','Клиент')}",
            original_filename=f'PORTAL_invoice_{identity[:24]}.pdf',mime_type='application/pdf',
            metadata={'notes':'Invoice snapshot '+identity})
        return docs.register(payload,body,'generated')
    if values.get('document_type')=='payroll_slip_pdf':
        service.need('payroll.all');service.need('payroll.settlement.read')
        period=service.closed_payroll_period(values.get('payroll_period_id'))
        employee_id=service.payroll_employee_id(values)
        employee=next((row for row in service.settlement_employees(period) if row['employee_id']==employee_id),None)
        if not employee: raise ValueError('Сотрудник отсутствует в закрытом снимке расчётного периода')
        summary=service.settlement_summary(period,service.r.payroll_settlements(period['id'],employee_id),employee_id)['employees'][0]
        from pdf_documents import payroll_slip_pdf
        payload=payroll_slip_pdf(company or {},period,employee,summary,service.clock()[:10])
        body=dict(values,document_type='payroll_slip_pdf',category='payroll',employee_id=employee_id,
            payroll_period_id=period['id'],title=f"Расчётный лист · {employee['display_name']}",
            original_filename=f'PORTAL_payroll_slip_{period["period_start"]}_{employee_id}.pdf',
            mime_type='application/pdf',metadata={'period_start':period['period_start'],'period_end':period['period_end']})
        return docs.register(payload,body,'generated')
    if values.get('document_type') not in ('payroll','payroll_xlsx'):
        raise ValueError('Для генерации доступен PDF счёта или расчётного листа из закрытого периода')
    service.need('payroll.all')
    start,end=service.payroll_bounds(values.get('period_start'),values.get('period_end'))
    period=next((p for p in service.r.list('payroll_periods') if p['period_start']==start and p['period_end']==end and p['status']=='closed'),None)
    if not period:raise ValueError('Сначала закройте расчётный период')
    snapshot_raw=json.dumps(period['snapshot'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    payload=deterministic_zip(payroll_xlsx(period['snapshot']))
    body=dict(values,document_type='payroll_xlsx',category='payroll',payroll_period_id=period['id'],
              title=values.get('title') or f'Расчётный период {start} — {end}',original_filename=f'PORTAL_payroll_{start}_{end}.xlsx',
              mime_type=XLSX_MIME,metadata=dict(period_start=start,period_end=end,snapshot_sha256=hashlib.sha256(snapshot_raw).hexdigest()))
    return docs.register(payload,body,'generated')
