import base64
import os
import sys
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
if str(HERE) not in sys.path: sys.path.insert(0,str(HERE))
import messenger_relay_auth as auth
import messenger_relay as relay

class MessengerRelayTest(unittest.TestCase):
    def setUp(self):
        self.env={
            'PORTAL_MESSENGER_RELAY_URL':'https://relay.vart-portal.ru:9443',
            'PORTAL_MESSENGER_RELAY_SECRET':'x'*48,
            'PORTAL_MESSENGER_RELAY_TTL_SECONDS':'3600',
        }

    def test_ticket_round_trip_and_expiry(self):
        ticket=auth.issue_ticket(7,11,self.env,now=1000)
        self.assertTrue(ticket['enabled'])
        self.assertEqual(ticket['proxy_url'],'https://relay.vart-portal.ru:9443')
        self.assertEqual(auth.validate_ticket(ticket['username'],ticket['password'],self.env['PORTAL_MESSENGER_RELAY_SECRET'],now=1100)['company_id'],11)
        self.assertIsNone(auth.validate_ticket(ticket['username'],ticket['password'],self.env['PORTAL_MESSENGER_RELAY_SECRET'],now=5001))
        self.assertIsNone(auth.validate_ticket(ticket['username'],ticket['password']+'x',self.env['PORTAL_MESSENGER_RELAY_SECRET'],now=1100))

    def test_disabled_without_secret_and_rejects_unsafe_url(self):
        self.assertEqual(auth.relay_status({'PORTAL_MESSENGER_RELAY_URL':'https://relay.vart-portal.ru'}),{'enabled':False})
        with self.assertRaises(ValueError): auth.normalize_proxy_url('http://relay.vart-portal.ru:9443')
        with self.assertRaises(ValueError): auth.normalize_proxy_url('https://user:pass@relay.vart-portal.ru')

    def test_destination_allowlist_and_public_ip_guard(self):
        for host in ('telegram.org','web.telegram.org','venus.web.telegram.org','t.me','web.max.ru','api.max.ru'):
            self.assertTrue(relay._allowed_host(host),host)
        for host in ('telegram.org.evil.example','eviltelegram.org','example.com','localhost'):
            self.assertFalse(relay._allowed_host(host),host)
        for ip in ('127.0.0.1','10.0.0.5','192.168.1.1','169.254.1.1','::1'):
            self.assertFalse(relay._public_ip(ip),ip)
        self.assertTrue(relay._public_ip('1.1.1.1'))

    def test_basic_proxy_auth_parser(self):
        raw=base64.b64encode(b'user:pass').decode()
        self.assertEqual(relay._basic_credentials({'proxy-authorization':'Basic '+raw}),('user','pass'))
        self.assertIsNone(relay._basic_credentials({}))

if __name__=='__main__': unittest.main()
