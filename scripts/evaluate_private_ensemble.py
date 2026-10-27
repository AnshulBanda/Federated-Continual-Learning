"""August-only evaluation of the single predeclared production confirmation.

Round four is the predeclared primary endpoint. All rounds are reported without
changing configuration or rerunning production noise. Metrics/thresholds are
nonprivate research disclosures, separate from the model-release DP guarantee.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import torch
from src.gnn import causal_temporal_graphsage as g
from streaming.app.final_model import build_ensemble,frozen_encoders,score_models,reference_model
from streaming.app.final_federation import BANK_ORDER
from distributed_federation.common.model_runtime import deserialize_state
from distributed_federation.common.checkpoints import verify_checkpoint


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--acceptance',type=Path,required=True)
    p.add_argument('--declaration',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise ValueError('Evaluation already retained; do not overwrite it')
    torch.set_num_threads(1)
    from adaptive_continual_federated import fast_choose_threshold
    report=json.loads(args.acceptance.read_text());run=report['complete_cohort']
    declaration=json.loads(args.declaration.read_text())
    assert declaration['production_runs']==1 and declaration['primary_round']==4
    assert run['run_id']==declaration['run_id']
    config_path=Path(report['runtime_root'])/'complete-cohort/central/collaboration/launch-config.json'
    cfg=json.loads(config_path.read_text());output=Path(cfg['output_dir'])/cfg['run_id']
    nodes,edges,schema=frozen_encoders();banks={}
    for bank in BANK_ORDER:
        static,streams,ncols,ecols=g.build_bank_data(args.dataset,bank,nodes,edges,splits=('training','validation'))
        assert set(streams)=={'training','validation'}
        assert ncols==schema['node_columns'] and ecols==schema['edge_columns']
        banks[bank]=(static,streams)
    trajectory=[]
    for rid in range(5):
        ensemble=build_ensemble(schema,checkpoints=rid==0)
        if rid:
            verify_checkpoint(output,rid)
            checkpoint=output/f'global_round_{rid:03d}.safetensors'
            ensemble.load_state_dict(deserialize_state(checkpoint.read_bytes()),strict=True)
            digest=hashlib.sha256(checkpoint.read_bytes()).hexdigest()
        else:digest=[m['sha256'] for m in reference_model('Key_Bank')['members']]
        models=list(ensemble.values())
        for model in models:model.eval()
        rows=[]
        for bank,(static,streams) in banks.items():
            mean,labels,members=score_models(models,static,streams)
            threshold=fast_choose_threshold(labels,mean)
            row=dict(bank=bank,validation=g.metric_block(labels,mean,threshold),threshold=threshold,
                ensemble_aggregation='arithmetic mean of three probabilities',
                members=[dict(seed=seed,metrics=g.metric_block(labels,pred,fast_choose_threshold(labels,pred)))
                    for seed,pred in zip((42,52,62),members)])
            rows.append(row)
        macro={key:float(np.mean([r['validation'][key] for r in rows])) for key in ('pr_auc','precision','recall','f1','roc_auc')}
        trajectory.append(dict(round=rid,macro=macro,per_bank=rows,checkpoint_sha256=digest))
        print('August round',rid,'macro',macro,flush=True)
    result=dict(scope='New private adaptive three-member ensemble; August validation only',
        production_run_id=run['run_id'],production_runs=1,primary_round=4,selected=trajectory[-1],trajectory=trajectory,
        primary_selection='Final round four fixed before production; no best-noise/round selection',
        declaration_sha256=hashlib.sha256(args.declaration.read_bytes()).hexdigest(),
        training=cfg,accounting=run['rounds'][-1]['accounting'],validation_loaded=True,test_loaded=False,
        metric_privacy='Metrics and August-selected decision thresholds are nonprivate research disclosures',
        result_does_not_relabel_reference_or_historical_dp=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
