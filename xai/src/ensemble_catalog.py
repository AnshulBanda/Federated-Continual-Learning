"""Validation catalog and decision views for the three-seed Sia ensemble."""
from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.metrics import f1_score


def choose_validation_threshold(labels: np.ndarray, probabilities: np.ndarray) -> float:
    """Use the same 501-quantile, maximum-F1 rule as the Sia training code."""
    labels = np.asarray(labels, dtype=np.int8).reshape(-1)
    probabilities = np.asarray(probabilities, dtype=np.float64).reshape(-1)
    if not len(labels) or len(labels) != len(probabilities):
        raise ValueError("labels and probabilities must have the same non-zero length")
    if not np.isfinite(probabilities).all() or np.any((probabilities < 0) | (probabilities > 1)):
        raise ValueError("probabilities must be finite values in [0, 1]")
    candidates = np.unique(np.quantile(probabilities, np.linspace(0, 1, 501)))
    scores = [f1_score(labels, probabilities >= value, zero_division=0) for value in candidates]
    return float(candidates[int(np.argmax(scores))])


def catalog_rows(
    bank: str,
    transaction_ids: list[str],
    timestamps: list[str],
    labels: np.ndarray,
    member_probabilities: list[np.ndarray],
) -> tuple[list[dict[str, Any]], float]:
    """Build checked ensemble rows while requiring exact transaction alignment."""
    labels = np.asarray(labels, dtype=np.int8).reshape(-1)
    ids = [str(value) for value in transaction_ids]
    times = [str(value) for value in timestamps]
    if len(ids) != len(labels) or len(times) != len(labels):
        raise ValueError(f"{bank}: transaction metadata and labels have different lengths")
    if len(member_probabilities) != 3:
        raise ValueError("the primary dashboard requires exactly three Sia seed predictions")
    members = [np.asarray(values, dtype=np.float64).reshape(-1) for values in member_probabilities]
    if any(len(values) != len(labels) for values in members):
        raise ValueError(f"{bank}: a seed prediction array does not align with validation rows")
    ensemble = np.mean(np.stack(members, axis=0), axis=0)
    threshold = choose_validation_threshold(labels, ensemble)
    predicted = ensemble >= threshold
    rows = []
    for index, (txn_id, timestamp, label, score, flag) in enumerate(
        zip(ids, times, labels, ensemble, predicted)
    ):
        actual = bool(label == 1)
        is_flagged = bool(flag)
        rows.append({
            "bank": bank,
            "transaction_id": txn_id,
            "timestamp": timestamp,
            "split": "validation",
            "label": "fraud" if actual else "not_fraud",
            "label_value": int(label),
            "member_probabilities": [float(values[index]) for values in members],
            "probability": float(score),
            "threshold": threshold,
            "flagged": is_flagged,
            "status": "detected_fraud" if actual and is_flagged else (
                "missed_fraud" if actual else ("false_alarm" if is_flagged else "not_flagged")
            ),
        })
    return rows, threshold


def filter_catalog(rows: list[dict[str, Any]], view: str, query: str = "") -> list[dict[str, Any]]:
    """Apply the user-visible transaction view filters."""
    if view not in {"all", "flagged", "known_fraud", "missed_fraud"}:
        raise ValueError(f"unsupported transaction view: {view}")
    needle = query.casefold().strip()
    result = []
    for row in rows:
        if view == "flagged" and not row["flagged"]:
            continue
        if view == "known_fraud" and row["label_value"] != 1:
            continue
        if view == "missed_fraud" and row["status"] != "missed_fraud":
            continue
        if needle and needle not in row["transaction_id"].casefold():
            continue
        result.append(row)
    return result
