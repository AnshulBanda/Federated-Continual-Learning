const assert=require('node:assert/strict'),test=require('node:test'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..');
function doc(){
 const nodes=new Map();
 const make=()=>({value:'',innerHTML:'',textContent:'',hidden:false,open:true,options:[],dataset:{},handlers:{},classList:{toggle(){}},
  addEventListener(k,fn){this.handlers[k]=fn},replaceChildren(){this.options=[];this.innerHTML=''},append(e){this.options.push(e)},focus(){},scrollIntoView(){}});
 return {nodes,getElementById(id){if(!nodes.has(id))nodes.set(id,make());return nodes.get(id)},createElement:make,
  querySelector(selector){return this.getElementById(selector.replace(/^#/,''))},querySelectorAll(){return[]}};
}
function replay(id='replay',bank='Wells_Fargo'){
 return {replay_id:id,bank,dataset_fingerprint:'data',member_count:3,threshold:.3,model:{sha256:'model-'+id,model_kind:'adaptive_probability_ensemble',version:'Reference ensemble',privacy:{differential_privacy:false}},rows:[{txn_id:'tx-'+id,score:.4}]};
}
function client(overrides={}){
 const document=doc(),context=vm.createContext({document});
 vm.runInContext(fs.readFileSync(path.join(root,'streaming/web/replay_investigator.js'),'utf8'),context);
 let bank='Wells_Fargo';const rendered=[],opened=[];const jobs=[];
 const controller=context.ReplayInvestigator.create({document,banks:{Wells_Fargo:'Wells Fargo',Key_Bank:'Key Bank'},getBank:()=>bank,
  setBank:async value=>bank=value,openTab:value=>opened.push(value),component:{renderVerified:(r,s)=>rendered.push({r,s})},
  post:async(url,data)=>{const r=replay(data.replay_id,bank),j={id:'job-'+data.replay_id,bank,replay_id:data.replay_id,txn_id:data.txn_id,status:'Completed',report_ready:true,detail:'Verified',model:r.model};jobs.unshift(j);return j},
  json:async url=>url==='/api/monitoring'?{jobs:jobs.map(j=>({...j,id:j.replay_id}))}:url==='/api/explanations'?{jobs}:url.startsWith('/api/explanations/report/')?{id:url.split('/').pop()}:replay(url.split('/').pop(),bank),...overrides});
 return {controller,document,rendered,opened,setBank:value=>bank=value,jobs};
}

test('Explain score passes the same replay transaction, score, cutoff and model directly to the embedded view',async()=>{
 const h=client(),r=replay();await h.controller.request(r.rows[0],r);
 assert.deepEqual(h.opened,['explanations']);assert.equal(h.rendered.length,1);
 const s=h.rendered[0].s;for(const [key,value]of Object.entries({transaction_id:'tx-replay',replay_id:'replay',score:.4,threshold:.3,model_sha256:'model-replay',model_count:3,model_family:'adaptive_probability_ensemble',dataset_fingerprint:'data',private_model:false}))assert.equal(s[key],value);
 assert.equal(h.document.getElementById('xaitransaction').value,'tx-replay');
 assert.equal(h.document.getElementById('xaibrowser').open,false);
 assert.equal(h.document.getElementById('xaireport').hidden,false);
});

test('periodic refresh does not reset graph inspection, reopen evidence or overwrite verified model context',async()=>{
 const h=client(),r=replay();await h.controller.request(r.rows[0],r);
 const message=h.document.getElementById('xainotice').textContent;await h.controller.refresh();
 assert.equal(h.rendered.length,1);assert.equal(h.document.getElementById('xainotice').textContent,message);
 assert.match(message,/replay model Reference ensemble/);
});

test('cross-bank or identity-incomplete replay requests fail closed before starting an explanation',async()=>{
 let calls=0;const h=client({post:async()=>{calls++;throw Error('should not post')}}),r=replay('wrong','Key_Bank');
 await h.controller.request(r.rows[0],r);assert.equal(calls,0);assert.equal(h.rendered.length,0);
 const missing=replay();delete missing.dataset_fingerprint;await h.controller.request(missing.rows[0],missing);
 assert.equal(calls,0);assert.match(h.document.getElementById('xainotice').textContent,/missing verified data identity/);
});

test('out-of-order explanation requests cannot overwrite the newest replay selection',async()=>{
 const pending=[];const h=client({post:(url,data)=>new Promise(resolve=>pending.push({data,resolve}))});
 const a=replay('a'),b=replay('b'),first=h.controller.request(a.rows[0],a),second=h.controller.request(b.rows[0],b);
 const job=r=>({id:'job-'+r.replay_id,bank:r.bank,replay_id:r.replay_id,txn_id:r.rows[0].txn_id,status:'Completed',report_ready:true,detail:'Verified',model:r.model});
 pending[1].resolve(job(b));await second;pending[0].resolve(job(a));await first;
 assert.equal(h.rendered.length,1);assert.equal(h.rendered[0].s.replay_id,'b');
});

test('a bank change while a report is loading prevents stale evidence from rendering',async()=>{
 let release;const h=client({json:async url=>url==='/api/monitoring'?{jobs:[]}:url==='/api/explanations'?{jobs:[]}:new Promise(resolve=>release=resolve)});
 const r=replay(),request=h.controller.request(r.rows[0],r);
 for(let i=0;i<20&&!release;i++)await Promise.resolve();
 assert.ok(release);h.setBank('Key_Bank');release({report:true});await request;
 assert.equal(h.rendered.length,0);
});

test('failed backend or incompatible legacy reports never expose a partial explanation',async()=>{
 for(const status of ['Failed','Completed']){
  const h=client({post:async()=>({id:'bad',bank:'Wells_Fargo',replay_id:'replay',txn_id:'tx-replay',status,report_ready:false,detail:'Parity mismatch'})});
  const r=replay();await h.controller.request(r.rows[0],r);
  assert.equal(h.rendered.length,0);assert.equal(h.document.getElementById('xaireport').hidden,true);
  assert.match(h.document.getElementById('xainotice').textContent,status==='Failed'?/Parity mismatch/:/older explanation/);
 }
});

test('browser selection preserves the typed transaction when the replay needs loading',async()=>{
 const h=client();await h.controller.refreshReplays();h.document.getElementById('xaireplay').value='browse';h.document.getElementById('xaitransaction').value='tx-browse';
 await h.controller.explainSelected();assert.equal(h.rendered.length,1);assert.equal(h.rendered[0].s.transaction_id,'tx-browse');
});

test('a replay-load failure cannot fall back to a previously loaded model',async()=>{
 let fail=false;const h=client({json:async url=>{if(url.startsWith('/api/monitoring/rows/')){if(fail)throw Error('Unavailable');return replay(url.split('/').pop())}return {jobs:[]}}});
 h.document.getElementById('xaireplay').value='a';await h.controller.loadReplay();fail=true;h.document.getElementById('xaireplay').value='b';h.document.getElementById('xaitransaction').value='tx-a';
 await h.controller.explainSelected();assert.equal(h.rendered.length,0);assert.match(h.document.getElementById('xainotice').textContent,/existing transaction/);
});

function replayValidator(){
 const document=doc(),ctx=vm.createContext({document,URLSearchParams,setTimeout,clearTimeout,ExplanationSummary:require('../static/explanation_summary.js')});
 vm.runInContext(fs.readFileSync(path.join(root,'xai/static/dashboard.js'),'utf8'),ctx);return ctx.InvestigatorXAI.create();
}
function pair(){
 const x=JSON.parse(fs.readFileSync(path.join(root,'xai/review/explanation-ux-v2/cases/Wells_Fargo_2954161.json')));
 x.replay_id='replay';x.replay_provenance={dataset_fingerprint:'data'};
 const s={bank:x.bank,transaction_id:x.transaction_id,replay_id:'replay',model_sha256:x.model.checkpoint_sha256,model_count:1,model_family:x.model.family,private_model:false,score:x.prediction.probability,threshold:x.prediction.threshold,dataset_fingerprint:'data'};
 return {x,s};
}

test('embedded replay validation rejects a different model, transaction, history/data or cutoff',()=>{
 const api=replayValidator();for(const field of ['model_sha256','transaction_id','replay_id','model_family','dataset_fingerprint']){const {x,s}=pair();s[field]='other';assert.throws(()=>api.validateReplay(x,s),/refused/)}
 const {x,s}=pair();s.threshold+=.1;assert.throws(()=>api.validateReplay(x,s),/cutoff/);
});

test('embedded replay target parity rejects 1.5e-6 and accepts 0.5e-6 without relaxing the guard',()=>{
 const api=replayValidator(),{x,s}=pair();api.validateReplay(x,s);
 x.feature_explanation.target_probability=s.score+.5e-6;api.validateReplay(x,s);
 x.feature_explanation.target_probability=s.score+1.5e-6;assert.throws(()=>api.validateReplay(x,s),/1e-6/);
});

test('an ensemble or private report cannot substitute a different member count or privacy scope',()=>{
 const api=replayValidator();let {x,s}=pair();s.model_count=3;assert.throws(()=>api.validateReplay(x,s),/model/);
 ({x,s}=pair());s.private_model=true;assert.throws(()=>api.validateReplay(x,s),/privacy/);
});

test('the shared renderer has no automatic standalone boot in the AML shell',()=>{
 const html=fs.readFileSync(path.join(root,'streaming/web/index.html'),'utf8');
 assert.match(html,/src="\/assets\/xai\/dashboard.js"/);assert.doesNotMatch(html,/data-standalone|<iframe|8766/);
 const standalone=fs.readFileSync(path.join(root,'xai/static/dashboard.html'),'utf8');assert.match(standalone,/data-standalone/);
});
