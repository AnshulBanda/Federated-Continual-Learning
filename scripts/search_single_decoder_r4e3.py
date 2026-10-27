"""Bounded, research-only single-model search. Never uses testing/September.

Calibration loads training only. Search uses August to compare fixed candidates.
All runs use the SAME frozen seed-42 warm model; 42/52/62 are continuation RNG
seeds, never ensemble members. Deterministic noise is not a production DP claim.
"""
import argparse
import copy
import hashlib
import json
import math
import statistics
import sys
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src/gnn')]
import numpy as np
import torch
import adaptive_continual_federated as research
from causal_temporal_graphsage import CausalTemporalGraphSAGE,build_bank_data,set_seed
from distributed_federation.common.model_runtime import FrozenEncoder,load_initial_checkpoint,serialize_state,train_local,RuntimeData
from distributed_federation.privacy.mechanism import Privacy,vector,client_contribution,aggregate
from distributed_federation.privacy.subset import configure_trainable,extract,reconstruct
from distributed_federation.privacy.server_optimizer import ServerConfig,ServerOptimizer
from distributed_federation.privacy.secagg import ClientKey,Round,context,pack,canonical

BANKS=('Key_Bank','Wells_Fargo','JPMorgan_Chase')
WARM=ROOT/'artifacts/research_adaptive_fcl/warm_start/federated/context_harmonized/seed_42/global_model.pt'
WARM_SHA='d650af6959d1da46888f30fb79bbfd888a6ec20743d14d447ea078dc351536f5'
EPSILON_FLOOR=127.36375184207253
BASE=dict(rounds=4,local_epochs=3,learning_rate=.0003,weight_decay=.0001,batch_size=1024,
          negative_ratio=20,replay='risk_context',replay_size=2000,rng_policy='per_client',
          private_subset='decoder',training_protocol='adaptive_single')


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def load_data(dataset,validation):
    schema=json.loads((ROOT/'distributed_federation/feature_schema.json').read_text())
    encoders=(FrozenEncoder(schema['nodes']),FrozenEncoder(schema['edges']))
    return {b:build_bank_data(dataset,b,*encoders,splits=('training','validation') if validation else ('training',))[:2] for b in BANKS}


def model():
    assert hashlib.sha256(WARM.read_bytes()).hexdigest()==WARM_SHA
    result=CausalTemporalGraphSAGE(57,32,128,.25)
    load_initial_checkpoint(result,WARM);configure_trainable(result,'decoder')
    assert sum(v.numel() for v in extract(result.state_dict(),'decoder').values())==65793
    return result


def configuration(dataset,candidate,seed):
    return SimpleNamespace(**dict(BASE,**candidate['training']),seed=seed,dataset_dir=dataset,
        clients=[SimpleNamespace(client_id=f'bank-{i+1}',bank=b) for i,b in enumerate(BANKS)],
        privacy=Privacy(mode='distributed_dp',clip=candidate['clip'],multiplier=.3,entropy='research',research_seed=seed))


def account(candidate):
    p=Privacy(mode='distributed_dp',clip=candidate['clip'],multiplier=.3,entropy='research')
    value=p.accounting(4)
    if value['epsilon']>EPSILON_FLOOR or value['rho']>3/(2*.15**2):raise ValueError('Privacy floor violated')
    return value


def evaluate(m,data):
    rows=[dict(bank=b,**research.validation(m,static,streams,1024)) for b,(static,streams) in data.items()]
    return dict(macro={k:float(np.mean([r['validation'][k] for r in rows])) for k in ('pr_auc','precision','recall','f1','roc_auc')},per_bank=rows)


def local_train(m,base,static,streams,cfg,rid,index):
    m.load_state_dict(base,strict=True)
    rt=RuntimeData(m,static,{'training':streams['training']},{},'research')
    train_local(rt,cfg,rid,index)
    state=m.state_dict()
    assert all(v.equal(base[k]) for k,v in state.items() if not k.startswith('decoder.'))
    return state


