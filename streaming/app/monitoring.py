"""Persistent, cancellable validation replay using the explicitly selected checkpoint."""
import hashlib
import json
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from .local_training import read_json, write_json, now, check_dataset
from .overview import Overview, REPO

class Monitoring:
    def __init__(self, root):
        self.root=Path(root)/'monitoring'
        self.root.mkdir(parents=True,exist_ok=True)
        self.process=None
        self.lock=threading.Lock()
        for path in self.root.glob('*/job.json'):
            job=read_json(path,{})
            if job.get('status') in ('Queued','Running'):
                job.update(status='Interrupted',detail='Dashboard restarted; start a new replay.')
                write_json(path,job)
    def status(self,bank):
        jobs=[read_json(p,{}) for p in self.root.glob('*/job.json')]
        return dict(jobs=sorted([j for j in jobs if j.get('bank')==bank],key=lambda j:j['started'],reverse=True)[:20], process_running=bool(self.process and self.process.poll() is None))
    def start(self,data,bank):
        with self.lock:
            if self.process and self.process.poll() is None:
                raise ValueError('Stop the current replay first.')
            model=Overview(self.root.parent).load().get('active_model')
            if not bank or not model:raise ValueError('Save your bank and select a completed local or shared model first.')
            dataset=Path(str(data.get('dataset',''))).resolve()
            if not (dataset/'configuration/model_feature_columns.json').is_file():raise ValueError('Connect a prepared dataset root.')
            key=uuid.uuid4().hex
            job=dict(id=key,bank=bank,model=model,dataset=str(dataset),started=now(),status='Queued',detail='Preparing validation replay',processed=0)
            path=self.root/key/'job.json'
            write_json(path,job)
            with (path.parent/'worker.log').open('wb') as log:
                self.process=subprocess.Popen([sys.executable,'-B','-m','streaming.app.monitoring','--job',str(path)],cwd=REPO,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            return job
    def cancel(self,key,bank):
        job=next((j for j in self.status(bank)['jobs'] if j['id']==key),None)
        if not job:raise ValueError('Replay not found for this bank.')
        if job['status'] in ('Queued','Running'):write_json(self.root/key/'cancel.json',{'requested':True})
        return dict(requested=True)
    def rows(self,key,bank):
        if not any(j['id']==key and j['status']=='Completed' for j in self.status(bank)['jobs']):raise ValueError('Choose a completed replay for this bank.')
        return read_json(self.root/key/'transactions.json',{})
    def close(self):
        if self.process and self.process.poll() is None:
            for path in self.root.glob('*/job.json'):
                if read_json(path,{}).get('status') in ('Queued','Running'):write_json(path.parent/'cancel.json',{'requested':True})
            try:self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.terminate();self.process.wait(timeout=10)

def worker(path):
    job=read_json(path)
    def update(**values):
        job.update(values);write_json(path,job)
    def check():
        if (path.parent/'cancel.json').exists():raise InterruptedError('Replay cancelled.')
    try:
        import numpy as np
        import pandas as pd
        import torch
        from src.gnn import causal_temporal_graphsage as g
        torch.set_num_threads(min(4,os.cpu_count() or 1))
        update(status='Running',detail='Checking local data and checkpoint')
        dataset=Path(job['dataset']);bank=job['bank'];selected=job['model']
        report=check_dataset(dataset,bank);check()
        from .final_model import load_runtime, score_models
        models,static,streams,_=load_runtime(selected,dataset,bank)
        probs,labels,members=score_models(models,static,streams,check,lambda text:update(detail=text))
        check()
        if check_dataset(dataset,bank)['fingerprint']!=report['fingerprint']:raise ValueError('Dataset changed during replay.')
        frame=pd.read_csv(dataset/'validation'/bank/'edge_list.csv.gz')
        frame=frame.iloc[np.argsort(pd.to_datetime(frame.timestamp).to_numpy(),kind='stable')].copy()
        mapping=pd.read_csv(dataset/'validation'/bank/'node_map.csv.gz').set_index('node_id').account_id.to_dict()
        rows=[]
        for i,row in enumerate(frame.to_dict('records')):
            rows.append(dict(txn_id=str(row['txn_id']),timestamp=str(row['timestamp']),source=str(mapping[row['src_node']]),target=str(mapping[row['dst_node']]),score=float(probs[i])))
        threshold=float(selected.get('threshold', .5))
        metrics=g.metric_block(labels,probs,threshold)
        write_json(path.parent/'transactions.json',dict(rows=rows,model=selected,bank=bank,split='August 2025 validation replay',threshold=threshold, member_count=len(models)))
        update(status='Completed',ended=now(),detail='Validation replay scored; no training or test data scoring performed.',processed=len(rows),metrics=metrics,alerts=sum(r['score']>=threshold for r in rows),threshold=threshold,alert_metrics=g.alert_budget_metrics(labels,probs,[10,25,50]),dataset_fingerprint=report['fingerprint'])
    except InterruptedError as exc:update(status='Cancelled',ended=now(),detail=str(exc))
    except Exception as exc:
        import traceback
        traceback.print_exc();update(status='Failed',ended=now(),detail=str(exc)[:1000])

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--job',type=Path,required=True)
    worker(parser.parse_args().job)
