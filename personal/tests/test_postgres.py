"""Real PostgreSQL integration suite. Uses ONLY an isolated loopback test DB."""
import io
import os
import re
import secrets
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from personal.app import create_app
from personal.accounts import connect
from personal.connections import settings
from personal.worker import run_round

TEST_URL=os.environ.get('TAKOLO_PG_TEST_URL')


@unittest.skipUnless(TEST_URL, 'Requires an isolated PostgreSQL test container, not production.')
class PostgresTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg import sql
        options=psycopg.conninfo.conninfo_to_dict(TEST_URL)
        if options.get('host') not in {'127.0.0.1','localhost'} or options.get('dbname')!='takolo_test':
            raise RuntimeError('Integration tests require the dedicated loopback takolo_test database.')
        with psycopg.connect(TEST_URL,autocommit=True) as admin:
            for row in admin.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name LIKE 'takolo_%'").fetchall():
                admin.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(row[0])))
        self.temp=tempfile.TemporaryDirectory()
        self.environment=patch.dict(os.environ,{'DATABASE_URL':TEST_URL,'TAKOLO_SESSION_SECRET':'test-stable-session-secret-only','TAKOLO_ENCRYPTION_SECRET':'test-stable-connection-secret-only','WHATSAPP_SEND_ENABLED':'0'})
        self.environment.start()
        self.app=create_app({'TESTING':True,'DATA_DIR':Path(self.temp.name)})
        self.accounts=self.app.extensions['accounts'];self.client=self.app.test_client()
        self.password=secrets.token_urlsafe(20)
        self.signup(self.client,'admin','/setup')

    def tearDown(self):
        self.environment.stop();self.temp.cleanup()

    def token(self,client,path='/'):
        return re.search(r'name="csrf_token" value="([^"]+)"',client.get(path).get_data(as_text=True)).group(1)

    def post(self,path,data=None,client=None,token_path='/'):
        client=client or self.client
        return client.post(path,data={'csrf_token':self.token(client,token_path),**(data or {})},follow_redirects=True)

    def signup(self,client,name,path='/register'):
        response=self.post(path,{'username':name,'name':name.title(),'password':self.password,'confirm':self.password},client,path)
        self.assertEqual(response.status_code,200);self.assertIn('Hola, '+name.title(),response.get_data(as_text=True))

    def workspace(self,name='admin'):
        return connect(self.accounts.database(self.accounts.find(name)))

    def add_client(self,name='Ana',reference='A',balance='1500'):
        response=self.post('/clients/new',{'name':name,'reference':reference,'phone':'+525512345678','balance':balance})
        self.assertEqual(response.status_code,200)
        with self.workspace() as db:
            return db.execute('SELECT id FROM clients WHERE reference=?',(reference,)).fetchone()[0]

    def payment(self,client_id,amount,token=None,client=None):
        client=client or self.client
        page=client.get(f'/clients/{client_id}').get_data(as_text=True)
        key=token or re.search(r'name="payment_token" value="([^"]+)"',page).group(1)
        response=self.post(f'/clients/{client_id}/payments',{'payment_token':key,'amount':amount},client)
        return response,key

    def import_csv(self,contents):
        result=self.client.post('/import',data={'csrf_token':self.token(self.client,'/import'),'file':(io.BytesIO(contents.encode()),'cartera.csv')})
        stage=result.headers['Location']
        return self.post(stage,{'reference':'Folio','name':'Nombre','balance':'Saldo','phone':'Telefono','manager':'Gestor','active_only':'on'},token_path=stage)

    def test_registration_login_roles_and_duplicate_names(self):
        second=self.app.test_client();self.signup(second,'beatriz')
        self.assertEqual(second.get('/admin/users').status_code,403)
        self.post('/logout')
        self.assertIn('Hola, Admin',self.post('/login',{'username':'admin','password':self.password},token_path='/login').get_data(as_text=True))
        guest=self.app.test_client()
        result=self.post('/register',{'username':'BEATRIZ','name':'Other','password':self.password,'confirm':self.password},guest,'/register')
        self.assertIn('ya está ocupado',result.get_data(as_text=True))

    def test_balances_payments_history_and_export(self):
        cid=self.add_client(balance='100.30');result,key=self.payment(cid,'0.10')
        self.assertIn('Pago registrado',result.get_data(as_text=True))
        self.payment(cid,'0.10',token=key)
        result,_=self.payment(cid,'101')
        self.assertIn('no puede superar',result.get_data(as_text=True))
        self.payment(cid,'100.20')
        with self.workspace() as db:
            self.assertEqual(db.execute('SELECT balance_cents FROM clients').fetchone()[0],0)
            self.assertEqual(tuple(db.execute("SELECT COUNT(*),SUM(amount_cents) FROM events WHERE kind='payment'").fetchone()),(2,10030))
        self.assertIn('Liquidado',self.client.get('/clients').get_data(as_text=True))
        self.assertIn('Ana',self.client.get('/export?format=csv').data.decode('utf-8-sig'))
        self.assertEqual(self.client.get('/export').status_code,200)

    def test_large_cent_amounts_fit_without_int32_overflow(self):
        self.add_client(balance='100000000.50')
        with self.workspace() as db:
            self.assertEqual(db.execute('SELECT balance_cents FROM clients').fetchone()[0],10000000050)

    def test_duplicate_import_preserves_payment_and_invalid_import_is_atomic(self):
        source='Folio,Nombre,Saldo,Telefono,Gestor\nA,Ana,1500,+525512345678,PERSONAL\n'
        self.import_csv(source)
        with self.workspace() as db: cid=db.execute('SELECT id FROM clients').fetchone()[0]
        self.payment(cid,'500');self.import_csv(source)
        with self.workspace() as db:
            self.assertEqual(tuple(db.execute('SELECT COUNT(*),SUM(balance_cents) FROM clients').fetchone()),(1,100000))
        self.import_csv('Folio,Nombre,Saldo,Telefono,Gestor\nB,Beto,100,+525500000001,PERSONAL\nC,Caro,incorrecto,+525500000002,PERSONAL\n')
        with self.workspace() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM clients').fetchone()[0],1)

    def test_workspace_routing_is_restored_after_session_settings_reset(self):
        self.add_client('Solo en este espacio')
        with self.workspace() as connection:
            connection.commit()
            connection._db.execute('SET search_path TO public')
            self.assertEqual(connection.execute('SELECT name FROM clients').fetchone()[0],'Solo en este espacio')
            connection.commit()
            connection._db.execute('SET search_path TO takolo_accounts')
            self.assertEqual(connection.execute('SELECT COUNT(*) FROM clients').fetchone()[0],1)

    def test_two_users_are_isolated_and_suspension_stops_access(self):
        self.add_client('Solo admin')
        second=self.app.test_client();self.signup(second,'beatriz')
        self.assertNotIn('Solo admin',second.get('/clients').get_data(as_text=True))
        self.assertEqual(second.get('/clients/1').status_code,404)
        row=self.accounts.find('beatriz')
        self.post('/admin/users/'+row['id']+'/status',{'active':'0'})
        self.assertEqual(second.get('/clients').headers['Location'],'/login')

    def test_encrypted_connections_and_remote_state_survive_empty_local_directory(self):
        self.add_client()
        self.post('/connections',{'META_PHONE_NUMBER_ID':'12345','META_ACCESS_TOKEN':'fake-private-test-value','META_APP_SECRET':'fake-secret','META_VERIFY_TOKEN':'fake-verify'})
        with self.workspace() as db:
            self.assertNotIn('fake-private-test-value',db.execute('SELECT payload FROM message_settings').fetchone()[0])
        with tempfile.TemporaryDirectory() as empty:
            restored=create_app({'TESTING':True,'DATA_DIR':Path(empty)})
            account=restored.extensions['accounts'].find('admin')
            self.assertIsNotNone(account)
            with connect(restored.extensions['accounts'].database(account)) as db:
                self.assertEqual(settings(db)['META_ACCESS_TOKEN'],'fake-private-test-value')
                self.assertEqual(db.execute('SELECT name FROM clients').fetchone()[0],'Ana')
            self.assertEqual(restored.config['SECRET_KEY'],self.app.config['SECRET_KEY'])

    def test_background_simulation_uses_postgres_queue(self):
        cid=self.add_client()
        self.post(f'/messages/consent/{cid}',{'granted':'yes','proof':'Autorización ficticia para simulación.'})
        self.post('/messages/queue',{'clients':[str(cid)],'mode':'test','request_key':secrets.token_urlsafe(24)})
        self.assertEqual(run_round(self.accounts,set(),transport=lambda *_:self.fail('No real sends in simulation')),0)
        with self.workspace() as db:
            self.assertEqual(db.execute('SELECT state FROM message_jobs').fetchone()[0],'simulated')

    def test_concurrent_payments_cannot_overdraw_the_same_balance(self):
        cid=self.add_client(balance='1000');account=self.accounts.find('admin')
        def pay(_):
            client=self.app.test_client()
            with client.session_transaction() as session:
                session.update(logged_in=True,account_id=account['id'],session_version=account['session_version'])
            return self.payment(cid,'800',client=client)[0].status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(pay,range(2))),[200,200])
        with self.workspace() as db:
            self.assertEqual(db.execute('SELECT balance_cents FROM clients').fetchone()[0],20000)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM events WHERE kind='payment'").fetchone()[0],1)

    def test_scheduled_reminder_persists_and_cancels_after_settlement(self):
        from datetime import datetime, timezone, timedelta
        from zoneinfo import ZoneInfo
        cid=self.add_client(balance='100')
        self.post(f'/messages/consent/{cid}',{'granted':'yes','proof':'Consentimiento ficticio de prueba.'})
        future=(datetime.now(timezone.utc)+timedelta(days=1)).astimezone(ZoneInfo('America/Mexico_City'))
        data={'clients':[str(cid)],'mode':'test','request_key':secrets.token_urlsafe(24),'balance_only':'yes','send_at':future.strftime('%Y-%m-%dT%H:%M')}
        self.post('/messages/queue',data);self.post('/messages/queue',data)
        self.assertEqual(run_round(self.accounts,set()),0)
        with self.workspace() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM message_jobs').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT require_balance FROM message_job_rules').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT state FROM message_jobs').fetchone()[0],'queued')
        self.payment(cid,'100')
        with self.workspace() as db:
            db.execute("UPDATE message_jobs SET available_at='2000-01-01 00:00:00'");db.commit()
        self.assertEqual(run_round(self.accounts,set(),transport=lambda *_:self.fail('Paid client contacted')),0)
        with self.workspace() as db:
            self.assertEqual(db.execute('SELECT state FROM message_jobs').fetchone()[0],'cancelled')


