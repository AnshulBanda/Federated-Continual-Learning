#!/usr/bin/env python3
"""Exercise final ensemble validation, grouped XAI and local adaptation through HTTP.

Uses a separate local state folder. Never loads September transactions or changes
original model checkpoints. Kafka collaboration has its own acceptance command.
"""
import argparse
import json
import re
import sys
import threading
import time
import urllib.request
import uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from streaming.app.dashboard import server
from streaming.app.final_model import reference_evidence


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skip-training',action='store_true')
    args=parser.parse_args()
    root=ROOT/'streaming/.local'/('dashboard-check-'+uuid.uuid4().hex[:10])
    app=server(root,0);thread=threading.Thread(target=app.serve_forever,daemon=True);thread.start()
    base='http://127.0.0.1:'+str(app.server_port)
    html=urllib.request.urlopen(base).read().decode()
    token=re.search("const token='([^']+)'",html).group(1)
    def get(route):return json.load(urllib.request.urlopen(base+route))
    def post(route,body):
        request=urllib.request.Request(base+route,data=json.dumps(body).encode(),headers={'Content-Type':'application/json','Origin':base,'X-Session-Token':token})
        return json.load(urllib.request.urlopen(request))
    def wait(route,key,timeout=300):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            status=get(route)
            job=next(j for j in status['jobs'] if j['id']==key)
            if job['status'] not in ('Queued','Running') and not status.get('process_running'):
                if job['status']!='Completed':raise RuntimeError(job['detail'])
                return job
            time.sleep(.3)
        raise TimeoutError(route+' timed out')
    evidence={'reference_macro_september_pr_auc':reference_evidence()['macro_pr_auc'],
              'test_data_loaded':False,'validation':[],'state_dir':str(root)}
    dataset=str(ROOT/'data/final_temporal_dataset')
    try:
        for bank in ('JPMorgan_Chase','Wells_Fargo','Key_Bank'):
            post('/api/overview',{'bank':bank})
            job=post('/api/monitoring/start',{'dataset':dataset})
            completed=wait('/api/monitoring',job['id'])
            expected=next(r['validation']['pr_auc'] for r in reference_evidence()['per_bank'] if r['bank']==bank)
            actual=completed['metrics']['pr_auc']
            assert abs(expected-actual)<1e-12,(bank,expected,actual)
            evidence['validation'].append({'bank':bank,'pr_auc':actual,'matches_frozen':True})
            print(bank+': validation PR-AUC matches frozen ensemble: '+str(actual),flush=True)
        rows=get('/api/monitoring/rows/'+completed['id'])['rows']
        transaction=max(rows,key=lambda r:r['score'])
        job=post('/api/explanations/start',{'replay_id':completed['id'],'txn_id':transaction['txn_id']})
        explained=wait('/api/explanations',job['id'])['report']
        assert abs(explained['ensemble_probability']-transaction['score'])<2e-6
        assert abs(explained['additivity_residual'])<1e-5
        evidence['xai']={'matches_replay':True,'additivity_residual':explained['additivity_residual'],
                         'method':explained['method'],'background_size':explained['background_size']}
        print('Grouped XAI matches the selected high-risk transaction.',flush=True)
        if not args.skip_training:
            job=post('/api/training/start',{'kind':'check','dataset':dataset});wait('/api/training',job['id'])
            job=post('/api/training/start',{'kind':'train','dataset':dataset});trained=wait('/api/training',job['id'])
            selected=post('/api/training/activate',{'id':job['id']})
            assert len(selected['members'])==3
            job=post('/api/monitoring/start',{'dataset':dataset});scored=wait('/api/monitoring',job['id'])
            assert abs(scored['metrics']['pr_auc']-trained['metrics']['validation']['pr_auc'])<1e-12
            evidence['local_adaptation']={'completed':True,'members':3,'validation_pr_auc':scored['metrics']['pr_auc'],
                'reloaded_score_matches':True,'member_results':trained['metrics']['members']}
            print('Local adaptation, selection and reloaded ensemble evaluation passed.',flush=True)
        evidence['privacy']=get('/api/privacy')
        assert evidence['privacy']['differential_privacy'] is False
        evidence['result']='PASS'
        (root/'result.json').write_text(json.dumps(evidence,indent=2)+'\n')
        print('PASS · Evidence: '+str(root/'result.json'),flush=True)
    finally:
        app.shutdown();app.server_close();thread.join()

if __name__=='__main__':main()
