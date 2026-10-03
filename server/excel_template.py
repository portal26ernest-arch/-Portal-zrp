"""Canonical Excel 2.0 workbook and explicit company projection; no credentials exported."""
from io import BytesIO
from decimal import Decimal
from zipfile import ZipFile
from xml.sax.saxutils import escape
from report_xlsx import XML, _cell, _column
from portal_excel_workbook import deterministic_zip
from document_domain import XLSX_MIME

TEMPLATE_VERSION='2.0'
REQUISITES=('legal_name','inn','kpp','ogrn','legal_address','settlement_account','bank_name','bik','correspondent_account','phone','email','tax_info')
ROLE_LABELS={'admin':'Управляющий','director':'Директор','manager':'Менеджер','accountant':'Бухгалтер','shift':'Старший смены','packer':'Упаковщик'}
LABELS={'legal_name':'Юридическое наименование','inn':'ИНН','kpp':'КПП','ogrn':'ОГРН','legal_address':'Юридический адрес',
        'settlement_account':'Расчётный счёт','bank_name':'Банк','bik':'БИК','correspondent_account':'Корреспондентский счёт',
        'phone':'Телефон','email':'Email','tax_info':'Налогообложение','director':'Руководитель','contact_person':'Контактное лицо'}
SHEETS={
 'Компания':[('name','Название компании (не менять)')]+[(k,LABELS[k]) for k in REQUISITES]+[('director',LABELS['director']),('company_id','ID компании · авто')],
 'Сотрудники':[('full_name','ФИО'),('profile_username','Логин'),('role','Роль'),('active','Активен'),
               ('initial_pin','Пароль нового доступа (4–128 символов)'),('employee_ref','Ключ строки · авто'),('employee_id','ID сотрудника · авто'),('user_id','ID доступа · авто')],
 'Клиенты':[('name','Название клиента'),('active','Активен')]+[(k,LABELS[k]) for k in REQUISITES]+
            [('contact_person',LABELS['contact_person']),('client_ref','Ключ клиента · авто'),('client_id','ID клиента · авто')],
 'Операции_Тарифы':[('client_name','Клиент'),('name','Операция'),('employee_rate','Ставка сотруднику, ₽'),('client_rate','Цена клиенту, ₽'),
                    ('active','Активна'),('effective_from','Дата начала новой ставки — необязательно'),('effective_to','Окончание · авто'),
                    ('client_ref','Ключ клиента · авто'),('client_id','ID клиента · авто'),('operation_id','ID операции · авто')],
 'Материалы':[('name','Материал'),('unit','Ед. изм.'),('unit_cost','Стоимость единицы, ₽'),('min_stock','Минимальный остаток'),
              ('active','Активен'),('material_ref','Ключ материала · авто'),('material_id','ID материала · авто')],
 'Приход_материалов':[('material_name','Материал'),('quantity','Количество прихода'),('unit_cost','Стоимость единицы, ₽'),('note','Комментарий'),
                      ('material_ref','Ключ материала · авто'),('material_id','ID материала · авто')],
 'Нормы_материалов':[('client_name','Клиент'),('operation_name','Операция'),('material_name','Материал'),('qty_per_unit','Расход на 1 ед.'),
                     ('active','Активна'),('operation_id','ID операции · авто'),('material_id','ID материала · авто'),('norm_id','ID нормы · авто')],
 'Выработка':[('employee_name','Сотрудник'),('client_name','Клиент'),('operation_name','Операция'),('quantity','Количество'),('product','Товар / комментарий'),
              ('employee_id','ID сотрудника · авто'),('client_id','ID клиента · авто'),('operation_id','ID операции · авто')],
}
TECHNICAL_KEYS={'company_id','employee_ref','employee_id','user_id','client_ref','client_id','operation_id','material_ref','material_id','norm_id','effective_to'}

def display_value(key,value):
    if key=='active' and value in (0,1,False,True):return 'Да' if bool(value) else 'Нет'
    if key=='role' and value in ROLE_LABELS:return ROLE_LABELS[value]
    return value

