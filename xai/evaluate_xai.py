"""Evaluate group SHAP, bounded replay and archived frozen detection separately."""
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from serve_dashboard import AdaptiveFederatedDashboard
from run_updated import git_blob, sha256


def replay_source(adapter, anchor, window, removed=None):
    """Source-level bounded replay independent of the bytecode replay helper."""
    from src.gnn.causal_temporal_graphsage import Events
    state = anchor
    with torch.inference_mode():
        for split, start, batch in window:
            if removed is not None:
                ids = adapter.frames[split].iloc[start:start+len(batch.src)]["txn_id"].astype(str).to_numpy()
                keep = torch.tensor(ids != str(removed), device=batch.src.device)
                batch = Events(*(value[keep] for value in (batch.src, batch.dst, batch.edge_attr, batch.timestamp, batch.labels)))
            if len(batch.src):
                _, state = adapter.model.score_and_update(state, batch)
    return state


def probability(predictor, row):
    logit = float(np.asarray(predictor(pd.DataFrame([row]))).reshape(-1)[0])
    return float(1/(1+np.exp(-np.clip(logit, -40, 40))))


def archived_detection(app):
    """Reuse one-time frozen results, checking checkpoint and cutoff lineage."""
    results = []
    root = "artifacts/research_adaptive_fcl/warm_start"
    for seed in (42, 52, 62):
        raw = git_blob("origin/sia", f"{root}/exploratory_september/context_harmonized_seed_{seed}.json")
        saved = json.loads(raw)
        base = f"{root}/federated/context_harmonized/seed_{seed}"
        assert saved["checkpoint_sha256"] == sha256(git_blob("origin/sia", f"{base}/global_model.pt"))
        metrics_raw = git_blob("origin/sia", f"{base}/metrics.json")
        assert saved["metrics_sha256"] == sha256(metrics_raw)
        metrics = {row["bank"]: row for row in json.loads(metrics_raw)["per_bank"]}
        for row in saved["per_bank"]:
            assert row["threshold_selected_on"] == "validation"
            assert abs(row["threshold"] - metrics[row["bank"]]["threshold"]) < 1e-12
            # Recover integer counts from archived recall-at-k and threshold metrics.
            budget = next(v for v in row["testing_alert_metrics"].values() if v["recall_at_k"] > 0)
            positives = round(budget["true_positives"] / budget["recall_at_k"])
            test = row["testing"]
            tp = round(positives * test["recall"])
            alerts = round(tp/test["precision"]) if test["precision"] else None
            assert alerts is not None and abs(tp/alerts-test["precision"]) < 1e-10
            results.append({"seed": seed, "bank": row["bank"], "cutoff": row["threshold"],
                **{key: test[key] for key in ("precision", "recall", "f1", "pr_auc")},
                "alert_count": alerts, "true_positives": tp, "false_positives": alerts-tp,
                "alert_count_source": "derived from archived exact threshold precision/recall and recall-at-k counts",
                "checkpoint_sha256": saved["checkpoint_sha256"], "artifact_sha256": sha256(raw)})
    return {"status": "archived frozen September evaluation; exploratory because September was previously inspected",
        "test_rerun": False, "threshold_changed": False, "rows": results}


