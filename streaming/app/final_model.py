"""One model contract for the dashboard's final ensemble, training and explanations."""
import hashlib
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SEEDS = (42, 52, 62)
MODEL_KIND = 'adaptive_probability_ensemble'
MEMBERS = 'artifacts/research_adaptive_fcl/warm_start/federated/context_harmonized'
FREEZE = 'artifacts/research_seed_ensemble/FREEZE.json'
METRICS = 'artifacts/research_seed_ensemble/exploratory_september/metrics.json'
SCHEMA = 'distributed_federation/feature_schema.json'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def reference_model(bank, repo=REPO):
    repo = Path(repo)
    freeze = json.loads((repo / FREEZE).read_text())
    members = []
    for seed in SEEDS:
        path = repo / MEMBERS / f'seed_{seed}/global_model.pt'
        expected = next(row['sha256'] for row in freeze['entries'] if row['seed'] == seed)
        if digest(path) != expected:
            raise ValueError(f'Seed {seed} checkpoint differs from the frozen ensemble.')
        members.append(dict(seed=seed, checkpoint=str(path), sha256=expected))
    signature = hashlib.sha256(json.dumps(members, sort_keys=True).encode()).hexdigest()
    row = next(row for row in freeze['per_bank'] if row['bank'] == bank)
    return dict(bank=bank, version='Final ensemble · 42 / 52 / 62', model_kind=MODEL_KIND,
                members=members, sha256=signature, reference=True, checkpoint=None,
                validation=row['validation'], threshold=freeze['thresholds'][bank],
                privacy=dict(differential_privacy=False, accounting=None))


def validate_selected(selected):
    if selected.get('model_kind') == MODEL_KIND:
        members = selected.get('members', [])
        if [m['seed'] for m in members] != list(SEEDS):
            raise ValueError('The final ensemble requires seeds 42, 52 and 62 in order.')
        for member in members:
            if digest(member['checkpoint']) != member['sha256']:
                raise ValueError('An ensemble checkpoint is missing or changed.')
        return
    if digest(selected['checkpoint']) != selected['sha256']:
        raise ValueError('Selected checkpoint changed.')


def frozen_encoders(repo=REPO):
    from distributed_federation.common.model_runtime import FrozenEncoder
    schema = json.loads((Path(repo) / SCHEMA).read_text())
    return FrozenEncoder(schema['nodes']), FrozenEncoder(schema['edges']), schema


def build_ensemble(schema, checkpoints=True):
    import torch
    from src.gnn.causal_temporal_graphsage import CausalTemporalGraphSAGE
    model = torch.nn.ModuleDict({str(seed): CausalTemporalGraphSAGE(
        schema['node_feature_count'], schema['edge_feature_count'], 128, .25) for seed in SEEDS})
    if checkpoints:
        selected = reference_model('Key_Bank')
        for member in selected['members']:
            saved = torch.load(member['checkpoint'], map_location='cpu', weights_only=True)
            model[str(member['seed'])].load_state_dict(saved['state_dict'], strict=True)
    return model


def load_runtime(selected, dataset, bank):
    """Load only training/validation. Shared encoders never fit on validation."""
    import torch
    from src.gnn import causal_temporal_graphsage as g
    validate_selected(selected)
    nodes, edges, schema = frozen_encoders()
    static, streams, ncols, ecols = g.build_bank_data(Path(dataset), bank, nodes, edges,
                                                   splits=('training', 'validation'))
    if ncols != schema['node_columns'] or ecols != schema['edge_columns']:
        raise ValueError('Dataset features do not match the final model contract.')
    if selected.get('model_kind') == MODEL_KIND:
        models = []
        for member in selected['members']:
            saved = torch.load(member['checkpoint'], map_location='cpu', weights_only=True)
            model = g.CausalTemporalGraphSAGE(static.shape[1], streams['training'].edge_attr.shape[1], 128, .25)
            model.load_state_dict(saved['state_dict'], strict=True)
            model.eval(); models.append(model)
    elif selected.get('model_kind') == 'federated_ensemble':
        from distributed_federation.common.model_runtime import deserialize_state
        from distributed_federation.common.checkpoints import verify_checkpoint
        checkpoint = Path(selected['checkpoint'])
        manifest = json.loads(checkpoint.with_suffix('.json').read_text())
        verify_checkpoint(checkpoint.parent, manifest['round_id'])
        if manifest['schema']['feature_contract'] != schema:
            raise ValueError('Shared checkpoint preprocessing contract differs.')
        ensemble = build_ensemble(schema, checkpoints=False)
        ensemble.load_state_dict(deserialize_state(checkpoint.read_bytes()), strict=True)
        models = list(ensemble.values())
        for model in models: model.eval()
    else:
        raise ValueError('Select the final ensemble or a new ensemble training run for scoring.')
    return models, static, streams, edges


def score_models(models, static, streams, check=lambda: None, progress=lambda _: None):
    import numpy as np
    import torch
    from src.gnn.causal_temporal_graphsage import score_stream
    members = []
    with torch.no_grad():
        for seed, model in zip(SEEDS, models):
            check(); progress(f'Scoring seed {seed}: reconstructing earlier account history')
            state = model.initial_state(static)
            _, _, state = score_stream(model, state, streams['training'], 1024, check_cancel=check)
            probabilities, labels, _ = score_stream(model, state, streams['validation'], 1024, check_cancel=check)
            members.append(probabilities)
    return np.mean(np.asarray(members, dtype=np.float64), axis=0), labels, members


def reference_evidence(repo=REPO):
    data = json.loads((Path(repo) / METRICS).read_text())
    return dict(macro_pr_auc=data['macro_testing_pr_auc'], validation_pr_auc=data['macro_validation_pr_auc'],
                members=3, split='September 2025', exploratory=True, per_bank=data['per_bank'],
                source=METRICS, differential_privacy=False)
