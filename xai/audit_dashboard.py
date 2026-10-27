"""Reproduce saved cutoff selection and independently check cached SHAP reports."""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from serve_dashboard import AdaptiveFederatedDashboard


def main():
    app = AdaptiveFederatedDashboard()
    from src.gnn.causal_temporal_graphsage import choose_threshold
    from src.ensemble_explainer import exact_interventional_shap

    results = {"checkpoint": app.checkpoint_hash, "banks": {}, "features": []}
    for bank, adapter in app.adapters.items():
        labels = adapter.frames["validation"]["y"].to_numpy()
        scores = app.probabilities[bank]
        selected = choose_threshold(labels, scores)
        saved = app.thresholds[bank]
        assert abs(selected - saved) < 1e-6, (bank, selected, saved)
        assert np.array_equal(scores >= selected, scores >= saved), bank
        predicted = scores >= saved
        results["banks"][bank] = {"saved_cutoff": saved, "recomputed_cutoff": selected,
            "absolute_cutoff_error": abs(selected - saved), "identical_alert_decisions": True,
            "selection": "maximum validation F1 over 501 score quantiles",
            "metrics_parity": app.manifest["banks"][bank]["validation_parity"],
            "alerts": int(predicted.sum()), "true_positives": int(((labels == 1) & predicted).sum()),
            "false_positives": int(((labels == 0) & predicted).sum())}
        print("Cutoff verified:", bank, flush=True)
        for path in sorted((app.output / "local" / bank / "reports").glob("*/explanation.json")):
            report = json.loads(path.read_text(encoding="utf-8"))
            # This original audit intentionally reproduces the legacy field SHAP.
            # Grouped production explanations are evaluated by evaluate_xai.py.
            feature = report.get("legacy_feature_explanation", report["feature_explanation"])
            index = int(adapter.index("validation", str(report["transaction_id"])))
            state, _, _ = adapter.context("validation", index, 8)
            predictor = adapter.predictor(state, "validation", index)
            row = adapter.frames["validation"].iloc[index]
            training = adapter.frames["training"].copy()
            training.index = training["txn_id"].astype(str)
            background = training.loc[list(map(str, feature["background_txn_ids"]))]
            names = [item["feature"] for item in feature["features"]]
            recomputed = exact_interventional_shap(predictor, row, background, names)
            actual = {item["feature"]: item["shap_logit"] for item in recomputed["features"]}
            error = max(abs(actual[item["feature"]] - item["shap_logit"]) for item in feature["features"])
            additivity = abs(recomputed["base_logit"] + sum(actual.values()) - recomputed["target_logit"])
            probability = float(1 / (1 + np.exp(-recomputed["target_logit"])))
            probability_error = abs(probability - report["prediction"]["probability"])
            # Independent leave-one-field-out reference ablations corroborate direction.
            ablations = {}
            for name in names:
                hybrids = pd.DataFrame([row.copy() for _ in range(len(background))])
                hybrids[name] = background[name].to_numpy()
                drop = recomputed["target_logit"] - float(np.mean(predictor(hybrids)))
                ablations[name] = {"logit_drop": drop, "shap_logit": actual[name],
                    "direction_agrees": bool(abs(actual[name]) < 1e-7 or drop * actual[name] >= 0)}
            assert error < 1e-5 and additivity < 1e-5 and probability_error < 1e-6
            results["features"].append({"bank": bank, "transaction_id": report["transaction_id"],
                "maximum_shap_error": error, "additivity_error": additivity,
                "displayed_probability_error": probability_error, "ablations": ablations})
            print("Features verified:", bank, report["transaction_id"], flush=True)
    results["limitations"] = ["Validation-selected cutoff and validation metrics are not independent test evidence.",
        "Attributions depend on 32 training reference rows and fixed account memory.",
        "Amount/currency aliases are perturbed separately by the original engine; display grouping is not grouped SHAP.",
        "Ablation direction agreement is a sensitivity check, not proof of fraud or global faithfulness."]
    output = app.output / "xai_audit.json"
    output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    print(output, flush=True)


if __name__ == "__main__":
    main()
