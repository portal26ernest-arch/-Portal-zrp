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
from employee_names import employee_name_key
from excel_template import catalog,REQUISITES,TEMPLATE_VERSION
from portal_excel_workbook import parse_template
from production_repository import utcnow
from employee_identity import account_directory
import production_permissions as rights

LOG=logging.getLogger('portal.import.audit')
if not LOG.handlers:LOG.addHandler(logging.StreamHandler())
LOG.setLevel(logging.INFO)
LOG.propagate=False
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
def decimal_number(value,optional=False,positive=False):
    if optional and value in (None,''):return None
    if not isinstance(value,str) or len(value)>32 or not re.fullmatch(r'[0-9]+(?:\.[0-9]{1,6})?',value):raise ValueError('invalid_number')
    try:number=Decimal(value)
    except InvalidOperation:raise ValueError('invalid_number') from None
    if not number.is_finite() or number<0 or number>1_000_000_000 or (positive and number<=0):raise ValueError('invalid_number')
    return format(number,'f')
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
        result['_users']=account_directory(self.r.conn,self.r.company_id)
        result['_employees']=self.r.employee_catalog()
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
        materials={m['material_id']:m for m in state.get('Материалы',[])}
        norms={n['norm_id']:n for n in state.get('Нормы_материалов',[])}
        refs={};output=[];seen={name:set() for name in parsed['sheets']};seen_names={'Клиенты':set(),'Сотрудники':set(),'Материалы':set()}
        employee_ids_seen=set();client_ids_seen=set();user_ids_seen=set();material_ids_seen=set();norm_ids_seen=set();new_access_usernames=set()
        normalized_clients={};normalized_employees={};normalized_operations={};normalized_materials={};now=self.s.clock()

        existing_client_names={}
        for item in clients.values():existing_client_names.setdefault(item['name'].casefold(),[]).append(item)
        existing_employee_names={}
        for item in state['_employees']:existing_employee_names.setdefault(employee_name_key(item['full_name']),[]).append(item)
        existing_operation_names={}
        for item in operations.values():existing_operation_names.setdefault((item['client_id'],item['name'].casefold()),[]).append(item)
        existing_material_names={}
        for item in materials.values():existing_material_names.setdefault(item['name'].casefold(),[]).append(item)

        def issue(row,code,classification='invalid'):
            row['errors'].append(code)
            if row['classification']!='invalid' or classification=='invalid':row['classification']=classification
        def same(before,value,keys):return all((before.get(k) if before.get(k) is not None else '')==(value.get(k) if value.get(k) is not None else '') for k in keys)
        def resolve_client(value):
            cid=identifier(value.get('client_id',''),True)
            ref=clean_text(value.get('client_ref',''),128,True)
            name=clean_text(value.get('client_name',''),200,True)
            if cid is not None:
                item=clients.get(cid)
                if not item:raise ValueError('foreign_or_missing_client')
                if name and item['name'].casefold()!=name.casefold():raise ValueError('client_reference_conflict')
                return cid,ref or 'client:'+str(cid),item['name']
            if ref:
                target=refs.get(ref)
                if isinstance(target,int):
                    item=clients.get(target)
                    if not item:raise ValueError('foreign_or_missing_client')
                    return target,ref,item['name']
                staged=normalized_clients.get(ref)
                if staged:return None,ref,staged['name']
            if name:
                matches=existing_client_names.get(name.casefold(),[])
                staged=[(key,item) for key,item in normalized_clients.items() if item['name'].casefold()==name.casefold()]
                if len(matches)+len(staged)!=1:raise ValueError('ambiguous_or_missing_client_reference')
                if matches:return matches[0]['client_id'],'client:'+str(matches[0]['client_id']),matches[0]['name']
                return None,staged[0][0],staged[0][1]['name']
            raise ValueError('missing_client_reference')
        def resolve_material(value):
            mid=identifier(value.get('material_id',''),True)
            ref=clean_text(value.get('material_ref',''),128,True)
            name=clean_text(value.get('material_name',''),200,True)
            if mid is not None:
                item=materials.get(mid)
                if not item:raise ValueError('foreign_or_missing_material')
                if name and item['name'].casefold()!=name.casefold():raise ValueError('material_reference_conflict')
                return mid,ref or 'material:'+str(mid),item['name']
            if ref:
                staged=normalized_materials.get(ref)
                if staged:return staged.get('material_id'),ref,staged['name']
                target=refs.get(ref)
                if isinstance(target,int) and target in materials:return target,ref,materials[target]['name']
            if name:
                matches=existing_material_names.get(name.casefold(),[])
                staged=[(key,item) for key,item in normalized_materials.items() if item['name'].casefold()==name.casefold()]
                if len(matches)+len(staged)!=1:raise ValueError('ambiguous_or_missing_material_reference')
                if matches:return matches[0]['material_id'],'material:'+str(matches[0]['material_id']),matches[0]['name']
                return staged[0][1].get('material_id'),staged[0][0],staged[0][1]['name']
            raise ValueError('missing_material_reference')
        def resolve_operation(value,cid,cref):
            oid=identifier(value.get('operation_id',''),True)
            name=clean_text(value.get('operation_name',''),200,True)
            if oid is not None:
                item=operations.get(oid)
                if not item or (cid is not None and item['client_id']!=cid):raise ValueError('foreign_or_missing_operation')
                if name and item['name'].casefold()!=name.casefold():raise ValueError('operation_reference_conflict')
                return oid,item['name']
            if not name:raise ValueError('missing_operation_reference')
            key=(cid if cid is not None else cref,name.casefold())
            staged=normalized_operations.get(key)
            if staged:return staged.get('operation_id'),staged['name']
            if cid is None:raise ValueError('ambiguous_or_missing_operation_reference')
            matches=existing_operation_names.get((cid,name.casefold()),[])
            if len(matches)!=1:raise ValueError('ambiguous_or_missing_operation_reference')
            return matches[0]['operation_id'],matches[0]['name']
        def resolve_employee(value):
            eid=identifier(value.get('employee_id',''),True)
            name=clean_text(value.get('employee_name',''),200,True)
            if eid is not None:
                item=employees.get(eid)
                if not item:raise ValueError('foreign_or_missing_employee')
                if name and employee_name_key(item['full_name'])!=employee_name_key(name):raise ValueError('employee_identity_conflict')
                return eid,None,item['full_name']
            if not name:raise ValueError('missing_employee_reference')
            key=employee_name_key(name);matches=existing_employee_names.get(key,[]);staged=normalized_employees.get(key)
            if len(matches)+(1 if staged else 0)!=1:raise ValueError('employee_identity_ambiguous')
            if staged:return staged.get('employee_id'),staged['employee_ref'],staged['full_name']
            return int(matches[0]['employee_id']),None,matches[0]['full_name']
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
                        name=clean_text(value['name']);cid=identifier(value['client_id'],True)
                        ref=clean_text(value['client_ref'],128,True) or 'client:name:'+name.casefold()
                        if ref in seen[sheet]:raise ValueError('duplicate_client_reference')
                        seen[sheet].add(ref)
                        if cid is not None and cid in client_ids_seen:raise ValueError('duplicate_client_id')
                        if cid is not None:client_ids_seen.add(cid)
                        before=clients.get(cid,{})
                        if cid is not None and not before:raise ValueError('foreign_or_missing_client')
                        normalized=dict(client_ref=ref,client_id=cid,name=name,active=active(value['active'],before.get('active',1)),**{k:value[k] for k in REQUISITES+('contact_person',)})
                        if name.casefold() in seen_names[sheet] or any(c['name'].casefold()==name.casefold() and c['client_id']!=cid for c in clients.values()):
                            issue(row,'client_unique_conflict','conflict')
                        seen_names[sheet].add(name.casefold())
                        if not row['errors']:row['classification']='unchanged' if before and same(before,normalized,[k for k in normalized if k not in ('client_ref','client_id')]) else 'update' if before else 'new'
                        refs[ref]=cid or ref;normalized_clients[ref]=normalized
                    elif sheet=='Сотрудники':
                        name=clean_text(value['full_name']);name_key=employee_name_key(name)
                        ref=clean_text(value['employee_ref'],128,True) or 'employee:name:'+name_key
                        eid=identifier(value['employee_id'],True);uid=identifier(value['user_id'],True)
                        if ref in seen[sheet] or (eid is not None and eid in employee_ids_seen) or (uid is not None and uid in user_ids_seen):raise ValueError('duplicate_employee_identity')
                        seen[sheet].add(ref)
                        if eid is not None:employee_ids_seen.add(eid)
                        if uid is not None:user_ids_seen.add(uid)
                        before=employees.get(eid,{})
                        if eid is not None and not before:raise ValueError('foreign_or_missing_employee')
                        if eid is None and (name_key in seen_names[sheet] or any(employee_name_key(e['full_name'])==name_key for e in state['_employees'])):
                            issue(row,'employee_identity_ambiguous','conflict')
                        seen_names[sheet].add(name_key)
                        role=value['role'];enabled=active(value['active'],None);pin=value.get('initial_pin','')
                        if role and role not in ROLES:raise ValueError('invalid_role')
                        create_access=uid is None and bool(role or pin or value['active'])
                        if uid is None and create_access:
                            username=clean_text(value['profile_username'],128)
                            if not role:raise ValueError('new_access_requires_role')
                            if not pin or not 4<=len(pin)<=128:raise ValueError('new_access_requires_valid_pin')
                            enabled=1 if enabled is None else enabled
                            if rights.defaults(role)-self.s.permissions:raise ValueError('role_escalation')
                            username_key=username.casefold()
                            if username_key in new_access_usernames or any((u.get('username') or '').casefold()==username_key for u in users.values()):raise ValueError('access_username_conflict')
                            new_access_usernames.add(username_key)
                        elif uid is not None:
                            if pin:raise ValueError('pin_change_requires_access_api')
                            user=users.get(uid)
                            mapping=self.r.payroll_employee(eid) if eid is not None else None
                            user_identity=user.get('employee_id') if user else None
                            if not user or not mapping or user_identity!=mapping['employee_id']:raise ValueError('employee_user_identity_conflict')
                            role=role or user['role'];enabled=user['active'] if enabled is None else enabled
                            if rights.defaults(role)-self.s.permissions or rights.effective(self.r,user)-self.s.permissions:raise ValueError('role_escalation')
                            if (role!=user['role'] or enabled!=user['active']) and uid==self.u['id'] and not self.u.get('technical_owner'):raise ValueError('own_access_change_requires_access_api')
                            if enabled and not user['active']:raise ValueError('activation_requires_access_api')
                        normalized=dict(employee_ref=ref,employee_id=eid,full_name=name,profile_username=value['profile_username'],user_id=uid,role=role,active=enabled,create_access=create_access,initial_pin=pin)
                        if before and uid is None and not create_access:
                            # Omitted account fields mean a profile edit, never an access edit.
                            before={k:v for k,v in before.items() if k not in ('user_id','role','active')}
                        compare=['full_name','profile_username','user_id','role','active']
                        if not row['errors']:row['classification']='unchanged' if before and not create_access and same(before,normalized,compare) else 'update' if before else 'new'
                        normalized_employees[name_key]=normalized
                    elif sheet=='Операции_Тарифы':
                        cid=identifier(value['client_id'],True);oid=identifier(value['operation_id'],True);ref=clean_text(value['client_ref'],128,True)
                        client_value=dict(value,client_id=str(cid) if cid is not None else value.get('client_id',''),client_ref=ref or value.get('client_ref',''))
                        cid,cref,cname=resolve_client(client_value)
                        if cref and any(r['sheet']=='Клиенты' and r['normalized'].get('client_ref')==cref and r['errors'] for r in output):raise ValueError('invalid_client_reference')
                        name=clean_text(value['name']);key=(cid if cid is not None else cref,oid or name.casefold())
                        if key in seen[sheet]:raise ValueError('duplicate_operation_row')
                        seen[sheet].add(key);before=operations.get(oid,{})
                        if oid is not None and (not before or (cid is not None and before['client_id']!=cid)):raise ValueError('foreign_or_missing_operation')
                        normalized=dict(client_ref=cref,client_id=cid,client_name=cname,operation_id=oid,name=name,active=active(value['active'],before.get('active',1)),
                                        employee_rate=money(value['employee_rate']),client_rate=money(value['client_rate'],True),effective_from=timestamp(value['effective_from']),effective_to=timestamp(value['effective_to']))
                        if normalized['effective_to'] is not None:raise ValueError('effective_end_not_supported_by_current_tariff_model')
                        if cid is not None and any(o['client_id']==cid and o['name'].casefold()==name.casefold() and o['operation_id']!=oid for o in operations.values()):issue(row,'operation_unique_conflict','conflict')
                        changed_rates=bool(before) and (normalized['employee_rate']!=money(before['employee_rate']) or normalized['client_rate']!=money(before['client_rate'],True))
                        versions=[t for t in state['_tariffs'] if t['operation_id']==oid] if oid else []
                        if changed_rates or (oid is None and normalized['effective_from']):
                            effective=normalized['effective_from']
                            if not effective or effective<timestamp(now):issue(row,'tariff_backdated_or_missing_date','conflict')
                            elif versions and effective<=max(timestamp(t['effective_from']) for t in versions):issue(row,'tariff_overlap_or_effective_conflict','conflict')
                        elif before and normalized['effective_from'] not in (None,timestamp(before['effective_from'])):
                            issue(row,'tariff_date_change_without_new_rates','conflict')
                        normalized['append_tariff']=changed_rates or not before
                        normalized['operation_key']=str(cid if cid is not None else cref)+'|'+name.casefold()
                        if not row['errors']:row['classification']='update' if before and (changed_rates or normalized['name']!=before['name'] or normalized['active']!=before['active']) else 'unchanged' if before else 'new'
                        normalized_operations[(cid if cid is not None else cref,name.casefold())]=normalized
                    elif sheet=='Материалы':
                        name=clean_text(value['name']);mid=identifier(value['material_id'],True)
                        ref=clean_text(value['material_ref'],128,True) or 'material:name:'+name.casefold()
                        if ref in seen[sheet] or (mid is not None and mid in material_ids_seen):raise ValueError('duplicate_material_identity')
                        seen[sheet].add(ref)
                        if mid is not None:material_ids_seen.add(mid)
                        before=materials.get(mid,{})
                        if mid is not None and not before:raise ValueError('foreign_or_missing_material')
                        normalized=dict(material_ref=ref,material_id=mid,name=name,unit=clean_text(value['unit'],50),
                                        unit_cost=money(value['unit_cost']),min_stock=decimal_number(value['min_stock'],True),
                                        active=active(value['active'],before.get('active',1)))
                        duplicates=existing_material_names.get(name.casefold(),[])
                        if name.casefold() in seen_names[sheet] or any(m['material_id']!=mid for m in duplicates):issue(row,'material_unique_conflict','conflict')
                        seen_names[sheet].add(name.casefold())
                        if before:
                            before_cost=money(str(before.get('unit_cost') or 0));before_min=decimal_number(str(before.get('min_stock') or 0),True)
                            changed=normalized['name']!=before.get('name') or normalized['unit']!=(before.get('unit') or '') or normalized['unit_cost']!=before_cost or normalized['min_stock']!=before_min or normalized['active']!=before.get('active',1)
                            if not row['errors']:row['classification']='update' if changed else 'unchanged'
                        normalized_materials[ref]=normalized;refs[ref]=mid or ref
                    elif sheet=='Приход_материалов':
                        mid,mref,mname=resolve_material(value)
                        quantity=decimal_number(value['quantity'],positive=True);unit_cost=money(value['unit_cost'],True)
                        before={}
                        normalized=dict(material_id=mid,material_ref=mref,material_name=mname,quantity=quantity,unit_cost=unit_cost,
                                        note=clean_text(value['note'],500,True) or '')
                        row['classification']='new'
                    elif sheet=='Нормы_материалов':
                        cid,cref,cname=resolve_client(value);oid,oname=resolve_operation(value,cid,cref);mid,mref,mname=resolve_material(value)
                        nid=identifier(value['norm_id'],True)
                        if nid is not None and nid in norm_ids_seen:raise ValueError('duplicate_norm_id')
                        if nid is not None:norm_ids_seen.add(nid)
                        before=norms.get(nid,{}) if nid is not None else {}
                        if nid is not None and (not before or (oid is not None and before['operation_id']!=oid) or (mid is not None and before['material_id']!=mid)):raise ValueError('foreign_or_missing_norm')
                        if nid is None and oid is not None and mid is not None:
                            matches=[item for item in norms.values() if item['operation_id']==oid and item['material_id']==mid]
                            if len(matches)>1:raise ValueError('ambiguous_norm_reference')
                            if len(matches)==1:before=matches[0];nid=before['norm_id']
                        op_key=(cid if cid is not None else cref,oname.casefold());key=(oid if oid is not None else op_key,mid if mid is not None else mref)
                        if key in seen[sheet]:raise ValueError('duplicate_norm_row')
                        seen[sheet].add(key)
                        normalized=dict(norm_id=nid,client_id=cid,client_ref=cref,client_name=cname,operation_id=oid,operation_name=oname,
                                        operation_key=str(op_key[0])+'|'+op_key[1],material_id=mid,material_ref=mref,material_name=mname,
                                        qty_per_unit=decimal_number(value['qty_per_unit'],positive=True),active=active(value['active'],before.get('active',1)))
                        if before:
                            before_qty=decimal_number(str(before.get('qty_per_unit') or 0),positive=True)
                            changed=normalized['qty_per_unit']!=before_qty or normalized['active']!=before.get('active',1)
                            row['classification']='update' if changed else 'unchanged'
                        else:row['classification']='new'
                    elif sheet=='Выработка':
                        eid,eref,ename=resolve_employee(value);cid,cref,cname=resolve_client(value);oid,oname=resolve_operation(value,cid,cref)
                        target_user_id=None
                        if eid is not None:
                            linked=[u for u in users.values() if u.get('employee_id')==eid and u.get('active') and 'work.write' in rights.effective(self.r,u)]
                            if len(linked)!=1:raise ValueError('employee_access_missing_for_work')
                            target_user_id=linked[0]['id']
                        else:
                            staged=normalized_employees.get(employee_name_key(ename))
                            if not staged or not staged.get('create_access') or not staged.get('active') or 'work.write' not in rights.defaults(staged.get('role')):raise ValueError('employee_access_missing_for_work')
                        before={}
                        quantity_value=Decimal(decimal_number(value['quantity'],positive=True))
                        if quantity_value!=quantity_value.to_integral_value() or quantity_value>1000000:raise ValueError('invalid_work_quantity')
                        op_key=(cid if cid is not None else cref,oname.casefold())
                        normalized=dict(employee_id=eid,employee_ref=eref,employee_name=ename,target_user_id=target_user_id,
                                        client_id=cid,client_ref=cref,client_name=cname,operation_id=oid,operation_name=oname,
                                        operation_key=str(op_key[0])+'|'+op_key[1],quantity=int(quantity_value),
                                        product=clean_text(value['product'],500,True) or '')
                        row['classification']='new'
                    else:raise ValueError('unsupported_sheet')
                    row['normalized']=normalized;row['before']=before
                    row['changes']={key:dict(before=before.get(key),after=value) for key,value in normalized.items() if key not in ('client_ref','employee_ref','append_tariff','create_access','initial_pin') and before.get(key)!=value}
                except (ValueError,PermissionError) as error:
                    # Validation codes deliberately omit cross-company object data.
                    code=str(error) if re.fullmatch(r'[a-z_]+',str(error)) else 'invalid_text_or_reference'
                    issue(row,code)
        # A simultaneous workbook edit must not disable the last administrator
        # and must respect the active-user limit when creating access in bulk.
        resulting={uid:dict(u) for uid,u in users.items()};new_access_rows=[]
        for row in output:
            value=row['normalized']
            if row['sheet']!='Сотрудники' or row['errors']:continue
            if value.get('user_id'):
                resulting[value['user_id']].update(role=value['role'],active=value['active'])
            elif value.get('create_access'):
                key='new:'+value['employee_ref'];resulting[key]=dict(role=value['role'],active=value['active'])
                new_access_rows.append(row)
        limit=state['_company_access'].get('user_limit')
        if limit is not None and sum(bool(u.get('active')) for u in resulting.values())>int(limit):
            for row in new_access_rows:
                if row['normalized'].get('active'):issue(row,'user_limit_exceeded','conflict')
        if not any(u.get('role')=='admin' and u.get('active') for u in resulting.values()):
            for row in output:
                value=row['normalized']
                if row['sheet']=='Сотрудники' and (value.get('user_id') or value.get('create_access')):issue(row,'last_admin_conflict','conflict')
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
        public_rows=[]
        for source in plan['rows']:
            item=dict(source);normalized=dict(item.get('normalized') or {})
            if normalized.get('initial_pin'):normalized['initial_pin']='***'
            item['normalized']=normalized;public_rows.append(item)
        public_plan=dict(plan,rows=public_rows)
        return dict(public_plan,import_id=import_id,template_version=TEMPLATE_VERSION,checksum=parsed['checksum_sha256'],preview_token=self.token(claims),expires_at=claims['expires'])
