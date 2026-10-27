"""Bank-level ensemble sensitivity, initialization, freezing and scope checks."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import torch

from distributed_federation.privacy import mechanism
from distributed_federation.privacy.subset import parameter_keys,extract,configure_trainable,reconstruct
from distributed_federation.common.events import event_sink
from distributed_federation.common.model_runtime import train_local
from streaming.app.final_model import build_ensemble,frozen_encoders,reference_model
from streaming.app.final_federation import PRIVACY,FIXED,PRIVATE_DIMENSION,OLD_EPSILON
from streaming.app.privacy import privacy_status


class PrivateEnsembleTests(unittest.TestCase):
    def test_actual_three_member_keys_hashes_and_dimensions(self):
        _,_,schema=frozen_encoders();model=build_ensemble(schema)
        self.assertEqual(list(model),['42','52','62'])
        state=model.state_dict();keys=parameter_keys(state,'ensemble_decoder')
        expected=sorted(f'{seed}.decoder.{k}' for seed,member in model.items() for k in member.decoder.state_dict())
        self.assertEqual(keys,expected)
        self.assertEqual(sum(state[k].numel() for k in keys),197379)
        self.assertEqual(PRIVATE_DIMENSION,197379)
        for seed in model:
            self.assertEqual(sum(v.numel() for k,v in state.items() if k.startswith(seed+'.decoder.')),65793)
        for member in reference_model('Key_Bank')['members']:
            self.assertEqual(hashlib.sha256(Path(member['checkpoint']).read_bytes()).hexdigest(),member['sha256'])
            saved=torch.load(member['checkpoint'],map_location='cpu',weights_only=True)['state_dict']
            for key,value in saved.items():self.assertTrue(torch.equal(state[str(member['seed'])+'.'+key],value))
            self.assertEqual(set(model[str(member['seed'])].state_dict()),{k.split('.',1)[1] for k in state if k.startswith(str(member['seed'])+'.')})
        with self.assertRaises(ValueError):parameter_keys(state,'decoder')
        missing={k:v for k,v in state.items() if not k.startswith('62.decoder.')}
        with self.assertRaises(ValueError):parameter_keys(missing,'ensemble_decoder')

    def test_one_global_clip_and_one_noise_vector_not_per_member(self):
        base={f'{seed}.decoder.weight':torch.zeros(1) for seed in (42,52,62)}
        local={k:torch.tensor([v]) for k,v in zip(base,(3.,4.,12.))}
        privacy=mechanism.Privacy(**PRIVACY)
        with patch.object(mechanism,'clip_vector',wraps=mechanism.clip_vector) as clip,\
             patch.object(mechanism,'gaussian',return_value=np.zeros(3)) as noise:
            result=mechanism.client_contribution(local,base,privacy,'run',1,'bank-1')
        clip.assert_called_once();noise.assert_called_once()
        self.assertEqual(noise.call_args.args[0],3)
        decoded=mechanism.decode(result,privacy.scale)
        np.testing.assert_allclose(decoded,np.array([3.,4.,12.])*.5,atol=1/2**24)
        self.assertAlmostEqual(np.linalg.norm(decoded),6.5,places=7)
        self.assertGreater(np.linalg.norm(np.minimum([3.,4.,12.],6.5)),6.5)

    def test_four_release_accounting_preserves_old_budget(self):
        new=mechanism.Privacy(**PRIVACY).accounting(FIXED['rounds'])
        old=mechanism.Privacy(mode='distributed_dp',multiplier=.15).accounting(1)
        self.assertEqual(FIXED['rounds'],4)
        self.assertGreaterEqual(PRIVACY['multiplier'],.30)
        self.assertEqual(new['rho'],old['rho'])
        self.assertLessEqual(new['epsilon'],OLD_EPSILON)
        self.assertEqual(new['bound'],'encoded_share_postprocessing')
        self.assertGreater(mechanism.Privacy(mode='distributed_dp',multiplier=.15).accounting(4)['epsilon'],OLD_EPSILON)

    def test_reconstructs_all_decoders_and_preserves_frozen_coordinates(self):
        _,_,schema=frozen_encoders();model=build_ensemble(schema);base=model.state_dict()
        keys=configure_trainable(model,'ensemble_decoder')
        for name,p in model.named_parameters():self.assertEqual(p.requires_grad,name in keys)
        updated={k:v+.01 for k,v in extract(base,'ensemble_decoder').items()}
        result=reconstruct(base,updated,'ensemble_decoder')
        for k in base:self.assertTrue(torch.equal(result[k],updated[k] if k in updated else base[k]),k)

    def test_real_local_ensemble_trainer_updates_only_decoders_and_hides_diagnostics(self):
        from causal_temporal_graphsage import CausalTemporalGraphSAGE,Events
        torch.manual_seed(4);torch.set_num_threads(1)
        model=torch.nn.ModuleDict({str(s):CausalTemporalGraphSAGE(3,2,4,.25) for s in (42,52,62)})
        initial=copy.deepcopy(model.state_dict())
        runtime=SimpleNamespace(model=model,static=torch.randn(4,3),streams={'training':Events(
            torch.arange(48)%4,(torch.arange(48)+1)%4,torch.randn(48,2),torch.arange(48).float(),
            torch.tensor([float(i%5==0) for i in range(48)]))})
        cfg=SimpleNamespace(**FIXED,privacy=mechanism.Privacy(**PRIVACY),dataset_dir=Path('unused'),
                            clients=[SimpleNamespace(bank=b) for b in ('a','b','c')])
        events=[]
        with patch('adaptive_continual_federated.calendar_boundary',return_value=24.),\
             event_sink(lambda kind,round_id=None,**data:events.append((kind,data))):
            result=train_local(runtime,cfg,1,0)
        self.assertIsNone(result);self.assertEqual(events,[])
        final=model.state_dict();private=parameter_keys(final,'ensemble_decoder')
        for k in initial:
            if k not in private:self.assertTrue(torch.equal(initial[k],final[k]),k)
        for seed in model:self.assertTrue(any(not torch.equal(initial[k],final[k]) for k in private if k.startswith(seed+'.')))

    def test_reference_and_operational_scopes_are_distinct(self):
        status=privacy_status()
        reference=status['scopes']['reference_ensemble'];operational=status['scopes']['operational_collaboration']
        self.assertFalse(reference['differential_privacy']);self.assertIsNone(reference['epsilon'])
        self.assertAlmostEqual(reference['exploratory_september_pr_auc'],.9067783483397621)
        self.assertTrue(operational['differential_privacy']);self.assertTrue(operational['secagg'])
        self.assertLessEqual(operational['epsilon'],OLD_EPSILON)
        self.assertIn('nonprivate frozen',operational['scope'])

    def test_privacy_http_endpoint_keeps_reference_and_collaboration_separate(self):
        import threading,urllib.request
        from streaming.app.dashboard import server
        with tempfile.TemporaryDirectory() as root:
            app=server(root,0)
            thread=threading.Thread(target=app.serve_forever,daemon=True);thread.start()
            try:
                status=json.load(urllib.request.urlopen(f'http://127.0.0.1:{app.server_port}/api/privacy'))
                self.assertFalse(status['scopes']['reference_ensemble']['differential_privacy'])
                private=status['scopes']['operational_collaboration']
                self.assertTrue(private['differential_privacy']);self.assertTrue(private['secagg'])
                self.assertEqual(private['required_cohort'],3)
                self.assertLessEqual(private['epsilon'],OLD_EPSILON)
            finally:app.shutdown();thread.join();app.server_close()


if __name__=='__main__':unittest.main()
