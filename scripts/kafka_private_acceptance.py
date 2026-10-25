#!/usr/bin/env python3
"""Three separate bank processes + coordinator, real local Kafka and real trainer.

Secrets are generated in memory for child environments only. Every returned
checkpoint must be byte-identical. Never writes .env or logs secret material.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from distributed_federation.common.config import load_config,secret_env_name
from distributed_federation.common.checkpoints import verify_checkpoint


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config',type=Path,default=ROOT/'configs/privacy_distributed_dp.json')
    p.add_argument('--rounds',type=int,default=2)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    raw=json.loads(args.config.read_text());raw.update(run_id='qa-'+uuid.uuid4().hex[:16],rounds=args.rounds,output_dir=str(args.output/'models'))
    cfgpath=args.output/'run.json';cfgpath.write_text(json.dumps(raw,indent=2)+'\n');cfg=load_config(cfgpath)
    from confluent_kafka.admin import AdminClient,NewTopic
    admin=AdminClient({'bootstrap.servers':cfg.broker})
    for name,future in admin.create_topics([NewTopic(cfg.global_topic,1,1),NewTopic(cfg.update_topic,3,1)]).items():
        try:future.result(30)
        except Exception as exc:
            if 'TOPIC_ALREADY_EXISTS' not in str(exc):raise
    env=os.environ.copy();env['OMP_NUM_THREADS']='1';env['MKL_NUM_THREADS']='1';env['FCL_CENTRAL_SECRET']=secrets.token_urlsafe(40)
    clientsecrets={c.client_id:secrets.token_urlsafe(40) for c in cfg.clients}
    processes=[];logs=[]
    try:
        for client in cfg.clients:
            child=env.copy();child['FCL_CLIENT_SECRET']=clientsecrets[client.client_id]
            log=(args.output/f'{client.client_id}.log').open('wb');logs.append(log)
            proc=subprocess.Popen([sys.executable,'-u','-m','distributed_federation.client.bank_worker','--config',str(cfgpath),'--client-id',client.client_id],cwd=ROOT,env=child,stdout=log,stderr=subprocess.STDOUT)
            processes.append(proc)
        central_env=env.copy();central_env.update({secret_env_name(k):v for k,v in clientsecrets.items()})
        log=(args.output/'central.log').open('wb');logs.append(log)
        processes.append(subprocess.Popen([sys.executable,'-u','-m','distributed_federation.central.aggregator','--config',str(cfgpath)],cwd=ROOT,env=central_env,stdout=log,stderr=subprocess.STDOUT))
        deadline=time.monotonic()+cfg.round_timeout_seconds+120
        while any(x.poll() is None for x in processes):
            if any(x.poll() not in (None,0) for x in processes):raise RuntimeError('Federation child failed; inspect local logs')
            if time.monotonic()>deadline:raise TimeoutError('Federation timeout')
            time.sleep(.5)
        if any(x.returncode!=0 for x in processes):raise RuntimeError('Failed child')
        evidence=[];root=cfg.output_dir/cfg.run_id
        for rid in range(1,cfg.rounds+1):
            verify_checkpoint(root,rid)
            data=(root/f'global_round_{rid:03d}.safetensors').read_bytes()
            for c in cfg.clients:
                verify_checkpoint(root/c.client_id,rid)
                assert data==(root/c.client_id/f'global_round_{rid:03d}.safetensors').read_bytes()
            evidence.append(dict(round=rid,sha256=hashlib.sha256(data).hexdigest(),bytes=len(data),verified_clients=3))
        result=dict(result='PASS',mode=cfg.privacy.mode,run_id=cfg.run_id,rounds=evidence,real_kafka=True,separate_processes=4,private_keys_persisted=False)
        (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
    finally:
        for proc in processes:
            if proc.poll() is None:proc.terminate()
        for proc in processes:
            try:proc.wait(timeout=10)
            except subprocess.TimeoutExpired:proc.kill();proc.wait()
        for log in logs:log.close()

if __name__=='__main__':main()
