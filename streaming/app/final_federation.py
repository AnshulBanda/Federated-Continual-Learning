"""Fail-closed adaptive ensemble deployment, conditional on nonprivate warm models.

Plaintext temporal harmonization remains an explicit research path. The private
ensemble uses Sia's adaptive local ensemble training but replaces plaintext
temporal harmonization with secure equal aggregation because SecAgg hides
individual client directions.
"""
import copy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from distributed_federation.common.config import REPO_ROOT
from distributed_federation.privacy.mechanism import Privacy
from distributed_federation.privacy.server_optimizer import ServerConfig

ROOT=REPO_ROOT
POLICY='level3_adaptive_ensemble_v2'
LABEL='Level-3 Distributed DP + Secure Aggregation'
BANK_ORDER=('Key_Bank','Wells_Fargo','JPMorgan_Chase')
CLIENTS={bank:f'bank-{i+1}' for i,bank in enumerate(BANK_ORDER)}
PRIVATE_DIMENSION=197379
EVIDENCE=Path('artifacts/dp_level3_ensemble')
CALIBRATION_SHA256='e404eb99a4d7f1883a5a3e374b25bb21f0af0b293bbbee9eaa5a006976447eb2'
FREEZE=Path('artifacts/research_seed_ensemble/FREEZE.json')
FREEZE_SHA256='4fefbd0f1bee7575a146d4647f54000b02fdeafff6425ee6e5d58d18c0b30d79'
SCHEMA=Path('distributed_federation/feature_schema.json')
SCHEMA_SHA256='ae6fabba8641da6f835b6ea9eb946f6ec9dc2713f50e3bf82446740b0f07dd35'
MEMBERS=Path('artifacts/research_adaptive_fcl/warm_start/federated/context_harmonized')
MEMBER_HASHES={42:'d650af6959d1da46888f30fb79bbfd888a6ec20743d14d447ea078dc351536f5',
 52:'98b6c782a27013e4b1917669b2a5ae48d3a7e44ce6a9aa0149aef446473ab0e2',
 62:'4cd0854f6740f99a9f9ef7f1ba3360c06b5178846394feb73033da718ac715fe'}
PRIVACY=dict(mode='distributed_dp',clip=6.5,multiplier=.30,delta=1e-6,
             expected_clients=3,min_noise_contributors=3,scale=2**24,entropy='production')
FIXED=dict(training_protocol='adaptive_ensemble',rounds=4,local_epochs=3,hidden_channels=128,dropout=.25,
    batch_size=1024,negative_ratio=20,learning_rate=.001,weight_decay=.0001,seed=42,
    return_aggregate=True,aggregation='equal',rng_policy='per_client',replay='risk_context',
    replay_size=2000,private_subset='ensemble_decoder',max_chunk_bytes=524288)
SERVER=dict(name='fedavg',learning_rate=1.,beta1=.9,beta2=.99,epsilon=.001)
OLD_EPSILON=127.36375184207253


def _json(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError) as exc:
        raise ValueError(f'Approved ensemble metadata is missing or invalid: {path.name}') from exc


def _verified_file(path,expected_hash,label):
    try:actual=hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:raise ValueError(f'Approved {label} is missing; private collaboration is blocked.') from exc
    if actual!=expected_hash:raise ValueError(f'Approved {label} hash differs; private collaboration is blocked.')
    return actual


