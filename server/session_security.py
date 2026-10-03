"""Shared tenant session storage and transaction-scoped revocation boundary."""
import hashlib
import re

_STORAGE_KEY = re.compile(r'h1:[0-9a-f]{64}\Z')

def authentication_lock(connection):
    """Use the existing tenant transaction lock before reading auth state."""
    if getattr(connection,'dialect','sqlite')=='postgresql' or not getattr(connection,'in_transaction',False):
        connection.execute('BEGIN IMMEDIATE')

def storage_key(token):
    """Never accept a DB digest as a bearer; hash the client token exactly once."""
    if not isinstance(token,str):raise ValueError('Invalid session token')
    return 'h1:'+hashlib.sha256(token.encode('utf-8')).hexdigest()

def migrate_tokens(connection,company_id):
    """Explicit operator migration; preserve client tokens without raw fallback."""
    from employee_identity import _columns
    authentication_lock(connection)
    cols=_columns(connection,'app_sessions')
    if not cols:return
    clause=' WHERE company_id=?' if 'company_id' in cols else ''
    scope=(company_id,) if clause else ()
    for row in connection.execute('SELECT token FROM app_sessions'+clause,scope).fetchall():
        token=row[0]
        if _STORAGE_KEY.fullmatch(token):continue
        if token.startswith('h1:'):raise RuntimeError('Invalid stored session key')
        connection.execute('UPDATE app_sessions SET token=? WHERE token=?'+(' AND company_id=?' if clause else ''),
                           (storage_key(token),token)+scope)

def revoke_sessions(connection,company_id,*,user_id=None,keep_token=None,before=None,
                    reason='access_changed',actor_id=None):
    """Close linked history and delete auth rows in the caller's transaction."""
    from employee_identity import _columns
    authentication_lock(connection)
    cols=_columns(connection,'app_sessions')
    if not cols:return 0
    conditions=[];args=[]
    if 'company_id' in cols:conditions.append('company_id=?');args.append(company_id)
    if user_id is not None:conditions.append('user_id=?');args.append(user_id)
    if keep_token is not None:conditions.append('token<>?');args.append(storage_key(keep_token))
    if before is not None:conditions.append('expires_at<?');args.append(before)
    if not conditions:raise ValueError('Session revocation requires a scope')
    where=' AND '.join(conditions)
    linked='portal_activity_id' in cols
    fields='token,user_id'+(',portal_activity_id' if linked else '')
    rows=connection.execute('SELECT '+fields+' FROM app_sessions WHERE '+where,tuple(args)).fetchall()
    if linked and rows:
        from production_repository import Repository,utcnow
        repo=Repository(connection,company_id)
        if repo.ready():
            at=utcnow()
            for row in rows:
                activity_id=row[2]
                session=repo.get('access_sessions',activity_id,False) if activity_id else None
                if session and not session['ended_at']:
                    session.update(ended_at=at,end_reason=reason,last_activity_at=at,ended_by=actor_id)
                    repo.update('access_sessions',session)
                repo.insert('access_events',dict(event='revoke',result='success',user_id=row[1],
                    actor_id=actor_id,reason=reason,client_type=session['client_type'] if session else 'Unknown',
                    at=at,activity_id=activity_id))
    connection.execute('DELETE FROM app_sessions WHERE '+where,tuple(args))
    return len(rows)
