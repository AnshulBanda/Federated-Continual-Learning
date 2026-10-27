"""Single-model repair, privacy floor and noisy-only server regression checks."""
import copy
import hashlib
import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
import torch

from distributed_federation.common.config import load_config
from distributed_federation.common.model_runtime import prepare_frozen_runtime,load_initial_checkpoint,train_local
from distributed_federation.common.events import event_sink
from distributed_federation.privacy import transport
from distributed_federation.privacy.mechanism import Privacy,vector,restore
from distributed_federation.privacy.server_optimizer import ServerConfig,ServerOptimizer
from distributed_federation.privacy.subset import extract,parameter_keys
from streaming.app.final_federation import ROOT,FIXED,PRIVACY,SERVER,WARM,WARM_SHA256,OLD_EPSILON
from streaming.app.collaboration import Collaboration
from streaming.app.final_model import reference_model,score_models
from streaming.app.privacy import privacy_status


class PrivateSingleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.manager=Collaboration(self.root)
        self.raw=self.manager.config(dict(self.manager.defaults(),dataset=str(self.root)))
        self.path=self.root/'config.json';self.path.write_text(json.dumps(self.raw))
        self.cfg=load_config(self.path)

    def test_exact_single_warm_state_decoder_dimension_and_freezing(self):
        runtime=prepare_frozen_runtime(self.cfg)
        self.assertNotIsInstance(runtime.model,torch.nn.ModuleDict)
        self.assertEqual(type(runtime.model).__name__,'CausalTemporalGraphSAGE')
        self.assertEqual(hashlib.sha256((ROOT/WARM).read_bytes()).hexdigest(),WARM_SHA256)
        load_initial_checkpoint(runtime.model,self.cfg.initial_checkpoint)
        saved=torch.load(ROOT/WARM,map_location='cpu',weights_only=True)['state_dict']
        for k,v in saved.items():self.assertTrue(torch.equal(v,runtime.model.state_dict()[k]))
        state=runtime.model.state_dict();private=extract(state,'decoder')
        self.assertEqual(sum(t.numel() for t in private.values()),65793)
        self.assertEqual(sum(t.numel() for t in state.values()),242561)
        self.assertTrue(all(k.startswith('decoder.') for k in private))
        self.assertFalse(any(k.startswith(('42.','52.','62.')) for k in state))

    def test_four_release_floor_and_postprocess_math(self):
        account=Privacy(**PRIVACY).accounting(4)
        self.assertLessEqual(account['epsilon'],OLD_EPSILON)
        self.assertEqual(account['rho'],Privacy(mode='distributed_dp',multiplier=.15).accounting(1)['rho'])
        self.assertGreater(Privacy(mode='distributed_dp',multiplier=.15).accounting(4)['epsilon'],OLD_EPSILON)
        self.assertEqual(account['bound'],'encoded_share_postprocessing')
        base={'decoder.w':torch.tensor([1.,-2.])};noisy={'decoder.w':torch.tensor([3.,5.])}
        result=ServerOptimizer(ServerConfig(**SERVER)).apply(base,noisy)
        expected=restore(vector(base)+SERVER['learning_rate']*(vector(noisy)-vector(base)),base)
        for k in result:self.assertTrue(torch.equal(result[k],expected[k]))

    def test_retired_private_ensemble_rejected_at_parser_and_transport(self):
        raw=dict(self.raw,training_protocol='adaptive_ensemble',private_subset='ensemble_decoder')
        self.path.write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError,'retired'):load_config(self.path)
        with self.assertRaisesRegex(ValueError,'retired'):transport._guard(replace(self.cfg,training_protocol='adaptive_ensemble'))
        with self.assertRaisesRegex(ValueError,'retired'):prepare_frozen_runtime(replace(self.cfg,training_protocol='adaptive_ensemble'))

    def test_single_training_freezes_backbone_and_releases_no_diagnostics(self):
        from causal_temporal_graphsage import CausalTemporalGraphSAGE,Events
        torch.manual_seed(4);torch.set_num_threads(1)
        model=CausalTemporalGraphSAGE(3,2,4,.25);initial=copy.deepcopy(model.state_dict())
        runtime=SimpleNamespace(model=model,static=torch.randn(4,3),streams={'training':Events(
            torch.arange(48)%4,(torch.arange(48)+1)%4,torch.randn(48,2),torch.arange(48).float(),
            torch.tensor([float(i%5==0) for i in range(48)]))})
        events=[]
        with patch('adaptive_continual_federated.calendar_boundary',return_value=24.),event_sink(lambda k,round_id=None,**d:events.append((k,d))):
            self.assertIsNone(train_local(runtime,self.cfg,1,0))
        self.assertEqual(events,[])
        for k,v in initial.items():
            if not k.startswith('decoder.'):self.assertTrue(torch.equal(v,model.state_dict()[k]),k)
        self.assertTrue(any(not torch.equal(initial[k],model.state_dict()[k]) for k in parameter_keys(initial,'decoder')))

    def test_single_inference_does_not_average_models(self):
        model=SimpleNamespace(initial_state=lambda _:None)
        streams={'training':object(),'validation':object()}
        probabilities=np.array([.2,.8]);labels=np.array([0.,1.])
        with patch('src.gnn.causal_temporal_graphsage.score_stream',side_effect=[(None,None,None),(probabilities,labels,None)]),patch('numpy.mean',side_effect=AssertionError('No single-model averaging')):
            actual,actual_labels,members=score_models([model],None,streams)
        np.testing.assert_array_equal(actual,probabilities);self.assertEqual(len(members),1)

    def test_reference_and_private_scopes_remain_separate(self):
        selected=reference_model('Key_Bank')
        self.assertEqual([m['seed'] for m in selected['members']],[42,52,62])
        self.assertFalse(selected['privacy']['differential_privacy'])
        scopes=privacy_status()['scopes']
        self.assertFalse(scopes['reference_ensemble']['differential_privacy'])
        self.assertTrue(scopes['operational_collaboration']['differential_privacy'])
        self.assertIn('Single-model',scopes['operational_collaboration']['scope'])

    def test_research_seeds_are_same_single_warm_model(self):
        out=ROOT/'artifacts/dp_singlemodel_r4e3'
        for seed in (42,52,62):
            record=json.loads((out/'research'/f'half_C_s{seed}'/'RESULT.json').read_text())
            self.assertTrue(record['single_model']);self.assertEqual(record['warm_sha256'],WARM_SHA256)
            self.assertEqual(record['seed'],seed);self.assertEqual(record['private_dimension'],65793)
            self.assertFalse(record['September_loaded']);self.assertFalse(record['testing_loaded'])
            self.assertEqual([r['round'] for r in record['history']],[0,1,2,3,4])


if __name__=='__main__':unittest.main()
