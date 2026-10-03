import importlib.util
import pathlib
import unittest

MODULE = pathlib.Path(__file__).with_name("validate_release_config.py")
SPEC = importlib.util.spec_from_file_location("validate_release_config", MODULE)
release = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(release)

class ReleaseConfigTests(unittest.TestCase):
    def test_stable_owned_https_origin(self):
        self.assertTrue(release.stable_https("https://portal.example.com"))
        self.assertTrue(release.stable_https("https://portal.example.com:443"))
        for value in [
            "http://portal.example.com",
            "https://portal.invalid",
            "https://127.0.0.1",
            "https://178-209-127-247.sslip.io",
            "https://portal.trycloudflare.com",
            "https://user:pass@portal.example.com",
            "https://portal.example.com/api",
            "https://portal.example.com/?token=x",
        ]:
            self.assertFalse(release.stable_https(value), value)

if __name__ == "__main__":
    unittest.main()
