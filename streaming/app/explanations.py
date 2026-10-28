"""Bank-local investigator explanations bound to the exact completed replay."""
import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from .local_training import read_json, write_json, now, check_dataset
from .final_model import REPO, digest
from .investigator import cache_inputs, hash_json, model_provenance, validate_report, explain_replay


class Explanations:
    def __init__(self, root, monitoring):
        self.root=Path(root)/'explanations'; self.root.mkdir(parents=True,exist_ok=True)
        self.monitoring=monitoring; self.process=None; self.lock=threading.Lock()
        for path in self.root.glob('*/job.json'):
            job=read_json(path,{})
            if job.get('status') in ('Queued','Running'):
                job.update(status='Interrupted',detail='Dashboard restarted. Request the explanation again.')
                write_json(path,job)

    @staticmethod
    def public(job):
        result={k:v for k,v in job.items() if k!='report'}
        result['report_ready']=job.get('status')=='Completed' and job.get('report',{}).get('schema_version')==4
        return result

    def status(self,bank):
        jobs=[read_json(p,{}) for p in self.root.glob('*/job.json')]
        return dict(jobs=[self.public(j) for j in sorted([j for j in jobs if j.get('bank')==bank],key=lambda j:j['started'],reverse=True)[:10]],
                    process_running=bool(self.process and self.process.poll() is None))

    def _snapshot(self,replay_id,txn_id,bank):
        replay=next((j for j in self.monitoring.status(bank)['jobs'] if j['id']==replay_id and j['status']=='Completed'),None)
        if not replay:raise ValueError('Load a completed replay for your bank first.')
        rows=self.monitoring.rows(replay['id'],bank)
        row=next((r for r in rows['rows'] if str(r['txn_id'])==str(txn_id)),None)
        if not row:raise ValueError('Transaction does not belong to this replay.')
        if rows.get('model')!=replay.get('model') or rows.get('bank')!=bank or rows.get('threshold')!=replay.get('threshold'):
            raise ValueError('Saved replay model, bank or cutoff changed. Score a new replay.')
        provenance=model_provenance(replay['model'],bank)
        inputs=cache_inputs(replay,rows,row,provenance,digest(self.monitoring.root/replay['id']/'transactions.json'))
        return replay,row,inputs

    def start(self,data,bank):
        with self.lock:
            replay,row,inputs=self._snapshot(data.get('replay_id'),data.get('txn_id'),bank)
            key=hash_json(inputs);path=self.root/key/'job.json'
            existing=read_json(path,{})
            if existing.get('status')=='Completed':
                self.report(key,bank)
                return self.public(existing)
            if self.process and self.process.poll() is None:
                raise ValueError('An explanation is running. Wait for completion.')
            job=dict(id=key,cache_key=key,cache_key_inputs=inputs,bank=bank,replay_id=replay['id'],txn_id=str(row['txn_id']),
                     expected_score=row['score'],expected_transfer=row,model=replay['model'],dataset=replay['dataset'],
                     dataset_fingerprint=replay['dataset_fingerprint'],started=now(),status='Queued',detail='Preparing verified investigator evidence')
            write_json(path,job)
            with (path.parent/'worker.log').open('wb') as log:
                self.process=subprocess.Popen([sys.executable,'-B','-m','streaming.app.explanations','--job',str(path)],cwd=REPO,
                    stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            return self.public(job)

    def report(self,key,bank):
        if not isinstance(key,str) or not re.fullmatch(r'[0-9a-f]{32,64}',key):raise ValueError('Explanation not found.')
        job=read_json(self.root/key/'job.json',{})
        if job.get('bank')!=bank or job.get('status')!='Completed':raise ValueError('Choose a completed explanation for this bank.')
        replay,row,inputs=self._snapshot(job['replay_id'],job['txn_id'],bank)
        if inputs!=job.get('cache_key_inputs'):raise ValueError('Explanation evidence is stale or belongs to another replay model. Request it again.')
        if check_dataset(Path(job['dataset']),bank)['fingerprint']!=job['dataset_fingerprint']:
            raise ValueError('Replay data changed. Score a new replay before explaining it.')
        return validate_report(job.get('report',{}),job)

    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate();self.process.wait(timeout=10)


def explain(job):
    return explain_replay(job)


def worker(path):
    import torch
    torch.set_num_threads(min(4,os.cpu_count() or 1))
    job=read_json(path)
    try:
        job.update(status='Running',detail='Reconstructing the selected replay model and measured evidence');write_json(path,job)
        report=explain(job)
        job.update(status='Completed',detail='Investigator evidence verified against this replay within 1e-6.',report=report,ended=now())
    except Exception as exc:
        import traceback;traceback.print_exc()
        job.pop('report',None)
        job.update(status='Failed',detail=str(exc)[:1000],ended=now())
    write_json(path,job)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--job',type=Path,required=True)
    worker(parser.parse_args().job)
