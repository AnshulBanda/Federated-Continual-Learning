const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const fixture = (bank, id) => JSON.parse(fs.readFileSync(path.join(root,
  'outputs/updated/adaptive_federated/seed_42/local', bank, 'reports', `validation_${id}`, 'explanation.json'), 'utf8'));
function harness(fetch) {
  const elements = new Map();
  function element(selector) {
    if (!elements.has(selector)) elements.set(selector, {
      value: selector === '#bank' ? 'Wells_Fargo' : selector === '#view' ? 'flagged' : '',
      innerHTML: '', textContent: '', dataset: {}, disabled: false,
      addEventListener() {}, querySelectorAll() { return []; },
    });
    return elements.get(selector);
  }
  const context = vm.createContext({document: {querySelector: element, querySelectorAll: () => []},
    URLSearchParams, location: {search: ''}, history: {replaceState() {}}, fetch,
    setTimeout, clearTimeout, ExplanationSummary: require('../static/explanation_summary.js')});
  const source = fs.readFileSync(path.join(root, 'static/dashboard.js'), 'utf8').replace(/\ninit\(\);\s*$/, '\n');
  vm.runInContext(source + '\nthis.api={render,validateExplanation,loadRows,loadExplanation,graphEdgeDetails,readableTechnicalDetails,observedPatterns,renderSimpleExplanation,setManifest:value=>currentManifest=value};', context);
  return {api: context.api, element};
}

test('every cached bank/transaction renders feature directions from its own SHAP', () => {
  const h = harness();
  let count = 0;
  for (const bank of ['JPMorgan_Chase', 'Wells_Fargo', 'Key_Bank']) {
    const folder = path.join(root, 'outputs/updated/adaptive_federated/seed_42/local', bank, 'reports');
    for (const name of fs.readdirSync(folder)) {
      const reportPath = path.join(folder, name, 'explanation.json');
      if (!fs.existsSync(reportPath)) continue;
      const report = JSON.parse(fs.readFileSync(reportPath, 'utf8'));
      h.api.validateExplanation(report, bank, report.transaction_id);
      h.api.render(report);
      const html = h.element('#detail').innerHTML;
      assert.ok(html.includes(`<h2>Transaction ${report.transaction_id}</h2>`));
      assert.ok(!html.includes('The main factor or its direction changed'));
      const summary = require('../static/explanation_summary.js').summarize(report);
      const simple = h.api.renderSimpleExplanation(report, summary);
      assert.ok(!/SHAP|logit|SHA-256|<pre>/.test(simple));
      for (const factor of summary.top_factors) {
        assert.ok(simple.includes(factor.label));
        assert.ok(simple.includes(factor.effect));
      }
      for (const feature of report.feature_explanation.features) {
        assert.ok(html.includes(String(feature.shap_logit)));
      }
      assert.ok(!html.includes('undefined'));
      count++;
    }
  }
  assert.ok(count >= 6);
});

test('empty eligible history renders an accurate message and no history table', () => {
  const h = harness();
  h.api.render(fixture('Wells_Fargo', '2954161'));
  const html = h.element('#detail').innerHTML;
  assert.ok(html.includes('No earlier eligible transfers involving these accounts were available to the model before this prediction'));
  assert.ok(!html.includes('no verified score test'));
  assert.ok(!html.includes('class="recorded-history"'));
  assert.ok(!html.includes('class="flow-table"'));
  assert.ok(html.includes('Observed:'));
});

test('untested existing history is not described as absent', () => {
  const report = fixture('JPMorgan_Chase', '180245');
  report.transaction_story.model_link_effects = [];
  const h = harness(); h.api.render(report);
  const html = h.element('#detail').innerHTML;
  assert.ok(html.includes('Earlier transfers were observed, but their effect on this prediction was not measured'));
  assert.ok(html.includes('class="recorded-history"'));
  assert.ok(!html.includes('No earlier eligible transfers involving these accounts were available'));
});

