#!/usr/bin/env python3
"""Validation-only real-model experiments, using the same trainer/mechanism as Kafka.

No September loader. Fixed-round primary metrics; every intermediate release is
accounted. Norm calibration is explicitly nonprivate and training-only.
"""
import argparse
import copy
import hashlib
import json
import math
import sys
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src/gnn')]
import adaptive_continual_federated as research
from causal_temporal_graphsage import BANKS,CausalTemporalGraphSAGE,set_seed
from distributed_federation.privacy.mechanism import Privacy,vector,client_contribution,aggregate
from distributed_federation.privacy.secagg import ClientKey,Round,context,pack,canonical
from distributed_federation.common.model_runtime import serialize_state
from distributed_federation.privacy.ledger import Ledger

# Capture imported source once. Reading files later in a long-lived process can
# mislabel the loaded code if development edits happen while other seeds train.
SOURCE_BYTES={}
for module in (research,sys.modules['causal_temporal_graphsage'],sys.modules['continual_temporal_graphsage'],
               sys.modules['distributed_federation.privacy.mechanism'],sys.modules['distributed_federation.privacy.secagg']):
    file=Path(module.__file__)
    SOURCE_BYTES[str(file.relative_to(ROOT))]=file.read_bytes()


def clean(value):
    if isinstance(value,dict):return {k:clean(v) for k,v in value.items()}
    if isinstance(value,list):return [clean(v) for v in value]
    if isinstance(value,float) and not math.isfinite(value):return 'infinite'
    return value


def write(path,value):research.json_write(path,clean(value))


def summarize(rows):
    keys=('pr_auc','f1','precision','recall','roc_auc')
    return {k:float(np.mean([r['validation'][k] for r in rows])) for k in keys}


