"""Pure request-parser regressions; no sockets or external databases."""
import io
from types import SimpleNamespace
import unittest
import test_portal_app_server as base


class JSONRequestValuesTest(unittest.TestCase):
    def parse(self, raw, path='/api/clients'):
        handler = SimpleNamespace(path=path, rfile=io.BytesIO(raw),
                                  headers={'Content-Length': str(len(raw))})
        return base.portal.parse_body(handler)

    def test_non_finite_numbers_are_rejected_on_ordinary_routes(self):
        for spelling in ('NaN', 'Infinity', '-Infinity', '1e999', '-1e999'):
            with self.subTest(spelling=spelling):
                with self.assertRaises(ValueError):
                    self.parse(('{"nested":{"amount":' + spelling + '}}').encode())

    def test_finite_numbers_and_integer_ids_keep_their_types(self):
        body = self.parse(b'{"id":12,"amount":1.25,"zero":0.0}')
        self.assertIs(type(body['id']), int)
        self.assertIs(type(body['amount']), float)
        self.assertEqual(body['amount'], 1.25)

    def test_settlement_decimals_keep_exact_spelling(self):
        body = self.parse(b'{"amount":1.2500}', '/api/v3/payroll-settlements')
        self.assertEqual(body['amount'], '1.2500')

    def test_settlement_non_finite_constants_are_rejected(self):
        for spelling in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(spelling=spelling), self.assertRaises(ValueError):
                self.parse(('{"amount":' + spelling + '}').encode(), '/api/v3/payroll-settlements')


class JSONRequestHTTPTest(unittest.TestCase):
    setUp = base.PortalAPITest.setUp
    tearDown = base.PortalAPITest.tearDown
    request = base.PortalAPITest.request

    def test_authenticated_http_request_rejects_non_finite_number(self):
        result = self.request('/api/admin/clients', self.admin,
                              body={'name': 'Invalid numeric client', 'amount': float('nan')},
                              method='POST', status=400)
        self.assertFalse(result['ok'])
