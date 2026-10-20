import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from streaming.app.transfers import Transfers, TOPIC, safe_filename
from distributed_federation.common.protocol import create_chunks, verify_chunk


class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.transfers = Transfers(self.tmp.name)
        self.job = dict(id='receipt-test', mode='send', transfer_id='test', sender='windows1',
                        recipient='mac1', bytes=4, total=4, sha256=hashlib.sha256(b'data').hexdigest())

    def receipt(self, token='fresh', secret='x'*32, **changes):
        payload = dict(sha256=self.job['sha256'], bytes=4, saved=True)
        payload.update(changes)
        metadata = dict(message_type='weight_receipt', run_id='test', round_id=0,
                        sender_id='mac1', recipient_id='windows1', receipt_token=token,
                        schema_sha256='opaque-file', base_model_sha256='')
        return create_chunks(json.dumps(payload).encode(), metadata, secret, 4096)[0]

    def test_ignores_forged_stale_and_wrong_file_receipts(self):
        messages = iter([b'not json', b'[]', self.receipt(token='old'),
                         self.receipt(secret='z'*32), self.receipt(bytes=99),
                         self.receipt(sha256='wrong'), self.receipt()])
        closed = []
        consumer = SimpleNamespace(subscribe=lambda topics: None, close=lambda: closed.append(True),
            poll=lambda timeout: SimpleNamespace(error=lambda: None, value=lambda: next(messages)))
        with patch.dict('sys.modules', {'confluent_kafka': SimpleNamespace(Consumer=lambda config: consumer)}):
            self.transfers.wait_receipt(self.job, 'local:9092', 'x'*32, 'fresh')
        self.assertEqual(self.job['status'], 'Delivered')
        self.assertEqual(closed, [True])

    def test_download_filename_rejects_paths_controls_and_reserved_names(self):
        self.assertEqual(safe_filename('global_model.pt'), 'global_model.pt')
        self.assertEqual(safe_filename('bank weights.safetensors'), 'bank weights.safetensors')
        for name in ('../model.pt', r'C:\secret.pt', '/tmp/model.pt', 'bad\n.pt', 'CON.pt', 'LPT1', 'model.', '.hidden', 'x'*181):
            self.assertIsNone(safe_filename(name))

    def test_filename_is_received_from_signed_metadata_without_changing_storage_path(self):
        metadata = dict(message_type='weight_file', run_id='test', round_id=0, sender_id='windows1',
                        recipient_id='mac1', file_name='global_model.pt', schema_sha256='opaque-file',
                        base_model_sha256='', file_size=4)
        raw = create_chunks(b'data', metadata, 'x'*32, 500)[0]
        consumer = SimpleNamespace(subscribe=lambda topics: None, close=lambda: None,
            poll=lambda timeout: SimpleNamespace(error=lambda: None, value=lambda: raw))
        job = dict(self.job, mode='receive', bytes=0)
        with patch.dict('sys.modules', {'confluent_kafka': SimpleNamespace(Consumer=lambda config: consumer)}):
            self.transfers.receive(job, 'local:9092', 'x'*32)
        self.assertEqual(job['file_name'], 'global_model.pt')
        self.assertTrue((Path(self.tmp.name)/(job['id']+'.weights')).is_file())
        self.assertFalse((Path(self.tmp.name)/'global_model.pt').exists())

    def test_cancel_receipt_wait_closes_consumer(self):
        closed = []
        consumer = SimpleNamespace(subscribe=lambda topics: None, close=lambda: closed.append(True))
        self.transfers.cancelled.set()
        with patch.dict('sys.modules', {'confluent_kafka': SimpleNamespace(Consumer=lambda config: consumer)}):
            with self.assertRaises(InterruptedError):
                self.transfers.wait_receipt(self.job, 'local:9092', 'x'*32, 'fresh')
        self.assertEqual(closed, [True])

    def test_receipt_is_signed_and_routes_back_to_sender(self):
        sent = []
        producer = SimpleNamespace(produce=lambda topic, **kwargs: sent.append((topic, kwargs)), flush=lambda timeout: 0)
        with patch.dict('sys.modules', {'confluent_kafka': SimpleNamespace(Producer=lambda config: producer)}):
            self.transfers.publish_receipt(self.job, 'local:9092', 'x'*32, 'fresh')
        topic, args = sent[0]
        chunk = verify_chunk(args['value'], 'x'*32)
        self.assertEqual(topic, TOPIC)
        self.assertEqual((chunk['sender_id'], chunk['recipient_id'], chunk['receipt_token']), ('mac1', 'windows1', 'fresh'))

    def test_saved_file_survives_receipt_failure(self):
        metadata = dict(message_type='weight_file', run_id='test', round_id=0, sender_id='windows1',
                        recipient_id='mac1', receipt_token='fresh', schema_sha256='opaque-file', base_model_sha256='', file_size=4)
        raw = create_chunks(b'data', metadata, 'x'*32, 500)[0]
        consumer = SimpleNamespace(subscribe=lambda topics: None, close=lambda: None,
            poll=lambda timeout: SimpleNamespace(error=lambda: None, value=lambda: raw))
        job = dict(self.job, mode='receive', bytes=0)
        with patch.dict('sys.modules', {'confluent_kafka': SimpleNamespace(Consumer=lambda config: consumer)}), patch.object(self.transfers, 'publish_receipt', side_effect=RuntimeError()):
            self.transfers.receive(job, 'local:9092', 'x'*32)
        self.assertEqual(job['status'], 'Verified')
        self.assertIn('receipt publication failed', job['detail'])
        self.assertEqual((Path(self.tmp.name)/(job['id']+'.weights')).read_bytes(), b'data')

    def test_receipt_timeout_preserves_publication_without_claiming_delivery(self):
        def send(job, *args):
            self.transfers.update(job, status='Published', awaiting_receipt=True)
            raise TimeoutError()
        with patch.object(self.transfers, 'send', side_effect=send):
            self.transfers.run(self.job, 'local:9092', 'x'*32, b'data')
        self.assertEqual(self.job['status'], 'Published')
        self.assertFalse(self.job['awaiting_receipt'])
        self.assertIn('unconfirmed', self.job['detail'])

    def test_check_connection_missing_topic_and_ready(self):
        for topic, expected in [(None, False), (SimpleNamespace(error=None), True)]:
            admin = SimpleNamespace(list_topics=lambda timeout: SimpleNamespace(topics={} if topic is None else {TOPIC: topic}))
            with patch.dict('sys.modules', {'confluent_kafka.admin': SimpleNamespace(AdminClient=lambda config: admin)}):
                self.assertEqual(self.transfers.check_connection('local:9092')['ready'], expected)

    def test_check_connection_error_is_actionable_and_does_not_leak_exception(self):
        with patch.dict('sys.modules', {'confluent_kafka.admin': SimpleNamespace(AdminClient=lambda config: (_ for _ in ()).throw(RuntimeError('private detail')))}):
            result = self.transfers.check_connection('local:9092')
        self.assertFalse(result['ready'])
        self.assertNotIn('private detail', result['detail'])
        self.assertIn('advertised listeners', result['detail'])

    def test_receipt_in_progress_is_interrupted_after_restart(self):
        self.transfers.update(self.job, status='Published', awaiting_receipt=True)
        reopened = Transfers(self.tmp.name)
        self.assertEqual(reopened.history()[0]['status'], 'Interrupted')
