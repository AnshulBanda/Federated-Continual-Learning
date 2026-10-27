import copy
import hashlib
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src/gnn')]
from distributed_federation.privacy.mechanism import (Privacy,vector,restore,clip_vector,encode,decode,gaussian,client_contribution,aggregate)
from distributed_federation.privacy.secagg import ClientKey,Round,context,pack,canonical,accept_roster
from distributed_federation.privacy.ledger import Ledger
from distributed_federation.common.protocol import create_chunks,verify_chunk,ChunkAssembler

class SecureAggregationTests(unittest.TestCase):
    def setUp(self):
        self.ctx=context('run',1,['a','b','c'],'schema','base',242561)
        self.keys={c:ClientKey(c,self.ctx) for c in self.ctx['cohort']}
        self.server=Round(self.ctx)
        for c,k in self.keys.items():self.server.add_key(k.hello(),c)
    def meta(self):return {**self.ctx,'secagg_context_sha256':hashlib.sha256(canonical(self.ctx)).hexdigest(),'roster_sha256':hashlib.sha256(self.server.roster()).hexdigest()}
    def test_real_payload_ring_cancels_exactly_with_safetensors_and_hmac(self):
        total=np.zeros(242561,dtype=np.uint64)
        for c in self.keys:
            value=np.random.default_rng(ord(c)).integers(0,2**64,242561,dtype=np.uint64)
            total=np.add(total,value,dtype=np.uint64)
            masked=self.keys[c].mask(value,self.server.keys)
            self.assertFalse(np.array_equal(masked,value))
            payload=pack(masked)
            metadata=dict(message_type='masked_client_update',sender_id=c,**self.meta())
            assembler=ChunkAssembler();assembled=None
            chunks=create_chunks(payload,metadata,'h'*32,524288)
            for chunk in chunks:assembled=assembler.add(verify_chunk(chunk,'h'*32))
            self.server.add_update(c,*assembled)
        actual=np.zeros_like(total)
        for value in self.server.complete():actual=np.add(actual,value,dtype=np.uint64)
        np.testing.assert_array_equal(actual,total)
    def test_pair_secrets_and_server_hmac_are_distinct(self):
        a,b,c=[self.keys[x] for x in 'abc']
        self.assertEqual(a.secret('b',b.public),b.secret('a',a.public))
        self.assertNotEqual(a.secret('b',b.public),a.secret('c',c.public))
        self.assertNotEqual(a.secret('b',b.public),hashlib.sha256(b'h'*32).digest())
        self.assertNotIn('_private',vars(self.server))
    def test_new_keys_and_round_domains_never_reuse_masks(self):
        a,b=self.keys['a'],self.keys['b']
        secret=a.secret('b',b.public)
        for field,value in [('round_id',2),('run_id','run2')]:
            other=ClientKey('a',{**self.ctx,field:value})
            other._private=a._private # Hold ECDH fixed to isolate HKDF separation.
            self.assertNotEqual(secret,other.secret('b',b.public))
        self.assertNotEqual(a.public,ClientKey('a',self.ctx).public)
    def test_rejects_malformed_and_low_order_public_keys(self):
        for public in ('00','zz'*32,'00'*32):
            with self.assertRaises(ValueError):self.keys['a'].secret('b',public)
    def test_key_context_substitution_and_duplicates(self):
        for field,value in [('run_id','other'),('round_id',2),('schema_sha256','x'),('base_model_sha256','x'),('cohort',['a','b'])]:
            item=json.loads(self.keys['a'].hello());item['context'][field]=value
            with self.assertRaises(ValueError):Round(self.ctx).add_key(canonical(item),'a')
        with self.assertRaises(ValueError):self.server.add_key(self.keys['a'].hello(),'a')
        payload=json.loads(self.server.roster());payload['keys']['a']=self.keys['b'].public
        with self.assertRaises(ValueError):accept_roster(canonical(payload),self.keys['a'])
    def test_update_context_duplicate_missing_fail_closed_and_no_plaintext(self):
        payload=pack(np.zeros(242561,dtype=np.uint64));meta=self.meta()
        for field,value in [('run_id','x'),('round_id',2),('schema_sha256','x'),('base_model_sha256','x'),('roster_sha256','x'),('secagg_context_sha256','x')]:
            with self.assertRaises(ValueError):self.server.add_update('a',payload,{**meta,field:value})
        from safetensors.torch import save
        with self.assertRaises(ValueError):self.server.add_update('a',save({'raw':torch.zeros(242561)}),meta)
        self.server.add_update('a',payload,meta)
        with self.assertRaises(ValueError):self.server.add_update('a',payload,meta)
        with self.assertRaises(ValueError):self.server.complete()
        with self.assertRaises(ValueError):Round(self.ctx).roster()
    def test_hmac_tamper_rejected(self):
        chunk=create_chunks(b'x',dict(message_type='secagg_public_key',sender_id='a',**self.ctx),'h'*32,100)[0]
        obj=json.loads(chunk);obj['run_id']='bad'
        with self.assertRaises(ValueError):verify_chunk(canonical(obj),'h'*32)

