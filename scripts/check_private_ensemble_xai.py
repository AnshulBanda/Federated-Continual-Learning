"""Check real reference/private ensemble replay parity without relaxing its guard."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import pandas as pd
import torch
from streaming.app.final_model import reference_model,load_runtime,score_models
from streaming.app.local_training import check_dataset
from streaming.app.explanations import explain


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True);p.add_argument('--acceptance',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    torch.set_num_threads(1);bank='Key_Bank'
    acceptance=json.loads(args.acceptance.read_text())
    model_path=Path(acceptance['runtime_root'])/'complete-cohort/bank-1/local-training/active-Key_Bank.json'
    private=json.loads(model_path.read_text())
    fingerprint=check_dataset(args.dataset,bank)['fingerprint']
    results=[]
    for name,selected in [('nonprivate_reference',reference_model(bank)),('private_ensemble_round4',private)]:
        models,static,streams,_=load_runtime(selected,args.dataset,bank)
        probabilities,_,_=score_models(models,static,streams)
        frame=pd.read_csv(args.dataset/'validation'/bank/'edge_list.csv.gz')
        frame=frame.iloc[np.argsort(pd.to_datetime(frame.timestamp).to_numpy(),kind='stable')].reset_index(drop=True)
        index=int(np.argmax(probabilities))
        job=dict(dataset=str(args.dataset),bank=bank,model=selected,dataset_fingerprint=fingerprint,
                 txn_id=str(frame.iloc[index].txn_id),expected_score=float(probabilities[index]))
        try:
            report=explain(job)
            difference=abs(report['ensemble_probability']-job['expected_score'])
            assert difference<=1e-6
            assert abs(report['additivity_residual'])<=1e-5
            guarded=False
            try:explain(dict(job,expected_score=report['ensemble_probability']+1.5e-6))
            except ValueError as exc:
                if 'does not match the saved replay' not in str(exc):raise
                guarded=True
            assert guarded
            result=dict(model=name,result='PASS',probability_parity_absolute_error=difference,
                strict_prediction_tolerance=1e-6,guard_rejects_1p5e_minus6_mismatch=True,
                additivity_residual=report['additivity_residual'],members=len(report['member_probabilities']),
                model_sha256=selected['sha256'],method=report['method'])
        except ValueError as exc:
            if name=='nonprivate_reference':raise
            result=dict(model=name,result='GUARDED',reason=str(exc),strict_prediction_tolerance=1e-6,
                        model_sha256=selected['sha256'])
        results.append(result);print(result,flush=True)
    args.output.write_text(json.dumps(dict(checks=results,scope='Local August replay/attribution only; no transaction-level DP claim',test_loaded=False),indent=2)+'\n')


if __name__=='__main__':main()
