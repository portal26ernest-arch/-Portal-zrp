"""Company-scoped one-time invitations for the active PORTAL account model."""
import hashlib
import re
import secrets
import sys
import uuid
from datetime import datetime, timedelta

from production_repository import Repository, utcnow
from employee_identity import create_invited_account, create_employee_card
from employee_names import persist_known_employee_aliases

TABLE = 'portal_access_invites'
ROLES = {'admin', 'director', 'manager', 'packer', 'shift', 'accountant'}
PUBLIC = ('id', 'company_id', 'created_by', 'created_at', 'expires_at', 'status',
          'role', 'username', 'display_name', 'employee_id', 'user_id', 'accepted_at',
          'decided_at', 'decided_by')

def _portal_app():
    app=sys.modules.get('portal_app_server')
    if app is not None:return app
    # The legacy unit fixture loads the module under a spec name rather than
    # registering it as portal_app_server.
    return sys.modules['test_portal_app_server'].portal


def _row(cursor, company_id, identity):
    row = cursor.execute('SELECT '+','.join(PUBLIC)+',token_hash FROM '+TABLE+
                         ' WHERE company_id=? AND id=?', (company_id, identity)).fetchone()
    return dict(zip(PUBLIC+('token_hash',), row)) if row else None


def safe(row):
    return {key: row[key] for key in PUBLIC}


def _stamp(value):
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo:
            raise ValueError()
        return parsed.isoformat(timespec='seconds')
    except (TypeError, ValueError):
        raise ValueError('Срок приглашения должен быть ISO 8601 без часового пояса')


def create(conn, repo, actor, body, company):
    if set(body) - {'action', 'request_id', 'role', 'username', 'display_name', 'employee_id', 'expires_at'}:
        raise ValueError('Неизвестные параметры приглашения')
    request_id = body.get('request_id')
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128 or request_id.strip() != request_id:
        raise ValueError('request_id: от 1 до 128 символов')
    old = conn.execute('SELECT id FROM '+TABLE+' WHERE company_id=? AND request_id=?',
                       (repo.company_id, request_id)).fetchone()
    if old:
        row = _row(conn, repo.company_id, old[0])
        return dict(invite=safe(row), token=None, replay=True)
    role = body.get('role', 'packer')
    if role not in ROLES:
        raise ValueError('Неизвестная роль приглашённого сотрудника')
    username = body.get('username')
    display_name = body.get('display_name')
    for value, label in ((username, 'Логин'), (display_name, 'Имя')):
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 100:
            raise ValueError(label+': укажите от 1 до 100 символов')
    username, display_name = username.strip(), display_name.strip()
    employee_id = body.get('employee_id')
    if employee_id is not None:
        if type(employee_id) is not int:
            raise ValueError('employee_id должен быть целым числом')
        _portal_app().validate_employee(conn, employee_id)
    if conn.execute('SELECT 1 FROM app_users WHERE lower(username)=lower(?) AND active=1', (username,)).fetchone():
        raise ValueError('Активная учётная запись с таким логином уже есть')
    expiry = _stamp(body.get('expires_at') or (datetime.now()+timedelta(days=7)).isoformat(timespec='seconds'))
    if expiry <= datetime.now().isoformat(timespec='seconds'):
        raise ValueError('Срок приглашения должен быть в будущем')
    identity = str(uuid.uuid4())
    raw_token = str(repo.company_id)+'.'+secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw_token.encode()).hexdigest()
    conn.execute('''INSERT INTO portal_access_invites
      (company_id,id,token_hash,created_by,created_at,expires_at,status,role,username,display_name,employee_id,request_id)
      VALUES(?,?,?,?,?,?,'pending',?,?,?,?,?)''',
      (repo.company_id, identity, digest, actor['id'], utcnow(), expiry, role, username,
       display_name, employee_id, request_id))
    if not actor.get('technical_owner'):
        repo.audit(actor, 'access_invite.created', identity, actor_kind='user')
    return dict(invite=safe(_row(conn, repo.company_id, identity)), token=raw_token, replay=False)


