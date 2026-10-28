"""Loopback dashboard; run with python -m streaming.app.dashboard."""
import argparse
import importlib.util
import json
import os
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .transfers import Transfers, MAX_BYTES
from .locking import RuntimeLock
from .peer_checks import PeerChecks
from .settings import Settings
from .overview import Overview
from .local_training import LocalTraining
from .collaboration import Collaboration
from .monitoring import Monitoring
from .results import research_results
from .explanations import Explanations
from .privacy import privacy_status
from .xai_assets import asset as xai_asset
from .final_model import reference_evidence, reference_model

WEB = Path(__file__).resolve().parents[1] / 'web' / 'index.html'


def server(root, port=8765):
    runtime_lock = RuntimeLock(Path(root) / "dashboard.lock")
    runtime_lock.__enter__()
    try:
        transfers = Transfers(root)
    except BaseException:
        runtime_lock.__exit__()
        raise
    peers = PeerChecks()
    settings = Settings(root)
    overview = Overview(root)
    training = LocalTraining(root)
    collaboration = Collaboration(root)
    monitoring = Monitoring(root)
    explanations = Explanations(root, monitoring)
    check_lock = threading.Lock()
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def respond(self, code, body, mime='application/json'):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            self.send_response(code)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'nonce-" + token + "'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def allowed(self, mutation=False):
            host = '127.0.0.1:' + str(self.server.server_port)
            if self.headers.get('Host') != host:
                self.respond(403, {'error': 'Use the local dashboard address.'})
                return False
            if mutation and (self.headers.get('Origin') != 'http://' + host or
                             not secrets.compare_digest(self.headers.get('X-Session-Token', ''), token)):
                self.respond(403, {'error': 'Refresh the local dashboard session.'})
                return False
            return True

        def do_GET(self):
            if not self.allowed():
                return
            path = urlparse(self.path).path
            if path == '/':
                self.respond(200, WEB.read_text(encoding='utf-8').replace('__TOKEN__', token).encode(), 'text/html; charset=utf-8')
            elif path.startswith('/assets/xai/'):
                found=xai_asset(path.removeprefix('/assets/xai/'))
                if found:self.respond(200,found[0],found[1])
                else:self.respond(404,{'error':'Not found.'})
            elif path.startswith('/api/explanations/report/'):
                try:self.respond(200,explanations.report(path.rsplit('/',1)[-1],overview.load()['bank']))
                except ValueError as exc:self.respond(400,{'error':str(exc)})
            elif path == '/api/privacy':
                self.respond(200, privacy_status(collaboration.status(overview.load()['bank'])))
            elif path == '/api/explanations':
                self.respond(200, explanations.status(overview.load()['bank']))
            elif path == '/api/final-model':
                self.respond(200, reference_evidence())
            elif path == '/api/monitoring':
                self.respond(200, monitoring.status(overview.load()['bank']))
            elif path.startswith('/api/monitoring/rows/'):
                try:
                    self.respond(200, monitoring.rows(path.rsplit('/',1)[-1],overview.load()['bank']))
                except ValueError as exc:
                    self.respond(400, {'error':str(exc)})
            elif path == '/api/results':
                bank=overview.load()['bank']
                self.respond(200,dict(bank=bank,research=research_results(),training=[j for j in training.status()['jobs'] if j['bank']==bank],monitoring=monitoring.status(bank)['jobs'],federation=collaboration.status(bank)['runs'],transfers=transfers.history()))
            elif path == '/api/collaboration':
                self.respond(200, collaboration.status(overview.load()['bank']))
            elif path == '/api/training':
                self.respond(200, training.status())
            elif path == '/api/overview':
                self.respond(200, overview.load())
            elif path == '/api/settings':
                self.respond(200, settings.load())
            elif path == '/api/status':
                self.respond(200, {'jobs': transfers.history(),
                                  'kafka_client': importlib.util.find_spec('confluent_kafka') is not None,
                                  'secret_ready': len(os.environ.get('FCL_TRANSFER_SECRET', '')) >= 32})
            elif path.startswith('/api/download/'):
                key = path.rsplit('/', 1)[-1]
                job = next((j for j in transfers.history() if j['id'] == key and j['status'] == 'Verified'), None)
                file = transfers.root / (key + '.weights') if job else None
                if file and file.is_file():
                    self.respond(200, file.read_bytes(), 'application/octet-stream')
                else:
                    self.respond(404, {'error': 'Verified file not found.'})
            else:
                self.respond(404, {'error': 'Not found.'})

        def do_POST(self):
            if not self.allowed(mutation=True):
                return
            try:
                length = int(self.headers.get('Content-Length', '0'))
                limit = MAX_BYTES if self.path == '/api/upload' else 8192
                if not 0 < length <= limit:
                    raise ValueError('Request is empty or too large.')
                self.connection.settimeout(30)
                body = self.rfile.read(length)
                if len(body) != length:
                    raise ValueError('Incomplete request.')
                if self.path == '/api/upload':
                    result = transfers.upload(body)
                else:
                    data = json.loads(body)
                    if not isinstance(data, dict):
                        raise ValueError('Expected a JSON object.')
                    if self.path == '/api/explanations/start':
                        result = explanations.start(data, overview.load()['bank'])
                    elif self.path == '/api/model/reference':
                        bank = overview.load()['bank']
                        if not bank: raise ValueError('Choose your bank first.')
                        result = reference_model(bank)
                        (Path(root)/'local-training'/('active-'+bank+'.json')).unlink(missing_ok=True)
                    elif self.path == '/api/monitoring/start':
                        result = monitoring.start(data, overview.load()['bank'])
                    elif self.path == '/api/monitoring/cancel':
                        result = monitoring.cancel(data.get('id'), overview.load()['bank'])
                    elif self.path == '/api/collaboration/save':
                        result = collaboration.save(data)
                    elif self.path == '/api/collaboration/check':
                        result = collaboration.preflight(data.get('profile'), overview.load()['bank'], data.get('prepare') is True)
                    elif self.path == '/api/collaboration/start':
                        if any(j['status'] in ('Queued','Running') for j in training.status()['jobs']):
                            raise ValueError('Finish or cancel local training before starting federation.')
                        result = collaboration.start(data, overview.load()['bank'])
                    elif self.path == '/api/collaboration/stop':
                        result = collaboration.control(data.get('run'), cancel=data.get('cancel') is True)
                    elif self.path == '/api/collaboration/select':
                        result = collaboration.select_model(data.get('run'), data.get('round'), overview.load()['bank'])
                    elif self.path == '/api/training/start':
                        if collaboration.process and collaboration.process.poll() is None:
                            raise ValueError('Finish or cancel federation before starting local training.')
                        result = training.start(data, overview.load()['bank'])
                    elif self.path == '/api/training/cancel':
                        result = training.cancel(data.get('id'))
                    elif self.path == '/api/training/activate':
                        result = training.activate(data.get('id'), overview.load()['bank'])
                    elif self.path == '/api/overview':
                        result = overview.save(data)
                    elif self.path == '/api/settings':
                        result = settings.save(data)
                    elif self.path == '/api/start':
                        result = {'id': transfers.start(data)}
                    elif self.path == '/api/retry':
                        result = {'id': transfers.retry(data.get('id'), data.get('transfer_id', ''))}
                    elif self.path == '/api/recover':
                        result = {'id': transfers.recover(data.get('id'))}
                    elif self.path == '/api/check':
                        if not check_lock.acquire(blocking=False):
                            raise ValueError('A connection check is already running. Wait for its result.')
                        try:
                            result = transfers.check_connection(data.get('broker', ''))
                            if result['ready']:
                                local_id, peer_id = (str(data.get(k, '')).strip() for k in (
                                    ('recipient', 'sender') if data.get('mode') == 'receive' else ('sender', 'recipient')))
                                result['peer'] = peers.check(result['broker'], os.environ.get('FCL_TRANSFER_SECRET', ''), local_id, peer_id)
                        finally:
                            check_lock.release()
                    elif self.path == '/api/cancel':
                        transfers.cancel(data.get('id'))
                        result = {'requested': True}
                    else:
                        self.respond(404, {'error': 'Not found.'})
                        return
                self.respond(200, result)
            except (ValueError, KeyError) as exc:
                self.respond(400, {'error': str(exc)})
            except Exception:
                self.respond(500, {'error': 'Local operation failed. Check storage and restart if needed.'})

    class Server(ThreadingHTTPServer):
        def server_close(self):
            explanations.close()
            monitoring.close()
            training.close()
            transfers.close()
            peers.close()
            super().server_close()
            runtime_lock.__exit__()

    try:
        httpd = Server(('127.0.0.1', port), Handler)
    except BaseException:
        runtime_lock.__exit__()
        raise
    httpd.transfers = transfers
    return httpd


def main():
    parser = argparse.ArgumentParser(description='AML dashboard: ensemble training, scoring, explanations and model collaboration')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--state-dir', type=Path, default=Path(__file__).resolve().parents[1] / '.local' / 'transfers')
    args = parser.parse_args()
    app = server(args.state_dir, args.port)
    print(f'AML dashboard: http://127.0.0.1:{app.server_port}', flush=True)
    try:
        app.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.transfers.cancelled.set()
        app.server_close()


if __name__ == '__main__':
    main()
