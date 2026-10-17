"""Personal portfolio workspace. Run with: python -m personal.app."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import secrets
import sqlite3
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from flask import Flask, abort, flash, g, has_request_context, redirect, render_template, request, send_file, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from .icons import icon
from .accounts import Accounts, connect

FIELDS = {'reference': 'Referencia', 'name': 'Nombre del cliente', 'phone': 'Teléfono',
          'balance': 'Saldo', 'manager': 'Gestor', 'status': 'Estado'}
ALIASES = {
    'reference': ['referencia', 'folio', 'contrato', 'credito', 'id', 'cuenta'],
    'name': ['nombre', 'cliente', 'nombre cliente', 'deudor', 'titular'],
    'phone': ['telefono', 'celular', 'whatsapp', 'tel', 'cel', 'movil'],
    'balance': ['saldo', 'monto', 'adeudo', 'deuda', 'saldo total', 'saldo actual'],
    'manager': ['gestor', 'asignado', 'ejecutivo', 'asesor', 'agente'],
    'status': ['estado', 'estatus', 'status', 'situacion'],
}

def now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value).lower().strip()) if not unicodedata.combining(c))


def cents(value):
    raw = str(value).strip().replace('MXN', '').replace('$', '').replace(' ', '')
    if not raw:
        raise ValueError('El monto está vacío.')
    if ',' in raw and '.' in raw:
        if raw.rfind(',') > raw.rfind('.'):
            if not re.fullmatch(r'\d{1,3}(?:\.\d{3})+,\d{1,2}', raw):
                raise ValueError('Revisa los separadores del monto; usa por ejemplo 1234.56.')
            raw = raw.replace('.', '').replace(',', '.')
        else:
            if not re.fullmatch(r'\d{1,3}(?:,\d{3})+\.\d{1,2}', raw):
                raise ValueError('Revisa los separadores del monto; usa por ejemplo 1234.56.')
            raw = raw.replace(',', '')
    elif ',' in raw:
        if raw.count(',') == 1 and len(raw.rsplit(',', 1)[1]) <= 2:
            raw = raw.replace(',', '.')
        elif re.fullmatch(r'\d{1,3}(?:,\d{3})+', raw):
            raw = raw.replace(',', '')
        else:
            raise ValueError('Revisa los separadores del monto; usa por ejemplo 1234.56.')
    if not re.fullmatch(r'\d+(?:\.\d{1,2})?', raw):
        raise ValueError('Escribe un monto positivo con un máximo de dos decimales.')
    try:
        amount = Decimal(raw)
        if not amount.is_finite() or amount < 0 or amount > Decimal('10000000000'):
            raise ValueError('El monto debe estar entre 0 y 10,000,000,000.')
        return int((amount * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except InvalidOperation as exc:
        raise ValueError('Escribe un monto válido, por ejemplo 1500.50.') from exc


def create_app(config=None):
    app = Flask(__name__)
    if os.environ.get('TAKOLO_TRUST_PROXY') == '1':
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    app.jinja_env.globals['icon'] = icon
    root = Path(os.environ.get('PERSONAL_DATA_DIR', '/workspace/.personal-app'))
    app.config.update(DATA_DIR=root, MAX_CONTENT_LENGTH=10 * 1024 * 1024,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SETUP_TOKEN=os.environ.get('PERSONAL_SETUP_TOKEN', ''),
                      SESSION_COOKIE_SECURE=os.environ.get('PERSONAL_HTTPS') == '1')
    if config:
        app.config.update(config)
    root = Path(app.config['DATA_DIR'])
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not app.config.get('SECRET_KEY'):
        key = root / 'session.key'
        try:
            with key.open('x') as f:
                os.chmod(key, 0o600)
                f.write(secrets.token_hex(32))
        except FileExistsError:
            pass
        app.config['SECRET_KEY'] = key.read_text().strip()
    app.config['DATABASE'] = str(root / 'personal.sqlite3')

    def initialize_workspace(connection):
        connection.executescript('''
        CREATE TABLE IF NOT EXISTS owner (id INTEGER PRIMARY KEY CHECK(id=1), name TEXT NOT NULL, password TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY, reference TEXT NOT NULL UNIQUE, name TEXT NOT NULL, phone TEXT NOT NULL DEFAULT '',
            manager TEXT NOT NULL DEFAULT 'Personal', initial_cents INTEGER NOT NULL CHECK(initial_cents>=0),
            balance_cents INTEGER NOT NULL CHECK(balance_cents>=0), notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, client_id INTEGER REFERENCES clients(id), kind TEXT NOT NULL,
            amount_cents INTEGER NOT NULL DEFAULT 0, detail TEXT NOT NULL, created_at TEXT NOT NULL,
            request_key TEXT UNIQUE);
        CREATE TABLE IF NOT EXISTS stages (id TEXT PRIMARY KEY, filename TEXT NOT NULL, data TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS attempts (id INTEGER PRIMARY KEY, created_at REAL NOT NULL);
        ''')
        from .messaging import init_schema
        init_schema(connection)

    with connect(app.config['DATABASE']) as initial:
        initialize_workspace(initial)
    accounts = Accounts(root, initialize_workspace)
    app.extensions['accounts'] = accounts

    def db():
        if 'db' not in g:
            account = getattr(g, 'webhook_account', None) or accounts.current()
            if has_request_context() and not account:
                abort(401)
            path = accounts.database(account) if account else Path(app.config['DATABASE'])
            g.db = connect(path)
        return g.db

    app.extensions['workspace_db'] = db

    @app.teardown_appcontext
    def close_db(_):
        connection = g.pop('db', None)
        if connection:
            connection.close()

    def owner():
        return accounts.current()

    @app.context_processor
    def context():
        return dict(csrf_token=session.setdefault('csrf', secrets.token_hex(24)), owner=owner(), fields=FIELDS)

    app.jinja_env.filters['money'] = lambda value: f'${value / 100:,.2f}'
    app.jinja_env.filters['localtime'] = lambda value: datetime.strptime(value, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).astimezone(ZoneInfo('America/Mexico_City')).strftime('%d/%m/%Y · %H:%M')

    @app.before_request
    def csrf():
        if request.method == 'POST' and request.endpoint != 'messaging.webhook':
            expected = session.get('csrf', '')
            if not expected or not secrets.compare_digest(expected, request.form.get('csrf_token', '')):
                abort(400, 'La sesión del formulario venció. Recarga la página e inténtalo de nuevo.')

    def login_required(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not owner():
                return redirect(url_for('login' if accounts.any() else 'setup'))
            return fn(*args, **kwargs)
        return wrapped

    def enter(account):
        session.clear()
        session.update(logged_in=True, account_id=account['id'], session_version=account['session_version'])

    @app.route('/setup', methods=['GET', 'POST'])
    def setup():
        if accounts.any():
            return redirect(url_for('login'))
        return register_account(True)

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if not accounts.any():
            return redirect(url_for('setup'))
        if os.environ.get('TAKOLO_REGISTRATION_OPEN', '1') != '1':
            abort(403)
        return register_account(False)

    def register_account(administrator):
        if request.method == 'POST':
            bucket = 'register:' + (request.remote_addr or '')
            if accounts.throttled(bucket):
                return render_template('auth.html', setup=True, administrator=administrator), 429
            accounts.failed(bucket)
            name = request.form.get('name', '').strip()[:100]
            password = request.form.get('password', '')
            if administrator and app.config['SETUP_TOKEN'] and not secrets.compare_digest(request.form.get('setup_code', ''), app.config['SETUP_TOKEN']):
                flash('El código de activación no es correcto. Consúltalo en las variables seguras de tu alojamiento.', 'error')
            elif password != request.form.get('confirm'):
                flash('Las contraseñas deben coincidir.', 'error')
            else:
                try:
                    account = accounts.create(request.form.get('username', ''), name, password, administrator)
                    enter(account)
                    flash('Tu espacio está listo. Tus datos y conexiones son independientes de otras cuentas.', 'success')
                    return redirect(url_for('dashboard'))
                except ValueError as exc:
                    flash(str(exc), 'error')
                except sqlite3.IntegrityError:
                    flash('Ese nombre de usuario ya está ocupado.', 'error')
        return render_template('auth.html', setup=True, administrator=administrator,
                               requires_setup_code=administrator and bool(app.config['SETUP_TOKEN']))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if not accounts.any():
            return redirect(url_for('setup'))
        if request.method == 'POST':
            username = request.form.get('username', '').strip().lower()[:60]
            bucket = 'login:' + username
            if accounts.throttled(bucket):
                flash('Demasiados intentos. Espera cinco minutos antes de volver a entrar.', 'error')
                return render_template('auth.html', setup=False), 429
            account = accounts.find(username)
            if account and account['active'] and check_password_hash(account['password'], request.form.get('password', '')):
                enter(account)
                return redirect(url_for('dashboard'))
            accounts.failed(bucket)
            flash('El usuario o la contraseña no son correctos.', 'error')
        return render_template('auth.html', setup=False)

    @app.get('/admin/users')
    @login_required
    def admin_users():
        if owner()['role'] != 'admin':
            abort(403)
        return render_template('users.html', users=accounts.all())

    @app.post('/admin/users/<account_id>/status')
    @login_required
    def user_status(account_id):
        if owner()['role'] != 'admin' or account_id == owner()['id']:
            abort(403)
        with connect(accounts.path) as identities:
            identities.execute('UPDATE accounts SET active=?,session_version=session_version+1 WHERE id=? AND role!=?',
                               (int(request.form.get('active') == '1'), account_id, 'admin'))
        flash('Acceso del usuario actualizado.', 'success')
        return redirect(url_for('admin_users'))

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('login'))

    def filtered_clients():
        clauses, args = [], []
        query = request.args.get('q', '').strip()[:150]
        manager = request.args.get('manager', '').strip()
        status = request.args.get('status', '')
        if query:
            clauses.append('(name LIKE ? OR reference LIKE ? OR phone LIKE ?)')
            args.extend(['%' + query + '%'] * 3)
        if manager:
            clauses.append('manager=?')
            args.append(manager)
        if status in ('active', 'paid'):
            clauses.append('balance_cents>0' if status == 'active' else 'balance_cents=0')
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        return db().execute('SELECT * FROM clients' + where + ' ORDER BY id DESC', args).fetchall()

    @app.get('/')
    @login_required
    def dashboard():
        stats = db().execute('SELECT COUNT(*) total, COALESCE(SUM(balance_cents),0) balance, SUM(balance_cents>0) active FROM clients').fetchone()
        collected = db().execute("SELECT COALESCE(SUM(amount_cents),0) FROM events WHERE kind='payment'").fetchone()[0]
        recent = db().execute('SELECT events.*,clients.name FROM events LEFT JOIN clients ON clients.id=events.client_id ORDER BY events.id DESC LIMIT 6').fetchall()
        return render_template('dashboard.html', stats=stats, collected=collected, recent=recent,
                               clients=db().execute('SELECT * FROM clients ORDER BY id DESC LIMIT 5').fetchall())

    @app.get('/clients')
    @login_required
    def clients():
        rows = filtered_clients()
        managers = db().execute('SELECT DISTINCT manager FROM clients ORDER BY manager').fetchall()
        return render_template('clients.html', clients=rows, managers=managers, total=sum(c['balance_cents'] for c in rows))

    @app.route('/clients/new', methods=['GET', 'POST'])
    @login_required
    def new_client():
        if request.method == 'POST':
            try:
                name = request.form.get('name', '').strip()[:200]
                if not name:
                    raise ValueError('Escribe el nombre del cliente.')
                amount = cents(request.form.get('balance', ''))
                reference = request.form.get('reference', '').strip()[:100] or 'P-' + secrets.token_hex(5).upper()
                c = db().execute('INSERT INTO clients(reference,name,phone,manager,initial_cents,balance_cents,notes,created_at) VALUES (?,?,?,?,?,?,?,?)',
                                 (reference, name, request.form.get('phone', '').strip()[:50], request.form.get('manager', '').strip()[:100] or 'Personal', amount, amount, request.form.get('notes', '').strip()[:3000], now()))
                db().execute("INSERT INTO events(client_id,kind,detail,created_at) VALUES (?,'created',?,?)", (c.lastrowid, 'Cliente agregado manualmente.', now()))
                db().commit()
                return redirect(url_for('client_detail', client_id=c.lastrowid))
            except (ValueError, sqlite3.IntegrityError) as exc:
                db().rollback()
                flash(str(exc) if isinstance(exc, ValueError) else 'Ya existe un cliente con esa referencia.', 'error')
        return render_template('new_client.html')

    @app.route('/clients/<int:client_id>', methods=['GET', 'POST'])
    @login_required
    def client_detail(client_id):
        client = db().execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
        if not client:
            abort(404)
        if request.method == 'POST':
            name = request.form.get('name', '').strip()[:200]
            if not name:
                flash('El nombre no puede estar vacío.', 'error')
            else:
                db().execute('UPDATE clients SET name=?,phone=?,manager=?,notes=? WHERE id=?',
                             (name, request.form.get('phone', '').strip()[:50], request.form.get('manager', '').strip()[:100] or 'Personal', request.form.get('notes', '').strip()[:3000], client_id))
                db().execute("INSERT INTO events(client_id,kind,detail,created_at) VALUES (?,'updated',?,?)", (client_id, 'Datos de contacto y notas actualizados.', now()))
                db().commit()
                flash('Datos guardados.', 'success')
            return redirect(url_for('client_detail', client_id=client_id))
        events = db().execute('SELECT * FROM events WHERE client_id=? ORDER BY id DESC', (client_id,)).fetchall()
        return render_template('client_detail.html', client=client, events=events, payment_token=secrets.token_urlsafe(24))

    @app.post('/clients/<int:client_id>/payments')
    @login_required
    def payment(client_id):
        try:
            payment_token = request.form.get('payment_token', '')
            if not re.fullmatch(r'[A-Za-z0-9_-]{32}', payment_token):
                raise ValueError('Recarga la ficha del cliente antes de registrar el pago.')
            amount = cents(request.form.get('amount', ''))
            if amount <= 0:
                raise ValueError('El pago debe ser mayor a cero.')
            db().execute('BEGIN IMMEDIATE')
            if db().execute('SELECT 1 FROM events WHERE request_key=?', (payment_token,)).fetchone():
                db().rollback()
                flash('Este pago ya fue registrado. No se descontó nuevamente.', 'success')
                return redirect(url_for('client_detail', client_id=client_id))
            client = db().execute('SELECT * FROM clients WHERE id=?', (client_id,)).fetchone()
            if not client:
                abort(404)
            if amount > client['balance_cents']:
                raise ValueError('El pago no puede superar el saldo pendiente.')
            db().execute('UPDATE clients SET balance_cents=balance_cents-? WHERE id=?', (amount, client_id))
            db().execute("INSERT INTO events(client_id,kind,amount_cents,detail,created_at,request_key) VALUES (?,'payment',?,?,?,?)",
                         (client_id, amount, request.form.get('note', '').strip()[:500] or 'Pago registrado.', now(), payment_token))
            db().commit()
            flash('Pago registrado. El saldo ya está actualizado.', 'success')
        except ValueError as exc:
            db().rollback()
            flash(str(exc), 'error')
        return redirect(url_for('client_detail', client_id=client_id))

    @app.get('/history')
    @login_required
    def history():
        events = db().execute('SELECT events.*,clients.name FROM events LEFT JOIN clients ON clients.id=events.client_id ORDER BY events.id DESC').fetchall()
        return render_template('history.html', events=events)

    def stage_for(stage_id):
        result = db().execute('SELECT * FROM stages WHERE id=?', (stage_id,)).fetchone()
        if not result:
            abort(404)
        return result, json.loads(result['data'])

    @app.route('/import', methods=['GET', 'POST'])
    @login_required
    def import_file():
        if request.method == 'POST':
            upload = request.files.get('file')
            try:
                if not upload or not upload.filename:
                    raise ValueError('Selecciona un archivo Excel o CSV.')
                extension = Path(upload.filename).suffix.lower()
                if extension not in {'.xlsx', '.xls', '.csv'}:
                    raise ValueError('Usa archivos .xlsx, .xls o .csv.')
                content = upload.read()
                if extension == '.csv':
                    try:
                        text = content.decode('utf-8-sig')
                    except UnicodeDecodeError:
                        text = content.decode('latin-1')
                    frame = pd.read_csv(io.StringIO(text), sep=None, engine='python', dtype=str, keep_default_na=False)
                else:
                    workbook = pd.read_excel(io.BytesIO(content), sheet_name=None, dtype=str, keep_default_na=False)
                    sheet = request.form.get('sheet', '').strip()
                    if sheet and sheet not in workbook:
                        raise ValueError('No se encontró esa hoja en el archivo.')
                    frame = workbook[sheet] if sheet else next((f for f in workbook.values() if not f.empty), pd.DataFrame())
                if frame.empty:
                    raise ValueError('El archivo no contiene filas de datos.')
                if len(frame) > 20000 or len(frame.columns) > 100:
                    raise ValueError('El límite es de 20,000 filas y 100 columnas por archivo.')
                frame.columns = [str(c).strip() for c in frame.columns]
                if len(set(frame.columns)) != len(frame.columns):
                    raise ValueError('Las columnas deben tener nombres diferentes.')
                payload = {'columns': list(frame.columns), 'rows': frame.fillna('').to_dict(orient='records')}
                stage_id = secrets.token_urlsafe(24)
                db().execute("DELETE FROM stages WHERE created_at < datetime('now','-1 day')")
                db().execute('INSERT INTO stages VALUES (?,?,?,?)', (stage_id, Path(upload.filename).name, json.dumps(payload), now()))
                db().commit()
                return redirect(url_for('import_preview', stage_id=stage_id))
            except (ValueError, ImportError, OSError, KeyError) as exc:
                flash('No se pudo leer el archivo: ' + str(exc), 'error')
            except Exception:
                flash('No se pudo leer el archivo. Comprueba que sea un Excel o CSV válido.', 'error')
        return render_template('import.html')

    @app.route('/import/<stage_id>', methods=['GET', 'POST'])
    @login_required
    def import_preview(stage_id):
        stage, payload = stage_for(stage_id)
        columns = payload['columns']
        mapping = {field: next((c for c in columns if normalize(c) in aliases), '') for field, aliases in ALIASES.items()}
        managers = []
        if mapping['manager']:
            managers = sorted({str(r.get(mapping['manager'], '')).strip() for r in payload['rows'] if str(r.get(mapping['manager'], '')).strip()})
        if request.method == 'POST':
            mapping = {f: request.form.get(f, '') for f in FIELDS}
            if not mapping['name'] or not mapping['balance'] or any(c and c not in columns for c in mapping.values()):
                flash('Selecciona las columnas de nombre y saldo. Revisa el resto de las columnas.', 'error')
            else:
                # Validate every selected row before writing any customer.
                prepared, errors = [], []
                manager_filter = request.form.get('manager_filter', '').strip()
                active_only = request.form.get('active_only') == 'on'
                for index, row in enumerate(payload['rows'], start=2):
                    def cell(field):
                        return str(row.get(mapping[field], '')).strip() if mapping[field] else ''
                    if not any(str(v).strip() for v in row.values()):
                        continue
                    manager = cell('manager')[:100] or 'Personal'
                    if manager_filter and normalize(manager) != normalize(manager_filter):
                        continue
                    try:
                        amount = cents(cell('balance'))
                        status = normalize(cell('status'))
                        paid = any(token in status for token in ['pagado', 'liquidado', 'finalizado'])
                        if active_only and (not amount or paid):
                            continue
                        name = cell('name')[:200]
                        if not name:
                            raise ValueError('Falta el nombre del cliente.')
                        phone = re.sub(r'[^\d+]', '', cell('phone'))[:50]
                        reference = cell('reference')[:100]
                        if not reference:
                            reference = 'AUTO-' + hashlib.sha256((normalize(name) + '|' + phone).encode()).hexdigest()[:16].upper()
                        prepared.append((reference, name, phone, manager, amount, amount, '', now()))
                    except ValueError as exc:
                        errors.append(f'Fila {index}: {exc}')
                if errors:
                    flash(f'No se importó ningún cliente. Hay {len(errors)} filas por corregir. ' + ' '.join(errors[:5]), 'error')
                elif not prepared:
                    flash('No hay clientes que coincidan con estos filtros.', 'error')
                else:
                    added, duplicates = 0, 0
                    db().execute('BEGIN IMMEDIATE')
                    # Recheck stage inside transaction to prevent double confirmation.
                    if not db().execute('SELECT 1 FROM stages WHERE id=?', (stage_id,)).fetchone():
                        db().rollback()
                        abort(409)
                    for values in prepared:
                        cursor = db().execute('INSERT OR IGNORE INTO clients(reference,name,phone,manager,initial_cents,balance_cents,notes,created_at) VALUES (?,?,?,?,?,?,?,?)', values)
                        if cursor.rowcount:
                            added += 1
                            db().execute("INSERT INTO events(client_id,kind,detail,created_at) VALUES (?,'imported',?,?)", (cursor.lastrowid, 'Importado de ' + stage['filename'], now()))
                        else:
                            duplicates += 1
                    db().execute("INSERT INTO events(kind,detail,created_at) VALUES ('import',?,?)", (f"{stage['filename']}: {added} clientes importados; {duplicates} referencias existentes omitidas.", now()))
                    db().execute('DELETE FROM stages WHERE id=?', (stage_id,))
                    db().commit()
                    flash(f'{added} clientes importados. {duplicates} referencias existentes omitidas; sus saldos y pagos se conservaron.', 'success')
                    return redirect(url_for('clients'))
        return render_template('preview.html', stage=stage, data=payload, mapping=mapping, managers=managers)

    @app.get('/export')
    @login_required
    def export():
        rows = filtered_clients()
        def safe(value):
            value = str(value)
            return "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value
        data = [{'Referencia': safe(r['reference']), 'Cliente': safe(r['name']), 'Teléfono': safe(r['phone']),
                 'Gestor': safe(r['manager']), 'Saldo inicial': r['initial_cents'] / 100,
                 'Saldo pendiente': r['balance_cents'] / 100, 'Estado': 'Activo' if r['balance_cents'] else 'Liquidado',
                 'Notas': safe(r['notes'])} for r in rows]
        headers = ['Referencia', 'Cliente', 'Teléfono', 'Gestor', 'Saldo inicial', 'Saldo pendiente', 'Estado', 'Notas']
        frame = pd.DataFrame(data, columns=headers)
        if request.args.get('format') == 'csv':
            output = io.BytesIO(frame.to_csv(index=False, quoting=csv.QUOTE_ALL).encode('utf-8-sig'))
            return send_file(output, mimetype='text/csv', as_attachment=True, download_name='mi-cartera.csv')
        output = io.BytesIO()
        frame.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)
        return send_file(output, as_attachment=True, download_name='mi-cartera.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    @app.errorhandler(413)
    def too_large(_):
        return render_template('error.html', title='El archivo es demasiado grande', message='El límite por archivo es de 10 MB.'), 413

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(409)
    def handle_error(error):
        return render_template('error.html', title='No se pudo completar la acción', message=error.description), error.code

    @app.get('/healthz')
    def healthz():
        with connect(accounts.path) as identities:
            identities.execute('SELECT 1').fetchone()
        return {'status': 'ok'}

    from .messaging import register_messaging
    register_messaging(app, db, login_required)
    return app


if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=int(os.environ.get('PORT', '5200')), debug=False)
