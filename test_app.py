import http.client
import http.cookies
import importlib
import os
import re
import tempfile
import threading
import unittest
from urllib.parse import urlencode

class Workflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        os.environ['MEMCHESTER_DATA']=cls.tmp.name
        cls.app=importlib.import_module('app')
        cls.server=cls.app.ThreadingHTTPServer(('127.0.0.1',0),cls.app.App)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.tmp.cleanup()
    def request(self,method,path,data=None,cookie=''):
        conn=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        headers={'Cookie':cookie}
        if data is not None: headers['Content-Type']='application/x-www-form-urlencoded'
        conn.request(method,path,urlencode(data) if data is not None else None,headers)
        r=conn.getresponse(); body=r.read().decode(); status=r.status; cookies=r.getheader('Set-Cookie',''); conn.close()
        return status,body,cookies.split(';')[0]
    def token(self,body): return re.search('name="csrf" value="([^"]+)"',body).group(1)
    def test_end_to_end(self):
        status,body,setup=self.request('GET','/')
        self.assertEqual(status,200)
        token=self.token(body)
        status,_,_=self.request('POST','/setup',dict(email='owner@example.test',pin='12345678',currency='CAD',csrf=token),setup)
        self.assertEqual(status,303)
        status,_,_=self.request('POST','/login',dict(email='owner@example.test',pin='99999999'))
        self.assertEqual(status,401)
        status,_,owner=self.request('POST','/login',dict(email='owner@example.test',pin='12345678'))
        self.assertEqual(status,303)
        _,body,_=self.request('GET','/',cookie=owner); token=self.token(body)
        self.assertIn('CAD',body)
        entry=dict(day='2026-10-23',description='Sponsor',category='Sponsorship',amount='100.25',kind='income',csrf=token)
        self.assertEqual(self.request('POST','/transaction',entry,owner)[0],303)
        entry.update(description='Pitch',category='Pitch hire',amount='20.10',kind='expense')
        self.assertEqual(self.request('POST','/transaction',entry,owner)[0],303)
        _,body,_=self.request('GET','/',cookie=owner)
        self.assertIn('80.15',body)
        entry['amount']='1.001'
        self.assertEqual(self.request('POST','/transaction',entry,owner)[0],400)
        entry.update(amount='1.00',csrf='invalid')
        self.assertEqual(self.request('POST','/transaction',entry,owner)[0],403)
        status,csv,_=self.request('GET','/export.csv',cookie=owner)
        self.assertEqual(status,200); self.assertIn('-20.10,CAD',csv)
        self.assertEqual(self.request('POST','/invite',dict(email='helper@example.test',pin='87654321',csrf=token),owner)[0],303)
        _,_,helper=self.request('POST','/login',dict(email='helper@example.test',pin='87654321'))
        _,body,_=self.request('GET','/',cookie=helper)
        self.assertNotIn('Access portal',body)
        helper_token=self.token(body)
        self.assertEqual(self.request('POST','/invite',dict(email='bad@example.test',pin='87654321',csrf=helper_token),helper)[0],403)
        with self.app.db() as c:
            helper_id=c.execute('SELECT id FROM users WHERE email=?',('helper@example.test',)).fetchone()[0]
            self.assertEqual(c.execute('SELECT count(*) FROM transactions').fetchone()[0],2)
        self.assertEqual(self.request('POST','/revoke',dict(id=helper_id,csrf=token),owner)[0],303)
        _,body,_=self.request('GET','/',cookie=helper)
        self.assertIn('Welcome back',body)
        self.assertEqual(self.request('POST','/logout',dict(csrf=token),owner)[0],303)
        _,body,_=self.request('GET','/',cookie=owner)
        self.assertIn('Welcome back',body)

if __name__=='__main__': unittest.main()
