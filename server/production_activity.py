"""Authentication history and presence, scoped by authenticated company.

No credential or bearer token is written to this ledger. The legacy auth table
continues to authenticate; its opaque activity ID links a live session here.
"""
from session_security import storage_key, authentication_lock
import uuid
from datetime import datetime, timedelta
from production_repository import utcnow
import production_permissions as rights

def client_type(headers):
    value=headers.get('X-Portal-Client','Android')
    return value if value in ('Android','PC-Web') else 'Unknown'

def configuration(repo):
    settings=repo.get('settings','control',False) or {}
    heartbeat=settings.get('presence_heartbeat_seconds',60)
    timeout=settings.get('presence_timeout_seconds',180)
    return heartbeat,timeout

def login(repo, username, user_id, successful, kind, token=None, at=None):
    """Called in the auth transaction after tenant verification."""
    at=at or utcnow()
    activity_id=str(uuid.uuid4()) if successful else None
    repo.insert('access_events',dict(event='login',result='success' if successful else 'denied',
        user_id=user_id,client_type=kind,at=at,activity_id=activity_id))
    if successful:
        repo.insert('access_sessions',dict(user_id=user_id,client_type=kind,signed_in_at=at,
            last_activity_at=at,ended_at=None,end_reason=None),activity_id)
        repo.sql('UPDATE app_sessions SET portal_activity_id=? WHERE token=? AND company_id=?',
                 (activity_id,storage_key(token),repo.company_id))
    return activity_id

def _linked(repo,token):
    row=repo.sql('SELECT portal_activity_id FROM app_sessions WHERE token=? AND company_id=?',
                 (storage_key(token),repo.company_id)).fetchone()
    return repo.get('access_sessions',row[0],False) if row and row[0] else None

def touch(repo,token,user,force=False,at=None):
    if not repo.ready():return None
    authentication_lock(repo.conn)
    # A request authenticated just before revocation must not recreate presence.
    if not repo.sql('SELECT 1 FROM app_sessions WHERE token=? AND company_id=? AND expires_at>=?',
                    (storage_key(token),repo.company_id,datetime.now().strftime('%Y-%m-%d %H:%M:%S'))).fetchone():return None
    at=at or utcnow();session=_linked(repo,token)
    if not session:
        # Historic session predates the migration. Mark first observed activity,
        # not a fabricated successful login time.
        session=repo.insert('access_sessions',dict(user_id=user['id'],client_type='Unknown',signed_in_at=None,
            last_activity_at=at,ended_at=None,end_reason=None))
        repo.sql('UPDATE app_sessions SET portal_activity_id=? WHERE token=? AND company_id=?',
                 (session['id'],storage_key(token),repo.company_id))
    if session['ended_at']:return session
    heartbeat,_=configuration(repo)
    if force or (datetime.fromisoformat(at)-datetime.fromisoformat(session['last_activity_at'])).total_seconds()>=heartbeat:
        session['last_activity_at']=at;repo.update('access_sessions',session)
    return session

def logout(repo,token,user,at=None):
    authentication_lock(repo.conn)
    at=at or utcnow();session=_linked(repo,token) if repo.ready() else None
    if session and not session['ended_at']:
        session.update(ended_at=at,end_reason='logout',last_activity_at=at)
        repo.update('access_sessions',session)
        repo.insert('access_events',dict(event='logout',result='success',user_id=user['id'],
            client_type=session['client_type'],at=at,activity_id=session['id']))
    repo.sql('DELETE FROM app_sessions WHERE token=? AND company_id=?',(storage_key(token),repo.company_id))

def presence(repo,user,at=None):
    if not ({'users.manage','access.history.read'} & rights.effective(repo,user)):
        raise PermissionError('Нет права просмотра сотрудников')
    at=at or utcnow();_,timeout=configuration(repo)
    sessions=repo.list('access_sessions');result=[]
    for employee in repo.catalog('users'):
        own=[s for s in sessions if s['user_id']==employee['id']]
        active=[s for s in own if s['ended_at'] is None and
                (datetime.fromisoformat(at)-datetime.fromisoformat(s['last_activity_at'])).total_seconds()<=timeout]
        last=max((s['last_activity_at'] for s in own),default=None)
        result.append(dict(user_id=employee['id'],display_name=employee['display_name'],
                           online=bool(active),last_activity_at=last,active_sessions=len(active)))
    return result

def history(repo,user,limit=100):
    rights.require(repo,user,'access.history.read')
    if type(limit) is not int or not 1<=limit<=200:raise ValueError('Неверный размер страницы')
    users={u['id'] for u in repo.catalog('users')}
    rows=[e for e in repo.list('access_events') if e['user_id'] in users or e['user_id'] is None]
    return list(reversed(rows[-limit:]))
