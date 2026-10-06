import asyncio
import base64
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import messenger_relay_auth as auth
import messenger_relay_ws as relay_ws


class RelayWssTicketTest(unittest.TestCase):
    def setUp(self):
        self.env = {
            "PORTAL_MESSENGER_RELAY_WSS_URL": "wss://relay.vart-portal.ru/connect",
            "PORTAL_MESSENGER_RELAY_SECRET": "s" * 48,
            "PORTAL_TELEGRAM_RELAY_REQUIRED": "1",
            "PORTAL_MESSENGER_RELAY_TTL_SECONDS": "3600",
        }

    def test_wss_only_ticket_is_enabled_without_direct_proxy(self):
        status = auth.relay_status(self.env)
        self.assertTrue(status["enabled"])
        self.assertTrue(status["required"])
        self.assertEqual(status["wss_url"], "wss://relay.vart-portal.ru/connect")
        self.assertNotIn("proxy_url", status)
        ticket = auth.issue_ticket(3, 4, self.env, now=1000)
        self.assertEqual(ticket["wss_url"], "wss://relay.vart-portal.ru/connect")
        self.assertNotIn(self.env["PORTAL_MESSENGER_RELAY_SECRET"], repr(ticket))

    def test_direct_and_wss_transports_can_coexist(self):
        env = dict(self.env, PORTAL_MESSENGER_RELAY_URL="https://relay-direct.vart-portal.ru:9443")
        status = auth.relay_status(env)
        self.assertEqual(status["proxy_url"], "https://relay-direct.vart-portal.ru:9443")
        self.assertEqual(status["wss_url"], "wss://relay.vart-portal.ru/connect")

    def test_invalid_wss_url_does_not_enable_relay(self):
        env = dict(self.env, PORTAL_MESSENGER_RELAY_WSS_URL="ws://127.0.0.1:9444/connect")
        self.assertEqual(auth.relay_status(env), {
            "provider": "telegram",
            "enabled": False,
            "required": True,
        })
        for value in (
            "https://relay.vart-portal.ru/connect",
            "wss://user:pass@relay.vart-portal.ru/connect",
            "wss://relay.vart-portal.ru/other",
            "wss://relay.vart-portal.ru/connect?ticket=x",
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                auth.normalize_wss_url(value)


class RelayWssProtocolTest(unittest.IsolatedAsyncioTestCase):
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
        self.secret = "w" * 48
        self.env = {
            "PORTAL_MESSENGER_RELAY_WSS_URL": "wss://relay.vart-portal.ru/connect",
            "PORTAL_MESSENGER_RELAY_SECRET": self.secret,
            "PORTAL_MESSENGER_RELAY_TTL_SECONDS": "3600",
        }

    async def _request(self, head: bytes, upstream=None):
        with mock.patch.dict(os.environ, {"PORTAL_MESSENGER_RELAY_SECRET": self.secret}, clear=False), \
             mock.patch.object(relay_ws, "_connect_socks5", new=mock.AsyncMock(return_value=upstream)):
            server = await asyncio.start_server(relay_ws.handle, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.write(head)
                await writer.drain()
                head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2)
                content_length = 0
                for line in head.decode("iso-8859-1").split("\r\n"):
                    if line.lower().startswith("content-length:"):
                        content_length = int(line.split(":", 1)[1].strip())
                        break
                body = await asyncio.wait_for(reader.readexactly(content_length), timeout=2) if content_length else b""
                writer.close()
                await writer.wait_closed()
                return head + body
            finally:
                server.close()
                await server.wait_closed()

    def _upgrade_head(self, *, target="web.telegram.org:443", credentials=None):
        websocket_key = base64.b64encode(bytes(range(16))).decode("ascii")
        lines = [
            "GET /connect HTTP/1.1",
            "Host: relay.vart-portal.ru",
            "Upgrade: websocket",
            "Connection: Upgrade",
            "Sec-WebSocket-Version: 13",
            f"Sec-WebSocket-Key: {websocket_key}",
            f"X-Portal-Target: {target}",
        ]
        if credentials:
            raw = base64.b64encode(f"{credentials[0]}:{credentials[1]}".encode()).decode()
            lines.append("Authorization: Basic " + raw)
        return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii")

    async def test_healthz_is_no_secret_and_contains_no_runtime_data(self):
        data = await self._request(b"GET /healthz HTTP/1.1\r\nHost: relay\r\n\r\n")
        self.assertTrue(data.startswith(b"HTTP/1.1 200 OK"))
        self.assertTrue(data.endswith(b"ok"))

    async def test_unauthenticated_upgrade_is_denied_before_upstream(self):
        with mock.patch.object(relay_ws, "_connect_socks5", new=mock.AsyncMock()) as upstream:
            data = await self._request(self._upgrade_head())
            self.assertTrue(data.startswith(b"HTTP/1.1 401 Unauthorized"))
            upstream.assert_not_awaited()

    async def test_authenticated_non_telegram_target_is_denied(self):
        ticket = auth.issue_ticket(1, 2, self.env)
        data = await self._request(
            self._upgrade_head(target="example.com:443", credentials=(ticket["username"], ticket["password"]))
        )
        self.assertTrue(data.startswith(b"HTTP/1.1 403 Forbidden"))

    async def test_text_frames_are_rejected(self):
        class FakeUpstreamWriter:
            def write(self, _data):
                pass
            async def drain(self):
                pass
            def close(self):
                pass
            async def wait_closed(self):
                pass

        upstream_reader = asyncio.StreamReader()
        ticket = auth.issue_ticket(1, 2, self.env)
        server = await asyncio.start_server(relay_ws.handle, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            with mock.patch.dict(os.environ, {"PORTAL_MESSENGER_RELAY_SECRET": self.secret}, clear=False), \
                 mock.patch.object(relay_ws, "_connect_socks5", new=mock.AsyncMock(return_value=(upstream_reader, FakeUpstreamWriter()))):
                reader, writer = await asyncio.open_connection("127.0.0.1", port)
                writer.write(self._upgrade_head(credentials=(ticket["username"], ticket["password"])))
                await writer.drain()
                response = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=2)
                self.assertTrue(response.startswith(b"HTTP/1.1 101 Switching Protocols"))
                payload = b"not allowed"
                mask = b"abcd"
                masked = bytes(value ^ mask[index % 4] for index, value in enumerate(payload))
                writer.write(bytes((0x81, 0x80 | len(payload))) + mask + masked)
                await writer.drain()
                close = await asyncio.wait_for(reader.read(64), timeout=2)
                self.assertTrue(close)
                writer.close()
                await writer.wait_closed()
        finally:
            server.close()
            await server.wait_closed()


if __name__ == "__main__":
    unittest.main()
