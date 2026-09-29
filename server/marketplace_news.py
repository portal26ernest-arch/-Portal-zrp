"""Trusted ingestion boundary for official marketplace publications.

Fetching is intentionally external: this module validates/upserts supplied records,
it does not scrape seller portals or retain credentials.
"""
from datetime import datetime, timezone
from hashlib import sha256
from html import unescape
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import re

HOSTS = {'ozon': {'seller.ozon.ru'}, 'wildberries': {'seller.wildberries.ru'}}
TRACKING = {'utm_source','utm_medium','utm_campaign','utm_term','utm_content','yclid','from'}

def canonical_url(source, value):
    if source not in HOSTS or not isinstance(value, str) or len(value)>2048:
        raise ValueError('Invalid marketplace source or URL')
    p=urlsplit(value.strip())
    if p.scheme.lower()!='https' or p.username or p.password or p.hostname is None or p.hostname.lower() not in HOSTS[source] or p.port not in (None,443):
        raise ValueError('URL must use HTTPS on the official seller host')
    path=re.sub(r'/+', '/', p.path or '/')
    query=urlencode(sorted((k,v) for k,v in parse_qsl(p.query,keep_blank_values=True) if k.lower() not in TRACKING))
    return urlunsplit(('https',p.hostname.lower(),path.rstrip('/') or '/',query,''))

def clean_text(value, name, limit, required=True):
    if value is None and not required:return ''
    if not isinstance(value,str):raise ValueError(f'{name} must be text')
    value=unescape(re.sub(r'<[^>]*>', ' ', value))
    value=' '.join(value.split())
    if (required and not value) or len(value)>limit or re.search(r'[<>\x00-\x08]',value):raise ValueError(f'Invalid {name}')
    return value

def publication(source, title, body, url, published_at=None, is_regulation=False):
    link=canonical_url(source,url)
    title=clean_text(title,'title',240)
    body=clean_text(body,'body',4000)
    if published_at is not None:
        if not isinstance(published_at,str):raise ValueError('Invalid publication date')
        try:dt=datetime.fromisoformat(published_at.replace('Z','+00:00'))
        except ValueError:raise ValueError('Invalid publication date')
        if dt.tzinfo is None:dt=dt.replace(tzinfo=timezone.utc)
        published_at=dt.astimezone(timezone.utc).isoformat()
    if type(is_regulation) is not bool:raise ValueError('Invalid regulation flag')
    return {'source':source,'title':title,'body':body,'url':link,'published_at':published_at,
            'is_regulation':is_regulation,'external_key':sha256((source+'\n'+link).encode()).hexdigest()}

def upsert(conn, company_id, item, fetched_at=None):
    """Idempotent company-scoped upsert into existing marketplace_news table."""
    fetched_at=fetched_at or datetime.now(timezone.utc).isoformat()
    conn.execute('''INSERT INTO marketplace_news(company_id,source,title,body,url,published_at,fetched_at,is_regulation,external_key)
                    VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(company_id,external_key) DO UPDATE SET
                    title=excluded.title,body=excluded.body,url=excluded.url,published_at=excluded.published_at,
                    fetched_at=excluded.fetched_at,is_regulation=excluded.is_regulation''',
                 (company_id,item['source'],item['title'],item['body'],item['url'],item['published_at'],fetched_at,int(item['is_regulation']),item['external_key']))
    return item['external_key']
