const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const fixture = (bank, id) => JSON.parse(fs.readFileSync(path.join(root,
  'outputs/updated/adaptive_federated/seed_42/local', bank, 'reports', `validation_${id}`, 'explanation.json'), 'utf8'));
function harness(fetch, graphItems = []) {
  const elements = new Map();
  function element(selector) {
    if (!elements.has(selector)) elements.set(selector, {
      value: selector === '#bank' ? 'Wells_Fargo' : selector === '#view' ? 'flagged' : '',
      innerHTML: '', textContent: '', dataset: {}, disabled: false,
      addEventListener() {}, querySelectorAll() { return []; },
    });
    return elements.get(selector);
  }
  const context = vm.createContext({document: {querySelector: element, querySelectorAll: selector => selector === '[data-edge],[data-account]' ? graphItems : []},
    URLSearchParams, location: {search: ''}, history: {replaceState() {}}, fetch,
    setTimeout, clearTimeout, BankDisplay: require('../static/bank_display.js'), ExplanationSummary: require('../static/explanation_summary.js')});
  const source = fs.readFileSync(path.join(root, 'static/dashboard.js'), 'utf8');
  vm.runInContext(source, context);
  context.api=context.InvestigatorXAI.create();
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

test('the visible network precedes lower history, pattern, sensitivity and evaluation sections',()=>{
 const h=harness();h.api.render(fixture('JPMorgan_Chase','180245'));
 const html=h.element('#detail').innerHTML,network=html.indexOf('id="network-question"');
 for(const section of ['id="history-question"','id="patterns-question"','What would have changed the result?','Dataset label and model outcome','id="technical-explanation"'])assert.ok(network<html.indexOf(section));
 assert.equal((html.match(/class="flow-card"/g)||[]).length,1);
 assert.doesNotMatch(html,/<details[^>]*class="network-details"/);
});

test('network and simple model explanation share the first investigation hero',()=>{
 const h=harness();h.api.render(fixture('Wells_Fargo','2954161'));
 const html=h.element('#detail').innerHTML;
 const hero=html.slice(html.indexOf('<div class="investigation-hero">'),html.indexOf('<div class="followup-explanation">'));
 assert.match(hero,/class="hero-network"/);assert.match(hero,/class="hero-explanation"/);
 assert.match(hero,/Why was this flagged\?/);assert.match(hero,/MAIN REASON/);
 assert.match(hero,/Review cutoff/);assert.match(hero,/above cutoff/);
 assert.doesNotMatch(hero,/SHAP|logit|SHA-256|<pre>|undefined|NaN/);
 assert.equal((hero.match(/class="factor-card"/g)||[]).length,2);
});

test('default assets use the actual AML Operations design tokens and components',()=>{
 const css=fs.readFileSync(path.join(root,'static/dashboard.css'),'utf8');
 const aml=fs.readFileSync(path.join(root,'../streaming/web/index.html'),'utf8');
 for(const [token,value] of [['green','#14785f'],['ink','#182a33'],['muted','#657580'],['line','#dfe5e8']]){
  const pattern=new RegExp(`--${token}:\\s*${value}`);assert.match(css,pattern);assert.match(aml,pattern);
 }
 assert.match(css,/background:\s*#f4f6f8/);assert.match(css,/--surface:\s*#ffffff/);
 assert.match(css,/font-family:\s*Inter/);assert.match(css,/outline:\s*2px solid #92c8b7/);
 assert.match(css,/button:hover\s*\{\s*background:\s*#0d604b/);
 const html=fs.readFileSync(path.join(root,'static/dashboard.html'),'utf8');
 assert.match(html,/href="\/dashboard.css"/);assert.match(html,/AML \/ Explanations/);
 assert.doesNotMatch(html,/<nav/);
});

test('the standalone page no longer defines a dark root theme or navy panels',()=>{
 const css=fs.readFileSync(path.join(root,'static/dashboard.css'),'utf8');
 assert.match(css,/color-scheme:\s*light/);
 assert.doesNotMatch(css,/color-scheme:\s*dark|#09121e|#101e2f|#0b1725|linear-gradient/i);
});

test('the selected transaction has the prominent class, arrow and amount badge',()=>{
 const x=fixture('JPMorgan_Chase','180245'),html=harness().api.flowDiagram(x.transaction_story);
 assert.match(html,new RegExp(`class="graph-edge selected-transfer" data-edge="${x.transaction_id}"`));
 assert.match(html,/class="flow-line selected-transfer" marker-end="url\(#arrow-selected\)"/);
 assert.match(html,/class="edge-badge selected-transfer"/);assert.match(html,/class="flow-amount"/);
 assert.match(html,/Account A/);assert.ok(html.includes(x.transaction_story.selected_transfer.source_account_id));
});

test('observed transfers are distinct from edges with a verified replay test',()=>{
 const h=harness(),x=fixture('JPMorgan_Chase','180245'),story=x.transaction_story;
 const html=h.api.flowDiagram(story),tested=new Set(story.model_link_effects.map(e=>String(e.transaction_id)));
 for(const event of story.transfers.filter(t=>t.kind==='earlier')){
  const cls=tested.has(String(event.transaction_id))?'tested-down':'observed-only';
  assert.ok(html.includes(`class="graph-edge ${cls}" data-edge="${event.transaction_id}"`));
 }
 const css=fs.readFileSync(path.join(root,'static/dashboard.css'),'utf8');
 assert.match(css,/\.flow-line\.observed-only\s*\{\s*stroke-dasharray:/);
 assert.match(css,/\.flow-line\.tested-down\s*\{\s*stroke:\s*#27846c/);
});

test('tested edge visual directions continue to use the measured score support',()=>{
 const h=harness();let up=0,down=0;
 for(const x of cachedReports())for(const event of x.transaction_story.transfers){
  const effect=x.transaction_story.model_link_effects.find(e=>String(e.transaction_id)===String(event.transaction_id));
  const cls=h.api.networkEdgeClass(event,effect);
  if(event.kind==='selected')assert.equal(cls,'selected-transfer');
  else if(!effect)assert.equal(cls,'observed-only');
  else if(effect.score_support>1e-6){assert.equal(cls,'tested-up');up++;}
  else if(effect.score_support< -1e-6){assert.equal(cls,'tested-down');down++;}
  else assert.equal(cls,'tested-neutral');
 }
 assert.ok(up>0&&down>0);
});

test('the graph legend explains each visual meaning and retains the observed-only disclaimer',()=>{
 const html=harness().api.renderNetwork(fixture('JPMorgan_Chase','180245'));
 for(const text of ['Selected transaction','Earlier observed transfer','Earlier transfer that raised score','Earlier transfer that lowered score','Tested: negligible effect'])assert.ok(html.includes(text));
 assert.match(html,/Connections show recorded activity\. A connection does not by itself mean it influenced the model or indicates fraud\./);
});

test('every cached network has deterministic finite routes and readable identity labels',()=>{
 const h=harness();
 for(const x of cachedReports()){
  const originalStory=JSON.stringify(x.transaction_story);
  const a=h.api.networkLayout(x.transaction_story),b=h.api.networkLayout(clone(x.transaction_story));
  assert.equal(JSON.stringify(x.transaction_story),originalStory);
  assert.equal(a.edges.size,x.transaction_story.transfers.length);
  for(const [id,edge] of a.edges){
   assert.equal(edge.path,b.edges.get(id).path);
   assert.deepEqual(edge.label,b.edges.get(id).label);
   assert.ok([edge.label.x,edge.label.y,edge.label.w,edge.label.h].every(Number.isFinite));
   assert.ok(edge.label.x-edge.label.w/2>=0&&edge.label.x+edge.label.w/2<=a.width);
   assert.ok(edge.label.y-edge.label.h/2>=0&&edge.label.y+edge.label.h/2<=a.height);
   const overlaps=(u,v)=>Math.abs(u.x-v.x)<(u.w+v.w)/2&&Math.abs(u.y-v.y)<(u.h+v.h)/2;
   for(const node of a.positions.values())assert.ok(!overlaps(edge.label,node),`${x.transaction_id}: ${id} label covers an account`);
   for(const [otherId,other] of a.edges)if(id!==otherId)assert.ok(!overlaps(edge.label,other.label),`${x.transaction_id}: ${id} and ${otherId} labels overlap`);
  }
  const html=h.api.flowDiagram(x.transaction_story);
  assert.doesNotMatch(html,/undefined|NaN/);
  for(const t of x.transaction_story.transfers)assert.ok(html.includes(`TX ${t.transaction_id}`));
  for(const account of x.transaction_story.accounts)assert.ok(html.includes(`Account ${account.alias}`));
 }
 const self={transaction_id:'self',source:1,target:1,source_alias:'A',target_alias:'A',source_account_id:'1001',target_account_id:'1001',kind:'selected',timestamp:'2025-08-01 12:00:00',amount:100,currency:'USD',payment_method:'ACH'};
 const story={selected_transfer:self,transfers:[self],accounts:[{alias:'A',account_id:'1001',node_id:1,role:'sender and receiver'}],model_link_effects:[]};
 assert.doesNotMatch(h.api.flowDiagram(story),/undefined|NaN/);
});

test('mobile styles stack the explanation immediately before the network and ahead of the picker',()=>{
 const css=fs.readFileSync(path.join(root,'static/dashboard.css'),'utf8');
 const mobile=css.slice(css.indexOf('@media (max-width: 1000px)'),css.indexOf('@media (max-width: 600px)'));
 assert.match(mobile,/\.investigation-hero\s*\{\s*grid-template-columns:\s*minmax\(0,1fr\)/);
 assert.match(mobile,/\.hero-explanation\s*\{\s*order:\s*-1/);
 assert.match(mobile,/\.layout:has\(\.investigator-summary\) \.detail\s*\{\s*order:\s*-1/);
 const desktop=css.slice(0,css.indexOf('@media'));
 assert.match(desktop,/grid-template-columns:\s*minmax\(0, 1\.35fr\) minmax\(0, 1fr\)/);
});

test('moving the graph into the hero keeps technical and raw disclosures collapsed',()=>{
 const h=harness();h.api.render(fixture('Key_Bank','2974317'));
 const html=h.element('#detail').innerHTML;
 assert.match(html,/<details class="technical-details" id="technical-explanation">/);
 assert.match(html,/<details class="raw-audit"><summary>View raw audit record/);
 assert.doesNotMatch(html,/<details[^>]*\bopen\b/);
 for(const name of ['A. Exact decision','B. Feature attribution','C. Feature faithfulness','D. Historical replay','E. Graph / network details','F. Constrained counterfactuals','G. Verification','H. Model provenance','I. Raw audit record'])assert.ok(html.includes(name));
});

test('network accounts and transfers retain Enter/Space interaction and active inspection state',()=>{
 const item=dataset=>({dataset,handlers:{},attributes:{},addEventListener(type,fn){this.handlers[type]=fn},setAttribute(k,v){this.attributes[k]=v}});
 const x=fixture('JPMorgan_Chase','180245'),event=x.transaction_story.transfers.find(e=>e.transaction_id==='180238');
 const edge=item({edge:event.transaction_id}),account=item({account:x.transaction_story.selected_transfer.source_account_id});
 const h=harness(undefined,[edge,account]);h.api.attachGraphInteractions(x.transaction_story,x.prediction);
 let prevented=false;edge.handlers.keydown({key:'Enter',preventDefault(){prevented=true}});
 assert.equal(prevented,true);assert.equal(edge.attributes['aria-pressed'],'true');
 const html=h.element('#graph-inspector').innerHTML;
 for(const text of ['Transaction 180238','Helped lower the score','Original score:','Without its history update:','Measured difference:'])assert.ok(html.includes(text));
 account.handlers.keydown({key:' ',preventDefault(){}});
 assert.equal(account.attributes['aria-pressed'],'true');assert.equal(edge.attributes['aria-pressed'],'false');
 assert.match(h.element('#graph-inspector').innerHTML,/displayed transfers/);assert.match(h.element('#graph-inspector').innerHTML,/Inspect TX/);
 const svg=h.api.flowDiagram(x.transaction_story);
 assert.equal((svg.match(/tabindex="0" role="button"/g)||[]).length,x.transaction_story.accounts.length+x.transaction_story.transfers.length);
});

// Integration regressions run with the existing required frontend command.
require('./test_operations_frontend.cjs');
