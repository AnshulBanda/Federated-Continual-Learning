"""Pinned four-round SINGLE-model Level-3 continuation; reference ensemble is separate."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
from distributed_federation.common.config import REPO_ROOT
from distributed_federation.privacy.mechanism import Privacy
from distributed_federation.privacy.server_optimizer import ServerConfig
ROOT=REPO_ROOT
POLICY='level3_single_decoder_r4e3_v3'
LABEL='Level-3 Distributed DP + Secure Aggregation'
BANK_ORDER=('Key_Bank','Wells_Fargo','JPMorgan_Chase')
CLIENTS={bank:f'bank-{i+1}' for i,bank in enumerate(BANK_ORDER)}
PRIVATE_DIMENSION=65793
EVIDENCE=Path('artifacts/dp_singlemodel_r4e3')
FREEZE=Path('artifacts/research_seed_ensemble/FREEZE.json')
FREEZE_SHA256='4fefbd0f1bee7575a146d4647f54000b02fdeafff6425ee6e5d58d18c0b30d79'
SCHEMA=Path('distributed_federation/feature_schema.json')
SCHEMA_SHA256='ae6fabba8641da6f835b6ea9eb946f6ec9dc2713f50e3bf82446740b0f07dd35'
OLD_EPSILON=127.36375184207253
FINALIST_SHA256='d1a6f929f05a7a756521f6bfa34c67aa1667411d99c071fb462206641b5006ee'
CALIBRATION_SHA256='5ed6da9bddaa3a5397a66c0bf1f29bb2a4cd8c0d20479105075515cb0dcad42b'
WARM=Path('artifacts/research_adaptive_fcl/warm_start/federated/context_harmonized/seed_42/global_model.pt')
WARM_SHA256='d650af6959d1da46888f30fb79bbfd888a6ec20743d14d447ea078dc351536f5'
PRIVACY={'mode': 'distributed_dp', 'clip': 0.875, 'multiplier': 0.3, 'delta': 1e-06, 'expected_clients': 3, 'min_noise_contributors': 3, 'scale': 16777216, 'entropy': 'production'}
FIXED={'training_protocol': 'adaptive_single', 'rounds': 4, 'local_epochs': 3, 'hidden_channels': 128, 'dropout': 0.25, 'batch_size': 1024, 'negative_ratio': 20, 'learning_rate': 0.0003, 'weight_decay': 0.0001, 'seed': 42, 'return_aggregate': True, 'aggregation': 'equal', 'rng_policy': 'per_client', 'replay': 'risk_context', 'replay_size': 2000, 'private_subset': 'decoder', 'max_chunk_bytes': 524288}
SERVER={'name': 'fedavg', 'learning_rate': 0.1, 'beta1': 0.9, 'beta2': 0.99, 'epsilon': 0.001}


def _json(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError) as exc:raise ValueError(f'Approved single-model metadata missing/invalid: {path.name}') from exc


def _verified_file(path,expected_hash,label):
    try:actual=hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:raise ValueError(f'Approved {label} is missing; private collaboration blocked.') from exc
    if actual!=expected_hash:raise ValueError(f'Approved {label} hash differs; private collaboration blocked.')
    return actual


def approved_template():
    _verified_file(ROOT/EVIDENCE/'FINALIST.json',FINALIST_SHA256,'single-model finalist')
    finalist=_json(ROOT/EVIDENCE/'FINALIST.json')
    if finalist['fixed']!=FIXED or finalist['privacy']!=PRIVACY or finalist['server_optimizer']!=SERVER or not finalist['single_model']:
        raise ValueError('Finalist metadata differs from single-model deployment policy')
    _verified_file(ROOT/EVIDENCE/'CALIBRATION.json',CALIBRATION_SHA256,'training-only calibration')
    _verified_file(ROOT/FREEZE,FREEZE_SHA256,'Sia warm provenance')
    entry=next((r for r in _json(ROOT/FREEZE)['entries'] if r['seed']==42),None)
    if not entry or entry['sha256']!=WARM_SHA256:raise ValueError('Seed-42 warm provenance differs')
    _verified_file(ROOT/WARM,WARM_SHA256,'seed-42 warm checkpoint')
    _verified_file(ROOT/SCHEMA,SCHEMA_SHA256,'feature schema')
    if Privacy(**PRIVACY).accounting(4)['epsilon']>OLD_EPSILON:raise ValueError('Four-release privacy floor violated')
    return dict(clients=[dict(client_id=CLIENTS[b],bank=b) for b in BANK_ORDER],schema_banks=list(BANK_ORDER),
                initial_checkpoint=str(WARM),warm_checkpoint_sha256=WARM_SHA256,feature_schema=str(SCHEMA))


def build_config(profile,output_dir,topics):
    return dict(FIXED,privacy=dict(PRIVACY),server_optimizer=dict(SERVER),**approved_template(),
                operational_policy=POLICY,broker=profile['broker'],run_id=profile['run_id'],dataset_dir=profile['dataset'],
                output_dir=str(output_dir),round_timeout_seconds=profile['timeout'],topics=dict(topics))


def validate_operational_config(raw,config):
    required=set(FIXED)|{'privacy','server_optimizer','clients','schema_banks','initial_checkpoint',
                        'warm_checkpoint_sha256','feature_schema','operational_policy'}
    if not required<=raw.keys() or raw.get('operational_policy')!=POLICY or 'ensemble_initialization' in raw:
        raise ValueError('Complete private SINGLE-model policy required; no defaults, ensemble or downgrade')
    reference=approved_template()
    for key,expected in FIXED.items():
        if raw[key]!=expected or getattr(config,key)!=expected or (isinstance(expected,int) and not isinstance(expected,bool) and isinstance(raw[key],bool)):
            raise ValueError(f'Final single-model collaboration cannot override {key}')
    if config.privacy!=Privacy(**PRIVACY) or config.server_optimizer!=ServerConfig(**SERVER):
        raise ValueError('Approved production DP and noisy-only server postprocessing required')
    if [asdict(c) for c in config.clients]!=reference['clients'] or config.schema_banks!=BANK_ORDER:
        raise ValueError('Complete canonical three-bank cohort required')
    if config.initial_checkpoint!=(ROOT/WARM).resolve() or config.feature_schema!=(ROOT/SCHEMA).resolve() or raw['warm_checkpoint_sha256']!=WARM_SHA256:
        raise ValueError('Approved seed-42 SINGLE-model warm checkpoint/schema required')
    from distributed_federation.common.model_runtime import prepare_frozen_runtime
    from distributed_federation.privacy.subset import extract
    import torch
    runtime=prepare_frozen_runtime(config)
    if isinstance(runtime.model,torch.nn.ModuleDict) or not hasattr(runtime.model,'decoder'):
        raise ValueError('Single CausalTemporalGraphSAGE required, never an ensemble')
    private=extract(runtime.model.state_dict(),'decoder')
    dimension=sum(v.numel() for v in private.values())
    if set(private)!=set('decoder.'+k for k in runtime.model.decoder.state_dict()) or dimension!=65793:
        raise ValueError('Actual single decoder schema/dimension differs')
    return dimension


def public_privacy():
    return dict(mode='distributed_dp',secagg=True,required_cohort=3,multiplier=.3,
                epsilon=Privacy(**PRIVACY).accounting(4)['epsilon'],delta=1e-6,phase='idle')
