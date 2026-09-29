from pathlib import Path
import importlib.util
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "https_preflight", ROOT / "ops/https_endpoint_preflight.py"
)
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class HttpsEndpointPreflightTest(unittest.TestCase):
    def test_url_policy(self):
        good = preflight.validate_url("https://portal.example")
        self.assertEqual(good.hostname, "portal.example")
        for bad in (
            "http://portal.example",
            "https://user:pass@portal.example",
            "https://portal.example?token=x",
            "https://portal.example/#debug",
            "https://portal.example:8443",
        ):
            with self.assertRaises(ValueError):
                preflight.validate_url(bad)

    def mocks(self):
        return (
            patch.object(
                preflight,
                "cert_check",
                return_value={
                    "tls_version": "TLSv1.3",
                    "certificate_expires_utc": "2027-01-01T00:00:00+00:00",
                    "certificate_days_remaining": 90,
                    "certificate_valid_long_enough": True,
                },
            ),
            patch.object(
                preflight,
                "https_ping",
                return_value=(
                    200,
                    {
                        "strict-transport-security": "max-age=31536000",
                        "x-content-type-options": "nosniff",
                        "x-frame-options": "DENY",
                        "referrer-policy": "no-referrer",
                    },
                    {"ok": True},
                ),
            ),
            patch.object(
                preflight,
                "http_redirect",
                return_value={
                    "status": 301,
                    "location": "https://portal.example/",
                    "safe_https_redirect": True,
                },
            ),
            patch.object(preflight, "api_port_closed", return_value=True),
        )

    def test_all_green_is_go(self):
        a, b, c, d = self.mocks()
        with a, b, c, d:
            result = preflight.evaluate(
                "https://portal.example",
                api_port=8770,
            )
        self.assertTrue(result["go"])
        self.assertEqual(result["failures"], [])
        self.assertTrue(result["checks"]["public_api_port"]["closed"])

    def test_missing_security_header_is_no_go(self):
        a, _, c, d = self.mocks()
        with a, c, d, patch.object(
            preflight,
            "https_ping",
            return_value=(
                200,
                {
                    "strict-transport-security": "max-age=31536000",
                    "x-content-type-options": "nosniff",
                    "referrer-policy": "no-referrer",
                },
                {"ok": True},
            ),
        ):
            result = preflight.evaluate("https://portal.example")
        self.assertFalse(result["go"])
        self.assertIn("header:x-frame-options", result["failures"])

    def test_public_api_port_is_no_go(self):
        a, b, c, _ = self.mocks()
        with a, b, c, patch.object(
            preflight, "api_port_closed", return_value=False
        ):
            result = preflight.evaluate(
                "https://portal.example",
                api_port=8770,
            )
        self.assertFalse(result["go"])
        self.assertIn("api_port_public", result["failures"])

    def test_bad_ping_and_redirect_are_no_go(self):
        a, _, _, d = self.mocks()
        with a, d, patch.object(
            preflight,
            "https_ping",
            return_value=(503, {}, {"ok": False}),
        ), patch.object(
            preflight,
            "http_redirect",
            return_value={
                "status": 200,
                "location": "",
                "safe_https_redirect": False,
            },
        ):
            result = preflight.evaluate("https://portal.example")
        self.assertFalse(result["go"])
        self.assertIn("api_ping", result["failures"])
        self.assertIn("http_to_https_redirect", result["failures"])

    def test_short_certificate_is_no_go(self):
        _, b, c, d = self.mocks()
        with b, c, d, patch.object(
            preflight,
            "cert_check",
            return_value={
                "tls_version": "TLSv1.3",
                "certificate_expires_utc": "soon",
                "certificate_days_remaining": 2,
                "certificate_valid_long_enough": False,
            },
        ):
            result = preflight.evaluate("https://portal.example")
        self.assertIn("certificate_expiry", result["failures"])


if __name__ == "__main__":
    unittest.main()
