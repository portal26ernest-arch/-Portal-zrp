"""Explicit adapter between canonical employee IDs and retained legacy columns.

Runtime APIs use employee_id. Historical tables still key employees by
telegram_id, so the only code allowed to read/translate those values lives here.
When the additive identity map is present, lookups are company-scoped and
fail closed for unmapped IDs. Older schemas retain a temporary compatibility
mode until the additive Stage 6 migration is applied.
"""


def _has_table(connection, name):
    dialect = getattr(connection, 'dialect', 'sqlite')
    if dialect == 'postgresql':
        return bool(connection.execute(
            'SELECT 1 FROM information_schema.tables '
            'WHERE table_schema=current_schema() AND table_name=?', (name,)
        ).fetchone())
    return bool(connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone())


def canonical_employee_id(connection, company_id, legacy_id):
    """Resolve a stored legacy employee key to the canonical runtime ID."""
    if legacy_id is None:
        return None
    try:
        legacy_id = int(legacy_id)
    except (TypeError, ValueError):
        return None
    if not _has_table(connection, 'payroll_employee_identities'):
        # Explicit pre-Stage-6 compatibility only; APIs still name it employee_id.
        return legacy_id
    row = connection.execute('''
        SELECT i.employee_id
        FROM payroll_employee_identities i
        JOIN employees e ON e.company_id=i.company_id
                        AND e.telegram_id=i.legacy_employee_id
        WHERE i.company_id=? AND i.legacy_employee_id=?
    ''', (company_id, legacy_id)).fetchone()
    return int(row[0]) if row else None


def legacy_employee_id(connection, company_id, employee_id):
    """Translate a canonical runtime ID only for a legacy-table operation."""
    if employee_id is None:
        return None
    try:
        employee_id = int(employee_id)
    except (TypeError, ValueError):
        return None
    if not _has_table(connection, 'payroll_employee_identities'):
        # Explicit pre-Stage-6 compatibility only; no caller may use this as API identity.
        return employee_id
    row = connection.execute('''
        SELECT i.legacy_employee_id
        FROM payroll_employee_identities i
        JOIN employees e ON e.company_id=i.company_id
                        AND e.telegram_id=i.legacy_employee_id
        WHERE i.company_id=? AND i.employee_id=?
    ''', (company_id, employee_id)).fetchone()
    return int(row[0]) if row else None


def employee_id_for_user(connection, company_id, user):
    """Return canonical identity for an authenticated legacy-linked user."""
    if user is None:
        return None
    def value(key):
        try:return user[key]
        except (KeyError,IndexError):return None
    if value('employee_id') is not None:
        identity=int(value('employee_id'))
        return identity if legacy_employee_id(connection,company_id,identity) is not None else None
    # telegram_id access is intentionally confined to this compatibility adapter.
    return canonical_employee_id(connection, company_id, value('telegram_id')) # employee_id compatibility boundary


def canonical_user_payload(connection, company_id, body, allow_legacy_bridge=False):
    """Normalize legacy-linked account payloads into the canonical employee_id field."""
    result=dict(body)
    if 'telegram_id' in result: # employee_id compatibility boundary
        if not allow_legacy_bridge:raise ValueError('Используйте employee_id')
        legacy=result.pop('telegram_id');mapped=canonical_employee_id(connection,company_id,legacy)
        if 'employee_id' in result and result['employee_id']!=mapped:raise ValueError('Конфликт employee_id')
        result['employee_id']=mapped
    return result


def canonical_settlement_payload(repository, body):
    """Compatibility adapter for old settlement callers; service receives employee_id only."""
    result=dict(body)
    if 'telegram_id' in result: # employee_id settlement bridge
        legacy=result.pop('telegram_id');mapped=repository.employee_identity_for_legacy(legacy)
        if result.get('employee_id') not in (None,mapped):raise ValueError('Идентификаторы сотрудника не совпадают')
        result['employee_id']=mapped
    return result


def canonical_settlement_query(repository, query):
    result={key:list(values) for key,values in query.items()}
    if 'telegram_id' in result: # employee_id settlement bridge
        legacy=result.pop('telegram_id')[0];mapped=repository.employee_identity_for_legacy(legacy)
        if result.get('employee_id') not in (None,[str(mapped)]):raise ValueError('Идентификаторы сотрудника не совпадают')
        result['employee_id']=[str(mapped)]
    return result


