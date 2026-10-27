"""Authenticated Kafka round coordinator; no plaintext fallback for secure modes.

No model/update diagnostic is included in private messages. The legacy signed
chunk transport, verified checkpoint writer, and return-aggregate path are reused.
"""
import hashlib
import json
import os
import time
from dataclasses import asdict

from distributed_federation.common.control import check_control
from distributed_federation.common.events import emit
from distributed_federation.common.protocol import ChunkAssembler, verify_for_run, peek_sender, sha256_bytes
from distributed_federation.common.model_runtime import (prepare_runtime,prepare_frozen_runtime,
    load_initial_checkpoint,serialize_state,deserialize_state,validate_state,train_local,
    save_state_and_manifest,fedavg)
from distributed_federation.common.kafka_io import make_consumer,make_producer,publish_payload
from distributed_federation.common.config import secret_env_name
from .mechanism import vector,restore,client_contribution,aggregate
from .secagg import ClientKey,Round,context,canonical,pack,accept_roster
from .ledger import Ledger
from .server_optimizer import ServerOptimizer
from .subset import extract,reconstruct


def secret(name):
    value=os.environ.get(name,'')
    if len(value)<32: raise RuntimeError('Set '+name+' to at least 32 random characters')
    return value


def metadata(cfg,runtime,round_id,base,kind,sender,**extras):
    return dict(run_id=cfg.run_id,round_id=round_id,schema_sha256=runtime.schema_sha256,
                base_model_sha256=base,message_type=kind,sender_id=sender,**extras)


def receive(consumer,assembler,cfg,secrets,round_id,kinds,deadline):
    while time.monotonic()<deadline:
        check_control()
        message=consumer.poll(min(1.,max(.01,deadline-time.monotonic())))
        if message is None: continue
        if message.error(): raise RuntimeError(str(message.error()))
        try:
            sender=peek_sender(message.value())
            if sender not in secrets: continue
            envelope=verify_for_run(message.value(),secrets[sender],cfg.run_id)
            if envelope is None or envelope['round_id']!=round_id or envelope['message_type'] not in kinds: continue
            assembled=assembler.add(envelope)
            if assembled is None: continue
            payload,meta=assembled
            consumer.commit(message=message,asynchronous=False)
            return sender,payload,meta
        except (ValueError,KeyError,TypeError):
            emit('message_rejected',round_id)
    raise TimeoutError('Incomplete required cohort/round; failing closed, no plaintext fallback')


def check_meta(meta,runtime,base):
    if meta['schema_sha256']!=runtime.schema_sha256 or meta['base_model_sha256']!=base:
        raise ValueError('Wrong schema or base model')


def publish(producer,cfg,runtime,round_id,base,kind,sender,payload,key,global_topic=False,**extras):
    return publish_payload(producer,cfg.global_topic if global_topic else cfg.update_topic,payload,
        metadata(cfg,runtime,round_id,base,kind,sender,**extras),key,cfg.max_chunk_bytes)


def _guard(cfg):
    if cfg.privacy.mode!='none' and getattr(cfg,'training_protocol','legacy')=='adaptive_ensemble':
        raise ValueError('Private ensemble federation is retired; use one decoder-private model')
    if cfg.privacy.mode!='none' and cfg.privacy.entropy!='production':
        raise ValueError('Deterministic research noise is forbidden in the operational private pipeline')
    if cfg.privacy.secure and (not cfg.feature_schema or len(cfg.clients)!=cfg.privacy.expected_clients):
        raise ValueError('Secure mode requires a frozen public feature schema and complete cohort')
    if cfg.privacy.mode != "none" and cfg.aggregation != "equal":
        raise ValueError("Private modes require equal weights")
    if cfg.rng_policy not in ('per_client','counter'): raise ValueError('Global simulator RNG cannot be shared across workers')


