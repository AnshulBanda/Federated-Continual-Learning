from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

XAI_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = XAI_ROOT.parent
sys.path.insert(0, str(XAI_ROOT))

from src.checkpoint_comparison import compare_checkpoints
from src.counterfactuals import constrained_amount_counterfactuals
from src.dashboard import build_dashboard
from src.ensemble_catalog import catalog_rows, filter_catalog
from src.ensemble_explainer import ensemble_logit_predictor, exact_interventional_shap, member_probability_details
from src.privacy_audit import redact_for_sharing


class XaiExtensionTests(unittest.TestCase):
    def test_counterfactual_keeps_amount_aliases_together_and_crosses_threshold(self):
        row = pd.Series({"amount": 100.0, "Amount_Received": 100.0, "currency": "USD", "payment_format": "ACH"})
        training = pd.DataFrame({
            "amount": [20.0, 50.0, 80.0, 120.0, 160.0, 200.0],
            "Amount_Received": [20.0, 50.0, 80.0, 120.0, 160.0, 200.0],
            "currency": ["USD"] * 6, "payment_format": ["ACH"] * 6,
        })

        def scorer(frame):
            return (pd.to_numeric(frame["amount"]).to_numpy() - 100.0) / 10.0

        result = constrained_amount_counterfactuals(row, training, scorer, threshold=0.7)
        self.assertEqual(result["status"], "found")
        candidate = result["counterfactuals"][0]
        self.assertEqual(candidate["changed_features"]["amount"], candidate["changed_features"]["Amount_Received"])
        self.assertGreaterEqual(candidate["counterfactual_probability"], 0.7)
        self.assertEqual(candidate["valid"], True)

    def test_exact_ensemble_shap_targets_mean_probability(self):
        first = lambda frame: frame["x"].to_numpy(dtype=float)
        second = lambda frame: (frame["x"].to_numpy(dtype=float) + frame["y"].to_numpy(dtype=float)) / 2.0
        predictor = ensemble_logit_predictor([first, second])
        row = pd.Series({"x": 1.0, "y": 2.0})
        background = pd.DataFrame({"x": [0.0, 0.0], "y": [0.0, 0.0]})
        explanation = exact_interventional_shap(predictor, row, background, ["x", "y"])
        detail = member_probability_details([first, second], pd.DataFrame([row]))
        self.assertAlmostEqual(detail["ensemble_probability"], float(1 / (1 + np.exp(-explanation["target_logit"]))), places=10)
        self.assertLess(abs(explanation["additivity_residual"]), 1e-10)
        self.assertEqual(explanation["units"], "logit(mean member probability)")

    def test_checkpoint_comparison_only_uses_shared_cases(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "tmp") as temp:
            base = Path(temp)
            roots = {"a": base / "a", "b": base / "b"}
            docs = {
                "a": [{"bank": "BankA", "transaction_id": "t1", "prediction": {"probability": 0.4, "class": "fraud"}, "feature_explanation": {"features": [{"feature": "amount", "shap_logit": 1.0}]}, "graph_explanation": {"important_edges": []}},
                      {"bank": "BankA", "transaction_id": "only-a", "prediction": {"probability": 0.2, "class": "legitimate"}, "feature_explanation": {"features": []}}],
                "b": [{"bank": "BankA", "transaction_id": "t1", "prediction": {"probability": 0.6, "class": "fraud"}, "feature_explanation": {"features": [{"feature": "amount", "shap_logit": 2.0}]}, "graph_explanation": {"important_edges": []}}],
            }
            for name, records in docs.items():
                for doc in records:
                    path = roots[name] / "local" / doc["bank"] / "reports" / f"validation_{doc['transaction_id']}" / "explanation.json"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(doc), encoding="utf-8")
            result = compare_checkpoints(roots, base / "comparison")
            self.assertEqual(result["shared_case_count"], 1)
            self.assertEqual(result["comparisons"][0]["paired_cases"], 1)

    def test_redaction_pseudonymizes_and_removes_private_detail(self):
        source = {"transaction_id": "123", "account_id": 456, "prediction": {"probability": 0.9},
                  "feature_explanation": {"features": [{"feature": "amount", "value": 100.0}]},
                  "graph_explanation": {"important_edges": [{"source": 2, "target": 3}]},
                  "temporal_explanation": {"historical_events": [{"txn_id": "old"}]}}
        result = redact_for_sharing(source, key=b"a sufficiently long test key for hmac")
        self.assertTrue(result["transaction_id"].startswith("id_"))
        self.assertNotIn("account_id", result)
        self.assertNotIn("important_edges", result["graph_explanation"])
        self.assertNotIn("historical_events", result["temporal_explanation"])
        self.assertNotIn("value", result["feature_explanation"]["features"][0])

    def test_dashboard_builds_from_report_json(self):
        with tempfile.TemporaryDirectory(dir=REPO_ROOT / "tmp") as temp:
            root = Path(temp) / "run"
            report = root / "local" / "BankA" / "reports" / "validation_1" / "explanation.json"
            report.parent.mkdir(parents=True)
            report.write_text(json.dumps({"bank": "BankA", "transaction_id": "t1", "split": "validation",
                                          "prediction": {"probability": 0.5, "threshold": 0.2, "class": "fraud"},
                                          "feature_explanation": {"features": []}}), encoding="utf-8")
            output = Path(temp) / "dashboard.html"
            self.assertEqual(build_dashboard(root, output), 1)
            self.assertIn("Federated AML", output.read_text(encoding="utf-8"))

    def test_ensemble_catalog_separates_flagged_known_and_missed_fraud(self):
        rows, threshold = catalog_rows(
            "BankA", ["TX101", "TX102", "TX103", "TX104"], ["t1", "t2", "t3", "t4"],
            np.asarray([1, 1, 0, 0]),
            [np.asarray([.8, .2, .7, .1])] * 3,
        )
        self.assertAlmostEqual(threshold, 0.1006)
        self.assertEqual([item["transaction_id"] for item in filter_catalog(rows, "flagged")], ["TX101", "TX102", "TX103"])
        self.assertEqual([item["transaction_id"] for item in filter_catalog(rows, "known_fraud")], ["TX101", "TX102"])
        self.assertEqual([item["transaction_id"] for item in filter_catalog(rows, "missed_fraud")], [])

    def test_catalog_missed_fraud_filter_is_independent_of_flagged_view(self):
        rows, _ = catalog_rows(
            "BankA", ["hit", "miss", "noise1", "noise2", "noise3"],
            ["t1", "t2", "t3", "t4", "t5"], np.asarray([1, 1, 0, 0, 0]),
            [np.asarray([.9, .3, .5, .5, .5])] * 3,
        )
        self.assertEqual([item["transaction_id"] for item in filter_catalog(rows, "flagged")], ["hit"])
        self.assertEqual([item["transaction_id"] for item in filter_catalog(rows, "known_fraud")], ["hit", "miss"])
        self.assertEqual([item["transaction_id"] for item in filter_catalog(rows, "missed_fraud")], ["miss"])
        self.assertEqual(len(filter_catalog(rows, "all", "HIT")), 1)


if __name__ == "__main__":
    unittest.main()
