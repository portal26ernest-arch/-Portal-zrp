import importlib.util,sqlite3,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
s=importlib.util.spec_from_file_location("m",ROOT/"ops/legacy_money_reconcile.py");m=importlib.util.module_from_spec(s);s.loader.exec_module(m)

class MoneyReconcileTest(unittest.TestCase):
    def fixture(self,p):
        c=sqlite3.connect(p);c.executescript("""
CREATE TABLE work_log(id INTEGER PRIMARY KEY,company_id INTEGER,salary REAL,revenue REAL,quantity REAL,salary_minor INTEGER,revenue_minor INTEGER);
INSERT INTO work_log VALUES(1,1,10.25,15.50,3.75,1025,1550);
INSERT INTO work_log VALUES(2,1,2.00,3.00,9.5,200,300);
INSERT INTO work_log VALUES(3,2,999.00,999.00,1,99900,99900);
CREATE TABLE payroll_settlement_entries(company_id INTEGER,amount_minor INTEGER);
INSERT INTO payroll_settlement_entries VALUES(1,125);
""");c.commit();c.close()
    def ro(self,p):
        return m.open_readonly(p)
    def test_exact_minor(self):
        self.assertEqual(m.expected_minor("10.25"),1025)
        with self.assertRaises(m.ReconciliationError):m.expected_minor("1.005")
    def test_scope_and_allowlist(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"x.db";self.fixture(p);c=self.ro(p)
            try:r=m.build_report(c,1,[])
            finally:c.close()
            names={(x["table"],x["field"]):x for x in r["money_fields"]}
            self.assertEqual(names[("work_log","salary")]["rows"],2)
            self.assertNotIn(("work_log","quantity"),names)
            self.assertEqual(r["minor_unit_fields"][0]["invalid_values"],0)
    def test_dual_read(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"x.db";self.fixture(p);c=self.ro(p)
            try:self.assertTrue(m.reconcile_pair(c,"work_log","salary","salary_minor",1)["ok"])
            finally:c.close()
            c=sqlite3.connect(p);c.execute("UPDATE work_log SET salary_minor=999 WHERE id=2");c.commit();c.close()
            c=self.ro(p)
            try:r=m.reconcile_pair(c,"work_log","salary","salary_minor",1)
            finally:c.close()
            self.assertEqual(r["mismatches"],1);self.assertFalse(r["ok"])
    def test_read_only(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"x.db";self.fixture(p);c=self.ro(p)
            try:
                with self.assertRaises(sqlite3.OperationalError):c.execute("UPDATE work_log SET salary=0")
            finally:c.close()
    def test_non_cent_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"x.db";self.fixture(p);c=sqlite3.connect(p)
            c.execute("INSERT INTO work_log VALUES(4,1,1.005,2,1,101,200)");c.commit();c.close()
            c=self.ro(p)
            try:r=m.build_report(c,1,[])
            finally:c.close()
            self.assertTrue(r["blockers"]);self.assertFalse(r["ready_for_additive_minor_unit_migration"])
    def test_pair_allowlist(self):
        self.assertEqual(m.parse_pair("work_log.salary=salary_minor"),("work_log","salary","salary_minor"))
        with self.assertRaises(m.ReconciliationError):m.parse_pair("work_log.quantity=quantity_minor")
        with self.assertRaises(m.ReconciliationError):m.parse_pair("work_log.salary=x;drop")

if __name__=="__main__":unittest.main()
