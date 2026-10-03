"""Login boundary tests on the existing synthetic in-memory HTTP fixture."""
import unittest
from unittest.mock import patch
import test_portal_app_server as base
from login_throttle import LoginLimiter,client_ip
portal=base.portal

class LimiterUnitTest(unittest.TestCase):
    def test_window_and_capacity_do_not_evict_active_lockout(self):
        now=[0.0];limiter=LoginLimiter(lambda:now[0],max_keys=1)
        self.assertEqual(limiter.consume('a',2,10),0)
        self.assertEqual(limiter.consume('a',2,10),0)
        self.assertEqual(limiter.consume('a',2,10),10)
        self.assertEqual(limiter.consume('b',2,10),10)
        self.assertEqual(limiter.consume('a',2,10),10)
        now[0]=10
        self.assertEqual(limiter.consume('b',2,10),0)

    def test_proxy_headers_need_explicit_peer_trust(self):
        headers={'X-Real-IP':'192.0.2.10'}
        self.assertEqual(client_ip('127.0.0.1',headers),'127.0.0.1')
        self.assertEqual(client_ip('198.51.100.5',headers,('127.0.0.1',)),'198.51.100.5')
        self.assertEqual(client_ip('127.0.0.1',headers,('127.0.0.1',)),'192.0.2.10')
        self.assertEqual(client_ip('127.0.0.1',{'X-Real-IP':'forged'},('127.0.0.1',)),'127.0.0.1')

class MigrationCLITest(unittest.TestCase):
    def test_operator_can_upgrade_before_new_session_marker_is_required(self):
        from contextlib import nullcontext
        with patch('sys.argv',['portal_app_server.py','--migrate-stage3','1']), \
             patch.object(portal,'ensure_schema') as readiness, \
             patch.object(portal,'db',return_value=nullcontext(object())), \
             patch.object(portal,'migrate_production') as migrate:
            portal.main()
        readiness.assert_called_once_with(require_session_storage=False)
        migrate.assert_called_once()

class LoginRouteTest(unittest.TestCase):
    setUp=base.PortalAPITest.setUp
    tearDown=base.PortalAPITest.tearDown
    request=base.PortalAPITest.request

    def test_tenant_aliases_share_budget_and_throttled_attempt_skips_hashing(self):
        for n in range(10):
            self.request('/api/login',body={'username':' Worker ' if n%2 else 'worker','pin':'incorrect-fixture-only'},status=401)
        with patch.object(portal,'verify_pin') as verify:
            result=self.request('/api/login',body={'username':'WORKER','pin':'incorrect-fixture-only'},status=429)
        verify.assert_not_called();self.assertGreater(result['retry_after'],0)

    def test_normal_login_still_works_after_one_failure(self):
        self.request('/api/login',body={'username':'worker','pin':'incorrect-fixture-only'},status=401)
        result=self.request('/api/login',body={'username':'worker','pin':'1234'})
        self.assertEqual(self.request('/api/me',result['token'])['user']['id'],self.worker_id)

    def test_platform_endpoint_and_tenant_fallback_share_owner_budget(self):
        portal.create_platform_owner('security-owner','synthetic-password-only')
        for n in range(10):
            endpoint='/api/platform/login' if n%2 else '/api/login'
            self.request(endpoint,body={'username':'security-owner','pin':'incorrect-fixture-only'},status=401)
        with patch.object(portal,'verify_pin') as verify:
            self.request('/api/platform/login',body={'username':'security-owner','pin':'incorrect-fixture-only'},status=429)
        verify.assert_not_called()

    def test_ip_budget_covers_unknown_accounts_and_cannot_be_header_rotated(self):
        portal.LOGIN_LIMITER=LoginLimiter()
        for n in range(60):
            self.request('/api/login',body={'username':'missing-fixture-'+str(n),'pin':'invalid'},status=401,
                         extra_headers={'X-Real-IP':'192.0.2.'+str(n+1)})
        self.request('/api/login',body={'username':'another-missing-fixture','pin':'invalid'},status=429)

if __name__=='__main__':unittest.main()
