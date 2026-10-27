#!/usr/bin/env python3
"""Summarize retained August-only trials without loading any dataset."""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sqlite3
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from distributed_federation.privacy.mechanism import Privacy


def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')


def collect(out):
    runs=[]
    for kind in ('research','production'):
        for p in sorted((out/kind).glob('*/results.json')):
            r=json.loads(p.read_text());r['run_id']=p.parent.name;r['result_path']=str(p);r['kind']=kind;runs.append(r)
    return runs


def stats(runs):
    values=[r['selected']['metrics']['pr_auc'] for r in runs]
    return dict(seeds=[r['seed'] for r in runs],mean=statistics.mean(values),sample_sd=statistics.stdev(values) if len(values)>1 else None)


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'artifacts/dp_level3_utility_optimization');p.add_argument('--finalist');args=p.parse_args();out=args.output.resolve()
    runs=collect(out);groups={}
    for r in runs:
        key=(r['kind'],r['run_id'].rsplit('_s',1)[0]);groups.setdefault(key,[]).append(r)
    frontier=[dict(id=key[1],kind=key[0],**stats(group),epsilon=group[0]['accounting']['epsilon'],config=group[0]['config'],complete=sorted(r['seed'] for r in group)==[42,52,62]) for key,group in groups.items()]
    postprocess=json.loads((out/'AGGREGATE_POSTPROCESSING_RESULTS.json').read_text()) if (out/'AGGREGATE_POSTPROCESSING_RESULTS.json').exists() else []
    for pp in postprocess:
        parent=json.loads((out/'research'/f"{pp['candidate']}_s{pp['seeds'][0]}"/'results.json').read_text())
        frontier.append(dict(id=pp['candidate']+'_'+pp['strategy'],kind='research_postprocessing',seeds=pp['seeds'],mean=pp['mean'],sample_sd=pp['sample_sd'],epsilon=parent['accounting']['epsilon'],config=dict(source_run=pp['candidate'],terminal_postprocessing=pp['strategy']),complete=sorted(pp['seeds'])==[42,52,62]))
    write(out/'PRIVACY_UTILITY_FRONTIER.json',frontier)
    write(out/'SEARCH_LOG.json',dict(status='complete' if args.finalist else 'in_progress',aggregate_postprocessing=postprocess,nonprivate_calibration='DECODER_CLIPPING_CALIBRATION.json',runs=[dict(id=r['run_id'],kind=r['kind'],seed=r['seed'],config=r['config'],selected=r['selected'],accounting=r['accounting'],result_path=r['result_path']) for r in runs]))
    fields=['id','kind','seed','macro_pr_auc','JPMorgan_Chase_pr_auc','Wells_Fargo_pr_auc','Key_Bank_pr_auc','precision','recall','f1','roc_auc','selected_round','executed_releases','epsilon','delta','checkpoint']
    with (out/'SEED_RESULTS.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fields,lineterminator="\n");writer.writeheader()
        for r in runs:
            row=dict(id=r['run_id'],kind=r['kind'],seed=r['seed'],macro_pr_auc=r['selected']['metrics']['pr_auc'],selected_round=r['selected']['round'],executed_releases=r['accounting']['releases'],epsilon=r['accounting']['epsilon'],delta=r['accounting']['delta'],checkpoint=r['selected_checkpoint'])
            row.update({bank['bank']+'_pr_auc':bank['validation']['pr_auc'] for bank in r['selected']['per_bank']})
            row.update({k:r['selected']['metrics'][k] for k in ('precision','recall','f1','roc_auc')});writer.writerow(row)
    if not args.finalist:return
    selected=groups[('production',args.finalist)];selected.sort(key=lambda r:r['seed']);assert [r['seed'] for r in selected]==[42,52,62]
    finalstats=stats(selected);assert finalstats['mean']>=.85
    baseline=Privacy(mode='distributed_dp',clip=6.5,multiplier=1e-5)
    b=dict(**baseline.parameters(242561),**baseline.accounting(4),multiplier=1e-5,rho_per_release=baseline.rho(),mode=baseline.mode)
    r=selected[0];privacy=Privacy(**r['privacy']);assert privacy.entropy=='production'
    f=dict(**r['parameters'],**r['accounting'],multiplier=privacy.multiplier,rho_per_release=privacy.rho(),mode=privacy.mode)
    assert f['epsilon']<=b['epsilon'] and f['delta']<=1e-6
    # Count spend-before-send reservations, including incomplete/failed attempts.
    b['encoded_share_sensitivity']=2*b['effective_clip'];f['encoded_share_sensitivity']=2*f['effective_clip']
    finite_rho=0.;spends=[]
    ledgers=list((out/'production').glob('*/ledger.sqlite3'))+list((out/'kafka_acceptance').glob('*/models/privacy-ledgers/central.sqlite3'))
    for dbpath in ledgers:
        db=sqlite3.connect(f'file:{dbpath}?mode=ro',uri=True)
        for run,rid,role,encoded in db.execute('SELECT run, round, role, config FROM spends WHERE round > 0'):
            pp=Privacy(**json.loads(encoded));rho=pp.rho();finite_rho+=rho
            spends.append(dict(ledger=str(dbpath),run=run,round=rid,role=role,rho=rho))
        db.close()
    write(out/'PRODUCTION_COMPOSITION.json',dict(reservations=spends,rho=finite_rho,epsilon=finite_rho+2*math.sqrt(finite_rho*math.log(1e6)),delta=1e-6,includes_failed_reservations=True))
    kafka=[]
    for pp in (out/'kafka_acceptance').glob('*/result.json'):
        kk=json.loads(pp.read_text());kcfg=json.loads((pp.parent/'run.json').read_text());kp=Privacy(**kcfg['privacy']);krho=kp.accounting(len(kk['rounds']))['rho'];kafka.append(dict(path=str(pp),result=kk['result'],rho=krho))
    historical=json.loads((ROOT/'artifacts/dp_level3_secagg/privacy_utility_frontier.json').read_text())['accounting']
    combined_rho=historical['private_experiment_and_kafka_rho']+finite_rho
    floor=dict(baseline=b,finalist=f,verdict='stronger' if f['epsilon']<b['epsilon'] else 'exactly equivalent',same_accountant=True,
               entropy='production',expected_clients=3,min_noise_contributors=3,parameter_field_note='In raw legacy manifests accounting_sensitivity is the mean sensitivity. Actual encoded-share accounting uses encoded_share_sensitivity=2*C_eff and sigma_share; rho_per_release=n/(2*m^2). Both are reported explicitly here.',
               threat_model='honest-but-curious coordinator; authenticated noncolluding protocol-following fixed cohort; all clients supply noise',
               scopes=dict(final_per_seed=f,historical_and_new_production_only=dict(rho=combined_rho,epsilon=combined_rho+2*math.sqrt(combined_rho*math.log(1e6)),delta=1e-6,historical_rho=historical['private_experiment_and_kafka_rho'],historical_source='artifacts/dp_level3_secagg/privacy_utility_frontier.json'),new_production_search_and_acceptance=dict(rho=finite_rho,epsilon=finite_rho+2*math.sqrt(finite_rho*math.log(1e6)),delta=1e-6),
               research_bundle='No finite end-to-end DP guarantee: deterministic research noise, nonprivate warm starts, original calibration and public validation/selection are included.'),
               caveats='Conservative encoded-share ideal-Gaussian bound; finite-precision sampler is not exact-DP certified. Incremental privacy conditional on nonprivate checkpoint; no end-to-end training claim.')
    write(out/'FINALIST_PRIVACY.json',floor)
    write(out/'FINALIST_RESULTS.json',dict(verdict='TARGET ACHIEVED',**finalstats,runs=selected,kafka=kafka))
    write(out/'CHECKPOINT_PROVENANCE.json',dict(starting=[dict(seed=x['seed'],path=x['checkpoint'],sha256=x['checkpoint_sha256']) for x in selected],
        retained=[dict(seed=x['seed'],path=x['selected_checkpoint'],sha256=x['selected']['sha256'],selected_round=x['selected']['round'],executed_releases=x['accounting']['releases']) for x in selected],
        all_round_checkpoints_retained=True,September_loaded=False))
    audit=json.loads((out/'INITIAL_AUDIT.json').read_text())
    unchanged=all((ROOT/k).is_file() and hashlib.sha256((ROOT/k).read_bytes()).hexdigest()==v for k,v in audit['historical_evidence_hashes'].items());assert unchanged
    sourcepaths=[* (ROOT/'distributed_federation').rglob('*.py'),* (ROOT/'src/gnn').glob('*.py'),* (ROOT/'scripts').glob('*utility*.py'),ROOT/'scripts/screen_aggregate_postprocessing.py',ROOT/'scripts/audit_final_kafka_wire.py',ROOT/'tests/test_utility_optimization.py']
    write(out/'SOURCE_MANIFEST.json',dict(starting_head=audit['head'],current_head=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),files={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sourcepaths)},historical_evidence_unchanged=unchanged,configuration_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [ROOT/'configs/privacy_level3_optimized.json',out/'FINALIST_CONFIG.json',out/'PRODUCTION_CONFIRMATION_PLAN.json']},production_sources=[dict(seed=x['seed'],hashes=x['source_hashes']) for x in selected]))
    lines=['# Level-3 utility optimization — final report','', '27 October 2026. Local work only; nothing pushed.','',
           f"**TARGET ACHIEVED: {finalstats['mean']:.6f} ± {finalstats['sample_sd']:.6f} macro August validation PR-AUC** across seeds 42, 52 and 62 (sample SD). These are private-continuation seeds from one fixed nonprivate pretraining checkpoint; see the explicit seed-scope statement below.",'',
           '## Starting baseline','',f"Reload-verified {audit['baseline_mean']:.6f} ± {audit['baseline_sample_sd']:.6f}. CausalTemporalGraphSAGE, 242,561 floating coordinates, fixed nonprivate warm starts, risk/account-context replay, equal secure mean, four private releases, C=6.5, multiplier=1e-5, delta=1e-6.",
           f"Conservative encoded-share epsilon: {b['epsilon']:.12g}. Exact checkpoint and source evidence: INITIAL_AUDIT.json, BASELINE_VERIFIED.json and baseline_reload_*.json.",'',
           '## Optimization evidence','',
           'All trials, including failures, appear below and in SEARCH_LOG.json. Screening uses deterministic research-only noise; these are not operational DP results. Only production-confirmed candidates establish success. Plans were saved before their associated runs. Selection always chooses highest equal-bank August AP, earliest round on a tie. All executed releases count, including those after an earlier selected checkpoint.','',
           '| Candidate | Phase | Seeds | Selected August AP mean ± sample SD | Epsilon per run |','|---|---|---|---:|---:|']
    for x in frontier:
        sd=f" ± {x['sample_sd']:.6f}" if x['sample_sd'] is not None else ' (single seed)'
        lines.append(f"| {x['id']} | {x['kind']} | {','.join(map(str,x['seeds']))} | {x['mean']:.6f}{sd} | {x['epsilon']:.8g} |")
    stagefile=out/'STAGE_DECISIONS.md'
    if stagefile.exists():lines+=['',stagefile.read_text()]
    lines+=['','## Final architecture','', 'The configuration is frozen in FINALIST_CONFIG.json; per-seed operational configs are retained next to it. Training uses the same trainer as independent Kafka workers. Model temporal state, replay and local optimizer remain inside each bank.', '', '```json',json.dumps(r['config'],indent=2),'```','',
            f"Trainable private dimension: {r['trainable_dimension']}; frozen keys: {242561-r['trainable_dimension']} coordinates. AdamW, June then July chronological risk/account-context replay; batch size 1024, TBPTT 2, local gradient norm cap 5 for stability. Full training settings: {json.dumps(r['training'],sort_keys=True)}.",
            '', '## Final three-seed utility','', '| Seed | Macro AP | JPMorgan AP | Wells Fargo AP | Key Bank AP | Precision | Recall | F1 | ROC-AUC | Selected round / releases |', '|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for x in selected:
        m=x['selected']['metrics'];banks={q['bank']:q['validation']['pr_auc'] for q in x['selected']['per_bank']}
        values=[x['seed'],f"{m['pr_auc']:.6f}",*[f'{banks[k]:.6f}' for k in ('JPMorgan_Chase','Wells_Fargo','Key_Bank')],*[f"{m[k]:.6f}" for k in ('precision','recall','f1','roc_auc')],f"{x['selected']['round']} / {x['accounting']['releases']}"]
        lines.append('| '+' | '.join(map(str,values))+' |')
    if '{seed}' not in r['config'].get('checkpoint_template','{seed}'):
        lines+=['', '**Seed scope:** all three runs use the same previously frozen, nonprivate August-selected checkpoint (pretraining seed 42). Seeds 42/52/62 independently control local continuation/replay randomness and each gets fresh production DP entropy. The reported SD measures continuation variance; it does not measure pretraining-seed variance. The original seed-specific starting-model results remain separate. The utility gain relies substantially on preserved nonprivate pretrained knowledge.']
    lines+=['', 'Precision/recall/F1 use each bank’s original August F1 threshold protocol. AP is sklearn average precision, averaged equally across banks; ordinary accuracy was never optimized.','',
            '## Privacy comparison','', '| Quantity | Baseline | Finalist |','|---|---:|---:|']
    for k in ('C','effective_clip','quantization_l2_bound','n','dimension','multiplier','sensitivity','encoded_share_sensitivity','sigma_mean','sigma_share','releases','rho_per_release','rho','epsilon','delta','expected_noise_l2'):
        lines.append(f'| {k} | {b[k]:.12g} | {f[k]:.12g} |')
    lines+=['', f"Privacy is **{floor['verdict']}** under the same conservative encoded-share accountant: rho per release = n/(2m²), epsilon = rho_total + 2 sqrt(rho_total ln(1/delta)). Quantization error is sqrt(d)/(2s), C_eff=C+error, mean sensitivity=2*C_eff/3 and sigma_share=sqrt(3)*sigma_mean. All three noise contributors remain mandatory, with production OS entropy. No clean aggregate reaches the coordinator.", '',floor['caveats'],'',
            f"New production experiments and Kafka acceptance compose to rho={finite_rho:.12g}, epsilon={floor['scopes']['new_production_search_and_acceptance']['epsilon']:.12g} at delta=1e-6. This includes all production-confirmed seeds/candidates and acceptance rounds, not only the retained models. Baseline reload consumes no new private release. Including the previous retained private-search rho of {historical['private_experiment_and_kafka_rho']:.12g}, the historical-plus-new production-only composition is rho={combined_rho:.12g}, epsilon={floor['scopes']['historical_and_new_production_only']['epsilon']:.12g} at the same delta. Historical source: artifacts/dp_level3_secagg/privacy_utility_frontier.json. Deterministic research screening and the complete research artifact bundle have no finite end-to-end DP guarantee.", '',
            '## Secure aggregation and Kafka','',
            'X25519 ephemeral keys, HKDF domain binding, ChaCha20 pair masks, exact uint64 ring cancellation, authenticated SHA/HMAC transport, schema/base binding, complete cohort, duplicate/stale rejection and fail-closed operation remain active. Server optimizer state derives only from the noisy secure aggregate. No private keys, shared secrets, mask seeds, clean client updates or Gaussian realization vectors are retained.', '','```json',json.dumps(kafka,indent=2),'```','',
            '## Tests and separate QA passes','', 'See TEST_REPORT.txt and QA_REPORT.md for the complete final regression, smoke, checkpoint reload and separate model/privacy/crypto/statistical/distributed/regression reviews. These are review passes, not an external security certification.','',
            '## Artifacts and reproduction','',
            'FINALIST_CONFIG.json; FINALIST_PRIVACY.json; FINALIST_RESULTS.json; SEED_RESULTS.csv; PRIVACY_UTILITY_FRONTIER.json; SEARCH_LOG.json; QA_REPORT.md; TEST_REPORT.txt; SOURCE_MANIFEST.json; CHECKPOINT_PROVENANCE.json. Every round checkpoint remains under research/ or production/. The production plan is frozen before execution. Exact retained metrics are reproduced by checkpoint reload; fresh private entropy intentionally changes new training trajectories.','',
            'Use the existing interpreter /Users/pj/Desktop/college/capstone/Capstone/.venv/bin/python. Run scripts/confirm_utility_finalists.py --plan artifacts/dp_level3_utility_optimization/PRODUCTION_CONFIRMATION_PLAN.json --output /absolute/path/to/NEW_output_directory. Do not overwrite completed evidence. Use scripts/evaluate_private_federation.py to reload any retained checkpoint. No dataset downloads, copies, regeneration or September evaluation occurred.','',
            '## Git state','',f"Branch {audit['branch']}; starting HEAD {audit['head']}. Historical Level-3 evidence hashes remain unchanged. Final status is recorded in FINAL_GIT_STATE.json. Nothing was pushed.",'',
            '## Presentation-safe statement','',
            f"The optimized three-bank Level-3 federated system retains secure aggregation and distributed differential privacy while achieving {finalstats['mean']:.4f} ± {finalstats['sample_sd']:.4f} macro August validation PR-AUC across private-continuation seeds 42, 52 and 62 from one fixed nonprivate warm start. The retained per-run privacy budget is {floor['verdict']} relative to the previous Level-3 configuration under the same conservative encoded-share accounting, with three required noise contributors and delta 1e-6. This is incremental privacy conditional on a nonprivately trained warm start; the large epsilon bound does not establish practically strong or end-to-end differential privacy.", '']
    (out/'FINAL_REPORT.md').write_text('\n'.join(lines))

if __name__=='__main__':main()
