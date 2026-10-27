"""X25519 + HKDF-SHA256 + ChaCha20 masks in Z/(2**64).

Private keys exist only in the client process and are fresh each round.
The server relays authenticated public rosters. HBC server, noncolluding banks;
this is not malicious-server/Byzantine/dropout-robust secure aggregation.
"""
import hashlib
import json
import numpy as np
import torch
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms


def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def context(run_id,round_id,cohort,schema,base,dimension):
    cohort = sorted(cohort)
    if len(cohort)!=len(set(cohort)) or len(cohort)<2 or round_id<1 or dimension<1:
        raise ValueError('Invalid cohort/round/dimension')
    return dict(run_id=run_id,round_id=round_id,cohort=cohort,schema_sha256=schema,
                base_model_sha256=base,dimension=dimension,domain='secagg-ring64-v1')


class ClientKey:
    def __init__(self,identity,ctx):
        if identity not in ctx['cohort']: raise ValueError('Unknown participant')
        self.identity,self.ctx = identity,ctx
        self._private = X25519PrivateKey.generate()
        self.public = self._private.public_key().public_bytes_raw().hex()

    def hello(self): return canonical(dict(context=self.ctx,client_id=self.identity,public_key=self.public))

    def secret(self,peer,public):
        if peer==self.identity or peer not in self.ctx['cohort']: raise ValueError('Invalid peer')
        try:
            key=bytes.fromhex(public)
            if len(key)!=32: raise ValueError('Wrong public key length')
            shared=self._private.exchange(X25519PublicKey.from_public_bytes(key))
        except (ValueError,TypeError) as exc: raise ValueError('Malformed/low-order X25519 public key') from exc
        domain=canonical(dict(context=self.ctx,pair=sorted([peer,self.identity])))
        return HKDF(algorithm=hashes.SHA256(),length=32,salt=hashlib.sha256(domain).digest(),info=b'pairwise-mask').derive(shared)

    def mask(self,contribution,roster):
        if set(roster)!=set(self.ctx['cohort']) or roster[self.identity]!=self.public:
            raise ValueError('Roster substitution/missing cohort')
        if len(contribution)!=self.ctx['dimension'] or contribution.dtype!=np.uint64:
            raise ValueError('Wrong contribution representation')
        result=contribution.copy()
        for peer in sorted(roster):
            if peer==self.identity: continue
            key=self.secret(peer,roster[peer])
            # Key already domain-separated by the complete round context.
            stream=Cipher(algorithms.ChaCha20(key,b'\0'*16),mode=None).encryptor().update(bytes(len(result)*8))
            pad=np.frombuffer(stream,dtype='<u8')
            result=(np.add(result,pad,dtype=np.uint64) if self.identity<peer
                    else np.subtract(result,pad,dtype=np.uint64))
        return result


class Round:
    def __init__(self,ctx): self.ctx,self.keys,self.updates=ctx,{},{}
    def add_key(self,payload,sender):
        item=json.loads(payload)
        if item.get('context')!=self.ctx or item.get('client_id')!=sender or sender not in self.ctx['cohort']:
            raise ValueError('Key context/identity mismatch')
        if sender in self.keys: raise ValueError('Duplicate key')
        public=item['public_key']
        # Also reject the low-order all-zero key via ephemeral validation exchange.
        ClientKey(self.ctx['cohort'][0],self.ctx).secret(
            next(x for x in self.ctx['cohort'] if x!=self.ctx['cohort'][0]),public)
        if public in self.keys.values(): raise ValueError('Duplicate public key')
        self.keys[sender]=public
    def roster(self):
        if set(self.keys)!=set(self.ctx['cohort']): raise ValueError('Incomplete key cohort')
        return canonical(dict(context=self.ctx,keys=self.keys))
    def add_update(self,sender,payload,metadata):
        if set(self.keys)!=set(self.ctx['cohort']): raise ValueError('Key exchange incomplete')
        if sender not in self.keys or sender in self.updates: raise ValueError('Unknown/duplicate participant')
        for name in ('run_id','round_id','schema_sha256','base_model_sha256'):
            if metadata.get(name)!=self.ctx[name]: raise ValueError('Update context mismatch: '+name)
        if metadata.get('secagg_context_sha256')!=hashlib.sha256(canonical(self.ctx)).hexdigest():
            raise ValueError('Cohort/encoding context mismatch')
        if metadata.get('roster_sha256')!=hashlib.sha256(self.roster()).hexdigest():
            raise ValueError('Key roster mismatch')
        from safetensors.torch import load
        tensors=load(payload)
        if set(tensors)!={'masked_ring'}: raise ValueError('Plaintext/model payload rejected')
        value=tensors['masked_ring']
        if value.dtype!=torch.int64 or list(value.shape)!=[self.ctx['dimension']]:
            raise ValueError('Masked payload schema mismatch')
        self.updates[sender]=value.numpy().view(np.uint64).copy()
    def complete(self):
        if set(self.updates)!=set(self.ctx['cohort']): raise ValueError('Incomplete update cohort; no plaintext fallback')
        return [self.updates[x] for x in self.ctx['cohort']]


def pack(masked):
    from safetensors.torch import save
    return save({'masked_ring':torch.from_numpy(masked.view(np.int64).copy())})


def accept_roster(payload,key):
    item=json.loads(payload)
    if item.get('context')!=key.ctx: raise ValueError('Wrong roster context')
    keys=item.get('keys',{})
    if set(keys)!=set(key.ctx['cohort']) or keys[key.identity]!=key.public: raise ValueError('Invalid roster')
    for peer in keys:
        if peer!=key.identity: key.secret(peer,keys[peer])
    return keys
