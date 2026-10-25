from __future__ import annotations

from distributed_federation.common.control import check_control

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import FederationConfig, REPO_ROOT
from .events import emit

GNN_DIR = REPO_ROOT / "src" / "gnn"
if str(GNN_DIR) not in sys.path:
    sys.path.insert(0, str(GNN_DIR))


@dataclass
class RuntimeData:
    model: Any
    static: Any
    streams: dict[str, Any]
    schema: dict[str, Any]
    schema_sha256: str


def _imports():
    import torch
    from causal_temporal_graphsage import (
        CausalTemporalGraphSAGE,
        build_bank_data,
        fit_shared_feature_encoders,
        set_seed,
    )

    return torch, CausalTemporalGraphSAGE, build_bank_data, fit_shared_feature_encoders, set_seed


def prepare_runtime(config: FederationConfig, bank: str) -> RuntimeData:
    torch, Model, build_bank_data, fit_encoders, set_seed = _imports()
    if config.feature_schema:
        return prepare_frozen_runtime(config, bank)
    set_seed(config.seed)
    node_encoder, edge_encoder = fit_encoders(config.dataset_dir, list(config.schema_banks))
    static, streams, node_columns, edge_columns = build_bank_data(
        config.dataset_dir, bank, node_encoder=node_encoder, edge_encoder=edge_encoder
    )
    model = Model(
        static.shape[1], streams["training"].edge_attr.shape[1],
        config.hidden_channels, config.dropout,
    ).cpu()
    schema = {
        "model": "CausalTemporalGraphSAGE",
        "schema_banks": list(config.schema_banks),
        "node_columns": list(node_columns),
        "edge_columns": list(edge_columns),
        "node_feature_count": int(static.shape[1]),
        "edge_feature_count": int(streams["training"].edge_attr.shape[1]),
        "hidden_channels": config.hidden_channels,
        "dropout": config.dropout,
        "state": {
            key: {"shape": list(value.shape), "dtype": str(value.dtype)}
            for key, value in model.state_dict().items()
        },
    }
    encoded = json.dumps(schema, sort_keys=True, separators=(",", ":")).encode()
    return RuntimeData(model, static, streams, schema, hashlib.sha256(encoded).hexdigest())


def serialize_state(state: dict[str, Any]) -> bytes:
    from safetensors.torch import save

    cpu_state = {key: value.detach().cpu().contiguous() for key, value in state.items()}
    return save(cpu_state)


def deserialize_state(payload: bytes) -> dict[str, Any]:
    from safetensors.torch import load

    return load(payload)


def validate_state(candidate: dict[str, Any], reference: dict[str, Any]) -> None:
    import torch

    if set(candidate) != set(reference):
        missing = sorted(set(reference) - set(candidate))
        extra = sorted(set(candidate) - set(reference))
        raise ValueError(f"State keys differ; missing={missing}, extra={extra}")
    for key, expected in reference.items():
        actual = candidate[key]
        if actual.shape != expected.shape or actual.dtype != expected.dtype:
            raise ValueError(
                f"Tensor {key} differs: got {tuple(actual.shape)}/{actual.dtype}, "
                f"expected {tuple(expected.shape)}/{expected.dtype}"
            )
        if actual.is_floating_point() and not torch.isfinite(actual).all():
            raise ValueError(f"Tensor {key} contains NaN or infinity")


def load_initial_checkpoint(model: Any, path: Path | None) -> bool:
    if path is None:
        return False
    if not path.is_file():
        raise FileNotFoundError(f"Initial checkpoint not found: {path}")
    import torch

    if path.suffix == ".safetensors":
        from safetensors.torch import load_file

        state = load_file(str(path), device="cpu")
    elif path.suffix in {".pt", ".pth"}:
        # The existing project checkpoint contains argparse/Path metadata, so
        # weights_only cannot read it. Only load checkpoints from this trusted repo.
        try:
            path.resolve().relative_to(REPO_ROOT.resolve())
        except ValueError as exc:
            raise ValueError("For safety, .pt/.pth checkpoints must be inside this repository") from exc
        bundle = torch.load(path, map_location="cpu", weights_only=False)
        state = bundle.get("state_dict", bundle) if isinstance(bundle, dict) else bundle
    else:
        raise ValueError("Initial checkpoint must end in .safetensors, .pt, or .pth")
    validate_state(state, model.state_dict())
    model.load_state_dict(state, strict=True)
    return True


