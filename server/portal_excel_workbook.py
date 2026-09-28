"""Bounded OOXML parsing. No formula calculation, macros or external resources."""
from contextlib import contextmanager
from io import BytesIO
from pathlib import PurePosixPath
import re
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
