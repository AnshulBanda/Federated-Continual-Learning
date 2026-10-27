"""Explicit privacy status of the implemented final model and transport."""

def privacy_status():
    return {
        'differential_privacy': False,
        'status': 'Not implemented in final training or transfers',
        'epsilon': None, 'delta': None, 'accounting': None,
        'checks': [
            {'name':'Transaction data', 'status':'Local', 'detail':'Bank workers train on their own transaction graph using a fixed synthetic-reference feature schema.'},
            {'name':'Transfer integrity', 'status':'Implemented', 'detail':'HMAC signatures, SHA-256 hashes, chunk verification and signed delivery receipts.'},
            {'name':'Differential privacy', 'status':'Not implemented', 'detail':'Final model updates have no DP noise mechanism or privacy accountant. Optimizer gradient clipping is not a DP guarantee.'},
            {'name':'Transport encryption', 'status':'Not configured by the app', 'detail':'Kafka clients do not configure TLS. Any private-network encryption is outside this application.'},
            {'name':'Secure aggregation', 'status':'Not implemented', 'detail':'The coordinator can read each client update.'},
            {'name':'Explanations', 'status':'Local only', 'detail':'Transaction explanations stay in the local workspace and are not included in automatic federation messages.'},
        ],
        'scope':'Current final ensemble, dashboard training, automatic federation and opaque file transfers.',
        'evidence':['src/gnn/adaptive_continual_federated.py','distributed_federation/common/model_runtime.py',
                    'distributed_federation/common/kafka_io.py','distributed_federation/common/protocol.py','streaming/app/transfers.py'],
    }
