import threading
import time
import unittest
from streaming.app.peer_checks import PeerChecks
from distributed_federation.common.protocol import create_chunks


class PeerCheckTests(unittest.TestCase):
    def setUp(self):
        self.peers = PeerChecks()
        self.secret = 'x'*32

    def test_signed_challenge_response_matches_pending_peer_and_nonce(self):
        event = threading.Event()
        self.peers.pending['fresh'] = ('mac1', event)
        request = self.peers.envelope('peer_probe', 'windows1', 'mac1', 'fresh', self.secret)
        response = self.peers.handle(request, self.secret, 'mac1')
        self.assertIsNotNone(response)
        self.peers.handle(response, self.secret, 'windows1')
        self.assertTrue(event.is_set())

    def test_wrong_secret_recipient_nonce_and_stale_response_cannot_confirm_peer(self):
        event = threading.Event()
        self.peers.pending['fresh'] = ('mac1', event)
        for secret, recipient, nonce, sender, stamp in [
                ('z'*32, 'windows1', 'fresh', 'mac1', time.time()),
                (self.secret, 'other', 'fresh', 'mac1', time.time()),
                (self.secret, 'windows1', 'old', 'mac1', time.time()),
                (self.secret, 'windows1', 'fresh', 'mac2', time.time()),
                (self.secret, 'windows1', 'fresh', 'mac1', time.time()-100)]:
            metadata = dict(message_type='peer_response', run_id=nonce, round_id=0,
                            sender_id=sender, recipient_id=recipient, schema_sha256='peer-check',
                            base_model_sha256='', created_at=stamp)
            raw = create_chunks(b'peer-check-v1', metadata, secret, 4096)[0]
            # create_chunks owns the timestamp; re-sign the stale envelope for this test.
            if stamp < time.time()-30:
                from unittest.mock import patch
                with patch('distributed_federation.common.protocol.time.time', return_value=stamp):
                    raw = create_chunks(b'peer-check-v1', metadata, secret, 4096)[0]
            self.peers.handle(raw, self.secret, 'windows1')
        self.assertFalse(event.is_set())

    def test_invalid_or_unrelated_records_do_not_stop_listener(self):
        for raw in (b'not json', b'[]', b'null', b'\xff', b'x'*9000):
            self.assertIsNone(self.peers.handle(raw, self.secret, 'windows1'))
