'use strict';
const $=selector=>document.querySelector(selector);
const bank=$('#bank'),view=$('#view'),query=$('#query'),body=$('#rows');
let currentPage=0,total=0,selected=null,requestSequence=0,catalogSequence=0,debounce,currentManifest=null;
const pageSize=75;
const esc=value=>String(value??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const score=value=>Number(value).toFixed(4);
const amount=event=>event.amount==null?'Amount unavailable':`${Number(event.amount).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})} ${esc(event.currency||'')}`;
const time=value=>esc(String(value||'').replace('T',' '));
async function json(url){const r=await fetch(url);const data=await r.json();if(!r.ok)throw Error(data.error||'The server could not complete this request.');return data}

async function loadRows(){
 const sequence=++catalogSequence;
 body.innerHTML='<tr><td colspan="4">Loading transactions…</td></tr>';
 $('#threshold').textContent='Loading configured review threshold…';
 $('#count').textContent='';
 try{
  const params=new URLSearchParams({bank:bank.value,view:view.value,q:query.value,page:String(currentPage),page_size:String(pageSize)});
  const d=await json('/api/catalog?'+params);if(sequence!==catalogSequence)return;total=d.total;
  if(d.bank!==bank.value)throw Error('Transaction catalog does not match the selected bank.');
  $('#threshold').innerHTML=`Configured review threshold: <strong>${score(d.threshold)}</strong>. Selected using validation data; scores at or above it are flagged.`;
  $('#count').textContent=`${total.toLocaleString()} matching transactions · ${d.counts.known_fraud} known fraud · ${d.counts.missed_fraud} missed fraud`;
  body.innerHTML=d.transactions.length?d.transactions.map(x=>`<tr class="case ${selected===x.transaction_id?'selected':''}" data-id="${esc(x.transaction_id)}"><td>${esc(x.transaction_id)}</td><td>${score(x.probability)}</td><td><span class="chip ${x.label_value?'known':''}">${x.label_value?'Fraud':'Not fraud'}</span></td><td><span class="chip ${x.flagged?'alert':''}">${x.flagged?'Flagged':'Not flagged'}</span></td></tr>`).join(''):'<tr><td colspan="4">No transactions match this view.</td></tr>';
  const pages=Math.max(1,Math.ceil(total/pageSize));$('#page').textContent=`${currentPage+1} / ${pages}`;
  $('#prev').disabled=currentPage===0;$('#next').disabled=currentPage+1>=pages;
  body.querySelectorAll('.case').forEach(row=>row.addEventListener('click',()=>loadExplanation(row.dataset.id)));
 }catch(error){if(sequence===catalogSequence)body.innerHTML=`<tr><td colspan="4" class="error">${esc(error.message)}</td></tr>`}
}
async function loadExplanation(id){
 selected=id;const sequence=++requestSequence;
 body.querySelectorAll('.case').forEach(row=>row.classList.toggle('selected',row.dataset.id===id));
 $('#detail').innerHTML=`<p class="loading">Preparing the transfer map and checking the model evidence for ${esc(id)}. The first visit can take a few minutes; verified results are saved for later visits.</p>`;
 try{const params=new URLSearchParams({bank:bank.value,transaction_id:id});const x=await json('/api/explanation?'+params);if(sequence===requestSequence){validateExplanation(x,bank.value,id);history.replaceState(null,'','?'+params);render(x)}}
 catch(error){if(sequence===requestSequence)$('#detail').innerHTML=`<h2>Explanation unavailable</h2><p class="error">${esc(error.message)}</p><p class="muted">The transaction is still listed. A verified model explanation could not be loaded for this request.</p>`}
}

function validateExplanation(x,expectedBank,expectedId){
 const fail=message=>{throw Error('Explanation consistency check failed: '+message)};
 if(x.bank!==expectedBank||String(x.transaction_id)!==String(expectedId))fail('requested transaction identity differs');
 const story=x.transaction_story,event=story?.selected_transfer,prediction=x.prediction,feature=x.feature_explanation;
 const provenance=x.xai_provenance,key=x.cache_key_inputs,verification=x.verification;
 if(!x.model?.checkpoint_sha256||x.model.checkpoint_sha256!==provenance?.checkpoint_sha256||x.model.checkpoint_sha256!==key?.checkpoint_sha256)fail('model fingerprint differs');
 if(currentManifest&&['checkpoint_sha256','preprocessing_sha256','family','seed','model_count','privacy_mode'].some(k=>provenance[k]!==currentManifest[k]))fail('evidence differs from the active model');
 if(key.bank!==expectedBank||String(key.transaction_id)!==String(expectedId)||key.preprocessing_sha256!==provenance.preprocessing_sha256||key.reference_prediction_sha256!==provenance.reference_prediction_sha256?.[expectedBank])fail('cache identity or preprocessing differs');
 if(!event||String(event.transaction_id)!==String(expectedId))fail('graph explains a different transaction');
 if(!prediction||![prediction.probability,prediction.threshold].every(value=>typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=1))fail('invalid score or threshold');
 const savedThreshold=x.xai_provenance?.banks?.[expectedBank]?.threshold;
 if(!Number.isFinite(savedThreshold)||Math.abs(prediction.threshold-savedThreshold)>1e-12)fail('threshold differs from the selected bank’s saved threshold');
 if(!['fraud','not_fraud'].includes(prediction.class)||(prediction.probability>=prediction.threshold)!==(prediction.class==='fraud'))fail('decision differs from score and threshold');
 if(!feature||!Number.isFinite(feature.target_probability)||Math.abs(feature.target_probability-prediction.probability)>1e-6)fail('SHAP targets a different score');
 if(verification?.passed!==true||verification.tolerance!==1e-6||verification.explained_checkpoint_sha256!==x.model.checkpoint_sha256)fail('strict model verification missing or mismatched');
 if(['existing_evaluation_probability','direct_model_probability','xai_probability'].some(k=>!Number.isFinite(verification[k])||Math.abs(verification[k]-prediction.probability)>1e-6))fail('model verification score differs');
 if(key.threshold!==prediction.threshold||x.model.family!==provenance.family||x.model.seed!==provenance.seed||x.model.model_count!==provenance.model_count)fail('model or cutoff provenance differs');
 if(!feature.features?.length||feature.features.some(item=>!Number.isFinite(item.shap_logit)))fail('invalid feature contributions');
 if(![feature.base_logit,feature.target_logit,feature.additivity_residual].every(Number.isFinite))fail('invalid attribution reconstruction');
 if(Math.abs(1/(1+Math.exp(-Math.max(-40,Math.min(40,feature.target_logit))))-prediction.probability)>1e-6)fail('internal explanation output targets a different score');
 const payment=feature.features.find(item=>item.feature==='payment_method');
 if(payment&&String(payment.value).replace(/^payment_format:\s*/,'')!==String(event.payment_method))fail('payment feature differs from selected transfer');
 const terms=feature.features.find(item=>item.feature==='transfer_terms');
 if(terms){const fields=transferFields(terms);if(!Number.isFinite(Number(fields.amount))||!Number.isFinite(Number(event.amount))||Math.abs(Number(fields.amount)-Number(event.amount))>1e-8||fields.currency!==event.currency)fail('amount/currency feature differs from selected transfer')}
 const selectedEvents=(story.transfers||[]).filter(item=>item.kind==='selected');
 if(selectedEvents.length!==1||String(selectedEvents[0].transaction_id)!==String(expectedId))fail('selected graph edge differs');
 for(const key of ['source_account_id','target_account_id','timestamp','amount','currency']){
  if(String(selectedEvents[0][key])!==String(event[key]))fail('selected graph edge details differ');
 }
 if((story.model_link_effects||[]).length&&!Number(story.earlier_related_transfers_considered)&&!(story.transfers||[]).some(item=>item.kind==='earlier'))fail('history effects have no eligible history');
 for(const effect of story.model_link_effects||[]){
  if(!Number.isFinite(effect.original_model_score)||Math.abs(effect.original_model_score-prediction.probability)>1e-6)fail('history effect targets a different score');
  if(!Number.isFinite(effect.model_score_without_event)||!Number.isFinite(effect.score_support)||Math.abs(effect.score_support-(effect.original_model_score-effect.model_score_without_event))>1e-6)fail('history effect arithmetic differs');
 }
 if((story.model_link_effects||[]).length!==ExplanationSummary.verifiedEffects(x).length)fail('history effect lacks verified replay evidence');
}

function observedPatterns(story){return ExplanationSummary.observedPatterns(story)}
function patternLabels(story){
 const patterns=observedPatterns(story);
 return `<div class="observed-patterns"><span class="muted">Observed transaction patterns:</span> ${patterns.length?patterns.map(pattern=>`<span class="pattern-chip" title="${esc(pattern.description)}">${pattern.label}</span>`).join(' '):'<span class="muted">No fan-in, fan-out or cycle found in the displayed transfers.</span>'}<small>Based only on the transfers shown, including the selected transfer. Fan-in/out requires at least 3 distinct counterpart accounts. These labels describe connections, not confirmed fraud or measured score effects.</small></div>`;
}
function flowDiagram(story){
 const measured=new Map((story.model_link_effects||[]).map(effect=>[String(effect.transaction_id),effect]));
 const positions=new Map(),others=[[360,55],[360,305],[215,65],[505,295],[505,65],[215,295]];let connectedIndex=0;
 for(const account of story.accounts){positions.set(account.alias,account.alias==='A'?[125,180]:account.alias==='B'?[595,180]:others[connectedIndex++]||[360,180])}
 const pairs=new Map();
 const paths=story.transfers.map(event=>{
  const [ax,ay]=positions.get(event.source_alias),[bx,by]=positions.get(event.target_alias),current=event.kind==='selected';
  const key=[event.source_alias,event.target_alias].sort().join('-'),index=pairs.get(key)||0;pairs.set(key,index+1);
  const distance=Math.hypot(bx-ax,by-ay)||1,dx=(bx-ax)/distance,dy=(by-ay)/distance;
  const sx=ax+39*dx,sy=ay+39*dy,tx=bx-43*dx,ty=by-43*dy;
  const effect=measured.get(String(event.transaction_id));
  const evidenceClass=current?'selected-transfer':!effect?'observed-only':effect.score_support>1e-6?'tested-up':effect.score_support< -1e-6?'tested-down':'tested-neutral';
  const evidenceText=current?'Transaction being explained':effect?`Tested: score ${score(effect.original_model_score)} → ${score(effect.model_score_without_event)} without this transfer; absolute change ${score(Math.abs(effect.score_support))}`:'Recorded earlier transfer';
  const offset=current?-22:30+index*22,cx=(ax+bx)/2-dy*offset,cy=(ay+by)/2+dx*offset;
  const path=event.source_alias===event.target_alias?`M ${ax-22} ${ay-24} C ${ax-90} ${ay-120}, ${ax+90} ${ay-120}, ${ax+22} ${ay-24}`:`M ${sx} ${sy} Q ${cx} ${cy} ${tx} ${ty}`;
  return `<g class="graph-edge" data-edge="${esc(event.transaction_id)}" tabindex="0" role="button" aria-label="Inspect transaction ${esc(event.transaction_id)}"><path d="${path}" class="flow-hit"/><path d="${path}" class="flow-line ${evidenceClass}" marker-end="url(#${current?'arrow-current':'arrow-earlier'})"><title>Transaction ${esc(event.transaction_id)}: account ${esc(event.source_account_id)} → account ${esc(event.target_account_id)}; ${amount(event)}; ${time(event.timestamp)}; ${esc(evidenceText)}</title></path><text class="flow-transaction ${current?'current':''}" x="${cx}" y="${cy-10}" text-anchor="middle">TX ${esc(event.transaction_id)}${effect?' [tested]':''}</text>${current?`<text class="flow-amount" x="${cx}" y="${cy+10}" text-anchor="middle">${amount(event)}</text>`:''}</g>`;
 }).join('');
 const nodes=story.accounts.map(account=>{const [x,y]=positions.get(account.alias),id=String(account.account_id??account.node_id);return `<g class="graph-account" data-account="${esc(id)}" tabindex="0" role="button" aria-label="Inspect account ${esc(id)}"><circle class="flow-node ${['sender','receiver','sender and receiver'].includes(account.role)?'current':''}" cx="${x}" cy="${y}" r="36"/><text class="flow-label" style="font-size:${id.length>7?11:14}px" x="${x}" y="${y+5}" text-anchor="middle">${esc(id)}</text><text class="flow-role" x="${x}" y="${y+55}" text-anchor="middle">${esc(account.role)}</text><title>Dataset account ID ${esc(id)}; model node ${esc(account.node_id)}</title></g>`}).join('');
 return `<figure class="flow-card"><svg viewBox="0 0 720 365" role="group" aria-label="Observed transfers labeled with actual transaction and dataset account IDs"><defs><marker id="arrow-current" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#f3c477"/></marker><marker id="arrow-earlier" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="#8aaed1"/></marker></defs>${paths}${nodes}</svg></figure>`;
}

function transferFields(feature){return Object.fromEntries(String(feature.value).split(' / ').map(part=>{const i=part.indexOf(': ');return [part.slice(0,i),part.slice(i+2)]}))}
function observedFeature(feature){
 if(feature.feature!=='transfer_terms')return esc(feature.feature==='payment_method'?String(feature.value).replace(/^payment_format:\s*/,''):feature.value);
 const fields=transferFields(feature);
 const sent=amount({amount:fields.amount,currency:fields.currency});
 const received=amount({amount:fields.Amount_Received,currency:fields.Receiving_Currency});
 return sent===received?sent:`Sent ${sent}; received ${received}`;
}
function displayScore(value){return value!==0&&Math.abs(value)<.0001?Number(value).toExponential(3):Number(value).toFixed(4)}
function exact(value){return value==null?'Not recorded':esc(String(value))}
function renderSimpleExplanation(x,s){
 const d=s.decision,h=s.history_summary,cf=s.counterfactual_summary,event=x.transaction_story.selected_transfer;
 const margin=d.margin===0?'At the review cutoff':`${displayScore(Math.abs(d.margin))} ${d.margin>0?'above':'below'} the review cutoff`;
 const factorCards=s.top_factors.map(f=>`<li class="factor-card"><div class="factor-heading"><strong>${f.direction==='up'?'↑':f.direction==='down'?'↓':'•'} ${esc(f.label)}</strong><span class="chip ${f.direction==='up'?'alert':f.direction==='down'?'known':''}">${esc(f.effect)}</span></div><p class="factor-value"><span class="observed-label">Observed:</span> ${esc(f.observed)}</p><div class="factor-track" aria-hidden="true"><span class="factor-bar ${f.direction==='down'?'lower':''}" style="width:${100*f.relative_size}%"></span></div></li>`).join('');
 const history=h.strongest?`<div class="score-comparison"><div><span>With this history</span><strong>${displayScore(h.strongest.original_model_score)}</strong></div><span class="comparison-arrow" aria-hidden="true">→</span><div><span>Without this history update</span><strong>${displayScore(h.strongest.model_score_without_event)}</strong></div></div><p class="muted">${h.tested_count} earlier transfer${h.tested_count===1?' has':'s have'} a verified score test. The strongest effect is shown.</p>`:'';
 const c=cf.alternative;
 const alternative=c?`<div class="score-comparison"><div><span>Current amount / score / decision</span><strong>${amount(event)}</strong><p>${displayScore(d.score)} · ${d.flagged?'Flagged':'Not flagged'}</p></div><span class="comparison-arrow" aria-hidden="true">→</span><div><span>Tested alternative / score / decision</span><strong>${amount({amount:c.changed_features.amount??c.changed_features.Amount_Received,currency:event.currency})}</strong><p>${displayScore(c.counterfactual_probability)} · ${c.counterfactual_probability>=d.threshold?'Flagged':'Not flagged'}</p></div></div>`:'';
 return `<div class="investigator-summary" data-view="simple">
 <div class="decision-banner ${d.flagged?'flagged':'not-flagged'}"><div><p class="eyebrow">MODEL DECISION</p><h3>${d.flagged?'Flagged for review':'Not flagged'}</h3><p>Score ${displayScore(d.score)} — ${margin.toLowerCase()}${d.margin===0?'':` of ${displayScore(d.threshold)}`}</p></div><span class="model-scope">${esc(s.model_scope)}</span></div>
 <div class="facts"><div class="fact"><span>MODEL SCORE</span><strong>${displayScore(d.score)}</strong></div><div class="fact"><span>BANK REVIEW CUTOFF</span><strong>${displayScore(d.threshold)}</strong></div><div class="fact"><span>MARGIN ${d.margin>=0?'ABOVE':'BELOW'} CUTOFF</span><strong>${d.margin>0?'+':d.margin<0?'−':''}${displayScore(Math.abs(d.margin))}</strong></div></div>
 <section aria-labelledby="decision-question"><h3 id="decision-question">${d.flagged?'Why was this flagged?':'Why was this not flagged?'}</h3><div class="reason"><span class="eyebrow">MAIN REASON</span><p class="primary-reason">${esc(s.primary_reason.sentence)}</p></div><div class="quick-context"><p><strong>Earlier activity</strong><br>${esc(h.sentence)}</p><p><strong>Account activity</strong><br>${s.patterns.length?s.patterns.map(p=>esc(p.label)).join(' · ')+' observed in the displayed transfers. Score effects of these patterns were not measured.':'No fan-in, fan-out or cycle in the displayed transfers.'}</p></div></section>
 <section class="section" aria-labelledby="feature-question"><h3 id="feature-question">Top factors</h3><ol class="factor-list">${factorCards}</ol><p class="muted relative-help" title="Strong: at least 67% of the largest absolute contribution; Moderate: at least 33%; Small: smaller non-negligible contributions.">Compared with training examples, with earlier account activity held fixed. Strength and bar lengths are relative to this explanation’s largest measured feature effect; they are visual comparisons, not probabilities.</p></section>
 <section class="section" aria-labelledby="history-question"><h3 id="history-question">Earlier activity</h3><p>${esc(h.sentence)}</p>${history}${h.tested_count?'<button type="button" id="see-history" class="text-button">See all tested earlier transfers</button>':''}</section>
 <section class="section" aria-labelledby="patterns-question"><h3 id="patterns-question">Account activity patterns</h3>${s.patterns.length?s.patterns.map(p=>`<p><strong>${esc(p.label)}</strong><br>${esc(p.description)}</p>`).join(''):'<p>No fan-in, fan-out or chronological cycle found in the displayed transfers.</p>'}<p class="muted">These describe observed account relationships. They do not prove fraud and do not automatically mean they affected the model score.</p></section>
 <section class="section"><h3>What would have changed the result?</h3><p>${esc(cf.sentence)}</p>${alternative}<p class="muted">${cf.note}</p></section>
 <p class="label-comparison">Dataset label: <strong>${s.evaluation.label}</strong> · ${s.evaluation.status}. Dataset labels are evaluation evidence, separate from the model decision.</p>
 <p class="muted">The score is not a calibrated probability of fraud. This explanation describes measured model behavior.</p></div>`;
}
function renderNetwork(x){
 const story=x.transaction_story,earlier=story.transfers.filter(t=>t.kind==='earlier');
 return `<details class="network-details"><summary>View transaction network</summary>${patternLabels(story)}<div class="graph-legend"><span class="legend-selected">Selected transfer</span><span class="legend-context">Earlier observed transfer</span><span class="legend-up">Verified test: raised score</span><span class="legend-down">Verified test: lowered score</span><span class="legend-neutral">Verified test: negligible effect</span></div><div class="graph-layout">${flowDiagram(story)}<aside id="graph-inspector" class="graph-inspector" aria-live="polite"><h4>Select an account or transfer</h4><p>View its details and any tested effect on the score.</p></aside></div>${earlier.length?`<details class="recorded-history"><summary>View earlier transaction history</summary>${historyTable(earlier,story.model_link_effects||[])}</details>`:''}</details>`;
}
function historyTable(events,effects){
 if(!events.length)return '<p>No earlier eligible transfers are recorded in this scope.</p>';
 return `<div class="table-scroll"><table class="technical-table flow-table"><thead><tr><th>Transfer / accounts / model nodes</th><th>Time / observed amount / method</th><th>Verified replay: with / without / delta</th></tr></thead><tbody>${events.map(t=>{
 const e=effects.find(e=>String(e.transaction_id)===String(t.transaction_id));
 return `<tr><td>TX ${esc(t.transaction_id)}<br>${esc(t.source_account_id??t.source)} → ${esc(t.target_account_id??t.target)}<br>Nodes ${esc(t.source)} → ${esc(t.target)}</td><td>${time(t.timestamp)}<br>${amount(t)}<br>${esc(t.payment_method)}</td><td>${e?`${exact(e.original_model_score)} / ${exact(e.model_score_without_event)}<br>Support: ${exact(e.score_support)}<br>${esc(e.scope)}`:'Observed; effect not measured'}</td></tr>`;
 }).join('')}</tbody></table></div>`;
}
// Structured, full-precision evidence without dumping JSON into the technical view.
function evidence(value){
 if(value==null)return '<p>Not recorded for this transaction. This does not mean the check passed.</p>';
 if(typeof value!=='object')return exact(value);
 const entries=Array.isArray(value)?value.map((v,i)=>[i+1,v]):Object.entries(value);
 if(!entries.length)return '<p>No entries recorded.</p>';
 return `<dl class="evidence-values">${entries.map(([k,v])=>`<div><dt>${esc(String(k).replaceAll('_',' '))}</dt><dd>${v!==null&&typeof v==='object'?evidence(v):exact(v)}</dd></div>`).join('')}</dl>`;
}
function readableTechnicalDetails(x){
 const f=x.feature_explanation,story=x.transaction_story,p=x.prediction,v=x.verification||{},provenance=x.xai_provenance||{};
 const allHistory=story.eligible_earlier_transfers||story.transfers.filter(t=>t.kind==='earlier');
 const effects=ExplanationSummary.verifiedEffects(x),cf=x.counterfactual_explanation||{};
 const tested=cf.tested_alternatives||cf.counterfactuals||[];
 const reconstructed=f.base_logit+f.features.reduce((sum,g)=>sum+g.shap_logit,0);
 const reconstructedScore=1/(1+Math.exp(-Math.max(-40,Math.min(40,reconstructed))));
 const rows=f.features.map(g=>`<tr><td>${esc(g.label||g.feature)}<br>Observed: ${observedFeature(g)}<br>Columns: ${esc((g.columns||[]).join(', '))}</td><td>${exact(g.shap_logit)}</td><td>${exact(g.ablation_logit_drop)}</td></tr>`).join('');
 const equation=`Base logit ${f.base_logit}\n+ grouped SHAP contributions (${f.features.map(g=>g.shap_logit).join(' + ')})\n= reconstructed logit ${reconstructed}\nTarget logit: ${f.target_logit}\nAdditivity residual: ${f.additivity_residual}\nsigmoid(reconstructed logit) = ${reconstructedScore}\nExplanation target score: ${f.target_probability}`;
 return `<details class="technical-details" id="technical-explanation"><summary>View in-depth explanation</summary>
 <h3>A. Exact decision</h3><p>Full-precision model score: <strong>${exact(p.probability)}</strong><br>Bank-specific threshold: <strong>${exact(p.threshold)}</strong><br>Exact margin: <strong>${exact(p.probability-p.threshold)}</strong><br>Model decision: ${p.probability>=p.threshold?'Flagged for review':'Not flagged'} (${esc(p.class)})<br>Evaluation label: ${esc(x.evaluation_label)}</p><p>Saved threshold source: ${esc(p.threshold_selection||provenance.threshold_policy||'Not recorded')}</p>
 <h3>B. Feature attribution</h3><p>Grouped empirical/interventional SHAP averages contributions across feature combinations using ${esc(f.background_size)} training comparison examples. Earlier account memory and target account metadata stay fixed. Amount sent, amount received and both currencies form a joint group; they cannot be assigned separate effects.</p><p>Method: ${esc(f.method)} · scope: ${esc(f.scope)} · units: ${esc(f.units)}</p><div class="table-scroll"><table class="technical-table"><thead><tr><th>Every feature group / observed value</th><th>Exact SHAP (logit)</th><th>One-group perturbation (logit drop)</th></tr></thead><tbody>${rows}</tbody></table></div><pre class="score-equation">${esc(equation)}</pre><details><summary>Comparison background and feature grouping</summary>${evidence({seed:f.seed,background_transaction_ids:f.background_txn_ids,groups:f.groups,limitations:f.limitations})}</details>
 <h3>C. Feature faithfulness</h3><p>SHAP is an average contribution over feature combinations. A one-group perturbation changes that group alone while holding other observed groups fixed. Differences do not by themselves invalidate either method.</p>${evidence(x.evaluation_checks?.faithfulness)}${evidence(x.evaluation?.feature_fidelity)}
 <h3 id="technical-history">D. Historical replay</h3><p>This is a model replay/intervention test, not GNNExplainer and not proof of transaction purpose or fraud. Each verified test suppresses one earlier history update and retains pre-window account memory.</p><p>${esc(story.history_scope)}</p><p>${effects.length} verified earlier-transfer test(s); ${esc(story.earlier_related_transfers_considered)} eligible earlier transfers considered. ${story.eligible_earlier_transfers?'Every eligible transfer in that bounded scope is listed below.':'This older report retained only the displayed earlier transfers; the remaining eligible records were not saved.'}</p>${historyTable(allHistory,effects)}${evidence({window_batches:x.graph_explanation?.window_batches,window_event_count:x.graph_explanation?.window_event_count,selection:x.graph_explanation?.selection,fidelity:x.graph_explanation?.fidelity,temporal_evidence:x.temporal_explanation})}
 <h3>E. Graph / network details</h3><p>Account IDs identify dataset accounts; model node IDs identify internal nodes. Patterns describe observed relationships and do not establish a measured model effect.</p>${historyTable([story.selected_transfer,...allHistory],effects)}${evidence(story.accounts)}${evidence(observedPatterns(story))}${evidence({important_nodes:x.graph_explanation?.important_nodes,important_edges:x.graph_explanation?.important_edges,limitations:x.graph_explanation?.limitations})}
 <h3>F. Constrained counterfactuals</h3><p>All retained tested amount alternatives and exact scores follow. This is a model-sensitivity test, not a recommendation for transaction behavior. Account memory and event history stay fixed.</p>${!cf.tested_alternatives?'<p>Legacy report: only threshold-crossing alternatives were retained. Other tested candidate values were not saved.</p>':''}${evidence({method:cf.method,status:cf.status,threshold:cf.threshold,candidates_evaluated:cf.candidates_evaluated,tested_alternatives:tested,limitations:cf.limitations})}
 <h3>G. Verification</h3><p>Strict XAI parity guard: 1e-6. Saved, direct and explanation scores must agree within this tolerance. Missing checks are not passes. Reference stability, feature faithfulness and numerical agreement answer different questions.</p>${evidence(v)}${evidence({grouped_explanation_target_score:f.target_probability,saved_catalog_score:p.probability,stability:x.evaluation_checks?.stability,temporal_replay:x.evaluation_checks?.temporal_replay,coverage:x.evaluation_checks?.coverage,engine_evaluation:x.evaluation,configuration:x.config})}
 <h3>H. Model provenance</h3><p>${esc(ExplanationSummary.modelScope(x))}. Local explanations do not inherit a model’s DP guarantee. The selected catalog supports only the model identified here.</p>${evidence({model:x.model,source:provenance,engine_provenance:x.provenance,limitations:x.limitations})}
 <h3>I. Raw audit record</h3><details class="raw-audit"><summary>View raw audit record</summary><pre>${esc(JSON.stringify(x,null,2))}</pre></details></details>`;
}
function render(x){
 const s=ExplanationSummary.summarize(x),event=x.transaction_story.selected_transfer;
 $('#detail').innerHTML=`<div class="transaction-heading"><div><p class="eyebrow bank">${esc(x.bank.replaceAll('_',' '))}</p><h2>Transaction ${esc(x.transaction_id)}</h2></div><a class="picker-link" href="#bank">Find another transaction</a><a class="depth-link" href="#technical-explanation" id="open-technical">In-depth explanation ↗</a></div><p class="intro">Account ${esc(event.source_account_id)} sent ${amount(event)} to account ${esc(event.target_account_id)} using ${esc(event.payment_method)}.</p>${renderSimpleExplanation(x,s)}${renderNetwork(x)}${readableTechnicalDetails(x)}`;
 attachGraphInteractions(x.transaction_story,x.prediction);
 if(typeof matchMedia==='function'&&matchMedia('(max-width:1000px)').matches)$('#detail').scrollIntoView({block:'start'});
 const open=()=>{$('#technical-explanation').open=true};
 $('#open-technical').addEventListener('click',open);
 $('#see-history')?.addEventListener('click',()=>{open();$('#technical-history').scrollIntoView({behavior:'smooth',block:'start'})});
}
function graphEdgeDetails(event,effect,prediction){
 const tested=event.kind==='earlier'&&effect;
 const status=tested?(effect.score_support>1e-6?'Helped raise the score':effect.score_support< -1e-6?'Helped lower the score':'Tested change was too small to measure clearly'):'';
 const scoreLabel=event.kind==='selected'?'Model score':'Selected transaction’s model score';
 return `<h4>Transaction ${esc(event.transaction_id)}</h4><p>Account ${esc(event.source_account_id)} → ${esc(event.target_account_id)}</p><p>${time(event.timestamp)}<br>${amount(event)}<br>${esc(event.payment_method)}</p>${status?`<p><strong>${status}</strong></p>`:''}<p>${scoreLabel}: ${score(prediction.probability)}</p>${tested?`<p>Without its history update: ${score(effect.model_score_without_event)}</p><p class="muted">Earlier account memory is retained. Full replay scope and exact scores are in the in-depth explanation.</p>`:''}`;
}
function attachGraphInteractions(story,prediction){
 const panel=$('#graph-inspector');
 const effects=new Map((story.model_link_effects||[]).map(effect=>[String(effect.transaction_id),effect]));
 const earlier=story.transfers.filter(event=>event.kind==='earlier');
 const verified=earlier.filter(event=>effects.has(String(event.transaction_id))).length;
 function inspectEdge(id){
  const event=story.transfers.find(event=>String(event.transaction_id)===String(id));
  if(!event)return;
  const effect=effects.get(String(id));
  panel.innerHTML=graphEdgeDetails(event,effect,prediction);
 }
 function inspectAccount(id){
  const account=story.accounts.find(account=>String(account.account_id)===String(id));
  const related=story.transfers.filter(event=>String(event.source_account_id)===String(id)||String(event.target_account_id)===String(id));
  panel.innerHTML=`<h4>Account ${esc(id)}</h4><p>${esc(account?.role)} · ${related.length} displayed transfers</p><p>Connections describe recorded activity; they do not identify account ownership, payment purpose, or fraud.</p>${related.map(event=>`<button class="inspect-transfer" data-inspect-edge="${esc(event.transaction_id)}">Inspect TX ${esc(event.transaction_id)}</button>`).join('')}`;
  panel.querySelectorAll('[data-inspect-edge]').forEach(button=>button.addEventListener('click',()=>inspectEdge(button.dataset.inspectEdge)));
 }
 document.querySelectorAll('[data-edge],[data-account]').forEach(element=>{
  const activate=()=>element.dataset.edge?inspectEdge(element.dataset.edge):inspectAccount(element.dataset.account);
  element.addEventListener('click',activate);
  element.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();activate()}});
 });
}
function reset(){currentPage=0;loadRows()}
bank.addEventListener('change',()=>{requestSequence++;selected=null;query.value='';history.replaceState(null,'','?bank='+encodeURIComponent(bank.value));$('#detail').innerHTML='<div class="empty"><h2>Select a transaction from this bank</h2></div>';reset()});view.addEventListener('change',reset);
query.addEventListener('input',()=>{clearTimeout(debounce);debounce=setTimeout(reset,220)});
$('#prev').addEventListener('click',()=>{if(currentPage){currentPage--;loadRows()}});
$('#next').addEventListener('click',()=>{if((currentPage+1)*pageSize<total){currentPage++;loadRows()}});
async function init(){try{const data=await json('/api/meta');currentManifest=data.manifest;bank.innerHTML=data.banks.map(value=>`<option value="${esc(value)}">${esc(value.replaceAll('_',' '))}</option>`).join('');const params=new URLSearchParams(location.search);if(params.has('bank')&&!data.banks.includes(params.get('bank')))throw Error('Unknown bank in transaction link.');if(data.banks.includes(params.get('bank')))bank.value=params.get('bank');const id=params.get('transaction_id');if(id){query.value=id;view.value='all'}await loadRows();if(id)await loadExplanation(id)}catch(error){$('#detail').innerHTML=`<p class="error">${esc(error.message)}</p>`}}
init();
