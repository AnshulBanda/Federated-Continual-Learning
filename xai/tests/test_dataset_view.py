"""Portability must reproduce saved bytes, never accept a different manifest."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.dataset_view import verified_dataset_view


class DatasetViewTests(unittest.TestCase):
    def test_line_endings_restored_in_temporary_view_with_original_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            dataset = base / 'data'
            (dataset / 'configuration').mkdir(parents=True)
            (dataset / 'training').mkdir()
            original = b'{\n  "columns": ["amount"]\n}\n'
            restored = original.replace(b'\n', b'\r\n')
            path = dataset / 'configuration/model_feature_columns.json'
            path.write_bytes(original)
            preprocessing = base / 'preprocessing.json'
            preprocessing.write_text(json.dumps({'banks': {'A': {'input_sha256': {
                'configuration/model_feature_columns.json': hashlib.sha256(restored).hexdigest()}}}}))
            view = verified_dataset_view(dataset, preprocessing, base)
            self.assertEqual((view / 'configuration/model_feature_columns.json').read_bytes(), restored)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual((view / 'training').resolve(), (dataset / 'training').resolve())
            self.assertEqual(verified_dataset_view(view, preprocessing, base), view)
            path.write_bytes(b'{"columns": ["unverified"]}')
            with self.assertRaisesRegex(ValueError, 'exact hash'):
                verified_dataset_view(dataset, preprocessing, base)

    def test_conflicting_expected_hashes_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / 'configuration').mkdir()
            (base / 'configuration/model_feature_columns.json').write_text('{}')
            artifact = base / 'preprocessing.json'
            artifact.write_text(json.dumps({'banks': {
                bank: {'input_sha256': {'configuration/model_feature_columns.json': digest}}
                for bank, digest in [('A', hashlib.sha256(b'{}').hexdigest()), ('B', 'wrong')]}}))
            with self.assertRaises(ValueError):
                verified_dataset_view(base, artifact, base)