def worker(cfg,client_id):
    _guard(cfg)
    client=cfg.client(client_id)
    central_key,client_key=secret('FCL_CENTRAL_SECRET'),secret('FCL_CLIENT_SECRET')
    runtime=prepare_runtime(cfg,client.bank)
    output=cfg.output_dir/cfg.run_id/client_id
    ledger=Ledger(cfg.output_dir/'privacy-ledgers'/f'{client_id}.sqlite3')
    # A process restart cannot resample keys/noise for an old run, even after a
    # failed send. Restart under a NEW run, composing all prior reservations.
    ledger.reserve(cfg.run_id,0,client_id,asdict(cfg.privacy))
    producer=make_producer(cfg.broker)
    consumer=make_consumer(cfg.broker,f'fcl-worker-{cfg.run_id}-{client_id}',[cfg.global_topic])
    assembler=ChunkAssembler()
    emit('runtime_ready',client_id=client_id,schema_sha256=runtime.schema_sha256)
    try:
        for rid in range(1,cfg.rounds+1):
            check_control(round_boundary=True)
            emit('waiting_for_model',rid,privacy_mode=cfg.privacy.mode)
            _,payload,meta=receive(consumer,assembler,cfg,{'central':central_key},rid,{'global_model'},time.monotonic()+cfg.round_timeout_seconds)
            base_hash=sha256_bytes(payload)
            check_meta(meta,runtime,base_hash)
            base=deserialize_state(payload);validate_state(base,runtime.model.state_dict())
            runtime.model.load_state_dict(base,strict=True)
            emit('model_loaded',rid,base_model_sha256=base_hash)
            key,roster,ctx=None,None,None
            if cfg.privacy.secure:
                ctx=context(cfg.run_id,rid,[c.client_id for c in cfg.clients],runtime.schema_sha256,base_hash,len(vector(extract(base,cfg.private_subset))))
                key=ClientKey(client_id,ctx)
                publish(producer,cfg,runtime,rid,base_hash,'secagg_public_key',client_id,key.hello(),client_key)
                _,payload,roster_meta=receive(consumer,assembler,cfg,{'central':central_key},rid,{'secagg_ready'},time.monotonic()+cfg.round_timeout_seconds)
                check_meta(roster_meta,runtime,base_hash)
                roster=accept_roster(payload,key)
                roster_hash=hashlib.sha256(payload).hexdigest()
                emit('secagg_ready',rid,privacy_mode=cfg.privacy.mode,required_cohort=len(cfg.clients))
            emit('training',rid)
            train_local(runtime,cfg,rid,[c.client_id for c in cfg.clients].index(client_id))
            emit('training_completed',rid)
            check_control()
            ledger.reserve(cfg.run_id,rid,client_id,asdict(cfg.privacy))
            extras={}
            if cfg.privacy.mode=='none' and cfg.aggregation=='samples':
                extras['training_examples']=len(runtime.streams['training'])
            if cfg.privacy.mode=='none':
                outgoing=serialize_state(runtime.model.state_dict());kind='client_update'
            else:
                contribution=client_contribution(extract(runtime.model.state_dict(),cfg.private_subset),extract(base,cfg.private_subset),cfg.privacy,cfg.run_id,rid,client_id)
                if cfg.privacy.secure:
                    outgoing=pack(key.mask(contribution,roster));kind='masked_client_update'
                    extras=dict(secagg_context_sha256=hashlib.sha256(canonical(ctx)).hexdigest(),roster_sha256=roster_hash)
                else:
                    outgoing=serialize_state(restore(vector(base)+contribution,base));kind='client_update'
            emit('publishing_update',rid,bytes=len(outgoing))
            update_hash=publish(producer,cfg,runtime,rid,base_hash,kind,client_id,outgoing,client_key,**extras)
            # Discard ephemeral key object; no secret or update ever enters a manifest.
            key=None
            emit('update_published',rid,payload_sha256=update_hash,privacy_mode=cfg.privacy.mode)
            if cfg.return_aggregate:
                emit('waiting_for_aggregate',rid)
                _,returned,meta=receive(consumer,assembler,cfg,{'central':central_key},rid,{'aggregated_model'},time.monotonic()+cfg.round_timeout_seconds)
                check_meta(meta,runtime,base_hash)
                state=deserialize_state(returned);validate_state(state,base)
                runtime.model.load_state_dict(state)
                path,manifest=save_state_and_manifest(state,output,rid,dict(run_id=cfg.run_id,round_id=rid,
                    input_global_sha256=base_hash,payload_sha256=sha256_bytes(returned),schema=runtime.schema,privacy_mode=cfg.privacy.mode))
                emit('aggregate_received',rid,payload_sha256=sha256_bytes(returned),checkpoint=str(path),manifest=str(manifest))
        emit('worker_completed',rounds=cfg.rounds)
        return 0
    finally: consumer.close();ledger.close()


