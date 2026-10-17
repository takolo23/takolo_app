"""Official WhatsApp templates with explicit consent, dry runs and durable results."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, url_for
from .accounts import connect
from .connections import settings, save_settings, FIELDS, SECRET_FIELDS


def stamp():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def phone_number(value):
    value = re.sub(r'[\s()-]', '', str(value))
    if not re.fullmatch(r'\+[1-9]\d{7,14}', value):
        raise ValueError('Usa formato internacional con + y código de país, por ejemplo +525512345678.')
    return value


def live_ready(config):
    return config.get('_SERVER_SEND_ENABLED') == '1' and config.get('META_CONNECTION_VERIFIED') == '1' and config['WHATSAPP_SEND_ENABLED'] == '1' and all(config[key] for key in [
        'META_ACCESS_TOKEN', 'META_PHONE_NUMBER_ID', 'META_GRAPH_VERSION', 'META_TEMPLATE_NAME',
        'META_TEMPLATE_LANGUAGE', 'META_APP_SECRET', 'META_VERIFY_TOKEN'])


def init_schema(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS message_settings (id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS message_consent (
        client_id INTEGER PRIMARY KEY REFERENCES clients(id), phone TEXT NOT NULL, granted INTEGER NOT NULL,
        proof TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS message_jobs (
        id INTEGER PRIMARY KEY, client_id INTEGER NOT NULL REFERENCES clients(id), request_key TEXT NOT NULL UNIQUE,
        phone TEXT NOT NULL, mode TEXT NOT NULL CHECK(mode IN ('test','live')), template TEXT NOT NULL,
        language TEXT NOT NULL, parameter TEXT NOT NULL, state TEXT NOT NULL,
        provider_id TEXT UNIQUE, detail TEXT NOT NULL DEFAULT '', attempts INTEGER NOT NULL DEFAULT 0,
        available_at TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS message_queue ON message_jobs(state,available_at);
    CREATE TABLE IF NOT EXISTS message_job_rules (
        job_id INTEGER PRIMARY KEY REFERENCES message_jobs(id), require_balance INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS message_dispatches (
        id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL REFERENCES message_jobs(id), started_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS message_receipts (
        provider_id TEXT PRIMARY KEY, state TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL);
    ''')
    db.commit()


def api(config, method, suffix, payload=None):
    version = config['META_GRAPH_VERSION']
    if not re.fullmatch(r'v\d+\.\d+', version) or not config['META_PHONE_NUMBER_ID'].isdigit():
        raise ValueError('Revisa la versión de Graph y el ID del número en la configuración.')
    url = f"https://graph.facebook.com/{version}/{config['META_PHONE_NUMBER_ID']}{suffix}"
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={
        'Authorization': 'Bearer ' + config['META_ACCESS_TOKEN'], 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=20, context=ssl.create_default_context()) as response:
        return json.load(response)


def message_payload(job):
    # The configured approved template must have exactly one body variable: customer name.
    return {'messaging_product': 'whatsapp', 'to': job['phone'].lstrip('+'), 'type': 'template',
            'template': {'name': job['template'], 'language': {'code': job['language']},
                         'components': [{'type': 'body', 'parameters': [{'type': 'text', 'text': job['parameter']}]}]}}


def process_one(db, transport=api, config=None, only_mode=None):
    config = settings(db) if config is None else config
    db.execute('BEGIN IMMEDIATE')
    query = "SELECT * FROM message_jobs WHERE state='queued' AND available_at<=?"
    args = [stamp()]
    if only_mode:
        query += ' AND mode=?'
        args.append(only_mode)
    job = db.execute(query + ' ORDER BY id LIMIT 1', args).fetchone()
    if not job:
        db.rollback()
        return False
    consent = db.execute('SELECT * FROM message_consent WHERE client_id=?', (job['client_id'],)).fetchone()
    client = db.execute('SELECT phone,balance_cents FROM clients WHERE id=?', (job['client_id'],)).fetchone()
    rule = db.execute('SELECT require_balance FROM message_job_rules WHERE job_id=?', (job['id'],)).fetchone()
    try:
        current_phone = phone_number(client['phone'])
    except (ValueError, TypeError):
        current_phone = ''
    reason = ''
    if not consent or not consent['granted'] or consent['phone'] != job['phone'] or current_phone != job['phone']:
        reason = 'Envío cancelado: falta autorización vigente para este número.'
    elif job['mode'] == 'live' and not live_ready(config):
        reason = 'Envío cancelado: la conexión real no está habilitada o está incompleta.'
    elif rule and rule['require_balance'] and client['balance_cents'] <= 0:
        reason = 'Recordatorio cancelado: el cliente ya liquidó su saldo.'
    if reason:
        db.execute("UPDATE message_jobs SET state='cancelled',detail=?,updated_at=? WHERE id=?", (reason, stamp(), job['id']))
        db.commit()
        return True
    if job['mode'] == 'test':
        db.execute("UPDATE message_jobs SET state='simulated',detail='Simulación terminada; no se contactó a WhatsApp ni al destinatario.',updated_at=? WHERE id=?", (stamp(), job['id']))
        db.commit()
        return True
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if db.execute('SELECT COUNT(*) FROM message_dispatches WHERE started_at>=?', (today,)).fetchone()[0] >= 50:
        tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime('%Y-%m-%d 00:00:00')
        db.execute("UPDATE message_jobs SET available_at=?,detail='Límite diario alcanzado; pendiente para el siguiente día.',updated_at=? WHERE id=?", (tomorrow, stamp(), job['id']))
        db.commit()
        return True
    db.execute('INSERT INTO message_dispatches(job_id,started_at) VALUES (?,?)', (job['id'], stamp()))
    db.execute("UPDATE message_jobs SET state='sending', attempts=attempts+1,updated_at=? WHERE id=?", (stamp(), job['id']))
    db.commit()
    state, detail, provider_id, available = 'failed', '', None, stamp()
    try:
        result = transport(config, 'POST', '/messages', message_payload(job))
        provider_id = result.get('messages', [{}])[0].get('id')
        if not provider_id:
            state, detail = 'uncertain', 'Respuesta sin identificador. Revisa en Meta antes de volver a enviar.'
        else:
            state, detail = 'accepted', 'Aceptado por WhatsApp. La entrega se confirma por webhook.'
    except urllib.error.HTTPError as exc:
        if exc.code == 429 and job['attempts'] < 2:
            state, detail = 'queued', 'El proveedor pidió esperar; se volverá a intentar en cinco minutos.'
            available = (datetime.now(timezone.utc) + timedelta(minutes=5)).strftime('%Y-%m-%d %H:%M:%S')
        else:
            state = 'uncertain' if exc.code >= 500 else 'failed'
            detail = f'WhatsApp respondió HTTP {exc.code}. ' + ('Revisa en Meta antes de reenviar.' if state == 'uncertain' else 'Revisa permisos, plantilla y número en Meta.')
    except ValueError:
        state, detail = 'failed', 'La configuración de Meta o su respuesta no es válida.'
    except (OSError, TimeoutError, IndexError, KeyError, TypeError):
        state, detail = 'uncertain', 'No se confirmó el resultado. No se reintentará automáticamente para evitar duplicados.'
    db.execute('BEGIN IMMEDIATE')
    receipt = db.execute('SELECT * FROM message_receipts WHERE provider_id=?', (provider_id,)).fetchone() if provider_id else None
    if receipt:
        state, detail = receipt['state'], receipt['detail']
    db.execute('UPDATE message_jobs SET state=?,detail=?,provider_id=?,available_at=?,updated_at=? WHERE id=?',
               (state, detail, provider_id, available, stamp(), job['id']))
    db.commit()
    return True


def register_messaging(app, db, login_required):
    bp = Blueprint('messaging', __name__)
    with app.app_context():
        init_schema(db())

    @bp.route('/connections', methods=['GET','POST'])
    @login_required
    def connection_settings():
        config = settings()
        if request.method == 'POST':
            for key in FIELDS:
                if key == 'META_CONNECTION_VERIFIED':
                    continue
                value = request.form.get(key, '').strip()[:4096]
                if key not in SECRET_FIELDS or value:
                    config[key] = value
            config['WHATSAPP_SEND_ENABLED'] = '1' if request.form.get('WHATSAPP_SEND_ENABLED') == '1' else '0'
            config['META_CONNECTION_VERIFIED'] = '0'
            config.pop('_SERVER_SEND_ENABLED', None)
            save_settings(db(), config)
            with connect(app.extensions['accounts'].path) as identities:
                identities.execute('DELETE FROM phone_bindings WHERE account_id=?', (app.extensions['accounts'].current()['id'],))
            flash('Conexión guardada para tu cuenta. Comprueba el acceso al número antes de habilitar envíos.', 'success')
            return redirect(url_for('messaging.connection_settings'))
        public = {k:v for k,v in config.items() if k not in SECRET_FIELDS}
        return render_template('connections.html', connection=public,
                               present={k:bool(config[k]) for k in SECRET_FIELDS},
                               account_id=app.extensions['accounts'].current()['id'])

    @bp.post('/connections/disconnect')
    @login_required
    def disconnect():
        db().execute('DELETE FROM message_settings')
        db().execute("UPDATE message_jobs SET state='cancelled',detail='Conexión desconectada.',updated_at=? WHERE mode='live' AND state='queued'", (stamp(),))
        db().commit()
        with connect(app.extensions['accounts'].path) as identities:
            identities.execute('DELETE FROM phone_bindings WHERE account_id=?', (app.extensions['accounts'].current()['id'],))
        flash('Conexión retirada de tu cuenta. Los mensajes reales pendientes se cancelaron.', 'success')
        return redirect(url_for('messaging.connection_settings'))

    @bp.get('/messages')
    @login_required
    def index():
        config = settings()
        clients = db().execute('SELECT clients.*,message_consent.granted,message_consent.phone consent_phone,message_consent.proof FROM clients LEFT JOIN message_consent ON clients.id=message_consent.client_id ORDER BY clients.name').fetchall()
        eligible = set()
        for client in clients:
            try:
                if client['granted'] and phone_number(client['phone']) == client['consent_phone']:
                    eligible.add(client['id'])
            except ValueError:
                pass
        jobs = db().execute('SELECT message_jobs.*,clients.name FROM message_jobs JOIN clients ON clients.id=message_jobs.client_id ORDER BY message_jobs.id DESC LIMIT 100').fetchall()
        import secrets
        return render_template('messages.html', clients=clients, eligible=eligible, jobs=jobs, ready=live_ready(config),
                               request_key=secrets.token_urlsafe(24), template=config['META_TEMPLATE_NAME'], language=config['META_TEMPLATE_LANGUAGE'])

    @bp.post('/messages/consent/<int:client_id>')
    @login_required
    def consent(client_id):
        client = db().execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        if not client:
            abort(404)
        try:
            phone = phone_number(client['phone'])
            granted = request.form.get('granted') == 'yes'
            proof = request.form.get('proof', '').strip()[:500]
            if granted and len(proof) < 10:
                raise ValueError('Anota cómo y cuándo esta persona autorizó el contacto por WhatsApp.')
            db().execute('INSERT INTO message_consent VALUES (?,?,?,?,?) ON CONFLICT(client_id) DO UPDATE SET phone=excluded.phone,granted=excluded.granted,proof=excluded.proof,updated_at=excluded.updated_at',
                         (client_id, phone, int(granted), proof or 'Autorización retirada.', stamp()))
            if not granted:
                db().execute("UPDATE message_consent SET granted=0,proof='Autorización retirada.',updated_at=? WHERE phone=?", (stamp(), phone))
                db().execute("UPDATE message_jobs SET state='cancelled',detail='Autorización retirada.',updated_at=? WHERE phone=? AND state='queued'", (stamp(), phone))
            db().commit()
            flash('Autorización actualizada.', 'success')
        except ValueError as exc:
            flash(str(exc), 'error')
        return redirect(url_for('messaging.index'))

    @bp.post('/messages/queue')
    @login_required
    def queue():
        config = settings()
        mode = request.form.get('mode', 'test')
        if mode not in {'test', 'live'}:
            abort(400)
        if mode == 'live' and (not live_ready(config) or request.form.get('confirm_live') != 'yes'):
            flash('El envío real requiere configuración completa y confirmación expresa de los destinatarios.', 'error')
            return redirect(url_for('messaging.index'))
        ids = list(dict.fromkeys(request.form.getlist('clients')))
        key = request.form.get('request_key', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{32}', key) or not ids or len(ids) > 50 or not all(i.isdigit() for i in ids):
            flash('Selecciona entre 1 y 50 clientes para esta prueba o envío.', 'error')
            return redirect(url_for('messaging.index'))
        available = stamp()
        scheduled = request.form.get('send_at', '').strip()
        if scheduled:
            try:
                when = datetime.strptime(scheduled, '%Y-%m-%dT%H:%M').replace(tzinfo=ZoneInfo('America/Mexico_City')).astimezone(timezone.utc)
                current = datetime.now(timezone.utc)
                if not current < when <= current + timedelta(days=90):
                    raise ValueError()
                available = when.strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                flash('Elige una fecha futura dentro de los próximos 90 días, en horario de Ciudad de México.', 'error')
                return redirect(url_for('messaging.index'))
        balance_only = request.form.get('balance_only') == 'yes'
        connection = db()
        connection.execute('BEGIN IMMEDIATE')
        if mode == 'live':
            today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            existing = connection.execute("SELECT COUNT(*) FROM message_jobs WHERE mode='live' AND created_at>=? AND state!='cancelled'", (today,)).fetchone()[0]
            if existing + len(ids) > 50:
                connection.rollback()
                flash('Se alcanzó el límite de 50 mensajes reales por día de esta aplicación. Esto no sustituye los límites o políticas de Meta.', 'error')
                return redirect(url_for('messaging.index'))
        prepared, errors, seen_phones = [], [], set()
        for client_id in ids:
            client = connection.execute('SELECT c.*,s.granted,s.phone consent_phone FROM clients c LEFT JOIN message_consent s ON c.id=s.client_id WHERE c.id=?', (client_id,)).fetchone()
            try:
                if not client:
                    raise ValueError('Hay un cliente que ya no existe.')
                phone = phone_number(client['phone'])
                if not client['granted'] or client['consent_phone'] != phone:
                    raise ValueError(f"Falta autorización vigente: {client['name']}.")
                if balance_only and client['balance_cents'] <= 0:
                    raise ValueError(f"El cliente ya no tiene saldo pendiente: {client['name']}.")
                if phone not in seen_phones:
                    prepared.append((client, phone))
                    seen_phones.add(phone)
            except ValueError as exc:
                errors.append(str(exc))
        if errors:
            connection.rollback()
            flash('No se agregó ningún mensaje. ' + ' '.join(errors[:3]), 'error')
        else:
            added = 0
            for client, phone in prepared:
                cursor = connection.execute('INSERT OR IGNORE INTO message_jobs(client_id,request_key,phone,mode,template,language,parameter,state,available_at,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                                            (client['id'], key + ':' + str(client['id']), phone, mode, config['META_TEMPLATE_NAME'] or 'vista_previa', config['META_TEMPLATE_LANGUAGE'] or 'es_MX', client['name'], 'queued', available, stamp(), stamp()))
                if cursor.rowcount:
                    connection.execute('INSERT INTO message_job_rules(job_id,require_balance) VALUES (?,?)', (cursor.lastrowid, int(balance_only)))
                added += cursor.rowcount
            connection.commit()
            flash(f'{added} mensajes agregados a la cola. ' + ('Son simulaciones: no se enviará nada.' if mode == 'test' else 'Se usará la plantilla aprobada configurada en Meta.'), 'success')
        return redirect(url_for('messaging.index'))

    @bp.post('/messages/test-process')
    @login_required
    def test_process():
        # Web action processes simulations only. Real jobs belong to the worker.
        connection = db()
        for _ in range(50):
            if not process_one(connection, only_mode='test'):
                break
        flash('Pruebas terminadas. Ninguna simulación envió mensajes reales.', 'success')
        return redirect(url_for('messaging.index'))

    @bp.post('/messages/cancel/<int:job_id>')
    @login_required
    def cancel(job_id):
        db().execute("UPDATE message_jobs SET state='cancelled',detail='Cancelado desde la aplicación.',updated_at=? WHERE id=? AND state='queued'", (stamp(), job_id))
        db().commit()
        flash('Solicitud de cancelación registrada. Solo se cancelan mensajes que aún están en cola.', 'success')
        return redirect(url_for('messaging.index'))

    @bp.post('/messages/check-connection')
    @login_required
    def check_connection():
        config = settings()
        if not config['META_ACCESS_TOKEN'] or not config['META_PHONE_NUMBER_ID'] or not config['META_GRAPH_VERSION']:
            flash('Faltan credenciales de Meta. Configura tu propia conexión en Conexión de WhatsApp.', 'error')
        else:
            try:
                result = api(config, 'GET', '?fields=id,display_phone_number,verified_name,quality_rating')
                if str(result.get('id')) != config['META_PHONE_NUMBER_ID']:
                    raise ValueError('Respuesta inesperada.')
                account = app.extensions['accounts'].current()
                try:
                    with connect(app.extensions['accounts'].path) as identities:
                        identities.execute('INSERT INTO phone_bindings(account_id,phone_id) VALUES (?,?) ON CONFLICT(account_id) DO UPDATE SET phone_id=excluded.phone_id', (account['id'], config['META_PHONE_NUMBER_ID']))
                except sqlite3.IntegrityError:
                    flash('Este número ya está conectado a otra cuenta de la plataforma.', 'error')
                    return redirect(url_for('messaging.connection_settings'))
                config['META_CONNECTION_VERIFIED'] = '1'
                config.pop('_SERVER_SEND_ENABLED', None)
                save_settings(db(), config)
                flash('Conexión con el número verificada. Esto no acredita que la plantilla esté aprobada ni garantiza la entrega.', 'success')
            except (OSError, ValueError, TypeError):
                flash('No se pudo verificar la conexión. Revisa permisos, número, versión de Graph y acceso de red.', 'error')
        return redirect(url_for('messaging.index'))

    @bp.route('/webhooks/whatsapp/<account_id>', methods=['GET', 'POST'])
    def webhook(account_id):
        account = app.extensions['accounts'].by_id(account_id)
        if not account or not account['active']:
            abort(404)
        g.webhook_account = account
        config = settings(db())
        if request.method == 'GET':
            supplied = request.args.get('hub.verify_token', '')
            if config['META_VERIFY_TOKEN'] and hmac.compare_digest(supplied, config['META_VERIFY_TOKEN']) and request.args.get('hub.mode') == 'subscribe':
                return request.args.get('hub.challenge', ''), 200
            abort(403)
        if not config['META_APP_SECRET']:
            abort(503)
        raw = request.get_data()
        signature = 'sha256=' + hmac.new(config['META_APP_SECRET'].encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, request.headers.get('X-Hub-Signature-256', '')):
            abort(403)
        content = request.get_json(silent=True)
        if not isinstance(content, dict):
            abort(400)
        connection = db()
        ranks = {'accepted': 0, 'sent': 1, 'delivered': 2, 'read': 3}
        for entry in content.get('entry', []):
            for change in entry.get('changes', []):
                value = change.get('value', {})
                if str(value.get('metadata', {}).get('phone_number_id', '')) != config['META_PHONE_NUMBER_ID']:
                    continue
                for status in value.get('statuses', []):
                    state, provider_id = status.get('status'), status.get('id')
                    if state not in {'sent', 'delivered', 'read', 'failed'} or not isinstance(provider_id, str):
                        continue
                    previous = connection.execute('SELECT state FROM message_receipts WHERE provider_id=?', (provider_id,)).fetchone()
                    if previous and (ranks.get(previous['state'], -1) > ranks.get(state, -1) or previous['state'] in {'delivered','read'} and state == 'failed'):
                        continue
                    detail = 'Confirmado por WhatsApp: ' + state
                    connection.execute('INSERT INTO message_receipts VALUES (?,?,?,?) ON CONFLICT(provider_id) DO UPDATE SET state=excluded.state,detail=excluded.detail,updated_at=excluded.updated_at', (provider_id, state, detail, stamp()))
                    connection.execute('UPDATE message_jobs SET state=?,detail=?,updated_at=? WHERE provider_id=?', (state, detail, stamp(), provider_id))
                for message in value.get('messages', []):
                    if message.get('type') == 'text' and message.get('text', {}).get('body', '').strip().upper() in {'BAJA','STOP','CANCELAR','NO MAS','NO MÁS'}:
                        try:
                            phone = phone_number('+' + message.get('from', ''))
                        except ValueError:
                            continue
                        connection.execute("UPDATE message_consent SET granted=0,proof='Baja recibida por WhatsApp.',updated_at=? WHERE phone=?", (stamp(), phone))
                        connection.execute("UPDATE message_jobs SET state='cancelled',detail='Baja recibida por WhatsApp.',updated_at=? WHERE phone=? AND state='queued'", (stamp(), phone))
        connection.commit()
        return jsonify(status='ok')

    app.register_blueprint(bp)
