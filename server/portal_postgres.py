"""Small PostgreSQL port for PORTAL's existing connection boundary.

This is not a SQL emulator. SQLite schema changes and upserts belong in explicit
backend branches. Only bound parameters and the three existing NOCASE shapes
are adapted here. Connections are never pooled, and tenant context is local to
each transaction. Importing this module does not require the PostgreSQL driver.
"""
import re


IDENTITY_TABLES = frozenset({
    'companies', 'platform_owners', 'platform_audit', 'app_users', 'portal_clients',
    'portal_client_operations', 'work_log', 'client_invoices', 'materials',
    'material_movements', 'operation_material_norms', 'production_jobs', 'audit_log',
})
CONTROL_LOCK = -706_672_841_003
MAX_COMPANY_ID = 2**63 - 1


class Row(tuple):
    """The mapping/sequence interface used by sqlite.Row call sites."""
    def __new__(cls, values, names):
        obj = super().__new__(cls, values)
        obj._names = tuple(names)
        obj._indices = {}
        for index, name in enumerate(obj._names):
            obj._indices.setdefault(name, index)
        return obj

    def keys(self):
        return list(self._names)

    def __getitem__(self, key):
        if isinstance(key, str):
            try:
                key = self._indices[key]
            except KeyError:
                raise IndexError('Column not found') from None
        return super().__getitem__(key)


def _segments(sql):
    """Yield SQL code separately from strings, identifiers and comments."""
    start = index = 0
    while index < len(sql):
        ch = sql[index]
        delimiter = None
        if ch in ("'", '"'):
            delimiter = ch
        elif ch == '$':
            match = re.match(r'\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$', sql[index:])
            if match:
                delimiter = match.group()
        if delimiter:
            if start < index:
                yield True, sql[start:index]
            quoted_start = index
            index += len(delimiter)
            while index < len(sql):
                if sql.startswith(delimiter, index):
                    index += len(delimiter)
                    if len(delimiter) == 1 and sql.startswith(delimiter, index):
                        index += 1
                        continue
                    break
                # PostgreSQL E'...' literals can escape their closing quote.
                is_escape = (delimiter == "'" and quoted_start > 0
                             and sql[quoted_start - 1] in 'eE'
                             and (quoted_start < 2 or not
                                  (sql[quoted_start - 2].isalnum() or sql[quoted_start - 2] == '_')))
                index += 2 if is_escape and sql[index] == '\\' else 1
            yield False, sql[quoted_start:index]
            start = index
        elif sql.startswith('--', index) or sql.startswith('/*', index):
            if start < index:
                yield True, sql[start:index]
            comment_start = index
            if sql.startswith('--', index):
                newline = sql.find('\n', index)
                index = len(sql) if newline < 0 else newline + 1
            else:
                index += 2
                depth = 1
                while index < len(sql) and depth:
                    if sql.startswith('/*', index):
                        depth += 1
                        index += 2
                    elif sql.startswith('*/', index):
                        depth -= 1
                        index += 2
                    else:
                        index += 1
            yield False, sql[comment_start:index]
            start = index
        else:
            index += 1
    if start < len(sql):
        yield True, sql[start:]


def _nocase_code(code):
    # Deliberately limited to API's existing unquoted identifier expressions.
    identifier = r'[A-Za-z_][A-Za-z_0-9]*(?:\.[A-Za-z_][A-Za-z_0-9]*)?'
    code = re.sub(r'(' + identifier + r')\s*=\s*(\?|%s)\s+COLLATE\s+NOCASE\b',
                  r'lower(\1)=lower(\2)', code, flags=re.I)
    return re.sub(r'(' + identifier + r')\s+COLLATE\s+NOCASE\b',
                  r'lower(\1)', code, flags=re.I)


def translate_sql(sql):
    """Convert positional placeholders; preserve literal ?, %, quoted SQL.

    psycopg parses percent placeholders even inside SQL string literals. Every
    literal percent must therefore be doubled, including those in comments.
    Native %s placeholders are accepted in code for the existing repository.
    PostgreSQL JSON '?' operators must use jsonb_exists() with this API.
    """
    result = []
    for is_code, segment in _segments(sql):
        if not is_code:
            result.append(segment.replace('%', '%%'))
            continue
        segment = _nocase_code(segment)
        index = 0
        while index < len(segment):
            if segment[index] == '?':
                result.append('%s')
            elif segment.startswith('%s', index):
                result.append('%s')
                index += 1
            elif segment[index] == '%':
                result.append('%%')
            else:
                result.append(segment[index])
            index += 1
    return ''.join(result)


