"""Opt-in real HTTP/Web/PostgreSQL gate using the established disposable fixture.

Run on the isolated PostgreSQL test host as its postgres OS user:
PORTAL_WEB_PG_E2E=1 python -m unittest test_web_postgresql_e2e
"""
import os
import unittest

import test_documents_postgresql as fixture


class WebPostgreSQLE2E(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('PORTAL_WEB_PG_E2E') == '1',
                         'requires isolated PostgreSQL and browser runtime')
    def test_disposable_postgresql_and_real_http_browser_flows(self):
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(
            fixture.DocumentsPostgreSQLTest)
        result = unittest.TestResult()
        suite.run(result)
        self.assertEqual(result.errors, [], result.errors)
        self.assertEqual(result.failures, [], result.failures)
        self.assertEqual(result.skipped, [], result.skipped)
        self.assertTrue(any(test._testMethodName ==
                            'test_real_web_static_login_meta_and_company_scope_in_browser'
                            for test in result.successes))
        self.assertGreater(result.testsRun, 0)


if __name__ == '__main__':
    unittest.main()
