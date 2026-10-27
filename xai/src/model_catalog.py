"""Catalog predictions from one saved global model with its saved cutoff."""
from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, roc_auc_score


def model_catalog_rows(bank: str, transaction_ids: list[str], timestamps: list[str],
                       labels: np.ndarray, probabilities: np.ndarray, *, threshold: float) -> list[dict[str, Any]]:
    scores = np.asarray(probabilities, dtype=float).reshape(-1)
    truth = np.asarray(labels).reshape(-1)
    if not len(scores) or not (len(scores) == len(truth) == len(transaction_ids) == len(timestamps)):
        raise ValueError("saved predictions and validation transaction rows do not align")
    if len(set(map(str, transaction_ids))) != len(transaction_ids):
        raise ValueError("validation transaction IDs must be unique within a bank")
    if not np.isfinite(scores).all() or np.any((scores < 0) | (scores > 1)):
        raise ValueError("saved probabilities must be finite values in [0, 1]")
    if not np.isin(truth, [0, 1]).all() or not np.isfinite(threshold) or not 0 < threshold < 1:
        raise ValueError("invalid ground-truth labels or saved model threshold")
    rows = []
    for txn_id, timestamp, label, probability in zip(transaction_ids, timestamps, truth, scores):
        flagged, actual = bool(probability >= threshold), bool(label == 1)
        rows.append({"bank": bank, "transaction_id": str(txn_id), "timestamp": str(timestamp),
                     "split": "validation", "label": "fraud" if actual else "not_fraud", "label_value": int(label),
                     "probability": float(probability), "threshold": float(threshold), "flagged": flagged,
                     "status": "detected_fraud" if actual and flagged else (
                         "missed_fraud" if actual else ("false_alarm" if flagged else "not_flagged"))})
    return rows


def verify_saved_metrics(labels: np.ndarray, probabilities: np.ndarray, threshold: float,
                         expected: dict[str, float]) -> dict[str, Any]:
    predicted = np.asarray(probabilities) >= threshold
    computed = {"pr_auc": float(average_precision_score(labels, probabilities)),
                "roc_auc": float(roc_auc_score(labels, probabilities)),
                "precision": float(precision_score(labels, predicted, zero_division=0)),
                "recall": float(recall_score(labels, predicted, zero_division=0)),
                "f1": float(f1_score(labels, predicted, zero_division=0))}
    errors = {key: abs(computed[key] - float(value)) for key, value in expected.items() if key in computed}
    if not errors or any(not np.isfinite(value) or value > 1e-10 for value in errors.values()):
        raise ValueError(f"saved global-model validation metrics do not reproduce: {errors}")
    return {"passed": True, "metric_absolute_errors": errors, "metrics": computed}


def filter_catalog(rows: list[dict[str, Any]], view: str, query: str = "") -> list[dict[str, Any]]:
    if view not in {"all", "flagged", "known_fraud", "missed_fraud"}:
        raise ValueError("unsupported transaction view")
    query = query.casefold().strip()
    return [row for row in rows if (view != "flagged" or row["flagged"])
            and (view != "known_fraud" or row["label_value"] == 1)
            and (view != "missed_fraud" or row["status"] == "missed_fraud")
            and (not query or query in row["transaction_id"].casefold())]
