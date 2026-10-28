/* Inline investigator selection; saved model results and independent labels stay separate. */
(function(global){
'use strict';
const finite=value=>typeof value==='number'&&Number.isFinite(value)&&value>=0&&value<=1;
function filterRows(rows,threshold,modelResult='flagged',actualLabel='all'){
 if(!finite(threshold))throw Error('The saved replay cutoff is unavailable.');
 if(!['flagged','not_flagged','all'].includes(modelResult)||!['fraud','not_fraud','all'].includes(actualLabel))throw Error('Choose valid investigation filters.');
 if(rows.some(r=>typeof r.txn_id!=='string'||!r.txn_id.trim()||!finite(r.score)||!['fraud','not_fraud'].includes(r.evaluation_label)))throw Error('Verified replay scores and independent dataset labels are required.');
 return rows.filter(r=>(modelResult==='all'||(r.score>=threshold)===(modelResult==='flagged'))&&(actualLabel==='all'||r.evaluation_label===actualLabel))
  .sort((a,b)=>(modelResult==='not_flagged'?a.score-b.score:b.score-a.score)||(String(a.txn_id)<String(b.txn_id)?-1:String(a.txn_id)>String(b.txn_id)?1:0));
}
function sameReplay(data,bank,id,expected){
 if(data.bank!==bank||data.replay_id!==id||!data.dataset_fingerprint||!data.model?.sha256||![1,3].includes(data.member_count)||!data.model.model_kind||!Array.isArray(data.rows))throw Error('The replay belongs to a different bank or has incomplete identity.');
 if(expected&&(data.model.sha256!==expected.model.sha256||data.model.model_kind!==expected.model.model_kind||data.member_count!==expected.member_count||data.threshold!==expected.threshold||data.dataset_fingerprint!==expected.dataset_fingerprint))throw Error('The selected replay model, cutoff or data differs.');
 filterRows(data.rows,data.threshold,'all','all');
 if(new Set(data.rows.map(r=>String(r.txn_id))).size!==data.rows.length)throw Error('Replay transaction IDs are ambiguous.');
 return data;
}
function create(options){
 const document=options.document||global.document,$=id=>document.getElementById(id),display=global.BankDisplay;
 const component=options.component||global.InvestigatorXAI.create({scope:$('xaireport'),detail:$('xaireport'),embedded:true,onBrowse:()=>{$('xaibrowser').open=true;$('xaibank').focus()}});
 const fetchJSON=options.json||(async url=>{const r=await fetch(url),data=await r.json();if(!r.ok)throw Error(display.text(data.error||'Explanation unavailable.'));return data});
 let bank=null,replay=null,selection=null,receipt=null,sequence=0,pollSequence=0,rendered=null,loading=null,listSignature=null,starting=false;
 const notice=value=>$('xainotice').textContent=display.text(value);
 const option=(value,label)=>{const e=document.createElement('option');e.value=value;e.textContent=display.text(label);return e};
 function clear(){sequence++;pollSequence++;selection=null;receipt=null;rendered=null;loading=null;starting=false;$('xaireport').hidden=true;$('xaireport').replaceChildren()}
 function emptyChoices(){$('xaitransaction').replaceChildren();$('xaitransaction').value='';$('xaitransaction').disabled=true;$('xaiexplain').disabled=true;$('xaicount').textContent=''}
 function syncBank(){
  const current=options.getBank();
  if(bank!==current){bank=current;replay=null;listSignature=null;clear();$('xaibrowser').open=true;$('xaireplay').replaceChildren();$('xaireplay').value='';emptyChoices();$('xaimodelresult').value='flagged';$('xaiactuallabel').value='all'}
  if(!$('xaibank').options.length){$('xaibank').append(option('','Choose a bank'));for(const id of Object.keys(options.banks))$('xaibank').append(option(id,display.label(id)))}
  $('xaibank').value=bank||'';return bank;
 }
 function choices(preferred=$('xaitransaction').value){
  emptyChoices();if(!replay)return;
  const rows=filterRows(replay.rows,replay.threshold,$('xaimodelresult').value,$('xaiactuallabel').value);
  for(const row of rows)$('xaitransaction').append(option(String(row.txn_id),`TX ${row.txn_id} · ${row.score>=replay.threshold?'Flagged':'Not flagged'} · Actual ${row.evaluation_label==='fraud'?'fraud':'not fraud'} · ${row.score.toFixed(4)}`));
  $('xaitransaction').value=rows.some(r=>String(r.txn_id)===preferred)?preferred:String(rows[0]?.txn_id||'');
  $('xaitransaction').disabled=!rows.length;$('xaiexplain').disabled=!rows.length;
  $('xaicount').textContent=rows.length?`${rows.length.toLocaleString()} matching transactions · saved review cutoff ${replay.threshold.toFixed(4)}`:'No transactions match these filters.';
  notice(rows.length?'Choose a transaction, then Explain selected transaction.':'No transactions match these filters.');
 }
 async function loadReplay(){
  syncBank();clear();replay=null;emptyChoices();const stamp=sequence,expectedBank=bank,id=$('xaireplay').value;
  if(!id){notice('Complete a replay in Transactions first.');return}
  notice('Loading saved replay scores and independent dataset labels…');
  try{const data=await fetchJSON('/api/explanations/cases/'+encodeURIComponent(id));
   if(stamp!==sequence||expectedBank!==options.getBank())return;
   replay=sameReplay(data,expectedBank,id);choices();
  }catch(error){if(stamp===sequence)notice(error.message)}
 }
 async function refreshReplays(){
  if(!syncBank()){notice('Choose and save a bank first.');return}
  const expectedBank=bank,stamp=sequence,data=await fetchJSON('/api/monitoring');
  if(expectedBank!==options.getBank()||stamp!==sequence)return;
  const jobs=data.jobs.filter(j=>j.status==='Completed'&&j.bank===bank),signature=JSON.stringify(jobs.map(j=>[j.id,j.model.version]));
  if(signature!==listSignature){
   const selected=replay?.replay_id||$('xaireplay').value;$('xaireplay').replaceChildren();
   for(const job of jobs)$('xaireplay').append(option(job.id,`${job.model.version} · ${job.started}`));
   $('xaireplay').value=jobs.some(j=>j.id===selected)?selected:(jobs[0]?.id||'');listSignature=signature;
  }
  if(!jobs.length){replay=null;emptyChoices();notice('Complete a replay in Transactions first.');return}
  if(!replay||replay.replay_id!==$('xaireplay').value)await loadReplay();
 }
 async function request(row,data,fromBrowser=false){
  syncBank();clear();const stamp=sequence,expectedBank=bank;
  options.openTab('explanations');$('xaibrowser').open=false;
  if(!data||data.bank!==bank||!data.replay_id){notice('Load a completed replay for the current bank in Transactions first.');return}
  if(!data.dataset_fingerprint){notice('This replay is missing verified data identity. Load a new completed replay.');return}
  starting=true;notice(`Preparing transaction ${row.txn_id} using replay model ${data.model.version}…`);
  try{
   const cases=replay?.replay_id===data.replay_id?replay:await fetchJSON('/api/explanations/cases/'+encodeURIComponent(data.replay_id));
   if(stamp!==sequence||expectedBank!==options.getBank())return;
   replay=sameReplay(cases,expectedBank,data.replay_id,data);$('xaireplay').value=data.replay_id;
   const exact=replay.rows.find(r=>String(r.txn_id)===String(row.txn_id));
   if(!exact||!finite(row.score)||exact.score!==row.score)throw Error('The selected transaction score differs from the saved replay.');
   if(!fromBrowser){$('xaimodelresult').value=row.score>=data.threshold?'flagged':'not_flagged';$('xaiactuallabel').value='all'}
   choices(String(row.txn_id));
   selection={bank,transaction_id:String(row.txn_id),replay_id:data.replay_id,model_sha256:data.model.sha256,model_count:data.member_count,
    model_family:data.model.model_kind,private_model:!!data.model.privacy?.differential_privacy,score:row.score,threshold:data.threshold,
    dataset_fingerprint:data.dataset_fingerprint,evaluation_label:exact.evaluation_label};
   notice(`Preparing transaction ${row.txn_id} using replay model ${data.model.version}…`);
   await refreshReplays();
   if(stamp!==sequence||expectedBank!==options.getBank())return;
   const job=await options.post('/api/explanations/start',{replay_id:data.replay_id,txn_id:String(row.txn_id)});
   if(stamp!==sequence||expectedBank!==options.getBank())return;
   receipt=job;starting=false;await refresh();
  }catch(error){if(stamp===sequence)notice('Explanation unavailable: '+error.message)}
  finally{if(stamp===sequence)starting=false}
 }
 async function explainSelected(){
  if(!replay||replay.replay_id!==$('xaireplay').value)await loadReplay();
  const id=$('xaitransaction').value,row=replay?.rows.find(r=>String(r.txn_id)===id);
  if(!row){notice('No transactions match these filters.');return}
  return request(row,replay,true);
 }
 async function refresh(){
  syncBank();if(starting)return;
  const stamp=sequence,poll=++pollSequence,expectedBank=bank;
  if(!selection||!receipt){try{await refreshReplays()}catch(e){notice(e.message)}return}
  try{const data=await fetchJSON('/api/explanations');
   if(stamp!==sequence||poll!==pollSequence||expectedBank!==options.getBank())return;
   const job=data.jobs.find(j=>j.id===receipt.id)||receipt;
   if(job.bank!==selection.bank||job.replay_id!==selection.replay_id||String(job.txn_id)!==selection.transaction_id)throw Error('The explanation job belongs to another selected transaction.');
   receipt=job;if(rendered===job.id&&job.status==='Completed')return;
   notice(`${job.status} · ${job.txn_id} · ${job.detail}`);
   if(job.status==='Failed'||job.status==='Interrupted'){$('xaireport').hidden=true;return}
   if(job.status!=='Completed')return;
   if(!job.report_ready)throw Error('This older explanation is not compatible. Request it again.');
   if(rendered===job.id||loading===job.id)return;
   loading=job.id;const report=await fetchJSON('/api/explanations/report/'+encodeURIComponent(job.id));
   if(stamp!==sequence||expectedBank!==options.getBank())return;
   component.renderVerified(report,selection);$('xaireport').hidden=false;rendered=job.id;
   notice(`Verified transaction ${job.txn_id} · replay model ${job.model.version} · saved replay cutoff ${Number(selection.threshold).toFixed(4)}. This view uses that replay, even if a different model is now selected.`);
  }catch(error){if(stamp===sequence){$('xaireport').hidden=true;notice('Explanation unavailable: '+error.message)}}
  finally{if(stamp===sequence)loading=null}
 }
 function bind(){
  $('xaimodelresult').value='flagged';$('xaiactuallabel').value='all';emptyChoices();
  $('xaibank').addEventListener('change',async()=>{clear();try{await options.setBank($('xaibank').value);syncBank();await refreshReplays()}catch(e){notice(e.message)}});
  $('xaireplay').addEventListener('change',loadReplay);
  for(const id of ['xaimodelresult','xaiactuallabel'])$(id).addEventListener('change',()=>{clear();choices()});
  $('xaitransaction').addEventListener('change',()=>{clear();notice('Choose Explain selected transaction to review this case.')} );
  $('xaiexplain').addEventListener('click',explainSelected);$('xairefresh').addEventListener('click',refresh);
 }
 bind();return {request,refresh,loadReplay,refreshReplays,explainSelected,clear};
}
global.ReplayInvestigator={create,filterRows,sameReplay};
})(globalThis);
