import sqlite3
import unittest
from marketplace_news import canonical_url, publication, upsert

class MarketplaceNewsTest(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.execute('''CREATE TABLE marketplace_news(id INTEGER PRIMARY KEY,company_id INTEGER,source TEXT,title TEXT,body TEXT,url TEXT,published_at TEXT,fetched_at TEXT,is_regulation INTEGER,external_key TEXT,UNIQUE(company_id,external_key))''')

    def test_only_https_official_hosts_and_canonical_dedup(self):
        item=publication('ozon','Новое правило','Краткое содержание','https://seller.ozon.ru/news/item?utm_source=x&b=2&a=1')
        self.assertEqual(item['url'],'https://seller.ozon.ru/news/item?a=1&b=2')
        upsert(self.db,1,item,'2026-09-29T00:00:00Z');upsert(self.db,1,item,'2026-09-30T00:00:00Z')
        self.assertEqual(self.db.execute('select count(*) from marketplace_news').fetchone()[0],1)
        self.assertEqual(self.db.execute('select fetched_at from marketplace_news').fetchone()[0],'2026-09-30T00:00:00Z')
        upsert(self.db,2,item)
        self.assertEqual(self.db.execute('select count(*) from marketplace_news').fetchone()[0],2)
        for source,url in [('ozon','http://seller.ozon.ru/x'),('ozon','https://ozon.ru/x'),('wildberries','https://seller.wildberries.ru.evil.test/x'),('wildberries','https://user@seller.wildberries.ru/x'),('ozon','javascript:alert(1)'),('ozon','https://seller.wildberries.ru/x')]:
            with self.assertRaises(ValueError):canonical_url(source,url)

    def test_payload_validation_and_no_markup(self):
        item=publication('wildberries','<b>Новости</b>','<script>alert(1)</script> Изменение','https://seller.wildberries.ru/instructions/item', '2026-09-29')
        self.assertNotIn('<',item['title']);self.assertNotIn('<',item['body'])
        for kwargs in [dict(title=''),dict(title='x'*241),dict(body='x'*4001),dict(is_regulation=1)]:
            values=dict(source='ozon',title='Valid',body='Body',url='https://seller.ozon.ru/news/a');values.update(kwargs)
            with self.assertRaises(ValueError):publication(**values)

if __name__=='__main__':unittest.main()
