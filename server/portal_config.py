"""Central server settings. Secrets are read from the environment, never logged."""
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from pathlib import Path


@dataclass(frozen=True)
class Config:
    environment: str
    backend: str
    sqlite_path: str
    postgres_dsn: str = field(repr=False)
    host: str
    port: int
    public_api_url: str
    control_dsn: str = field(default='', repr=False)
    postgres_pool_size: int = 0
    setup_token: str = field(default='', repr=False)


def load_config(env):
    environment = env.get('PORTAL_ENV', 'development')
    backend = env.get('PORTAL_DB_BACKEND', 'sqlite')
    if environment not in ('development', 'test', 'production'):
        raise ValueError('Invalid PORTAL_ENV')
    if backend not in ('sqlite', 'postgresql'):
        raise ValueError('Invalid PORTAL_DB_BACKEND')
    if environment == 'production' and backend != 'postgresql':
        raise ValueError('Production requires explicit PostgreSQL backend')
    try:
        port = int(env.get('PORTAL_APP_PORT', '8765'))
    except ValueError as exc:
        raise ValueError('Invalid PORTAL_APP_PORT') from exc
    if not 1 <= port <= 65535:
        raise ValueError('Invalid PORTAL_APP_PORT')
    url = env.get('PORTAL_PUBLIC_API_URL', '').rstrip('/')
    if url:
        parsed = urlsplit(url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            raise ValueError('Invalid PORTAL_PUBLIC_API_URL')
    if environment == 'production' and (not url or not url.startswith('https://')):
        raise ValueError('Production requires HTTPS PORTAL_PUBLIC_API_URL')
    dsn = env.get('PORTAL_DATABASE_URL', '')
    if backend == 'postgresql' and not dsn:
        raise ValueError('PORTAL_DATABASE_URL is required for PostgreSQL')
    control_dsn = env.get('PORTAL_CONTROL_DATABASE_URL', '')
    if backend == 'postgresql' and not control_dsn:
        raise ValueError('PORTAL_CONTROL_DATABASE_URL is required for PostgreSQL')
    if backend == 'postgresql' and environment == 'development':
        raise ValueError('PostgreSQL runtime requires PORTAL_ENV=test or production')
    if backend == 'postgresql' and environment == 'production':
        if env.get('PORTAL_ENABLE_POSTGRES_PRODUCTION', '').lower() != 'true':
            raise ValueError('Production PostgreSQL requires explicit PORTAL_ENABLE_POSTGRES_PRODUCTION=true')
        for name, value in (('PORTAL_DATABASE_URL', dsn),
                            ('PORTAL_CONTROL_DATABASE_URL', control_dsn)):
            parsed = urlsplit(value)
            if parsed.scheme not in ('postgresql', 'postgres') or not parsed.hostname or not parsed.username or not parsed.path.strip('/'):
                raise ValueError(f'Production requires a complete {name}')
    default_pool = '8' if backend == 'postgresql' and environment == 'production' else '0'
    try:
        postgres_pool_size = int(env.get('PORTAL_PG_POOL_SIZE', default_pool))
    except ValueError as exc:
        raise ValueError('Invalid PORTAL_PG_POOL_SIZE') from exc
    if not 0 <= postgres_pool_size <= 64:
        raise ValueError('Invalid PORTAL_PG_POOL_SIZE')
    setup_token = env.get('PORTAL_SETUP_TOKEN', '')
    if setup_token and (len(setup_token) < 32 or len(setup_token) > 256 or any(ch.isspace() for ch in setup_token)):
        raise ValueError('Invalid PORTAL_SETUP_TOKEN')
    return Config(environment, backend,
                  env.get('PORTAL_DB', str(Path.cwd() / 'portal.db')),
                  dsn, env.get('PORTAL_APP_HOST', '127.0.0.1' if environment == 'production' or backend == 'postgresql' else '0.0.0.0'),
                  port, url, control_dsn, postgres_pool_size, setup_token)
