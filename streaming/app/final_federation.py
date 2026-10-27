"""Fail-closed deployment policy for the retained Level-3 private continuation.

The developer federation CLI remains available for explicit research configs.
Browser collaboration always uses this policy; the child independently checks it.
"""
import copy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from distributed_federation.common.config import REPO_ROOT
from distributed_federation.privacy.mechanism import Privacy
from distributed_federation.privacy.server_optimizer import ServerConfig

ROOT = REPO_ROOT
POLICY = 'level3_final_v1'
LABEL = 'Level-3 Distributed DP + Secure Aggregation'
BANK_ORDER = ('JPMorgan_Chase', 'Wells_Fargo', 'Key_Bank')
CLIENTS = {bank: f'bank-{index+1}' for index, bank in enumerate(BANK_ORDER)}
PRIVATE_DIMENSION = 65793
EVIDENCE = Path('artifacts/dp_level3_utility_optimization')
PRIVACY = dict(mode='distributed_dp', clip=1.25, multiplier=.15, delta=1e-6,
               expected_clients=3, min_noise_contributors=3, scale=2**24, entropy='production')
FIXED = dict(rounds=1, local_epochs=2, hidden_channels=128, dropout=.25,
             batch_size=1024, negative_ratio=20, learning_rate=.0003, weight_decay=.0001,
             seed=42, return_aggregate=True, aggregation='equal', rng_policy='per_client',
             replay='risk_context', replay_size=2000, private_subset='decoder', max_chunk_bytes=524288)
SERVER = dict(name='fedavg', learning_rate=1., beta1=.9, beta2=.99, epsilon=.001)


def _json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise ValueError(f'Approved Level-3 metadata is missing or invalid: {path.name}. Update the project on all laptops.') from exc


def _verified_file(path, expected_hash, label):
    try:
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ValueError(f'Approved {label} is missing; private collaboration is blocked.') from exc
    if actual != expected_hash:
        raise ValueError(f'Approved {label} hash differs; private collaboration is blocked.')
    return actual


def approved_template():
    """Resolve public assets from retained provenance, independently on each laptop."""
    reference_path = ROOT / EVIDENCE / 'FINALIST_CONFIG.json'
    manifest = _json(ROOT / EVIDENCE / 'SOURCE_MANIFEST.json')
    expected_reference = manifest['configuration_sha256'].get(str(EVIDENCE / 'FINALIST_CONFIG.json'))
    if not expected_reference:
        raise ValueError('Approved finalist config hash is missing.')
    _verified_file(reference_path, expected_reference, 'finalist configuration')
    reference = _json(reference_path)
    for key, expected in FIXED.items():
        if reference.get(key) != expected:
            raise ValueError(f'Approved finalist metadata does not match deployment policy: {key}')
    if reference.get('privacy') != PRIVACY or reference.get('server_optimizer') != SERVER:
        raise ValueError('Approved finalist privacy/server policy differs.')
    expected_clients = [dict(client_id=CLIENTS[b], bank=b) for b in BANK_ORDER]
    if reference.get('clients') != expected_clients or reference.get('schema_banks') != list(BANK_ORDER):
        raise ValueError('Approved finalist cohort/order differs.')
    # The repository-relative retained path is reproducible across laptops.
    warm_relative = Path(reference['initial_checkpoint'])
    schema_relative = Path(reference['feature_schema'])
    if warm_relative.is_absolute() or schema_relative.is_absolute() or '..' in warm_relative.parts or '..' in schema_relative.parts:
        raise ValueError('Approved model/schema paths must be repository-relative.')
    provenance = _json(ROOT / EVIDENCE / 'CHECKPOINT_PROVENANCE.json')
    starts = provenance.get('starting', [])
    expected_warm = reference.get('nonprivate_checkpoint_sha256')
    if sorted(row.get('seed') for row in starts) != [42, 52, 62] or not expected_warm or any(row.get('sha256') != expected_warm for row in starts):
        raise ValueError('Approved warm checkpoint provenance differs.')
    _verified_file(ROOT / warm_relative, expected_warm, 'warm checkpoint')
    historical = _json(ROOT / EVIDENCE / 'INITIAL_AUDIT.json')['historical_evidence_hashes']
    expected_schema = historical.get(str(schema_relative))
    if not expected_schema:
        raise ValueError('Approved feature-schema provenance is missing.')
    _verified_file(ROOT / schema_relative, expected_schema, 'feature schema')
    return copy.deepcopy(reference)


def build_config(profile, output_dir, topics):
    reference = approved_template()
    result = {**FIXED, 'privacy': dict(PRIVACY), 'server_optimizer': dict(SERVER),
              'clients': copy.deepcopy(reference['clients']), 'schema_banks': list(BANK_ORDER),
              'initial_checkpoint': reference['initial_checkpoint'], 'feature_schema': reference['feature_schema'],
              'operational_policy': POLICY, 'broker': profile['broker'], 'run_id': profile['run_id'],
              'dataset_dir': profile['dataset'], 'output_dir': str(output_dir),
              'round_timeout_seconds': profile['timeout'], 'topics': dict(topics)}
    return result


def validate_operational_config(raw, config):
    """Called before spawn AND in the runner, with a forced command-line guard."""
    required = set(FIXED) | {'privacy', 'server_optimizer', 'clients', 'schema_banks',
                             'initial_checkpoint', 'feature_schema', 'operational_policy'}
    if not required <= raw.keys() or raw.get('operational_policy') != POLICY:
        raise ValueError('Final private collaboration requires the complete Level-3 policy; no defaults or downgrade.')
    reference = approved_template()
    for key, expected in FIXED.items():
        if raw[key] != expected or getattr(config, key) != expected:
            raise ValueError(f'Final private collaboration cannot override {key}.')
        if isinstance(expected, int) and not isinstance(expected, bool) and isinstance(raw[key], bool):
            raise ValueError(f'Invalid final collaboration count: {key}')
    if config.privacy != Privacy(**PRIVACY) or config.server_optimizer != ServerConfig(**SERVER):
        raise ValueError('Final private collaboration requires approved distributed DP, production entropy and server policy.')
    if [asdict(c) for c in config.clients] != reference['clients'] or config.schema_banks != BANK_ORDER:
        raise ValueError('Final private collaboration requires the exact three-bank cohort and public seed order.')
    if config.initial_checkpoint != (ROOT / reference['initial_checkpoint']).resolve() or config.feature_schema != (ROOT / reference['feature_schema']).resolve():
        raise ValueError('Final private collaboration requires the approved warm checkpoint and feature schema.')
    from distributed_federation.common.model_runtime import prepare_frozen_runtime
    from distributed_federation.privacy.subset import extract
    # Construct from the public schema only; the coordinator reads no bank data.
    runtime = prepare_frozen_runtime(config)
    dimension = sum(v.numel() for v in extract(runtime.model.state_dict(), config.private_subset).values())
    if dimension != PRIVATE_DIMENSION:
        raise ValueError('Final private decoder dimension differs from 65,793.')
    return dimension


def public_privacy():
    return dict(mode=PRIVACY['mode'], secagg=True, required_cohort=3, multiplier=.15,
                epsilon=Privacy(**PRIVACY).accounting(1)['epsilon'], delta=1e-6, phase='idle')
