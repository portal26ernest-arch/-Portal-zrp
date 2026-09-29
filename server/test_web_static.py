import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import web_static

class FakeHandler:
    def __init__(self, path):
        self.path = path; self.headers = {}; self.status = None; self.wfile = io.BytesIO()
    def send_error(self, status): self.status = status
    def send_response(self, status): self.status = status
    def send_header(self, key, value): self.headers[key] = value
    def end_headers(self): pass

class WebStaticTests(unittest.TestCase):
    def test_shell_assets_and_security_headers(self):
        for path, mime in [('/web/', 'text/html'),('/web/ui.css','text/css'),('/web/app.js','text/javascript'),('/web/brand-mark.svg','image/svg+xml'),('/web/stickers/catalog.json','application/json')]:
            handler=FakeHandler(path); web_static.serve(handler)
            self.assertEqual(handler.status,200,path); self.assertTrue(handler.headers['Content-Type'].startswith(mime))
            self.assertEqual(handler.headers['Cache-Control'],'no-store'); self.assertEqual(handler.headers['X-Content-Type-Options'],'nosniff')
            self.assertIn("connect-src 'self'",handler.headers['Content-Security-Policy']); self.assertIn("frame-ancestors 'none'",handler.headers['Content-Security-Policy'])
    def test_rejects_traversal_and_non_allowlisted_files(self):
        for path in ['/webjunk','/web/../.env','/web/%2e%2e/.env','/web/%252e%252e/.env','/web/..%5c.env','/web/server.py','/web/.git/config','/web/index.html?x=../../etc/passwd']:
            handler=FakeHandler(path); web_static.serve(handler); self.assertEqual(handler.status,404,path)

if __name__ == '__main__': unittest.main()
