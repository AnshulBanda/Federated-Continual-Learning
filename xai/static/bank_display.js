/* Display aliases only. Canonical identifiers and saved evidence stay unchanged. */
(function(root,factory){
 'use strict';const api=factory();
 if(typeof module==='object'&&module.exports)module.exports=api;
 else root.BankDisplay=api;
})(typeof globalThis!=='undefined'?globalThis:this,function(){
 'use strict';
 const names=Object.freeze({Key_Bank:'Bank A',Wells_Fargo:'Bank B',JPMorgan_Chase:'Bank C'});
 const aliases=Object.entries(names).flatMap(([id,name])=>[[id,name],[id.replaceAll('_',' '),name]]);
 const pattern=new RegExp(aliases.map(([id])=>id).join('|'),'gi');
 const lookup=new Map(aliases.map(([id,name])=>[id.toLowerCase(),name]));
 const text=value=>String(value??'').replace(pattern,id=>lookup.get(id.toLowerCase()));
 const label=id=>names[id]||text(id);
 function sanitize(root){
  if(!root)return;
  if(root.nodeType===3){if(['SCRIPT','STYLE'].includes(root.parentElement?.tagName))return;const value=text(root.nodeValue);if(value!==root.nodeValue)root.nodeValue=value;return}
  if(root.nodeType!==1&&root.nodeType!==9&&root.nodeType!==11)return;
  if(['SCRIPT','STYLE'].includes(root.tagName))return;
  const bank=root.getAttribute?.('data-bank-label');
  if(bank&&root.textContent!==label(bank))root.textContent=label(bank);
  // Never rewrite option values, form values, IDs, URLs, data attributes or payloads.
  for(const key of ['title','aria-label','placeholder']){
   const value=root.getAttribute?.(key);
   if(value!=null&&text(value)!==value)root.setAttribute(key,text(value));
  }
  for(const child of root.childNodes||[])sanitize(child);
 }
 function observe(root){
  sanitize(root);
  const observer=new MutationObserver(records=>{
   for(const record of records){
    if(record.type==='childList')for(const child of record.addedNodes)sanitize(child);
    else sanitize(record.target);
   }
  });
  observer.observe(root,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['title','aria-label','placeholder']});
  return observer;
 }
 return Object.freeze({names,label,text,sanitize,observe});
});
