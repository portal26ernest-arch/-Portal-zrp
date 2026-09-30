import unittest
from contextlib import contextmanager
from datetime import datetime, timezone

from reminder_operator import run_company_jobs


class Repository:
    def __init__(self, company_id, settings):
        self.company_id = company_id
        self.settings = settings

    def get(self, kind, identity, required=False):
        if (kind, identity) == ("settings", "control"):
            return self.settings
        raise AssertionError("Unexpected repository access")


class ReminderOperatorTest(unittest.TestCase):
    def test_operator_scopes_enabled_companies_and_aggregates_sanitized_results(self):
        settings = {
            1: {"reminder_enabled": True, "reminder_cadence": "daily"},
            2: None,
            3: {"reminder_enabled": True, "reminder_cadence": "weekly"},
        }
        opened = []
        calls = []

        @contextmanager
        def open_company(company_id):
            opened.append(company_id)
            yield Repository(company_id, settings[company_id])

        def run_job(repository, *, now, run_id):
            calls.append((repository.company_id, now, run_id))
            if repository.company_id == 3:
                return {"enabled": True, "sent": 0, "duplicate": 1, "failed": 2}
            return {"enabled": True, "sent": 2, "duplicate": 1, "failed": 0}

        now = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)
        result = run_company_jobs([1, 2, 3, 4], open_company=open_company,
                                  company_available=lambda cid: cid != 4,
                                  run_job=run_job, now=now, run_prefix="nightly-test")
        self.assertEqual(opened, [1, 2, 3])
        self.assertEqual([call[0] for call in calls], [1, 3])
        self.assertEqual([call[2] for call in calls], ["nightly-test:1", "nightly-test:3"])
        self.assertTrue(all(call[1] is now for call in calls))
        self.assertEqual(result, dict(companies_seen=4, companies_skipped=2, companies_run=2,
                                      reminders_enabled=2, sent=2, duplicate=2,
                                      candidate_failures=2, failures=0))

    def test_default_and_invalid_opt_in_never_call_delivery(self):
        for settings in (None, {"reminder_enabled": False}):
            with self.subTest(settings=settings):
                calls = []

                @contextmanager
                def open_company(company_id):
                    yield Repository(company_id, settings)

                result = run_company_jobs([1], open_company=open_company,
                    company_available=lambda _cid: True,
                    run_job=lambda *_args, **_kwargs: calls.append(True))
                self.assertEqual(calls, [])
                self.assertEqual((result["companies_skipped"], result["companies_run"]), (1, 0))

        with self.assertRaises(ValueError):
            run_company_jobs([1], open_company=lambda _cid: None,
                             company_available=lambda _cid: True,
                             run_job=lambda *_args, **_kwargs: None,
                             run_prefix="has spaces")


if __name__ == "__main__":
    unittest.main()
