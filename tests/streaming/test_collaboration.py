import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from streaming.app.collaboration import Collaboration, CLIENTS, SCHEMA
from streaming.app.local_training import write_json
from streaming.app.overview import REPO

class CollaborationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.manager=Collaboration(self.tmp.name)
        self.profile=self.manager.defaults()
        self.profile.update(dataset=self.tmp.name,broker='localhost:9092')
    def test_profile_rejects_secrets_duplicate_banks_and_invalid_numbers(self):
        for changes in ({'secret':'s'*32},{'banks':['Key_Bank','Key_Bank']},{'banks':['Citi']},{'rounds':True},{'local_epochs':0},{'timeout':20},{'broker':'bad:99999'},{'run_id':'../bad'}):
            with self.assertRaises(ValueError):self.manager.save(dict(self.profile,**changes))
        saved=self.manager.save(self.profile)
        self.assertEqual(saved['banks'],list(CLIENTS))
        self.assertNotIn('secret',json.dumps(saved))
    def test_preflight_is_required_and_secret_is_not_persisted(self):
        secret='do-not-store-this-secret-string-123456789'
        with self.assertRaisesRegex(ValueError,'Check readiness'):
            self.manager.start(dict(profile=self.profile,secret=secret),'Key_Bank')
        self.assertFalse(list(self.manager.root.glob('configs/*.json')))
        self.manager.save(self.profile)
        self.assertNotIn(secret,(self.manager.root/'profile.json').read_text())
    def test_current_round_roster_uses_observed_evidence_only(self):
        p=self.manager.save(self.profile)
        run=self.manager.controller.store.begin(p['run_id'],'central',self.manager.config(p))
        self.manager.controller.store.emit(run,'participant_ready',1,client_id='bank-1')
        self.manager.controller.store.emit(run,'update_validated',1,client_id='bank-1',training_examples=12,payload_sha256='abc')
        self.manager.controller.store.finish(run,'Completed')
        result=self.manager.status(None)
        self.assertEqual(result['current_round'],1)
        self.assertEqual(result['roster'][0]['status'],'Update verified by coordinator')
        self.assertEqual(result['roster'][1]['status'],'Not observed on this laptop')
    def test_shared_model_selection_refuses_wrong_bank_or_missing_receipt(self):
        p=self.manager.save(self.profile)
        run=self.manager.controller.store.begin(p['run_id'],'bank:bank-1',self.manager.config(p))
        with self.assertRaises(ValueError):self.manager.select_model(run,1,'Wells_Fargo')
        with self.assertRaises(ValueError):self.manager.select_model(run,1,'Key_Bank')

class SharedFeatureSchemaTests(unittest.TestCase):
    def test_coordinator_builds_model_without_reading_any_bank_data(self):
        from distributed_federation.common.config import load_config
        from distributed_federation.common.model_runtime import prepare_frozen_runtime
        with tempfile.TemporaryDirectory() as tmp:
            manager=Collaboration(tmp)
            p=manager.defaults();p.update(dataset=tmp,broker='localhost:9092')
            path=Path(tmp)/'config.json';write_json(path,manager.config(p))
            cfg=load_config(path)
            with patch('causal_temporal_graphsage.build_bank_data',create=True) as build:
                runtime=prepare_frozen_runtime(cfg)
                build.assert_not_called()
            self.assertEqual(runtime.streams,{})
            self.assertIsNone(runtime.static)
            self.assertEqual(len(runtime.schema_sha256),64)
    def test_json_encoder_matches_reference_training_fitted_transform(self):
        import numpy as np
        import pandas as pd
        from src.gnn.causal_temporal_graphsage import BANKS,fit_shared_feature_encoders
        from distributed_federation.common.model_runtime import FrozenEncoder
        nodes,edges=fit_shared_feature_encoders(REPO/'data/final_temporal_dataset',BANKS)
        contract=json.loads(SCHEMA.read_text())
        base=REPO/'data/final_temporal_dataset/training/Key_Bank'
        for reference,key,file in ((nodes,'nodes','node_features.csv.gz'),(edges,'edges','edge_list.csv.gz')):
            frame=pd.read_csv(base/file,nrows=100)
            np.testing.assert_allclose(FrozenEncoder(contract[key]).transform(frame),reference.transform(frame),rtol=1e-6,atol=1e-6)

class CollaborationProtocolTests(unittest.TestCase):
    def test_retained_other_run_is_ignored_but_current_run_requires_signature(self):
        from distributed_federation.common.protocol import create_chunks,verify_for_run
        metadata=dict(message_type='global_model',run_id='old',round_id=1,sender_id='central',schema_sha256='schema',base_model_sha256='base')
        raw=create_chunks(b'weights',metadata,'a'*32,1000)[0]
        self.assertIsNone(verify_for_run(raw,'b'*32,'new'))
        with self.assertRaises(ValueError):verify_for_run(raw,'b'*32,'old')
        self.assertEqual(verify_for_run(raw,'a'*32,'old')['run_id'],'old')
    def test_collaboration_start_endpoint_uses_session_origin_protection(self):
        import re,threading,urllib.request,urllib.error
        from streaming.app.dashboard import server
        with tempfile.TemporaryDirectory() as tmp:
            app=server(tmp,0)
            worker=threading.Thread(target=app.serve_forever,daemon=True);worker.start()
            base='http://127.0.0.1:'+str(app.server_port)
            try:
                html=urllib.request.urlopen(base).read().decode()
                token=re.search("const token='([^']+)'",html)[1]
                with patch('streaming.app.collaboration.Collaboration.start',return_value={'started':True}) as start:
                    payload=json.dumps({'profile':{},'secret':'never-return-this-secret-value-123456'}).encode()
                    request=urllib.request.Request(base+'/api/collaboration/start',data=payload,headers={'Content-Type':'application/json'})
                    with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
                    self.assertEqual(error.exception.code,403);start.assert_not_called()
                    request.add_header('Origin',base);request.add_header('X-Session-Token',token)
                    self.assertTrue(json.load(urllib.request.urlopen(request))['started']);start.assert_called_once()
                state=json.load(urllib.request.urlopen(base+'/api/collaboration'))
                self.assertNotIn('secret',state['profile'])
            finally:
                app.shutdown();worker.join();app.server_close()
