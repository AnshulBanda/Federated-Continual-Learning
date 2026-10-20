"""Opt-in signed peer probes on the existing file topic; no new broker topic."""
import base64
import json
import math
import threading
import time
import uuid

from distributed_federation.common.protocol import create_chunks, verify_chunk
from .transfers import ID, TOPIC


class PeerChecks:
    def __init__(self):
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.config = None
        self.pending = {}
        self.error = None

    def close(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)

    def configure(self, broker, secret, local_id):
        config = (broker, secret, local_id)
        if self.config == config and self.thread and self.thread.is_alive():
            return
        self.close()
        if self.thread and self.thread.is_alive():
            raise ValueError('Previous peer check is stopping. Try again shortly.')
        self.config = config
        self.stop_event = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self.listen, args=config, daemon=True)
        self.thread.start()

    @staticmethod
    def envelope(kind, source, target, nonce, secret):
        metadata = dict(message_type=kind, run_id=nonce, round_id=0, sender_id=source,
                        recipient_id=target, schema_sha256='peer-check', base_model_sha256='')
        return create_chunks(b'peer-check-v1', metadata, secret, 4096)[0]

    def handle(self, raw, secret, local_id):
        """Return a signed response or signal a matching pending challenge."""
        if not raw or len(raw) > 8192:
            return None
        try:
            envelope = json.loads(raw)
            if not isinstance(envelope, dict) or envelope.get('message_type') not in ('peer_probe', 'peer_response') or envelope.get('recipient_id') != local_id:
                return None
            chunk = verify_chunk(raw, secret)
            if (not math.isfinite(float(chunk['created_at'])) or abs(time.time() - float(chunk['created_at'])) > 30
                    or chunk['chunk_count'] != 1 or chunk['chunk_index'] != 0
                    or base64.b64decode(chunk['payload_b64'], validate=True) != b'peer-check-v1'
                    or not ID.fullmatch(str(chunk['sender_id']))
                    or not ID.fullmatch(str(chunk['run_id']))):
                return None
            nonce = chunk['run_id']
            if chunk['message_type'] == 'peer_probe':
                return self.envelope('peer_response', local_id, chunk['sender_id'], nonce, secret)
            with self.lock:
                pending = self.pending.get(nonce)
                if pending and pending[0] == chunk['sender_id']:
                    pending[1].set()
        except (ValueError, TypeError, KeyError, UnicodeDecodeError, OverflowError):
            pass
        return None

    def listen(self, broker, secret, local_id):
        consumer = None
        try:
            from confluent_kafka import Consumer, Producer
            consumer = Consumer({'bootstrap.servers': broker, 'group.id': 'peer-' + uuid.uuid4().hex,
                                 'auto.offset.reset': 'earliest', 'enable.auto.commit': False,
                                 'allow.auto.create.topics': False})
            producer = Producer({'bootstrap.servers': broker, 'message.timeout.ms': 3000})
            consumer.subscribe([TOPIC])
            while not self.stop_event.is_set():
                message = consumer.poll(.25)
                if message is None:
                    continue
                if message.error():
                    self.error = 'Peer listener could not read the transfer topic.'
                    continue
                response = self.handle(message.value(), secret, local_id)
                if response:
                    producer.produce(TOPIC, value=response)
                    producer.flush(3)
        except Exception:
            self.error = 'Peer listener unavailable. Check Kafka access and retry.'
        finally:
            if consumer:
                consumer.close()

    def check(self, broker, secret, local_id, peer_id):
        if len(secret) < 32:
            raise ValueError('Set the shared transfer secret before checking a peer.')
        if not all(ID.fullmatch(value) for value in (local_id, peer_id)) or local_id == peer_id:
            raise ValueError('Enter different valid sender and recipient IDs before checking a peer.')
        # Only one configure/check call at a time; the listener uses a separate lock.
        self.configure(broker, secret, local_id)
        nonce = uuid.uuid4().hex
        event = threading.Event()
        with self.lock:
            self.pending[nonce] = (peer_id, event)
        try:
            from confluent_kafka import Producer
            producer = Producer({'bootstrap.servers': broker, 'message.timeout.ms': 5000})
            errors = []
            producer.produce(TOPIC, value=self.envelope('peer_probe', local_id, peer_id, nonce, secret),
                             callback=lambda error, message: errors.append(error) if error else None)
            if producer.flush(6) or errors:
                return {'ready': False, 'detail': 'Could not publish peer challenge. Check Kafka access.'}
            ready = event.wait(10)
            return {'ready': ready, 'detail': ('Fresh signed response received from ' + peer_id + '. Both dashboards agree on the shared secret.' if ready else self.error or 'No signed peer response. Both teammates must click Check connection with matching IDs and secret, then retry. Leave both dashboards running.')}
        finally:
            with self.lock:
                self.pending.pop(nonce, None)
