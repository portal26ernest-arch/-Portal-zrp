"""Read-only staged preview, signed explicit approval and atomic tenant apply."""
import base64
import hashlib
import hmac
import json
import logging
import re
import secrets
import time
import uuid
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation

from document_domain import Documents,clean_text,decode_file,validate_upload,XLSX_MIME
from documents_api import require_import
from excel_template import catalog,REQUISITES,TEMPLATE_VERSION
from portal_excel_workbook import parse_template
from production_repository import utcnow
import production_permissions as rights

LOG=logging.getLogger('portal.import.audit')
_SIGNING_KEY=secrets.token_bytes(32)
IMPORT_ACTIONS={'excel-import-preview','excel-import-apply','excel-import-result'}
ROLES={'admin','director','manager','accountant','shift','packer'}

def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def identifier(value,optional=False):
    if optional and value in (None,''):return None
    if not isinstance(value,str) or not re.fullmatch('[1-9][0-9]{0,18}',value) or int(value)>2**63-1:
        raise ValueError('invalid_id')
    return int(value)
def active(value,default=1):
    if value in (None,''):return default
    if str(value).lower() not in ('0','1','true','false'):raise ValueError('invalid_status')
    return 1 if str(value).lower() in ('1','true') else 0
def money(value,optional=False):
    if optional and value=='':return None
    if not isinstance(value,str) or len(value)>32 or not re.fullmatch(r'[0-9]+(?:\.[0-9]{1,2})?',value):raise ValueError('invalid_money')
    try:number=Decimal(value)*100
    except InvalidOperation:raise ValueError('invalid_money') from None
    if not number.is_finite() or not 0<=number<=100_000_000_000:raise ValueError('invalid_money')
    return int(number)
def timestamp(value):
    if value in (None,''):return None
    try:
        parsed=datetime.fromisoformat(value)
        if parsed.tzinfo:parsed=parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed.isoformat(timespec='microseconds')
    except (ValueError,TypeError):raise ValueError('invalid_date') from None