def train_local(runtime: RuntimeData, config: FederationConfig, round_id: int, client_index: int) -> float:
    torch, _, _, _, set_seed = _imports()
    from causal_temporal_graphsage import epoch_sample_mask, train_temporal_epoch
    seed = config.seed + round_id * 100_000 + client_index
    set_seed(seed)
    model, static, train = runtime.model, runtime.static, runtime.streams['training']
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    generator = torch.Generator().manual_seed(seed)
    losses = []
    for epoch in range(config.local_epochs):
        check_control()
        mask = epoch_sample_mask(train.labels, config.negative_ratio, generator)
        loss, steps = train_temporal_epoch(model, static, train, optimizer, mask,
            config.batch_size, 2, 1.0, check_cancel=check_control)
        losses.append(loss)
        emit('epoch_completed', round_id, epoch=epoch+1, total_epochs=config.local_epochs,
             mean_train_loss=loss, optimizer_steps=steps)
    return sum(losses) / max(1, len(losses))


def fedavg(states: list[dict[str, Any]], weights: list[int]) -> dict[str, Any]:
    if not states or len(states) != len(weights) or any(weight <= 0 for weight in weights):
        raise ValueError("FedAvg requires states with matching positive sample weights")
    total = float(sum(weights))
    result: dict[str, Any] = {}
    for key in states[0]:
        reference = states[0][key]
        if reference.is_floating_point():
            accumulator = reference.to(dtype=reference.dtype) * (weights[0] / total)
            for state, weight in zip(states[1:], weights[1:]):
                accumulator = accumulator + state[key].to(dtype=reference.dtype) * (weight / total)
            if not accumulator.isfinite().all():
                raise ValueError(f"Aggregated tensor {key} is not finite")
            result[key] = accumulator
        else:
            if any(not state[key].equal(reference) for state in states[1:]):
                raise ValueError(f"Non-floating tensor {key} differs between clients")
            result[key] = reference.clone()
    return result


def save_state_and_manifest(
    state: dict[str, Any], output_dir: Path, round_id: int, manifest: dict[str, Any]
) -> tuple[Path, Path]:
    from .checkpoints import save_checkpoint, verify_checkpoint

    paths = save_checkpoint(serialize_state(state), output_dir, round_id, manifest)
    verify_checkpoint(output_dir, round_id)
    return paths


class FrozenEncoder:
    """Apply the shared demo preprocessing contract without reading other banks."""
    def __init__(self, specification):
        self.spec = specification
    def transform(self, frame):
        import numpy as np
        import pandas as pd
        blocks = []
        for column in self.spec['numeric']:
            values = pd.to_numeric(frame[column['name']], errors='raise').to_numpy(dtype=float)
            values = np.where(np.isnan(values), column['median'], values)
            blocks.append(((values-column['mean'])/column['scale']).reshape(-1,1))
        for column in self.spec['categorical']:
            values = frame[column['name']].fillna(column['fill']).to_numpy()
            blocks.append(np.column_stack([values==category for category in column['categories']]))
        result=np.concatenate(blocks, axis=1).astype(np.float32)
        if not np.isfinite(result).all():
            raise ValueError('Non-finite features after shared preprocessing')
        return result


def prepare_frozen_runtime(config, bank=None):
    torch, Model, build_bank_data, _, set_seed = _imports()
    contract = json.loads(config.feature_schema.read_text(encoding='utf-8'))
    if contract.get('format') != 1:
        raise ValueError('Unknown feature-schema format')
    set_seed(config.seed)
    nodes, edges = FrozenEncoder(contract['nodes']), FrozenEncoder(contract['edges'])
    static, streams = None, {}
    if bank is not None:
        static, streams, node_columns, edge_columns = build_bank_data(config.dataset_dir, bank,
            nodes, edges, splits=('training',))
        if node_columns != contract['node_columns'] or edge_columns != contract['edge_columns']:
            raise ValueError('Local approved feature columns differ from the shared schema')
    model = Model(contract['node_feature_count'], contract['edge_feature_count'], config.hidden_channels, config.dropout).cpu()
    schema = dict(model='CausalTemporalGraphSAGE', feature_contract=contract,
                  training_protocol=dict(rounds=config.rounds,local_epochs=config.local_epochs,batch_size=config.batch_size,
                      negative_ratio=config.negative_ratio,learning_rate=config.learning_rate,weight_decay=config.weight_decay,
                      seed=config.seed,clients=[dict(client_id=c.client_id,bank=c.bank) for c in config.clients]),
                  hidden_channels=config.hidden_channels, dropout=config.dropout,
                  state={key:dict(shape=list(value.shape),dtype=str(value.dtype)) for key,value in model.state_dict().items()})
    encoded=json.dumps(schema, sort_keys=True, separators=(',',':')).encode()
    return RuntimeData(model, static, streams, schema, hashlib.sha256(encoded).hexdigest())
