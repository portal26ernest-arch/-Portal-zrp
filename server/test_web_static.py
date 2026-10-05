import gzip
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import web_static

class FakeHandler:
    def __init__(self, path, request_headers=None):
        self.path = path; self.headers = dict(request_headers or {}); self.status = None; self.wfile = io.BytesIO()
    def send_error(self, status): self.status = status
    def send_response(self, status): self.status = status
    def send_header(self, key, value): self.headers[key] = value
    def end_headers(self): pass

class WebStaticTests(unittest.TestCase):
    def test_shell_assets_and_security_headers(self):
        for path, mime in [('/web/', 'text/html'),('/web/privacy.html','text/html'),('/web/support.html','text/html'),('/web/ui.css','text/css'),('/web/app.js','text/javascript'),('/web/build_meta.js','text/javascript'),('/web/brand-mark.svg','image/svg+xml'),('/web/stickers/catalog.json','application/json')]:
            handler=FakeHandler(path); web_static.serve(handler)
            self.assertEqual(handler.status,200,path); self.assertTrue(handler.headers['Content-Type'].startswith(mime))
            expected='no-cache, max-age=0, must-revalidate' if path in ('/web/','/web/build_meta.js') else 'private, max-age=3600, must-revalidate'
            self.assertEqual(handler.headers['Cache-Control'],expected)
            self.assertRegex(handler.headers['ETag'],r'^"[0-9a-f]{64}"$')
            self.assertEqual(handler.headers['Vary'],'Accept-Encoding')
            self.assertEqual(handler.headers['X-Content-Type-Options'],'nosniff')
            self.assertIn("connect-src 'self'",handler.headers['Content-Security-Policy']); self.assertIn("frame-ancestors 'none'",handler.headers['Content-Security-Policy'])

    def test_compresses_large_assets_and_supports_etag_revalidation(self):
        handler=FakeHandler('/web/production.js',{'Accept-Encoding':'gzip'}); web_static.serve(handler)
        self.assertEqual(handler.status,200); self.assertEqual(handler.headers.get('Content-Encoding'),'gzip')
        self.assertGreater(len(gzip.decompress(handler.wfile.getvalue())),1000)
        etag=handler.headers['ETag']
        second=FakeHandler('/web/production.js',{'If-None-Match':etag,'Accept-Encoding':'gzip'}); web_static.serve(second)
        self.assertEqual(second.status,304); self.assertEqual(second.wfile.getvalue(),b'')

    def test_rejects_traversal_and_non_allowlisted_files(self):
        for path in ['/webjunk','/web/../.env','/web/%2e%2e/.env','/web/%252e%252e/.env','/web/..%5c.env','/web/server.py','/web/.git/config','/web/index.html?x=../../etc/passwd']:
            handler=FakeHandler(path); web_static.serve(handler); self.assertEqual(handler.status,404,path)

    def test_serves_only_supported_raster_sticker_extensions(self):
        import tempfile
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as directory:
            sticker_dir=Path(directory)/'stickers';sticker_dir.mkdir()
            for extension,mime in (('png','image/png'),('webp','image/webp'),('gif','image/gif')):
                (sticker_dir/f'test.{extension}').write_bytes(b'asset')
                with patch.object(web_static,'ASSETS',Path(directory)):
                    handler=FakeHandler(f'/web/stickers/test.{extension}');web_static.serve(handler)
                self.assertEqual(handler.status,200)
                self.assertTrue(handler.headers['Content-Type'].startswith(mime))
            (sticker_dir/'test.jpg').write_bytes(b'asset')
            with patch.object(web_static,'ASSETS',Path(directory)):
                handler=FakeHandler('/web/stickers/test.jpg');web_static.serve(handler)
            self.assertEqual(handler.status,404)

if __name__ == '__main__': unittest.main()
