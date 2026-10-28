"""Final shell integration and replay/model identity regression boundaries."""
import copy
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
from unittest.mock import patch

from streaming.app.dashboard import server
from streaming.app.final_model import reference_model, digest
from streaming.app.investigator import model_provenance, validate_report, hash_json
from streaming.app.explanations import Explanations
from streaming.app.monitoring import Monitoring
from streaming.app.local_training import write_json, now
from streaming.app.xai_assets import scoped_css
from streaming.app import final_federation as final

ROOT=Path(__file__).resolve().parents[2]


class DashboardIntegrationTests(unittest.TestCase):
    def test_global_title_navigation_and_single_inline_explanation_surface(self):
        html=(ROOT/'streaming/web/index.html').read_text()
        self.assertEqual(html.count('<h1>FCL for Anti-Money Laundering</h1>'),1)
        self.assertIn('<title>FCL for Anti-Money Laundering | Review workspace</title>',html)
        for text in ('<h1>Risk operations</h1>','id="privacytab"','id="privacypanel"',"$('privacytab')",'Privacy &amp; transfers','How to read the explanation','function refreshExplanations(){try{'):
            self.assertNotIn(text,html)
        self.assertIn('id="explanationstab"',html)
        self.assertIn('id="xaireport" class="xai-investigator"',html)
        self.assertIn('requestExplanation(row)',html)
        self.assertIn('replayInvestigator.request(row,monData)',html)
        self.assertNotIn('<iframe',html)
        self.assertNotIn('8766',html)
        self.assertIn(final.LABEL,html)
        for name in ('overview','training','collaboration','monitoring','results','transfer','explanations'):
            self.assertIn('id="'+name+'tab"',html)

    def test_component_css_is_scoped_and_does_not_recreate_the_shell(self):
        css=scoped_css((ROOT/'xai/static/dashboard.css').read_text())
        self.assertIn('.xai-investigator .investigation-hero',css)
        self.assertIn('.xai-investigator .hero-network',css)
        self.assertIn('.xai-investigator .hero-explanation',css)
        self.assertNotIn(':root',css)
        self.assertNotIn('header{',css)
        self.assertNotIn('.xai-investigator .layout{',css)
        self.assertNotIn('.xai-investigator .filters{',css)
        self.assertIn('@media (max-width: 1000px)',css)

    def test_assets_and_privacy_api_remain_available_with_session_guards(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=server(tmp,0);thread=threading.Thread(target=app.serve_forever,daemon=True);thread.start()
            try:
                base='http://127.0.0.1:'+str(app.server_port)
                response=urllib.request.urlopen(base+'/');html=response.read().decode()
                policy=response.headers['Content-Security-Policy']
                self.assertIn("script-src 'nonce-",policy);self.assertNotIn('unsafe-eval',policy)
                self.assertIn("style-src 'self' 'unsafe-inline'",policy)
                for name in ('dashboard.js','dashboard.css','explanation_summary.js','bank_display.js','replay_investigator.js'):
                    asset=urllib.request.urlopen(base+'/assets/xai/'+name)
                    self.assertEqual(asset.status,200)
                    self.assertTrue(asset.read())
                privacy=json.load(urllib.request.urlopen(base+'/api/privacy'))
                operational=privacy['scopes']['operational_collaboration']
                self.assertTrue(operational['differential_privacy']);self.assertTrue(operational['secagg'])
                self.assertEqual(operational['mode'],'distributed_dp')
                self.assertEqual(operational['delta'],1e-6)
                with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(base+'/assets/xai/../../streaming/app/privacy.py')
                with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(urllib.request.Request(base+'/api/explanations/start',data=b'{}',headers={'Content-Type':'application/json'}))
            finally:
                app.shutdown();app.server_close();thread.join(timeout=2)

    def test_reference_identity_and_canonical_private_scope_use_the_actual_checkpoints(self):
        reference=reference_model('Wells_Fargo');p=model_provenance(reference,'Wells_Fargo')
        self.assertEqual(p['model_count'],3);self.assertEqual(p['privacy_mode'],'none')
        self.assertEqual(p['checkpoint_sha256'],reference['sha256'])
        bad=copy.deepcopy(reference);bad['sha256']='wrong'
        with self.assertRaisesRegex(ValueError,'fingerprint'):model_provenance(bad,'Wells_Fargo')
        private=json.loads((ROOT/'artifacts/dp_singlemodel_r4e3/PRODUCTION_MODEL.json').read_text())
        private.update(bank='Wells_Fargo',checkpoint=str(ROOT/private['checkpoint']),threshold=.5)
        p=model_provenance(private,'Wells_Fargo')
        self.assertEqual(p['model_count'],1);self.assertEqual(p['privacy_mode'],'level3')
        self.assertEqual(p['seed'],42);self.assertEqual(p['checkpoint_sha256'],private['sha256'])
        bad=copy.deepcopy(private);bad['privacy']['differential_privacy']=False
        with self.assertRaisesRegex(ValueError,'privacy claim'):model_provenance(bad,'Wells_Fargo')

    def report_and_job(self):
        report=json.loads((ROOT/'xai/review/explanation-ux-v2/cases/Wells_Fargo_2954161.json').read_text())
        selected={'sha256':report['model']['checkpoint_sha256'],'model_kind':report['model']['family']}
        report['replay_id']='replay';report['replay_provenance']={'dataset_fingerprint':'data','saved_rows_sha256':'rows'}
        report['xai_provenance']['selected_model']=selected
        inputs=copy.deepcopy(report['cache_key_inputs']);inputs.update(model_count=1,privacy_mode='none',reference_prediction_sha256='rows')
        report['cache_key_inputs']=inputs;report['cache_key']=hash_json(inputs)
        event=report['transaction_story']['selected_transfer']
        job=dict(cache_key_inputs=inputs,model=selected,bank=report['bank'],txn_id=report['transaction_id'],replay_id='replay',
                 dataset_fingerprint='data',expected_score=report['prediction']['probability'],
                 expected_transfer={'source':event['source_account_id'],'target':event['target_account_id'],'timestamp':event['timestamp']})
        return report,job

    def test_saved_replay_parity_keeps_exact_one_e_minus_six_guard(self):
        report,job=self.report_and_job();validate_report(report,job)
        report['feature_explanation']['target_probability']=job['expected_score']+.5e-6
        validate_report(report,job)
        report['feature_explanation']['target_probability']=job['expected_score']+1.5e-6
        with self.assertRaisesRegex(ValueError,'1e-6'):validate_report(report,job)

    def test_stale_identity_decision_privacy_data_and_graph_are_rejected(self):
        mutations=[lambda r:r['model'].update(checkpoint_sha256='wrong'),
                   lambda r:r.update(replay_id='wrong'),lambda r:r['replay_provenance'].update(dataset_fingerprint='wrong'),
                   lambda r:r['prediction'].update(threshold=.9),lambda r:r['verification'].update(tolerance=1e-5),
                   lambda r:r['xai_provenance'].update(privacy_mode='level3'),lambda r:r['xai_provenance'].update(preprocessing_sha256='wrong'),
                   lambda r:r['transaction_story']['selected_transfer'].update(source_account_id='wrong'),
                   lambda r:r['prediction'].update(**{'class':'not_fraud'})]
        for mutate in mutations:
            report,job=self.report_and_job();mutate(report)
            with self.assertRaises(ValueError):validate_report(report,job)

    def test_explanation_cache_is_replay_and_model_specific(self):
        with tempfile.TemporaryDirectory() as tmp:
            monitoring=Monitoring(tmp);manager=Explanations(tmp,monitoring);model=reference_model('Wells_Fargo')
            replay=dict(id='replay',bank='Wells_Fargo',status='Completed',started=now(),model=model,
                        threshold=model['threshold'],dataset='/not/read/in/this/unit/test',dataset_fingerprint='data')
            row=dict(txn_id='tx',score=.4,source='a',target='b',timestamp='2025-08-01 00:00:00')
            path=Path(tmp)/'monitoring/replay';write_json(path/'job.json',replay)
            write_json(path/'transactions.json',dict(bank='Wells_Fargo',rows=[row],model=model,threshold=model['threshold'],member_count=3))
            with patch('streaming.app.explanations.subprocess.Popen') as spawn:
                spawn.return_value.poll.return_value=0
                first=manager.start({'replay_id':'replay','txn_id':'tx'},'Wells_Fargo')
                stored=json.loads((manager.root/first['id']/'job.json').read_text())
                self.assertEqual(stored['expected_score'],.4)
                self.assertEqual(stored['cache_key_inputs']['model_count'],3)
                changed=dict(row,score=.5)
                write_json(path/'transactions.json',dict(bank='Wells_Fargo',rows=[changed],model=model,threshold=model['threshold'],member_count=3))
                second=manager.start({'replay_id':'replay','txn_id':'tx'},'Wells_Fargo')
                self.assertNotEqual(first['id'],second['id'])
            with self.assertRaises(ValueError):manager.report(first['id'],'Key_Bank')
            with self.assertRaises(ValueError):manager.report('../job','Wells_Fargo')

    def test_retained_dp_results_and_broker_contract_are_unchanged(self):
        retained=json.loads((ROOT/'artifacts/dp_singlemodel_r4e3/PRODUCTION_MODEL.json').read_text())
        self.assertAlmostEqual(retained['August_validation']['pr_auc'],.9135646317452175)
        self.assertEqual(retained['privacy']['accounting']['epsilon'],127.36375184207253)
        self.assertEqual(retained['privacy']['accounting']['delta'],1e-6)
        self.assertEqual(final.PRIVACY['clip'],.875);self.assertEqual(final.PRIVACY['multiplier'],.30)
        self.assertEqual(final.PRIVATE_DIMENSION,65793);self.assertEqual(final.SERVER['learning_rate'],.1)
        html=(ROOT/'streaming/web/index.html').read_text()
        self.assertIn('10.30.127.124:9092',html)
        self.assertIn("$('checkconnection').onclick",html)
        self.assertIn('Kafka',html)
