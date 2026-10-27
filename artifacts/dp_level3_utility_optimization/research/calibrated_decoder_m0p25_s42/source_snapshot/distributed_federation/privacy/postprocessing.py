"""Single-model averaging of public checkpoints from the SAME accounted run."""
import torch

STRATEGIES=('mean_last2','mean_last3','mean_all','ema_half')


def terminal_average(released_checkpoints,strategy,private_keys):
    if strategy not in STRATEGIES or not released_checkpoints:
        raise ValueError('Invalid terminal average')
    states=released_checkpoints
    base=states[0]
    if any(set(s)!=set(base) for s in states):raise ValueError('Checkpoint schemas differ')
    for state in states:
        for k,v in state.items():
            if v.shape!=base[k].shape or v.dtype!=base[k].dtype or not v.isfinite().all():
                raise ValueError('Invalid released checkpoint')
            if k not in private_keys and not torch.equal(v,base[k]):
                raise ValueError('Frozen public parameter changed')
    if strategy.startswith('mean_last'):
        count=int(strategy[-1]);states=states[-count:]
    if strategy=='ema_half':
        weights=[.5**(len(states)-1)]+[.5**(len(states)-i) for i in range(1,len(states))]
    else:weights=[1/len(states)]*len(states)
    result={}
    for k,v in base.items():
        if k not in private_keys:result[k]=v.detach().clone();continue
        total=torch.zeros_like(v,dtype=torch.float64)
        for state,weight in zip(states,weights):total+=state[k].double()*weight
        result[k]=total.to(v.dtype)
    return result
