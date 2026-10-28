"""Read-only investigator labels never alter replay/model decisions or identifiers."""
import copy
import csv
import gzip
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from streaming.app.explanation_cases import replay_cases


class ExplanationCaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.dataset=Path(self.temp.name);self.bank='Key_Bank'
        self.data=dict(bank=self.bank,replay_id='replay',dataset_fingerprint='fingerprint',threshold=.5,
                       model=dict(bank=self.bank,sha256='unchanged',checkpoint='models/Key_Bank/weights'),member_count=1,
                       rows=[dict(txn_id='tp',score=.8),dict(txn_id='fp',score=.7),dict(txn_id='tn',score=.1),dict(txn_id='fn',score=.2)])
        self.job=dict(id='replay',status='Completed',bank=self.bank,model=self.data['model'],threshold=.5,dataset=str(self.dataset),dataset_fingerprint='fingerprint')
        self.monitoring=unittest.mock.Mock()
        self.monitoring.status.return_value={'jobs':[self.job]}
        self.monitoring.rows.return_value=self.data
        self.labels([('tp','1'),('fp','0'),('tn','0'),('fn','1')])
        self.check=patch('streaming.app.explanation_cases.check_dataset',return_value={'fingerprint':'fingerprint'}).start()
        self.addCleanup(patch.stopall)

    def labels(self,rows):
        path=self.dataset/'validation'/self.bank/'ground_truth.csv.gz';path.parent.mkdir(parents=True,exist_ok=True)
        with gzip.open(path,'wt',newline='') as stream:
            writer=csv.writer(stream);writer.writerow(['txn_id','y']);writer.writerows(rows)

    def test_labels_are_independent_and_scores_cutoff_model_and_canonical_ids_are_unchanged(self):
        before=copy.deepcopy(self.data)
        data=replay_cases(self.monitoring,'replay',self.bank)
        self.assertEqual(self.data,before)
        self.assertEqual(data['bank'],'Key_Bank');self.assertEqual(data['model'],before['model'])
        self.assertEqual(data['threshold'],.5)
        self.assertEqual([r['score'] for r in data['rows']],[.8,.7,.1,.2])
        self.assertEqual([r['evaluation_label'] for r in data['rows']],['fraud','not_fraud','not_fraud','fraud'])
        self.assertNotIn('evaluation_label',self.data['rows'][0])

    def test_cross_bank_or_missing_completed_replay_is_refused(self):
        self.monitoring.status.return_value={'jobs':[]}
        with self.assertRaisesRegex(ValueError,'completed replay'):replay_cases(self.monitoring,'other','Wells_Fargo')
        self.monitoring.rows.assert_not_called()

    def test_noncompleted_replay_is_not_browsable(self):
        self.job['status']='Running'
        with self.assertRaises(ValueError):replay_cases(self.monitoring,'replay',self.bank)

    def test_changed_replay_bank_model_or_threshold_is_refused(self):
        for key,value in [('bank','JPMorgan_Chase'),('model',{'sha256':'different'}),('threshold',.3)]:
            with self.subTest(key=key):
                before=self.data[key];self.data[key]=value
                with self.assertRaisesRegex(ValueError,'identity'):replay_cases(self.monitoring,'replay',self.bank)
                self.data[key]=before

    def test_changed_data_fingerprint_is_refused(self):
        self.check.return_value={'fingerprint':'changed'}
        with self.assertRaisesRegex(ValueError,'Replay data changed'):replay_cases(self.monitoring,'replay',self.bank)

    def test_dataset_change_during_label_read_is_refused(self):
        self.check.side_effect=[{'fingerprint':'fingerprint'},{'fingerprint':'changed'}]
        with self.assertRaisesRegex(ValueError,'while loading'):replay_cases(self.monitoring,'replay',self.bank)

    def test_missing_duplicate_or_nonbinary_labels_fail_closed(self):
        for rows in [[('tp','1')],[('tp','1'),('tp','0')],[('tp','unknown')]]:
            with self.subTest(rows=rows):
                self.labels(rows)
                with self.assertRaises(ValueError):replay_cases(self.monitoring,'replay',self.bank)

    def test_aliases_are_not_accepted_as_dataset_bank_identifiers(self):
        self.monitoring.rows.return_value=dict(self.data,bank='Bank A')
        with self.assertRaisesRegex(ValueError,'identity'):replay_cases(self.monitoring,'replay',self.bank)
