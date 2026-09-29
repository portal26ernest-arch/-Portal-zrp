from pathlib import Path
import importlib.util
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "render_nginx", ROOT / "ops/render_nginx_config.py"
)
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


class RenderNginxConfigTest(unittest.TestCase):
    def test_valid_fqdn_and_default_port_render(self):
        text = renderer.render("Portal.Example.COM", 8765)
        self.assertIn("server_name portal.example.com;", text)
        self.assertIn("proxy_pass http://127.0.0.1:8765;", text)
        self.assertNotIn("__PORTAL_", text)
        self.assertNotIn("proxy_pass http://0.0.0.0:", text)

    def test_bad_hosts_are_rejected(self):
        for host in (
            "http://portal.example.com",
            "user@portal.example.com",
            "portal.example.com/path",
            "portal.example.com:443",
            "localhost",
            "bad host.example",
        ):
            with self.assertRaises(ValueError):
                renderer.validate_host(host)
    def test_bad_ports_are_rejected(self):
        for port in (0, 80, 443, 65536, "8765"):
            with self.assertRaises(ValueError):
                renderer.validate_port(port)

    def test_template_requires_exact_port_placeholder(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "nginx.template"
            p.write_text(
                "server_name __PORTAL_HOST__;\n"
                "proxy_pass http://127.0.0.1:8765;\n",
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                renderer.render("portal.example.com", 8765, p)

    def test_render_hash_is_stable(self):
        first = renderer.render("portal.example.com", 8765)
        second = renderer.render("portal.example.com", 8765)
        self.assertEqual(renderer.sha256_text(first), renderer.sha256_text(second))
        self.assertEqual(len(renderer.sha256_text(first)), 64)


if __name__ == "__main__":
    unittest.main()
