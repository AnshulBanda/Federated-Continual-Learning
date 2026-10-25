#!/usr/bin/env python3
"""Freeze one checkpoint-selection follow-up from the complete validation screen."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--dataset',type=Path,required=True);p.add_argument('--run',action='store_true');a=p.parse_args()
    freeze=a.root/'validation_selection_freeze.json'
    if freeze.exists():raise FileExistsError('Follow-up already frozen; do not refreeze after seeing outcomes')
    candidates=[];hashes={}
    for m in (1e-5,1e-4,1e-3,1e-2):
        rows=[]
        for seed in (42,52,62):
            path=a.root/'experiments'/f'warm_distributed_dp_m{m:g}_s{seed}'/'results.json'
            d=json.loads(path.read_text());hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
            rows.append(d['best_validation_secondary']['metrics']['pr_auc'])
        candidates.append(dict(multiplier=m,mean_best_august=float(np.mean(rows)),seed_best_scores=rows))
    eligible=[x for x in candidates if x['mean_best_august']>=.85]
    chosen=max(eligible,key=lambda x:x['multiplier']) if eligible else max(candidates,key=lambda x:x['mean_best_august'])
    record=dict(rule='largest multiplier whose three-seed mean best intermediate August score >=0.85; otherwise highest three-seed mean',chosen=chosen,all_screen_points=candidates,screen_hashes=hashes,seeds=[42,52,62],rounds=4,C=6.5,selection='best_validation',test_loaded=False,confirmation_repeats=1)
    freeze.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2),flush=True)
    if a.run:
        subprocess.run([sys.executable,'-u',str(ROOT/'scripts/run_private_federation.py'),'--dataset',str(a.dataset),'--output',str(a.root/'experiments'),'--mode','distributed_dp','--clip','6.5','--multipliers',str(chosen['multiplier']),'--seeds','42','52','62','--rounds','4','--selection','best_validation'],check=True,cwd=ROOT)
if __name__=='__main__':main()
