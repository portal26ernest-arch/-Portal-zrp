"""Conservative employee-name matching aliases from the PORTAL Knowledge Base."""
import hashlib
import re
import unicodedata


_SURNAME_ALIASES = {
    'борисенко': 'борискин',
    'вартанян': 'варданян',
    'вдовин': 'вдовина',
    'шульгинова': 'шульгина',
    'эленгатика': 'элегантика',
    'корягин': 'карягин',
    'коорягин': 'карягин',
    'чотчаев': 'чотчаева',
}
_CANONICAL_TO_ALIASES = {}
for _alias, _canonical in _SURNAME_ALIASES.items():
    _CANONICAL_TO_ALIASES.setdefault(_canonical, []).append(_alias)


def employee_name_key(value):
    """Return a search key; never use it to rewrite a stored employee name."""
    normalized = unicodedata.normalize('NFKC', str(value or '')).strip().casefold()
    tokens = re.split(r'([^\w]+)', normalized)
    return ''.join(_SURNAME_ALIASES.get(token, token) for token in tokens)


def _literal_key(value):
    return unicodedata.normalize('NFKC', str(value or '')).strip().casefold()


def known_employee_aliases(value):
    """Generate approved spelling variants for search only, preserving the rest of FIO."""
    text = unicodedata.normalize('NFKC', str(value or '')).strip()
    tokens = re.split(r'(\W+)', text, flags=re.UNICODE)
    result=[]
    for index, token in enumerate(tokens):
        canonical=token.casefold()
        for alias in _CANONICAL_TO_ALIASES.get(canonical, ()):
            shaped=alias.title() if token.istitle() else alias.upper() if token.isupper() else alias
            variant=list(tokens);variant[index]=shaped
            candidate=''.join(variant)
            if _literal_key(candidate)!=_literal_key(text):result.append(candidate)
    return tuple(dict.fromkeys(result))


def persist_employee_alias(repo, employee_id, alias, source, canonical_name):
    alias=str(alias or '').strip();canonical_name=str(canonical_name or '').strip()
    if not alias or not canonical_name:return None
    literal=_literal_key(alias)
    identity=hashlib.sha256(f'{int(employee_id)}\0{literal}'.encode('utf-8')).hexdigest()
    value=dict(employee_id=int(employee_id),alias=alias,alias_key=employee_name_key(alias),
               source=source,canonical_name_snapshot=canonical_name)
    repo.insert_once('employee_aliases',value,identity)
    return identity


def persist_known_employee_aliases(repo, employee_id, canonical_name):
    return [persist_employee_alias(repo,employee_id,alias,'knowledge',canonical_name)
            for alias in known_employee_aliases(canonical_name)]


def persist_employee_rename(repo, employee_id, old_name, new_name):
    if _literal_key(old_name)==_literal_key(new_name):
        persist_known_employee_aliases(repo,employee_id,new_name);return None
    row=repo.insert('employee_name_history',dict(employee_id=int(employee_id),old_name=old_name,new_name=new_name))
    persist_employee_alias(repo,employee_id,old_name,'rename',new_name)
    persist_known_employee_aliases(repo,employee_id,new_name)
    return row
