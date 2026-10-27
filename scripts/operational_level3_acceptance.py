"""Real Kafka acceptance through the browser's Collaboration.start boundary.

Uses existing prepared data and approved single-model assets. No utility tuning.
Runtime models/ledgers stay local; only public hashes and protocol evidence are
written to the report. The caller owns broker lifecycle.
"""
import argparse
import hashlib
import json
import math
import secrets
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from streaming.app.collaboration import Collaboration, GLOBAL_TOPIC, UPDATE_TOPIC
from streaming.app.final_federation import BANK_ORDER, CLIENTS, PRIVATE_DIMENSION, FIXED, validate_operational_config
from distributed_federation.common.config import load_config
from distributed_federation.common.checkpoints import verify_checkpoint
from distributed_federation.common.model_runtime import deserialize_state, prepare_frozen_runtime, load_initial_checkpoint
from distributed_federation.common.protocol import ChunkAssembler, verify_chunk
from distributed_federation.privacy.ledger import Ledger
from distributed_federation.privacy.subset import extract,parameter_keys
from distributed_federation.privacy.mechanism import vector,decode,restore
import numpy as np


def offsets(broker):
    from confluent_kafka import Consumer, TopicPartition
    consumer=Consumer({'bootstrap.servers':broker,'group.id':'acceptance-offset-'+uuid.uuid4().hex})
    try:
        return {topic:consumer.get_watermark_offsets(TopicPartition(topic,0),timeout=10)[1]
                for topic in (GLOBAL_TOPIC,UPDATE_TOPIC)}
    finally: consumer.close()


def inspect_wire(broker, run_id, secret, begin, end):
    from confluent_kafka import Consumer, TopicPartition
    from safetensors.numpy import load
    consumer=Consumer({'bootstrap.servers':broker,'group.id':'acceptance-audit-'+uuid.uuid4().hex,
                       'enable.auto.commit':False})
    assembler=ChunkAssembler(); records=[]; rings={}; public_bases={}
    try:
        for topic in begin:
            consumer.assign([TopicPartition(topic,0,begin[topic])])
            position=begin[topic]; deadline=time.monotonic()+30
            while position<end[topic]:
                if time.monotonic()>deadline: raise TimeoutError('Wire audit did not reach captured end offset')
                msg=consumer.poll(1)
                if msg is None: continue
                if msg.error(): raise RuntimeError(str(msg.error()))
                position=msg.offset()+1
                if json.loads(msg.value()).get('run_id')!=run_id: continue
                envelope=verify_chunk(msg.value(),secret)
                assert not {'training_examples','mean_train_loss','clean_norm','private_key','mask_seed','noise_share'} & envelope.keys()
                assembled=assembler.add(envelope)
                if assembled is None: continue
                payload,meta=assembled
                kind=meta['message_type']
                assert kind!='client_update', 'Plaintext update on final private wire'
                record=dict(topic=topic,message_type=kind,sender_id=meta['sender_id'],
                            round_id=meta['round_id'],payload_sha256=meta['payload_sha256'],bytes=len(payload),hmac_verified=True)
                if kind=='masked_client_update':
                    state=load(payload)
                    assert set(state)=={'masked_ring'}
                    ring=state['masked_ring']
                    # Wire format deliberately stores uint64 ring bits as int64.
                    assert ring.shape==(PRIVATE_DIMENSION,) and ring.dtype.name=='int64'
                    record.update(tensor_keys=list(state),dimension=ring.size,dtype=ring.dtype.name)
                    rings.setdefault(meta['round_id'],{})[meta['sender_id']]=ring.view(np.uint64)
                elif kind=='global_model':
                    public_bases[meta['round_id']]=deserialize_state(payload)
                elif kind=='secagg_ready':
                    roster=json.loads(payload)
                    assert set(roster['keys'])==set(CLIENTS.values())
                    assert roster['context']['dimension']==PRIVATE_DIMENSION
                records.append(record)
    finally: consumer.close()
    return records,rings,public_bases


