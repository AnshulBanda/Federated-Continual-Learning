import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from serve_dashboard import cached_explanation_matches


class DashboardCacheTests(unittest.TestCase):
    def setUp(self):
        self.report = {
            "cache_key": "current-key",
            "verification": {"passed": True},
            "model": {"checkpoint_sha256": "current-checkpoint"},
            "prediction": {"probability": 0.42},
            "feature_explanation": {"target_probability": 0.4200001},
        }

    def test_matching_verified_explanation_is_reused(self):
        self.assertTrue(cached_explanation_matches(
            self.report, "current-key", "current-checkpoint"))

    def test_legacy_cache_without_target_score_is_regenerated(self):
        self.report["feature_explanation"].pop("target_probability")
        self.assertFalse(cached_explanation_matches(
            self.report, "current-key", "current-checkpoint"))

    def test_cache_with_a_different_shap_target_is_regenerated(self):
        self.report["feature_explanation"]["target_probability"] = 0.7
        self.assertFalse(cached_explanation_matches(
            self.report, "current-key", "current-checkpoint"))

    def test_wrong_cache_key_or_checkpoint_is_not_reused(self):
        self.assertFalse(cached_explanation_matches(
            self.report, "old-key", "current-checkpoint"))
        self.assertFalse(cached_explanation_matches(
            self.report, "current-key", "old-checkpoint"))


class FullDashboardCacheTests(unittest.TestCase):
    def setUp(self):
        import json
        path = Path(__file__).resolve().parents[1] / 'outputs/updated/adaptive_federated/seed_42/local/Wells_Fargo/reports/validation_2954161/explanation.json'
        self.report = json.loads(path.read_text())
        self.key = self.report['cache_key']
        self.inputs = self.report['cache_key_inputs']
        self.checkpoint = self.report['model']['checkpoint_sha256']
        self.score = self.report['prediction']['probability']

    def matches(self):
        return cached_explanation_matches(self.report, self.key, self.checkpoint, self.inputs, self.score)

    def test_identity_model_specific_cache_and_exact_guard(self):
        self.assertTrue(self.matches())
        for field, value in [('bank', 'OtherBank'), ('transaction_id', 'other')]:
            original = self.report[field]
            self.report[field] = value
            self.assertFalse(self.matches())
            self.report[field] = original
        self.report['verification']['tolerance'] = 1e-5
        self.assertFalse(self.matches())

    def test_mismatched_preprocessing_score_and_decision_are_rejected(self):
        import copy
        valid = copy.deepcopy(self.report)
        for section, field, value in [
            ('xai_provenance', 'preprocessing_sha256', 'wrong'),
            ('prediction', 'probability', self.score + 1.5e-6),
            ('prediction', 'class', 'not_fraud'),
            ('verification', 'direct_model_probability', self.score + 1.5e-6),
            ('verification', 'passed', False),
        ]:
            self.report = copy.deepcopy(valid)
            self.report[section][field] = value
            self.assertFalse(self.matches(), (section, field))


if __name__ == "__main__":
    unittest.main()
