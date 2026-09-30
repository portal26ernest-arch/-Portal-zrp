"""Stable client-name search aliases without rewriting canonical catalogue names."""
import hashlib
import unicodedata
from datetime import datetime, timezone

_KNOWN_ALIASES = {
    'борискин': ('Борисенко',),
    'варданян': ('Вартанян',),
    'вдовина': ('Вдовин',),
    'шульгина': ('Шульгинова',),
    'элегантика': ('Эленгатика',),
    'карягин': ('Корягин', 'Коорягин'),
    'чотчаева': ('Чотчаев',),
}

def client_name_key(value):
    """Return a comparison key only; never use it to rewrite a stored client name."""
    return unicodedata.normalize('NFKC', str(value or '')).strip().casefold()

def known_client_aliases(canonical_name):
    return _KNOWN_ALIASES.get(client_name_key(canonical_name), ())

def _alias_identity(client_id, alias):
    digest=hashlib.sha256(client_name_key(alias).encode('utf-8')).hexdigest()
    return f'{int(client_id)}:{digest}'

def persist_client_alias(repo, client_id, alias, source, canonical_name):
    alias=str(alias or '').strip()
    if not alias or client_name_key(alias)==client_name_key(canonical_name):
        return False
    identity=_alias_identity(client_id,alias)
    if repo.get('client_aliases',identity,False): return False
    return repo.insert_once('client_aliases',dict(
        client_id=int(client_id),alias=alias,alias_key=client_name_key(alias),
        source=source,canonical_name_snapshot=str(canonical_name),
        occurred_at=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec='microseconds')
    ),identity)

def persist_known_client_aliases(repo, client_id, canonical_name):
    return sum(bool(persist_client_alias(repo,client_id,alias,'knowledge',canonical_name))
               for alias in known_client_aliases(canonical_name))