def public_user_record(user):
    """Drop the retained account-column name from a public employee_id response."""
    result=dict(user);result.pop('telegram_id',None);return result


def legacy_employee_id_for_user(connection, company_id, user):
    """Resolve an authenticated user to a legacy key at the storage boundary."""
    identity = employee_id_for_user(connection, company_id, user)
    return legacy_employee_id(connection, company_id, identity)


def _columns(connection, table):
    dialect=getattr(connection,'dialect','sqlite')
    if dialect=='postgresql':
        return {row[0] for row in connection.execute(
            'SELECT column_name FROM information_schema.columns '
            'WHERE table_schema=current_schema() AND table_name=?',(table,)).fetchall()}
    return {row[1] for row in connection.execute('PRAGMA table_info('+table+')').fetchall()}


def _has_table(connection, name):
    return bool(connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone()) if getattr(connection,'dialect','sqlite')!='postgresql' else bool(connection.execute('SELECT 1 FROM information_schema.tables WHERE table_schema=current_schema() AND table_name=?',(name,)).fetchone())


def sync_employee_mappings(connection, company_id):
    if not _has_table(connection,'payroll_employee_identities') or not _has_table(connection,'employees'):return
    # The legacy telegram_id column is kept here as an explicit employee_id migration bridge.
    connection.execute('''INSERT INTO payroll_employee_identities(company_id,legacy_employee_id) -- employee_id adapter
        SELECT e.company_id,e.telegram_id FROM employees e WHERE e.company_id=? AND NOT EXISTS
        (SELECT 1 FROM payroll_employee_identities i WHERE i.company_id=e.company_id AND i.legacy_employee_id=e.telegram_id) -- employee_id adapter
        ORDER BY e.telegram_id''',(company_id,))


def employee_catalog(connection, company_id):
    if not _has_table(connection,'employees'):return []
    cols=_columns(connection,'employees')
    scoped='company_id' in cols
    if not _has_table(connection,'payroll_employee_identities'):
        rows=connection.execute('SELECT telegram_id,full_name,username FROM employees'+(' WHERE company_id=?' if scoped else '')+' ORDER BY full_name',((company_id,) if scoped else ())).fetchall() # employee_id compatibility projection
        return [dict(employee_id=row[0],full_name=row[1],username=row[2]) for row in rows]
    # P1 schema bridge: only this mapper projects a retained telegram_id column to employee_id.
    rows=connection.execute('''SELECT i.employee_id,e.full_name,e.username FROM payroll_employee_identities i
        JOIN employees e ON e.company_id=i.company_id AND e.telegram_id=i.legacy_employee_id -- employee_id adapter
        WHERE i.company_id=? ORDER BY e.full_name,i.employee_id''',(company_id,)).fetchall()
    return [dict(employee_id=row[0],full_name=row[1],username=row[2]) for row in rows]


def user_catalog(connection, company_id):
    cols=_columns(connection,'app_users')
    if not _has_table(connection,'payroll_employee_identities'):
        field='telegram_id' if 'telegram_id' in cols else 'NULL'
        rows=connection.execute(f'SELECT id,display_name,role,{field},active,company_id FROM app_users WHERE company_id=?',(company_id,)).fetchall()
        return [dict(zip(('id','display_name','role','employee_id','active','company_id'),row)) for row in rows]
    rows=connection.execute('''SELECT u.id,u.display_name,u.role,i.employee_id,u.active,u.company_id
        FROM app_users u LEFT JOIN payroll_employee_identities i
        ON i.company_id=u.company_id AND i.legacy_employee_id=u.telegram_id -- employee_id adapter
        LEFT JOIN employees e ON e.company_id=i.company_id AND e.telegram_id=i.legacy_employee_id
        WHERE u.company_id=? AND (i.employee_id IS NULL OR e.telegram_id IS NOT NULL)''',(company_id,)).fetchall()
    return [dict(zip(('id','display_name','role','employee_id','active','company_id'),row)) for row in rows]


