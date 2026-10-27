"""Constrained, model-agnostic counterfactual search for transaction features.

The scorer must be the production XAI prediction wrapper for a target row. It
must score before applying the target event to temporal memory. This module
does not mutate account history and deliberately changes only amount fields.
"""
from __future__ import annotations

from typing import Callable, Iterable

import numpy as np
import pandas as pd


def constrained_amount_counterfactuals(
    row: pd.Series | dict[str, object],
    training_rows: pd.DataFrame,
    predict_logits: Callable[[pd.DataFrame], Iterable[float] | np.ndarray],
    *,
    threshold: float,
    amount_fields: tuple[str, ...] = ("amount", "Amount_Received"),
    matching_fields: tuple[str, ...] = ("currency", "Receiving_Currency", "payment_format"),
    quantiles: tuple[float, ...] = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95),
    max_candidates: int = 64,
) -> dict[str, object]:
    """Search training-supported amount values while matching categorical context.

    Amount aliases are changed together to preserve the dataset's duplicate
    amount semantics. We never fabricate category values. A successful result
    means only that the model score crossed its supplied decision threshold.
    """
    original = pd.Series(row).copy()
    if not 0.0 < threshold < 1.0:
        raise ValueError("threshold must be a probability strictly between zero and one")
    fields = tuple(field for field in amount_fields if field in original.index)
    if not fields:
        raise ValueError(f"none of the amount fields are present: {amount_fields}")
    amount_field = fields[0]
    try:
        amount = float(original[amount_field])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{amount_field} must be numeric") from exc
    if not np.isfinite(amount) or amount < 0:
        raise ValueError("target amount must be finite and non-negative")

    eligible = training_rows.copy()
    notes = ["candidate amounts come from training rows only"]
    for field in matching_fields:
        if field in original.index and field in eligible.columns and pd.notna(original[field]):
            eligible = eligible[eligible[field].astype(str) == str(original[field])]
    if eligible.empty:
        # Fall back to the entire training distribution rather than inventing
        # values; the report records that exact categorical matching failed.
        eligible = training_rows
        notes.append("no exact categorical stratum; used the training amount distribution")

    candidate_values: set[float] = set()
    for field in fields:
        if field not in eligible.columns:
            continue
        vals = pd.to_numeric(eligible[field], errors="coerce").dropna()
        vals = vals[np.isfinite(vals) & (vals >= 0)]
        if len(vals):
            candidate_values.update(float(v) for v in vals.quantile(list(quantiles)).tolist())
            candidate_values.update(float(v) for v in vals.describe()[["min", "max"]].tolist())
    candidate_values.discard(amount)
    ordered = sorted(candidate_values, key=lambda value: (abs(value - amount), value))[:max_candidates]
    if not ordered:
        return {"status": "no_candidates", "threshold": threshold, "notes": notes}

    candidates = []
    for value in ordered:
        changed = original.copy()
        for field in fields:
            changed[field] = value
        candidates.append(changed)
    frame = pd.DataFrame(candidates, columns=original.index)
    base_logit = float(np.asarray(predict_logits(pd.DataFrame([original]))).reshape(-1)[0])
    logits = np.asarray(predict_logits(frame), dtype=float).reshape(-1)
    if len(logits) != len(ordered) or not np.isfinite(logits).all():
        raise ValueError("predict_logits must return one finite logit per candidate row")
    probs = 1.0 / (1.0 + np.exp(-np.clip(logits, -40.0, 40.0)))
    base_probability = float(1.0 / (1.0 + np.exp(-np.clip(base_logit, -40.0, 40.0))))
    original_flag = base_probability >= threshold
    # Keep only threshold-flipping candidates; smallest absolute amount change wins.
    selected = []
    for value, probability in zip(ordered, probs):
        if (bool(probability >= threshold) != original_flag):
            selected.append({
                "changed_features": {field: float(value) for field in fields},
                "original_probability": base_probability,
                "counterfactual_probability": float(probability),
                "score_change": float(probability - base_probability),
                "valid": True,
                "constraint_notes": notes + ["matched known categorical context", "amount aliases changed together"],
                "amount_change_absolute": abs(float(value) - amount),
            })
    selected.sort(key=lambda item: (item["amount_change_absolute"], abs(item["score_change"])))
    return {
        "method": "training_supported_constrained_amount_search",
        "status": "found" if selected else "no_threshold_flip_found",
        "threshold": float(threshold),
        "original_class": "fraud" if original_flag else "non_fraud",
        "original_probability": base_probability,
        "candidates_evaluated": len(ordered),
        "counterfactuals": selected[:5],
        "interpretation": "Model sensitivity only; not advice to evade controls or evidence of real-world intent.",
        "limitations": ["only amount fields were varied", "account memory and event history were held fixed", "training-supported values do not guarantee real-world plausibility"],
    }
