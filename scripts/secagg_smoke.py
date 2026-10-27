#!/usr/bin/env python3
"""Run an authenticated, serialized 242,561-coordinate SecAgg simulation, no data."""
import hashlib
import json
import sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from distributed_federation.privacy.secagg import ClientKey,Round,context,pack,canonical
from distributed_federation.privacy.mechanism import encode,decode
from distributed_federation.common.protocol import create_chunks,verify_chunk,ChunkAssembler

def main():
    ctx=context('smoke',1,['bank-1','bank-2','bank-3'],'schema','base',242561)
    keys={c:ClientKey(c,ctx) for c in ctx['cohort']};server=Round(ctx)
    for c,key in keys.items():server.add_key(key.hello(),c)
    total=np.zeros(242561,dtype=np.uint64)
    for index,(c,key) in enumerate(keys.items()):
        contribution=encode(np.full(242561,(index+1)/100),2**24)
        total=np.add(total,contribution,dtype=np.uint64)
        meta=dict(message_type='masked_client_update',sender_id=c,**ctx,
            secagg_context_sha256=hashlib.sha256(canonical(ctx)).hexdigest(),roster_sha256=hashlib.sha256(server.roster()).hexdigest())
        payload=pack(key.mask(contribution,server.keys));assembler=ChunkAssembler()
        for chunk in create_chunks(payload,meta,'test-secret-no-real-credentials-00',524288):
            assembled=assembler.add(verify_chunk(chunk,'test-secret-no-real-credentials-00'))
        server.add_update(c,*assembled)
    result=np.zeros_like(total)
    for value in server.complete():result=np.add(result,value,dtype=np.uint64)
    assert np.array_equal(result,total)
    print(json.dumps(dict(result='PASS',dimension=len(total),exact_ring_cancellation=True,mean=float(decode(result,2**24).mean()/3)),indent=2))
if __name__=='__main__':main()
