"""Bounded OOXML parsing. No formula calculation, macros or external resources."""
from contextlib import contextmanager
from io import BytesIO
from pathlib import PurePosixPath
import re
import hashlib
from datetime import datetime,timedelta
from decimal import Decimal,InvalidOperation
from zipfile import ZipFile, BadZipFile, ZipInfo, ZIP_DEFLATED
from xml.etree import ElementTree as ET

NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL='http://schemas.openxmlformats.org/package/2006/relationships'
DOCREL='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
MAX_BYTES=10*1024*1024
MAX_EXPANDED=40*1024*1024
MAX_ROWS=2000
MAX_CELLS=50000
MAX_TEXT=1000

def deterministic_zip(payload):
    out=BytesIO()
    with ZipFile(BytesIO(payload)) as source, ZipFile(out,'w') as target:
        for name in source.namelist():
            info=ZipInfo(name,(2000,1,1,0,0,0));info.compress_type=ZIP_DEFLATED
            target.writestr(info,source.read(name))
    return out.getvalue()

def xml(raw):
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('DTD/ENTITY запрещены')
    try:return ET.fromstring(raw)
    except ET.ParseError:raise ValueError('Повреждён XML книги') from None

@contextmanager
def archive_xlsx(payload):
    if not isinstance(payload,bytes) or not 0<len(payload)<=MAX_BYTES:raise ValueError('Размер XLSX превышает лимит')
    try:
        with ZipFile(BytesIO(payload)) as book:
            infos=book.infolist();names=[i.filename for i in infos]
            if len(infos)>256 or len(names)!=len(set(names)) or sum(i.file_size for i in infos)>MAX_EXPANDED:raise ValueError('Превышен лимит XLSX/ZIP')
            for item in infos:
                name=item.filename.lower();path=PurePosixPath(item.filename)
                if path.is_absolute() or '..' in path.parts or '\\' in name or item.flag_bits&1:raise ValueError('Небезопасный ZIP путь/шифрование')
                if item.file_size>MAX_EXPANDED or item.file_size>max(1024,item.compress_size)*200:raise ValueError('Превышен лимит распаковки')
                if any(part in name for part in ('vbaproject','activex','embeddings/','externallinks/')):raise ValueError('Макросы/внешние объекты запрещены')
                if name.endswith(('.xml','.rels')):
                    root=xml(book.read(item))
                    if name.endswith('.rels') and any(node.get('TargetMode')=='External' for node in root):raise ValueError('Внешние ссылки запрещены')
            if not {'[Content_Types].xml','xl/workbook.xml','xl/_rels/workbook.xml.rels'}.issubset(names):raise ValueError('Повреждён XLSX')
            types=book.read('[Content_Types].xml').lower()
            if b'macroenabled' in types or b'vba' in types:raise ValueError('Макросы запрещены')
            yield book
    except (BadZipFile,KeyError,RuntimeError,NotImplementedError,EOFError):raise ValueError('Некорректная книга XLSX') from None

def inspect_xlsx(payload):
    with archive_xlsx(payload) as book:
        root=xml(book.read('xl/workbook.xml'))
        if root.tag!='{'+NS+'}workbook' or not root.findall('{'+NS+'}sheets/{'+NS+'}sheet'):raise ValueError('Некорректная структура книги')
        for item in book.infolist():
            if item.filename.startswith('xl/worksheets/') and item.filename.endswith('.xml'):
                root=xml(book.read(item));rows=root.findall('{'+NS+'}sheetData/{'+NS+'}row')
                if len(rows)>MAX_ROWS or sum(len(row) for row in rows)>MAX_CELLS:raise ValueError('Превышен лимит строк/ячеек')
    return True

