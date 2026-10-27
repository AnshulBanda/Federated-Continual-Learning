#!/usr/bin/env python3
"""Explicitly NONPRIVATE training-only bound calibration for a fixed decoder track.

No clean client model/delta, private key, or noise vector is returned or saved.
Only the already-authorized nonprivate research calibration statistics are saved.
The operational coordinator never runs this code or receives these local norms.
"""
import copy
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'src/gnn')]
import adaptive_continual_federated as research
from causal_temporal_graphsage import CausalTemporalGraphSAGE,BANKS,set_seed
from distributed_federation.common.model_runtime import load_initial_checkpoint
from distributed_federation.privacy.subset import configure_trainable,extract
from distributed_federation.privacy.mechanism import vector


def client_norm(base_model,static,training,boundary,cfg,seed):
    local=copy.deepcopy(base_model)
    research.train_client(local,static,training,boundary,cfg,seed)
    # A scalar is computed locally; no model/update leaves this function.
    return float(np.linalg.norm(vector(extract(local.state_dict(),'decoder'))-vector(extract(base_model.state_dict(),'decoder'))))


def main():
 out=ROOT/'artifacts/dp_level3_utility_optimization';target=out/'DECODER_CLIPPING_CALIBRATION.json'
 if target.exists():raise ValueError('Calibration already frozen')
 torch.set_num_threads(1);torch.set_num_interop_threads(1);torch.use_deterministic_algorithms(True)
 clients=research.load_development_clients(Path('/Users/pj/Desktop/college/capstone/Capstone/data/final_temporal_dataset'))
 static,streams,_=clients[BANKS[0]];set_seed(42);model=CausalTemporalGraphSAGE(static.shape[1],streams['training'].edge_attr.shape[1],128,.25)
 cp=out/'frozen_warm_starts/seed_42/global_model.pt';load_initial_checkpoint(model,cp);configure_trainable(model,'decoder')
 cfg=SimpleNamespace(local_epochs=2,batch_size=1024,replay_size=2000,learning_rate=.0003,weight_decay=.0001,negative_ratio=20,replay='risk_context',distill=0.,rng_policy='per_client')
 values=[]
 for seed in (42,52,62):
  for index,(bank,(static,streams,boundary)) in enumerate(clients.items()):
   values.append(client_norm(model,static,streams['training'],boundary,cfg,seed+100+index))
  print('training-only calibration seed complete',seed,flush=True)
 bound=math.ceil(max(values)*4)/4
 record=dict(nonprivate_research_calibration=True,scope='Conditional public C, as in the retained baseline; does not privatize calibration itself',uses_validation_scores=False,September_loaded=False,raw_updates_persisted=False,individual_norms_persisted=False,norm_count=len(values),summary=dict(min=min(values),median=float(np.median(values)),p95=float(np.quantile(values,.95)),max=max(values)),frozen_C=bound,selection_rule='Maximum training-only decoder update norm across 9 fixed warm continuation workers, rounded upward to next quarter unit',seeds=[42,52,62],training=vars(cfg),checkpoint=str(cp))
 research.json_write(target,record);print(json.dumps(record,indent=2))

if __name__=='__main__':main()
