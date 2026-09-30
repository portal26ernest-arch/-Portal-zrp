import unittest
from datetime import datetime, timezone

from reminder_jobs import Reminder, ReminderRunner


class ReminderRunnerTests(unittest.TestCase):
    def test_disabled_by_default_never_calls_delivery(self):
        called = []
        result = ReminderRunner().run(
            4, [Reminder("invoice_overdue", "inv-1", "Invoice overdue")],
            already_sent=lambda *_: False,
            deliver=lambda *args: called.append(args),
        )
        self.assertEqual(result, {"enabled": False, "sent": 0, "duplicate": 0, "failed": 0})
        self.assertEqual(called, [])

    def test_company_scoped_idempotency_and_retry_after_failure(self):
        now = datetime(2026, 9, 30, 21, 0, tzinfo=timezone.utc)
        runner = ReminderRunner(enabled=True, cadence="daily", clock=lambda: now)
        sent = set()
        deliveries = []
        reminder = Reminder("invoice_overdue", "invoice-7", "Overdue")

        def deliver(company, candidate, key):
            if not deliveries:
                deliveries.append((company, key, "failed"))
                raise RuntimeError("must not be exposed")
            deliveries.append((company, key, "sent"))
            sent.add((company, key))

        failed = runner.run(4, [reminder], already_sent=lambda c, k: (c, k) in sent, deliver=deliver)
        retried = runner.run(4, [reminder], already_sent=lambda c, k: (c, k) in sent, deliver=deliver)
        repeated = runner.run(4, [reminder], already_sent=lambda c, k: (c, k) in sent, deliver=deliver)
        other_company = runner.run(5, [reminder], already_sent=lambda c, k: (c, k) in sent, deliver=deliver)

        self.assertEqual(failed["failed"], 1)
        self.assertEqual(retried["sent"], 1)
        self.assertEqual(repeated["duplicate"], 1)
        self.assertEqual(other_company["sent"], 1)
        self.assertEqual(deliveries[0][1], deliveries[1][1])
        self.assertEqual(deliveries[1][1], deliveries[2][1])
        self.assertEqual(deliveries[1][0], 4)
        self.assertEqual(deliveries[2][0], 5)

    def test_weekly_cadence_and_timezone_boundaries(self):
        runner = ReminderRunner(enabled=True, cadence="weekly")
        monday = datetime(2026, 9, 28, 0, 30, tzinfo=timezone.utc)
        self.assertEqual(runner.cadence_id(monday), "2026-W40")
        self.assertEqual(runner.cadence_id(datetime(2026, 10, 4, 23, 59, tzinfo=timezone.utc)), "2026-W40")
        moscow = ReminderRunner(enabled=True, cadence="daily", utc_offset_minutes=180)
        self.assertEqual(moscow.cadence_id(datetime(2026, 9, 30, 21, 30, tzinfo=timezone.utc)), "2026-10-01")
        with self.assertRaises(ValueError):
            runner.cadence_id(datetime(2026, 9, 30))

    def test_missing_or_invalid_company_scope_fails_closed(self):
        runner = ReminderRunner(enabled=True)
        for company in (None, 0, "4", True):
            with self.subTest(company=company), self.assertRaises(PermissionError):
                runner.run(company, [], already_sent=lambda *_: False, deliver=lambda *_: None)
        with self.assertRaises(ValueError):
            ReminderRunner(utc_offset_minutes=900)

    def test_candidate_identity_rejects_control_and_secret_like_values(self):
        with self.assertRaises(ValueError):
            Reminder("invoice", "../private-token", "x").key("2026-09-30")


if __name__ == "__main__":
    unittest.main()
