"""Session hashing and revocation regression on disposable tenant fixtures."""
import unittest
import test_production as base
from production_repository import Repository
from session_security import storage_key,migrate_tokens,revoke_sessions
import production_activity as activity
portal=base.portal

class SessionSecurityTest(unittest.TestCase):
    setUp=base.ProductionTest.setUp
    tearDown=base.ProductionTest.tearDown
    request=base.ProductionTest.request
    post=base.ProductionTest.post
    get=base.ProductionTest.get

    def login(self):
        return self.request('/api/login',body={'username':'worker','pin':'1234'})['token']

    def test_only_digest_is_stored_and_digest_cannot_authenticate(self):
        token=self.login()
        with portal.db() as conn:
            keys=[row[0] for row in conn.execute('SELECT token FROM app_sessions')]
        self.assertIn(storage_key(token),keys);self.assertNotIn(token,keys)
        self.assertTrue(all(key.startswith('h1:') and len(key)==67 for key in keys))
        self.request('/api/me',storage_key(token),status=401)
        self.assertEqual(self.request('/api/me',token)['user']['id'],self.worker_id)
        self.request('/api/logout',token,{})
        self.request('/api/me',token,status=401)

    def test_explicit_legacy_conversion_preserves_client_token_and_is_idempotent(self):
        raw='prefixless-fixture-session'
        with portal.db() as conn:
            conn.execute('INSERT INTO app_sessions(token,user_id,created_at,expires_at,company_id) VALUES(?,?,?,?,?)',
                         (raw,self.worker_id,'2026-01-01','2099-01-01',1))
            migrate_tokens(conn,1);migrate_tokens(conn,1)
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM app_sessions WHERE token=?',(raw,)).fetchone()[0],0)
        self.assertEqual(self.request('/api/me',raw)['user']['id'],self.worker_id)

    def test_pin_change_keeps_current_session_and_closes_other_history(self):
        current=self.login();other=self.login()
        self.request('/api/me/pin',current,{'current_pin':'1234','new_pin':'synthetic-new-pin-only'})
        self.request('/api/me',current);self.request('/api/me',other,status=401)
        with portal.db() as conn:
            repo=Repository(conn,1);sessions=repo.list('access_sessions');events=repo.list('access_events')
        self.assertEqual(sum(s['ended_at'] is None for s in sessions),1)
        self.assertTrue(any(s['end_reason']=='pin_changed' for s in sessions))
        self.assertTrue(any(e['event']=='revoke' and e['reason']=='pin_changed' for e in events))
        self.assertNotIn(other,str(events));self.assertNotIn(current,str(events))

    def test_account_edit_revokes_auth_and_presence_atomically(self):
        token=self.login()
        self.request('/api/users/'+str(self.worker_id),self.admin,{'active':0})
        self.request('/api/me',token,status=401)
        with portal.db() as conn:
            repo=Repository(conn,1)
            self.assertTrue(all(s['ended_at'] and s['end_reason']=='access_changed' for s in repo.list('access_sessions') if s['user_id']==self.worker_id))
            self.assertTrue(any(e['reason']=='access_changed' for e in repo.list('access_events') if e['event']=='revoke'))

    def test_expiry_closes_activity_without_cross_tenant_deletion(self):
        token=self.login()
        with portal.db() as conn:
            conn.execute('UPDATE app_sessions SET expires_at=? WHERE token=?',('2000-01-01',storage_key(token)))
            portal.create_session(conn,self.admin_id)
            ended=Repository(conn,1).list('access_sessions')
        self.assertTrue(any(s['end_reason']=='expired' for s in ended))
        self.request('/api/me',token,status=401)
        self.request('/api/me',self.other_admin)

    def test_late_heartbeat_does_not_recreate_revoked_presence(self):
        token=self.login()
        with portal.db() as conn:
            repo=Repository(conn,1)
            revoke_sessions(conn,1,user_id=self.worker_id,reason='fixture_revoke')
            before=len(repo.list('access_sessions'))
            self.assertIsNone(activity.touch(repo,token,{'id':self.worker_id},force=True))
            self.assertEqual(len(repo.list('access_sessions')),before)
            self.assertTrue(all(s['ended_at'] for s in repo.list('access_sessions')))

    def test_revocation_rollback_preserves_auth_and_history(self):
        token=self.login()
        with self.assertRaises(RuntimeError):
            with portal.db() as conn:
                revoke_sessions(conn,1,user_id=self.worker_id,reason='fixture_rollback')
                raise RuntimeError('synthetic rollback')
        self.request('/api/me',token)
        with portal.db() as conn:
            self.assertTrue(all(s['ended_at'] is None for s in Repository(conn,1).list('access_sessions')))

if __name__=='__main__':unittest.main()
