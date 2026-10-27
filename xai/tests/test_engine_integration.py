"""Integration guards for the preserved source-less engine and DP boundary."""
import hashlib
import importlib.machinery
import json
import math
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

XAI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(XAI_ROOT))
import run_updated


class EngineIntegrationTests(unittest.TestCase):
    def test_preserved_bundle_integrity_and_loader_resolution(self):
        manifest = json.loads((run_updated.ENGINE_ROOT / 'MANIFEST.json').read_text())
        self.assertEqual(manifest['runtime'], 'CPython 3.12')
        self.assertEqual(len(manifest['modules']), 17)
        for name, entry in manifest['modules'].items():
            path = run_updated.ENGINE_ROOT / name
            self.assertEqual(path.stat().st_size, entry['bytes'])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry['sha256'])
        spec = run_updated.CachedXaiFinder().find_spec('xai.temporal')
        self.assertIsInstance(spec.loader, importlib.machinery.SourcelessFileLoader)
        self.assertEqual(Path(spec.origin), run_updated.ENGINE_ROOT / 'temporal.cpython-312.pyc')

    def test_incompatible_runtime_rejected_before_checkpoint_source_staging(self):
        with patch.object(run_updated.sys, 'version_info', (3, 13, 0)), patch.object(run_updated, 'git_blob') as blob:
            with self.assertRaisesRegex(RuntimeError, 'CPython 3.12'):
                run_updated.load_cached_engine('unused')
            blob.assert_not_called()

    def test_dp_target_parity_keeps_original_tolerance(self):
        target_probability = .5

        class Adapter:
            def __init__(self, *args):
                self.frames = {'validation': pd.DataFrame({'txn_id': ['synthetic']})}

            def index(self, *args):
                return 0

            def context(self, *args):
                return None, None, None

            def predictor(self, *args):
                return lambda frame: np.array([math.log(target_probability / (1-target_probability))])

        package = types.ModuleType('xai')
        package.__path__ = []
        temporal = types.ModuleType('xai.temporal')
        temporal.TemporalAdapter = Adapter
        package.temporal = temporal
        with tempfile.TemporaryDirectory() as directory, patch.dict(sys.modules, {'xai': package, 'xai.temporal': temporal}):
            output = Path(directory)
            reference = output / 'local' / 'synthetic_bank' / 'reference_predictions.npz'
            reference.parent.mkdir(parents=True)
            np.savez(reference, validation=np.array([.5]))
            for target_probability, expected in ((.5+2e-6, False), (.5+.5e-6, True)):
                result = run_updated.preflight_dp_cases(output, output/'unused.pt', {'synthetic_bank': ['synthetic']})
                self.assertEqual(result['tolerance'], 1e-6)
                self.assertEqual(result['passed'], expected)
                self.assertEqual(result['cases'][0]['passed'], expected)
                self.assertFalse(result['test_loaded'])


if __name__ == '__main__':
    unittest.main()
