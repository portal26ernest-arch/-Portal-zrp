import unittest

import desktop_update


class DesktopUpdateManifestTest(unittest.TestCase):
    def test_unconfigured_is_not_advertised(self):
        self.assertIsNone(desktop_update.load_manifest({}))

    def test_valid_https_manifest(self):
        data = desktop_update.load_manifest({
            "PORTAL_DESKTOP_UPDATE_VERSION": "3.7.0",
            "PORTAL_DESKTOP_UPDATE_BUILD": "37",
            "PORTAL_DESKTOP_UPDATE_URL": "https://downloads.example.test/PORTAL-Desktop-win-x64-3.7.0.zip",
            "PORTAL_DESKTOP_UPDATE_SHA256": "A" * 64,
        })
        self.assertEqual(data["build"], 37)
        self.assertEqual(data["sha256"], "a" * 64)
        self.assertNotIn("token", data)
        self.assertNotIn("secret", data)

    def test_rejects_insecure_or_credentialed_url(self):
        base = {
            "PORTAL_DESKTOP_UPDATE_VERSION": "3.7.0",
            "PORTAL_DESKTOP_UPDATE_BUILD": "37",
            "PORTAL_DESKTOP_UPDATE_SHA256": "a" * 64,
        }
        for url in (
            "http://example.test/setup.exe",
            "https://user:pass@example.test/setup.exe",
            "https://example.test/setup.exe?token=secret",
        ):
            with self.subTest(url=url), self.assertRaises(RuntimeError):
                desktop_update.load_manifest({**base, "PORTAL_DESKTOP_UPDATE_URL": url})

    def test_loopback_http_allowed_for_disposable_staging(self):
        data = desktop_update.load_manifest({
            "PORTAL_DESKTOP_UPDATE_VERSION": "3.7.0",
            "PORTAL_DESKTOP_UPDATE_BUILD": "37",
            "PORTAL_DESKTOP_UPDATE_URL": "http://127.0.0.1:8770/PORTAL-Desktop-win-x64-3.7.0.zip",
            "PORTAL_DESKTOP_UPDATE_SHA256": "1" * 64,
        })
        self.assertEqual(data["build"], 37)

    def test_partial_or_invalid_manifest_fails_closed(self):
        with self.assertRaises(RuntimeError):
            desktop_update.load_manifest({"PORTAL_DESKTOP_UPDATE_VERSION": "3.7.0"})
        with self.assertRaises(RuntimeError):
            desktop_update.load_manifest({
                "PORTAL_DESKTOP_UPDATE_VERSION": "3.7.0",
                "PORTAL_DESKTOP_UPDATE_BUILD": "0",
                "PORTAL_DESKTOP_UPDATE_URL": "https://example.test/setup.exe",
                "PORTAL_DESKTOP_UPDATE_SHA256": "bad",
            })


if __name__ == "__main__":
    unittest.main()
