"""Deployment boundary checks; research configurations retain their own CLI."""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from distributed_federation.common.config import load_config
from streaming.app.collaboration import Collaboration
from streaming.app import final_federation as final
from streaming.app.runner import execute


class OperationalLevel3Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manager = Collaboration(self.root)
        self.profile = dict(self.manager.defaults(), dataset=str(self.root), broker='10.30.127.124:9092')
        self.raw = self.manager.config(self.profile)
        self.path = self.root / 'config.json'

    def config(self, raw):
        self.path.write_text(json.dumps(raw))
        return load_config(self.path)

    def test_generated_policy_matches_retained_finalist_and_dimension(self):
        for key, value in final.FIXED.items():
            self.assertEqual(self.raw[key], value, key)
        self.assertEqual(self.raw['privacy'], final.PRIVACY)
        self.assertEqual(self.raw['server_optimizer'], final.SERVER)
        reference = final.approved_template()
        self.assertEqual(self.raw['initial_checkpoint'], reference['initial_checkpoint'])
        self.assertIsNone(self.raw['initial_checkpoint'])
        self.assertEqual([m['seed'] for m in self.raw['ensemble_initialization']],[42,52,62])
        self.assertTrue(all(not Path(m['checkpoint']).is_absolute() for m in self.raw['ensemble_initialization']))
        self.assertEqual(self.raw['broker'], self.profile['broker'])
        self.assertEqual([c['bank'] for c in self.raw['clients']], list(final.BANK_ORDER))
        self.assertEqual(final.validate_operational_config(self.raw, self.config(self.raw)), 197379)

    def test_incomplete_duplicate_or_downgraded_setup_rejected(self):
        changes = [dict(banks=list(final.BANK_ORDER)[:n]) for n in (1, 2)]
        changes += [dict(banks=['Key_Bank']*3), dict(rounds=2), dict(local_epochs=1),
                    dict(privacy={'mode':'none'}), dict(aggregation='samples')]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.manager.config(dict(self.profile, **change))

    def test_controller_rejects_missing_or_tampered_policy_before_spawn(self):
        mutations = [(key, None) for key in ('privacy','operational_policy','initial_checkpoint','replay','ensemble_initialization')]
        mutations += [('aggregation','samples'), ('private_subset','all'), ('initial_checkpoint','other.pt'),
                      ('privacy',dict(final.PRIVACY, entropy='research')),
                      ('privacy',dict(final.PRIVACY, multiplier=.2)), ('local_epochs',2), ('rounds',1.4),
                      ('clients',self.raw['clients'][:2]), ('replay_size',0)]
        mutations += [('private_subset','decoder'),('training_protocol','legacy'),
                      ('privacy',dict(final.PRIVACY,multiplier=.15)),('privacy',dict(final.PRIVACY,multiplier=.29)),
                      ('ensemble_initialization',self.raw['ensemble_initialization'][:2])]
        for key, value in mutations:
            raw = copy.deepcopy(self.raw)
            if value is None: raw.pop(key)
            else: raw[key] = value
            self.path.write_text(json.dumps(raw))
            with self.subTest(key=key, value=value), patch('subprocess.Popen') as spawn:
                with self.assertRaises(ValueError):
                    self.manager.controller.start(self.path, 'central', operational=True)
                spawn.assert_not_called()

    def test_snapshot_carries_policy_and_forced_runner_flag(self):
        self.config(self.raw)
        with patch('subprocess.Popen') as spawn:
            self.manager.controller.start(self.path, 'central', operational=True)
        command = spawn.call_args.args[0]
        self.assertIn('--operational-final', command)
        snapshot = Path(command[command.index('--config')+1])
        raw = json.loads(snapshot.read_text())
        self.assertEqual(raw['operational_policy'], final.POLICY)
        self.assertEqual(final.validate_operational_config(raw, load_config(snapshot)),197379)

    def test_runner_forced_flag_rejects_removed_marker_and_privacy(self):
        raw = copy.deepcopy(self.raw)
        raw.pop('operational_policy'); raw.pop('privacy'); raw['private_subset']='all'
        self.config(raw)
        with patch('distributed_federation.central.aggregator.run') as run:
            with self.assertRaises(ValueError): execute(self.path,'central',self.root,operational=True)
            run.assert_not_called()

    def test_missing_or_changed_approved_warm_asset_fails_closed(self):
        # Copy public metadata only; never alter the retained experiment assets.
        alternate = self.root/'repository'
        for relative in (final.EVIDENCE/'CALIBRATION.json', final.FREEZE):
            target = alternate/relative; target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(final.ROOT/relative,target)
        warm = alternate/self.raw['ensemble_initialization'][0]['checkpoint']
        with patch.object(final,'ROOT',alternate):
            with self.assertRaisesRegex(ValueError,'warm ensemble seed-42 checkpoint is missing'): final.approved_template()
            warm.parent.mkdir(parents=True,exist_ok=True); warm.write_bytes(b'wrong model')
            with self.assertRaisesRegex(ValueError,'warm ensemble seed-42 checkpoint hash differs'): final.approved_template()

    def test_private_status_drops_diagnostics_and_exposes_budget(self):
        self.manager.save(self.profile)
        store = self.manager.controller.store
        run = store.begin(self.profile['run_id'],'central',self.raw)
        store.emit(run,'update_validated',1,client_id='bank-1',payload_sha256='hash',
                   training_examples=555,mean_train_loss=.4,clean_norm=4.,private_key='NEVER',
                   mask_seed='NEVER',noise_share=[1,2],clean_update=[3,4])
        store.finish(run,'Completed')
        status = self.manager.status(None)
        details = status['runs'][0]['events'][0]['details']
        self.assertEqual(details,dict(client_id='bank-1',payload_sha256='hash'))
        self.assertNotIn('config',status['runs'][0])
        self.assertNotIn('examples',status['roster'][0])
        self.assertEqual(status['privacy_label'],final.LABEL)
        self.assertEqual(status['privacy'],dict(final.public_privacy(),phase='update_validated'))

    def test_nonprivate_history_is_clearly_labeled(self):
        raw = dict(self.raw,privacy={'mode':'none'},aggregation='samples')
        raw.pop('operational_policy')
        run = self.manager.controller.store.begin(self.profile['run_id'],'central',raw)
        self.manager.controller.store.finish(run,'Completed')
        status = self.manager.status(None)
        self.assertIn('Non-private federation',status['privacy_label'])
        self.assertFalse(status['privacy']['secagg'])

    def test_other_distributed_settings_are_labeled_research_history(self):
        raw = dict(self.raw,privacy=dict(final.PRIVACY,multiplier=.1))
        run = self.manager.controller.store.begin(self.profile['run_id'],'central',raw)
        self.manager.controller.store.finish(run,'Completed')
        status = self.manager.status(None)
        self.assertIn('Research/debug privacy mode',status['privacy_label'])

    def test_status_uses_actual_reservations_and_reports_composition(self):
        from distributed_federation.privacy.ledger import Ledger
        from distributed_federation.privacy.mechanism import Privacy
        store=self.manager.controller.store
        run=store.begin(self.profile['run_id'],'central',self.raw)
        ledger=Ledger(Path(self.raw['output_dir'])/'privacy-ledgers/central.sqlite3')
        ledger.reserve('previous-run',1,'central',final.PRIVACY)
        ledger.reserve(self.profile['run_id'],0,'central',final.PRIVACY)
        ledger.reserve(self.profile['run_id'],1,'central',final.PRIVACY);ledger.close()
        store.finish(run,'Failed')
        status=self.manager.status(None)
        self.assertEqual(status['privacy']['epsilon'],Privacy(**final.PRIVACY).accounting(1)['epsilon'])
        self.assertEqual(status['privacy_accounting']['current_run_reserved_releases'],1)
        self.assertEqual(status['privacy_accounting']['cumulative']['reservations'],2)
        self.assertEqual(status['privacy_accounting']['cumulative']['epsilon'],Privacy(**final.PRIVACY).accounting(2)['epsilon'])

    def test_previous_single_model_result_is_labeled_historical(self):
        raw=dict(self.raw,operational_policy='level3_final_v1',privacy=dict(final.PRIVACY,clip=1.25,multiplier=.15),rounds=1)
        run=self.manager.controller.store.begin(self.profile['run_id'],'central',raw)
        self.manager.controller.store.finish(run,'Completed')
        self.assertIn('Previous single-model decoder-private',self.manager.status(None)['privacy_label'])

    def test_legacy_bank_identity_comes_from_saved_config(self):
        from distributed_federation.common.checkpoints import save_checkpoint
        import hashlib
        raw = copy.deepcopy(self.raw)
        raw['clients']=[dict(client_id='bank-1',bank='JPMorgan_Chase')]
        raw['training_protocol']='legacy'
        raw['privacy']={'mode':'none'};raw['aggregation']='samples';raw.pop('operational_policy')
        store=self.manager.controller.store
        run=store.begin(self.profile['run_id'],'bank:bank-1',raw)
        payload=b'verified historical checkpoint'
        path,_=save_checkpoint(payload,self.manager.root/'models'/'legacy'/'bank-1',1,{'scope':'legacy'})
        store.emit(run,'aggregate_received',1,checkpoint=str(path),payload_sha256=hashlib.sha256(payload).hexdigest())
        store.finish(run,'Completed')
        self.assertEqual(self.manager.status('JPMorgan_Chase')['runs'][0]['bank'],'JPMorgan_Chase')
        selected=self.manager.select_model(run,1,'JPMorgan_Chase')
        self.assertEqual(selected['sha256'],hashlib.sha256(payload).hexdigest())
        with self.assertRaises(ValueError):self.manager.select_model(run,1,'Key_Bank')

    def test_final_dashboard_controls_and_public_status_are_visible(self):
        html = (final.ROOT/'streaming/web/index.html').read_text()
        for bank in ('key','wells','jpm'):
            self.assertRegex(html,rf'id="fed-{bank}"[^>]*checked disabled')
        self.assertRegex(html,r'id="fedrounds"[^>]*value="4" readonly')
        self.assertRegex(html,r'id="fedepochs"[^>]*value="3" readonly')
        self.assertIn(final.LABEL,html)
        self.assertIn("privacy.epsilon",html)
        self.assertIn('nonprivate warm ensemble',html)
