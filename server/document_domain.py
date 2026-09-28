"""Central document metadata and a replaceable company-scoped byte store."""
import base64
import hashlib
import json
import os
import re
import uuid
from datetime import date
from pathlib import Path
from typing import Protocol
from production_repository import utcnow

XLSX_MIME='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
MAX_DOCUMENT_BYTES=10*1024*1024
DOCUMENT_TYPES={key:(extension,mime) for key,extension,mime in (
 ('payroll_xlsx','.xlsx',XLSX_MIME),('payroll_slip_xlsx','.xlsx',XLSX_MIME),
 ('payroll_slip_pdf','.pdf','application/pdf'),('invoice_xlsx','.xlsx',XLSX_MIME),
 ('invoice_pdf','.pdf','application/pdf'),('report_xlsx','.xlsx',XLSX_MIME),
 ('report_pdf','.pdf','application/pdf'),('import_template_xlsx','.xlsx',XLSX_MIME),
 ('import_result','.json','application/json'))}
COLUMNS=('company_id','id','document_type','category','title','original_filename','storage_key',
 'mime_type','size_bytes','checksum_sha256','client_id','employee_id','invoice_id','invoice_kind',
 'payroll_period_id','payroll_period_kind','created_by','actor_kind','created_at','document_date',
 'status','metadata','source_kind','revision','previous_id','request_id','fingerprint')

def clean_text(value,limit=1000,optional=False):
    if optional and value in (None,''):return None
    if not isinstance(value,str) or not value.strip() or len(value)>limit:
        raise ValueError('Ожидается непустой текст допустимой длины')
    if any(ord(ch)<32 and ch not in '\n\t' for ch in value):raise ValueError('Управляющие символы запрещены')
    return value.strip()

def iso_date(value):
    if value in (None,''):return None
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',value):raise ValueError('Дата: YYYY-MM-DD')
    try:return date.fromisoformat(value).isoformat()
    except ValueError:raise ValueError('Некорректная календарная дата') from None

def decode_file(body):
    value=body.get('file_b64')
    if not isinstance(value,str) or len(value)>((MAX_DOCUMENT_BYTES+2)//3)*4:raise ValueError('Файл больше 10 МБ')
    try:return base64.b64decode(value,validate=True)
    except (ValueError,TypeError):raise ValueError('Некорректный base64 файл') from None

class ByteStorage(Protocol):
    def put(self,payload:bytes,company_id:int)->str: ...
    def get(self,key:str,company_id:int)->bytes: ...

class LocalFileStorage:
    """Immutable content-addressed blobs. Rollback orphans are retained for reconciliation."""
    def __init__(self,root):self.root=Path(root).resolve()
    def _path(self,key,company_id):
        if type(company_id) is not int or company_id<1:raise PermissionError('Некорректная компания')
        if not isinstance(key,str) or not re.fullmatch(str(company_id)+r'/[a-f0-9]{64}',key):raise PermissionError('Недопустимый ключ компании')
        target=self.root/key
        if target.parent.is_symlink() or target.is_symlink() or target.resolve().parent!=self.root/str(company_id):
            raise PermissionError('Ссылки за пределы хранилища запрещены')
        return target
    def put(self,payload,company_id=1):
        digest=hashlib.sha256(payload).hexdigest();key=f'{company_id}/{digest}';target=self._path(key,company_id)
        target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if target.exists():self.get(key,company_id);return key
        temporary=target.parent/('.tmp-'+uuid.uuid4().hex)
        try:
            fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as stream:stream.write(payload);stream.flush();os.fsync(stream.fileno())
            self._path(key,company_id);os.replace(temporary,target)
        finally:temporary.unlink(missing_ok=True)
        return key
    def get(self,key,company_id=1):
        target=self._path(key,company_id)
        with os.fdopen(os.open(target,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0)),'rb') as stream:
            payload=stream.read(MAX_DOCUMENT_BYTES+1)
        if len(payload)>MAX_DOCUMENT_BYTES or hashlib.sha256(payload).hexdigest()!=key.split('/')[1]:
            raise ValueError('Checksum/размер файла не совпадает')
        return payload

def validate_upload(filename,mime_type,payload,document_type=None):
    filename=clean_text(filename,255)
    if filename in {'.','..'} or re.search(r'[\\/:\x00-\x1f]',filename) or filename.endswith(('.', ' ')):
        raise ValueError('Недопустимое имя файла')
    if not isinstance(payload,bytes) or not 0<len(payload)<=MAX_DOCUMENT_BYTES:raise ValueError('Недопустимый размер файла')
    suffix=Path(filename).suffix.lower();allowed={'.xlsx':XLSX_MIME,'.pdf':'application/pdf','.json':'application/json'}
    if allowed.get(suffix)!=mime_type or (document_type is not None and DOCUMENT_TYPES.get(document_type)!=(suffix,mime_type)):
        raise ValueError('Тип документа/MIME не соответствует расширению')
    if suffix=='.xlsx':
        from portal_excel_workbook import inspect_xlsx
        inspect_xlsx(payload)
    elif suffix=='.pdf':
        if not payload.startswith(b'%PDF-') or b'%%EOF' not in payload[-2048:]:raise ValueError('PDF повреждён')
    else:
        if document_type!='import_result':raise ValueError('JSON разрешён только для отчёта импорта')
        try:value=json.loads(payload)
        except (ValueError,UnicodeError):raise ValueError('Некорректный JSON отчёта') from None
        if not isinstance(value,dict):raise ValueError('Отчёт должен быть JSON-объектом')
    return hashlib.sha256(payload).hexdigest()