def calibrate(dataset,out):
    target=out/'CALIBRATION.json'
    if target.exists():return json.loads(target.read_text())
    plan=dict(tracks=[dict(id='base',training={}),dict(id='low_lr',training={'learning_rate':.0001}),
                      dict(id='smaller_replay',training={'replay_size':1000})],
        max_local_train_calls=36,continuation_seed=42,rounds=4,epochs=3,splits=['training'],
        C_rule='25% headroom over maximum training-only whole-decoder norm; round up to .25',
        candidate_C_rules=['max_bound','half_max_bound'],nonprivate_research=True,validation_loaded=False,test_loaded=False)
    write(out/'CALIBRATION_PLAN.json',plan)
    data=load_data(dataset,False);results={}
    for track in plan['tracks']:
        global_model=model();workers=[model() for _ in BANKS];rows=[]
        candidate=dict(training=track['training'],clip=1.)
        cfg=configuration(dataset,candidate,42)
        for rid in range(1,5):
            base={k:v.clone() for k,v in global_model.state_dict().items()};sums={k:torch.zeros_like(v,dtype=torch.float64) for k,v in extract(base,'decoder').items()}
            for i,(b,(static,streams)) in enumerate(data.items()):
                local=local_train(workers[i],base,static,streams,cfg,rid,i)
                norm=float(np.linalg.norm(vector(extract(local,'decoder'))-vector(extract(base,'decoder'))))
                rows.append(dict(round=rid,bank=b,norm=norm))
                for k in sums:sums[k]+=local[k].double()/3
            global_model.load_state_dict(reconstruct(base,{k:v.to(base[k].dtype) for k,v in sums.items()},'decoder'))
        values=np.array([r['norm'] for r in rows]);bound=max(.25,math.ceil(1.25*values.max()*4)/4)
        stats=dict(min=float(values.min()),median=float(np.median(values)),mean=float(values.mean()),p75=float(np.quantile(values,.75)),p90=float(np.quantile(values,.90)),p95=float(np.quantile(values,.95)),max=float(values.max()))
        results[track['id']]=dict(training=track['training'],rows=rows,statistics=stats,max_bound=bound,
            candidate_clipping_rates={str(c):float(np.mean(values>c)) for c in (bound,bound/2,bound/4)})
        print('CALIBRATION',track['id'],stats,'C',bound,flush=True)
        write(out/'CALIBRATION_PROGRESS.json',results)
    result=dict(plan=plan,tracks=results,warm_sha256=WARM_SHA,nonprivate_research=True,validation_loaded=False,test_loaded=False)
    write(target,result);return result


