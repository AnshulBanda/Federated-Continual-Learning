#!/usr/bin/env python3
"""Validation-only averaging of public checkpoints within one accounted run."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import torch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'src/gnn')]
import adaptive_continual_federated as research
from causal_temporal_graphsage import CausalTemporalGraphSAGE,BANKS
from distributed_federation.privacy.postprocessing import terminal_average


def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=ROOT/'artifacts/dp_level3_utility_optimization');args=p.parse_args();out=args.root
 plan=json.loads((out/'AGGREGATE_POSTPROCESSING_PLAN.json').read_text());torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
 clients=research.load_development_clients(Path('/Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset'));records=[]
 static,streams,_=clients[BANKS[0]];model=CausalTemporalGraphSAGE(static.shape[1],streams['training'].edge_attr.shape[1],128,.25)
 for candidate in plan['candidates']:
  for seed in plan['seeds']:
   parent=out/'research'/f'{candidate}_s{seed}';original=json.loads((parent/'results.json').read_text());states=[]
   for h in original['history']:
    cp=Path(h['checkpoint']);assert cp.resolve().parent==parent.resolve() # no independently trained run mixing
    assert hashlib.sha256(cp.read_bytes()).hexdigest()==h['sha256']
    states.append(torch.load(cp,weights_only=True,map_location='cpu')['state_dict'])
   for strategy in plan['strategies']:
    dest=out/'postprocessing'/f'{candidate}_{strategy}_s{seed}';dest.mkdir(parents=True,exist_ok=True)
    if (dest/'results.json').exists():r=json.loads((dest/'results.json').read_text());records.append(r);continue
    state=terminal_average(states,strategy,(original.get('private_parameter_keys') or original['private_keys']));model.load_state_dict(state,strict=True)
    rows=[dict(bank=b,**research.validation(model,s,ss,1024)) for b,(s,ss,_) in clients.items()]
    score=sum(x['validation']['pr_auc'] for x in rows)/3
    checkpoint=dest/'model.pt';torch.save(dict(state_dict=state),checkpoint)
    r=dict(candidate=candidate,strategy=strategy,seed=seed,macro_AP=score,per_bank=rows,checkpoint=str(checkpoint),sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),source_run=str(parent),accounting=original['accounting'],private_mechanisms_composed=1,all_four_releases_counted=True,research_only=True,September_loaded=False)
    research.json_write(dest/'results.json',r);records.append(r);print(candidate,strategy,seed,round(score,6),flush=True)
  summary=[]
  for c in plan['candidates']:
   for strategy in plan['strategies']:
    rr=[r for r in records if r['candidate']==c and r['strategy']==strategy]
    if rr:summary.append(dict(candidate=c,strategy=strategy,seeds=[r['seed'] for r in rr],mean=statistics.mean(r['macro_AP'] for r in rr),sample_sd=statistics.stdev(r['macro_AP'] for r in rr) if len(rr)>1 else None))
  research.json_write(out/'AGGREGATE_POSTPROCESSING_RESULTS.json',summary)

if __name__=='__main__':main()
