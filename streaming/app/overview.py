"""Saved bank identity and honest Overview evidence."""
import json
import hashlib
import os
import threading
import uuid
from pathlib import Path
BANKS = {'Key_Bank': 'Bank A', 'Wells_Fargo': 'Bank B', 'JPMorgan_Chase': 'Bank C'}
REPO = Path(__file__).resolve().parents[2]
class Overview:
    def __init__(self, root, repo=REPO):
        self.path = Path(root) / 'bank.json'
        self.repo = Path(repo)
        self.lock = threading.Lock()
    def save(self, data):
        if set(data) != {'bank'} or not isinstance(data['bank'], str) or data['bank'] not in BANKS:
            raise ValueError('Choose one of the three project banks.')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock:
            temp = self.path.with_name(uuid.uuid4().hex + '.tmp')
            try:
                with temp.open('x', encoding='utf-8') as out:
                    json.dump(data, out)
                    out.flush()
                    os.fsync(out.fileno())
                os.replace(temp, self.path)
            finally:
                temp.unlink(missing_ok=True)
        return self.load()
    def load(self):
        bank = None
        warnings = []
        try:
            bank = json.loads(self.path.read_text(encoding='utf-8'))['bank']
            if not isinstance(bank, str) or bank not in BANKS:
                raise ValueError()
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError, TypeError):
            bank = None
            warnings.append('Saved bank is unreadable. Choose and save your bank again.')
        result = dict(bank=bank, banks=BANKS, active_model=None, last_training=None,
                      reference_model=None, evaluation=None, warnings=warnings)
        folder = self.repo / 'artifacts/final_evaluation/corrected_fedavg/seed_42'
        try:
            metrics = json.loads((folder / 'metrics.json').read_text(encoding='utf-8'))
            result['reference_model'] = dict(name='FedAvg + continual replay', seed=42,
                round=metrics['best_round'], checkpoint_available=(folder / 'global_model.pt').is_file())
            if bank:
                row = next(r for r in metrics['per_bank'] if r['bank'] == bank)
                values = {k: row['testing'][k] for k in ('pr_auc', 'precision', 'recall')}
                if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1 for v in values.values()):
                    raise ValueError()
                result['evaluation'] = dict(values, period='September 2025 test', source='Saved frozen evaluation, seed 42')
        except (OSError, ValueError, KeyError, TypeError, StopIteration):
            result['reference_model'] = None
            result['evaluation'] = None
            warnings.append('Saved evaluation artifacts are missing or invalid.')
        if bank:
            local = self.path.parent / 'local-training'
            active = None
            try:
                active = json.loads((local / ('active-'+bank+'.json')).read_text(encoding='utf-8'))
                checkpoint = Path(active['checkpoint'])
                if not checkpoint.is_file() or hashlib.sha256(checkpoint.read_bytes()).hexdigest()!=active['sha256']:
                    raise ValueError()
                result['active_model'] = active
            except FileNotFoundError:
                pass
            except (OSError, ValueError, KeyError, TypeError):
                warnings.append('Selected local checkpoint is unavailable. Select a completed model again.')
            runs = []
            for path in local.glob('*/job.json'):
                try:
                    run = json.loads(path.read_text(encoding='utf-8'))
                    if run['bank']==bank and run['kind']=='train' and run['status']=='Completed':
                        runs.append(run)
                except (OSError, ValueError, KeyError, TypeError):
                    continue
            if runs:
                latest = max(runs, key=lambda r:r['ended'])
                result['last_training'] = latest['ended']
                result['latest_local_evaluation'] = dict(latest['metrics']['validation'], period='Local validation split', source='Latest completed local training, '+latest['id'][:12])
        if bank:
            import sqlite3
            dbpath = self.path.parent / 'collaboration/state.sqlite3'
            client_id = {'Key_Bank':'bank-1','Wells_Fargo':'bank-2','JPMorgan_Chase':'bank-3'}[bank]
            if dbpath.is_file():
                try:
                    db=sqlite3.connect(dbpath.resolve().as_uri()+'?mode=ro',uri=True,timeout=2)
                    try:
                        row=db.execute("SELECT e.time FROM events e JOIN runs r ON e.run=r.id WHERE r.actor=? AND e.kind='training_completed' ORDER BY e.id DESC LIMIT 1",('bank:'+client_id,)).fetchone()
                        if row and (not result['last_training'] or row[0]>result['last_training']):
                            result['last_training']=row[0]
                            result['last_training_source']='Federated local training phase'
                    finally:
                        db.close()
                except sqlite3.Error:
                    warnings.append('Federated training time is temporarily unavailable.')
            if (result.get('active_model') or {}).get('model_kind'):
                result['evaluation_notice']='Displayed scores belong to the most recent standalone local model. The selected shared model has not been evaluated by this dashboard.'
        return result
