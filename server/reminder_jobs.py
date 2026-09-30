"""Company-scoped, opt-in reminder scheduling primitives.

This module deliberately does not start a timer or send external messages. A
trusted operator job supplies candidate reminders and a company-scoped delivery
callback. The callback must atomically insert the unique reminder key and its
internal notification in one tenant-scoped transaction; failed deliveries are
returned as sanitized counts and remain retryable.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
import uuid


_KEY_PART = re.compile(r"^[A-Za-z0-9._:-]{1,160}$")


@dataclass(frozen=True)
class Reminder:
    kind: str
    entity_id: str
    title: str

    def __post_init__(self):
        if not isinstance(self.title,str) or not self.title.strip() or len(self.title)>200 or any(ord(c)<32 for c in self.title):
            raise ValueError("Reminder title is invalid")

    def key(self, cadence_id: str) -> str:
        if not _KEY_PART.fullmatch(self.kind) or not _KEY_PART.fullmatch(self.entity_id):
            raise ValueError("Reminder identity is invalid")
        return f"reminder:{self.kind}:{self.entity_id}:{cadence_id}"


def source_candidates(repository, now, *, utc_offset_minutes=0):
    """Build reminder candidates only from rows visible in one explicit tenant repository."""
    if type(getattr(repository,'company_id',None)) is not int or repository.company_id<1:
        raise PermissionError("An explicit company scope is required")
    if type(utc_offset_minutes) is not int or not -840<=utc_offset_minutes<=840:
        raise ValueError("Invalid reminder UTC offset")
    if not isinstance(now,datetime) or now.tzinfo is None:
        raise ValueError("Reminder clock must include a timezone")
    local_today=now.astimezone(timezone(timedelta(minutes=utc_offset_minutes))).date()
    payments=repository.list('payments')
    revisions=repository.list('invoice_revisions')
    invoices=repository.list('invoices')
    latest={}
    for revision in revisions:
        current=latest.get(revision['invoice_id'])
        if current is None or revision['revision']>current['revision']:
            latest[revision['invoice_id']]=revision
    paid={}
    for payment in payments:paid[payment['invoice_id']]=paid.get(payment['invoice_id'],0)+payment['amount']
    candidates=[]
    billed={wid for invoice in invoices for wid in invoice.get('work_ids',[])}
    for revision in revisions:billed.update(revision.get('snapshot',{}).get('work_ids',[]))
    for invoice in invoices:
        revision=latest.get(invoice['id'])
        snapshot=revision.get('snapshot',{}) if revision else invoice
        amount=snapshot.get('amount',invoice.get('amount'))
        due=snapshot.get('due_at',invoice.get('due_at'))
        if not due or amount is None:continue
        try:
            due_value=datetime.fromisoformat(due)
            due_date=due_value.astimezone(timezone(timedelta(minutes=utc_offset_minutes))).date() if due_value.tzinfo else due_value.date()
        except (TypeError,ValueError):continue
        if due_date<local_today and amount-paid.get(invoice['id'],0)>0:
            candidates.append(Reminder('invoice_overdue',str(invoice['id']),'Просрочена оплата по счёту'))
    for work in repository.list('works'):
        if work['id'] in billed:continue
        candidates.append(Reminder('work_unbilled',str(work['id']),'Выполненная работа не выставлена клиенту'))
    return sorted(candidates,key=lambda item:(item.kind,item.entity_id))


def persist_once(repository, company_id, reminder, key, occurred_at):
    """Append an internal notification; caller owns the tenant transaction/commit."""
    if type(company_id) is not int or company_id<1 or company_id!=getattr(repository,'company_id',None):
        raise PermissionError("Reminder company scope mismatch")
    if not isinstance(reminder,Reminder) or not isinstance(key,str):
        raise ValueError("Reminder dispatch is invalid")
    prefix=f"reminder:{reminder.kind}:{reminder.entity_id}:"
    if not key.startswith(prefix) or not key[len(prefix):] or not isinstance(occurred_at,datetime) or occurred_at.tzinfo is None:
        raise ValueError("Reminder dispatch identity is invalid")
    return repository.insert_once('notifications',dict(event='reminder',reminder_kind=reminder.kind,
        entity_id=reminder.entity_id,title=reminder.title,idempotency_key=key,
        occurred_at=occurred_at.astimezone(timezone.utc).isoformat()),key)


def repository_dispatcher(repository, *, occurred_at=None):
    """Adapt a transaction-scoped Repository to ReminderRunner's callback contract."""
    def dispatch(company_id, reminder, key):
        return persist_once(repository,company_id,reminder,key,occurred_at or datetime.now(timezone.utc))
    return dispatch


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

    def run(self, company_id, reminders, *, dispatch_once):
        """Deliver a batch for one explicit tenant.

        `dispatch_once(company_id, reminder, key)` must atomically create the
        notification and a unique sent-key record in the caller's tenant-scoped
        transaction. It returns True for a newly dispatched reminder, False if
        the key already exists, and raises on a retryable failure. The runner
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
            try:
                was_sent = dispatch_once(company_id, reminder, key)
            except Exception:
                # Deliberately do not serialize exception text or candidate data.
                failed += 1
                continue
            if was_sent:
                sent += 1
            else:
                duplicate += 1
        return {"enabled": True, "sent": sent, "duplicate": duplicate, "failed": failed}


def next_run_at(now, cadence, utc_offset_minutes=0):
    """Return the next local cadence boundary as a UTC ISO timestamp."""
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ValueError("Reminder clock must include a timezone")
    if cadence not in {"daily", "weekly"}:
        raise ValueError("Unsupported reminder cadence")
    if type(utc_offset_minutes) is not int or not -840 <= utc_offset_minutes <= 840:
        raise ValueError("Invalid reminder UTC offset")
    zone = timezone(timedelta(minutes=utc_offset_minutes))
    local = now.astimezone(zone)
    if cadence == "daily":
        target = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        days = 7 - local.weekday()
        target = (local + timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
    return target.astimezone(timezone.utc).isoformat()


def run_scheduled_company(repository, *, enabled=False, cadence="daily",
                          utc_offset_minutes=0, now=None, run_id=None):
    """Operator entry point for one explicitly scoped company transaction.

    Production remains disabled unless the trusted operator explicitly enables
    it. Every attempted run appends a sanitized run record. Failed candidates
    are safe to retry in the same cadence because notification inserts are
    atomic and keyed by company/entity/cadence.
    """
    company_id = getattr(repository, "company_id", None)
    if type(company_id) is not int or company_id < 1:
        raise PermissionError("An explicit company scope is required")
    current = now or datetime.now(timezone.utc)
    if not isinstance(current, datetime) or current.tzinfo is None:
        raise ValueError("Reminder clock must include a timezone")
    if type(enabled) is not bool:
        raise ValueError("Reminder scheduler enable flag must be explicit")
    if run_id is None:
        run_id = str(uuid.uuid4())
    if not isinstance(run_id, str) or not _KEY_PART.fullmatch(run_id):
        raise ValueError("Invalid reminder run identity")

    runner = ReminderRunner(enabled=enabled, cadence=cadence,
                            utc_offset_minutes=utc_offset_minutes,
                            clock=lambda: current)
    cadence_id = runner.cadence_id(current)
    result = {"enabled": False, "sent": 0, "duplicate": 0, "failed": 0}
    candidates = []
    if enabled:
        try:
            candidates = source_candidates(repository, current,
                                           utc_offset_minutes=utc_offset_minutes)
            result = runner.run(company_id, candidates,
                                dispatch_once=repository_dispatcher(repository, occurred_at=current))
        except Exception:
            # Exception messages may contain SQL or tenant data.
            result = {"enabled": True, "sent": 0, "duplicate": 0, "failed": 1}
    outcome = "disabled" if not enabled else ("retryable" if result["failed"] else "success")
    record = dict(company_id=company_id, run_id=run_id, enabled=enabled, cadence=cadence,
                  cadence_id=cadence_id, started_at=current.astimezone(timezone.utc).isoformat(),
                  completed_at=current.astimezone(timezone.utc).isoformat(),
                  next_run_at=next_run_at(current, cadence, utc_offset_minutes),
                  outcome=outcome, candidate_count=len(candidates), sent=result["sent"],
                  duplicate=result["duplicate"], failed=result["failed"])
    repository.insert_once("reminder_job_runs", record, run_id)
    return {key: value for key, value in record.items() if key != "company_id"}


def run_configured_company(repository, *, now=None, run_id=None):
    """Run one explicitly scoped company using its saved opt-in settings.

    Missing settings preserve the disabled-by-default contract. This is an
    operator entry point, not a timer; the caller still owns scheduling and
    supplies a transaction-scoped, tenant-bound repository.
    """
    company_id = getattr(repository, "company_id", None)
    if type(company_id) is not int or company_id < 1:
        raise PermissionError("An explicit company scope is required")
    settings = repository.get("settings", "control", False) or {}
    if not isinstance(settings, dict):
        raise ValueError("Company reminder settings are invalid")
    enabled = settings.get("reminder_enabled", False)
    cadence = settings.get("reminder_cadence", "daily")
    offset = settings.get("utc_offset_minutes", 0)
    if type(enabled) is not bool:
        raise ValueError("Company reminder enable flag must be explicit")
    return run_scheduled_company(repository, enabled=enabled, cadence=cadence,
                                 utc_offset_minutes=offset, now=now, run_id=run_id)
