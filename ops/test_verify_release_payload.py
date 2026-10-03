from pathlib import Path
import importlib.util
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verify_release_payload", ROOT / "ops" / "verify_release_payload.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class ReleasePayloadTest(unittest.TestCase):
    def make_complete(self, root: Path):
        for rel in mod.REQUIRED_FILES:
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x", encoding="utf-8")

    def test_complete_payload_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_complete(root)
            missing, empty = mod.verify_payload(root)
            self.assertEqual(missing, [])
            self.assertEqual(empty, [])

    def test_missing_web_assets_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_complete(root)
            (root / "android_src/app/src/main/assets/app.js").unlink()
            missing, empty = mod.verify_payload(root)
            self.assertIn("android_src/app/src/main/assets/app.js", missing)
            self.assertEqual(empty, [])

    def test_empty_required_file_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.make_complete(root)
            (root / "server/web_static.py").write_bytes(b"")
            missing, empty = mod.verify_payload(root)
            self.assertEqual(missing, [])
            self.assertIn("server/web_static.py", empty)

    def test_smoke_requires_every_endpoint(self):
        class Resp:
            def __init__(self, url):
                self.status = 200
                self.url = url
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self, _limit):
                return b'{"ok": true}' if self.url.endswith("/api/ping") else b"x"
        seen = []
        def fake(req, timeout):
            seen.append(req.full_url)
            return Resp(req.full_url)
        with patch.object(mod, "urlopen", side_effect=fake):
            self.assertEqual(mod.smoke("https://portal.example"), [])
        self.assertEqual([u.rsplit("portal.example",1)[1] for u in seen], list(mod.SMOKE_PATHS))

if __name__ == "__main__":
    unittest.main()