def _returning_id(sql):
    code = ''.join(part if is_code else ' ' * len(part) for is_code, part in _segments(sql))
    if re.search(r'\bRETURNING\b', code, re.I):
        return sql, False
    match = re.match(r'\s*INSERT\s+INTO\s+(?:public\.)?([A-Za-z_][A-Za-z_0-9]*)\b', code, re.I)
    if not match or match.group(1).lower() not in IDENTITY_TABLES:
        return sql, False
    # Application INSERT statements are single statements, without trailing
    # comments. Reject surprising shapes rather than reinterpret SQL.
    trailing = sql.rstrip()
    if trailing.endswith(';'):
        trailing = trailing[:-1]
    return trailing + ' RETURNING id', True


class Cursor:
    def __init__(self, cursor, capture_id=False):
        self._cursor = cursor
        self.lastrowid = None
        if capture_id:
            row = cursor.fetchone()
            if row is not None:
                self.lastrowid = row[0]

    @property
    def description(self):
        return self._cursor.description

    @property
    def rowcount(self):
        return self._cursor.rowcount

    def _row(self, value):
        if value is None:
            return None
        return Row(value, [column[0] for column in self.description])

    def fetchone(self):
        return self._row(self._cursor.fetchone())

    def fetchall(self):
        return [self._row(row) for row in self._cursor.fetchall()]

    def __iter__(self):
        while True:
            row = self.fetchone()
            if row is None:
                return
            yield row

    def close(self):
        self._cursor.close()


class Connection:
    dialect = 'postgresql'

    def __init__(self, raw, company_id=None, company_key=None):
        if company_id is not None and (type(company_id) is not int or not 0 < company_id <= MAX_COMPANY_ID):
            raise PermissionError('Некорректная компания')
        if company_id is not None and (not isinstance(company_key, str) or len(company_key) < 64):
            raise PermissionError('Ключ контекста компании отсутствует')
        self._raw = raw
        self.company_id = company_id
        self._company_key = company_key
        self._context_applied = False

    def _ensure_context(self):
        if not self._context_applied:
            if self.company_id is None:
                # The control role never receives tenant data privileges.
                self._raw.execute("SELECT set_config('portal.company_id', %s, true)", ('',))
            else:
                self._raw.execute('SELECT portal_bind_company(%s,%s)',
                                  (self.company_id, self._company_key))
            self._context_applied = True

    def execute(self, sql, parameters=()):
        self._ensure_context()
        if sql.strip().rstrip(';').upper() == 'BEGIN IMMEDIATE':
            key = CONTROL_LOCK if self.company_id is None else self.company_id
            return Cursor(self._raw.execute('SELECT pg_advisory_xact_lock(%s)', (key,)))
        sql, capture_id = _returning_id(sql)
        return Cursor(self._raw.execute(translate_sql(sql), tuple(parameters)), capture_id)

    def commit(self):
        try:
            self._raw.commit()
        finally:
            self._context_applied = False

    def rollback(self):
        try:
            self._raw.rollback()
        finally:
            self._context_applied = False

    def close(self):
        self._raw.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        try:
            self.rollback() if exc_type is not None else self.commit()
        except Exception:
            if exc_type is None:
                raise
        finally:
            self.close()
        return False


def connect(dsn, company_id=None, company_key=None):
    """Open a new scoped connection without leaking DSN or connection errors."""
    if company_id is not None and (type(company_id) is not int or not 0 < company_id <= MAX_COMPANY_ID):
        raise PermissionError('Некорректная компания')
    try:
        import psycopg
    except ImportError:
        raise RuntimeError('Для PostgreSQL требуется драйвер psycopg 3') from None
    try:
        raw = psycopg.connect(dsn, connect_timeout=10, autocommit=False)
    except Exception:
        raise ConnectionError('Не удалось подключиться к PostgreSQL') from None
    connection = Connection(raw, company_id, company_key)
    try:
        connection._ensure_context()
        return connection
    except Exception:
        raw.close()
        raise ConnectionError('Не удалось установить контекст PostgreSQL') from None


def table_exists(conn, name):
    return conn.execute('SELECT 1 FROM information_schema.tables WHERE table_schema=current_schema() AND table_name=?', (name,)).fetchone() is not None


def columns(conn, table):
    return [row[0] for row in conn.execute('SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=? ORDER BY ordinal_position', (table,))]


def table_names(conn):
    return [row[0] for row in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=current_schema() AND table_type='BASE TABLE' ORDER BY table_name")]


def validate_runtime_role(conn):
    """Fail closed for roles able to bypass tenant isolation or create tables."""
    row = conn.execute('''SELECT r.rolsuper, r.rolbypassrls,
        has_schema_privilege(current_user, 'public', 'CREATE'),
        EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relkind IN ('r','p')
                  AND pg_has_role(current_user,c.relowner,'USAGE')),
        EXISTS (SELECT 1 FROM pg_roles privileged
                WHERE (privileged.rolsuper OR privileged.rolbypassrls)
                  AND pg_has_role(current_user,privileged.oid,'MEMBER'))
        FROM pg_roles r WHERE r.rolname=current_user''').fetchone()
    if row is None or any(row):
        raise PermissionError('Роль PostgreSQL не удовлетворяет ограничениям изоляции PORTAL')
    return True
