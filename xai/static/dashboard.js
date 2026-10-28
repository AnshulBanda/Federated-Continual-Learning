(function(global){
'use strict';
function create(options={}){
const document=options.document||global.document,scope=options.scope||document;
const $=selector=>selector==='#detail'&&options.detail?options.detail:scope.querySelector(selector);
const all=selector=>scope.querySelectorAll(selector);
const bank=$('#bank'),view=$('#view'),query=$('#query'),body=$('#rows');
let currentPage=0,total=0,selected=null,requestSequence=0,catalogSequence=0,debounce,currentManifest=null;
const pageSize=75;
const escapeHTML=value=>String(value??'—').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const esc=value=>escapeHTML(BankDisplay.text(value??'—'));
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
// Geometry is presentation-only. Event selection and measured effects are unchanged.
function networkLayout(story){
 const width=740,height=560,positions=new Map(),selected=story.selected_transfer;
 const source=selected.source_alias,target=selected.target_alias;
 for(const account of story.accounts){
  const current=account.alias===source||account.alias===target;
  if(current)positions.set(account.alias,{x:source===target?370:account.alias===source?145:595,y:280,w:158,h:90});
 }
 const slots=[{x:135,y:86},{x:370,y:86},{x:605,y:86},{x:135,y:474},{x:370,y:474},{x:605,y:474}];
 for(const account of story.accounts.filter(a=>!positions.has(a.alias))){
  const peers=story.transfers.filter(e=>e.source_alias===account.alias||e.target_alias===account.alias)
   .map(e=>e.source_alias===account.alias?e.target_alias:e.source_alias);
  const preferred=peers.includes(source)&&peers.includes(target)?370:peers.includes(source)?135:peers.includes(target)?605:370;
  slots.sort((a,b)=>Math.abs(a.x-preferred)-Math.abs(b.x-preferred)||a.y-b.y||a.x-b.x);
  positions.set(account.alias,{...slots.shift(),w:142,h:80});
 }
 const overlaps=(a,b,gap=8)=>a.x-a.w/2<b.x+b.w/2+gap&&a.x+a.w/2>b.x-b.w/2-gap&&a.y-a.h/2<b.y+b.h/2+gap&&a.y+a.h/2>b.y-b.h/2-gap;
 const inside=(p,box,gap=0)=>Math.abs(p.x-box.x)<box.w/2+gap&&Math.abs(p.y-box.y)<box.h/2+gap;
 const clip=(node,toward,pad)=>{
  const dx=toward.x-node.x,dy=toward.y-node.y;
  const scale=Math.min((node.w/2+pad)/(Math.abs(dx)||.001),(node.h/2+pad)/(Math.abs(dy)||.001));
  return {x:node.x+dx*scale,y:node.y+dy*scale};
 };
 const nodeBoxes=[...positions.values()],options=new Map();
 // Reserve the selected badge first. Historical routing then avoids that focal point.
 const importance=event=>Math.abs((story.model_link_effects||[]).find(e=>String(e.transaction_id)===String(event.transaction_id))?.score_support||0);
 const ordered=[...story.transfers].sort((a,b)=>(b.kind==='selected')-(a.kind==='selected')||importance(b)-importance(a));
 for(const event of ordered){
  const a=positions.get(event.source_alias),b=positions.get(event.target_alias),current=event.kind==='selected';
  const effect=(story.model_link_effects||[]).find(e=>String(e.transaction_id)===String(event.transaction_id));
  const primary=`${!current&&effect?(effect.score_support>1e-6?'↑ ':effect.score_support< -1e-6?'↓ ':'• '):''}TX ${event.transaction_id}`;
  const secondary=current?amount(event):'';
  const box={w:Math.max(current?140:112,primary.length*(current?8:7.5)+24,secondary.length*7.2+20),h:current?49:26};
  const offsets=current?[-60,60,-120,120,0,-200,200]:[0,80,-80,160,-160,240,-240,320,-320];
  const choices=[];
  for(const offset of offsets){
   let start,end,control,path,point;
   if(event.source_alias===event.target_alias){
    const direction=offset>0?1:-1,reach=130+Math.abs(offset)/2;
    start={x:a.x-a.w*.35,y:a.y+direction*(a.h/2+4)};
    end={x:a.x+a.w*.35,y:start.y};
    const c1={x:a.x-reach,y:a.y+direction*reach},c2={x:a.x+reach,y:c1.y};
    point=t=>({x:(1-t)**3*start.x+3*(1-t)**2*t*c1.x+3*(1-t)*t*t*c2.x+t**3*end.x,
     y:(1-t)**3*start.y+3*(1-t)**2*t*c1.y+3*(1-t)*t*t*c2.y+t**3*end.y});
    path=`M ${start.x} ${start.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${end.x} ${end.y}`;
   }else{
    // Use a canonical normal so opposite-direction transfers separate consistently.
    const first=event.source_alias<event.target_alias?a:b,last=first===a?b:a;
    const dx=last.x-first.x,dy=last.y-first.y,distance=Math.hypot(dx,dy)||1;
    control={x:(a.x+b.x)/2-dy/distance*offset,y:(a.y+b.y)/2+dx/distance*offset};
    start=clip(a,control,5);end=clip(b,control,9);
    point=t=>({x:(1-t)**2*start.x+2*(1-t)*t*control.x+t*t*end.x,y:(1-t)**2*start.y+2*(1-t)*t*control.y+t*t*end.y});
    path=`M ${start.x} ${start.y} Q ${control.x} ${control.y}, ${end.x} ${end.y}`;
   }
   const samples=Array.from({length:19},(_,i)=>point((i+1)/20));
   for(const t of [.5,.35,.65,.2,.8])for(const [shiftX,shiftY] of (current?[[0,0]]:[[0,0],[0,-36],[0,36],[-28,-28],[28,28]])){
    const anchor=point(t),candidate={...box,x:anchor.x+shiftX,y:anchor.y+shiftY};
    let cost=Math.abs(offset)*.012+Math.abs(t-.5)*12+Math.hypot(shiftX,shiftY)*.08;
    const nodeHits=nodeBoxes.filter(n=>overlaps(candidate,n,8)).length;
    const boundsClear=!(candidate.x-box.w/2<12||candidate.x+box.w/2>width-12||candidate.y-box.h/2<12||candidate.y+box.h/2>height-12);
    cost+=nodeHits*50000+(boundsClear?0:20000);
    const baseCost=cost+samples.filter(p=>nodeBoxes.some(n=>n!==a&&n!==b&&inside(p,n,7))).length*100+samples.filter(p=>p.x<8||p.x>width-8||p.y<8||p.y>height-8).length*1000;
    choices.push({path,label:candidate,anchor,samples,baseCost,clear:nodeHits===0&&boundsClear,primary,secondary});
   }
  }
  const free=choices.filter(c=>c.clear);
  options.set(String(event.transaction_id),(free.length?free:choices).sort((a,b)=>a.baseCost-b.baseCost));
 }
 // Keep a bounded set of whole-layout alternatives so an early badge cannot
 // consume the only clear space needed by a later parallel transfer.
 let beam=[{cost:0,placed:[]}];
 for(const event of ordered){
  const id=String(event.transaction_id),unique=new Map();
  for(const option of options.get(id)){
   const key=[option.label.x.toFixed(0),option.label.y.toFixed(0)].join(',');
   if(!unique.has(key))unique.set(key,option);
  }
  const choices=[...unique.values()].slice(0,event.kind==='selected'?1:64),next=[];
  for(const state of beam)for(const candidate of choices){
   let cost=state.cost+candidate.baseCost;
   for(const [,previous] of state.placed){
    if(overlaps(candidate.label,previous.label,6))cost+=10000;
    for(const p of candidate.samples)if(inside(p,previous.label,3))cost+=20;
    for(const p of previous.samples)if(inside(p,candidate.label,3))cost+=20;
   }
   next.push({cost,placed:[...state.placed,[id,candidate]]});
  }
  next.sort((a,b)=>a.cost-b.cost);beam=next.slice(0,16);
 }
 return {width,height,positions,edges:new Map(beam[0].placed)};
}
function networkEdgeClass(event,effect){
 return event.kind==='selected'?'selected-transfer':!effect?'observed-only':effect.score_support>1e-6?'tested-up':effect.score_support< -1e-6?'tested-down':'tested-neutral';
}
function flowDiagram(story){
 const measured=new Map((story.model_link_effects||[]).map(e=>[String(e.transaction_id),e]));
 const layout=networkLayout(story);
 const paths=[...story.transfers].sort((a,b)=>(a.kind==='selected')-(b.kind==='selected')).map(event=>{
  const route=layout.edges.get(String(event.transaction_id)),label=route.label,current=event.kind==='selected';
  const effect=measured.get(String(event.transaction_id)),evidenceClass=networkEdgeClass(event,effect);
  const marker=current?'selected':!effect?'observed':effect.score_support>1e-6?'up':effect.score_support< -1e-6?'down':'neutral';
  const evidenceText=current?'Selected transaction':effect?`Verified replay: original score ${score(effect.original_model_score)}, without this history update ${score(effect.model_score_without_event)}; measured support ${effect.score_support}`:'Earlier observed transfer; effect not measured';
  return `<g class="graph-edge ${evidenceClass}" data-edge="${esc(event.transaction_id)}" tabindex="0" role="button" aria-pressed="false" aria-label="Inspect transaction ${esc(event.transaction_id)}"><title>TX ${esc(event.transaction_id)}: account ${esc(event.source_account_id)} → ${esc(event.target_account_id)}; ${time(event.timestamp)}; ${amount(event)}; ${esc(event.payment_method)}; ${esc(evidenceText)}</title><path d="${route.path}" class="flow-hit"/><path d="${route.path}" class="flow-halo"/><path d="${route.path}" class="flow-line ${evidenceClass}" marker-end="url(#arrow-${marker})"/>${Math.hypot(route.anchor.x-label.x,route.anchor.y-label.y)>0?`<line class="badge-leader" x1="${route.anchor.x}" y1="${route.anchor.y}" x2="${label.x}" y2="${label.y}"/>`:''}<g class="edge-badge ${evidenceClass}" transform="translate(${label.x-label.w/2},${label.y-label.h/2})"><rect width="${label.w}" height="${label.h}" rx="${current?9:13}"/><text class="flow-transaction" x="${label.w/2}" y="${current?20:17}" text-anchor="middle">${esc(route.primary)}</text>${current?`<text class="flow-amount" x="${label.w/2}" y="38" text-anchor="middle">${route.secondary}</text>`:''}</g></g>`;
 }).join('');
 const nodes=story.accounts.map(account=>{
  const n=layout.positions.get(account.alias),id=String(account.account_id??account.node_id);
  const current=['sender','receiver','sender and receiver'].includes(account.role);
  return `<g class="graph-account" data-account="${esc(id)}" tabindex="0" role="button" aria-pressed="false" aria-label="Inspect account ${esc(id)}"><title>Account ${esc(account.alias)}: dataset ID ${esc(id)}; model node ${esc(account.node_id)}; ${esc(account.role)}</title><rect class="flow-node ${current?'current':''}" x="${n.x-n.w/2}" y="${n.y-n.h/2}" width="${n.w}" height="${n.h}" rx="14"/><text class="account-alias" x="${n.x}" y="${n.y-18}" text-anchor="middle">Account ${esc(account.alias)}</text><text class="flow-label ${current?'current':''}" x="${n.x}" y="${n.y+6}" text-anchor="middle">${esc(id)}</text><text class="flow-role" x="${n.x}" y="${n.y+26}" text-anchor="middle">${esc(account.role)}</text></g>`;
 }).join('');
 const markers=[['selected','#14785f'],['observed','#a9b8bf'],['up','#b57728'],['down','#27846c'],['neutral','#819197']]
  .map(([name,color])=>`<marker id="arrow-${name}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="${name==='selected'?12:9}" markerHeight="${name==='selected'?12:9}" markerUnits="userSpaceOnUse" orient="auto"><path d="M 0 0 L 10 5 L 0 10 z" fill="${color}"/></marker>`).join('');
 return `<figure class="flow-card"><svg viewBox="0 0 ${layout.width} ${layout.height}" role="group" aria-label="Observed transfers labeled with actual transaction and dataset account IDs"><defs>${markers}</defs>${paths}${nodes}</svg><figcaption>Select any account or transfer. Use Enter or Space on a focused item.</figcaption></figure>`;
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
function renderHeroExplanation(s){
 const d=s.decision,h=s.history_summary;
 const margin=d.margin===0?'At the review cutoff':`${d.margin>0?'+':'−'}${displayScore(Math.abs(d.margin))} ${d.margin>0?'above':'below'} cutoff`;
 const factors=s.top_factors.map(f=>`<li class="factor-card"><div class="factor-heading"><strong><span class="direction ${f.direction}" aria-hidden="true">${f.direction==='up'?'↑':f.direction==='down'?'↓':'•'}</span> ${esc(f.label)}</strong><span class="factor-effect ${f.direction}">${esc(f.effect)}</span></div><p class="factor-value"><span class="observed-label">Observed:</span> ${esc(f.observed)}</p><div class="factor-track" aria-hidden="true"><span class="factor-bar ${f.direction==='down'?'lower':''}" style="width:${100*f.relative_size}%"></span></div></li>`).join('');
 return `<section class="hero-explanation" aria-labelledby="decision-question"><p class="eyebrow">Model explanation</p><h3 id="decision-question">${d.flagged?'Why was this flagged?':'Why was this not flagged?'}</h3>
 <div class="decision-banner"><span class="status ${d.flagged?'review-status':''}">${d.flagged?'Flagged for review':'Not flagged'}</span><p class="decision-score">Score <strong>${displayScore(d.score)}</strong> <span aria-hidden="true">·</span> Review cutoff <strong>${displayScore(d.threshold)}</strong></p><p class="decision-margin">${margin}</p></div>
 <div class="reason"><h4>MAIN REASON</h4><p class="primary-reason">${esc(s.primary_reason.sentence)}</p></div>
 <div class="top-factors"><h4>Top factors</h4><ol class="factor-list">${factors}</ol><p class="relative-help" title="Strong: at least 67% of the largest absolute contribution; Moderate: at least 33%; Small: smaller non-negligible contributions. Compared with training examples, holding earlier account activity fixed.">Strength is relative to this explanation’s largest feature effect, not a probability.</p></div>
 <div class="hero-history"><h4>Earlier activity</h4><p>${esc(h.sentence)}</p></div><p class="model-scope">${esc(s.model_scope)}</p></section>`;
}
function renderFollowupExplanation(x,s){
 const d=s.decision,h=s.history_summary,cf=s.counterfactual_summary,story=x.transaction_story,event=story.selected_transfer;
 const earlier=story.transfers.filter(t=>t.kind==='earlier');
 const history=h.strongest?`<div class="score-comparison"><div><span>With this history</span><strong>${displayScore(h.strongest.original_model_score)}</strong></div><span class="comparison-arrow" aria-hidden="true">→</span><div><span>Without this history update</span><strong>${displayScore(h.strongest.model_score_without_event)}</strong></div></div><p class="muted">${h.tested_count} earlier transfer${h.tested_count===1?' has':'s have'} a verified score test. The strongest effect is shown.</p>`:'';
 const c=cf.alternative;
 const alternative=c?`<div class="score-comparison"><div><span>Current amount / score / decision</span><strong>${amount(event)}</strong><p>${displayScore(d.score)} · ${d.flagged?'Flagged':'Not flagged'}</p></div><span class="comparison-arrow" aria-hidden="true">→</span><div><span>Tested alternative / score / decision</span><strong>${amount({amount:c.changed_features.amount??c.changed_features.Amount_Received,currency:event.currency})}</strong><p>${displayScore(c.counterfactual_probability)} · ${c.counterfactual_probability>=d.threshold?'Flagged':'Not flagged'}</p></div></div>`:'';
 return `<div class="followup-explanation"><section class="section" aria-labelledby="history-question"><p class="eyebrow">Earlier activity</p><h3 id="history-question">Tested account history</h3><p>${esc(h.sentence)}</p>${history}${h.tested_count?'<button type="button" id="see-history" class="secondary">See all tested earlier transfers</button>':''}${earlier.length?`<details class="recorded-history"><summary>View earlier transaction history</summary>${historyTable(earlier,story.model_link_effects||[])}</details>`:''}</section>
 <section class="section" aria-labelledby="patterns-question"><p class="eyebrow">Observed relationships</p><h3 id="patterns-question">Account activity patterns</h3>${s.patterns.length?s.patterns.map(p=>`<p><span class="pattern-chip">${esc(p.label)}</span> ${esc(p.description)}</p>`).join(''):'<p>No fan-in, fan-out or chronological cycle found in the displayed transfers.</p>'}<p class="muted">These describe observed account relationships. They do not prove fraud and do not automatically mean they affected the model score.</p></section>
 <section class="section"><p class="eyebrow">Model sensitivity</p><h3>What would have changed the result?</h3><p>${esc(cf.sentence)}</p>${alternative}<p class="muted">${cf.note}</p></section>
 <section class="section label-comparison"><p class="eyebrow">Independent evaluation</p><h3>Dataset label and model outcome</h3><p>Dataset label: <strong>${s.evaluation.label}</strong> · ${s.evaluation.status}. Dataset labels are evaluation evidence, separate from the model decision.</p><p class="muted">The score is not a calibrated probability of fraud. This explanation describes measured model behavior.</p></section></div>`;
}
function renderSimpleExplanation(x,s){
 return `<div class="investigator-summary" data-view="simple"><div class="investigation-hero">${renderNetwork(x)}${renderHeroExplanation(s)}</div>${renderFollowupExplanation(x,s)}</div>`;
}
function renderNetwork(x){
 const story=x.transaction_story;
 return `<section class="hero-network" aria-labelledby="network-question"><h3 class="eyebrow" id="network-question">Transaction network</h3><p class="network-meta">${story.accounts.length} accounts <span aria-hidden="true">·</span> ${story.transfers.length} displayed transfers <span class="selected-tx">Selected TX ${esc(x.transaction_id)}</span></p>${flowDiagram(story)}<div class="graph-legend" aria-label="Network legend"><span class="legend-selected">Selected transaction</span><span class="legend-context">Earlier observed transfer</span><span class="legend-up">Earlier transfer that raised score</span><span class="legend-down">Earlier transfer that lowered score</span><span class="legend-neutral">Tested: negligible effect</span></div><p class="network-disclaimer">Connections show recorded activity. A connection does not by itself mean it influenced the model or indicates fraud.</p><aside id="graph-inspector" class="graph-inspector" aria-live="polite"><h4>Explore this network</h4><p>Select an account or transfer to see its details and any verified score test.</p></aside></section>`;
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
 <h3>I. Raw audit record</h3><details class="raw-audit"><summary>View raw audit record</summary><p>Bank names use display aliases here. Saved provenance retains canonical identifiers.</p><pre>${esc(JSON.stringify(x,null,2))}</pre></details></details>`;
}
function renderCaseComparison(summary){
 const known=summary.evaluation.label!=='Not recorded';
 const title=summary.evaluation.status.replace(' (false negative)','').toUpperCase();
 const sentence=known?`Model ${summary.decision.flagged?'flagged':'did not flag'} this transaction${['True positive','True negative'].includes(summary.evaluation.status)?' and':', but'} the dataset label is ${summary.evaluation.label}.`:'The independent dataset label is unavailable.';
 return `<section class="case-comparison" aria-label="Independent evaluation comparison"><p class="eyebrow">INDEPENDENT EVALUATION COMPARISON</p><h3>${esc(title)}</h3><p>${esc(sentence)}</p><small>The dataset label did not determine the model prediction.</small></section>`;
}
function render(x){
 const s=ExplanationSummary.summarize(x),event=x.transaction_story.selected_transfer;
 $('#detail').innerHTML=`<div class="transaction-heading"><div><p class="eyebrow bank">${esc(BankDisplay.label(x.bank))}</p><h2>Transaction ${esc(x.transaction_id)}</h2></div><a class="picker-link" href="${options.embedded?'#xaibank':'#bank'}">Find another transaction</a><a class="depth-link" href="#technical-explanation" id="open-technical">In-depth explanation ↗</a></div><p class="intro">Account ${esc(event.source_account_id)} sent ${amount(event)} to account ${esc(event.target_account_id)} using ${esc(event.payment_method)}.</p>${renderCaseComparison(s)}${renderSimpleExplanation(x,s)}${readableTechnicalDetails(x)}`;
 attachGraphInteractions(x.transaction_story,x.prediction);
 if(typeof matchMedia==='function'&&matchMedia('(max-width:1000px)').matches)$('#detail').scrollIntoView({block:'start'});
 if(options.embedded){
  const context=document.createElement('p');context.className='model-context';context.textContent=BankDisplay.text(`Replay model: ${x.xai_provenance.selected_model.version} · ${x.model.model_count} ${x.model.model_count===1?'model':'models'}`);
  $('#detail').querySelector('.intro').after(context);
  $('.picker-link')?.addEventListener('click',()=>options.onBrowse?.());
 }
 const open=()=>{$('#technical-explanation').open=true};
 $('#open-technical').addEventListener('click',open);
 $('#see-history')?.addEventListener('click',()=>{open();$('#technical-history').scrollIntoView({behavior:'smooth',block:'start'})});
}
function graphEdgeDetails(event,effect,prediction){
 const tested=event.kind==='earlier'&&effect;
 const status=tested?(effect.score_support>1e-6?'Helped raise the score':effect.score_support< -1e-6?'Helped lower the score':'Tested change was too small to measure clearly'):'';
 const scoreLabel=event.kind==='selected'?'Model score':'Selected transaction’s model score';
 return `<h4>Transaction ${esc(event.transaction_id)}</h4><p>Account ${esc(event.source_account_id)} → ${esc(event.target_account_id)}</p><p>${time(event.timestamp)}<br>${amount(event)}<br>${esc(event.payment_method)}</p>${status?`<p class="inspector-effect"><strong>${status}</strong></p>`:''}<p>${scoreLabel}: ${score(prediction.probability)}</p>${tested?`<div class="inspector-scores"><p>Original score: <strong title="${exact(effect.original_model_score)}">${score(effect.original_model_score)}</strong></p><p>Without its history update: ${score(effect.model_score_without_event)}</p><p>Measured difference: <strong>${effect.score_support>0?'+':''}${displayScore(effect.score_support)}</strong></p></div><p class="muted">Earlier account memory is retained. Full replay scope and exact scores are in the in-depth explanation.</p>`:event.kind==='earlier'?'<p class="muted">Observed transfer; its score effect was not measured.</p>':''}`;
}
function attachGraphInteractions(story,prediction){
 const panel=$('#graph-inspector');
 const effects=new Map((story.model_link_effects||[]).map(effect=>[String(effect.transaction_id),effect]));
 function markSelected(kind,id){
  all('[data-edge],[data-account]').forEach(element=>element.setAttribute('aria-pressed',String(element.dataset[kind]===String(id))));
 }
 function inspectEdge(id){
  const event=story.transfers.find(event=>String(event.transaction_id)===String(id));
  if(!event)return;
  const effect=effects.get(String(id));
  panel.innerHTML=graphEdgeDetails(event,effect,prediction);
  markSelected('edge',id);
 }
 function inspectAccount(id){
  const account=story.accounts.find(account=>String(account.account_id)===String(id));
  const related=story.transfers.filter(event=>String(event.source_account_id)===String(id)||String(event.target_account_id)===String(id));
  markSelected('account',id);
  panel.innerHTML=`<h4>Account ${esc(id)}</h4><p>${esc(account?.role)} · ${related.length} displayed transfers</p><p>Connections describe recorded activity; they do not identify account ownership, payment purpose, or fraud.</p>${related.map(event=>`<button class="inspect-transfer" data-inspect-edge="${esc(event.transaction_id)}">Inspect TX ${esc(event.transaction_id)}</button>`).join('')}`;
  panel.querySelectorAll('[data-inspect-edge]').forEach(button=>button.addEventListener('click',()=>inspectEdge(button.dataset.inspectEdge)));
 }
 all('[data-edge],[data-account]').forEach(element=>{
  const activate=()=>element.dataset.edge?inspectEdge(element.dataset.edge):inspectAccount(element.dataset.account);
  element.addEventListener('click',activate);
  element.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();activate()}});
 });
}
function bindStandalone(){
function reset(){currentPage=0;loadRows()}
bank.addEventListener('change',()=>{requestSequence++;selected=null;query.value='';history.replaceState(null,'','?bank='+encodeURIComponent(bank.value));$('#detail').innerHTML='<div class="empty"><h2>Select a transaction from this bank</h2></div>';reset()});view.addEventListener('change',reset);
query.addEventListener('input',()=>{clearTimeout(debounce);debounce=setTimeout(reset,220)});
$('#prev').addEventListener('click',()=>{if(currentPage){currentPage--;loadRows()}});
$('#next').addEventListener('click',()=>{if((currentPage+1)*pageSize<total){currentPage++;loadRows()}});
}
async function init(){try{const data=await json('/api/meta');currentManifest=data.manifest;bank.innerHTML=data.banks.map(value=>`<option value="${escapeHTML(value)}">${esc(BankDisplay.label(value))}</option>`).join('');const params=new URLSearchParams(location.search);if(params.has('bank')&&!data.banks.includes(params.get('bank')))throw Error('Unknown bank in transaction link.');if(data.banks.includes(params.get('bank')))bank.value=params.get('bank');const id=params.get('transaction_id');if(id){query.value=id;view.value='all'}await loadRows();if(id)await loadExplanation(id)}catch(error){$('#detail').innerHTML=`<p class="error">${esc(error.message)}</p>`}}
function validateReplay(x,selection){
 const fail=message=>{throw Error('Explanation refused: '+message)};
 if(!selection||x.replay_id!==selection.replay_id||x.bank!==selection.bank||String(x.transaction_id)!==String(selection.transaction_id))fail('the report belongs to another replay or transaction.');
 if(x.model.checkpoint_sha256!==selection.model_sha256||x.model.model_count!==selection.model_count||x.model.family!==selection.model_family||x.replay_provenance?.dataset_fingerprint!==selection.dataset_fingerprint)fail('the selected replay model or data differs.');
 if((x.xai_provenance.privacy_mode!=='none')!==selection.private_model)fail('the selected replay privacy scope differs.');
 if(!Number.isFinite(selection.score)||Math.abs(x.prediction.probability-selection.score)>1e-6||Math.abs(x.feature_explanation.target_probability-selection.score)>1e-6)fail('the explanation score differs from the saved replay by more than 1e-6. Rescore this model.');
 if(x.prediction.threshold!==selection.threshold)fail('the saved replay cutoff differs.');
 if(selection.evaluation_label&&x.evaluation_label!==selection.evaluation_label)fail('the independent dataset label differs.');
}
return {render,validateExplanation,loadRows,loadExplanation,graphEdgeDetails,readableTechnicalDetails,observedPatterns,renderSimpleExplanation,
 networkLayout,networkEdgeClass,flowDiagram,renderNetwork,renderCaseComparison,attachGraphInteractions,setManifest:value=>currentManifest=value,
 init:()=>{bindStandalone();return init()},
 renderVerified:(report,selection)=>{validateExplanation(report,selection.bank,selection.transaction_id);validateReplay(report,selection);render(report)},validateReplay};
}
global.InvestigatorXAI={create};
if(global.document?.currentScript?.hasAttribute('data-standalone'))create().init();
})(globalThis);
