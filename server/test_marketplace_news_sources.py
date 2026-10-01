import io
import json
import unittest
from datetime import datetime, timezone

from marketplace_news_sources import WB_ENDPOINT, wildberries_fetcher


class Response(io.BytesIO):
    status = 200
    def __enter__(self): return self
    def __exit__(self, *args): self.close()


class WildberriesNewsSourceTest(unittest.TestCase):
    def test_official_api_maps_to_trusted_publications(self):
        seen={}
        payload={"data":[{"id":123,"header":"Новость WB","content":"Текст новости",
                           "date":"2026-10-01T09:00:00Z","types":[]}]}
        def opener(request, timeout):
            seen.update(url=request.full_url, auth=request.get_header("Authorization"), timeout=timeout)
            return Response(json.dumps(payload).encode())
        fetch=wildberries_fetcher("secret-token", opener=opener, lookback_days=7)
        rows=fetch(now=datetime(2026,10,1,12,tzinfo=timezone.utc))
        self.assertTrue(seen["url"].startswith(WB_ENDPOINT+"?"))
        self.assertEqual(seen["auth"],"Bearer secret-token")
        self.assertEqual(seen["timeout"],15)
        self.assertEqual(rows,[{"title":"Новость WB","body":"Текст новости",
                                "url":"https://seller.wildberries.ru/news-v2/news-details?id=123",
                                "published_at":"2026-10-01T09:00:00Z","is_regulation":False}])

    def test_rejects_bad_token_and_payload(self):
        bad_tokens=(None,"","bad"+chr(10)+"value")
        for token in bad_tokens:
            with self.subTest(token=token), self.assertRaises(ValueError):
                wildberries_fetcher(token)
        def opener(request, timeout):
            return Response(b'{"unexpected": []}')
        fetch=wildberries_fetcher("test-token",opener=opener)
        with self.assertRaises(ValueError):
            fetch(now=datetime(2026,10,1,12,tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
