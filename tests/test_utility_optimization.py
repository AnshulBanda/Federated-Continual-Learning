"""Regression guards for aggregate-only optimization and experiment selection."""
import copy
import importlib.util
import inspect
import math
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import pytest
import torch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src/gnn')]
from distributed_federation.privacy.server_optimizer import ServerConfig,ServerOptimizer
from distributed_federation.privacy.mechanism import Privacy,client_contribution,aggregate,vector
spec=importlib.util.spec_from_file_location('utility',ROOT/'scripts/optimize_private_utility.py')
utility=importlib.util.module_from_spec(spec);spec.loader.exec_module(utility)


def test_fedavg_and_momentum_hand_calculation_aggregate_only():
    base={'w':torch.tensor([1.,2.])};released={'w':torch.tensor([3.,1.])}
    torch.testing.assert_close(ServerOptimizer().apply(base,released)['w'],released['w'],rtol=0,atol=0)
    opt=ServerOptimizer(ServerConfig('fedavgm',.5,.5))
    first=opt.apply(base,released)
    torch.testing.assert_close(first['w'],torch.tensor([2.,1.5]))
    second=opt.apply(first,{'w':first['w']+torch.tensor([1.,2.])})
    torch.testing.assert_close(second['w'],torch.tensor([3.,2.25]))
    assert list(inspect.signature(opt.apply).parameters)==['base','noisy_aggregate']
    assert all('client' not in k for k in vars(opt))


@pytest.mark.parametrize('kind',['fedadam','fedyogi'])
def test_adaptive_optimizer_matches_independent_recurrence(kind):
    opt=ServerOptimizer(ServerConfig(kind,.03,.8,.9,.001));base={'w':torch.zeros(2)}
    m=np.zeros(2);v=np.zeros(2);x=np.zeros(2)
    for delta in (np.array([1.,-2.]),np.array([.5,3.]),np.array([-.2,.1])):
        m=.8*m+.2*delta
        v=.9*v+.1*delta**2 if kind=='fedadam' else v-.1*delta**2*np.sign(v-delta**2)
        x=x+.03*m/(np.sqrt(v)+.001)
        base=opt.apply(base,{'w':base['w']+torch.tensor(delta,dtype=torch.float32)})
        np.testing.assert_allclose(base['w'].numpy(),x,rtol=2e-6,atol=1e-7)
    assert np.all(v>=0)


def test_privacy_floor_counts_all_executed_releases():
    p=Privacy(mode='distributed_dp',clip=6.5,multiplier=1e-5)
    utility.assert_floor(p,4)
    with pytest.raises(ValueError):utility.assert_floor(p,5)
    with pytest.raises(ValueError):utility.assert_floor(Privacy(mode='distributed_dp',multiplier=9e-6),4)
    utility.assert_floor(Privacy(mode='distributed_dp',multiplier=math.sqrt(2)*1e-5),8)
    history=[dict(round=1,metrics=dict(pr_auc=.9)),dict(round=2,metrics=dict(pr_auc=.8)),dict(round=3,metrics=dict(pr_auc=.9))]
    assert utility.select(history)['round']==1
    assert p.accounting(len(history))['releases']==3
    assert p.accounting(3)['epsilon']>p.accounting(1)['epsilon']


def test_subset_reconstruction_noise_dimension_and_frozen_modules():
    from causal_temporal_graphsage import CausalTemporalGraphSAGE
    model=CausalTemporalGraphSAGE(3,2,4,.25)
    base={k:v.detach().clone() for k,v in model.state_dict().items()}
    keys=utility.private_keys(base,'decoder')
    for name,param in model.named_parameters():param.requires_grad_(name in keys)
    assert all(p.requires_grad==n.startswith('decoder.') for n,p in model.named_parameters())
    small={k:base[k] for k in keys};local={k:small[k]+.01 for k in keys}
    p=Privacy(mode='distributed_dp',clip=2,multiplier=.1,entropy='research')
    dimensions=[]
    def noise(d,*a):dimensions.append(d);return np.zeros(d)
    with patch('distributed_federation.privacy.mechanism.gaussian',side_effect=noise):
        outgoing=[client_contribution(local,small,p,'r',1,c) for c in 'abc']
    d=sum(v.numel() for v in small.values())
    assert dimensions==[d]*3
    result=aggregate(outgoing,small,p,'r',1)
    model.load_state_dict({**base,**result},strict=True)
    for k,v in model.state_dict().items():
        if k not in keys:assert torch.equal(v,base[k])
    assert p.parameters(d)['dimension']==d<sum(v.numel() for v in base.values())
    assert p.parameters(d)['quantization_l2_bound']==math.sqrt(d)/(2*p.scale)


