#!/usr/bin/env python3
"""Bounded August-only utility experiments. Never saves clean client updates."""
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
from distributed_federation.privacy.server_optimizer import ServerConfig,ServerOptimizer
from distributed_federation.common.model_runtime import serialize_state,load_initial_checkpoint
from distributed_federation.privacy.ledger import Ledger


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    research.json_write(path,value)


def summary(rows):
    return {k:float(np.mean([r['validation'][k] for r in rows])) for k in ('pr_auc','precision','recall','f1','roc_auc')}


def select(history):
    # Predeclared: largest equal-bank August AP, earliest round breaks exact ties.
    return max(history,key=lambda r:(r['metrics']['pr_auc'],-r['round']))


def assert_floor(privacy,releases):
    baseline=Privacy(mode='distributed_dp',clip=6.5,multiplier=1e-5)
    if (privacy.mode!='distributed_dp' or not privacy.secure or privacy.expected_clients!=3
        or privacy.min_noise_contributors!=3 or privacy.delta>1e-6
        or privacy.accounting(releases)['epsilon']>baseline.accounting(4)['epsilon']):
        raise ValueError('Candidate violates retained Level-3 privacy floor')


def private_keys(state,subset):
    prefixes={'all':('',),'decoder':('decoder.',),'temporal_decoder':('time_projection.','memory_update.','decoder.'),
              'message_decoder':('message_projection.','memory_update.','decoder.')}
    if subset not in prefixes:raise ValueError('Unknown private subset')
    return sorted(k for k in state if k.startswith(prefixes[subset]))


def run(clients,cfg,seed,out):
    out.mkdir(parents=True,exist_ok=False)
    cfg=copy.deepcopy(cfg)
    rounds=cfg.get('rounds',4)
    privacy=Privacy(mode='distributed_dp',clip=cfg.get('clip',6.5),multiplier=cfg.get('multiplier',1e-5),
                    entropy=cfg.get('entropy','research'),research_seed=20261027)
    assert_floor(privacy,rounds)
    set_seed(seed)
    static,streams,_=clients[BANKS[0]]
    model=CausalTemporalGraphSAGE(static.shape[1],streams['training'].edge_attr.shape[1],128,cfg.get('dropout',.25))
    checkpoint=Path(cfg.get('checkpoint_template','/Users/pj/Desktop/college/capstone/Capstone/artifacts/final_evaluation/corrected_fedavg/seed_{seed}/global_model.pt').format(seed=seed))
    load_initial_checkpoint(model,checkpoint)
    keys=private_keys(model.state_dict(),cfg.get('subset','all'))
    for name,param in model.named_parameters():param.requires_grad_(name in keys)
    localcfg=SimpleNamespace(local_epochs=cfg.get('local_epochs',3),batch_size=1024,replay_size=cfg.get('replay_size',2000),
            learning_rate=cfg.get('learning_rate',.001),weight_decay=cfg.get('weight_decay',1e-4),negative_ratio=cfg.get('negative_ratio',20),
            replay='risk_context',distill=0.,rng_policy=cfg.get('rng_policy','per_client'))
    server=ServerOptimizer(ServerConfig(**cfg.get('server',{})))
    dim=sum(model.state_dict()[k].numel() for k in keys)
    sources={}
    for p in sorted([* (ROOT/'distributed_federation').rglob('*.py'),* (ROOT/'src/gnn').glob('*.py'),Path(__file__)]):
        rel=p.relative_to(ROOT);data=p.read_bytes();sources[str(rel)]=hashlib.sha256(data).hexdigest()
        target=out/'source_snapshot'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    meta=dict(config=cfg,seed=seed,privacy=asdict(privacy),parameters=privacy.parameters(dim),accounting=privacy.accounting(rounds),
            selection_rule='highest_August_macro_AP_earliest_tie; all executed releases charged',
            source_hashes=sources,checkpoint=str(checkpoint),checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
            private_keys=keys,trainable_dimension=dim,training=vars(localcfg),test_loaded=False,
            scope='incremental DP conditional on nonprivate fixed warm start and public preprocessing/validation',
            noise_realization_persisted=False)
    write(out/'manifest.json',meta)
    ledger=Ledger(out/'ledger.sqlite3');history=[];start=time.monotonic()
    # The fixed common domain gives controlled comparisons of research noise.
    # Operational entropy ignores this public domain and never uses a public seed.
    noise_domain=f'utility-control-seed-{seed}'
    try:
        for rid in range(1,rounds+1):
            base={k:v.detach().clone() for k,v in model.state_dict().items()}
            private_base={k:base[k] for k in keys}
            ledger.reserve(out.name,rid,'simulation',asdict(privacy))
            ctx=context(out.name,rid,list(BANKS),'utility-'+hashlib.sha256(json.dumps(cfg,sort_keys=True).encode()).hexdigest(),
                        hashlib.sha256(serialize_state(base)).hexdigest(),dim)
            receiver=Round(ctx)
            clientkeys={bank:ClientKey(bank,ctx) for bank in BANKS}
            for bank,key in clientkeys.items():receiver.add_key(key.hello(),bank)
            rh=hashlib.sha256(receiver.roster()).hexdigest()
            for index,(bank,(static,streams,boundary)) in enumerate(clients.items()):
                # This block models one worker; only its masked bytes reach receiver.
                local=copy.deepcopy(model)
                research.train_client(local,static,streams['training'],boundary,localcfg,seed+rid*100+index)
                state=local.state_dict()
                if any(not torch.equal(state[k],base[k]) for k in base if k not in keys):
                    raise AssertionError('Frozen parameter changed')
                contribution=client_contribution({k:state[k] for k in keys},private_base,privacy,noise_domain,rid,str(index))
                masked=clientkeys[bank].mask(contribution,receiver.keys)
                md={**ctx,'secagg_context_sha256':hashlib.sha256(canonical(ctx)).hexdigest(),'roster_sha256':rh}
                receiver.add_update(bank,pack(masked),md)
                del state,local,contribution,masked
            noisy=aggregate(receiver.complete(),private_base,privacy,noise_domain,rid)
            result=server.apply(private_base,noisy)
            model.load_state_dict({**base,**result},strict=True)
            del receiver,clientkeys,noisy,result
            rows=[dict(bank=bank,**research.validation(model,static,streams,1024)) for bank,(static,streams,_) in clients.items()]
            cp=out/f'round_{rid:02d}.pt'
            torch.save(dict(state_dict=model.state_dict(),best_round=rid),cp)
            history.append(dict(round=rid,metrics=summary(rows),per_bank=rows,accounting=privacy.accounting(rid),
                                checkpoint=str(cp),sha256=hashlib.sha256(cp.read_bytes()).hexdigest(),seconds=time.monotonic()-start))
            write(out/'progress.json',dict(**meta,history=history))
            print(out.name,'round',rid,'AP',round(history[-1]['metrics']['pr_auc'],7),'seconds',round(history[-1]['seconds'],1),flush=True)
        chosen=select(history)
        record=dict(**meta,history=history,selected=chosen,selected_checkpoint=chosen['checkpoint'],elapsed_seconds=time.monotonic()-start)
        write(out/'results.json',record)
        return record
    finally:ledger.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--dataset',type=Path,default=Path('/Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset'))
    args=p.parse_args();plan=json.loads(args.plan.read_text())
    torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
    clients=research.load_development_clients(args.dataset)
    for entry in plan:
        for seed in entry['seeds']:
            dest=args.output/f"{entry['id']}_s{seed}"
            if (dest/'results.json').exists():continue
            run(clients,entry['config'],seed,dest)

if __name__=='__main__':main()