def validation_xml(columns):
    rules=[]
    for index,(key,_) in enumerate(columns,1):
        if key=='active':options='Да,Нет'
        elif key=='role':options=','.join(ROLE_LABELS.values())
        else:continue
        column=_column(index)
        rules.append(f'<dataValidation type="list" allowBlank="1" showErrorMessage="1" sqref="{column}4:{column}10003"><formula1>"{escape(options)}"</formula1></dataValidation>')
    return '' if not rules else '<dataValidations count="'+str(len(rules))+'">'+''.join(rules)+'</dataValidations>'

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
    for source in r.employee_catalog():
        canonical_id=int(source['employee_id'])
        accounts=[u for u in users if u.get('employee_id')==canonical_id]
        employee=dict(employee_ref='employee:'+str(canonical_id),employee_id=canonical_id,
                      full_name=source['full_name'],profile_username=source['username'] or '')
        if len(accounts)==1:employee.update(user_id=accounts[0]['id'],role=accounts[0]['role'],active=accounts[0]['active'])
        employees.append(employee)
    client_names={row['client_id']:row['name'] for row in clients}
    operations=[]
    for op in r.catalog('operations'):
        try:tariff=service.tariff(op['id'])
        except ValueError:tariff={}
        operations.append(dict(operation_id=op['id'],client_id=op['client_id'],client_ref='client:'+str(op['client_id']),
          client_name=client_names.get(op['client_id'],''),name=op['name'],active=op['active'],
          employee_rate=format(Decimal(tariff.get('employee_rate') or 0)/100,'.2f'),
          client_rate='' if tariff.get('client_rate') is None else format(Decimal(tariff['client_rate'])/100,'.2f'),effective_from=tariff.get('effective_from',''),effective_to=''))
    materials=[]
    material_source=r.catalog('materials') if r.has_table('materials') and 'company_id' in r.columns('materials') else []
    for row in material_source:
        materials.append(dict(material_ref='material:'+str(row['id']),material_id=row['id'],name=row['name'],unit=row.get('unit') or '',
          unit_cost=row.get('unit_cost') if row.get('unit_cost') is not None else '',min_stock=row.get('min_stock') if row.get('min_stock') is not None else '',active=row.get('active',1)))
    material_names={row['material_id']:row['name'] for row in materials}
    operation_names={row['operation_id']:row for row in operations}
    norms=[]
    norm_source=r.catalog('norms') if r.has_table('operation_material_norms') and {'company_id','id'}.issubset(r.columns('operation_material_norms')) else []
    for row in norm_source:
        op=operation_names.get(row['operation_id'],{})
        norms.append(dict(norm_id=row['id'],operation_id=row['operation_id'],material_id=row['material_id'],
          client_name=op.get('client_name',''),operation_name=op.get('name',''),material_name=material_names.get(row['material_id'],''),
          qty_per_unit=row.get('qty_per_unit') if row.get('qty_per_unit') is not None else '',active=row.get('active',1)))
    return {'Компания':[profile],'Сотрудники':employees,'Клиенты':sorted(clients,key=lambda c:c['client_id']),
            'Операции_Тарифы':sorted(operations,key=lambda o:o['operation_id']),
            'Материалы':sorted(materials,key=lambda m:m['material_id']),'Приход_материалов':[],
            'Нормы_материалов':sorted(norms,key=lambda n:n['norm_id']),'Выработка':[]}

def workbook(data=None):
    data=data or {};names=list(SHEETS);out=BytesIO();sheet_count=len(names);styles_id=sheet_count+1
    with ZipFile(out,'w') as book:
        book.writestr('[Content_Types].xml',XML+'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'+''.join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,sheet_count+1))+'</Types>')
        book.writestr('_rels/.rels',XML+'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        book.writestr('xl/workbook.xml',XML+'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i,name in enumerate(names,1))+'</sheets></workbook>')
        book.writestr('xl/_rels/workbook.xml.rels',XML+'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,sheet_count+1))+f'<Relationship Id="rId{styles_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
        book.writestr('xl/styles.xml',XML+'''<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="3"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font><font><sz val="9"/><color rgb="FF64748B"/><name val="Consolas"/></font></fonts>
<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF17365D"/><bgColor indexed="64"/></patternFill></fill></fills>
<borders count="1"><border/></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3"><xf numFmtId="49" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFill="1" applyFont="1"><alignment wrapText="1" vertical="center"/></xf><xf numFmtId="49" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>''')
        for i,name in enumerate(names,1):
            columns=SHEETS[name];rows=[['PORTAL_TEMPLATE_VERSION',TEMPLATE_VERSION],[(key,2) for key,_ in columns],[(label,1) for _,label in columns]]
            for source in data.get(name,[]):rows.append([display_value(key,source.get(key,'')) if source.get(key) is not None else '' for key,_ in columns])
            body=''.join('<row r="'+str(n)+'"'+(' hidden="1"' if n in (1,2) else ' ht="40" customHeight="1"' if n==3 else '')+'>'+''.join(_cell(f'{_column(c)}{n}',value) for c,value in enumerate(row,1))+'</row>' for n,row in enumerate(rows,1))
            cols=''.join(f'<col min="{c}" max="{c}" width="{2 if key in TECHNICAL_KEYS else 36 if key in ("name","full_name","legal_name","legal_address","effective_from","product") else 24}" customWidth="1"'+(' hidden="1"' if key in TECHNICAL_KEYS else '')+'/>' for c,(key,_) in enumerate(columns,1))
            sheet=XML+'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="3" topLeftCell="A4" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>'+cols+'</cols><sheetData>'+body+'</sheetData><autoFilter ref="A3:'+_column(len(columns))+str(max(3,len(rows)))+'"/>'+validation_xml(columns)+'</worksheet>'
            book.writestr(f'xl/worksheets/sheet{i}.xml',sheet)
    return deterministic_zip(out.getvalue())

def template_xlsx(company=None):
    return workbook({'Компания':[{'company_id':(company or {}).get('id',''),'name':(company or {}).get('name','')}]}) if company else workbook()