class PrivacyMathTests(unittest.TestCase):
    def test_sensitivity_and_roundtrip_bound(self):
        cfg=Privacy(mode="secure_central_dp",clip=2)
        p=cfg.parameters(242561)
        self.assertEqual(p['ideal_sensitivity'],4/3)
        x=np.random.default_rng(8).normal(size=242561)
        x=clip_vector(x,2)
        self.assertLessEqual(np.linalg.norm(x),2+1e-12)
        y=decode(encode(x,cfg.scale),cfg.scale)
        self.assertLessEqual(np.linalg.norm(x-y),p['quantization_l2_bound'])
        self.assertGreaterEqual(p['sensitivity'],4/3)
    def test_clipping_central_sigma_and_accounting_independent(self):
        cfg=Privacy(mode='secure_central_dp',clip=2,multiplier=3)
        p=cfg.parameters(7)
        self.assertAlmostEqual(p['sigma_mean'],3*p['sensitivity'])
        actual=cfg.accounting(8)
        rho=8/(2*3**2)
        self.assertAlmostEqual(actual['epsilon'],rho+2*math.sqrt(rho*math.log(1e6)))
        self.assertEqual(Privacy(mode='distributed_dp',multiplier=3).accounting(8)['rho'],3*rho)
        self.assertEqual(cfg.accounting(0)['epsilon'],0)
    def test_monte_carlo_distributed_variance_mean_independence_and_gaussian_reference(self):
        cfg=Privacy(mode='distributed_dp',clip=2,multiplier=.7,entropy='research')
        p=cfg.parameters(1);size=180000
        shares=np.array([gaussian(size,p['sigma_share'],cfg,'run',1,c) for c in 'abc'])
        mean=np.mean(shares,axis=0)
        target=p['sigma_mean']**2
        self.assertLess(abs(mean.mean()),.01*p['sigma_mean'])
        self.assertLess(abs(mean.var()/target-1),.015)
        for i in range(3):self.assertLess(abs(shares[i].var()/p['sigma_share']**2-1),.015)
        self.assertLess(abs(np.corrcoef(shares)[0,1]),.01)
        # Rounded ring Gaussian shares retain the predicted variance numerically.
        encoded=np.zeros(size,dtype=np.uint64)
        for share in shares:encoded=np.add(encoded,encode(share,cfg.scale),dtype=np.uint64)
        np.testing.assert_allclose(decode(encoded,cfg.scale)/3,mean,atol=1/cfg.scale)
        from scipy.stats import ks_2samp
        direct=np.random.default_rng(9).normal(0,p['sigma_mean'],size)
        self.assertGreater(ks_2samp(mean,direct).pvalue,.001)
    def test_production_sampler_and_integrated_clipping_noise_shapes(self):
        cfg=Privacy(mode='distributed_dp',clip=2,multiplier=.7)
        sigma=cfg.parameters(1)['sigma_share']
        shares=np.array([gaussian(180000,sigma,cfg,'production',1,c) for c in 'abc'])
        self.assertLess(abs(shares.mean()),.02*sigma)
        self.assertLess(abs(shares.var()/sigma**2-1),.02)
        self.assertLess(abs(np.corrcoef(shares)[0,1]),.02)
        base={'a':torch.zeros(5),'b':torch.zeros(2,3)}
        large={k:torch.ones_like(v)*1000 for k,v in base.items()}
        zero=Privacy(mode='secure_central_dp',clip=2)
        encoded=client_contribution(large,base,zero,'r',1,'a')
        self.assertLessEqual(np.linalg.norm(decode(encoded,zero.scale)),zero.parameters(11)['effective_clip'])
        central=Privacy(mode='secure_central_dp',clip=2,multiplier=.1)
        noisy=aggregate([encoded]*3,base,central,'r',1)
        self.assertEqual(noisy['b'].shape,base['b'].shape)
        self.assertTrue(np.isfinite(vector(noisy)).all())
    def test_rng_repeatability_and_production_entropy(self):
        cfg=Privacy(mode='distributed_dp',entropy='research')
        first=gaussian(100,1,cfg,'r',1,'a')
        np.testing.assert_array_equal(first,gaussian(100,1,cfg,'r',1,'a'))
        for round_id,client in ((2,'a'),(1,'b')):
            self.assertFalse(np.array_equal(first,gaussian(100,1,cfg,'r',round_id,client)))
        prod=Privacy()
        self.assertFalse(np.array_equal(gaussian(100,1,prod,'r',1,'a'),gaussian(100,1,prod,'r',1,'a')))
    def test_zero_noise_modes_equivalence_and_shapes(self):
        base={'a':torch.zeros(17),'b':torch.zeros(2,3)}
        local=[{'a':torch.ones(17)*i/100,'b':torch.ones(2,3)*i/100} for i in range(3)]
        results=[]
        for mode in ('none','secure_central_dp','distributed_dp'):
            cfg=Privacy(mode=mode,clip=10)
            updates=[client_contribution(s,base,cfg,'r',1,str(i)) for i,s in enumerate(local)]
            result=aggregate(updates,base,cfg,'r',1);results.append(vector(result))
            self.assertEqual(result['b'].dtype,torch.float32)
        np.testing.assert_allclose(results[0],results[1],atol=1e-7)
        np.testing.assert_array_equal(results[1],results[2])
    def test_noise_remains_after_masks_and_central_sees_only_masked(self):
        base={'w':torch.zeros(8000)};cfg=Privacy(mode='distributed_dp',multiplier=1,entropy='research')
        ctx=context('r',1,'abc','s','b',8000);keys={c:ClientKey(c,ctx) for c in 'abc'}
        roster={c:k.public for c,k in keys.items()}
        plain=[client_contribution(base,base,cfg,'r',1,c) for c in 'abc']
        masked=[keys[c].mask(v,roster) for c,v in zip('abc',plain)]
        a=aggregate(plain,base,cfg,'r',1);b=aggregate(masked,base,cfg,'r',1)
        np.testing.assert_array_equal(vector(a),vector(b));self.assertGreater(np.linalg.norm(vector(b)),1)
    def test_incomplete_noise_cohort_and_weighted_not_supported(self):
        with self.assertRaises(ValueError):Privacy(min_noise_contributors=2)
        with self.assertRaisesRegex(ValueError,'Unsafe fixed-point'):
            Privacy(mode='distributed_dp',clip=1e20,multiplier=1).parameters(242561)
        with self.assertRaises(ValueError):aggregate([np.zeros(1)],{'x':torch.zeros(1)},Privacy(mode='distributed_dp'),'r',1)
    def test_ledger_restart_and_duplicate_guard_no_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'ledger.sqlite3';ledger=Ledger(path)
            cfg={'multiplier':1};ledger.reserve('run',1,'a',cfg);ledger.close()
            ledger=Ledger(path)
            with self.assertRaises(ValueError):ledger.reserve('run',1,'a',cfg)
            ledger.reserve('new-run',1,'a',cfg)
            self.assertEqual(len(ledger.entries()),2)
            self.assertNotIn('secret',str(ledger.entries()));ledger.close()

