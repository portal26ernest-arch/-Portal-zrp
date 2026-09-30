"""Stage 3 activity and timing regressions; temporary tenant databases only."""
import json
import unittest
from datetime import datetime, timedelta, timezone

import test_production as base
from production_repository import Repository
from production_service import Production
import production_activity as activity

portal=base.portal

def leaf_values(value):
    if isinstance(value,dict):
        for item in value.values():yield from leaf_values(item)
    elif isinstance(value,(list,tuple)):
        for item in value:yield from leaf_values(item)
    else:yield value

class ActivityTest(unittest.TestCase):
    setUp=base.ProductionTest.setUp
    tearDown=base.ProductionTest.tearDown
    request=base.ProductionTest.request
    post=base.ProductionTest.post
    get=base.ProductionTest.get
    batch=base.ProductionTest.batch
    task=base.ProductionTest.task

    def test_login_history_permission_secrets_and_isolation(self):
        self.request('/api/login',body={'company_id':1,'username':'worker','pin':'wrong-secret-canary'},status=401)
        token=self.request('/api/login',body={'company_id':1,'username':'worker','pin':'1234'},extra_headers={'X-Portal-Client':'PC-Web'})['token']
        self.request('/api/login',body={'company_id':self.other,'username':'worker','pin':'5678'})
        rows=self.get('activity')['data']
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['result'],'success')
        self.assertEqual(rows[0]['client_type'],'PC-Web')
        self.assertNotIn('wrong-secret-canary',json.dumps(rows))
        self.assertNotIn(token,json.dumps(rows))
        self.get('activity',self.worker,status=403)
        self.post('permissions',{'user_id':self.worker_id,'permissions':{'access.history.read':True}})
        self.assertEqual(len(self.get('activity',self.worker)['data']),2)
        self.assertNotIn('5678',list(leaf_values(rows)))
        with portal.tenants.company_scope(1),portal.db() as conn:
            ledger=[json.loads(row[0]) for row in conn.execute("SELECT payload FROM portal_production WHERE kind IN ('access_events','access_sessions')")]
        values=list(leaf_values(ledger))
        for secret in ('wrong-secret-canary','1234','5678',token):self.assertNotIn(secret,values)
        sensitive={'pin','password','token','authorization','cookie','secret'}
        self.assertFalse(any(sensitive.intersection(map(str.lower,event)) for event in ledger))

    def test_presence_heartbeat_timeout_logout_and_multiple_sessions(self):
        first=self.request('/api/login',body={'username':'worker','pin':'1234'})['token']
        second=self.request('/api/login',body={'username':'worker','pin':'1234'})['token']
        def status():return next(x for x in self.get('presence')['data'] if x['user_id']==self.worker_id)
        self.assertEqual(status()['active_sessions'],2)
        self.request('/api/logout',first,{})
        self.assertEqual(status()['active_sessions'],1)
        self.request('/api/v3/heartbeat',second,{})
        self.assertTrue(status()['online'])
        with portal.tenants.company_scope(1),portal.db() as conn:
            repo=Repository(conn,1);now=datetime.fromisoformat(activity.utcnow())
            self.assertFalse(next(x for x in activity.presence(repo,{'id':self.admin_id,'role':'admin','company_id':1},(now+timedelta(minutes=4)).isoformat()) if x['user_id']==self.worker_id)['online'])
        self.request('/api/logout',second,{})
        self.assertFalse(status()['online'])
        self.request('/api/v3/heartbeat',second,{},status=401)

    def test_timed_task_pause_resume_finish_net_time_and_piecework(self):
        batch=self.batch();task=self.task(batch)
        at=datetime.now(timezone.utc).replace(tzinfo=None)+timedelta(minutes=1)
        with portal.tenants.company_scope(1),portal.db() as conn:
            repo=Repository(conn,1);user=dict(conn.execute('SELECT * FROM app_users WHERE id=?',(self.worker_id,)).fetchone());user['company_id']=1
            user['employee_id']=repo.employee_identity_for_user(user)
            clock=[at];service=Production(repo,user,lambda:clock[0].isoformat(timespec='microseconds'))
            timer=service.timer({'event':'start','task_id':task['id']})
            clock[0]+=timedelta(minutes=20);service.timer({'event':'pause','session_id':timer['id']})
            clock[0]+=timedelta(minutes=10);service.timer({'event':'resume','session_id':timer['id']})
            clock[0]+=timedelta(minutes=10);done=service.timer({'event':'finish','session_id':timer['id'],'quantity':5})
            work=repo.get('works',done['work_id']);conn.commit()
        self.assertEqual((done['calendar_seconds'],done['net_seconds']),(2400,1800))
        self.assertEqual(len(done['pauses']),1)
        self.assertEqual((work['quantity'],work['units_per_hour'],work['salary']),(5,10,1000))
        self.assertEqual(self.get('tasks',self.worker)['data'][0]['done'],5)
        self.assertEqual(self.get('works',self.worker)['data'][0]['salary'],1000)

    def test_timing_permissions_and_invalid_transitions(self):
        batch=self.batch();task=self.task(batch)
        started=self.post('timers',{'event':'start','task_id':task['id']},self.worker)['data']
        self.post('timers',{'event':'start','task_id':task['id']},self.worker,status=400)
        self.post('timers',{'event':'pause','session_id':started['id']},self.admin,status=403)
        self.post('timers',{'event':'pause','session_id':started['id']},self.worker)
        self.post('timers',{'event':'pause','session_id':started['id']},self.worker,status=400)
        self.post('timers',{'event':'resume','session_id':started['id']},self.worker)
        self.post('timers',{'event':'finish','session_id':started['id'],'quantity':1},self.worker)
        self.post('timers',{'event':'resume','session_id':started['id']},self.worker,status=400)

if __name__=='__main__':unittest.main()
