"""Regression checks for actual final-model wiring, privacy claims and XAI isolation."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from streaming.app.final_model import reference_model, validate_selected, reference_evidence, frozen_encoders, build_ensemble
from streaming.app.privacy import privacy_status
from streaming.app.explanations import Explanations
from streaming.app.monitoring import Monitoring
from streaming.app.local_training import write_json, now
from streaming.app.collaboration import Collaboration

class FinalEnsembleTests(unittest.TestCase):
    def test_reference_members_match_frozen_hashes_and_score(self):
        selected=reference_model('Key_Bank')
        self.assertEqual([m['seed'] for m in selected['members']],[42,52,62])
        validate_selected(selected)
        self.assertAlmostEqual(reference_evidence()['macro_pr_auc'],.9067783483397621)
        self.assertFalse(selected['privacy']['differential_privacy'])
    def test_missing_member_and_hash_change_fail_closed(self):
        selected=reference_model('Key_Bank');selected['members'].pop()
        with self.assertRaises(ValueError):validate_selected(selected)
        selected=reference_model('Key_Bank');selected['members'][0]['sha256']='0'*64
        with self.assertRaises(ValueError):validate_selected(selected)
    def test_collaboration_uses_final_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=Collaboration(tmp); cfg=app.config(app.defaults())
            self.assertEqual(cfg['training_protocol'],'adaptive_ensemble')
            self.assertEqual(cfg['replay_size'],2000)
            self.assertEqual(cfg['local_epochs'],3)
    def test_serialized_ensemble_round_trip_and_harmonization(self):
        import torch
        from distributed_federation.common.model_runtime import serialize_state,deserialize_state,aggregate_adaptive
        torch.set_num_threads(1)
        _,_,schema=frozen_encoders(); model=build_ensemble(schema)
        state=model.state_dict(); reloaded=deserialize_state(serialize_state(state))
        self.assertEqual(set(reloaded),set(state))
        for key in state:self.assertTrue(torch.equal(state[key],reloaded[key]))
        combined=aggregate_adaptive([state,copy.deepcopy(state)],state)
        for key in state:self.assertTrue(torch.equal(state[key],combined[key]))
    def test_privacy_report_does_not_confuse_signatures_with_dp(self):
        status=privacy_status()
        self.assertFalse(status['differential_privacy'])
        self.assertIsNone(status['epsilon']);self.assertIsNone(status['accounting'])
        self.assertTrue(any(c['name']=='Transfer integrity' and c['status']=='Implemented' for c in status['checks']))
    def test_explanations_reject_cross_bank_and_unknown_transactions(self):
        with tempfile.TemporaryDirectory() as tmp:
            monitoring=Monitoring(tmp); xai=Explanations(tmp,monitoring)
            path=Path(tmp)/'monitoring'/'test'
            write_json(path/'job.json',dict(id='test',bank='Key_Bank',status='Completed',started=now()))
            write_json(path/'transactions.json',{'rows':[{'txn_id':'known'}]})
            with self.assertRaisesRegex(ValueError,'completed replay'):
                xai.start({'replay_id':'test','txn_id':'known'},'Wells_Fargo')
            with self.assertRaisesRegex(ValueError,'does not belong'):
                xai.start({'replay_id':'test','txn_id':'unknown'},'Key_Bank')

if __name__=='__main__':unittest.main()
