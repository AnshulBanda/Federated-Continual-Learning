"""Paired checkpoint-level XAI comparison on fixed bank/transaction cases."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import mean
from typing import Any


def _report_map(root: Path) -> dict[tuple[str, str], dict[str, Any]]:
    found: dict[tuple[str, str], dict[str, Any]] = {}
    for path in root.glob("**/reports/validation_*/explanation.json"):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            found[(str(doc["bank"]), str(doc["transaction_id"]))] = doc
        except (OSError, KeyError, json.JSONDecodeError):
            continue
    return found


def compare_checkpoints(roots: dict[str, Path], output_dir: Path) -> dict[str, Any]:
    """Compare only identical cases; write local pair-level and safe aggregate files."""
    if len(roots) < 2:
        raise ValueError("at least two checkpoint report roots are required")
    reports = {name: _report_map(root) for name, root in roots.items()}
    shared = set.intersection(*(set(items) for items in reports.values()))
    rows = []
    for bank, txn_id in sorted(shared):
        docs = {name: mapping[(bank, txn_id)] for name, mapping in reports.items()}
        for name, doc in docs.items():
            pred = doc.get("prediction", {})
            feats = doc.get("feature_explanation", {}).get("features", [])
            top = [f["feature"] for f in sorted(feats, key=lambda f: abs(float(f.get("shap_logit", 0))), reverse=True)[:3]]
            rows.append({"bank": bank, "transaction_id": txn_id, "checkpoint": name,
                         "probability": pred.get("probability"), "threshold": pred.get("threshold"),
                         "decision": pred.get("class"), "top3_features": "|".join(top),
                         "verification_passed": doc.get("verification", {}).get("passed")})
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "paired_case_details.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=("bank", "transaction_id", "checkpoint", "probability", "threshold", "decision", "top3_features", "verification_passed"))
        writer.writeheader(); writer.writerows(rows)

    comparisons = []
    base_name = next(iter(roots))
    base = reports[base_name]
    for name in list(roots)[1:]:
        other = reports[name]
        deltas = []
        jaccards = []
        decision_flips = 0
        graph_jaccards = []
        for key in sorted(set(base) & set(other)):
            a, b = base[key], other[key]
            pa = float(a["prediction"]["probability"]); pb = float(b["prediction"]["probability"])
            deltas.append(abs(pa - pb))
            def top_features(doc: dict[str, Any]) -> set[str]:
                fs = doc.get("feature_explanation", {}).get("features", [])
                return {x["feature"] for x in sorted(fs, key=lambda x: abs(float(x.get("shap_logit", 0))), reverse=True)[:3]}
            fa, fb = top_features(a), top_features(b)
            jaccards.append(len(fa & fb) / len(fa | fb) if (fa | fb) else 1.0)
            def top_edges(doc: dict[str, Any]) -> set[tuple[str, str]]:
                edges = doc.get("graph_explanation", {}).get("important_edges", [])
                ranked = sorted(edges, key=lambda edge: abs(float(edge.get("delta_probability", 0))), reverse=True)[:5]
                return {(str(edge.get("source", edge.get("src"))), str(edge.get("target", edge.get("dst")))) for edge in ranked}
            ea, eb = top_edges(a), top_edges(b)
            graph_jaccards.append(len(ea & eb) / len(ea | eb) if (ea | eb) else 1.0)
            decision_flips += a.get("prediction", {}).get("class") != b.get("prediction", {}).get("class")
        def metric_means(name: str) -> dict[str, float]:
            manifest_path = roots[name] / "xai_run_manifest.json"
            if not manifest_path.exists():
                return {}
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            banks = manifest.get("validation_metrics", [])
            keys = ("pr_auc", "roc_auc", "precision", "recall", "f1")
            found = {}
            for metric in keys:
                vals = []
                for row in banks:
                    if not isinstance(row, dict):
                        continue
                    metric_block = row.get("metrics") or row.get("validation")
                    if isinstance(metric_block, dict) and metric_block.get(metric) is not None:
                        vals.append(float(metric_block[metric]))
                if vals:
                    found[metric] = mean(vals)
            return found
        comparisons.append({"baseline": base_name, "comparison": name, "paired_cases": len(deltas),
                            "mean_absolute_probability_change": mean(deltas) if deltas else None,
                            "mean_top3_feature_jaccard": mean(jaccards) if jaccards else None,
                            "mean_top5_graph_edge_jaccard": mean(graph_jaccards) if graph_jaccards else None,
                            "decision_flips": decision_flips,
                            "baseline_mean_validation_metrics": metric_means(base_name),
                            "comparison_mean_validation_metrics": metric_means(name)})
    result = {"method": "paired_validation_case_comparison", "case_key": "bank + transaction_id",
              "checkpoint_count": len(roots), "shared_case_count": len(shared),
              "checkpoint_names": list(roots), "comparisons": comparisons,
              "privacy": "paired transaction details are local-only; aggregate file contains no identifiers or bank-level rows"}
    (output_dir / "comparison_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
