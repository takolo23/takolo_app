"""Central identities; every workspace has its own database and connections."""
import re
import secrets
import sqlite3
import time
from pathlib import Path
from flask import g, has_request_context, session
from werkzeug.security import generate_password_hash


from .storage import connect, protect_local


class Accounts:
    def __init__(self, root, initialize):
        self.root = Path(root)
        self.path = self.root / 'accounts.sqlite3'
        self.initialize = initialize
        with connect(self.path) as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, name TEXT NOT NULL,
                password TEXT NOT NULL, db_name TEXT UNIQUE NOT NULL, role TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1, session_version INTEGER NOT NULL DEFAULT 1);
            CREATE TABLE IF NOT EXISTS auth_attempts (bucket TEXT NOT NULL, created_at REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS phone_bindings (
                account_id TEXT PRIMARY KEY REFERENCES accounts(id), phone_id TEXT UNIQUE NOT NULL);
            ''')
        protect_local(self.path)
        # Retain any pre-existing personal workspace under a documented login.
        with connect(self.root / 'personal.sqlite3') as legacy, connect(self.path) as identities:
            old = legacy.execute('SELECT * FROM owner WHERE id=1').fetchone()
            if old and not identities.execute('SELECT 1 FROM accounts LIMIT 1').fetchone():
                identities.execute('INSERT INTO accounts(id,username,name,password,db_name,role) VALUES (?,?,?,?,?,?)',
                                   (secrets.token_hex(16), 'principal', old['name'], old['password'], 'personal.sqlite3', 'admin'))

    def any(self):
        with connect(self.path) as db:
            return bool(db.execute('SELECT 1 FROM accounts LIMIT 1').fetchone())

    def find(self, username):
        with connect(self.path) as db:
            return db.execute('SELECT * FROM accounts WHERE username=?', (username.strip().lower(),)).fetchone()

    def by_id(self, account_id):
        with connect(self.path) as db:
            return db.execute('SELECT * FROM accounts WHERE id=?', (account_id,)).fetchone()

    def current(self):
        if not has_request_context():
            return None
        if not hasattr(g, 'account'):
            row = self.by_id(session.get('account_id', ''))
            g.account = row if row and row['active'] and row['session_version'] == session.get('session_version') else None
        return g.account

    def database(self, account):
        filename = account['db_name']
        if not re.fullmatch(r'personal\.sqlite3|workspace-[a-f0-9]{32}\.sqlite3', filename):
            raise ValueError('Ruta de espacio no válida.')
        return self.root / filename

    def create(self, username, name, password, administrator=False):
        username = username.strip().lower()
        if not re.fullmatch(r'[a-z0-9_.-]{3,60}', username):
            raise ValueError('El usuario debe tener de 3 a 60 letras sin acentos, números, puntos, guiones o guiones bajos.')
        if not name or len(password) < 10:
            raise ValueError('Escribe tu nombre y una contraseña de al menos 10 caracteres.')
        identity = secrets.token_hex(16)
        password_hash = generate_password_hash(password)
        with connect(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            first = not db.execute('SELECT 1 FROM accounts LIMIT 1').fetchone()
            if administrator != first:
                raise ValueError('La administración inicial ya está configurada o todavía no está disponible.')
            filename = 'personal.sqlite3' if first else 'workspace-' + identity + '.sqlite3'
            db.execute('INSERT INTO accounts(id,username,name,password,db_name,role) VALUES (?,?,?,?,?,?)',
                       (identity, username, name[:100], password_hash, filename, 'admin' if first else 'user'))
            with connect(self.root / filename) as workspace:
                self.initialize(workspace)
                workspace.execute('INSERT INTO owner VALUES (1,?,?)', (name[:100], password_hash))
            protect_local(self.root / filename)
        return self.by_id(identity)

    def throttled(self, bucket):
        with connect(self.path) as db:
            db.execute('DELETE FROM auth_attempts WHERE created_at<?', (time.time() - 300,))
            return db.execute('SELECT COUNT(*) FROM auth_attempts WHERE bucket=?', (bucket,)).fetchone()[0] >= 10

    def failed(self, bucket):
        with connect(self.path) as db:
            db.execute('INSERT INTO auth_attempts VALUES (?,?)', (bucket, time.time()))

    def all(self, active_only=False):
        with connect(self.path) as db:
            return db.execute('SELECT * FROM accounts' + (' WHERE active=1' if active_only else '') + ' ORDER BY username').fetchall()
