"""Minimal dependency-free XLSX renderer for immutable PORTAL snapshots."""
from io import BytesIO
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape
import re

XML='<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'

def _column(index):
    name=''
    while index:
        index,rem=divmod(index-1,26);name=chr(65+rem)+name
    return name

def _clean(value):
    return ''.join(ch for ch in str(value) if ch in '\t\n\r' or ord(ch)>=32)

def _cell(ref,value):
    style=0
    if isinstance(value,tuple):value,style=value
    attr=f' s="{style}"' if style else ''
    if isinstance(value,(int,float)) and not isinstance(value,bool):
        return f'<c r="{ref}"{attr}><v>{value}</v></c>'
    text=escape(_clean('' if value is None else value))
    return f'<c r="{ref}" t="inlineStr"{attr}><is><t>{text}</t></is></c>'

def _sheet(rows):
    body=[]
    for rno,row in enumerate(rows,1):
        cells=''.join(_cell(f'{_column(cno)}{rno}',value) for cno,value in enumerate(row,1))
        body.append(f'<row r="{rno}">{cells}</row>')
    return XML+'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join(body)+'</sheetData></worksheet>'

def _safe_sheet(name,used):
    value=re.sub(r'[\\/*?:\[\]]',' ',_clean(name)).strip() or 'Лист'
    value=value[:31];base=value;i=2
    while value.casefold() in used:
        suffix=f' {i}';value=(base[:31-len(suffix)]+suffix);i+=1
    used.add(value.casefold());return value

def _styles():
    return XML+'''<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00"/></numFmts>
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="1"><fill><patternFill patternType="none"/></fill></fills><borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"/></cellXfs>
</styleSheet>'''

def _rub(cents): return (int(cents or 0)/100,1)
def payroll_xlsx(snapshot):
    used=set();sheets=[]
    summary=[
        [('PORTAL · расчётный период',2)],
        ['Период',snapshot['period_start']+' — '+snapshot['period_end']],
        ['Общая выработка',snapshot['total_quantity']],
        ['Начислено, ₽',_rub(snapshot['total_salary'])],
        ['Записей работ',snapshot['work_rows']],
    ]
    sheets.append((_safe_sheet('Сводка',used),summary))
    employees=[[('Сотрудник',2),('Количество',2),('Начислено, ₽',2),('Записей',2)]]
    for row in snapshot.get('employees',[]):
        employees.append([row['display_name'],row['quantity'],_rub(row['salary']),row['work_rows']])
    sheets.append((_safe_sheet('Сотрудники',used),employees))
    details=[[('Дата',2),('Сотрудник',2),('Клиент',2),('Операция',2),('Количество',2),('Ставка, ₽',2),('Начислено, ₽',2)]]
    for row in snapshot.get('details',[]):
        details.append([row['completed_at'],row['display_name'],row['client_name'],row['operation_name'],
                        row['quantity'],_rub(row['employee_rate']),_rub(row['salary'])])
    sheets.append((_safe_sheet('Детализация',used),details))
    for employee in snapshot.get('employees',[]):
        rows=[[('Расчётный лист PORTAL',2)],[('Сотрудник',2),employee['display_name']],
              ['Период',snapshot['period_start']+' — '+snapshot['period_end']],
              ['Выработка',employee['quantity']],['Начислено, ₽',_rub(employee['salary'])],[],
              [('Дата',2),('Клиент',2),('Операция',2),('Количество',2),('Ставка, ₽',2),('Начислено, ₽',2)]]
        for row in snapshot.get('details',[]):
            if row['user_id']==employee['user_id']:
                rows.append([row['completed_at'],row['client_name'],row['operation_name'],row['quantity'],
                             _rub(row['employee_rate']),_rub(row['salary'])])
        sheets.append((_safe_sheet(employee['display_name'],used),rows))
    workbook=XML+'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets>'+''.join(
        f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>' for i,(name,_) in enumerate(sheets,1))+'</sheets></workbook>'
    rels=XML+'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+''.join(
        f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1,len(sheets)+1))+f'<Relationship Id="rId{len(sheets)+1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'
    types=XML+'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'+''.join(
        f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1,len(sheets)+1))+'</Types>'
    root=XML+'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    out=BytesIO()
    with ZipFile(out,'w',ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml',types)
        z.writestr('_rels/.rels',root)
        z.writestr('xl/workbook.xml',workbook)
        z.writestr('xl/_rels/workbook.xml.rels',rels)
        z.writestr('xl/styles.xml',_styles())
        for i,(_,rows) in enumerate(sheets,1):
            z.writestr(f'xl/worksheets/sheet{i}.xml',_sheet(rows))
    return out.getvalue()