def run(dataset,data,candidate,seed,out):
    dest=out/'research'/f"{candidate['id']}_s{seed}"
    if (dest/'RESULT.json').exists():return json.loads((dest/'RESULT.json').read_text())
    if dest.exists():raise ValueError('Preserve incomplete experiment; do not overwrite/replay')
    dest.mkdir(parents=True)
    cfg=configuration(dataset,candidate,seed);privacy=cfg.privacy;budget=account(candidate)
    global_model=model();workers=[model() for _ in BANKS]
    server=ServerOptimizer(ServerConfig(**candidate['server']))
    history=[dict(round=0,**evaluate(global_model,data))];start=time.monotonic()
    for rid in range(1,5):
        base={k:v.clone() for k,v in global_model.state_dict().items()};private=extract(base,'decoder')
        ctx=context('single-research-'+str(seed),rid,[c.client_id for c in cfg.clients],'single-decoder',hashlib.sha256(serialize_state(base)).hexdigest(),65793)
        receiver=Round(ctx);keys={c.client_id:ClientKey(c.client_id,ctx) for c in cfg.clients}
        for c,key in keys.items():receiver.add_key(key.hello(),c)
        roster_sha=hashlib.sha256(receiver.roster()).hexdigest();diagnostics=[]
        for i,(b,(static,streams)) in enumerate(data.items()):
            local=local_train(workers[i],base,static,streams,cfg,rid,i)
            norm=float(np.linalg.norm(vector(extract(local,'decoder'))-vector(private)))
            cid=cfg.clients[i].client_id
            share=client_contribution(extract(local,'decoder'),private,privacy,'research-single-'+str(seed),rid,cid)
            masked=keys[cid].mask(share,receiver.keys)
            receiver.add_update(cid,pack(masked),dict(ctx,secagg_context_sha256=hashlib.sha256(canonical(ctx)).hexdigest(),roster_sha256=roster_sha))
            diagnostics.append(dict(bank=b,decoder_update_l2=norm,clipped=norm>privacy.clip))
            del local,share,masked
        noisy=aggregate(receiver.complete(),private,privacy,'research-single-'+str(seed),rid)
        result=server.apply(private,noisy)
        noisy_norm=float(np.linalg.norm(vector(noisy)-vector(private)));step=float(np.linalg.norm(vector(result)-vector(private)))
        global_model.load_state_dict(reconstruct(base,result,'decoder'))
        row=dict(round=rid,**evaluate(global_model,data),clients=diagnostics,
            fraction_clipped=sum(d['clipped'] for d in diagnostics)/3,C=privacy.clip,multiplier=.3,
            mechanism_parameters=privacy.parameters(65793),noisy_aggregate_step_l2=noisy_norm,applied_aggregate_step_l2=step,
            accounting=privacy.accounting(rid))
        history.append(row)
        write(dest/'PROGRESS.json',dict(candidate=candidate,seed=seed,history=history))
        print(candidate['id'],'seed',seed,'round',rid,'AP',round(row['macro']['pr_auc'],7),'step',round(step,4),flush=True)
    from safetensors.torch import save_file
    save_file(global_model.state_dict(),str(dest/'round4.safetensors'))
    result=dict(candidate=candidate,seed=seed,single_model=True,warm_sha256=WARM_SHA,
        seed_role='Continuation/randomness only; same fixed seed-42 checkpoint',history=history,
        final=history[-1],accounting=budget,entropy='research',private_dimension=65793,
        testing_loaded=False,September_loaded=False,diagnostics_scope='Nonprivate local research metadata; never operational API/wire',
        elapsed_seconds=time.monotonic()-start)
    write(dest/'RESULT.json',result);return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--phase',choices=['calibrate','screen','confirm'],required=True)
    args=p.parse_args();torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
    calibration=calibrate(args.dataset,args.output)
    if args.phase=='calibrate':return
    if args.phase=='screen':
        tracks=calibration['tracks'];base=tracks['base']['max_bound']
        candidates=[dict(id='baseline',training={},clip=base,server={'learning_rate':1.}),
            *[dict(id='server_'+str(rate).replace('.','p'),training={},clip=base,server={'learning_rate':rate}) for rate in (.25,.1,.05)],
            dict(id='low_lr',training=tracks['low_lr']['training'],clip=tracks['low_lr']['max_bound'],server={'learning_rate':.1}),
            dict(id='smaller_replay',training=tracks['smaller_replay']['training'],clip=tracks['smaller_replay']['max_bound'],server={'learning_rate':.1}),
            dict(id='half_C',training={},clip=base/2,server={'learning_rate':.1})]
        write(args.output/'SCREEN_PLAN.json',dict(candidates=candidates,seed=42,max_candidates=7,selection='Final round-four AP; no production noise used'))
        data=load_data(args.dataset,True)
        for candidate in candidates:run(args.dataset,data,candidate,42,args.output)
    else:
        plan=json.loads((args.output/'ROBUSTNESS_PLAN.json').read_text())
        data=load_data(args.dataset,True);results=[]
        for candidate in plan['candidates']:
            runs=[run(args.dataset,data,candidate,seed,args.output) for seed in (42,52,62)]
            scores=[r['final']['macro']['pr_auc'] for r in runs]
            results.append(dict(candidate=candidate,scores=scores,mean=statistics.mean(scores),sample_sd=statistics.stdev(scores),worst=min(scores)))
        write(args.output/'ROBUSTNESS_RESULTS.json',results)
        print('ROBUSTNESS',results,flush=True)


if __name__=='__main__':main()