def approved_template():
    _verified_file(ROOT/EVIDENCE/'CALIBRATION.json',CALIBRATION_SHA256,'ensemble calibration')
    calibration=_json(ROOT/EVIDENCE/'CALIBRATION.json')
    if calibration['clip']!=PRIVACY['clip'] or calibration['dimension']!=PRIVATE_DIMENSION or calibration['training']!=FIXED:
        raise ValueError('Approved ensemble calibration differs from deployment policy.')
    _verified_file(ROOT/FREEZE,FREEZE_SHA256,'ensemble provenance')
    entries=_json(ROOT/FREEZE)['entries']
    members=[]
    for seed,expected in MEMBER_HASHES.items():
        if next((r['sha256'] for r in entries if r['seed']==seed),None)!=expected:
            raise ValueError('Approved ensemble member provenance differs.')
        path=MEMBERS/f'seed_{seed}/global_model.pt'
        _verified_file(ROOT/path,expected,f'warm ensemble seed-{seed} checkpoint')
        members.append(dict(seed=seed,checkpoint=str(path),sha256=expected))
    _verified_file(ROOT/SCHEMA,SCHEMA_SHA256,'feature schema')
    if Privacy(**PRIVACY).accounting(FIXED['rounds'])['epsilon']>OLD_EPSILON:
        raise ValueError('Ensemble privacy is weaker than the previous per-run budget.')
    return dict(clients=[dict(client_id=CLIENTS[b],bank=b) for b in BANK_ORDER],
        schema_banks=list(BANK_ORDER),initial_checkpoint=None,feature_schema=str(SCHEMA),
        ensemble_initialization=members)


def build_config(profile,output_dir,topics):
    return dict(FIXED,privacy=dict(PRIVACY),server_optimizer=dict(SERVER),**approved_template(),
        operational_policy=POLICY,broker=profile['broker'],run_id=profile['run_id'],
        dataset_dir=profile['dataset'],output_dir=str(output_dir),round_timeout_seconds=profile['timeout'],topics=dict(topics))


def validate_operational_config(raw,config):
    required=set(FIXED)|{'privacy','server_optimizer','clients','schema_banks','initial_checkpoint',
                         'feature_schema','ensemble_initialization','operational_policy'}
    if not required<=raw.keys() or raw.get('operational_policy')!=POLICY:
        raise ValueError('Final private collaboration requires the complete ensemble policy; no defaults or downgrade.')
    reference=approved_template()
    for key,expected in FIXED.items():
        if raw[key]!=expected or getattr(config,key)!=expected or (isinstance(expected,int) and not isinstance(expected,bool) and isinstance(raw[key],bool)):
            raise ValueError(f'Final private collaboration cannot override {key}.')
    if config.privacy!=Privacy(**PRIVACY) or config.server_optimizer!=ServerConfig(**SERVER):
        raise ValueError('Final ensemble requires calibrated distributed DP and production entropy.')
    if [asdict(c) for c in config.clients]!=reference['clients'] or config.schema_banks!=BANK_ORDER:
        raise ValueError('Final ensemble requires the exact three-bank cohort and public RNG order.')
    if config.initial_checkpoint is not None or config.feature_schema!=(ROOT/SCHEMA).resolve() or raw['ensemble_initialization']!=reference['ensemble_initialization']:
        raise ValueError('Final ensemble requires all three approved warm checkpoints and schema.')
    from distributed_federation.common.model_runtime import prepare_frozen_runtime
    from distributed_federation.privacy.subset import extract
    runtime=prepare_frozen_runtime(config)
    state=runtime.model.state_dict();private=extract(state,'ensemble_decoder')
    per_member={str(seed):sum(v.numel() for k,v in private.items() if k.startswith(str(seed)+'.')) for seed in MEMBER_HASHES}
    if list(runtime.model.keys())!=['42','52','62'] or per_member!={'42':65793,'52':65793,'62':65793}:
        raise ValueError('Actual ensemble member/decoder dimensions differ from approved architecture.')
    # Count actual tensors rather than accepting 3*65793 arithmetic alone.
    dimension=sum(t.numel() for t in private.values())
    if dimension!=PRIVATE_DIMENSION:raise ValueError('Actual private ensemble dimension differs.')
    return dimension


def public_privacy():
    return dict(mode='distributed_dp',secagg=True,required_cohort=3,multiplier=PRIVACY['multiplier'],
                epsilon=Privacy(**PRIVACY).accounting(FIXED['rounds'])['epsilon'],delta=1e-6,phase='idle')
