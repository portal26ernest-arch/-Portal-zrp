"""Conservative employee-name matching aliases from the PORTAL Knowledge Base."""
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


def employee_name_key(value):
    """Return a search key; never use it to rewrite a stored employee name."""
    normalized = unicodedata.normalize('NFKC', str(value or '')).strip().casefold()
    tokens = re.split(r'([^\w]+)', normalized)
    return ''.join(_SURNAME_ALIASES.get(token, token) for token in tokens)
