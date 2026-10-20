"""Opaque file transfers. No model deserialization or training dependencies."""
from contextlib import contextmanager
import base64
import hashlib
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from distributed_federation.common.protocol import create_chunks, verify_chunk, ChunkAssembler

MAX_BYTES = 100_000_000
TOPIC = 'fcl.weight-files.v1'
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$')


def safe_filename(value):
    """Download label only. Storage always uses application-generated IDs."""
    if not isinstance(value, str):
        return None
    name = value
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._ -]{0,179}', name) or name.endswith(('.', ' ')):
        return None
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        return None
    return name


class Transfers:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'transfers.sqlite3'
        self.lock = threading.Lock()
        self.active = None
        self.worker = None
        self.cancelled = threading.Event()
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
            for key, raw in db.execute('SELECT id,data FROM jobs').fetchall():
                data = json.loads(raw)
                if data.get('receipt_pending'):
                    data.update(receipt_pending=False, detail='Verified file retained after restart. Resend its receipt if the sender needs confirmation.')
                    db.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(data), key))
                if data['status'] in ('Queued', 'Sending', 'Receiving') or data.get('awaiting_receipt'):
                    data.update(status='Interrupted', awaiting_receipt=False, detail='Application closed before completion. Check delivery again if published, or coordinate a retry with a fresh transfer ID.')
                    saved_file = self.root / (key + '.weights')
                    if data.get('mode') == 'receive' and data.get('expected_sha256') and saved_file.is_file() and saved_file.stat().st_size <= MAX_BYTES:
                        try:
                            saved = saved_file.read_bytes()
                        except OSError:
                            saved = b''
                        if len(saved) == data.get('total') and hashlib.sha256(saved).hexdigest() == data['expected_sha256']:
                            data.update(status='Verified', sha256=data['expected_sha256'], bytes=len(saved),
                                        detail='Recovered and hash-verified the saved file after restart. Resend receipt to confirm delivery.')
                    db.execute('UPDATE jobs SET data=? WHERE id=?', (json.dumps(data), key))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def history(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute('SELECT data FROM jobs ORDER BY rowid DESC LIMIT 100')]

    def update(self, job, **values):
        job.update(values, updated=time.time())
        with self.connect() as db:
            db.execute('INSERT INTO jobs VALUES(?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data',
                       (job['id'], json.dumps(job)))

    def upload(self, payload):
        if not 0 < len(payload) <= MAX_BYTES:
            raise ValueError('Choose a nonempty file no larger than 100 MB.')
        key = uuid.uuid4().hex
        self.write_file(key + '.upload', payload)
        return {'file_id': key, 'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}

    def write_file(self, name, payload):
        target = self.root / name
        temp = self.root / (uuid.uuid4().hex + '.tmp')
        try:
            with temp.open('xb') as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)

    def start(self, settings):
        settings = dict(settings)
        for key in ('transfer_id', 'sender', 'recipient'):
            settings[key] = str(settings.get(key, '')).strip()
        mode = settings.get('mode')
        if mode not in ('send', 'receive'):
            raise ValueError('Choose send or receive.')
        for key in ('transfer_id', 'sender', 'recipient'):
            if not ID.fullmatch(str(settings.get(key, ''))):
                raise ValueError('IDs must start with a letter or number and use 1-64 letters, numbers, dots, underscores or hyphens.')
        broker = str(settings.get('broker', '')).strip()
        if not broker or len(broker) > 250 or ':' not in broker or any(c.isspace() for c in broker):
            raise ValueError('Enter a Kafka broker address as host:port.')
        secret = os.environ.get('FCL_TRANSFER_SECRET', '')
        if len(secret) < 32:
            raise ValueError('Set FCL_TRANSFER_SECRET to a shared secret of at least 32 characters before launching.')
        payload = None
        if mode == 'send':
            file_id = str(settings.get('file_id', ''))
            if not re.fullmatch('[a-f0-9]{32}', file_id):
                raise ValueError('Upload a file first.')
            path = self.root / (file_id + '.upload')
            if not path.is_file() or not 0 < path.stat().st_size <= MAX_BYTES:
                raise ValueError('Uploaded file is unavailable or too large.')
            payload = path.read_bytes()
            expected = settings.get('expected_sha256')
            if expected and hashlib.sha256(payload).hexdigest() != expected:
                raise ValueError('Saved upload changed. Retry refused; select the original checkpoint for a new transfer.')
        with self.lock:
            if self.active is not None:
                raise ValueError('A local transfer is already active.')
            with self.connect() as db:
                previous = [json.loads(row[0]) for row in db.execute('SELECT data FROM jobs')]
            if any((old.get('transfer_id'), old.get('sender'), old.get('recipient')) == (settings['transfer_id'], settings['sender'], settings['recipient']) for old in previous):
                raise ValueError('This transfer ID was already used locally. Agree on a fresh ID on both laptops.')
            self.cancelled.clear()
            job = {'id': uuid.uuid4().hex, 'mode': mode, 'transfer_id': settings['transfer_id'],
                   'sender': settings['sender'], 'recipient': settings['recipient'],
                   'file_name': safe_filename(settings.get('file_name', '')) if mode == 'send' else None,
                   'broker': broker, 'file_id': settings.get('file_id') if mode == 'send' else None,
                   'source_sha256': hashlib.sha256(payload).hexdigest() if payload else None,
                   'expected_sha256': settings.get('expected_sha256'),
                   'retry_of': settings.get('retry_of'), 'retry_transfer_id': settings.get('retry_transfer_id'),
                   'status': 'Queued', 'bytes': 0, 'total': len(payload) if payload else None,
                   'detail': 'Waiting for Kafka connection.'}
            self.active = job['id']
            self.update(job)
            self.worker = threading.Thread(target=self.run, args=(job, broker, secret, payload), daemon=True)
            self.worker.start()
        return job['id']

    def get_job(self, key):
        with self.connect() as db:
            row = db.execute('SELECT data FROM jobs WHERE id=?', (str(key),)).fetchone()
        if row is None:
            raise ValueError('Transfer not found.')
        return json.loads(row[0])

    def retry(self, key, transfer_id):
        old = self.get_job(key)
        if old.get('status') not in ('Failed', 'Cancelled', 'Interrupted', 'Published'):
            raise ValueError('Only failed, cancelled, interrupted or unconfirmed transfers can be retried.')
        if not old.get('broker'):
            raise ValueError('This older transfer has no saved connection. Set up a new transfer manually.')
        if str(transfer_id).strip() == old['transfer_id']:
            raise ValueError('Agree on a NEW transfer ID on both laptops before retrying.')
        values = {key: old.get(key) for key in ('mode', 'broker', 'sender', 'recipient', 'file_id', 'file_name')}
        values.update(transfer_id=transfer_id, retry_of=old['id'], retry_transfer_id=old['transfer_id'],
                      expected_sha256=old.get('source_sha256') or old.get('expected_sha256') or old.get('sha256'))
        if old['mode'] == 'send' and not values['expected_sha256']:
            raise ValueError('Original file hash unavailable. Start a new transfer manually.')
        return self.start(values)

    def recover(self, key):
        job = self.get_job(key)
        if not job.get('broker') or not job.get('receipt_token') or not job.get('sha256'):
            raise ValueError('Receipt recovery data unavailable. Coordinate a new transfer instead.')
        if job['mode'] == 'receive':
            if job['status'] != 'Verified':
                raise ValueError('Only a verified saved file can send a receipt again.')
            path = self.root / (job['id'] + '.weights')
            if not path.is_file() or path.stat().st_size > MAX_BYTES:
                raise ValueError('Verified file is missing or too large. Coordinate a new transfer.')
            data = path.read_bytes()
            if len(data) != job['total'] or hashlib.sha256(data).hexdigest() != job['sha256']:
                raise ValueError('Saved file changed. Receipt refused; coordinate a new transfer.')
        elif not job.get('publication_acked') or job['status'] not in ('Published', 'Interrupted', 'Cancelled', 'Failed'):
            raise ValueError('Only broker-acknowledged, unconfirmed sends can recheck delivery.')
        secret = os.environ.get('FCL_TRANSFER_SECRET', '')
        if len(secret) < 32:
            raise ValueError('Set the shared secret before recovering delivery.')
        with self.lock:
            if self.active is not None:
                raise ValueError('A local transfer is already active.')
            self.cancelled.clear()
            self.active = job['id']
            if job['mode'] == 'send':
                self.update(job, status='Published', awaiting_receipt=True,
                            detail='Rechecking retained signed receipts without sending the file again.')
            else:
                self.update(job, receipt_pending=True, detail='Verified file retained; resending its signed receipt.')
            self.worker = threading.Thread(target=self.recover_receipt, args=(job, secret), daemon=True)
            self.worker.start()
        return job['id']

    def recover_receipt(self, job, secret):
        try:
            if job['mode'] == 'send':
                self.wait_receipt(job, job['broker'], secret, job['receipt_token'])
            else:
                self.publish_receipt(job, job['broker'], secret, job['receipt_token'])
                self.update(job, receipt_sent=True, detail='Verified saved file retained; signed receipt published again.')
        except Exception:
            self.update(job, detail='Delivery receipt recovery did not complete. File/publication evidence retained; retry the receipt check or coordinate a new transfer.')
        finally:
            self.update(job, awaiting_receipt=False, receipt_pending=False)
            with self.lock:
                self.active = None

    def close(self):
        self.cancelled.set()
        if self.worker:
            self.worker.join(timeout=30)
            if self.worker.is_alive():
                raise RuntimeError('Transfer still stopping. State lock is retained until process exit.')

    def cancel(self, key):
        with self.lock:
            if key != self.active:
                raise ValueError('Transfer is not active.')
            self.cancelled.set()

    def run(self, job, broker, secret, payload):
        try:
            if job['mode'] == 'send':
                self.send(job, broker, secret, payload)
            else:
                self.receive(job, broker, secret)
        except InterruptedError:
            self.update(job, status='Cancelled', detail='Local operation stopped; published messages cannot be retracted.')
        except TimeoutError:
            if job.get('status') == 'Published':
                self.update(job, awaiting_receipt=False, detail='Published, but no valid receipt arrived within two minutes. Check the receiver; delivery remains unconfirmed.')
            else:
                self.update(job, status='Failed', detail='Timed out. Check the broker and matching IDs; start the receiver first.')
        except ValueError:
            self.update(job, status='Failed', detail='Transfer validation failed. Compare shared-secret fingerprints and IDs; retry with a new transfer ID.')
        except ImportError:
            self.update(job, status='Failed', detail='Kafka client is missing. Install streaming/requirements.txt to enable transfers.')
        except Exception as exc:
            if job.get('status') == 'Published':
                self.update(job, awaiting_receipt=False, detail='Published, but receiver confirmation failed. Check the receiver; delivery remains unconfirmed.')
            else:
                self.update(job, status='Failed', detail='Transfer failed (' + type(exc).__name__ + '). Check broker, topic and credentials.')
        finally:
            if job.get('awaiting_receipt'):
                self.update(job, awaiting_receipt=False)
            with self.lock:
                self.active = None

    def check_cancel(self):
        if self.cancelled.is_set():
            raise InterruptedError()

    def check_connection(self, broker):
        broker = str(broker).strip()
        if not broker or len(broker) > 250 or ':' not in broker or any(c.isspace() for c in broker):
            raise ValueError('Enter a Kafka broker address as host:port.')
        try:
            from confluent_kafka.admin import AdminClient
            metadata = AdminClient({'bootstrap.servers': broker, 'allow.auto.create.topics': False}).list_topics(timeout=8)
            topic = metadata.topics.get(TOPIC)
            ready = topic is not None and topic.error is None
            return {'broker': broker, 'ready': ready, 'checked_at': time.time(),
                    'detail': 'Broker metadata and transfer topic are available.' if ready else 'Broker reached, but fcl.weight-files.v1 is missing or unavailable. Ask the host to create it.'}
        except ImportError:
            return {'broker': broker, 'ready': False, 'detail': 'Install streaming/requirements.txt using the Python that launches this dashboard.'}
        except Exception:
            return {'broker': broker, 'ready': False, 'detail': 'Kafka metadata check failed. Check ZeroTier, firewall, broker address and advertised listeners.'}

    def send(self, job, broker, secret, payload):
        from confluent_kafka import Producer
        producer = Producer({'bootstrap.servers': broker, 'enable.idempotence': True,
                             'message.timeout.ms': 15000})
        receipt_token = uuid.uuid4().hex
        metadata = {'receipt_token': receipt_token, 'message_type': 'weight_file', 'run_id': job['transfer_id'], 'round_id': 0,
                    'sender_id': job['sender'], 'recipient_id': job['recipient'],
                    'schema_sha256': 'opaque-file', 'base_model_sha256': '', 'file_size': len(payload)}
        if job.get('file_name'):
            metadata['file_name'] = job['file_name']
        self.update(job, receipt_token=receipt_token, sha256=hashlib.sha256(payload).hexdigest())
        chunks = create_chunks(payload, metadata, secret, 500_000)
        self.update(job, status='Sending', detail='Publishing signed chunks. Progress counts broker acknowledgments.')
        errors = []
        def delivered(size):
            def callback(error, message):
                if error:
                    errors.append(True)
                else:
                    self.update(job, bytes=job['bytes'] + size)
            return callback
        deadline = time.monotonic() + 120
        for index, chunk in enumerate(chunks):
            while True:
                self.check_cancel()
                if time.monotonic() > deadline or errors:
                    raise TimeoutError()
                try:
                    producer.produce(TOPIC, key=job['transfer_id'].encode(), value=chunk,
                                     callback=delivered(min(500_000, len(payload) - index * 500_000)))
                    break
                except BufferError:
                    producer.poll(.2)
            producer.poll(0)
        while len(producer):
            self.check_cancel()
            if time.monotonic() > deadline or errors:
                raise TimeoutError()
            producer.poll(.2)
        if errors:
            raise RuntimeError('delivery failed')
        self.update(job, status='Published', publication_acked=True, awaiting_receipt=True, sha256=hashlib.sha256(payload).hexdigest(),
                    detail='Broker acknowledged all chunks. Waiting up to two minutes for a signed receiver receipt.')
        self.wait_receipt(job, broker, secret, receipt_token)

    def wait_receipt(self, job, broker, secret, token):
        from confluent_kafka import Consumer
        consumer = Consumer({'bootstrap.servers': broker, 'group.id': 'receipt-' + job['id'],
                             'auto.offset.reset': 'earliest', 'enable.auto.commit': False,
                             'allow.auto.create.topics': False})
        deadline = time.monotonic() + 120
        try:
            consumer.subscribe([TOPIC])
            while time.monotonic() < deadline:
                self.check_cancel()
                message = consumer.poll(.25)
                if message is None:
                    continue
                if message.error():
                    raise RuntimeError('receipt broker error')
                raw = message.value()
                if not raw or len(raw) > 8192:
                    continue
                try:
                    envelope = json.loads(raw)
                    if not isinstance(envelope, dict) or tuple(envelope.get(k) for k in (
                            'message_type', 'run_id', 'sender_id', 'recipient_id', 'receipt_token')) != (
                            'weight_receipt', job['transfer_id'], job['recipient'], job['sender'], token):
                        continue
                    chunk = verify_chunk(raw, secret)
                    payload = base64.b64decode(chunk['payload_b64'], validate=True)
                    receipt = json.loads(payload)
                    if (chunk['chunk_count'] != 1 or chunk['chunk_index'] != 0
                            or hashlib.sha256(payload).hexdigest() != chunk['payload_sha256']
                            or receipt != {'sha256': job['sha256'], 'bytes': job['total'], 'saved': True}):
                        continue
                except (ValueError, TypeError, KeyError, UnicodeDecodeError):
                    continue
                self.update(job, status='Delivered', awaiting_receipt=False,
                            detail='Signed receiver receipt confirms matching hash, byte count and saved file. Authentication uses the shared team secret.')
                return
            raise TimeoutError()
        finally:
            consumer.close()

    def publish_receipt(self, job, broker, secret, token):
        from confluent_kafka import Producer
        payload = json.dumps({'sha256': job['sha256'], 'bytes': job['total'], 'saved': True}).encode()
        metadata = dict(message_type='weight_receipt', run_id=job['transfer_id'], round_id=0,
                        sender_id=job['recipient'], recipient_id=job['sender'], receipt_token=token,
                        schema_sha256='opaque-file', base_model_sha256='')
        raw = create_chunks(payload, metadata, secret, 4096)[0]
        producer = Producer({'bootstrap.servers': broker, 'message.timeout.ms': 10000})
        errors = []
        producer.produce(TOPIC, key=job['transfer_id'].encode(), value=raw,
                         callback=lambda error, message: errors.append(error) if error else None)
        if producer.flush(12) or errors:
            raise RuntimeError('receipt publication failed')

    def receive(self, job, broker, secret):
        from confluent_kafka import Consumer
        consumer = Consumer({'bootstrap.servers': broker, 'group.id': 'weight-file-' + job['id'],
                             'auto.offset.reset': 'earliest', 'enable.auto.commit': False,
                             'allow.auto.create.topics': False})
        assembler = ChunkAssembler(MAX_BYTES)
        seen = set()
        selected_hash = None
        deadline = time.monotonic() + 120
        self.update(job, status='Receiving', detail='Waiting up to two minutes for the matching signed transfer.')
        try:
            consumer.subscribe([TOPIC])
            while time.monotonic() < deadline:
                self.check_cancel()
                message = consumer.poll(.25)
                if message is None:
                    continue
                if message.error():
                    raise RuntimeError('broker error')
                raw = message.value()
                if raw is None or len(raw) > 1_000_000:
                    continue
                # Retained topic records may belong to other transfers/secrets.
                # Untrusted routing fields only decide what to skip; matching
                # records must still pass the full signature and payload checks.
                try:
                    envelope = json.loads(raw)
                except (ValueError, UnicodeDecodeError):
                    continue
                if not isinstance(envelope, dict):
                    continue
                if tuple(envelope.get(key) for key in (
                        'message_type', 'run_id', 'sender_id', 'recipient_id')) != (
                        'weight_file', job['transfer_id'], job['sender'], job['recipient']):
                    continue
                try:
                    chunk = verify_chunk(raw, secret)
                    if (chunk['message_type'], chunk['run_id'], chunk['sender_id'], chunk.get('recipient_id')) != (
                            'weight_file', job['transfer_id'], job['sender'], job['recipient']):
                        continue
                    size = int(chunk.get('file_size', 0))
                    count = int(chunk['chunk_count'])
                    if not 0 < size <= MAX_BYTES or not 1 <= count <= 200:
                        raise ValueError('invalid transfer size')
                    if selected_hash is not None and selected_hash != chunk['payload_sha256']:
                        raise ValueError('conflicting transfer')
                    if job.get('expected_sha256') and job['expected_sha256'] != chunk['payload_sha256']:
                        raise ValueError('retry payload changed')
                    selected_hash = chunk['payload_sha256']
                    self.update(job, expected_sha256=selected_hash, receipt_token=chunk.get('receipt_token'),
                                file_name=safe_filename(chunk.get('file_name', '')))
                    result = assembler.add(chunk)
                    index = int(chunk['chunk_index'])
                    if index not in seen:
                        seen.add(index)
                        self.update(job, bytes=job['bytes'] + len(base64.b64decode(chunk['payload_b64'])), total=size)
                    if result:
                        data, metadata = result
                        if len(data) != size:
                            raise ValueError('size mismatch')
                        self.check_cancel()
                        self.write_file(job['id'] + '.weights', data)
                        self.update(job, status='Verified', sha256=metadata['payload_sha256'],
                                    file_name=safe_filename(metadata.get('file_name', '')),
                                    detail='Signature and SHA-256 verified; file saved locally. Model contents were not inspected.')
                        token = chunk.get('receipt_token')
                        if token:
                            try:
                                self.publish_receipt(job, broker, secret, token)
                                self.update(job, receipt_sent=True, detail='Signature and SHA-256 verified; file saved and signed receipt published.')
                            except Exception:
                                self.update(job, receipt_sent=False, detail='File verified and saved, but receipt publication failed. Sender delivery may remain unconfirmed.')
                        return
                except (ValueError, TypeError, KeyError):
                    # Invalid messages never become downloadable results.
                    raise ValueError('invalid signed transfer')
            raise TimeoutError()
        finally:
            consumer.close()
