"""Saved bank identity and honest Overview evidence."""
import json
import hashlib
import os
import threading
import uuid
from pathlib import Path
BANKS = {'Key_Bank': 'Key Bank', 'Wells_Fargo': 'Wells Fargo', 'JPMorgan_Chase': 'JPMorgan Chase'}
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
        from .final_model import reference_model, reference_evidence, validate_selected
        try:
            evidence = reference_evidence(self.repo)
            result['ensemble_evidence'] = evidence
            result['reference_model'] = dict(name='Adaptive probability ensemble', seeds=[42,52,62], checkpoint_available=True)
            if bank:
                result['active_model'] = reference_model(bank, self.repo)
                row = next(r for r in evidence['per_bank'] if r['bank'] == bank)
                result['evaluation'] = dict(row['testing'], period='September 2025 · exploratory', source='Saved final three-model ensemble')
        except (OSError, ValueError, KeyError, TypeError, StopIteration):
            warnings.append('Final ensemble artifacts are missing or invalid.')
        if bank:
            local = self.path.parent / 'local-training'
            active = None
            try:
                active = json.loads((local / ('active-'+bank+'.json')).read_text(encoding='utf-8'))
                validate_selected(active)
                if active.get('model_kind') not in ('adaptive_probability_ensemble', 'federated_ensemble'):
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
            if dbpath.is_file():
                try:
                    db=sqlite3.connect(dbpath.resolve().as_uri()+'?mode=ro',uri=True,timeout=2)
                    try:
                        rows=db.execute("SELECT e.time,r.actor,r.config FROM events e JOIN runs r ON e.run=r.id WHERE e.kind='training_completed' ORDER BY e.id DESC").fetchall()
                        # Client IDs changed across historical deployments; the
                        # saved run config is the authority for its bank identity.
                        stamp=next((time for time,actor,raw in rows if any(
                            c['bank']==bank and actor=='bank:'+c['client_id']
                            for c in json.loads(raw).get('clients',[]))),None)
                        if stamp and (not result['last_training'] or stamp>result['last_training']):
                            result['last_training']=stamp
                            result['last_training_source']='Federated local training phase'
                    finally:
                        db.close()
                except (sqlite3.Error,ValueError,KeyError,TypeError):
                    warnings.append('Federated training time is temporarily unavailable.')
            if (result.get('active_model') or {}).get('model_kind'):
                if not result['active_model'].get('reference'):
                    result['evaluation_notice']='The 90.68% reference result belongs to the original ensemble. Evaluate this selected version to see its own scores.'
        return result
