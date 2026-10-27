"""Local, asynchronous exact grouped SHAP for the selected replay's ensemble."""
import os
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from .local_training import read_json, write_json, now
from .final_model import REPO


class Explanations:
    def __init__(self, root, monitoring):
        self.root=Path(root)/'explanations'; self.root.mkdir(parents=True,exist_ok=True)
        self.monitoring=monitoring; self.process=None; self.lock=threading.Lock()
        for path in self.root.glob('*/job.json'):
            job=read_json(path,{})
            if job.get('status') in ('Queued','Running'):
                job.update(status='Interrupted',detail='Dashboard restarted. Request the explanation again.')
                write_json(path,job)
    def status(self,bank):
        jobs=[read_json(p,{}) for p in self.root.glob('*/job.json')]
        return dict(jobs=sorted([j for j in jobs if j.get('bank')==bank],key=lambda j:j['started'],reverse=True)[:10], process_running=bool(self.process and self.process.poll() is None))
    def start(self,data,bank):
        with self.lock:
            if self.process and self.process.poll() is None:raise ValueError('An explanation is running. Wait for completion.')
            replay=next((j for j in self.monitoring.status(bank)['jobs'] if j['id']==data.get('replay_id') and j['status']=='Completed'),None)
            if not replay:raise ValueError('Load a completed replay for your bank first.')
            rows=self.monitoring.rows(replay['id'],bank)['rows']
            row=next((r for r in rows if r['txn_id']==data.get('txn_id')),None)
            if not row:raise ValueError('Transaction does not belong to this replay.')
            key=uuid.uuid4().hex
            job=dict(id=key,bank=bank,replay_id=replay['id'],txn_id=row['txn_id'],expected_score=row['score'],
                     model=replay['model'],dataset=replay['dataset'],dataset_fingerprint=replay['dataset_fingerprint'],
                     started=now(),status='Queued',detail='Preparing local explanation')
            path=self.root/key/'job.json';write_json(path,job)
            with (path.parent/'worker.log').open('wb') as log:
                self.process=subprocess.Popen([sys.executable,'-B','-m','streaming.app.explanations','--job',str(path)],cwd=REPO,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            return job
    def close(self):
        if self.process and self.process.poll() is None:
            self.process.terminate(); self.process.wait(timeout=10)


def explain(job):
    import numpy as np
    import pandas as pd
    import torch
    from src.gnn import causal_temporal_graphsage as g
    from xai.src.grouped_features import explain_groups
    from xai.src.ensemble_explainer import ensemble_logit_predictor, member_probability_details
    from .final_model import load_runtime
    from .local_training import check_dataset
    dataset=Path(job['dataset']); bank=job['bank']
    if check_dataset(dataset,bank)['fingerprint']!=job['dataset_fingerprint']:
        raise ValueError('Replay data has changed. Score a new replay before explaining it.')
    models,static,streams,encoder=load_runtime(job['model'],dataset,bank)
    frame=pd.read_csv(dataset/'validation'/bank/'edge_list.csv.gz')
    frame=frame.iloc[np.argsort(pd.to_datetime(frame.timestamp).to_numpy(),kind='stable')].reset_index(drop=True)
    indices=np.flatnonzero(frame.txn_id.astype(str).to_numpy()==job['txn_id'])
    if len(indices)!=1:raise ValueError('Transaction ID is missing or ambiguous.')
    index=int(indices[0]); batch_start=index//1024*1024; event=streams['validation']
    predictors=[]
    with torch.no_grad():
        for model in models:
            state=model.initial_state(static)
            _,_,state=g.score_stream(model,state,streams['training'],1024)
            for start in range(0,batch_start,1024):
                batch=g.Events(*(v[start:start+1024] for v in (event.src,event.dst,event.edge_attr,event.timestamp,event.labels)))
                _,state=model.score_and_update(state,batch)
            source=state.memory[event.src[index]].clone(); target=state.memory[event.dst[index]].clone()
            def predict(rows,model=model,source=source,target=target):
                with torch.no_grad():
                    edge=model.edge_projection(torch.from_numpy(encoder.transform(rows)))
                    src=source.expand(len(rows),-1); dst=target.expand(len(rows),-1)
                    return model.decoder(torch.cat((src,dst,torch.abs(src-dst),edge),dim=1)).squeeze(1).numpy()
            predictors.append(predict)
    row=frame.iloc[index]
    if len(predictors)==1:
        single_logit=float(np.asarray(predictors[0](pd.DataFrame([row]))).reshape(-1)[0])
        probability=float(torch.sigmoid(torch.tensor(single_logit,dtype=torch.float64)))
        probabilities=dict(member_probabilities=[probability],ensemble_probability=probability,
                           aggregation='single model probability')
        predictor=predictors[0]
    else:
        probabilities=member_probability_details(predictors,pd.DataFrame([row]))
        predictor=ensemble_logit_predictor(predictors)
    if abs(probabilities['ensemble_probability']-job['expected_score'])>1e-6:
        raise ValueError('Explanation score does not match the saved replay. Rescore this model.')
    background=pd.read_csv(dataset/'training'/bank/'edge_list.csv.gz')
    report=explain_groups(predictor,row,background,background_size=32)
    report.update(probabilities, units='single-model logit' if len(predictors)==1 else 'logit(mean of three member probabilities)',
                  transaction_id=job['txn_id'],bank=bank,model_version=job['model']['version'],
                  checkpoint_hash=job['model']['sha256'],history_events=batch_start,
                  privacy='Local explanation; no differential privacy guarantee',
                  scope='Current transaction features with each member\'s pre-batch account memory fixed',
                  split='August validation',threshold=float(job['model'].get('threshold',.5)))
    report.pop('background_txn_ids',None)
    if check_dataset(dataset,bank)['fingerprint']!=job['dataset_fingerprint']:
        raise ValueError('Dataset changed during explanation.')
    return report


def worker(path):
    import torch
    torch.set_num_threads(min(4,os.cpu_count() or 1))
    job=read_json(path)
    try:
        job.update(status='Running',detail='Reconstructing causal history and computing grouped SHAP');write_json(path,job)
        report=explain(job)
        job.update(status='Completed',detail='Explanation matches the saved ensemble prediction.',report=report,ended=now())
    except Exception as exc:
        import traceback;traceback.print_exc()
        job.update(status='Failed',detail=str(exc)[:1000],ended=now())
    write_json(path,job)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--job',type=Path,required=True)
    worker(parser.parse_args().job)
