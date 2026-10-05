import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import sticker_catalog


class StickerCatalogTests(unittest.TestCase):
    def test_enabled_fallback_and_deferred_owner_ids(self):
        entries = sticker_catalog.catalog_entries()
        self.assertEqual(sticker_catalog.allowed_sticker_keys(), {
            'accepted', 'in_progress', 'done', 'help', 'important', 'thanks'
        })
        self.assertEqual([item['key'] for item in entries[6:]],
                         ['hello', 'happy', 'wow', 'cheer', 'sad', 'sleep', 'shrug', 'ok'])
        self.assertTrue(all(not item['enabled'] for item in entries[6:]))

    def test_rejects_unsafe_asset_paths_even_when_disabled(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / 'catalog.json'
            manifest.write_text(json.dumps({'version': 1, 'stickers': [
                {'key': 'safe', 'label': 'Safe', 'asset': '../outside.png', 'enabled': False}
            ]}), encoding='utf-8')
            with patch.object(sticker_catalog, 'CATALOG', manifest):
                with self.assertRaisesRegex(ValueError, 'asset name'):
                    sticker_catalog.catalog_entries()

    def test_rejects_missing_enabled_asset(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / 'catalog.json'
            manifest.write_text(json.dumps({'version': 1, 'stickers': [
                {'key': 'safe', 'label': 'Safe', 'asset': 'missing.webp', 'enabled': True}
            ]}), encoding='utf-8')
            with patch.object(sticker_catalog, 'CATALOG', manifest):
                with self.assertRaisesRegex(ValueError, 'asset is missing'):
                    sticker_catalog.catalog_entries()


if __name__ == '__main__':
    unittest.main()
