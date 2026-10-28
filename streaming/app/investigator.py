"""Measured investigator evidence for the exact completed operational replay.

This adapter uses the existing selected-model runtime and approved XAI helpers.
It never loads the standalone dashboard checkpoint, trains, or samples DP noise.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path

from .final_model import REPO, MODEL_KIND, SCHEMA, validate_selected, digest

TOLERANCE = 1e-6
BATCH_SIZE = 1024
HISTORY_BATCHES = 8
MAX_HISTORY_TESTS = 8
SCHEMA_VERSION = 'aml-investigator-replay-v1'


def hash_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def require_score(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f'Invalid {name}; a verified replay score is required.')
    return float(value)


def model_provenance(selected, bank):
    """Validate the actual files, ensemble signature and declared privacy scope."""
    if selected.get('bank', bank) != bank:
        raise ValueError('The replay model belongs to another bank.')
    validate_selected(selected)
    kind = selected['model_kind']
    manifest = {}
    if kind == MODEL_KIND:
        if hash_json(selected['members']) != selected['sha256']:
            raise ValueError('The replay ensemble fingerprint differs from its members.')
        members = copy.deepcopy(selected['members'])
        if selected.get('privacy', {}).get('differential_privacy'):
            raise ValueError('This reference/adapted ensemble has no DP guarantee.')
    else:
        path = Path(selected['checkpoint'])
        manifest = json.loads(path.with_suffix('.json').read_text())
        private = bool(manifest.get('schema', {}).get('privacy', {}).get('differential_privacy'))
        if bool(selected.get('privacy', {}).get('differential_privacy')) != private:
            raise ValueError('The selected model privacy claim differs from its verified checkpoint.')
        member_seed=manifest.get('schema',{}).get('training_protocol',{}).get('seed')
        members = [dict(seed=member_seed, checkpoint=str(path), sha256=selected['sha256'])] if kind == 'federated_single' else []
    mode = 'none' if not selected.get('privacy', {}).get('differential_privacy') else 'unverified_private_scope'
    if mode != 'none':
        from .final_federation import PRIVACY, FIXED, SERVER
        protocol = manifest.get('schema', {}).get('training_protocol', {})
        privacy = manifest.get('privacy', {})
        canonical = (kind == 'federated_single' and all(privacy.get(k) == v for k, v in PRIVACY.items())
                     and all(protocol.get(k) == FIXED[k] for k in ('seed','rounds','local_epochs','private_subset','batch_size','replay','replay_size'))
                     and protocol.get('server_optimizer') == SERVER and manifest.get('aggregation_method') == 'secure_equal'
                     and manifest.get('mechanism_parameters', {}).get('dimension') == 65793)
        if not canonical:
            raise ValueError('This private checkpoint does not have the verified canonical Level-3 explanation contract.')
        mode = 'level3'
    return dict(family=kind, seed=manifest.get('schema',{}).get('training_protocol',{}).get('seed') if kind == 'federated_single' else '42/52/62',
                model_count=1 if kind == 'federated_single' else 3,
                checkpoint_sha256=selected['sha256'], checkpoint_members=members,
                preprocessing_sha256=digest(REPO / SCHEMA), privacy_mode=mode,
                model_role='reference' if selected.get('reference') else 'verified_selected',
                best_round=manifest.get('round_id'), selected_model=copy.deepcopy(selected),
                checkpoint_manifest=manifest, evaluation_split='validation', test_loaded=False,
                source_ref='operational selected replay', model_source_sha256=digest(REPO/'src/gnn/causal_temporal_graphsage.py'))


def implementation_hashes():
    names = ['streaming/app/investigator.py','streaming/app/explanations.py',
             'xai/src/grouped_features.py','xai/src/ensemble_explainer.py',
             'xai/src/transaction_story.py','xai/src/counterfactuals.py']
    return {name: digest(REPO/name) for name in names}


def cache_inputs(replay, rows, row, provenance, rows_sha256):
    return dict(schema=SCHEMA_VERSION, bank=replay['bank'], transaction_id=str(row['txn_id']),
                replay_id=replay['id'], seed=provenance['seed'], checkpoint_sha256=provenance['checkpoint_sha256'],
                model_descriptor_sha256=hash_json(replay['model']), model_count=provenance['model_count'], privacy_mode=provenance['privacy_mode'],
                preprocessing_sha256=provenance['preprocessing_sha256'],
                reference_prediction_sha256=rows_sha256, dataset_fingerprint=replay['dataset_fingerprint'],
                threshold=require_score(rows['threshold'], 'saved cutoff'), expected_score=require_score(row['score'], 'saved score'),
                background_size=32, history_batches=HISTORY_BATCHES, max_history_tests=MAX_HISTORY_TESTS,
                implementation_sha256=implementation_hashes())


def validate_report(report, job):
    """Fail closed on stale jobs, mismatched models, thresholds, data or scores."""
    try:
        key = job['cache_key_inputs']
        p, f, v = report['prediction'], report['feature_explanation'], report['verification']
        provenance=report['xai_provenance']; transfer=report['transaction_story']['selected_transfer']
        expected = require_score(job['expected_score'], 'saved score')
        if (report['cache_key'] != hash_json(key) or report['cache_key_inputs'] != key
                or report['bank'] != job['bank'] or str(report['transaction_id']) != job['txn_id']
                or report['replay_id'] != job['replay_id']
                or report['model']['checkpoint_sha256'] != job['model']['sha256']
                or report['model']['model_count'] != key['model_count']
                or report['model']['family'] != job['model']['model_kind']
                or report['model']['seed'] != key['seed']
                or provenance['checkpoint_sha256'] != job['model']['sha256']
                or provenance['selected_model'] != job['model']
                or provenance['preprocessing_sha256'] != key['preprocessing_sha256']
                or provenance['privacy_mode'] != key['privacy_mode']
                or provenance['banks'][job['bank']]['threshold'] != key['threshold']
                or report['replay_provenance']['saved_rows_sha256'] != key['reference_prediction_sha256']
                or report['replay_provenance']['dataset_fingerprint'] != job['dataset_fingerprint']
                or v['explained_checkpoint_sha256'] != job['model']['sha256']
                or str(transfer['transaction_id']) != job['txn_id']
                or any(str(transfer[k])!=str(job['expected_transfer'][v]) for k,v in [('source_account_id','source'),('target_account_id','target'),('timestamp','timestamp')])
                or p['threshold'] != key['threshold'] or v['tolerance'] != TOLERANCE or v['passed'] is not True):
            raise ValueError('Explanation identity, model, data or saved cutoff differs from the selected replay.')
        for score in [p['probability'], f['target_probability'], v['existing_evaluation_probability'],
                      v['direct_model_probability'], v['xai_probability']]:
            if abs(require_score(score, 'explanation target') - expected) > TOLERANCE:
                raise ValueError('Explanation score differs from the saved replay by more than 1e-6. Rescore this model.')
        if p['class'] != ('fraud' if expected >= key['threshold'] else 'not_fraud'):
            raise ValueError('Explanation decision differs from the saved replay.')
    except (KeyError, TypeError) as exc:
        raise ValueError('This explanation is incomplete or obsolete. Request a new verified explanation.') from exc
    return report


def explain_replay(job):
    import numpy as np
    import pandas as pd
    import torch
    from src.gnn import causal_temporal_graphsage as g
    from xai.src.grouped_features import explain_groups
    from xai.src.ensemble_explainer import ensemble_logit_predictor, member_probability_details
    from xai.src.counterfactuals import constrained_amount_counterfactuals
    from xai.src.transaction_story import build_transaction_story, completed_history
    from .final_model import load_runtime
    from .local_training import check_dataset

    dataset, bank = Path(job['dataset']), job['bank']
    if check_dataset(dataset, bank)['fingerprint'] != job['dataset_fingerprint']:
        raise ValueError('Replay data has changed. Score a new replay before explaining it.')
    provenance = model_provenance(job['model'], bank)
    if provenance['checkpoint_sha256'] != job['cache_key_inputs']['checkpoint_sha256']:
        raise ValueError('Replay checkpoint changed.')
    models, static, streams, encoder = load_runtime(job['model'], dataset, bank)
    if len(models) != provenance['model_count']:
        raise ValueError('Loaded model count differs from the selected replay.')
    frames, maps = {}, []
    for split in ('training', 'validation'):
        frame = pd.read_csv(dataset/split/bank/'edge_list.csv.gz')
        frame = frame.iloc[np.argsort(pd.to_datetime(frame.timestamp).to_numpy(), kind='stable')].reset_index(drop=True)
        if len(frame) != len(streams[split]):
            raise ValueError('Replay events do not align with the transaction rows.')
        frame['src_node'] = streams[split].src.cpu().numpy()
        frame['dst_node'] = streams[split].dst.cpu().numpy()
        frame['y'] = streams[split].labels.cpu().numpy()
        frames[split] = frame
        maps.append(pd.read_csv(dataset/split/bank/'node_map.csv.gz')['account_id'])
    accounts = {i: str(value) for i, value in enumerate(pd.concat(maps,ignore_index=True).drop_duplicates().tolist())}
    indices = np.flatnonzero(frames['validation'].txn_id.astype(str).to_numpy() == job['txn_id'])
    if len(indices) != 1:
        raise ValueError('Transaction ID is missing or ambiguous in this replay.')
    index = int(indices[0]); row = frames['validation'].iloc[index]
    selected_event = streams['validation']; batch_start = index//BATCH_SIZE*BATCH_SIZE
    descriptors = []
    for split, stop in [('training',len(frames['training'])), ('validation',batch_start)]:
        descriptors += [(split,start,min(start+BATCH_SIZE,stop)) for start in range(0,stop,BATCH_SIZE)]
    anchor_index = max(0,len(descriptors)-HISTORY_BATCHES)

    def batch(split,start,stop,removed=None):
        stream=streams[split]
        values=[v[start:stop] for v in (stream.src,stream.dst,stream.edge_attr,stream.timestamp,stream.labels)]
        if removed is not None:
            keep=torch.from_numpy(frames[split].iloc[start:stop].txn_id.astype(str).to_numpy()!=str(removed))
            values=[v[keep] for v in values]
        return g.Events(*values)

    def member_predictor(model,state):
        source=state.memory[selected_event.src[index]].clone(); target=state.memory[selected_event.dst[index]].clone()
        def predict(rows):
            with torch.no_grad():
                edge=model.edge_projection(torch.from_numpy(encoder.transform(rows)))
                src=source.expand(len(rows),-1); dst=target.expand(len(rows),-1)
                return model.decoder(torch.cat((src,dst,torch.abs(src-dst),edge),dim=1)).squeeze(1).cpu().numpy()
        return predict

    predictors, anchors = [], []
    with torch.no_grad():
        for model in models:
            state=model.initial_state(static)
            for i,(split,start,stop) in enumerate(descriptors):
                if i==anchor_index:anchors.append(state.detached())
                _,state=model.score_and_update(state,batch(split,start,stop))
            if anchor_index==len(descriptors):anchors.append(state.detached())
            predictors.append(member_predictor(model,state))
    predictor=predictors[0] if len(models)==1 else ensemble_logit_predictor(predictors)

    def probabilities(functions):
        values=[float(1/(1+np.exp(-np.clip(float(np.asarray(fn(pd.DataFrame([row]))).reshape(-1)[0]),-40,40)))) for fn in functions]
        return values,float(np.mean(values))

    members,direct=probabilities(predictors)
    expected=require_score(job['expected_score'],'saved score')
    if abs(direct-expected)>TOLERANCE:
        raise ValueError('Explanation score does not match the saved replay within 1e-6. Rescore this model.')
    feature=explain_groups(predictor,row,frames['training'],background_size=32)
    if abs(feature['target_probability']-expected)>TOLERANCE:
        raise ValueError('Grouped explanation target differs from the saved replay by more than 1e-6.')
    threshold=job['cache_key_inputs']['threshold']
    history=completed_history(frames['training'],frames['validation'],index,BATCH_SIZE)
    # The same approved story builder defines eligible relationships and display scope.
    provisional={'prediction':{'probability':expected},'feature_explanation':feature}
    story=build_transaction_story(row,history,provisional,account_ids=accounts)
    original_transfer=story['selected_transfer']
    if any(str(original_transfer[k])!=str(job['expected_transfer'][v]) for k,v in [('source_account_id','source'),('target_account_id','target'),('timestamp','timestamp')]):
        raise ValueError('Transaction account IDs or timestamp differ from the saved replay.')

    def replay(removed=None):
        functions=[]
        with torch.no_grad():
            for model,anchor in zip(models,anchors):
                state=anchor
                for split,start,stop in descriptors[anchor_index:]:
                    events=batch(split,start,stop,removed)
                    if len(events):_,state=model.score_and_update(state,events)
                functions.append(member_predictor(model,state))
        return probabilities(functions)

    baseline_members,baseline=replay()
    baseline_error=max([abs(baseline-direct)]+[abs(a-b) for a,b in zip(baseline_members,members)])
    if baseline_error>TOLERANCE:raise ValueError('Unperturbed historical replay failed the 1e-6 parity guard.')
    window_ids={str(tx) for split,start,stop in descriptors[anchor_index:] for tx in frames[split].iloc[start:stop].txn_id}
    candidates=[e for e in reversed(story['eligible_earlier_transfers']) if e['transaction_id'] in window_ids][:MAX_HISTORY_TESTS]
    edges=[]
    for event in candidates:
        without_members,without=replay(event['transaction_id'])
        edges.append(dict(transaction_id=event['transaction_id'],source=event['source'],target=event['target'],timestamp=event['timestamp'],
                          probability_without=without,delta_probability=without-direct,importance=abs(without-direct),
                          member_probabilities_without=without_members,verified_model_count=len(models)))
    graph=dict(method='bounded_chronological_replay_of_selected_predictor',window_batches=HISTORY_BATCHES,
               window_event_count=sum(stop-start for _,start,stop in descriptors[anchor_index:]),
               selection='up to eight most recent eligible endpoint transfers within the last eight completed model batches',
               important_edges=edges,important_nodes=[],fidelity=dict(original_probability=direct,unperturbed_replay_error=baseline_error,
               baseline_member_probabilities=baseline_members),limitations='One update suppressed per test; pre-window memory retained. Not GNNExplainer or causal proof.')
    report=dict(schema_version=4,bank=bank,transaction_id=job['txn_id'],replay_id=job['replay_id'],split='validation',
                prediction=dict(probability=expected,threshold=threshold,**{'class':'fraud' if expected>=threshold else 'not_fraud'},
                                threshold_selection='saved selected-model cutoff captured in this completed replay; no threshold fitting'),
                evaluation_label='fraud' if int(row['y']) else 'not_fraud',feature_explanation=feature,graph_explanation=graph,
                model={k:provenance[k] for k in ('family','seed','model_count','checkpoint_sha256','best_round')},
                counterfactual_explanation=constrained_amount_counterfactuals(row,frames['training'],predictor,threshold=threshold),
                cache_key=job['cache_key'],cache_key_inputs=job['cache_key_inputs'],
                verification=dict(existing_evaluation_probability=expected,direct_model_probability=direct,xai_probability=feature['target_probability'],
                                  tolerance=TOLERANCE,passed=True,explained_checkpoint_sha256=job['model']['sha256'],
                                  absolute_errors=dict(saved_vs_direct=abs(expected-direct),saved_vs_target=abs(expected-feature['target_probability'])),
                                  saved_threshold_used=True,model_count=len(models)),
                replay_provenance=dict(replay_id=job['replay_id'],dataset_fingerprint=job['dataset_fingerprint'],
                                       saved_rows_sha256=job['cache_key_inputs']['reference_prediction_sha256'],member_probabilities=members,
                                       batch_size=BATCH_SIZE,target_index=index,completed_validation_rows=batch_start),
                limitations=['Model scores are uncalibrated; explanations do not prove fraud or transaction purpose.',
                             'Local transaction explanations and histories do not inherit a model DP guarantee.',
                             'Grouped attribution holds pre-batch account memory fixed; replay suppresses bounded historical updates only.'])
    report['transaction_story']=build_transaction_story(row,history,report,account_ids=accounts)
    for effect in report['transaction_story']['model_link_effects']:
        edge=next(e for e in edges if e['transaction_id']==effect['transaction_id'])
        if len(edge['member_probabilities_without'])!=len(models):raise ValueError('Incomplete ensemble replay test.')
        effect.update(verified_model_count=len(models),scope='one earlier update suppressed separately in every selected model member; pre-window account memory retained')
    visible=[e for e in report['transaction_story']['transfers'] if e['kind']=='earlier']
    tested={e['transaction_id'] for e in report['transaction_story']['model_link_effects']}
    report['evaluation_checks']=dict(faithfulness=dict(groups=[dict(group=f['feature'],shap_logit=f['shap_logit'],reference_ablation_logit_drop=f['ablation_logit_drop'],
        direction_agrees=bool(abs(f['shap_logit'])<1e-7 or f['shap_logit']*f['ablation_logit_drop']>=0)) for f in feature['features']]),
        stability=None,temporal_replay=dict(baseline_error=baseline_error,tested_events=len(edges),member_count=len(models),scope=graph['selection']),
        coverage=dict(displayed_history_edges=len(visible),verified_displayed_edges=sum(e['transaction_id'] in tested for e in visible)))
    provenance.update(banks={bank:dict(threshold=threshold)},threshold_policy=report['prediction']['threshold_selection'],
                      reference_prediction_sha256={bank:job['cache_key_inputs']['reference_prediction_sha256']},
                      implementation_sha256=job['cache_key_inputs']['implementation_sha256'])
    report['xai_provenance']=provenance
    if check_dataset(dataset,bank)['fingerprint']!=job['dataset_fingerprint']:raise ValueError('Dataset changed during explanation.')
    model_provenance(job['model'],bank)  # Files and metadata must still match after computation.
    return validate_report(report,job)
