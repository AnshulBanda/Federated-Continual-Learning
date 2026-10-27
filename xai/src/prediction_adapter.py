"""Small source-level interface around the preserved temporal XAI engine.

The adapter scores the target event against its pre-event account memory. The
underlying cached engine is imported by ``xai.run_updated``; no second model or
independently fitted preprocessor is introduced here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class TargetPredictionContext:
    adapter: Any
    state: Any
    anchor: Any
    window: Any
    frame: pd.DataFrame
    index: int
    split: str

    def predict_logits(self, rows: pd.DataFrame):
        """Score altered target rows without applying target memory updates."""
        return self.adapter.predictor(self.state, self.split, self.index)(rows)


def load_target_context(
    temporal_module: Any,
    *,
    dataset: Path,
    checkpoint: Path,
    bank: str,
    preprocessing: Path,
    reference_predictions: Path,
    split: str,
    transaction_id: str,
    window_batches: int = 8,
) -> TargetPredictionContext:
    """Load the saved model pipeline and construct a causal pre-event context."""
    adapter = temporal_module.TemporalAdapter(
        dataset, checkpoint, bank, "federated", preprocessing, reference_predictions
    )
    index = int(adapter.index(split, str(transaction_id)))
    state, anchor, window = adapter.context(split, index, window_batches)
    frame = adapter.frames[split].iloc[[index]].copy()
    return TargetPredictionContext(adapter, state, anchor, window, frame, index, split)
