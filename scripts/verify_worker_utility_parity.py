#!/usr/bin/env python3
"""Real-data simulator/worker local training comparison; persists booleans only."""
import argparse
import copy
import json
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import torch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'src/gnn')]
import adaptive_continual_federated as research
from causal_temporal_graphsage import BANKS
from distributed_federation.common.config import load_config
from distributed_federation.common.model_runtime import prepare_runtime,load_initial_checkpoint,train_local
from distributed_federation.privacy.subset import configure_trainable


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
 if args.output.exists():p.error('Refusing to overwrite parity evidence')
 torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
 cfg=load_config(args.config);clients=research.load_development_clients(cfg.dataset_dir);rows=[]
 for index,client in enumerate(cfg.clients):
  runtime=prepare_runtime(cfg,client.bank);load_initial_checkpoint(runtime.model,cfg.initial_checkpoint)
  ref=copy.deepcopy(runtime.model);configure_trainable(ref,cfg.private_subset)
  localcfg=SimpleNamespace(local_epochs=cfg.local_epochs,batch_size=cfg.batch_size,replay_size=cfg.replay_size,learning_rate=cfg.learning_rate,weight_decay=cfg.weight_decay,negative_ratio=cfg.negative_ratio,replay=cfg.replay,distill=0.,rng_policy=cfg.rng_policy)
  static,streams,boundary=clients[client.bank]
  research.train_client(ref,static,streams['training'],boundary,localcfg,cfg.seed+100+index)
  train_local(runtime,cfg,1,index)
  equal=all(torch.equal(v,runtime.model.state_dict()[k]) for k,v in ref.state_dict().items())
  rows.append(dict(bank=client.bank,bitwise_equal=equal,raw_updates_persisted=False))
 result=dict(result='PASS' if all(r['bitwise_equal'] for r in rows) else 'FAIL',comparisons=rows,September_loaded=False)
 args.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));assert result['result']=='PASS'

if __name__=='__main__':main()
