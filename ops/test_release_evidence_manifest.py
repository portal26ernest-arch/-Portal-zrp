import importlib.util, tempfile, unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release_evidence',ROOT/'ops/release_evidence_manifest.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class ReleaseEvidenceManifestTest(unittest.TestCase):
    def test_current_repo_manifest_has_required_evidence(self):
        data=m.build_manifest(ROOT)
        self.assertEqual(len(data['head']),40)
        self.assertIn('PORTAL_RELEASE_READINESS_MATRIX.md',data['evidence'])
        self.assertIn('.github/workflows/infra-readiness.yml',data['evidence'])
        self.assertEqual(len(data['evidence']['PORTAL_RELEASE_READINESS_MATRIX.md']['sha256']),64)
        self.assertEqual(data['release']['buildNumber'],'3.5')

    def test_fingerprint_changes_with_content(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'x.txt';p.write_text('a',encoding='utf-8');a=m.fingerprint(p)
            p.write_text('b',encoding='utf-8');b=m.fingerprint(p)
            self.assertNotEqual(a['sha256'],b['sha256'])
    def test_release_metadata_requires_alignment(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/'release.properties'
            p.write_text('versionName=3.5-dev\nversionCode=35\nbuildNumber=3.5\nbuildDate=2026-09-30\nchannel=staging\n',encoding='utf-8')
            self.assertEqual(m.parse_properties(p)['versionCode'],'35')
            p.write_text('versionName=3.6-dev\nversionCode=35\nbuildNumber=3.5\nbuildDate=2026-09-30\nchannel=staging\n',encoding='utf-8')
            with self.assertRaises(m.EvidenceError):m.parse_properties(p)

    def test_markdown_contains_head_and_hashes(self):
        data=m.build_manifest(ROOT);text=m.markdown(data)
        self.assertIn(data['head'],text)
        self.assertIn('Evidence fingerprints',text)
        self.assertNotIn(str(ROOT),text)

if __name__=='__main__':unittest.main()
