import sqlite3
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone

from marketplace_news_jobs import MAX_PUBLICATIONS_PER_SOURCE, run_company, run_companies


class Repository:
    def __init__(self, company_id):
        self.company_id = company_id
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute('''CREATE TABLE marketplace_news(
            id INTEGER PRIMARY KEY,company_id INTEGER,source TEXT,title TEXT,body TEXT,
            url TEXT,published_at TEXT,fetched_at TEXT,is_regulation INTEGER,
            external_key TEXT,UNIQUE(company_id,external_key))''')


class MarketplaceNewsJobsTest(unittest.TestCase):
    def setUp(self):
        self.repository = Repository(1)
        self.now = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)

    def test_default_disabled_does_not_call_sources_or_write(self):
        def forbidden(**kwargs):
            self.fail("disabled scheduler called a source adapter")

        result = run_company(self.repository, source_fetchers={"ozon": forbidden}, now=self.now)
        self.assertEqual(result, {"enabled": False, "sources_configured": 1,
            "sources_succeeded": 0, "sources_failed": 0, "sources_skipped": 2,
            "publications_upserted": 0})
        self.assertEqual(self.repository.conn.execute(
            "SELECT COUNT(*) FROM marketplace_news").fetchone()[0], 0)

    def test_validated_official_publications_upsert_tenant_scoped_and_idempotently(self):
        values = [{"title": "Notice", "body": "Summary",
                   "url": "https://seller.ozon.ru/news/a?utm_source=test",
                   "published_at": "2026-09-29T10:00:00Z", "is_regulation": True}]
        result = run_company(self.repository, enabled=True,
                             source_fetchers={"ozon": lambda **kwargs: values}, now=self.now)
        self.assertEqual(result["publications_upserted"], 1)
        other = Repository(2)
        run_company(other, enabled=True, source_fetchers={"ozon": lambda **kwargs: values}, now=self.now)
        for repository in (self.repository, other):
            self.assertEqual(repository.conn.execute(
                "SELECT COUNT(*) FROM marketplace_news").fetchone()[0], 1)
        run_company(self.repository, enabled=True,
                    source_fetchers={"ozon": lambda **kwargs: values}, now=self.now)
        self.assertEqual(self.repository.conn.execute(
            "SELECT COUNT(*) FROM marketplace_news").fetchone()[0], 1)

    def test_invalid_source_payload_is_counted_without_partial_upsert_or_details(self):
        values = [
            {"title": "Valid", "body": "Summary", "url": "https://seller.ozon.ru/news/a"},
            {"title": "Invalid", "body": "Summary", "url": "https://ozon.ru/news/b"},
        ]
        result = run_company(self.repository, enabled=True,
                             source_fetchers={"ozon": lambda **kwargs: values}, now=self.now)
        self.assertEqual((result["sources_failed"], result["publications_upserted"]), (1, 0))
        self.assertNotIn("ozon.ru/news/b", repr(result))
        self.assertEqual(self.repository.conn.execute(
            "SELECT COUNT(*) FROM marketplace_news").fetchone()[0], 0)

    def test_adapter_exceptions_are_sanitized_and_unknown_sources_fail_closed(self):
        def failing(**kwargs):
            raise RuntimeError("credential-like adapter detail")

        result = run_company(self.repository, enabled=True,
                             source_fetchers={"wildberries": failing}, now=self.now)
        self.assertEqual((result["sources_failed"], result["sources_skipped"]), (1, 1))
        self.assertNotIn("credential-like", repr(result))
        with self.assertRaises(ValueError):
            run_company(self.repository, enabled=True, source_fetchers={"untrusted": failing})

    def test_explicit_company_and_bounded_response_are_required(self):
        with self.assertRaises(PermissionError):
            run_company(Repository(None), enabled=True)
        excessive = ({"title": "Notice", "body": "Summary",
                     "url": "https://seller.ozon.ru/news/a"}
                     for _ in range(MAX_PUBLICATIONS_PER_SOURCE + 1))
        result = run_company(self.repository, enabled=True,
                             source_fetchers={"ozon": lambda **kwargs: excessive}, now=self.now)
        self.assertEqual((result["sources_failed"], result["publications_upserted"]), (1, 0))
        self.assertEqual(self.repository.conn.execute(
            "SELECT COUNT(*) FROM marketplace_news").fetchone()[0], 0)

    def test_operator_is_disabled_without_opening_tenants_and_scopes_enabled_runs(self):
        calls = []
        disabled = run_companies([1, 2], open_company=lambda _: self.fail("opened while disabled"),
            company_available=lambda _: self.fail("checked while disabled"), now=self.now)
        self.assertEqual(disabled["companies_skipped"], 2)
        repositories = {1: self.repository, 2: Repository(2)}

        @contextmanager
        def open_company(company_id):
            calls.append(company_id)
            yield repositories[company_id]

        values = [{"title": "Notice", "body": "Summary",
                   "url": "https://seller.wildberries.ru/instructions/a"}]
        result = run_companies([1, 2], open_company=open_company,
            company_available=lambda company_id: company_id == 1, enabled=True,
            source_fetchers={"wildberries": lambda **kwargs: values}, now=self.now)
        self.assertEqual(calls, [1])
        self.assertEqual((result["companies_run"], result["companies_skipped"],
                          result["publications_upserted"]), (1, 1, 1))
        with self.assertRaises(ValueError):
            run_companies([1, 1], open_company=open_company,
                          company_available=lambda _: True, enabled=True, now=self.now)


if __name__ == "__main__":
    unittest.main()
