import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from streaming.app.overview import Overview, BANKS

class OverviewTests(unittest.TestCase):
    def test_bank_persists_and_metrics_match_selected_bank(self):
        with tempfile.TemporaryDirectory() as tmp:
            overview = Overview(tmp)
            self.assertIsNone(overview.load()['bank'])
            for bank in BANKS:
                result = overview.save({'bank': bank})
                self.assertEqual(Overview(tmp).load()['bank'], bank)
                self.assertEqual(len(result['active_model']['members']),3)
                self.assertIsNone(result['last_training'])
                source = json.loads((overview.repo / 'artifacts/research_seed_ensemble/exploratory_september/metrics.json').read_text())
                expected = next(row['testing'] for row in source['per_bank'] if row['bank'] == bank)
                for metric in ('pr_auc', 'precision', 'recall'):
                    self.assertEqual(result['evaluation'][metric], expected[metric])
    def test_invalid_identity_and_missing_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            overview = Overview(tmp, repo=tmp)
            for value in ({'bank': 'unknown'}, {'bank': []}, {'bank': 'Key_Bank', 'secret': 'x'}):
                with self.assertRaises(ValueError):
                    overview.save(value)
            result = overview.save({'bank': 'Key_Bank'})
            self.assertIsNone(result['evaluation'])
            self.assertTrue(result['warnings'])
            overview.path.write_text('broken')
            self.assertIsNone(overview.load()['bank'])
    def test_failed_save_preserves_previous_bank(self):
        with tempfile.TemporaryDirectory() as tmp:
            overview = Overview(tmp)
            overview.save({'bank': 'Key_Bank'})
            with patch('streaming.app.overview.os.replace', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):
                    overview.save({'bank': 'Wells_Fargo'})
            self.assertEqual(overview.load()['bank'], 'Key_Bank')
