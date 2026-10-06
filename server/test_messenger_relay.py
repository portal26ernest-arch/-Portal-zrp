import base64
import asyncio
import os
import sys
from unittest import mock
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
            'PORTAL_TELEGRAM_RELAY_REQUIRED':'1',
        }

    def test_ticket_round_trip_and_expiry(self):
        ticket=auth.issue_ticket(7,11,self.env,now=1000)
        self.assertTrue(ticket['enabled'])
        self.assertTrue(ticket['required'])
        self.assertEqual(ticket['provider'],'telegram')
        self.assertEqual(ticket['proxy_url'],'https://relay.vart-portal.ru:9443')
        identity=auth.validate_ticket(ticket['username'],ticket['password'],self.env['PORTAL_MESSENGER_RELAY_SECRET'],now=1100)
        self.assertEqual(identity['company_id'],11)
        self.assertEqual(identity['scope'],'telegram')
        self.assertIsNone(auth.validate_ticket('v1.7.11.4600.nonce','x',self.env['PORTAL_MESSENGER_RELAY_SECRET'],now=1100))
        self.assertIsNone(auth.validate_ticket(ticket['username'],ticket['password'],self.env['PORTAL_MESSENGER_RELAY_SECRET'],now=5001))
        self.assertIsNone(auth.validate_ticket(ticket['username'],ticket['password']+'x',self.env['PORTAL_MESSENGER_RELAY_SECRET'],now=1100))

    def test_disabled_without_secret_and_rejects_unsafe_url(self):
        status=auth.relay_status({'PORTAL_MESSENGER_RELAY_URL':'https://relay.vart-portal.ru','PORTAL_TELEGRAM_RELAY_REQUIRED':'true'})
        self.assertEqual(status,{'provider':'telegram','enabled':False,'required':True})
        with self.assertRaises(ValueError): auth.normalize_proxy_url('http://relay.vart-portal.ru:9443')
        with self.assertRaises(ValueError): auth.normalize_proxy_url('https://user:pass@relay.vart-portal.ru')

    def test_unknown_required_flag_defaults_off(self):
        status=auth.relay_status({'PORTAL_TELEGRAM_RELAY_REQUIRED':'enabled-ish'})
        self.assertEqual(status,{'provider':'telegram','enabled':False,'required':False})

    def test_destination_allowlist_and_public_ip_guard(self):
        self.assertEqual(relay.ALLOWED_SUFFIXES,('telegram.org','t.me'))
        for host in ('telegram.org','web.telegram.org','venus.web.telegram.org','t.me'):
            self.assertTrue(relay._allowed_host(host),host)
        for host in ('telegram.org.evil.example','eviltelegram.org','example.com','localhost','max.ru','web.max.ru'):
            self.assertFalse(relay._allowed_host(host),host)
        for ip in ('127.0.0.1','10.0.0.5','192.168.1.1','169.254.1.1','::1'):
            self.assertFalse(relay._public_ip(ip),ip)
        self.assertTrue(relay._public_ip('1.1.1.1'))

    def test_basic_proxy_auth_parser(self):
        raw=base64.b64encode(b'user:pass').decode()
        self.assertEqual(relay._basic_credentials({'proxy-authorization':'Basic '+raw}),('user','pass'))
        self.assertIsNone(relay._basic_credentials({}))

    def test_upstream_parser_loopback_and_rejections(self):
        for url, expected in (("socks5://127.0.0.1:19050", ("127.0.0.1", 19050)),
                              ("socks5://[::1]:9050", ("::1", 9050)),
                              ("socks5://localhost:1", ("localhost", 1))):
            self.assertEqual(relay._parse_upstream_socks5(url), expected)
        self.assertIsNone(relay._parse_upstream_socks5(None))
        for url in ("socks5://example.com:9050", "socks5://user:pass@127.0.0.1:9050",
                    "socks5://127.0.0.1:9050/path", "socks5://127.0.0.1:9050?q=1",
                    "socks5://127.0.0.1:9050?", "socks5://127.0.0.1:9050#frag",
                    "socks5://127.0.0.1:9050#", "http://127.0.0.1:9050",
                    "socks5://127.0.0.1:0", "socks5://127.0.0.1:65536",
                    "socks5://127.0.0.1", "socks5://192.168.1.2:9050"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                relay._parse_upstream_socks5(url)


class Socks5RelayTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls._old_event_loop_policy = asyncio.get_event_loop_policy()
        selector_policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
        if selector_policy is not None:
            asyncio.set_event_loop_policy(selector_policy())

    @classmethod
    def tearDownClass(cls):
        asyncio.set_event_loop_policy(cls._old_event_loop_policy)

    async def asyncSetUp(self):
        self.requests = []
        async def fake_socks(reader, writer):
            greeting = await reader.readexactly(3)
            self.requests.append(greeting)
            writer.write(b"\x05\x00")
            await writer.drain()
            header = await reader.readexactly(5)
            size = header[4]
            domain = await reader.readexactly(size)
            port = await reader.readexactly(2)
            self.requests.append(header + domain + port)
            writer.write(b"\x05\x00\x00\x01\x7f\x00\x00\x01\x00\x50")
            await writer.drain()
            writer.close()
        self.server = await asyncio.start_server(fake_socks, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()

    async def test_socks_greeting_domain_connect(self):
        result = await relay._connect_socks5("web.telegram.org", 443, ("127.0.0.1", self.port))
        reader, writer = result
        self.assertEqual(self.requests[0], b"\x05\x01\x00")
        self.assertEqual(self.requests[1], b"\x05\x01\x00\x03" + bytes([len(b"web.telegram.org")]) + b"web.telegram.org\x01\xbb")
        writer.transport.abort()

    async def test_socks_failure_never_falls_back_to_direct(self):
        with mock.patch.object(relay, "_connect_public", new=mock.AsyncMock(side_effect=AssertionError("direct fallback"))) as direct:
            async def reject(reader, writer):
                await reader.readexactly(3)
                writer.write(b"\x05\xff")
                await writer.drain()
                writer.close()
            bad = await asyncio.start_server(reject, "127.0.0.1", 0)
            try:
                with self.assertRaises(OSError):
                    await relay._connect_socks5("web.telegram.org", 443, ("127.0.0.1", bad.sockets[0].getsockname()[1]))
                direct.assert_not_awaited()
            finally:
                bad.close()
                await bad.wait_closed()

    async def test_unset_upstream_uses_direct_connector(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(relay, "_connect_public", new=mock.AsyncMock(return_value=("reader", "writer"))) as direct:
            self.assertEqual(await relay._connect_socks5("web.telegram.org", 443), ("reader", "writer"))
            direct.assert_awaited_once_with("web.telegram.org", 443)

if __name__=='__main__': unittest.main()
