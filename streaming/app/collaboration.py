"""Browser-facing supervisor for one bank or coordinator on this laptop."""
import hashlib
import importlib.util
import json
import os
import threading
import time
from pathlib import Path
from distributed_federation.common.config import load_config, secret_env_name, RUN_ID_RE
from .controller import RunController
from .local_training import read_json, write_json, now
from .overview import BANKS, REPO
from .settings import validate_settings

CLIENTS={'Key_Bank':'bank-1','Wells_Fargo':'bank-2','JPMorgan_Chase':'bank-3'}
SCHEMA=REPO/'distributed_federation/feature_schema.json'
GLOBAL_TOPIC='fcl.collaboration.global.v1'
UPDATE_TOPIC='fcl.collaboration.updates.v1'

class Collaboration:
    def __init__(self, root):
        self.root=Path(root)/'collaboration'
        self.controller=RunController(self.root)
        self.lock=threading.Lock()
        self.process=None
        self.started=0
        self.checked=None
    def defaults(self):
        return dict(role='bank',broker='10.30.127.124:9092',run_id='team-'+time.strftime('%Y%m%d-%H%M%S'),
                    banks=list(CLIENTS),dataset=str(REPO/'data/final_temporal_dataset'),rounds=4,local_epochs=3,timeout=900)
    def profile(self):
        return read_json(self.root/'profile.json',self.defaults())
    def validate(self, data):
        fields={'role','broker','run_id','banks','dataset','rounds','local_epochs','timeout'}
        if not isinstance(data,dict) or set(data)!=fields:
            raise ValueError('Provide only collaboration setup fields; secrets must be entered separately.')
        if data['role'] not in ('central','bank'):
            raise ValueError('Select coordinator or bank role.')
        values=dict(data)
        values['broker']=validate_settings(dict(broker=data['broker'],mode='send',sender='central',recipient='bank-1'))['broker']
        if not isinstance(data['run_id'],str) or not RUN_ID_RE.fullmatch(data['run_id']):
            raise ValueError('Use a fresh run ID: 1-64 letters, numbers, dots, underscores or hyphens.')
        banks=data['banks']
        if not isinstance(banks,list) or not banks or any(not isinstance(b,str) or b not in BANKS for b in banks) or len(set(banks))!=len(banks):
            raise ValueError('Choose one to three different project banks.')
        values['banks']=[b for b in CLIENTS if b in banks]
        for name,low,high in (('rounds',1,16),('local_epochs',1,5),('timeout',60,3600)):
            value=data[name]
            if isinstance(value,bool) or not isinstance(value,int) or not low<=value<=high:
                raise ValueError(f'{name} must be an integer from {low} to {high}.')
        if not isinstance(data['dataset'],str) or not data['dataset'].strip():
            raise ValueError('Set the local prepared dataset folder.')
        values['dataset']=str(Path(data['dataset'].strip()).expanduser().resolve())
        if not Path(values['dataset']).is_dir():
            raise ValueError('Local dataset folder does not exist.')
        return values
    def save(self, data):
        profile=self.validate(data)
        write_json(self.root/'profile.json',profile)
        return profile
    def config(self, profile):
        return dict(broker=profile['broker'],run_id=profile['run_id'],
            clients=[dict(client_id=CLIENTS[b],bank=b) for b in profile['banks']],
            schema_banks=list(CLIENTS),dataset_dir=profile['dataset'],
            output_dir=str(self.root/'models'),initial_checkpoint=None,
            feature_schema=str(SCHEMA),return_aggregate=True,training_protocol="adaptive_ensemble",replay_size=2000,
            rounds=profile['rounds'],local_epochs=profile['local_epochs'],hidden_channels=128,
            dropout=.25,batch_size=1024,negative_ratio=20,learning_rate=.001,weight_decay=.0001,
            seed=42,round_timeout_seconds=profile['timeout'],max_chunk_bytes=524288,
            topics=dict(global_model=GLOBAL_TOPIC,client_updates=UPDATE_TOPIC))
    def preflight(self, data, bank, prepare=False):
        profile=self.save(data)
        if profile['role']=='bank' and bank not in profile['banks']:
            raise ValueError('Save a participating bank on Overview first.')
        missing=[m for m in ('torch','numpy','pandas','sklearn','safetensors','confluent_kafka') if importlib.util.find_spec(m) is None]
        if missing:raise ValueError('Missing federation dependencies: '+', '.join(missing))
        if not SCHEMA.is_file():raise ValueError('Shared feature-schema file is missing. Update the project on all laptops.')
        if profile['role']=='bank':
            folder=Path(profile['dataset'])/'training'/bank
            if any(not (folder/(name+'.csv.gz')).is_file() for name in ('node_features','node_map','edge_list','ground_truth')):
                raise ValueError('Prepared training graph files are missing for this bank.')
        from confluent_kafka.admin import AdminClient, NewTopic
        admin=AdminClient({'bootstrap.servers':profile['broker'],'socket.timeout.ms':5000})
        metadata=admin.list_topics(timeout=5)
        topics=(GLOBAL_TOPIC,UPDATE_TOPIC)
        missing_topics=[name for name in topics if name not in metadata.topics]
        if prepare and profile['role']=='central' and missing_topics:
            for name,future in admin.create_topics([NewTopic(name,num_partitions=1,replication_factor=1) for name in missing_topics],request_timeout=10).items():
                future.result(timeout=12)
            metadata=admin.list_topics(timeout=5)
        for name in topics:
            topic=metadata.topics.get(name)
            if topic is None or topic.error:
                raise ValueError('Federation topics are missing/unavailable. Coordinator: click Prepare topics first.')
            if len(topic.partitions)!=1:
                raise ValueError('Federation topics must each have one partition for ordered model returns.')
        digest=hashlib.sha256(SCHEMA.read_bytes()).hexdigest()
        result=dict(ready=True,setup=profile,checked_at=now(),broker=profile['broker'],feature_schema_sha256=digest,
                    detail='Broker and both federation topics available. This checks this laptop; peer readiness is observed during the run.')
        self.checked=(profile,time.monotonic(),bank,result)
        return result
    def start(self, data, bank):
        if not isinstance(data,dict) or set(data)!={'profile','secret'}:
            raise ValueError('Provide setup and the team federation secret.')
        profile=self.validate(data['profile'])
        secret=data['secret']
        if not isinstance(secret,str) or len(secret)<32 or len(secret)>1024:
            raise ValueError('Use the same privately shared federation secret of at least 32 characters on all participants.')
        with self.lock:
            if self.process and self.process.poll() is None:
                raise ValueError('A collaboration process is already running on this laptop.')
            if not self.checked or self.checked[0]!=profile or self.checked[2]!=bank or time.monotonic()-self.checked[1]>300:
                raise ValueError('Run Check readiness for this setup within five minutes before starting.')
            if profile['role']=='bank' and bank not in profile['banks']:
                raise ValueError('The saved bank is not in this run roster.')
            actor='central' if profile['role']=='central' else 'bank:'+CLIENTS[bank]
            runs=self.controller.status()
            if any(r['status']=='Running' for r in runs):raise ValueError('A worker still owns the collaboration workspace.')
            if any(r['run_id']==profile['run_id'] and r['actor']==actor for r in runs):
                raise ValueError('This run ID was already used on this laptop. Coordinate a fresh ID on all laptops.')
            profile=self.save(profile)
            config=self.config(profile)
            path=self.root/'launch-config.json'
            write_json(path,config)
            load_config(path)
            env=os.environ.copy()
            env['PYTHONUNBUFFERED']='1'
            env['OMP_NUM_THREADS']='4'
            env['MKL_NUM_THREADS']='4'
            env['FCL_CENTRAL_SECRET']=secret
            env['FCL_CLIENT_SECRET']=secret
            for bank_id in profile['banks']:env[secret_env_name(CLIENTS[bank_id])]=secret
            self.started=time.monotonic()
            with (self.root/'worker.log').open('wb') as output:
                self.process=self.controller.start(path,profile['role'],None if profile['role']=='central' else CLIENTS[bank],environment=env,output=output)
            return dict(started=True,run_id=profile['run_id'],actor=actor)
    def control(self, run, cancel=False):
        if isinstance(run,bool) or not isinstance(run,int):raise ValueError('Select a local run record.')
        return dict(requested=self.controller.stop(run,cancel=cancel))
    def select_model(self, run_id, round_id, bank):
        from distributed_federation.common.checkpoints import verify_checkpoint
        if isinstance(run_id,bool) or not isinstance(run_id,int) or isinstance(round_id,bool) or not isinstance(round_id,int):
            raise ValueError('Choose a recorded federation run and round.')
        run=next((r for r in self.controller.store.runs() if r['id']==run_id),None)
        if not run or bank not in CLIENTS or run['actor']!='bank:'+CLIENTS[bank]:
            raise ValueError('Select a shared model received by the saved bank.')
        event=next((e for e in self.controller.store.events(run_id,limit=1000) if e['kind']=='aggregate_received' and e['round_id']==round_id),None)
        if not event:raise ValueError('No verified shared model was received for that round.')
        checkpoint=Path(event['details']['checkpoint']).resolve()
        checkpoint.relative_to((self.root/'models').resolve())
        verify_checkpoint(checkpoint.parent,round_id)
        digest=hashlib.sha256(checkpoint.read_bytes()).hexdigest()
        if digest!=event['details']['payload_sha256']:raise ValueError('Shared checkpoint changed; selection refused.')
        manifest=read_json(checkpoint.with_suffix('.json'),{})
        if manifest.get('schema',{}).get('training_protocol',{}).get('protocol')!='adaptive_ensemble':
            raise ValueError('This is a legacy federation model. Start a new ensemble collaboration run.')
        model=dict(bank=bank,version=f"fed-{run['run_id']}-r{round_id}",sha256=digest,
            checkpoint=str(checkpoint),trained_at=event['time'],selected_at=now(),
            model_kind='federated_ensemble',validation=None,job='federation:'+str(run_id))
        write_json(self.root.parent/'local-training'/('active-'+bank+'.json'),model)
        return model
    def status(self, bank):
        runs=self.controller.status()
        for run in runs[:5]:
            run.pop('config',None)
            run['events']=self.controller.store.events(run['id'],limit=1000)
            run['control']=self.controller.store.control(run['id'])
        active=runs[0] if runs else None
        profile=self.profile()
        config=self.config(profile)
        if active:
            record=next((r for r in self.controller.store.runs() if r['id']==active['id']),None)
            if record:config=json.loads(record['config'])
        roster=[dict(client_id=c['client_id'],bank=c['bank'],name=BANKS.get(c['bank'],c['bank']),status='Not observed on this laptop') for c in config['clients']]
        events=active.get('events',[]) if active else []
        latest_round=max([e['round_id'] or 0 for e in events]+[0])
        for row in roster:
            ready=any(e['kind']=='participant_ready' and e['details'].get('client_id')==row['client_id'] for e in events)
            if ready:row['status']='Readiness observed earlier in this run'
            for event in events:
                kind=event['kind'];details=event['details']
                own=active and active['actor']=='bank:'+row['client_id']
                if event['round_id']!=latest_round:continue
                if kind=='update_validated' and details.get('client_id')==row['client_id']:
                    row.update(status='Update verified by coordinator',sha256=details.get('payload_sha256'),examples=details.get('training_examples'))
                elif own and kind in ('training','epoch_completed','training_completed','publishing_update','update_published','waiting_for_aggregate','aggregate_received'):
                    labels={'training':'Training locally','epoch_completed':'Training locally','training_completed':'Local training completed','publishing_update':'Publishing update','update_published':'Update published; coordinator acceptance unconfirmed','waiting_for_aggregate':'Update published; waiting for shared model','aggregate_received':'Shared model verified and saved locally'}
                    row.update(status=labels[kind],sha256=details.get('payload_sha256'))
        busy=self.process is not None and self.process.poll() is None
        launch_error=None
        if self.process is not None and self.process.poll() not in (None,0):
            launch_error='Local federation worker exited with an error. Check the saved setup, broker, schema, dependencies and terminal log.'
        return dict(profile=profile,roster=roster,current_round=latest_round,rounds=config['rounds'],runs=runs[:5],
            process_running=busy,launch_pending=busy and (not active or active['status']!='Running'),launch_error=launch_error,
            checked=self.checked[3] if self.checked else None,bank=bank,local_client_id=CLIENTS.get(bank),
            feature_schema_sha256=hashlib.sha256(SCHEMA.read_bytes()).hexdigest() if SCHEMA.is_file() else None,
            topics=dict(global_model=GLOBAL_TOPIC,client_updates=UPDATE_TOPIC))
