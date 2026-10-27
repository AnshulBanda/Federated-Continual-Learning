#!/usr/bin/env python3
"""One production-entropy confirmation per predeclared finalist and seed."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import sys
import torch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import optimize_private_utility as utility


def hashes():
 paths=[*(ROOT/'distributed_federation').rglob('*.py'),*(ROOT/'src/gnn').glob('*.py'),ROOT/'scripts/optimize_private_utility.py',Path(__file__)]
 return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def main():
 p=argparse.ArgumentParser();p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
 plan=json.loads(args.plan.read_text());freeze=args.output/'CONFIRMATION_FREEZE.json'
 record=dict(plan=json.loads(args.plan.read_text()),plan_sha256=hashlib.sha256(args.plan.read_bytes()).hexdigest(),source_sha256=hashes(),selection='Lowest epsilon among successful full three-seed production confirmations; candidates ordered by epsilon. All seeds finish before any decision.',no_same_configuration_noise_reruns=True)
 if freeze.exists():
  old=json.loads(freeze.read_text());assert old==record,'Frozen source/plan changed'
 else:utility.write(freeze,record)
 torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
 clients=utility.research.load_development_clients(Path('/Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset'))
 attempts=[];previous_epsilon=-1
 for entry in plan:
  assert entry['seeds']==[42,52,62]
  cfg=entry['config'];assert cfg['entropy']=='production'
  privacy=utility.Privacy(mode='distributed_dp',clip=cfg.get('clip',6.5),multiplier=cfg['multiplier'])
  epsilon=privacy.accounting(cfg['rounds'])['epsilon'];assert epsilon>=previous_epsilon;previous_epsilon=epsilon
  rows=[]
  for seed in entry['seeds']:
   assert hashes()==record['source_sha256'],'Computational source changed during confirmation'
   dest=args.output/'production'/f"{entry['id']}_s{seed}"
   if (dest/'results.json').exists():row=json.loads((dest/'results.json').read_text())
   else:row=utility.run(clients,cfg,seed,dest) # existing partial directories fail closed
   rows.append(row)
  scores=[r['selected']['metrics']['pr_auc'] for r in rows];mean=statistics.mean(scores)
  attempt=dict(id=entry['id'],seeds=entry['seeds'],scores=scores,mean=mean,sample_sd=statistics.stdev(scores),epsilon=epsilon,passed=mean>=.85)
  attempts.append(attempt);utility.write(args.output/'CONFIRMATION_RESULTS.json',dict(attempts=attempts,selected=entry['id'] if mean>=.85 else None))
  print('CONFIRMATION',json.dumps(attempt),flush=True)
  if mean>=.85:return
 raise RuntimeError('All predeclared production finalists failed; preserve evidence and resume architectural search')

if __name__=='__main__':main()
