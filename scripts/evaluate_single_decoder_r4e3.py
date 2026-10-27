"""Evaluate the one fixed production run on August; no training or test reads."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import torch
import search_single_decoder_r4e3 as experiment
from distributed_federation.common.model_runtime import deserialize_state
from distributed_federation.common.checkpoints import verify_checkpoint


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--acceptance',type=Path,required=True)
    p.add_argument('--declaration',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise ValueError('Preserve existing evaluation')
    torch.set_num_threads(1);torch.use_deterministic_algorithms(True)
    acceptance=json.loads(args.acceptance.read_text());run=acceptance['complete_cohort']
    plan=json.loads(args.declaration.read_text())
    assert plan['production_runs']==1 and plan['primary_round']==4 and plan['run_id']==run['run_id']
    config=json.loads((Path(acceptance['runtime_root'])/'complete-cohort/central/collaboration/launch-config.json').read_text())
    assert config['training_protocol']=='adaptive_single' and config['private_subset']=='decoder'
    output=Path(config['output_dir'])/config['run_id']
    data=experiment.load_data(args.dataset,True);m=experiment.model();history=[]
    for rid in range(5):
        if rid:
            verify_checkpoint(output,rid)
            path=output/f'global_round_{rid:03d}.safetensors';state=deserialize_state(path.read_bytes())
            assert not any(k.startswith(('42.','52.','62.')) for k in state)
            m.load_state_dict(state,strict=True)
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
        else:digest=experiment.WARM_SHA
        history.append(dict(round=rid,**experiment.evaluate(m,data),checkpoint_sha256=digest))
        print('Production August round',rid,history[-1]['macro'],flush=True)
    result=dict(single_model=True,primary_round=4,production_runs=1,run_id=run['run_id'],
        final=history[-1],history=history,config=config,accounting=run['rounds'][-1]['accounting'],
        warm_sha256=experiment.WARM_SHA,private_dimension=65793,
        declaration_sha256=hashlib.sha256(args.declaration.read_bytes()).hexdigest(),
        September_loaded=False,test_loaded=False,
        evaluation_privacy='Nonprivate August research metrics/thresholds; not included in model-release accounting')
    experiment.write(args.output,result)


if __name__=='__main__':main()
