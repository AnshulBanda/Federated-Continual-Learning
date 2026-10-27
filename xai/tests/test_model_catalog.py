from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.model_catalog import filter_catalog, model_catalog_rows, verify_saved_metrics


class ModelCatalogTests(unittest.TestCase):
    def test_saved_threshold_is_used_including_equality(self):
        rows = model_catalog_rows("bank", ["one", "two", "three"], ["t"] * 3,
                                  np.array([0, 1, 1]), np.array([.8, .3, .5]), threshold=.5)
        self.assertEqual([row["flagged"] for row in rows], [True, False, True])
        self.assertEqual([row["transaction_id"] for row in filter_catalog(rows, "missed_fraud")], ["two"])
        self.assertEqual([row["threshold"] for row in rows], [.5] * 3)
        self.assertNotIn("member_probabilities", rows[0])

    def test_dataset_labels_do_not_change_the_model_prediction(self):
        first = model_catalog_rows("bank", ["one", "two"], ["t"] * 2,
                                   np.array([0, 1]), np.array([.8, .1]), threshold=.6)
        second = model_catalog_rows("bank", ["one", "two"], ["t"] * 2,
                                    np.array([1, 0]), np.array([.8, .1]), threshold=.6)
        self.assertEqual([row["flagged"] for row in first], [row["flagged"] for row in second])
        self.assertNotEqual([row["status"] for row in first], [row["status"] for row in second])

    def test_incompatible_reference_probabilities_or_metrics_are_rejected(self):
        with self.assertRaises(ValueError):
            model_catalog_rows("bank", ["one"], ["t"], np.array([1]), np.array([.1, .2]), threshold=.5)
        with self.assertRaises(ValueError):
            verify_saved_metrics(np.array([0, 1]), np.array([.2, .8]), .5, {"precision": .2})


if __name__ == "__main__":
    unittest.main()
