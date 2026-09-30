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


def repository_dispatcher(repository):
    """Adapt a transaction-scoped Repository to ReminderRunner's callback contract."""
    def dispatch(company_id, reminder, key):
        return persist_once(repository,company_id,reminder,key,datetime.now(timezone.utc))
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