test('mixed identities, scores, feature values, decisions and stale graph effects are rejected', () => {
  const h = harness();
  const mutations = [
    r => r.transaction_id = 'wrong',
    r => r.transaction_story.selected_transfer.transaction_id = 'wrong',
    r => r.feature_explanation.target_probability = .7,
    r => r.feature_explanation.features[0].value = 'Wire',
    r => r.feature_explanation.features[1].value = 'amount: 0 / currency: USD',
    r => r.prediction.class = 'not_fraud',
    r => r.transaction_story.model_link_effects[0].original_model_score = .8,
  ];
  for (const mutate of mutations) {
    const report = fixture('JPMorgan_Chase', '180245'); mutate(report);
    assert.throws(() => h.api.validateExplanation(report, 'JPMorgan_Chase', '180245'), /consistency check failed/);
  }
});

function deferredFetch() {
  const requests = [];
  return {requests, fetch: url => new Promise(resolve => requests.push({url, resolve: data => resolve({ok:true,json:async()=>data})}))};
}
test('out-of-order catalog responses cannot overwrite the current bank threshold', async () => {
  const deferred = deferredFetch(), h = harness(deferred.fetch);
  const first = h.api.loadRows();
  h.element('#bank').value = 'Key_Bank';
  const second = h.api.loadRows();
  const catalog = (bank, threshold) => ({bank,threshold,total:0,counts:{known_fraud:0,missed_fraud:0},transactions:[]});
  deferred.requests[1].resolve(catalog('Key_Bank', .3759)); await second;
  deferred.requests[0].resolve(catalog('Wells_Fargo', .1869)); await first;
  assert.ok(h.element('#threshold').innerHTML.includes('0.3759'));
  assert.ok(!h.element('#threshold').innerHTML.includes('0.1869'));
});

test('out-of-order explanation responses cannot overwrite the selected transaction', async () => {
  const deferred = deferredFetch(), h = harness(deferred.fetch);
  h.element('#bank').value = 'JPMorgan_Chase';
  const first = h.api.loadExplanation('180245'), second = h.api.loadExplanation('2580817');
  deferred.requests[1].resolve(fixture('JPMorgan_Chase','2580817')); await second;
  deferred.requests[0].resolve(fixture('JPMorgan_Chase','180245')); await first;
  assert.ok(h.element('#detail').innerHTML.includes('<h2>Transaction 2580817</h2>'));
});


test('selected transfer cards across every bank show model score without historical-test wording', () => {
  const h = harness();
  for (const [bank,id] of [['Wells_Fargo','2954161'],['JPMorgan_Chase','180245'],['Key_Bank','2974317']]) {
    const report = fixture(bank,id);
    const html = h.api.graphEdgeDetails(report.transaction_story.selected_transfer, undefined, report.prediction);
    assert.ok(html.includes(`Model score: ${report.prediction.probability.toFixed(4)}`));
    assert.ok(!html.includes('Connection only:'));
    assert.ok(!html.includes('With this earlier transfer'));
    assert.ok(!html.includes('Without its history update'));
  }
  const report = fixture('JPMorgan_Chase','180245');
  const earlier = report.transaction_story.transfers.find(event => event.transaction_id === '180238');
  const effect = report.transaction_story.model_link_effects.find(effect => effect.transaction_id === '180238');
  const measured = h.api.graphEdgeDetails(earlier,effect,report.prediction);
  assert.ok(measured.includes('Helped lower the score'));
  assert.ok(measured.includes('Without its history update: 0.2785'));
  const context = h.api.graphEdgeDetails(earlier,undefined,report.prediction);
  assert.ok(context.includes('Selected transaction’s model score: 0.0862'));
  assert.ok(!context.includes('score effect has not been tested'));
});


test('technical threshold is bank-specific and a different bank threshold is rejected', () => {
  const h = harness();
  for (const [bank,id,threshold] of [['JPMorgan_Chase','180245','0.01780519'],['Wells_Fargo','2954161','0.18689416'],['Key_Bank','2974317','0.37591952']]) {
    const report=fixture(bank,id);
    h.api.validateExplanation(report,bank,id);
    h.api.render(report);
    assert.ok(h.element('#detail').innerHTML.includes(`Bank-specific threshold: <strong>${report.prediction.threshold}</strong>`));
  }
  const wrong=fixture('Wells_Fargo','2954161');
  wrong.prediction.threshold=wrong.xai_provenance.banks.JPMorgan_Chase.threshold;
  assert.throws(()=>h.api.validateExplanation(wrong,'Wells_Fargo','2954161'),/threshold differs from the selected bank/);
});