def assignment_catalog(connection, company_id):
    cols=_columns(connection,'manager_client_assignments')
    if not cols:return []
    cursor=connection.execute('SELECT * FROM manager_client_assignments WHERE company_id=?',(company_id,)) if 'company_id' in cols else connection.execute('SELECT * FROM manager_client_assignments')
    names=[item[0] for item in cursor.description];rows=cursor.fetchall()
    result=[]
    for row in rows:
        item=dict(zip(names,row));legacy=item.pop('telegram_id',None)
        item['employee_id']=canonical_employee_id(connection,company_id,legacy)
        result.append(item)
    return result


def assigned_client_ids(connection, company_id, employee_id):
    legacy=legacy_employee_id(connection,company_id,employee_id)
    if legacy is None:return set()
    cols=_columns(connection,'manager_client_assignments');scope='company_id=? AND ' if 'company_id' in cols else ''
    params=(company_id,legacy) if scope else (legacy,)
    rows=connection.execute('SELECT client_id FROM manager_client_assignments WHERE '+scope+'telegram_id=? AND active=1',params).fetchall() # employee_id adapter
    return {int(row[0]) for row in rows}


def employee_exists(connection, company_id, employee_id):
    legacy=legacy_employee_id(connection,company_id,employee_id)
    if legacy is None:return False
    cols=_columns(connection,'employees');scope='company_id=? AND ' if 'company_id' in cols else ''
    params=(company_id,legacy) if scope else (legacy,)
    return bool(connection.execute('SELECT 1 FROM employees WHERE '+scope+'telegram_id=?',params).fetchone()) # employee_id adapter


