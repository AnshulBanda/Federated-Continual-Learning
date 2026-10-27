"""Real Kafka + PyTorch, final Level-3 three-bank acceptance (local processes)."""
import argparse
import hashlib
import json
import secrets
import time
import uuid
from pathlib import Path
from .app.collaboration import Collaboration, CLIENTS
from .app.local_training import write_json
from .app.overview import REPO
from distributed_federation.common.checkpoints import verify_checkpoint


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--broker',default='10.30.127.124:9092')
    parser.add_argument('--rounds',type=int,choices=[1],default=1)
    parser.add_argument('--client-state-dir',type=Path,help='Optional existing client dashboard state folder; records Key Bank acceptance run there.')
    parser.add_argument('--central-state-dir',type=Path,help='Optional existing coordinator dashboard state folder.')
    args=parser.parse_args()
    run_id='accept-'+uuid.uuid4().hex[:16]
    evidence=REPO/'streaming/.local'/run_id
    actors={name:Collaboration(args.client_state_dir if name==CLIENTS['Key_Bank'] and args.client_state_dir else args.central_state_dir if name=='central' and args.central_state_dir else evidence/name) for name in ('central',*CLIENTS.values())}
    secret=secrets.token_urlsafe(40)
    shared=dict(broker=args.broker,run_id=run_id,banks=list(CLIENTS),dataset=actors['central'].defaults()['dataset'],rounds=args.rounds,local_epochs=2,timeout=900)
    started=[]
    try:
        actors['central'].preflight(dict(shared,role='central'),None,prepare=True)
        for bank,client_id in CLIENTS.items():
            manager=actors[client_id]
            profile=dict(shared,role='bank')
            manager.preflight(profile,bank)
            manager.start(dict(profile=profile,secret=secret),bank)
            started.append(manager)
        central=actors['central']
        profile=dict(shared,role='central')
        central.preflight(profile,None,prepare=True)
        central.start(dict(profile=profile,secret=secret),None)
        started.append(central)
        print('Started three real bank trainers and coordinator through Kafka:',run_id,flush=True)
        deadline=time.monotonic()+1000
        while any(m.process.poll() is None for m in started):
            if time.monotonic()>deadline:raise TimeoutError('Federation acceptance check exceeded its deadline')
            for name,m in actors.items():
                if m.process and m.process.poll() not in (None,0):
                    raise RuntimeError(f'{name} failed; inspect {m.root / "worker.log"}')
            time.sleep(1)
        result=dict(run_id=run_id,broker=args.broker,rounds=args.rounds,banks=list(CLIENTS),result='PASS',rounds_verified=[])
        for name,manager in actors.items():
            runs=manager.controller.status()
            assert runs[0]['status']=='Completed' and runs[0]['run_id']==run_id,(name,runs)
        for round_id in range(1,args.rounds+1):
            base=central.root/'models'/run_id
            verify_checkpoint(base,round_id)
            original=(base/f'global_round_{round_id:03d}.safetensors').read_bytes()
            digest=hashlib.sha256(original).hexdigest()
            for bank,client_id in CLIENTS.items():
                root=actors[client_id].root/'models'/run_id/client_id
                verify_checkpoint(root,round_id)
                assert (root/f'global_round_{round_id:03d}.safetensors').read_bytes()==original
                events=actors[client_id].controller.store.events(actors[client_id].controller.status()[0]['id'],limit=1000)
                assert any(e['kind']=='aggregate_received' and e['round_id']==round_id for e in events)
            events=central.controller.store.events(central.controller.status()[0]['id'],limit=1000)
            updates=[e for e in events if e['kind']=='update_validated' and e['round_id']==round_id]
            assert len(updates)==3
            result['rounds_verified'].append(dict(round=round_id,sha256=digest,bytes=len(original),verified_banks=3,verified_updates=len(updates)))
        for bank,client_id in CLIENTS.items():
            selected=actors[client_id].select_model(actors[client_id].controller.status()[0]['id'],args.rounds,bank)
            assert selected['sha256']==result['rounds_verified'][-1]['sha256']
        write_json(evidence/'result.json',result)
        print('PASS: actual Level-3 local training, signed masked Kafka contributions, noisy equal aggregate, and byte-identical verified returns to every bank.',flush=True)
        print('Evidence:',evidence,flush=True)
    finally:
        for manager in started:
            if manager.process.poll() is None:
                for run in manager.controller.status():
                    if run['status']=='Running':manager.controller.stop(run['id'],cancel=True)
                try:manager.process.wait(timeout=15)
                except Exception:manager.process.terminate()

if __name__=='__main__':main()
