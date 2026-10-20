import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch, Mock

from streaming.app.settings import Settings, validate_settings
from streaming.app.dashboard import server
from streaming.app.launcher import main

VALID = dict(broker='10.30.127.124:9092', mode='receive', sender='windows1', recipient='mac1')


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_settings_survive_restart_and_reject_secret_or_transfer_id(self):
        settings = Settings(self.root)
        settings.save(dict(VALID, broker=' 10.30.127.124:9092 '))
        self.assertEqual(Settings(self.root).load()['settings'], VALID)
        for field in ('secret', 'FCL_TRANSFER_SECRET', 'transfer_id', 'file_id'):
            with self.assertRaises(ValueError):
                settings.save(dict(VALID, **{field: 'do-not-save'}))
        self.assertNotIn('do-not-save', settings.path.read_text())
        self.assertEqual(Settings(self.root).load()['settings'], VALID)

    def test_failed_settings_replace_keeps_previous_configuration(self):
        settings = Settings(self.root)
        settings.save(VALID)
        with patch('streaming.app.settings.os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                settings.save(dict(VALID, mode='send'))
        self.assertEqual(settings.load()['settings'], VALID)
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_corrupt_settings_do_not_crash_or_overwrite_file(self):
        settings = Settings(self.root)
        settings.path.write_text('not json')
        result = settings.load()
        self.assertEqual(result['settings'], {})
        self.assertTrue(result['warning'])
        self.assertEqual(settings.path.read_text(), 'not json')
        settings.save(VALID)
        self.assertIsNone(settings.load()['warning'])

    def test_invalid_broker_ids_and_mode(self):
        for changes in ({'broker': 'localhost:0'}, {'broker': 'localhost:65536'}, {'broker': ':9092'},
                        {'broker': 'localhost:notaport'}, {'sender': '../bad'}, {'mode': 'run'},
                        {'sender': 'mac1'}, {'broker': 'bad host:9092'}):
            with self.assertRaises(ValueError):
                validate_settings(dict(VALID, **changes))

    def test_settings_endpoint_requires_session_and_never_returns_secret(self):
        app = server(self.root, 0)
        worker = threading.Thread(target=app.serve_forever, daemon=True)
        worker.start()
        self.addCleanup(worker.join, 2)
        self.addCleanup(app.server_close)
        self.addCleanup(app.shutdown)
        base = 'http://127.0.0.1:' + str(app.server_port)
        html = urllib.request.urlopen(base).read().decode()
        token = html.split("const token='")[1].split("'")[0]
        req = urllib.request.Request(base+'/api/settings', data=json.dumps(VALID).encode(), method='POST')
        with self.assertRaises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(req)
        self.assertEqual(denied.exception.code, 403)
        denied.exception.close()
        req.add_header('Origin', base)
        req.add_header('X-Session-Token', token)
        with urllib.request.urlopen(req) as response:
            self.assertEqual(json.load(response)['settings'], VALID)
        with patch.dict(os.environ, FCL_TRANSFER_SECRET='test-private-secret'*3):
            with urllib.request.urlopen(base+'/api/settings') as response:
                result = response.read().decode()
        self.assertNotIn('test-private-secret', result)

    def test_launcher_check_only_never_prompts_starts_or_opens_browser(self):
        with patch('streaming.app.launcher.prerequisites', return_value=[]), \
             patch('streaming.app.launcher.getpass.getpass') as prompt, \
             patch('streaming.app.launcher.server') as start, \
             patch('streaming.app.launcher.webbrowser.open') as browser:
            self.assertEqual(main(['--check-only', '--state-dir', str(self.root)]), 0)
        prompt.assert_not_called()
        start.assert_not_called()
        browser.assert_not_called()

    def test_launcher_reports_duplicate_and_does_not_open_browser(self):
        with patch('streaming.app.launcher.prerequisites', return_value=[]), \
             patch.dict(os.environ, FCL_TRANSFER_SECRET='x'*32), \
             patch('streaming.app.launcher.server', side_effect=RuntimeError('locked')), \
             patch('streaming.app.launcher.webbrowser.open') as browser:
            self.assertEqual(main(['--state-dir', str(self.root)]), 1)
        browser.assert_not_called()

    def test_launcher_shutdown_closes_server_without_persisting_secret(self):
        app = Mock(server_port=8765)
        app.serve_forever.side_effect = KeyboardInterrupt
        with patch('streaming.app.launcher.prerequisites', return_value=[]), \
             patch.dict(os.environ, FCL_TRANSFER_SECRET='x'*32), \
             patch('streaming.app.launcher.server', return_value=app), \
             patch('streaming.app.launcher.webbrowser.open', return_value=True) as browser:
            self.assertEqual(main(['--state-dir', str(self.root)]), 0)
        browser.assert_called_once_with('http://127.0.0.1:8765')
        app.server_close.assert_called_once()
        self.assertFalse((self.root/'settings.json').exists())