def accept(conn, repo, token, pin):
    if not isinstance(token, str) or len(token) > 180 or not re.fullmatch(r'[1-9][0-9]{0,17}\.[A-Za-z0-9_-]{32,100}', token):
        raise PermissionError('Приглашение недействительно')
    if not isinstance(pin, str) or not 4 <= len(pin) <= 128:
        raise ValueError('PIN должен содержать от 4 до 128 символов')
    digest = hashlib.sha256(token.encode()).hexdigest()
    row = conn.execute('SELECT '+','.join(PUBLIC)+',token_hash FROM '+TABLE+
                       ' WHERE company_id=? AND token_hash=?', (repo.company_id, digest)).fetchone()
    if not row:
        raise PermissionError('Приглашение недействительно')
    invite = dict(zip(PUBLIC+('token_hash',), row))
    if invite['status'] == 'accepted':
        return dict(status='pending_approval', invite_id=invite['id'])
    if invite['status'] != 'pending':
        raise PermissionError('Приглашение уже недоступно')
    if invite['expires_at'] <= datetime.now().isoformat(timespec='seconds'):
        conn.execute('UPDATE '+TABLE+" SET status='expired' WHERE company_id=? AND id=?", (repo.company_id, invite['id']))
        repo.audit(None, 'access_invite.expired', invite['id'], actor_kind='system')
        return dict(status='expired', invite_id=invite['id'])
    if conn.execute('SELECT 1 FROM app_users WHERE lower(username)=lower(?)', (invite['username'],)).fetchone():
        raise ValueError('Логин уже занят; обратитесь к администратору компании')
    employee_id = invite['employee_id']
    if employee_id is None:
        employee_id = create_employee_card(conn,repo.company_id,invite['display_name'],invite['username'])
        persist_known_employee_aliases(repo,employee_id,invite['display_name'])
    app=_portal_app()
    salt, pin_hash = app.hash_pin(pin)
    user_id=create_invited_account(conn,repo.dialect,repo.company_id,dict(invite,employee_id=employee_id),salt,pin_hash,app.now_text())
    conn.execute("UPDATE "+TABLE+" SET status='accepted',user_id=?,accepted_at=? WHERE company_id=? AND id=? AND status='pending'",
                 (user_id, utcnow(), repo.company_id, invite['id']))
    repo.audit(None, 'access_invite.accepted', invite['id'], actor_kind='invitee')
    return dict(status='pending_approval', invite_id=invite['id'])


def list_invites(conn, company_id, page=1, limit=50, status='all'):
    if type(page) is not int or not 1 <= page <= 10000 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Некорректная пагинация')
    if status not in ('all', 'pending', 'accepted', 'approved', 'revoked', 'expired', 'rejected'):
        raise ValueError('Некорректный статус приглашения')
    where='company_id=?'; args=[company_id]
    if status!='all':
        where+=' AND status=?';args.append(status)
    total=conn.execute('SELECT COUNT(*) FROM '+TABLE+' WHERE '+where, tuple(args)).fetchone()[0]
    rows=conn.execute('SELECT '+','.join(PUBLIC)+' FROM '+TABLE+' WHERE '+where+
                       ' ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?',tuple(args+[limit,(page-1)*limit])).fetchall()
    return dict(items=[dict(zip(PUBLIC,row)) for row in rows],page=page,limit=limit,total=total)


def decide(conn, repo, actor, identity, action):
    if action not in ('approve', 'revoke', 'reject'):
        raise ValueError('Действие недоступно')
    invite = _row(conn, repo.company_id, identity)
    if not invite:
        raise ValueError('Приглашение не найдено')
    if action == 'approve':
        if invite['status'] == 'approved':
            return safe(invite)
        if invite['status'] != 'accepted' or not invite['user_id']:
            raise ValueError('Нет принятого запроса на подтверждение')
        _portal_app().save_user({'active': 1}, invite['user_id'])
        status='approved'
    else:
        if invite['status'] not in ('pending', 'accepted'):
            if invite['status'] in ('revoked', 'rejected'):
                return safe(invite)
            raise ValueError('Приглашение уже обработано')
        status='revoked' if action=='revoke' else 'rejected'
    conn.execute('UPDATE '+TABLE+' SET status=?,decided_at=?,decided_by=? WHERE company_id=? AND id=?',
                 (status, utcnow(), actor['id'], repo.company_id, identity))
    if not actor.get('technical_owner'):
        repo.audit(actor, 'access_invite.'+status, identity, actor_kind='user')
    return safe(_row(conn, repo.company_id, identity))
