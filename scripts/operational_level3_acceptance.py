"""Real Kafka acceptance through the browser's Collaboration.start boundary.

Uses existing prepared data and approved warm assets. No evaluation or tuning.
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
from streaming.app.final_federation import BANK_ORDER, CLIENTS, validate_operational_config
from distributed_federation.common.config import load_config
from distributed_federation.common.checkpoints import verify_checkpoint
from distributed_federation.common.model_runtime import deserialize_state, prepare_frozen_runtime, load_initial_checkpoint
from distributed_federation.common.protocol import ChunkAssembler, verify_chunk
from distributed_federation.privacy.ledger import Ledger


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
    assembler=ChunkAssembler(); records=[]
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
                            payload_sha256=meta['payload_sha256'],bytes=len(payload),hmac_verified=True)
                if kind=='masked_client_update':
                    state=load(payload)
                    assert set(state)=={'masked_ring'}
                    ring=state['masked_ring']
                    # Wire format deliberately stores uint64 ring bits as int64.
                    assert ring.shape==(65793,) and ring.dtype.name=='int64'
                    record.update(tensor_keys=list(state),dimension=ring.size,dtype=ring.dtype.name)
                records.append(record)
    finally: consumer.close()
    return records


def run_case(root,dataset,broker,missing=False):
    name='missing-bank' if missing else 'complete-cohort'
    run_id='op-'+name+'-'+uuid.uuid4().hex[:16]
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
        wire=inspect_wire(broker,run_id,secret,begin,end)
        events={}; statuses={}; accounts={}
        for actor in started:
            manager=managers[actor]
            bank=next((b for b,c in CLIENTS.items() if c==actor),None)
            status=manager.status(bank); record=status['runs'][0]
            statuses[actor]=dict(status=record['status'],privacy=status['privacy'],label=status['privacy_label'])
            events[actor]=[dict(kind=e['kind'],round_id=e['round_id'],details=e['details']) for e in record['events']]
            cfg=load_config(manager.root/'launch-config.json')
            assert validate_operational_config(json.loads((manager.root/'launch-config.json').read_text()),cfg)==65793
            ledger=Ledger(cfg.output_dir/'privacy-ledgers'/f'{actor}.sqlite3')
            accounts[actor]=ledger.accounting(actor,1e-6);ledger.close()
            assert status['privacy']['mode']=='distributed_dp' and status['privacy']['secagg']
            assert abs(status['privacy']['epsilon']-127.36375184207253)<1e-9
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
            assert len(masked)==3 and {m['sender_id'] for m in masked}==set(CLIENTS.values())
            assert kinds=={'global_model','secagg_public_key','secagg_ready','masked_client_update','aggregated_model'}
            cfg=load_config(central.root/'launch-config.json')
            runtime=prepare_frozen_runtime(cfg);load_initial_checkpoint(runtime.model,cfg.initial_checkpoint)
            warm=runtime.model.state_dict();payloads=[];checkpoints={}
            for actor in started:
                output=managers[actor].root/'models'/run_id
                if actor!='central': output/=actor
                records=verify_checkpoint(output,1)
                payload=(output/'global_round_001.safetensors').read_bytes();payloads.append(payload)
                checkpoints[actor]=records
                assert statuses[actor]['status']=='Completed'
                assert accounts[actor]['reservations']==1
                if actor!='central':assert any(e['kind']=='aggregate_received' for e in events[actor])
            assert all(payload==payloads[0] for payload in payloads)
            released=deserialize_state(payloads[0])
            frozen=[k for k in warm if not k.startswith('decoder.')]
            assert all(warm[k].equal(released[k]) for k in frozen)
            assert any(not warm[k].equal(released[k]) for k in warm if k.startswith('decoder.'))
            manifest=json.loads((cfg.output_dir/run_id/'global_round_001.json').read_text())
            assert manifest['mechanism_parameters']['dimension']==65793
            assert manifest['accounting']['releases']==1
            assert manifest['privacy']['entropy']=='production'
            selections={}
            for bank,actor in CLIENTS.items():
                run=managers[actor].controller.status()[0]
                selected=managers[actor].select_model(run['id'],1,bank)
                assert selected['sha256']==hashlib.sha256(payloads[0]).hexdigest()
                selections[bank]=dict(sha256=selected['sha256'],model_kind=selected['model_kind'])
            result.update(checkpoints=checkpoints,model_selections=selections,frozen_tensors_unchanged=len(frozen),
                          aggregate_sha256=hashlib.sha256(payloads[0]).hexdigest(),accounting=manifest['accounting'],
                          result='PASS: three masked contributions, aggregate returned and identical verified checkpoints on all four participants')
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
    args=parser.parse_args()
    if args.runtime_root.exists():raise ValueError('Use a fresh runtime root; preserve previous ledgers')
    report=dict(scope='Actual Collaboration.start subprocesses, local Kafka; no remote ZeroTier cryptography test',
                runtime_root=str(args.runtime_root),broker=args.broker)
    for missing in (False,True):
        report['missing_bank' if missing else 'complete_cohort']=run_case(args.runtime_root,args.dataset,args.broker,missing)
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2)+'\n')
    rho=sum(report[k]['ledger_accounting']['central']['rho'] for k in ('complete_cohort','missing_bank'))
    report['acceptance_central_reservations_composed']=dict(reservations=2,rho=rho,
        epsilon=rho+2*math.sqrt(rho*math.log(1e6)),delta=1e-6,
        scope='Both acceptance roots combined, including failed key-exchange reservation; excludes prior development ledgers')
    args.report.write_text(json.dumps(report,indent=2)+'\n')


if __name__=='__main__':main()
