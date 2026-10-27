"""Public parameter subsets; full checkpoints retain the original evaluator schema."""
PREFIXES={
    'all':('',),
    'decoder':('decoder.',),
    'ensemble_decoder':('42.decoder.','52.decoder.','62.decoder.'),
    'temporal_decoder':('time_projection.','memory_update.','decoder.'),
    'message_decoder':('message_projection.','memory_update.','decoder.'),
}


def parameter_keys(state,subset='all'):
    if subset not in PREFIXES:raise ValueError('Unknown private subset')
    keys=sorted(k for k in state if k.startswith(PREFIXES[subset]))
    if not keys:raise ValueError('Empty private subset')
    if subset=='ensemble_decoder':
        # All three members must have the same decoder key contract. Never
        # silently release only one member or broaden the legacy decoder subset.
        members=[{k.split('.',1)[1] for k in keys if k.startswith(seed+'.')} for seed in ('42','52','62')]
        if not members[0] or any(member!=members[0] for member in members):
            raise ValueError('Ensemble private subset requires all three complete decoders')
    return keys


def extract(state,subset='all'):
    return {k:state[k] for k in parameter_keys(state,subset)}


def configure_trainable(model,subset='all'):
    keys=parameter_keys(model.state_dict(),subset)
    for name,param in model.named_parameters():param.requires_grad_(name in keys)
    return keys


def reconstruct(base,updated,subset='all'):
    if set(updated)!=set(parameter_keys(base,subset)):
        raise ValueError('Private subset schema mismatch')
    for k,v in updated.items():
        if v.shape!=base[k].shape or v.dtype!=base[k].dtype or not v.isfinite().all():
            raise ValueError('Invalid private subset tensor')
    return {k:(updated[k] if k in updated else v).detach().clone() for k,v in base.items()}
