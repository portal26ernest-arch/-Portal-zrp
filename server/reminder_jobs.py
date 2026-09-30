"""Company-scoped, opt-in reminder scheduling primitives.

This module deliberately does not start a timer or send external messages. A
trusted operator job supplies candidate reminders and a company-scoped delivery
callback. Successful reminder keys are persisted by the caller so retries are
safe; failed deliveries are returned as sanitized counts and remain retryable.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re


_KEY_PART = re.compile(r"^[A-Za-z0-9._:-]{1,160}$")


@dataclass(frozen=True)
class Reminder:
    kind: str
    entity_id: str
    title: str

    def key(self, cadence_id: str) -> str:
        if not _KEY_PART.fullmatch(self.kind) or not _KEY_PART.fullmatch(self.entity_id):
            raise ValueError("Reminder identity is invalid")
        return f"reminder:{self.kind}:{self.entity_id}:{cadence_id}"


class ReminderRunner:
    """Dispatch source-backed reminders with deterministic cadence/idempotency."""

    def __init__(self, *, enabled=False, cadence="daily", utc_offset_minutes=0, clock=None):
        if cadence not in {"daily", "weekly"}:
            raise ValueError("Unsupported reminder cadence")
        if type(utc_offset_minutes) is not int or not -840 <= utc_offset_minutes <= 840:
            raise ValueError("Invalid reminder UTC offset")
        self.timezone = timezone(timedelta(minutes=utc_offset_minutes))
        self.enabled = bool(enabled)
        self.cadence = cadence
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def cadence_id(self, now=None):
        current = now or self.clock()
        if current.tzinfo is None:
            raise ValueError("Reminder clock must include a timezone")
        current = current.astimezone(self.timezone)
        if self.cadence == "daily":
            return current.strftime("%Y-%m-%d")
        iso = current.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"

    def run(self, company_id, reminders, *, already_sent, deliver):
        """Deliver a batch for one explicit tenant.

        `already_sent(company_id, key)` and `deliver(company_id, reminder, key)`
        must use the caller's tenant-scoped transaction/repository. The runner
        never changes company context or interpolates company IDs into queries.
        """
        if type(company_id) is not int or company_id < 1:
            raise PermissionError("An explicit company scope is required")
        if not self.enabled:
            return {"enabled": False, "sent": 0, "duplicate": 0, "failed": 0}
        now = self.clock()
        cadence_id = self.cadence_id(now)
        sent = duplicate = failed = 0
        for reminder in reminders:
            if not isinstance(reminder, Reminder):
                raise TypeError("Reminder candidates must be validated Reminder values")
            key = reminder.key(cadence_id)
            if already_sent(company_id, key):
                duplicate += 1
                continue
            try:
                deliver(company_id, reminder, key)
            except Exception:
                # Deliberately do not serialize exception text or candidate data.
                failed += 1
                continue
            sent += 1
        return {"enabled": True, "sent": sent, "duplicate": duplicate, "failed": failed}
