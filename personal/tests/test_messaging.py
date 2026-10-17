import hashlib
import hmac
import io
import json
import os
import re
import secrets
import sqlite3
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch
from contextlib import contextmanager

from personal.app import create_app
from personal.messaging import process_one, settings
from personal.connections import save_settings

CONFIG = {'WHATSAPP_SEND_ENABLED': '1', 'META_ACCESS_TOKEN': 'test-placeholder-not-a-real-token',
          'META_PHONE_NUMBER_ID': '123456789', 'META_GRAPH_VERSION': 'v99.0',
          'META_TEMPLATE_NAME': 'test_template', 'META_TEMPLATE_LANGUAGE': 'es_MX',
          'META_APP_SECRET': 'test-signing-secret', 'META_VERIFY_TOKEN': 'test-verification-value'}


class MessagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING': True, 'DATA_DIR': Path(self.temp.name), 'SECRET_KEY': 'test-only'})
        self.client = self.app.test_client()
        self.environment = patch.dict(os.environ, {**CONFIG, 'WHATSAPP_SEND_ENABLED': '0'})
        self.environment.start()
        password = secrets.token_urlsafe(20)
        self.post('/setup', {'name':'Test', 'password':password,'confirm':password}, '/setup')
        self.post('/clients/new', {'name':'Ana', 'reference':'A', 'phone':'+525512345678','balance':'1000','manager':'Personal'})
        with self.db() as db:
            self.client_id = db.execute('SELECT id FROM clients').fetchone()[0]
            save_settings(db,{**CONFIG,'WHATSAPP_SEND_ENABLED':'0','META_CONNECTION_VERIFIED':'0'})

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    @contextmanager
    def live_config(self):
        with self.db() as connection:
            save_settings(connection, {**CONFIG, 'META_CONNECTION_VERIFIED':'1'})
        try:
            with patch.dict(os.environ,CONFIG):
                yield
        finally:
            with self.db() as connection:
                save_settings(connection, {**CONFIG, 'WHATSAPP_SEND_ENABLED':'0', 'META_CONNECTION_VERIFIED':'0'})

    def webhook_url(self):
        return '/webhooks/whatsapp/' + self.app.extensions['accounts'].find('tester')['id']

    def db(self):
        connection = sqlite3.connect(self.app.config['DATABASE'])
        connection.row_factory = sqlite3.Row
        return connection

    def token(self, path='/messages'):
        return re.search(r'name="csrf_token" value="([^"]+)"', self.client.get(path).get_data(as_text=True)).group(1)

    def post(self, path, data=None, token_path='/messages'):
        return self.client.post(path, data={'csrf_token':self.token(token_path), **({'username':'tester'} if path in ['/setup','/register','/login'] else {}), **(data or {})}, follow_redirects=True)

    def consent(self):
        return self.post(f'/messages/consent/{self.client_id}', {'granted':'yes','proof':'Autorización ficticia exclusivamente para esta prueba.'})

    def queue(self, mode='test', key=None, ids=None, confirm='yes'):
        return self.post('/messages/queue', {'clients':ids or [str(self.client_id)], 'mode':mode, 'request_key':key or secrets.token_urlsafe(24),'confirm_live':confirm})

    def signed_webhook(self, value):
        raw=json.dumps({'entry':[{'changes':[{'value':{'metadata':{'phone_number_id':CONFIG['META_PHONE_NUMBER_ID']},**value}}]}]}).encode()
        signature='sha256='+hmac.new(CONFIG['META_APP_SECRET'].encode(),raw,hashlib.sha256).hexdigest()
        return self.client.post(self.webhook_url(),data=raw,content_type='application/json',headers={'X-Hub-Signature-256':signature})

    def test_simulation_never_calls_provider(self):
        self.consent(); self.queue()
        def forbidden(*_):
            raise AssertionError('A simulation must never contact a provider')
        with self.db() as db:
            self.assertTrue(process_one(db,transport=forbidden))
            job=db.execute('SELECT * FROM message_jobs').fetchone()
            self.assertEqual(job['state'],'simulated')
            self.assertIsNone(job['provider_id'])
            self.assertEqual(job['attempts'],0)

    def test_consent_is_required_and_invalid_phone_does_not_gain_permission(self):
        response=self.queue()
        self.assertIn('Falta autorización',response.get_data(as_text=True))
        with self.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM message_jobs').fetchone()[0],0)
            db.execute("UPDATE clients SET phone='5512345678'")
        self.assertIn('formato internacional',self.consent().get_data(as_text=True))
        with self.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM message_consent').fetchone()[0],0)

    def test_duplicate_queue_submission_does_not_duplicate_job(self):
        self.consent(); key=secrets.token_urlsafe(24)
        self.queue(key=key); self.queue(key=key)
        with self.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM message_jobs').fetchone()[0],1)

    def test_same_phone_in_two_customers_receives_only_one_job_per_batch(self):
        self.consent()
        self.post('/clients/new', {'name':'Ana segundo crédito','reference':'B','phone':'+525512345678','balance':'100'})
        with self.db() as db:
            other=db.execute("SELECT id FROM clients WHERE reference='B'").fetchone()[0]
        self.post(f'/messages/consent/{other}',{'granted':'yes','proof':'Autorización ficticia de prueba.'})
        self.queue(ids=[str(self.client_id),str(other)])
        with self.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM message_jobs').fetchone()[0],1)

    def test_live_requires_enabled_credentials_and_explicit_confirmation(self):
        self.consent(); self.queue(mode='live')
        with self.live_config():
            self.queue(mode='live',confirm='no')
        with self.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM message_jobs').fetchone()[0],0)

    def test_accepted_is_not_delivered_and_uses_approved_template(self):
        self.consent()
        calls=[]
        def transport(config,method,suffix,payload):
            calls.append(payload)
            self.assertEqual(method,'POST'); self.assertEqual(suffix,'/messages')
            return {'messages':[{'id':'wamid.test'}]}
        with self.live_config():
            self.queue(mode='live')
            with self.db() as db:
                process_one(db,transport=transport)
                self.assertEqual(db.execute('SELECT state FROM message_jobs').fetchone()[0],'accepted')
        self.assertEqual(calls[0]['type'],'template')
        self.assertEqual(calls[0]['template']['components'][0]['parameters'][0]['text'],'Ana')

    def test_network_timeout_does_not_automatically_resend(self):
        self.consent()
        def timeout(*_):
            raise TimeoutError()
        with self.live_config():
            self.queue(mode='live')
            with self.db() as db:
                process_one(db,transport=timeout)
                self.assertFalse(process_one(db,transport=timeout))
                job=db.execute('SELECT * FROM message_jobs').fetchone()
                self.assertEqual(job['state'],'uncertain')
                self.assertEqual(job['attempts'],1)

    def test_rate_limit_retries_at_most_three_times(self):
        self.consent()
        def limited(*_):
            raise urllib.error.HTTPError('https://example.invalid',429,'Too many requests',{},None)
        with self.live_config():
            self.queue(mode='live')
            with self.db() as db:
                for _ in range(3):
                    db.execute("UPDATE message_jobs SET available_at='2000-01-01 00:00:00'");db.commit()
                    process_one(db,transport=limited)
                self.assertEqual(tuple(db.execute('SELECT state,attempts FROM message_jobs').fetchone()),('failed',3))

    def test_phone_change_or_revoked_permission_cancels_before_send(self):
        self.consent()
        with self.live_config():
            self.queue(mode='live')
            with self.db() as db:
                db.execute("UPDATE clients SET phone='+525511111111'");db.commit()
                process_one(db,transport=lambda *_:self.fail('Must not send after phone changed'))
                self.assertEqual(db.execute('SELECT state FROM message_jobs').fetchone()[0],'cancelled')

    def test_unsigned_webhook_is_rejected_and_signed_receipt_never_regresses(self):
        self.consent()
        with self.live_config():
            self.queue(mode='live')
            with self.db() as db:
                process_one(db,transport=lambda *_:{'messages':[{'id':'wamid.test'}]})
        self.assertEqual(self.client.post(self.webhook_url(),json={}).status_code,403)
        for state in ['delivered','sent','read','delivered']:
            self.assertEqual(self.signed_webhook({'statuses':[{'id':'wamid.test','status':state}]}).status_code,200)
        with self.db() as db:
            self.assertEqual(db.execute('SELECT state FROM message_jobs').fetchone()[0],'read')

    def test_receipt_arriving_before_provider_response_is_preserved(self):
        self.consent()
        def transport(*_):
            self.signed_webhook({'statuses':[{'id':'wamid.race','status':'delivered'}]})
            return {'messages':[{'id':'wamid.race'}]}
        with self.live_config():
            self.queue(mode='live')
            with self.db() as db:
                process_one(db,transport=transport)
                self.assertEqual(db.execute('SELECT state FROM message_jobs').fetchone()[0],'delivered')

    def test_optout_webhook_revokes_consent_and_cancels_queued_jobs(self):
        self.consent();self.queue()
        self.assertEqual(self.signed_webhook({'messages':[{'type':'text','from':'525512345678','text':{'body':'BAJA'}}]}).status_code,200)
        with self.db() as db:
            self.assertEqual(db.execute('SELECT granted FROM message_consent').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT state FROM message_jobs').fetchone()[0],'cancelled')

    def test_simulation_button_does_not_process_live_jobs(self):
        self.consent()
        with self.live_config():
            self.queue(mode='live')
            self.post('/messages/test-process')
        with self.db() as db:
            self.assertEqual(db.execute('SELECT state FROM message_jobs').fetchone()[0],'queued')

    def test_public_account_setup_can_require_private_activation_code(self):
        with tempfile.TemporaryDirectory() as root:
            app=create_app({'TESTING':True,'DATA_DIR':Path(root),'SECRET_KEY':'test','SETUP_TOKEN':'activation-test-only'})
            client=app.test_client()
            html=client.get('/setup').get_data(as_text=True)
            token=re.search(r'name="csrf_token" value="([^"]+)"',html).group(1)
            data={'csrf_token':token,'username':'owner','name':'Owner','password':'temporary-test-only','confirm':'temporary-test-only','setup_code':'incorrect'}
            self.assertEqual(client.post('/setup',data=data).status_code,200)
            with sqlite3.connect(app.config['DATABASE']) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM owner').fetchone()[0],0)
            data['setup_code']='activation-test-only'
            self.assertEqual(client.post('/setup',data=data).status_code,302)


if __name__ == '__main__':
    unittest.main()
