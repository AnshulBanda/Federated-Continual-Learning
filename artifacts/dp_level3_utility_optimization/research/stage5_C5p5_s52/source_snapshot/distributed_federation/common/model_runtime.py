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
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    from causal_temporal_graphsage import (
        CausalTemporalGraphSAGE,
        build_bank_data,
        fit_shared_feature_encoders,
        set_seed,
    )

    return torch, CausalTemporalGraphSAGE, build_bank_data, fit_shared_feature_encoders, set_seed


def implementation_sha256():
    """Bind the training/encoding implementation, not only parameter shapes."""
    files=("src/gnn/causal_temporal_graphsage.py", "src/gnn/adaptive_continual_federated.py",
        "src/gnn/continual_temporal_graphsage.py", "distributed_federation/common/model_runtime.py",
        "distributed_federation/privacy/mechanism.py", "distributed_federation/privacy/secagg.py",
        "distributed_federation/privacy/server_optimizer.py", "distributed_federation/privacy/subset.py")
    return hashlib.sha256(b"".join(name.encode()+b"\0"+(REPO_ROOT/name).read_bytes() for name in files)).hexdigest()


def prepare_runtime(config: FederationConfig, bank: str) -> RuntimeData:
    torch, Model, build_bank_data, fit_encoders, set_seed = _imports()
    if config.feature_schema:
        return prepare_frozen_runtime(config, bank)
    set_seed(config.seed)
    node_encoder, edge_encoder = fit_encoders(config.dataset_dir, list(config.schema_banks))
    static, streams, node_columns, edge_columns = build_bank_data(
        config.dataset_dir, bank, node_encoder=node_encoder, edge_encoder=edge_encoder, splits=("training",)
    )
    model = Model(
        static.shape[1], streams["training"].edge_attr.shape[1],
        config.hidden_channels, config.dropout,
    ).cpu()
    from dataclasses import asdict
    schema = {
        "training_protocol": dict(aggregation=config.aggregation,replay=config.replay,replay_size=config.replay_size,
            rng_policy=config.rng_policy,local_epochs=config.local_epochs,seed=config.seed,
            learning_rate=config.learning_rate,batch_size=config.batch_size,
            clients=[dict(client_id=c.client_id,bank=c.bank) for c in config.clients],
            privacy=asdict(config.privacy),server_optimizer=asdict(config.server_optimizer),private_subset=config.private_subset),
        "model": "CausalTemporalGraphSAGE",
        "implementation_sha256": implementation_sha256(),
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
        # No pickle execution: accept the fixed checkpoint outside the worktree
        # without requiring a duplicate. Only inert pathlib metadata is allowed.
        from pathlib import PosixPath
        with torch.serialization.safe_globals([Path, PosixPath]):
            bundle = torch.load(path, map_location="cpu", weights_only=True)
        state = bundle.get("state_dict", bundle) if isinstance(bundle, dict) else bundle
    else:
        raise ValueError("Initial checkpoint must end in .safetensors, .pt, or .pth")
    validate_state(state, model.state_dict())
    model.load_state_dict(state, strict=True)
    return True


def train_local(runtime: RuntimeData, config: FederationConfig, round_id: int, client_index: int) -> float:
    from adaptive_continual_federated import train_client, calendar_boundary
    from types import SimpleNamespace
    check_control()
    from distributed_federation.privacy.subset import configure_trainable
    configure_trainable(runtime.model,getattr(config,"private_subset","all"))
    cfg = SimpleNamespace(local_epochs=config.local_epochs, learning_rate=config.learning_rate,
        batch_size=config.batch_size, replay_size=config.replay_size, replay=config.replay,
        distill=0., rng_policy=config.rng_policy,
        weight_decay=getattr(config,"weight_decay",1e-4),negative_ratio=getattr(config,"negative_ratio",20))
    # Same local seed rule as Sia's simulator. Per-client RNG is necessary for
    # independent processes; global simulator RNG is kept as a separate reference.
    train_client(runtime.model, runtime.static, runtime.streams['training'],
        calendar_boundary(config.dataset_dir, config.clients[client_index].bank), cfg,
        config.seed + round_id*100 + client_index, check_cancel=check_control)
    check_control()
    return None  # No identifiable loss/replay statistics leave a bank.


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
    from dataclasses import asdict
    schema = dict(implementation_sha256=implementation_sha256(),model='CausalTemporalGraphSAGE', feature_contract=contract,
                  training_protocol=dict(aggregation=config.aggregation,rounds=config.rounds,local_epochs=config.local_epochs,batch_size=config.batch_size,
                      negative_ratio=config.negative_ratio,learning_rate=config.learning_rate,weight_decay=config.weight_decay,
                      replay=config.replay,replay_size=config.replay_size,rng_policy=config.rng_policy,
                      privacy=asdict(config.privacy),server_optimizer=asdict(config.server_optimizer),private_subset=config.private_subset,seed=config.seed,clients=[dict(client_id=c.client_id,bank=c.bank) for c in config.clients]),
                  hidden_channels=config.hidden_channels, dropout=config.dropout,
                  state={key:dict(shape=list(value.shape),dtype=str(value.dtype)) for key,value in model.state_dict().items()})
    encoded=json.dumps(schema, sort_keys=True, separators=(',',':')).encode()
    return RuntimeData(model, static, streams, schema, hashlib.sha256(encoded).hexdigest())
