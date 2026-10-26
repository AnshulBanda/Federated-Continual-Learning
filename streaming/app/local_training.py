"""Bank-local dataset checks, training jobs and explicit checkpoint selection."""
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from .locking import RuntimeLock
from .overview import BANKS, REPO

MAX_TRAINING_EPOCHS = 25
EARLY_STOPPING_PATIENCE = 5

def now():
    return datetime.now(timezone.utc).isoformat()

def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('x', encoding='utf-8') as out:
            json.dump(data, out, indent=2, allow_nan=False)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)

def read_json(path, fallback=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return fallback

def check_dataset(dataset, bank):
    import numpy as np
    import pandas as pd
    from src.gnn.causal_temporal_graphsage import FORBIDDEN
    manifest = read_json(dataset / 'configuration/model_feature_columns.json')
    if not isinstance(manifest, dict):
        raise ValueError('Missing configuration/model_feature_columns.json. Connect the prepared dataset root.')
    report, signatures, previous, transaction_ids = [], {}, None, set()
    for split in ('training', 'validation'):
        folder = dataset / split / bank
        frames = {}
        for name in ('node_features', 'node_map', 'edge_list', 'ground_truth'):
            path = folder / (name + '.csv.gz')
            if not path.is_file() or path.stat().st_size > 500_000_000:
                raise ValueError(f'{split}: missing or oversized {name}.csv.gz')
            signatures[str(path.relative_to(dataset))] = hashlib.sha256(path.read_bytes()).hexdigest()
            frames[name] = pd.read_csv(path)
        nodes, mapping, edges, truth = (frames[k] for k in ('node_features', 'node_map', 'edge_list', 'ground_truth'))
        required = ((nodes, ['node_id']), (mapping, ['node_id', 'account_id']), (edges, ['txn_id', 'src_node', 'dst_node', 'timestamp']), (truth, ['txn_id', 'y']))
        for frame, columns in required:
            if frame.empty or any(c not in frame for c in columns):
                raise ValueError(f'{split}: empty table or missing required columns {columns}')
            if frame[columns].isna().any().any():
                raise ValueError(f'{split}: missing identifiers, timestamps or labels')
            if frame[columns[0]].duplicated().any():
                raise ValueError(f'{split}: duplicate {columns[0]}')
        if mapping['account_id'].duplicated().any() or set(nodes.node_id) != set(mapping.node_id):
            raise ValueError(f'{split}: node map and features must match one-to-one')
        if not set(edges.src_node).union(edges.dst_node).issubset(set(mapping.node_id)):
            raise ValueError(f'{split}: transaction endpoint missing from node map')
        if set(edges.txn_id) != set(truth.txn_id):
            raise ValueError(f'{split}: transaction/label IDs do not match exactly')
        if transaction_ids.intersection(set(edges.txn_id)):
            raise ValueError('Transaction IDs overlap between training and validation')
        transaction_ids.update(edges.txn_id)
        if set(truth.y.unique()) != {0, 1}:
            raise ValueError(f'{split}: labels must contain both 0 and 1')
        times = pd.to_datetime(edges.timestamp, errors='raise', utc=True)
        if times.isna().any() or (previous is not None and times.min() <= previous):
            raise ValueError('Training must end strictly before validation begins')
        previous = times.max()
        missing = 0
        for frame, key in ((nodes, 'graph_node_safe_features'), (edges, 'graph_edge_safe_features')):
            columns = [c for c in manifest.get(key, []) if c not in FORBIDDEN]
            if not columns or any(c not in frame for c in columns):
                raise ValueError(f'{split}: approved model features are missing')
            missing += int(frame[columns].isna().sum().sum())
            numeric = frame[columns].select_dtypes(include='number')
            if np.isinf(numeric.to_numpy()).any():
                raise ValueError(f'{split}: infinite feature values')
            if frame[columns].isna().all().any():
                raise ValueError(f'{split}: a feature column is entirely empty')
        report.append(dict(split=split, transactions=len(edges), accounts=len(nodes), positives=int(truth.y.sum()), missing_features=missing, first=times.min().isoformat(), last=times.max().isoformat()))
    signatures['configuration/model_feature_columns.json'] = hashlib.sha256((dataset / 'configuration/model_feature_columns.json').read_bytes()).hexdigest()
    digest = hashlib.sha256(json.dumps(signatures, sort_keys=True).encode()).hexdigest()
    return dict(passed=True, splits=report, fingerprint=digest, checked_at=now(), note='Training and validation only. Missing feature values are imputed by the training-fitted encoder. No test files loaded.')

class LocalTraining:
    def __init__(self, root):
        self.root = Path(root) / 'local-training'
        self.root.mkdir(parents=True, exist_ok=True)
        self.mutex = threading.Lock()
        self.process = None
    def jobs(self):
        jobs = [read_json(p) for p in self.root.glob('*/job.json')]
        return sorted([j for j in jobs if isinstance(j, dict)], key=lambda j:j['started'], reverse=True)
    def status(self):
        jobs = self.jobs()
        for job in jobs:
            if job['status'] in ('Queued', 'Running'):
                try:
                    with RuntimeLock(self.root / 'training.lock'):
                        # Allow the newly launched child time to acquire its lock.
                        age = (datetime.now(timezone.utc) - datetime.fromisoformat(job['started'])).total_seconds()
                        if age > 15:
                            job.update(status='Interrupted', ended=now(), detail='Worker stopped before recording completion. Start a new run.')
                            write_json(self.root / job['id'] / 'job.json', job)
                except RuntimeError:
                    pass
            log = self.root / job['id'] / 'output.log'
            try:
                with log.open('rb') as stream:
                    stream.seek(max(0, log.stat().st_size - 12000))
                    job['log'] = stream.read().decode('utf-8', errors='replace')
            except OSError:
                job['log'] = ''
        return dict(jobs=jobs[:20], default_dataset=str(REPO / 'data/final_temporal_dataset'), dependencies={name:importlib.util.find_spec(name) is not None for name in ('torch','pandas','numpy','sklearn')})
    def start(self, data, bank):
        if bank not in BANKS:
            raise ValueError('Save your bank on Overview first.')
        kind = data.get('kind')
        if kind not in ('check', 'train'):
            raise ValueError('Choose check or train.')
        raw = data.get('dataset', '')
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError('Enter the prepared dataset root folder.')
        dataset = Path(raw.strip()).expanduser().resolve()
        if not dataset.is_dir():
            raise ValueError('Dataset folder does not exist on this laptop.')
        if 'epochs' in data:
            raise ValueError('Epochs are managed automatically. Refresh the dashboard before training.')
        epochs = MAX_TRAINING_EPOCHS
        with self.mutex:
            if self.process and self.process.poll() is None:
                raise ValueError('A local data check or training job is already running.')
            if any(j['status'] in ('Queued','Running') for j in self.status()['jobs']):
                raise ValueError('A local worker is still active. Wait for completion or cancel it.')
            try:
                with RuntimeLock(self.root / 'training.lock'):
                    pass
            except RuntimeError:
                raise ValueError('A training worker already owns this workspace.')
            missing = [m for m in ('torch','pandas','numpy','sklearn') if importlib.util.find_spec(m) is None]
            if missing:
                raise ValueError('Missing ML dependencies: '+', '.join(missing)+'. Install requirements.txt in the project environment.')
            if kind == 'train':
                checks = [j for j in self.jobs() if j['bank']==bank and j['dataset']==str(dataset) and j['kind']=='check' and j['status']=='Completed']
                if not checks:
                    raise ValueError('Run and pass Check data quality for this bank and folder first.')
            key = uuid.uuid4().hex
            folder = self.root / key
            job = dict(id=key, bank=bank, dataset=str(dataset), kind=kind, epochs=epochs, patience=EARLY_STOPPING_PATIENCE, epoch=0, status='Queued', started=now(), detail='Starting local worker')
            write_json(folder / 'job.json', job)
            try:
                with (folder / 'output.log').open('wb') as output:
                    self.process = subprocess.Popen([sys.executable, '-u', '-m', 'streaming.app.local_training', '--job', str(folder / 'job.json')], cwd=REPO, stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            except OSError:
                job.update(status='Failed', detail='Unable to start local worker', ended=now())
                write_json(folder / 'job.json', job)
                raise
            return job
    def cancel(self, key):
        with self.mutex:
            job = next((j for j in self.jobs() if j['id']==key), None)
            if not job or job['status'] not in ('Queued','Running'):
                raise ValueError('That job is not active.')
            write_json(self.root / key / 'cancel.json', {'requested':True})
            return {'requested':True}
    def activate(self, key, bank):
        with self.mutex:
            job = next((j for j in self.jobs() if j['id']==key and j['bank']==bank), None)
            if not job or job['kind']!='train' or job['status']!='Completed':
                raise ValueError('Select a completed training run for the saved bank.')
            checkpoint = self.root / key / (bank+'_causal_temporal_graphsage.pt')
            if not checkpoint.is_file() or hashlib.sha256(checkpoint.read_bytes()).hexdigest()!=job['sha256']:
                raise ValueError('Checkpoint is missing or changed. Train a new model.')
            model = dict(bank=bank, version='local-'+key[:12], sha256=job['sha256'], checkpoint=str(checkpoint), trained_at=job['ended'], selected_at=now(), validation=job['metrics']['validation'], job=key)
            write_json(self.root / ('active-'+bank+'.json'), model)
            return model
    def close(self):
        if self.process and self.process.poll() is None:
            for job in self.jobs():
                if job['status'] in ('Queued','Running'):
                    write_json(self.root / job['id'] / 'cancel.json', {'requested':True})
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=10)


def worker(path):
    job = read_json(path)
    folder = path.parent
    def update(**values):
        job.update(values)
        write_json(path, job)
    def cancelled():
        if (folder / 'cancel.json').exists():
            raise InterruptedError('Cancelled locally. Partial outputs are not selectable.')
    try:
        with RuntimeLock(folder.parent / 'training.lock'):
            update(status='Running', detail='Checking bank-local training and validation data')
            cancelled()
            report = check_dataset(Path(job['dataset']), job['bank'])
            update(quality=report, detail='Data quality checks passed')
            cancelled()
            if job['kind']=='train':
                import torch
                from src.gnn import causal_temporal_graphsage as model
                import argparse
                torch.set_num_threads(min(4, os.cpu_count() or 1))
                args = argparse.Namespace(dataset_dir=Path(job['dataset']), output_dir=folder, seed=42, validation_only=True, hidden_channels=128, dropout=0.25, learning_rate=0.001, weight_decay=0.0001, negative_ratio=20, full_training_weighted_bce=False, loss_pos_weight=1.0, event_batch_size=1024, tbptt_steps=2, epochs=job['epochs'], patience=job.get('patience', EARLY_STOPPING_PATIENCE), calibration='none', alert_k='10,25,50')
                def progress(epoch, loss, score):
                    cancelled()
                    update(epoch=epoch, loss=loss, validation_pr_auc=score, detail=f'Epoch {epoch} completed; monitoring validation PR-AUC for early stopping')
                update(detail='Training Temporal GraphSAGE locally on CPU')
                metrics = model.train_bank(args, job['bank'], torch.device('cpu'), progress=progress, check_cancel=cancelled)
                cancelled()
                if check_dataset(Path(job['dataset']), job['bank'])['fingerprint'] != report['fingerprint']:
                    raise ValueError('Dataset changed during training. This checkpoint cannot be selected; check data and run again.')
                write_json(folder / 'metrics.json', metrics)
                checkpoint = folder / (job['bank']+'_causal_temporal_graphsage.pt')
                update(stop_reason='Early stopping' if metrics.get('early_stopping_epoch') else 'Automatic epoch limit reached', metrics=metrics, sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest())
            update(status='Completed', ended=now(), detail='Data checks completed' if job['kind']=='check' else 'Local training and validation completed. Select this model to use it in the workspace.')
    except InterruptedError as exc:
        update(status='Cancelled', ended=now(), detail=str(exc))
    except Exception as exc:
        import traceback
        traceback.print_exc()
        update(status='Failed', ended=now(), detail=str(exc)[:1000])

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--job', type=Path, required=True)
    worker(parser.parse_args().job)
