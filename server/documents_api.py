"""Additive v3 Documents routes, preserving legacy payroll response fields."""
import hashlib
import json
import base64
from document_domain import Documents, decode_file, XLSX_MIME
from report_xlsx import payroll_xlsx
from portal_excel_workbook import deterministic_zip
from financial_xlsx import invoice_xlsx, payroll_slip_xlsx

DOCUMENT_ACTIONS={'documents','document-file','document-metadata','document-history','document-upload','document-archive','document-generate'}
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
    payload=workbook(data);filename=f'PORTAL_template_v{TEMPLATE_VERSION}.xlsx'
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
        if action=='document-history':return docs.history(identity)
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
    if values.get('document_type') in ('invoice_pdf','invoice_xlsx'):
        service.need('invoices.read')
        invoice=service.invoice_current(values.get('invoice_id'))
        from excel_template import catalog, SHEETS
        catalogs=catalog(service,company)
        company_sheet,_,clients_sheet,_=SHEETS.keys()
        client=next((row for row in catalogs[clients_sheet] if row['id']==invoice['client_id']),None)
        if client is None: raise PermissionError('Клиент недоступен')
        company_profile=catalogs[company_sheet][0]
        invoice=dict(invoice,lines=[dict(line) for line in invoice.get('snapshot',{}).get('lines',invoice.get('lines',[]))])
        if not invoice['lines'] or any(line.get('operation_name') is None or
            any(line.get(key) is None for key in ('quantity','client_rate','amount')) for line in invoice['lines']):
            raise ValueError('Для счёта отсутствуют подтверждённые строки операции')
        operations={line.get('operation_id'):line.get('operation_name') for line in invoice['lines'] if line.get('operation_id')}
        if values.get('document_type')=='invoice_xlsx':
            payload=deterministic_zip(invoice_xlsx(company_profile,client,invoice));extension='.xlsx';mime=XLSX_MIME
        else:
            from pdf_documents import invoice_pdf
            payload=invoice_pdf(company_profile,client,invoice,operations);extension='.pdf';mime='application/pdf'
        identity=str(invoice['id'])
        body=dict(values,document_type=values['document_type'],category='invoice',invoice_id=identity,
            client_id=invoice['client_id'],title=f"Счёт на оплату · {client.get('name','Клиент')}",
            original_filename=f'PORTAL_invoice_{identity[:24]}{extension}',mime_type=mime,
            metadata={'notes':'Invoice snapshot '+identity,'snapshot_sha256':hashlib.sha256(json.dumps(invoice.get('snapshot',invoice),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()})
        return docs.register(payload,body,'generated')
    if values.get('document_type') in ('payroll_slip_pdf','payroll_slip_xlsx'):
        service.need('payroll.all');service.need('payroll.settlement.read')
        period=service.closed_payroll_period(values.get('payroll_period_id'))
        employee_id=service.payroll_employee_id(values)
        employee=next((dict(row,employee_id=employee_id) for row in period['snapshot']['employees']
            if row.get('employee_id') is not None and service.r.payroll_employee(row['employee_id'],legacy=True)['employee_id']==employee_id),None)
        if not employee: raise ValueError('Сотрудник отсутствует в закрытом снимке расчётного периода')
        # Payslips are issued from the immutable close snapshot; later settlements cannot rewrite history.
        summary={'balance':employee['salary'],'accrued':employee['salary'],'paid':0,'adjustment':0}
        if values['document_type']=='payroll_slip_xlsx':
            summary=dict(summary,balance=employee['salary'])
            issue_date=str(period.get('closed_at') or period['period_end'])[:10]
            payload=deterministic_zip(payroll_slip_xlsx(company or {},period,employee,summary,issue_date));extension='.xlsx';mime=XLSX_MIME
        else:
            from pdf_documents import payroll_slip_pdf
            payload=payroll_slip_pdf(company or {},period,employee,dict(summary,balance=employee['salary']),str(period.get('closed_at') or period['period_end'])[:10]);extension='.pdf';mime='application/pdf'
        snapshot_raw=json.dumps(period['snapshot'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
        body=dict(values,document_type=values['document_type'],category='payroll',employee_id=employee_id,
            payroll_period_id=period['id'],title=f"Расчётный лист · {employee['display_name']}",
            original_filename=f'PORTAL_payroll_slip_{period["period_start"]}_{employee_id}{extension}',
            mime_type=mime,metadata={'period_start':period['period_start'],'period_end':period['period_end'],
                'snapshot_sha256':hashlib.sha256(snapshot_raw).hexdigest()})
        return docs.register(payload,body,'generated')
    if values.get('document_type') not in ('payroll','payroll_xlsx'):
        raise ValueError('Для генерации доступен PDF счёта или расчётного листа из закрытого периода')
    service.need('payroll.all')
    start,end=service.payroll_bounds(values.get('period_start'),values.get('period_end'))
    period=next((p for p in service.r.list('payroll_periods') if p['period_start']==start and p['period_end']==end and p['status']=='closed'),None)
    if not period:raise ValueError('Сначала закройте расчётный период')
    snapshot_raw=json.dumps(period['snapshot'],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    settlements=service.settlement_summary(period,service.r.payroll_settlements(period['id']))
    payload=deterministic_zip(payroll_xlsx(period['snapshot'],settlements))
    body=dict(values,document_type='payroll_xlsx',category='payroll',payroll_period_id=period['id'],
              title=values.get('title') or f'Расчётный период {start} — {end}',original_filename=f'PORTAL_payroll_{start}_{end}.xlsx',
              mime_type=XLSX_MIME,metadata=dict(period_start=start,period_end=end,snapshot_sha256=hashlib.sha256(snapshot_raw).hexdigest()))
    return docs.register(payload,body,'generated')
