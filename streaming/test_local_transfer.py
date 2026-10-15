"""Exercise the dashboard upload, Kafka transfer, and verified download locally."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import sys
import time
import urllib.request


def request(base, path, data=None, token=None):
    headers = {}
    if data is not None:
        headers = {'Origin': base, 'X-Session-Token': token,
                   'Content-Type': 'application/octet-stream' if isinstance(data, bytes) else 'application/json'}
        if not isinstance(data, bytes):
            data = json.dumps(data).encode()
    with urllib.request.urlopen(urllib.request.Request(base + path, data=data, headers=headers), timeout=10) as response:
        return response.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--broker', default='localhost:9092')
    args = parser.parse_args()
    if importlib.util.find_spec('confluent_kafka') is None:
        parser.exit(1, 'Install streaming/requirements.txt first.\n')
    from confluent_kafka.admin import AdminClient
    topic = 'fcl.weight-files.v1'
    try:
        metadata = AdminClient({'bootstrap.servers': args.broker}).list_topics(timeout=10)
        if topic not in metadata.topics or metadata.topics[topic].error:
            raise RuntimeError('Create the Kafka topic ' + topic + ' before testing.')
        # list_topics also exercises the broker advertised address.
    except Exception as exc:
        parser.exit(1, 'Kafka readiness failed: ' + str(exc) + '\n')

    from streaming.app.dashboard import server
    import threading
    root = Path(__file__).resolve().parents[1]
    result_dir = root / '.local' / ('local-2mb-' + time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3))
    result_dir.mkdir(parents=True)
    env_secret = os.environ.get('FCL_TRANSFER_SECRET')
    os.environ['FCL_TRANSFER_SECRET'] = secrets.token_urlsafe(48)
    servers = []
    threads = []
    try:
        # Port zero asks Windows/macOS for free loopback ports.
        for role in ('sender', 'receiver'):
            app = server(result_dir / role, 0)
            thread = threading.Thread(target=app.serve_forever, daemon=True)
            thread.start()
            servers.append(app)
            threads.append(thread)
        bases = ['http://127.0.0.1:' + str(app.server_port) for app in servers]
        tokens = [re.search(r"const token='([^']+)'", request(base, '/').decode()).group(1) for base in bases]
        payload = secrets.token_bytes(2_000_000)
        (result_dir / 'source.bin').write_bytes(payload)
        upload = json.loads(request(bases[0], '/api/upload', payload, tokens[0]))
        settings = dict(broker=args.broker, transfer_id=result_dir.name, sender='bank-a', recipient='central')
        receiver_id = json.loads(request(bases[1], '/api/start', dict(settings, mode='receive'), tokens[1]))['id']
        sender_id = json.loads(request(bases[0], '/api/start', dict(settings, mode='send', file_id=upload['file_id']), tokens[0]))['id']
        print('Transferring 2,000,000 bytes through Kafka (four chunks)...', flush=True)
        deadline = time.monotonic() + 135
        while True:
            jobs = [next(j for j in json.loads(request(base, '/api/status'))['jobs'] if j['id'] == key)
                    for base, key in zip(bases, (sender_id, receiver_id))]
            if any(job['status'] in ('Failed', 'Cancelled', 'Interrupted') for job in jobs):
                raise RuntimeError(json.dumps(jobs, indent=2))
            if [job['status'] for job in jobs] == ['Published', 'Verified']:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('Transfer deadline exceeded: ' + json.dumps(jobs))
            time.sleep(.25)
        downloaded = request(bases[1], '/api/download/' + receiver_id)
        (result_dir / 'received.weights').write_bytes(downloaded)
        original_hash = hashlib.sha256(payload).hexdigest()
        received_hash = hashlib.sha256(downloaded).hexdigest()
        if downloaded != payload or original_hash != received_hash:
            raise RuntimeError('Downloaded bytes differ from the source.')
        if any(job.get('sha256') != original_hash or job['bytes'] != len(payload) for job in jobs):
            raise RuntimeError('Dashboard hash or byte count differs from source.')
        report = dict(result='PASS', broker=args.broker, transfer_id=result_dir.name,
                      bytes=len(payload), expected_chunks=4, source_sha256=original_hash,
                      received_sha256=received_hash, byte_identical=True, jobs=jobs)
        (result_dir / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('PASS: sender Published; receiver Verified; downloaded bytes and SHA-256 match.')
        print('SHA-256:', original_hash)
        print('Evidence:', result_dir)
    finally:
        for app in servers:
            app.transfers.cancelled.set()
        for app in servers:
            app.shutdown()
            app.server_close()
        for thread in threads:
            thread.join(timeout=5)
        if env_secret is None:
            os.environ.pop('FCL_TRANSFER_SECRET', None)
        else:
            os.environ['FCL_TRANSFER_SECRET'] = env_secret


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('FAIL:', exc, file=sys.stderr)
        sys.exit(1)

