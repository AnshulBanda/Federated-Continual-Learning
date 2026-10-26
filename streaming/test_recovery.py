"""Verify checkpoint retry and lost-receipt recovery across application restarts."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from unittest.mock import patch

from .app.dashboard import server
from .test_local_transfer import request


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--broker', default='localhost:9092')
    parser.add_argument('--file', type=Path, default=root/'artifacts/final_evaluation/corrected_fedavg/seed_42/global_model.pt')
    args = parser.parse_args()
    payload = args.file.read_bytes()
    if not 0 < len(payload) <= 100_000_000 or payload.startswith(b'version https://git-lfs.github.com/spec/v1'):
        parser.error('Choose a complete checkpoint from 1 byte to 100 MB.')
    digest = hashlib.sha256(payload).hexdigest()
    evidence = root/'streaming/.local'/('recovery-'+time.strftime('%Y%m%d-%H%M%S')+'-'+secrets.token_hex(3))
    evidence.mkdir(parents=True)
    apps, threads, bases, tokens = [], [], [], []
    original_secret = os.environ.get('FCL_TRANSFER_SECRET')
    os.environ['FCL_TRANSFER_SECRET'] = secrets.token_urlsafe(48)

    def start():
        for name in ('sender', 'receiver'):
            app = server(evidence/name, 0)
            thread = threading.Thread(target=app.serve_forever, daemon=True)
            thread.start()
            apps.append(app)
            threads.append(thread)
            base = 'http://127.0.0.1:'+str(app.server_port)
            bases.append(base)
            tokens.append(re.search(r"const token='([^']+)'", request(base, '/').decode()).group(1))

    def stop():
        for app in apps:
            app.shutdown()
            app.server_close()
        for thread in threads:
            thread.join(2)
        apps.clear(); threads.clear(); bases.clear(); tokens.clear()

    def post(index, path, data):
        return json.loads(request(bases[index], path, data, tokens[index]))

    def wait_done():
        deadline = time.monotonic()+135
        while any(app.transfers.active is not None for app in apps):
            if time.monotonic()>deadline:
                raise TimeoutError('Recovery integration deadline exceeded.')
            time.sleep(.1)

    try:
        start()
        upload = post(0, '/api/upload', payload)
        settings = dict(broker=args.broker, transfer_id=evidence.name+'a', sender='windows1', recipient='mac1')
        with patch.object(apps[0].transfers, 'send', side_effect=TimeoutError), patch.object(apps[1].transfers, 'receive', side_effect=TimeoutError):
            failed_receiver = post(1, '/api/start', dict(settings, mode='receive'))['id']
            failed_sender = post(0, '/api/start', dict(settings, mode='send', file_id=upload['file_id'], file_name=args.file.name))['id']
            wait_done()
        assert apps[0].transfers.get_job(failed_sender)['status'] == 'Failed'
        stop(); start()
        new_transfer_id = evidence.name+'b'
        # Drop the receipt and force the sender's receipt deadline to expire.
        # Chunk transport and receiver file verification still use real Kafka.
        with patch.object(apps[1].transfers, 'publish_receipt', side_effect=RuntimeError('simulated receipt outage')), patch.object(apps[0].transfers, 'wait_receipt', side_effect=TimeoutError):
            receiver = post(1, '/api/retry', dict(id=failed_receiver, transfer_id=new_transfer_id))['id']
            sender = post(0, '/api/retry', dict(id=failed_sender, transfer_id=new_transfer_id))['id']
            wait_done()
        assert apps[0].transfers.get_job(sender)['status'] == 'Published'
        assert apps[1].transfers.get_job(receiver)['status'] == 'Verified'
        print('PASS: saved checkpoint retried after restart; receiver saved it despite lost receipt.', flush=True)
        stop(); start()
        with patch.object(apps[0].transfers, 'send', side_effect=AssertionError('receipt recovery must not resend chunks')):
            post(0, '/api/recover', dict(id=sender))
            post(1, '/api/recover', dict(id=receiver))
            wait_done()
        jobs = [apps[0].transfers.get_job(sender), apps[1].transfers.get_job(receiver)]
        assert [job['status'] for job in jobs] == ['Delivered', 'Verified']
        downloaded = request(bases[1], '/api/download/'+receiver)
        assert downloaded == payload and hashlib.sha256(downloaded).hexdigest() == digest
        assert hashlib.sha256(args.file.read_bytes()).hexdigest() == digest
        assert all(job['retry_of'] for job in jobs)
        (evidence/'result.json').write_text(json.dumps(dict(result='PASS', source=str(args.file), bytes=len(payload),
            sha256=digest, retry_after_restart=True, receipt_recovery_after_restart=True, jobs=jobs), indent=2))
        (evidence/args.file.name).write_bytes(downloaded)
        print('PASS: signed receipt recovered after another restart, no file resend; bytes and hash match.')
        print('Evidence:', evidence)
    finally:
        stop()
        if original_secret is None:
            os.environ.pop('FCL_TRANSFER_SECRET', None)
        else:
            os.environ['FCL_TRANSFER_SECRET'] = original_secret


if __name__ == '__main__':
    main()
