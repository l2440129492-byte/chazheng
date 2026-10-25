"""首次配置：使用临时目录和假密钥，不调用真实搜索。"""
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))


class CredentialTests(unittest.TestCase):
    def test_private_store_and_clear(self):
        import credentials as c
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'private' / 'credentials.json'
            c.save_key('sk-test-secret', dest)
            self.assertEqual(c.read_key(dest), 'sk-test-secret')
            if os.name != 'nt':
                self.assertEqual(stat.S_IMODE(dest.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(dest.parent.stat().st_mode), 0o700)
            c.delete_key(dest)
            self.assertIsNone(c.read_key(dest))

    def test_popup_accepts_only_session_form_and_never_echoes_secret(self):
        import credentials as c
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'private' / 'credentials.json'
            server = c.make_server(dest)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = 'http://127.0.0.1:%s' % server.server_port
                def post(route, data, origin=base):
                    req = urllib.request.Request(base + route, json.dumps(data).encode(),
                          {'Content-Type':'application/json', 'Origin':origin})
                    return urllib.request.urlopen(req)
                with self.assertRaises(urllib.error.HTTPError) as err:
                    post('/save', {'key':'sk-test-secret'})
                self.assertEqual(err.exception.code, 403)
                with self.assertRaises(urllib.error.HTTPError):
                    post('/save', {'key':'sk-test-secret', 'token':server.token}, 'https://evil.example')
                self.assertFalse(dest.exists())
                page = urllib.request.urlopen(base + '/' + server.token).read().decode()
                self.assertIn('type="password"', page)
                self.assertNotIn('sk-test-secret', page)
                with post('/save', {'key':'sk-test-secret','token':server.token,'remember':True}) as res:
                    self.assertNotIn('sk-test-secret', res.read().decode())
                self.assertEqual(c.read_key(dest), 'sk-test-secret')
                self.assertTrue(server.saved.is_set())
            finally:
                server.shutdown(); server.server_close(); thread.join()

    def test_environment_then_private_store_without_editing_env(self):
        import credentials as c
        from unittest.mock import patch
        spec = importlib.util.spec_from_file_location('detective_auth', SCRIPTS / 'detective.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {'YB_API_KEY':'environment-key'}, clear=True):
                self.assertEqual(module.api_key(), 'environment-key')
            with patch.dict(os.environ, {}, clear=True), patch.object(c, 'read_key', return_value='stored-key'):
                self.assertEqual(module.api_key(), 'stored-key')
