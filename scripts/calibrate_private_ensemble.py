"""One bounded, training-only clipping calibration; an explicit nonprivate disclosure.

Twelve whole-bank concatenated decoder norms, four clean equal-mean rounds, no
validation/test reads, no noise search. The rule is declared before observation:
C = ceil(1.25 * maximum norm / 0.5) * 0.5, with minimum C=0.5.
"""
import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

import numpy as np
import torch
from distributed_federation.common.config import load_config
from distributed_federation.common.model_runtime import prepare_frozen_runtime,train_local,fedavg
from distributed_federation.privacy.subset import extract,parameter_keys
from distributed_federation.privacy.mechanism import vector
from streaming.app.final_model import reference_model,SEEDS

BANK_ORDER=('Key_Bank','Wells_Fargo','JPMorgan_Chase')
TRAINING=dict(training_protocol='adaptive_ensemble',rounds=4,local_epochs=3,learning_rate=.001,
    weight_decay=.0001,batch_size=1024,negative_ratio=20,replay='risk_context',replay_size=2000,
    rng_policy='per_client',seed=42,hidden_channels=128,dropout=.25,aggregation='equal',
    private_subset='ensemble_decoder',return_aggregate=True,max_chunk_bytes=524288)


def calibration_config(dataset,output):
    return dict(TRAINING,broker='127.0.0.1:19092',run_id='training-only-calibration',
        clients=[dict(client_id=f'bank-{i+1}',bank=b) for i,b in enumerate(BANK_ORDER)],
        schema_banks=list(BANK_ORDER),dataset_dir=str(dataset),output_dir=str(output),
        feature_schema='distributed_federation/feature_schema.json',initial_checkpoint=None,
        round_timeout_seconds=900,topics=dict(global_model='calibration.unused.global',client_updates='calibration.unused.updates'),
        privacy=dict(mode='distributed_dp',clip=1.,multiplier=.3,delta=1e-6,expected_clients=3,
                     min_noise_contributors=3,scale=2**24,entropy='production'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise ValueError('Calibration already exists; preserve the fixed choice')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    plan=args.output.with_name('CALIBRATION_PLAN.json')
    plan.write_text(json.dumps(dict(training=TRAINING,bank_order=BANK_ORDER,samples=12,
        rule='ceil(1.25 * max(global ensemble decoder L2) / 0.5) * 0.5; minimum 0.5',
        splits=['training'],validation_loaded=False,test_loaded=False,
        disclosure='Nonprivate research calibration; no DP claim for norm statistics or C selection'),indent=2)+'\n')
    config=args.output.parent/'CALIBRATION_CONFIG.json'
    config.write_text(json.dumps(calibration_config(args.dataset.resolve(),ROOT/'.local/dp-ensemble-level3/calibration'),indent=2)+'\n')
    cfg=load_config(config);torch.set_num_threads(1)
    public=prepare_frozen_runtime(cfg);base={k:v.clone() for k,v in public.model.state_dict().items()}
    keys=parameter_keys(base,'ensemble_decoder')
    per_member={str(seed):sum(v.numel() for k,v in extract(base,'ensemble_decoder').items() if k.startswith(str(seed)+'.')) for seed in SEEDS}
    assert per_member=={'42':65793,'52':65793,'62':65793}
    dimension=sum(per_member.values());assert dimension==197379
    runtimes=[prepare_frozen_runtime(cfg,c.bank) for c in cfg.clients]
    rows=[]
    for rid in range(1,5):
        locals=[]
        for index,(client,runtime) in enumerate(zip(cfg.clients,runtimes)):
            runtime.model.load_state_dict(base,strict=True)
            train_local(runtime,cfg,rid,index)
            local={k:v.detach().clone() for k,v in runtime.model.state_dict().items()}
            assert all(local[k].equal(base[k]) for k in base if k not in keys)
            delta=vector(extract(local,'ensemble_decoder'))-vector(extract(base,'ensemble_decoder'))
            row=dict(round=rid,bank=client.bank,global_ensemble_decoder_l2=float(np.linalg.norm(delta)))
            rows.append(row);locals.append(local)
            print(row,flush=True)
        base=fedavg(locals,[1,1,1])
    values=np.array([r['global_ensemble_decoder_l2'] for r in rows])
    stats=dict(min=float(values.min()),median=float(np.median(values)),mean=float(values.mean()),
               p75=float(np.percentile(values,75)),p90=float(np.percentile(values,90)),
               p95=float(np.percentile(values,95)),max=float(values.max()))
    clip=max(.5,math.ceil(1.25*stats['max']/.5)*.5)
    result=dict(clip=clip,dimension=dimension,per_member_dimension=per_member,private_keys=keys,
        statistics=stats,samples=rows,training=TRAINING,bank_order=BANK_ORDER,
        rule=json.loads(plan.read_text())['rule'],splits=['training'],validation_loaded=False,test_loaded=False,
        disclosure='Nonprivate research disclosure; calibration was not separately privatized',
        ensemble_members=reference_model('Key_Bank')['members'],
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [Path(__file__).resolve(),ROOT/'src/gnn/adaptive_continual_federated.py',
             ROOT/'distributed_federation/common/model_runtime.py',ROOT/'distributed_federation/privacy/subset.py']})
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print('FROZEN C:',clip,'statistics:',stats,flush=True)


if __name__=='__main__':main()
