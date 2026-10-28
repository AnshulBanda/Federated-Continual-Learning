/* One inline investigator view, bound to the explicitly selected completed replay. */
(function(global){
'use strict';
function create(options){
 const document=options.document||global.document,$=id=>document.getElementById(id);
 const component=options.component||global.InvestigatorXAI.create({scope:$('xaireport'),detail:$('xaireport'),embedded:true,onBrowse:()=>{$('xaibrowser').open=true;$('xaibank').focus()}});
 const fetchJSON=options.json|| (async url=>{const r=await fetch(url),data=await r.json();if(!r.ok)throw Error(data.error||'Explanation unavailable.');return data});
 let bank=null,replay=null,selection=null,receipt=null,sequence=0,pollSequence=0,rendered=null,loading=null;
 const option=(value,label)=>{const e=document.createElement('option');e.value=value;e.textContent=label;return e};
 function clear(){sequence++;pollSequence++;selection=null;receipt=null;rendered=null;loading=null;$('xaireport').hidden=true;$('xaireport').replaceChildren()}
 function syncBank(){
  const current=options.getBank();
  if(bank!==current){bank=current;replay=null;clear();$('xaibrowser').open=true;$('xaitransaction').value='';$('xaireplay').replaceChildren();$('xaitransactions').replaceChildren()}
  if(!$('xaibank').options.length){$('xaibank').append(option('','Choose a bank'));for(const [value,label] of Object.entries(options.banks))$('xaibank').append(option(value,label))}
  $('xaibank').value=bank||'';return bank;
 }
 function suggestions(){
  const query=$('xaitransaction').value.trim();$('xaitransactions').replaceChildren();
  for(const row of (replay?.rows||[]).filter(r=>r.txn_id.includes(query)).slice(0,50))$('xaitransactions').append(option(row.txn_id,`${row.txn_id} · score ${Number(row.score).toFixed(4)}`));
 }
 async function refreshReplays(){
  if(!syncBank())return;
  const expectedBank=bank,stamp=sequence,data=await fetchJSON('/api/monitoring');
  if(expectedBank!==options.getBank()||stamp!==sequence)return;
  const selected=replay?.replay_id||$('xaireplay').value;$('xaireplay').replaceChildren();
  for(const job of data.jobs.filter(j=>j.status==='Completed'&&j.bank===bank))$('xaireplay').append(option(job.id,`${job.model.version} · ${job.started}`));
  if([...$('xaireplay').options].some(o=>o.value===selected))$('xaireplay').value=selected;
 }
 async function loadReplay(){
  syncBank();clear();replay=null;const stamp=sequence,expectedBank=bank,id=$('xaireplay').value;
  if(!id){$('xainotice').textContent='Complete a replay in Transactions first.';return}
  try{const data=await fetchJSON('/api/monitoring/rows/'+encodeURIComponent(id));
   if(stamp!==sequence||expectedBank!==options.getBank())return;
   if(data.bank!==expectedBank||data.replay_id!==id)throw Error('The replay belongs to a different bank.');
   replay=data;$('xaitransaction').value='';suggestions();$('xainotice').textContent=`Replay model: ${data.model.version}. Choose a transaction; its saved review cutoff will be used.`;
  }catch(error){if(stamp===sequence)$('xainotice').textContent=error.message}
 }
 async function request(row,data){
  syncBank();clear();const stamp=sequence,expectedBank=bank;
  options.openTab('explanations');$('xaibrowser').open=false;
  if(!data||data.bank!==bank||!data.replay_id){$('xainotice').textContent='Load a completed replay for the current bank in Transactions first.';return}
  replay=data;$('xaitransaction').value=row.txn_id;suggestions();
  selection={bank,transaction_id:String(row.txn_id),replay_id:data.replay_id,model_sha256:data.model.sha256,
   model_count:data.member_count,model_family:data.model.model_kind,private_model:!!data.model.privacy?.differential_privacy,score:row.score,threshold:data.threshold,dataset_fingerprint:data.dataset_fingerprint};
  if(!selection.dataset_fingerprint){$('xainotice').textContent='This replay is missing verified data identity. Load a new completed replay.';selection=null;return}
  $('xainotice').textContent=`Preparing transaction ${row.txn_id} using replay model ${data.model.version}…`;
  refreshReplays().catch(()=>{});
  try{const job=await options.post('/api/explanations/start',{replay_id:data.replay_id,txn_id:String(row.txn_id)});
   if(stamp!==sequence||expectedBank!==options.getBank())return;
   receipt=job;await refresh();
  }catch(error){if(stamp===sequence)$('xainotice').textContent='Explanation unavailable: '+error.message}
 }
 async function explainSelected(){
  const requested=$('xaitransaction').value.trim();
  if(!replay||replay.replay_id!==$('xaireplay').value)await loadReplay();
  $('xaitransaction').value=requested;
  const row=replay?.rows.find(r=>r.txn_id===requested);
  if(!row){$('xainotice').textContent='Choose an existing transaction ID from the selected replay.';return}
  return request(row,replay);
 }
 async function refresh(){
  syncBank();const stamp=sequence,poll=++pollSequence,expectedBank=bank;
  if(!selection||!receipt){try{await refreshReplays();if(!selection)$('xainotice').textContent='Choose a scored transaction from a completed replay.'}catch(e){$('xainotice').textContent=e.message}return}
  try{const data=await fetchJSON('/api/explanations');
   if(stamp!==sequence||poll!==pollSequence||expectedBank!==options.getBank())return;
   const job=data.jobs.find(j=>j.id===receipt.id)||receipt;
   if(job.bank!==selection.bank||job.replay_id!==selection.replay_id||String(job.txn_id)!==selection.transaction_id)throw Error('The explanation job belongs to another selected transaction.');
   receipt=job;if(rendered===job.id&&job.status==='Completed')return;
   $('xainotice').textContent=`${job.status} · ${job.txn_id} · ${job.detail}`;
   if(job.status==='Failed'||job.status==='Interrupted'){$('xaireport').hidden=true;return}
   if(job.status!=='Completed')return;
   if(!job.report_ready)throw Error('This older explanation is not compatible. Request it again.');
   if(rendered===job.id||loading===job.id)return;
   loading=job.id;const report=await fetchJSON('/api/explanations/report/'+encodeURIComponent(job.id));
   if(stamp!==sequence||expectedBank!==options.getBank())return;
   $('xaireport').hidden=false;component.renderVerified(report,selection);rendered=job.id;
   $('xainotice').textContent=`Verified transaction ${job.txn_id} · replay model ${job.model.version} · saved replay cutoff ${Number(selection.threshold).toFixed(4)}. This view uses that replay, even if a different model is now selected.`;
  }catch(error){if(stamp===sequence){$('xaireport').hidden=true;$('xainotice').textContent='Explanation unavailable: '+error.message}}
  finally{if(stamp===sequence)loading=null}
 }
 function bind(){
  $('xaibank').addEventListener('change',async()=>{clear();try{await options.setBank($('xaibank').value);syncBank();await refreshReplays();$('xainotice').textContent='Choose a completed replay for this bank.'}catch(e){$('xainotice').textContent=e.message}});
  $('xaireplay').addEventListener('change',loadReplay);$('xaitransaction').addEventListener('input',suggestions);
  $('xaiexplain').addEventListener('click',explainSelected);$('xairefresh').addEventListener('click',refresh);
 }
 bind();return {request,refresh,loadReplay,refreshReplays,explainSelected,clear};
}
global.ReplayInvestigator={create};
})(globalThis);
