"""Keep reference-model claims separate from actual private collaboration."""

def privacy_status(collaboration=None):
    from .final_federation import public_privacy, LABEL
    private=collaboration['privacy'] if collaboration else public_privacy()
    model_scope=collaboration.get('model_scope','Three-member ensemble continuation') if collaboration else 'Three-member ensemble continuation'
    reference=dict(label='Reference Sia ensemble',differential_privacy=False,
        status='Non-private frozen three-member reference ensemble',
        exploratory_september_pr_auc=.9067783483397621,epsilon=None,delta=None,accounting=None)
    operational=dict(label='Operational federated collaboration',**private,
        differential_privacy=private['mode']=='distributed_dp',
        status=collaboration['privacy_label'] if collaboration else LABEL,
        accounting='encoded_share_postprocessing' if private['mode']=='distributed_dp' else None,
        accounting_scope=collaboration['epsilon_scope'] if collaboration else 'Configured per-run bound; reserved runs/releases compose',
        scope=model_scope+' conditional on nonprivate frozen checkpoints and fixed public calibration; local validation/XAI are not private releases' if private['mode']!='none' else 'Nonprivate reference/research history; no DP accounting guarantee')
    return {
        # Backwards-compatible top-level fields describe the reference ONLY.
        'differential_privacy': False,
        'status': reference['status'],
        'epsilon': None, 'delta': None, 'accounting': None,
        'scopes':dict(reference_ensemble=reference,operational_collaboration=operational),
        'checks': [
            {'name':'Transaction data', 'status':'Local', 'detail':'Bank workers train on their own transaction graph using a fixed synthetic-reference feature schema.'},
            {'name':'Transfer integrity', 'status':'Implemented', 'detail':'HMAC signatures, SHA-256 hashes, chunk verification and signed delivery receipts.'},
            {'name':'Reference Sia ensemble', 'status':'Non-private', 'detail':'Frozen three-member reference; 90.68% exploratory September PR-AUC. No DP claim applies to this result or ordinary local training.'},
            {'name':'Operational collaboration', 'status':operational['status'], 'detail':'Bank-level distributed DP with production noise before masking, three mandatory banks and conservative encoded-share accounting. All reserved releases compose.'},
            {'name':'Transport encryption', 'status':'Not configured by the app', 'detail':'Kafka clients do not configure TLS. Any private-network encryption is outside this application.'},
            {'name':'Secure aggregation', 'status':'Required in private collaboration', 'detail':'X25519/HKDF-SHA256/ChaCha20 pair masks; no individual client state or clean aggregate at the distributed-DP coordinator. Opaque manual file transfers have no DP guarantee.'},
            {'name':'Explanations', 'status':'Local only', 'detail':'Transaction explanations stay in the local workspace and are not included in automatic federation messages.'},
        ],
        'scope':'Top-level privacy fields describe the Reference Sia ensemble only. Operational collaboration has a separate explicit scope.',
        'evidence':['src/gnn/adaptive_continual_federated.py','distributed_federation/common/model_runtime.py',
                    'distributed_federation/common/kafka_io.py','distributed_federation/common/protocol.py','streaming/app/transfers.py'],
    }
