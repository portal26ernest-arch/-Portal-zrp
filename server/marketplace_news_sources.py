"""Official marketplace-news source adapters.

Only documented HTTPS APIs are used here. Credentials are injected at runtime
and are never persisted by the adapter or included in returned publications.
"""
from datetime import timedelta
import json
from urllib.parse import urlencode
from urllib.request import Request, urlopen

WB_ENDPOINT = "https://common-api.wildberries.ru/api/communications/v2/news"
WB_ARTICLE = "https://seller.wildberries.ru/news-v2/news-details?id={}"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def _token(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise ValueError("Wildberries news token is invalid")
    if any(ord(ch) < 32 for ch in value):
        raise ValueError("Wildberries news token is invalid")
    return value.strip()


def wildberries_fetcher(token, *, opener=urlopen, lookback_days=14):
    """Return a trusted fetcher compatible with marketplace_news_jobs.run_company."""
    secret = _token(token)
    if type(lookback_days) is not int or not 1 <= lookback_days <= 90:
        raise ValueError("Wildberries news lookback is invalid")

    def fetch(*, now):
        since = (now.date() - timedelta(days=lookback_days)).isoformat()
        request = Request(
            WB_ENDPOINT + "?" + urlencode({"from": since}),
            headers={"Authorization": f"Bearer {secret}", "Accept": "application/json",
                     "User-Agent": "PORTAL/marketplace-news"},
            method="GET",
        )
        with opener(request, timeout=15) as response:
            if getattr(response, "status", 200) != 200:
                raise ValueError("Wildberries news source returned an error")
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise ValueError("Wildberries news response is too large")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Wildberries news response is invalid") from exc
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            raise ValueError("Wildberries news response is invalid")
        result = []
        for row in rows:
            if not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] < 1:
                raise ValueError("Wildberries news item is invalid")
            result.append({"title": row.get("header"), "body": row.get("content"),
                           "url": WB_ARTICLE.format(row["id"]), "published_at": row.get("date"),
                           "is_regulation": False})
        return result

    return fetch
