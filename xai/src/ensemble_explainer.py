"""Exact feature attribution for the Sia three-member probability ensemble.

The ensemble score is mean(member sigmoid(logit)), followed by logit only for
SHAP's additive scale. This is not the mean member logit. Each member is scored
against its own pre-event account memory.
"""
from __future__ import annotations

import itertools
import math
from typing import Callable, Iterable

import numpy as np
import pandas as pd


def _sigmoid(logits: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(logits, -40.0, 40.0)))


def ensemble_logit_predictor(member_predictors: list[Callable[[pd.DataFrame], Iterable[float]]]):
    if len(member_predictors) < 2:
        raise ValueError("an ensemble explanation requires at least two members")

    def predict(frame: pd.DataFrame) -> np.ndarray:
        member_probabilities = [_sigmoid(np.asarray(fn(frame), dtype=float).reshape(-1)) for fn in member_predictors]
        if len({len(x) for x in member_probabilities}) != 1:
            raise ValueError("ensemble members returned different batch lengths")
        mean_probability = np.mean(np.stack(member_probabilities, axis=0), axis=0)
        clipped = np.clip(mean_probability, 1e-12, 1.0 - 1e-12)
        return np.log(clipped / (1.0 - clipped))

    return predict


def exact_interventional_shap(
    predict_logit: Callable[[pd.DataFrame], Iterable[float]],
    row: pd.Series,
    background: pd.DataFrame,
    features: list[str],
) -> dict[str, object]:
    """Exact Shapley values for the empirical interventional background game."""
    features = [name for name in features if name in row.index]
    if len(features) > 10:
        raise ValueError("exact feature SHAP is capped at 10 explained fields")
    if background.empty or not features:
        raise ValueError("background and explainable feature list must be non-empty")
    base_row = row.copy()
    backgrounds = background.reindex(columns=row.index).copy()
    n = len(features)
    coalition_values: dict[int, float] = {}
    for mask in range(1 << n):
        candidates = []
        for _, base in backgrounds.iterrows():
            hybrid = base.copy()
            for bit, feature in enumerate(features):
                if mask & (1 << bit):
                    hybrid[feature] = base_row[feature]
            candidates.append(hybrid)
        logits = np.asarray(predict_logit(pd.DataFrame(candidates, columns=row.index)), dtype=float).reshape(-1)
        if len(logits) != len(backgrounds):
            raise ValueError("predictor must return one logit per hybrid row")
        coalition_values[mask] = float(np.mean(logits))
    values = {}
    for bit, feature in enumerate(features):
        contribution = 0.0
        for mask in range(1 << n):
            if mask & (1 << bit):
                continue
            size = mask.bit_count()
            weight = math.factorial(size) * math.factorial(n - size - 1) / math.factorial(n)
            contribution += weight * (coalition_values[mask | (1 << bit)] - coalition_values[mask])
        values[feature] = float(contribution)
    target_logit = float(np.asarray(predict_logit(pd.DataFrame([base_row]))).reshape(-1)[0])
    residual = target_logit - coalition_values[(1 << n) - 1]
    return {"base_logit": coalition_values[0], "target_logit": target_logit,
            "additivity_residual": float(residual), "units": "logit(mean member probability)",
            "method": "exact_empirical_interventional_shap", "background_size": len(backgrounds),
            "features": [{"feature": key, "shap_logit": val, "value": base_row[key]} for key, val in values.items()]}


def member_probability_details(member_predictors: list[Callable[[pd.DataFrame], Iterable[float]]], row: pd.DataFrame) -> dict[str, object]:
    individual = [float(_sigmoid(np.asarray(fn(row)).reshape(-1))[0]) for fn in member_predictors]
    return {"member_probabilities": individual, "ensemble_probability": float(np.mean(individual)),
            "aggregation": "arithmetic mean of member probabilities"}