class TrainingEquivalenceTests(unittest.TestCase):
    def test_distributed_shared_trainer_matches_research_local_exactly(self):
        import adaptive_continual_federated as research
        from causal_temporal_graphsage import CausalTemporalGraphSAGE,Events
        from distributed_federation.common.model_runtime import RuntimeData,train_local
        torch.manual_seed(3)
        static=torch.randn(4,3)
        events=Events(torch.arange(24)%4,(torch.arange(24)+1)%4,torch.randn(24,2),
            torch.arange(24).float(),torch.tensor([float(i%5==0) for i in range(24)]))
        model=CausalTemporalGraphSAGE(3,2,4,.25)
        reference=copy.deepcopy(model);runtime=RuntimeData(model,static,{'training':events},{},'x')
        cfg=SimpleNamespace(local_epochs=2,learning_rate=.001,batch_size=3,replay_size=6,replay='risk_context',
            distill=0.,rng_policy='per_client',seed=42,dataset_dir=Path('unused'),clients=[SimpleNamespace(bank='a')])
        research.train_client(reference,static,events,12.,cfg,42+200)
        with patch.object(research,'calendar_boundary',return_value=12.):train_local(runtime,cfg,2,0)
        for key,value in reference.state_dict().items():self.assertTrue(torch.equal(value,model.state_dict()[key]),key)
        self.assertEqual(set(vector(model.state_dict()).shape),{len(vector(model.state_dict()))})
        self.assertEqual(len(model.state_dict()),len(dict(model.named_parameters())))

if __name__=='__main__':
    torch.set_num_threads(1);unittest.main()