def run(clients,seed,rounds,track,mode,multiplier,clip,output,reference=False,selection="final"):

    output.mkdir(parents=True,exist_ok=False)
    set_seed(seed)
    static,streams,_=clients[BANKS[0]]
    model=CausalTemporalGraphSAGE(static.shape[1],streams['training'].edge_attr.shape[1],128,.25)
    checkpoint=None
    if track=='warm':
        checkpoint=Path('/Users/pj/Desktop/college/capstone/Capstone/artifacts/final_evaluation/corrected_fedavg')/f'seed_{seed}'/'global_model.pt'
        with torch.serialization.safe_globals([Path, __import__('pathlib').PosixPath]):
            state=torch.load(checkpoint,map_location='cpu',weights_only=True)['state_dict']
        model.load_state_dict(state,strict=True)
    cfg=SimpleNamespace(local_epochs=3,batch_size=1024,replay_size=2000,learning_rate=.001,
                        replay='risk_context',distill=0.,rng_policy='global' if reference else 'per_client')
    privacy=Privacy(mode=mode,clip=clip,multiplier=multiplier,entropy='production')
    dim=len(vector(model.state_dict()))
    params=privacy.parameters(dim)
    metadata=dict(seed=seed,rounds=rounds,track=track,privacy=asdict(privacy),parameters=params,
        training=vars(cfg),aggregation='temporal_harmonized' if reference else 'equal_mean',test_loaded=False,
        checkpoint=str(checkpoint) if checkpoint else None,
        checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest() if checkpoint else None,
        scope='conditional_checkpoint' if checkpoint else 'random_initialization_conditional_public_preprocessing',
        gaussian_sampler='OS entropy production; no released noise seed',selection=selection)
    source_hashes={}
    source_dir=output/'source_snapshot'
    for relative,source in SOURCE_BYTES.items():
        target=source_dir/relative;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(source);source_hashes[relative]=hashlib.sha256(source).hexdigest()
    metadata['source_hashes']=source_hashes
    write(output/'manifest.json',metadata)
    ledger=Ledger(output/'local-ledger.sqlite3')
    norms=[];history=[];best_score=-1.;start=time.monotonic()
    for rid in range(1,rounds+1):
        base={k:v.detach().clone() for k,v in model.state_dict().items()}
        states=[]
        for index,(bank,(static,streams,boundary)) in enumerate(clients.items()):
            local=copy.deepcopy(model)
            research.train_client(local,static,streams['training'],boundary,cfg,seed+rid*100+index)
            state={k:v.detach().clone() for k,v in local.state_dict().items()}
            if mode=='none':norms.append(dict(bank=bank,round=rid,norm=float(np.linalg.norm(vector(state)-vector(base)))))
            states.append(state)
        ledger.reserve(output.name,rid,'simulation',asdict(privacy))
        clean_mean=np.mean([vector(s)-vector(base) for s in states],axis=0) if mode=='none' else None
        if reference:
            state,_=research.temporal_harmonized_average(states,base)
        else:
            contributions=[client_contribution(s,base,privacy,'experiment',rid,str(i)) for i,s in enumerate(states)]
            if privacy.secure:
                ctx=context(output.name,rid,list(BANKS),'model-schema',hashlib.sha256(serialize_state(base)).hexdigest(),dim)
                server=Round(ctx)
                keys={bank:ClientKey(bank,ctx) for bank in BANKS}
                for bank,key in keys.items():server.add_key(key.hello(),bank)
                roster=server.keys;rh=hashlib.sha256(server.roster()).hexdigest()
                for bank,value in zip(BANKS,contributions):
                    masked=keys[bank].mask(value,roster)
                    meta={**ctx,'secagg_context_sha256':hashlib.sha256(canonical(ctx)).hexdigest(),'roster_sha256':rh}
                    server.add_update(bank,pack(masked),meta)
                contributions=server.complete()
            state=aggregate(contributions,base,privacy,'experiment',rid)
        model.load_state_dict(state)
        rows=[dict(bank=bank,**research.validation(model,static,streams,1024)) for bank,(static,streams,_) in clients.items()]
        record=dict(round=rid,metrics=summarize(rows),per_bank=rows,accounting=privacy.accounting(rid),seconds=time.monotonic()-start)
        if clean_mean is not None:record['aggregate_update_norm_training_only']=float(np.linalg.norm(clean_mean))
        history.append(record)
        if record['metrics']['pr_auc']>best_score:
            best_score=record['metrics']['pr_auc']
            if selection=='best_validation':
                torch.save(dict(state_dict=model.state_dict(),args=metadata,best_round=rid),output/'selected_model.pt')
        write(output/'progress.json',dict(**metadata,history=history))
        print(output.name,'round',rid,record['metrics']['pr_auc'],round(record['seconds'],1),flush=True)
    torch.save(dict(state_dict=model.state_dict(),args=metadata,best_round=rounds),output/'global_model.pt')
    best=max(history,key=lambda x:x['metrics']['pr_auc'])
    result=dict(**metadata,history=history,final=history[-1],best_validation_secondary=best,
        selected=best if selection=='best_validation' else history[-1],selected_checkpoint=str(output/('selected_model.pt' if selection=='best_validation' else 'global_model.pt')),
        accounting=privacy.accounting(rounds),elapsed_seconds=time.monotonic()-start)
    if norms:
        result['training_norms']=norms
        values=[x['norm'] for x in norms]
        def stats(v):return dict(min=float(np.min(v)),median=float(np.median(v)),mean=float(np.mean(v)),
            p75=float(np.quantile(v,.75)),p90=float(np.quantile(v,.9)),p95=float(np.quantile(v,.95)),max=float(np.max(v)))
        result['norm_statistics']=dict(overall=stats(values),per_bank={b:stats([x['norm'] for x in norms if x['bank']==b]) for b in BANKS})
    write(output/'results.json',result);ledger.close()
    return clean(result)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--track',choices=('warm','scratch'),default='warm')
    p.add_argument('--mode',choices=('none','option_a','secure_central_dp','distributed_dp'),default='distributed_dp')
    p.add_argument('--multipliers',type=float,nargs='+',default=[.001,.01,.1,1.])
    p.add_argument('--seeds',type=int,nargs='+',default=[42,52,62])
    p.add_argument('--rounds',type=int,default=4)
    p.add_argument('--clip',type=float,default=1.)
    p.add_argument('--reference',action='store_true')
    p.add_argument('--selection',choices=('final','best_validation'),default='final')
    args=p.parse_args()
    if args.reference and args.mode!='none':p.error('Harmonization cannot be used with private modes')
    torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
    clients=research.load_development_clients(args.dataset)
    for m in args.multipliers:
        for seed in args.seeds:
            name=f'{args.track}_{"reference" if args.reference else args.mode}_m{m:g}_s{seed}'
            if args.selection!='final':name+='_'+args.selection
            path=args.output/name
            if (path/'results.json').exists():continue
            run(clients,seed,args.rounds,args.track,args.mode,m,args.clip,path,args.reference,args.selection)

if __name__=='__main__':main()
