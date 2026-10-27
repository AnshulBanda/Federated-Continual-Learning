#!/usr/bin/env python3
"""Reload a frozen private global checkpoint and score August only."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import torch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src/gnn')]
import adaptive_continual_federated as research
from causal_temporal_graphsage import CausalTemporalGraphSAGE,BANKS
from distributed_federation.common.model_runtime import deserialize_state


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():p.error('Refusing to overwrite evaluation')
    torch.set_num_threads(1)
    clients=research.load_development_clients(args.dataset)
    static,streams,_=clients[BANKS[0]]
    model=CausalTemporalGraphSAGE(static.shape[1],streams['training'].edge_attr.shape[1],128,.25)
    if args.checkpoint.suffix=='.safetensors':state=deserialize_state(args.checkpoint.read_bytes())
    else:
        from pathlib import PosixPath
        with torch.serialization.safe_globals([Path,PosixPath]):state=torch.load(args.checkpoint,weights_only=True,map_location='cpu')['state_dict']
    model.load_state_dict(state,strict=True)
    rows=[dict(bank=bank,**research.validation(model,static,streams,1024)) for bank,(static,streams,_) in clients.items()]
    value=dict(checkpoint=str(args.checkpoint),sha256=hashlib.sha256(args.checkpoint.read_bytes()).hexdigest(),test_loaded=False,
        macro_pr_auc=sum(x['validation']['pr_auc'] for x in rows)/len(rows),per_bank=rows)
    args.output.parent.mkdir(parents=True,exist_ok=True);research.json_write(args.output,value);print(json.dumps(value,indent=2))
if __name__=='__main__':main()
