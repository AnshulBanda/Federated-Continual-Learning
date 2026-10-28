"""Read-only dataset labels for the investigator's completed-replay selector.

Labels remain separate from replay scoring and are never added to its feed or
persisted model/provenance. Decisions use only the saved score and cutoff.
"""
import csv
import gzip
from pathlib import Path
from .local_training import check_dataset


def replay_cases(monitoring, replay_id, bank):
    job = next((j for j in monitoring.status(bank)['jobs']
                if j['id'] == replay_id and j['status'] == 'Completed'), None)
    if not job:
        raise ValueError('Choose a completed replay for this bank.')
    data = monitoring.rows(replay_id, bank)
    if (data.get('bank') != bank or data.get('model') != job.get('model')
            or data.get('threshold') != job.get('threshold')):
        raise ValueError('Saved replay identity changed. Score a new replay.')
    dataset = Path(job['dataset'])
    before = check_dataset(dataset, bank)['fingerprint']
    if before != job.get('dataset_fingerprint'):
        raise ValueError('Replay data changed. Score a new replay before browsing dataset labels.')
    labels = {}
    with gzip.open(dataset/'validation'/bank/'ground_truth.csv.gz', 'rt', newline='') as source:
        for row in csv.DictReader(source):
            txn, value = row['txn_id'], row['y']
            if txn in labels or value not in ('0', '1'):
                raise ValueError('Dataset labels are missing, invalid or ambiguous.')
            labels[txn] = 'fraud' if value == '1' else 'not_fraud'
    if set(labels) != {str(row['txn_id']) for row in data['rows']}:
        raise ValueError('Dataset labels do not match this completed replay.')
    if check_dataset(dataset, bank)['fingerprint'] != before:
        raise ValueError('Dataset changed while loading labels. Try a new replay.')
    return dict(data, rows=[dict(row, evaluation_label=labels[str(row['txn_id'])]) for row in data['rows']],
                label_source='Independent validation dataset labels; not used to determine model flags.')
