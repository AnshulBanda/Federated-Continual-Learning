from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.transaction_story import build_transaction_story, canonical_frames, completed_history


def event(txn_id, source, target, day):
    return {"txn_id": txn_id, "src_node": source, "dst_node": target,
            "timestamp": f"2025-08-{day:02d} 10:00:00", "amount": 100,
            "currency": "USD", "payment_format": "ACH", "y": 0}


def report():
    probabilities = [.6, .7, .8]
    without = [.5, .6, .7]
    members = []
    for seed, original, removed in zip([42, 52, 62], probabilities, without):
        members.append({"seed": seed, "graph_explanation": {
            "fidelity": {"original_probability": original, "unperturbed_replay_error": 0},
            "important_edges": [{"transaction_id": "h2", "source": 3, "target": 1,
                                 "timestamp": "2025-08-02 10:00:00", "probability_without": removed}]}})
    return {"prediction": {"probability": .7}, "ensemble": {"member_probabilities": probabilities},
            "per_member_graph_evidence": members,
            "feature_explanation": {"features": [{"feature": "payment_format", "value": "ACH", "shap_logit": 1}]}}


class TransactionStoryTests(unittest.TestCase):
    def test_all_eligible_history_is_retained_separately_from_bounded_graph(self):
        row = pd.Series(event("selected", 1, 2, 10))
        history = pd.DataFrame([event(f"h{day}", 1, day + 2, day) for day in range(1, 7)]
                               + [event("future", 1, 2, 11)])
        result = build_transaction_story(row, history, report(), max_edges=3)
        self.assertEqual(len(result["transfers"]), 3)
        self.assertEqual(len(result["eligible_earlier_transfers"]), 6)
        self.assertEqual(result["earlier_related_transfers_considered"], 6)
        self.assertNotIn("future", [e["transaction_id"] for e in result["eligible_earlier_transfers"]])

    def test_split_local_node_ids_do_not_connect_different_accounts(self):
        adapter = SimpleNamespace(
            frames={"training": pd.DataFrame([event("train", 1, 2, 1)]),
                    "validation": pd.DataFrame([event("same_batch", 1, 2, 2), event("selected", 1, 2, 3)])},
            streams={"training": SimpleNamespace(src=torch.tensor([100]), dst=torch.tensor([200])),
                     "validation": SimpleNamespace(src=torch.tensor([300, 300]), dst=torch.tensor([400, 400]))},
        )
        frames = canonical_frames(adapter)
        history = completed_history(frames["training"], frames["validation"], 1, 2)
        story = build_transaction_story(frames["validation"].iloc[1], history, report())
        self.assertEqual(story["selected_transfer"]["source"], 300)
        self.assertEqual(story["selected_transfer"]["target"], 400)
        self.assertEqual(story["pattern"], "single_transfer")
        self.assertEqual(len(story["transfers"]), 1)
        self.assertEqual(adapter.frames["validation"].iloc[1]["src_node"], 1)

    def test_inconsistent_account_mapping_rejects_story(self):
        adapter = SimpleNamespace(
            frames={"training": pd.DataFrame([event("one", 1, 2, 1), event("two", 1, 3, 2)])},
            streams={"training": SimpleNamespace(src=torch.tensor([100, 999]), dst=torch.tensor([200, 300]))},
        )
        with self.assertRaisesRegex(ValueError, "do not align"):
            canonical_frames(adapter)

    def test_history_excludes_current_batch_and_future_training_rows(self):
        training = pd.DataFrame([event("train", 1, 3, 1), event("future", 2, 1, 10)])
        validation = pd.DataFrame([event("same_batch", 3, 1, 2), event("selected", 1, 2, 3), event("later", 2, 1, 4)])
        history = completed_history(training, validation, index=1, batch_size=2)
        self.assertEqual(history["txn_id"].tolist(), ["train"])
        self.assertNotIn("y", history.columns)

    def test_loop_requires_chronologically_observed_transfers(self):
        row = pd.Series(event("selected", 1, 2, 4))
        history = pd.DataFrame([event("h1", 2, 3, 1), event("h2", 3, 1, 2)])
        story = build_transaction_story(row, history, report())
        self.assertEqual(story["pattern"], "observed_return_path")
        self.assertIn("2 → 3 → 1 → 2", story["observation"])
        self.assertEqual(story["selected_transfer"]["source_alias"], "A")
        self.assertTrue(story["path_is_not_a_fraud_classification"])
        self.assertEqual([event["transaction_id"] for event in story["eligible_earlier_transfers"]], ["h1", "h2"])
        self.assertEqual(story["eligible_earlier_transfers"][0]["source_account_id"], "2")
        history.loc[0, "timestamp"] = "2025-08-03 10:00:00"
        unordered = build_transaction_story(row, history, report())
        self.assertNotEqual(unordered["pattern"], "observed_return_path")

    def test_actual_account_ids_and_transaction_ids_are_kept_separate(self):
        row = pd.Series(event("TX300", 1, 2, 4))
        history = pd.DataFrame([event("TX100", 2, 3, 1), event("TX200", 3, 1, 2)])
        result = build_transaction_story(row, history, report(), account_ids={1: "00123", 2: "00045", 3: "00999"})
        self.assertEqual(result["selected_transfer"]["transaction_id"], "TX300")
        self.assertEqual(result["selected_transfer"]["source_account_id"], "00123")
        self.assertEqual(result["selected_transfer"]["target_account_id"], "00045")
        self.assertIn("00045 → 00999 → 00123 → 00045", result["observation"])
        self.assertIn("TX100 → TX200 → TX300", result["observation"])
        with self.assertRaisesRegex(ValueError, "absent"):
            build_transaction_story(row, history, report(), account_ids={1: "00123"})

    def test_ensemble_effect_uses_same_event_checked_in_all_three_models(self):
        row = pd.Series(event("selected", 1, 2, 4))
        history = pd.DataFrame([event("h2", 3, 1, 2)])
        result = build_transaction_story(row, history, report())
        effect = result["ensemble_link_effects"][0]
        self.assertAlmostEqual(effect["ensemble_score_without_event"], .6)
        self.assertAlmostEqual(effect["score_support"], .1)
        partial = copy.deepcopy(report())
        partial["per_member_graph_evidence"][2]["graph_explanation"]["important_edges"] = []
        self.assertEqual(build_transaction_story(row, history, partial)["ensemble_link_effects"], [])

    def test_selected_global_model_effect_does_not_average_other_runs(self):
        row = pd.Series(event("selected", 1, 2, 4))
        history = pd.DataFrame([event("h2", 3, 1, 2)])
        fixture = report()
        single = {"prediction": {"probability": .6},
                  "graph_explanation": fixture["per_member_graph_evidence"][0]["graph_explanation"],
                  "feature_explanation": fixture["feature_explanation"]}
        result = build_transaction_story(row, history, single)
        self.assertNotIn("ensemble_link_effects", result)
        effect = result["model_link_effects"][0]
        self.assertAlmostEqual(effect["original_model_score"], .6)
        self.assertAlmostEqual(effect["model_score_without_event"], .5)
        self.assertEqual(effect["verified_model_count"], 1)
        single["graph_explanation"]["fidelity"]["original_probability"] = .7
        self.assertEqual(build_transaction_story(row, history, single)["model_link_effects"], [])

    def test_future_edges_and_no_history_never_create_a_claimed_path(self):
        row = pd.Series(event("selected", 1, 2, 4))
        history = pd.DataFrame([event("future", 2, 1, 5)])
        result = build_transaction_story(row, history, report())
        self.assertEqual(result["pattern"], "single_transfer")
        self.assertEqual(len(result["transfers"]), 1)
        self.assertEqual(result["ensemble_link_effects"], [])

    def test_mismatched_event_endpoints_or_replay_failure_reject_effect(self):
        row = pd.Series(event("selected", 1, 2, 4))
        history = pd.DataFrame([event("h2", 3, 1, 2)])
        for field, value in [("source", 99), ("timestamp", "2025-08-01 10:00:00")]:
            invalid = report()
            invalid["per_member_graph_evidence"][0]["graph_explanation"]["important_edges"][0][field] = value
            self.assertEqual(build_transaction_story(row, history, invalid)["ensemble_link_effects"], [])
        invalid = report()
        invalid["per_member_graph_evidence"][1]["graph_explanation"]["fidelity"]["unperturbed_replay_error"] = .01
        self.assertEqual(build_transaction_story(row, history, invalid)["ensemble_link_effects"], [])


if __name__ == "__main__":
    unittest.main()
