"""Trusted, PostgreSQL-only operator entry point for internal reminders.

This module never sends email, Telegram, push, or other external messages.
Companies must explicitly opt in through their own settings. The example
systemd timer is not enabled by this code or by repository installation.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import re
import sys
import uuid


_RUN_PREFIX = re.compile(r"^[A-Za-z0-9._:-]{1,96}$")


def run_company_jobs(company_ids, *, open_company, company_available, run_job,
                     now=None, run_prefix=None):
    """Run opted-in companies through caller-provided tenant-bound resources.

    `open_company(id)` must yield a transaction-scoped repository for exactly
    that company. The scheduler neither accepts a company ID from its CLI nor
    changes tenant context itself. Exceptions are counted without serializing
    exception text or tenant data.
    """
    current = now or datetime.now(timezone.utc)
    if not isinstance(current, datetime) or current.tzinfo is None:
        raise ValueError("Reminder operator clock must include a timezone")
    prefix = run_prefix or uuid.uuid4().hex
    if not isinstance(prefix, str) or not _RUN_PREFIX.fullmatch(prefix):
        raise ValueError("Invalid reminder operator run identity")
    ids = list(company_ids)
    if any(type(company_id) is not int or company_id < 1 for company_id in ids):
        raise ValueError("Invalid company registry row")
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate company registry row")

    summary = dict(companies_seen=len(ids), companies_skipped=0, companies_run=0,
                   reminders_enabled=0, sent=0, duplicate=0,
                   candidate_failures=0, failures=0)
    for company_id in ids:
        try:
            if not company_available(company_id):
                summary["companies_skipped"] += 1
                continue
            with open_company(company_id) as repository:
                if getattr(repository, "company_id", None) != company_id:
                    raise PermissionError("Company repository scope mismatch")
                settings = repository.get("settings", "control", False) or {}
                if not isinstance(settings, dict):
                    raise ValueError("Company reminder settings are invalid")
                enabled = settings.get("reminder_enabled", False)
                if type(enabled) is not bool:
                    raise ValueError("Company reminder enable flag must be explicit")
                if not enabled:
                    summary["companies_skipped"] += 1
                    continue
                record = run_job(repository, now=current,
                                 run_id=f"{prefix}:{company_id}")
            summary["companies_run"] += 1
            summary["reminders_enabled"] += int(record["enabled"] is True)
            summary["sent"] += record["sent"]
            summary["duplicate"] += record["duplicate"]
            summary["candidate_failures"] += record["failed"]
        except Exception:
            summary["failures"] += 1
    return summary


def run_enabled_companies(*, now=None, run_prefix=None):
    """Enumerate the control registry and process only available PostgreSQL tenants."""
    import portal_app_server as app
    from reminder_jobs import run_configured_company

    if app.CONFIG.backend != "postgresql":
        raise RuntimeError("Reminder operator requires the PostgreSQL runtime")
    with app.tenants.control(app.DB_PATH) as registry:
        company_ids = [row[0] for row in registry.execute(
            "SELECT id FROM companies ORDER BY id").fetchall()]

    @contextmanager
    def open_company(company_id):
        with app.tenants.company_scope(company_id), app.db() as connection:
            yield app.Repository(connection, company_id)

    def company_available(company_id):
        return app.tenants.available(app.tenants.get_company(app.DB_PATH, company_id))

    return run_company_jobs(company_ids, open_company=open_company,
                            company_available=company_available,
                            run_job=run_configured_company,
                            now=now, run_prefix=run_prefix)


def main():
    try:
        summary = run_enabled_companies()
    except Exception:
        # Do not expose connection strings, SQL, or customer data in service logs.
        print(json.dumps({"error": "reminder operator failed"}, sort_keys=True))
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 1 if summary["failures"] or summary["candidate_failures"] else 0


if __name__ == "__main__":
    sys.exit(main())