def run_case(root,dataset,broker,missing=False,run_id=None):
    name='missing-bank' if missing else 'complete-cohort'
    run_id=run_id or 'op-'+name+'-'+uuid.uuid4().hex[:16]
    secret=secrets.token_urlsafe(48)
    managers={actor:Collaboration(root/name/actor) for actor in ('central',*CLIENTS.values())}
    profiles={}
    for actor,manager in managers.items():
        profiles[actor]=dict(manager.defaults(),role='central' if actor=='central' else 'bank',
                             dataset=str(dataset),broker=broker,run_id=run_id,timeout=60 if missing else 900)
    central=managers['central']
    central.preflight(profiles['central'],None,prepare=True)
    begin=offsets(broker)
    started=[]
    try:
        for bank in BANK_ORDER[:2] if missing else BANK_ORDER:
            actor=CLIENTS[bank]; manager=managers[actor]
            manager.preflight(profiles[actor],bank)
            manager.start(dict(profile=profiles[actor],secret=secret),bank)
            started.append(actor)
        central.start(dict(profile=profiles['central'],secret=secret),None)
        started.append('central')
        print(name+': launched via Collaboration.start -> controller -> runner',flush=True)
        deadline=time.monotonic()+(180 if missing else 1000)
        while any(managers[a].process.poll() is None for a in started):
            if time.monotonic()>deadline: raise TimeoutError('Acceptance child deadline exceeded')
            time.sleep(.5)
        codes={a:managers[a].process.returncode for a in started}
        end=offsets(broker)
        wire,rings,public_bases=inspect_wire(broker,run_id,secret,begin,end)
        events={}; statuses={}; accounts={}
        for actor in started:
            manager=managers[actor]
            bank=next((b for b,c in CLIENTS.items() if c==actor),None)
            status=manager.status(bank); record=status['runs'][0]
            statuses[actor]=dict(status=record['status'],privacy=status['privacy'],label=status['privacy_label'])
            events[actor]=[dict(kind=e['kind'],round_id=e['round_id'],details=e['details']) for e in record['events']]
            cfg=load_config(manager.root/'launch-config.json')
            assert validate_operational_config(json.loads((manager.root/'launch-config.json').read_text()),cfg)==PRIVATE_DIMENSION
            ledger=Ledger(cfg.output_dir/'privacy-ledgers'/f'{actor}.sqlite3')
            accounts[actor]=ledger.accounting(actor,1e-6);ledger.close()
            assert status['privacy']['mode']=='distributed_dp' and status['privacy']['secagg']
            assert abs(status['privacy']['epsilon']-accounts[actor]['epsilon'])<1e-9
        result=dict(run_id=run_id,exit_codes=codes,status=statuses,events=events,wire=wire,
                    ledger_accounting=accounts,begin_offsets=begin,end_offsets=end)
        kinds={m['message_type'] for m in wire}
        if missing:
            assert all(code!=0 for code in codes.values())
            assert 'masked_client_update' not in kinds and 'aggregated_model' not in kinds and 'secagg_ready' not in kinds
            assert {m['sender_id'] for m in wire if m['message_type']=='secagg_public_key'}==set(started)-{'central'}
            for actor in started:
                assert statuses[actor]['status']=='Failed'
                assert any(e['kind']=='process_failed' and e['details'].get('error_type')=='TimeoutError' for e in events[actor])
                assert not any(e['kind']=='training' for e in events[actor])
                assert not list(managers[actor].root.glob('models/**/*.safetensors'))
            assert accounts['central']['reservations']==1
            result['result']='PASS: missing third bank aborts before training; no update, aggregate, checkpoint or fallback'
        else:
            assert all(code==0 for code in codes.values()), codes
            masked=[m for m in wire if m['message_type']=='masked_client_update']
            assert len(masked)==3*FIXED['rounds']
            assert kinds=={'global_model','secagg_public_key','secagg_ready','masked_client_update','aggregated_model'}
            cfg=load_config(central.root/'launch-config.json')
            runtime=prepare_frozen_runtime(cfg);load_initial_checkpoint(runtime.model,cfg.initial_checkpoint)
            warm=runtime.model.state_dict();checkpoints={};rounds=[]
            private_keys=parameter_keys(warm,FIXED['private_subset'])
            from distributed_federation.privacy.server_optimizer import ServerOptimizer
            postprocess=ServerOptimizer(cfg.server_optimizer)
            frozen=[k for k in warm if k not in private_keys]
            for rid in range(1,cfg.rounds+1):
                round_messages=[m for m in masked if m['round_id']==rid]
                assert len(round_messages)==3 and {m['sender_id'] for m in round_messages}==set(CLIENTS.values())
                payloads=[];checkpoints[str(rid)]={}
                for actor in started:
                    output=managers[actor].root/'models'/run_id
                    if actor!='central':output/=actor
                    records=verify_checkpoint(output,rid)
                    payload=(output/f'global_round_{rid:03d}.safetensors').read_bytes();payloads.append(payload)
                    checkpoints[str(rid)][actor]=records
                    assert statuses[actor]['status']=='Completed'
                    assert accounts[actor]['reservations']==cfg.rounds
                    if actor!='central':assert any(e['kind']=='aggregate_received' and e['round_id']==rid for e in events[actor])
                assert all(payload==payloads[0] for payload in payloads)
                released=deserialize_state(payloads[0])
                assert all(warm[k].equal(released[k]) for k in frozen)
                assert any(not warm[k].equal(released[k]) for k in private_keys)
                total=np.zeros(PRIVATE_DIMENSION,dtype=np.uint64)
                for ring in rings[rid].values():total=np.add(total,ring,dtype=np.uint64)
                private_base=extract(public_bases[rid],FIXED['private_subset'])
                reconstructed=restore(vector(private_base)+decode(total,cfg.privacy.scale)/3,private_base)
                reconstructed=postprocess.apply(private_base,reconstructed)
                assert all(reconstructed[k].equal(released[k]) for k in reconstructed)
                manifest=json.loads((cfg.output_dir/run_id/f'global_round_{rid:03d}.json').read_text())
                assert manifest['mechanism_parameters']['dimension']==PRIVATE_DIMENSION
                assert manifest['accounting']['releases']==rid
                assert manifest['privacy']['entropy']=='production'
                rounds.append(dict(round=rid,masked_contributions=3,dimension=PRIVATE_DIMENSION,
                    aggregate_sha256=hashlib.sha256(payloads[0]).hexdigest(),accounting=manifest['accounting'],
                    masked_ring_sum_reconstructs_returned_noisy_aggregate=True,frozen_tensors_unchanged=len(frozen)))
            selections={}
            for bank,actor in CLIENTS.items():
                run=managers[actor].controller.status()[0]
                selected=managers[actor].select_model(run['id'],cfg.rounds,bank)
                assert selected['sha256']==rounds[-1]['aggregate_sha256']
                assert selected['model_kind']=='federated_single'
                selections[bank]=dict(sha256=selected['sha256'],model_kind=selected['model_kind'])
            result.update(checkpoints=checkpoints,rounds=rounds,model_selections=selections,
                          result='PASS: all four single-model rounds; three masked contributions per round; identical verified returns and frozen non-decoders')
        print(result['result'],flush=True)
        return result
    finally:
        for actor in started:
            process=managers[actor].process
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=10)
                except __import__('subprocess').TimeoutExpired:process.kill();process.wait()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--broker',default='127.0.0.1:19092')
    parser.add_argument('--runtime-root',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    parser.add_argument('--case',choices=['missing','complete','both'],default='both')
    parser.add_argument('--run-id')
    args=parser.parse_args()
    if args.runtime_root.exists():raise ValueError('Use a fresh runtime root; preserve previous ledgers')
    report=dict(scope='Actual Collaboration.start subprocesses, local Kafka; no remote ZeroTier cryptography test',
                runtime_root=str(args.runtime_root),broker=args.broker)
    for missing in ([True] if args.case=='missing' else [False] if args.case=='complete' else [True,False]):
        report['missing_bank' if missing else 'complete_cohort']=run_case(args.runtime_root,args.dataset,args.broker,missing,args.run_id)
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2)+'\n')
    names=[k for k in ('complete_cohort','missing_bank') if k in report]
    accounts=[report[k]['ledger_accounting']['central'] for k in names]
    rho=sum(a['rho'] for a in accounts)
    report['acceptance_central_reservations_composed']=dict(reservations=sum(a['reservations'] for a in accounts),rho=rho,
        epsilon=rho+2*math.sqrt(rho*math.log(1e6)),delta=1e-6,
        scope='Acceptance roots in this report combined; excludes prior development ledgers')
    args.report.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
