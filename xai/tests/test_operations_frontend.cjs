const assert=require('node:assert/strict'),test=require('node:test'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const root=path.resolve(__dirname,'../..'),BankDisplay=require('../static/bank_display.js'),Summary=require('../static/explanation_summary.js');
const forbidden=/Key[_ ]Bank|Wells[_ ]Fargo|JPMorgan[_ ]Chase/i;
function doc(){
 const nodes=new Map();
 const make=()=>({value:'',innerHTML:'',textContent:'',hidden:false,open:true,options:[],dataset:{},handlers:{},classList:{toggle(){}},
  addEventListener(k,fn){this.handlers[k]=fn},replaceChildren(){this.options=[];this.innerHTML=''},append(e){this.options.push(e)},focus(){},scrollIntoView(){}});
 return {nodes,getElementById(id){if(!nodes.has(id))nodes.set(id,make());return nodes.get(id)},createElement:make,
  querySelector(selector){return this.getElementById(selector.replace(/^#/,''))},querySelectorAll(){return[]}};
}
function replay(id='replay',bank='Wells_Fargo'){
 return {replay_id:id,bank,dataset_fingerprint:'data',member_count:3,threshold:.3,model:{sha256:'model-'+id,model_kind:'adaptive_probability_ensemble',version:'Reference ensemble',privacy:{differential_privacy:false}},rows:[{txn_id:'tx-'+id,score:.4,evaluation_label:'fraud'}]};
}
function client(overrides={}){
 const document=doc(),context=vm.createContext({document,BankDisplay});
 vm.runInContext(fs.readFileSync(path.join(root,'streaming/web/replay_investigator.js'),'utf8'),context);
 let bank='Wells_Fargo';const rendered=[],opened=[],jobs=[];
 const baseJSON=async url=>url==='/api/monitoring'?{jobs:['replay','a','b','browse'].map(id=>({id,bank,status:'Completed',started:'2026-10-28',model:replay(id,bank).model}))}:url==='/api/explanations'?{jobs}:url.startsWith('/api/explanations/report/')?{id:url.split('/').pop()}:replay(url.split('/').pop(),bank);
 const controller=context.ReplayInvestigator.create({document,banks:BankDisplay.names,getBank:()=>bank,
  setBank:async value=>bank=value,openTab:value=>opened.push(value),component:{renderVerified:(r,s)=>rendered.push({r,s})},
  post:async(url,data)=>{const r=replay(data.replay_id,bank),j={id:'job-'+data.replay_id,bank,replay_id:data.replay_id,txn_id:data.txn_id,status:'Completed',report_ready:true,detail:'Verified',model:r.model};jobs.unshift(j);return j},
  ...overrides,json:url=>overrides.json?overrides.json(url,baseJSON):baseJSON(url)});
 return {controller,document,rendered,opened,setBank:value=>bank=value,jobs,api:context.ReplayInvestigator};
}
const spin=async predicate=>{for(let i=0;i<100&&!predicate();i++)await Promise.resolve();assert.ok(predicate())};

test('Explain score opens the exact replay with score, cutoff, model and independent label selected',async()=>{
 const h=client(),r=replay();await h.controller.request(r.rows[0],r);
 assert.deepEqual(h.opened,['explanations']);assert.equal(h.rendered.length,1);
 const s=h.rendered[0].s;for(const [key,value]of Object.entries({transaction_id:'tx-replay',replay_id:'replay',score:.4,threshold:.3,model_sha256:'model-replay',model_count:3,model_family:'adaptive_probability_ensemble',dataset_fingerprint:'data',private_model:false,evaluation_label:'fraud'}))assert.equal(s[key],value);
 assert.equal(h.document.getElementById('xaitransaction').value,'tx-replay');assert.equal(h.document.getElementById('xaibrowser').open,false);
});
test('periodic refresh preserves graph inspection, disclosures and verified model context',async()=>{
 const h=client(),r=replay();await h.controller.request(r.rows[0],r);const message=h.document.getElementById('xainotice').textContent;
 await h.controller.refresh();assert.equal(h.rendered.length,1);assert.equal(h.document.getElementById('xainotice').textContent,message);
});
test('cross-bank and data-incomplete requests fail closed before starting an explanation',async()=>{
 let calls=0;const h=client({post:async()=>{calls++}}),r=replay('wrong','Key_Bank');await h.controller.request(r.rows[0],r);
 const missing=replay();delete missing.dataset_fingerprint;await h.controller.request(missing.rows[0],missing);
 assert.equal(calls,0);assert.equal(h.rendered.length,0);assert.match(h.document.getElementById('xainotice').textContent,/missing verified data identity/);
});
test('out-of-order explanation requests cannot overwrite the newest transaction',async()=>{
 const pending=[],h=client({post:(url,data)=>new Promise(resolve=>pending.push({data,resolve}))}),a=replay('a'),b=replay('b');
 const first=h.controller.request(a.rows[0],a);await spin(()=>pending.length===1);
 const second=h.controller.request(b.rows[0],b);await spin(()=>pending.length===2);
 const job=r=>({id:'job-'+r.replay_id,bank:r.bank,replay_id:r.replay_id,txn_id:r.rows[0].txn_id,status:'Completed',report_ready:true,detail:'Verified',model:r.model});
 pending[1].resolve(job(b));await second;pending[0].resolve(job(a));await first;assert.equal(h.rendered.length,1);assert.equal(h.rendered[0].s.replay_id,'b');
});
test('bank changes during report loading prevent stale evidence from rendering',async()=>{
 let release;const h=client({json:(url,base)=>url.startsWith('/api/explanations/report/')?new Promise(resolve=>release=resolve):base(url)}),r=replay();
 const request=h.controller.request(r.rows[0],r);await spin(()=>!!release);h.setBank('Key_Bank');release({report:true});await request;assert.equal(h.rendered.length,0);
});
test('failed backend and legacy reports never expose a partial explanation',async()=>{
 for(const status of ['Failed','Completed']){const h=client({post:async()=>({id:'bad',bank:'Wells_Fargo',replay_id:'replay',txn_id:'tx-replay',status,report_ready:false,detail:'Parity mismatch'})}),r=replay();
  await h.controller.request(r.rows[0],r);assert.equal(h.rendered.length,0);assert.equal(h.document.getElementById('xaireport').hidden,true);
  assert.match(h.document.getElementById('xainotice').textContent,status==='Failed'?/Parity mismatch/:/older explanation/);
 }
});
test('dropdown browsing needs no typed ID and explains the selected transaction',async()=>{
 const h=client();await h.controller.refresh();assert.equal(h.document.getElementById('xaitransaction').value,'tx-replay');
 h.document.getElementById('xaireplay').value='browse';await h.controller.loadReplay();await h.controller.explainSelected();
 assert.equal(h.rendered[0].s.transaction_id,'tx-browse');assert.equal(h.document.getElementById('xaibrowser').open,false);
});
test('replay-load failures cannot fall back to an older loaded model',async()=>{
 let fail=false;const h=client({json:(url,base)=>{if(fail&&url.startsWith('/api/explanations/cases/'))throw Error('Unavailable');return base(url)}});
 await h.controller.refresh();fail=true;h.document.getElementById('xaireplay').value='b';await h.controller.loadReplay();await h.controller.explainSelected();
 assert.equal(h.rendered.length,0);assert.equal(h.document.getElementById('xaitransaction').options.length,0);
});
function replayValidator(){
 const document=doc(),ctx=vm.createContext({document,URLSearchParams,setTimeout,clearTimeout,BankDisplay,ExplanationSummary:Summary});
 vm.runInContext(fs.readFileSync(path.join(root,'xai/static/dashboard.js'),'utf8'),ctx);return {api:ctx.InvestigatorXAI.create(),document};
}
function pair(){
 const x=JSON.parse(fs.readFileSync(path.join(root,'xai/review/explanation-ux-v2/cases/Wells_Fargo_2954161.json')));x.replay_id='replay';x.replay_provenance={dataset_fingerprint:'data'};
 const s={bank:x.bank,transaction_id:x.transaction_id,replay_id:'replay',model_sha256:x.model.checkpoint_sha256,model_count:1,model_family:x.model.family,private_model:false,score:x.prediction.probability,threshold:x.prediction.threshold,dataset_fingerprint:'data',evaluation_label:x.evaluation_label};return {x,s};
}
test('embedded validation rejects changed model, transaction, replay data, cutoff or independent label',()=>{
 const {api}=replayValidator();for(const field of ['model_sha256','transaction_id','replay_id','model_family','dataset_fingerprint','evaluation_label']){const {x,s}=pair();s[field]='other';assert.throws(()=>api.validateReplay(x,s),/refused/)}
 const {x,s}=pair();s.threshold+=.1;assert.throws(()=>api.validateReplay(x,s),/cutoff/);
});
test('strict parity still accepts 0.5e-6 and refuses 1.5e-6',()=>{
 const {api}=replayValidator(),{x,s}=pair();x.feature_explanation.target_probability=s.score+.5e-6;api.validateReplay(x,s);
 x.feature_explanation.target_probability=s.score+1.5e-6;assert.throws(()=>api.validateReplay(x,s),/1e-6/);
});
test('member counts and privacy scope cannot substitute another replay model',()=>{
 const {api}=replayValidator();let {x,s}=pair();s.model_count=3;assert.throws(()=>api.validateReplay(x,s),/model/);
 ({x,s}=pair());s.private_model=true;assert.throws(()=>api.validateReplay(x,s),/privacy/);
});
test('the approved renderer stays embedded with one shell and no iframe or standalone bootstrap',()=>{
 const html=fs.readFileSync(path.join(root,'streaming/web/index.html'),'utf8');assert.match(html,/src="\/assets\/xai\/dashboard.js"/);assert.doesNotMatch(html,/data-standalone|<iframe|8766/);
 assert.match(fs.readFileSync(path.join(root,'xai/static/dashboard.html'),'utf8'),/data-standalone/);
});
const mixed=[{txn_id:'tp',score:.9,evaluation_label:'fraud'},{txn_id:'fp',score:.8,evaluation_label:'not_fraud'},{txn_id:'tn',score:.1,evaluation_label:'not_fraud'},{txn_id:'fn',score:.2,evaluation_label:'fraud'},{txn_id:'boundary',score:.5,evaluation_label:'fraud'}];
const ids=rows=>Array.from(rows,r=>r.txn_id);
test('flagged and not-flagged filters use the saved cutoff, independently of actual labels',()=>{
 const {filterRows}=client().api;assert.deepEqual(ids(filterRows(mixed,.5,'flagged')),['tp','fp','boundary']);assert.deepEqual(ids(filterRows(mixed,.5,'not_flagged')),['tn','fn']);
});
test('fraud, not-fraud and combined filters return all and only the matching cases',()=>{
 const {filterRows}=client().api;assert.deepEqual(ids(filterRows(mixed,.5,'all','fraud')),['tp','boundary','fn']);assert.deepEqual(ids(filterRows(mixed,.5,'all','not_fraud')),['fp','tn']);
 assert.deepEqual(ids(filterRows(mixed,.5,'flagged','not_fraud')),['fp']);assert.deepEqual(ids(filterRows(mixed,.5,'not_flagged','fraud')),['fn']);
});
test('transaction ordering is deterministic and uses the transaction ID to break score ties',()=>{
 const {filterRows}=client().api;const rows=['z','a','b'].map(txn_id=>({txn_id,score:.8,evaluation_label:'fraud'}));assert.deepEqual(ids(filterRows(rows,.5)),['a','b','z']);assert.deepEqual(rows.map(r=>r.txn_id),['z','a','b']);
});
test('the transaction dropdown contains every matching case without a truncation cap',async()=>{
 const rows=Array.from({length:220},(_,i)=>({txn_id:String(i),score:.9-i*.001,evaluation_label:'fraud'}));
 const h=client({json:(url,base)=>url.startsWith('/api/explanations/cases/')?{...replay(),rows}:base(url)});await h.controller.refresh();
 assert.equal(h.document.getElementById('xaitransaction').options.length,220);assert.equal(h.document.getElementById('xaitransaction').value,'0');
});
test('changing banks clears old replay and transaction choices and resets the demo filters',async()=>{
 const h=client();await h.controller.refresh();h.document.getElementById('xaiactuallabel').value='fraud';h.setBank('Key_Bank');await h.controller.refresh();
 assert.equal(h.document.getElementById('xaibank').value,'Key_Bank');assert.equal(h.document.getElementById('xaiactuallabel').value,'all');assert.equal(h.document.getElementById('xaimodelresult').value,'flagged');
 assert.equal(h.document.getElementById('xaireport').hidden,true);assert.equal(h.rendered.length,0);
});
test('empty combined filters show the explicit empty state and cannot request a fabricated case',async()=>{
 const h=client();await h.controller.refresh();h.document.getElementById('xaimodelresult').value='not_flagged';await h.document.getElementById('xaimodelresult').handlers.change();
 assert.equal(h.document.getElementById('xaitransaction').value,'');assert.equal(h.document.getElementById('xaiexplain').disabled,true);assert.equal(h.document.getElementById('xainotice').textContent,'No transactions match these filters.');
 await h.controller.explainSelected();assert.equal(h.rendered.length,0);
});
test('changing a transaction invalidates the previous hero before another explanation is requested',async()=>{
 const h=client(),r=replay();await h.controller.request(r.rows[0],r);await h.document.getElementById('xaitransaction').handlers.change();assert.equal(h.document.getElementById('xaireport').hidden,true);
});
test('all four evaluation case types are separate from the unchanged explanation and graph',()=>{
 const {api}=replayValidator();for(const [flagged,label,title]of [[true,'fraud','TRUE POSITIVE'],[true,'not_fraud','FALSE POSITIVE'],[false,'not_fraud','TRUE NEGATIVE'],[false,'fraud','MISSED FRAUD']]){
  const {x}=pair();x.prediction.probability=flagged?.8:.1;x.prediction.threshold=.5;x.evaluation_label=label;const before=JSON.stringify(x);
  const html=api.renderCaseComparison(Summary.summarize(x));assert.match(html,new RegExp(title));assert.match(html,/independent evaluation|INDEPENDENT EVALUATION/);assert.match(html,/did not determine/);assert.doesNotMatch(html,/undefined|NaN/);assert.equal(JSON.stringify(x),before);
 }
});
test('display aliases have canonical option values for all three banks',async()=>{
 assert.deepEqual(BankDisplay.names,{Key_Bank:'Bank A',Wells_Fargo:'Bank B',JPMorgan_Chase:'Bank C'});const h=client();await h.controller.refresh();
 assert.deepEqual(h.document.getElementById('xaibank').options.slice(1).map(o=>[o.value,o.textContent]),Object.entries(BankDisplay.names));
});
test('visible XAI and raw audit displays contain aliases while model, data and provenance objects stay canonical',()=>{
 const {api,document}=replayValidator();for(const bank of Object.keys(BankDisplay.names)){
  const {x}=pair();x.bank=bank;const before=JSON.stringify(x);api.render(x);const html=document.getElementById('detail').innerHTML;
  assert.doesNotMatch(html,forbidden);assert.ok(html.includes(BankDisplay.label(bank)));assert.doesNotMatch(html,/undefined|NaN/);assert.match(html,/investigation-hero/);assert.match(html,/Transaction network/i);assert.equal(JSON.stringify(x),before);
 }
});
test('the central display boundary anonymizes nested status, errors, paths, labels and accessible tooltips, preserving internal attributes',()=>{
 const node=(tagName,attributes={},children=[])=>({nodeType:1,tagName,attributes,childNodes:children,getAttribute(k){return this.attributes[k]??null},setAttribute(k,v){this.attributes[k]=v}});
 const text={nodeType:3,nodeValue:'Key Bank / Wells_Fargo / JPMorgan Chase'};const option=node('OPTION',{value:'Wells_Fargo',title:'JPMorgan_Chase'},[text]);
 const scriptText={nodeType:3,nodeValue:'Key_Bank'};const root=node('DIV',{},[option,node('SCRIPT',{},[scriptText])]);BankDisplay.sanitize(root);
 assert.equal(text.nodeValue,'Bank A / Bank B / Bank C');assert.equal(option.attributes.title,'Bank C');assert.equal(option.attributes.value,'Wells_Fargo');assert.equal(scriptText.nodeValue,'Key_Bank');
 assert.equal(BankDisplay.text('Failed /training/JPMorgan_Chase/checkpoint Key_Bank WELLS FARGO'),'Failed /training/Bank C/checkpoint Bank A Bank B');
});
test('invalid scores or missing independent labels never render undefined or NaN choices',()=>{
 const {filterRows}=client().api;assert.throws(()=>filterRows([{txn_id:'x',score:NaN,evaluation_label:'fraud'}],.5),/Verified/);
 assert.throws(()=>filterRows([{txn_id:'x',score:.2}],.5),/Verified/);assert.throws(()=>filterRows(mixed,NaN),/cutoff/);
});
test('late-rendered legacy status text is anonymized by the display observer before the next paint',()=>{
 const previous=global.MutationObserver;let callback,watched;
 global.MutationObserver=class{constructor(fn){callback=fn}observe(root,options){watched=options}};
 try{
  const root={nodeType:1,tagName:'DIV',childNodes:[],getAttribute(){return null}};BankDisplay.observe(root);
  const late={nodeType:3,nodeValue:'Wells_Fargo worker failed; JPMorgan Chase / Key Bank'};
  callback([{type:'childList',addedNodes:[late]}]);assert.equal(late.nodeValue,'Bank B worker failed; Bank C / Bank A');
  late.nodeValue='KEY_BANK';callback([{type:'characterData',target:late}]);assert.equal(late.nodeValue,'Bank A');
  assert.deepEqual(watched.attributeFilter,['title','aria-label','placeholder']);
 }finally{if(previous===undefined)delete global.MutationObserver;else global.MutationObserver=previous}
});