def test_three_seed_macro_and_sample_sd():
    from statistics import mean,stdev
    bank_ap=[[.7,.8,.9],[.8,.9,1.],[.9,.8,.85]]
    scores=[utility.summary([dict(validation={k:v for k in ('pr_auc','precision','recall','f1','roc_auc')}) for v in bank])['pr_auc'] for bank in bank_ap]
    assert mean(scores)==pytest.approx(.85)
    assert stdev(scores)==pytest.approx(.05)


def test_local_config_changes_are_honored_and_worker_matches():
    import adaptive_continual_federated as research
    from causal_temporal_graphsage import CausalTemporalGraphSAGE,Events
    from distributed_federation.common.model_runtime import RuntimeData,train_local
    torch.set_num_threads(1);torch.manual_seed(3)
    static=torch.randn(4,3)
    events=Events(torch.arange(24)%4,(torch.arange(24)+1)%4,torch.randn(24,2),torch.arange(24).float(),torch.tensor([float(i%5==0) for i in range(24)]))
    model=CausalTemporalGraphSAGE(3,2,4,.25);ref=copy.deepcopy(model)
    cfg=SimpleNamespace(local_epochs=2,learning_rate=.0005,batch_size=3,replay_size=6,replay='risk_context',distill=0.,rng_policy='per_client',seed=42,dataset_dir=Path('unused'),clients=[SimpleNamespace(bank='a')],weight_decay=.0003,negative_ratio=10)
    research.train_client(ref,static,events,12.,cfg,242)
    with patch.object(research,'calendar_boundary',return_value=12.):train_local(RuntimeData(model,static,{'training':events},{},'x'),cfg,2,0)
    for k,v in ref.state_dict().items():assert torch.equal(v,model.state_dict()[k])


def test_public_counter_rng_has_domains_and_worker_parity():
    import adaptive_continual_federated as research
    from causal_temporal_graphsage import CausalTemporalGraphSAGE,Events
    from distributed_federation.common.model_runtime import RuntimeData,train_local
    assert len({research.public_training_seed(242,p,e) for p in ('june_dropout','june_sampling','july_dropout','july_sampling') for e in (0,1)})==8
    assert research.public_training_seed(242,'june_dropout',0)!=research.public_training_seed(243,'june_dropout',0)
    torch.set_num_threads(1);torch.manual_seed(3)
    static=torch.randn(4,3);events=Events(torch.arange(24)%4,(torch.arange(24)+1)%4,torch.randn(24,2),torch.arange(24).float(),torch.tensor([float(i%5==0) for i in range(24)]))
    model=CausalTemporalGraphSAGE(3,2,4,.25);ref=copy.deepcopy(model)
    cfg=SimpleNamespace(local_epochs=2,learning_rate=.001,batch_size=3,replay_size=6,replay='risk_context',distill=0.,rng_policy='counter',seed=42,dataset_dir=Path('unused'),clients=[SimpleNamespace(bank='a')])
    research.train_client(ref,static,events,12.,cfg,242)
    torch.rand(971) # unrelated process RNG consumption must not affect the worker
    with patch.object(research,'calendar_boundary',return_value=12.):train_local(RuntimeData(model,static,{'training':events},{},'x'),cfg,2,0)
    for k,v in ref.state_dict().items():assert torch.equal(v,model.state_dict()[k])


