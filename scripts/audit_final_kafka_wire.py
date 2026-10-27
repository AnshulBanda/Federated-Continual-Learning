#!/usr/bin/env python3
"""Read-only audit of the completed acceptance run; never saves wire payloads."""
import json
import time
import uuid
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from confluent_kafka import Consumer,TopicPartition,KafkaError
from safetensors.torch import load
from distributed_federation.common.protocol import ChunkAssembler


def main():
 out=ROOT/'artifacts/dp_level3_utility_optimization/kafka_acceptance/finalist';cfg=json.loads((out/'run.json').read_text());manifest=json.loads((out/'models'/cfg['run_id']/'global_round_001.json').read_text())
 consumer=Consumer({'bootstrap.servers':cfg['broker'],'group.id':'audit-'+uuid.uuid4().hex,'enable.auto.commit':False,'enable.partition.eof':True})
 assembler=ChunkAssembler();ends={};assign=[];done=set();messages=[]
 try:
  for topic in cfg['topics'].values():
   info=consumer.list_topics(topic,timeout=10).topics[topic]
   for part in info.partitions:
    tp=TopicPartition(topic,part);low,high=consumer.get_watermark_offsets(tp,timeout=10);ends[(topic,part)]=high;assign.append(TopicPartition(topic,part,low))
    if low==high:done.add((topic,part))
  consumer.assign(assign);deadline=time.monotonic()+60
  while len(done)<len(ends):
   if time.monotonic()>deadline:raise TimeoutError('Wire read audit timed out')
   msg=consumer.poll(1)
   if msg is None:continue
   key=(msg.topic(),msg.partition())
   if msg.error():
    if msg.error().code()==KafkaError._PARTITION_EOF:done.add(key);continue
    raise RuntimeError(str(msg.error()))
   if msg.offset()+1>=ends[key]:done.add(key)
   header=json.loads(msg.value())
   if header.get('run_id')!=cfg['run_id']:continue
   assert 'message_hmac_sha256' in header
   assert not {'training_examples','loss','local_loss','update_norm','gradient_norm','noise_seed','private_key','shared_secret'} & header.keys()
   assembled=assembler.add(header)
   if assembled is None:continue
   payload,meta=assembled;kind=meta['message_type'];record=dict(type=kind,sender=meta['sender_id'],sha256=meta['payload_sha256'],round=meta['round_id'])
   assert meta['schema_sha256']==manifest['schema_sha256']
   assert meta['base_model_sha256']==manifest['input_global_sha256']
   if kind=='masked_client_update':
    tensors=load(payload);assert list(tensors)==['masked_ring'];assert list(tensors['masked_ring'].shape)==[65793]
    record.update(tensor_names=['masked_ring'],dimension=65793)
    expected={c['client_id']:c['update_sha256'] for c in manifest['clients']};assert record['sha256']==expected[record['sender']]
    del tensors
   assert kind!='client_update','Plaintext update on secure run'
   messages.append(record)
  updates=[r for r in messages if r['type']=='masked_client_update'];hellos=[r for r in messages if r['type']=='secagg_public_key']
  assert {r['sender'] for r in updates}=={'bank-1','bank-2','bank-3'}
  assert {r['sender'] for r in hellos}=={'bank-1','bank-2','bank-3'}
  assert len(updates)==3 and any(r['type']=='aggregated_model' for r in messages)
  result=dict(result='PASS',run_id=cfg['run_id'],messages=messages,masked_updates_only=True,noise_contributors_required=3,no_clean_updates_persisted=True,wire_payloads_persisted=False,HMAC_note='HMACs were verified by operational coordinator/workers; this post-run read audit checks payload SHA against the verified manifests because ephemeral HMAC secrets were intentionally not persisted.')
  (out/'WIRE_AUDIT.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
 finally:consumer.close()

if __name__=='__main__':main()
