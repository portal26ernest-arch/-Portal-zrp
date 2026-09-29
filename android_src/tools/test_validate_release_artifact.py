import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TOOL = Path(__file__).with_name("validate_release_artifact.py")


class ReleaseArtifactContractTests(unittest.TestCase):
    def test_manifest_must_match_release_metadata_apk_digest_and_exact_asset_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            props = root / "release.properties"
            apk = root / "PORTAL_Android_4.0_release.apk"
            manifest = root / "portal-update.json"
            props.write_text(
                "versionName=4.0\nversionCode=40\nbuildNumber=4.0\nchannel=release\n",
                encoding="utf-8",
            )
            apk.write_bytes(b"signed-apk-fixture")
            values = {
                "schemaVersion": 1,
                "applicationId": "ru.portal.app",
                "channel": "release",
                "versionCode": 40,
                "versionName": "4.0",
                "buildNumber": "4.0",
                "publishedAt": "2026-09-29T12:00:00Z",
                "changelog": "Test",
                "apkUrl": "https://github.com/portal26ernest-arch/-Portal-zrp/releases/download/portal-android-v4.0/PORTAL_Android_4.0_release.apk",
                "sha256": hashlib.sha256(apk.read_bytes()).hexdigest(),
            }

            def run():
                return subprocess.run(
                    [sys.executable, str(TOOL), "--properties", str(props), "--apk", str(apk),
                     "--manifest", str(manifest), "--repository", "portal26ernest-arch/-Portal-zrp",
                     "--tag", "portal-android-v4.0"], capture_output=True, text=True,
                )

            manifest.write_text(json.dumps(values), encoding="utf-8")
            self.assertEqual(run().returncode, 0)
            values["apkUrl"] = "https://attacker.example/app.apk"
            manifest.write_text(json.dumps(values), encoding="utf-8")
            self.assertNotEqual(run().returncode, 0)


if __name__ == "__main__":
    unittest.main()
