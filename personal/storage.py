"""Workspace storage: SQLite locally; isolated PostgreSQL schemas on ephemeral hosts.

SQL used by this app is deliberately small. PostgreSQL preserves the existing
workspace boundaries and serializes explicit write transactions per workspace.
"""
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import ssl


class SQLiteConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def remote_enabled():
    return bool(os.environ.get('DATABASE_URL'))


def schema_for(path):
    name = Path(path).name
    if name == 'accounts.sqlite3':
        return 'takolo_accounts'
    if name == 'personal.sqlite3':
        return 'takolo_primary'
    if re.fullmatch(r'workspace-[a-f0-9]{32}\.sqlite3', name):
        return 'takolo_' + name[10:-8]
    raise ValueError('Identificador de espacio no válido para PostgreSQL.')


class Record(dict):
    def __getitem__(self, key):
        return list(self.values())[key] if isinstance(key, int) else super().__getitem__(key)

    def __iter__(self):
        return iter(self.values())


class Result:
    def __init__(self, cursor=None, columns=None, rows=None, lastrowid=None, rowcount=None):
        self.cursor = cursor
        self.columns = columns or []
        self.rows = rows
        self.lastrowid = lastrowid
        self.rowcount = cursor.rowcount if cursor is not None else (rowcount or 0)

    def _record(self, row):
        return None if row is None else Record(zip(self.columns, row))

    def fetchone(self):
        if self.rows is not None:
            return self._record(self.rows.pop(0)) if self.rows else None
        return self._record(self.cursor.fetchone())

    def fetchall(self):
        if self.rows is not None:
            rows, self.rows = self.rows, []
        else:
            rows = self.cursor.fetchall()
        return [self._record(row) for row in rows]


class PostgresConnection:
    def __init__(self, path):
        import psycopg
        from psycopg import sql
        self.path = str(path)
        self.schema = schema_for(path)
        self._lock = int.from_bytes(hashlib.sha256(self.schema.encode()).digest()[:8], 'big', signed=True)
        try:
            options = psycopg.conninfo.conninfo_to_dict(os.environ['DATABASE_URL'])
        except Exception:
            raise RuntimeError('DATABASE_URL no tiene un formato PostgreSQL válido.') from None
        host = options.get('host', '')
        # Only isolated loopback test instances may use plaintext. Remote hosts
        # always verify the server certificate and hostname against system roots.
        if host not in {'localhost', '127.0.0.1', '::1'}:
            # psycopg-binary bundles OpenSSL with build-machine default paths.
            # Use Python's resolved system bundle rather than libpq's "system".
            ca_bundle = ssl.get_default_verify_paths().cafile
            if not ca_bundle:
                raise RuntimeError('No se encontró el almacén de certificados TLS del sistema.')
            options.update(sslmode='verify-full', sslrootcert=ca_bundle)
        self._db = psycopg.connect(**options, autocommit=True, connect_timeout=15, prepare_threshold=None)
        self._db.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(self.schema)))

    def _transaction(self):
        import psycopg
        from psycopg import sql
        if self._db.info.transaction_status == psycopg.pq.TransactionStatus.IDLE:
            self._db.execute('BEGIN')
            # Transaction-local routing remains isolated with PgBouncer/Neon
            # pooling; it never depends on a previous session's search_path.
            self._db.execute(sql.SQL('SET LOCAL search_path TO {}').format(sql.Identifier(self.schema)))
            self._db.execute("SET LOCAL statement_timeout='30s'")
            self._db.execute("SET LOCAL idle_in_transaction_session_timeout='45s'")

    def execute(self, query, parameters=()):
        import psycopg
        normalized = query.strip().upper()
        if normalized == 'PRAGMA DATABASE_LIST':
            return Result(columns=['seq','name','file'], rows=[(0,'main',self.path)])
        if normalized.startswith('PRAGMA '):
            return Result()
        if normalized in {'BEGIN', 'BEGIN IMMEDIATE'}:
            self._transaction()
            self._db.execute('SELECT pg_advisory_xact_lock(%s)', (self._lock,))
            return Result()
        self._transaction()
        ignore = bool(re.match(r'INSERT\s+OR\s+IGNORE\b', query, re.I))
        translated = re.sub(r'INSERT\s+OR\s+IGNORE\b', 'INSERT', query, flags=re.I).rstrip().rstrip(';')
        translated = translated.replace('?', '%s')
        if ignore:
            translated += ' ON CONFLICT DO NOTHING'
        table = re.match(r'INSERT\s+INTO\s+([a-z_]+)', translated, re.I)
        returning = bool(table and table.group(1).lower() in {'clients','events','message_jobs','attempts'})
        if returning:
            translated += ' RETURNING id'
        try:
            cursor = self._db.execute(translated, tuple(parameters))
        except psycopg.IntegrityError:
            raise sqlite3.IntegrityError('La operación no cumple una restricción de los datos.') from None
        columns = [column.name for column in cursor.description] if cursor.description else []
        result = Result(cursor=cursor, columns=columns)
        if returning:
            row = cursor.fetchone()
            result.lastrowid = row[0] if row else None
        return result

    def executescript(self, script):
        self.commit()
        self._transaction()
        script = re.sub(r'\bINTEGER\s+PRIMARY\s+KEY\b', 'BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY', script, flags=re.I)
        script = re.sub(r'\bINTEGER\b', 'BIGINT', script, flags=re.I)
        script = re.sub(r'\bREAL\b', 'DOUBLE PRECISION', script, flags=re.I)
        for statement in script.split(';'):
            if statement.strip():
                self._db.execute(statement)
        self.commit()

    def commit(self):
        self._db.commit()

    def rollback(self):
        self._db.rollback()

    def close(self):
        self._db.rollback()
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, kind, *_):
        try:
            self.rollback() if kind else self.commit()
        finally:
            self.close()


def connect(path):
    if remote_enabled():
        return PostgresConnection(path)
    if os.environ.get('TAKOLO_REQUIRE_REMOTE_DB') == '1':
        raise RuntimeError('Falta DATABASE_URL. No se guardarán datos en el disco temporal del alojamiento gratuito.')
    connection = sqlite3.connect(str(path), timeout=15, factory=SQLiteConnection)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    return connection


def protect_local(path):
    if not remote_enabled():
        Path(path).chmod(0o600)