@pytest.mark.parametrize('subset',['decoder','temporal_decoder','message_decoder'])
def test_actual_local_training_freezes_subset_and_secure_transport_reconstructs(subset):
    import adaptive_continual_federated as research
    from causal_temporal_graphsage import CausalTemporalGraphSAGE,Events
    from distributed_federation.privacy.subset import configure_trainable,extract,reconstruct
    from distributed_federation.privacy.secagg import ClientKey,Round,context,pack,canonical
    import hashlib
    torch.set_num_threads(1);torch.manual_seed(12)
    static=torch.randn(4,3);events=Events(torch.arange(24)%4,(torch.arange(24)+1)%4,torch.randn(24,2),torch.arange(24).float(),torch.tensor([float(i%5==0) for i in range(24)]))
    model=CausalTemporalGraphSAGE(3,2,4,.25);base=copy.deepcopy(model.state_dict());keys=configure_trainable(model,subset)
    cfg=SimpleNamespace(local_epochs=2,learning_rate=.001,batch_size=3,replay_size=6,replay='risk_context',distill=0.,rng_policy='per_client')
    research.train_client(model,static,events,12.,cfg,242)
    for k,v in model.state_dict().items():
        if k not in keys:assert torch.equal(v,base[k])
    small=extract(base,subset);d=len(vector(small));p=Privacy(mode='distributed_dp',clip=6.5,multiplier=1e-5,entropy='research')
    ctx=context('subset',1,'abc','s','b',d);receiver=Round(ctx);clientkeys={c:ClientKey(c,ctx) for c in 'abc'}
    for c,key in clientkeys.items():receiver.add_key(key.hello(),c)
    meta={**ctx,'secagg_context_sha256':hashlib.sha256(canonical(ctx)).hexdigest(),'roster_sha256':hashlib.sha256(receiver.roster()).hexdigest()}
    for c,key in clientkeys.items():
        value=client_contribution(extract(model.state_dict(),subset),small,p,'subset',1,c)
        receiver.add_update(c,pack(key.mask(value,receiver.keys)),meta)
    released=aggregate(receiver.complete(),small,p,'subset',1);full=reconstruct(base,released,subset)
    assert len(vector(released))==p.parameters(d)['dimension']==d
    for k in base:
        if k not in keys:assert torch.equal(full[k],base[k])
    model.load_state_dict(full,strict=True)
    with pytest.raises(ValueError):reconstruct(base,{**released,'bad':torch.zeros(1)},subset)


def test_terminal_average_is_single_run_postprocessing_and_preserves_frozen():
    from distributed_federation.privacy.postprocessing import terminal_average
    states=[dict(w=torch.tensor([x]),frozen=torch.tensor([.1234567])) for x in (1.,3.,5.,9.)]
    assert terminal_average(states,'mean_last2',['w'])['w'].item()==7.
    assert terminal_average(states,'mean_all',['w'])['w'].item()==4.5
    assert terminal_average(states,'ema_half',['w'])['w'].item()==6.25
    assert torch.equal(terminal_average(states,'mean_last3',['w'])['frozen'],states[0]['frozen'])
    privacy=Privacy(mode='distributed_dp',multiplier=1e-5)
    assert privacy.accounting(len(states))['releases']==4
    bad=copy.deepcopy(states);bad[-1]['frozen']+=1
    with pytest.raises(ValueError):terminal_average(bad,'mean_all',['w'])


def test_retained_operational_candidate_meets_exact_privacy_floor():
    from distributed_federation.common.config import load_config
    cfg=load_config(ROOT/'configs/privacy_level3_optimized.json')
    assert cfg.privacy.mode=='distributed_dp' and cfg.privacy.secure
    assert cfg.privacy.entropy=='production'
    assert cfg.privacy.min_noise_contributors==cfg.privacy.expected_clients==len(cfg.clients)==3
    assert cfg.privacy.delta==1e-6
    assert cfg.private_subset=='decoder' and cfg.rounds==1
    utility.assert_floor(cfg.privacy,cfg.rounds)
    from causal_temporal_graphsage import CausalTemporalGraphSAGE
    model=CausalTemporalGraphSAGE(57,32,128,.25)
    from distributed_federation.privacy.subset import extract
    dimension=len(vector(extract(model.state_dict(),cfg.private_subset)))
    assert dimension==65793
    p=cfg.privacy.parameters(dimension)
    assert p['effective_clip']==pytest.approx(1.25+math.sqrt(dimension)/(2*2**24))
    assert p['sigma_share']==pytest.approx(p['sigma_mean']*math.sqrt(3))
    assert cfg.privacy.accounting(1)['epsilon']==pytest.approx(127.36375184207253)