class FreeHostingGuards(unittest.TestCase):
    def test_free_host_fails_without_remote_database(self):
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'DATABASE_URL':'','TAKOLO_REQUIRE_REMOTE_DB':'1'}):
            with self.assertRaisesRegex(RuntimeError,'Falta DATABASE_URL'):
                create_app({'TESTING':True,'DATA_DIR':Path(root)})

    def test_remote_database_requires_persistent_keys(self):
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{'DATABASE_URL':'postgresql://example.invalid/db','TAKOLO_SESSION_SECRET':'','TAKOLO_ENCRYPTION_SECRET':''}):
            with self.assertRaisesRegex(RuntimeError,'claves persistentes'):
                create_app({'TESTING':True,'DATA_DIR':Path(root)})

    def test_remote_connections_enforce_certificate_and_hostname_verification(self):
        with patch.dict(os.environ,{'DATABASE_URL':'postgresql://test@example.invalid/db?sslmode=disable'}),patch('psycopg.connect',side_effect=RuntimeError('stop before network')) as driver:
            with self.assertRaisesRegex(RuntimeError,'stop before network'):
                connect('/tmp/accounts.sqlite3')
            self.assertEqual(driver.call_args.kwargs['sslmode'],'verify-full')
            import ssl
            self.assertEqual(driver.call_args.kwargs['sslrootcert'],ssl.get_default_verify_paths().cafile)

    def test_remote_database_fails_closed_without_trusted_roots(self):
        from types import SimpleNamespace
        with patch.dict(os.environ,{'DATABASE_URL':'postgresql://test@example.invalid/db'}),patch('personal.storage.ssl.get_default_verify_paths',return_value=SimpleNamespace(cafile=None)),patch('psycopg.connect') as driver:
            with self.assertRaisesRegex(RuntimeError,'certificados TLS'):
                connect('/tmp/accounts.sqlite3')
            driver.assert_not_called()


if __name__=='__main__': unittest.main()
