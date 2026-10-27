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
        return dict(jobs=sorted([j for j in jobs if j.get('bank')==bank],key=lambda j:j['started'],reverse=True)[:20])
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
        dataset=Path(job['dataset']);bank=job['bank'];selected=job['model'];checkpoint=Path(selected['checkpoint'])
        report=check_dataset(dataset,bank);check()
        payload=checkpoint.read_bytes()
        if hashlib.sha256(payload).hexdigest()!=selected['sha256']:raise ValueError('Selected checkpoint changed.')
        n=e=None
        if selected.get('model_kind'):
            from distributed_federation.common.model_runtime import FrozenEncoder, deserialize_state
            from distributed_federation.common.checkpoints import verify_checkpoint
            manifest=read_json(checkpoint.with_suffix('.json'))
            verify_checkpoint(checkpoint.parent,manifest['round_id'])
            schema=manifest['schema']['feature_contract']
            n,e=FrozenEncoder(schema['nodes']),FrozenEncoder(schema['edges'])
            state=deserialize_state(payload);hidden=manifest['schema']['hidden_channels'];dropout=manifest['schema']['dropout']
        else:
            import io
            import pathlib
            with torch.serialization.safe_globals([pathlib.WindowsPath,pathlib.PosixPath]):
                saved=torch.load(io.BytesIO(payload),map_location='cpu',weights_only=True)
            state=saved['state_dict'];hidden=saved['args']['hidden_channels'];dropout=saved['args']['dropout']
        static,streams,ncols,ecols=g.build_bank_data(dataset,bank,n,e,splits=('training','validation'))
        if not selected.get('model_kind') and (saved['node_columns']!=ncols or saved['edge_columns']!=ecols):raise ValueError('Checkpoint feature columns differ from dataset.')
        if not selected.get('model_kind'):
            origin=read_json(checkpoint.parent/'job.json',{})
            if origin.get('quality',{}).get('fingerprint')!=report['fingerprint']:raise ValueError('Use the unchanged dataset used to train this local model.')
        model=g.CausalTemporalGraphSAGE(static.shape[1],streams['training'].edge_attr.shape[1],hidden,dropout)
        model.load_state_dict(state,strict=True);model.eval()
        update(detail='Warming account memory on earlier training events');check()
        with torch.no_grad():
            memory=model.initial_state(static)
            _,_,memory=g.score_stream(model,memory,streams['training'],1024,check_cancel=check)
            update(detail='Scoring August validation transactions chronologically')
            probs,labels,_=g.score_stream(model,memory,streams['validation'],1024,check_cancel=check)
        check()
        if check_dataset(dataset,bank)['fingerprint']!=report['fingerprint']:raise ValueError('Dataset changed during replay.')
        frame=pd.read_csv(dataset/'validation'/bank/'edge_list.csv.gz')
        frame=frame.iloc[np.argsort(pd.to_datetime(frame.timestamp).to_numpy(),kind='stable')].copy()
        mapping=pd.read_csv(dataset/'validation'/bank/'node_map.csv.gz').set_index('node_id').account_id.to_dict()
        rows=[]
        for i,row in enumerate(frame.to_dict('records')):
            rows.append(dict(txn_id=str(row['txn_id']),timestamp=str(row['timestamp']),source=str(mapping[row['src_node']]),target=str(mapping[row['dst_node']]),score=float(probs[i])))
        metrics=g.metric_block(labels,probs,.5)
        write_json(path.parent/'transactions.json',dict(rows=rows,model=selected,bank=bank,split='August 2025 validation replay',threshold=.5))
        update(status='Completed',ended=now(),detail='Validation replay scored; no training or test data scoring performed.',processed=len(rows),metrics=metrics,alerts=sum(r['score']>=.5 for r in rows),dataset_fingerprint=report['fingerprint'])
    except InterruptedError as exc:update(status='Cancelled',ended=now(),detail=str(exc))
    except Exception as exc:
        import traceback
        traceback.print_exc();update(status='Failed',ended=now(),detail=str(exc)[:1000])

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--job',type=Path,required=True)
    worker(parser.parse_args().job)