test('plain-language technical details adapt to selected score, directions, history and available checks', () => {
  const h=harness();
  const wells=fixture('Wells_Fargo','2954161');
  const empty=h.api.readableTechnicalDetails(wells);
  assert.ok(empty.includes(String(wells.prediction.probability)));
  assert.ok(empty.includes(String(wells.feature_explanation.features.find(f=>f.feature==='transfer_terms').shap_logit)));
  assert.ok(empty.includes('Exact SHAP (logit)'));
  assert.ok(empty.includes('0 eligible earlier transfers considered'));
  assert.ok(empty.includes('Not recorded for this transaction. This does not mean the check passed.'));
  assert.ok(!empty.includes('0.53210872'));
  const key=h.api.readableTechnicalDetails(fixture('Key_Bank','2974317'));
  assert.ok(key.includes(String(fixture('Key_Bank','2974317').feature_explanation.features[0].shap_logit)));
  assert.ok(key.includes('1 verified earlier-transfer test(s)'));
  assert.ok(!key.includes('The leading factor changed.'));
  const untested=h.api.readableTechnicalDetails(fixture('JPMorgan_Chase','2580817'));
  assert.ok(untested.includes('0 verified earlier-transfer test(s)'));
  const legitimate=h.api.readableTechnicalDetails(fixture('Wells_Fargo','2965480'));
  assert.ok(legitimate.includes('Model decision: Not flagged'));
  assert.ok(legitimate.includes('Exact margin:'));
});


test('observed pattern labels count distinct peers and require a chronological cycle', () => {
 const h=harness();
 const event=(source,target,day,kind='earlier')=>({source,target,timestamp:`2025-07-${String(day).padStart(2,'0')}T00:00:00`,kind});
 const selected=event('A','B',20,'selected');
 const labels=earlier=>Array.from(h.api.observedPatterns({selected_transfer:selected,transfers:[...earlier,selected]}),p=>p.label);
 assert.deepEqual(labels([]),[]);
 assert.deepEqual(labels([event('A','B',1),event('A','B',2)]),[]);
 assert.ok(labels([event('A','C',1),event('A','D',2)]).includes('Fan-out'));
 assert.ok(labels([event('C','B',1),event('D','B',2)]).includes('Fan-in'));
 assert.ok(labels([event('B','C',1),event('C','A',2)]).includes('Cycle'));
 assert.ok(!labels([event('B','C',2),event('C','A',1)]).includes('Cycle'));
 assert.ok(!labels([event('B','A',21)]).includes('Cycle'));
});

const summaryApi = require('../static/explanation_summary.js');
const clone = value => JSON.parse(JSON.stringify(value));
function cachedReports() {
 const reports=[];
 for(const bank of ['JPMorgan_Chase','Wells_Fargo','Key_Bank']) {
  const folder=path.join(root,'outputs/updated/adaptive_federated/seed_42/local',bank,'reports');
  for(const name of fs.readdirSync(folder)) {
   const file=path.join(folder,name,'explanation.json');
   if(fs.existsSync(file))reports.push(JSON.parse(fs.readFileSync(file,'utf8')));
  }
 }
 return reports;
}

