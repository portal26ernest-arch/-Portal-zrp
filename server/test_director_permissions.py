import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import production_permissions as perms

class DirectorPermissionsTest(unittest.TestCase):
    def test_director_label_and_full_company_business_defaults(self):
        self.assertEqual(perms.ROLE_NAMES["director"], "Директор")
        director = perms.defaults("director")
        admin = perms.defaults("admin")
        self.assertTrue(admin <= director, sorted(admin - director))
        self.assertIn("clients.manage", director)

    def test_director_is_not_platform_owner(self):
        class Repo:
            company_id = 1
            def get(self, *args, **kwargs):
                return None
        with self.assertRaises(PermissionError):
            perms.require(Repo(), {"id": 7, "role": "director", "company_id": 2}, "clients.manage")

if __name__ == "__main__":
    unittest.main()
