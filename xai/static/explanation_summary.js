/* Deterministic evidence → presentation. No network, model inference, or generated prose. */
(function(root, factory) {
 'use strict';
 const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 else root.ExplanationSummary=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const negligible=1e-8, parity=1e-6;
 const finite=value=>typeof value==='number'&&Number.isFinite(value);
 const label=f=>f.feature==='transfer_terms'?'Amount and currencies':f.feature==='payment_method'?'Payment method':f.label||f.feature.replaceAll('_',' ');
 const fields=f=>Object.fromEntries(String(f.value).split(' / ').map(part=>{const i=part.indexOf(': ');return [part.slice(0,i),part.slice(i+2)]}));
 const number=value=>Number(value).toLocaleString('en-US',{maximumFractionDigits:2});
 function observed(f){
  if(f.feature!=='transfer_terms')return String(f.value??'Not recorded').replace(/^payment_format:\s*/,'');
  const v=fields(f),term=(a,c)=>finite(Number(a))?`${number(a)} ${c||''}`.trim():'Not recorded';
  return `Sent ${term(v.amount,v.currency)}; received ${term(v.Amount_Received,v.Receiving_Currency)}`;
 }
 function modelScope(x){
  const p=x.xai_provenance||{},mode=p.privacy_mode??x.model?.privacy_mode;
  if(mode==='none')return p.model_role==='verified_selected'?'Non-private selected model':'Non-private reference model';
  if(['level3','level_3','level3_decoder_private'].includes(mode)&&p.model_count===1)return 'Level-3 DP federated model';
  return 'Model privacy scope not established';
 }
 function observedPatterns(story){
  const key=(event,side)=>String(event[side+'_account_id']??event[side]);
  const selected=story.selected_transfer,source=key(selected,'source'),target=key(selected,'target');
  const when=event=>Date.parse(String(event.timestamp).replace(' ','T'));
  const earlier=(story.transfers||[]).filter(event=>event.kind==='earlier'&&when(event)<when(selected));
  const events=[...earlier,selected],patterns=[];
  const senders=new Set(events.filter(e=>key(e,'target')===target&&key(e,'source')!==target).map(e=>key(e,'source')));
  const recipients=new Set(events.filter(e=>key(e,'source')===source&&key(e,'target')!==source).map(e=>key(e,'target')));
  if(senders.size>=3)patterns.push({label:'Fan-in',description:`The receiving account received transfers from ${senders.size} different counterparties in the displayed history, including this transaction.`});
  if(recipients.size>=3)patterns.push({label:'Fan-out',description:`The sending account transferred to ${recipients.size} different counterparties in the displayed history, including this transaction.`});
  function returnPath(node,lastTime,visited){
   for(const event of earlier){
    if(key(event,'source')!==node||when(event)<=lastTime)continue;
    const next=key(event,'target');
    if(next===source)return true;
    if(!visited.has(next)&&returnPath(next,when(event),new Set([...visited,next])))return true;
   }
   return false;
  }
  if(source!==target&&returnPath(target,-Infinity,new Set([target])))patterns.push({label:'Cycle',description:'Earlier transfers form a chronological return path that closes with this transaction.'});
  return patterns;
 }
 function verifiedEffects(x){
  const story=x.transaction_story,p=x.prediction,g=x.graph_explanation?.fidelity;
  if(!(Number(story.earlier_related_transfers_considered)>0)&&!story.transfers.some(e=>e.kind==='earlier'))return [];
  if(!g||!finite(g.original_probability)||Math.abs(g.original_probability-p.probability)>parity||!finite(g.unperturbed_replay_error)||Math.abs(g.unperturbed_replay_error)>parity)return [];
  const earlier=story.eligible_earlier_transfers||story.transfers.filter(e=>e.kind==='earlier');
  return (story.model_link_effects||[]).filter(e=>{
   const edge=x.graph_explanation?.important_edges?.find(t=>String(t.transaction_id)===String(e.transaction_id));
   // Legacy reports saved a bounded display, but retained the independently checked replay edge.
   const event=earlier.find(t=>String(t.transaction_id)===String(e.transaction_id))||(!story.eligible_earlier_transfers?edge:null);
   return event&&edge&&e.verified_model_count===x.model.model_count&&
    Date.parse(event.timestamp.replace(' ','T'))<Date.parse(story.selected_transfer.timestamp.replace(' ','T'))&&
    String(edge.source)===String(event.source)&&String(edge.target)===String(event.target)&&
    Date.parse(edge.timestamp.replace(' ','T'))===Date.parse(event.timestamp.replace(' ','T'))&&
    [e.original_model_score,e.model_score_without_event,e.score_support,edge.probability_without].every(finite)&&
    e.model_score_without_event>=0&&e.model_score_without_event<=1&&
    Math.abs(e.original_model_score-p.probability)<=parity&&
    Math.abs(e.model_score_without_event-edge.probability_without)<=parity&&
    Math.abs(e.score_support-(e.original_model_score-e.model_score_without_event))<=parity;
  }).sort((a,b)=>Math.abs(b.score_support)-Math.abs(a.score_support)||String(a.transaction_id).localeCompare(String(b.transaction_id)));
 }
 function summarize(x){
  const p=x.prediction,story=x.transaction_story;
  if(!p||![p.probability,p.threshold].every(finite)||!story)throw Error('Summary requires finite decision evidence and transaction history.');
  const flagged=p.probability>=p.threshold;
  const features=[...x.feature_explanation.features];
  if(!features.length||features.some(f=>!finite(f.shap_logit)))throw Error('Summary requires measured feature contributions.');
  features.sort((a,b)=>Math.abs(b.shap_logit)-Math.abs(a.shap_logit)||a.feature.localeCompare(b.feature));
  const largest=Math.max(...features.map(f=>Math.abs(f.shap_logit)));
  const factors=features.map(f=>{
   const v=f.shap_logit,ratio=largest?Math.abs(v)/largest:0,direction=Math.abs(v)<negligible?'neutral':v>0?'up':'down';
   const strength=direction==='neutral'?'No clear':ratio>=.67?'Strong':ratio>=.33?'Moderate':'Small';
   return {feature:f.feature,label:label(f),observed:observed(f),contribution:v,direction,strength,relative_size:ratio,
    effect:direction==='neutral'?'No clear measured effect':`${strength} ${direction==='up'?'upward':'downward'} effect`};
  });
  const primary=factors.find(f=>flagged?f.direction==='up':f.direction==='down');
  const subject=primary?.feature==='transfer_terms'?'The amount and currency combination':primary?`The ${primary.label.toLowerCase()}`:'';
  const primary_reason=primary?{...primary,sentence:`${subject} ${flagged?'was the strongest measured factor pushing the model score higher.':'was the strongest measured factor pushing the model score lower.'}`}:
   {feature:null,direction:'neutral',sentence:`No measured transaction feature group clearly pushed the score ${flagged?'higher':'lower'} relative to the comparison examples. The comparison starting point and fixed account history also contribute to the score; see the in-depth explanation.`};
  const earlier=story.transfers.filter(e=>e.kind==='earlier'),effects=verifiedEffects(x);
  const hasHistory=Number(story.earlier_related_transfers_considered)>0||earlier.length>0;
  const strongest=effects[0]||null;
  const history_summary={status:!hasHistory?'none':!effects.length?'untested':'tested',strongest,tested_count:effects.length,
   sentence:!hasHistory?'No earlier eligible transfers involving these accounts were available to the model before this prediction.':!effects.length?'Earlier transfers were observed, but their effect on this prediction was not measured.':
    strongest.score_support>0?`TX ${strongest.transaction_id}: this earlier transfer helped push the current score higher.`:strongest.score_support<0?`TX ${strongest.transaction_id}: this earlier transfer helped keep the current score lower.`:`TX ${strongest.transaction_id}: the tested earlier transfer did not change the current score.`};
  const cf=x.counterfactual_explanation||{},tested=cf.tested_alternatives||cf.counterfactuals||[];
  const valid=tested.filter(c=>c.valid===true&&finite(c.counterfactual_probability)&&c.counterfactual_probability>=0&&c.counterfactual_probability<=1&&
   finite(c.changed_features?.amount??c.changed_features?.Amount_Received)&&finite(c.original_probability)&&Math.abs(c.original_probability-p.probability)<=parity&&finite(cf.threshold)&&Math.abs(cf.threshold-p.threshold)<=1e-12);
  const crossing=valid.find(c=>(c.counterfactual_probability>=p.threshold)!==flagged)||null;
  const completeTests=Array.isArray(cf.tested_alternatives)&&valid.length===cf.candidates_evaluated&&valid.length>0;
  const verifiedNoFlip=cf.status==='no_threshold_flip_found'&&finite(cf.original_probability)&&Math.abs(cf.original_probability-p.probability)<=parity&&finite(cf.threshold)&&Math.abs(cf.threshold-p.threshold)<=1e-12;
  const counterfactual_summary={alternative:crossing,crossed:!!crossing,available_count:valid.length,
   sentence:crossing?`In the tested model-sensitivity check, changing the transfer amount to approximately ${number(crossing.changed_features.amount??crossing.changed_features.Amount_Received)} ${story.selected_transfer.currency} moved the score ${flagged?'below':'at or above'} the review cutoff.`:
    completeTests||verifiedNoFlip?'None of the tested amount changes moved the model across the review cutoff.':'No verified amount alternative that changes the decision is available for this transaction.',
   note:'This is a model-sensitivity test, not a recommendation for transaction behavior.'};
  const known=x.evaluation_label==='fraud',hasLabel=['fraud','not_fraud'].includes(x.evaluation_label);
  return {decision:{flagged,score:p.probability,threshold:p.threshold,margin:p.probability-p.threshold},primary_reason,
   top_factors:factors.slice(0,3),history_summary,patterns:observedPatterns(story),counterfactual_summary,model_scope:modelScope(x),
   evaluation:{label:hasLabel?(known?'Fraud':'Not fraud'):'Not recorded',status:!hasLabel?'Dataset label unavailable':flagged?(known?'True positive':'False positive'):(known?'Missed fraud (false negative)':'True negative')}};
 }
 return {summarize,observedPatterns,verifiedEffects,modelScope};
});