test('all cached summaries deterministically select the measured primary direction, rank factors and compute margins',()=>{
 for(const x of cachedReports()) {
  const a=summaryApi.summarize(x),b=summaryApi.summarize(clone(x));
  assert.deepEqual(a,b);
  assert.equal(a.decision.margin,x.prediction.probability-x.prediction.threshold);
  const sorted=[...x.feature_explanation.features].sort((a,b)=>Math.abs(b.shap_logit)-Math.abs(a.shap_logit)||a.feature.localeCompare(b.feature));
  const primary=sorted.find(f=>a.decision.flagged?f.shap_logit>=1e-8:f.shap_logit<=-1e-8);
  assert.equal(a.primary_reason.feature,primary?.feature??null);
  assert.deepEqual(a.top_factors.map(f=>f.feature),sorted.slice(0,3).map(f=>f.feature));
  for(const f of a.top_factors) {
   assert.equal(f.direction,Math.abs(f.contribution)<1e-8?'neutral':f.contribution>0?'up':'down');
   assert.ok(f.observed.length>0);
  }
  const h=harness(),simple=h.api.renderSimpleExplanation(x,a);
  assert.doesNotMatch(simple,/SHAP|logit|SHA-256|<pre>|undefined|NaN/);
  assert.doesNotMatch(simple,/this proves fraud|this account is suspicious|caused fraud|knows the purpose/i);
  assert.match(simple,/MAIN REASON/);
  const technical=h.api.readableTechnicalDetails(x),withoutRaw=technical.split('<h3>I.')[0];
  assert.match(withoutRaw,/SHAP \(logit\)/);
  for(const f of x.feature_explanation.features)assert.ok(withoutRaw.includes(String(f.shap_logit)));
  assert.ok(withoutRaw.includes(String(x.prediction.threshold)));
  assert.ok(withoutRaw.includes(String(x.feature_explanation.target_logit)));
  assert.doesNotMatch(withoutRaw,/<pre>\s*\{/);
  assert.doesNotMatch(technical,/<details[^>]*\bopen\b/);
  h.api.render(x);
  assert.doesNotMatch(h.element('#detail').innerHTML,/<details[^>]*\bopen\b|undefined|NaN/);
 }
});

test('top three factors, ties, neutral values and relative strength boundaries remain deterministic',()=>{
 const x=fixture('Wells_Fargo','2954161');
 x.feature_explanation.features=[1,.67,-.33,.1,0].map((v,i)=>({feature:`group_${i}`,label:`Group ${i}`,value:'observed',shap_logit:v}));
 const s=summaryApi.summarize(x);
 assert.equal(s.top_factors.length,3);
 assert.deepEqual(s.top_factors.map(f=>f.strength),['Strong','Strong','Moderate']);
 x.prediction.probability=.01;
 assert.equal(summaryApi.summarize(x).primary_reason.feature,'group_2');
 x.feature_explanation.features.forEach(f=>f.shap_logit=0);
 assert.equal(summaryApi.summarize(x).primary_reason.feature,null);
 assert.ok(summaryApi.summarize(x).primary_reason.sentence.length>0);
 x.feature_explanation.features[0].shap_logit=NaN;
 assert.throws(()=>summaryApi.summarize(x),/measured feature/);
});

test('only independently verified replay effects create positive or negative history claims',()=>{
 for(const [bank,id,word] of [['JPMorgan_Chase','180245','lower'],['Key_Bank','2974317','higher']]) {
  const x=fixture(bank,id),s=summaryApi.summarize(x);
  assert.match(s.history_summary.sentence,new RegExp(word));
  assert.equal(s.history_summary.status,'tested');
  for(const mutate of [r=>r.transaction_story.model_link_effects[0].verified_model_count=0,
   r=>r.graph_explanation.fidelity.unperturbed_replay_error=1.5e-6,
   r=>r.graph_explanation.important_edges=[],
   r=>r.transaction_story.model_link_effects[0].score_support+=.1]) {
   const invalid=clone(x);mutate(invalid);
   assert.equal(summaryApi.summarize(invalid).history_summary.status,'untested');
   assert.throws(()=>harness().api.validateExplanation(invalid,bank,id),/consistency check failed/);
  }
 }
 const absent=summaryApi.summarize(fixture('Wells_Fargo','2954161'));
 assert.equal(absent.history_summary.status,'none');
 assert.match(absent.history_summary.sentence,/No earlier eligible/);
 const observed=fixture('JPMorgan_Chase','180245');observed.transaction_story.model_link_effects=[];
 const s=summaryApi.summarize(observed);
 assert.equal(s.history_summary.status,'untested');
 assert.match(s.history_summary.sentence,/effect on this prediction was not measured/);
 assert.ok(s.patterns.some(p=>p.label==='Fan-out'));
 assert.doesNotMatch(s.patterns.map(p=>p.description).join(' '),/push|influenc|caus|fraud|score/);
});

test('counterfactual decision changes require actual crossing with matching baseline and cutoff',()=>{
 const x=fixture('Wells_Fargo','2954161'),p=x.prediction;
 const candidate=score=>({valid:true,original_probability:p.probability,counterfactual_probability:score,changed_features:{amount:100}});
 x.counterfactual_explanation={threshold:p.threshold,candidates_evaluated:1,tested_alternatives:[candidate(p.threshold)]};
 assert.equal(summaryApi.summarize(x).counterfactual_summary.crossed,false); // equality is flagged
 assert.match(summaryApi.summarize(x).counterfactual_summary.sentence,/None of the tested/);
 x.counterfactual_explanation.tested_alternatives=[candidate(p.threshold-1e-8)];
 assert.equal(summaryApi.summarize(x).counterfactual_summary.crossed,true);
 assert.match(summaryApi.summarize(x).counterfactual_summary.sentence,/below/);
 x.counterfactual_explanation.threshold+=.1;
 assert.equal(summaryApi.summarize(x).counterfactual_summary.crossed,false);
 x.counterfactual_explanation.threshold=p.threshold;
 x.counterfactual_explanation.tested_alternatives[0].original_probability+=1.5e-6;
 assert.equal(summaryApi.summarize(x).counterfactual_summary.crossed,false);
 const unflagged=fixture('Wells_Fargo','2965480');
 unflagged.counterfactual_explanation={threshold:unflagged.prediction.threshold,candidates_evaluated:1,tested_alternatives:[{valid:true,changed_features:{amount:200},original_probability:unflagged.prediction.probability,counterfactual_probability:unflagged.prediction.threshold}]};
 assert.match(summaryApi.summarize(unflagged).counterfactual_summary.sentence,/at or above/);
 assert.match(summaryApi.summarize(unflagged).counterfactual_summary.note,/not a recommendation/);
});

test('evaluation labels remain independent of the four possible model outcomes',()=>{
 const x=fixture('Wells_Fargo','2954161');
 for(const [score,label,status] of [[.9,'fraud','True positive'],[.9,'not_fraud','False positive'],[.01,'not_fraud','True negative'],[.01,'fraud','Missed fraud (false negative)']]) {
  x.prediction.probability=score;x.evaluation_label=label;
  const s=summaryApi.summarize(x);
  assert.equal(s.evaluation.status,status);
  const primary=s.primary_reason;
  x.evaluation_label=label==='fraud'?'not_fraud':'fraud';
  assert.deepEqual(summaryApi.summarize(x).primary_reason,primary);
 }
});

test('privacy scope is explicit and model evidence or a relaxed parity tolerance is rejected',()=>{
 const x=fixture('Wells_Fargo','2954161');
 assert.equal(summaryApi.modelScope(x),'Non-private reference model');
 x.xai_provenance.privacy_mode='level3';
 assert.equal(summaryApi.modelScope(x),'Level-3 DP federated model');
 delete x.xai_provenance.privacy_mode;
 assert.equal(summaryApi.modelScope(x),'Model privacy scope not established');
 for(const mutate of [r=>r.model.checkpoint_sha256='stale',r=>r.cache_key_inputs.transaction_id='other',
  r=>r.verification.tolerance=1e-5,r=>r.verification.direct_model_probability+=1.5e-6,
  r=>r.feature_explanation.target_probability+=1.5e-6,r=>r.verification.passed=false]) {
  const invalid=fixture('Wells_Fargo','2954161');mutate(invalid);
  assert.throws(()=>harness().api.validateExplanation(invalid,'Wells_Fargo','2954161'),/consistency check failed/);
 }
 for(const field of ['base_logit','target_logit','additivity_residual']) {
  const invalid=fixture('Wells_Fargo','2954161');invalid.feature_explanation[field]=NaN;
  assert.throws(()=>harness().api.validateExplanation(invalid,'Wells_Fargo','2954161'),/attribution reconstruction/);
 }
 const valid=fixture('Wells_Fargo','2954161');valid.feature_explanation.target_probability+=.5e-6;
 assert.doesNotThrow(()=>harness().api.validateExplanation(valid,'Wells_Fargo','2954161'));
});


test('a self-consistent report from another checkpoint is rejected against the active catalog',()=>{
 const report=fixture('Wells_Fargo','2954161'),h=harness();
 h.api.setManifest(clone(report.xai_provenance));
 h.api.validateExplanation(report,'Wells_Fargo','2954161');
 for(const section of ['model','xai_provenance','cache_key_inputs'])report[section].checkpoint_sha256='other-model';
 report.verification.explained_checkpoint_sha256='other-model';
 assert.throws(()=>h.api.validateExplanation(report,'Wells_Fargo','2954161'),/active model/);
});
