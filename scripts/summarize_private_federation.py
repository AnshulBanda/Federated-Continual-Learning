#!/usr/bin/env python3
"""Build complete seed-level and aggregate validation/privacy frontier artifacts."""
import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
import numpy as np

METRICS=('pr_auc','precision','recall','f1','roc_auc')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args();root=args.root
    results=[json.loads(p.read_text())|{'result_path':str(p)} for p in sorted((root/'experiments').glob('*/results.json'))]
    baseline={}
    for track in ('warm','scratch'):
        norms=[h['aggregate_update_norm_training_only'] for d in results if d['track']==track and d['privacy']['mode']=='none' and d['aggregation']=='equal_mean' for h in d['history']]
        baseline[track]=float(np.median(norms)) if norms else None
    rows=[];groups=defaultdict(list);private_rho=0.
    for d in results:
        privacy=d['privacy'];p=d['parameters'];chosen=d.get('selected',d['final']);metrics=chosen['metrics'];m=privacy['multiplier'];mode=privacy['mode']
        row=dict(track=d['track'],mode='research_reference' if d['aggregation']=='temporal_harmonized' else mode,seed=d['seed'],selection_protocol='best_validation' if d.get('selection')=='best_validation' else 'final',C=privacy['clip'],n=privacy['expected_clients'],multiplier=m,
            sensitivity=p['sensitivity'],sigma_mean=p['sigma_mean'],sigma_share=p['sigma_share'],noise_l2=p['expected_noise_l2'],noise_update_ratio=p['expected_noise_l2']/baseline[d['track']] if baseline[d['track']] else None,
            epsilon=d['accounting']['epsilon'],delta=privacy['delta'],releases=d['rounds'],**metrics,
            **{r['bank']+'_pr_auc':r['validation']['pr_auc'] for r in chosen['per_bank']},
            best_intermediate_pr_auc=d['best_validation_secondary']['metrics']['pr_auc'],best_intermediate_round=d['best_validation_secondary']['round'],
            checkpoint=d.get('selected_checkpoint',str(Path(d['result_path']).parent/'global_model.pt')),privacy_scope=d['scope'])
        rows.append(row);groups[(row['track'],row['mode'],m,row['selection_protocol'])].append(row)
        if mode!='none' and m>0:private_rho+=float(d['accounting']['rho'])
    with (root/'seed_results.csv').open('w') as out:
        writer=csv.DictWriter(out,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summaries=[]
    for (track,mode,m,protocol),members in sorted(groups.items()):
        summary=dict(track=track,mode=mode,selection_protocol=protocol,multiplier=m,seeds=[r['seed'] for r in members],count=len(members),epsilon_per_seed=members[0]['epsilon'],delta=members[0]['delta'],releases_per_seed=members[0]['releases'])
        for metric in (*METRICS,'best_intermediate_pr_auc'):
            values=[r[metric] for r in members]
            summary[metric+'_mean']=float(np.mean(values));summary[metric+'_sample_std']=float(np.std(values,ddof=1)) if len(values)>1 else None
        summaries.append(summary)
    ddp=[s for s in summaries if s['mode']=='distributed_dp' and s['count']==3]
    selected={}
    for track in ('warm','scratch'):
        frontier=[x for x in ddp if x['track']==track]
        eligible=[x for x in frontier if x['pr_auc_mean']>=.85]
        useful={}
        for threshold in (.85,.8,.7,.6,.5):
            qualifying=[x for x in frontier if x['pr_auc_mean']>=threshold]
            useful[str(threshold)]=min(qualifying,key=lambda x:float(x['epsilon_per_seed'])) if qualifying else None
        selected[track]=dict(target_achieved=bool(eligible),strongest_target=min(eligible,key=lambda x:float(x['epsilon_per_seed'])) if eligible else None,best_utility=max(frontier,key=lambda x:x['pr_auc_mean']) if frontier else None,strongest_above_thresholds=useful)
    # Kafka acceptance runs also release private models on the same reference data.
    kafka=[]
    for p in (root/'kafka_acceptance').glob('*/models/*/global_round_*.json'):
        if p.name.endswith('.commit.json'):continue
        d=json.loads(p.read_text());a=d.get('accounting',{})
        if isinstance(a.get('rho'),(int,float)):
            # Each manifest reports cumulative rho within that run; add only the increment.
            cfg=d['privacy'];factor=cfg['expected_clients'] if cfg['mode']=='distributed_dp' else 1
            private_rho+=factor/(2*cfg['multiplier']**2)
            kafka.append(str(p))
    delta=1e-6
    accounting=dict(private_experiment_and_kafka_rho=private_rho,delta=delta,epsilon=private_rho+2*math.sqrt(private_rho*math.log(1/delta)),
        disclaimer='Only the private subset is composed. The complete bundle includes nonprivate references and calibration and has NO finite end-to-end DP guarantee.',kafka_manifests=kafka)
    (root/'aggregate_results.json').write_text(json.dumps(summaries,indent=2)+'\n')
    (root/'privacy_utility_frontier.json').write_text(json.dumps(dict(selection=selected,all_configurations=summaries,accounting=accounting,primary='initial final-round screen plus explicitly labeled best-August follow-up',baseline_update_norm_median=baseline),indent=2)+'\n')
    lines=['# Validation/privacy frontier','', 'Initial screening uses fixed final checkpoints; the separately frozen follow-up retains the best-August checkpoint, labeled explicitly. ± is sample standard deviation across model seeds, with one independent production noise sequence per seed. Best intermediate August AP is descriptive; all rounds are charged. Epsilon is per seed/pipeline, not the entire search. See `seed_results.csv` for every metric, bank and mechanism parameter.','', '| Track | Mode / selection | m | Seeds | Selected macro AP ± SD | Best intermediate AP ± SD | Epsilon/pipeline |','|---|---|---:|---|---:|---:|---:|']
    for s in summaries:
        fmt=lambda k:f"{s[k+'_mean']:.4f}"+(f" ± {s[k+'_sample_std']:.4f}" if s[k+'_sample_std'] is not None else ' (single seed)')
        eps=s['epsilon_per_seed'];eps=f'{eps:.6g}' if isinstance(eps,(int,float)) else str(eps)
        lines.append(f"| {s['track']} | {s['mode']} / {s['selection_protocol']} | {s['multiplier']:g} | {','.join(map(str,s['seeds']))} | {fmt('pr_auc')} | {fmt('best_intermediate_pr_auc')} | {eps} |")
    lines+=['',f"Private subset composition: rho={private_rho:.8g}, epsilon={accounting['epsilon']:.8g}, delta=1e-6. The whole nonprivate research bundle is not DP.",'','A bounded negative result does not prove impossibility for every other multiplier or training configuration. No seed, noise realization or September result is selected to manufacture a passing mean.']
    (root/'FRONTIER.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps(selected,indent=2))

if __name__=='__main__':main()
