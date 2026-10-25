"""Full client/coordinator state machines over signed duplicate chunk delivery."""
import copy
import hashlib
import json
import queue
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import torch
from distributed_federation.privacy import transport
from distributed_federation.common.config import load_config,secret_env_name
from distributed_federation.common.checkpoints import verify_checkpoint
from distributed_federation.common.events import event_sink
from distributed_federation.common.model_runtime import deserialize_state

class Message:
    def __init__(self,value):self.raw=value
    def value(self):return self.raw
    def error(self):return None
class Consumer:
    def __init__(self,q):self.q=q
    def poll(self,timeout):
        try:return self.q.get(timeout=min(timeout,.02))
        except queue.Empty:return None
    def commit(self,**kw):pass
    def close(self):pass

class PrivateRoundTrip(unittest.TestCase):
    def run_mode(self,mode,m):
        with tempfile.TemporaryDirectory() as temp:
            raw=json.loads((Path(__file__).resolve().parents[1]/'configs/privacy_distributed_dp.json').read_text())
            raw.update(dataset_dir=temp,output_dir=str(Path(temp)/'out'),feature_schema=str(Path(temp)/'schema.json'),rounds=2,round_timeout_seconds=10)
            raw['privacy']['mode']=mode;raw['privacy']['multiplier']=m
            path=Path(temp)/'config.json';path.write_text(json.dumps(raw));cfg=load_config(path)
            upstream=queue.Queue();queues={c.client_id:queue.Queue() for c in cfg.clients}
            barrier=threading.Barrier(4);messages=[];events=[]
            def consumer(broker,group,topics):
                q=upstream if topics==[cfg.update_topic] else queues[next(c for c in queues if group.endswith(c))]
                barrier.wait(timeout=5);return Consumer(q)
            class Producer:
                def produce(self,topic,key,value,callback):
                    messages.append(json.loads(value))
                    for q in (queues.values() if topic==cfg.global_topic else [upstream]):
                        q.put(Message(value));q.put(Message(value))
                    callback(None,None)
                def poll(self,*a):pass
                def flush(self,*a):return 0
            def runtime(*args):
                model=torch.nn.Linear(3,2)
                with torch.no_grad():
                    for p in model.parameters():p.zero_()
                return SimpleNamespace(model=model,schema={},schema_sha256='schema',streams={'training':list(range(4))})
            def train(rt,cfg,rid,index):
                with torch.no_grad():
                    for p in rt.model.parameters():p.add_((index+1)/100)
            secrets={'FCL_CENTRAL_SECRET':'c'*32,'FCL_CLIENT_SECRET':'s'*32}
            secrets.update({secret_env_name(c.client_id):'s'*32 for c in cfg.clients})
            with patch.dict('os.environ',secrets),patch.object(transport,'make_consumer',side_effect=consumer),patch.object(transport,'make_producer',side_effect=lambda _:Producer()),patch.object(transport,'prepare_runtime',side_effect=runtime),patch.object(transport,'prepare_frozen_runtime',side_effect=runtime),patch.object(transport,'train_local',side_effect=train):
                def central():
                    with event_sink(lambda kind,round_id=None,**data:events.append((kind,round_id,data))):return transport.central(cfg)
                with ThreadPoolExecutor(4) as pool:
                    jobs=[pool.submit(transport.worker,cfg,c.client_id) for c in cfg.clients]+[pool.submit(central)]
                    self.assertEqual([f.result(timeout=15) for f in jobs],[0]*4)
            root=cfg.output_dir/cfg.run_id
            for rid in (1,2):
                verify_checkpoint(root,rid)
                payload=(root/f'global_round_{rid:03d}.safetensors').read_bytes()
                for c in cfg.clients:
                    verify_checkpoint(root/c.client_id,rid)
                    self.assertEqual(payload,(root/c.client_id/f'global_round_{rid:03d}.safetensors').read_bytes())
            state=deserialize_state(payload)
            if m==0:
                for p in state.values():self.assertTrue(torch.allclose(p,torch.full_like(p,.04),atol=1e-7))
            kinds={x['message_type'] for x in messages}
            self.assertIn('masked_client_update',kinds);self.assertNotIn('client_update',kinds)
            self.assertIn('secagg_public_key',kinds);self.assertIn('secagg_ready',kinds)
            for x in messages:
                self.assertNotIn('training_examples',x);self.assertNotIn('mean_train_loss',x)
            manifest=json.loads((root/'global_round_002.json').read_text())
            self.assertEqual(manifest['accounting']['releases'],2)
            self.assertFalse(any('norm' in str(e) or 'noise_share' in str(e) or 'private_key' in str(e) for e in events))
    def test_missing_secure_client_and_restart_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            raw=json.loads((Path(__file__).resolve().parents[1]/'configs/privacy_distributed_dp.json').read_text())
            raw.update(dataset_dir=temp,output_dir=str(Path(temp)/'out'),feature_schema=str(Path(temp)/'schema.json'))
            path=Path(temp)/'config.json';path.write_text(json.dumps(raw))
            cfg=replace(load_config(path),round_timeout_seconds=0)
            rt=SimpleNamespace(model=torch.nn.Linear(3,2),schema={},schema_sha256='schema')
            secrets={'FCL_CENTRAL_SECRET':'c'*32,**{secret_env_name(c.client_id):'s'*32 for c in cfg.clients}}
            with patch.dict('os.environ',secrets),patch.object(transport,'prepare_frozen_runtime',return_value=rt),patch.object(transport,'make_producer'),patch.object(transport,'make_consumer'),patch.object(transport,'publish_payload'),patch.object(transport,'aggregate') as private_average,patch.object(transport,'fedavg') as plain_average:
                with self.assertRaises(TimeoutError):transport.central(cfg)
                private_average.assert_not_called();plain_average.assert_not_called()
                with self.assertRaisesRegex(ValueError,'Already reserved'):transport.central(cfg)
            self.assertFalse((cfg.output_dir/cfg.run_id).exists())
    def test_central_dp_zero_noise_and_distributed_private_round_trip(self):
        self.run_mode('secure_central_dp',0.)
        self.run_mode('distributed_dp',.1)
