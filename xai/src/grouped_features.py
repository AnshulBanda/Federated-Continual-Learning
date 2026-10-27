"""Exact empirical group SHAP with coherent transfer-field replacements."""
from __future__ import annotations

import math
import numpy as np
import pandas as pd

GROUPS = {
    "payment_method": ("payment_format",),
    "transfer_terms": ("amount", "Amount_Received", "currency", "Receiving_Currency"),
}
LABELS = {"payment_method": "Payment method", "transfer_terms": "Amount and currencies (joint)"}
METHOD = "exact_empirical_group_interventional_shap_v1"


def explain_groups(predictor, row, training, *, background_size=32, seed=42, background_ids=None):
    groups = {key: [name for name in names if name in row.index] for key, names in GROUPS.items()}
    groups = {key: names for key, names in groups.items() if names}
    if not groups or training.empty:
        raise ValueError("group SHAP requires features and training references")
    if background_ids is None:
        background = training.sample(n=min(background_size, len(training)), random_state=seed)
    else:
        indexed = training.set_index(training["txn_id"].astype(str), drop=False)
        background = indexed.loc[list(map(str, background_ids))]
    keys = list(groups)
    n = len(keys)
    values = {}
    for mask in range(1 << n):
        # Start from the target: account IDs, timestamp, and other metadata never change.
        hybrids = pd.DataFrame([row.copy() for _ in range(len(background))])
        for bit, key in enumerate(keys):
            if not mask & (1 << bit):
                for column in groups[key]:
                    hybrids[column] = background[column].to_numpy()
        logits = np.asarray(predictor(hybrids), dtype=float).reshape(-1)
        if len(logits) != len(background) or not np.isfinite(logits).all():
            raise ValueError("invalid group SHAP predictions")
        values[mask] = float(logits.mean())
    target = float(np.asarray(predictor(pd.DataFrame([row]))).reshape(-1)[0])
    features = []
    for bit, key in enumerate(keys):
        contribution = 0.0
        for mask in range(1 << n):
            if mask & (1 << bit):
                continue
            size = mask.bit_count()
            weight = math.factorial(size) * math.factorial(n-size-1) / math.factorial(n)
            contribution += weight * (values[mask | (1 << bit)] - values[mask])
        features.append({"feature": key, "label": LABELS[key], "columns": groups[key],
            "value": str(row[groups[key][0]]) if key == "payment_method" else " / ".join(f"{column}: {row[column]}" for column in groups[key]),
            "shap_logit": contribution,
            "ablation_logit_drop": target-values[((1 << n)-1) ^ (1 << bit)]})
    residual = target-values[0]-sum(item["shap_logit"] for item in features)
    probability = float(1/(1+np.exp(-np.clip(target, -40, 40))))
    if abs(residual) > 1e-5:
        raise ValueError("group SHAP failed additive reconstruction")
    return {"method": METHOD, "units": "raw_logit", "scope": "transaction_groups_given_fixed_account_memory",
        "base_logit": values[0], "target_logit": target, "target_probability": probability,
        "additivity_residual": residual, "features": features, "groups": groups,
        "seed": seed, "background_size": len(background),
        "background_txn_ids": background["txn_id"].astype(str).tolist(),
        "limitations": ["Joint transfer attribution cannot be split into separate amount and currency effects.",
            "Other dependencies between groups and reference sensitivity remain; this is not causal evidence."]}