def create_employee_card(connection, company_id, display_name, username):
    cols=_columns(connection,'employees');scope=' WHERE company_id=?' if 'company_id' in cols else '';params=(company_id,) if scope else ()
    row=connection.execute('SELECT MIN(telegram_id) FROM employees'+scope+(' AND' if scope else ' WHERE')+' telegram_id<0',params).fetchone() # employee_id adapter
    legacy=min((row[0] or 0)-1,-1);values={'telegram_id':legacy,'full_name':display_name,'username':username,'company_id':company_id}
    values={key:value for key,value in values.items() if key in cols}
    connection.execute('INSERT INTO employees('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',tuple(values.values()))
    sync_employee_mappings(connection,company_id)
    return canonical_employee_id(connection,company_id,legacy)


def update_employee_card(connection, company_id, employee_id, display_name, username):
    """Update a profile through its company-scoped canonical employee ID."""
    legacy=legacy_employee_id(connection,company_id,employee_id)
    if legacy is None:raise ValueError('employee_id не найден в этой компании')
    cols=_columns(connection,'employees');scope=' AND company_id=?' if 'company_id' in cols else ''
    params=(display_name,username,legacy,company_id) if scope else (display_name,username,legacy)
    cursor=connection.execute('UPDATE employees SET full_name=?,username=? WHERE telegram_id=?'+scope,params)
    if cursor.rowcount!=1:raise ValueError('employee_id не найден в этой компании')
    return employee_id


def write_user_account(connection, company_id, user_id, values, salt, digest, updated_at):
    employee_id=values.get('employee_id')
    legacy=legacy_employee_id(connection,company_id,employee_id)
    if employee_id is not None and legacy is None:raise ValueError('Сотрудник employee_id не найден в этой компании')
    if user_id:
        connection.execute('UPDATE app_users SET username=?,display_name=?,role=?,telegram_id=?,active=?,pin_salt=?,pin_hash=?,updated_at=? WHERE id=?', # employee_id adapter
            (values['username'],values['display_name'],values['role'],legacy,values['active'],salt,digest,updated_at,user_id))
        connection.execute('DELETE FROM app_sessions WHERE user_id=?',(user_id,))
    else:
        user_id=connection.execute('INSERT INTO app_users(username,display_name,role,telegram_id,active,pin_salt,pin_hash,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)', # employee_id adapter
            (values['username'],values['display_name'],values['role'],legacy,values['active'],salt,digest,updated_at,updated_at)).lastrowid
    return user_id


def insert_unlinked_user(connection, username, display_name, salt, digest, now):
    cursor=connection.execute('INSERT INTO app_users(username,display_name,pin_salt,pin_hash,role,telegram_id,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)', # employee_id adapter
        (username,display_name,salt,digest,'admin',None,1,now,now))
    return cursor.lastrowid


def legacy_paid_period(connection, company_id, employee_id, period_start, period_end):
    legacy=legacy_employee_id(connection,company_id,employee_id)
    if legacy is None:return False
    return bool(connection.execute('SELECT 1 FROM payroll_payments WHERE telegram_id=? AND period_start=? AND period_end=? AND status=\'paid\'', # employee_id adapter
        (legacy,period_start,period_end)).fetchone())


def update_legacy_job_progress(connection, dialect, company_id, jobs, work_id, employee_id, quantity, timestamp, client_name, operation_name, product_name):
    legacy=legacy_employee_id(connection,company_id,employee_id)
    if legacy is None:raise ValueError('employee_id не связан с сотрудником этой компании')
    remaining=float(quantity)
    for job in jobs:
        if remaining<=1e-9:break
        capacity=max(float(job[1])-float(job[2]),0)
        if capacity<=0:continue
        add=min(capacity,remaining)
        sql='INSERT INTO production_job_progress(job_id,work_id,telegram_id,quantity,created_at) VALUES(?,?,?,?,?)' # employee_id adapter
        if dialect=='postgresql':sql+=' ON CONFLICT(company_id,job_id,work_id) DO NOTHING'
        else:sql='INSERT OR IGNORE INTO production_job_progress(job_id,work_id,telegram_id,quantity,created_at) VALUES(?,?,?,?,?)' # employee_id adapter
        connection.execute(sql,(job[0],work_id,legacy,add,timestamp))
        connection.execute("UPDATE production_jobs SET status='in_progress',updated_at=? WHERE id=? AND status='open'",(timestamp,job[0]))
        remaining-=add
        if float(job[2])+add+1e-9>=float(job[1]):connection.execute("UPDATE production_jobs SET status='done',completed_at=?,updated_at=? WHERE id=?",(timestamp,timestamp,job[0]))


def personal_work_rows(connection, company_id, employee_id, limit=50):
    legacy=legacy_employee_id(connection,company_id,employee_id)
    if legacy is None:return []
    rows=connection.execute('SELECT id,client,operation,quantity,rate,salary,created_at FROM work_log WHERE telegram_id=? ORDER BY id DESC LIMIT ?',(legacy,limit)).fetchall() # employee_id-scoped legacy ledger read
    names=('id','client','operation','quantity','rate','salary','created_at')
    return [dict(zip(names,row)) for row in rows]


def personal_payroll_totals(connection, company_id, employee_id, start, end):
    legacy=legacy_employee_id(connection,company_id,employee_id)
    if legacy is None:return (0,0,0)
    work=connection.execute('SELECT COALESCE(SUM(quantity),0),COALESCE(SUM(salary),0) FROM work_log WHERE telegram_id=? AND created_at BETWEEN ? AND ?',(legacy,start,end)).fetchone() # employee_id-scoped legacy ledger read
    paid=connection.execute('SELECT COALESCE(SUM(amount),0) FROM payroll_transactions WHERE telegram_id=? AND period_start=? AND period_end=?',(legacy,start,end)).fetchone()[0] if _has_table(connection,'payroll_transactions') else 0 # employee_id-scoped legacy ledger read
    return work[0],work[1],paid


def employee_work_summary(connection, company_id, employee_id, start, end):
    legacy=legacy_employee_id(connection,company_id,employee_id)
    if legacy is None:return dict(qty=0,salary=0,revenue=0,direct_cost=0)
    row=connection.execute('SELECT COALESCE(SUM(quantity),0),COALESCE(SUM(salary),0),COALESCE(SUM(revenue),0),COALESCE(SUM(direct_cost),0) FROM work_log WHERE telegram_id=? AND created_at BETWEEN ? AND ?',(legacy,start,end)).fetchone() # employee_id-scoped legacy ledger read
    return dict(zip(('qty','salary','revenue','direct_cost'),row))


def account_directory(connection, company_id):
    cols=_columns(connection,'app_users')
    if 'company_id' not in cols:return []
    # The raw account key is projected only here and immediately mapped to employee_id.
    rows=connection.execute('SELECT id,username,display_name,role,telegram_id AS employee_id,active,created_at FROM app_users WHERE company_id=? ORDER BY display_name',(company_id,)).fetchall()
    return [dict(id=row[0],username=row[1],display_name=row[2],role=row[3],employee_id=canonical_employee_id(connection,company_id,row[4]),active=row[5],created_at=row[6]) for row in rows]


def has_legacy_payroll(connection, company_id, period, employee_id):
    legacy=legacy_employee_id(connection,company_id,employee_id)
    if legacy is None:return False
    for table in ('payroll_transactions','payroll_payments'):
        if _has_table(connection,table) and connection.execute('SELECT 1 FROM '+table+' WHERE company_id=? AND telegram_id=? AND substr(period_start,1,10)<=? AND substr(period_end,1,10)>=? LIMIT 1',(company_id,legacy,period['period_end'],period['period_start'])).fetchone():return True # employee_id adapter
    return False


def write_legacy_work(connection, dialect, company_id, employee_id, user, client, operation, quantity, employee_rate, client_rate, created):
    legacy=legacy_employee_id(connection,company_id,employee_id)
    if legacy is None:raise ValueError('employee_id не связан с сотрудником этой компании')
    values=dict(company_id=company_id,telegram_id=legacy,username=user.get('username',''),first_name=user.get('display_name',''),client=client['name'],operation=operation['name'],quantity=quantity,rate=employee_rate/100,salary=quantity*employee_rate/100,client_rate=client_rate/100,revenue=quantity*client_rate/100,direct_cost=0,created_at=created.replace('T',' ')[:19])
    cols=_columns(connection,'work_log');values={key:value for key,value in values.items() if key in cols}
    cursor=connection.execute('INSERT INTO work_log('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')'+(' RETURNING id' if dialect=='postgresql' else ''),tuple(values.values()))
    return cursor.fetchone()[0] if dialect=='postgresql' else cursor.lastrowid


def linked_user_catalog(connection, company_id):
    return user_catalog(connection,company_id)


def payroll_identity_lookup(connection, company_id, identity, legacy=False):
    column='legacy_employee_id' if legacy else 'employee_id'
    cursor=connection.execute('SELECT i.employee_id,i.legacy_employee_id FROM payroll_employee_identities i JOIN employees e ON e.company_id=i.company_id AND e.telegram_id=i.legacy_employee_id WHERE i.company_id=? AND i.'+column+'=?',(company_id,identity))
    row=cursor.fetchone()
    if row is None:raise ValueError('Сотрудник не найден в этой компании')
    return dict(employee_id=row[0],legacy_employee_id=row[1])


def create_invited_account(connection, dialect, company_id, invite, pin_salt, pin_hash, now):
    employee_id=invite['employee_id']
    legacy=legacy_employee_id(connection,company_id,employee_id)
    if employee_id is not None and legacy is None:raise ValueError('employee_id не найден в компании приглашения')
    sql='INSERT INTO app_users(username,display_name,role,telegram_id,active,pin_salt,pin_hash,created_at,updated_at) VALUES(?,?,?,?,0,?,?,?,?)' # employee_id adapter
    if dialect=='postgresql':sql+=' RETURNING id'
    cursor=connection.execute(sql,(invite['username'],invite['display_name'],invite['role'],legacy,pin_salt,pin_hash,now,now))
    return cursor.fetchone()[0] if dialect=='postgresql' else cursor.lastrowid


def insert_legacy_work_values(connection, dialect, company_id, employee_id, values):
    legacy=legacy_employee_id(connection,company_id,employee_id)
    if legacy is None:raise ValueError('employee_id не связан с сотрудником этой компании')
    stored=dict(values);stored.pop('employee_id',None);stored['telegram_id']=legacy # employee_id retained-ledger projection
    cols=_columns(connection,'work_log');stored={key:value for key,value in stored.items() if key in cols}
    cursor=connection.execute('INSERT INTO work_log('+','.join(stored)+') VALUES('+','.join('?' for _ in stored)+')'+(' RETURNING id' if dialect=='postgresql' else ''),tuple(stored.values()))
    return cursor.fetchone()[0] if dialect=='postgresql' else cursor.lastrowid
