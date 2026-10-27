"""Bank-local continual adaptation of all three final ensemble members."""
import copy
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

from .final_model import REPO, SEEDS, MODEL_KIND, reference_model, load_runtime, score_models, digest
from .local_training import write_json


def train_ensemble(job, folder, update, check):
    import numpy as np
    import torch
    from src.gnn import causal_temporal_graphsage as g
    if str(REPO/'src/gnn') not in sys.path: sys.path.insert(0, str(REPO/'src/gnn'))
    from adaptive_continual_federated import train_client, calendar_boundary, fast_choose_threshold
    selected = reference_model(job['bank'])
    models, static, streams, _ = load_runtime(selected, job['dataset'], job['bank'])
    cfg = SimpleNamespace(local_epochs=3, replay='risk_context', replay_size=2000, distill=0,
                          batch_size=1024, learning_rate=.001, rng_policy='per_client')
    boundary = calendar_boundary(Path(job['dataset']), job['bank'])
    member_info, predictions, summaries = [], [], []
    for index, (seed, model) in enumerate(zip(SEEDS, models)):
        check()
        before, labels, _ = score_models([model], static, streams, check)
        baseline_ap = g.metric_block(labels, before, .5)['pr_auc']
        original = copy.deepcopy(model.state_dict())
        def progress(task, epoch):
            check()
            done = index * 6 + (3 if task.startswith('July') else 0) + epoch
            update(epoch=done, detail=f'Seed {seed} · {task} · epoch {epoch}/3')
        diagnostics = train_client(model, static, streams['training'], boundary, cfg, seed,
                                   check_cancel=check, progress=progress)
        after, labels, _ = score_models([model], static, streams, check)
        candidate_ap = g.metric_block(labels, after, .5)['pr_auc']
        retained = candidate_ap <= baseline_ap
        if retained:
            model.load_state_dict(original); after = before
        predictions.append(after)
        path = folder / f'seed_{seed}.pt'
        torch.save(dict(state_dict=model.state_dict(), args=dict(hidden_channels=128, dropout=.25,
                   batch_size=1024, seed=seed), protocol='bank_local_context_replay',
                   baseline_retained=retained), path)
        member_info.append(dict(seed=seed, checkpoint=str(path), sha256=digest(path)))
        summaries.append(dict(seed=seed, baseline_pr_auc=baseline_ap, candidate_pr_auc=candidate_ap,
                              baseline_retained=retained, replay=diagnostics))
        update(member_results=summaries)
    probabilities = np.mean(np.asarray(predictions, dtype=np.float64), axis=0)
    threshold = fast_choose_threshold(labels, probabilities)
    metrics = dict(bank=job['bank'], validation=g.metric_block(labels, probabilities, threshold),
                   threshold=threshold, alert_metrics=g.alert_budget_metrics(labels, probabilities, [10,25,50]),
                   members=summaries, test_loaded=False, protocol='bank_local_context_replay_ensemble')
    selected = dict(bank=job['bank'], version='Local ensemble · '+job['id'][:8], model_kind=MODEL_KIND,
                    members=member_info, reference=False, threshold=threshold, validation=metrics['validation'],
                    privacy=dict(differential_privacy=False, accounting=None))
    selected['sha256'] = hashlib.sha256(json.dumps(member_info, sort_keys=True).encode()).hexdigest()
    write_json(folder/'ensemble.json', selected)
    return metrics, selected
