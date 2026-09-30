# PORTAL marketplace-news scheduler framework

`server/marketplace_news_jobs.py` supplies a bounded, disabled-by-default
operator framework. It accepts trusted source adapters as an explicit
dependency; it does not make network requests, scrape seller portals, or
discover adapters dynamically. Source adapters may only return bounded
publication records. The existing ingestion boundary then enforces HTTPS and
the exact official seller host before an idempotent company-scoped upsert.

The multi-company operator accepts company IDs only from a trusted registry
caller and requires the caller to open each company-bound repository. Disabled
runs do not check tenant availability or open tenant repositories. Adapter and
tenant failures are reduced to aggregate counters; exception messages, URLs,
credentials, and publication data are not logged. The caller owns transaction
commit/rollback, so a failed database write must roll back its company
transaction.

There are currently **no official public-feed adapters** in the repository.
Consequently this code must remain disabled and no timer/service is installed.
Add an adapter only after verifying an official, unauthenticated source and its
stable data contract. Do not add seller credentials, brittle HTML scraping, or
production scheduling as part of the framework. Existing news reads remain
company-scoped and unchanged.

Run the isolated primitives with `python -m unittest test_marketplace_news
test_marketplace_news_jobs` from `server/`. The tests use only in-memory SQLite
fixtures and injected callbacks; they make no HTTP requests.