class ExcelImport:
    def __init__(self,service,storage,company,signing_key=None):
        self.s,self.r,self.u,self.storage,self.company=service,service.r,service.u,storage,company
        self.key=signing_key or _SIGNING_KEY

    def state(self):
        result=catalog(self.s,self.company)
        result['_users']=self.r.catalog('users')
        result['_employees']=[dict(legacy_id=row[0],full_name=row[1],username=row[2] or '') for row in self.r.sql('SELECT telegram_id,full_name,username FROM employees WHERE company_id=? ORDER BY telegram_id',(self.r.company_id,)).fetchall()]
        result['_tariffs']=self.r.list('tariffs')
        result['_company_access']={k:self.company.get(k) for k in ('status','service_status','user_limit')}
        return result

    def token(self,claims):
        raw=canonical(claims).encode();encoded=base64.urlsafe_b64encode(raw).decode().rstrip('=')
        return encoded+'.'+hmac.new(self.key,raw,hashlib.sha256).hexdigest()

    def verify(self,token):
        if not isinstance(token,str) or len(token)>2000:raise ValueError('Нужно подтверждение preview')
        try:
            encoded,signature=token.split('.');raw=base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4))
            if not hmac.compare_digest(signature,hmac.new(self.key,raw,hashlib.sha256).hexdigest()):raise ValueError()
            claims=json.loads(raw)
            if claims['company_id']!=self.r.company_id or claims['actor_id']!=self.u['id'] or claims['actor_kind']!=self.actor_kind():raise PermissionError('Подтверждение другой компании/автора')
            if type(claims['expires']) is not int or claims['expires']<time.time():raise ValueError()
            return claims
        except PermissionError:raise
        except (ValueError,KeyError,TypeError):raise ValueError('Preview истёк или подтверждение повреждено; повторите preview') from None

    def actor_kind(self):return 'platform_owner' if self.u.get('technical_owner') else 'user'

    def plan(self,parsed,state):
        clients={c['client_id']:c for c in state['Клиенты']}
        employees={e['employee_id']:e for e in state['Сотрудники']}
        users={u['id']:u for u in state['_users']}
        operations={o['operation_id']:o for o in state['Операции_Тарифы']}
        refs={};output=[];seen={name:set() for name in parsed['sheets']};seen_names={'Клиенты':set(),'Сотрудники':set()}
        employee_ids_seen=set();client_ids_seen=set();user_ids_seen=set()
        normalized_clients={};now=self.s.clock()

        def issue(row,code,classification='invalid'):
            row['errors'].append(code)
            if row['classification']!='invalid' or classification=='invalid':row['classification']=classification
        def same(before,value,keys):return all((before.get(k) if before.get(k) is not None else '')==(value.get(k) if value.get(k) is not None else '') for k in keys)
        for sheet in parsed['sheets']:
            for source in parsed['rows'][sheet]:
                row=dict(sheet=sheet,row=source['_row'],classification='new',errors=[],normalized={},before={},changes={})
                output.append(row)
                try:
                    value={key:clean_text(text,1000,True) or '' for key,text in source.items() if key!='_row'}
                    if sheet=='Компания':
                        if len(parsed['rows'][sheet])!=1:raise ValueError('duplicate_company_row')
                        cid=identifier(value['company_id'],True)
                        if cid not in (None,self.r.company_id):raise ValueError('foreign_or_missing_company')
                        if value['name'] and value['name']!=self.company['name']:
                            issue(row,'company_name_read_only','conflict')
                        before=state[sheet][0];normalized={k:value[k] for k in REQUISITES+('director',)}
                        if not row['errors']:row['classification']='unchanged' if same(before,normalized,normalized) else 'update'
                    elif sheet=='Клиенты':
                        ref=clean_text(value['client_ref'],128);cid=identifier(value['client_id'],True)
                        if ref in seen[sheet]:raise ValueError('duplicate_client_reference')
                        seen[sheet].add(ref)
                        if cid is not None and cid in client_ids_seen:raise ValueError('duplicate_client_id')
                        if cid is not None:client_ids_seen.add(cid)
                        name=clean_text(value['name']);before=clients.get(cid,{})
                        if cid is not None and not before:raise ValueError('foreign_or_missing_client')
                        normalized=dict(client_ref=ref,client_id=cid,name=name,active=active(value['active'],before.get('active',1)),**{k:value[k] for k in REQUISITES+('contact_person',)})
                        if name.casefold() in seen_names[sheet] or any(c['name'].casefold()==name.casefold() and c['client_id']!=cid for c in clients.values()):
                            issue(row,'client_unique_conflict','conflict')
                        seen_names[sheet].add(name.casefold())
                        if not row['errors']:row['classification']='unchanged' if before and same(before,normalized,[k for k in normalized if k not in ('client_ref','client_id')]) else 'update' if before else 'new'
                        refs[ref]=cid or ref;normalized_clients[ref]=normalized
                    elif sheet=='Сотрудники':
                        ref=clean_text(value['employee_ref'],128);eid=identifier(value['employee_id'],True);uid=identifier(value['user_id'],True)
                        if ref in seen[sheet] or (eid is not None and eid in employee_ids_seen) or (uid is not None and uid in user_ids_seen):raise ValueError('duplicate_employee_identity')
                        seen[sheet].add(ref)
                        if eid is not None:employee_ids_seen.add(eid)
                        if uid is not None:user_ids_seen.add(uid)
                        name=clean_text(value['full_name']);before=employees.get(eid,{})
                        if eid is not None and not before:raise ValueError('foreign_or_missing_employee')
                        if eid is None and (name.casefold() in seen_names[sheet] or any((e['full_name'] or '').casefold()==name.casefold() for e in state['_employees'])):
                            issue(row,'employee_identity_ambiguous','conflict')
                        seen_names[sheet].add(name.casefold())
                        role=value['role'];enabled=active(value['active'],None)
                        if role and role not in ROLES:raise ValueError('invalid_role')
                        if uid is None and (role or enabled is not None):raise ValueError('access_requires_existing_user_id')
                        if uid is not None:
                            user=users.get(uid)
                            mapping=self.r.payroll_employee(eid) if eid is not None else None
                            if not user or not mapping or user.get('telegram_id')!=mapping['legacy_employee_id']:raise ValueError('employee_user_identity_conflict')
                            role=role or user['role'];enabled=user['active'] if enabled is None else enabled
                            if rights.defaults(role)-self.s.permissions or rights.effective(self.r,user)-self.s.permissions:raise ValueError('role_escalation')
                            if (role!=user['role'] or enabled!=user['active']) and uid==self.u['id'] and not self.u.get('technical_owner'):raise ValueError('own_access_change_requires_access_api')
                            if enabled and not user['active']:raise ValueError('activation_requires_access_api')
                        normalized=dict(employee_ref=ref,employee_id=eid,full_name=name,profile_username=value['profile_username'],user_id=uid,role=role,active=enabled)
                        if not row['errors']:row['classification']='unchanged' if before and same(before,normalized,['full_name','profile_username','user_id','role','active']) else 'update' if before else 'new'
                    else:
                        cid=identifier(value['client_id'],True);oid=identifier(value['operation_id'],True);ref=value['client_ref']
                        target=refs.get(ref) if ref else None
                        if ref and target is None:raise ValueError('ambiguous_or_missing_client_reference')
                        if cid is not None and cid not in clients:raise ValueError('foreign_or_missing_client')
                        if cid is not None and target is not None and target!=cid:raise ValueError('client_reference_conflict')
                        target=cid if cid is not None else target
                        if target is None:raise ValueError('missing_client_reference')
                        if ref and any(r['sheet']=='Клиенты' and r['normalized'].get('client_ref')==ref and r['errors'] for r in output):raise ValueError('invalid_client_reference')
                        name=clean_text(value['name']);key=(target,oid or name.casefold())
                        if key in seen[sheet]:raise ValueError('duplicate_operation_row')
                        seen[sheet].add(key);before=operations.get(oid,{})
                        if oid is not None and (not before or before['client_id']!=target):raise ValueError('foreign_or_missing_operation')
                        normalized=dict(client_ref=ref,client_id=target,operation_id=oid,name=name,active=active(value['active'],before.get('active',1)),
                                        employee_rate=money(value['employee_rate']),client_rate=money(value['client_rate'],True),effective_from=timestamp(value['effective_from']),effective_to=timestamp(value['effective_to']))
                        if normalized['effective_to'] is not None:raise ValueError('effective_end_not_supported_by_current_tariff_model')
                        if any(o['client_id']==target and o['name'].casefold()==name.casefold() and o['operation_id']!=oid for o in operations.values()):issue(row,'operation_unique_conflict','conflict')
                        changed_rates=bool(before) and (normalized['employee_rate']!=money(before['employee_rate']) or normalized['client_rate']!=money(before['client_rate'],True))
                        versions=[t for t in state['_tariffs'] if t['operation_id']==oid] if oid else []
                        if changed_rates or (oid is None and normalized['effective_from']):
                            effective=normalized['effective_from']
                            if not effective or effective<now:issue(row,'tariff_backdated_or_missing_date','conflict')
                            elif versions and effective<=max(t['effective_from'] for t in versions):issue(row,'tariff_overlap_or_effective_conflict','conflict')
                        elif before and normalized['effective_from'] not in (None,before['effective_from']):
                            issue(row,'tariff_date_change_without_new_rates','conflict')
                        normalized['append_tariff']=changed_rates or not before
                        if not row['errors']:row['classification']='update' if before and (changed_rates or normalized['name']!=before['name'] or normalized['active']!=before['active']) else 'unchanged' if before else 'new'
                    row['normalized']=normalized;row['before']=before
                    row['changes']={key:dict(before=before.get(key),after=value) for key,value in normalized.items() if key not in ('client_ref','employee_ref','append_tariff') and before.get(key)!=value}
                except (ValueError,PermissionError) as error:
                    # Validation codes deliberately omit cross-company object data.
                    code=str(error) if re.fullmatch(r'[a-z_]+',str(error)) else 'invalid_text_or_reference'
                    issue(row,code)
        # A simultaneous workbook edit must not disable the last administrator.
        resulting={uid:dict(u) for uid,u in users.items()}
        for row in output:
            value=row['normalized']
            if row['sheet']=='Сотрудники' and not row['errors'] and value.get('user_id'):
                resulting[value['user_id']].update(role=value['role'],active=value['active'])
        if not any(u['role']=='admin' and u['active'] for u in resulting.values()):
            for row in output:
                if row['sheet']=='Сотрудники' and row['normalized'].get('user_id'):issue(row,'last_admin_conflict','conflict')
        counts={key:sum(row['classification']==key for row in output) for key in ('new','update','unchanged','conflict','invalid')}
        return dict(rows=output,summary=counts,can_apply=not(counts['conflict'] or counts['invalid']),snapshot_sha256=digest(state))

    def preview(self,body):
        require_import(self.s)
        if set(body)-{'company_id','file_b64','original_filename','mime_type','request_id'}:raise ValueError('Неизвестные параметры preview')
        payload=decode_file(body);validate_upload(body.get('original_filename','PORTAL_template.xlsx'),body.get('mime_type',XLSX_MIME),payload,'import_template_xlsx')
        parsed=parse_template(payload);state=self.state();plan=self.plan(parsed,state)
        import_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'portal-import:'+str(self.r.company_id)+':'+parsed['checksum_sha256']))
        claims=dict(company_id=self.r.company_id,actor_id=self.u['id'],actor_kind=self.actor_kind(),import_id=import_id,
                    checksum=parsed['checksum_sha256'],snapshot=plan['snapshot_sha256'],plan=digest(plan),expires=int(time.time())+1800)
        LOG.info(canonical(dict(event='import_preview_created',company_id=self.r.company_id,actor_id=self.u['id'],import_id=import_id,summary=plan['summary'])))
        return dict(plan,import_id=import_id,template_version=TEMPLATE_VERSION,checksum=parsed['checksum_sha256'],preview_token=self.token(claims),expires_at=claims['expires'])
