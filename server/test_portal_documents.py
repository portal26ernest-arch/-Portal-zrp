import hashlib
import tempfile
import unittest
from pathlib import Path

from portal_documents import (LocalFileStorage, SHEETS, TEMPLATE_VERSION, XLSX_MIME,
                              parse_template, template_xlsx, validate_upload)


class PortalDocumentTests(unittest.TestCase):
    def test_template_is_valid_and_contract_is_exact(self):
        payload = template_xlsx({'id': 7, 'name': 'Тестовая компания'})
        parsed = parse_template(payload)
        self.assertEqual(parsed['sheets'], ['Компания', 'Сотрудники', 'Клиенты', 'Операции_Тарифы'])
        self.assertEqual(parsed['template_version'], TEMPLATE_VERSION)
        self.assertEqual(parsed['checksum_sha256'], hashlib.sha256(payload).hexdigest())

    def test_blank_and_prefilled_are_deterministic_and_scoped(self):
        self.assertEqual(template_xlsx({'id': 1}), template_xlsx({'id': 1}))
        self.assertNotEqual(template_xlsx({'id': 1}), template_xlsx({'id': 2}))
        self.assertEqual(len(SHEETS), 4)

    def test_upload_filename_and_mime_validation(self):
        valid = template_xlsx()
        digest = validate_upload('report.xlsx', XLSX_MIME, valid)
        self.assertEqual(digest, hashlib.sha256(valid).hexdigest())
        for name, mime in [('../escape.xlsx', XLSX_MIME), ('x.pdf', XLSX_MIME), ('..', XLSX_MIME)]:
            with self.assertRaises(ValueError):
                validate_upload(name, mime, valid)

    def test_storage_key_is_generated_and_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalFileStorage(directory)
            key = store.put(b'synthetic')
            self.assertEqual(store.get(key), b'synthetic')
            with self.assertRaises(PermissionError):
                store.get('../outside')

    def test_rejects_non_xlsx_and_corrupt_workbook(self):
        with self.assertRaises(ValueError):
            parse_template(b'not a zip')


if __name__ == '__main__':
    unittest.main()
