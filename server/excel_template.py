"""Canonical v1 workbook and explicit catalog projection; no credentials exported."""
from io import BytesIO
from decimal import Decimal
from zipfile import ZipFile
from xml.sax.saxutils import escape
from report_xlsx import XML, _cell, _column
from portal_excel_workbook import deterministic_zip
from document_domain import XLSX_MIME

TEMPLATE_VERSION='1.0'
REQUISITES=('legal_name','inn','kpp','ogrn','legal_address','settlement_account','bank_name','bik','correspondent_account','phone','email','tax_info')
LABELS={'legal_name':'Юридическое наименование','inn':'ИНН','kpp':'КПП','ogrn':'ОГРН','legal_address':'Юридический адрес',
        'settlement_account':'Расчётный счёт','bank_name':'Банк','bik':'БИК','correspondent_account':'Корреспондентский счёт',
        'phone':'Телефон','email':'Email','tax_info':'Налогообложение','director':'Руководитель','contact_person':'Контактное лицо'}
SHEETS={
 'Компания':[('company_id','ID компании (не менять)'),('name','Название компании (не менять)')]+[(k,LABELS[k]) for k in REQUISITES]+[('director',LABELS['director'])],
 'Сотрудники':[('employee_ref','Ключ строки сотрудника'),('employee_id','ID сотрудника PORTAL'),('full_name','ФИО'),
               ('profile_username','Профиль: имя пользователя'),('user_id','ID существующего доступа'),('role','Роль доступа'),('active','Доступ активен (1/0)')],
 'Клиенты':[('client_ref','Ключ клиента в книге'),('client_id','ID клиента PORTAL'),('name','Название клиента'),('active','Активен (1/0)')]+
            [(k,LABELS[k]) for k in REQUISITES]+[('contact_person',LABELS['contact_person'])],
 'Операции_Тарифы':[('client_ref','Ключ клиента в книге'),('client_id','ID клиента PORTAL'),('operation_id','ID операции PORTAL'),
                    ('name','Операция'),('employee_rate','Ставка сотруднику, ₽'),('client_rate','Цена клиенту, ₽'),('active','Активна (1/0)'),
                    ('effective_from','Начало действия, UTC ISO8601'),('effective_to','Окончание (оставить пустым)')],
}

def table_rows(repo,table,fields):
    if not repo.has_table(table):return []
    supported=[field for field in fields if field in repo.columns(table)]
    if not supported:return []
    return [dict(zip(supported,row)) for row in repo.sql('SELECT '+','.join(supported)+' FROM '+table+' WHERE company_id=?',(repo.company_id,)).fetchall()]

def catalog(service,company=None):
    r=service.r
    profile={'company_id':r.company_id,'name':(company or {}).get('name','')}
    company_rows=table_rows(r,'portal_company_requisites',('id',)+REQUISITES+('director',))
    if company_rows:profile.update({k:v for k,v in company_rows[0].items() if k!='id'})
    clients=[dict(row,client_ref='client:'+str(row['id']),client_id=row['id']) for row in r.catalog('clients')]
    requisites={row['client_id']:row for row in table_rows(r,'portal_client_requisites',('client_id',)+REQUISITES+('contact_person',))}
    for row in clients:row.update({k:v for k,v in requisites.get(row['id'],{}).items() if k!='client_id'})
    employees=[];users=r.catalog('users')
    if r.has_table('payroll_employee_identities'):
        mapped=r.sql('''SELECT i.employee_id,i.legacy_employee_id,e.full_name,e.username
            FROM payroll_employee_identities i JOIN employees e ON e.company_id=i.company_id AND e.telegram_id=i.legacy_employee_id
            WHERE i.company_id=? ORDER BY i.employee_id''',(r.company_id,)).fetchall()
        for eid,legacy,name,username in mapped:
            accounts=[u for u in users if u.get('telegram_id')==legacy]
            employee=dict(employee_ref='employee:'+str(eid),employee_id=eid,full_name=name,profile_username=username or '')
            if len(accounts)==1:employee.update(user_id=accounts[0]['id'],role=accounts[0]['role'],active=accounts[0]['active'])
            employees.append(employee)
    operations=[]
    for op in r.catalog('operations'):
        try:tariff=service.tariff(op['id'])
        except ValueError:tariff={}
        operations.append(dict(operation_id=op['id'],client_id=op['client_id'],client_ref='client:'+str(op['client_id']),name=op['name'],active=op['active'],
          employee_rate=format(Decimal(tariff.get('employee_rate') or 0)/100,'.2f'),
          client_rate='' if tariff.get('client_rate') is None else format(Decimal(tariff['client_rate'])/100,'.2f'),effective_from=tariff.get('effective_from',''),effective_to=''))
    return {'Компания':[profile],'Сотрудники':employees,'Клиенты':sorted(clients,key=lambda c:c['client_id']),
            'Операции_Тарифы':sorted(operations,key=lambda o:o['operation_id'])}

def workbook(data=None):
    data=data or {};names=list(SHEETS);out=BytesIO()
    with ZipFile(out,'w') as book:
        book.writestr('[Content_Types].xml',XML+'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'+''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,5))+'</Types>')
        book.writestr('_rels/.rels',XML+'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        book.writestr('xl/workbook.xml',XML+'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i,name in enumerate(names,1))+'</sheets></workbook>')
        book.writestr('xl/_rels/workbook.xml.rels',XML+'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,5))+'<Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        book.writestr('xl/styles.xml',XML+'''<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="3"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font><font><sz val="9"/><color rgb="FF64748B"/><name val="Consolas"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF17365D"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3"><xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1"><alignment wrapText="1" vertical="center"/></xf><xf numFmtId="49" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>''')
        for i,name in enumerate(names,1):
            columns=SHEETS[name];rows=[['PORTAL_TEMPLATE_VERSION',TEMPLATE_VERSION],[(key,2) for key,_ in columns],[(label,1) for _,label in columns]]
            for source in data.get(name,[]):rows.append([source.get(key,'') if source.get(key) is not None else '' for key,_ in columns])
            body=''.join('<row r="'+str(n)+'"'+(' ht="40" customHeight="1"' if n==3 else '')+'>'+''.join(_cell(f'{_column(c)}{n}',value) for c,value in enumerate(row,1))+'</row>' for n,row in enumerate(rows,1))
            cols=''.join(f'<col min="{c}" max="{c}" width="{36 if key in ("name","full_name","legal_name","legal_address","effective_from") else 24}" customWidth="1"/>' for c,(key,_) in enumerate(columns,1))
            sheet=XML+'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="3" topLeftCell="A4" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>'+cols+'</cols><sheetData>'+body+'</sheetData><autoFilter ref="A3:'+_column(len(columns))+str(max(3,len(rows)))+'"/></worksheet>'
            book.writestr(f'xl/worksheets/sheet{i}.xml',sheet)
    return deterministic_zip(out.getvalue())

def template_xlsx(company=None):
    return workbook({'Компания':[{'company_id':(company or {}).get('id',''),'name':(company or {}).get('name','')}]}) if company else workbook()
