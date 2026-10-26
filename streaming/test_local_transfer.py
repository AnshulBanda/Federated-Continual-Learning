"""Exercise peer checks, checkpoint transfer, signed receipt, and verified download."""
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
    with urllib.request.urlopen(urllib.request.Request(base + path, data=data, headers=headers), timeout=35) as response:
        return response.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--broker', default='localhost:9092')
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument('--file', type=Path, help='Existing checkpoint to transfer; never modified or loaded.')
    source_group.add_argument('--synthetic', action='store_true', help='Use random 2 MB bytes for an additional transport stress check.')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = args.file or root / 'artifacts/final_evaluation/corrected_fedavg/seed_42/global_model.pt'
    if args.synthetic:
        payload = secrets.token_bytes(2_000_000)
        source_name = 'synthetic-2mb.bin'
    else:
        source = source.expanduser().resolve()
        if not source.is_file() or not 0 < source.stat().st_size <= 100_000_000:
            parser.error('Checkpoint missing, empty or over 100 MB. Use --file with an existing checkpoint.')
        payload = source.read_bytes()
        if payload.startswith(b'version https://git-lfs.github.com/spec/v1'):
            parser.error('This is a Git LFS pointer, not checkpoint bytes. Fetch the model first.')
        source_name = source.name
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
    result_dir = root / 'streaming' / '.local' / (('local-synthetic-' if args.synthetic else 'local-checkpoint-') + time.strftime('%Y%m%d-%H%M%S') + '-' + secrets.token_hex(3))
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
        (result_dir / source_name).write_bytes(payload)
        upload = json.loads(request(bases[0], '/api/upload', payload, tokens[0]))
        settings = dict(broker=args.broker, transfer_id=result_dir.name, sender='bank-a', recipient='central')
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(request, bases[i], '/api/check', dict(settings, mode=mode), tokens[i]) for i, mode in enumerate(('send', 'receive'))]
            checks = [json.loads(future.result()) for future in futures]
        if not all(check['ready'] and check.get('peer', {}).get('ready') for check in checks):
            raise RuntimeError('Signed peer checks failed: ' + json.dumps(checks))
        print('PASS: broker/topic and signed peer checks on both dashboards.', flush=True)
        receiver_id = json.loads(request(bases[1], '/api/start', dict(settings, mode='receive'), tokens[1]))['id']
        sender_id = json.loads(request(bases[0], '/api/start', dict(settings, mode='send', file_id=upload['file_id'], file_name=source_name), tokens[0]))['id']
        print(f'Transferring {source_name}: {len(payload):,} bytes through Kafka...', flush=True)
        deadline = time.monotonic() + 135
        while True:
            jobs = [next(j for j in json.loads(request(base, '/api/status'))['jobs'] if j['id'] == key)
                    for base, key in zip(bases, (sender_id, receiver_id))]
            if any(job['status'] in ('Failed', 'Cancelled', 'Interrupted') for job in jobs):
                raise RuntimeError(json.dumps(jobs, indent=2))
            if [job['status'] for job in jobs] == ['Delivered', 'Verified']:
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('Transfer deadline exceeded: ' + json.dumps(jobs))
            time.sleep(.25)
        downloaded = request(bases[1], '/api/download/' + receiver_id)
        received_dir = result_dir / 'downloaded'
        received_dir.mkdir()
        (received_dir / source_name).write_bytes(downloaded)
        if jobs[1].get('file_name') != source_name:
            raise RuntimeError('Receiver filename differs from source.')
        original_hash = hashlib.sha256(payload).hexdigest()
        received_hash = hashlib.sha256(downloaded).hexdigest()
        if downloaded != payload or original_hash != received_hash:
            raise RuntimeError('Downloaded bytes differ from the source.')
        if any(job.get('sha256') != original_hash or job['bytes'] != len(payload) for job in jobs):
            raise RuntimeError('Dashboard hash or byte count differs from source.')
        if not args.synthetic and hashlib.sha256(source.read_bytes()).hexdigest() != original_hash:
            raise RuntimeError('Source checkpoint changed during the test.')
        report = dict(result='PASS', broker=args.broker, transfer_id=result_dir.name,
                      source_file=str(source) if not args.synthetic else None, source_name=source_name,
                      source_kind='synthetic' if args.synthetic else 'checkpoint',
                      bytes=len(payload), expected_chunks=(len(payload)+499_999)//500_000, source_sha256=original_hash,
                      received_sha256=received_hash, byte_identical=True, connection_checks=checks, jobs=jobs)
        (result_dir / 'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('PASS: sender Delivered; receiver Verified; downloaded bytes and SHA-256 match.')
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