def main():
    app = AdaptiveFederatedDashboard()
    from src.grouped_features import explain_groups
    cases = []
    for bank in app.adapters:
        for path in sorted((app.output / "local" / bank / "reports").glob("*/explanation.json")):
            cases.append((bank, str(json.loads(path.read_text())["transaction_id"])))
    # Deliberate strata: known fraud, false alarm, and legitimate non-alert per bank.
    for bank, rows in app.rows.items():
        for status in ("detected_fraud", "false_alarm", "not_flagged"):
            match = next((r for r in rows if r["status"] == status), None)
            if match and (bank, match["transaction_id"]) not in cases:
                cases.append((bank, match["transaction_id"]))
    result = {"model": app.checkpoint_hash, "case_selection": "cached examples plus first case of each available bank/status stratum",
        "numerical_consistency": [], "stability": [], "faithfulness": [], "temporal_replay": [], "coverage": []}
    for bank, txn in cases:
        print("Evaluating", bank, txn, flush=True)
        report = app.explain(bank, txn)
        adapter = app.adapters[bank]
        index = int(adapter.index("validation", txn))
        state, anchor, window = adapter.context("validation", index, 8)
        row = adapter.frames["validation"].iloc[index]
        predictor = adapter.predictor(state, "validation", index)
        feature = report["feature_explanation"]
        result["numerical_consistency"].append({"bank": bank, "transaction_id": txn,
            "additivity_error": abs(feature["additivity_residual"]),
            "probability_error": abs(feature["target_probability"]-report["prediction"]["probability"])})
        runs = [explain_groups(predictor, row, adapter.frames["training"], seed=seed) for seed in (42, 52, 62)]
        values = np.array([[f["shap_logit"] for f in run["features"]] for run in runs])
        top = np.argmax(np.abs(values), axis=1)
        result["stability"].append({"bank": bank, "transaction_id": txn,
            "reference_seeds": [42,52,62], "references_per_run": 32,
            "groups": [f["feature"] for f in feature["features"]],
            "shap_values": values.tolist(), "range_per_group": np.ptp(values, axis=0).tolist(),
            "top_group_agrees": bool(np.all(top == top[0])),
            "sign_agrees_per_group": [bool(np.all(values[:,i] > 1e-7) or np.all(values[:,i] < -1e-7) or np.all(np.abs(values[:,i]) <= 1e-7)) for i in range(values.shape[1])]})
        result["faithfulness"].append({"bank": bank, "transaction_id": txn,
            "scope": "joint-group reference replacements with other actual groups fixed; not a causal claim",
            "groups": [{"group": f["feature"], "shap_logit": f["shap_logit"],
                "reference_ablation_logit_drop": f["ablation_logit_drop"],
                "direction_agrees": bool(abs(f["shap_logit"]) < 1e-7 or f["shap_logit"]*f["ablation_logit_drop"] >= 0)} for f in feature["features"]]})
        baseline = probability(adapter.predictor(replay_source(adapter, anchor, window), "validation", index), row)
        assert abs(baseline-report["prediction"]["probability"]) < 1e-6
        story = report["transaction_story"]
        effects = story["model_link_effects"]
        checked = []
        for effect in effects:
            without = probability(adapter.predictor(replay_source(adapter, anchor, window, effect["transaction_id"]), "validation", index), row)
            error = abs(without-effect["model_score_without_event"])
            assert error < 1e-6, (txn, effect["transaction_id"], error)
            checked.append({"transaction_id": effect["transaction_id"], "without_probability": without, "error": error})
        result["temporal_replay"].append({"bank": bank, "transaction_id": txn, "baseline_error": abs(baseline-report["prediction"]["probability"]), "independent_source_replays": checked})
        displayed = [e for e in story["transfers"] if e["kind"] == "earlier"]
        effect_ids = {e["transaction_id"] for e in effects}
        verified = sum(e["transaction_id"] in effect_ids for e in displayed)
        result["coverage"].append({"bank": bank, "transaction_id": txn, "displayed_history_edges": len(displayed),
            "verified_displayed_edges": verified, "fraction": verified/len(displayed) if displayed else None})
        # Exact identity lookup and API output; browser checks are recorded separately.
        assert str(row["txn_id"]) == txn and report["bank"] == bank and str(report["transaction_id"]) == txn
        out = app.output / "xai_evaluation.json"
        out.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    result["detection_performance"] = archived_detection(app)
    result["limitations"] = ["Reference stability covers three samples of 32 training rows, not all valid backgrounds.",
        "Stratified cases are a diagnostic sample, not an exhaustive or unbiased estimate.",
        "Numerical consistency, reference stability and perturbation faithfulness are separate measurements.",
        "Graph coverage counts displayed edges with verified effects; untested edges remain context."]
    out.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(out, flush=True)


if __name__ == "__main__":
    main()
