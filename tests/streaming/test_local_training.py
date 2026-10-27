import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from streaming.app.local_training import LocalTraining, write_json, read_json

class LocalTrainingTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.training=LocalTraining(self.tmp.name)
    def test_training_requires_bank_quality_check_and_automatic_epochs(self):
        args=dict(dataset=self.tmp.name,kind='train')
        with self.assertRaises(ValueError):self.training.start(args,None)
        for epochs in (0,1,25,26,True,1.5):
            with self.assertRaises(ValueError):self.training.start(dict(args,epochs=epochs),'Key_Bank')
        with patch('streaming.app.local_training.importlib.util.find_spec',return_value=object()):
            with self.assertRaisesRegex(ValueError,'Check data quality'):
                self.training.start(args,'Key_Bank')
    def test_new_jobs_use_automatic_limit_and_patience(self):
        with patch('streaming.app.local_training.subprocess.Popen') as process, patch('streaming.app.local_training.importlib.util.find_spec',return_value=object()):
            result=self.training.start(dict(dataset=self.tmp.name,kind='check'),'Key_Bank')
            job=self.training.jobs()[0]
            self.assertEqual(job['epochs'],18)
            self.assertEqual(job['patience'],5)
            self.assertTrue(process.called)

    def test_selection_rejects_unfinished_wrong_bank_and_changed_checkpoint(self):
        import hashlib
        folder=self.training.root/'abc'
        folder.mkdir()
        path=folder/'Key_Bank_causal_temporal_graphsage.pt'
        path.write_bytes(b'checkpoint')
        job=dict(id='abc',bank='Key_Bank',kind='train',dataset=self.tmp.name,status='Running',started='2026-10-25T00:00:00+00:00',ended='2026-10-25T00:01:00+00:00',sha256=hashlib.sha256(path.read_bytes()).hexdigest(),metrics={'validation':{'pr_auc':.5,'precision':.6,'recall':.7}})
        write_json(folder/'job.json',job)
        with self.assertRaises(ValueError):self.training.activate('abc','Key_Bank')
        job['status']='Completed';write_json(folder/'job.json',job)
        with self.assertRaises(ValueError):self.training.activate('abc','Wells_Fargo')
        with self.assertRaisesRegex(ValueError,'legacy'):
            self.training.activate('abc','Key_Bank')
        write_json(folder/'ensemble.json',dict(bank='Key_Bank',version='local-abc',model_kind='adaptive_probability_ensemble',
            members=[dict(seed=seed,checkpoint=str(path),sha256=job['sha256']) for seed in (42,52,62)],sha256=job['sha256']))
        model=self.training.activate('abc','Key_Bank')
        self.assertEqual(model['version'],'local-abc')
        self.assertEqual(read_json(self.training.root/'active-Key_Bank.json')['sha256'],job['sha256'])
        path.write_bytes(b'changed')
        with self.assertRaises(ValueError):self.training.activate('abc','Key_Bank')
    def test_cancel_is_persistent_and_terminal_jobs_reject_it(self):
        folder=self.training.root/'abc'
        write_json(folder/'job.json',dict(id='abc',bank='Key_Bank',status='Running',started='2026-10-25T00:00:00+00:00'))
        self.training.cancel('abc')
        self.assertTrue(read_json(folder/'cancel.json')['requested'])
        write_json(folder/'job.json',dict(id='abc',status='Completed',started='2026-10-25T00:00:00+00:00'))
        with self.assertRaises(ValueError):self.training.cancel('abc')

class DataQualityTests(unittest.TestCase):
    def setUp(self):
        import pandas as pd
        self.pd=pd
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        write_json(self.root/'configuration/model_feature_columns.json',{'graph_node_safe_features':['hist_sent_count'],'graph_edge_safe_features':['amount']})
        for split,month in (('training','06'),('validation','08')):
            folder=self.root/split/'Key_Bank';folder.mkdir(parents=True)
            pd.DataFrame({'node_id':[0,1],'hist_sent_count':[1,2]}).to_csv(folder/'node_features.csv.gz',index=False)
            pd.DataFrame({'node_id':[0,1],'account_id':['a','b']}).to_csv(folder/'node_map.csv.gz',index=False)
            pd.DataFrame({'txn_id':[split+'0',split+'1'],'src_node':[0,1],'dst_node':[1,0],'timestamp':[f'2025-{month}-01',f'2025-{month}-02'],'amount':[10,20]}).to_csv(folder/'edge_list.csv.gz',index=False)
            pd.DataFrame({'txn_id':[split+'0',split+'1'],'y':[0,1]}).to_csv(folder/'ground_truth.csv.gz',index=False)
    def test_checks_training_validation_without_test_directory(self):
        from streaming.app.local_training import check_dataset
        result=check_dataset(self.root,'Key_Bank')
        self.assertTrue(result['passed'])
        self.assertEqual([r['transactions'] for r in result['splits']],[2,2])
        self.assertEqual(len(result['fingerprint']),64)
    def test_missing_label_and_temporal_overlap_are_rejected(self):
        from streaming.app.local_training import check_dataset
        folder=self.root/'validation/Key_Bank'
        truth=self.pd.read_csv(folder/'ground_truth.csv.gz');truth.loc[0,'txn_id']='missing';truth.to_csv(folder/'ground_truth.csv.gz',index=False)
        with self.assertRaisesRegex(ValueError,'IDs do not match'):check_dataset(self.root,'Key_Bank')
        truth.loc[0,'txn_id']='validation0';truth.to_csv(folder/'ground_truth.csv.gz',index=False)
        edges=self.pd.read_csv(folder/'edge_list.csv.gz');edges['timestamp']='2025-05-01';edges.to_csv(folder/'edge_list.csv.gz',index=False)
        with self.assertRaisesRegex(ValueError,'strictly before'):check_dataset(self.root,'Key_Bank')
    def test_missing_endpoint_is_rejected(self):
        from streaming.app.local_training import check_dataset
        path=self.root/'training/Key_Bank/edge_list.csv.gz'
        edges=self.pd.read_csv(path);edges.loc[0,'src_node']=999;edges.to_csv(path,index=False)
        with self.assertRaisesRegex(ValueError,'endpoint'):check_dataset(self.root,'Key_Bank')
    def test_training_loader_rejects_unlabeled_edges_instead_of_dropping_them(self):
        from src.gnn.causal_temporal_graphsage import load_bank_frames
        folder=self.root/'training/Key_Bank'
        edges=self.pd.read_csv(folder/'edge_list.csv.gz')
        extra=edges.iloc[[0]].copy();extra['txn_id']='unlabeled'
        self.pd.concat([edges,extra],ignore_index=True).to_csv(folder/'edge_list.csv.gz',index=False)
        with self.assertRaisesRegex(ValueError,'match exactly'):
            load_bank_frames(self.root,'Key_Bank',('training',))