class Documents:
    def __init__(self,service,storage):self.s,self.r,self.u,self.storage=service,service.r,service.u,storage
    def ready(self):
        if not self.r.has_table('portal_documents'):raise ValueError('Сначала примените миграцию Documents/Excel')
    def visible(self,item):
        if self.u['role']=='manager' and not self.u.get('technical_owner'):
            if item.get('client_id') is None or not self.s.visible(item['client_id']):return False
        if item['document_type'].startswith('payroll') and 'payroll.all' not in self.s.permissions:return False
        if item['document_type']=='import_template_xlsx' and 'imports.manage' not in self.s.permissions:return False
        return item.get('client_id') is None or self.s.visible(item['client_id'])
    @staticmethod
    def public(item):
        value={k:v for k,v in item.items() if k not in ('fingerprint','request_id','storage_key','file_b64','invoice_kind','payroll_period_kind')}
        value.update(filename=item['original_filename'],sha256=item['checksum_sha256'])
        if item.get('payroll_period_id'):
            value['period_id']=item['payroll_period_id'];value['snapshot']={}
            value.update({k:v for k,v in item.get('metadata',{}).items() if k in ('period_start','period_end')})
        return value
    def _row(self,row):
        item=dict(zip(COLUMNS,row));item['metadata']=json.loads(item['metadata']);return item
    def legacy(self,old):
        archived=any(a.get('event')=='document_archived' and a.get('entity_id')==old['id'] for a in self.r.list('audit'))
        return dict(old,document_type='payroll_xlsx' if old.get('document_type')=='payroll' else old.get('document_type','report_xlsx'),
          original_filename=old.get('original_filename',old.get('filename','document.xlsx')),
          checksum_sha256=old.get('checksum_sha256',old.get('sha256')),payroll_period_id=old.get('period_id'),
          metadata={k:old[k] for k in ('period_start','period_end') if k in old},
          status='archived' if archived else old.get('status','ready'),source_kind=old.get('source_kind','generated'),revision=1)
    def get(self,identity):
        self.s.need('documents.read');self.ready()
        row=self.r.sql('SELECT '+','.join(COLUMNS)+' FROM portal_documents WHERE company_id=? AND id=?',(self.r.company_id,str(identity))).fetchone()
        if row:item=self._row(row)
        else:
            old=self.r.get('documents',identity,False)
            if not old:raise ValueError('Документ не найден')
            item=self.legacy(old)
        if not self.visible(item):raise PermissionError('Документ недоступен')
        return item
    def rows(self,params):
        self.s.need('documents.read');self.ready()
        page=int(params.get('page',['1'])[0]);limit=int(params.get('limit',['50'])[0])
        if not 1<=page<=100000 or not 1<=limit<=200:raise ValueError('Некорректная пагинация')
        q=params.get('q',[''])[0].strip().casefold()
        if len(q)>200:raise ValueError('Поиск не более 200 символов')
        start=iso_date(params.get('date_from',[None])[0]);end=iso_date(params.get('date_to',[None])[0])
        if start and end and start>end:raise ValueError('Диапазон дат перепутан')
        items=[self._row(row) for row in self.r.sql('SELECT '+','.join(COLUMNS)+' FROM portal_documents WHERE company_id=?',(self.r.company_id,)).fetchall()]
        ids={i['id'] for i in items};items.extend(self.legacy(old) for old in self.r.list('documents') if old['id'] not in ids)
        status=params.get('status',['ready'])[0]
        if params.get('include_archived',['false'])[0]=='true' and 'status' not in params:status='all'
        if status not in ('ready','archived','all'):raise ValueError('Некорректный статус')
        selected=[]
        for item in items:
            if not self.visible(item) or (status!='all' and item['status']!=status):continue
            if any(key in params and str(item.get(key)) not in params[key] for key in ('document_type','category','client_id','employee_id')):continue
            day=item.get('document_date') or item['created_at'][:10]
            if (start and day<start) or (end and day>end):continue
            if q and q not in (item['title']+' '+item['original_filename']).casefold():continue
            selected.append(self.public(item))
        selected.sort(key=lambda i:(i['created_at'],i['id']),reverse=True);result=selected[(page-1)*limit:page*limit]
        return {'items':result,'page':page,'limit':limit,'total':len(selected)} if params else result
    def download(self,identity):
        item=self.get(identity)
        if item['status']!='ready':raise ValueError('Документ находится в архиве')
        try:
            payload=self.storage.get(item['storage_key'],self.r.company_id) if item.get('storage_key') and not item['storage_key'].startswith('ledger:') else base64.b64decode(item['file_b64'],validate=True)
        except (FileNotFoundError,KeyError):raise ValueError('Файл отсутствует; метаданные сохранены') from None
        if len(payload)!=item['size_bytes'] or hashlib.sha256(payload).hexdigest()!=item['checksum_sha256']:raise ValueError('Checksum/размер документа не совпадает')
        return dict(id=item['id'],filename=item['original_filename'],mime_type=item['mime_type'],size_bytes=len(payload),sha256=item['checksum_sha256'],file_b64=base64.b64encode(payload).decode('ascii'))
    def register(self,payload,body,source_kind='uploaded',identity=None):
        self.s.need('documents.manage');self.ready();document_type=body.get('document_type','report_xlsx')
        filename=body.get('original_filename');mime=body.get('mime_type');checksum=validate_upload(filename,mime,payload,document_type)
        metadata=body.get('metadata',{})
        if not isinstance(metadata,dict) or set(metadata)-{'template_version','period_start','period_end','snapshot_sha256','import_id','result','notes'} or len(json.dumps(metadata))>4000:raise ValueError('Недопустимые метаданные')
        item=dict(company_id=self.r.company_id,id=str(identity or uuid.uuid4()),document_type=document_type,
          category=clean_text(body.get('category',document_type.split('_')[0]),80),title=clean_text(body.get('title',filename)),
          original_filename=filename,storage_key='',mime_type=mime,size_bytes=len(payload),checksum_sha256=checksum,
          client_id=body.get('client_id'),employee_id=body.get('employee_id'),invoice_id=body.get('invoice_id'),invoice_kind='invoices',
          payroll_period_id=body.get('payroll_period_id'),payroll_period_kind='payroll_periods',created_by=self.u['id'],
          actor_kind='platform_owner' if self.u.get('technical_owner') else 'user',created_at=utcnow(),document_date=iso_date(body.get('document_date')),
          status='ready',metadata=metadata,source_kind=source_kind,revision=1,previous_id=body.get('previous_id'),
          request_id=clean_text(body.get('request_id'),128),fingerprint='')
        if item['client_id'] is not None:
            if type(item['client_id']) is not int:raise ValueError('client_id: целое число')
            self.s.client(item['client_id'])
        if item['employee_id'] is not None:
            if type(item['employee_id']) is not int:raise ValueError('employee_id: целое число')
            self.r.payroll_employee(item['employee_id'])
        for field,kind in (('invoice_id','invoices'),('payroll_period_id','payroll_periods')):
            if item[field] is not None:
                linked=self.r.get(kind,item[field])
                if linked.get('client_id') is not None:
                    self.s.client(linked['client_id'])
                    if item['client_id'] not in (None,linked['client_id']):raise ValueError('Связь клиента не совпадает')
                    item['client_id']=linked['client_id']
        if item['previous_id']:
            previous=self.get(item['previous_id'])
            if previous['document_type']!=document_type:raise ValueError('Тип предыдущей версии не совпадает')
            item['revision']=previous.get('revision',1)+1
        if not self.visible(item):raise PermissionError('Документ недоступен')
        semantic={k:v for k,v in item.items() if k not in ('id','created_at','storage_key','fingerprint','request_id')}
        item['fingerprint']=hashlib.sha256(json.dumps(semantic,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        old=self.r.sql('SELECT '+','.join(COLUMNS)+' FROM portal_documents WHERE company_id=? AND request_id=?',(self.r.company_id,item['request_id'])).fetchone()
        if old:
            old=self._row(old)
            if old['fingerprint']!=item['fingerprint']:raise ValueError('request_id уже использован для другого документа')
            return self.public(old)
        item['storage_key']=self.storage.put(payload,self.r.company_id);values=dict(item,metadata=json.dumps(metadata,sort_keys=True,ensure_ascii=False))
        self.r.sql('INSERT INTO portal_documents('+','.join(COLUMNS)+') VALUES('+','.join('?' for _ in COLUMNS)+')',tuple(values[k] for k in COLUMNS))
        self.r.audit(self.u,'document_uploaded' if source_kind=='uploaded' else 'document_generated',item['id'])
        return self.public(item)
    def archive(self,identity):
        self.s.need('documents.manage');item=self.get(identity)
        if item['status']=='archived':return self.public(item)
        if self.r.sql('SELECT 1 FROM portal_documents WHERE company_id=? AND id=?',(self.r.company_id,item['id'])).fetchone():
            self.r.sql("UPDATE portal_documents SET status='archived' WHERE company_id=? AND id=?",(self.r.company_id,item['id']))
        self.r.audit(self.u,'document_archived',item['id']);return self.public(dict(item,status='archived'))
