import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.grouped_features import explain_groups


class GroupedFeatureTests(unittest.TestCase):
    def setUp(self):
        self.row = pd.Series(dict(txn_id="target", src_node=7, dst_node=8,
            timestamp="2025-08-20", payment_format="ACH", amount=5.,
            Amount_Received=5., currency="USD", Receiving_Currency="USD"))
        self.training = pd.DataFrame([
            dict(self.row, txn_id="a", amount=10., Amount_Received=9., currency="EUR", Receiving_Currency="GBP", payment_format="Wire"),
            dict(self.row, txn_id="b", amount=20., Amount_Received=20., payment_format="ACH")])

    def test_joint_replacements_preserve_whole_transfer_and_target_metadata(self):
        allowed = {(5.,5.,"USD","USD"), (10.,9.,"EUR","GBP"), (20.,20.,"USD","USD")}
        def predict(frame):
            self.assertTrue((frame.txn_id == "target").all())
            self.assertTrue((frame.src_node == 7).all())
            for row in frame.itertuples():
                self.assertIn((row.amount,row.Amount_Received,row.currency,row.Receiving_Currency),allowed)
            return np.asarray(frame.amount)*.01 + (frame.payment_format == "ACH").astype(float)
        result = explain_groups(predict, self.row, self.training)
        self.assertEqual(len(result["features"]), 2)
        self.assertLess(abs(result["additivity_residual"]), 1e-12)
        self.assertEqual(result["groups"]["transfer_terms"], ["amount","Amount_Received","currency","Receiving_Currency"])
        terms = next(f for f in result["features"] if f["feature"] == "transfer_terms")
        self.assertLess(terms["shap_logit"], 0)

    def test_constant_model_gives_zero_attributions(self):
        result = explain_groups(lambda frame: np.full(len(frame), .5), self.row, self.training)
        self.assertTrue(all(f["shap_logit"] == 0 for f in result["features"]))

    def test_recorded_background_can_be_reproduced(self):
        predictor = lambda frame: np.asarray(frame.amount,dtype=float)
        first = explain_groups(predictor, self.row, self.training, background_size=1, seed=52)
        second = explain_groups(predictor, self.row, self.training, background_ids=first["background_txn_ids"])
        self.assertEqual(first["features"], second["features"])

    def test_nonfinite_model_output_is_rejected(self):
        with self.assertRaises(ValueError):
            explain_groups(lambda frame: np.full(len(frame), np.nan), self.row, self.training)


if __name__ == "__main__":
    unittest.main()
