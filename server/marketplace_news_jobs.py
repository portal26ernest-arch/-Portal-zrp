"""Disabled-by-default operator primitives for trusted marketplace news feeds.

This module does not fetch URLs or scrape seller portals. A future official,
public-source adapter must be explicitly supplied by trusted server code. Each
run operates on one company-bound repository and validates a complete bounded
source response before writing any of that source's publications.
"""
from collections.abc import Mapping
from datetime import datetime, timezone

from marketplace_news import HOSTS, publication, upsert


MAX_PUBLICATIONS_PER_SOURCE = 100
PUBLICATION_FIELDS = frozenset({"title", "body", "url", "published_at", "is_regulation"})


def _validated_batch(source, fetcher, now):
    if not callable(fetcher):
        raise ValueError("Marketplace source adapter is invalid")
    values = fetcher(now=now)
    try:
        iterator = iter(values)
    except TypeError as exc:
        raise ValueError("Marketplace source response is invalid") from exc
    result = []
    for value in iterator:
        if len(result) >= MAX_PUBLICATIONS_PER_SOURCE:
            raise ValueError("Marketplace source response exceeds its item limit")
        if not isinstance(value, Mapping) or set(value) - PUBLICATION_FIELDS:
            raise ValueError("Marketplace publication fields are invalid")
        try:
            item = publication(source, **dict(value))
        except (TypeError, ValueError) as exc:
            raise ValueError("Marketplace publication failed validation") from exc
        result.append(item)
    return result


def run_company(repository, *, enabled=False, source_fetchers=None, now=None):
    """Run supplied trusted adapters in a single explicit tenant transaction.

    The caller owns transaction commit/rollback. Disabled runs never call an
    adapter. Adapter and validation failures are counted per source without
    exposing exception text, source payloads, credentials, or URLs.
    """
    company_id = getattr(repository, "company_id", None)
    if type(company_id) is not int or company_id < 1:
        raise PermissionError("An explicit company scope is required")
    if type(enabled) is not bool:
        raise ValueError("Marketplace news enable flag must be explicit")
    current = now or datetime.now(timezone.utc)
    if not isinstance(current, datetime) or current.tzinfo is None:
        raise ValueError("Marketplace news clock must include a timezone")
    adapters = {} if source_fetchers is None else source_fetchers
    if not isinstance(adapters, Mapping) or set(adapters) - set(HOSTS):
        raise ValueError("Marketplace source adapters are invalid")

    result = {"enabled": enabled, "sources_configured": len(adapters),
              "sources_succeeded": 0, "sources_failed": 0,
              "sources_skipped": 0, "publications_upserted": 0}
    if not enabled:
        result["sources_skipped"] = len(HOSTS)
        return result

    fetched_at = current.astimezone(timezone.utc).isoformat()
    for source in sorted(HOSTS):
        fetcher = adapters.get(source)
        if fetcher is None:
            result["sources_skipped"] += 1
            continue
        try:
            batch = _validated_batch(source, fetcher, current)
        except Exception:
            # Do not reveal adapter exception text, which may contain secrets.
            result["sources_failed"] += 1
            continue
        for item in batch:
            upsert(repository.conn, company_id, item, fetched_at)
        result["sources_succeeded"] += 1
        result["publications_upserted"] += len(batch)
    return result


def run_companies(company_ids, *, open_company, company_available,
                  enabled=False, source_fetchers=None, now=None):
    """Traverse a trusted company registry using caller-provided tenant scopes.

    The operator never builds SQL or accepts a company ID from a request. A
    disabled run does not check availability or open tenant repositories.
    """
    ids = list(company_ids)
    if any(type(company_id) is not int or company_id < 1 for company_id in ids):
        raise ValueError("Invalid company registry row")
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate company registry row")
    if not callable(open_company) or not callable(company_available):
        raise ValueError("Marketplace operator callbacks are required")
    if type(enabled) is not bool:
        raise ValueError("Marketplace news enable flag must be explicit")

    result = {"companies_seen": len(ids), "companies_skipped": 0,
              "companies_run": 0, "sources_succeeded": 0,
              "sources_failed": 0, "sources_skipped": 0,
              "publications_upserted": 0, "failures": 0}
    if not enabled:
        result["companies_skipped"] = len(ids)
        return result

    current = now or datetime.now(timezone.utc)
    for company_id in ids:
        try:
            if not company_available(company_id):
                result["companies_skipped"] += 1
                continue
            with open_company(company_id) as repository:
                if getattr(repository, "company_id", None) != company_id:
                    raise PermissionError("Company repository scope mismatch")
                run = run_company(repository, enabled=True,
                                  source_fetchers=source_fetchers, now=current)
            result["companies_run"] += 1
            for key in ("sources_succeeded", "sources_failed", "sources_skipped",
                        "publications_upserted"):
                result[key] += run[key]
        except Exception:
            # Do not serialize exception text, tenant data, or source values.
            result["failures"] += 1
    return result