def parse_template(payload):
    from excel_template import SHEETS,TEMPLATE_VERSION
    with archive_xlsx(payload) as book:
        workbook=xml(book.read('xl/workbook.xml'))
        sheets=workbook.findall('{'+NS+'}sheets/{'+NS+'}sheet')
        if [s.get('name') for s in sheets]!=list(SHEETS):raise ValueError('Неверный набор/порядок листов')
        relationships={r.get('Id'):r for r in xml(book.read('xl/_rels/workbook.xml.rels'))}
        shared=[]
        if 'xl/sharedStrings.xml' in book.namelist():
            for item in xml(book.read('xl/sharedStrings.xml')).findall('{'+NS+'}si'):
                value=''.join(node.text or '' for node in item.iter('{'+NS+'}t'))
                if len(value)>MAX_TEXT or len(shared)>=MAX_CELLS:raise ValueError('Превышен лимит sharedStrings')
                shared.append(value)
        date_styles=set()
        if 'xl/styles.xml' in book.namelist():
            styles=xml(book.read('xl/styles.xml'))
            formats={int(n.get('numFmtId')):n.get('formatCode','') for n in styles.findall('{'+NS+'}numFmts/{'+NS+'}numFmt')}
            for i,node in enumerate(styles.findall('{'+NS+'}cellXfs/{'+NS+'}xf')):
                fmt=int(node.get('numFmtId','0'))
                if fmt in set(range(14,23))|{45,46,47} or re.search(r'[yd]',re.sub(r'"[^"]*"|\[[^]]*\]','',formats.get(fmt,'')).lower()):date_styles.add(i)
        props=workbook.find('{'+NS+'}workbookPr');use_1904=props is not None and props.get('date1904') in ('1','true')
        result={};total_cells=0;total_rows=0
        for sheet in sheets:
            name=sheet.get('name');link=relationships.get(sheet.get('{'+DOCREL+'}id'))
            if link is None or not link.get('Type','').endswith('/worksheet'):raise ValueError('Некорректная связь листа')
            target=link.get('Target','')
            path=target.lstrip('/') if target.startswith('/xl/') else 'xl/'+target
            if '..' in PurePosixPath(path).parts or '\\' in path or not path.startswith('xl/worksheets/'):raise ValueError('Некорректный путь листа')
            grid={};rows=xml(book.read(path)).findall('{'+NS+'}sheetData/{'+NS+'}row')
            if len(rows)>MAX_ROWS+3:raise ValueError('Превышен лимит строк')
            for row in rows:
                try:rno=int(row.get('r','0'))
                except ValueError:raise ValueError('Некорректный номер строки') from None
                if not 1<=rno<=MAX_ROWS+3 or rno in grid:raise ValueError('Некорректный/повторный номер строки')
                values={};grid[rno]=values
                for cell in row.findall('{'+NS+'}c'):
                    total_cells+=1
                    if total_cells>MAX_CELLS:raise ValueError('Превышен лимит ячеек')
                    match=re.fullmatch(r'([A-Z]{1,2})([1-9][0-9]*)',cell.get('r',''))
                    if not match or int(match[2])!=rno:raise ValueError('Некорректная координата ячейки')
                    col=0
                    for ch in match[1]:col=col*26+ord(ch)-64
                    if not 1<=col<=len(SHEETS[name]) or col in values:raise ValueError('Лишние/повторные столбцы')
                    if cell.find('{'+NS+'}f') is not None:raise ValueError('Формулы в импортируемой книге запрещены')
                    kind=cell.get('t','n');node=cell.find('{'+NS+'}v');value=node.text or '' if node is not None else ''
                    if kind=='inlineStr':value=''.join(n.text or '' for n in cell.iter('{'+NS+'}t'))
                    elif kind=='s':
                        try:index=int(value);value=shared[index] if index>=0 else None
                        except (ValueError,IndexError):raise ValueError('Некорректная shared string') from None
                        if value is None:raise ValueError('Некорректная shared string')
                    elif kind not in ('n','str','b','d'):raise ValueError('Недопустимый тип ячейки')
                    if len(value)>MAX_TEXT:raise ValueError('Текст ячейки слишком длинный')
                    if kind=='n' and value and int(cell.get('s','0')) in date_styles:
                        try:
                            serial=Decimal(value)
                            if not serial.is_finite() or not 0<=serial<=2958465 or (not use_1904 and 60<=serial<61):raise ValueError()
                            epoch=datetime(1904,1,1) if use_1904 else datetime(1899,12,30 if serial>=61 else 31)
                            value=(epoch+timedelta(seconds=float(serial*86400))).isoformat(timespec='microseconds')
                        except (ValueError,InvalidOperation,OverflowError):raise ValueError('Некорректная Excel-дата') from None
                    values[col]=value
            if grid.get(1,{}).get(1)!='PORTAL_TEMPLATE_VERSION' or grid.get(1,{}).get(2)!=TEMPLATE_VERSION:raise ValueError('Неподдерживаемая версия шаблона')
            keys=[key for key,_ in SHEETS[name]]
            if [grid.get(2,{}).get(i+1) for i in range(len(keys))]!=keys:raise ValueError('Неверные/недостающие машинные столбцы: '+name)
            if [grid.get(3,{}).get(i+1) for i in range(len(keys))]!=[label for _,label in SHEETS[name]]:raise ValueError('Неверные заголовки: '+name)
            parsed=[]
            for number,values in sorted(grid.items()):
                if number<=3 or not any(v.strip() for v in values.values()):continue
                total_rows+=1
                if total_rows>MAX_ROWS:raise ValueError('Превышен общий лимит строк')
                parsed.append(dict(zip(keys,[values.get(i+1,'') for i in range(len(keys))]),_row=number))
            result[name]=parsed
    return dict(template_version=TEMPLATE_VERSION,sheets=list(SHEETS),rows=result,checksum_sha256=hashlib.sha256(payload).hexdigest())
