import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from distributed_federation.common.protocol import create_chunks

from streaming.app.transfers import Transfers


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.transfers = Transfers(self.tmp.name)
        self.addCleanup(self.transfers.close)
        self.env = patch.dict(os.environ, FCL_TRANSFER_SECRET='x'*32)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.payload = b'checkpoint-bytes'
        self.upload = self.transfers.upload(self.payload)
        self.values = dict(mode='send', broker='local:9092', transfer_id='first', sender='windows1',
                           recipient='mac1', file_id=self.upload['file_id'], file_name='model.pt')

    def failed_send(self):
        with patch.object(self.transfers, 'send', side_effect=TimeoutError()):
            key = self.transfers.start(self.values)
            self.transfers.worker.join(2)
        return key

    def test_retry_after_restart_preserves_source_and_records_parent(self):
        first = self.failed_send()
        self.transfers = Transfers(self.tmp.name)
        self.addCleanup(self.transfers.close)
        captured = []
        with patch.object(self.transfers, 'send', side_effect=lambda job, broker, secret, payload: captured.append(payload)):
            retry = self.transfers.retry(first, 'second')
            self.transfers.worker.join(2)
        old = self.transfers.get_job(first)
        new = self.transfers.get_job(retry)
        self.assertEqual(captured, [self.payload])
        self.assertEqual(old['status'], 'Failed')
        self.assertEqual(new['retry_of'], first)
        self.assertEqual(new['transfer_id'], 'second')
        self.assertEqual(new['source_sha256'], old['source_sha256'])
        self.assertEqual(new['file_id'], old['file_id'])
        self.assertNotIn('x'*32, json.dumps(self.transfers.history()))

    def test_retry_rejects_changed_and_missing_uploads(self):
        key = self.failed_send()
        path = Path(self.tmp.name)/(self.upload['file_id']+'.upload')
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.transfers.retry(key, 'second')
        path.unlink()
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            self.transfers.retry(key, 'third')
        self.assertIsNone(self.transfers.active)

    def test_retry_rejects_reused_ids_and_completed_jobs(self):
        key = self.failed_send()
        with self.assertRaisesRegex(ValueError, 'NEW'):
            self.transfers.retry(key, 'first')
        with self.assertRaisesRegex(ValueError, 'already used'):
            self.transfers.start(self.values)
        job = self.transfers.get_job(key)
        self.transfers.update(job, status='Delivered')
        with self.assertRaises(ValueError):
            self.transfers.retry(key, 'second')

    def test_receiver_retry_pins_expected_file_hash(self):
        job = dict(id='receiver', mode='receive', status='Failed', broker='local:9092', sender='windows1',
                   recipient='mac1', transfer_id='first', bytes=2, expected_sha256=hashlib.sha256(self.payload).hexdigest())
        self.transfers.update(job)
        with patch.object(self.transfers, 'receive'):
            key = self.transfers.retry(job['id'], 'second')
            self.transfers.worker.join(2)
        self.assertEqual(self.transfers.get_job(key)['expected_sha256'], job['expected_sha256'])

    def test_rechecks_retained_receipt_after_restart_without_sending_chunks(self):
        job = dict(id='sender', mode='send', status='Published', awaiting_receipt=True, broker='local:9092',
                   transfer_id='first', sender='windows1', recipient='mac1', total=16, bytes=16,
                   receipt_token='token', publication_acked=True, sha256=hashlib.sha256(self.payload).hexdigest())
        self.transfers.update(job)
        self.transfers = Transfers(self.tmp.name)
        self.addCleanup(self.transfers.close)
        def delivered(current, *args):
            self.transfers.update(current, status='Delivered')
        with patch.object(self.transfers, 'wait_receipt', side_effect=delivered) as wait, patch.object(self.transfers, 'send') as send:
            self.transfers.recover('sender')
            self.transfers.worker.join(2)
        wait.assert_called_once()
        send.assert_not_called()
        self.assertEqual(self.transfers.get_job('sender')['status'], 'Delivered')

    def test_receipt_recovery_preserves_verified_file_and_refuses_tampering(self):
        job = dict(id='receiver', mode='receive', status='Verified', broker='local:9092', transfer_id='first',
                   sender='windows1', recipient='mac1', receipt_token='token', total=len(self.payload), bytes=len(self.payload),
                   sha256=hashlib.sha256(self.payload).hexdigest())
        self.transfers.update(job)
        path = Path(self.tmp.name)/'receiver.weights'
        path.write_bytes(self.payload)
        with patch.object(self.transfers, 'publish_receipt') as publish:
            self.transfers.recover('receiver')
            self.transfers.worker.join(2)
        publish.assert_called_once()
        self.assertTrue(self.transfers.get_job('receiver')['receipt_sent'])
        path.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.transfers.recover('receiver')

    def test_restart_reconciles_atomic_file_saved_before_completion_record(self):
        job = dict(id='receiver', mode='receive', status='Receiving', total=len(self.payload), bytes=len(self.payload),
                   expected_sha256=hashlib.sha256(self.payload).hexdigest(), receipt_token='token')
        self.transfers.update(job)
        (Path(self.tmp.name)/'receiver.weights').write_bytes(self.payload)
        reopened = Transfers(self.tmp.name)
        self.assertEqual(reopened.get_job('receiver')['status'], 'Verified')
        self.assertEqual(reopened.get_job('receiver')['sha256'], job['expected_sha256'])

    def test_restart_does_not_verify_partial_or_changed_file(self):
        job = dict(id='receiver', mode='receive', status='Receiving', total=len(self.payload), bytes=2,
                   expected_sha256=hashlib.sha256(self.payload).hexdigest())
        self.transfers.update(job)
        (Path(self.tmp.name)/'receiver.weights').write_bytes(b'partial')
        self.assertEqual(Transfers(self.tmp.name).get_job('receiver')['status'], 'Interrupted')

    def test_receiver_retry_rejects_different_signed_checkpoint(self):
        wrong_payload = b'other-model'
        metadata = dict(message_type='weight_file', run_id='second', round_id=0, sender_id='windows1',
                        recipient_id='mac1', schema_sha256='opaque-file', base_model_sha256='', file_size=len(wrong_payload))
        raw = create_chunks(wrong_payload, metadata, 'x'*32, 500)[0]
        consumer = SimpleNamespace(subscribe=lambda topics: None, close=lambda: None,
            poll=lambda timeout: SimpleNamespace(error=lambda: None, value=lambda: raw))
        job = dict(id='receiver', mode='receive', transfer_id='second', sender='windows1', recipient='mac1',
                   bytes=0, expected_sha256=hashlib.sha256(self.payload).hexdigest())
        with patch.dict('sys.modules', {'confluent_kafka': SimpleNamespace(Consumer=lambda config: consumer)}):
            with self.assertRaises(ValueError):
                self.transfers.receive(job, 'local:9092', 'x'*32)
        self.assertFalse((Path(self.tmp.name)/'receiver.weights').exists())

    def test_failed_receipt_recovery_preserves_evidence_and_clears_busy_state(self):
        job = dict(id='sender', mode='send', status='Published', broker='local:9092', receipt_token='token',
                   publication_acked=True, sha256='a'*64)
        self.transfers.update(job)
        with patch.object(self.transfers, 'wait_receipt', side_effect=TimeoutError):
            self.transfers.recover('sender')
            self.transfers.worker.join(2)
        self.assertEqual(self.transfers.get_job('sender')['status'], 'Published')
        self.assertFalse(self.transfers.get_job('sender')['awaiting_receipt'])
        self.assertIsNone(self.transfers.active)
