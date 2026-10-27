#!/usr/bin/env python3
"""Explain the actual three-seed Sia probability ensemble on fixed cases."""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import pandas as pd

from run_updated import BANKS, DATASET, REPO_ROOT, XAI_ROOT, git_blob, load_cached_engine, normalize_checkpoint_for_engine, sha256


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", nargs=3, type=int, choices=(42, 52, 62), default=(42, 52, 62))
    parser.add_argument("--banks", nargs="+", choices=BANKS, default=BANKS)
    parser.add_argument("--background-size", type=int, default=32)
    args = parser.parse_args()
    if args.background_size < 1:
        parser.error("--background-size must be positive")
    cli = load_cached_engine("origin/sia")
    import xai.temporal as temporal
    from xai.src.ensemble_explainer import exact_interventional_shap, ensemble_logit_predictor, member_probability_details

    case_manifest = json.loads((XAI_ROOT / "outputs/updated/case_manifest.json").read_text(encoding="utf-8"))
    output = XAI_ROOT / "outputs/updated/sia_ensemble" / ("_".join(str(seed) for seed in args.seeds))
    output.mkdir(parents=True, exist_ok=True)
    all_hashes = {}
    for seed in args.seeds:
        rel = f"artifacts/research_adaptive_fcl/warm_start/federated/context_harmonized/seed_{seed}/global_model.pt"
        blob = git_blob("origin/sia", rel)
        all_hashes[str(seed)] = sha256(blob)
    manifest = {"family": "sia_three_member_probability_ensemble", "seeds": args.seeds,
                "checkpoint_sha256": all_hashes, "source_ref": "origin/sia", "evaluation_split": "validation",
                "test_loaded": False, "privacy_mode": "none", "aggregation": "mean of probabilities",
                "explanation_scope": "exact empirical interventional feature SHAP for logit(mean member probability); per-member graph explanations only"}
    (output / "xai_run_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    staging = REPO_ROOT / "tmp"; staging.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="xai_ensemble_", dir=staging) as temp_name:
        temp = Path(temp_name)
        checkpoints = {}
        for seed in args.seeds:
            rel = f"artifacts/research_adaptive_fcl/warm_start/federated/context_harmonized/seed_{seed}/global_model.pt"
            blob = git_blob("origin/sia", rel)
            expected = json.loads((XAI_ROOT / "outputs/updated/sia_context_harmonized" / f"seed_{seed}" / "preprocessing.json").read_text(encoding="utf-8"))["checkpoint_sha256"]
            staged_blob = blob if sha256(blob) == expected else normalize_checkpoint_for_engine(blob)
            if sha256(staged_blob) != expected:
                raise ValueError(f"seed {seed} checkpoint does not match its preprocessing artifact")
            path = temp / f"seed_{seed}.pt"; path.write_bytes(staged_blob); checkpoints[seed] = path
        for bank in args.banks:
            adapters = []
            for seed in args.seeds:
                member_root = XAI_ROOT / "outputs/updated/sia_context_harmonized" / f"seed_{seed}"
                if not (member_root / "preprocessing.json").exists():
                    raise FileNotFoundError(f"Run Sia XAI first for seed {seed}: missing {member_root / 'preprocessing.json'}")
                adapter = temporal.TemporalAdapter(DATASET, checkpoints[seed], bank, "federated",
                    member_root / "preprocessing.json", member_root / "local" / bank / "reference_predictions.npz")
                adapters.append(adapter)
            for transaction_id in case_manifest["cases"][bank]:
                report_dir = output / "local" / bank / "reports" / f"validation_{transaction_id}"
                report_dir.mkdir(parents=True, exist_ok=True)
                if (report_dir / "explanation.json").exists():
                    continue
                member_contexts = []
                for adapter in adapters:
                    idx = int(adapter.index("validation", str(transaction_id)))
                    state, anchor, window = adapter.context("validation", idx, 8)
                    member_contexts.append((adapter, idx, state, anchor, window))
                row = adapters[0].frames["validation"].iloc[member_contexts[0][1]].copy()
                predictors = [adapter.predictor(state, "validation", idx)
                              for adapter, idx, state, _, _ in member_contexts]
                ensemble_predict = ensemble_logit_predictor(predictors)
                details = member_probability_details(predictors, pd.DataFrame([row]))
                member_reports = []
                for seed in args.seeds:
                    report_root = XAI_ROOT / "outputs/updated/sia_context_harmonized" / f"seed_{seed}" / "local" / bank
                    matched = None
                    for path in report_root.glob("reports/validation_*/explanation.json"):
                        doc = json.loads(path.read_text(encoding="utf-8"))
                        if str(doc.get("transaction_id")) == str(transaction_id):
                            matched = doc; break
                    if matched is None:
                        raise FileNotFoundError(f"Missing paired member explanation for {bank}/{transaction_id}, seed {seed}")
                    member_reports.append(matched)
                reference = member_reports[0]
                features = [item["feature"] for item in reference["feature_explanation"]["features"]]
                background = adapters[0].frames["training"].sample(
                    min(args.background_size, len(adapters[0].frames["training"])), random_state=42
                )
                shap = exact_interventional_shap(ensemble_predict, row, background, features)
                shap["background_transaction_ids"] = [str(x) for x in background["txn_id"].tolist()] if "txn_id" in background else []
                combined = {
                    "schema_version": 1, "bank": bank, "transaction_id": str(transaction_id),
                    "split": "validation", "timestamp": reference.get("timestamp"),
                    "prediction": {"probability": details["ensemble_probability"],
                                   "score_type": "uncalibrated arithmetic mean of member probabilities",
                                   "decision": None, "decision_note": "No independently calibrated ensemble threshold was available."},
                    "ensemble": details,
                    "verification": {
                        "member_saved_probabilities": [float(doc["prediction"]["probability"]) for doc in member_reports],
                        "member_probability_absolute_errors": [abs(float(actual) - float(doc["prediction"]["probability"]))
                            for actual, doc in zip(details["member_probabilities"], member_reports)],
                        "ensemble_probability_is_mean_of_members": abs(float(details["ensemble_probability"])
                            - sum(float(doc["prediction"]["probability"]) for doc in member_reports) / len(member_reports)) < 1e-12,
                        "passed": all(abs(float(actual) - float(doc["prediction"]["probability"])) <= 1e-6
                            for actual, doc in zip(details["member_probabilities"], member_reports)),
                        "tolerance": 1e-6,
                    },
                    "feature_explanation": shap,
                    "temporal_explanation": reference.get("temporal_explanation"),
                    "per_member_graph_evidence": [],
                    "limitations": ["Feature SHAP targets the actual mean-probability ensemble with pre-event memory fixed for each member.",
                                   "Graph perturbation evidence is not recomputed for the ensemble; stored graph evidence is from the seed-42 member only.",
                                   "The mean probability has no independent ensemble alert threshold.",
                                   "This is model behavior, not fraud, laundering typology, or causal evidence."],
                    "xai_provenance": manifest,
                }
                # Replace repeated seed-42 evidence with each member's matched report.
                member_graphs = [{"seed": seed, "graph_explanation": doc.get("graph_explanation")}
                                 for seed, doc in zip(args.seeds, member_reports)]
                combined["per_member_graph_evidence"] = member_graphs
                # Preserve stable internal index naming used by the dashboard loader.
                (report_dir / "explanation.json").write_text(json.dumps(combined, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"Saved ensemble explanations: {output}")


if __name__ == "__main__":
    main()