def central(cfg):
    _guard(cfg)
    central_key=secret('FCL_CENTRAL_SECRET')
    keys={c.client_id:secret(secret_env_name(c.client_id)) for c in cfg.clients}
    runtime=prepare_frozen_runtime(cfg) if cfg.feature_schema else prepare_runtime(cfg,cfg.clients[0].bank)
    load_initial_checkpoint(runtime.model,cfg.initial_checkpoint)
    base={k:v.detach().clone() for k,v in runtime.model.state_dict().items()}
    server_optimizer=ServerOptimizer(cfg.server_optimizer)
    output=cfg.output_dir/cfg.run_id
    ledger=Ledger(cfg.output_dir/'privacy-ledgers'/'central.sqlite3')
    ledger.reserve(cfg.run_id,0,'central',asdict(cfg.privacy))
    producer=make_producer(cfg.broker)
    consumer=make_consumer(cfg.broker,f'fcl-central-{cfg.run_id}',[cfg.update_topic])
    assembler=ChunkAssembler()
    emit('runtime_ready',schema_sha256=runtime.schema_sha256)
    try:
        for rid in range(1,cfg.rounds+1):
            check_control(round_boundary=True)
            ledger.reserve(cfg.run_id,rid,'central',asdict(cfg.privacy))
            payload=serialize_state(base);base_hash=sha256_bytes(payload)
            publish(producer,cfg,runtime,rid,base_hash,'global_model','central',payload,central_key,True)
            deadline=time.monotonic()+cfg.round_timeout_seconds
            secure=None
            exchange_metadata=None
            if cfg.privacy.secure:
                ctx=context(cfg.run_id,rid,keys,runtime.schema_sha256,base_hash,len(vector(extract(base,cfg.private_subset))))
                secure=Round(ctx)
                emit('secagg_key_exchange',rid,privacy_mode=cfg.privacy.mode,required_cohort=len(keys))
                while len(secure.keys)<len(keys):
                    sender,payload,meta=receive(consumer,assembler,cfg,keys,rid,{'secagg_public_key'},deadline)
                    check_meta(meta,runtime,base_hash)
                    if sender in secure.keys:
                        if json.loads(payload).get('public_key')!=secure.keys[sender]:
                            raise ValueError('Conflicting duplicate public key')
                        continue # exact delivery retry, never replace a key
                    secure.add_key(payload,sender)
                roster_payload=secure.roster()
                exchange_metadata=dict(context=ctx,public_keys=dict(secure.keys),roster_sha256=hashlib.sha256(roster_payload).hexdigest())
                publish(producer,cfg,runtime,rid,base_hash,'secagg_ready','central',roster_payload,central_key,True)
            emit('waiting_for_updates',rid,privacy_mode=cfg.privacy.mode,secagg=cfg.privacy.secure,required_cohort=len(keys))
            states={};hashes={};counts={}
            kind='masked_client_update' if secure else 'client_update'
            while len(hashes)<len(keys):
                sender,payload,meta=receive(consumer,assembler,cfg,keys,rid,{kind},deadline)
                check_meta(meta,runtime,base_hash)
                if sender in hashes:
                    if hashes[sender]!=sha256_bytes(payload): raise ValueError('Conflicting duplicate contribution')
                    continue
                if secure: secure.add_update(sender,payload,meta)
                else:
                    state=deserialize_state(payload);validate_state(state,base);states[sender]=state
                if not secure and cfg.aggregation=='samples':
                    counts[sender]=int(meta.get('training_examples',0))
                    if counts[sender]<=0: raise ValueError('Invalid public sample weight')
                hashes[sender]=sha256_bytes(payload)
                emit('update_validated',rid,client_id=sender,payload_sha256=hashes[sender])
            # The round was reserved before broadcasting, covering a crash after
            # all distributed shares arrive but before checkpoint persistence.
            if secure:
                private_base=extract(base,cfg.private_subset)
                noisy_aggregate=aggregate(secure.complete(),private_base,cfg.privacy,cfg.run_id,rid)
                base=reconstruct(base,server_optimizer.apply(private_base,noisy_aggregate),cfg.private_subset)
                del noisy_aggregate
                secure=None  # Distributed DP noise is already inside every bank share.
            elif cfg.privacy.mode=='none' and getattr(cfg,'training_protocol','legacy')=='adaptive_ensemble':
                # Plaintext reference/research only. SecAgg deliberately hides
                # individual directions, so private mode never harmonizes them.
                from distributed_federation.common.model_runtime import aggregate_adaptive
                base=aggregate_adaptive([states[c.client_id] for c in cfg.clients],base)
            else:
                base=fedavg([states[c.client_id] for c in cfg.clients],[counts[c.client_id] for c in cfg.clients] if cfg.aggregation=='samples' else [1]*len(keys))
            runtime.model.load_state_dict(base)
            released=serialize_state(base);digest=sha256_bytes(released)
            account=cfg.privacy.accounting(rid)
            # JSON manifests cannot use infinity; explicit nonfinite values mean no finite DP.
            cumulative=ledger.accounting('central',cfg.privacy.delta)
            cumulative={k:(v if not isinstance(v,float) or __import__('math').isfinite(v) else 'infinite') for k,v in cumulative.items()}
            account={k:(v if not isinstance(v,float) or __import__('math').isfinite(v) else 'infinite') for k,v in account.items()}
            manifest=dict(run_id=cfg.run_id,round_id=rid,schema_sha256=runtime.schema_sha256,
                input_global_sha256=base_hash,output_global_sha256=digest,schema=runtime.schema,
                clients=[dict(client_id=c.client_id,bank=c.bank,update_sha256=hashes[c.client_id]) for c in cfg.clients],
                aggregation=cfg.aggregation,secagg_exchange=exchange_metadata,privacy=asdict(cfg.privacy),mechanism_parameters=cfg.privacy.parameters(len(vector(extract(base,cfg.private_subset)))) if cfg.privacy.mode!="none" else None,accounting=account,cumulative_ledger_accounting=cumulative,
                starting_checkpoint_scope='conditional_nonprivate_frozen_ensemble' if getattr(cfg,'training_protocol','legacy')=='adaptive_ensemble' else 'conditional_fixed_checkpoint' if cfg.initial_checkpoint else 'random_initialization_public_schema',
                aggregation_method='secure_equal' if secure is not None or cfg.privacy.secure else 'temporal_harmonization' if getattr(cfg,'training_protocol','legacy')=='adaptive_ensemble' else 'fedavg')
            path,manifest_path=save_state_and_manifest(base,output,rid,manifest)
            emit('round_completed',rid,checkpoint=str(path),manifest=str(manifest_path),privacy_mode=cfg.privacy.mode,
                 secagg=cfg.privacy.secure,epsilon=account['epsilon'],delta=account['delta'],required_cohort=len(keys))
            if cfg.return_aggregate:
                publish(producer,cfg,runtime,rid,base_hash,'aggregated_model','central',released,central_key,True)
                emit('aggregate_published',rid,payload_sha256=digest)
        emit('run_completed',rounds=cfg.rounds)
        return 0
    finally: consumer.close();ledger.close()
