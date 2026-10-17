import hashlib
import hmac
import io
import json
import os
import re
import secrets
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from personal.app import create_app
from personal.accounts import connect
from personal.connections import settings, save_settings
from personal.worker import run_round


class MultiuserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING':True,'DATA_DIR':Path(self.temp.name),'SECRET_KEY':'test-only'})
        self.store = self.app.extensions['accounts']
        self.a = self.app.test_client();self.b = self.app.test_client()
        self.password = secrets.token_urlsafe(20)
        self.signup(self.a,'admin','/setup')
        self.signup(self.b,'beatriz')

    def tearDown(self):
        self.temp.cleanup()

    def token(self, client, path='/'):
        return re.search(r'name="csrf_token" value="([^"]+)"', client.get(path).get_data(as_text=True)).group(1)

    def post(self, client, path, data=None, token_path='/'):
        return client.post(path,data={'csrf_token':self.token(client,token_path),**(data or {})},follow_redirects=True)

    def signup(self, client, username, path='/register'):
        response=self.post(client,path,{'username':username,'name':username.title(),'password':self.password,'confirm':self.password},path)
        self.assertEqual(response.status_code,200)

    def workspace(self, username):
        return connect(self.store.database(self.store.find(username)))

    def new_client(self, client, name, ref='SAME', balance='100'):
        return self.post(client,'/clients/new',{'name':name,'reference':ref,'phone':'+525512345678','balance':balance})

    def configure(self, client, number='12345', secret='private-app-secret', token='private-token'):
        return self.post(client,'/connections',{'META_PHONE_NUMBER_ID':number,'META_GRAPH_VERSION':'v99.0','META_ACCESS_TOKEN':token,'META_APP_SECRET':secret,'META_VERIFY_TOKEN':'test-verify','META_TEMPLATE_NAME':'approved_name','META_TEMPLATE_LANGUAGE':'es_MX','WHATSAPP_SEND_ENABLED':'1'})

    def queue_test(self, client):
        self.post(client,'/messages/consent/1',{'granted':'yes','proof':'Autorización ficticia para pruebas.'})
        self.post(client,'/messages/queue',{'clients':['1'],'mode':'test','request_key':secrets.token_urlsafe(24)})

    def test_usernames_are_unique_normalized_and_roles_cannot_be_requested(self):
        guest=self.app.test_client()
        response=self.post(guest,'/register',{'username':'BEATRIZ','name':'Intruso','password':self.password,'confirm':self.password},'/register')
        self.assertIn('ya está ocupado',response.get_data(as_text=True))
        self.assertEqual(len(self.store.all()),2)
        self.assertEqual(self.store.find('beatriz')['role'],'user')
        self.assertEqual(self.b.get('/admin/users').status_code,403)

    def test_client_data_exports_and_ids_are_isolated(self):
        self.new_client(self.a,'Privado del administrador')
        self.new_client(self.a,'Segundo privado','SECOND')
        self.new_client(self.b,'Privado de Beatriz')
        for path in ['/clients','/history','/export?format=csv']:
            content=self.b.get(path).get_data(as_text=True)
            self.assertNotIn('Privado del administrador',content)
            self.assertNotIn('Segundo privado',content)
        self.assertEqual(self.b.get('/clients/2').status_code,404)
        with self.workspace('admin') as first,self.workspace('beatriz') as second:
            self.assertEqual(first.execute('SELECT COUNT(*) FROM clients').fetchone()[0],2)
            self.assertEqual(second.execute('SELECT COUNT(*) FROM clients').fetchone()[0],1)
            self.assertNotEqual(self.store.database(self.store.find('admin')),self.store.database(self.store.find('beatriz')))

    def test_cross_account_modifications_cannot_touch_foreign_customer(self):
        self.new_client(self.a,'Admin Uno');self.new_client(self.a,'Admin Dos','TWO')
        self.new_client(self.b,'Beatriz Uno')
        response=self.post(self.b,'/clients/2',{'name':'Cambio ajeno'})
        self.assertEqual(response.status_code,404)
        with self.workspace('admin') as db:
            self.assertEqual(db.execute('SELECT name FROM clients WHERE id=2').fetchone()[0],'Admin Dos')

    def test_upload_stage_cannot_be_opened_or_confirmed_by_another_user(self):
        token=self.token(self.a,'/import')
        response=self.a.post('/import',data={'csrf_token':token,'file':(io.BytesIO(b'Nombre,Saldo\nCliente privado,100\n'),'private.csv')})
        stage=response.headers['Location']
        self.assertEqual(self.b.get(stage).status_code,404)
        self.assertEqual(self.post(self.b,stage,{'name':'Nombre','balance':'Saldo'}).status_code,404)

    def test_credentials_are_encrypted_and_never_inherited_or_rendered(self):
        self.configure(self.a,token='admin-token-do-not-render')
        content=self.a.get('/connections').get_data(as_text=True)
        self.assertNotIn('admin-token-do-not-render',content)
        self.assertNotIn('private-app-secret',content)
        with self.workspace('admin') as first,self.workspace('beatriz') as second:
            raw=first.execute('SELECT payload FROM message_settings').fetchone()[0]
            self.assertNotIn('admin-token-do-not-render',raw)
            self.assertEqual(settings(first)['META_ACCESS_TOKEN'],'admin-token-do-not-render')
            self.assertEqual(settings(second)['META_ACCESS_TOKEN'],'')
        with patch.dict(os.environ,{'META_ACCESS_TOKEN':'server-token-not-for-users'}):
            with self.workspace('beatriz') as db:
                self.assertEqual(settings(db)['META_ACCESS_TOKEN'],'')

    def test_each_user_saves_their_own_number_and_disconnect_does_not_affect_other(self):
        self.configure(self.a,'11111',token='token-a');self.configure(self.b,'22222',token='token-b')
        self.post(self.b,'/connections/disconnect')
        with self.workspace('admin') as first,self.workspace('beatriz') as second:
            self.assertEqual(settings(first)['META_PHONE_NUMBER_ID'],'11111')
            self.assertEqual(settings(second)['META_PHONE_NUMBER_ID'],'')

    def test_verification_prevents_binding_same_number_to_two_accounts(self):
        self.configure(self.a,'11111');self.configure(self.b,'11111')
        with patch('personal.messaging.api',return_value={'id':'11111'}):
            self.post(self.a,'/messages/check-connection')
            response=self.post(self.b,'/messages/check-connection')
        self.assertIn('ya está conectado a otra cuenta',response.get_data(as_text=True))
        with self.workspace('admin') as first,self.workspace('beatriz') as second:
            self.assertEqual(settings(first)['META_CONNECTION_VERIFIED'],'1')
            self.assertEqual(settings(second)['META_CONNECTION_VERIFIED'],'0')

    def test_webhook_for_another_account_rejects_own_secret(self):
        self.new_client(self.a,'Admin');self.new_client(self.b,'Beatriz')
        self.configure(self.a,'11111',secret='secret-a');self.configure(self.b,'22222',secret='secret-b')
        self.queue_test(self.a);self.queue_test(self.b)
        payload={'entry':[{'changes':[{'value':{'metadata':{'phone_number_id':'22222'},'messages':[{'type':'text','from':'525512345678','text':{'body':'BAJA'}}]}}]}]}
        raw=json.dumps(payload).encode()
        signature='sha256='+hmac.new(b'secret-a',raw,hashlib.sha256).hexdigest()
        url='/webhooks/whatsapp/'+self.store.find('beatriz')['id']
        self.assertEqual(self.a.post(url,data=raw,content_type='application/json',headers={'X-Hub-Signature-256':signature}).status_code,403)
        signature='sha256='+hmac.new(b'secret-b',raw,hashlib.sha256).hexdigest()
        self.assertEqual(self.a.post(url,data=raw,content_type='application/json',headers={'X-Hub-Signature-256':signature}).status_code,200)
        with self.workspace('admin') as first,self.workspace('beatriz') as second:
            self.assertEqual(first.execute('SELECT state FROM message_jobs').fetchone()[0],'queued')
            self.assertEqual(second.execute('SELECT state FROM message_jobs').fetchone()[0],'cancelled')

    def test_worker_processes_active_accounts_and_suspension_invalidates_session(self):
        self.new_client(self.a,'Admin');self.new_client(self.b,'Beatriz')
        self.queue_test(self.a);self.queue_test(self.b)
        account_id=self.store.find('beatriz')['id']
        self.post(self.a,f'/admin/users/{account_id}/status',{'active':'0'})
        self.assertEqual(self.b.get('/clients').headers['Location'],'/login')
        self.assertEqual(run_round(self.store,set(),transport=lambda *_:self.fail('Simulation must not send')),0)
        with self.workspace('admin') as first,self.workspace('beatriz') as second:
            self.assertEqual(first.execute('SELECT state FROM message_jobs').fetchone()[0],'simulated')
            self.assertEqual(second.execute('SELECT state FROM message_jobs').fetchone()[0],'queued')
        self.post(self.a,f'/admin/users/{account_id}/status',{'active':'1'})
        self.assertEqual(self.b.get('/clients').headers['Location'],'/login')
        run_round(self.store,set())
        with self.workspace('beatriz') as db:
            self.assertEqual(db.execute('SELECT state FROM message_jobs').fetchone()[0],'simulated')

    def test_admin_cannot_suspend_itself_and_csrf_does_not_cross_accounts(self):
        own=self.store.find('admin')['id']
        self.assertEqual(self.post(self.a,f'/admin/users/{own}/status',{'active':'0'}).status_code,403)
        token=self.token(self.a)
        self.assertEqual(self.b.post('/clients/new',data={'csrf_token':token,'name':'No','balance':'100'}).status_code,400)

    def test_one_corrupt_connection_does_not_block_other_accounts(self):
        self.new_client(self.a,'Admin');self.new_client(self.b,'Beatriz')
        self.queue_test(self.a);self.queue_test(self.b)
        self.configure(self.a)
        with self.workspace('admin') as connection:
            connection.execute("UPDATE message_settings SET payload='not-valid-ciphertext'")
        self.assertEqual(run_round(self.store,set()),1)
        with self.workspace('beatriz') as connection:
            self.assertEqual(connection.execute('SELECT state FROM message_jobs').fetchone()[0],'simulated')

    def test_callback_uses_https_only_when_proxy_trust_is_configured(self):
        account=self.store.find('beatriz')
        for trust,scheme in [('0','http'),('1','https')]:
            with patch.dict(os.environ,{'TAKOLO_TRUST_PROXY':trust}):
                app=create_app({'TESTING':True,'DATA_DIR':Path(self.temp.name),'SECRET_KEY':'test-only'})
            client=app.test_client()
            with client.session_transaction() as session:
                session.update(logged_in=True,account_id=account['id'],session_version=account['session_version'])
            html=client.get('/connections',headers={'X-Forwarded-Proto':'https'}).get_data(as_text=True)
            self.assertIn(scheme+'://localhost/webhooks/whatsapp/'+account['id'],html)

    def test_existing_personal_workspace_is_retained_during_upgrade(self):
        with tempfile.TemporaryDirectory() as root:
            app=create_app({'TESTING':True,'DATA_DIR':Path(root),'SECRET_KEY':'test'})
            with connect(app.config['DATABASE']) as db:
                db.execute("INSERT INTO owner VALUES (1,'Cuenta anterior','existing-hash')")
                db.execute("INSERT INTO clients(reference,name,initial_cents,balance_cents,created_at) VALUES ('KEEP','Cliente anterior',10000,7000,'2026-01-01 00:00:00')")
            migrated=create_app({'TESTING':True,'DATA_DIR':Path(root),'SECRET_KEY':'test'})
            account=migrated.extensions['accounts'].find('principal')
            self.assertIsNotNone(account)
            self.assertEqual(account['password'],'existing-hash')
            with connect(migrated.extensions['accounts'].database(account)) as db:
                self.assertEqual(tuple(db.execute('SELECT name,balance_cents FROM clients').fetchone()),('Cliente anterior',7000))


if __name__ == '__main__':
    unittest.main()
