"""Encrypted per-workspace credentials. No account inherits another account's keys."""
import json
import base64
import hashlib
import os
import sqlite3
import tempfile
from pathlib import Path
from cryptography.fernet import Fernet
from flask import current_app, has_request_context

FIELDS = ['META_ACCESS_TOKEN','META_PHONE_NUMBER_ID','META_GRAPH_VERSION','META_TEMPLATE_NAME',
          'META_TEMPLATE_LANGUAGE','META_APP_SECRET','META_VERIFY_TOKEN','WHATSAPP_SEND_ENABLED','META_CONNECTION_VERIFIED']
SECRET_FIELDS = {'META_ACCESS_TOKEN','META_APP_SECRET','META_VERIFY_TOKEN'}


def cipher_for(root):
    secret = os.environ.get('TAKOLO_ENCRYPTION_SECRET')
    if secret:
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))
    if os.environ.get('DATABASE_URL'):
        raise RuntimeError('Falta la clave persistente de cifrado.')
    path = Path(root) / 'connections.key'
    if not path.exists():
        with tempfile.NamedTemporaryFile(dir=root, delete=False) as temp:
            temporary = Path(temp.name)
            temp.write(Fernet.generate_key())
        temporary.chmod(0o600)
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
        finally:
            temporary.unlink()
    return Fernet(path.read_bytes())


def root_for(connection):
    return Path(connection.execute('PRAGMA database_list').fetchone()[2]).parent


def save_settings(connection, values):
    payload = cipher_for(root_for(connection)).encrypt(json.dumps(values).encode()).decode()
    connection.execute('INSERT INTO message_settings(id,payload) VALUES (1,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload', (payload,))
    connection.commit()


def settings(connection=None):
    values = dict.fromkeys(FIELDS, '')
    if connection is None and has_request_context():
        connection = current_app.extensions['workspace_db']()
    if connection is not None:
        row = connection.execute('SELECT payload FROM message_settings WHERE id=1').fetchone()
        if row:
            values.update(json.loads(cipher_for(root_for(connection)).decrypt(row['payload'].encode())))
    values['_SERVER_SEND_ENABLED'] = os.environ.get('WHATSAPP_SEND_ENABLED','0')
    return values
